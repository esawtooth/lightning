# Vextir Integrated Dashboard

A unified web interface that combines the dashboard and chat functionality into a single, cohesive application with a left navigation sidebar.

## Features

### 🏠 Dashboard
- Real-time analytics and metrics
- Task status overview
- System health monitoring
- Quick actions for creating new tasks
- Activity feed with recent task updates

### 💬 Chat Interface
- Integrated AI chat assistant
- Real-time messaging interface
- Quick action buttons for common queries
- Chat history management
- Seamless integration with the task system

### 📋 Task Management
- Comprehensive task listing with filtering and sorting
- Detailed task views with metadata and logs
- Task status tracking and monitoring
- Export functionality for task data
- Real-time updates and notifications

### 🔔 Notifications
- Centralized notification management
- Filter by type and status
- Mark as read/unread functionality
- Detailed notification views
- Integration with task system

### 🎨 UI/UX Features
- **Collapsible Left Sidebar**: Clean navigation with expandable/collapsible sidebar
- **Responsive Design**: Works on desktop, tablet, and mobile devices
- **Real-time Updates**: Auto-refresh functionality for live data
- **Modern Interface**: Built with Tailwind CSS and Font Awesome icons
- **Consistent Branding**: Unified Vextir branding throughout the application

## Architecture

### Backend (FastAPI)
- **Authentication**: JWT-based authentication with session management
- **API Integration**: Connects to existing Azure Functions backend
- **Middleware**: Authentication middleware for protected routes
- **Templates**: Jinja2 templating for server-side rendering

### Frontend
- **Framework**: Vanilla JavaScript with modern ES6+ features
- **Styling**: Tailwind CSS for responsive design
- **Icons**: Font Awesome for consistent iconography
- **Interactions**: Real-time updates and smooth transitions

### Integration Points
- **Auth Gateway**: Integrates with existing authentication system
- **Azure Functions**: Connects to backend API endpoints
- **Chainlit**: Prepared for integration with chat backend
- **Task System**: Full integration with task management APIs

## Quick Start

### Prerequisites
- Python 3.8+
- Node.js (for development tools, optional)

### Installation & Setup

1. **Navigate to the integrated app directory:**
   ```bash
   cd ui/integrated_app
   ```

2. **Run the startup script:**
   ```bash
   ./start.sh
   ```

   This will:
   - Create a virtual environment
   - Install all dependencies
   - Set up environment variables
   - Start the development server

3. **Access the application:**
   - Main Dashboard: http://localhost:8002/
   - Chat Interface: http://localhost:8002/chat
   - Task Management: http://localhost:8002/tasks
   - Notifications: http://localhost:8002/notifications

### Manual Setup

If you prefer manual setup:

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export API_BASE="http://localhost:7071/api"
export AUTH_GATEWAY_URL="http://localhost:8001"
export CHAINLIT_URL="http://localhost:8000"
export SESSION_SECRET="your-secret-key"

# Start the server
uvicorn app:app --host 0.0.0.0 --port 8002 --reload
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `API_BASE` | `http://localhost:7071/api` | Backend API base URL |
| `AUTH_GATEWAY_URL` | `http://localhost:8001` | Authentication gateway URL |
| `CHAINLIT_URL` | `http://localhost:8000` | Chainlit chat service URL |
| `SESSION_SECRET` | `your-secret-key-change-in-production` | Session encryption key |
| `AUTH_TOKEN` | None | Optional API authentication token |

### Customization

#### Branding
- Update `static/vextir-logo.svg` for custom logo
- Modify color scheme in `templates/base.html`
- Customize navigation items in the sidebar

#### API Integration
- Update API endpoints in `app.py`
- Modify authentication logic as needed
- Add new API routes for additional functionality

## Development

### Project Structure
```
ui/integrated_app/
├── app.py                 # Main FastAPI application
├── requirements.txt       # Python dependencies
├── start.sh              # Startup script
├── README.md             # This file
├── static/               # Static assets
│   └── vextir-logo.svg   # Application logo
└── templates/            # Jinja2 templates
    ├── base.html         # Base template with sidebar
    ├── dashboard.html    # Dashboard page
    ├── chat.html         # Chat interface
    ├── tasks.html        # Task management
    └── notifications.html # Notifications page
```

### Key Components

#### Navigation Sidebar (`templates/base.html`)
- Collapsible sidebar with smooth animations
- User information display
- Active page highlighting
- Responsive design for mobile devices

#### Dashboard (`templates/dashboard.html`)
- Analytics cards with real-time data
- Activity feed with recent tasks
- Quick action buttons
- System status monitoring

#### Chat Interface (`templates/chat.html`)
- Modern chat UI with message bubbles
- Auto-resizing text input
- Quick action buttons for common queries
- Real-time message handling (ready for WebSocket integration)

#### Task Management (`templates/tasks.html`)
- Comprehensive task table with filtering
- Detailed task modals
- Export functionality
- Real-time status updates

#### Notifications (`templates/notifications.html`)
- Notification feed with filtering
- Mark as read/unread functionality
- Detailed notification views
- Integration with task system

### Adding New Features

1. **New Pages**: Create new templates and add routes in `app.py`
2. **API Endpoints**: Add new FastAPI routes for backend integration
3. **Navigation**: Update the sidebar in `templates/base.html`
4. **Styling**: Use Tailwind CSS classes for consistent styling

## Integration with Existing Systems

### Authentication
The integrated app works with the existing authentication system:
- Redirects unauthenticated users to the auth gateway
- Validates JWT tokens from cookies
- Maintains session state across page navigation

### Backend APIs
Connects to existing Azure Functions:
- Task management endpoints
- Event creation and monitoring
- Analytics and reporting
- Notification system

### Chat System
Prepared for integration with Chainlit:
- Chat interface ready for WebSocket connections
- Message queuing through existing event system
- Real-time response handling

## Deployment

### Development
Use the provided `start.sh` script for local development with hot reload.

### Production
1. Set appropriate environment variables
2. Use a production WSGI server like Gunicorn:
   ```bash
   gunicorn app:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8002
   ```
3. Configure reverse proxy (nginx) for static file serving
4. Set up SSL/TLS certificates for HTTPS

### Docker (Optional)
Create a Dockerfile for containerized deployment:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8002
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8002"]
```

## Troubleshooting

### Common Issues

1. **Authentication Errors**
   - Check `AUTH_GATEWAY_URL` configuration
   - Verify JWT token format and expiration
   - Ensure session secret is consistent

2. **API Connection Issues**
   - Verify `API_BASE` URL is correct
   - Check if backend services are running
   - Review CORS settings if needed

3. **Static Files Not Loading**
   - Ensure `static/` directory exists
   - Check file permissions
   - Verify logo file is present

### Logs and Debugging
- Enable FastAPI debug mode for detailed error messages
- Check browser console for JavaScript errors
- Monitor network requests in browser dev tools

## Contributing

1. Follow the existing code structure and naming conventions
2. Add appropriate error handling and logging
3. Update documentation for new features
4. Test across different browsers and screen sizes
5. Ensure responsive design principles are maintained

## License

This project is part of the Vextir platform. See the main project LICENSE file for details.
