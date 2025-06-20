# Lightning Core

Lightning Core is the Python library that provides the foundational components for the Lightning OS.

## Architecture

Lightning Core uses an abstraction layer that allows the same code to run in both local development and cloud environments:

- **Local providers**: SQLite, Redis, Docker, Python subprocesses
- **Cloud providers**: Cosmos DB, Service Bus, Azure Functions, Container Instances

## Key Components

### Abstractions (`lightning_core/abstractions/`)
- `StorageProvider` - Abstract storage interface
- `EventBus` - Abstract messaging interface  
- `ContainerRuntime` - Abstract container management
- `ServerlessRuntime` - Abstract function execution
- `RuntimeConfig` - Configuration management

### Providers (`lightning_core/providers/`)
- `local/` - Local development implementations
- `azure/` - Azure cloud implementations
- `aws/` - AWS implementations (future)

### Event Processing (`lightning_core/vextir_os/`)
- Event-driven architecture
- Universal event processor
- Driver management system
- Event categorization (Input, Internal, Output)

### Planning System (`lightning_core/planner/`)
- Petri net-based workflow planning
- JSON plan validation
- Acyclic and reactive graph types
- Mermaid/Graphviz visualization

### Tools (`lightning_core/tools/`)
- Tool registry and bridges
- Integration with external services
- Agent tool management

## Usage

### Local Development
```python
from lightning_core.runtime import Runtime

# Initialize with local providers
runtime = Runtime(mode="local")
await runtime.start()
```

### Azure Deployment
```python
from lightning_core.runtime import Runtime

# Initialize with Azure providers
runtime = Runtime(mode="azure")
await runtime.start()
```

## Configuration

Set environment variables to control provider selection:

```bash
# Local development
export LIGHTNING_MODE=local
export LIGHTNING_STORAGE_PROVIDER=local
export LIGHTNING_EVENT_BUS_PROVIDER=redis

# Azure production  
export LIGHTNING_MODE=azure
export LIGHTNING_STORAGE_PROVIDER=cosmos
export LIGHTNING_EVENT_BUS_PROVIDER=servicebus
```

## Development Commands

```bash
# Install for development
pip install -e .[dev]

# Run tests
pytest

# Run with coverage
pytest --cov=lightning_core

# Type checking
mypy lightning_core

# Linting
flake8 lightning_core tests
black lightning_core tests
isort lightning_core tests
```

## Integration Points

- **Context Hub**: Persistent storage and CRDT synchronization
- **Agents**: AI agent execution and management
- **UI Components**: Web interfaces for interaction
- **External Tools**: Email, calendar, GitHub, Teams integrations