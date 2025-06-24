###############################################################################
# vextir infra – DEV / Pilot‑ready  (budget ≈ $170 / mo)
# 2025‑06‑12
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
    applicationinsights,          # <‑‑ fixed
    privatedns,                   # <‑‑ NEW (correct module)
    app,                          # <‑‑ Container Apps
)
import pulumi_azuread as azuread
import pulumi_docker as docker

# ─────────────────────────────────────────────────────────────────────────────
# 1. CONFIG
# ─────────────────────────────────────────────────────────────────────────────
cfg = pulumi.Config()
stack_suffix = pulumi.get_stack()

location          = cfg.get("location") or "centralindia"
domain            = cfg.get("domain")   or "vextir.com"
worker_image      = cfg.get("workerImage")  or f"vextiracr{stack_suffix}.azurecr.io/lightning-worker:latest"
conseil_image     = cfg.get("conseilImage") or f"vextiracr{stack_suffix}.azurecr.io/conseil-agent:latest"
voice_ws_image    = cfg.get("voiceWsImage") or f"vextiracr{stack_suffix}.azurecr.io/voice-ws:latest"
# Image for the context hub container.
hub_image_cfg     = cfg.get("hubImage") or f"vextiracr{stack_suffix}.azurecr.io/context-hub:latest"
ui_image          = cfg.get("uiImage") or f"vextiracr{stack_suffix}.azurecr.io/integrated-ui:latest"

openai_api_key    = cfg.require_secret("openaiApiKey")
aad_client_id     = cfg.require_secret("aadClientId")
aad_client_secret = cfg.require_secret("aadClientSecret")
aad_tenant_id     = cfg.require("aadTenantId")
twilio_account_sid= cfg.require_secret("twilioAccountSid")
twilio_auth_token = cfg.require_secret("twilioAuthToken")


dns_suffix = cfg.get("dnsSuffix") or RandomString(
    "dns-suffix",
    length=10,
    upper=False,
    special=False,
).result
# ui_dns_label = pulumi.Output.concat("chat-ui-", dns_suffix)  # Not used anymore with Container Apps

client_cfg      = authorization.get_client_config()
subscription_id = client_cfg.subscription_id
tenant_id       = client_cfg.tenant_id

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
# 3. KEY VAULT (RBAC)  + Postgres secret
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

authorization.RoleAssignment(
    "kv-admin",
    principal_id = client_cfg.object_id,                  # who is running Pulumi
    principal_type = "ServicePrincipal",
    role_definition_id = (
        "/subscriptions/" + subscription_id +
        "/providers/Microsoft.Authorization/roleDefinitions/" +
        "00482a5a-887f-4fb3-b363-3b7fe8e74483"            # Key Vault Administrator
    ),
    scope = rg.id,
    role_assignment_name = str(uuid.uuid5(
        uuid.NAMESPACE_URL, f"{rg.name}-kv-admin-{client_cfg.object_id}"
    )),
)

# Allow the Pulumi service principal to manage Key Vault secrets
kv_secret_delete_guid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{stack_suffix}-kv-secret-delete"))
authorization.RoleAssignment(
    "pulumi-sp-secret-delete",
    principal_id=client_cfg.object_id,
    principal_type="ServicePrincipal",
    role_definition_id=pulumi.Output.concat(
        "/subscriptions/", subscription_id,
        "/providers/Microsoft.Authorization/roleDefinitions/b86a8fe4-44ce-4948-aee5-eccb2c155cd7",
    ),
    scope=vault.id,
    role_assignment_name=kv_secret_delete_guid,
)



# ─────────────────────────────────────────────────────────────────────────────
# 4. NETWORKING
# ─────────────────────────────────────────────────────────────────────────────
vnet = network.VirtualNetwork(
    "vnet",
    resource_group_name=rg.name,
    location=rg.location,
    virtual_network_name=f"vextir-vnet-{stack_suffix}",
    address_space=network.AddressSpaceArgs(address_prefixes=["10.0.0.0/16"]),
)

# Container Apps infrastructure subnet (requires /23 or larger)
# Note: Container Apps doesn't use delegation, unlike ACI
ca_subnet = network.Subnet(
    "ca-subnet",
    resource_group_name=rg.name,
    virtual_network_name=vnet.name,
    subnet_name="container-apps",
    address_prefix="10.0.8.0/23",  # Changed to avoid overlap
)

# Keep ACI subnet for Conseil (event-driven workload)
aci_subnet = network.Subnet(
    "aci-subnet",
    resource_group_name=rg.name,
    virtual_network_name=vnet.name,
    subnet_name="aci",
    address_prefix="10.0.4.0/24",
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
    opts=pulumi.ResourceOptions(
        delete_before_replace=False,  # ← prevents forced replacement
        ignore_changes=["addressPrefix", "delegations"],  # ← no diff noise
    ),
)

pe_subnet = network.Subnet(
    "pe-subnet",
    resource_group_name=rg.name,
    virtual_network_name=vnet.name,
    subnet_name="privatelink",
    address_prefix="10.0.2.0/24",
    service_endpoints=[
        network.ServiceEndpointPropertiesFormatArgs(service="Microsoft.Storage"),
        network.ServiceEndpointPropertiesFormatArgs(service="Microsoft.AzureCosmosDB"),
    ],
    opts=pulumi.ResourceOptions(
        delete_before_replace=False,
        ignore_changes=["addressPrefix"],
    ),
)

# **Only** Cosmos gets a private endpoint / private‑DNS zone
cosmos_zone = privatedns.PrivateZone(
    "cosmos-zone",
    resource_group_name=rg.name,
    private_zone_name="privatelink.documents.azure.com",
    location            = "global",
)

privatedns.VirtualNetworkLink(
    "cosmos-zone-link",
    resource_group_name=rg.name,
    private_zone_name=cosmos_zone.name,
    virtual_network_link_name="link-cosmos",
    virtual_network=privatedns.SubResourceArgs(id=vnet.id),
    registration_enabled=False,
    location="global",  # privatedns links require location 'global'
)

# ─────────────────────────────────────────────────────────────────────────────
# 5. LOG ANALYTICS + APP INSIGHTS  (App Insights Component = correct type)
# ─────────────────────────────────────────────────────────────────────────────
workspace = operationalinsights.Workspace(
    "log",
    resource_group_name=rg.name,
    workspace_name=f"vextir-logs-{stack_suffix}",
    location=rg.location,
    sku=operationalinsights.WorkspaceSkuArgs(name="PerGB2018"),
    retention_in_days=30,
)
workspace_keys = operationalinsights.get_shared_keys_output(
    resource_group_name=rg.name, workspace_name=workspace.name
)
app_insights = applicationinsights.Component(
    "ai",
    resource_group_name=rg.name,
    application_type="web",
    kind="web",
    workspace_resource_id=workspace.id,
    location=rg.location,
)

# ─────────────────────────────────────────────────────────────────────────────
# 6. COSMOS DB (Serverless mode)
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
    "users",
    account_name=cosmos_account.name,
    resource_group_name=rg.name,
    database_name=cosmos_db.name,
    container_name="users",
    resource=cosmosdb.SqlContainerResourceArgs(
        id="users",
        partition_key=cosmosdb.ContainerPartitionKeyArgs(paths=["/pk"], kind="Hash"),
    ),
)
cosmos_conn = cosmosdb.list_database_account_connection_strings_output(
    account_name=cosmos_account.name,
    resource_group_name=rg.name,
).connection_strings[0].connection_string

cosmos_pe = network.PrivateEndpoint(
    "cosmos-pe",
    resource_group_name=rg.name,
    private_endpoint_name=f"cosmos-pe-{stack_suffix}",
    subnet=network.SubnetArgs(id=pe_subnet.id),
    location=rg.location,
    private_link_service_connections=[
        network.PrivateLinkServiceConnectionArgs(
            name="cosmos",
            private_link_service_id=cosmos_account.id,
            group_ids=["Sql"],
            private_link_service_connection_state=network.PrivateLinkServiceConnectionStateArgs(
                status="Approved", description="Auto‑approved"
            ),
        )
    ],
)
network.PrivateDnsZoneGroup(
    "cosmos-pe-dns",
    resource_group_name=rg.name,
    private_endpoint_name=cosmos_pe.name,
    private_dns_zone_group_name="cosmosz",
    private_dns_zone_configs=[
        network.PrivateDnsZoneConfigArgs(
            name="cfg", private_dns_zone_id=cosmos_zone.id
        )
    ],
)

# ─────────────────────────────────────────────────────────────────────────────
# 7. STORAGE ACCOUNTS  (function + repo)
# ─────────────────────────────────────────────────────────────────────────────
func_sa = storage.StorageAccount(
    "funcsa",
    resource_group_name=rg.name,
    kind=storage.Kind.STORAGE_V2,
    sku=storage.SkuArgs(name=storage.SkuName.STANDARD_LRS),
    location=rg.location,
)

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

# Use the configured hub image directly (no Docker build)
hub_image = hub_image_cfg

# ─────────────────────────────────────────────────────────────────────────────
# 9. SERVICE BUS
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
    "send",
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
# 10. AAD APP
# ─────────────────────────────────────────────────────────────────────────────
aad_app = azuread.Application(
    "aad-app",
    display_name=f"Vextir-{stack_suffix}",
    sign_in_audience="AzureADMultipleOrgs",  # Enable multi-tenant support
    web=azuread.ApplicationWebArgs(
        redirect_uris=[
            pulumi.Output.concat("https://", domain, "/auth/callback"),
            pulumi.Output.concat("https://www.", domain, "/auth/callback"),
            pulumi.Output.concat("https://hub.", domain, "/auth/callback"),
            # Support legacy redirect to /auth/login
            pulumi.Output.concat("https://", domain, "/auth/login"),
            pulumi.Output.concat("https://www.", domain, "/auth/login"),
            pulumi.Output.concat("https://hub.", domain, "/auth/login"),
        ]
    ),
    # Enable public client for desktop apps
    public_client=azuread.ApplicationPublicClientArgs(
        redirect_uris=[
            "http://localhost:9899/callback",  # Desktop app callback
            "ms-appx-web://microsoft.aad.brokerplugin/YOUR_CLIENT_ID",  # Windows broker
        ]
    ),
    # API configuration for v2.0 tokens
    api=azuread.ApplicationApiArgs(
        requested_access_token_version=2,
    ),
    # Required permissions
    required_resource_accesses=[
        azuread.ApplicationRequiredResourceAccessArgs(
            resource_app_id="00000003-0000-0000-c000-000000000000",  # Microsoft Graph
            resource_accesses=[
                azuread.ApplicationRequiredResourceAccessResourceAccessArgs(
                    id="e1fe6dd8-ba31-4d61-89e7-88639da4683d",  # User.Read
                    type="Scope",
                ),
                azuread.ApplicationRequiredResourceAccessResourceAccessArgs(
                    id="64a6cdd6-aab1-4aaf-94b8-3cc8405e90d0",  # email
                    type="Scope",
                ),
                azuread.ApplicationRequiredResourceAccessResourceAccessArgs(
                    id="14dad69e-099b-42c9-810b-d002981feec1",  # profile
                    type="Scope",
                ),
                azuread.ApplicationRequiredResourceAccessResourceAccessArgs(
                    id="7427e0e9-2fba-42fe-b0c0-848c9e6a8182",  # offline_access
                    type="Scope",
                ),
            ],
        ),
    ],
    # App roles for RBAC
    app_roles=[
        azuread.ApplicationAppRoleArgs(
            allowed_member_types=["User"],
            description="Context Hub administrators",
            display_name="Context Hub Admin",
            enabled=True,
            id=str(uuid.uuid4()),
            value="ContextHub.Admin",
        ),
        azuread.ApplicationAppRoleArgs(
            allowed_member_types=["User"],
            description="Context Hub users",
            display_name="Context Hub User",
            enabled=True,
            id=str(uuid.uuid4()),
            value="ContextHub.User",
        ),
    ],
    # Group membership claims
    group_membership_claims=["SecurityGroup"],
)

aad_sp = azuread.ServicePrincipal("aad-sp", client_id=aad_app.client_id)
aad_password = azuread.ApplicationPassword(
    "aad-pwd",
    application_id=aad_app.id,
    end_date=(datetime.datetime.utcnow() + datetime.timedelta(days=730)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    ),
)
pulumi.export("aadClientId", aad_app.client_id)
pulumi.export("aadClientSecret", pulumi.Output.secret(aad_password.value))

# Desktop app configuration
pulumi.export("desktopAppConfig", pulumi.Output.all(aad_app.client_id, aad_tenant_id).apply(
    lambda args: {
        "clientId": args[0],
        "tenantId": args[1],
        "redirectUri": "http://localhost:9899/callback",
        "authority": f"https://login.microsoftonline.com/{args[1]}",
        "scopes": ["User.Read", "email", "profile", "offline_access"],
    }
))

# JWKS URL for token validation
pulumi.export("jwksUrl", pulumi.Output.concat(
    "https://login.microsoftonline.com/", aad_tenant_id, "/discovery/v2.0/keys"
))

# ─────────────────────────────────────────────────────────────────────────────
# 11. CONTAINER APPS ENVIRONMENT
# ─────────────────────────────────────────────────────────────────────────────
ca_env = app.ManagedEnvironment(
    "ca-env",
    resource_group_name=rg.name,
    location=rg.location,
    environment_name=f"vextir-env-{stack_suffix}",
    vnet_configuration=app.VnetConfigurationArgs(
        infrastructure_subnet_id=ca_subnet.id,
    ),
    app_logs_configuration=app.AppLogsConfigurationArgs(
        destination="log-analytics",
        log_analytics_configuration=app.LogAnalyticsConfigurationArgs(
            customer_id=workspace.customer_id,
            shared_key=operationalinsights.get_shared_keys_output(
                resource_group_name=rg.name,
                workspace_name=workspace.name
            ).primary_shared_key,
        ),
    ),
    zone_redundant=False,  # Set to True for production
)

# ─────────────────────────────────────────────────────────────────────────────
# 12. HELPER – ACI CONTAINER GROUP (for Conseil only)
# ─────────────────────────────────────────────────────────────────────────────
def aci_group(
    name: str,
    image: pulumi.Input[str],
    port: int,
    env: list[containerinstance.EnvironmentVariableArgs],
    volumes=None,
    cmd: list[str] | None = None,
    cpu: float = 1,
    mem: float = 1.5,
    public: bool = False,
    liveness_delay: int = 30,
    readiness_delay: int = 10,
):
    ip_cfg, subnet_ids = (
        # PUBLIC ✔ – no VNet attachment
        (
            containerinstance.IpAddressArgs(
                type = containerinstance.ContainerGroupIpAddressType.PUBLIC,
                ports=[containerinstance.PortArgs(protocol="TCP", port=port)],
                dns_name_label=pulumi.Output.concat(name, "-", dns_suffix),
            ),
            None,                                       # ← no subnet_ids
        )
        if public
        else
        # PRIVATE ✔ – inside VNet
        (
            containerinstance.IpAddressArgs(
                type = containerinstance.ContainerGroupIpAddressType.PRIVATE,
                ports=[containerinstance.PortArgs(protocol="TCP", port=port)],
            ),
            [containerinstance.ContainerGroupSubnetIdArgs(id=aci_subnet.id)],
        )
    )

    # ---------- decide lazily whether we need ACR creds ---------------------
    # ‑ Pulumi resolves both `image` and `acr.login_server` first,
    #   then the lambda runs.
    cred_obj = containerinstance.ImageRegistryCredentialArgs(
        server   = acr.login_server,
        username = acr_creds.username,
        password = acr_creds.passwords[0].value,
    )
    registry_creds = pulumi.Output.all(image, acr.login_server).apply(
        lambda pair: [cred_obj] if pair[0].startswith(pair[1]) else None
    )
    # ------------------------------------------------------------------------

    return containerinstance.ContainerGroup(
        name,
        resource_group_name=rg.name,
        location=rg.location,
        container_group_name=name,
        os_type="Linux",
        subnet_ids=subnet_ids,
        ip_address=ip_cfg,
        restart_policy=containerinstance.ContainerGroupRestartPolicy.ON_FAILURE,  # Better restart policy
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
                command=cmd,
                volume_mounts=[
                    containerinstance.VolumeMountArgs(
                        name=v.name, mount_path="/mnt/" + v.name
                    )
                    for v in volumes or []
                ],
                # Health probes ensure the container is restarted when unresponsive
                liveness_probe=containerinstance.ContainerProbeArgs(
                    http_get=containerinstance.ContainerHttpGetArgs(
                        path="/health" if name in ["chatui", "contexthub"] else "/",
                        port=port,
                        scheme=containerinstance.Scheme.HTTP,
                    ),
                    initial_delay_seconds=liveness_delay,
                    period_seconds=10,
                    failure_threshold=3,
                    timeout_seconds=5,
                )
                if name in ["chatui", "voicews", "contexthub"]
                else None,
                readiness_probe=containerinstance.ContainerProbeArgs(
                    http_get=containerinstance.ContainerHttpGetArgs(
                        path="/health" if name in ["chatui", "contexthub"] else "/",
                        port=port,
                        scheme=containerinstance.Scheme.HTTP,
                    ),
                    initial_delay_seconds=readiness_delay,
                    period_seconds=5,
                    failure_threshold=3,
                    timeout_seconds=5,
                )
                if name in ["chatui", "voicews", "contexthub"]
                else None,
            )
        ],
        volumes=volumes,
        diagnostics=containerinstance.ContainerGroupDiagnosticsArgs(
            log_analytics=containerinstance.LogAnalyticsArgs(
                workspace_id=workspace.customer_id,
                workspace_key=workspace_keys.primary_shared_key,
                workspace_resource_id=workspace.id,
                log_type=containerinstance.LogAnalyticsLogType.CONTAINER_INSIGHTS,  # Enhanced logging
            )
        ),
        image_registry_credentials=registry_creds,
        opts=pulumi.ResourceOptions(
            replace_on_changes=["containers", "restart_policy"],
            delete_before_replace=True,
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 13. HELPER - CONTAINER APPS
# ─────────────────────────────────────────────────────────────────────────────
def create_container_app(
    name: str,
    image: pulumi.Input[str],
    port: int,
    env_vars: list[app.EnvironmentVarArgs],
    secrets: list[app.SecretArgs] = None,
    min_replicas: int = 0,
    max_replicas: int = 10,
    cpu: float = 0.5,
    memory: str = "1Gi",
    external: bool = True,
    health_path: str = "/health",
    scale_rules: list[app.ScaleRuleArgs] = None,
):
    """Create a Container App with standard configuration."""
    
    # Build registry credential if using ACR
    registry_creds = pulumi.Output.all(image, acr.login_server).apply(
        lambda pair: [app.RegistryCredentialsArgs(
            server=acr.login_server,
            username=acr_creds.username,
            password_secret_ref="acr-password",
        )] if pair[0].startswith(pair[1]) else []
    )
    
    # Add ACR password to secrets if needed
    if secrets is None:
        secrets = []
    
    secrets.append(app.SecretArgs(
        name="acr-password",
        value=acr_creds.passwords[0].value,
    ))
    
    return app.ContainerApp(
        name,
        resource_group_name=rg.name,
        location=rg.location,
        container_app_name=f"{name}-{stack_suffix}",
        managed_environment_id=ca_env.id,
        configuration=app.ConfigurationArgs(
            ingress=app.IngressArgs(
                external=external,
                target_port=port,
                transport="auto",  # Supports both HTTP and WebSocket
                allow_insecure=False,
                traffic=[app.TrafficWeightArgs(latest_revision=True, weight=100)],
            ) if external else None,
            registries=registry_creds,
            secrets=secrets,
        ),
        template=app.TemplateArgs(
            containers=[
                app.ContainerArgs(
                    name=name,
                    image=image,
                    resources=app.ContainerResourcesArgs(
                        cpu=cpu,
                        memory=memory,
                    ),
                    env=env_vars,
                    probes=[
                        app.ContainerAppProbeArgs(
                            type="Liveness",
                            http_get=app.ContainerAppProbeHttpGetArgs(
                                path=health_path,
                                port=port,
                            ),
                            initial_delay_seconds=30,
                            period_seconds=10,
                            failure_threshold=3,
                            timeout_seconds=5,
                        ),
                        app.ContainerAppProbeArgs(
                            type="Readiness",
                            http_get=app.ContainerAppProbeHttpGetArgs(
                                path=health_path,
                                port=port,
                            ),
                            initial_delay_seconds=10,
                            period_seconds=5,
                            failure_threshold=3,
                            timeout_seconds=5,
                        ),
                    ] if health_path else [],
                )
            ],
            scale=app.ScaleArgs(
                min_replicas=min_replicas,
                max_replicas=max_replicas,
                rules=scale_rules or [],
            ),
        ),
    )


# UI container moved after function app definition

# Voice WebSocket Container App (replaced ACI with Container Apps)
voice_secrets = [
    app.SecretArgs(name="openai-api-key", value=openai_api_key),
    app.SecretArgs(name="twilio-account-sid", value=twilio_account_sid),
    app.SecretArgs(name="twilio-auth-token", value=twilio_auth_token),
    app.SecretArgs(name="cosmos-connection", value=cosmos_conn),
]

voice_ca = create_container_app(
    "voicews",
    voice_ws_image,
    8081,
    [
        app.EnvironmentVarArgs(name="OPENAI_API_KEY", secret_ref="openai-api-key"),
        app.EnvironmentVarArgs(name="TWILIO_ACCOUNT_SID", secret_ref="twilio-account-sid"),
        app.EnvironmentVarArgs(name="TWILIO_AUTH_TOKEN", secret_ref="twilio-auth-token"),
        app.EnvironmentVarArgs(name="PUBLIC_URL", value=pulumi.Output.concat("https://voice-ws.", domain)),
        app.EnvironmentVarArgs(name="COSMOS_CONNECTION", secret_ref="cosmos-connection"),
        app.EnvironmentVarArgs(name="COSMOS_DATABASE", value=cosmos_db.name),
        app.EnvironmentVarArgs(name="USER_CONTAINER", value=user_container.name),
    ],
    secrets=voice_secrets,
    min_replicas=1,  # WebSocket needs to be always on
    max_replicas=10,
    external=True,
)

conseil_cg = aci_group(
    "conseil",
    conseil_image,
    8080,
    [
        containerinstance.EnvironmentVariableArgs(name="OPENAI_API_KEY", secure_value=openai_api_key),
        containerinstance.EnvironmentVariableArgs(name="NODE_ENV", value="production"),
        containerinstance.EnvironmentVariableArgs(name="CONSEIL_MODE", value="server"),
    ],
    cmd=["node", "dist/cli.js", "--help"],
    public=False,  # Internal service for agent execution
)

# Context Hub Container App (replaced ACI with Container Apps)
hub_secrets = [
    app.SecretArgs(name="jwt-secret", value=aad_password.value),
    app.SecretArgs(name="cosmos-connection", value=cosmos_conn),
]

hub_ca = create_container_app(
    "contexthub",
    hub_image,
    3000,
    [
        app.EnvironmentVarArgs(name="AZURE_JWKS_URL", value=pulumi.Output.concat("https://login.microsoftonline.com/", aad_tenant_id, "/discovery/v2.0/keys")),
        app.EnvironmentVarArgs(name="AAD_CLIENT_ID", value=aad_app.client_id),
        app.EnvironmentVarArgs(name="AAD_TENANT_ID", value=aad_tenant_id),
        app.EnvironmentVarArgs(name="JWT_SECRET", secret_ref="jwt-secret"),
        app.EnvironmentVarArgs(name="PORT", value="3000"),
        app.EnvironmentVarArgs(name="COSMOS_CONNECTION_STRING", secret_ref="cosmos-connection"),
        app.EnvironmentVarArgs(name="COSMOS_DATABASE", value="context-hub"),
        app.EnvironmentVarArgs(name="COSMOS_CONTAINER", value="contexts"),
    ],
    secrets=hub_secrets,
    min_replicas=1,  # Always on for hub
    max_replicas=5,
    external=True,
    health_path=None,  # Disable health probes temporarily
)

# Get internal URL for hub (for other services to use)
hub_internal_url = pulumi.Output.concat("https://", hub_ca.configuration.ingress.fqdn)

# Export Container Apps FQDNs
pulumi.export("voiceWsFqdn", voice_ca.configuration.ingress.fqdn)
pulumi.export("conseilIp", conseil_cg.ip_address.apply(lambda ip: ip.ip))
pulumi.export("contextHubFqdn", hub_ca.configuration.ingress.fqdn)

# ─────────────────────────────────────────────────────────────────────────────
# 14. COMMUNICATION SERVICE  (kept data_location="United States" – supported)
# ─────────────────────────────────────────────────────────────────────────────
comm_svc = communication.CommunicationService(
    "comm",
    resource_group_name=rg.name,
    location="global",
    communication_service_name=f"vextir-comm-{stack_suffix}",
    data_location="United States",
)
email_svc = communication.EmailService(
    "email",
    resource_group_name=rg.name,
    location="global",
    email_service_name=f"vextir-email-{stack_suffix}",
    data_location="United States",
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
# 15. FUNCTION APP
# ─────────────────────────────────────────────────────────────────────────────
plan = web.AppServicePlan(
    "func-plan",
    resource_group_name=rg.name,
    kind="FunctionApp",
    sku=web.SkuDescriptionArgs(tier="Dynamic", name="Y1"),
    location=rg.location,
    reserved=True,  # Required for Linux plans
)
func_app = web.WebApp(
    "func",
    resource_group_name=rg.name,
    location=rg.location,
    server_farm_id=plan.id,
    kind="FunctionApp",
    identity=web.ManagedServiceIdentityArgs(type=web.ManagedServiceIdentityType.SYSTEM_ASSIGNED),
    site_config=web.SiteConfigArgs(linux_fx_version="python|3.10"),
)

# Role assignment: Storage Blob Data Reader
assign_guid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{stack_suffix}-func-blob-reader"))
func_blob_reader = authorization.RoleAssignment(
    "func-blob-reader",
    principal_id=func_app.identity.principal_id,
    principal_type="ServicePrincipal",
    role_definition_id=pulumi.Output.concat(
        "/subscriptions/", subscription_id,
        "/providers/Microsoft.Authorization/roleDefinitions/2a2b9908-6ea1-4ae2-8e65-a410df84e7d1"
    ),
    scope=func_sa.id,
    role_assignment_name=assign_guid,
)

# ZIP‑deploy package (only built during non‑preview runs)
def build_zip():
    build_dir = Path(tempfile.mkdtemp())
    shutil.copytree("../azure-function", build_dir / "azure-function", dirs_exist_ok=True)
    for extra in ("../events", "../common"):
        if Path(extra).is_dir():
            shutil.copytree(extra, build_dir / Path(extra).name, dirs_exist_ok=True)
    site_pkgs = build_dir / ".python_packages" / "lib" / "site-packages"
    site_pkgs.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-r", "../azure-function/requirements.txt", "--target", str(site_pkgs)]
    )
    zip_path = Path(tempfile.mktemp(suffix=".zip"))
    shutil.make_archive(zip_path.with_suffix(""), "zip", build_dir)
    return str(zip_path)

if runtime.is_dry_run():
    # Preview phase – create an in‑memory empty asset
    zip_asset = pulumi.StringAsset("")          # <── NEW
else:
    zip_path  = build_zip()
    zip_asset = pulumi.FileAsset(zip_path)      # <── NEW

deploy_container = storage.BlobContainer(
    "deploy",
    resource_group_name=rg.name,
    account_name=func_sa.name,
    container_name="deploy",
    public_access=storage.PublicAccess.NONE,
)
storage.Blob(
    "func-zip",
    resource_group_name=rg.name,
    account_name=func_sa.name,
    container_name=deploy_container.name,
    blob_name="function.zip",
    type=storage.BlobType.BLOCK,
    source=zip_asset,
)
pkg_url = pulumi.Output.format(
    "https://{0}.blob.core.windows.net/{1}/function.zip", func_sa.name, deploy_container.name
)

func_settings = {
    "AzureWebJobsStorage": pulumi.Output.concat(
        "DefaultEndpointsProtocol=https;AccountName=", func_sa.name,
        ";AccountKey=", storage.list_storage_account_keys_output(
            resource_group_name=rg.name, account_name=func_sa.name
        ).keys[0].value),
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "FUNCTIONS_EXTENSION_VERSION": "~4",
    "WEBSITE_RUN_FROM_PACKAGE": pkg_url,
    "APPINSIGHTS_INSTRUMENTATIONKEY": app_insights.instrumentation_key,
    "COSMOS_CONNECTION": cosmos_conn,
    "COSMOS_DATABASE": "vextir",
    "USER_CONTAINER": "users",
    "SERVICEBUS_CONNECTION": sb_keys.primary_connection_string,
    "SERVICEBUS_QUEUE": sb_queue.name,
    "OPENAI_API_KEY": openai_api_key,
    "WORKER_IMAGE": worker_image,
    "CONSEIL_IMAGE": conseil_image,
    "AAD_CLIENT_ID": aad_app.client_id,
    "AAD_CLIENT_SECRET": aad_password.value,
    "AAD_TENANT_ID": aad_tenant_id,
    "NOTIFY_URL": pulumi.Output.concat("https://www.", domain, "/chat/notify"),
    "HUB_URL": hub_internal_url,
    "CONSEIL_URL": conseil_cg.ip_address.apply(lambda ip: f"http://{ip.ip}:8080"),
    "ACS_CONNECTION": comm_keys.primary_connection_string,
    "ACS_SENDER": pulumi.Output.concat("no-reply@", domain),
    "VERIFY_BASE": pulumi.Output.concat("https://www.", domain),
}
web.WebAppApplicationSettings(
    "func-settings",
    name=func_app.name,
    resource_group_name=rg.name,
    properties=func_settings,
    opts=pulumi.ResourceOptions(depends_on=[func_blob_reader]),
)
pulumi.export("functionEndpoint", pulumi.Output.concat("https://", func_app.default_host_name, "/api/events"))

# UI Container App (replaced ACI with Container Apps)
ui_secrets = [
    app.SecretArgs(name="aad-client-secret", value=aad_password.value),
    app.SecretArgs(name="session-secret", value=aad_password.value),
]

ui_ca = create_container_app(
    "chatui",
    ui_image,
    8080,  # Changed from 8000 to 8080
    [
        app.EnvironmentVarArgs(name="API_BASE", value=pulumi.Output.concat("https://", func_app.default_host_name)),
        app.EnvironmentVarArgs(name="EVENT_API_URL", value=pulumi.Output.concat("https://", func_app.default_host_name, "/api/events")),
        app.EnvironmentVarArgs(name="AUTH_API_URL", value=pulumi.Output.concat("https://", func_app.default_host_name, "/api")),
        app.EnvironmentVarArgs(name="AAD_CLIENT_ID", value=aad_app.client_id),
        app.EnvironmentVarArgs(name="AAD_CLIENT_SECRET", secret_ref="aad-client-secret"),
        app.EnvironmentVarArgs(name="AAD_TENANT_ID", value=aad_tenant_id),
        app.EnvironmentVarArgs(name="SESSION_SECRET", secret_ref="session-secret"),
        app.EnvironmentVarArgs(name="APPINSIGHTS_INSTRUMENTATIONKEY", value=app_insights.instrumentation_key),
        app.EnvironmentVarArgs(name="CHAINLIT_URL", value=pulumi.Output.concat("https://www.", domain, "/chat")),
        app.EnvironmentVarArgs(name="DEPLOYMENT_ID", value="container-apps-v1"),
        app.EnvironmentVarArgs(name="PYTHONUNBUFFERED", value="1"),
        app.EnvironmentVarArgs(name="PYTHONDONTWRITEBYTECODE", value="1"),
        app.EnvironmentVarArgs(name="LOG_LEVEL", value="INFO"),
        app.EnvironmentVarArgs(name="PORT", value="8080"),  # Ensure app runs on correct port
        app.EnvironmentVarArgs(name="AUTH_ENABLED", value="true"),  # Enable authentication
        app.EnvironmentVarArgs(name="AUTH_GATEWAY_URL", value=pulumi.Output.concat("https://", func_app.default_host_name, "/api/auth")),
        app.EnvironmentVarArgs(name="CONTEXT_HUB_URL", value=pulumi.Output.concat("https://", hub_ca.configuration.ingress.fqdn)),
        app.EnvironmentVarArgs(name="HUB_URL", value=pulumi.Output.concat("https://", hub_ca.configuration.ingress.fqdn)),
    ],
    secrets=ui_secrets,
    min_replicas=1,  # UI should be always on
    max_replicas=10,
    cpu=0.5,
    memory="1Gi",
    external=True,
    health_path=None,  # Disable health probes for now
    scale_rules=[
        app.ScaleRuleArgs(
            name="http-rule",
            http=app.HttpScaleRuleArgs(
                metadata={"concurrentRequests": "50"},
            ),
        ),
    ],
)

# Export UI FQDN
pulumi.export("uiFqdn", ui_ca.configuration.ingress.fqdn)

# ─────────────────────────────────────────────────────────────────────────────
# 16. FRONT DOOR + DNS (Updated for Container Apps)
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

def origin_group(
    name: str,
    probe_path: str,
    host: pulumi.Input[str],
    port: int,
    https: bool = True,
    host_header: pulumi.Input[str] | None = None,
    *,
    enforce_cert: bool = True,
):
    protocol = cdn.ProbeProtocol.HTTPS if https else cdn.ProbeProtocol.HTTP
    og = cdn.afd_origin_group.AFDOriginGroup(
        f"{name}-og",
        resource_group_name=rg.name,
        profile_name=fd_profile.name,
        origin_group_name=name,
        health_probe_settings=cdn.HealthProbeParametersArgs(
            probe_path=probe_path,
            probe_protocol=protocol,
            probe_request_type=cdn.HealthProbeRequestType.GET,
            probe_interval_in_seconds=30,
        ),
        load_balancing_settings = cdn.LoadBalancingSettingsParametersArgs(
            sample_size                 = 4,
            successful_samples_required = 3,
            additional_latency_in_milliseconds = 0,
        ),
    )
    origin = cdn.afd_origin.AFDOrigin(
        f"{name}-origin",
        resource_group_name=rg.name,
        profile_name=fd_profile.name,
        origin_group_name=og.name,
        origin_name=f"{name}Origin",
        host_name=host,
        origin_host_header=host_header or host,
        http_port=port if not https else None,
        https_port=port if https else None,
        enabled_state=cdn.EnabledState.ENABLED,
        enforce_certificate_name_check=enforce_cert,
    )
    return og, origin

# Container Apps use HTTPS with managed certificates
ui_og, ui_origin = origin_group(
    "ui",
    "/health",
    ui_ca.configuration.ingress.fqdn,
    443,
    https=True,
    # Don't override host header - Container Apps need their own FQDN
)
api_og, api_origin = origin_group(
    "api",
    "/api/health",
    func_app.default_host_name,
    443,
    https=True,
    # Use the function app's default hostname for the host header so
    # requests succeed even if the custom domain is not bound yet. Azure
    # provides a managed certificate for *.azurewebsites.net so the
    # Front Door to Function App connection is valid over HTTPS.
    host_header=func_app.default_host_name,
)
voice_og, voice_origin = origin_group(
    "voice",
    "/health",
    voice_ca.configuration.ingress.fqdn,
    443,
    https=True,
    # Don't override host header - Container Apps need their own FQDN
)
hub_og, hub_origin = origin_group(
    "hub",
    "/health",
    hub_ca.configuration.ingress.fqdn,
    443,
    https=True,
    # Don't override host header - Container Apps need their own FQDN
)


def afd_domain(label, sub):
    return cdn.afd_custom_domain.AFDCustomDomain(
        f"{label}-cd",
        resource_group_name=rg.name,
        profile_name=fd_profile.name,
        custom_domain_name=label,
        host_name=f"{sub}.{domain}",
        tls_settings=cdn.AFDDomainHttpsParametersArgs(
            certificate_type=cdn.AfdCertificateType.MANAGED_CERTIFICATE,
            minimum_tls_version=cdn.AfdMinimumTlsVersion.TLS12,
        ),
    )
ui_cd   = afd_domain("ui",   "www")
api_cd  = afd_domain("api",  "api")
voice_cd= afd_domain("voice","voice-ws")
hub_cd  = afd_domain("hub",  "hub")

def afd_route(name, pattern, og, origin, cd, fp):
    cdn.route.Route(
        f"{name}-route",
        resource_group_name=rg.name,
        profile_name=fd_profile.name,
        endpoint_name=fd_ep.name,
        route_name=name,
        origin_group=cdn.ResourceReferenceArgs(id=og.id),
        patterns_to_match=[pattern],
        forwarding_protocol=fp,
        https_redirect=cdn.HttpsRedirect.ENABLED,
        link_to_default_domain=cdn.LinkToDefaultDomain.DISABLED,
        supported_protocols=[cdn.AFDEndpointProtocols.HTTPS],
        custom_domains=[cdn.ActivatedResourceReferenceArgs(id=cd.id)],
        opts=pulumi.ResourceOptions(depends_on=[og, origin]),
    )
afd_route("ui",    "/*",           ui_og, ui_origin,   ui_cd,   cdn.ForwardingProtocol.HTTPS_ONLY)
afd_route(
    "api",
    "/api/*",
    api_og,
    api_origin,
    api_cd,
    cdn.ForwardingProtocol.HTTPS_ONLY,
)
afd_route("voice", "/voice-ws/*",  voice_og, voice_origin, voice_cd, cdn.ForwardingProtocol.HTTPS_ONLY)
afd_route("hub",   "/*",           hub_og, hub_origin,   hub_cd,   cdn.ForwardingProtocol.HTTPS_ONLY)

dns_zone = dns.Zone(
    "zone",
    resource_group_name=rg.name,
    zone_name=domain,
    location="global",
)
def cname(label):
    dns.RecordSet(
        f"{label}-cname",
        resource_group_name=rg.name,
        zone_name=dns_zone.name,
        relative_record_set_name=label,
        record_type="CNAME",
        ttl=300,
        cname_record=dns.CnameRecordArgs(cname=fd_ep.host_name),
    )
for lbl in ["www", "api", "voice-ws", "hub"]:
    cname(lbl)

api_asuid = dns.RecordSet(
    "api-asuid",
    resource_group_name=rg.name,
    zone_name=dns_zone.name,
    relative_record_set_name="asuid.api",
    record_type="TXT",
    ttl=3600,
    txt_records=[dns.TxtRecordArgs(value=[func_app.custom_domain_verification_id])],
)
def afd_txt(label, cd):
    dns.RecordSet(
        f"{label}-afd-txt",
        resource_group_name=rg.name,
        zone_name=dns_zone.name,
        relative_record_set_name=f"_dnsauth.{label}",
        record_type="TXT",
        ttl=3600,
        txt_records=[dns.TxtRecordArgs(value=[cd.validation_properties.validation_token])],
    )
afd_txt("www",      ui_cd)
afd_txt("api",      api_cd)
afd_txt("voice-ws", voice_cd)
afd_txt("hub",      hub_cd)

web.WebAppHostNameBinding(
    "api-hostname",
    resource_group_name=rg.name,
    name=func_app.name,
    site_name=func_app.name,
    host_name=pulumi.Output.concat("api.", domain),
    azure_resource_name=func_app.name,
    azure_resource_type=web.AzureResourceType.WEBSITE,
    custom_host_name_dns_record_type=web.CustomHostNameDnsRecordType.C_NAME,
    host_name_type=web.HostNameType.VERIFIED,
    ssl_state=web.SslState.DISABLED,
    opts=pulumi.ResourceOptions(depends_on=[api_asuid]),
)

pulumi.export("frontdoorHost", fd_ep.host_name)
pulumi.export("uiUrl",        pulumi.Output.concat("https://www.",   domain))
pulumi.export("apiUrl",       pulumi.Output.concat("https://api.",   domain))
pulumi.export("voiceWsUrl",   pulumi.Output.concat("https://voice-ws.", domain))
pulumi.export("hubUrl",       pulumi.Output.concat("https://hub.", domain))

# ─────────────────────────────────────────────────────────────────────────────
# 15. SECURE OUTPUTS
# ─────────────────────────────────────────────────────────────────────────────
pulumi.export("serviceBusConnection", pulumi.Output.secret(sb_keys.primary_connection_string))
pulumi.export("acrLoginServer", acr.login_server)
pulumi.export("acrUsername",    acr_creds.username)
pulumi.export("acrPassword",    pulumi.Output.secret(acr_creds.passwords[0].value))
pulumi.export("cosmosConn",     pulumi.Output.secret(cosmos_conn))
pulumi.export("acsConnection",  pulumi.Output.secret(comm_keys.primary_connection_string))

# Container Apps exports
pulumi.export("containerAppsEnvironment", ca_env.name)
pulumi.export("uiContainerAppUrl", ui_ca.configuration.ingress.fqdn)
pulumi.export("voiceContainerAppUrl", voice_ca.configuration.ingress.fqdn)
pulumi.export("hubContainerAppUrl", hub_ca.configuration.ingress.fqdn)
pulumi.export("conseilInternalUrl", conseil_cg.ip_address.apply(lambda ip: f"http://{ip.ip}:8080"))
