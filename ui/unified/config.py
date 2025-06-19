"""
Configuration management for Lightning Unified UI.
"""

import os
from typing import Optional, List
from pydantic_settings import BaseSettings
from pydantic import Field, validator
from enum import Enum


class Environment(str, Enum):
    """Application environment."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class AuthProvider(str, Enum):
    """Authentication providers."""
    AZURE = "azure"
    LOCAL = "local"
    JWT = "jwt"


class Settings(BaseSettings):
    """Application settings."""
    
    # Application
    app_name: str = "Lightning AI OS"
    app_version: str = "1.0.0"
    app_env: Environment = Environment.DEVELOPMENT
    app_port: int = 8000
    app_host: str = "0.0.0.0"
    
    # URLs
    app_url: str = "http://localhost:8000"
    api_base: str = "http://localhost:7071/api"
    
    # Authentication
    auth_provider: AuthProvider = AuthProvider.LOCAL
    session_secret: str = Field(default="change-me-in-production")
    jwt_secret: str = Field(default="change-me-in-production")
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60
    
    # Azure AD (if using Azure auth)
    aad_client_id: Optional[str] = None
    aad_tenant_id: Optional[str] = None
    aad_client_secret: Optional[str] = None
    aad_redirect_uri: Optional[str] = None
    
    # Backend Services
    event_bus_url: Optional[str] = None
    storage_url: Optional[str] = None
    
    # Redis (for sessions/caching)
    redis_url: Optional[str] = "redis://localhost:6379"
    redis_prefix: str = "lightning:"
    
    # WebSocket
    ws_heartbeat_interval: int = 30
    ws_max_connections: int = 1000
    ws_message_queue_size: int = 100
    
    # Features
    enable_chat: bool = True
    enable_tasks: bool = True
    enable_monitoring: bool = True
    enable_notifications: bool = True
    enable_admin: bool = True
    
    # Security
    cors_origins: List[str] = ["*"]
    cors_credentials: bool = True
    rate_limit_requests: int = 100
    rate_limit_period: int = 60  # seconds
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "json"  # json or text
    
    # Monitoring
    enable_metrics: bool = True
    metrics_port: int = 9090
    
    @validator("app_url", pre=True, always=True)
    def set_app_url(cls, v, values):
        """Set app URL based on environment."""
        if v:
            return v
        
        env = values.get("app_env", Environment.DEVELOPMENT)
        if env == Environment.PRODUCTION:
            return "https://lightning.ai"
        elif env == Environment.STAGING:
            return "https://staging.lightning.ai"
        else:
            host = values.get("app_host", "localhost")
            port = values.get("app_port", 8000)
            return f"http://{host}:{port}"
    
    @validator("aad_redirect_uri", pre=True, always=True)
    def set_redirect_uri(cls, v, values):
        """Set Azure AD redirect URI."""
        if v:
            return v
        
        app_url = values.get("app_url", "http://localhost:8000")
        return f"{app_url}/auth/callback"
    
    @validator("cors_origins", pre=True)
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    class Config:
        """Pydantic config."""
        env_prefix = "LIGHTNING_"
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get application settings."""
    return settings


# Convenience accessors
def is_production() -> bool:
    """Check if running in production."""
    return settings.app_env == Environment.PRODUCTION


def is_development() -> bool:
    """Check if running in development."""
    return settings.app_env == Environment.DEVELOPMENT


def get_redis_key(key: str) -> str:
    """Get Redis key with prefix."""
    return f"{settings.redis_prefix}{key}"