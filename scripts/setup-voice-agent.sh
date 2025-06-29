#!/bin/bash

# Lightning Voice Agent Setup Script
# This script helps set up the voice agent for local development

set -e

echo "🎤 Lightning Voice Agent Setup"
echo "================================"

# Check if running from correct directory
if [[ ! -f "docker-compose.local.yml" ]]; then
    echo "❌ Please run this script from the Lightning root directory"
    exit 1
fi

# Check for required environment file
if [[ ! -f ".env.local" ]]; then
    echo "❌ .env.local file not found. Please ensure it exists with required configuration."
    exit 1
fi

# Function to check if variable is set in .env.local
check_env_var() {
    local var_name=$1
    local required=${2:-true}
    
    if grep -q "^${var_name}=" .env.local; then
        local value=$(grep "^${var_name}=" .env.local | cut -d'=' -f2- | sed 's/^"//' | sed 's/"$//')
        if [[ -n "$value" && "$value" != "your_"* ]]; then
            echo "✅ $var_name is configured"
            return 0
        fi
    fi
    
    if [[ "$required" == "true" ]]; then
        echo "❌ $var_name is not configured in .env.local"
        return 1
    else
        echo "⚠️  $var_name is not configured (optional)"
        return 0
    fi
}

echo ""
echo "📋 Checking environment configuration..."

# Check required variables
MISSING_REQUIRED=false

if ! check_env_var "OPENAI_API_KEY"; then
    MISSING_REQUIRED=true
fi

if ! check_env_var "TWILIO_ACCOUNT_SID" false; then
    echo "ℹ️  Twilio configuration is optional for development"
fi

if ! check_env_var "TWILIO_AUTH_TOKEN" false; then
    echo "ℹ️  Set TWILIO_* variables for actual phone calling"
fi

if ! check_env_var "TWILIO_PHONE_NUMBER" false; then
    echo "ℹ️  Without Twilio config, only testing mode available"
fi

if [[ "$MISSING_REQUIRED" == "true" ]]; then
    echo ""
    echo "❌ Missing required configuration. Please update .env.local with:"
    echo "   OPENAI_API_KEY=sk-your-key-here"
    echo ""
    echo "   Optional (for actual calling):"
    echo "   TWILIO_ACCOUNT_SID=your_account_sid"
    echo "   TWILIO_AUTH_TOKEN=your_auth_token"
    echo "   TWILIO_PHONE_NUMBER=+1234567890"
    echo "   NGROK_AUTHTOKEN=your_ngrok_token"
    exit 1
fi

echo ""
echo "🚀 Starting voice agent setup..."

# Function to start services with error handling
start_services() {
    local profile=$1
    local description=$2
    
    echo ""
    echo "🔧 Starting $description..."
    
    if ! docker compose --profile "$profile" up -d; then
        echo "❌ Failed to start $description"
        return 1
    fi
    
    echo "✅ $description started successfully"
    return 0
}

# Check what the user wants to start
echo ""
echo "🎯 What would you like to start?"
echo "1) Voice agent only (inbound calls)"
echo "2) Voice agent with ngrok tunnel (for webhook testing)"
echo "3) Full stack including outbound calling"
echo "4) Everything (recommended for development)"

read -p "Enter choice (1-4): " choice

case $choice in
    1)
        start_services "voice-agent" "voice agent (inbound only)"
        FRONTEND_URL="http://localhost:3001"
        WEBHOOK_URL="http://localhost:8081/twiml"
        NGROK_ENABLED=false
        ;;
    2)
        start_services "voice-agent" "voice agent with ngrok"
        docker compose --profile ngrok up -d
        FRONTEND_URL="http://localhost:3001"
        NGROK_ENABLED=true
        ;;
    3)
        start_services "voice-agent" "voice agent"
        start_services "voice-agent-outbound" "outbound calling"
        FRONTEND_URL="http://localhost:3001"
        WEBHOOK_URL="http://localhost:8081/twiml"
        NGROK_ENABLED=false
        ;;
    4)
        start_services "all" "full Lightning stack"
        docker compose --profile ngrok up -d 2>/dev/null || echo "⚠️  Ngrok tunnel failed (optional)"
        FRONTEND_URL="http://localhost:3001"
        NGROK_ENABLED=true
        ;;
    *)
        echo "❌ Invalid choice"
        exit 1
        ;;
esac

# Wait for services to be ready
echo ""
echo "⏳ Waiting for services to be ready..."
sleep 10

# Check service health
echo ""
echo "🔍 Checking service health..."

# Check Lightning API
if curl -s http://localhost:8000/health > /dev/null; then
    echo "✅ Lightning Core API is healthy"
else
    echo "⚠️  Lightning Core API is not responding"
fi

# Check Context Hub
if curl -s http://localhost:3000/health > /dev/null 2>&1; then
    echo "✅ Context Hub is healthy"
else
    echo "⚠️  Context Hub is not responding"
fi

# Check Voice Agent
if curl -s http://localhost:8081/health > /dev/null; then
    echo "✅ Voice Agent Server is healthy"
    
    # Show health details
    echo ""
    echo "📊 Voice Agent Status:"
    curl -s http://localhost:8081/health | jq . 2>/dev/null || curl -s http://localhost:8081/health
else
    echo "❌ Voice Agent Server is not responding"
fi

# Get ngrok URL if enabled
NGROK_URL=""
if [[ "$NGROK_ENABLED" == "true" ]]; then
    echo ""
    echo "🌐 Getting ngrok tunnel URL..."
    sleep 5
    
    # Try to get ngrok URL (this is a simplified approach)
    if docker compose logs ngrok 2>/dev/null | grep -o 'https://[^[:space:]]*\.ngrok\.io' | head -1 > /tmp/ngrok_url; then
        NGROK_URL=$(cat /tmp/ngrok_url)
        echo "✅ Ngrok tunnel: $NGROK_URL"
        WEBHOOK_URL="$NGROK_URL/twiml"
        rm -f /tmp/ngrok_url
    else
        echo "⚠️  Could not determine ngrok URL automatically"
        echo "   Check logs: docker compose logs ngrok"
    fi
fi

# Show final status and next steps
echo ""
echo "🎉 Voice Agent Setup Complete!"
echo "================================"
echo ""
echo "📱 Services Running:"
echo "   • Voice Agent Server: http://localhost:8081"
echo "   • Monitoring Frontend: $FRONTEND_URL"
echo "   • Lightning Core API: http://localhost:8000"
echo "   • Context Hub: http://localhost:3000"

if [[ -n "$WEBHOOK_URL" ]]; then
    echo ""
    echo "🔗 Webhook Configuration:"
    echo "   Twilio Webhook URL: $WEBHOOK_URL"
    
    if [[ -n "$NGROK_URL" ]]; then
        echo "   (Use this URL in your Twilio console)"
    fi
fi

echo ""
echo "🛠️  Next Steps:"
echo "   1. Configure Twilio webhook URL (if using real phone number)"
echo "   2. Open monitoring interface: $FRONTEND_URL"
echo "   3. Test inbound calls to your Twilio number"

if [[ $choice -ge 3 ]]; then
    echo "   4. Test outbound calling:"
    echo "      docker compose exec voice-agent-outbound python outbound_agent.py \\"
    echo "        --phone \"+1234567890\" --objective \"Test call\""
fi

echo ""
echo "📚 Documentation: agents/voice-agent/README.md"
echo "🔍 Check logs: docker compose logs voice-agent-server"
echo "🏥 Health check: curl http://localhost:8081/health"

echo ""
echo "🎤 Voice Agent is ready!"