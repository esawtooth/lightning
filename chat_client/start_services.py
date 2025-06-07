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

def start_gateway():
    """Run the combined gateway on port 443."""
    print("🚀 Starting Gateway on port 443...")
    try:
        subprocess.run([
            sys.executable, "-m", "uvicorn",
            "gateway_app:app",
            "--host", "0.0.0.0",
            "--port", "443"
        ], check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Gateway failed to start: {e}")
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
    
    try:
        start_gateway()
    except KeyboardInterrupt:
        print("\n🛑 Received shutdown signal")
    finally:
        print("👋 Lightning Chat services stopped")

if __name__ == "__main__":
    main()
