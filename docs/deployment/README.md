# Lightning Deployment Guide

Lightning OS supports both local development and cloud deployment using unified Docker containers and configuration.

## Deployment Options

### 1. Local Development
- **Docker Compose**: Full local stack with PostgreSQL, Redis, and all services
- **Hybrid**: Some services local, others in cloud
- **Minimal**: Python-only demo without containers

### 2. Cloud Deployment
- **Azure**: Fully managed with Azure Functions, Cosmos DB, Service Bus
- **Kubernetes**: Container orchestration for any cloud provider
- **Hybrid Cloud**: Mix of cloud services and containers

## Quick Start

### Local Development
```bash
# Full stack with Docker Compose
./scripts/deploy-test.sh -m local

# Or minimal Python demo
python examples/local_demo.py
```

### Azure Deployment
```bash
# Build and deploy to Azure
./scripts/build-images.sh -m azure -p -r myregistry.azurecr.io
cd infra && pulumi up
```

## Configuration

Lightning uses environment-based configuration to support multiple deployment modes:

### Local Configuration (`.env.local`)
```bash
LIGHTNING_MODE=local
LIGHTNING_STORAGE_PROVIDER=local
LIGHTNING_EVENT_BUS_PROVIDER=redis
DATABASE_URL=postgres://lightning:lightning123@postgres:5432/lightning_db
REDIS_URL=redis://redis:6379
```

### Azure Configuration (`.env.azure`)
```bash
LIGHTNING_MODE=azure
LIGHTNING_STORAGE_PROVIDER=cosmos
LIGHTNING_EVENT_BUS_PROVIDER=servicebus
COSMOS_CONNECTION_STRING=${COSMOS_CONNECTION_STRING}
SERVICE_BUS_CONNECTION_STRING=${SERVICE_BUS_CONNECTION_STRING}
OPENAI_API_KEY=${OPENAI_API_KEY}
```

## Services

### Core API
- **Local**: FastAPI server on port 8000
- **Azure**: Azure Functions with HTTP triggers

### Event Processor
- **Local**: Background Python process
- **Azure**: Azure Functions with Service Bus triggers

### Context Hub
- **Local**: Rust binary on port 3000
- **Azure**: Container Instance with Azure Storage

### UI Components
- **Local**: FastAPI/Streamlit on port 8080
- **Azure**: Container Instance with CDN

## Docker Images

All services use unified Dockerfiles that adapt based on build arguments:

```bash
# Build local image
docker build --build-arg LIGHTNING_MODE=local -t lightning-api ./core

# Build Azure image  
docker build --build-arg LIGHTNING_MODE=azure -t lightning-api ./core
```

## Infrastructure as Code

### Pulumi (Azure)
```typescript
// Create unified container images
const images = createUnifiedContainerImages(acr, acrCreds);

// Deploy API service
const apiContainer = new azure.containerinstance.ContainerGroup("lightning-api", {
    containers: [{
        name: "api",
        image: images.api,
        ports: [{ port: 8000 }],
        environmentVariables: [
            { name: "LIGHTNING_MODE", value: "azure" },
            { name: "SERVICE_TYPE", value: "api" }
        ]
    }]
});
```

### Kubernetes
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: lightning-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: lightning-api
  template:
    metadata:
      labels:
        app: lightning-api
    spec:
      containers:
      - name: api
        image: lightning-api:latest
        ports:
        - containerPort: 8000
        env:
        - name: LIGHTNING_MODE
          value: "kubernetes"
        - name: SERVICE_TYPE
          value: "api"
```

## Scaling and Performance

### Horizontal Scaling
- **API**: Scale based on HTTP request load
- **Event Processor**: Scale based on queue depth
- **Context Hub**: Scale based on storage operations

### Resource Requirements
- **API**: 0.5 CPU, 1GB RAM per instance
- **Event Processor**: 1 CPU, 2GB RAM per instance  
- **Context Hub**: 1 CPU, 4GB RAM, SSD storage

## Monitoring and Observability

### Health Checks
All services expose `/health` endpoints:
```bash
curl http://localhost:8000/health
curl http://localhost:3000/health
```

### Metrics
- **Prometheus**: Metrics collection
- **Grafana**: Visualization
- **Application Insights**: Azure-specific monitoring

### Logging
- **Structured logging**: JSON format
- **Log levels**: DEBUG, INFO, WARN, ERROR
- **Log aggregation**: ELK stack or Azure Monitor

## Security

### Authentication
- **Local**: JWT tokens or API keys
- **Azure**: Azure AD integration
- **Kubernetes**: RBAC and service accounts

### Network Security
- **Local**: Host firewall rules
- **Azure**: Network Security Groups, Private Endpoints
- **Kubernetes**: Network Policies

### Secrets Management
- **Local**: Environment variables, `.env` files
- **Azure**: Key Vault integration
- **Kubernetes**: Kubernetes Secrets

## Backup and Recovery

### Data Backup
- **Local**: Database dumps, file system backups
- **Azure**: Cosmos DB automatic backups
- **Context Hub**: Snapshot-based backups

### Disaster Recovery
- **RTO**: 15 minutes (Recovery Time Objective)
- **RPO**: 5 minutes (Recovery Point Objective)
- **Multi-region**: Active-passive deployment

## CI/CD Pipeline

### Build Pipeline
```yaml
# .github/workflows/build.yml
name: Build and Deploy
on:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Build Images
        run: |
          ./scripts/build-images.sh -m local -s all
          ./scripts/build-images.sh -m azure -s all -p -r ${{ secrets.ACR_LOGIN_SERVER }}
      
      - name: Deploy to Staging
        run: |
          cd infra
          pulumi up --stack staging
```

### Deployment Strategies
- **Blue-Green**: Zero-downtime deployments
- **Rolling**: Gradual instance replacement
- **Canary**: Traffic splitting for testing

## Troubleshooting

### Common Issues
1. **Port conflicts**: Check for conflicting services
2. **Missing dependencies**: Verify all required packages installed
3. **Configuration errors**: Validate environment variables
4. **Network connectivity**: Check firewall and DNS settings

### Debug Commands
```bash
# Check service status
./scripts/deploy-test.sh -a status

# View logs
docker-compose logs -f lightning-api

# Test connectivity
curl -v http://localhost:8000/health
```

### Performance Issues
- **High CPU**: Check for infinite loops or excessive processing
- **High memory**: Look for memory leaks or large data structures
- **Slow responses**: Profile database queries and external API calls