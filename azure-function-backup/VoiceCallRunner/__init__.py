import json
import logging
import os
import uuid
from datetime import datetime

import azure.functions as func
from azure.cosmos import CosmosClient, PartitionKey
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
from azure.servicebus import ServiceBusClient, ServiceBusMessage

from events import Event, VoiceCallEvent

COSMOS_CONN = os.environ.get("COSMOS_CONNECTION")
COSMOS_DB = os.environ.get("COSMOS_DATABASE", "vextir")
CALL_CONTAINER = os.environ.get("CALL_CONTAINER", "calls")
SERVICEBUS_CONN = os.environ.get("SERVICEBUS_CONNECTION")
SERVICEBUS_QUEUE = os.environ.get("SERVICEBUS_QUEUE")
ACI_RESOURCE_GROUP = os.environ.get("ACI_RESOURCE_GROUP")
ACI_SUBSCRIPTION_ID = os.environ.get("ACI_SUBSCRIPTION_ID")
ACI_REGION = os.environ.get("ACI_REGION", "centralindia")
VOICE_IMAGE = os.environ.get("VOICE_IMAGE", "voice-agent")

_client = CosmosClient.from_connection_string(COSMOS_CONN)
_db = _client.create_database_if_not_exists(COSMOS_DB)
_call_container = _db.create_container_if_not_exists(
    id=CALL_CONTAINER, partition_key=PartitionKey(path="/pk")
)
_sb_client = ServiceBusClient.from_connection_string(SERVICEBUS_CONN)
_credential = DefaultAzureCredential()
_aci_client = None
if ACI_RESOURCE_GROUP and ACI_SUBSCRIPTION_ID:
    _aci_client = ContainerInstanceManagementClient(_credential, ACI_SUBSCRIPTION_ID)


def main(msg: func.ServiceBusMessage) -> None:
    body = msg.get_body().decode("utf-8")
    try:
        data = json.loads(body)
        event = VoiceCallEvent.from_dict(data)
    except Exception as e:
        logging.error("Invalid event: %s", e)
        return

    call_id = uuid.uuid4().hex
    entity = {
        "id": call_id,
        "pk": event.user_id,
        "phone": event.phone,
        "objective": event.objective,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
    }
    try:
        _call_container.upsert_item(entity)
    except Exception as e:
        logging.error("Failed to record call: %s", e)

    result = ""
    group_name = None
    try:
        if not _aci_client:
            raise RuntimeError("ACI client not configured")
        env_list = [
            EnvironmentVariable(name="OPENAI_API_KEY", value=os.environ.get("OPENAI_API_KEY", "")),
            EnvironmentVariable(name="SERVICEBUS_CONNECTION", value=SERVICEBUS_CONN or ""),
            EnvironmentVariable(name="SERVICEBUS_QUEUE", value=SERVICEBUS_QUEUE or ""),
            EnvironmentVariable(name="COSMOS_CONNECTION", value=COSMOS_CONN or ""),
            EnvironmentVariable(name="COSMOS_DATABASE", value=COSMOS_DB),
            EnvironmentVariable(name="CALL_CONTAINER", value=CALL_CONTAINER),
            EnvironmentVariable(name="OUTBOUND_TO", value=event.phone),
            EnvironmentVariable(name="OBJECTIVE", value=event.objective or ""),
            EnvironmentVariable(name="PUBLIC_URL", value=os.environ.get("PUBLIC_URL", "")),
            EnvironmentVariable(name="TWILIO_ACCOUNT_SID", value=os.environ.get("TWILIO_ACCOUNT_SID", "")),
            EnvironmentVariable(name="TWILIO_AUTH_TOKEN", value=os.environ.get("TWILIO_AUTH_TOKEN", "")),
            EnvironmentVariable(name="TWILIO_FROM_NUMBER", value=os.environ.get("TWILIO_FROM_NUMBER", "")),
        ]
        container = Container(
            name="voice",
            image=VOICE_IMAGE,
            resources=ResourceRequirements(
                requests=ResourceRequests(cpu=1.0, memory_in_gb=1.0)
            ),
            environment_variables=env_list,
        )
        group = ContainerGroup(
            location=ACI_REGION,
            os_type=OperatingSystemTypes.LINUX,
            restart_policy=ContainerGroupRestartPolicy.NEVER,
            containers=[container],
        )
        group_name = f"voice-{call_id[:8]}"
        _aci_client.container_groups.begin_create_or_update(
            ACI_RESOURCE_GROUP, group_name, group
        ).result()
        entity["container_group"] = group_name
        entity["status"] = "started"
        entity["updated_at"] = datetime.utcnow().isoformat()
        _call_container.upsert_item(entity)
        result = "started"
    except Exception as e:
        entity["status"] = "error"
        entity["updated_at"] = datetime.utcnow().isoformat()
        try:
            _call_container.upsert_item(entity)
        except Exception:
            pass
        result = f"error: {e}"

    out_event = Event(
        timestamp=datetime.utcnow(),
        source="VoiceCallRunner",
        type="voice.call.started",
        user_id=event.user_id,
        metadata={"result": result, "callId": call_id},
        history=event.history + [event.to_dict()],
    )

    message = ServiceBusMessage(json.dumps(out_event.to_dict()))
    message.application_properties = {"topic": out_event.type}
    with _sb_client:
        sender = _sb_client.get_queue_sender(queue_name=SERVICEBUS_QUEUE)
        with sender:
            sender.send_messages(message)
        if _aci_client and group_name:
            try:
                _aci_client.container_groups.begin_delete(
                    ACI_RESOURCE_GROUP, group_name
                )
            except Exception:
                pass

