# Vextir Chat - Authentication Gateway

This directory contains the Vextir Chat client secured with Azure Entra ID.

## Architecture

The chat client exposes a gateway service on port 443 that handles the OAuth
flow with Azure Entra ID and proxies the Chainlit interface.

## Features

### 🔐 Authentication
Users authenticate using the Microsoft identity platform. The gateway performs
the OAuth redirect, validates the returned token and stores it in a secure
cookie.

### 💬 Chat Interface
- Beautiful Chainlit-powered chat UI
- User context in conversations
- Event logging with user attribution
- Dashboard integration

### 🎨 Modern UI
- Responsive design
- Professional authentication pages
- Vextir-themed branding
- Error handling and feedback

## Environment Variables

Required environment variables:
```bash
AAD_CLIENT_ID=<app-id>
AAD_TENANT_ID=<tenant-id>
AAD_CLIENT_SECRET=<client-secret>
```

Optional:
```bash
SESSION_SECRET=your-session-secret
CHAINLIT_URL=https://localhost/chat  # For custom gateway URL
EVENT_API_URL=https://your-function-app.azurewebsites.net/api/events
AUTH_TOKEN=your-api-auth-token
GITEA_URL=https://your-gitea-instance
```

## Local Development

### Prerequisites
```bash
pip install -r requirements.txt
```

### Quick Start
```bash
# Set environment variables
export AAD_CLIENT_ID="<app-id>"
export AAD_TENANT_ID="<tenant-id>"
export AAD_CLIENT_SECRET="<client-secret>"

# Start the gateway and chat services
./start.sh
```

### Testing
```bash
# Run local development tests
pytest ..
```

### Manual Testing
1. Visit https://localhost/auth/login
2. Authenticate with your Microsoft account
3. Access the chat interface
4. Send test messages

## Docker Deployment

### Build
```bash
docker build -t vextir-chat .
```

### Run
```bash
docker run -p 443:443 \
  -e AAD_CLIENT_ID="<app-id>" \
  -e AAD_TENANT_ID="<tenant-id>" \
  -e AAD_CLIENT_SECRET="<client-secret>" \
  vextir-chat
```

## File Structure

```
chat_client/
├── auth_app.py           # Authentication gateway FastAPI app
├── chainlit_app.py       # Chainlit chat application
├── start.sh              # Multi-service startup script
├── requirements.txt      # Python dependencies
├── Dockerfile           # Container configuration
└── templates/
    ├── login.html       # Login page
    └── register.html    # Registration page
```

## API Endpoints

### Authentication Gateway (`/auth`)
- `GET /auth/` - Login page (redirects if authenticated)
- `POST /auth/login` - User authentication
- `GET /auth/register` - Registration page
- `POST /auth/register` - User registration
- `GET /auth/chat` - Redirect to chat (requires auth)
- `GET /auth/logout` - User logout
- `GET /auth/health` - Health check

### Chat Service (`/chat`)
- `GET /chat/` - Chainlit chat interface (requires auth)
- `POST /chat/notify` - External message notifications
- `GET /chat/health` - Health check
- `GET /chat/dashboard` - Analytics dashboard
- `GET /repo` - Redirect to the user's Gitea repository

## Security Features

- JWT token-based authentication
- Secure HTTP-only cookies
- Session management
- Password validation
- CSRF protection
- Input sanitization
- Secure redirects

## Integration with Azure Functions

The authentication gateway integrates with your Azure Function endpoints:

- `POST /api/auth/register` - User registration
- `POST /api/auth/login` - User authentication

Make sure your Azure Function has the UserAuth function deployed and configured.

## Troubleshooting

### Common Issues

1. **Services won't start**
   - Check environment variables are set
   - Verify port 443 is available
   - Check Python dependencies are installed

2. **Authentication fails**
   - Verify the Entra ID application configuration
   - Ensure environment variables are set correctly

3. **Chat not accessible**
   - Confirm authentication is working
   - Check the gateway service is running on port 443
   - Verify authentication middleware is working

### Logs
Both services output logs to stdout. Check for:
- Authentication errors
- Network connectivity issues
- JWT token validation problems
- Service startup failures

## Development Notes

- The authentication gateway uses FastAPI for flexibility
- Chainlit handles the chat interface and WebSocket connections
- Session state is managed separately from JWT tokens
- The startup script coordinates both services
- Docker exposes both ports for load balancer configuration
