import os
import jwt


def verify_token(auth_header: str) -> str:
    """Validate a bearer token and return the user ID."""
    key = os.environ.get("JWT_SIGNING_KEY")
    if not key:
        raise RuntimeError("JWT_SIGNING_KEY not configured")

    if not auth_header or not auth_header.startswith("Bearer "):
        raise ValueError("Missing bearer token")

    token = auth_header.split(" ", 1)[1]
    options = {"require": ["exp"]}
    try:
        claims = jwt.decode(token, key, algorithms=["HS256"], options=options)
    except Exception as e:
        raise ValueError("Invalid token") from e

    issuer = os.environ.get("ISSUER")
    if issuer and claims.get("iss") != issuer:
        raise ValueError("Invalid issuer")

    user_id = claims.get("sub") or claims.get("user_id") or claims.get("userID")
    if not user_id:
        raise ValueError("user id claim missing")
    return user_id
