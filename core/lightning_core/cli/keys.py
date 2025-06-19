#!/usr/bin/env python3
"""
Lightning Core API Key Management CLI

Commands for managing API keys securely.
"""

import asyncio
import click
from datetime import datetime, timedelta
from typing import Optional
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from lightning_core.security.key_manager import (
    get_key_manager, KeyProvider, LocalFileSecretProvider,
    EnvironmentSecretProvider, KeyRotationPolicy
)


@click.group()
def cli():
    """Lightning Core API Key Management"""
    pass


@cli.command()
@click.option('--provider', '-p', help='Filter by provider (e.g., openai, openrouter)')
@click.option('--show-values', is_flag=True, help='Show actual key values (careful!)')
def list(provider: Optional[str], show_values: bool):
    """List all API keys and their status."""
    async def _list():
        manager = await get_key_manager()
        keys = manager.list_keys(provider)
        
        if not keys:
            click.echo("No API keys found.")
            return
            
        for prov, key_list in keys.items():
            click.echo(f"\n{click.style(prov.upper(), bold=True)}")
            click.echo("-" * 40)
            
            for key in key_list:
                status_color = {
                    "active": "green",
                    "rotating": "yellow",
                    "expired": "red",
                    "revoked": "red"
                }.get(key["status"], "white")
                
                click.echo(f"  ID: {key['key_id']}")
                click.echo(f"  Status: {click.style(key['status'], fg=status_color)}")
                click.echo(f"  Created: {key['created_at']}")
                click.echo(f"  Expires: {key['expires_at'] or 'Never'}")
                click.echo(f"  Last Used: {key['last_used'] or 'Never'}")
                click.echo(f"  Usage Count: {key['usage_count']}")
                
                if show_values:
                    # Get actual key value
                    actual_key = await manager.get_key(prov)
                    if actual_key:
                        # Mask most of the key
                        masked = actual_key[:8] + "..." + actual_key[-4:]
                        click.echo(f"  Value: {masked}")
                
                click.echo()
    
    asyncio.run(_list())


@cli.command()
@click.argument('provider')
@click.argument('api_key')
@click.option('--expires-days', default=90, help='Days until key expires')
def add(provider: str, api_key: str, expires_days: int):
    """Add a new API key for a provider."""
    async def _add():
        manager = await get_key_manager()
        
        expires_at = None
        if expires_days > 0:
            expires_at = datetime.now() + timedelta(days=expires_days)
            
        key = await manager.add_key(
            provider=provider.lower(),
            value=api_key,
            expires_at=expires_at
        )
        
        click.echo(f"Added API key for {provider}")
        click.echo(f"Key ID: {key.key_id}")
        if expires_at:
            click.echo(f"Expires: {expires_at.isoformat()}")
    
    asyncio.run(_add())


@cli.command()
@click.argument('provider')
@click.argument('new_api_key')
def rotate(provider: str, new_api_key: str):
    """Rotate API key for a provider."""
    async def _rotate():
        manager = await get_key_manager()
        
        if await manager.rotate_key(provider.lower(), new_api_key):
            click.echo(f"Successfully rotated API key for {provider}")
            click.echo("Old keys will remain active for transition period")
        else:
            click.echo(f"Failed to rotate key for {provider}", err=True)
    
    asyncio.run(_rotate())


@cli.command()
@click.argument('provider')
@click.argument('key_id')
def revoke(provider: str, key_id: str):
    """Revoke a specific API key."""
    async def _revoke():
        manager = await get_key_manager()
        
        if await manager.revoke_key(provider.lower(), key_id):
            click.echo(f"Successfully revoked key {key_id} for {provider}")
        else:
            click.echo(f"Failed to revoke key {key_id} for {provider}", err=True)
    
    asyncio.run(_revoke())


@cli.command()
@click.argument('provider')
def test(provider: str):
    """Test if an API key is working."""
    async def _test():
        manager = await get_key_manager()
        key = await manager.get_key(provider.lower())
        
        if not key:
            click.echo(f"No active key found for {provider}", err=True)
            return
            
        click.echo(f"Found active key for {provider}")
        
        # Test the key based on provider
        if provider.lower() == "openai":
            from lightning_core.providers.llm import OpenAIProvider
            from lightning_core.abstractions.llm import LLMProviderConfig
            
            config = LLMProviderConfig(provider_type="openai", api_key=key)
            provider_obj = OpenAIProvider(config)
            
            if await provider_obj.validate_api_key():
                click.echo(click.style("✓ API key is valid", fg="green"))
            else:
                click.echo(click.style("✗ API key is invalid", fg="red"), err=True)
                
        elif provider.lower() == "openrouter":
            from lightning_core.providers.llm import OpenRouterProvider
            from lightning_core.abstractions.llm import LLMProviderConfig
            
            config = LLMProviderConfig(provider_type="openrouter", api_key=key)
            provider_obj = OpenRouterProvider(config)
            
            if await provider_obj.validate_api_key():
                click.echo(click.style("✓ API key is valid", fg="green"))
            else:
                click.echo(click.style("✗ API key is invalid", fg="red"), err=True)
        else:
            click.echo(f"Testing not implemented for {provider}")
    
    asyncio.run(_test())


@cli.command()
@click.option('--use-local', is_flag=True, help='Use local encrypted file storage')
@click.option('--rotation-days', default=90, help='Days before key rotation')
@click.option('--auto-rotate', is_flag=True, help='Enable automatic rotation')
def init(use_local: bool, rotation_days: int, auto_rotate: bool):
    """Initialize key management system."""
    if use_local:
        click.echo("Initializing local encrypted key storage...")
        os.environ["LIGHTNING_SECRET_PROVIDER"] = "local"
        
        # Create local storage
        provider = LocalFileSecretProvider()
        click.echo(f"Created encrypted storage at: {provider.file_path}")
        click.echo(f"Encryption key at: .lightning/secret.key")
        click.echo("\n⚠️  Keep the secret.key file safe! It's needed to decrypt your API keys.")
    else:
        click.echo("Using environment variable storage")
        click.echo("\nSet API keys using one of these formats:")
        click.echo("  export LIGHTNING_API_KEY_OPENAI=sk-...")
        click.echo("  export OPENAI_API_KEY=sk-...")
    
    if auto_rotate:
        click.echo(f"\nAuto-rotation enabled: keys will rotate every {rotation_days} days")
    
    click.echo("\nKey management initialized!")


@cli.command()
def migrate():
    """Migrate API keys from environment to secure storage."""
    async def _migrate():
        click.echo("Migrating API keys from environment variables...")
        
        # Set up local storage
        os.environ["LIGHTNING_SECRET_PROVIDER"] = "local"
        manager = await get_key_manager()
        
        # Known API key patterns
        patterns = [
            ("OPENAI_API_KEY", "openai"),
            ("OPENROUTER_API_KEY", "openrouter"),
            ("ANTHROPIC_API_KEY", "anthropic"),
            ("GOOGLE_API_KEY", "google"),
            ("AZURE_OPENAI_API_KEY", "azure"),
        ]
        
        migrated = 0
        for env_var, provider in patterns:
            if env_var in os.environ:
                value = os.environ[env_var]
                await manager.add_key(provider, value)
                click.echo(f"✓ Migrated {env_var} to secure storage")
                migrated += 1
                
        # Also check LIGHTNING_API_KEY_* pattern
        for key, value in os.environ.items():
            if key.startswith("LIGHTNING_API_KEY_"):
                provider = key[18:].lower()
                await manager.add_key(provider, value)
                click.echo(f"✓ Migrated {key} to secure storage")
                migrated += 1
        
        if migrated > 0:
            click.echo(f"\nMigrated {migrated} API keys to secure storage")
            click.echo("\n⚠️  You can now remove these from your environment variables")
            click.echo("Keys are stored encrypted in: .lightning/secrets.enc")
        else:
            click.echo("No API keys found to migrate")
    
    asyncio.run(_migrate())


if __name__ == "__main__":
    cli()