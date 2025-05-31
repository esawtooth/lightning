import json
import os
import hashlib
import secrets
from datetime import datetime, timedelta

import azure.functions as func
from azure.data.tables import TableServiceClient
import jwt

STORAGE_CONN = os.environ.get("STORAGE_CONNECTION")
USER_TABLE = os.environ.get("USER_TABLE", "users")
JWT_SIGNING_KEY = os.environ.get("JWT_SIGNING_KEY")

service = TableServiceClient.from_connection_string(STORAGE_CONN)
_table = service.get_table_client(USER_TABLE)
_table.create_table_if_not_exists()


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def _register(data: dict) -> func.HttpResponse:
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return func.HttpResponse("Missing credentials", status_code=400)
    try:
        _table.get_entity(username, "user")
        return func.HttpResponse("Username exists", status_code=409)
    except Exception:
        pass
    salt = secrets.token_hex(16)
    hashed = _hash_password(password, salt)
    entity = {"PartitionKey": username, "RowKey": "user", "hash": hashed, "salt": salt}
    _table.upsert_entity(entity)
    return func.HttpResponse("", status_code=201)


def _login(data: dict) -> func.HttpResponse:
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return func.HttpResponse("Missing credentials", status_code=400)
    try:
        entity = _table.get_entity(username, "user")
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
