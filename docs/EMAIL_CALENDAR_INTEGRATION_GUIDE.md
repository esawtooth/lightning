# Email and Calendar Integration System

This document describes the email and calendar integration system for Vextir OS, which enables intelligent processing of email and calendar events through user-defined instructions.

## Overview

The system follows a **instruction-driven, context-synthesis** approach:

1. **No Default Processing**: Events are only processed if users have defined instructions
2. **Context Synthesis**: Instead of storing raw email data, the system maintains intelligent summaries in the Context Hub
3. **Dynamic Instructions**: Users can create custom instructions to handle different types of events
4. **Multi-Provider Support**: Works with Gmail, Outlook, and iCloud

## Architecture Components

### 1. Event Types

#### EmailEvent
```python
{
  "type": "email.received",
  "operation": "received",  # received, send, reply, forward
  "provider": "gmail",      # gmail, outlook, icloud
  "email_data": {
    "from": "sender@example.com",
    "to": ["recipient@example.com"],
    "subject": "Meeting Tomorrow",
    "body": "Let's meet at 2pm...",
    "timestamp": "2025-06-15T10:00:00Z"
  }
}
```

#### CalendarEvent
```python
{
  "type": "calendar.received",
  "operation": "received",  # received, create, update, delete
  "provider": "outlook",
  "calendar_data": {
    "title": "Team Meeting",
    "start_time": "2025-06-15T14:00:00Z",
    "end_time": "2025-06-15T15:00:00Z",
    "attendees": ["team@example.com"],
    "location": "Conference Room A"
  }
}
```

### 2. Instruction System

Users create instructions that define:
- **Triggers**: What events to match
- **Actions**: What to do when matched

#### Example Instruction: Email Summary
```json
{
  "name": "Daily Email Summary",
  "description": "Maintain a running summary of important emails",
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
      "synthesis_prompt": "Update the email summary with key information: action items, important dates, and project updates."
    }
  }
}
```

#### Example Instruction: Meeting Notifications
```json
{
  "name": "Meeting Reminders",
  "description": "Send email reminders for upcoming meetings",
  "trigger": {
    "event_type": "calendar.received",
    "providers": ["outlook"],
    "conditions": {
      "time_range": {
        "start_hour": 9,
        "end_hour": 17
      }
    }
  },
  "action": {
    "type": "send_email",
    "config": {
      "email": {
        "to": "user@example.com",
        "subject": "Meeting Reminder: {title}",
        "body_template": "You have a meeting '{title}' at {start_time}"
      }
    }
  }
}
```

### 3. Context Synthesis

The system maintains intelligent summaries in the Context Hub:

```markdown
# Email Summary

## Recent Communications (Updated: 2025-06-15 10:30)

### Project Alpha
- Status update from Alice: On track for Q2 delivery
- Budget review scheduled for next week
- Need to finalize vendor contracts by Friday

### Team Meetings
- Weekly standup moved to Tuesdays
- All-hands meeting next month - prepare Q1 report
- New team member starting Monday

### Action Items
- [ ] Review budget proposal (Due: Friday)
- [ ] Prepare Q1 report (Due: Next month)
- [ ] Follow up with vendor contracts
```

## API Endpoints

### 1. Instruction Management

#### Create Instruction
```http
POST /api/instructions
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "Email Summary",
  "trigger": { ... },
  "action": { ... }
}
```

#### List Instructions
```http
GET /api/instructions
Authorization: Bearer <token>
```

#### Update Instruction
```http
PUT /api/instructions/{instruction_id}
Authorization: Bearer <token>
Content-Type: application/json

{
  "enabled": false
}
```

### 2. Email/Calendar Operations

#### Send Email
```http
POST /api/connector/email
Authorization: Bearer <token>
Content-Type: application/json

{
  "type": "email.send",
  "metadata": {
    "operation": "send",
    "provider": "gmail",
    "email_data": {
      "to": ["recipient@example.com"],
      "subject": "Hello",
      "body": "This is a test email"
    }
  }
}
```

#### Create Calendar Event
```http
POST /api/connector/calendar
Authorization: Bearer <token>
Content-Type: application/json

{
  "type": "calendar.create",
  "metadata": {
    "operation": "create",
    "provider": "outlook",
    "calendar_data": {
      "title": "Team Meeting",
      "start_time": "2025-06-15T14:00:00Z",
      "end_time": "2025-06-15T15:00:00Z"
    }
  }
}
```

### 3. Webhooks

#### Email Webhook
```http
POST /api/connector/webhook/gmail?type=email&user_id={user_id}
Content-Type: application/json

{
  "message": {
    "id": "msg123",
    "threadId": "thread456"
  },
  "from": "sender@example.com",
  "subject": "Important Update"
}
```

## Setup Instructions

### 1. Provider Authentication

#### Gmail
1. Create Google Cloud Project
2. Enable Gmail API and Google Calendar API
3. Create OAuth2 credentials
4. Configure redirect URI: `{function_url}/api/connector/auth/gmail`

#### Outlook
1. Register app in Azure AD
2. Configure Microsoft Graph permissions
3. Set redirect URI: `{function_url}/api/connector/auth/outlook`

#### iCloud
1. Generate app-specific password
2. Configure IMAP/SMTP settings
3. Set up CalDAV for calendar access

### 2. Environment Variables

Add to Azure Function configuration:

```bash
COSMOS_CONNECTION=<cosmos_connection_string>
SERVICEBUS_CONNECTION=<servicebus_connection_string>
SERVICEBUS_QUEUE=<queue_name>
HUB_URL=<context_hub_url>
OPENAI_API_KEY=<openai_api_key>
INSTRUCTION_CONTAINER=instructions
```

### 3. Webhook Registration

For real-time updates, register webhooks with providers:

#### Gmail
```python
# Use Gmail Push Notifications
# Configure Cloud Pub/Sub topic
# Set webhook URL: /api/connector/webhook/gmail
```

#### Outlook
```python
# Use Microsoft Graph Subscriptions
# Set notification URL: /api/connector/webhook/outlook
```

## Usage Examples

### 1. Basic Email Monitoring

Create an instruction to track project emails:

```bash
curl -X POST /api/instructions \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Project Email Tracker",
    "trigger": {
      "event_type": "email.received",
      "conditions": {
        "content_filters": {
          "subject_contains": ["Project Alpha"]
        }
      }
    },
    "action": {
      "type": "update_context_summary",
      "config": {
        "context_key": "project_alpha_emails",
        "synthesis_prompt": "Track Project Alpha updates, decisions, and action items."
      }
    }
  }'
```

### 2. Calendar Integration

Create an instruction to sync meeting information:

```bash
curl -X POST /api/instructions \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Meeting Context Builder",
    "trigger": {
      "event_type": "calendar.received",
      "providers": ["outlook"]
    },
    "action": {
      "type": "update_context_summary",
      "config": {
        "context_key": "meeting_schedule",
        "synthesis_prompt": "Maintain an overview of upcoming meetings, attendees, and agenda items."
      }
    }
  }'
```

### 3. Automated Responses

Create an instruction to auto-respond to certain emails:

```bash
curl -X POST /api/instructions \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Auto-Reply for Urgent Emails",
    "trigger": {
      "event_type": "email.received",
      "conditions": {
        "content_filters": {
          "subject_contains": ["URGENT"]
        }
      }
    },
    "action": {
      "type": "send_email",
      "config": {
        "email": {
          "to": "assistant@example.com",
          "subject": "Urgent Email Received",
          "body_template": "Urgent email received from {from}: {subject}"
        }
      }
    }
  }'
```

## Security Considerations

1. **OAuth2 Authentication**: All provider integrations use OAuth2
2. **Token Storage**: Credentials stored securely in Azure Key Vault
3. **User Isolation**: Each user's instructions and context are isolated
4. **Webhook Validation**: Webhook payloads are validated and authenticated
5. **Rate Limiting**: API calls respect provider rate limits

## Monitoring and Debugging

### Logs
- Check Azure Function logs for processing status
- Monitor Service Bus message flow
- Track instruction execution counts

### Metrics
- Instruction match rates
- Context update frequency
- Provider API usage
- Error rates by provider

## Future Enhancements

1. **Advanced Filtering**: ML-based content classification
2. **Smart Scheduling**: AI-powered meeting optimization
3. **Cross-Provider Sync**: Sync events between providers
4. **Template Library**: Pre-built instruction templates
5. **Analytics Dashboard**: Usage and effectiveness metrics

## Troubleshooting

### Common Issues

1. **Events Not Processing**
   - Check if user has matching instructions
   - Verify Service Bus connectivity
   - Check instruction trigger conditions

2. **Context Not Updating**
   - Verify Context Hub connectivity
   - Check OpenAI API key configuration
   - Review synthesis prompts

3. **Provider Authentication**
   - Refresh OAuth tokens
   - Check API permissions
   - Verify webhook endpoints

### Debug Commands

```bash
# Check instruction status
curl -X GET /api/instructions \
  -H "Authorization: Bearer <token>"

# Test webhook endpoint
curl -X POST /api/connector/webhook/gmail?type=email&user_id=test \
  -H "Content-Type: application/json" \
  -d '{"test": "data"}'

# Check context status
curl -X GET /api/context/status \
  -H "Authorization: Bearer <token>"
```

This integration system provides a powerful, flexible foundation for intelligent email and calendar processing while maintaining user privacy and control.
