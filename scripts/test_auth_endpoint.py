#!/usr/bin/env python3
"""
Test the Auth endpoint after deployment to ensure it's working correctly.
This prevents issues like the 404 error that occurred with the Auth function.
"""

import os
import sys
import requests
import time
from urllib.parse import urlparse

def test_auth_endpoint(api_url: str, domain: str = "vextir.com", max_retries: int = 5) -> bool:
    """Test that the Auth endpoint returns a proper OAuth redirect."""
    auth_url = f"{api_url}/api/Auth?redirect=https://www.{domain}/"
    
    print(f"Testing Auth endpoint: {auth_url}")
    
    for attempt in range(max_retries):
        try:
            # Don't follow redirects - we want to check the redirect response
            response = requests.get(auth_url, allow_redirects=False, timeout=10)
            
            if response.status_code == 302:
                # Check redirect location
                location = response.headers.get('Location', '')
                if 'login.microsoftonline.com' in location and 'oauth2/v2.0/authorize' in location:
                    print(f"✅ Auth endpoint working correctly!")
                    print(f"   Status: {response.status_code}")
                    print(f"   Redirects to: {location[:80]}...")
                    return True
                else:
                    print(f"❌ Auth endpoint returned unexpected redirect: {location}")
                    return False
            elif response.status_code == 404:
                print(f"⚠️  Attempt {attempt + 1}/{max_retries}: Auth endpoint returned 404. Waiting 10s...")
                if attempt < max_retries - 1:
                    time.sleep(10)
                continue
            else:
                print(f"❌ Auth endpoint returned unexpected status: {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Error testing Auth endpoint: {e}")
            if attempt < max_retries - 1:
                print(f"   Retrying in 10s...")
                time.sleep(10)
            continue
    
    print(f"❌ Auth endpoint failed after {max_retries} attempts")
    return False

def test_health_endpoint(api_url: str) -> bool:
    """Test that the Health endpoint is accessible."""
    health_url = f"{api_url}/api/health"
    
    print(f"\nTesting Health endpoint: {health_url}")
    
    try:
        response = requests.get(health_url, timeout=10)
        if response.status_code == 200:
            print(f"✅ Health endpoint working correctly!")
            return True
        else:
            print(f"❌ Health endpoint returned status: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Error testing Health endpoint: {e}")
        return False

def main():
    """Run endpoint tests."""
    # Default to production API URL
    api_url = os.environ.get("API_URL", "https://api.vextir.com")
    domain = os.environ.get("DOMAIN", "vextir.com")
    
    if len(sys.argv) > 1:
        api_url = sys.argv[1].rstrip('/')
    if len(sys.argv) > 2:
        domain = sys.argv[2]
    
    print(f"Testing Azure Functions at: {api_url}")
    print(f"Using domain: {domain}")
    print("-" * 50)
    
    # Test both endpoints
    health_ok = test_health_endpoint(api_url)
    auth_ok = test_auth_endpoint(api_url, domain)
    
    print("-" * 50)
    
    if health_ok and auth_ok:
        print("\n✅ All endpoint tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Some endpoint tests failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()