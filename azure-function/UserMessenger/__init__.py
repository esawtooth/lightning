import json
import logging
import os

import azure.functions as func
import requests

from events import Event
from events.utils import event_matches

NOTIFY_URL = os.environ.get("NOTIFY_URL")
NOTIFY_TOKEN = os.environ.get("NOTIFY_TOKEN")

if not NOTIFY_URL:
    logging.error("Missing required environment variable: NOTIFY_URL")
    raise RuntimeError("Azure Function misconfigured")


def main(msg: func.ServiceBusMessage) -> None:
    body = msg.get_body().decode("utf-8")
    try:
        data = json.loads(body)
        event = Event.from_dict(data)
    except Exception as e:
        logging.error("Invalid event: %s", e)
        return

    if event_matches(event.type, "user.message"):
        text = event.metadata.get("message")
        if not text:
            logging.error("user.message event missing 'message'")
            return
    elif event_matches(event.type, "llm.chat.response"):
        text = event.metadata.get("reply")
        if not text:
            logging.error("llm.chat.response event missing 'reply'")
            return
    else:
        return

    if not NOTIFY_URL:
        logging.info("User %s says: %s", event.user_id, text)
        return

    try:
        headers = {"Authorization": f"Bearer {NOTIFY_TOKEN}"} if NOTIFY_TOKEN else None
        resp = requests.post(NOTIFY_URL, json={"user_id": event.user_id, "message": text}, headers=headers)
        if not 200 <= resp.status_code < 300:
            logging.warning("Notify endpoint returned status %s: %s", resp.status_code, resp.text)
    except Exception as e:
        logging.error("Failed to notify user: %s", e)

