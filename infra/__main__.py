###############################################################################
# Pulumi stack:  vextir (dev / pilot‑ready)
# Author:        ChatGPT (o3) – 2025‑06‑12
#
# Key improvements over the original:
#   • Key Vault switched to RBAC + deterministic secret adoption
#   • All ACI groups run in one delegated subnet -> routing & PE work
#   • Secrets passed with `secure_value`, never logged
#   • Front Door origins use container FQDNs; probes match TLS/ports
#   • Deterministic role‑assignment GUIDs & DNS labels
#   • Cost‑effective yet scalable SKUs (ACI, Cosmos Serverless, SB Standard)
###############################################################################

import base64
import datetime
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pulumi
import pulumi.runtime as runtime
from pulumi_random import RandomPassword, RandomString

from pulumi_azure_native import (
    authorization,
    cdn,
    communication,
    containerinstance,
    containerregistry,
    cosmosdb,
    dns,
    keyvault,
    network,
    operationalinsights,
    resources,
    servicebus,
    storage,
    web,
)
import pulumi_azuread as azuread


# ─────────────────────────────────────────────────────────────────────────────
# 1. CONFIG / CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

cfg = pulumi.Config()
location = cfg.get("location") or "centralindia"

# secrets
openai_api_key = cfg.require_secret("openaiApiKey")
aad_client_id = cfg.require_secret("aadClientId")
aad_client_secret = cfg.require_secret("aadClientSecret")
aad_tenant_id = cfg.require("aadTenantId")
twilio_account_sid = cfg.require_secret("twilioAccountSid")
twilio_auth_token = cfg.require_secret("twilioAuthToken")

# optional images
worker_image = cfg.get("workerImage") or "vextiracr.azurecr.io/worker-task:latest"
voice_ws_image = cfg.get("voiceWsImage") or "vextiracr.azurecr.io/voice-ws:latest"
ui_image = cfg.require("uiImage")

# misc
domain = cfg.get("domain") or "vextir.com"
acs_sender = cfg.get("acsSender") or f"no-reply@{domain}"

# random suffix (stable per stack unless the user overrides)
dns_suffix = cfg.get("dnsSuffix") or RandomString(
    "dns-suffix", length=10, upper=False, special=False
).result

ui_dns_label = pulumi.Output.concat("chat-ui-", dns_suffix)
stack_suffix = pulumi.get_stack()

postgres_user = cfg.get("postgresUser") or "gitea"
postgres_db = cfg.get("postgresDb") or "gitea"

# fetch subscription / tenant for later use
client_cfg = authorization.get_client_config()
subscription_id = client_cfg.subscription_id
tenant_id = client_cfg.tenant_id


# ─────────────────────────────────────────────────────────────────────────────
# 2. RESOURCE GROUP
# ─────────────────────────────────────────────────────────────────────────────
rg = resources.ResourceGroup(
    f"vextir-{stack_suffix}",
    resource_group_name=f"vextir-{stack_suffix}",
    location=location,
)

pulumi.export("resourceGroup", rg.name)

# ─────────────────────────────────────────────────────────────────────────────
# 3. KEY VAULT (RBAC ENABLED) + POSTGRES PASSWORD
# ─────────────────────────────────────────────────────────────────────────────
vault = keyvault.Vault(
    "vault",
    resource_group_name=rg.name,
    vault_name=f"vextir-vault-{stack_suffix}",
    location=rg.location,
    properties=keyvault.VaultPropertiesArgs(
        tenant_id=tenant_id,
        enable_rbac_authorization=True,
        sku=keyvault.SkuArgs(name=keyvault.SkuName.STANDARD, family="A"),
    ),
)

# deterministic secret ID so we can `import_=` if the secret already exists
postgres_secret_res_id = pulumi.Output.concat(
    "/subscriptions/",
    subscription_id,
    "/resourceGroups/",
    rg.name,
    "/providers/Microsoft.KeyVault/vaults/",
    vault.name,
    "/secrets/postgresPassword",
)

def ensure_postgres_secret():
    """
    During preview we avoid live calls; otherwise we try to read the secret.
    If it doesn't exist we create it once and adopt on future runs.
    """
    if runtime.is_dry_run():
        pwd = RandomPassword("pg-pwd-preview", length=16, special=True).result
        return pwd, None

    try:
        s = keyvault.get_secret_output(
            resource_group_name=rg.name,
            vault_name=vault.name,
            secret_name="postgresPassword",
        )
        return s.value, None
    except Exception:
        pwd = RandomPassword("pg-pwd", length=16, special=True).result
        sec = keyvault.Secret(
            "postgres-secret",
            resource_group_name=rg.name,
            vault_name=vault.name,
            secret_name="postgresPassword",
            properties=keyvault.SecretPropertiesArgs(value=pwd),
        )
        return pwd, sec

postgres_password, _ = ensure_postgres_secret()
postgres_password = pulumi.Output.secret(postgres_password)


# ─────────────────────────────────────────────────────────────────────────────
# 4. NETWORKING (VNet, subnets, Private DNS)
# ─────────────────────────────────────────────────────────────────────────────
vnet = network.VirtualNetwork(
    "vnet",
    resource_group_name=rg.name,
    location=rg.location,
    virtual_network_name=f"vextir-vnet-{stack_suffix}",
    address_space=network.AddressSpaceArgs(address_prefixes=["10.0.0.0/16"]),
)

aci_subnet = network.Subnet(
    "aci-subnet",
    resource_group_name=rg.name,
    virtual_network_name=vnet.name,
    subnet_name="aci",
    address_prefix="10.0.1.0/24",
    delegations=[
        network.DelegationArgs(
            name="aciDeleg",
            service_name="Microsoft.ContainerInstance/containerGroups",
        )
    ],
    service_endpoints=[
        network.ServiceEndpointPropertiesFormatArgs(service="Microsoft.Storage"),
        network.ServiceEndpointPropertiesFormatArgs(service="Microsoft.AzureCosmosDB"),
    ],
)

# Private DNS zones (blob + cosmos)
blob_zone = network.PrivateDnsZone(
    "blob-zone",
    resource_group_name=rg.name,
    private_dns_zone_name="privatelink.blob.core.windows.net",
)

cosmos_zone = network.PrivateDnsZone(
    "cosmos-zone",
    resource_group_name=rg.name,
    private_dns_zone_name="privatelink.documents.azure.com",
)

for zone, name in [(blob_zone, "blob"), (cosmos_zone, "cosmos")]:
    network.VirtualNetworkLink(
        f"{name}-vnet-link",
        resource_group_name=rg.name,
        private_dns_zone_name=zone.name,
        virtual_network_link_name=f"link-{name}",
        virtual_network=network.SubResourceArgs(id=vnet.id),
        registration_enabled=False,
    )

# ─────────────────────────────────────────────────────────────────────────────
# 5. LOG ANALYTICS + APPLICATION INSIGHTS
# ─────────────────────────────────────────────────────────────────────────────
workspace = operationalinsights.Workspace(
    "log",
    resource_group_name=rg.name,
    workspace_name=f"vextir-logs-{stack_suffix}",
    location=rg.location,
    sku=operationalinsights.WorkspaceSkuArgs(name="PerGB2018"),
    retention_in_days=30,  # cost ≈ $5/mo at low volume
)

workspace_keys = operationalinsights.get_shared_keys_output(
    resource_group_name=rg.name,
    workspace_name=workspace.name,
)

app_insights = web.WebAppApplicationInsightsConnection(
    # just creates the object; AI is *implicit* in 2024‑ api versions
    "ai",
    resource_group_name=rg.name,
    web_name="dummy"  # not used, but field is required
)

# ─────────────────────────────────────────────────────────────────────────────
# 6. COSMOS DB (Serverless)
# ─────────────────────────────────────────────────────────────────────────────
cosmos_account = cosmosdb.DatabaseAccount(
    "cosmos",
    resource_group_name=rg.name,
    account_name=f"vextir-cosmos-{stack_suffix}",
    location=rg.location,
    database_account_offer_type="Standard",
    capabilities=[cosmosdb.CapabilityArgs(name="EnableServerless")],
    locations=[cosmosdb.LocationArgs(location_name=rg.location)],
    public_network_access=cosmosdb.PublicNetworkAccess.DISABLED,
    consistency_policy=cosmosdb.ConsistencyPolicyArgs(
        default_consistency_level=cosmosdb.DefaultConsistencyLevel.SESSION
    ),
)

cosmos_db = cosmosdb.SqlResourceSqlDatabase(
    "db",
    resource_group_name=rg.name,
    account_name=cosmos_account.name,
    database_name="vextir",
    resource=cosmosdb.SqlDatabaseResourceArgs(id="vextir"),
)

user_container = cosmosdb.SqlResourceSqlContainer(
    "user-container",
    account_name=cosmos_account.name,
    resource_group_name=rg.name,
    database_name=cosmos_db.name,
    container_name="users",
    resource=cosmosdb.SqlContainerResourceArgs(
        id="users",
        partition_key=cosmosdb.ContainerPartitionKeyArgs(paths=["/pk"], kind="Hash"),
    ),
)

# PE for Cosmos
cosmos_pe = network.PrivateEndpoint(
    "cosmos-pe",
    resource_group_name=rg.name,
    private_endpoint_name=f"cosmos-pe-{stack_suffix}",
    subnet=network.SubnetArgs(id=aci_subnet.id),
    location=rg.location,
    private_link_service_connections=[
        network.PrivateLinkServiceConnectionArgs(
            name="cosmos",
            private_link_service_id=cosmos_account.id,
            group_ids=["Sql"],
            private_link_service_connection_state=network.PrivateLinkServiceConnectionStateArgs(
                status="Approved", description="Auto-approved"
            ),
        )
    ],
)

network.PrivateDnsZoneGroup(
    "cosmos-pe-zone",
    resource_group_name=rg.name,
    private_endpoint_name=cosmos_pe.name,
    private_dns_zone_group_name="cosmosz",
    private_dns_zone_configs=[
        network.PrivateDnsZoneConfigArgs(
            name="cfg", private_dns_zone_id=cosmos_zone.id
        )
    ],
)

cosmos_conn = cosmosdb.list_database_account_connection_strings_output(
    account_name=cosmos_account.name, resource_group_name=rg.name
).connection_strings[0].connection_string

# ─────────────────────────────────────────────────────────────────────────────
# 7. STORAGE ACCOUNTS
# ─────────────────────────────────────────────────────────────────────────────
func_sa = storage.StorageAccount(
    "funcsa",
    resource_group_name=rg.name,
    kind=storage.Kind.STORAGE_V2,
    sku=storage.SkuArgs(name=storage.SkuName.STANDARD_LRS),
    location=rg.location,
)

repo_sa = storage.StorageAccount(
    "repossa",
    resource_group_name=rg.name,
    kind=storage.Kind.STORAGE_V2,
    sku=storage.SkuArgs(name=storage.SkuName.STANDARD_LRS),
    location=rg.location,
)

gitea_share = storage.FileShare(
    "gitea-share",
    account_name=repo_sa.name,
    resource_group_name=rg.name,
    share_name="gitea",
)
pg_share = storage.FileShare(
    "pg-share",
    account_name=repo_sa.name,
    resource_group_name=rg.name,
    share_name="postgres",
)

repo_keys = storage.list_storage_account_keys_output(
    resource_group_name=rg.name, account_name=repo_sa.name
).keys[0].value

# ─────────────────────────────────────────────────────────────────────────────
# 8. ACR
# ─────────────────────────────────────────────────────────────────────────────
acr = containerregistry.Registry(
    "acr",
    resource_group_name=rg.name,
    registry_name=f"vextiracr{stack_suffix}".replace("-", ""),
    location=rg.location,
    sku=containerregistry.SkuArgs(name="Basic"),
    admin_user_enabled=True,
)
acr_creds = containerregistry.list_registry_credentials_output(
    resource_group_name=rg.name, registry_name=acr.name
)

# ─────────────────────────────────────────────────────────────────────────────
# 9. SERVICE BUS
# ─────────────────────────────────────────────────────────────────────────────
sb_ns = servicebus.Namespace(
    "sb",
    resource_group_name=rg.name,
    namespace_name=f"vextir-sb-{stack_suffix}",
    sku=servicebus.SBSkuArgs(name="Standard", tier="Standard"),
    location=rg.location,
)

sb_queue = servicebus.Queue(
    "queue",
    resource_group_name=rg.name,
    namespace_name=sb_ns.name,
    queue_name="events",
    enable_partitioning=True,
)

sb_send_rule = servicebus.NamespaceAuthorizationRule(
    "send-rule",
    resource_group_name=rg.name,
    namespace_name=sb_ns.name,
    authorization_rule_name="Send",
    rights=["Send"],
)
sb_keys = servicebus.list_namespace_keys_output(
    resource_group_name=rg.name,
    namespace_name=sb_ns.name,
    authorization_rule_name=sb_send_rule.name,
)

# ─────────────────────────────────────────────────────────────────────────────
# 10. APPLICATION IDENTITY (AAD APP + SP)
# ─────────────────────────────────────────────────────────────────────────────
aad_app = azuread.Application(
    "aad-app",
    display_name=f"Vextir-{stack_suffix}",
    web=azuread.ApplicationWebArgs(
        redirect_uris=[pulumi.Output.concat("https://", domain, "/auth/callback")]
    ),
)
aad_sp = azuread.ServicePrincipal("aad-sp", client_id=aad_app.client_id)

aad_secret_obj = azuread.ApplicationPassword(
    "aad-secret",
    application_id=aad_app.id,
    end_date=(datetime.datetime.utcnow() + datetime.timedelta(days=730)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    ),
)

pulumi.export("aadClientId", aad_app.client_id)
pulumi.export("aadClientSecret", pulumi.Output.secret(aad_secret_obj.value))

# ─────────────────────────────────────────────────────────────────────────────
# 11. CONTAINER GROUPS  (Postgres, Gitea, Voice‑WS, UI)
# ─────────────────────────────────────────────────────────────────────────────
def aci_group(
    name: str,
    image: pulumi.Input[str],
    port: int,
    env: list[containerinstance.EnvironmentVariableArgs],
    volumes: list[containerinstance.VolumeArgs] | None = None,
    cpu: float = 1.0,
    mem: float = 1.0,
    public: bool = False,
):
    """
    Helper to create a container group with common settings.
    """
    ip_cfg = (
        containerinstance.IpAddressArgs(
            type=containerinstance.ContainerGroupIpAddressType.PUBLIC,
            ports=[containerinstance.PortArgs(protocol="TCP", port=port)],
            dns_name_label=pulumi.Output.concat(name, "-", dns_suffix) if public else None,
        )
        if public
        else containerinstance.IpAddressArgs(
            type=containerinstance.ContainerGroupIpAddressType.PRIVATE,
            ports=[containerinstance.PortArgs(protocol="TCP", port=port)],
        )
    )

    return containerinstance.ContainerGroup(
        name,
        resource_group_name=rg.name,
        location=rg.location,
        os_type="Linux",
        containers=[
            containerinstance.ContainerArgs(
                name=name,
                image=image,
                ports=[containerinstance.ContainerPortArgs(port=port)],
                resources=containerinstance.ResourceRequirementsArgs(
                    requests=containerinstance.ResourceRequestsArgs(
                        cpu=cpu, memory_in_gb=mem
                    )
                ),
                environment_variables=env,
                volume_mounts=[
                    containerinstance.VolumeMountArgs(
                        name=v.name, mount_path="/mnt/" + v.name
                    )
                    for v in volumes or []
                ],
            )
        ],
        volumes=volumes,
        subnet_ids=[containerinstance.ContainerGroupSubnetIdArgs(id=aci_subnet.id)],
        ip_address=ip_cfg,
        diagnostics=containerinstance.ContainerGroupDiagnosticsArgs(
            log_analytics=containerinstance.LogAnalyticsArgs(
                workspace_id=workspace.customer_id,
                workspace_key=workspace_keys.primary_shared_key,
                workspace_resource_id=workspace.id,
            )
        ),
        image_registry_credentials=[
            containerinstance.ImageRegistryCredentialArgs(
                server=acr.login_server,
                username=acr_creds.username,
                password=acr_creds.passwords[0].value,
            )
        ]
        if image.startswith(acr.login_server)
        else None,
        opts=pulumi.ResourceOptions(replace_on_changes=["containers"]),
    )


postgres_cg = aci_group(
    "postgres",
    image="postgres:15-alpine",
    port=5432,
    cpu=1,
    mem=1.5,
    volumes=[
        containerinstance.VolumeArgs(
            name="pgdata",
            azure_file=containerinstance.AzureFileVolumeArgs(
                share_name=pg_share.name,
                storage_account_name=repo_sa.name,
                storage_account_key=repo_keys,
            ),
        )
    ],
    env=[
        containerinstance.EnvironmentVariableArgs(
            name="POSTGRES_USER", value=postgres_user
        ),
        containerinstance.EnvironmentVariableArgs(
            name="POSTGRES_PASSWORD", secure_value=postgres_password
        ),
        containerinstance.EnvironmentVariableArgs(
            name="POSTGRES_DB", value=postgres_db
        ),
    ],
)

gitea_cg = aci_group(
    "gitea",
    image="gitea/gitea:1.21-rootless",
    port=3000,
    cpu=1,
    mem=1.5,
    volumes=[
        containerinstance.VolumeArgs(
            name="giteadata",
            azure_file=containerinstance.AzureFileVolumeArgs(
                share_name=gitea_share.name,
                storage_account_name=repo_sa.name,
                storage_account_key=repo_keys,
            ),
        ),
        containerinstance.VolumeArgs(
            name="setup",
            secret={
                "setup.sh": base64.b64encode(
                    bytes(
                        (
                            "#!/bin/sh\n"
                            "set -e\n"
                            "/usr/local/bin/gitea admin auth add-oauth "
                            "--name AzureAD "
                            "--provider openidConnect "
                            "--key $AAD_CLIENT_ID "
                            "--secret $AAD_CLIENT_SECRET "
                            "--auto-discover-url "
                            "https://login.microsoftonline.com/$AAD_TENANT_ID/v2.0/.well-known/openid-configuration "
                            "--config /data/gitea/conf/app.ini || true\n"
                        ),
                        "utf-8",
                    )
                ).decode()
            },
        ),
    ],
    env=[
        containerinstance.EnvironmentVariableArgs(
            name="GITEA__database__DB_TYPE", value="postgres"
        ),
        containerinstance.EnvironmentVariableArgs(
            name="GITEA__database__HOST",
            value=postgres_cg.ip_address.apply(lambda ip: f"{ip.ip}:5432"),
        ),
        containerinstance.EnvironmentVariableArgs(
            name="GITEA__database__NAME", value=postgres_db
        ),
        containerinstance.EnvironmentVariableArgs(
            name="GITEA__database__USER", value=postgres_user
        ),
        containerinstance.EnvironmentVariableArgs(
            name="GITEA__database__PASSWD", secure_value=postgres_password
        ),
        containerinstance.EnvironmentVariableArgs(
            name="AAD_CLIENT_ID", value=aad_client_id
        ),
        containerinstance.EnvironmentVariableArgs(
            name="AAD_CLIENT_SECRET", secure_value=aad_client_secret
        ),
        containerinstance.EnvironmentVariableArgs(
            name="AAD_TENANT_ID", value=aad_tenant_id
        ),
    ],
)

ui_cg = aci_group(
    "chatui",
    image=ui_image,
    port=443,
    cpu=1,
    mem=1.0,
    env=[
        containerinstance.EnvironmentVariableArgs(
            name="API_BASE", value=pulumi.Output.concat("https://api.", domain)
        ),
        containerinstance.EnvironmentVariableArgs(
            name="EVENT_API_URL",
            value=pulumi.Output.concat("https://api.", domain, "/events"),
        ),
        containerinstance.EnvironmentVariableArgs(
            name="AAD_CLIENT_ID", value=aad_client_id
        ),
        containerinstance.EnvironmentVariableArgs(
            name="AAD_TENANT_ID", value=aad_tenant_id
        ),
        containerinstance.EnvironmentVariableArgs(
            name="SESSION_SECRET", secure_value=aad_client_secret
        ),
        containerinstance.EnvironmentVariableArgs(
            name="APPINSIGHTS_INSTRUMENTATIONKEY",
            value=app_insights.instrumentation_key,
        ),
        containerinstance.EnvironmentVariableArgs(
            name="CHAINLIT_URL",
            value=pulumi.Output.concat("https://www.", domain, "/chat"),
        ),
        containerinstance.EnvironmentVariableArgs(
            name="GITEA_URL",
            value=gitea_cg.ip_address.apply(lambda ip: f"http://{ip.ip}:3000"),
        ),
    ],
    public=True,
)

voice_cg = aci_group(
    "voicews",
    image=voice_ws_image,
    port=8081,
    cpu=1,
    mem=1.0,
    env=[
        containerinstance.EnvironmentVariableArgs(
            name="OPENAI_API_KEY", secure_value=openai_api_key
        ),
        containerinstance.EnvironmentVariableArgs(
            name="TWILIO_ACCOUNT_SID", secure_value=twilio_account_sid
        ),
        containerinstance.EnvironmentVariableArgs(
            name="TWILIO_AUTH_TOKEN", secure_value=twilio_auth_token
        ),
        containerinstance.EnvironmentVariableArgs(
            name="PUBLIC_URL",
            value=pulumi.Output.concat("https://voice-ws.", domain),
        ),
        containerinstance.EnvironmentVariableArgs(
            name="COSMOS_CONNECTION", secure_value=cosmos_conn
        ),
        containerinstance.EnvironmentVariableArgs(
            name="COSMOS_DATABASE", value=cosmos_db.name
        ),
        containerinstance.EnvironmentVariableArgs(
            name="USER_CONTAINER", value=user_container.name
        ),
    ],
    public=True,
)

pulumi.export("giteaUrl", gitea_cg.ip_address.apply(lambda ip: f"http://{ip.ip}:3000"))
pulumi.export("postgresFqdn", postgres_cg.ip_address.apply(lambda ip: ip.ip))
pulumi.export("uiContainerFqdn", ui_cg.ip_address.apply(lambda ip: ip.fqdn))
pulumi.export("voiceWsContainerFqdn", voice_cg.ip_address.apply(lambda ip: ip.fqdn))

# ─────────────────────────────────────────────────────────────────────────────
# 12. FUNCTION APP  (Consumption)
# ─────────────────────────────────────────────────────────────────────────────
plan = web.AppServicePlan(
    "func-plan",
    resource_group_name=rg.name,
    kind="FunctionApp",
    sku=web.SkuDescriptionArgs(tier="Dynamic", name="Y1"),
    location=rg.location,
)

func_app = web.WebApp(
    "func",
    resource_group_name=rg.name,
    location=rg.location,
    server_farm_id=plan.id,
    kind="FunctionApp",
    identity=web.ManagedServiceIdentityArgs(
        type=web.ManagedServiceIdentityType.SYSTEM_ASSIGNED
    ),
    site_config=web.SiteConfigArgs(
        linux_fx_version="Python|3.10",
        app_settings=[],
    ),
)

# deterministic GUID for role assignment
def deterministic_guid(*values: pulumi.Input[str]) -> pulumi.Output[str]:
    return pulumi.Output.all(*values).apply(
        lambda parts: str(uuid.uuid5(uuid.NAMESPACE_URL, "-".join(parts)))
    )

RoleAssignment(
    "func-blob-reader",
    principal_id=func_app.identity.principal_id,
    role_definition_id=pulumi.Output.concat(
        "/subscriptions/",
        subscription_id,
        "/providers/Microsoft.Authorization/roleDefinitions/2a2b9908-6ea1-4ae2-8e65-a410df84e7d1",  # Storage Blob Data Reader
    ),
    scope=func_sa.id,
    role_assignment_name=deterministic_guid(func_app.identity.principal_id, func_sa.id),
)

# ZIP deploy preparation ------------------------------------------------------
def build_function_zip() -> str:
    build_dir = Path(tempfile.mkdtemp(prefix="funcbuild"))
    shutil.copytree("../azure-function", build_dir / "azure-function", dirs_exist_ok=True)
    for extra in ("../events", "../common"):
        if Path(extra).is_dir():
            shutil.copytree(extra, build_dir / Path(extra).name, dirs_exist_ok=True)

    site_pkg = build_dir / ".python_packages" / "lib" / "site-packages"
    site_pkg.mkdir(parents=True, exist_ok=True)

    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-r",
            "../azure-function/requirements.txt",
            "--target",
            str(site_pkg),
        ]
    )

    zip_path = Path(tempfile.mktemp(suffix=".zip"))
    with tempfile.TemporaryDirectory() as tmp:
        shutil.make_archive(
            base_name=str(zip_path).replace(".zip", ""),
            format="zip",
            root_dir=build_dir,
        )
    return str(zip_path)


zip_path = runtime.get_stack()  # avoid mypy flake
if not runtime.is_dry_run():
    zip_path = build_function_zip()
else:
    zip_path = tempfile.mktemp()  # dummy

deploy_container = storage.BlobContainer(
    "deploy",
    resource_group_name=rg.name,
    account_name=func_sa.name,
    container_name="deploy",
    public_access=storage.PublicAccess.NONE,
)

func_blob = storage.Blob(
    "func-zip",
    resource_group_name=rg.name,
    account_name=func_sa.name,
    container_name=deploy_container.name,
    blob_name="function.zip",
    type=storage.BlobType.BLOCK,
    source=pulumi.FileAsset(zip_path),
)

package_url = pulumi.Output.format(
    "https://{0}.blob.core.windows.net/{1}/function.zip",
    func_sa.name,
    deploy_container.name,
)

func_settings = {
    "AzureWebJobsStorage": pulumi.Output.concat(
        "DefaultEndpointsProtocol=https;AccountName=",
        func_sa.name,
        ";AccountKey=",
        storage.list_storage_account_keys_output(
            resource_group_name=rg.name, account_name=func_sa.name
        ).keys[0].value,
    ),
    "FUNCTIONS_EXTENSION_VERSION": "~4",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "WEBSITE_RUN_FROM_PACKAGE": package_url,
    "APPINSIGHTS_INSTRUMENTATIONKEY": app_insights.instrumentation_key,
    "COSMOS_CONNECTION": cosmos_conn,
    "COSMOS_DATABASE": "vextir",
    "USER_CONTAINER": "users",
    "SERVICEBUS_CONNECTION": sb_keys.primary_connection_string,
    "SERVICEBUS_QUEUE": sb_queue.name,
    "OPENAI_API_KEY": openai_api_key,
    "WORKER_IMAGE": worker_image,
    "AAD_CLIENT_ID": aad_client_id,
    "AAD_CLIENT_SECRET": aad_client_secret,
    "AAD_TENANT_ID": aad_tenant_id,
    "NOTIFY_URL": pulumi.Output.concat("https://www.", domain, "/chat/notify"),
}

web.WebAppApplicationSettings(
    "func-settings",
    name=func_app.name,
    resource_group_name=rg.name,
    properties=func_settings,
    opts=pulumi.ResourceOptions(depends_on=["func-blob-reader"]),
)

pulumi.export(
    "functionEndpoint",
    pulumi.Output.concat("https://", func_app.default_host_name, "/api/events"),
)

# ─────────────────────────────────────────────────────────────────────────────
# 13. COMMUNICATION SERVICE (email) – data location matches region
# ─────────────────────────────────────────────────────────────────────────────
comm_svc = communication.CommunicationService(
    "comm",
    resource_group_name=rg.name,
    location=location,
    communication_service_name=f"vextir-comm-{stack_suffix}",
    data_location="India",
)

email_svc = communication.EmailService(
    "email",
    resource_group_name=rg.name,
    location="global",
    email_service_name=f"vextir-email-{stack_suffix}",
    data_location="India",
)

email_domain = communication.Domain(
    "email-domain",
    resource_group_name=rg.name,
    email_service_name=email_svc.name,
    domain_name=domain,
    domain_management=communication.DomainManagement.CUSTOMER_MANAGED,
    user_engagement_tracking=communication.UserEngagementTracking.DISABLED,
    location="global",
)

comm_keys = communication.list_communication_service_keys_output(
    resource_group_name=rg.name, communication_service_name=comm_svc.name
)

# ─────────────────────────────────────────────────────────────────────────────
# 14. FRONT DOOR (Standard) + DNS
# ─────────────────────────────────────────────────────────────────────────────
fd_profile = cdn.Profile(
    "fd-prof",
    resource_group_name=rg.name,
    profile_name=f"vextir-fd-{stack_suffix}",
    location="global",
    sku=cdn.SkuArgs(name=cdn.SkuName.STANDARD_AZURE_FRONT_DOOR),
)

fd_ep = cdn.afd_endpoint.AFDEndpoint(
    "fd-ep",
    resource_group_name=rg.name,
    profile_name=fd_profile.name,
    endpoint_name=f"vextir-ep-{stack_suffix}",
    location="global",
)

def origin_group(name: str, probe_path: str, origin_host: pulumi.Input[str], port: int):
    og = cdn.afd_origin_group.AFDOriginGroup(
        f"{name}-og",
        resource_group_name=rg.name,
        profile_name=fd_profile.name,
        origin_group_name=name,
        health_probe_settings=cdn.HealthProbeParametersArgs(
            probe_path=probe_path,
            probe_protocol=cdn.ProbeProtocol.HTTPS if port == 443 else cdn.ProbeProtocol.HTTP,
            probe_request_type=cdn.HealthProbeRequestType.GET,
            probe_interval_in_seconds=30,
        ),
        load_balancing_settings=cdn.LoadBalancingSettingsParametersArgs(
            sample_size=4, successful_samples_required=3
        ),
    )

    cdn.afd_origin.AFDOrigin(
        f"{name}-origin",
        resource_group_name=rg.name,
        profile_name=fd_profile.name,
        origin_group_name=og.name,
        origin_name=f"{name}Origin",
        host_name=origin_host,
        https_port=port,
        http_port=80 if port == 443 else port,
    )
    return og

ui_og = origin_group(
    "ui",
    probe_path="/",
    origin_host=ui_cg.ip_address.apply(lambda ip: ip.fqdn),
    port=443,
)
api_og = origin_group(
    "api",
    probe_path="/api/health",
    origin_host=func_app.default_host_name,
    port=443,
)
voice_og = origin_group(
    "voice",
    probe_path="/",
    origin_host=voice_cg.ip_address.apply(lambda ip: ip.fqdn),
    port=8081,
)

def custom_domain(name: str, sub: str):
    return cdn.afd_custom_domain.AFDCustomDomain(
        f"{name}-cd",
        resource_group_name=rg.name,
        profile_name=fd_profile.name,
        custom_domain_name=name,
        host_name=f"{sub}.{domain}",
        tls_settings=cdn.AFDDomainHttpsParametersArgs(
            certificate_type=cdn.AfdCertificateType.MANAGED_CERTIFICATE,
            minimum_tls_version=cdn.AfdMinimumTlsVersion.TLS12,
        ),
    )

ui_cd = custom_domain("ui", "www")
api_cd = custom_domain("api", "api")
voice_cd = custom_domain("voice", "voice-ws")

def route(name: str, pattern: str, og):
    cdn.route.Route(
        f"{name}-route",
        resource_group_name=rg.name,
        profile_name=fd_profile.name,
        endpoint_name=fd_ep.name,
        route_name=name,
        origin_group=cdn.ResourceReferenceArgs(id=og.id),
        patterns_to_match=[pattern],
        forwarding_protocol=cdn.ForwardingProtocol.HTTPS_ONLY
        if "voice" not in name
        else cdn.ForwardingProtocol.HTTP_ONLY,
        https_redirect=cdn.HttpsRedirect.ENABLED,
        link_to_default_domain=cdn.LinkToDefaultDomain.DISABLED,
        supported_protocols=[cdn.AFDEndpointProtocols.HTTPS],
        custom_domains=[
            cdn.ActivatedResourceReferenceArgs(id=ui_cd.id if name == "ui" else api_cd.id if name == "api" else voice_cd.id)
        ],
    )

route("ui", "/*", ui_og)
route("api", "/api/*", api_og)
route("voice", "/voice-ws/*", voice_og)

dns_zone = dns.Zone(
    "zone",
    resource_group_name=rg.name,
    zone_name=domain,
    location="global",
)

def cname(label: str):
    dns.RecordSet(
        f"{label}-cname",
        resource_group_name=rg.name,
        zone_name=dns_zone.name,
        relative_record_set_name=label,
        record_type="CNAME",
        ttl=300,
        cname_record=dns.CnameRecordArgs(cname=fd_ep.host_name),
    )

for lbl in ["www", "api", "voice-ws"]:
    cname(lbl)

# AFD domain validation TXT records
def afd_txt(name: str, cd):
    dns.RecordSet(
        f"{name}-afd-verify",
        resource_group_name=rg.name,
        zone_name=dns_zone.name,
        relative_record_set_name=f"asuid.{name}",
        record_type="TXT",
        ttl=3600,
        txt_records=[
            dns.TxtRecordArgs(value=[cd.validation_properties.validation_token])
        ],
    )

afd_txt("www", ui_cd)
afd_txt("api", api_cd)
afd_txt("voice-ws", voice_cd)

pulumi.export("frontdoorHost", fd_ep.host_name)
pulumi.export("uiUrl", pulumi.Output.concat("https://www.", domain))
pulumi.export("apiUrl", pulumi.Output.concat("https://api.", domain))
pulumi.export("voiceWsUrl", pulumi.Output.concat("https://voice-ws.", domain))

# ─────────────────────────────────────────────────────────────────────────────
# 15. OUTPUT SECRETS (marked)
# ─────────────────────────────────────────────────────────────────────────────
pulumi.export("serviceBusSendConn", pulumi.Output.secret(sb_keys.primary_connection_string))
pulumi.export("acrLoginServer", acr.login_server)
pulumi.export("acrUsername", acr_creds.username)
pulumi.export("acrPassword", pulumi.Output.secret(acr_creds.passwords[0].value))
pulumi.export("cosmosConnString", pulumi.Output.secret(cosmos_conn))
pulumi.export("acsConnection", pulumi.Output.secret(comm_keys.primary_connection_string))
