import json
import logging
import os
import uuid

from azure.identity import DefaultAzureCredential
from azure.mgmt.containerinstance import ContainerInstanceManagementClient
from azure.mgmt.containerinstance.models import (
    Container,
    ContainerGroup,
    ContainerGroupRestartPolicy,
    EnvironmentVariable,
    OperatingSystemTypes,
    ResourceRequests,
    ResourceRequirements,
)
from datetime import datetime

import azure.functions as func
from azure.data.tables import TableServiceClient
from azure.servicebus import ServiceBusClient, ServiceBusMessage

from events import Event, WorkerTaskEvent

STORAGE_CONN = os.environ.get("STORAGE_CONNECTION")
REPO_TABLE = os.environ.get("REPO_TABLE", "repos")
SERVICEBUS_CONN = os.environ.get("SERVICEBUS_CONNECTION")
SERVICEBUS_QUEUE = os.environ.get("SERVICEBUS_QUEUE")
ACI_RESOURCE_GROUP = os.environ.get("ACI_RESOURCE_GROUP")
ACI_SUBSCRIPTION_ID = os.environ.get("ACI_SUBSCRIPTION_ID")
ACI_REGION = os.environ.get("ACI_REGION", "centralindia")

_table_service = TableServiceClient.from_connection_string(STORAGE_CONN)
_repo_table = _table_service.get_table_client(REPO_TABLE)
_sb_client = ServiceBusClient.from_connection_string(SERVICEBUS_CONN)
_credential = DefaultAzureCredential()
_aci_client = None
if ACI_RESOURCE_GROUP and ACI_SUBSCRIPTION_ID:
    _aci_client = ContainerInstanceManagementClient(_credential, ACI_SUBSCRIPTION_ID)


WORKER_IMAGE = os.environ.get("WORKER_IMAGE", "worker-task")


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

    if repo and not event.repo_url:
        event.repo_url = repo

    result = ""
    try:
        if not _aci_client:
            raise RuntimeError("ACI client not configured")
        env_list = [
            EnvironmentVariable(name="SERVICEBUS_CONNECTION", value=SERVICEBUS_CONN or ""),
            EnvironmentVariable(name="SERVICEBUS_QUEUE", value=SERVICEBUS_QUEUE or ""),
            EnvironmentVariable(name="WORKER_EVENT", value=json.dumps(event.to_dict())),
        ]
        container = Container(
            name="worker",
            image=WORKER_IMAGE,
            resources=ResourceRequirements(requests=ResourceRequests(cpu=1.0, memory_in_gb=1.0)),
            environment_variables=env_list,
        )
        group = ContainerGroup(
            location=ACI_REGION,
            os_type=OperatingSystemTypes.LINUX,
            restart_policy=ContainerGroupRestartPolicy.NEVER,
            containers=[container],
        )
        group_name = f"worker-{uuid.uuid4().hex[:8]}"
        _aci_client.container_groups.begin_create_or_update(ACI_RESOURCE_GROUP, group_name, group).result()
        result = "started"
    except Exception as e:
        result = f"error: {e}"

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
