"""Simplified authentication helpers for Azure Functions."""
import os
import logging
import importlib


def get_user_from_headers(headers):
    """Extract and verify user from Authorization header."""
    auth_header = headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            auth_mod = importlib.import_module("auth")
            return auth_mod.verify_token(auth_header)
        except Exception as exc:
            logging.warning("Invalid token: %s", exc)
            return None
    return None


def verify_user(req):
    user_id = get_user_from_headers(getattr(req, "headers", {}))
    if not user_id:
        raise ValueError("User not authenticated")
    return user_id


def is_development_mode() -> bool:
    return os.environ.get("AZURE_FUNCTIONS_ENVIRONMENT") == "Development"


def get_user_id_permissive(req):
    try:
        return verify_user(req)
    except Exception:
        if is_development_mode():
            logging.warning("Development mode: using default user ID")
            return "default-user"
        raise
