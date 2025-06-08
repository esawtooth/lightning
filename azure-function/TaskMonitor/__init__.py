import json
import os

import azure.functions as func
from azure.cosmos import CosmosClient, PartitionKey
from azure.identity import DefaultAzureCredential
from azure.mgmt.containerinstance import ContainerInstanceManagementClient

from auth import verify_token

COSMOS_CONN = os.environ.get("COSMOS_CONNECTION")
COSMOS_DB = os.environ.get("COSMOS_DATABASE", "vextir")
TASK_CONTAINER = os.environ.get("TASK_CONTAINER", "tasks")
ACI_RESOURCE_GROUP = os.environ.get("ACI_RESOURCE_GROUP")
ACI_SUBSCRIPTION_ID = os.environ.get("ACI_SUBSCRIPTION_ID")

_client = CosmosClient.from_connection_string(COSMOS_CONN)
_db = _client.create_database_if_not_exists(COSMOS_DB)
_container = _db.create_container_if_not_exists(
    id=TASK_CONTAINER, partition_key=PartitionKey(path="/pk")
)

_aci_client = None
if ACI_RESOURCE_GROUP and ACI_SUBSCRIPTION_ID:
    _aci_client = ContainerInstanceManagementClient(
        DefaultAzureCredential(), ACI_SUBSCRIPTION_ID
    )


def _get_logs(group: str) -> str:
    if not _aci_client or not group:
        return ""
    try:
        logs = _aci_client.containers.list_logs(
            ACI_RESOURCE_GROUP, group, "worker"
        )
        return getattr(logs, "content", getattr(logs, "log_content", ""))
    except Exception as e:
        return f"error: {e}"


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        user_id = verify_token(req.headers.get("Authorization"))
    except Exception:
        return func.HttpResponse("Unauthorized", status_code=401)

    task_id = req.route_params.get("task_id")
    if task_id:
        try:
            entity = _container.read_item(task_id, partition_key=user_id)
        except Exception:
            return func.HttpResponse("Not found", status_code=404)
        entity["logs"] = _get_logs(entity.get("container_group"))
        return func.HttpResponse(
            json.dumps(entity), status_code=200, mimetype="application/json"
        )

    query = "SELECT * FROM c WHERE c.pk = @u ORDER BY c.created_at DESC"
    items = list(
        _container.query_items(
            query,
            parameters=[{"name": "@u", "value": user_id}],
            enable_cross_partition_query=True,
        )
    )
    return func.HttpResponse(
        json.dumps(items), status_code=200, mimetype="application/json"
    )
