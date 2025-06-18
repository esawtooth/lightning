"""
Example: Deploying Universal Event Processor - Local vs Azure Functions

This example demonstrates how to deploy and run the Lightning Core
universal event processor in both local and Azure Functions environments
using the same codebase.
"""

import asyncio
import os
import json
from datetime import datetime
from typing import Dict, Any

from lightning_core.runtime import get_runtime, initialize_runtime
from lightning_core.abstractions import (
    RuntimeConfig, ExecutionMode,
    EventMessage, EventPriority,
    FunctionConfig, RuntimeType
)
from lightning_core.vextir_os.serverless_processor import (
    universal_event_processor_handler,
    create_test_handler,
    FUNCTION_CONFIG
)


async def deploy_local_processor():
    """Deploy the universal event processor for local development."""
    print("\n=== Deploying Universal Event Processor Locally ===")
    
    # Configure for local execution
    config = RuntimeConfig(
        mode=ExecutionMode.LOCAL,
        storage_provider="local",
        storage_path="./data/processor",
        event_bus_provider="local",
        serverless_provider="local"
    )
    
    # Initialize runtime
    runtime = await initialize_runtime(config)
    
    # Create function configuration
    function_config = FunctionConfig(
        name="universal-event-processor",
        handler="universal_event_processor_handler",
        runtime=RuntimeType.PYTHON,
        memory_mb=512,
        timeout_seconds=300,
        environment_variables={
            "LOGGING_LEVEL": "INFO",
            "LIGHTNING_MODE": "local",
            "CONTEXT_HUB_ENDPOINT": "http://localhost:8000"
        }
    )
    
    # Add event trigger for all event types
    function_config.add_event_trigger(["*"], topic="vextir-events")
    
    # Deploy the function locally
    function_id = await runtime.serverless.deploy_function(
        function_config,
        universal_event_processor_handler
    )
    
    print(f"✓ Deployed function locally with ID: {function_id}")
    
    # Set up event bus subscription to route events to the processor
    async def route_to_processor(event: EventMessage):
        """Route events to the serverless processor."""
        await runtime.serverless.invoke_function(
            function_id,
            {
                "event": event.to_json(),
                "event_type": event.event_type,
                "data": event.data
            },
            async_invoke=True
        )
    
    # Subscribe to all events
    subscription_id = await runtime.event_bus.subscribe(
        "*",  # Subscribe to all event types
        route_to_processor,
        topic="vextir-events"
    )
    
    print(f"✓ Set up event routing (subscription: {subscription_id})")
    
    return runtime, function_id


async def deploy_azure_processor():
    """Deploy the universal event processor to Azure Functions."""
    print("\n=== Deploying Universal Event Processor to Azure ===")
    
    # Configure for Azure execution
    config = RuntimeConfig(
        mode=ExecutionMode.AZURE,
        storage_provider="azure_cosmos",
        event_bus_provider="azure_service_bus",
        serverless_provider="azure_functions",
        resource_group=os.getenv("AZURE_RESOURCE_GROUP", "my-resource-group"),
        region="eastus"
    )
    
    # Initialize runtime
    runtime = await initialize_runtime(config)
    
    # Create function configuration
    function_config = FunctionConfig.from_dict(FUNCTION_CONFIG)
    
    # Deploy the function (registers it with the runtime)
    function_id = await runtime.serverless.deploy_function(function_config)
    
    print(f"✓ Registered function with ID: {function_id}")
    print("\nDeployment Instructions:")
    print(runtime.serverless.get_deployment_instructions(function_config))
    
    return runtime, function_id


async def test_local_processor(runtime, function_id):
    """Test the locally deployed processor."""
    print("\n=== Testing Local Event Processor ===")
    
    # Create test events
    test_events = [
        EventMessage(
            event_type="user.action",
            data={
                "action": "login",
                "userId": "test-user-123",
                "timestamp": datetime.utcnow().isoformat()
            },
            metadata={"source": "test", "environment": "local"}
        ),
        EventMessage(
            event_type="system.health_check",
            data={"component": "event_processor", "check_type": "ping"},
            priority=EventPriority.HIGH
        ),
        EventMessage(
            event_type="task.created",
            data={
                "taskId": "task-456",
                "title": "Process data",
                "assignedTo": "test-user-123"
            }
        )
    ]
    
    # Send events
    for event in test_events:
        print(f"\nSending event: {event.event_type}")
        await runtime.publish_event(event, topic="vextir-events")
    
    # Wait for processing
    await asyncio.sleep(2)
    
    # Check function logs
    logs = await runtime.serverless.get_function_logs(
        function_id,
        max_items=10
    )
    
    print("\n=== Function Logs ===")
    for log in logs:
        print(f"[{log['timestamp']}] {log['type']}: {log.get('payload', '')}")
    
    # Get function stats
    info = await runtime.serverless.get_function(function_id)
    print(f"\n✓ Function invoked {info['invocation_count']} times")


async def test_azure_processor(runtime, function_id):
    """Test the Azure-deployed processor."""
    print("\n=== Testing Azure Event Processor ===")
    
    # Create test event
    test_event = {
        "type": "user.action",
        "userID": "azure-test-user",
        "data": {
            "action": "test_azure_deployment",
            "timestamp": datetime.utcnow().isoformat()
        },
        "metadata": {
            "source": "deployment_test",
            "environment": "azure"
        }
    }
    
    # Invoke via HTTP trigger (if available)
    print("\nInvoking function via HTTP trigger...")
    response = await runtime.serverless.invoke_function(
        function_id,
        test_event
    )
    
    print(f"Response Status: {response.status_code}")
    print(f"Response Body: {json.dumps(response.body, indent=2)}")
    
    # For Service Bus trigger, we would publish to the queue
    print("\nFor Service Bus trigger, publish event to queue:")
    print(f"Queue: {os.getenv('SERVICE_BUS_QUEUE_NAME', 'vextir-events')}")
    print(f"Event: {json.dumps(test_event, indent=2)}")


async def compare_deployments():
    """Compare local and Azure deployments side by side."""
    print("\n=== Deployment Comparison ===")
    
    comparison = {
        "Local Development": {
            "Storage": "SQLite (./data/)",
            "Event Bus": "In-memory asyncio queues",
            "Container Runtime": "Docker",
            "Serverless": "Python subprocess",
            "Setup Time": "< 1 second",
            "Cost": "$0",
            "Use Case": "Development, testing, debugging"
        },
        "Azure Production": {
            "Storage": "Cosmos DB",
            "Event Bus": "Service Bus",
            "Container Runtime": "Azure Container Instances",
            "Serverless": "Azure Functions",
            "Setup Time": "5-10 minutes",
            "Cost": "Pay per use",
            "Use Case": "Production, scalable workloads"
        }
    }
    
    for env, details in comparison.items():
        print(f"\n{env}:")
        for key, value in details.items():
            print(f"  {key}: {value}")


async def main():
    """Main example function."""
    # Show deployment comparison
    await compare_deployments()
    
    # Example 1: Local Deployment
    print("\n" + "="*60)
    print("EXAMPLE 1: LOCAL DEPLOYMENT")
    print("="*60)
    
    try:
        # Deploy locally
        local_runtime, local_function_id = await deploy_local_processor()
        
        # Test local deployment
        await test_local_processor(local_runtime, local_function_id)
        
        # Cleanup
        await local_runtime.shutdown()
        
    except Exception as e:
        print(f"Local deployment error: {e}")
    
    # Example 2: Azure Deployment (requires Azure credentials)
    if os.getenv("AZURE_SUBSCRIPTION_ID"):
        print("\n" + "="*60)
        print("EXAMPLE 2: AZURE DEPLOYMENT")
        print("="*60)
        
        try:
            # Deploy to Azure
            azure_runtime, azure_function_id = await deploy_azure_processor()
            
            # Test Azure deployment
            await test_azure_processor(azure_runtime, azure_function_id)
            
            # Cleanup
            await azure_runtime.shutdown()
            
        except Exception as e:
            print(f"Azure deployment error: {e}")
    else:
        print("\n" + "="*60)
        print("AZURE DEPLOYMENT EXAMPLE")
        print("="*60)
        print("To test Azure deployment, set these environment variables:")
        print("  - AZURE_SUBSCRIPTION_ID")
        print("  - AZURE_RESOURCE_GROUP")
        print("  - AZURE_FUNCTION_APP")
        print("  - COSMOS_CONNECTION_STRING")
        print("  - SERVICE_BUS_CONNECTION_STRING")
    
    # Example 3: Migration Path
    print("\n" + "="*60)
    print("MIGRATION PATH")
    print("="*60)
    
    print("""
To migrate from local to Azure deployment:

1. Develop and test locally:
   python event_processor_deployment.py

2. Set up Azure resources:
   - Create Function App
   - Create Service Bus namespace and queue
   - Create Cosmos DB account
   - Set up Application Insights

3. Update configuration:
   export LIGHTNING_MODE=azure
   export AZURE_SUBSCRIPTION_ID=your-subscription
   export AZURE_RESOURCE_GROUP=your-rg
   export AZURE_FUNCTION_APP=your-function-app

4. Deploy function code:
   func azure functionapp publish your-function-app

5. The same event processing logic runs in both environments!
""")


if __name__ == "__main__":
    asyncio.run(main())