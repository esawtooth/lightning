import json
import os

import azure.functions as func
from azure.cosmos import CosmosClient, PartitionKey

from auth import verify_token

COSMOS_CONN = os.environ.get("COSMOS_CONNECTION")
COSMOS_DB = os.environ.get("COSMOS_DATABASE", "lightning")
POLICY_CONTAINER = os.environ.get("POLICY_CONTAINER", "policies")

_client = CosmosClient.from_connection_string(COSMOS_CONN)
_db = _client.create_database_if_not_exists(COSMOS_DB)
_container = _db.create_container_if_not_exists(
    id=POLICY_CONTAINER, partition_key=PartitionKey(path="/pk")
)


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        user_id = verify_token(req.headers.get("Authorization"))
    except Exception:
        return func.HttpResponse("Unauthorized", status_code=401)

    if req.method == "GET":
        try:
            entity = _container.read_item("policy", partition_key=user_id)
            policy = entity.get("policy", {})
        except Exception:
            policy = {}
        return func.HttpResponse(json.dumps(policy), status_code=200, mimetype="application/json")

    if req.method in ["POST", "PUT"]:
        try:
            data = req.get_json()
        except ValueError:
            return func.HttpResponse("Invalid JSON", status_code=400)
        entity = {"id": "policy", "pk": user_id, "policy": data}
        try:
            _container.upsert_item(entity)
        except Exception:
            return func.HttpResponse("Failed", status_code=500)
        return func.HttpResponse("ok", status_code=200)

    return func.HttpResponse("Method not allowed", status_code=405)
