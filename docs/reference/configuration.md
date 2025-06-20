# Lightning Configuration Reference

Lightning OS uses environment variables and configuration files to adapt to different deployment environments.

## Core Environment Variables

### Runtime Mode
```bash
# Deployment mode - determines which providers to use
LIGHTNING_MODE=local|azure|kubernetes

# Service type - for multi-service containers
SERVICE_TYPE=api|event_processor|ui|agent
```

### Provider Configuration
```bash
# Storage provider selection
LIGHTNING_STORAGE_PROVIDER=local|cosmos|postgres

# Event bus provider selection  
LIGHTNING_EVENT_BUS_PROVIDER=redis|servicebus|rabbitmq

# Container runtime provider
LIGHTNING_CONTAINER_RUNTIME=docker|azure_container_instances

# Serverless runtime provider
LIGHTNING_SERVERLESS_RUNTIME=local|azure_functions
```

## Local Development

### Database Configuration
```bash
# PostgreSQL (primary database)
DATABASE_URL=postgres://username:password@host:port/database

# SQLite (fallback/testing)
SQLITE_DATABASE_PATH=/path/to/database.db
```

### Event Bus Configuration
```bash
# Redis
REDIS_URL=redis://host:port
REDIS_PASSWORD=password

# RabbitMQ
RABBITMQ_URL=amqp://username:password@host:port
```

### Context Hub Configuration
```bash
# Context Hub service endpoint
CONTEXT_HUB_URL=http://localhost:3000

# Context Hub data directory
CONTEXT_HUB_DATA_DIR=/app/data

# Context Hub log level
CONTEXT_HUB_LOG_LEVEL=info|debug|warn|error
```

## Azure Cloud Configuration

### Storage Configuration
```bash
# Cosmos DB
COSMOS_CONNECTION_STRING=AccountEndpoint=...;AccountKey=...
COSMOS_DATABASE_NAME=lightning
COSMOS_CONTAINER_NAME=documents

# Azure Storage (for Context Hub)
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=...
AZURE_STORAGE_CONTAINER_NAME=lightning-data
```

### Messaging Configuration  
```bash
# Service Bus
SERVICE_BUS_CONNECTION_STRING=Endpoint=...;SharedAccessKeyName=...
SERVICE_BUS_TOPIC_NAME=lightning-events
SERVICE_BUS_SUBSCRIPTION_NAME=lightning-processor
```

### Azure Services
```bash
# Application Insights
APPINSIGHTS_INSTRUMENTATIONKEY=key
APPINSIGHTS_CONNECTION_STRING=InstrumentationKey=...

# Azure Functions
AZURE_FUNCTIONS_APP_NAME=lightning-functions
AZURE_FUNCTIONS_RESOURCE_GROUP=lightning-rg
```

## AI and LLM Configuration

### OpenAI Configuration
```bash
# OpenAI API key
OPENAI_API_KEY=sk-...

# Model selection
OPENAI_MODEL=gpt-4|gpt-3.5-turbo
OPENAI_MAX_TOKENS=4096
OPENAI_TEMPERATURE=0.7
```

### Azure OpenAI Configuration
```bash
# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=key
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4
AZURE_OPENAI_API_VERSION=2023-05-15
```

## Authentication and Security

### JWT Configuration
```bash
# JWT signing key
JWT_SECRET_KEY=your-secret-key
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=1440
```

### Azure AD Configuration
```bash
# Azure Active Directory
AZURE_CLIENT_ID=client-id
AZURE_CLIENT_SECRET=client-secret
AZURE_TENANT_ID=tenant-id
AZURE_AUTHORITY=https://login.microsoftonline.com/tenant-id
```

### API Keys
```bash
# Lightning API key (for internal service communication)
LIGHTNING_API_KEY=your-api-key

# External service API keys
GITHUB_API_KEY=ghp_...
GOOGLE_API_KEY=key
```

## Logging and Monitoring

### Log Configuration
```bash
# Log level
LOG_LEVEL=DEBUG|INFO|WARNING|ERROR

# Log format
LOG_FORMAT=json|text

# Log file path (if file logging enabled)
LOG_FILE_PATH=/var/log/lightning/app.log
```

### Monitoring Configuration
```bash
# Enable metrics collection
ENABLE_METRICS=true|false

# Metrics port
METRICS_PORT=9090

# Health check endpoint
HEALTH_CHECK_ENDPOINT=/health
```

## Agent Configuration

### Conseil Agent
```bash
# Conseil agent configuration
CONSEIL_AGENT_ENABLED=true|false
CONSEIL_MAX_CONCURRENT_TASKS=5
CONSEIL_RESEARCH_TIMEOUT_SECONDS=300
```

### Voice Agent  
```bash
# Voice agent configuration
VOICE_AGENT_ENABLED=true|false
VOICE_AGENT_PORT=3001
VOICE_STT_PROVIDER=azure|google|openai
VOICE_TTS_PROVIDER=azure|google|openai
```

## Development and Testing

### Development Configuration
```bash
# Enable development mode
DEVELOPMENT_MODE=true|false

# Enable auto-reload
AUTO_RELOAD=true|false

# Enable debug logging
DEBUG=true|false
```

### Testing Configuration
```bash
# Test database URL (separate from production)
TEST_DATABASE_URL=postgres://test:test@localhost:5433/lightning_test

# Test mode
TEST_MODE=true|false

# Mock external services
MOCK_OPENAI=true|false
MOCK_AZURE_SERVICES=true|false
```

## Performance Configuration

### Resource Limits
```bash
# Maximum memory usage (MB)
MAX_MEMORY_MB=2048

# Maximum CPU cores
MAX_CPU_CORES=2

# Connection pool sizes
DATABASE_POOL_SIZE=10
REDIS_POOL_SIZE=20
```

### Caching Configuration
```bash
# Enable caching
ENABLE_CACHING=true|false

# Cache TTL (seconds)
CACHE_TTL_SECONDS=3600

# Cache backend
CACHE_BACKEND=redis|memory
```

## Configuration Files

### Environment Files
```bash
# Load environment from file
ENV_FILE=.env.local|.env.azure|.env.production
```

### YAML Configuration
```yaml
# config/lightning.yml
lightning:
  mode: local
  storage:
    provider: local
    database_url: ${DATABASE_URL}
  event_bus:
    provider: redis
    url: ${REDIS_URL}
  agents:
    conseil:
      enabled: true
      max_tasks: 5
    voice:
      enabled: false
```

### JSON Configuration
```json
{
  "lightning": {
    "mode": "azure",
    "storage": {
      "provider": "cosmos",
      "connection_string": "${COSMOS_CONNECTION_STRING}"
    },
    "event_bus": {
      "provider": "servicebus", 
      "connection_string": "${SERVICE_BUS_CONNECTION_STRING}"
    }
  }
}
```

## Configuration Validation

Lightning validates configuration on startup:

```python
from lightning_core.config import validate_config

# Validate current configuration
errors = validate_config()
if errors:
    print(f"Configuration errors: {errors}")
    exit(1)
```

## Best Practices

### Security
- Never commit secrets to version control
- Use environment variables for sensitive data
- Rotate API keys regularly
- Use least-privilege access principles

### Organization
- Group related configuration variables
- Use consistent naming conventions
- Document all configuration options
- Provide sensible defaults

### Environment Management
- Use separate configurations for dev/staging/prod
- Validate configuration on startup
- Log configuration errors clearly
- Support configuration hot-reloading when possible