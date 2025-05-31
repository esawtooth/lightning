import json
import logging
import os

import azure.functions as func
import requests

from events import Event
from events.utils import event_matches

NOTIFY_URL = os.environ.get("NOTIFY_URL")


def main(msg: func.ServiceBusMessage) -> None:
    body = msg.get_body().decode("utf-8")
    try:
        data = json.loads(body)
        event = Event.from_dict(data)
    except Exception as e:
        logging.error("Invalid event: %s", e)
        return

    if not event_matches(event.type, "user.message"):
        return

    user_text = event.metadata.get("message")
    if not user_text:
        logging.error("user.message event missing 'message'")
        return

    if not NOTIFY_URL:
        logging.info("User %s says: %s", event.user_id, user_text)
        return

    try:
        requests.post(NOTIFY_URL, json={"user_id": event.user_id, "message": user_text})
    except Exception as e:
        logging.error("Failed to notify user: %s", e)

