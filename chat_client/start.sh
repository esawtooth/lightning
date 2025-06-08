#!/bin/bash

set -e

echo "⚡ Vextir Chat - Starting Gateway"

# Verify required environment variables
check_env_var() {
    if [ -z "${!1}" ]; then
        echo "❌ Missing required environment variable: $1"
        exit 1
    fi
}

check_env_var "AAD_CLIENT_ID"
check_env_var "AAD_TENANT_ID"
check_env_var "AAD_CLIENT_SECRET"

# Run the gateway on HTTPS port 443
exec python -m uvicorn gateway_app:app --host 0.0.0.0 --port 443

