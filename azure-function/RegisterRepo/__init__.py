import json
import os
import logging

import azure.functions as func
from azure.data.tables import TableServiceClient
from auth import verify_token

STORAGE_CONN = os.environ.get("STORAGE_CONNECTION")
REPO_TABLE = os.environ.get("REPO_TABLE", "repos")

service = TableServiceClient.from_connection_string(STORAGE_CONN)
_table = service.get_table_client(REPO_TABLE)
_table.create_table_if_not_exists()


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

    entity = {"PartitionKey": user_id, "RowKey": "repo", "repo": repo}
    try:
        _table.upsert_entity(entity)
    except Exception as e:
        logging.error("Failed to save repo: %s", e)
        return func.HttpResponse("Failed", status_code=500)

    return func.HttpResponse("ok", status_code=200)
