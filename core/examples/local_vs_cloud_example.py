"""
Example demonstrating how to use Lightning Core in both local and cloud modes.

This example shows:
1. How to configure for local vs cloud execution
2. How to use the same code for both environments
3. How to switch between providers dynamically
"""

import asyncio
import os
from datetime import datetime
from typing import Dict, Any

from lightning_core.abstractions import (
    RuntimeConfig, ExecutionMode, ProviderFactory,
    Document, EventMessage, EventPriority,
    ContainerConfig, ResourceRequirements,
    FunctionConfig, FunctionContext, FunctionResponse, RuntimeType
)


# Example document class
class TaskDocument(Document):
    """Example task document."""
    
    def __init__(self, task_name: str = "", status: str = "pending", **kwargs):
        super().__init__(**kwargs)
        self.data["task_name"] = task_name
        self.data["status"] = status
    
    @property
    def task_name(self) -> str:
        return self.data.get("task_name", "")
    
    @property
    def status(self) -> str:
        return self.data.get("status", "pending")


async def example_storage_operations(config: RuntimeConfig):
    """Demonstrate storage operations."""
    print(f"\n=== Storage Example ({config.mode.value} mode) ===")
    
    # Create storage provider
    storage = ProviderFactory.create_storage_provider(config)
    await storage.initialize()
    
    # Create container
    await storage.create_container_if_not_exists("tasks")
    
    # Get document store
    task_store = storage.get_document_store("tasks", TaskDocument)
    
    # Create a task
    task = TaskDocument(
        task_name="Process data",
        status="pending",
        partition_key="user123"
    )
    created_task = await task_store.create(task)
    print(f"Created task: {created_task.id}")
    
    # Read the task
    read_task = await task_store.read(created_task.id, "user123")
    print(f"Read task: {read_task.task_name} - {read_task.status}")
    
    # Update the task
    read_task.data["status"] = "completed"
    updated_task = await task_store.update(read_task)
    print(f"Updated task status: {updated_task.status}")
    
    # Query tasks
    pending_tasks = await task_store.query(
        {"status": "pending"},
        partition_key="user123"
    )
    print(f"Pending tasks: {len(pending_tasks)}")
    
    # Clean up
    await task_store.delete(created_task.id, "user123")
    await storage.close()


async def example_event_bus_operations(config: RuntimeConfig):
    """Demonstrate event bus operations."""
    print(f"\n=== Event Bus Example ({config.mode.value} mode) ===")
    
    # Create event bus
    event_bus = ProviderFactory.create_event_bus(config)
    
    # Create topic
    await event_bus.create_topic("task-events")
    
    # Define event handler
    events_received = []
    
    async def handle_task_event(event: EventMessage):
        print(f"Received event: {event.event_type} - {event.data}")
        events_received.append(event)
    
    # Subscribe to events
    subscription_id = await event_bus.subscribe(
        "task.completed",
        handle_task_event,
        topic="task-events"
    )
    
    # Start event bus
    await event_bus.start()
    
    # Publish events
    event = EventMessage(
        event_type="task.completed",
        data={"task_id": "123", "result": "success"},
        priority=EventPriority.HIGH
    )
    await event_bus.publish(event, topic="task-events")
    
    # Wait for processing
    await asyncio.sleep(1)
    
    print(f"Events received: {len(events_received)}")
    
    # Clean up
    await event_bus.unsubscribe(subscription_id)
    await event_bus.stop()


async def example_container_operations(config: RuntimeConfig):
    """Demonstrate container operations."""
    print(f"\n=== Container Runtime Example ({config.mode.value} mode) ===")
    
    # Create container runtime
    runtime = ProviderFactory.create_container_runtime(config)
    
    # Define container configuration
    container_config = ContainerConfig(
        name="example-worker",
        image="python:3.9-slim",
        command=["python", "-c"],
        args=['print("Hello from container!"); import time; time.sleep(5)'],
        environment_variables={
            "TASK_ID": "123",
            "ENV": config.mode.value
        },
        resources=ResourceRequirements(cpu=0.5, memory_gb=0.5),
        labels={"app": "lightning", "component": "example"}
    )
    
    try:
        # Create and start container
        container = await runtime.create_container(container_config)
        print(f"Created container: {container.id}")
        print(f"Container state: {container.state.value}")
        
        # Get logs
        logs = await runtime.get_container_logs(container.id)
        print(f"Container logs: {logs[:100]}...")
        
        # Wait for completion
        exit_code = await runtime.wait_for_container(container.id, timeout_seconds=10)
        print(f"Container exited with code: {exit_code}")
        
    finally:
        # Clean up
        if 'container' in locals():
            await runtime.remove_container(container.id)


async def example_serverless_operations(config: RuntimeConfig):
    """Demonstrate serverless operations."""
    print(f"\n=== Serverless Runtime Example ({config.mode.value} mode) ===")
    
    # Create serverless runtime
    runtime = ProviderFactory.create_serverless_runtime(config)
    
    # Define function handler
    async def process_task(context: FunctionContext) -> FunctionResponse:
        """Example serverless function."""
        task_id = context.trigger_data.get("task_id")
        print(f"Processing task {task_id} in function {context.function_name}")
        
        # Simulate processing
        result = {
            "task_id": task_id,
            "processed_at": datetime.utcnow().isoformat(),
            "status": "completed"
        }
        
        return FunctionResponse(
            status_code=200,
            body=result,
            headers={"X-Function-ID": context.invocation_id}
        )
    
    # Define function configuration
    function_config = FunctionConfig(
        name="task-processor",
        handler="process_task",
        runtime=RuntimeType.PYTHON,
        memory_mb=256,
        timeout_seconds=60,
        environment_variables={
            "LOG_LEVEL": "INFO",
            "ENV": config.mode.value
        }
    )
    
    # Add triggers
    function_config.add_event_trigger(["task.created", "task.updated"])
    function_config.add_http_trigger(["POST"], "/process")
    
    # Deploy function
    function_id = await runtime.deploy_function(function_config, process_task)
    print(f"Deployed function: {function_id}")
    
    # Invoke function
    response = await runtime.invoke_function(
        function_id,
        {"task_id": "456", "action": "process"}
    )
    print(f"Function response: {response.status_code} - {response.body}")
    
    # Get function info
    info = await runtime.get_function(function_id)
    print(f"Function info: {info['name']} - {info['invocation_count']} invocations")
    
    # Clean up
    await runtime.delete_function(function_id)


async def main():
    """Main example function."""
    # Example 1: Local execution
    print("\n" + "="*50)
    print("RUNNING IN LOCAL MODE")
    print("="*50)
    
    local_config = RuntimeConfig(
        mode=ExecutionMode.LOCAL,
        storage_provider="local",
        storage_path="./example_data",
        event_bus_provider="local",
        container_runtime="docker",
        serverless_provider="local"
    )
    
    await example_storage_operations(local_config)
    await example_event_bus_operations(local_config)
    
    # Check if Docker is available for container example
    try:
        import docker
        client = docker.from_env()
        client.ping()
        await example_container_operations(local_config)
    except Exception as e:
        print(f"\nSkipping container example: Docker not available ({e})")
    
    await example_serverless_operations(local_config)
    
    # Example 2: Cloud execution (Azure)
    # Uncomment and configure to test with real Azure resources
    """
    print("\n" + "="*50)
    print("RUNNING IN AZURE MODE")
    print("="*50)
    
    # Set up Azure credentials
    os.environ["COSMOS_CONNECTION_STRING"] = "your-cosmos-connection-string"
    os.environ["SERVICE_BUS_CONNECTION_STRING"] = "your-service-bus-connection-string"
    
    azure_config = RuntimeConfig(
        mode=ExecutionMode.AZURE,
        storage_provider="azure_cosmos",
        event_bus_provider="azure_service_bus",
        container_runtime="azure_aci",
        serverless_provider="azure_functions",
        resource_group="your-resource-group",
        region="eastus"
    )
    
    await example_storage_operations(azure_config)
    await example_event_bus_operations(azure_config)
    await example_container_operations(azure_config)
    await example_serverless_operations(azure_config)
    """
    
    # Example 3: Configuration from environment
    print("\n" + "="*50)
    print("LOADING CONFIGURATION FROM ENVIRONMENT")
    print("="*50)
    
    # Set environment variables
    os.environ["LIGHTNING_MODE"] = "local"
    os.environ["LIGHTNING_STORAGE_PROVIDER"] = "local"
    os.environ["LIGHTNING_STORAGE_PATH"] = "./env_data"
    
    env_config = RuntimeConfig.from_env()
    print(f"Loaded config: {env_config.mode.value} mode")
    print(f"Storage: {env_config.storage_provider}")
    print(f"Event Bus: {env_config.event_bus_provider}")
    
    # Save and load configuration
    env_config.save("config.json")
    loaded_config = RuntimeConfig.load("config.json")
    print(f"Loaded config from file: {loaded_config.mode.value} mode")


if __name__ == "__main__":
    asyncio.run(main())