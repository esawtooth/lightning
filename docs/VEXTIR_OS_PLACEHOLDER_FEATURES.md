# Vextir OS Placeholder Feature Summary

This document lists the major features that remain unimplemented or are still using placeholder logic after migrating the Azure Functions to driver-based components.

## Provider-Specific Email and Calendar APIs

The new `EmailConnectorDriver` and `CalendarConnectorDriver` still include placeholders for provider integrations:

- Email sending via Gmail, Outlook, or iCloud is not yet implemented. The driver notes this explicitly:
  - Gmail integration TODO【F:vextir_os/communication_drivers.py†L125-L128】
  - Outlook integration TODO【F:vextir_os/communication_drivers.py†L130-L134】
  - iCloud SMTP TODO【F:vextir_os/communication_drivers.py†L136-L140】
- Calendar event creation currently returns placeholders instead of calling real APIs:
  - Google Calendar TODO【F:vextir_os/communication_drivers.py†L334-L338】
  - Microsoft Graph TODO【F:vextir_os/communication_drivers.py†L340-L344】
  - iCloud CalDAV TODO【F:vextir_os/communication_drivers.py†L346-L350】

## Messaging and Notification Channels

`UserMessengerDriver` methods for sending messages or notifications via Slack, Teams, SMS, or push are also stubs:

- Email connector integration TODO【F:vextir_os/communication_drivers.py†L511-L515】
- SMS provider integration TODO【F:vextir_os/communication_drivers.py†L517-L521】
- Slack API TODO【F:vextir_os/communication_drivers.py†L523-L527】
- Teams API TODO【F:vextir_os/communication_drivers.py†L529-L533】
- Push notifications TODO【F:vextir_os/communication_drivers.py†L557-L561】
- Email notification TODO【F:vextir_os/communication_drivers.py†L563-L567】
- SMS notification TODO【F:vextir_os/communication_drivers.py†L569-L573】
- Real-time in‑app notifications TODO【F:vextir_os/communication_drivers.py†L575-L579】

## Instruction CRUD Endpoints

The original Azure Functions exposed explicit HTTP endpoints for managing user instructions:

```text
GET /api/instructions
POST /api/instructions
PUT /api/instructions/{id}
DELETE /api/instructions/{id}
```
【F:docs/EMAIL_CALENDAR_SYSTEM_COMPLETE.md†L108-L114】

In the current driver-based implementation, `InstructionEngineDriver` processes instructions stored in Cosmos DB but there are no new API routes for creating, updating, or deleting instructions. A future API is needed to restore this functionality.

## Other TODOs

The authorization context still uses placeholder values for metrics and cost tracking【F:vextir_os/security.py†L185-L192】.

---
These placeholders highlight areas that still require development to reach feature parity with the old Azure Functions implementation.
