# Lightning Core

Lightning Core is a comprehensive AI planning and operating system library that provides two main components:

1. **Lightning Planner** - A workflow planning and validation system using Petri nets
2. **Vextir OS** - An event-driven AI operating system with driver architecture

## Features

### Lightning Planner
- **Workflow Planning**: Create complex workflows using natural language instructions
- **Petri Net Validation**: Validate workflows using Petri net theory for correctness
- **Tool Registry**: Manage and discover available tools and capabilities
- **Plan Storage**: Store and retrieve plans with versioning support
- **Schema Validation**: Comprehensive JSON schema validation for plans

### Vextir OS
- **Event-Driven Architecture**: Asynchronous event bus for system communication
- **Driver Framework**: Pluggable driver system for extending functionality
- **Agent Drivers**: LLM-powered agents for intelligent event processing
- **Tool Drivers**: Specific capability providers (email, calendar, etc.)
- **IO Drivers**: External system interfaces
- **Security**: Policy-based authorization and audit logging

## Installation

```bash
pip install lightning-core
```

### Optional Dependencies

For specific functionality, install optional dependencies:

```bash
# For Petri net validation
pip install lightning-core[petri]

# For email integration
pip install lightning-core[email]

# For calendar integration  
pip install lightning-core[calendar]

# For messaging (Slack, SMS, etc.)
pip install lightning-core[messaging]

# Install all optional dependencies
pip install lightning-core[all]

# For development
pip install lightning-core[dev]
```

## Quick Start

### Lightning Planner

```python
from lightning_core.planner import create_verified_plan, PlanModel

# Create a plan from natural language
plan = create_verified_plan("Send daily email summaries at 6 PM")

# The plan is automatically validated and ready to use
print(f"Created plan: {plan['plan_name']}")
print(f"Steps: {len(plan['steps'])}")
```

### Vextir OS Event System

```python
import asyncio
from lightning_core.vextir_os import EventBus, Event, EventFilter

async def main():
    # Create event bus
    bus = EventBus()
    
    # Subscribe to events
    def handle_user_events(event):
        print(f"Received user event: {event.type}")
    
    filter = EventFilter(event_types=["user.*"])
    bus.subscribe(filter, handle_user_events)
    
    # Emit events
    await bus.emit(Event(type="user.login", data={"user_id": "123"}))
    await bus.emit(Event(type="user.action", data={"action": "click"}))

asyncio.run(main())
```

### Driver System

```python
from lightning_core.vextir_os import Driver, DriverManifest, DriverType, ResourceSpec

# Create a custom driver
class MyCustomDriver(Driver):
    def get_capabilities(self):
        return ["custom.action"]
    
    def get_resource_requirements(self):
        return ResourceSpec(memory_mb=256, timeout_seconds=30)
    
    async def handle_event(self, event):
        if event.type == "custom.action":
            print(f"Handling custom action: {event.data}")
            return [Event(type="custom.completed", data={"result": "success"})]
        return []

# Register the driver
manifest = DriverManifest(
    id="my-custom-driver",
    name="My Custom Driver",
    version="1.0.0",
    author="Your Name",
    description="A custom driver example",
    driver_type=DriverType.TOOL,
    capabilities=["custom.action"],
    resource_requirements=ResourceSpec()
)

# Use with driver registry
from lightning_core.vextir_os import get_driver_registry

registry = get_driver_registry()
await registry.register_driver(manifest, MyCustomDriver)
```

## Architecture

### Lightning Planner Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Instruction   │───▶│   LLM Planner    │───▶│   Plan JSON     │
│   (Natural      │    │   (OpenAI GPT)   │    │   (Structured)  │
│   Language)     │    │                  │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │                        │
                                ▼                        ▼
                       ┌──────────────────┐    ┌─────────────────┐
                       │   Tool Registry  │    │   Validator     │
                       │   (Available     │    │   (Petri Net +  │
                       │   Actions)       │    │   Schema)       │
                       └──────────────────┘    └─────────────────┘
```

### Vextir OS Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Vextir OS                                │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────┐ │
│  │   Agent     │  │    Tool     │  │     IO      │  │   UI    │ │
│  │  Drivers    │  │  Drivers    │  │  Drivers    │  │ Drivers │ │
│  │             │  │             │  │             │  │         │ │
│  │ • Chat      │  │ • Email     │  │ • Calendar  │  │ • Web   │ │
│  │ • Research  │  │ • GitHub    │  │ • Slack     │  │ • CLI   │ │
│  │ • Assistant │  │ • Context   │  │ • SMS       │  │         │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────┘ │
├─────────────────────────────────────────────────────────────────┤
│                     Driver Registry                             │
├─────────────────────────────────────────────────────────────────┤
│                       Event Bus                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │   Events    │  │  Filters    │  │  Streams    │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
├─────────────────────────────────────────────────────────────────┤
│                   Security & Policy                             │
└─────────────────────────────────────────────────────────────────┘
```

## Examples

### Email Workflow Plan

```python
from lightning_core.planner import create_verified_plan

# Create an email workflow
instruction = """
Create a workflow that:
1. Checks for new emails every hour
2. Summarizes important emails
3. Sends a daily summary at 6 PM
4. Handles urgent emails immediately
"""

plan = create_verified_plan(instruction)

# The plan will include:
# - External events (time.cron for hourly checks, webhooks for urgent emails)
# - Steps (fetch emails, summarize, send summary, handle urgent)
# - Proper event flow and dependencies
```

### Real-time Event Processing

```python
import asyncio
from lightning_core.vextir_os import EventBus, EventFilter, EventStream

async def process_user_actions():
    bus = EventBus()
    
    # Create a stream for user events
    filter = EventFilter(
        event_types=["user.click", "user.scroll", "user.type"],
        categories=[EventCategory.INPUT]
    )
    
    async with EventStream(filter, bus) as stream:
        while True:
            event = await stream.get_event()
            
            # Process the event
            if event.type == "user.click":
                print(f"User clicked: {event.data.get('element')}")
            elif event.type == "user.scroll":
                print(f"User scrolled: {event.data.get('direction')}")
            elif event.type == "user.type":
                print(f"User typed: {event.data.get('text')}")

# Run the processor
asyncio.run(process_user_actions())
```

## Configuration

### Environment Variables

```bash
# OpenAI API Key (for planner)
export OPENAI_API_KEY="your-openai-api-key"

# Database connection (for plan storage)
export LIGHTNING_DB_ENDPOINT="your-database-endpoint"
export LIGHTNING_DB_KEY="your-database-key"

# Email configuration (for email drivers)
export GMAIL_CLIENT_ID="your-gmail-client-id"
export GMAIL_CLIENT_SECRET="your-gmail-client-secret"

# Slack configuration (for messaging drivers)
export SLACK_BOT_TOKEN="your-slack-bot-token"
```

### Configuration File

Create a `lightning.config.json` file:

```json
{
  "planner": {
    "model": "gpt-4",
    "max_retries": 3,
    "timeout": 30
  },
  "vextir_os": {
    "event_bus": {
      "max_history": 10000
    },
    "drivers": {
      "auto_start": true,
      "resource_limits": {
        "memory_mb": 1024,
        "timeout_seconds": 60
      }
    }
  }
}
```

## Testing

Run the test suite:

```bash
# Install development dependencies
pip install lightning-core[dev]

# Run all tests
pytest

# Run with coverage
pytest --cov=lightning_core

# Run specific test modules
pytest tests/planner/
pytest tests/vextir_os/

# Run integration tests
pytest -m integration
```

## Development

### Setting up Development Environment

```bash
# Clone the repository
git clone https://github.com/lightning-ai/lightning-core.git
cd lightning-core

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode
pip install -e .[dev]

# Install pre-commit hooks
pre-commit install
```

### Code Quality

The project uses several tools for code quality:

- **Black**: Code formatting
- **isort**: Import sorting
- **flake8**: Linting
- **mypy**: Type checking
- **pytest**: Testing

Run quality checks:

```bash
# Format code
black lightning_core tests

# Sort imports
isort lightning_core tests

# Lint code
flake8 lightning_core tests

# Type check
mypy lightning_core

# Run all checks
pre-commit run --all-files
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for your changes
5. Ensure all tests pass (`pytest`)
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- **Documentation**: [https://lightning-core.readthedocs.io](https://lightning-core.readthedocs.io)
- **Issues**: [https://github.com/lightning-ai/lightning-core/issues](https://github.com/lightning-ai/lightning-core/issues)
- **Discussions**: [https://github.com/lightning-ai/lightning-core/discussions](https://github.com/lightning-ai/lightning-core/discussions)

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for a list of changes and version history.
