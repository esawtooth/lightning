import json
import os
import uuid
from datetime import datetime

import azure.functions as func
from azure.data.tables import TableServiceClient
from croniter import croniter

from events import Event

STORAGE_CONN = os.environ.get("STORAGE_CONNECTION")
SCHEDULE_TABLE = os.environ.get("SCHEDULE_TABLE", "schedules")

service = TableServiceClient.from_connection_string(STORAGE_CONN)
_table = service.get_table_client(SCHEDULE_TABLE)
_table.create_table_if_not_exists()


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()
    except ValueError:
        return func.HttpResponse("Invalid JSON", status_code=400)

    user_id = req.headers.get("x-user-id")
    if not user_id:
        return func.HttpResponse("Missing user ID", status_code=400)

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
        "PartitionKey": user_id,
        "RowKey": sched_id,
        "event": json.dumps(event_payload),
        "cron": cron_expr or "",
        "runAt": next_time.isoformat(),
    }
    _table.upsert_entity(entity)

    return func.HttpResponse(
        json.dumps({"id": sched_id}),
        status_code=201,
        mimetype="application/json",
    )
