#!/usr/bin/env python3
"""
Local development test script for Lightning Chat with Authentication.
This script helps test the authentication flow locally before deployment.
"""

import os
import sys
import time
import requests
import subprocess
from pathlib import Path

def check_dependencies():
    """Check if required dependencies are installed."""
    try:
        import chainlit
        import fastapi
        import uvicorn
        import jwt
        print("✅ All dependencies are installed")
        return True
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("Install with: pip install -r chat_client/requirements.txt")
        return False

def check_environment():
    """Check if required environment variables are set."""
    required_vars = {
        "AUTH_API_URL": "Azure Function auth endpoint URL",
        "JWT_SIGNING_KEY": "Secret key for JWT tokens"
    }
    
    missing = []
    for var, description in required_vars.items():
        if not os.environ.get(var):
            missing.append(f"  {var}: {description}")
    
    if missing:
        print("❌ Missing environment variables:")
        for var in missing:
            print(var)
        print("\nExample setup:")
        print("export AUTH_API_URL='https://your-function-app.azurewebsites.net/api/auth'")
        print("export JWT_SIGNING_KEY='your-secret-key-here'")
        return False
    
    print("✅ Environment variables are set")
    return True

def test_auth_endpoints():
    """Test the authentication endpoints if available."""
    auth_url = os.environ.get("AUTH_API_URL")
    if not auth_url:
        print("⏭️  Skipping auth endpoint tests (AUTH_API_URL not set)")
        return True
    
    print("🔍 Testing authentication endpoints...")
    
    # Test registration endpoint
    try:
        test_user = {
            "username": f"testuser_{int(time.time())}",
            "password": "testpass123"
        }
        
        register_url = f"{auth_url}/register"
        response = requests.post(register_url, json=test_user, timeout=10)
        
        if response.status_code == 201:
            print("✅ Registration endpoint working")
            
            # Test login endpoint
            login_url = f"{auth_url}/login"
            login_response = requests.post(login_url, json=test_user, timeout=10)
            
            if login_response.status_code == 200:
                token_data = login_response.json()
                if "token" in token_data:
                    print("✅ Login endpoint working")
                    return True
                else:
                    print("❌ Login response missing token")
            else:
                print(f"❌ Login failed: {login_response.status_code}")
        else:
            print(f"❌ Registration failed: {response.status_code}")
            
    except requests.RequestException as e:
        print(f"❌ Network error testing auth endpoints: {e}")
    
    return False

def start_local_services():
    """Start the local authentication and chat services."""
    os.chdir(Path(__file__).parent / "chat_client")
    
    print("🚀 Starting Lightning Chat services locally...")
    print("📍 Gateway: https://localhost")
    print("\nPress Ctrl+C to stop services")
    
    try:
        # Run the startup script
        subprocess.run(["./start.sh"], check=True)
    except subprocess.CalledProcessError:
        print("❌ Failed to start services")
        return False
    except KeyboardInterrupt:
        print("\n🛑 Services stopped by user")
        return True

def main():
    """Main test function."""
    print("⚡ Lightning Chat - Local Development Test")
    print("=" * 50)
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Check environment
    if not check_environment():
        print("\n💡 You can still test locally with mock auth by setting:")
        print("export AUTH_API_URL='http://localhost:9999/api/auth'")
        print("export JWT_SIGNING_KEY='test-key-123'")
        response = input("\nContinue anyway? (y/N): ").lower()
        if response != 'y':
            sys.exit(1)
    
    # Test auth endpoints if available
    test_auth_endpoints()
    
    print("\n" + "=" * 50)
    print("🎯 Test Checklist:")
    print("1. Visit https://localhost/auth")
    print("2. Try to access chat without logging in (should redirect)")
    print("3. Register a new account")
    print("4. Login with your credentials") 
    print("5. Access the chat interface")
    print("6. Send a test message")
    print("7. Check that events are logged")
    print("\n" + "=" * 50)
    
    # Start services
    start_local_services()

if __name__ == "__main__":
    main()
