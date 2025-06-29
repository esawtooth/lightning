# Lightning Voice Agent

AI-powered voice agent integrated with Lightning OS for inbound and outbound calling.

## Features

- **Inbound calling**: Receive calls via Twilio with GPT-4o Realtime API
- **Outbound calling**: Make calls with specific objectives using Python script  
- **Lightning Core integration**: Context Hub search, event generation, web search
- **Local development**: Docker Compose setup with ngrok for webhook testing
- **Azure deployment**: Production-ready cloud deployment

## Quick Start

### Prerequisites

1. **OpenAI API Key**: Required for GPT-4o Realtime API
2. **Twilio Account**: For phone number and calling functionality
3. **Ngrok Account** (for local development): For webhook tunneling

### Local Development Setup

1. **Configure environment variables** in `.env.local`:
```bash
# Required
OPENAI_API_KEY=sk-your-openai-key-here
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_PHONE_NUMBER=+1234567890

# Optional for ngrok
NGROK_AUTHTOKEN=your_ngrok_token
```

2. **Start the voice agent stack**:
```bash
# Start full voice agent with Lightning Core
docker compose --profile voice-agent up

# Or start with ngrok tunnel for webhook testing
docker compose --profile voice-agent --profile ngrok up
```

3. **Configure Twilio webhook** (if using ngrok):
   - Get ngrok tunnel URL from container logs
   - Set Twilio webhook URL to: `https://your-ngrok-url.ngrok.io/twiml`

### Making Outbound Calls

Use the Python outbound agent script:

```bash
# Basic outbound call
docker compose exec voice-agent-outbound python outbound_agent.py \
  --phone "+1234567890" \
  --objective "Call to check on project status"

# Call with context search
docker compose exec voice-agent-outbound python outbound_agent.py \
  --phone "+1234567890" \
  --objective "Schedule a meeting for next week" \
  --search-queries "meeting schedules" "calendar availability" \
  --user-id "123"

# Call with custom context
docker compose exec voice-agent-outbound python outbound_agent.py \
  --phone "+1234567890" \
  --objective "Follow up on contract discussion" \
  --context '{"project_id": "abc123", "priority": "high"}'
```

## Architecture

### Inbound Call Flow
1. **Twilio** receives call → webhook to voice agent
2. **Voice Agent Server** establishes WebSocket connections:
   - Twilio ↔ Voice Agent ↔ OpenAI Realtime API
3. **Lightning Core Integration**:
   - Context Hub search via `/search` endpoint
   - Event generation via `/events` endpoint  
   - Web search via `/tools/execute` endpoint
4. **Call logging** and event publishing through Lightning Core

### Outbound Call Flow  
1. **Python script** with objective and context
2. **Context gathering** from Context Hub and user data
3. **Call initiation** through Twilio API
4. **Real-time conversation** with Lightning Core tool access
5. **Event publishing** for follow-up actions

### Available Tools During Calls

- **`user_search`**: Search your knowledge base/Context Hub
- **`web_search`**: Search the web for current information  
- **`generate_event`**: Create events in Lightning OS for follow-ups
- **`dial_digits`**: Send DTMF digits for IVR navigation

## Services

### Docker Compose Services

- **`voice-agent-server`**: Node.js WebSocket server handling Twilio ↔ OpenAI
- **`voice-agent-frontend`**: Next.js monitoring interface (port 3001)
- **`voice-agent-outbound`**: Python container for outbound calling
- **`ngrok`**: Automatic tunnel setup for local webhook testing

### Service Profiles

```bash
# Start basic voice agent (inbound only)
docker compose --profile voice-agent up

# Start with ngrok tunnel
docker compose --profile voice-agent --profile ngrok up  

# Start outbound calling container
docker compose --profile voice-agent-outbound up

# Start everything
docker compose --profile all up
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `VOICE_AGENT_PORT` | WebSocket server port | 8081 |
| `VOICE_AGENT_FRONTEND_PORT` | Frontend port | 3001 |
| `VOICE_AGENT_OBJECTIVE` | Default call objective | "I am your AI assistant..." |
| `TWILIO_ACCOUNT_SID` | Twilio account SID | Required |
| `TWILIO_AUTH_TOKEN` | Twilio auth token | Required |
| `TWILIO_PHONE_NUMBER` | Your Twilio phone number | Required |
| `NGROK_AUTHTOKEN` | Ngrok authentication token | Optional |

### Lightning Core Integration

The voice agent automatically inherits Lightning Core configuration:
- **Storage**: Uses Lightning Core storage abstractions (local/Azure)
- **Events**: Publishes to Lightning Core event bus (Redis/Service Bus)  
- **Tools**: Accesses Lightning Core tool registry and MCP providers

## Development

### File Structure

```
agents/voice-agent/
├── websocket-server/          # Node.js WebSocket server
│   ├── src/
│   │   ├── server.ts         # Main server with Lightning integration
│   │   ├── functionHandlers.ts # Tool functions (search, events, etc.)
│   │   └── sessionManager.ts   # Call session management
│   └── Dockerfile
├── webapp/                    # Next.js monitoring frontend  
│   ├── app/
│   ├── components/
│   └── Dockerfile
├── outbound_agent.py         # Python outbound calling script
└── README.md
```

### Adding New Tools

1. **Add to functionHandlers.ts**:
```typescript
functions.push({
  schema: {
    name: "my_tool",
    description: "Tool description",
    parameters: { /* schema */ }
  },
  handler: async (args) => {
    // Use Lightning Core APIs
    const result = await callLightningAPI('/some/endpoint', {...});
    return JSON.stringify(result);
  }
});
```

2. **Register in Lightning Core** tool registry if needed

### Debugging

- **Server logs**: `docker compose logs voice-agent-server`
- **Frontend**: http://localhost:3001 (call monitoring interface)
- **Health check**: http://localhost:8081/health
- **Ngrok tunnel**: Check container logs for public URL

## Deployment

### Azure Production

The voice agent integrates with Lightning's Azure deployment:
- **Voice Agent Server**: Azure Container Instance or App Service
- **Webhook URL**: Azure Front Door with custom domain
- **Storage**: Azure Cosmos DB via Lightning Core  
- **Events**: Azure Service Bus via Lightning Core
- **Tools**: Azure-hosted Lightning Core tool registry

Configuration automatically switches based on `LIGHTNING_MODE=azure`.

## Troubleshooting

### Common Issues

1. **"No OpenAI API Key"**: Set `OPENAI_API_KEY` in environment
2. **"Twilio webhook timeout"**: Check ngrok tunnel is running and accessible
3. **"Context Hub search failed"**: Verify Lightning Core services are running
4. **"Tool execution failed"**: Check Lightning Core tool registry is accessible

### Logs and Monitoring

- Voice agent publishes events to Lightning Core event system
- Call transcripts stored via Lightning Core storage
- Health checks available at `/health` endpoint
- Frontend provides real-time call monitoring

## Examples

### Example Objectives

- "Call and confirm the meeting for tomorrow at 2 PM"
- "Check on the status of project XYZ and get an update"  
- "Schedule a follow-up call for next week"
- "Remind about the upcoming deadline and ask if help is needed"
- "Conduct a brief customer satisfaction survey"

### Example Context

```json
{
  "user_id": "user_123",
  "project_id": "proj_456", 
  "priority": "high",
  "search_queries": ["project status", "recent updates"],
  "previous_interactions": ["email_2024_01_15", "call_2024_01_10"]
}
```