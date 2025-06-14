import json
import logging
import os
from datetime import datetime

import azure.functions as func
from azure.servicebus import ServiceBusClient, ServiceBusMessage

from events import Event
from simple_auth import get_user_id_permissive

SERVICEBUS_CONN = os.environ.get("SERVICEBUS_CONNECTION")
SERVICEBUS_QUEUE = os.environ.get("SERVICEBUS_QUEUE")

client = None
if SERVICEBUS_CONN:
    client = ServiceBusClient.from_connection_string(SERVICEBUS_CONN)


def main(req: func.HttpRequest) -> func.HttpResponse:
    missing = []
    if not SERVICEBUS_CONN:
        missing.append("SERVICEBUS_CONNECTION")
    if not SERVICEBUS_QUEUE:
        missing.append("SERVICEBUS_QUEUE")
    if missing:
        logging.error("Missing required environment variable(s): %s", ", ".join(missing))
        return func.HttpResponse("Service not configured", status_code=500)

    try:
        data = req.get_json()
    except ValueError:
        return func.HttpResponse("Invalid JSON", status_code=400)

    try:
        user_id = get_user_id_permissive(req)
    except Exception:
        return func.HttpResponse("Unauthorized", status_code=401)
    data["userID"] = user_id

    try:
        event = Event.from_dict(data)
    except ValueError as e:
        return func.HttpResponse(str(e), status_code=400)

    message = ServiceBusMessage(json.dumps(event.to_dict()))
    message.application_properties = {"topic": event.type}
    try:
        with client:
            sender = client.get_queue_sender(queue_name=SERVICEBUS_QUEUE)
            with sender:
                sender.send_messages(message)
    except Exception as e:
        logging.error("Failed to send event: %s", e)
        return func.HttpResponse("Failed to queue event", status_code=500)

    return func.HttpResponse("Queued", status_code=202)
