"""
Authentication models for Lightning Unified UI.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field


class User(BaseModel):
    """User model."""
    id: str
    username: str
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    role: str = "user"  # user, admin, service
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "user_123",
                "username": "johndoe",
                "email": "john@example.com",
                "full_name": "John Doe",
                "role": "user",
                "is_active": True,
            }
        }


class Token(BaseModel):
    """Token response model."""
    access_token: str
    token_type: str = "bearer"
    expires_in: Optional[int] = None
    refresh_token: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIs...",
                "token_type": "bearer",
                "expires_in": 3600,
            }
        }


class LoginRequest(BaseModel):
    """Login request model."""
    username: str
    password: str
    remember_me: bool = False
    
    class Config:
        json_schema_extra = {
            "example": {
                "username": "johndoe",
                "password": "secret123",
                "remember_me": True,
            }
        }


class RegisterRequest(BaseModel):
    """Registration request model."""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "username": "johndoe",
                "email": "john@example.com",
                "password": "securepass123",
                "full_name": "John Doe",
            }
        }


class UserUpdate(BaseModel):
    """User update model."""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "newemail@example.com",
                "full_name": "John Updated Doe",
            }
        }


class PasswordChange(BaseModel):
    """Password change request."""
    current_password: str
    new_password: str = Field(..., min_length=8)
    
    class Config:
        json_schema_extra = {
            "example": {
                "current_password": "oldpass123",
                "new_password": "newpass456",
            }
        }