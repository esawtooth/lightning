import json
import os
from datetime import datetime

import azure.functions as func
from azure.data.tables import TableServiceClient
from azure.servicebus import ServiceBusClient, ServiceBusMessage
from croniter import croniter

STORAGE_CONN = os.environ.get("STORAGE_CONNECTION")
SCHEDULE_TABLE = os.environ.get("SCHEDULE_TABLE", "schedules")
SERVICEBUS_CONN = os.environ.get("SERVICEBUS_CONNECTION")
SERVICEBUS_QUEUE = os.environ.get("SERVICEBUS_QUEUE")

service = TableServiceClient.from_connection_string(STORAGE_CONN)
_table = service.get_table_client(SCHEDULE_TABLE)
_servicebus = ServiceBusClient.from_connection_string(SERVICEBUS_CONN)


def main(mytimer: func.TimerRequest) -> None:
    now = datetime.utcnow()
    due_filter = f"runAt le '{now.isoformat()}'"
    entities = list(_table.query_entities(due_filter))
    for ent in entities:
        event = json.loads(ent["event"])
        msg = ServiceBusMessage(json.dumps(event))
        msg.application_properties = {"topic": event["type"]}
        with _servicebus:
            sender = _servicebus.get_queue_sender(queue_name=SERVICEBUS_QUEUE)
            with sender:
                sender.send_messages(msg)
        if ent.get("cron"):
            next_time = croniter(ent["cron"], now).get_next(datetime)
            ent["runAt"] = next_time.isoformat()
            _table.update_entity(ent)
        else:
            _table.delete_entity(ent["PartitionKey"], ent["RowKey"])
