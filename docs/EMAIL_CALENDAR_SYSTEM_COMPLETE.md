# Email & Calendar Integration System - Complete Implementation

## Overview

This document describes the complete email and calendar integration system that enables users to:

1. **Gather events** from email and calendar across iCloud, Outlook, Gmail, etc.
2. **Set calendar events** and send invites
3. **Send emails** or respond to emails
4. **Process events** through a service bus with intelligent instruction handling
5. **Remove unprocessed events** automatically if no instructions match
6. **Handle complex tasks** with dynamically created instruction handlers powered by Conseil AI

## System Architecture

### Core Components

1. **EmailCalendarConnector** - Azure Function for provider integration
2. **InstructionManager** - Manages user-defined processing instructions
3. **InstructionProcessor** - Processes events against user instructions
4. **ContextSynthesizer** - Updates context based on events
5. **Service Bus** - Event routing and processing pipeline
6. **Conseil AI Integration** - Advanced AI-powered event processing

### Event Flow

```
Email/Calendar Provider → EmailCalendarConnector → Service Bus → InstructionProcessor → Action Execution
                                                                      ↓
                                                              No Instructions = Discard Event
                                                                      ↓
                                                              Instructions Match = Execute Actions:
                                                              - Fast Actions (Context, Email, Notification)
                                                              - AI Actions (Conseil Worker Tasks)
```

## Key Features

### 1. Multi-Provider Support

**Supported Providers:**
- Gmail (Google Workspace)
- Outlook (Microsoft 365)
- iCloud (Apple)

**Capabilities:**
- Receive email/calendar webhooks
- Send emails via provider APIs
- Create/update/delete calendar events
- OAuth authentication flows

### 2. Intelligent Instruction System

**Instruction Types:**

#### Fast Actions (Immediate Processing)
- **Update Context Summary**: Synthesize event data into context hub
- **Send Email**: Send notification emails
- **Send Notification**: Create system notifications
- **Create Task**: Generate simple worker tasks

#### AI-Powered Actions (Conseil Integration)
- **Conseil Task**: Spawn AI worker with full context and reasoning capabilities

**Trigger Conditions:**
- Event type matching (email.received, calendar.created, etc.)
- Provider filtering (gmail, outlook, icloud)
- Content-based filters (subject contains, sender filters)
- Time-based conditions (business hours, etc.)

### 3. Conseil AI Integration

**Capabilities:**
- Full event context analysis
- Complex reasoning and decision making
- Context hub read/write operations
- Service bus event creation
- System command execution
- Fallback action handling

**Configuration Options:**
- **Complexity Levels**: Simple, Complex, Advanced
- **Custom Prompts**: Detailed task descriptions
- **Fallback Actions**: Error handling strategies

### 4. Context Hub Integration

**Features:**
- Automatic context synthesis from events
- User-defined context keys
- Event history tracking
- Searchable context storage

## Implementation Details

### Azure Functions

#### EmailCalendarConnector
- **Triggers**: HTTP (webhooks/API) + Service Bus (outbound events)
- **Purpose**: Provider integration and event translation
- **Endpoints**:
  - `POST /api/connector/webhook/{provider}` - Receive webhooks
  - `POST /api/connector/auth/{provider}` - OAuth flows
  - Service Bus: Handle outbound email/calendar operations

#### InstructionManager
- **Triggers**: HTTP
- **Purpose**: CRUD operations for user instructions
- **Endpoints**:
  - `GET /api/instructions` - List instructions
  - `POST /api/instructions` - Create instruction
  - `PUT /api/instructions/{id}` - Update instruction
  - `DELETE /api/instructions/{id}` - Delete instruction
  - `PATCH /api/instructions/{id}/toggle` - Enable/disable

#### InstructionProcessor
- **Triggers**: Service Bus
- **Purpose**: Process events against user instructions
- **Logic**:
  1. Receive event from service bus
  2. Load user instructions from Cosmos DB
  3. Match event against instruction triggers
  4. Execute matching instruction actions
  5. Discard event if no instructions match

#### ContextSynthesizer
- **Triggers**: Service Bus
- **Purpose**: Update context hub based on events
- **Features**:
  - Event content extraction
  - Context synthesis with AI
  - History tracking

### Event Types

```python
# Email Events
EmailEvent(
    type="email.received|email.sent",
    provider="gmail|outlook|icloud",
    operation="received|sent",
    email_data={
        "id": "message_id",
        "from": "sender@example.com",
        "to": ["recipient@example.com"],
        "subject": "Email subject",
        "body": "Email content",
        "timestamp": "2024-01-01T00:00:00Z"
    }
)

# Calendar Events
CalendarEvent(
    type="calendar.received|calendar.created|calendar.updated",
    provider="gmail|outlook|icloud",
    operation="received|created|updated|deleted",
    calendar_data={
        "id": "event_id",
        "title": "Meeting title",
        "description": "Meeting description",
        "start_time": "2024-01-01T10:00:00Z",
        "end_time": "2024-01-01T11:00:00Z",
        "attendees": ["attendee@example.com"],
        "location": "Conference Room A"
    }
)
```

### Instruction Configuration

```json
{
    "name": "Project Email Processor",
    "description": "Process project-related emails with AI analysis",
    "enabled": true,
    "trigger": {
        "event_type": "email.received",
        "providers": ["gmail", "outlook"],
        "conditions": {
            "content_filters": {
                "subject_contains": ["project", "deadline", "milestone"]
            },
            "time_range": {
                "start_hour": 9,
                "end_hour": 17
            }
        }
    },
    "action": {
        "type": "conseil_task",
        "config": {
            "prompt": "Analyze this project email and extract action items. Update project context and create tasks for any deadlines. Send me a summary if urgent.",
            "complexity": "complex",
            "fallback_action": "send_notification"
        }
    }
}
```

## User Interface

### Dashboard Features

1. **Instructions Management**
   - Create/edit/delete instructions
   - Enable/disable instructions
   - View execution statistics
   - Real-time status monitoring

2. **Event Monitoring**
   - Live event stream
   - Event history and filtering
   - Processing status tracking
   - Error monitoring

3. **Provider Management**
   - OAuth connection status
   - Provider configuration
   - Connection testing
   - Webhook management

4. **Context Visualization**
   - Context hub browser
   - Search and filtering
   - Context history
   - Synthesis monitoring

## Example Use Cases

### 1. Email Summary Generation
```
Trigger: All emails received
Action: Update context summary with key information
Result: Maintain running summary of all communications
```

### 2. Meeting Scheduler
```
Trigger: Emails containing "schedule meeting"
Action: Conseil AI analyzes email and creates calendar event
Result: Automatic meeting scheduling with attendee invites
```

### 3. Project Management
```
Trigger: Project-related emails
Action: Conseil AI extracts action items and deadlines
Result: Automatic task creation and project status updates
```

### 4. Urgent Email Alerts
```
Trigger: Emails with "urgent" in subject
Action: Send immediate notification + create high-priority task
Result: Real-time urgent email handling
```

## Security & Privacy

### Authentication
- OAuth 2.0 for provider access
- JWT tokens for API authentication
- User-scoped data isolation

### Data Protection
- Encrypted storage in Cosmos DB
- Secure webhook endpoints
- Provider token encryption
- GDPR compliance ready

### Access Control
- User-based instruction isolation
- Provider permission scoping
- API rate limiting
- Audit logging

## Deployment

### Azure Resources Required
- Azure Functions (Premium plan recommended)
- Azure Service Bus (Standard tier)
- Azure Cosmos DB (serverless or provisioned)
- Azure Storage Account
- Azure Key Vault (for secrets)

### Environment Variables
```
COSMOS_CONNECTION=<cosmos_connection_string>
SERVICEBUS_CONNECTION=<servicebus_connection_string>
OPENAI_API_KEY=<openai_api_key>
GMAIL_CLIENT_ID=<gmail_oauth_client_id>
OUTLOOK_CLIENT_ID=<outlook_oauth_client_id>
```

### Provider Setup
1. **Gmail**: Google Cloud Console API setup
2. **Outlook**: Microsoft Graph API registration
3. **iCloud**: App-specific password configuration

## Future Enhancements

### Planned Features
1. **Advanced AI Capabilities**
   - Multi-step reasoning workflows
   - Cross-event correlation analysis
   - Predictive scheduling

2. **Enhanced Provider Support**
   - Slack integration
   - Teams integration
   - Additional calendar providers

3. **Workflow Automation**
   - Visual workflow builder
   - Conditional logic chains
   - Template library

4. **Analytics & Insights**
   - Processing analytics
   - Performance metrics
   - Usage patterns

### Scalability Considerations
- Horizontal scaling with Azure Functions
- Service Bus partitioning
- Cosmos DB auto-scaling
- CDN for UI assets

## Conclusion

This email and calendar integration system provides a comprehensive solution for intelligent event processing. The combination of fast rule-based actions and AI-powered Conseil workers enables both simple automation and complex reasoning tasks.

The system is designed to be:
- **Scalable**: Handle high event volumes
- **Flexible**: Support diverse use cases
- **Intelligent**: Leverage AI for complex decisions
- **Secure**: Protect user data and credentials
- **User-friendly**: Intuitive configuration interface

Users can start with simple instructions and gradually build more sophisticated automation as their needs evolve.
