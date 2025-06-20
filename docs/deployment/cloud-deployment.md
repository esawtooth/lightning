# Cloud Deployment Recommendations for Lightning OS

## Overview

This document provides recommendations for unifying the Docker-based local deployment with Azure cloud deployment using the same Dockerfiles and configurations.

## Current State Analysis

### Local Setup (Docker Compose)
- **PostgreSQL** for data storage
- **Redis** for event bus and caching
- **RabbitMQ** for additional messaging
- **Event Processor** as a container
- All services run as Docker containers
- Direct port mapping for access

### Azure Setup (Pulumi)
- **Cosmos DB** for data storage
- **Service Bus** for messaging
- **Azure Functions** for serverless compute
- **Container Instances** for UI and agents
- **Front Door** for CDN and routing
- **Azure AD** for authentication

## Key Recommendations

### 1. Unified Dockerfile Strategy

#### Current Issues:
- Dockerfiles hardcode local dependencies (`pip install -e .[local]`)
- No support for Azure-specific dependencies
- Different entry points for local vs cloud

#### Recommended Changes:

**Core Dockerfile** (`core/Dockerfile`):
```dockerfile
# Lightning Core API Dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY pyproject.toml .
COPY README.md .

# Install Python dependencies based on environment
ARG LIGHTNING_MODE=local
RUN pip install --no-cache-dir -U pip setuptools wheel
RUN if [ "$LIGHTNING_MODE" = "azure" ]; then \
        pip install --no-cache-dir -e .[azure,dev]; \
    else \
        pip install --no-cache-dir -e .[local,dev]; \
    fi

# Copy application code
COPY . .

# Create data directory
RUN mkdir -p /app/data

# Default command (can be overridden)
CMD ["python", "-m", "lightning_core.runtime"]
```

### 2. Environment-Based Configuration

Create a unified runtime entry point that adapts based on environment:

**`lightning_core/runtime.py`**:
```python
import os
import sys

def main():
    mode = os.getenv("LIGHTNING_MODE", "local")
    service_type = os.getenv("SERVICE_TYPE", "api")
    
    if service_type == "api":
        if mode == "azure":
            # Azure Function handler
            from lightning_core.azure.function_app import app
            # Azure Functions runtime will handle this
        else:
            # Local FastAPI
            import uvicorn
            from lightning_core.api.main import app
            uvicorn.run(app, host="0.0.0.0", port=8000)
    
    elif service_type == "event_processor":
        if mode == "azure":
            # Azure Functions handles this via triggers
            from lightning_core.azure.event_processor import handler
        else:
            # Local event processor
            from lightning_core.vextir_os.local_event_processor import main
            main()

if __name__ == "__main__":
    main()
```

### 3. Build Strategy

#### Multi-Stage Dockerfile for Optimization:
```dockerfile
# Base stage
FROM python:3.10-slim AS base
WORKDIR /app
RUN apt-get update && apt-get install -y gcc g++ git curl && rm -rf /var/lib/apt/lists/*

# Local build stage
FROM base AS local-build
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir -e .[local,dev]

# Azure build stage
FROM base AS azure-build
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir -e .[azure,dev]

# Final stage
FROM base AS final
ARG LIGHTNING_MODE=local
COPY --from=local-build /usr/local /usr/local
COPY --from=azure-build /usr/local /usr/local
COPY . .
RUN mkdir -p /app/data
CMD ["python", "-m", "lightning_core.runtime"]
```

### 4. Azure Container Instances Deployment

Update Pulumi to use the same Docker images:

```python
# Build images with Azure mode
api_image = docker.Image(
    "lightning-api",
    build=docker.DockerBuildArgs(
        context="../core",
        dockerfile="../core/Dockerfile",
        args={"LIGHTNING_MODE": "azure"},
    ),
    image_name=pulumi.Output.concat(acr.login_server, "/lightning-api:latest"),
    registry=docker.RegistryArgs(
        server=acr.login_server,
        username=acr_creds.username,
        password=acr_creds.passwords[0].value,
    ),
)

# Deploy API as Container Instance
api_cg = aci_group(
    "lightning-api",
    api_image.image_name,
    8000,
    [
        containerinstance.EnvironmentVariableArgs(name="LIGHTNING_MODE", value="azure"),
        containerinstance.EnvironmentVariableArgs(name="SERVICE_TYPE", value="api"),
        containerinstance.EnvironmentVariableArgs(name="COSMOS_CONNECTION_STRING", value=cosmos_cs),
        containerinstance.EnvironmentVariableArgs(name="SERVICE_BUS_CONNECTION_STRING", value=sb_cs),
        # ... other Azure-specific env vars
    ],
)
```

### 5. Event Processing Strategy

For event processing, create a hybrid approach:

1. **Local**: Run as a container with Redis subscription
2. **Azure**: Deploy as both:
   - Azure Function for Service Bus triggers (serverless)
   - Container Instance for continuous processing (if needed)

### 6. Configuration Management

Create environment-specific configuration files:

**`.env.local`**:
```bash
LIGHTNING_MODE=local
LIGHTNING_STORAGE_PROVIDER=local
LIGHTNING_EVENT_BUS_PROVIDER=redis
DATABASE_URL=postgres://lightning:lightning123@postgres:5432/lightning_db
REDIS_URL=redis://redis:6379
```

**`.env.azure`**:
```bash
LIGHTNING_MODE=azure
LIGHTNING_STORAGE_PROVIDER=cosmos
LIGHTNING_EVENT_BUS_PROVIDER=servicebus
COSMOS_CONNECTION_STRING=${COSMOS_CONNECTION_STRING}
SERVICE_BUS_CONNECTION_STRING=${SERVICE_BUS_CONNECTION_STRING}
```

### 7. Docker Compose for Azure Testing

Create `docker-compose.azure.yml` for testing Azure configurations locally:

```yaml
version: '3.8'

services:
  # Azurite for local Azure Storage emulation
  azurite:
    image: mcr.microsoft.com/azure-storage/azurite
    ports:
      - "10000:10000"  # Blob
      - "10001:10001"  # Queue
      - "10002:10002"  # Table

  # API with Azure configuration
  lightning-api:
    build:
      context: ./core
      dockerfile: Dockerfile
      args:
        LIGHTNING_MODE: azure
    environment:
      LIGHTNING_MODE: azure
      SERVICE_TYPE: api
      # Use Azurite for local testing
      AZURE_STORAGE_CONNECTION_STRING: "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=..."
```

### 8. CI/CD Pipeline

Create a unified build pipeline:

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
      
      - name: Build Local Images
        run: |
          docker build --build-arg LIGHTNING_MODE=local -t lightning-api:local ./core
          
      - name: Build Azure Images
        run: |
          docker build --build-arg LIGHTNING_MODE=azure -t lightning-api:azure ./core
          
      - name: Push to ACR
        if: github.ref == 'refs/heads/main'
        run: |
          docker tag lightning-api:azure ${{ secrets.ACR_LOGIN_SERVER }}/lightning-api:latest
          docker push ${{ secrets.ACR_LOGIN_SERVER }}/lightning-api:latest
```

## Implementation Priority

1. **Phase 1**: Update Dockerfiles with build arguments and multi-stage builds
2. **Phase 2**: Create unified runtime entry point
3. **Phase 3**: Update Pulumi infrastructure to use containerized services
4. **Phase 4**: Implement hybrid event processing
5. **Phase 5**: Set up CI/CD pipeline

## Benefits

1. **Single Codebase**: Same Docker images work locally and in Azure
2. **Easy Testing**: Test Azure configurations locally
3. **Flexible Deployment**: Choose between serverless (Functions) or containers
4. **Cost Optimization**: Use Container Instances for always-on services, Functions for event-driven
5. **Development Parity**: Local environment closely matches production

## Migration Path

1. Start with API service as proof of concept
2. Gradually migrate other services
3. Maintain backward compatibility during transition
4. Test thoroughly in staging environment
5. Document configuration differences