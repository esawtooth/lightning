# Lightning Chat - Authentication Gateway

This directory contains the enhanced Lightning Chat client with authentication.

## Architecture

The chat client now consists of two services:

1. **Authentication Gateway** (Port 8000)
   - User registration and login
   - Session management
   - JWT token verification
   - Redirects authenticated users to chat

2. **Chainlit Chat App** (Port 8001)  
   - AI chat interface
   - Protected by authentication middleware
   - Event logging and user context

## Features

### 🔐 Authentication
- User registration with password validation
- Secure login with JWT tokens
- Session management with secure cookies
- Automatic redirection for unauthenticated users

### 💬 Chat Interface
- Beautiful Chainlit-powered chat UI
- User context in conversations
- Event logging with user attribution
- Dashboard integration

### 🎨 Modern UI
- Responsive design
- Professional authentication pages
- Lightning-themed branding
- Error handling and feedback

## Environment Variables

Required:
```bash
AUTH_API_URL=https://your-function-app.azurewebsites.net/api/auth
JWT_SIGNING_KEY=your-secret-signing-key
```

Optional:
```bash
SESSION_SECRET=your-session-secret
CHAINLIT_URL=http://localhost:8001  # For custom chat service URL
EVENT_API_URL=https://your-function-app.azurewebsites.net/api/events
AUTH_TOKEN=your-api-auth-token
```

## Local Development

### Prerequisites
```bash
pip install -r requirements.txt
```

### Quick Start
```bash
# Set environment variables
export AUTH_API_URL="https://your-function-app.azurewebsites.net/api/auth"
export JWT_SIGNING_KEY="your-secret-key"

# Start both services
./start.sh
```

### Testing
```bash
# Run local development tests
python ../test_local_auth.py
```

### Manual Testing
1. Visit http://localhost:8000
2. Register a new account
3. Login with credentials
4. Access chat interface
5. Send test messages

## Docker Deployment

### Build
```bash
docker build -t lightning-chat .
```

### Run
```bash
docker run -p 8000:8000 -p 8001:8001 \
  -e AUTH_API_URL="https://your-function-app.azurewebsites.net/api/auth" \
  -e JWT_SIGNING_KEY="your-secret-key" \
  lightning-chat
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

### Authentication Gateway (Port 8000)
- `GET /` - Login page (redirects if authenticated)
- `POST /login` - User authentication
- `GET /register` - Registration page  
- `POST /register` - User registration
- `GET /chat` - Redirect to chat (requires auth)
- `GET /logout` - User logout
- `GET /health` - Health check

### Chat Service (Port 8001)
- `GET /` - Chainlit chat interface (requires auth)
- `POST /notify` - External message notifications
- `GET /health` - Health check
- `GET /dashboard` - Analytics dashboard

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
   - Verify ports 8000 and 8001 are available
   - Check Python dependencies are installed

2. **Authentication fails**
   - Verify AUTH_API_URL is accessible
   - Check JWT_SIGNING_KEY matches Azure Function
   - Ensure Azure Function is deployed and running

3. **Chat not accessible**
   - Confirm authentication is working
   - Check Chainlit service is running on port 8001
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
