import os
import logging
from typing import Optional

import requests

import azure.functions as func
from azure.cosmos import CosmosClient, PartitionKey
from simple_auth import get_user_id_permissive

COSMOS_CONN = os.environ.get("COSMOS_CONNECTION")
COSMOS_DB = os.environ.get("COSMOS_DATABASE", "vextir")
REPO_CONTAINER = os.environ.get("REPO_CONTAINER", "repos")
GITEA_URL = os.environ.get("GITEA_URL")
GITEA_TOKEN = os.environ.get("GITEA_TOKEN")

_client = CosmosClient.from_connection_string(COSMOS_CONN)
_db = _client.create_database_if_not_exists(COSMOS_DB)
_container = _db.create_container_if_not_exists(
    id=REPO_CONTAINER, partition_key=PartitionKey(path="/pk")
)


def _create_repo(user: str) -> Optional[str]:
    """Create a new Gitea repository and return its clone URL."""
    if not (GITEA_URL and GITEA_TOKEN):
        logging.warning("Gitea not configured")
        return None
    data = {"name": user, "private": False, "auto_init": True}
    headers = {"Authorization": f"token {GITEA_TOKEN}"}
    try:
        r = requests.post(f"{GITEA_URL}/api/v1/user/repos", json=data, headers=headers, timeout=10)
    except Exception as e:
        logging.error("Gitea request failed: %s", e)
        return None
    if r.status_code not in (200, 201):
        logging.error("Gitea repo creation failed: %s %s", r.status_code, r.text)
        return None
    try:
        return r.json().get("clone_url")
    except Exception:
        return None


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        req.get_json()
    except ValueError:
        pass

    try:
        user_id = get_user_id_permissive(req)
    except Exception:
        return func.HttpResponse("Unauthorized", status_code=401)

    clone_url = _create_repo(user_id)
    if clone_url is None:
        return func.HttpResponse("Failed", status_code=500)

    entity = {"id": "repo", "pk": user_id, "repo": clone_url}
    try:
        _container.upsert_item(entity)
    except Exception as e:
        logging.error("Failed to save repo: %s", e)
        return func.HttpResponse("Failed", status_code=500)

    return func.HttpResponse("ok", status_code=200)
