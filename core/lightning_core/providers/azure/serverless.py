"""
Azure Functions serverless runtime implementation.

Note: This implementation provides management capabilities for Azure Functions.
The actual function code still needs to be deployed through Azure deployment tools.
"""

import base64
import json
import logging
import os
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional

import aiohttp
from azure.identity.aio import DefaultAzureCredential
from azure.mgmt.web.aio import WebSiteManagementClient
from azure.mgmt.web.models import NameValuePair, Site, SiteConfig

from lightning_core.abstractions.serverless import (
    FunctionConfig,
    FunctionContext,
    FunctionHandler,
    FunctionResponse,
    RuntimeType,
    ServerlessRuntime,
    TriggerType,
)

logger = logging.getLogger(__name__)


class AzureFunctionsRuntime(ServerlessRuntime):
    """Azure Functions serverless runtime implementation."""

    def __init__(
        self,
        subscription_id: Optional[str] = None,
        resource_group: Optional[str] = None,
        function_app_name: Optional[str] = None,
        credential: Optional[Any] = None,
        **kwargs: Any,
    ):
        self.subscription_id = subscription_id or os.getenv("AZURE_SUBSCRIPTION_ID")
        self.resource_group = resource_group or os.getenv("AZURE_RESOURCE_GROUP")
        self.function_app_name = function_app_name or os.getenv("AZURE_FUNCTION_APP")

        if not all([self.subscription_id, self.resource_group, self.function_app_name]):
            raise ValueError(
                "Azure subscription ID, resource group, and function app name required"
            )

        # Use DefaultAzureCredential if no credential provided
        self.credential = credential or DefaultAzureCredential()

        # Function app base URL
        self.function_app_url = f"https://{self.function_app_name}.azurewebsites.net"

        # Track deployed functions (in production, this would be from Azure)
        self._functions: Dict[str, Dict[str, Any]] = {}

    async def deploy_function(
        self, config: FunctionConfig, handler: Optional[FunctionHandler] = None
    ) -> str:
        """
        Deploy a serverless function to Azure Functions.

        Note: In Azure Functions, deployment typically happens through:
        1. Azure DevOps pipelines
        2. GitHub Actions
        3. Azure CLI (func deploy)
        4. ARM templates or Bicep

        This implementation tracks the function configuration and can invoke
        already-deployed functions, but doesn't handle actual code deployment.
        """
        function_id = f"azure-{config.name}"

        # Store function configuration
        self._functions[function_id] = {
            "config": config,
            "handler": handler,
            "deployed_at": datetime.utcnow().isoformat(),
            "url": f"{self.function_app_url}/api/{config.name}",
        }

        logger.info(f"Registered Azure Function {config.name} with ID {function_id}")
        logger.info(
            f"Note: Ensure function {config.name} is deployed to Azure Function App {self.function_app_name}"
        )

        return function_id

    async def invoke_function(
        self, function_id: str, payload: Dict[str, Any], async_invoke: bool = False
    ) -> FunctionResponse:
        """Invoke an Azure Function via HTTP trigger."""
        if function_id not in self._functions:
            return FunctionResponse(
                status_code=404,
                is_error=True,
                error_message=f"Function {function_id} not found",
            )

        function_info = self._functions[function_id]
        function_url = function_info["url"]

        # Get function key if available
        function_key = os.getenv(
            f"AZURE_FUNCTION_KEY_{function_info['config'].name.upper()}"
        )

        headers = {"Content-Type": "application/json"}
        if function_key:
            headers["x-functions-key"] = function_key

        try:
            async with aiohttp.ClientSession() as session:
                # Add async flag to payload if needed
                if async_invoke:
                    payload["_async"] = True

                async with session.post(
                    function_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=300),
                ) as response:

                    response_text = await response.text()

                    # Try to parse JSON response
                    try:
                        response_body = json.loads(response_text)
                    except json.JSONDecodeError:
                        response_body = response_text

                    return FunctionResponse(
                        status_code=response.status,
                        body=response_body,
                        headers=dict(response.headers),
                        is_error=response.status >= 400,
                    )

        except aiohttp.ClientError as e:
            logger.error(f"Failed to invoke Azure Function {function_id}: {e}")
            return FunctionResponse(
                status_code=500,
                is_error=True,
                error_message=f"Failed to invoke function: {str(e)}",
            )

    async def update_function(
        self,
        function_id: str,
        config: Optional[FunctionConfig] = None,
        handler: Optional[FunctionHandler] = None,
    ) -> None:
        """Update function configuration."""
        if function_id not in self._functions:
            raise ValueError(f"Function {function_id} not found")

        if config:
            self._functions[function_id]["config"] = config
        if handler:
            self._functions[function_id]["handler"] = handler

        logger.info(f"Updated function configuration for {function_id}")
        logger.info(
            "Note: Code updates require redeployment through Azure deployment tools"
        )

    async def delete_function(self, function_id: str) -> None:
        """Remove function from tracking (doesn't delete from Azure)."""
        if function_id in self._functions:
            del self._functions[function_id]
            logger.info(f"Removed function {function_id} from tracking")
            logger.info(
                "Note: Function still exists in Azure. Delete through Azure Portal or CLI"
            )

    async def list_functions(
        self, name_prefix: Optional[str] = None, labels: Optional[Dict[str, str]] = None
    ) -> List[Dict[str, Any]]:
        """List tracked functions."""
        functions = []

        for function_id, function_info in self._functions.items():
            config = function_info["config"]

            # Filter by name prefix
            if name_prefix and not config.name.startswith(name_prefix):
                continue

            # Filter by labels
            if labels:
                if not all(config.labels.get(k) == v for k, v in labels.items()):
                    continue

            functions.append(
                {
                    "function_id": function_id,
                    "name": config.name,
                    "runtime": config.runtime.value,
                    "memory_mb": config.memory_mb,
                    "timeout_seconds": config.timeout_seconds,
                    "deployed_at": function_info.get("deployed_at"),
                    "url": function_info.get("url"),
                    "triggers": config.triggers,
                    "labels": config.labels,
                }
            )

        return functions

    async def get_function(self, function_id: str) -> Optional[Dict[str, Any]]:
        """Get function information."""
        if function_id not in self._functions:
            return None

        function_info = self._functions[function_id]
        config = function_info["config"]

        return {
            "function_id": function_id,
            "name": config.name,
            "runtime": config.runtime.value,
            "memory_mb": config.memory_mb,
            "timeout_seconds": config.timeout_seconds,
            "deployed_at": function_info.get("deployed_at"),
            "url": function_info.get("url"),
            "triggers": config.triggers,
            "labels": config.labels,
            "environment_variables": list(config.environment_variables.keys()),
        }

    async def get_function_logs(
        self,
        function_id: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        max_items: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get function execution logs from Application Insights.

        Note: This requires Application Insights to be configured
        and accessible via the Azure Monitor API.
        """
        if function_id not in self._functions:
            return []

        # In a full implementation, this would query Application Insights
        logger.info(
            f"Log retrieval for {function_id} requires Application Insights integration"
        )
        return []

    async def set_function_concurrency(
        self, function_id: str, reserved_concurrency: Optional[int] = None
    ) -> None:
        """
        Set function concurrency limits.

        Note: Azure Functions concurrency is managed through:
        1. Function app scaling settings
        2. host.json configuration
        3. App Service Plan limits
        """
        if function_id not in self._functions:
            raise ValueError(f"Function {function_id} not found")

        logger.info(
            f"Concurrency settings for Azure Functions are managed at the app level"
        )
        logger.info(f"Update host.json or App Service Plan to modify concurrency")

    async def create_function_url(
        self, function_id: str, cors_config: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Get the function URL.

        Note: Azure Functions automatically provide HTTP endpoints.
        CORS is configured at the Function App level.
        """
        if function_id not in self._functions:
            raise ValueError(f"Function {function_id} not found")

        if cors_config:
            logger.info(
                "CORS configuration for Azure Functions is managed in the Azure Portal or ARM templates"
            )

        return self._functions[function_id]["url"]

    async def register_event_source(
        self, function_id: str, event_source_config: Dict[str, Any]
    ) -> str:
        """
        Register an event source for the function.

        Note: In Azure Functions, event sources are configured through:
        1. function.json bindings
        2. Attribute-based configuration in code
        3. ARM templates or Bicep

        Common event sources:
        - Service Bus queues/topics
        - Event Hubs
        - Storage queues
        - Cosmos DB change feed
        """
        if function_id not in self._functions:
            raise ValueError(f"Function {function_id} not found")

        mapping_id = f"mapping-{function_id}-{datetime.utcnow().timestamp()}"

        logger.info(
            f"Event source registration for Azure Functions requires deployment configuration"
        )
        logger.info(
            f"Add binding configuration to function.json or use attributes in code"
        )

        return mapping_id

    async def unregister_event_source(self, event_source_id: str) -> None:
        """Remove event source (requires redeployment in Azure)."""
        logger.info(
            f"Event source removal requires updating function bindings and redeploying"
        )

    async def invoke_via_service_bus(
        self, function_name: str, event_data: Dict[str, Any]
    ) -> None:
        """
        Invoke a function via Service Bus (for event-triggered functions).

        This method would send a message to the Service Bus queue/topic
        that triggers the function.
        """
        # This would use the Service Bus client to send a message
        # For now, it's a placeholder showing the pattern
        logger.info(
            f"Service Bus invocation would send message to trigger {function_name}"
        )
        logger.info(f"Event data: {event_data}")

    def get_deployment_instructions(self, config: FunctionConfig) -> str:
        """Get deployment instructions for the function."""
        return f"""
To deploy this function to Azure:

1. Create a function in your Azure Function App:
   - Name: {config.name}
   - Runtime: {config.runtime.value}
   - Trigger: {config.triggers[0]['type'] if config.triggers else 'HTTP'}

2. Deploy using Azure Functions Core Tools:
   func azure functionapp publish {self.function_app_name} --{config.runtime.value}

3. Or use VS Code Azure Functions extension

4. Set environment variables in Azure Portal:
   {json.dumps(config.environment_variables, indent=2)}

5. Configure triggers in function.json or through bindings

Function will be available at:
{self.function_app_url}/api/{config.name}
"""
