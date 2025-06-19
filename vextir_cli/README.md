# Vextir CLI - Lightning AI Operating System

A comprehensive command-line interface for operating the Lightning AI Operating System. This CLI provides full access to all Lightning Core functionality with seamless switching between local development and cloud production environments (Azure, AWS, GCP).

## Features

### Multi-Environment Support
- **Local Mode**: Development with Docker containers and local storage
- **Azure Mode**: Production deployment with Azure services (Cosmos DB, Service Bus, Container Instances, Functions)
- **AWS Mode**: Production deployment with AWS services (DynamoDB, SQS, ECS, Lambda)
- **GCP Mode**: Production deployment with Google Cloud services (Firestore, Pub/Sub, Cloud Run, Cloud Functions)

### Core Capabilities
- **Event Management**: Emit, list, and stream events with Lightning Core runtime support
- **Driver Control**: Start, stop, and monitor Lightning OS drivers
- **Model Operations**: List and manage AI models across providers
- **Tool Management**: Access and control available tools and bridges
- **Context Hub**: Read, write, and query the persistent context database
- **Runtime Management**: Initialize, test, and switch between execution environments
- **System Monitoring**: Check system status and metrics across all environments
- **Configuration**: Manage CLI settings, authentication, and provider configurations

## Installation

### Prerequisites

- Python 3.8 or higher
- Azure CLI (for authentication)
- Access to a Vextir OS deployment

### Install from Source

```bash
# Clone the repository
git clone https://github.com/vextir/vextir-cli.git
cd vextir-cli

# Install dependencies
pip install -r requirements.txt

# Install the CLI
pip install -e .
```

### Quick Install Script

```bash
# Run the installation script
chmod +x install.sh
./install.sh
```

## Configuration

### Initial Setup

1. **Configure the endpoint**:
   ```bash
   vextir config set endpoint https://api.vextir.com
   ```

2. **Set up authentication** (using Azure CLI):
   ```bash
   az login
   vextir config set auth.method azure_cli
   ```

3. **Verify configuration**:
   ```bash
   vextir config get
   vextir system status
   ```

### Configuration Options

The CLI stores configuration in `~/.vextir/config.json`. Key settings include:

- `endpoint`: Vextir OS API endpoint URL
- `auth.method`: Authentication method (`azure_cli` or `token`)
- `auth.token`: Bearer token (if using token auth)
- `output.format`: Default output format (`table`, `json`)
- `output.colors`: Enable colored output
- `event_streaming.buffer_size`: Event stream buffer size
- `context_hub.default_path`: Default context path

## Usage

### Runtime Management

```bash
# Check current runtime status
vextir runtime status

# Switch between environments
vextir runtime switch local     # Local development
vextir runtime switch azure     # Azure production
vextir runtime switch aws       # AWS production
vextir runtime switch gcp       # GCP production

# Initialize runtime environment
vextir runtime init --mode azure

# Test runtime components
vextir runtime test --component storage
vextir runtime test --component all

# Set provider-specific configuration
vextir config set azure.resource_group "lightning-rg"
vextir config set azure.storage_connection_string "AccountName=..."
vextir config set aws.region "us-west-2"
vextir config set gcp.project_id "my-project"
```

### Event Management

```bash
# Emit an event (legacy client)
vextir event emit user.action --metadata '{"action": "login"}'

# Emit an event (Lightning Core runtime)
vextir event emit user.action --use-runtime --metadata '{"action": "login"}'

# List recent events
vextir event list --limit 20 --type user.action

# Stream events in real-time
vextir event stream --type system.*

# Emit event with metadata from file
vextir event emit task.created --file event_data.json
```

### Driver Management

```bash
# List all drivers
vextir driver list

# Get driver status
vextir driver status email_agent

# Start a driver
vextir driver start email_agent --config '{"enabled": true}'

# Stop a driver
vextir driver stop email_agent

# Filter drivers by type
vextir driver list --type agent --status running
```

### Model Operations

```bash
# List available models
vextir model list

# Get model information
vextir model info gpt-4

# Filter by provider
vextir model list --provider openai

# Filter by capability
vextir model list --capability function_calling
```

### Tool Management

```bash
# List available tools
vextir tool list

# Filter by type
vextir tool list --type mcp_server

# Filter by capability
vextir tool list --capability search
```

### Context Hub Operations

```bash
# Read from context
vextir context read /Projects/Alpha

# Write to context
vextir context write /Tasks/Current "Current task list" --metadata '{"priority": "high"}'

# Query context with SQL
vextir context query "SELECT * FROM context WHERE path LIKE '/Projects/%'" --limit 10
```

### Instruction Management

```bash
# List instructions
vextir instruction list

# Execute an instruction
vextir instruction execute daily_standup

# Filter by status
vextir instruction list --status active
```

### System Monitoring

```bash
# Check system status
vextir system status

# Get detailed metrics
vextir system metrics

# Monitor system health
watch -n 5 vextir system status
```

### Configuration Management

```bash
# View all configuration
vextir config get

# Get specific value
vextir config get endpoint

# Set configuration value
vextir config set output.format json

# Delete configuration key
vextir config delete auth.token

# Reset to defaults
vextir config reset
```

## Output Formats

The CLI supports multiple output formats:

- **table**: Human-readable tables (default)
- **json**: Machine-readable JSON
- **tree**: Hierarchical tree view (for events)

```bash
# Use JSON output
vextir driver list --format json

# Use tree view for events
vextir event list --format tree
```

## Authentication

### Azure CLI Authentication (Recommended)

```bash
# Login to Azure
az login

# Configure CLI to use Azure CLI tokens
vextir config set auth.method azure_cli
```

### Token Authentication

```bash
# Set bearer token directly
vextir config set auth.method token
vextir config set auth.token your_bearer_token_here
```

## Advanced Usage

### Event Streaming with Filters

```bash
# Stream only error events
vextir event stream --type "*.error"

# Stream events from specific source
vextir event stream --source email_agent

# Stream events for specific user
vextir event stream --user-id user123
```

### Batch Operations

```bash
# Start multiple drivers
for driver in email_agent web_search context_manager; do
  vextir driver start $driver
done

# Check status of all drivers
vextir driver list --format json | jq '.[] | {id: .id, status: .status}'
```

### Configuration Profiles

```bash
# Use different config file
vextir --config ~/.vextir/prod-config.json system status

# Override endpoint for single command
vextir --endpoint https://api.vextir.com system status
```

## Troubleshooting

### Common Issues

1. **Authentication Failed**
   ```bash
   # Refresh Azure CLI login
   az login --force
   
   # Verify token
   az account get-access-token
   ```

2. **Connection Errors**
   ```bash
   # Check endpoint configuration
   vextir config get endpoint
   
   # Test connectivity
   curl -I https://your-endpoint.com/api/Health
   ```

3. **Permission Denied**
   ```bash
   # Check Azure CLI account
   az account show
   
   # Verify role assignments in Azure portal
   ```

### Debug Mode

```bash
# Enable verbose output
vextir --verbose system status

# Check configuration
vextir config get
```

### Log Files

The CLI logs to `~/.vextir/logs/` by default. Check these files for detailed error information.

## Development

### Running from Source

```bash
# Install in development mode
pip install -e .

# Run directly
python -m vextir_cli.main --help
```

### Testing

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run tests
pytest tests/
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

MIT License - see LICENSE file for details.

## Support

- Documentation: https://docs.vextir.com/cli
- Issues: https://github.com/vextir/vextir-cli/issues
- Community: https://discord.gg/vextir
