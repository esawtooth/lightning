import json
import os
from datetime import datetime

import azure.functions as func
from azure.cosmos import CosmosClient, PartitionKey
from azure.servicebus import ServiceBusClient, ServiceBusMessage
from croniter import croniter

COSMOS_CONN = os.environ.get("COSMOS_CONNECTION")
COSMOS_DB = os.environ.get("COSMOS_DATABASE", "lightning")
SCHEDULE_CONTAINER = os.environ.get("SCHEDULE_CONTAINER", "schedules")
SERVICEBUS_CONN = os.environ.get("SERVICEBUS_CONNECTION")
SERVICEBUS_QUEUE = os.environ.get("SERVICEBUS_QUEUE")

_client = CosmosClient.from_connection_string(COSMOS_CONN)
_db = _client.create_database_if_not_exists(COSMOS_DB)
_container = _db.create_container_if_not_exists(
    id=SCHEDULE_CONTAINER, partition_key=PartitionKey(path="/pk")
)
_servicebus = ServiceBusClient.from_connection_string(SERVICEBUS_CONN)


def main(mytimer: func.TimerRequest) -> None:
    now = datetime.utcnow()
    query = "SELECT * FROM c WHERE c.runAt <= @t"
    entities = list(
        _container.query_items(
            query,
            parameters=[{"name": "@t", "value": now.isoformat()}],
            enable_cross_partition_query=True,
        )
    )
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
            _container.upsert_item(ent)
        else:
            _container.delete_item(ent["id"], partition_key=ent["pk"])
