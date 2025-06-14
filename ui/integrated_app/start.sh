#!/bin/bash

# Vextir Integrated Dashboard Startup Script

set -e

echo "🚀 Starting Vextir Integrated Dashboard..."

# Check if we're in the right directory
if [ ! -f "app.py" ]; then
    echo "❌ Error: app.py not found. Please run this script from the ui/integrated_app directory."
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Set default environment variables if not set
export API_BASE=${API_BASE:-"http://localhost:7071/api"}
export AUTH_GATEWAY_URL=${AUTH_GATEWAY_URL:-"http://localhost:8001"}
export CHAINLIT_URL=${CHAINLIT_URL:-"http://localhost:8000"}
export SESSION_SECRET=${SESSION_SECRET:-"your-secret-key-change-in-production"}

echo "🌐 Environment Configuration:"
echo "  API_BASE: $API_BASE"
echo "  AUTH_GATEWAY_URL: $AUTH_GATEWAY_URL"
echo "  CHAINLIT_URL: $CHAINLIT_URL"
echo ""

# Start the application
echo "🎯 Starting Vextir Integrated Dashboard on http://localhost:8002"
echo "📊 Dashboard: http://localhost:8002/"
echo "💬 Chat: http://localhost:8002/chat"
echo "📋 Tasks: http://localhost:8002/tasks"
echo "🔔 Notifications: http://localhost:8002/notifications"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

uvicorn app:app --host 0.0.0.0 --port 8002 --reload
