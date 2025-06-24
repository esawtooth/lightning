#!/usr/bin/env python3
"""
Script to check the deployment status of Azure Functions and UI containers.
"""

import os
import requests
import time
import sys

def check_endpoint(url, expected_status=200, timeout=5):
    """Check if an endpoint is responding with expected status."""
    try:
        response = requests.get(url, timeout=timeout)
        return response.status_code == expected_status
    except requests.RequestException:
        return False

def check_deployment_status():
    """Check the status of key endpoints."""
    domain = os.environ.get("DOMAIN", "vextir.com")
    endpoints = [
        ("API Health", f"https://api.{domain}/api/health", 200),
        ("Azure Function Events", f"https://api.{domain}/api/events", 405),  # POST endpoint, GET should return 405
        ("UI Website", f"https://www.{domain}", 200),
        ("Voice WebSocket", f"https://voice-ws.{domain}", 200),
    ]
    
    print("Checking deployment status...")
    print("=" * 50)
    
    all_healthy = True
    for name, url, expected_status in endpoints:
        try:
            response = requests.get(url, timeout=10)
            status = response.status_code
            if status == expected_status:
                print(f"✅ {name}: {status} (OK)")
            else:
                print(f"❌ {name}: {status} (Expected {expected_status})")
                all_healthy = False
        except requests.RequestException as e:
            print(f"❌ {name}: Connection failed ({e})")
            all_healthy = False
    
    print("=" * 50)
    if all_healthy:
        print("🎉 All services are healthy!")
        return True
    else:
        print("⚠️  Some services are not responding correctly.")
        return False

if __name__ == "__main__":
    if check_deployment_status():
        sys.exit(0)
    else:
        sys.exit(1)
