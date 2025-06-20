# Lightning OS

Lightning is an event-driven AI operating system that orchestrates autonomous and reactive AI workflows.

## Overview

Lightning provides a unified platform for building AI-powered applications that can:
- **Plan and execute complex workflows** using Petri net-based planning
- **Process events in real-time** through an event-driven architecture
- **Integrate with multiple AI providers** (OpenAI, Azure OpenAI, etc.)
- **Deploy anywhere** - same code runs locally and in the cloud
- **Persist and synchronize state** with CRDT-based storage

## Quick Start

### Local Development
```bash
# Clone the repository
git clone https://github.com/your-org/lightning.git
cd lightning

# Start the full stack locally
./scripts/deploy-test.sh -m local

# Or run a simple Python demo
python examples/local_demo.py
```

### Docker Compose
```bash
# Start all services with Docker Compose
docker-compose up -d

# Check service status
docker-compose ps
```

### Access Points
- **Lightning UI**: http://localhost:8080
- **Lightning API**: http://localhost:8000
- **Context Hub**: http://localhost:3000

## Architecture

Lightning uses a **provider-agnostic abstraction layer** that enables the same code to run in multiple environments:

```
┌─────────────────────────────────────────────────────────────────────┐
│                         APPLICATION CODE                             │
│  (Planner, Event Processor, Drivers, UI - Same for Local & Cloud)   │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        ABSTRACTION LAYER                             │
├─────────────────┬──────────────────┬──────────────────┬────────────┤
│ StorageProvider │    EventBus      │ ContainerRuntime │ Serverless │
│   (Abstract)    │    (Abstract)    │   (Abstract)     │ (Abstract) │
└─────────────────┴──────────────────┴──────────────────┴────────────┘
         │                   │                  │                │
         ▼                   ▼                  ▼                ▼
┌─────────────────┬──────────────────┬──────────────────┬────────────┐
│      LOCAL      │      AZURE       │   KUBERNETES     │     AWS    │
├─────────────────┼──────────────────┼──────────────────┼────────────┤
│ SQLite/Postgres │   Cosmos DB      │   PostgreSQL     │  DynamoDB  │
│ Redis/RabbitMQ  │  Service Bus     │   Redis/Kafka    │    SQS     │
│     Docker      │ Container Inst.  │   Kubernetes     │    ECS     │
│ Python Process  │ Azure Functions  │   Kubernetes     │  Lambda    │
└─────────────────┴──────────────────┴──────────────────┴────────────┘
```

## Core Components

### Lightning Core (`/core/`)
- **Planner**: Petri net-based workflow planning and execution
- **Vextir OS**: Event-driven operating system with universal event processor
- **Abstractions**: Provider-agnostic interfaces for storage, messaging, and compute
- **Tools**: Registry and bridges for external integrations

### Context Hub (`/context-hub/`)
- **Persistent Storage**: CRDT-based document storage with conflict resolution
- **Timeline System**: Event timeline with scrubbing and replay capabilities
- **Search Engine**: Full-text search with Tantivy
- **Snapshots**: Point-in-time backups and recovery

### AI Agents (`/agents/`)
- **Conseil**: Research and analysis agent (TypeScript/Node.js)
- **Voice Agent**: Real-time voice interaction (Next.js/React)
- **Agent Framework**: Flexible system for building custom AI agents

### User Interfaces (`/ui/`)
- **Integrated App**: Unified web interface for all Lightning features
- **Chat Interface**: Real-time conversation with AI agents
- **Dashboard**: System monitoring and management

## Key Features

### 🔄 Event-Driven Architecture
All system communication flows through events, enabling loose coupling and scalability.

### 🧠 AI-Powered Planning
Petri net-based planning system validates and executes complex multi-agent workflows.

### 🔗 Universal Abstractions
Same codebase runs locally (SQLite, Redis, Docker) and in cloud (Cosmos DB, Service Bus, Functions).

### 📊 Persistent State
CRDT-based storage ensures consistency across distributed deployments.

### 🛠️ Extensible Tools
Rich ecosystem of tool integrations (email, calendar, GitHub, etc.).

## Configuration

Lightning adapts to different environments through configuration:

```bash
# Local Development
export LIGHTNING_MODE=local
export LIGHTNING_STORAGE_PROVIDER=local
export LIGHTNING_EVENT_BUS_PROVIDER=redis

# Azure Production
export LIGHTNING_MODE=azure
export LIGHTNING_STORAGE_PROVIDER=cosmos
export LIGHTNING_EVENT_BUS_PROVIDER=servicebus
```

## Development

### Prerequisites
- Python 3.10+
- Docker and Docker Compose
- Node.js 18+ (for agents)
- Rust 1.70+ (for Context Hub)

### Common Commands
```bash
# Core development
cd core
pip install -e .[dev]
pytest

# Context Hub
cd context-hub
cargo build --release
cargo test

# Conseil Agent
cd agents/conseil
pnpm install
pnpm test

# Voice Agent
cd agents/voice-agent/webapp
npm install
npm run dev
```

## Documentation

Complete documentation is available in the [`/docs`](./docs) directory:

- **[Getting Started](./docs/development/LOCAL_DEVELOPMENT.md)** - Local development setup
- **[Architecture](./docs/architecture/SYSTEM_OVERVIEW.md)** - System architecture overview
- **[Deployment](./docs/deployment/README.md)** - Deployment guides for different environments
- **[API Reference](./docs/reference/api.md)** - Complete API documentation
- **[Configuration](./docs/reference/configuration.md)** - Environment variables and settings

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m 'Add amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- **Issues**: Report bugs and request features on [GitHub Issues](https://github.com/your-org/lightning/issues)
- **Discussions**: Join the community on [GitHub Discussions](https://github.com/your-org/lightning/discussions)
- **Documentation**: Comprehensive docs at [`/docs`](./docs)

---

Built with ❤️ by the Lightning OS team