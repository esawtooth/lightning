import json
import logging
import os
from datetime import datetime

import azure.functions as func
from azure.eventhub import EventHubProducerClient, EventData

from events import Event

EVENTHUB_CONN = os.environ.get("EVENTHUB_CONNECTION")

producer = EventHubProducerClient.from_connection_string(EVENTHUB_CONN)


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()
    except ValueError:
        return func.HttpResponse("Invalid JSON", status_code=400)

    try:
        event = Event.from_dict(data)
    except ValueError as e:
        return func.HttpResponse(str(e), status_code=400)

    event_data = EventData(json.dumps(event.to_dict()))
    event_data.properties = {"topic": event.type}
    try:
        with producer:
            producer.send_batch([event_data])
    except Exception as e:
        logging.error("Failed to send event: %s", e)
        return func.HttpResponse("Failed to queue event", status_code=500)

    return func.HttpResponse("Queued", status_code=202)
