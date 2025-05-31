import json
import os
import logging

import azure.functions as func
from azure.cosmos import CosmosClient, PartitionKey
from auth import verify_token

COSMOS_CONN = os.environ.get("COSMOS_CONNECTION")
COSMOS_DB = os.environ.get("COSMOS_DATABASE", "lightning")
REPO_CONTAINER = os.environ.get("REPO_CONTAINER", "repos")

_client = CosmosClient.from_connection_string(COSMOS_CONN)
_db = _client.create_database_if_not_exists(COSMOS_DB)
_container = _db.create_container_if_not_exists(
    id=REPO_CONTAINER, partition_key=PartitionKey(path="/pk")
)


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()
    except ValueError:
        return func.HttpResponse("Invalid JSON", status_code=400)

    try:
        user_id = verify_token(req.headers.get("Authorization"))
    except Exception:
        return func.HttpResponse("Unauthorized", status_code=401)

    repo = data.get("repo")
    if not repo:
        return func.HttpResponse("Missing repo", status_code=400)

    entity = {"id": "repo", "pk": user_id, "repo": repo}
    try:
        _container.upsert_item(entity)
    except Exception as e:
        logging.error("Failed to save repo: %s", e)
        return func.HttpResponse("Failed", status_code=500)

    return func.HttpResponse("ok", status_code=200)
