# Email & Calendar Integration System - Complete Implementation

## Overview

This document describes the complete email and calendar integration system for the Vextir platform. The system enables users to gather events from email and calendar across iCloud, Outlook, Gmail, and other providers, process them through a service bus, and handle them with dynamically created instruction handlers.

## Architecture

### Core Components

1. **EmailCalendarConnector** - Azure Function for provider integration
2. **InstructionManager** - Manages user-defined processing instructions
3. **InstructionProcessor** - Executes instructions based on events
4. **ContextSynthesizer** - Updates context summaries based on processed events
5. **Integrated UI** - Web interface for managing the entire system

### Data Flow

```
Email/Calendar Providers → EmailCalendarConnector → Service Bus → InstructionProcessor → Actions
                                                                        ↓
                                                              ContextSynthesizer
```

## Implementation Details

### 1. Azure Functions

#### EmailCalendarConnector (`azure-function/EmailCalendarConnector/`)
- **Purpose**: Connect to email/calendar providers and fetch events
- **Providers Supported**: Gmail, Outlook, iCloud
- **Authentication**: OAuth2 for Gmail/Outlook, IMAP/SMTP for iCloud
- **Endpoints**:
  - `GET /connector/status` - Get connection status for all providers
  - `GET /connector/auth/{provider}` - Start OAuth flow
  - `POST /connector/test/{provider}` - Test provider connection
  - `DELETE /connector/{provider}` - Disconnect provider
  - `POST /connector/webhook/{provider}` - Receive webhook notifications

#### InstructionManager (`azure-function/InstructionManager/`)
- **Purpose**: Manage user-defined processing instructions
- **Endpoints**:
  - `GET /instructions` - List user instructions
  - `POST /instructions` - Create new instruction
  - `PUT /instructions/{id}` - Update instruction
  - `DELETE /instructions/{id}` - Delete instruction
  - `PATCH /instructions/{id}/toggle` - Enable/disable instruction

#### InstructionProcessor (`azure-function/InstructionProcessor/`)
- **Purpose**: Process events based on user instructions
- **Trigger**: Service Bus queue messages
- **Actions Supported**:
  - Update context summaries
  - Send emails
  - Create tasks
  - Send notifications

#### ContextSynthesizer (`azure-function/ContextSynthesizer/`)
- **Purpose**: Synthesize and update context summaries
- **Trigger**: HTTP requests from InstructionProcessor
- **Features**:
  - AI-powered content synthesis
  - Context key management
  - Incremental updates

### 2. Event Processing

#### Event Structure
```json
{
  "timestamp": "2025-06-15T01:00:00Z",
  "source": "gmail",
  "type": "email.received",
  "metadata": {
    "provider": "gmail",
    "operation": "received",
    "email_data": {
      "from": "sender@example.com",
      "to": ["user@example.com"],
      "subject": "Important Meeting",
      "body": "Meeting details...",
      "timestamp": "2025-06-15T01:00:00Z"
    }
  }
}
```

#### Instruction Structure
```json
{
  "id": "instruction-uuid",
  "name": "Email Summary Updates",
  "description": "Keep email summary updated with important emails",
  "enabled": true,
  "trigger": {
    "event_type": "email.received",
    "providers": ["gmail", "outlook"],
    "conditions": {
      "content_filters": {
        "subject_contains": ["project", "urgent", "meeting"]
      }
    }
  },
  "action": {
    "type": "update_context_summary",
    "config": {
      "context_key": "email_summary",
      "synthesis_prompt": "Update the summary with key information: action items, deadlines, and important decisions."
    }
  }
}
```

### 3. User Interface

#### New Pages Added

1. **Instructions Page** (`/instructions`)
   - Create and manage processing instructions
   - Configure triggers and actions
   - Monitor execution statistics
   - Test instruction matching

2. **Events Page** (`/events`)
   - Real-time event stream monitoring
   - Filter by event type and provider
   - Create test events for debugging
   - View detailed event data

3. **Providers Page** (`/providers`)
   - Connect/disconnect email and calendar providers
   - View connection status
   - Test provider connections
   - Configure webhook URLs

#### Enhanced Navigation
- Added new navigation items in the sidebar
- Integrated with existing dashboard and context hub
- Consistent UI/UX with the rest of the platform

### 4. Provider Integration

#### Gmail Integration
- **Authentication**: OAuth2 with Google Cloud Platform
- **APIs Used**: Gmail API, Google Calendar API
- **Features**: Real-time webhooks, email reading/sending, calendar events
- **Setup**: Requires Google Cloud Project with enabled APIs

#### Outlook Integration
- **Authentication**: OAuth2 with Microsoft Azure AD
- **APIs Used**: Microsoft Graph API
- **Features**: Exchange integration, Teams calendar sync, enterprise features
- **Setup**: Requires Azure AD app registration

#### iCloud Integration
- **Authentication**: App-specific passwords
- **Protocols**: IMAP/SMTP for email, CalDAV for calendar
- **Features**: iCloud Mail access, calendar synchronization
- **Setup**: Requires 2FA and app-specific password generation

### 5. Context Hub Integration

#### Context Summaries
- **Purpose**: Maintain up-to-date summaries of email and calendar data
- **Keys**: User-defined (e.g., "email_summary", "meeting_schedule")
- **Updates**: Triggered by instruction processing
- **AI Synthesis**: Uses LLM to intelligently update summaries

#### API Endpoints
- `GET /context/summaries` - List all summaries
- `GET /context/summaries/{key}` - Get specific summary
- `POST /context/summaries/{key}/synthesize` - Trigger manual synthesis

## Configuration

### Environment Variables

```bash
# Email/Calendar Integration
GMAIL_CLIENT_ID=your_gmail_client_id
GMAIL_CLIENT_SECRET=your_gmail_client_secret
OUTLOOK_CLIENT_ID=your_outlook_client_id
OUTLOOK_CLIENT_SECRET=your_outlook_client_secret

# Service Bus
SERVICE_BUS_CONNECTION_STRING=your_service_bus_connection
EMAIL_EVENTS_QUEUE=email-events
CALENDAR_EVENTS_QUEUE=calendar-events

# Context Hub
CONTEXT_HUB_URL=http://localhost:8080
OPENAI_API_KEY=your_openai_key
```

### Azure Function Configuration

Update `azure-function/host.json`:
```json
{
  "version": "2.0",
  "extensions": {
    "serviceBus": {
      "prefetchCount": 100,
      "messageHandlerOptions": {
        "autoComplete": true,
        "maxConcurrentCalls": 32,
        "maxAutoRenewDuration": "00:55:00"
      }
    }
  }
}
```

## Usage Examples

### 1. Email Summary Instruction
Create an instruction that maintains an up-to-date summary of all important emails:

```json
{
  "name": "Important Email Summary",
  "description": "Maintain summary of emails marked as important",
  "trigger": {
    "event_type": "email.received",
    "providers": ["gmail", "outlook"],
    "conditions": {
      "content_filters": {
        "subject_contains": ["urgent", "important", "action required"]
      }
    }
  },
  "action": {
    "type": "update_context_summary",
    "config": {
      "context_key": "important_emails",
      "synthesis_prompt": "Summarize the key points, action items, and deadlines from this email. Include sender and urgency level."
    }
  }
}
```

### 2. Meeting Notification Instruction
Send notifications for new calendar events:

```json
{
  "name": "Meeting Notifications",
  "description": "Send notifications for new meetings",
  "trigger": {
    "event_type": "calendar.received",
    "providers": ["gmail", "outlook"]
  },
  "action": {
    "type": "send_notification",
    "config": {
      "title": "New Meeting: {title}",
      "message": "Meeting scheduled for {start_time} with {attendees}"
    }
  }
}
```

### 3. Weekly Email Summary
Automatically send weekly email summaries:

```json
{
  "name": "Weekly Email Summary",
  "description": "Send weekly summary of all emails",
  "trigger": {
    "event_type": "schedule.weekly",
    "schedule": "0 9 * * 1"
  },
  "action": {
    "type": "send_email",
    "config": {
      "email": {
        "to": "user@example.com",
        "subject": "Weekly Email Summary",
        "body_template": "Here's your weekly email summary: {email_summary}"
      }
    }
  }
}
```

## Testing

### Test Email Integration
```bash
# Test the complete integration
python test_email_calendar_integration.py

# Test specific provider
curl -X POST http://localhost:7071/api/connector/test/gmail

# Create test event
curl -X POST http://localhost:7071/api/events/test \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "email.received",
    "provider": "gmail",
    "test_data": {
      "email_data": {
        "from": "test@example.com",
        "subject": "Test Email",
        "body": "This is a test email"
      }
    }
  }'
```

### UI Testing
1. Navigate to `/providers` and connect email providers
2. Go to `/instructions` and create processing instructions
3. Visit `/events` to monitor real-time event processing
4. Check `/context` to see updated summaries

## Security Considerations

### Authentication
- OAuth2 tokens stored securely in Azure Key Vault
- App-specific passwords encrypted at rest
- JWT tokens for API authentication

### Data Privacy
- Email content processed only according to user instructions
- No persistent storage of email content
- Context summaries can be deleted by users

### Access Control
- User-scoped instructions and events
- Provider connections tied to user accounts
- API endpoints protected with authentication

## Monitoring and Logging

### Azure Application Insights
- Function execution metrics
- Error tracking and alerting
- Performance monitoring

### Custom Metrics
- Instruction execution counts
- Provider connection status
- Event processing latency

### Logging
- Structured logging with correlation IDs
- Error details for debugging
- Audit trail for instruction changes

## Deployment

### Azure Functions Deployment
```bash
# Deploy all functions
func azure functionapp publish your-function-app

# Deploy specific function
func azure functionapp publish your-function-app --slot staging
```

### UI Deployment
```bash
# Start integrated UI
cd ui/integrated_app
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

### Infrastructure as Code
The system integrates with existing Pulumi infrastructure:
- Service Bus queues automatically created
- Function app configuration updated
- Key Vault secrets managed

## Future Enhancements

### Planned Features
1. **Advanced Filtering**: More sophisticated content filtering options
2. **Custom Actions**: User-defined action types with custom code
3. **Batch Processing**: Process multiple events together
4. **Analytics Dashboard**: Detailed analytics on email/calendar patterns
5. **Mobile App**: Mobile interface for monitoring and configuration

### Integration Opportunities
1. **Slack Integration**: Send notifications to Slack channels
2. **Teams Integration**: Create Teams meetings from calendar events
3. **CRM Integration**: Sync email data with CRM systems
4. **Task Management**: Create tasks in external systems

## Conclusion

The email and calendar integration system provides a comprehensive solution for processing email and calendar events through user-defined instructions. The system is designed to be:

- **Scalable**: Handles high volumes of events through Azure Service Bus
- **Flexible**: User-defined instructions for custom processing
- **Secure**: Proper authentication and data privacy controls
- **Extensible**: Easy to add new providers and action types
- **User-Friendly**: Intuitive web interface for configuration and monitoring

The integration seamlessly fits into the existing Vextir platform while providing powerful new capabilities for email and calendar automation.
