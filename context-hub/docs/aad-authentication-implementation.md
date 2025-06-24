# Azure AD/Entra Authentication Implementation

This document describes the complete Azure AD authentication implementation for Context Hub.

## Overview

Context Hub now supports enterprise-grade authentication using Azure AD (Entra ID) with:
- Multi-tenant support
- Desktop app authentication
- Token-based API access
- User isolation

## Components

### 1. Infrastructure (Pulumi)

The AAD app registration is managed in `/infra/__main__.py`:

```python
aad_app = azuread.Application(
    "aad-app",
    display_name=f"Vextir-{stack_suffix}",
    sign_in_audience="AzureADMultipleOrgs",  # Multi-tenant
    # ... configuration for web, desktop, API, roles, etc.
)
```

Key features:
- Multi-tenant support (`AzureADMultipleOrgs`)
- Desktop app support (public client with `http://localhost:9899/callback`)
- Web app redirect URIs
- App roles for RBAC (Admin, User)
- Microsoft Graph permissions

### 2. Server-Side Authentication

#### Auth Middleware (`src/api/auth_middleware.rs`)
- Validates Bearer tokens from Authorization header
- Falls back to X-User-Id header for backward compatibility
- Extracts user context for all API requests

#### Updated API (`src/api/legacy.rs`)
- All endpoints now require authentication
- User context available in all handlers via `Extension<AuthContext>`
- Health endpoint remains unauthenticated

#### Token Validation
- Uses Azure JWKS endpoint for RS256 validation
- Configurable via `AZURE_JWKS_URL` environment variable
- Falls back to HS256 for development

### 3. Desktop App Authentication

#### AAD Integration (`macos-app/src/auth/aad.rs`)
- OAuth 2.0 flow with PKCE
- Automatic token refresh
- Secure storage in macOS Keychain
- ID token parsing for user info

#### Configuration
1. Run `./get-aad-config.sh` to fetch AAD config from Pulumi
2. Creates `aad-config.json` with client ID, tenant ID, etc.
3. App loads config on startup

## Deployment

### GitHub Actions

The deployment workflow (`/.github/workflows/deploy.yml`) automatically:
1. Uses service principal credentials as AAD app credentials
2. Configures all containers with AAD settings
3. Exports configuration for desktop apps

### Environment Variables

Context Hub containers receive:
- `AAD_CLIENT_ID` - Application client ID
- `AAD_TENANT_ID` - Azure tenant ID
- `AZURE_JWKS_URL` - JWKS endpoint for token validation

## Usage

### For Desktop App Users

1. Launch Context Hub desktop app
2. Click "Login with Azure"
3. Authenticate in browser
4. App receives tokens and stores securely
5. All API calls include Bearer token

### For API Consumers

Include the Bearer token in all requests:
```
Authorization: Bearer <access_token>
```

### For Developers

1. Get AAD configuration:
   ```bash
   cd macos-app
   ./get-aad-config.sh
   ```

2. Build and run:
   ```bash
   cargo build --release
   ./target/release/ContextHub
   ```

## Security Features

1. **Token Validation**: All tokens validated against Azure AD JWKS
2. **User Isolation**: Each user's data is isolated by user ID
3. **Secure Storage**: Tokens stored in OS keychain
4. **Automatic Refresh**: Tokens refreshed before expiry
5. **PKCE Flow**: Protects against authorization code interception

## Multi-Tenant Support

The app supports multiple Azure AD tenants:
- Users from any organization can authenticate
- Each tenant's data is isolated
- Tenant ID included in user context

## Migration from Legacy Auth

The system maintains backward compatibility:
1. Bearer token (preferred) - Standard OAuth2
2. X-User-Id header (deprecated) - For legacy clients

Legacy clients should migrate to Bearer token authentication.

## Troubleshooting

### "Failed to read AAD config"
Run `./get-aad-config.sh` to fetch configuration from Pulumi.

### "Token validation failed"
Ensure `AZURE_JWKS_URL` is set correctly in the server environment.

### "Login failed"
Check that the AAD app registration includes your tenant in allowed tenants.

## Future Enhancements

1. **Conditional Access**: Support for Azure AD conditional access policies
2. **Group-Based Access**: Use Azure AD groups for permissions
3. **Guest Access**: B2B collaboration support
4. **Device Trust**: Require managed devices for access