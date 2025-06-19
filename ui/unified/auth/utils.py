"""
Authentication utilities for Lightning Unified UI.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from config import settings

logger = logging.getLogger(__name__)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.
    
    Args:
        data: Data to encode in the token
        expires_delta: Token expiration time
        
    Returns:
        Encoded JWT token
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expiration_minutes)
    
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm
    )
    
    return encoded_jwt


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify and decode a JWT token.
    
    Args:
        token: JWT token to verify
        
    Returns:
        Decoded token data if valid, None otherwise
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm]
        )
        return payload
    except JWTError as e:
        logger.debug(f"JWT verification failed: {e}")
        return None


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.
    
    Args:
        password: Plain text password
        
    Returns:
        Hashed password
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against a hash.
    
    Args:
        plain_password: Plain text password
        hashed_password: Hashed password
        
    Returns:
        True if password matches, False otherwise
    """
    return pwd_context.verify(plain_password, hashed_password)


def create_session_token(user_id: str, username: str, email: Optional[str] = None) -> str:
    """
    Create a session token for a user.
    
    Args:
        user_id: User ID
        username: Username
        email: User email
        
    Returns:
        JWT token for session
    """
    token_data = {
        "sub": user_id,
        "username": username,
        "email": email,
        "type": "session",
    }
    
    return create_access_token(token_data)


def create_api_token(service_name: str, permissions: Optional[list] = None) -> str:
    """
    Create an API token for service-to-service communication.
    
    Args:
        service_name: Name of the service
        permissions: List of permissions
        
    Returns:
        JWT token for API access
    """
    token_data = {
        "sub": service_name,
        "type": "api",
        "permissions": permissions or [],
    }
    
    # API tokens have longer expiration
    expires_delta = timedelta(days=365)
    
    return create_access_token(token_data, expires_delta)