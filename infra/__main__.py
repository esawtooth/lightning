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
)

# Cosmos DB resources live in a separate module
from pulumi_azure_native import cosmosdb
from pulumi_azure_native.authorization import get_client_config, RoleAssignment
from pulumi_azure_native import dns

config = pulumi.Config()
location = config.get("location") or "centralindia"
openai_api_key = config.require_secret("openaiApiKey")
jwt_signing_key = config.require_secret("jwtSigningKey")
# Worker image will be configured by GitHub Actions or default to ACR image
worker_image = config.get("workerImage") or "lightningacr.azurecr.io/worker-task:latest"
domain = config.get("domain") or "agentsmith.in"

# Resource group
resource_group = resources.ResourceGroup(
    "lightning_dev-1",
    resource_group_name="lightning_dev-1",
    location=location,
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

pulumi.export("resourceGroupName", resource_group.name)
pulumi.export("serviceBusNamespaceName", namespace.name)
pulumi.export("queueName", queue.name)
pulumi.export("appInsightsKey", app_insights.instrumentation_key)

# Storage account for Function App
storage_account = storage.StorageAccount(
    "funcsa",
    resource_group_name=resource_group.name,
    sku=storage.SkuArgs(name=storage.SkuName.STANDARD_LRS),
    kind=storage.Kind.STORAGE_V2,
)

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

# Function App
client_config = get_client_config()
subscription_id = client_config.subscription_id

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
        container_group_name="chat-ui",
        location=resource_group.location,
        os_type="Linux",
        containers=[
            containerinstance.ContainerArgs(
                name="chat-ui",
                image=ui_image,
                ports=[containerinstance.ContainerPortArgs(port=8000)],
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
                        name="AUTH_API_URL",
                        value=pulumi.Output.concat(
                            "https://", func_app.default_host_name, "/api/auth"
                        ),
                    ),
                    containerinstance.EnvironmentVariableArgs(
                        name="JWT_SIGNING_KEY",
                        value=jwt_signing_key,
                    ),
                    containerinstance.EnvironmentVariableArgs(
                        name="SESSION_SECRET",
                        value=jwt_signing_key,  # Use same key for session encryption
                    ),
                    containerinstance.EnvironmentVariableArgs(
                        name="APPINSIGHTS_INSTRUMENTATIONKEY",
                        value=app_insights.instrumentation_key,
                    ),
                ],
                resources=containerinstance.ResourceRequirementsArgs(
                    requests=containerinstance.ResourceRequestsArgs(cpu=1.0, memory_in_gb=1.0)
                ),
            )
        ],
        image_registry_credentials=[
            containerinstance.ImageRegistryCredentialArgs(
                server=acr.login_server,
                username=acr_credentials.username,
                password=acr_credentials.passwords[0].value,
            )
        ],
        ip_address=containerinstance.IpAddressArgs(
            ports=[containerinstance.PortArgs(protocol="TCP", port=8000)],
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
    )

pulumi.export("uiUrl", ui_container.ip_address.apply(lambda ip: f"http://{ip.fqdn}"))

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

# Wire the functions back to the Chainlit UI once the container address is known
notify_url = ui_container.ip_address.apply(lambda ip: f"http://{ip.fqdn}/notify")

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
    "JWT_SIGNING_KEY": jwt_signing_key,
    "NOTIFY_URL": notify_url,
    "WEBSITE_RUN_FROM_PACKAGE": function_package_url,
    "APPINSIGHTS_INSTRUMENTATIONKEY": app_insights.instrumentation_key,
}

web.WebAppApplicationSettings(
    "function-settings",
    name=func_app.name,
    resource_group_name=resource_group.name,
    properties=all_app_settings,
)
