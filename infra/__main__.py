import pulumi
import os
import zipfile
import tempfile
import datetime
import atexit
import uuid
from pulumi_azure_native import (
    resources,
    servicebus,
    storage,
    web,
    authorization,
    containerinstance,
    containerregistry,
    operationalinsights,
    applicationinsights,
    communication,
    keyvault,
)
import pulumi_azuread as azuread

from pulumi_random import RandomPassword
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from azure.core.exceptions import ResourceNotFoundError

# Cosmos DB resources live in a separate module
from pulumi_azure_native import cosmosdb
from pulumi_azure_native.authorization import get_client_config, RoleAssignment
from pulumi_azure_native import dns

config = pulumi.Config()
location = config.get("location") or "centralindia"
openai_api_key = config.require_secret("openaiApiKey")
aad_client_id = config.require_secret("aadClientId")
aad_client_secret = config.require_secret("aadClientSecret")
aad_tenant_id = config.require("aadTenantId")
# Database credentials for the PostgreSQL container
postgres_user = config.get("postgresUser") or "gitea"
postgres_db = config.get("postgresDb") or "gitea"

# Resource names
resource_group_name = "lightning_dev-1"
vault_name = "lightning-vault"
# Worker image will be configured by GitHub Actions or default to ACR image
worker_image = config.get("workerImage") or "lightningacr.azurecr.io/worker-task:latest"
domain = config.get("domain") or "agentsmith.in"
acs_sender = config.get("acsSender") or f"no-reply@{domain}"

# Fetch subscription ID early so it can be used anywhere below
client_config = get_client_config()
subscription_id = client_config.subscription_id

# Azure Entra ID application used for authentication
aad_app = azuread.Application(
    "lightning-app",
    display_name="Lightning Chat",
    web=azuread.ApplicationWebArgs(
        redirect_uris=[pulumi.Output.concat("https://", domain, "/auth/callback")],
    ),
)

aad_sp = azuread.ServicePrincipal(
    "lightning-sp",
    client_id=aad_app.client_id,
)

aad_secret = azuread.ApplicationPassword(
    "lightning-secret",
    application_id=aad_app.id,
    end_date_relative="8760h",
)

pulumi.export("aadClientId", aad_app.client_id)
pulumi.export("aadClientSecret", aad_secret.value)
pulumi.export("aadTenantId", aad_tenant_id)

# Resource group
resource_group = resources.ResourceGroup(
    resource_group_name,
    resource_group_name=resource_group_name,
    location=location,
)

# Key Vault to store secrets
vault = keyvault.Vault(
    "vault",
    resource_group_name=resource_group.name,
    vault_name=vault_name,
    location=resource_group.location,
    properties=keyvault.VaultPropertiesArgs(
        tenant_id=client_config.tenant_id,
        sku=keyvault.SkuArgs(name=keyvault.SkuName.STANDARD, family="A"),
        access_policies=[
            keyvault.AccessPolicyEntryArgs(
                tenant_id=client_config.tenant_id,
                object_id=client_config.object_id,
                permissions=keyvault.PermissionsArgs(secrets=["get", "set", "list"]),
            )
        ],
    ),
)

# Retrieve existing secret or create a new one
credential = DefaultAzureCredential()
postgres_password: pulumi.Output[str]
try:
    secret_client = SecretClient(vault_url=f"https://{vault_name}.vault.azure.net/", credential=credential)
    existing = secret_client.get_secret("postgresPassword")
    postgres_password = pulumi.Output.secret(existing.value)
    secret_id = subscription_id.apply(
        lambda sid: f"/subscriptions/{sid}/resourceGroups/{resource_group_name}/providers/Microsoft.KeyVault/vaults/{vault_name}/secrets/postgresPassword"
    )
    postgres_password_secret_res = keyvault.Secret(
        "postgres-password-secret",
        resource_group_name=resource_group.name,
        vault_name=vault.name,
        secret_name="postgresPassword",
        opts=pulumi.ResourceOptions(import_=secret_id),
    )
except ResourceNotFoundError:
    postgres_password_secret_res = None
    postgres_password_secret = RandomPassword("postgres-password", length=16, special=True)
    postgres_password = postgres_password_secret.result
    postgres_password_secret_res = keyvault.Secret(
        "postgres-password-secret",
        resource_group_name=resource_group.name,
        vault_name=vault.name,
        secret_name="postgresPassword",
        properties=keyvault.SecretPropertiesArgs(value=postgres_password_secret.result),
    )


# Log Analytics Workspace for Application Insights
workspace = operationalinsights.Workspace(
    "log-workspace",
    resource_group_name=resource_group.name,
    workspace_name="lightning-logs",
    location=resource_group.location,
    sku=operationalinsights.WorkspaceSkuArgs(name="PerGB2018"),
    retention_in_days=30,
)

# Fetch Log Analytics workspace keys for container diagnostics
workspace_keys = operationalinsights.get_shared_keys_output(
    resource_group_name=resource_group.name,
    workspace_name=workspace.name,
)

# Application Insights instance
app_insights = applicationinsights.Component(
    "lightning-ai",
    resource_group_name=resource_group.name,
    kind="web",
    application_type="web",
    workspace_resource_id=workspace.id,
)

# Service Bus namespace and queue
namespace = servicebus.Namespace(
    "lightning-namespace",
    resource_group_name=resource_group.name,
    namespace_name="lightning-namespace",
    location=resource_group.location,
    sku=servicebus.SBSkuArgs(name="Standard", tier="Standard"),
)

queue = servicebus.Queue(
    "lightning-queue",
    resource_group_name=resource_group.name,
    namespace_name=namespace.name,
    queue_name="lightning-queue",
    enable_partitioning=True,
)


# Azure Communication Service and Email Service for sending emails
communication_service = communication.CommunicationService(
    "comm-service",
    resource_group_name=resource_group.name,
    communication_service_name="lightning-comm",
    data_location="United States",
    location="global",
)

# Separate EmailService resource is required for domain management
email_service = communication.EmailService(
    "email-service",
    resource_group_name=resource_group.name,
    email_service_name="lightning-email",
    data_location="United States",
    location="global",
)

#
# Email domain (agentsmith.in) already exists in the lightning‑email service.
# Tell Pulumi to adopt it instead of trying to create it.
email_domain = communication.Domain(
    "email-domain",
    resource_group_name=resource_group.name,
    email_service_name=email_service.name,
    domain_name=domain,
    domain_management=communication.DomainManagement.CUSTOMER_MANAGED,
    user_engagement_tracking=communication.UserEngagementTracking.DISABLED,
    location="global",
    opts=pulumi.ResourceOptions(
        # Import the pre‑existing resource so future `pulumi up` runs are idempotent
        import_=f"/subscriptions/{subscription_id}/resourceGroups/lightning_dev-1/providers/Microsoft.Communication/emailServices/lightning-email/domains/{domain}"
    ),
)

# (Optional) surface the domain in stack outputs
pulumi.export("emailDomainName", email_domain.domain_name)
comm_keys = communication.list_communication_service_keys_output(
    resource_group_name=resource_group.name,
    communication_service_name=communication_service.name,
)

pulumi.export("resourceGroupName", resource_group.name)
pulumi.export("serviceBusNamespaceName", namespace.name)
pulumi.export("queueName", queue.name)
pulumi.export("communicationConnectionString", comm_keys.primary_connection_string)
pulumi.export("emailServiceName", email_service.name)
pulumi.export("emailDomain", email_domain.from_sender_domain)
pulumi.export("emailVerificationRecords", email_domain.verification_records)
pulumi.export("appInsightsKey", app_insights.instrumentation_key)

# Storage account for Function App
storage_account = storage.StorageAccount(
    "funcsa",
    resource_group_name=resource_group.name,
    sku=storage.SkuArgs(name=storage.SkuName.STANDARD_LRS),
    kind=storage.Kind.STORAGE_V2,
)

# Separate storage account for Git repositories and database volumes
repo_storage_account = storage.StorageAccount(
    "giteasa",
    resource_group_name=resource_group.name,
    sku=storage.SkuArgs(name=storage.SkuName.STANDARD_LRS),
    kind=storage.Kind.STORAGE_V2,
)

# File shares used by Gitea and PostgreSQL containers
gitea_share = storage.FileShare(
    "gitea-share",
    account_name=repo_storage_account.name,
    resource_group_name=resource_group.name,
    share_name="gitea",
)

postgres_share = storage.FileShare(
    "postgres-share",
    account_name=repo_storage_account.name,
    resource_group_name=resource_group.name,
    share_name="postgres",
)

repo_storage_keys = storage.list_storage_account_keys_output(
    resource_group_name=resource_group.name,
    account_name=repo_storage_account.name,
)
repo_primary_key = repo_storage_keys.keys[0].value

# Azure Container Registry
acr = containerregistry.Registry(
    "lightning-acr",
    resource_group_name=resource_group.name,
    registry_name="lightningacr",
    location=resource_group.location,
    sku=containerregistry.SkuArgs(name="Basic"),
    admin_user_enabled=True,
)

# Get ACR credentials
acr_credentials = containerregistry.list_registry_credentials_output(
    resource_group_name=resource_group.name,
    registry_name=acr.name,
)

# Export ACR details
pulumi.export("acrLoginServer", acr.login_server)
pulumi.export("acrUsername", acr_credentials.username)
pulumi.export("acrPassword", acr_credentials.passwords[0].value)

# Cosmos DB account and database
cosmos_account = cosmosdb.DatabaseAccount(
    "cosmos-account",
    resource_group_name=resource_group.name,
    account_name="lightning-cosmos",
    location=resource_group.location,
    database_account_offer_type="Standard",
    locations=[cosmosdb.LocationArgs(location_name=resource_group.location)],
    consistency_policy=cosmosdb.ConsistencyPolicyArgs(
        default_consistency_level=cosmosdb.DefaultConsistencyLevel.SESSION
    ),
)

cosmos_db = cosmosdb.SqlResourceSqlDatabase(
    "cosmos-db",
    account_name=cosmos_account.name,
    resource_group_name=resource_group.name,
    database_name="lightning",
    resource=cosmosdb.SqlDatabaseResourceArgs(id="lightning"),
)

user_container = cosmosdb.SqlResourceSqlContainer(
    "users-container",
    account_name=cosmos_account.name,
    resource_group_name=resource_group.name,
    database_name=cosmos_db.name,
    container_name="users",
    resource=cosmosdb.SqlContainerResourceArgs(
        id="users",
        partition_key=cosmosdb.ContainerPartitionKeyArgs(paths=["/pk"], kind="Hash"),
    ),
)

repo_container = cosmosdb.SqlResourceSqlContainer(
    "repos-container",
    account_name=cosmos_account.name,
    resource_group_name=resource_group.name,
    database_name=cosmos_db.name,
    container_name="repos",
    resource=cosmosdb.SqlContainerResourceArgs(
        id="repos",
        partition_key=cosmosdb.ContainerPartitionKeyArgs(paths=["/pk"], kind="Hash"),
    ),
)

schedule_container = cosmosdb.SqlResourceSqlContainer(
    "schedules-container",
    account_name=cosmos_account.name,
    resource_group_name=resource_group.name,
    database_name=cosmos_db.name,
    container_name="schedules",
    resource=cosmosdb.SqlContainerResourceArgs(
        id="schedules",
        partition_key=cosmosdb.ContainerPartitionKeyArgs(paths=["/pk"], kind="Hash"),
    ),
)

cosmos_keys = cosmosdb.list_database_account_connection_strings_output(
    account_name=cosmos_account.name,
    resource_group_name=resource_group.name,
)
cosmos_connection_string = cosmos_keys.connection_strings[0].connection_string

storage_keys = storage.list_storage_account_keys_output(
    resource_group_name=resource_group.name,
    account_name=storage_account.name,
)
primary_storage_key = storage_keys.keys[0].value
storage_connection_string = pulumi.Output.concat(
    "DefaultEndpointsProtocol=https;AccountName=",
    storage_account.name,
    ";AccountKey=",
    primary_storage_key,
)

# App Service plan for Function App (Linux required for Python functions)
app_service_plan = web.AppServicePlan(
    "function-plan",
    resource_group_name=resource_group.name,
    kind="FunctionApp",
    sku=web.SkuDescriptionArgs(tier="Dynamic", name="Y1"),
    reserved=True,  # Set to True for Linux
)

# Authorization rule to send messages
send_rule = servicebus.NamespaceAuthorizationRule(
    "send-rule",
    resource_group_name=resource_group.name,
    namespace_name=namespace.name,
    authorization_rule_name="send",
    rights=["Send"],
)

send_keys = servicebus.list_namespace_keys_output(
    authorization_rule_name=send_rule.name,
    namespace_name=namespace.name,
    resource_group_name=resource_group.name,
)

#
# Function App
func_app = web.WebApp(
    "event-function-linux",
    resource_group_name=resource_group.name,
    server_farm_id=app_service_plan.id,
    kind="FunctionApp",
    identity=web.ManagedServiceIdentityArgs(type=web.ManagedServiceIdentityType.SYSTEM_ASSIGNED),
    site_config=web.SiteConfigArgs(
        linux_fx_version="Python|3.10",  # Updated to Python 3.10 runtime
        # App settings will be configured separately via WebAppApplicationSettings
    ),
)

# TODO: Role assignment requires higher privileges - commenting out for now
# aci_role = RoleAssignment(
#     "aci-contributor",
#     principal_id=func_app.identity.principal_id,
#     principal_type="ServicePrincipal",
#     role_definition_id=f"/subscriptions/{subscription_id}/providers/Microsoft.Authorization/roleDefinitions/b24988ac-6180-42a0-ab88-20f7382dd24c",
#     scope=resource_group.id,
# )

pulumi.export(
    "functionEndpoint",
    pulumi.Output.concat("https://", func_app.default_host_name, "/api/events"),
)

# Container group hosting the Chainlit app and dashboard

ui_image = config.require("uiImage")

ui_container = containerinstance.ContainerGroup(
        "chat-ui",
        resource_group_name=resource_group.name,
        location=resource_group.location,
        os_type="Linux",
        containers=[
            containerinstance.ContainerArgs(
                name="chat-ui",
                image=ui_image,
                ports=[
                containerinstance.ContainerPortArgs(port=443),
                ],
                environment_variables=[
                    containerinstance.EnvironmentVariableArgs(
                        name="EVENT_API_URL",
                        value=pulumi.Output.concat(
                            "https://", func_app.default_host_name, "/api/events"
                        ),
                    ),
                    containerinstance.EnvironmentVariableArgs(
                        name="API_BASE",
                        value=pulumi.Output.concat(
                            "https://", func_app.default_host_name, "/api"
                        ),
                    ),
                    containerinstance.EnvironmentVariableArgs(
                        name="AAD_CLIENT_ID",
                        value=aad_client_id,
                    ),
                    containerinstance.EnvironmentVariableArgs(
                        name="AAD_TENANT_ID",
                        value=aad_tenant_id,
                    ),
                    containerinstance.EnvironmentVariableArgs(
                        name="AAD_CLIENT_SECRET",
                        value=aad_client_secret,
                    ),
                    containerinstance.EnvironmentVariableArgs(
                        name="SESSION_SECRET",
                        value=aad_client_secret,
                    ),
                    containerinstance.EnvironmentVariableArgs(
                        name="APPINSIGHTS_INSTRUMENTATIONKEY",
                        value=app_insights.instrumentation_key,
                    ),
                    containerinstance.EnvironmentVariableArgs(
                        name="CHAINLIT_URL",
                        value=pulumi.Output.concat("https://", domain, "/chat"),
                    ),
                ],
                resources=containerinstance.ResourceRequirementsArgs(
                    requests=containerinstance.ResourceRequestsArgs(cpu=1.0, memory_in_gb=1.0)
                ),
            ),
        ],
        image_registry_credentials=[
            containerinstance.ImageRegistryCredentialArgs(
                server=acr.login_server,
                username=acr_credentials.username,
                password=acr_credentials.passwords[0].value,
            )
        ],
        ip_address=containerinstance.IpAddressArgs(
            ports=[
                containerinstance.PortArgs(protocol="TCP", port=443),
            ],
            type=containerinstance.ContainerGroupIpAddressType.PUBLIC,
        ),
        diagnostics=containerinstance.ContainerGroupDiagnosticsArgs(
            log_analytics=containerinstance.LogAnalyticsArgs(
                workspace_id=workspace.customer_id,
                workspace_key=workspace_keys.primary_shared_key,
                workspace_resource_id=workspace.id,
                log_type=containerinstance.LogAnalyticsLogType.CONTAINER_INSIGHTS,
            )
        ),
        opts=pulumi.ResourceOptions(replace_on_changes=["containers"]),
    )

pulumi.export("uiUrl", ui_container.ip_address.apply(lambda ip: f"http://{ip.fqdn}"))
pulumi.export(
    "giteaUrl",
    gitea_container.ip_address.apply(lambda ip: f"http://{ip.fqdn}"),
)
pulumi.export(
    "postgresFqdn",
    postgres_container.ip_address.apply(lambda ip: ip.fqdn),
)

if domain:
    pulumi.export("uiDomain", pulumi.Output.concat("https://", domain))
    pulumi.export("apiDomain", pulumi.Output.concat("https://api.", domain))

    dns_zone = dns.Zone(
        "domain-zone",
        resource_group_name=resource_group.name,
        zone_name=domain,
        location="global",
    )
    pulumi.export("dnsZoneNameServers", dns_zone.name_servers)

    dns.RecordSet(
        "ui-a-record",
        resource_group_name=resource_group.name,
        zone_name=dns_zone.name,
        relative_record_set_name="@",
        record_type="A",
        ttl=600,
        a_records=[
            dns.ARecordArgs(
                ipv4_address=ui_container.ip_address.apply(lambda ip: ip.ip)
            )
        ],
    )

    dns.RecordSet(
        "api-cname",
        resource_group_name=resource_group.name,
        zone_name=dns_zone.name,
        relative_record_set_name="api",
        record_type="CNAME",
        ttl=600,
        cname_record=dns.CnameRecordArgs(cname=func_app.default_host_name),
    )

    # Create DNS records required to verify the email sending domain
    def create_verification_record(name: str, record_output: pulumi.Output):
        """
        Safely create a DNS verification record only if the Communication
        Service returns a non‑null verification record.

        Some properties (e.g. DKIM2, DMARC) may be absent until the first
        verification step finishes, so we guard against `None`.
        """
        def _create(r):
            if r is None:
                return None  # Nothing to provision yet.

            txt_records = (
                [dns.TxtRecordArgs(value=[r.value])] if r.type == "TXT" else None
            )
            cname_record = (
                dns.CnameRecordArgs(cname=r.value) if r.type == "CNAME" else None
            )
            mx_records = (
                [dns.MxRecordArgs(exchange=r.value, preference=0)] if r.type == "MX" else None
            )

            return dns.RecordSet(
                name,
                resource_group_name=resource_group.name,
                zone_name=dns_zone.name,
                relative_record_set_name=r.name,
                record_type=r.type,
                ttl=float(r.ttl),
                txt_records=txt_records,
                cname_record=cname_record,
                mx_records=mx_records,
            )

        # Apply the creation only when the record materialises
        return record_output.apply(_create)

    create_verification_record("domain-verification", email_domain.verification_records.domain)
    create_verification_record("dkim-verification", email_domain.verification_records.d_kim)
    create_verification_record("dkim2-verification", email_domain.verification_records.d_kim2)
    create_verification_record("dmarc-verification", email_domain.verification_records.d_marc)
    create_verification_record("spf-verification", email_domain.verification_records.s_pf)

# PostgreSQL container for Gitea
postgres_container = containerinstance.ContainerGroup(
    "postgres",
    resource_group_name=resource_group.name,
    location=resource_group.location,
    os_type="Linux",
    containers=[
        containerinstance.ContainerArgs(
            name="postgres",
            image="postgres:15-alpine",
            ports=[containerinstance.ContainerPortArgs(port=5432)],
            environment_variables=[
                containerinstance.EnvironmentVariableArgs(name="POSTGRES_USER", value=postgres_user),
                containerinstance.EnvironmentVariableArgs(name="POSTGRES_PASSWORD", secure_value=postgres_password),
                containerinstance.EnvironmentVariableArgs(name="POSTGRES_DB", value=postgres_db),
            ],
            resources=containerinstance.ResourceRequirementsArgs(
                requests=containerinstance.ResourceRequestsArgs(cpu=0.5, memory_in_gb=1.0)
            ),
            volume_mounts=[
                containerinstance.VolumeMountArgs(name="postgres-data", mount_path="/var/lib/postgresql/data")
            ],
        )
    ],
    volumes=[
        containerinstance.VolumeArgs(
            name="postgres-data",
            azure_file=containerinstance.AzureFileVolumeArgs(
                share_name=postgres_share.name,
                storage_account_name=repo_storage_account.name,
                storage_account_key=repo_primary_key,
            ),
        )
    ],
    ip_address=containerinstance.IpAddressArgs(
        ports=[containerinstance.PortArgs(protocol="TCP", port=5432)],
        type=containerinstance.ContainerGroupIpAddressType.PUBLIC,
    ),
    diagnostics=containerinstance.ContainerGroupDiagnosticsArgs(
        log_analytics=containerinstance.LogAnalyticsArgs(
            workspace_id=workspace.customer_id,
            workspace_key=workspace_keys.primary_shared_key,
            workspace_resource_id=workspace.id,
        )
    ),
)

# Gitea container using the PostgreSQL database
gitea_container = containerinstance.ContainerGroup(
    "gitea",
    resource_group_name=resource_group.name,
    location=resource_group.location,
    os_type="Linux",
    containers=[
        containerinstance.ContainerArgs(
            name="gitea",
            image="gitea/gitea:1.21-rootless",
            ports=[containerinstance.ContainerPortArgs(port=3000)],
            environment_variables=[
                containerinstance.EnvironmentVariableArgs(name="GITEA__database__DB_TYPE", value="postgres"),
                containerinstance.EnvironmentVariableArgs(
                    name="GITEA__database__HOST",
                    value=postgres_container.ip_address.apply(lambda ip: f"{ip.ip}:5432"),
                ),
                containerinstance.EnvironmentVariableArgs(name="GITEA__database__NAME", value=postgres_db),
                containerinstance.EnvironmentVariableArgs(name="GITEA__database__USER", value=postgres_user),
                containerinstance.EnvironmentVariableArgs(
                    name="GITEA__database__PASSWD", secure_value=postgres_password
                ),
                containerinstance.EnvironmentVariableArgs(name="AAD_CLIENT_ID", value=aad_client_id),
                containerinstance.EnvironmentVariableArgs(name="AAD_CLIENT_SECRET", value=aad_client_secret),
                containerinstance.EnvironmentVariableArgs(name="AAD_TENANT_ID", value=aad_tenant_id),
            ],
            resources=containerinstance.ResourceRequirementsArgs(
                requests=containerinstance.ResourceRequestsArgs(cpu=0.5, memory_in_gb=1.0)
            ),
            volume_mounts=[
                containerinstance.VolumeMountArgs(name="gitea-data", mount_path="/data"),
                containerinstance.VolumeMountArgs(name="gitea-setup", mount_path="/setup", read_only=True),
            ],
            command=[
                "/bin/sh",
                "-c",
                "/setup/setup.sh; /usr/local/bin/docker-entrypoint.sh",
            ],
        )
    ],
    volumes=[
        containerinstance.VolumeArgs(
            name="gitea-data",
            azure_file=containerinstance.AzureFileVolumeArgs(
                share_name=gitea_share.name,
                storage_account_name=repo_storage_account.name,
                storage_account_key=repo_primary_key,
            ),
        ),
        containerinstance.VolumeArgs(
            name="gitea-setup",
            secret={
                "setup.sh": pulumi.Output.from_input(
                    "#!/bin/sh\n"
                    "set -e\n"
                    "/usr/local/bin/gitea admin auth add-oauth \\\n+  --name AzureAD \\\n+  --provider openidConnect \\\n+  --key $AAD_CLIENT_ID \\\n+  --secret $AAD_CLIENT_SECRET \\\n+  --auto-discover-url https://login.microsoftonline.com/$AAD_TENANT_ID/v2.0/.well-known/openid-configuration \\\n+  --config /data/gitea/conf/app.ini || true\n"
                ).apply(lambda s: __import__("base64").b64encode(s.encode()).decode()),
            },
        ),
    ],
    ip_address=containerinstance.IpAddressArgs(
        ports=[containerinstance.PortArgs(protocol="TCP", port=3000)],
        type=containerinstance.ContainerGroupIpAddressType.PUBLIC,
    ),
    diagnostics=containerinstance.ContainerGroupDiagnosticsArgs(
        log_analytics=containerinstance.LogAnalyticsArgs(
            workspace_id=workspace.customer_id,
            workspace_key=workspace_keys.primary_shared_key,
            workspace_resource_id=workspace.id,
        )
    ),
)

# Wire the functions back to the Chainlit UI once the container address is known
notify_url = ui_container.ip_address.apply(lambda ip: f"https://{ip.fqdn}/chat/notify")

# Function to create and upload Function App package
def create_function_package():
    """Create a ZIP package of the Azure Functions code with its dependencies."""
    import zipfile
    import tempfile
    import os
    import atexit
    import shutil
    import subprocess
    import sys
    from pathlib import Path

    build_dir = tempfile.mkdtemp(prefix="func-build-")
    atexit.register(lambda: shutil.rmtree(build_dir, ignore_errors=True))

    # Copy the function source code
    shutil.copytree("../azure-function", build_dir, dirs_exist_ok=True)

    # Copy supporting packages used by the functions
    for package in ("../events", "../common"):
        if os.path.isdir(package):
            dest = os.path.join(build_dir, os.path.basename(package))
            shutil.copytree(package, dest, dirs_exist_ok=True)

    # Install Python dependencies into .python_packages
    site_packages = os.path.join(build_dir, ".python_packages", "lib", "site-packages")
    os.makedirs(site_packages, exist_ok=True)
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-r",
            "../azure-function/requirements.txt",
            "--target",
            site_packages,
            "--platform",
            "manylinux2014_x86_64",
            "--implementation",
            "cp",
            "--python-version",
            "3.10",
            "--only-binary=:all:",
        ]
    )

    # Create a temporary ZIP file that persists until cleanup
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    zip_path = tmp.name
    tmp.close()
    atexit.register(lambda: os.path.exists(zip_path) and os.remove(zip_path))

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(build_dir):
            for file in files:
                file_path = os.path.join(root, file)
                if "__pycache__" in file_path or file.endswith(".pyc"):
                    continue
                arcname = os.path.relpath(file_path, build_dir)
                zipf.write(file_path, arcname)

    return zip_path

# Create the function package
function_zip_path = create_function_package()

# Create a container for function deployments
deployment_container = storage.BlobContainer(
    "deployments",
    resource_group_name=resource_group.name,
    account_name=storage_account.name,
    container_name="deployments",
    public_access=storage.PublicAccess.NONE,
)

# Upload the ZIP package to blob storage for deployment
function_blob = storage.Blob(
    "function-package",
    resource_group_name=resource_group.name,
    account_name=storage_account.name,
    container_name=deployment_container.name,
    blob_name="function-package.zip",
    type=storage.BlobType.BLOCK,
    source=pulumi.FileAsset(function_zip_path),
)

# Build the URL to the deployment package without a SAS token
function_package_url = pulumi.Output.format(
    "https://{0}.blob.core.windows.net/{1}/function-package.zip",
    storage_account.name,
    deployment_container.name,
)

# Grant the Function App's managed identity read access to the package
storage_blob_reader_role_id = "2a2b9908-6ea1-4ae2-8e65-a410df84e7d1"
RoleAssignment(
    "function-package-reader",
    principal_id=func_app.identity.principal_id,
    principal_type="ServicePrincipal",
    role_definition_id=pulumi.Output.concat(
        "/subscriptions/",
        subscription_id,
        "/providers/Microsoft.Authorization/roleDefinitions/",
        storage_blob_reader_role_id,
    ),
    scope=storage_account.id,
    role_assignment_name=str(uuid.uuid4()),
)

# Deploy the function package using WebAppApplicationSettings
# Combine all app settings including the package URL and notify URL
all_app_settings = {
    "AzureWebJobsStorage": storage_connection_string,
    "FUNCTIONS_EXTENSION_VERSION": "~4",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "COSMOS_CONNECTION": cosmos_connection_string,
    "COSMOS_DATABASE": "lightning",
    "SCHEDULE_CONTAINER": "schedules",
    "SERVICEBUS_CONNECTION": send_keys.primary_connection_string,
    "SERVICEBUS_QUEUE": queue.name,
    "REPO_CONTAINER": "repos",
    "USER_CONTAINER": "users",
    "ACI_RESOURCE_GROUP": resource_group.name,
    "ACI_SUBSCRIPTION_ID": subscription_id,
    "ACI_REGION": location,
    "OPENAI_API_KEY": openai_api_key,
    "WORKER_IMAGE": worker_image,
    "AAD_CLIENT_ID": aad_client_id,
    "AAD_CLIENT_SECRET": aad_client_secret,
    "AAD_TENANT_ID": aad_tenant_id,
    "NOTIFY_URL": notify_url,
    "WEBSITE_RUN_FROM_PACKAGE": function_package_url,
    "APPINSIGHTS_INSTRUMENTATIONKEY": app_insights.instrumentation_key,
    "ACS_CONNECTION": comm_keys.primary_connection_string,
    "ACS_SENDER": acs_sender,
    "VERIFY_BASE_URL": pulumi.Output.concat("https://", func_app.default_host_name),
}

web.WebAppApplicationSettings(
    "function-settings",
    name=func_app.name,
    resource_group_name=resource_group.name,
    properties=all_app_settings,
)
