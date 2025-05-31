import json
import logging
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
import uuid

import azure.functions as func
from azure.data.tables import TableServiceClient
from azure.servicebus import ServiceBusClient, ServiceBusMessage

from events import Event, WorkerTaskEvent

STORAGE_CONN = os.environ.get("STORAGE_CONNECTION")
REPO_TABLE = os.environ.get("REPO_TABLE", "repos")
SERVICEBUS_CONN = os.environ.get("SERVICEBUS_CONNECTION")
SERVICEBUS_QUEUE = os.environ.get("SERVICEBUS_QUEUE")

_table_service = TableServiceClient.from_connection_string(STORAGE_CONN)
_repo_table = _table_service.get_table_client(REPO_TABLE)
_sb_client = ServiceBusClient.from_connection_string(SERVICEBUS_CONN)


def main(msg: func.ServiceBusMessage) -> None:
    body = msg.get_body().decode("utf-8")
    try:
        data = json.loads(body)
        event = WorkerTaskEvent.from_dict(data)
    except Exception as e:
        logging.error("Invalid event: %s", e)
        return

    repo = event.repo_url
    if not repo:
        try:
            ent = _repo_table.get_entity(event.user_id, "repo")
            repo = ent["repo"]
        except Exception as e:
            logging.error("Repo not found for user %s: %s", event.user_id, e)
            return

    workdir = tempfile.mkdtemp(prefix="repo")
    image_tag = f"task-{event.user_id}-{uuid.uuid4().hex[:8]}"
    result = ""
    try:
        subprocess.run(["git", "clone", repo, workdir], check=True)
        subprocess.run(["docker", "build", "-t", image_tag, workdir], check=True)
        env = os.environ.copy()
        env.update(
            {
                "SERVICEBUS_CONNECTION": SERVICEBUS_CONN or "",
                "SERVICEBUS_QUEUE": SERVICEBUS_QUEUE or "",
                "WORKER_EVENT": json.dumps(event.to_dict()),
            }
        )
        subprocess.run(
            ["docker", "run", "-d", "--rm", image_tag], env=env, check=True
        )
        result = "started"
    except subprocess.CalledProcessError as e:
        result = f"error: {e}"
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    out_event = Event(
        timestamp=datetime.utcnow(),
        source="WorkerTaskRunner",
        type="worker.task.result",
        user_id=event.user_id,
        metadata={"result": result},
    )

    message = ServiceBusMessage(json.dumps(out_event.to_dict()))
    message.application_properties = {"topic": out_event.type}
    with _sb_client:
        sender = _sb_client.get_queue_sender(queue_name=SERVICEBUS_QUEUE)
        with sender:
            sender.send_messages(message)
