# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Lightning is an event-driven AI operating system that orchestrates autonomous and reactive AI workflows. It consists of:
- **Lightning Core**: Python library with planning system (Petri net-based workflows) and Vextir OS (event-driven architecture)
- **Azure Infrastructure**: Serverless deployment using Functions, Service Bus, Cosmos DB
- **Multiple UIs**: Chat client (Chainlit), dashboard (FastAPI), voice agent (Next.js)
- **Context Hub**: Rust-based persistent storage with CRDT synchronization

## Common Development Commands

### Python Core Development (`/core/`)
```bash
# Run all tests
cd core && pytest

# Run specific test file
pytest tests/planner/test_planner_integration.py

# Run with coverage
pytest --cov=lightning_core

# Linting and formatting
flake8 lightning_core tests
black lightning_core tests
isort lightning_core tests

# Type checking
mypy lightning_core

# Install for development
pip install -e .[dev]

# Install with local providers (Docker, SQLite)
pip install -e .[local]

# Install with Azure providers
pip install -e .[azure]

# Run event processor locally
python examples/run_event_processor_locally.py

# Test local vs cloud deployment
python examples/local_vs_cloud_example.py
```

### Conseil Agent (`/agents/conseil/`)
```bash
# Uses pnpm - ensure you have it installed
pnpm install
pnpm build
pnpm test
pnpm lint
pnpm typecheck
pnpm format:fix
```

### Voice Agent (`/agents/voice-agent/webapp/`)
```bash
# Standard Next.js commands
npm run dev     # Development server
npm run build   # Production build
npm run lint    # Linting
```

## Architecture Overview

### Abstraction Layer (NEW)
- **Provider-agnostic design**: Same code runs locally and in cloud
- **Storage**: Abstract document store (local SQLite, Azure Cosmos DB)
- **Event Bus**: Abstract messaging (local queues, Azure Service Bus)
- **Container Runtime**: Abstract containers (Docker, Azure Container Instances)
- **Serverless**: Abstract functions (local processes, Azure Functions)
- **Configuration**: Environment-based provider selection

### Event-Driven Core
- All system communication flows through events (abstracted event bus)
- Events categorized as Input (external triggers), Internal (system state), Output (external actions)
- Universal Processor handles event routing and execution
- **Works both locally and in Azure Functions with same codebase**

### Petri Net Planning System
- Plans are JSON structures representing concurrent workflows
- Two graph types: Acyclic (one-time) and Reactive (continuous)
- Plans validated using Petri net theory before execution
- Visualization available via Mermaid/Graphviz

### Driver Architecture
- **Agent Drivers**: LLM-powered agents (Conseil for research, Vex for voice)
- **Tool Drivers**: Integrations (email, calendar, GitHub, Teams)
- **Communication Drivers**: Notification systems
- **IO Drivers**: External system interfaces

### Key Components
- `lightning_core/abstractions/`: Provider interfaces and configuration
- `lightning_core/providers/`: Local and cloud implementations
- `lightning_core/runtime.py`: Unified runtime for all services
- `lightning_core/planner/`: Workflow planning and validation
- `lightning_core/vextir_os/`: Event processing and driver management
- `lightning_core/tools/`: Tool registry and bridges
- `lightning_core/events/`: Event models and registry

## Testing Strategy

### Python Tests
- Unit tests: Fast, isolated component tests
- Integration tests: End-to-end workflow validation
- Use pytest markers: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.slow`
- Mock external services (OpenAI, Azure) in unit tests

### Running Single Tests
```bash
# Run specific test function
pytest path/to/test.py::TestClass::test_method

# Run tests matching pattern
pytest -k "test_pattern"

# Skip slow tests
pytest -m "not slow"
```

## Important Considerations

### Environment Variables
- `OPENAI_API_KEY`: Required for LLM planning features
- Azure credentials needed for cloud deployment
- Check `.env.example` files for required configuration

### Git Workflow
- Main branch is `main`
- Recent restructuring moved from separate `planner/` and `vextir_os/` to unified `lightning_core/`
- Use descriptive commit messages following conventional commits

### Code Style
- Python: Black formatting (88 char lines), isort for imports, type hints required
- TypeScript: ESLint + Prettier configuration in Conseil agent
- Follow existing patterns in each component

### Azure Deployment
- Infrastructure defined in `/infra/` using Pulumi
- Deployment requires Azure subscription and appropriate permissions
- Azure Functions for serverless compute, Service Bus for messaging

### Tool Registry
When adding new tools:
1. Define in `lightning_core/tools/registry.tools.json`
2. Implement bridge in `lightning_core/tools/bridges/`
3. Add tests for tool execution
4. Update tool documentation

### Event Models
- Events use Pydantic models for validation
- Follow naming convention: `category.subcategory.action`
- Events must be registered in event registry