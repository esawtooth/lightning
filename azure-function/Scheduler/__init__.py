import json
import os
import uuid
from datetime import datetime

import azure.functions as func
from azure.cosmos import CosmosClient, PartitionKey
from croniter import croniter

from events import Event
from simple_auth import get_user_id_permissive

COSMOS_CONN = os.environ.get("COSMOS_CONNECTION")
COSMOS_DB = os.environ.get("COSMOS_DATABASE", "vextir")
SCHEDULE_CONTAINER = os.environ.get("SCHEDULE_CONTAINER", "schedules")

_client = CosmosClient.from_connection_string(COSMOS_CONN)
_db = _client.create_database_if_not_exists(COSMOS_DB)
_container = _db.create_container_if_not_exists(
    id=SCHEDULE_CONTAINER, partition_key=PartitionKey(path="/pk")
)


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()
    except ValueError:
        return func.HttpResponse("Invalid JSON", status_code=400)

    try:
        user_id = get_user_id_permissive(req)
    except Exception:
        return func.HttpResponse("Unauthorized", status_code=401)

    event_payload = data.get("event")
    cron_expr = data.get("cron")
    run_at = data.get("timestamp")

    if not event_payload:
        return func.HttpResponse("Missing event payload", status_code=400)
    if not cron_expr and not run_at:
        return func.HttpResponse("Missing schedule", status_code=400)

    event_payload["userID"] = user_id
    try:
        Event.from_dict(event_payload)
    except ValueError as e:
        return func.HttpResponse(str(e), status_code=400)

    if run_at:
        try:
            next_time = datetime.fromisoformat(run_at)
        except Exception:
            return func.HttpResponse("Invalid timestamp", status_code=400)
    else:
        try:
            next_time = croniter(cron_expr, datetime.utcnow()).get_next(datetime)
        except Exception:
            return func.HttpResponse("Invalid cron expression", status_code=400)

    sched_id = uuid.uuid4().hex
    entity = {
        "id": sched_id,
        "pk": user_id,
        "event": json.dumps(event_payload),
        "cron": cron_expr or "",
        "runAt": next_time.isoformat(),
    }
    _container.upsert_item(entity)

    return func.HttpResponse(
        json.dumps({"id": sched_id}),
        status_code=201,
        mimetype="application/json",
    )
