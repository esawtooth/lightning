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
VERIFY_BASE = os.environ.get("VERIFY_BASE", "https://www.vextir.com")
ADMIN_EMAIL = "mail@rohitja.in"  # Hardcoded for now

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


def _send_admin_notification(user_data: dict) -> None:
    """Send notification to admin about new access request."""
    if not _email_client or not ADMIN_EMAIL:
        return
    
    sender = ACS_SENDER or "no-reply@vextir.com"
    subject = f"New Access Request - {user_data.get('name', 'Unknown User')}"
    content = f"""
    New user access request:
    
    Name: {user_data.get('name', 'Not provided')}
    Email: {user_data.get('email')}
    User ID: {user_data.get('user_id')}
    Requested: {user_data.get('created_at')}
    
    Please review and approve/deny this request in the admin panel.
    """
    
    message = {
        "senderAddress": sender,
        "content": {"subject": subject, "plainText": content},
        "recipients": {"to": [{"address": ADMIN_EMAIL}]},
    }
    try:
        _email_client.begin_send(message)
    except Exception:
        pass


def _send_user_notification(email: str, approved: bool) -> None:
    """Send notification to user about approval status."""
    if not _email_client:
        return
    
    sender = ACS_SENDER or "no-reply@vextir.com"
    
    if approved:
        subject = "Access Approved - Welcome to Vextir!"
        content = """
        Great news! Your access request has been approved.
        
        You can now sign in to Vextir using your Microsoft account.
        
        Visit: https://www.vextir.com
        
        Welcome to the team!
        """
    else:
        subject = "Access Request Update"
        content = """
        Thank you for your interest in Vextir.
        
        Your access request is currently under review. We'll notify you once a decision has been made.
        
        If you have any questions, please contact our support team.
        """
    
    message = {
        "senderAddress": sender,
        "content": {"subject": subject, "plainText": content},
        "recipients": {"to": [{"address": email}]},
    }
    try:
        _email_client.begin_send(message)
    except Exception:
        pass


def _get_user_status(user_id: str) -> func.HttpResponse:
    """Get approval status for a user."""
    try:
        items = list(_container.query_items(
            query="SELECT * FROM c WHERE c.user_id=@user_id",
            parameters=[{"name": "@user_id", "value": user_id}],
            enable_cross_partition_query=True,
        ))
        
        if not items:
            return func.HttpResponse(
                json.dumps({"status": "not_found", "approved": False}),
                status_code=200,
                mimetype="application/json"
            )
        
        user = items[0]
        approved = user.get("status") == "approved"
        
        response_data = {
            "status": user.get("status", "pending"),
            "approved": approved,
            "email": user.get("email"),
            "name": user.get("name"),
            "created_at": user.get("created_at")
        }
        
        return func.HttpResponse(
            json.dumps(response_data),
            status_code=200,
            mimetype="application/json"
        )
        
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"error": str(e), "approved": False}),
            status_code=500,
            mimetype="application/json"
        )


def _request_access(data: dict) -> func.HttpResponse:
    """Handle access request from user."""
    user_id = data.get("user_id")
    email = data.get("email")
    name = data.get("name")
    
    if not user_id or not email:
        return func.HttpResponse("missing user_id or email", status_code=400)
    
    # Check if user already exists
    existing_items = list(_container.query_items(
        query="SELECT * FROM c WHERE c.user_id=@user_id OR c.email=@email",
        parameters=[
            {"name": "@user_id", "value": user_id},
            {"name": "@email", "value": email}
        ],
        enable_cross_partition_query=True,
    ))
    
    if existing_items:
        # User already exists, return current status
        user = existing_items[0]
        return func.HttpResponse(
            json.dumps({
                "message": "existing_user",
                "status": user.get("status", "pending")
            }),
            status_code=200,
            mimetype="application/json"
        )
    
    # Create new access request
    entity = {
        "id": f"user-{secrets.token_hex(4)}",
        "pk": user_id,
        "user_id": user_id,
        "email": email,
        "name": name or "Unknown",
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
        "type": "access_request"
    }
    
    try:
        _container.upsert_item(entity)
        _send_admin_notification(entity)
        _send_user_notification(email, False)  # Send pending notification
        
        return func.HttpResponse(
            json.dumps({"message": "access_requested", "status": "pending"}),
            status_code=201,
            mimetype="application/json"
        )
    except Exception as e:
        return func.HttpResponse(f"error creating request: {str(e)}", status_code=500)


def _approve_user(data: dict) -> func.HttpResponse:
    """Approve or deny user access (admin function)."""
    user_id = data.get("user_id")
    approved = data.get("approved", False)
    admin_notes = data.get("notes", "")
    
    if not user_id:
        return func.HttpResponse("missing user_id", status_code=400)
    
    try:
        items = list(_container.query_items(
            query="SELECT * FROM c WHERE c.user_id=@user_id",
            parameters=[{"name": "@user_id", "value": user_id}],
            enable_cross_partition_query=True,
        ))
        
        if not items:
            return func.HttpResponse("user not found", status_code=404)
        
        user = items[0]
        user["status"] = "approved" if approved else "denied"
        user["approved_at"] = datetime.utcnow().isoformat()
        user["admin_notes"] = admin_notes
        
        _container.upsert_item(user)
        _send_user_notification(user.get("email"), approved)
        
        return func.HttpResponse(
            json.dumps({"message": "user_updated", "status": user["status"]}),
            status_code=200,
            mimetype="application/json"
        )
        
    except Exception as e:
        return func.HttpResponse(f"error updating user: {str(e)}", status_code=500)


def main(req: func.HttpRequest) -> func.HttpResponse:
    action = req.route_params.get("action")
    
    # GET /auth/status/{user_id}
    if action and action.startswith("status/"):
        user_id = action[7:]  # Remove "status/" prefix
        return _get_user_status(user_id)
    
    # POST /auth/request
    if action == "request" and req.method == "POST":
        try:
            data = req.get_json()
        except ValueError:
            data = {}
        return _request_access(data)
    
    # POST /auth/approve (admin function)
    if action == "approve" and req.method == "POST":
        try:
            data = req.get_json()
        except ValueError:
            data = {}
        return _approve_user(data)
    
    # Legacy register endpoint (now redirects to request)
    if action == "register" and req.method == "POST":
        return func.HttpResponse(
            json.dumps({
                "message": "Registration has moved to AAD authentication. Please sign in with Microsoft.",
                "redirect": "/login"
            }),
            status_code=302,
            mimetype="application/json"
        )
    
    return func.HttpResponse("not found", status_code=404)
