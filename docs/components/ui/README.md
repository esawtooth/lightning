# Lightning UI - Clean Interface for Lightning OS

The new Lightning UI provides a clean, functional interface for the Lightning OS without unnecessary complexity or fake data.

## Features

### 1. **Chat Interface**
- Real-time WebSocket connection for instant messaging
- Direct integration with Lightning's event system
- Chat history maintained per session
- Quick action buttons for common requests

### 2. **Context Hub Viewer**
- Browse and view documents in your knowledge base
- Folder structure navigation
- Real-time document viewing
- Create new documents directly from the UI

### 3. **Event Stream**
- Real-time event monitoring
- Filter by event type (Input, Internal, Output)
- Clear visualization of system activity
- No fake data - shows actual system events

### 4. **Workflow Plans**
- View and manage workflow plans
- Create new plans through the chat interface
- See active and inactive workflows
- Direct configuration access

## Running the Lightning UI

### Quick Start with Docker Compose

```bash
# Start the entire Lightning stack with the new UI
docker-compose -f docker-compose.lightning-ui.yml up -d

# Access the UI at http://localhost:8080
```

### Running Just the UI (for development)

```bash
cd ui/integrated_app
python lightning_ui.py
```

### Environment Variables

- `LIGHTNING_UI=true` - Enable the new Lightning UI in the Docker container
- `API_BASE` - Lightning API endpoint (default: http://localhost:7071/api)
- `CONTEXT_HUB_URL` - Context Hub endpoint (default: http://localhost:3000)

## Key Differences from the Old UI

1. **No Fake Data**: All displayed information is real and comes from the actual system
2. **Focused Features**: Only includes features that are functional and useful
3. **Real-time Updates**: WebSocket connection for live updates
4. **Clean Design**: Simple, intuitive interface without clutter
5. **No Internal Details**: Removes technical details like latency, system services, etc.

## Architecture

The Lightning UI connects to:
- **Lightning API**: For event processing and task management
- **Context Hub**: For document storage and retrieval
- **WebSocket**: For real-time chat and updates

## Chat Commands

You can interact with the AI assistant using natural language. Some examples:

- "Create a new plan for daily email summaries"
- "Show my active tasks"
- "Explain how Lightning works"
- "Process my recent emails"
- "Set up a workflow for calendar events"

## Troubleshooting

### Connection Issues
- Ensure all services are running: `docker-compose -f docker-compose.lightning-ui.yml ps`
- Check logs: `docker-compose -f docker-compose.lightning-ui.yml logs lightning-ui`

### Chat Not Working
- Verify the Lightning API is running on port 7071
- Check WebSocket connection in browser console
- Ensure OPENAI_API_KEY is set in your environment

### Context Hub Empty
- Make sure the Context Hub service is running on port 3000
- Initialize the Context Hub if needed through the API

## Development

To modify the Lightning UI:

1. Edit `ui/integrated_app/lightning_ui.py`
2. Rebuild the Docker image: `docker-compose -f docker-compose.lightning-ui.yml build lightning-ui`
3. Restart the service: `docker-compose -f docker-compose.lightning-ui.yml restart lightning-ui`

The UI is built with:
- FastAPI for the backend
- WebSockets for real-time communication
- Tailwind CSS for styling (via CDN)
- Vanilla JavaScript for interactivity