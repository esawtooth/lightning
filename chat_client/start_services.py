#!/bin/bash
"""
Startup script for Vextir Chat with Authentication Gateway.
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
    """Run the combined gateway on port 80."""
    print("🚀 Starting Gateway on port 80...")
    try:
        subprocess.run([
            sys.executable, "-m", "uvicorn",
            "gateway_app:app",
            "--host", "0.0.0.0",
            "--port", "80"
        ], check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Gateway failed to start: {e}")
        sys.exit(1)

def signal_handler(signum, frame):
    """Handle shutdown signals."""
    print("\n🛑 Shutting down Vextir Chat services...")
    sys.exit(0)

def main():
    """Main startup function."""
    print("⚡ Vextir Chat - Starting Services")
    print("=" * 50)
    
    # Check required environment variables
    required_vars = ["AAD_CLIENT_ID", "AAD_TENANT_ID", "AAD_CLIENT_SECRET"]
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        print("\nRequired environment variables:")
        print("- AAD_CLIENT_ID: Entra ID application ID")
        print("- AAD_TENANT_ID: Entra ID tenant ID")
        print("- AAD_CLIENT_SECRET: Client secret for the application")
        sys.exit(1)
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        start_gateway()
    except KeyboardInterrupt:
        print("\n🛑 Received shutdown signal")
    finally:
        print("👋 Vextir Chat services stopped")

if __name__ == "__main__":
    main()
