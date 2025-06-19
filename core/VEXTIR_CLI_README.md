# Vextir OS - Unified CLI

The single command-line interface for the entire Vextir OS event-driven AI system.

## Quick Start

```bash
# Show all available commands
python vextir.py --help

# Check system status
python vextir.py status

# Start interactive chat
python vextir.py chat

# Send a single event
python vextir.py send -t llm.chat -d '{"messages":[{"role":"user","content":"Hello"}]}' --wait

# Monitor all system events
python vextir.py monitor
```

## Commands

### `chat` - Interactive Chat
Start a conversational session with the AI through the event-driven architecture.

```bash
python vextir.py chat
python vextir.py chat --model gpt-4
python vextir.py chat --temperature 0.8 --verbose
```

Options:
- `--model`: Specify the model (default: gpt-3.5-turbo)
- `--temperature`: Set creativity level (default: 0.7)

### `send` - Send Events
Send individual events to the system.

```bash
# Send and wait for response
python vextir.py send -t llm.chat -d '{"messages":[{"role":"user","content":"Hi"}]}' --wait

# Send event without waiting
python vextir.py send -t system.health

# Send with custom timeout
python vextir.py send -t custom.event -d '{"data":"value"}' --wait --timeout 20
```

Options:
- `-t, --type`: Event type (required)
- `-d, --data`: Event data as JSON string
- `--wait`: Wait for response
- `--timeout`: Response timeout in seconds (default: 10)

### `monitor` - Event Monitoring
Watch events flowing through the system in real-time.

```bash
# Monitor all events
python vextir.py monitor

# Filter by event type
python vextir.py monitor --filter llm

# Verbose monitoring with full event details
python vextir.py monitor --verbose
```

Options:
- `--filter`: Filter events by type substring
- `--verbose`: Show detailed event information

### `status` - System Status
Check the health and status of Vextir OS components.

```bash
python vextir.py status
python vextir.py status --verbose
```

## Configuration

The CLI uses environment variables from `.env`:
- `OPENAI_API_KEY`: Your OpenAI API key
- `OPENAI_MODEL`: Default model to use

## Architecture

The CLI demonstrates the event-driven architecture:

1. **Chat Command**: Creates `llm.chat` events, publishes to event bus
2. **Event Bus**: Routes events to appropriate processors
3. **Universal Processor**: Handles events through driver system
4. **Chat Driver**: Processes chat events via OpenAI API
5. **Response Events**: Published back through event bus to CLI

This architecture allows for:
- Complete decoupling of components
- Scalable event processing
- Easy addition of new event types and processors
- Cloud deployment readiness

## Examples

```bash
# Quick chat session
python vextir.py chat

# System health check
python vextir.py status

# Watch events in real-time
python vextir.py monitor --filter chat

# Send a custom event
python vextir.py send -t custom.event -d '{"message":"Hello World"}' --wait
```

The CLI provides a complete interface to the Vextir OS event-driven AI system!