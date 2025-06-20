# Vextir Chat - Enhanced Authentication & Authorization System

## Overview

The Vextir Chat UI container has been enhanced with a comprehensive authentication and authorization system. Users must authenticate before accessing chat, and only admin-approved users can access the system after registration. Registration places users on a waitlist pending admin approval.

## Architecture

-### Multi-Service Design
- **Gateway** (Port 443): Routes `/auth` to the auth service and `/chat` to the chat interface
- **Azure Functions**: Backend API for user management and authentication

### Authorization Flow
1. User registers → Placed on waitlist
2. Admin reviews and approves/rejects users
3. Approved users can login and access chat
4. Rejected users are blocked from access

## Components

### 1. Enhanced Azure Function (`/azure-function/UserAuth/__init__.py`)
- **Registration**: Places users on waitlist by default
- **Login**: Checks approval status before granting access
- **Admin Functions**: User approval/rejection, user listing
- **JWT Tokens**: Include role and status claims
- **Database Schema**: Added status, role, email, timestamps

### 2. Authentication Gateway (`/chat_client/auth_app.py`)
- **FastAPI Service**: Mounted under `/auth`
- **JWT Verification**: Secure token handling
- **Session Management**: HTTP-only cookies
- **Admin Panel**: User management interface
- **API Endpoints**: RESTful admin APIs

### 3. Integrated Dashboard (`/integrated_app/app.py`)
- **Auth Middleware**: Protects all routes
- **User Context**: Passed to the dashboard and chat views
- **Health Checks**: Service monitoring

### 4. Professional UI Templates
- **Login Page** (`templates/login.html`): Vextir-branded with status messaging
- **Registration Page** (`templates/register.html`): Email field and waitlist info
- **Admin Panel** (`templates/admin.html`): Full-featured user management interface

### 5. Infrastructure
- **Multi-Service Startup** (`start.sh`): Orchestrates both services
- **Docker Support** (`Dockerfile`): Container for dual services
- **Dependencies** (`requirements.txt`): All needed packages

## Setup Instructions

### 1. Environment Variables
```bash
# Required for Azure Functions
export COSMOS_URL="https://your-cosmos-account.documents.azure.com:443/"
export COSMOS_KEY="your-cosmos-primary-key"
export COSMOS_DATABASE="vextir"
export COSMOS_CONTAINER="users"
export JWT_SIGNING_KEY="your-jwt-signing-key"

# Required for Chat Client
export AUTH_API_URL="https://your-function-app.azurewebsites.net/api"
export CHAINLIT_URL="https://localhost/chat"  # In Docker: https://gateway/chat
```

### 2. Deploy Azure Functions
```bash
cd azure-function
func azure functionapp publish your-function-app-name
```

### 3. Build and Run Chat Client
```bash
cd chat_client

# Local development
pip install -r requirements.txt
chmod +x start.sh
./start.sh

# Docker deployment
docker build -t vextir-chat .
docker run -p 443:443 \
  -e AUTH_API_URL="https://your-function-app.azurewebsites.net/api" \
  -e JWT_SIGNING_KEY="your-jwt-signing-key" \
  vextir-chat
```

### 4. Create First Admin User
```bash
# Set environment variables for Cosmos DB
export COSMOS_URL="https://your-cosmos-account.documents.azure.com:443/"
export COSMOS_KEY="your-cosmos-primary-key"

# Run admin creation script
python create_admin_user.py
```

## Testing

### Comprehensive Flow Test
```bash
# Start services first
cd chat_client && ./start.sh

# Run comprehensive test in another terminal
python test_auth_flow.py
```

### Manual Testing Steps
1. **Registration**: Visit https://localhost/auth/register
2. **Waitlist Check**: Try logging in (should be blocked)
3. **Admin Login**: Use admin credentials at https://localhost/auth/admin
4. **User Approval**: Approve pending users in admin panel
5. **User Access**: Approved users can now access chat

## API Endpoints

### Public Endpoints
- `POST /register` - User registration
- `POST /login` - User login
- `GET /` - Login page
- `GET /logout` - User logout

### Protected Endpoints
- `GET /chat` - Redirect to chat (authenticated users)
- `GET /admin` - Admin panel (admin users only)

### Admin API Endpoints
- `GET /admin/api/users` - Get all users with stats
- `POST /admin/api/user-action` - Approve/reject users

### Azure Function Endpoints
- `POST /api/register` - User registration
- `POST /api/login` - User authentication
- `GET /api/pending` - List all users (admin only)
- `POST /api/approve` - Approve/reject user (admin only)
- `GET /api/status` - Get user status

## Database Schema

### User Entity
```json
{
  "id": "user",
  "pk": "username",
  "hash": "password_hash",
  "salt": "random_salt",
  "email": "user@example.com",
  "role": "user|admin",
  "status": "waitlist|approved|rejected",
  "created_at": "2025-06-01T12:00:00Z",
  "approved_at": "2025-06-01T12:30:00Z",
  "approved_by": "admin_username"
}
```

## Security Features

### Authentication
- **Password Hashing**: SHA-256 with random salt
- **JWT Tokens**: 1-hour expiration with role/status claims
- **Session Management**: Secure HTTP-only cookies
- **Token Verification**: Middleware protection

### Authorization
- **Role-Based Access**: User vs Admin permissions
- **Status Checks**: Waitlist/approved/rejected validation
- **Admin Verification**: Token-based admin endpoint protection

### Input Validation
- **Password Requirements**: Minimum 8 characters with letters and numbers
- **Email Validation**: Optional but validated if provided
- **CSRF Protection**: Session-based request validation
- **Rate Limiting**: Basic per-IP throttling

## Monitoring & Logging

### Health Checks
- `/health` endpoints on both services
- Service availability monitoring
- Database connection validation

### Logging
- User registration/login events
- Admin actions (approval/rejection)
- Authentication failures
- Service errors

## Error Handling

### User-Friendly Messages
- **Account Pending**: Clear waitlist messaging
- **Account Rejected**: Admin contact information
- **Service Errors**: Graceful degradation
- **Network Issues**: Retry guidance

### Admin Notifications
- **Real-time Stats**: Pending user counts
- **Action Confirmations**: Success/failure feedback
- **Error Reporting**: Detailed error messages

## File Structure

```
/Users/rohit/src/vextir/
├── azure-function/
│   └── UserAuth/
│       ├── __init__.py          # Enhanced auth functions
│       └── function.json        # Function configuration
├── chat_client/
│   ├── auth_app.py              # Authentication gateway
│   ├── gateway_app.py           # Mounts auth and integrated UI
│   ├── start.sh                 # Multi-service startup
│   ├── Dockerfile               # Container definition
│   ├── requirements.txt         # Dependencies
│   └── templates/
│       ├── login.html           # Login interface
│       ├── register.html        # Registration interface
│       └── admin.html           # Admin panel
├── integrated_app/
│   ├── app.py                   # Integrated dashboard
│   └── templates/               # UI pages
├── create_admin_user.py         # Admin user creation tool
├── test_auth_flow.py            # Comprehensive testing
└── test_local_auth.py           # Local development testing
```

## Next Steps

### Production Deployment
1. **HTTPS Configuration**: Enable SSL/TLS
2. **Environment Secrets**: Use Azure Key Vault
3. **Load Balancing**: Multiple service instances
4. **Monitoring**: Application Insights integration

### Feature Enhancements
1. **Email Notifications**: User approval status updates
2. **Password Reset**: Self-service password recovery
3. **User Profiles**: Extended user information
4. **Audit Logging**: Detailed admin action tracking

### Performance Optimization
1. **Caching**: Redis for session storage
2. **Database Indexing**: Optimized queries
3. **CDN Integration**: Static asset delivery
4. **Connection Pooling**: Database performance

## Troubleshooting

### Common Issues

#### "Service Unavailable" Error
- Check Azure Function deployment status
- Verify environment variables are set
- Test Function App URL directly

#### "Admin Required" Error
- Ensure user role is set to "admin" in database
- Verify JWT token contains correct role claim
- Check admin user creation script execution

#### "Authentication Failed" Error
- Verify AUTH_API_URL is correct
- Check JWT_SIGNING_KEY matches between services
- Ensure Azure Function is responding

#### Users Stuck on Waitlist
- Verify admin user has correct permissions
- Check approval API is working
- Ensure database updates are successful

### Debug Commands

```bash
# Check service health
curl https://localhost/auth/health
curl https://localhost/chat/health

# Test Azure Function
curl -X POST "https://your-function-app.azurewebsites.net/api/register" \
  -H "Content-Type: application/json" \
  -d '{"username":"test","password":"test123"}'

# View Docker logs
docker logs container-name

# Check environment variables
env | grep -E "(AUTH_API_URL|JWT_SIGNING_KEY|COSMOS_)"
```

This completes the comprehensive authentication and authorization enhancement for Vextir Chat. The system now provides secure, admin-controlled access with a professional user interface and robust backend infrastructure.
