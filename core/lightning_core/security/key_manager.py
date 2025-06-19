"""
Centralized API Key Management for Lightning Core

Provides secure storage, rotation, and access control for API keys.
"""

import os
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
import asyncio
from cryptography.fernet import Fernet
import base64

logger = logging.getLogger(__name__)


class KeyStatus(Enum):
    ACTIVE = "active"
    ROTATING = "rotating"
    EXPIRED = "expired"
    REVOKED = "revoked"


class KeyProvider(Enum):
    ENVIRONMENT = "environment"
    AZURE_KEYVAULT = "azure_keyvault"
    AWS_SECRETS = "aws_secrets"
    GCP_SECRET_MANAGER = "gcp_secret_manager"
    LOCAL_FILE = "local_file"


@dataclass
class APIKey:
    """Represents an API key with metadata."""
    key_id: str
    provider: str
    value: str
    status: KeyStatus = KeyStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    last_used: Optional[datetime] = None
    usage_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class KeyRotationPolicy:
    """Policy for automatic key rotation."""
    rotation_days: int = 90
    warning_days: int = 7
    keep_old_keys: int = 2
    auto_rotate: bool = False


class SecretProvider(ABC):
    """Abstract base class for secret storage providers."""
    
    @abstractmethod
    async def get_secret(self, key_name: str) -> Optional[str]:
        """Retrieve a secret value."""
        pass
    
    @abstractmethod
    async def set_secret(self, key_name: str, value: str) -> bool:
        """Store a secret value."""
        pass
    
    @abstractmethod
    async def delete_secret(self, key_name: str) -> bool:
        """Delete a secret."""
        pass
    
    @abstractmethod
    async def list_secrets(self) -> List[str]:
        """List all secret names."""
        pass


class EnvironmentSecretProvider(SecretProvider):
    """Provider that reads from environment variables."""
    
    async def get_secret(self, key_name: str) -> Optional[str]:
        """Get from environment variable."""
        # Try Lightning-specific format first
        lightning_key = f"LIGHTNING_API_KEY_{key_name.upper()}"
        if lightning_key in os.environ:
            return os.environ[lightning_key]
            
        # Try direct format
        direct_key = f"{key_name.upper()}_API_KEY"
        if direct_key in os.environ:
            return os.environ[direct_key]
            
        # Try exact match
        if key_name in os.environ:
            return os.environ[key_name]
            
        return None
    
    async def set_secret(self, key_name: str, value: str) -> bool:
        """Cannot set environment variables."""
        logger.warning("Cannot set secrets in environment provider")
        return False
    
    async def delete_secret(self, key_name: str) -> bool:
        """Cannot delete environment variables."""
        logger.warning("Cannot delete secrets in environment provider")
        return False
    
    async def list_secrets(self) -> List[str]:
        """List relevant environment variables."""
        secrets = []
        for key in os.environ:
            if "API_KEY" in key or key.startswith("LIGHTNING_"):
                secrets.append(key)
        return secrets


class LocalFileSecretProvider(SecretProvider):
    """Provider that stores encrypted secrets in a local file."""
    
    def __init__(self, file_path: str = ".lightning/secrets.enc"):
        self.file_path = file_path
        self._ensure_encryption_key()
        
    def _ensure_encryption_key(self):
        """Ensure we have an encryption key."""
        key_file = ".lightning/secret.key"
        os.makedirs(os.path.dirname(key_file), exist_ok=True)
        
        if os.path.exists(key_file):
            with open(key_file, 'rb') as f:
                self.cipher = Fernet(f.read())
        else:
            key = Fernet.generate_key()
            with open(key_file, 'wb') as f:
                f.write(key)
            self.cipher = Fernet(key)
            os.chmod(key_file, 0o600)  # Read/write for owner only
    
    async def get_secret(self, key_name: str) -> Optional[str]:
        """Get encrypted secret from file."""
        if not os.path.exists(self.file_path):
            return None
            
        try:
            with open(self.file_path, 'r') as f:
                data = json.load(f)
                
            if key_name in data:
                encrypted = base64.b64decode(data[key_name])
                return self.cipher.decrypt(encrypted).decode()
        except Exception as e:
            logger.error(f"Error reading secret: {e}")
            
        return None
    
    async def set_secret(self, key_name: str, value: str) -> bool:
        """Store encrypted secret in file."""
        try:
            data = {}
            if os.path.exists(self.file_path):
                with open(self.file_path, 'r') as f:
                    data = json.load(f)
            
            encrypted = self.cipher.encrypt(value.encode())
            data[key_name] = base64.b64encode(encrypted).decode()
            
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            with open(self.file_path, 'w') as f:
                json.dump(data, f, indent=2)
            os.chmod(self.file_path, 0o600)
            
            return True
        except Exception as e:
            logger.error(f"Error storing secret: {e}")
            return False
    
    async def delete_secret(self, key_name: str) -> bool:
        """Delete secret from file."""
        try:
            if not os.path.exists(self.file_path):
                return False
                
            with open(self.file_path, 'r') as f:
                data = json.load(f)
                
            if key_name in data:
                del data[key_name]
                with open(self.file_path, 'w') as f:
                    json.dump(data, f, indent=2)
                return True
        except Exception as e:
            logger.error(f"Error deleting secret: {e}")
            
        return False
    
    async def list_secrets(self) -> List[str]:
        """List all secret names."""
        if not os.path.exists(self.file_path):
            return []
            
        try:
            with open(self.file_path, 'r') as f:
                data = json.load(f)
            return list(data.keys())
        except Exception as e:
            logger.error(f"Error listing secrets: {e}")
            return []


class APIKeyManager:
    """Centralized API key management with rotation and access control."""
    
    def __init__(
        self,
        provider: SecretProvider = None,
        rotation_policy: KeyRotationPolicy = None,
    ):
        self.provider = provider or EnvironmentSecretProvider()
        self.rotation_policy = rotation_policy or KeyRotationPolicy()
        self.keys: Dict[str, List[APIKey]] = {}
        self._rotation_tasks: Dict[str, asyncio.Task] = {}
        
    async def initialize(self):
        """Initialize the key manager and load existing keys."""
        # Load keys from provider
        secret_names = await self.provider.list_secrets()
        
        for name in secret_names:
            value = await self.provider.get_secret(name)
            if value:
                # Determine provider from secret name
                provider = self._extract_provider(name)
                if provider:
                    await self.add_key(provider, value, key_id=name)
        
        # Start rotation monitoring if enabled
        if self.rotation_policy.auto_rotate:
            for provider in self.keys:
                self._start_rotation_monitor(provider)
    
    def _extract_provider(self, secret_name: str) -> Optional[str]:
        """Extract provider name from secret name."""
        # Handle LIGHTNING_API_KEY_PROVIDER format
        if secret_name.startswith("LIGHTNING_API_KEY_"):
            return secret_name[18:].lower()
            
        # Handle PROVIDER_API_KEY format
        if secret_name.endswith("_API_KEY"):
            return secret_name[:-8].lower()
            
        # Known providers
        known_providers = ["openai", "openrouter", "anthropic", "google", "azure"]
        for provider in known_providers:
            if provider in secret_name.lower():
                return provider
                
        return None
    
    async def add_key(
        self,
        provider: str,
        value: str,
        key_id: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> APIKey:
        """Add a new API key for a provider."""
        if not key_id:
            key_id = f"{provider}_{datetime.now().timestamp()}"
            
        key = APIKey(
            key_id=key_id,
            provider=provider,
            value=value,
            expires_at=expires_at or (
                datetime.now() + timedelta(days=self.rotation_policy.rotation_days)
                if self.rotation_policy.auto_rotate else None
            ),
        )
        
        if provider not in self.keys:
            self.keys[provider] = []
            
        self.keys[provider].append(key)
        
        # Store in provider if it supports writing
        await self.provider.set_secret(f"LIGHTNING_API_KEY_{provider.upper()}", value)
        
        logger.info(f"Added API key for provider {provider}")
        return key
    
    async def get_key(self, provider: str, user_id: Optional[str] = None) -> Optional[str]:
        """Get an active API key for a provider."""
        if provider not in self.keys:
            return None
            
        # Find active keys
        active_keys = [
            key for key in self.keys[provider]
            if key.status == KeyStatus.ACTIVE
        ]
        
        if not active_keys:
            return None
            
        # Use round-robin or least-used strategy
        key = min(active_keys, key=lambda k: k.usage_count)
        
        # Update usage stats
        key.usage_count += 1
        key.last_used = datetime.now()
        
        # Check if key is expiring soon
        if key.expires_at:
            days_until_expiry = (key.expires_at - datetime.now()).days
            if days_until_expiry <= self.rotation_policy.warning_days:
                logger.warning(
                    f"API key for {provider} expires in {days_until_expiry} days"
                )
        
        return key.value
    
    async def rotate_key(self, provider: str, new_value: str) -> bool:
        """Rotate API key for a provider."""
        if provider not in self.keys:
            return False
            
        # Mark current keys as rotating
        for key in self.keys[provider]:
            if key.status == KeyStatus.ACTIVE:
                key.status = KeyStatus.ROTATING
                
        # Add new key
        new_key = await self.add_key(provider, new_value)
        
        # Keep old keys for transition period
        old_keys = [
            k for k in self.keys[provider]
            if k.status == KeyStatus.ROTATING
        ]
        
        if len(old_keys) > self.rotation_policy.keep_old_keys:
            # Revoke oldest keys
            for key in sorted(old_keys, key=lambda k: k.created_at)[
                :-self.rotation_policy.keep_old_keys
            ]:
                key.status = KeyStatus.REVOKED
                
        logger.info(f"Rotated API key for provider {provider}")
        return True
    
    async def revoke_key(self, provider: str, key_id: str) -> bool:
        """Revoke a specific API key."""
        if provider not in self.keys:
            return False
            
        for key in self.keys[provider]:
            if key.key_id == key_id:
                key.status = KeyStatus.REVOKED
                logger.info(f"Revoked API key {key_id} for provider {provider}")
                return True
                
        return False
    
    def list_keys(self, provider: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
        """List all keys with their status."""
        result = {}
        
        providers = [provider] if provider else self.keys.keys()
        
        for prov in providers:
            if prov in self.keys:
                result[prov] = [
                    {
                        "key_id": key.key_id,
                        "status": key.status.value,
                        "created_at": key.created_at.isoformat(),
                        "expires_at": key.expires_at.isoformat() if key.expires_at else None,
                        "last_used": key.last_used.isoformat() if key.last_used else None,
                        "usage_count": key.usage_count,
                    }
                    for key in self.keys[prov]
                ]
                
        return result
    
    def _start_rotation_monitor(self, provider: str):
        """Start monitoring keys for automatic rotation."""
        async def monitor():
            while True:
                await asyncio.sleep(86400)  # Check daily
                
                for key in self.keys.get(provider, []):
                    if key.status == KeyStatus.ACTIVE and key.expires_at:
                        if datetime.now() >= key.expires_at:
                            key.status = KeyStatus.EXPIRED
                            logger.warning(f"API key {key.key_id} for {provider} has expired")
                            
        if provider not in self._rotation_tasks:
            self._rotation_tasks[provider] = asyncio.create_task(monitor())


# Global key manager instance
_global_key_manager: Optional[APIKeyManager] = None


async def get_key_manager() -> APIKeyManager:
    """Get the global key manager instance."""
    global _global_key_manager
    
    if _global_key_manager is None:
        # Determine provider based on environment
        if os.getenv("LIGHTNING_SECRET_PROVIDER") == "local":
            provider = LocalFileSecretProvider()
        else:
            provider = EnvironmentSecretProvider()
            
        _global_key_manager = APIKeyManager(provider=provider)
        await _global_key_manager.initialize()
        
    return _global_key_manager


# Convenience function for getting API keys
async def get_api_key(provider: str, user_id: Optional[str] = None) -> Optional[str]:
    """Get an API key for a provider."""
    manager = await get_key_manager()
    return await manager.get_key(provider, user_id)