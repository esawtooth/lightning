"""
Example Pulumi code showing how to deploy the unified Docker images to Azure.
This demonstrates using the same Dockerfiles for both local and cloud deployment.
"""

import pulumi
import pulumi_docker as docker
from pulumi_azure_native import containerinstance, containerregistry

# This is an example showing how to integrate the unified Docker approach
# into the existing Pulumi infrastructure


def create_unified_container_images(acr: containerregistry.Registry, acr_creds):
    """
    Build and push unified Docker images to Azure Container Registry.
    These images can run in both local and Azure modes based on environment variables.
    """
    
    # Lightning API image (Azure mode)
    lightning_api_image = docker.Image(
        "lightning-api-azure",
        build=docker.DockerBuildArgs(
            context="../core",
            dockerfile="../core/Dockerfile",
            args={
                "LIGHTNING_MODE": "azure",
                "SERVICE_TYPE": "api"
            },
        ),
        image_name=pulumi.Output.concat(acr.login_server, "/lightning-api:latest"),
        registry=docker.RegistryArgs(
            server=acr.login_server,
            username=acr_creds.username,
            password=acr_creds.passwords[0].value,
        ),
    )
    
    # Lightning Event Processor image (Azure mode)
    lightning_processor_image = docker.Image(
        "lightning-processor-azure",
        build=docker.DockerBuildArgs(
            context="../core",
            dockerfile="../core/Dockerfile.processor",
            args={
                "LIGHTNING_MODE": "azure"
            },
        ),
        image_name=pulumi.Output.concat(acr.login_server, "/lightning-processor:latest"),
        registry=docker.RegistryArgs(
            server=acr.login_server,
            username=acr_creds.username,
            password=acr_creds.passwords[0].value,
        ),
    )
    
    # Lightning UI image (Azure mode)
    lightning_ui_image = docker.Image(
        "lightning-ui-azure",
        build=docker.DockerBuildArgs(
            context="..",
            dockerfile="../ui/integrated_app/Dockerfile",
            args={
                "LIGHTNING_MODE": "azure"
            },
        ),
        image_name=pulumi.Output.concat(acr.login_server, "/lightning-ui:latest"),
        registry=docker.RegistryArgs(
            server=acr.login_server,
            username=acr_creds.username,
            password=acr_creds.passwords[0].value,
        ),
    )
    
    return {
        "api": lightning_api_image,
        "processor": lightning_processor_image,
        "ui": lightning_ui_image
    }


def deploy_api_container(images, rg, vault_secret_uri, service_bus_cs, cosmos_cs):
    """
    Deploy Lightning API as Azure Container Instance using unified image.
    """
    
    api_cg = containerinstance.ContainerGroup(
        "lightning-api",
        resource_group_name=rg.name,
        location=rg.location,
        os_type=containerinstance.OperatingSystemTypes.LINUX,
        containers=[
            containerinstance.ContainerArgs(
                name="lightning-api",
                image=images["api"].image_name,
                resources=containerinstance.ResourceRequirementsArgs(
                    requests=containerinstance.ResourceRequestsArgs(
                        cpu=1.0,
                        memory_in_gb=1.5,
                    )
                ),
                ports=[containerinstance.ContainerPortArgs(port=8000, protocol="TCP")],
                environment_variables=[
                    # Lightning Core Configuration
                    containerinstance.EnvironmentVariableArgs(
                        name="LIGHTNING_MODE", 
                        value="azure"
                    ),
                    containerinstance.EnvironmentVariableArgs(
                        name="SERVICE_TYPE", 
                        value="api"
                    ),
                    containerinstance.EnvironmentVariableArgs(
                        name="LIGHTNING_STORAGE_PROVIDER", 
                        value="cosmos"
                    ),
                    containerinstance.EnvironmentVariableArgs(
                        name="LIGHTNING_EVENT_BUS_PROVIDER", 
                        value="servicebus"
                    ),
                    
                    # Azure Service Connections
                    containerinstance.EnvironmentVariableArgs(
                        name="COSMOS_CONNECTION_STRING", 
                        value=cosmos_cs
                    ),
                    containerinstance.EnvironmentVariableArgs(
                        name="SERVICE_BUS_CONNECTION_STRING", 
                        value=service_bus_cs
                    ),
                    
                    # Runtime Configuration
                    containerinstance.EnvironmentVariableArgs(
                        name="PORT", 
                        value="8000"
                    ),
                    containerinstance.EnvironmentVariableArgs(
                        name="HOST", 
                        value="0.0.0.0"
                    ),
                    containerinstance.EnvironmentVariableArgs(
                        name="LOG_LEVEL", 
                        value="INFO"
                    ),
                ],
                # Secrets from Key Vault
                environment_variables_secure=[
                    containerinstance.EnvironmentVariableArgs(
                        name="OPENAI_API_KEY",
                        secure_value=vault_secret_uri  # Reference to Key Vault secret
                    ),
                ],
            )
        ],
        ip_address=containerinstance.IpAddressArgs(
            type=containerinstance.ContainerGroupIpAddressType.PRIVATE,
            ports=[containerinstance.PortArgs(protocol="TCP", port=8000)],
        ),
        # Add to VNet subnet (defined in main infrastructure)
        subnet_ids=[containerinstance.ContainerGroupSubnetIdArgs(id="subnet-id-here")],
    )
    
    return api_cg


def deploy_event_processor_container(images, rg, vault_secret_uri, service_bus_cs, cosmos_cs):
    """
    Deploy Lightning Event Processor as Azure Container Instance.
    This can run alongside or instead of Azure Functions.
    """
    
    processor_cg = containerinstance.ContainerGroup(
        "lightning-processor",
        resource_group_name=rg.name,
        location=rg.location,
        os_type=containerinstance.OperatingSystemTypes.LINUX,
        containers=[
            containerinstance.ContainerArgs(
                name="lightning-processor",
                image=images["processor"].image_name,
                resources=containerinstance.ResourceRequirementsArgs(
                    requests=containerinstance.ResourceRequestsArgs(
                        cpu=0.5,
                        memory_in_gb=1.0,
                    )
                ),
                environment_variables=[
                    # Lightning Core Configuration
                    containerinstance.EnvironmentVariableArgs(
                        name="LIGHTNING_MODE", 
                        value="azure"
                    ),
                    containerinstance.EnvironmentVariableArgs(
                        name="SERVICE_TYPE", 
                        value="event_processor"
                    ),
                    containerinstance.EnvironmentVariableArgs(
                        name="AZURE_DEPLOYMENT_TYPE", 
                        value="container"
                    ),
                    containerinstance.EnvironmentVariableArgs(
                        name="LIGHTNING_STORAGE_PROVIDER", 
                        value="cosmos"
                    ),
                    containerinstance.EnvironmentVariableArgs(
                        name="LIGHTNING_EVENT_BUS_PROVIDER", 
                        value="servicebus"
                    ),
                    
                    # Azure Service Connections
                    containerinstance.EnvironmentVariableArgs(
                        name="COSMOS_CONNECTION_STRING", 
                        value=cosmos_cs
                    ),
                    containerinstance.EnvironmentVariableArgs(
                        name="SERVICE_BUS_CONNECTION_STRING", 
                        value=service_bus_cs
                    ),
                    
                    # Runtime Configuration
                    containerinstance.EnvironmentVariableArgs(
                        name="LOG_LEVEL", 
                        value="INFO"
                    ),
                ],
                environment_variables_secure=[
                    containerinstance.EnvironmentVariableArgs(
                        name="OPENAI_API_KEY",
                        secure_value=vault_secret_uri
                    ),
                ],
            )
        ],
        # No public IP needed for processor
        subnet_ids=[containerinstance.ContainerGroupSubnetIdArgs(id="subnet-id-here")],
    )
    
    return processor_cg


def deploy_ui_container(images, rg, api_url, context_hub_url):
    """
    Deploy Lightning UI as Azure Container Instance.
    This replaces the current UI deployment with the unified container.
    """
    
    ui_cg = containerinstance.ContainerGroup(
        "lightning-ui",
        resource_group_name=rg.name,
        location=rg.location,
        os_type=containerinstance.OperatingSystemTypes.LINUX,
        containers=[
            containerinstance.ContainerArgs(
                name="lightning-ui",
                image=images["ui"].image_name,
                resources=containerinstance.ResourceRequirementsArgs(
                    requests=containerinstance.ResourceRequestsArgs(
                        cpu=0.5,
                        memory_in_gb=1.0,
                    )
                ),
                ports=[containerinstance.ContainerPortArgs(port=8080, protocol="TCP")],
                environment_variables=[
                    # Lightning Core Configuration
                    containerinstance.EnvironmentVariableArgs(
                        name="LIGHTNING_MODE", 
                        value="azure"
                    ),
                    containerinstance.EnvironmentVariableArgs(
                        name="SERVICE_TYPE", 
                        value="ui"
                    ),
                    
                    # Backend API URLs
                    containerinstance.EnvironmentVariableArgs(
                        name="API_BASE", 
                        value=api_url
                    ),
                    containerinstance.EnvironmentVariableArgs(
                        name="EVENT_API_URL", 
                        value=f"{api_url}/api/events"
                    ),
                    containerinstance.EnvironmentVariableArgs(
                        name="CONTEXT_HUB_URL", 
                        value=context_hub_url
                    ),
                    
                    # Runtime Configuration
                    containerinstance.EnvironmentVariableArgs(
                        name="APP_HOST", 
                        value="0.0.0.0"
                    ),
                    containerinstance.EnvironmentVariableArgs(
                        name="APP_PORT", 
                        value="8080"
                    ),
                    containerinstance.EnvironmentVariableArgs(
                        name="LOG_LEVEL", 
                        value="INFO"
                    ),
                ],
            )
        ],
        ip_address=containerinstance.IpAddressArgs(
            type=containerinstance.ContainerGroupIpAddressType.PUBLIC,
            ports=[containerinstance.PortArgs(protocol="TCP", port=8080)],
            dns_name_label="lightning-ui-unique-suffix",  # Make this unique
        ),
    )
    
    return ui_cg


# Example usage in main Pulumi script:
"""
# In your main __main__.py, after creating ACR and other resources:

# Build and push unified images
images = create_unified_container_images(acr, acr_creds)

# Deploy API container
api_cg = deploy_api_container(
    images, 
    rg, 
    vault_openai_secret.id,  # Key Vault secret reference
    service_bus_connection_string,
    cosmos_connection_string
)

# Deploy Event Processor container (optional, can use alongside Functions)
processor_cg = deploy_event_processor_container(
    images,
    rg,
    vault_openai_secret.id,
    service_bus_connection_string,
    cosmos_connection_string
)

# Deploy UI container
ui_cg = deploy_ui_container(
    images,
    rg,
    pulumi.Output.concat("https://", api_cg.ip_address.apply(lambda ip: ip.fqdn)),
    pulumi.Output.concat("https://", hub_cg.ip_address.apply(lambda ip: ip.fqdn))
)

# Export URLs
pulumi.export("apiUrl", api_cg.ip_address.apply(lambda ip: f"https://{ip.fqdn}"))
pulumi.export("uiUrl", ui_cg.ip_address.apply(lambda ip: f"https://{ip.fqdn}"))
"""