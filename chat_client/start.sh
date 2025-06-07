#!/bin/bash

set -e

echo "⚡ Lightning Chat - Starting Gateway"

# Verify required environment variables
check_env_var() {
    if [ -z "${!1}" ]; then
        echo "❌ Missing required environment variable: $1"
        exit 1
    fi
}

check_env_var "AUTH_API_URL"
check_env_var "JWT_SIGNING_KEY"

# Run the gateway on HTTPS port 443
exec python -m uvicorn gateway_app:app --host 0.0.0.0 --port 443

