import json
import os
import hashlib
import secrets
from datetime import datetime, timedelta

import azure.functions as func
from azure.cosmos import CosmosClient, PartitionKey
import jwt

COSMOS_CONN = os.environ.get("COSMOS_CONNECTION")
COSMOS_DB = os.environ.get("COSMOS_DATABASE", "lightning")
USER_CONTAINER = os.environ.get("USER_CONTAINER", "users")
JWT_SIGNING_KEY = os.environ.get("JWT_SIGNING_KEY")

_client = CosmosClient.from_connection_string(COSMOS_CONN)
_db = _client.create_database_if_not_exists(COSMOS_DB)
_container = _db.create_container_if_not_exists(
    id=USER_CONTAINER, partition_key=PartitionKey(path="/pk")
)


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def _register(data: dict) -> func.HttpResponse:
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return func.HttpResponse("Missing credentials", status_code=400)
    try:
        _container.read_item("user", partition_key=username)
        return func.HttpResponse("Username exists", status_code=409)
    except Exception:
        pass
    salt = secrets.token_hex(16)
    hashed = _hash_password(password, salt)
    entity = {"id": "user", "pk": username, "hash": hashed, "salt": salt}
    _container.upsert_item(entity)
    return func.HttpResponse("", status_code=201)


def _login(data: dict) -> func.HttpResponse:
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return func.HttpResponse("Missing credentials", status_code=400)
    try:
        entity = _container.read_item("user", partition_key=username)
    except Exception:
        return func.HttpResponse("Unauthorized", status_code=401)
    expected = _hash_password(password, entity.get("salt", ""))
    if expected != entity.get("hash"):
        return func.HttpResponse("Unauthorized", status_code=401)
    if not JWT_SIGNING_KEY:
        return func.HttpResponse("Server error", status_code=500)
    payload = {"sub": username, "exp": datetime.utcnow() + timedelta(hours=1)}
    token = jwt.encode(payload, JWT_SIGNING_KEY, algorithm="HS256")
    return func.HttpResponse(json.dumps({"token": token}), status_code=200, mimetype="application/json")


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()
    except ValueError:
        return func.HttpResponse("Invalid JSON", status_code=400)
    action = req.route_params.get("action")
    if action == "register":
        return _register(data)
    if action == "login":
        return _login(data)
    return func.HttpResponse("Not found", status_code=404)
