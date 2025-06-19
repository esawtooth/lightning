# API Key Configuration Guide

This guide explains how to configure and manage API keys for Lightning Core's model registry and LLM providers.

## Overview

Lightning Core supports multiple methods for configuring API keys:

1. **Environment Variables** (default, simple)
2. **Local Encrypted Storage** (secure, recommended for development)
3. **Cloud Secret Managers** (future: Azure Key Vault, AWS Secrets Manager)

## Quick Start

### Method 1: Environment Variables (Simplest)

```bash
# Direct provider format
export OPENAI_API_KEY=sk-...
export OPENROUTER_API_KEY=sk-or-...

# Lightning format (recommended)
export LIGHTNING_API_KEY_OPENAI=sk-...
export LIGHTNING_API_KEY_OPENROUTER=sk-or-...
```

### Method 2: Local Encrypted Storage (More Secure)

```bash
# Initialize secure storage
python -m lightning_core.cli.keys init --use-local

# Add keys
python -m lightning_core.cli.keys add openai sk-...
python -m lightning_core.cli.keys add openrouter sk-or-...

# List keys (without showing values)
python -m lightning_core.cli.keys list
```

### Method 3: Migrate Existing Keys

```bash
# Automatically migrate from environment to secure storage
python -m lightning_core.cli.keys migrate
```

## Supported Providers

| Provider | Environment Variable | Lightning Format | Models |
|----------|---------------------|------------------|---------|
| OpenAI | `OPENAI_API_KEY` | `LIGHTNING_API_KEY_OPENAI` | GPT-4o, GPT-4, O1, O3 |
| OpenRouter | `OPENROUTER_API_KEY` | `LIGHTNING_API_KEY_OPENROUTER` | Claude, Gemini, Llama, etc |
| Anthropic | `ANTHROPIC_API_KEY` | `LIGHTNING_API_KEY_ANTHROPIC` | Claude (direct) |
| Google | `GOOGLE_API_KEY` | `LIGHTNING_API_KEY_GOOGLE` | Gemini |
| Azure OpenAI | `AZURE_OPENAI_API_KEY` | `LIGHTNING_API_KEY_AZURE` | GPT-4, etc |

## Key Management CLI

### List Keys
```bash
# List all keys
python -m lightning_core.cli.keys list

# List keys for specific provider
python -m lightning_core.cli.keys list --provider openai

# Show masked key values (careful!)
python -m lightning_core.cli.keys list --show-values
```

### Add Keys
```bash
# Add key with default 90-day expiration
python -m lightning_core.cli.keys add openai sk-...

# Add key with custom expiration
python -m lightning_core.cli.keys add openai sk-... --expires-days 180

# Add key that never expires
python -m lightning_core.cli.keys add openai sk-... --expires-days 0
```

### Rotate Keys
```bash
# Rotate a provider's key (keeps old key active for transition)
python -m lightning_core.cli.keys rotate openai sk-new-key...
```

### Revoke Keys
```bash
# Revoke a specific key by ID
python -m lightning_core.cli.keys revoke openai openai_1234567890.123
```

### Test Keys
```bash
# Test if a key is valid
python -m lightning_core.cli.keys test openai
python -m lightning_core.cli.keys test openrouter
```

## Security Features

### 1. Local Encrypted Storage

When using `--use-local`, keys are:
- Encrypted using Fernet (symmetric encryption)
- Stored in `.lightning/secrets.enc`
- Encryption key in `.lightning/secret.key` (keep this safe!)
- Files have restricted permissions (owner read/write only)

### 2. Key Rotation

- Keys can have expiration dates
- Automatic rotation reminders
- Multiple keys per provider supported
- Graceful transition period during rotation

### 3. Usage Tracking

- Track which keys are being used
- Monitor usage frequency
- Identify unused keys for cleanup

## Configuration in Code

### Using the Key Manager Directly

```python
from lightning_core.security.key_manager import get_key_manager

# Get a key
manager = await get_key_manager()
openai_key = await manager.get_key("openai")

# Add a new key
await manager.add_key("openai", "sk-new-key...")

# Rotate keys
await manager.rotate_key("openai", "sk-newer-key...")
```

### Automatic Provider Integration

The model registry automatically uses the key manager:

```python
from lightning_core.llm import get_completions_api

# Keys are loaded automatically
api = get_completions_api()
response = await api.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello"}]
)
```

## Best Practices

### 1. Use the Lightning Format

```bash
# Preferred
export LIGHTNING_API_KEY_OPENAI=sk-...

# Also works but less preferred
export OPENAI_API_KEY=sk-...
```

### 2. Set Key Expiration

```bash
# Set reasonable expiration times
python -m lightning_core.cli.keys add openai sk-... --expires-days 90
```

### 3. Use Encrypted Storage for Development

```bash
# Initialize once
python -m lightning_core.cli.keys init --use-local

# Keys are now encrypted at rest
```

### 4. Regular Key Rotation

```bash
# Rotate keys periodically
python -m lightning_core.cli.keys rotate openai sk-new...

# Old keys remain active during transition
```

### 5. Monitor Key Usage

```bash
# Check which keys are active
python -m lightning_core.cli.keys list

# Remove unused keys
python -m lightning_core.cli.keys revoke openai old_key_id
```

## Environment Variables Reference

### Required for Providers

```bash
# Option 1: Direct format
export OPENAI_API_KEY=sk-...
export OPENROUTER_API_KEY=sk-or-...

# Option 2: Lightning format (recommended)
export LIGHTNING_API_KEY_OPENAI=sk-...
export LIGHTNING_API_KEY_OPENROUTER=sk-or-...
```

### Key Management Configuration

```bash
# Use local encrypted storage instead of env vars
export LIGHTNING_SECRET_PROVIDER=local

# Future: Use cloud secret manager
export LIGHTNING_SECRET_PROVIDER=azure_keyvault
export AZURE_KEYVAULT_URL=https://myvault.vault.azure.net/
```

## Troubleshooting

### No API Key Found

```bash
# Check if keys are configured
python -m lightning_core.cli.keys list

# Test specific provider
python -m lightning_core.cli.keys test openai
```

### Invalid API Key

```bash
# Test the key
python -m lightning_core.cli.keys test openai

# If invalid, update it
python -m lightning_core.cli.keys rotate openai sk-new-valid-key...
```

### Permission Errors

```bash
# Fix permissions on secret files
chmod 600 .lightning/secret.key
chmod 600 .lightning/secrets.enc
```

### Lost Encryption Key

If you lose `.lightning/secret.key`, you'll need to:
1. Delete `.lightning/secrets.enc`
2. Re-initialize: `python -m lightning_core.cli.keys init --use-local`
3. Re-add all keys

## Example .env.example

Create this file to document required keys:

```bash
# Lightning Core API Keys
# Use one of these formats for each provider:

# OpenAI (required for GPT models)
OPENAI_API_KEY=sk-...
# or
LIGHTNING_API_KEY_OPENAI=sk-...

# OpenRouter (required for Claude, Gemini via OpenRouter)
OPENROUTER_API_KEY=sk-or-...
# or
LIGHTNING_API_KEY_OPENROUTER=sk-or-...

# Anthropic (optional, for direct Claude access)
ANTHROPIC_API_KEY=sk-ant-...
# or
LIGHTNING_API_KEY_ANTHROPIC=sk-ant-...

# Key Management (optional)
LIGHTNING_SECRET_PROVIDER=environment  # or 'local' for encrypted storage
```

## Multi-Tenant Considerations

For production environments with multiple users:

1. **Per-User Keys**: Future enhancement to support user-specific keys
2. **Key Pools**: Multiple keys per provider for load balancing
3. **Usage Limits**: Set per-key or per-user usage limits
4. **Audit Logging**: Track key usage by user and agent

## Security Checklist

- [ ] Never commit API keys to version control
- [ ] Use `.gitignore` for `.env` and `.lightning/` directory
- [ ] Rotate keys regularly (every 90 days recommended)
- [ ] Use encrypted storage for development
- [ ] Monitor key usage and revoke unused keys
- [ ] Set up alerts for expiring keys
- [ ] Use separate keys for development/staging/production
- [ ] Implement key access logging