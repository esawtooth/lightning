#!/usr/bin/env python3
"""
Script to test the deployed Vextir application endpoints.
"""

import requests
import json
import time

def test_endpoints():
    print("🧪 Testing Vextir Application Deployment")
    print("=" * 50)
    
    # Based on your infrastructure, these are the expected endpoints:
    # 1. Chainlit UI - Container Instance with public IP
    # 2. Azure Function - Function App endpoint
    
    print("\n🔍 Looking for deployed endpoints...")
    print("💡 Check the Azure portal for:")
    print("   - Container Instance 'chat-ui' public IP")
    print("   - Function App 'vextir-func-<hash>' URL")
    print()
    
    # Test scenarios to try once you have the URLs:
    test_scenarios = [
        {
            "name": "Authentication Flow",
            "description": "Test user registration and login",
            "example": "1. Visit https://<ui-url>/auth\n   2. Register new account\n   3. Login with credentials"
        },
        {
            "name": "Chat Interface", 
            "description": "Authenticated Chainlit chat UI",
            "example": "After login, access chat at https://<ui-url>/chat"
        },
        {
            "name": "Health Checks",
            "description": "Service health monitoring",
            "example": "GET https://<ui-url>/auth/health (Auth Gateway)\n   GET https://<ui-url>/chat/health (Chat Service)"
        },
        {
            "name": "Event API",
            "description": "Azure Function event endpoint", 
            "example": "POST https://<function-url>/api/events"
        },
        {
            "name": "User Authentication API",
            "description": "User registration and login endpoints",
            "example": "POST https://<function-url>/api/auth/register\n   POST https://<function-url>/api/auth/login"
        }
    ]
    
    print("🎯 Test Scenarios to Try:")
    for i, scenario in enumerate(test_scenarios, 1):
        print(f"\n{i}. {scenario['name']}")
        print(f"   📝 {scenario['description']}")
        print(f"   💻 {scenario['example']}")
    
    print("\n" + "=" * 50)
    print("🚀 Quick Start Guide:")
    print("1. Get endpoints from Azure portal")
    print("2. Visit the Vextir Chat UI in your browser")
    print("3. Register a new account or login")
    print("4. Access the authenticated chat interface")
    print("5. Try chatting with the AI assistant")
    print("6. Test repository integration features")
    print("7. Check the dashboard for events and analytics")

def get_azure_resources():
    """Helper to show how to find resources in Azure"""
    print("\n🔍 How to find your deployed resources:")
    print()
    print("Option 1 - Azure Portal:")
    print("1. Go to https://portal.azure.com")
    print("2. Navigate to Resource Group 'vextir'")
    print("3. Look for:")
    print("   - Container Instance 'chat-ui' → Get public IP (Gateway on :443)")
    print("   - Function App 'vextir-func-*' → Get URL (API endpoints)")
    print("   - Container Registry 'vextiracr' → Container images")
    print("   - Cosmos DB 'vextir-cosmos-*' → User and event storage")
    print()
    print("Option 2 - Azure CLI:")
    print("az container show --resource-group vextir --name chat-ui --query ipAddress.fqdn")
    print("az functionapp list --resource-group vextir --query '[].defaultHostName'")

if __name__ == "__main__":
    test_endpoints()
    get_azure_resources()
    print("\n✅ Ready to test your Vextir application!")
