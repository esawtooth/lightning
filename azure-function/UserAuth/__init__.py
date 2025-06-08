import os
import json
import secrets
import hashlib
from datetime import datetime

import azure.functions as func
from azure.cosmos import CosmosClient, PartitionKey
from azure.communication.email import EmailClient


COSMOS_CONN = os.environ.get("COSMOS_CONNECTION")
COSMOS_DB = os.environ.get("COSMOS_DATABASE", "vextir")
USER_CONTAINER = os.environ.get("USER_CONTAINER", "users")
ACS_CONNECTION = os.environ.get("ACS_CONNECTION")
ACS_SENDER = os.environ.get("ACS_SENDER")
VERIFY_BASE = os.environ.get("VERIFY_BASE_URL", "")

_client = CosmosClient.from_connection_string(COSMOS_CONN)
_db = _client.create_database_if_not_exists(COSMOS_DB)
_container = _db.create_container_if_not_exists(id=USER_CONTAINER, partition_key=PartitionKey(path="/pk"))
_email_client = EmailClient.from_connection_string(ACS_CONNECTION) if ACS_CONNECTION else None


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode()).hexdigest()


def _send_verification(email: str, token: str) -> None:
    if not _email_client:
        return
    sender = ACS_SENDER or f"no-reply@{email.split('@')[1]}"
    link = f"{VERIFY_BASE.rstrip('/')}/api/auth/verify?token={token}"
    message = {
        "senderAddress": sender,
        "content": {"subject": "Verify your email", "plainText": f"Click to verify: {link}"},
        "recipients": {"to": [{"address": email}]},
    }
    try:
        _email_client.begin_send(message)
    except Exception:
        pass


def _register(data: dict) -> func.HttpResponse:
    username = data.get("username")
    password = data.get("password")
    email = data.get("email")
    if not all([username, password, email]):
        return func.HttpResponse("missing fields", status_code=400)
    salt = secrets.token_hex(8)
    token = secrets.token_urlsafe(16)
    entity = {
        "id": "user",
        "pk": username,
        "hash": _hash_password(password, salt),
        "salt": salt,
        "email": email,
        "status": "waitlist",
        "verify_token": token,
        "created_at": datetime.utcnow().isoformat(),
    }
    _container.upsert_item(entity)
    _send_verification(email, token)
    return func.HttpResponse("", status_code=201)


def _verify(token: str) -> func.HttpResponse:
    if not token:
        return func.HttpResponse("missing token", status_code=400)
    items = list(_container.query_items(
        query="SELECT * FROM c WHERE c.id='user' AND c.verify_token=@t",
        parameters=[{"name": "@t", "value": token}],
        enable_cross_partition_query=True,
    ))
    if not items:
        return func.HttpResponse("invalid token", status_code=404)
    user = items[0]
    user.pop("verify_token", None)
    user["email_verified"] = True
    _container.upsert_item(user)
    return func.HttpResponse("verified", status_code=200)


def main(req: func.HttpRequest) -> func.HttpResponse:
    action = req.route_params.get("action")
    if action == "register" and req.method == "POST":
        try:
            data = req.get_json()
        except ValueError:
            data = {}
        return _register(data)
    if action == "verify":
        token = req.params.get("token")
        return _verify(token)
    return func.HttpResponse("not found", status_code=404)
