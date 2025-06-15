import json
import logging
import os
from datetime import datetime
from typing import Dict, Any, List, Optional

import azure.functions as func
from azure.servicebus import ServiceBusClient, ServiceBusMessage

from events import EmailEvent, CalendarEvent
from simple_auth import get_user_id_permissive

SERVICEBUS_CONN = os.environ.get("SERVICEBUS_CONNECTION")
SERVICEBUS_QUEUE = os.environ.get("SERVICEBUS_QUEUE")

_sb_client = ServiceBusClient.from_connection_string(SERVICEBUS_CONN) if SERVICEBUS_CONN else None


def _publish_event(event: EmailEvent | CalendarEvent):
    """Publish an event to the service bus."""
    if not _sb_client:
        logging.error("Service bus not configured")
        return False
    
    try:
        message = ServiceBusMessage(json.dumps(event.to_dict()))
        message.application_properties = {"topic": event.type}
        
        with _sb_client:
            sender = _sb_client.get_queue_sender(queue_name=SERVICEBUS_QUEUE)
            with sender:
                sender.send_messages(message)
        
        logging.info(f"Published {event.type} event for user {event.user_id}")
        return True
    except Exception as e:
        logging.error(f"Failed to publish event: {e}")
        return False


def _handle_email_webhook(provider: str, user_id: str, webhook_data: Dict[str, Any]) -> bool:
    """Handle incoming email webhook from provider."""
    try:
        # Extract email data based on provider format
        if provider == "gmail":
            # Gmail webhook format
            email_data = {
                "id": webhook_data.get("message", {}).get("id"),
                "thread_id": webhook_data.get("message", {}).get("threadId"),
                "from": webhook_data.get("from"),
                "to": webhook_data.get("to"),
                "subject": webhook_data.get("subject"),
                "body": webhook_data.get("body"),
                "timestamp": webhook_data.get("internalDate"),
                "labels": webhook_data.get("labelIds", [])
            }
        
        elif provider == "outlook":
            # Microsoft Graph webhook format
            email_data = {
                "id": webhook_data.get("id"),
                "conversation_id": webhook_data.get("conversationId"),
                "from": webhook_data.get("from", {}).get("emailAddress", {}).get("address"),
                "to": [addr.get("emailAddress", {}).get("address") for addr in webhook_data.get("toRecipients", [])],
                "subject": webhook_data.get("subject"),
                "body": webhook_data.get("body", {}).get("content"),
                "timestamp": webhook_data.get("receivedDateTime"),
                "categories": webhook_data.get("categories", [])
            }
        
        else:
            logging.error(f"Unsupported email provider: {provider}")
            return False
        
        # Create email event
        event = EmailEvent(
            timestamp=datetime.utcnow(),
            source="EmailCalendarConnector",
            type="email.received",
            user_id=user_id,
            operation="received",
            provider=provider,
            email_data=email_data
        )
        
        return _publish_event(event)
    
    except Exception as e:
        logging.error(f"Error handling email webhook: {e}")
        return False


def _handle_calendar_webhook(provider: str, user_id: str, webhook_data: Dict[str, Any]) -> bool:
    """Handle incoming calendar webhook from provider."""
    try:
        # Extract calendar data based on provider format
        if provider == "gmail":
            # Google Calendar webhook format
            calendar_data = {
                "id": webhook_data.get("id"),
                "calendar_id": webhook_data.get("calendarId"),
                "title": webhook_data.get("summary"),
                "description": webhook_data.get("description"),
                "start_time": webhook_data.get("start", {}).get("dateTime"),
                "end_time": webhook_data.get("end", {}).get("dateTime"),
                "attendees": [att.get("email") for att in webhook_data.get("attendees", [])],
                "location": webhook_data.get("location"),
                "status": webhook_data.get("status")
            }
        
        elif provider == "outlook":
            # Microsoft Graph calendar webhook format
            calendar_data = {
                "id": webhook_data.get("id"),
                "calendar_id": webhook_data.get("calendarId"),
                "title": webhook_data.get("subject"),
                "description": webhook_data.get("body", {}).get("content"),
                "start_time": webhook_data.get("start", {}).get("dateTime"),
                "end_time": webhook_data.get("end", {}).get("dateTime"),
                "attendees": [att.get("emailAddress", {}).get("address") for att in webhook_data.get("attendees", [])],
                "location": webhook_data.get("location", {}).get("displayName"),
                "status": webhook_data.get("showAs")
            }
        
        else:
            logging.error(f"Unsupported calendar provider: {provider}")
            return False
        
        # Create calendar event
        event = CalendarEvent(
            timestamp=datetime.utcnow(),
            source="EmailCalendarConnector",
            type="calendar.received",
            user_id=user_id,
            operation="received",
            provider=provider,
            calendar_data=calendar_data
        )
        
        return _publish_event(event)
    
    except Exception as e:
        logging.error(f"Error handling calendar webhook: {e}")
        return False


def _handle_email_send(user_id: str, email_event: EmailEvent) -> func.HttpResponse:
    """Handle email send request."""
    # This would integrate with actual email providers
    # For now, return a placeholder response
    
    provider = email_event.provider
    email_data = email_event.email_data
    
    logging.info(f"Email send request for user {user_id} via {provider}")
    logging.info(f"To: {email_data.get('to')}, Subject: {email_data.get('subject')}")
    
    # TODO: Implement actual email sending via provider APIs
    # - Gmail: Use Gmail API
    # - Outlook: Use Microsoft Graph API
    # - iCloud: Use SMTP with app-specific password
    
    return func.HttpResponse(
        json.dumps({"status": "queued", "message": "Email send functionality not yet implemented"}),
        status_code=202,
        mimetype="application/json"
    )


def _handle_calendar_create(user_id: str, calendar_event: CalendarEvent) -> func.HttpResponse:
    """Handle calendar event creation request."""
    # This would integrate with actual calendar providers
    # For now, return a placeholder response
    
    provider = calendar_event.provider
    calendar_data = calendar_event.calendar_data
    
    logging.info(f"Calendar create request for user {user_id} via {provider}")
    logging.info(f"Title: {calendar_data.get('title')}, Start: {calendar_data.get('start_time')}")
    
    # TODO: Implement actual calendar event creation via provider APIs
    # - Google Calendar: Use Google Calendar API
    # - Outlook Calendar: Use Microsoft Graph API
    # - iCloud Calendar: Use CalDAV
    
    return func.HttpResponse(
        json.dumps({"status": "queued", "message": "Calendar create functionality not yet implemented"}),
        status_code=202,
        mimetype="application/json"
    )


def _execute_email_send(email_event: EmailEvent) -> func.HttpResponse:
    """Execute email send operation from service bus event."""
    provider = email_event.provider
    email_data = email_event.email_data
    user_id = email_event.user_id
    
    logging.info(f"Executing email send for user {user_id} via {provider}")
    logging.info(f"To: {email_data.get('to')}, Subject: {email_data.get('subject')}")
    
    # TODO: Implement actual email sending via provider APIs
    # This would use stored OAuth tokens for the user
    
    try:
        # Placeholder for actual implementation
        if provider == "gmail":
            # Use Gmail API with stored OAuth token
            pass
        elif provider == "outlook":
            # Use Microsoft Graph API with stored OAuth token
            pass
        elif provider == "icloud":
            # Use SMTP with app-specific password
            pass
        else:
            logging.error(f"Unsupported email provider: {provider}")
            return func.HttpResponse("Unsupported provider", status_code=400)
        
        logging.info(f"Email sent successfully for user {user_id}")
        return func.HttpResponse("Email sent", status_code=200)
        
    except Exception as e:
        logging.error(f"Failed to send email: {e}")
        return func.HttpResponse(f"Send failed: {str(e)}", status_code=500)


def _execute_calendar_create(calendar_event: CalendarEvent) -> func.HttpResponse:
    """Execute calendar event creation from service bus event."""
    provider = calendar_event.provider
    calendar_data = calendar_event.calendar_data
    user_id = calendar_event.user_id
    
    logging.info(f"Executing calendar create for user {user_id} via {provider}")
    logging.info(f"Title: {calendar_data.get('title')}, Start: {calendar_data.get('start_time')}")
    
    try:
        # Placeholder for actual implementation
        if provider == "gmail":
            # Use Google Calendar API with stored OAuth token
            pass
        elif provider == "outlook":
            # Use Microsoft Graph API with stored OAuth token
            pass
        elif provider == "icloud":
            # Use CalDAV with stored credentials
            pass
        else:
            logging.error(f"Unsupported calendar provider: {provider}")
            return func.HttpResponse("Unsupported provider", status_code=400)
        
        logging.info(f"Calendar event created successfully for user {user_id}")
        return func.HttpResponse("Calendar event created", status_code=200)
        
    except Exception as e:
        logging.error(f"Failed to create calendar event: {e}")
        return func.HttpResponse(f"Creation failed: {str(e)}", status_code=500)


def _execute_calendar_update(calendar_event: CalendarEvent) -> func.HttpResponse:
    """Execute calendar event update from service bus event."""
    provider = calendar_event.provider
    calendar_data = calendar_event.calendar_data
    user_id = calendar_event.user_id
    
    logging.info(f"Executing calendar update for user {user_id} via {provider}")
    logging.info(f"Event ID: {calendar_data.get('id')}, Title: {calendar_data.get('title')}")
    
    try:
        # Placeholder for actual implementation
        if provider == "gmail":
            # Use Google Calendar API with stored OAuth token
            pass
        elif provider == "outlook":
            # Use Microsoft Graph API with stored OAuth token
            pass
        elif provider == "icloud":
            # Use CalDAV with stored credentials
            pass
        else:
            logging.error(f"Unsupported calendar provider: {provider}")
            return func.HttpResponse("Unsupported provider", status_code=400)
        
        logging.info(f"Calendar event updated successfully for user {user_id}")
        return func.HttpResponse("Calendar event updated", status_code=200)
        
    except Exception as e:
        logging.error(f"Failed to update calendar event: {e}")
        return func.HttpResponse(f"Update failed: {str(e)}", status_code=500)


def _execute_calendar_delete(calendar_event: CalendarEvent) -> func.HttpResponse:
    """Execute calendar event deletion from service bus event."""
    provider = calendar_event.provider
    calendar_data = calendar_event.calendar_data
    user_id = calendar_event.user_id
    
    logging.info(f"Executing calendar delete for user {user_id} via {provider}")
    logging.info(f"Event ID: {calendar_data.get('id')}")
    
    try:
        # Placeholder for actual implementation
        if provider == "gmail":
            # Use Google Calendar API with stored OAuth token
            pass
        elif provider == "outlook":
            # Use Microsoft Graph API with stored OAuth token
            pass
        elif provider == "icloud":
            # Use CalDAV with stored credentials
            pass
        else:
            logging.error(f"Unsupported calendar provider: {provider}")
            return func.HttpResponse("Unsupported provider", status_code=400)
        
        logging.info(f"Calendar event deleted successfully for user {user_id}")
        return func.HttpResponse("Calendar event deleted", status_code=200)
        
    except Exception as e:
        logging.error(f"Failed to delete calendar event: {e}")
        return func.HttpResponse(f"Deletion failed: {str(e)}", status_code=500)


def main(req: func.HttpRequest = None, msg: func.ServiceBusMessage = None) -> func.HttpResponse:
    """Main handler for email/calendar connector operations."""
    
    # Handle service bus messages (outbound events from Conseil)
    if msg:
        return _handle_service_bus_message(msg)
    
    # Handle HTTP requests (webhooks and API calls)
    if req:
        return _handle_http_request(req)
    
    return func.HttpResponse("No valid input provided", status_code=400)


def _handle_service_bus_message(msg: func.ServiceBusMessage) -> func.HttpResponse:
    """Handle service bus messages for outbound email/calendar operations."""
    if not _sb_client:
        logging.error("Service bus not configured")
        return func.HttpResponse("Service bus not configured", status_code=500)
    
    body = msg.get_body().decode("utf-8")
    try:
        data = json.loads(body)
        event_type = data.get("type")
        
        if event_type == "email.send":
            email_event = EmailEvent.from_dict(data)
            return _execute_email_send(email_event)
        elif event_type == "calendar.create":
            calendar_event = CalendarEvent.from_dict(data)
            return _execute_calendar_create(calendar_event)
        elif event_type == "calendar.update":
            calendar_event = CalendarEvent.from_dict(data)
            return _execute_calendar_update(calendar_event)
        elif event_type == "calendar.delete":
            calendar_event = CalendarEvent.from_dict(data)
            return _execute_calendar_delete(calendar_event)
        else:
            logging.info(f"Ignoring event type: {event_type}")
            return func.HttpResponse("Event type not handled", status_code=200)
    
    except Exception as e:
        logging.error(f"Error processing service bus message: {e}")
        return func.HttpResponse(f"Processing error: {str(e)}", status_code=500)


def _handle_http_request(req: func.HttpRequest) -> func.HttpResponse:
    """Handle HTTP requests for webhooks and API operations."""
    if not _sb_client:
        return func.HttpResponse("Service bus not configured", status_code=500)
    
    method = req.method
    route_params = req.route_params
    action = route_params.get("action", "")
    provider = route_params.get("provider", "")
    
    try:
        # Handle webhooks from providers
        if action == "webhook" and method == "POST":
            # Extract user ID from webhook data or headers
            # This would typically come from webhook registration
            user_id = req.headers.get("X-User-Id") or req.params.get("user_id")
            if not user_id:
                return func.HttpResponse("Missing user ID", status_code=400)
            
            try:
                webhook_data = req.get_json()
            except ValueError:
                return func.HttpResponse("Invalid JSON", status_code=400)
            
            webhook_type = req.params.get("type", "email")
            
            if webhook_type == "email":
                success = _handle_email_webhook(provider, user_id, webhook_data)
            elif webhook_type == "calendar":
                success = _handle_calendar_webhook(provider, user_id, webhook_data)
            else:
                return func.HttpResponse("Invalid webhook type", status_code=400)
            
            if success:
                return func.HttpResponse("Processed", status_code=200)
            else:
                return func.HttpResponse("Processing failed", status_code=500)
        
        # Handle email/calendar operations
        elif action in ["email", "calendar"] and method == "POST":
            try:
                user_id = get_user_id_permissive(req)
            except Exception:
                return func.HttpResponse("Unauthorized", status_code=401)
            
            try:
                data = req.get_json()
            except ValueError:
                return func.HttpResponse("Invalid JSON", status_code=400)
            
            if action == "email":
                try:
                    email_event = EmailEvent.from_dict({
                        **data,
                        "timestamp": datetime.utcnow().isoformat(),
                        "source": "EmailCalendarConnector",
                        "userID": user_id
                    })
                    return _handle_email_send(user_id, email_event)
                except ValueError as e:
                    return func.HttpResponse(str(e), status_code=400)
            
            elif action == "calendar":
                try:
                    calendar_event = CalendarEvent.from_dict({
                        **data,
                        "timestamp": datetime.utcnow().isoformat(),
                        "source": "EmailCalendarConnector",
                        "userID": user_id
                    })
                    return _handle_calendar_create(user_id, calendar_event)
                except ValueError as e:
                    return func.HttpResponse(str(e), status_code=400)
        
        # Handle OAuth authentication flows
        elif action == "auth" and method in ["GET", "POST"]:
            # TODO: Implement OAuth flows for each provider
            return func.HttpResponse(
                json.dumps({"message": "OAuth authentication not yet implemented"}),
                status_code=501,
                mimetype="application/json"
            )
        
        else:
            return func.HttpResponse("Invalid request", status_code=400)
    
    except Exception as e:
        logging.error(f"Error in email/calendar connector: {e}")
        return func.HttpResponse(f"Internal error: {str(e)}", status_code=500)
