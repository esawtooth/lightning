#!/bin/bash

set -e

echo "⚡ Vextir Chat - Starting Gateway"
echo "🐍 Python version: $(python --version)"
echo "📦 Working directory: $(pwd)"
echo "📁 Directory contents:"
ls -la

# Verify required environment variables (with fallbacks for legacy names)
check_any_env_var() {
    canonical=$1
    shift
    for var in "$@"; do
        if [ -n "${!var}" ]; then
            export "$canonical"="${!var}"
            echo "✅ Found $canonical from $var"
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

# Check if required files exist
echo "🔍 Checking required files..."
for file in gateway_app.py auth_app.py chainlit_app.py; do
    if [ -f "$file" ]; then
        echo "✅ Found $file"
    else
        echo "❌ Missing $file"
        exit 1
    fi
done

# Check if required directories exist
for dir in templates common events; do
    if [ -d "$dir" ]; then
        echo "✅ Found directory $dir"
    else
        echo "❌ Missing directory $dir"
        exit 1
    fi
done

# Test Python imports
echo "🧪 Testing Python imports..."
python -c "
try:
    import gateway_app
    print('✅ gateway_app import successful')
except Exception as e:
    print(f'❌ gateway_app import failed: {e}')
    exit(1)

try:
    import auth_app
    print('✅ auth_app import successful')
except Exception as e:
    print(f'❌ auth_app import failed: {e}')
    exit(1)

try:
    import chainlit_app
    print('✅ chainlit_app import successful')
except Exception as e:
    print(f'❌ chainlit_app import failed: {e}')
    exit(1)
"

if [ $? -ne 0 ]; then
    echo "❌ Python import test failed"
    exit 1
fi

echo "🚀 All checks passed, starting uvicorn..."

# Run the gateway on HTTP port 80 with enhanced logging
exec python -m uvicorn gateway_app:app \
    --host 0.0.0.0 \
    --port 80 \
    --log-level debug \
    --access-log \
    --use-colors
