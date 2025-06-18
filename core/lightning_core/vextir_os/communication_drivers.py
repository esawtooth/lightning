"""
Communication drivers that replace email/calendar and messaging Azure Functions
"""

import asyncio
import base64
import json
import logging
import os
import smtplib
import uuid
from datetime import datetime
from email.message import EmailMessage
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

import requests
from lightning_core.events.models import CalendarEvent, EmailEvent, Event, VoiceCallEvent
from lightning_core.abstractions import ContainerConfig, EventMessage, ResourceRequirements
from lightning_core.runtime import LightningRuntime

from .drivers import (
    AgentDriver,
    Driver,
    DriverManifest,
    DriverType,
    IODriver,
    ResourceSpec,
    ToolDriver,
    driver,
)


@driver(
    "email_connector",
    DriverType.IO,
    capabilities=["email.send", "email.receive", "email.webhook"],
    name="Email Connector Driver",
    description="Email integration with multiple providers",
)
class EmailConnectorDriver(IODriver):
    """Replaces EmailCalendarConnector Azure Function for email operations"""

    def __init__(
        self, manifest: DriverManifest, config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(manifest, config)
        self.gmail_token = os.environ.get("GMAIL_OAUTH_TOKEN")
        self.outlook_token = os.environ.get("OUTLOOK_OAUTH_TOKEN")
        self.icloud_username = os.environ.get("ICLOUD_USERNAME")
        self.icloud_app_password = os.environ.get("ICLOUD_APP_PASSWORD")

        # Initialize Lightning Runtime for provider abstraction
        self.runtime = LightningRuntime()

    def get_capabilities(self) -> List[str]:
        return ["email.send", "email.receive", "email.webhook"]

    def get_resource_requirements(self) -> ResourceSpec:
        return ResourceSpec(memory_mb=512, timeout_seconds=30)

    async def handle_event(self, event: Event) -> List[Event]:
        """Handle email-related events"""
        output_events = []

        if isinstance(event, EmailEvent):
            if event.operation == "send":
                # Handle email sending
                success = await self._execute_email_send(event)

                result_event = Event(
                    timestamp=datetime.utcnow(),
                    source="EmailConnectorDriver",
                    type="email.sent" if success else "email.send.failed",
                    user_id=event.user_id,
                    metadata={
                        "email_id": event.email_data.get("id"),
                        "to": event.email_data.get("to"),
                        "subject": event.email_data.get("subject"),
                        "success": success,
                    },
                )
                output_events.append(result_event)

            elif event.operation == "received":
                # Handle incoming email webhook
                processed_event = await self._process_incoming_email(event)
                if processed_event:
                    output_events.append(processed_event)

        elif event.type == "email.webhook":
            # Handle webhook from email providers
            provider = event.metadata.get("provider")
            webhook_data = event.metadata.get("webhook_data", {})

            email_event = await self._handle_email_webhook(
                provider, event.user_id, webhook_data
            )
            if email_event:
                output_events.append(email_event)

        return output_events

    async def _execute_email_send(self, email_event: EmailEvent) -> bool:
        """Execute email send operation"""
        provider = email_event.provider
        email_data = email_event.email_data
        user_id = email_event.user_id

        logging.info(f"Executing email send for user {user_id} via {provider}")
        logging.info(
            f"To: {email_data.get('to')}, Subject: {email_data.get('subject')}"
        )

        try:
            # TODO: Implement actual email sending via provider APIs
            # This would use stored OAuth tokens for the user

            if provider == "gmail":
                # Use Gmail API with stored OAuth token
                return await self._send_via_gmail(user_id, email_data)
            elif provider == "outlook":
                # Use Microsoft Graph API with stored OAuth token
                return await self._send_via_outlook(user_id, email_data)
            elif provider == "icloud":
                # Use SMTP with app-specific password
                return await self._send_via_icloud(user_id, email_data)
            else:
                logging.error(f"Unsupported email provider: {provider}")
                return False

        except Exception as e:
            logging.error(f"Failed to send email: {e}")
            return False

    async def _send_via_gmail(self, user_id: str, email_data: Dict[str, Any]) -> bool:
        """Send email via Gmail API"""
        token = self.gmail_token
        if not token:
            logging.error("GMAIL_OAUTH_TOKEN not configured")
            return False

        def _send() -> bool:
            msg = MIMEText(email_data.get("body", ""))
            msg["to"] = email_data.get("to")
            msg["subject"] = email_data.get("subject", "")
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
            resp = requests.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                headers=headers,
                json={"raw": raw},
            )
            return resp.status_code in (200, 202)

        return await asyncio.to_thread(_send)

    async def _send_via_outlook(self, user_id: str, email_data: Dict[str, Any]) -> bool:
        """Send email via Microsoft Graph API"""
        token = self.outlook_token
        if not token:
            logging.error("OUTLOOK_OAUTH_TOKEN not configured")
            return False

        def _send() -> bool:
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
            body = {
                "message": {
                    "subject": email_data.get("subject", ""),
                    "body": {
                        "contentType": "HTML",
                        "content": email_data.get("body", ""),
                    },
                    "toRecipients": [
                        {"emailAddress": {"address": email_data.get("to")}}
                    ],
                }
            }
            resp = requests.post(
                "https://graph.microsoft.com/v1.0/me/sendMail",
                headers=headers,
                json=body,
            )
            return resp.status_code in (200, 202)

        return await asyncio.to_thread(_send)

    async def _send_via_icloud(self, user_id: str, email_data: Dict[str, Any]) -> bool:
        """Send email via iCloud SMTP"""
        username = self.icloud_username
        password = self.icloud_app_password
        if not username or not password:
            logging.error("iCloud credentials not configured")
            return False

        def _send() -> bool:
            msg = EmailMessage()
            msg["From"] = username
            msg["To"] = email_data.get("to")
            msg["Subject"] = email_data.get("subject", "")
            msg.set_content(email_data.get("body", ""))
            with smtplib.SMTP_SSL("smtp.mail.me.com", 587) as smtp:
                smtp.login(username, password)
                smtp.sendmail(username, [email_data.get("to")], msg.as_string())
            return True

        return await asyncio.to_thread(_send)

    async def _handle_email_webhook(
        self, provider: str, user_id: str, webhook_data: Dict[str, Any]
    ) -> Optional[EmailEvent]:
        """Handle incoming email webhook from provider"""
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
                    "labels": webhook_data.get("labelIds", []),
                }

            elif provider == "outlook":
                # Microsoft Graph webhook format
                email_data = {
                    "id": webhook_data.get("id"),
                    "conversation_id": webhook_data.get("conversationId"),
                    "from": webhook_data.get("from", {})
                    .get("emailAddress", {})
                    .get("address"),
                    "to": [
                        addr.get("emailAddress", {}).get("address")
                        for addr in webhook_data.get("toRecipients", [])
                    ],
                    "subject": webhook_data.get("subject"),
                    "body": webhook_data.get("body", {}).get("content"),
                    "timestamp": webhook_data.get("receivedDateTime"),
                    "categories": webhook_data.get("categories", []),
                }

            else:
                logging.error(f"Unsupported email provider: {provider}")
                return None

            # Create email event
            return EmailEvent(
                timestamp=datetime.utcnow(),
                source="EmailConnectorDriver",
                type="email.received",
                user_id=user_id,
                operation="received",
                provider=provider,
                email_data=email_data,
            )

        except Exception as e:
            logging.error(f"Error handling email webhook: {e}")
            return None

    async def _process_incoming_email(self, email_event: EmailEvent) -> Optional[Event]:
        """Process incoming email and create appropriate events"""
        email_data = email_event.email_data

        # Create a processed email event for other drivers to handle
        return Event(
            timestamp=datetime.utcnow(),
            source="EmailConnectorDriver",
            type="email.processed",
            user_id=email_event.user_id,
            metadata={
                "email_id": email_data.get("id"),
                "from": email_data.get("from"),
                "subject": email_data.get("subject"),
                "body": email_data.get("body", "")[:1000],  # Truncate for metadata
                "provider": email_event.provider,
            },
        )


@driver(
    "calendar_connector",
    DriverType.IO,
    capabilities=[
        "calendar.create",
        "calendar.update",
        "calendar.delete",
        "calendar.webhook",
    ],
    name="Calendar Connector Driver",
    description="Calendar integration with multiple providers",
)
class CalendarConnectorDriver(IODriver):
    """Replaces EmailCalendarConnector Azure Function for calendar operations"""

    def __init__(
        self, manifest: DriverManifest, config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(manifest, config)
        self.gmail_token = os.environ.get("GMAIL_OAUTH_TOKEN")
        self.outlook_token = os.environ.get("OUTLOOK_OAUTH_TOKEN")
        self.icloud_username = os.environ.get("ICLOUD_USERNAME")
        self.icloud_app_password = os.environ.get("ICLOUD_APP_PASSWORD")

        # Initialize Lightning Runtime for provider abstraction
        self.runtime = LightningRuntime()

    def get_capabilities(self) -> List[str]:
        return [
            "calendar.create",
            "calendar.update",
            "calendar.delete",
            "calendar.webhook",
        ]

    def get_resource_requirements(self) -> ResourceSpec:
        return ResourceSpec(memory_mb=512, timeout_seconds=30)

    async def handle_event(self, event: Event) -> List[Event]:
        """Handle calendar-related events"""
        output_events = []

        if isinstance(event, CalendarEvent):
            if event.operation == "create":
                success = await self._execute_calendar_create(event)

                result_event = Event(
                    timestamp=datetime.utcnow(),
                    source="CalendarConnectorDriver",
                    type="calendar.created" if success else "calendar.create.failed",
                    user_id=event.user_id,
                    metadata={
                        "calendar_id": event.calendar_data.get("id"),
                        "title": event.calendar_data.get("title"),
                        "start_time": event.calendar_data.get("start_time"),
                        "success": success,
                    },
                )
                output_events.append(result_event)

            elif event.operation == "update":
                success = await self._execute_calendar_update(event)

                result_event = Event(
                    timestamp=datetime.utcnow(),
                    source="CalendarConnectorDriver",
                    type="calendar.updated" if success else "calendar.update.failed",
                    user_id=event.user_id,
                    metadata={
                        "calendar_id": event.calendar_data.get("id"),
                        "success": success,
                    },
                )
                output_events.append(result_event)

            elif event.operation == "delete":
                success = await self._execute_calendar_delete(event)

                result_event = Event(
                    timestamp=datetime.utcnow(),
                    source="CalendarConnectorDriver",
                    type="calendar.deleted" if success else "calendar.delete.failed",
                    user_id=event.user_id,
                    metadata={
                        "calendar_id": event.calendar_data.get("id"),
                        "success": success,
                    },
                )
                output_events.append(result_event)

        elif event.type == "calendar.webhook":
            # Handle webhook from calendar providers
            provider = event.metadata.get("provider")
            webhook_data = event.metadata.get("webhook_data", {})

            calendar_event = await self._handle_calendar_webhook(
                provider, event.user_id, webhook_data
            )
            if calendar_event:
                output_events.append(calendar_event)

        return output_events

    async def _execute_calendar_create(self, calendar_event: CalendarEvent) -> bool:
        """Execute calendar event creation"""
        provider = calendar_event.provider
        calendar_data = calendar_event.calendar_data
        user_id = calendar_event.user_id

        logging.info(f"Executing calendar create for user {user_id} via {provider}")
        logging.info(
            f"Title: {calendar_data.get('title')}, Start: {calendar_data.get('start_time')}"
        )

        try:
            if provider == "gmail":
                # Use Google Calendar API with stored OAuth token
                return await self._create_via_google_calendar(user_id, calendar_data)
            elif provider == "outlook":
                # Use Microsoft Graph API with stored OAuth token
                return await self._create_via_outlook_calendar(user_id, calendar_data)
            elif provider == "icloud":
                # Use CalDAV with stored credentials
                return await self._create_via_icloud_calendar(user_id, calendar_data)
            else:
                logging.error(f"Unsupported calendar provider: {provider}")
                return False

        except Exception as e:
            logging.error(f"Failed to create calendar event: {e}")
            return False

    async def _execute_calendar_update(self, calendar_event: CalendarEvent) -> bool:
        """Execute calendar event update"""
        # Similar implementation to create but for updates
        logging.info(f"Calendar update placeholder for {calendar_event.provider}")
        return True  # Placeholder

    async def _execute_calendar_delete(self, calendar_event: CalendarEvent) -> bool:
        """Execute calendar event deletion"""
        # Similar implementation to create but for deletions
        logging.info(f"Calendar delete placeholder for {calendar_event.provider}")
        return True  # Placeholder

    async def _create_via_google_calendar(
        self, user_id: str, calendar_data: Dict[str, Any]
    ) -> bool:
        """Create calendar event via Google Calendar API"""
        token = self.gmail_token
        if not token:
            logging.error("GMAIL_OAUTH_TOKEN not configured")
            return False

        def _create() -> bool:
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
            body = {
                "summary": calendar_data.get("title"),
                "description": calendar_data.get("description"),
                "start": {"dateTime": calendar_data.get("start_time")},
                "end": {"dateTime": calendar_data.get("end_time")},
            }
            resp = requests.post(
                "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                headers=headers,
                json=body,
            )
            return resp.status_code in (200, 201)

        return await asyncio.to_thread(_create)

    async def _create_via_outlook_calendar(
        self, user_id: str, calendar_data: Dict[str, Any]
    ) -> bool:
        """Create calendar event via Microsoft Graph API"""
        token = self.outlook_token
        if not token:
            logging.error("OUTLOOK_OAUTH_TOKEN not configured")
            return False

        def _create() -> bool:
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
            body = {
                "subject": calendar_data.get("title"),
                "body": {
                    "contentType": "HTML",
                    "content": calendar_data.get("description", ""),
                },
                "start": {"dateTime": calendar_data.get("start_time")},
                "end": {"dateTime": calendar_data.get("end_time")},
            }
            resp = requests.post(
                "https://graph.microsoft.com/v1.0/me/events",
                headers=headers,
                json=body,
            )
            return resp.status_code in (200, 201)

        return await asyncio.to_thread(_create)

    async def _create_via_icloud_calendar(
        self, user_id: str, calendar_data: Dict[str, Any]
    ) -> bool:
        """Create calendar event via iCloud CalDAV"""
        username = self.icloud_username
        password = self.icloud_app_password
        if not username or not password:
            logging.error("iCloud credentials not configured")
            return False

        def _create() -> bool:
            event_uid = str(uuid.uuid4())
            ics = (
                "BEGIN:VCALENDAR\n"
                "VERSION:2.0\n"
                "BEGIN:VEVENT\n"
                f"UID:{event_uid}\n"
                f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}\n"
                f"DTSTART:{calendar_data.get('start_time')}\n"
                f"DTEND:{calendar_data.get('end_time')}\n"
                f"SUMMARY:{calendar_data.get('title')}\n"
                f"DESCRIPTION:{calendar_data.get('description','')}\n"
                "END:VEVENT\n"
                "END:VCALENDAR"
            )
            headers = {"Content-Type": "text/calendar"}
            resp = requests.post(
                "https://caldav.icloud.com/",
                data=ics,
                headers=headers,
                auth=(username, password),
            )
            return resp.status_code in (200, 201, 204)

        return await asyncio.to_thread(_create)

    async def _handle_calendar_webhook(
        self, provider: str, user_id: str, webhook_data: Dict[str, Any]
    ) -> Optional[CalendarEvent]:
        """Handle incoming calendar webhook from provider"""
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
                    "attendees": [
                        att.get("email") for att in webhook_data.get("attendees", [])
                    ],
                    "location": webhook_data.get("location"),
                    "status": webhook_data.get("status"),
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
                    "attendees": [
                        att.get("emailAddress", {}).get("address")
                        for att in webhook_data.get("attendees", [])
                    ],
                    "location": webhook_data.get("location", {}).get("displayName"),
                    "status": webhook_data.get("showAs"),
                }

            else:
                logging.error(f"Unsupported calendar provider: {provider}")
                return None

            # Create calendar event
            return CalendarEvent(
                timestamp=datetime.utcnow(),
                source="CalendarConnectorDriver",
                type="calendar.received",
                user_id=user_id,
                operation="received",
                provider=provider,
                calendar_data=calendar_data,
            )

        except Exception as e:
            logging.error(f"Error handling calendar webhook: {e}")
            return None


@driver(
    "user_messenger",
    DriverType.IO,
    capabilities=["message.send", "notification.deliver"],
    name="User Messenger Driver",
    description="User messaging and notification delivery",
)
class UserMessengerDriver(IODriver):
    """Replaces UserMessenger Azure Function"""

    def __init__(
        self, manifest: DriverManifest, config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(manifest, config)
        # Initialize Lightning Runtime for provider abstraction
        self.runtime = LightningRuntime()

    def get_capabilities(self) -> List[str]:
        return ["message.send", "notification.deliver"]

    def get_resource_requirements(self) -> ResourceSpec:
        return ResourceSpec(memory_mb=256, timeout_seconds=15)

    async def handle_event(self, event: Event) -> List[Event]:
        """Handle messaging and notification events"""
        output_events = []

        if event.type == "message.send":
            # Handle direct message sending
            recipient = event.metadata.get("recipient")
            message = event.metadata.get("message")
            channel = event.metadata.get("channel", "default")

            success = await self._send_message(
                event.user_id, recipient, message, channel
            )

            result_event = Event(
                timestamp=datetime.utcnow(),
                source="UserMessengerDriver",
                type="message.sent" if success else "message.failed",
                user_id=event.user_id,
                metadata={
                    "recipient": recipient,
                    "channel": channel,
                    "success": success,
                },
            )
            output_events.append(result_event)

        elif event.type == "notification.deliver":
            # Handle notification delivery
            notification_data = event.metadata

            success = await self._deliver_notification(event.user_id, notification_data)

            result_event = Event(
                timestamp=datetime.utcnow(),
                source="UserMessengerDriver",
                type="notification.delivered" if success else "notification.failed",
                user_id=event.user_id,
                metadata={
                    "notification_id": notification_data.get("id"),
                    "channel": notification_data.get("channel"),
                    "success": success,
                },
            )
            output_events.append(result_event)

        return output_events

    async def _send_message(
        self, user_id: str, recipient: str, message: str, channel: str
    ) -> bool:
        """Send a message via specified channel"""
        try:
            if channel == "email":
                # Send via email
                return await self._send_email_message(user_id, recipient, message)
            elif channel == "sms":
                # Send via SMS
                return await self._send_sms_message(user_id, recipient, message)
            elif channel == "slack":
                # Send via Slack
                return await self._send_slack_message(user_id, recipient, message)
            elif channel == "teams":
                # Send via Microsoft Teams
                return await self._send_teams_message(user_id, recipient, message)
            else:
                logging.error(f"Unsupported message channel: {channel}")
                return False
        except Exception as e:
            logging.error(f"Failed to send message: {e}")
            return False

    async def _deliver_notification(
        self, user_id: str, notification_data: Dict[str, Any]
    ) -> bool:
        """Deliver notification via appropriate channels"""
        try:
            channels = notification_data.get("channels", ["default"])
            title = notification_data.get("title", "Notification")
            message = notification_data.get("message", "")
            priority = notification_data.get("priority", "normal")

            success_count = 0
            for channel in channels:
                if await self._send_notification_via_channel(
                    user_id, channel, title, message, priority
                ):
                    success_count += 1

            return success_count > 0
        except Exception as e:
            logging.error(f"Failed to deliver notification: {e}")
            return False

    async def _send_email_message(
        self, user_id: str, recipient: str, message: str
    ) -> bool:
        """Send message via email"""
        # TODO: Integrate with email connector
        logging.info(f"Email message placeholder: {user_id} -> {recipient}")
        return True  # Placeholder

    async def _send_sms_message(
        self, user_id: str, recipient: str, message: str
    ) -> bool:
        """Send message via SMS"""
        # TODO: Integrate with SMS provider (Twilio, etc.)
        logging.info(f"SMS message placeholder: {user_id} -> {recipient}")
        return True  # Placeholder

    async def _send_slack_message(
        self, user_id: str, recipient: str, message: str
    ) -> bool:
        """Send message via Slack"""
        # TODO: Integrate with Slack API
        logging.info(f"Slack message placeholder: {user_id} -> {recipient}")
        return True  # Placeholder

    async def _send_teams_message(
        self, user_id: str, recipient: str, message: str
    ) -> bool:
        """Send message via Microsoft Teams"""
        # TODO: Integrate with Teams API
        logging.info(f"Teams message placeholder: {user_id} -> {recipient}")
        return True  # Placeholder

    async def _send_notification_via_channel(
        self, user_id: str, channel: str, title: str, message: str, priority: str
    ) -> bool:
        """Send notification via specific channel"""
        try:
            if channel == "push":
                # Send push notification
                return await self._send_push_notification(
                    user_id, title, message, priority
                )
            elif channel == "email":
                # Send email notification
                return await self._send_email_notification(user_id, title, message)
            elif channel == "sms":
                # Send SMS notification
                return await self._send_sms_notification(user_id, title, message)
            elif channel == "in_app":
                # Send in-app notification
                return await self._send_in_app_notification(user_id, title, message)
            else:
                logging.warning(f"Unknown notification channel: {channel}")
                return False
        except Exception as e:
            logging.error(f"Failed to send notification via {channel}: {e}")
            return False

    async def _send_push_notification(
        self, user_id: str, title: str, message: str, priority: str
    ) -> bool:
        """Send push notification"""
        # TODO: Integrate with push notification service
        logging.info(f"Push notification placeholder for {user_id}: {title}")
        return True  # Placeholder

    async def _send_email_notification(
        self, user_id: str, title: str, message: str
    ) -> bool:
        """Send email notification"""
        # TODO: Integrate with email connector
        logging.info(f"Email notification placeholder for {user_id}: {title}")
        return True  # Placeholder

    async def _send_sms_notification(
        self, user_id: str, title: str, message: str
    ) -> bool:
        """Send SMS notification"""
        # TODO: Integrate with SMS provider
        logging.info(f"SMS notification placeholder for {user_id}: {title}")
        return True  # Placeholder

    async def _send_in_app_notification(
        self, user_id: str, title: str, message: str
    ) -> bool:
        """Send in-app notification"""
        # TODO: Integrate with real-time notification system
        logging.info(f"In-app notification placeholder for {user_id}: {title}")
        return True  # Placeholder


@driver(
    "voice_call",
    DriverType.IO,
    capabilities=["voice.call"],
    name="Voice Call Driver",
    description="Initiate outbound phone calls via Twilio",
)
class VoiceCallDriver(IODriver):
    """Driver that launches a voice agent container for phone calls."""

    def __init__(
        self, manifest: DriverManifest, config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(manifest, config)
        self.cosmos_db = os.environ.get("COSMOS_DATABASE", "vextir")
        self.call_container = os.environ.get("CALL_CONTAINER", "calls")
        self.aci_region = os.environ.get("ACI_REGION", "centralindia")
        self.voice_image = os.environ.get("VOICE_IMAGE", "voice-agent")

        # Initialize Lightning Runtime for provider abstraction
        self.runtime = LightningRuntime()

    def get_capabilities(self) -> List[str]:
        return ["voice.call"]

    def get_resource_requirements(self) -> ResourceSpec:
        return ResourceSpec(memory_mb=1024, timeout_seconds=60)

    async def handle_event(self, event: Event) -> List[Event]:
        output_events = []

        if event.type != "voice.call":
            return output_events

        if not hasattr(event, "phone"):
            try:
                v_event = VoiceCallEvent.from_dict(event.to_dict())
            except Exception:
                logging.error("Invalid voice call event")
                return output_events
        else:
            v_event = event

        call_id = uuid.uuid4().hex
        
        # Store call record using abstracted storage
        from lightning_core.abstractions import Document
        call_doc = Document(
            id=call_id,
            partition_key=v_event.user_id,
            data={
                "phone": v_event.phone,
                "objective": v_event.objective,
                "status": "pending",
                "created_at": datetime.utcnow().isoformat(),
            }
        )
        
        try:
            await self.runtime.storage.create_document(self.call_container, call_doc)
        except Exception as e:
            logging.error("Failed to record call: %s", e)

        result = ""
        container_name = None
        try:
            # Create container configuration using abstraction
            container_config = ContainerConfig(
                name="voice",
                image=self.voice_image,
                environment_variables={
                    "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", ""),
                    "COSMOS_DATABASE": self.cosmos_db,
                    "CALL_CONTAINER": self.call_container,
                    "OUTBOUND_TO": v_event.phone,
                    "OBJECTIVE": v_event.objective or "",
                    "PUBLIC_URL": os.environ.get("PUBLIC_URL", ""),
                    "TWILIO_ACCOUNT_SID": os.environ.get("TWILIO_ACCOUNT_SID", ""),
                    "TWILIO_AUTH_TOKEN": os.environ.get("TWILIO_AUTH_TOKEN", ""),
                    "TWILIO_FROM_NUMBER": os.environ.get("TWILIO_FROM_NUMBER", ""),
                },
                resources=ResourceRequirements(cpu=1.0, memory_gb=1.0),
                restart_policy="Never"
            )
            
            container_name = f"voice-{call_id[:8]}"
            container = await self.runtime.container_runtime.create_container(
                container_name, container_config
            )
            
            # Update call record
            call_doc.data.update({
                "container_id": container.id,
                "status": "started",
                "updated_at": datetime.utcnow().isoformat(),
            })
            await self.runtime.storage.update_document(self.call_container, call_doc)
            result = "started"
            
        except Exception as e:
            call_doc.data.update({
                "status": "error",
                "updated_at": datetime.utcnow().isoformat(),
            })
            try:
                await self.runtime.storage.update_document(self.call_container, call_doc)
            except Exception:
                pass
            result = f"error: {e}"

        out_event = Event(
            timestamp=datetime.utcnow(),
            source="VoiceCallDriver",
            type="voice.call.started",
            user_id=v_event.user_id,
            metadata={"result": result, "callId": call_id},
            history=v_event.history + [v_event.to_dict()],
        )

        # Send event using abstracted event bus
        try:
            event_message = EventMessage(
                event_type=out_event.type,
                data=out_event.to_dict(),
                metadata={"topic": out_event.type}
            )
            await self.runtime.event_bus.publish(event_message)
        except Exception as e:
            logging.error(f"Failed to publish event: {e}")

        output_events.append(out_event)
        return output_events
