#!/bin/bash

set -e

echo "⚡ Vextir Chat - Starting Gateway"

# Verify required environment variables (with fallbacks for legacy names)
check_any_env_var() {
    canonical=$1
    shift
    for var in "$@"; do
        if [ -n "${!var}" ]; then
            export "$canonical"="${!var}"
            return 0
        fi
    done
    echo "❌ Missing required environment variable: $canonical"
    echo "   Please set one of: $*"
    exit 1
}

# Support old ARM_/AZURE_ variable names for compatibility
check_any_env_var "AAD_CLIENT_ID" "AAD_CLIENT_ID" "ARM_CLIENT_ID" "AZURE_CLIENT_ID"
check_any_env_var "AAD_TENANT_ID" "AAD_TENANT_ID" "ARM_TENANT_ID" "AZURE_TENANT_ID"
check_any_env_var "AAD_CLIENT_SECRET" "AAD_CLIENT_SECRET" "ARM_CLIENT_SECRET" "AZURE_CLIENT_SECRET"

echo "✅ Azure AD authentication configured"

# Run the gateway on HTTP port 80
exec python -m uvicorn gateway_app:app --host 0.0.0.0 --port 80

