import os
import jwt
from jwt import PyJWKClient


def _verify_aad(token: str, tenant: str, client_id: str) -> dict:
    """Verify a token issued by Azure AD."""
    jwk_client = PyJWKClient(
        f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys"
    )
    signing_key = jwk_client.get_signing_key_from_jwt(token).key
    return jwt.decode(
        token,
        signing_key,
        algorithms=["RS256"],
        audience=client_id,
        issuer=f"https://login.microsoftonline.com/{tenant}/v2.0",
    )


def verify_token(token_or_header: str) -> str:
    """Validate a JWT or Authorization header and return the user ID."""
    if not token_or_header:
        raise ValueError("Missing bearer token")

    token = token_or_header
    if token_or_header.startswith("Bearer "):
        token = token_or_header.split(" ", 1)[1]

    key = os.environ.get("JWT_SIGNING_KEY")
    tenant = (
        os.environ.get("AAD_TENANT_ID")
        or os.environ.get("ARM_TENANT_ID")
        or os.environ.get("AZURE_TENANT_ID")
    )
    client_id = (
        os.environ.get("AAD_CLIENT_ID")
        or os.environ.get("ARM_CLIENT_ID")
        or os.environ.get("AZURE_CLIENT_ID")
    )

    if key:
        options = {"require": ["exp"]}
        try:
            claims = jwt.decode(token, key, algorithms=["HS256"], options=options)
        except Exception as e:
            raise ValueError("Invalid token") from e

        issuer = os.environ.get("ISSUER")
        if issuer and claims.get("iss") != issuer:
            raise ValueError("Invalid issuer")
    elif tenant and client_id:
        try:
            claims = _verify_aad(token, tenant, client_id)
        except Exception as e:
            raise ValueError("Invalid token") from e
    else:
        raise RuntimeError("JWT_SIGNING_KEY not configured")

    user_id = claims.get("oid") or claims.get("sub") or claims.get("user_id") or claims.get("userID")
    if not user_id:
        raise ValueError("user id claim missing")
    return user_id
