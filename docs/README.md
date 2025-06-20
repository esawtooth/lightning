# Lightning OS Documentation

Lightning is an event-driven AI operating system that orchestrates autonomous and reactive AI workflows.

## Quick Start

- [Local Development](development/LOCAL_DEVELOPMENT.md) - Set up Lightning locally
- [System Overview](architecture/SYSTEM_OVERVIEW.md) - Understanding Lightning's architecture
- [Deployment Guide](deployment/README.md) - Deploy to cloud environments

## Architecture

- [System Overview](architecture/SYSTEM_OVERVIEW.md) - High-level architecture
- [Event-Driven Design](architecture/event-driven.md) - Event processing and flows
- [Abstraction Layer](architecture/abstraction-layer.md) - Provider-agnostic design
- [Petri Net Planning](architecture/planning.md) - Workflow planning system

## Development

- [Local Development](development/LOCAL_DEVELOPMENT.md) - Local setup and testing
- [Tool Management](development/TOOL_MANAGEMENT_GUIDE.md) - Adding and managing tools
- [CLI Guide](development/CLI_GUIDE.md) - Command-line interface usage
- [Testing](development/testing.md) - Running tests and benchmarks

## Deployment

- [Cloud Deployment](deployment/cloud-deployment.md) - Azure deployment recommendations
- [Docker Setup](deployment/docker.md) - Containerization guide
- [Unified Deployment](deployment/unified-deployment.md) - Local/cloud unified approach

## Components

### Core
- [Lightning Core](components/core/README.md) - Python library overview
- [Planner Integration](components/core/planner-integration.md) - Workflow planning
- [Vextir OS](components/core/vextir-os.md) - Event-driven operating system

### Context Hub
- [Context Hub](components/context-hub/README.md) - Persistent storage with CRDT sync
- [API Guide](components/context-hub/api-guide.md) - REST API documentation
- [Timeline System](components/context-hub/timeline.md) - Event timeline and scrubbing

### Agents
- [Agent System](components/agents/README.md) - Overview of AI agents
- [Conseil Agent](components/agents/conseil.md) - Research agent
- [Voice Agent](components/agents/voice-agent.md) - Voice interaction agent

### UI Components
- [Lightning UI](components/ui/README.md) - User interface overview
- [Integrated App](components/ui/integrated-app.md) - Unified UI application

## Reference

- [API Reference](reference/api.md) - REST API documentation
- [Configuration](reference/configuration.md) - Environment variables and settings
- [Event Schema](reference/events.md) - Event types and structures
- [Migration Guides](reference/migrations.md) - Version upgrade guides

## Contributing

- [Development Workflow](contributing/workflow.md) - Git workflow and conventions
- [Code Style](contributing/style.md) - Coding standards
- [Documentation](contributing/documentation.md) - Documentation guidelines