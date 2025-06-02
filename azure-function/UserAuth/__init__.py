import json
import os
import hashlib
import secrets
from datetime import datetime, timedelta
import logging

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


def _hash_password(password: str, salt: bytes = None) -> tuple[str, str]:
    """Hash the password using PBKDF2. Returns (hash, salt)"""
    if salt is None:
        salt = secrets.token_bytes(32)
    elif isinstance(salt, str):
        salt = bytes.fromhex(salt)
    
    password_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return password_hash.hex(), salt.hex()


def _verify_password(password: str, hashed: str, salt: str) -> bool:
    """Verify a password against its hash."""
    try:
        salt_bytes = bytes.fromhex(salt)
        password_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt_bytes, 100000)
        return password_hash.hex() == hashed
    except Exception:
        logging.exception("Exception during password verification")
        return False


def _is_strong_password(password: str) -> bool:
    if len(password) < 8:
        return False
    has_letter = any(c.isalpha() for c in password)
    has_digit = any(c.isdigit() for c in password)
    return has_letter and has_digit


def _register(data: dict) -> func.HttpResponse:
    username = data.get("username")
    password = data.get("password")
    email = data.get("email", "")
    logging.info("Register attempt: username=%s, email=%s", username, email)
    if not username or not password:
        return func.HttpResponse("Missing credentials", status_code=400)

    if not _is_strong_password(password):
        logging.warning("Weak password provided for username=%s", username)
        return func.HttpResponse(
            "Password must be at least 8 characters and include letters and numbers",
            status_code=400,
        )
    try:
        existing_user = _container.read_item("user", partition_key=username)
        return func.HttpResponse("Username exists", status_code=409)
    except Exception:
        logging.exception("Error checking existing user: username=%s", username)
        pass
    
    hashed, salt = _hash_password(password)
    
    # New users are placed on waitlist by default
    entity = {
        "id": "user",
        "pk": username,
        "hash": hashed,
        "salt": salt,
        "email": email,
        "status": "waitlist",  # waitlist, approved, rejected
        "role": "user",  # user, admin
        "created_at": datetime.utcnow().isoformat(),
        "approved_at": None,
        "approved_by": None
    }
    
    _container.upsert_item(entity)
    logging.info("User registered and added to waitlist: username=%s", username)
    
    return func.HttpResponse(
        json.dumps({"message": "Registration successful. You are now on the waitlist for approval."}),
        status_code=201,
        mimetype="application/json"
    )


def _login(data: dict) -> func.HttpResponse:
    username = data.get("username")
    password = data.get("password")
    logging.info("Login attempt: username=%s", username)
    if not username or not password:
        return func.HttpResponse("Missing credentials", status_code=400)
    try:
        entity = _container.read_item("user", partition_key=username)
    except Exception:
        logging.warning("Login failed: user not found - username=%s", username)
        logging.exception("Exception during user lookup")
        return func.HttpResponse("Unauthorized", status_code=401)
    
    # Verify password using PBKDF2
    if not _verify_password(password, entity.get("hash", ""), entity.get("salt", "")):
        logging.warning("Login failed: invalid password for username=%s", username)
        return func.HttpResponse("Unauthorized", status_code=401)
    
    # Check if user is approved
    user_status = entity.get("status", "approved")
    if user_status != "approved":
        if user_status == "waitlist":
            return func.HttpResponse(
                json.dumps({"error": "Account pending approval", "status": "waitlist"}),
                status_code=403,
                mimetype="application/json"
            )
        elif user_status == "rejected":
            return func.HttpResponse(
                json.dumps({"error": "Account access denied", "status": "rejected"}),
                status_code=403,
                mimetype="application/json"
            )
        else:
            return func.HttpResponse("Account not approved", status_code=403)
    
    if not JWT_SIGNING_KEY:
        return func.HttpResponse("Server error", status_code=500)
    
    # Include user role in JWT token
    user_role = entity.get("role", "user")
    payload = {
        "sub": username,
        "role": user_role,
        "status": user_status,
        "exp": datetime.utcnow() + timedelta(hours=1)
    }
    token = jwt.encode(payload, JWT_SIGNING_KEY, algorithm="HS256")
    logging.info("Login successful: username=%s", username)
    
    return func.HttpResponse(
        json.dumps({"token": token, "role": user_role}),
        status_code=200,
        mimetype="application/json"
    )


def _approve_user(data: dict, admin_username: str) -> func.HttpResponse:
    """Approve a user (admin only)."""
    target_user_id = data.get("user_id")
    target_username = data.get("username")  # Fallback for backward compatibility
    action = data.get("action", "approve")  # approve or reject
    
    # Use user_id if provided, otherwise fall back to username
    lookup_key = target_user_id or target_username
    
    if not lookup_key:
        return func.HttpResponse("Missing user_id or username", status_code=400)
    
    if action not in ["approve", "reject"]:
        return func.HttpResponse("Invalid action", status_code=400)
    
    try:
        entity = _container.read_item("user", partition_key=lookup_key)
    except Exception:
        logging.exception("Exception during user lookup for approval: user=%s", lookup_key)
        return func.HttpResponse("User not found", status_code=404)
    
    # Update user status
    entity["status"] = "approved" if action == "approve" else "rejected"
    entity["approved_at"] = datetime.utcnow().isoformat()
    entity["approved_by"] = admin_username
    
    _container.upsert_item(entity)
    
    return func.HttpResponse(
        json.dumps({"message": f"User {entity.get('pk')} {action}d successfully"}),
        status_code=200,
        mimetype="application/json"
    )



def _list_pending_users(admin_username: str) -> func.HttpResponse:
    """List all users with stats (admin only) - renamed but returns all users for admin panel."""
    try:
        # Query for all users
        query = "SELECT * FROM c ORDER BY c.created_at DESC"
        items = list(_container.query_items(query=query, enable_cross_partition_query=True))
        
        # Remove sensitive information and prepare user data
        users = []
        pending_count = 0
        approved_count = 0
        rejected_count = 0
        
        for item in items:
            # Remove sensitive fields
            item.pop("hash", None)
            item.pop("salt", None)
            
            # Add user_id field for consistency
            item["user_id"] = item.get("pk")
            
            # Count by status
            status = item.get("status", "waitlist")
            if status == "waitlist":
                pending_count += 1
            elif status == "approved":
                approved_count += 1
            elif status == "rejected":
                rejected_count += 1
            
            users.append(item)
        
        return func.HttpResponse(
            json.dumps({
                "users": users,
                "pending_count": pending_count,
                "approved_count": approved_count,
                "rejected_count": rejected_count
            }),
            status_code=200,
            mimetype="application/json"
        )
    except Exception as e:
        logging.exception("Exception fetching users")
        return func.HttpResponse(f"Error fetching users: {str(e)}", status_code=500)


def _get_user_info(data: dict) -> func.HttpResponse:
    """Get user status information."""
    username = data.get("username")
    if not username:
        return func.HttpResponse("Missing username", status_code=400)
    
    try:
        entity = _container.read_item("user", partition_key=username)
        # Remove sensitive information
        user_info = {
            "username": entity.get("pk"),
            "email": entity.get("email", ""),
            "status": entity.get("status", "waitlist"),
            "role": entity.get("role", "user"),
            "created_at": entity.get("created_at"),
            "approved_at": entity.get("approved_at"),
            "approved_by": entity.get("approved_by")
        }
        return func.HttpResponse(
            json.dumps(user_info),
            status_code=200,
            mimetype="application/json"
        )
    except Exception:
        logging.exception("Exception fetching user info: username=%s", username)
        return func.HttpResponse("User not found", status_code=404)


def _verify_admin(auth_header: str) -> str:
    """Verify admin token and return username."""
    if not JWT_SIGNING_KEY:
        raise RuntimeError("JWT_SIGNING_KEY not configured")

    if not auth_header or not auth_header.startswith("Bearer "):
        raise ValueError("Missing bearer token")

    token = auth_header.split(" ", 1)[1]
    try:
        claims = jwt.decode(token, JWT_SIGNING_KEY, algorithms=["HS256"])
    except Exception as e:
        logging.exception("Exception decoding admin token")
        raise ValueError("Invalid token") from e

    username = claims.get("sub")
    role = claims.get("role", "user")
    
    if not username:
        raise ValueError("Username claim missing")
    
    if role != "admin":
        raise ValueError("Admin privileges required")
    
    return username


def _refresh_token(auth_header: str) -> func.HttpResponse:
    """Refresh a valid JWT and return one with an updated exp claim."""
    if not JWT_SIGNING_KEY:
        return func.HttpResponse("Server error", status_code=500)

    if not auth_header or not auth_header.startswith("Bearer "):
        return func.HttpResponse("Unauthorized", status_code=401)

    token = auth_header.split(" ", 1)[1]
    try:
        claims = jwt.decode(token, JWT_SIGNING_KEY, algorithms=["HS256"])
    except Exception:
        logging.exception("Exception decoding token during refresh")
        return func.HttpResponse("Unauthorized", status_code=401)

    new_payload = {
        "sub": claims.get("sub"),
        "role": claims.get("role", "user"),
        "status": claims.get("status", "approved"),
        "exp": datetime.utcnow() + timedelta(hours=1),
    }

    new_token = jwt.encode(new_payload, JWT_SIGNING_KEY, algorithm="HS256")
    return func.HttpResponse(
        json.dumps({"token": new_token, "role": new_payload["role"]}),
        status_code=200,
        mimetype="application/json",
    )


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json() if req.get_body() else {}
    except ValueError:
        return func.HttpResponse("Invalid JSON", status_code=400)
    
    action = req.route_params.get("action")
    
    # Public endpoints (no auth required)
    if action == "register":
        return _register(data)
    elif action == "login":
        return _login(data)
    elif action == "status":
        return _get_user_info(data)
    elif action == "refresh":
        auth_header = req.headers.get("Authorization", "")
        return _refresh_token(auth_header)
    
    # Admin endpoints (require admin token)
    elif action in ["approve", "pending"]:
        try:
            auth_header = req.headers.get("Authorization", "")
            admin_username = _verify_admin(auth_header)
            
            if action == "approve":
                return _approve_user(data, admin_username)
            elif action == "pending":
                return _list_pending_users(admin_username)
                
        except ValueError as e:
            return func.HttpResponse(str(e), status_code=403)
        except RuntimeError as e:
            return func.HttpResponse(str(e), status_code=500)
    try:
        return func.HttpResponse("Not found", status_code=404)
    except Exception as e:
        logging.exception("Unhandled exception during request routing")
        return func.HttpResponse("Internal server error", status_code=500)
