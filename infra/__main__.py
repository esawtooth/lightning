import pulumi
import os
import zipfile
import tempfile
import datetime
import atexit
from pulumi_azure_native import (
    resources,
    servicebus,
    storage,
    web,
    authorization,
    containerinstance,
    containerregistry,
)

# Cosmos DB resources live in a separate module
from pulumi_azure_native import cosmosdb
from pulumi_azure_native.authorization import get_client_config, RoleAssignment

config = pulumi.Config()
location = config.get("location") or "centralindia"
openai_api_key = config.require_secret("openaiApiKey")
jwt_signing_key = config.require_secret("jwtSigningKey")
# Worker image will be configured by GitHub Actions or default to ACR image
worker_image = config.get("workerImage") or "lightningacr.azurecr.io/worker-task:latest"

# Resource group
resource_group = resources.ResourceGroup(
    "lightning",
    resource_group_name="lightning",
    location=location,
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
send_rule = servicebus.QueueAuthorizationRule(
    "send-rule",
    resource_group_name=resource_group.name,
    namespace_name=namespace.name,
    queue_name=queue.name,
    authorization_rule_name="send",
    rights=["Send"],
)

send_keys = servicebus.list_queue_keys_output(
    authorization_rule_name=send_rule.name,
    queue_name=queue.name,
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
        linux_fx_version="Python|3.9",  # Specify Linux Python runtime
        app_settings=[
            web.NameValuePairArgs(name="AzureWebJobsStorage", value=storage_connection_string),
            web.NameValuePairArgs(name="FUNCTIONS_EXTENSION_VERSION", value="~4"),
            web.NameValuePairArgs(name="FUNCTIONS_WORKER_RUNTIME", value="python"),
            web.NameValuePairArgs(name="COSMOS_CONNECTION", value=cosmos_connection_string),
            web.NameValuePairArgs(name="COSMOS_DATABASE", value="lightning"),
            web.NameValuePairArgs(name="SCHEDULE_CONTAINER", value="schedules"),
            web.NameValuePairArgs(name="SERVICEBUS_CONNECTION", value=send_keys.primary_connection_string),
            web.NameValuePairArgs(name="SERVICEBUS_QUEUE", value=queue.name),
            web.NameValuePairArgs(name="REPO_CONTAINER", value="repos"),
            web.NameValuePairArgs(name="USER_CONTAINER", value="users"),
            web.NameValuePairArgs(name="ACI_RESOURCE_GROUP", value=resource_group.name),
            web.NameValuePairArgs(name="ACI_SUBSCRIPTION_ID", value=subscription_id),
            web.NameValuePairArgs(name="ACI_REGION", value=location),
            web.NameValuePairArgs(name="OPENAI_API_KEY", value=openai_api_key),
            web.NameValuePairArgs(name="WORKER_IMAGE", value=worker_image),
            web.NameValuePairArgs(name="JWT_SIGNING_KEY", value=jwt_signing_key)
        ]
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

ui_image = config.get("uiImage") or pulumi.Output.concat("lightningacr.azurecr.io/chainlit-client:latest")

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
            ports=[
                containerinstance.ContainerPortArgs(port=8000),
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
)

pulumi.export("uiUrl", ui_container.ip_address.apply(lambda ip: f"http://{ip.fqdn}"))

# Wire the functions back to the Chainlit UI once the container address is known
notify_url = ui_container.ip_address.apply(lambda ip: f"http://{ip.fqdn}/notify")

# Function to create and upload Function App package
def create_function_package():
    """Create a ZIP package of the Azure Functions code"""
    import zipfile
    import tempfile
    import os
    import atexit

    # Create a temporary ZIP file that persists until cleanup
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    zip_path = tmp.name
    tmp.close()

    # Ensure the temporary file gets removed after deployment
    atexit.register(lambda: os.path.exists(zip_path) and os.remove(zip_path))
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Walk through the azure-function directory
        for root, dirs, files in os.walk('../azure-function'):
            for file in files:
                file_path = os.path.join(root, file)
                # Skip __pycache__ directories and .pyc files
                if '__pycache__' not in file_path and not file_path.endswith('.pyc'):
                    # Get the relative path from azure-function directory
                    arcname = os.path.relpath(file_path, '../azure-function')
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

# Generate a SAS token for the ZIP blob so the Function App can access it
sas_start = datetime.datetime.utcnow().isoformat() + "Z"
sas_expiry = (datetime.datetime.utcnow() + datetime.timedelta(days=1)).isoformat() + "Z"

package_sas = storage.list_storage_account_service_sas_output(
    account_name=storage_account.name,
    resource_group_name=resource_group.name,
    protocols="https",
    shared_access_start_time=sas_start,
    shared_access_expiry_time=sas_expiry,
    permissions="r",
    canonicalized_resource=pulumi.Output.concat(
        "/blob/",
        storage_account.name,
        "/",
        deployment_container.name,
        "/function-package.zip",
    ),
    resource="b",
)

function_package_url = pulumi.Output.concat(
    "https://",
    storage_account.name,
    ".blob.core.windows.net/",
    deployment_container.name,
    "/function-package.zip?",
    package_sas.service_sas_token,
)

# Deploy the function package using WebAppApplicationSettings
web.WebAppApplicationSettings(
    "function-settings",
    name=func_app.name,
    resource_group_name=resource_group.name,
    properties={
        "NOTIFY_URL": notify_url,
        "WEBSITE_RUN_FROM_PACKAGE": function_package_url,
    },
)
