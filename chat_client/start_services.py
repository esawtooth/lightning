#!/bin/bash
"""
Startup script for Lightning Chat with Authentication Gateway.
This script starts both the authentication gateway and the Chainlit chat app.
"""

import os
import sys
import time
import signal
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor

def start_auth_gateway():
    """Start the authentication gateway on port 8000."""
    print("🔐 Starting Authentication Gateway on port 8000...")
    try:
        subprocess.run([
            sys.executable, "-m", "uvicorn", 
            "auth_app:app", 
            "--host", "0.0.0.0", 
            "--port", "8000",
            "--reload"
        ], check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Auth gateway failed to start: {e}")
        sys.exit(1)

def start_chainlit_app():
    """Start the Chainlit chat app on port 8001."""
    print("💬 Starting Chainlit Chat App on port 8001...")
    # Give auth gateway time to start
    time.sleep(2)
    try:
        subprocess.run([
            "chainlit", "run", "chainlit_app.py", 
            "--host", "0.0.0.0", 
            "--port", "8001"
        ], check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Chainlit app failed to start: {e}")
        sys.exit(1)

def signal_handler(signum, frame):
    """Handle shutdown signals."""
    print("\n🛑 Shutting down Lightning Chat services...")
    sys.exit(0)

def main():
    """Main startup function."""
    print("⚡ Lightning Chat - Starting Services")
    print("=" * 50)
    
    # Check required environment variables
    required_vars = ["AUTH_API_URL", "JWT_SIGNING_KEY"]
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        print("\nRequired environment variables:")
        print("- AUTH_API_URL: URL of the Azure Function auth endpoint")
        print("- JWT_SIGNING_KEY: Secret key for JWT token verification")
        sys.exit(1)
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start both services concurrently
    with ThreadPoolExecutor(max_workers=2) as executor:
        auth_future = executor.submit(start_auth_gateway)
        chat_future = executor.submit(start_chainlit_app)
        
        try:
            # Wait for both services
            auth_future.result()
            chat_future.result()
        except KeyboardInterrupt:
            print("\n🛑 Received shutdown signal")
        except Exception as e:
            print(f"❌ Service error: {e}")
        finally:
            print("👋 Lightning Chat services stopped")

if __name__ == "__main__":
    main()
