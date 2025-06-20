# Lightning Core Migration Guide

This guide helps you migrate from direct Azure service usage to the new abstracted Lightning Core architecture.

## Overview

The new architecture introduces abstraction layers that allow Lightning Core to run in multiple environments:
- **Local**: Using Docker, SQLite, and in-memory event bus
- **Azure**: Using Azure services (Cosmos DB, Service Bus, ACI, Functions)
- **AWS**: Using AWS services (DynamoDB, SQS, ECS, Lambda) - coming soon
- **GCP**: Using Google Cloud services (Firestore, Pub/Sub, Cloud Run, Cloud Functions) - coming soon

## Key Changes

### 1. Configuration-Based Provider Selection

Instead of directly importing Azure services, use the abstraction layer:

**Before:**
```python
from azure.cosmos import CosmosClient
from azure.servicebus import ServiceBusClient

cosmos_client = CosmosClient.from_connection_string(conn_str)
service_bus_client = ServiceBusClient.from_connection_string(conn_str)
```

**After:**
```python
from lightning_core.runtime import get_runtime
from lightning_core.abstractions import RuntimeConfig, ExecutionMode

# Configure for local or cloud execution
config = RuntimeConfig(
    mode=ExecutionMode.LOCAL,  # or ExecutionMode.AZURE
    storage_provider="local",   # or "azure_cosmos"
    event_bus_provider="local", # or "azure_service_bus"
)

runtime = await initialize_runtime(config)
storage = runtime.storage
event_bus = runtime.event_bus
```

### 2. Storage Operations

**Before:**
```python
# Direct Cosmos DB usage
container = cosmos_client.get_database_client("mydb").get_container_client("tasks")
item = {"id": "123", "name": "My Task", "status": "pending"}
container.create_item(body=item)
```

**After:**
```python
from lightning_core.abstractions import Document

class TaskDocument(Document):
    def __init__(self, name="", status="pending", **kwargs):
        super().__init__(**kwargs)
        self.data["name"] = name
        self.data["status"] = status

# Get document store
task_store = runtime.get_document_store("tasks", TaskDocument)

# Create document
task = TaskDocument(name="My Task", status="pending")
await task_store.create(task)
```

### 3. Event Bus Operations

**Before:**
```python
# Direct Service Bus usage
async with ServiceBusClient.from_connection_string(conn_str) as client:
    sender = client.get_queue_sender("myqueue")
    message = ServiceBusMessage("Hello")
    await sender.send_messages(message)
```

**After:**
```python
from lightning_core.abstractions import EventMessage, EventPriority

# Publish event
event = EventMessage(
    event_type="task.created",
    data={"task_id": "123", "name": "My Task"},
    priority=EventPriority.HIGH
)
await runtime.publish_event(event, topic="task-events")

# Subscribe to events
async def handle_task_event(event: EventMessage):
    print(f"Task created: {event.data}")

await runtime.subscribe_to_events("task.created", handle_task_event)
```

### 4. Container Operations

**Before:**
```python
# Direct Azure Container Instances usage
from azure.mgmt.containerinstance import ContainerInstanceManagementClient

aci_client = ContainerInstanceManagementClient(credential, subscription_id)
container_group = aci_client.container_groups.create_or_update(
    resource_group, container_name, container_config
)
```

**After:**
```python
from lightning_core.abstractions import ContainerConfig, ResourceRequirements

# Define container
config = ContainerConfig(
    name="my-worker",
    image="python:3.9",
    command=["python", "worker.py"],
    environment_variables={"TASK_ID": "123"},
    resources=ResourceRequirements(cpu=1.0, memory_gb=1.5)
)

# Create container
container = await runtime.container_runtime.create_container(config)
```

### 5. Serverless Functions

**Before:**
```python
# Direct Azure Functions usage
# Requires separate function app deployment
```

**After:**
```python
from lightning_core.abstractions import (
    FunctionConfig, FunctionContext, FunctionResponse, RuntimeType
)

# Define function
async def process_task(context: FunctionContext) -> FunctionResponse:
    task_id = context.trigger_data.get("task_id")
    # Process task...
    return FunctionResponse(status_code=200, body={"result": "success"})

# Deploy function
config = FunctionConfig(
    name="task-processor",
    handler="process_task",
    runtime=RuntimeType.PYTHON,
    memory_mb=256
)
config.add_event_trigger(["task.created"])

function_id = await runtime.serverless.deploy_function(config, process_task)
```

## Migration Steps

### Step 1: Install Dependencies

```bash
# For local development
pip install lightning-core[local]

# For Azure deployment
pip install lightning-core[azure]

# For all providers
pip install lightning-core[all]
```

### Step 2: Update Configuration

Create a configuration file or use environment variables:

```python
# config.py
from lightning_core.abstractions import RuntimeConfig, ExecutionMode

def get_config():
    if os.getenv("ENVIRONMENT") == "production":
        return RuntimeConfig(
            mode=ExecutionMode.AZURE,
            storage_provider="azure_cosmos",
            storage_connection_string=os.getenv("COSMOS_CONNECTION_STRING"),
            event_bus_provider="azure_service_bus",
            event_bus_connection_string=os.getenv("SERVICE_BUS_CONNECTION_STRING"),
            container_runtime="azure_aci",
            serverless_provider="azure_functions"
        )
    else:
        return RuntimeConfig(
            mode=ExecutionMode.LOCAL,
            storage_provider="local",
            storage_path="./data",
            event_bus_provider="local",
            container_runtime="docker",
            serverless_provider="local"
        )
```

### Step 3: Refactor Service Usage

Replace direct Azure service usage with abstracted providers:

1. **Storage**: Replace Cosmos DB calls with DocumentStore methods
2. **Events**: Replace Service Bus calls with EventBus methods
3. **Containers**: Replace ACI calls with ContainerRuntime methods
4. **Functions**: Replace Azure Functions with ServerlessRuntime

### Step 4: Update Tests

Tests can now run locally without Azure dependencies:

```python
import pytest
from lightning_core.abstractions import RuntimeConfig, ExecutionMode
from lightning_core.runtime import LightningRuntime

@pytest.fixture
async def runtime():
    config = RuntimeConfig(mode=ExecutionMode.LOCAL)
    runtime = LightningRuntime(config)
    await runtime.initialize()
    yield runtime
    await runtime.shutdown()

async def test_storage_operations(runtime):
    # Test works the same in local and cloud modes
    store = runtime.get_document_store("test", MyDocument)
    doc = MyDocument(data={"test": "value"})
    created = await store.create(doc)
    assert created.id is not None
```

### Step 5: Environment Variables

Set environment variables for configuration:

```bash
# Local development
export LIGHTNING_MODE=local
export LIGHTNING_STORAGE_PATH=./data

# Azure production
export LIGHTNING_MODE=azure
export LIGHTNING_STORAGE_PROVIDER=azure_cosmos
export COSMOS_CONNECTION_STRING=your-connection-string
export SERVICE_BUS_CONNECTION_STRING=your-connection-string
```

## Best Practices

1. **Use Runtime Context**: Always use the `LightningRuntime` class for service access
2. **Configuration Management**: Store configuration in environment variables or config files
3. **Async/Await**: All operations are async - ensure proper async/await usage
4. **Error Handling**: Abstract providers throw standard Python exceptions
5. **Testing**: Test with local providers first, then test with cloud providers

## Common Patterns

### Pattern 1: Service Initialization

```python
from lightning_core.runtime import get_runtime

async def main():
    runtime = await initialize_runtime()
    
    # Use runtime services
    await runtime.publish_event(...)
    
    # Or use context manager
    async with runtime.session() as rt:
        await rt.publish_event(...)
```

### Pattern 2: Multi-Environment Support

```python
def create_runtime():
    if os.getenv("CI"):
        # Use local providers in CI
        return LightningRuntime(RuntimeConfig(mode=ExecutionMode.LOCAL))
    elif os.getenv("ENVIRONMENT") == "production":
        # Use Azure in production
        return LightningRuntime(RuntimeConfig(mode=ExecutionMode.AZURE))
    else:
        # Use local for development
        return LightningRuntime(RuntimeConfig(mode=ExecutionMode.LOCAL))
```

### Pattern 3: Gradual Migration

You can mix local and cloud providers:

```python
config = RuntimeConfig(
    mode=ExecutionMode.HYBRID,
    storage_provider="azure_cosmos",      # Use Azure for storage
    event_bus_provider="local",           # Use local for events
    container_runtime="docker",           # Use Docker locally
    serverless_provider="azure_functions" # Use Azure Functions
)
```

## Troubleshooting

### Issue: "Provider not found"
- Ensure you've installed the correct optional dependencies
- Check that provider names are spelled correctly

### Issue: "Connection failed"
- For local mode: Ensure Docker is running (for containers)
- For Azure mode: Check connection strings and network access

### Issue: "Container not starting"
- Local: Check Docker daemon is running and has sufficient resources
- Azure: Check Azure subscription limits and container configuration

## Next Steps

1. Review the [example code](examples/local_vs_cloud_example.py)
2. Start with local mode for development
3. Test with cloud providers in staging
4. Deploy to production with cloud providers

For more examples and detailed API documentation, see the Lightning Core documentation.