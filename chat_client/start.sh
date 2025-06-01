#!/bin/bash

# Lightning Chat - Multi-Service Startup Script
# This script starts both the authentication gateway and Chainlit chat app

set -e

echo "⚡ Lightning Chat - Starting Services"
echo "=" | sed 's/./=/g' | head -c 50 && echo

# Check required environment variables
check_env_var() {
    if [ -z "${!1}" ]; then
        echo "❌ Missing required environment variable: $1"
        return 1
    fi
}

echo "🔍 Checking environment variables..."
if ! check_env_var "AUTH_API_URL" || ! check_env_var "JWT_SIGNING_KEY"; then
    echo
    echo "Required environment variables:"
    echo "- AUTH_API_URL: URL of the Azure Function auth endpoint"
    echo "- JWT_SIGNING_KEY: Secret key for JWT token verification"
    echo "- SESSION_SECRET: Secret for session management (optional)"
    exit 1
fi

echo "✅ Environment variables OK"

# Function to cleanup background processes
cleanup() {
    echo
    echo "🛑 Shutting down Lightning Chat services..."
    jobs -p | xargs -r kill
    wait
    echo "👋 Lightning Chat services stopped"
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

# Start authentication gateway in background
echo "🔐 Starting Authentication Gateway on port 8000..."
python -m uvicorn auth_app:app --host 0.0.0.0 --port 8000 &
AUTH_PID=$!

# Wait a moment for auth gateway to start
sleep 3

# Check if auth gateway started successfully
if ! kill -0 $AUTH_PID 2>/dev/null; then
    echo "❌ Authentication gateway failed to start"
    exit 1
fi

echo "✅ Authentication gateway started (PID: $AUTH_PID)"

# Start Chainlit app in background
echo "💬 Starting Chainlit Chat App on port 8001..."
chainlit run chainlit_app.py --host 0.0.0.0 --port 8001 &
CHAINLIT_PID=$!

# Wait a moment for Chainlit to start
sleep 3

# Check if Chainlit started successfully
if ! kill -0 $CHAINLIT_PID 2>/dev/null; then
    echo "❌ Chainlit app failed to start"
    kill $AUTH_PID 2>/dev/null || true
    exit 1
fi

echo "✅ Chainlit chat app started (PID: $CHAINLIT_PID)"
echo
echo "🚀 Lightning Chat is ready!"
echo "📱 Access the application at: http://localhost:8000"
echo "🔐 Users must authenticate before accessing chat"
echo
echo "Press Ctrl+C to stop all services"

# Wait for both processes
wait
