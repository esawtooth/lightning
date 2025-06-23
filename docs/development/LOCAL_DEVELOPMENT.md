# Lightning OS - Local Development Guide

This guide explains how to run the entire Lightning OS stack locally using Docker Compose.

## Overview

The local development environment includes:
- **Lightning Core API**: FastAPI backend with all abstraction layers
- **Event Processor**: Local event processing service
- **Context Hub**: Rust-based document storage with CRDT support
- **UI Components**: Chat client, dashboard, and integrated app
- **Storage**: PostgreSQL (replaces Cosmos DB)
- **Message Queue**: Redis (replaces Azure Service Bus)
- **Container Runtime**: Docker (replaces Azure Container Instances)

## Prerequisites

1. **Docker Desktop** (includes Docker and Docker Compose)
   - [Download for Mac](https://www.docker.com/products/docker-desktop/)
   - [Download for Windows](https://www.docker.com/products/docker-desktop/)
   - [Download for Linux](https://docs.docker.com/desktop/install/linux-install/)

2. **OpenAI API Key** (for LLM features)
   - Get from [OpenAI Platform](https://platform.openai.com/api-keys)

3. **Git** (to clone the repository)

4. **Minimum System Requirements**:
   - 8GB RAM (16GB recommended)
   - 10GB free disk space
   - Docker Desktop running

## Quick Start

1. **Clone the repository**:
   ```bash
   git clone https://github.com/your-org/lightning.git
   cd lightning
   ```

2. **Run the startup script**:
   ```bash
   ./scripts/start-local.sh
   ```

3. **First time setup**:
   - The script will create a `.env` file
   - Edit `.env` and add your OpenAI API key
   - Run the script again

4. **Access the system**:
   - Integrated UI: http://localhost:8080
   - Chat Client: http://localhost:8501
   - Dashboard: http://localhost:8502
   - API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

## Manual Setup

If you prefer manual setup or need to customize:

### 1. Create Environment File

Create `.env` in the project root:

```env
# OpenAI Configuration
OPENAI_API_KEY=your-openai-api-key-here

# Authentication
JWT_SECRET=local-development-secret-key
AUTH_ENABLED=false

# Logging
LOG_LEVEL=INFO

# Lightning Mode
LIGHTNING_MODE=local
```

### 2. Build Services

```bash
docker-compose build
```

### 3. Start Services

```bash
# Start all services
docker-compose -f docker-compose.local.yml up -d

# Start specific services
docker-compose -f docker-compose.local.yml up -d postgres redis
docker-compose -f docker-compose.local.yml up -d lightning-api event-processor
docker-compose -f docker-compose.local.yml up -d chat-client dashboard integrated-app
```

### 4. View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f lightning-api
docker-compose logs -f event-processor
```

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Integrated    │     │   Chat Client   │     │    Dashboard    │
│      UI         │     │       UI        │     │       UI        │
│   Port: 8080    │     │   Port: 8501    │     │   Port: 8502    │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                         │
         └───────────────────────┴─────────────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    │   Lightning Core API    │
                    │      Port: 8000         │
                    └────────────┬────────────┘
                                 │
          ┌──────────────────────┼──────────────────────┐
          │                      │                      │
┌─────────┴────────┐   ┌────────┴────────┐   ┌────────┴────────┐
│ Event Processor  │   │   Context Hub   │   │     Redis       │
│  (Functions)     │   │   Port: 3000    │   │   Port: 6379    │
└──────────────────┘   └─────────────────┘   └─────────────────┘
                                 │
                       ┌─────────┴────────┐
                       │   PostgreSQL     │
                       │   Port: 5432     │
                       └──────────────────┘
```

## Testing the System

### 1. Health Check
```bash
curl http://localhost:8000/health
```

### 2. Submit Test Event
```bash
curl -X POST http://localhost:8000/api/events \
  -H "Content-Type: application/json" \
  -d '{
    "type": "user.action",
    "userID": "test-user",
    "data": {
      "action": "test",
      "timestamp": "'$(date -u +"%Y-%m-%dT%H:%M:%SZ")'"
    }
  }'
```

### 3. Create Test Task
```bash
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -H "X-User-ID: test-user" \
  -d '{
    "title": "Test Task",
    "description": "This is a test task",
    "priority": "high"
  }'
```

### 4. Check Event Processing
```bash
# View event processor logs
docker-compose logs -f event-processor

# View API logs
docker-compose logs -f lightning-api
```

## Development Workflow

### 1. Hot Reload
- Python services (API, event processor) support hot reload
- Changes to code are automatically reflected
- UI changes require page refresh

### 2. Adding New Features
1. Update code in your local directory
2. Services will auto-reload (Python) or rebuild (UI)
3. Test using the local endpoints

### 3. Running Tests
```bash
# Run tests in container
docker-compose exec lightning-api pytest

# Run specific test
docker-compose exec lightning-api pytest tests/test_api.py
```

### 4. Database Access
```bash
# Connect to PostgreSQL
docker-compose exec postgres psql -U lightning -d lightning_db

# Connect to Redis
docker-compose exec redis redis-cli
```

## Troubleshooting

### Services Not Starting
1. Check Docker is running: `docker info`
2. Check ports are available: `lsof -i :8000`
3. View logs: `docker-compose logs [service-name]`

### Database Connection Issues
1. Ensure PostgreSQL is healthy: `docker-compose ps postgres`
2. Check connection: `docker-compose exec postgres pg_isready`

### Event Processing Issues
1. Check Redis is running: `docker-compose ps redis`
2. Monitor event processor: `docker-compose logs -f event-processor`

### UI Not Loading
1. Check API is running: `curl http://localhost:8000/health`
2. Check browser console for errors
3. Ensure CORS is properly configured

## Advanced Configuration

### Using Different Ports
Edit `docker-compose.local.yml` and change the port mappings:
```yaml
ports:
  - "9000:8000"  # API on port 9000 instead of 8000
```

### Persistent Data
Data is stored in Docker volumes. To reset:
```bash
docker-compose -f docker-compose.local.yml down -v  # Remove volumes
docker-compose -f docker-compose.local.yml up -d    # Recreate
```

### Running Agents
```bash
# Run Conseil agent
docker-compose --profile agents run agent-runner
```

### Production Mode Locally
Set in `.env`:
```env
LIGHTNING_MODE=azure
# Add Azure connection strings
```

## Cleanup

### Stop Services
```bash
docker-compose down
```

### Remove Everything (including data)
```bash
docker-compose down -v
docker system prune -a
```

## Next Steps

1. **Explore the API**: http://localhost:8000/docs
2. **Try the Chat Interface**: http://localhost:8501
3. **Create Plans**: Use the integrated UI at http://localhost:8080
4. **Monitor Events**: Watch the event processor logs
5. **Build Agents**: Check the agents directory

## Contributing

When developing locally:
1. Make changes in your local files
2. Test with the local stack
3. Commit changes
4. Push to create PR

The same code runs in both local and cloud environments!