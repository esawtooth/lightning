#!/usr/bin/env python3
"""
Comprehensive test script for Lightning Chat authorization flow.
Tests the complete registration → waitlist → admin approval → access flow.
"""

import requests
import json
import time
import os
from datetime import datetime

# Configuration
AUTH_SERVICE_URL = "http://localhost:8000"
CHAT_SERVICE_URL = "http://localhost:8001"
AUTH_API_URL = os.environ.get("AUTH_API_URL", "https://your-function-app.azurewebsites.net/api")

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    END = '\033[0m'
    BOLD = '\033[1m'

def log(message, color=Colors.CYAN):
    print(f"{color}{datetime.now().strftime('%H:%M:%S')} - {message}{Colors.END}")

def log_success(message):
    log(f"✅ {message}", Colors.GREEN)

def log_error(message):
    log(f"❌ {message}", Colors.RED)

def log_warning(message):
    log(f"⚠️  {message}", Colors.YELLOW)

def log_info(message):
    log(f"ℹ️  {message}", Colors.BLUE)

def test_service_health():
    """Test if services are running."""
    log_info("Testing service health...")
    
    try:
        # Test auth service
        response = requests.get(f"{AUTH_SERVICE_URL}/health", timeout=5)
        if response.status_code == 200:
            log_success("Auth service is healthy")
        else:
            log_error(f"Auth service unhealthy: {response.status_code}")
            return False
    except Exception as e:
        log_error(f"Auth service unreachable: {e}")
        return False
    
    try:
        # Test chat service
        response = requests.get(f"{CHAT_SERVICE_URL}/health", timeout=5)
        if response.status_code == 200:
            log_success("Chat service is healthy")
        else:
            log_error(f"Chat service unhealthy: {response.status_code}")
            return False
    except Exception as e:
        log_error(f"Chat service unreachable: {e}")
        return False
    
    return True

def test_user_registration():
    """Test user registration flow."""
    log_info("Testing user registration...")
    
    # Test data
    test_users = [
        {"username": "testuser1", "password": "password123", "email": "test1@example.com"},
        {"username": "testuser2", "password": "password456", "email": "test2@example.com"},
        {"username": "adminuser", "password": "admin123", "email": "admin@example.com"}
    ]
    
    session = requests.Session()
    
    for user in test_users:
        try:
            response = session.post(f"{AUTH_SERVICE_URL}/register", data=user, allow_redirects=False)
            
            if response.status_code == 302:  # Redirect to login with success message
                log_success(f"User {user['username']} registered successfully")
            else:
                log_error(f"Registration failed for {user['username']}: {response.status_code}")
                return False
                
        except Exception as e:
            log_error(f"Registration error for {user['username']}: {e}")
            return False
    
    return True

def test_waitlist_login_attempt():
    """Test that waitlisted users cannot login."""
    log_info("Testing waitlist login restriction...")
    
    session = requests.Session()
    
    try:
        response = session.post(f"{AUTH_SERVICE_URL}/login", 
                              data={"username": "testuser1", "password": "password123"}, 
                              allow_redirects=False)
        
        if response.status_code == 302:
            # Check if redirected with pending account error
            location = response.headers.get('Location', '')
            if 'account_pending' in location:
                log_success("Waitlisted user correctly blocked from login")
                return True
        
        log_error("Waitlisted user was allowed to login")
        return False
        
    except Exception as e:
        log_error(f"Waitlist login test error: {e}")
        return False

def create_admin_user():
    """Create an admin user directly via API."""
    log_info("Creating admin user...")
    
    try:
        # Register admin user first
        admin_data = {
            "username": "adminuser",
            "password": "admin123",
            "email": "admin@example.com"
        }
        
        response = requests.post(f"{AUTH_API_URL}/register", json=admin_data, timeout=10)
        
        if response.status_code in [201, 409]:  # Created or already exists
            log_success("Admin user registered")
            
            # Note: In a real scenario, you'd manually update the database to set role=admin
            # For testing, we'll assume this is done manually or via a separate script
            log_warning("Manual step required: Set adminuser role to 'admin' and status to 'approved' in database")
            return True
        else:
            log_error(f"Admin registration failed: {response.status_code}")
            return False
            
    except Exception as e:
        log_error(f"Admin creation error: {e}")
        return False

def test_admin_login():
    """Test admin login after manual approval."""
    log_info("Testing admin login (requires manual approval)...")
    
    session = requests.Session()
    
    try:
        response = session.post(f"{AUTH_SERVICE_URL}/login", 
                              data={"username": "adminuser", "password": "admin123"}, 
                              allow_redirects=False)
        
        if response.status_code == 302:
            location = response.headers.get('Location', '')
            if '/chat' in location:
                log_success("Admin login successful")
                
                # Get auth token from cookies
                auth_token = None
                for cookie in session.cookies:
                    if cookie.name == 'auth_token':
                        auth_token = cookie.value
                        break
                
                if auth_token:
                    log_success("Admin auth token obtained")
                    return session, auth_token
                else:
                    log_warning("Admin logged in but no auth token found")
                    return session, None
            else:
                log_error(f"Admin login redirected to unexpected location: {location}")
        else:
            log_error(f"Admin login failed: {response.status_code}")
        
        return None, None
        
    except Exception as e:
        log_error(f"Admin login error: {e}")
        return None, None

def test_admin_panel_access(session, auth_token):
    """Test admin panel access."""
    log_info("Testing admin panel access...")
    
    if not session:
        log_error("No admin session available")
        return False
    
    try:
        response = session.get(f"{AUTH_SERVICE_URL}/admin", allow_redirects=False)
        
        if response.status_code == 200:
            log_success("Admin panel accessible")
            return True
        elif response.status_code == 302:
            location = response.headers.get('Location', '')
            if 'admin_required' in location:
                log_error("Admin access denied - role not set to admin")
            else:
                log_error(f"Admin panel redirected to: {location}")
        else:
            log_error(f"Admin panel access failed: {response.status_code}")
        
        return False
        
    except Exception as e:
        log_error(f"Admin panel access error: {e}")
        return False

def test_user_list_api(session):
    """Test admin API for user list."""
    log_info("Testing admin user list API...")
    
    if not session:
        log_error("No admin session available")
        return False
    
    try:
        response = session.get(f"{AUTH_SERVICE_URL}/admin/api/users")
        
        if response.status_code == 200:
            data = response.json()
            users = data.get('users', [])
            log_success(f"User list API working - found {len(users)} users")
            log_info(f"Pending: {data.get('pending_count', 0)}, Approved: {data.get('approved_count', 0)}, Rejected: {data.get('rejected_count', 0)}")
            return True
        else:
            log_error(f"User list API failed: {response.status_code}")
        
        return False
        
    except Exception as e:
        log_error(f"User list API error: {e}")
        return False

def test_user_approval_api(session):
    """Test admin API for user approval."""
    log_info("Testing user approval API...")
    
    if not session:
        log_error("No admin session available")
        return False
    
    try:
        # First get user list to find a user to approve
        response = session.get(f"{AUTH_SERVICE_URL}/admin/api/users")
        if response.status_code != 200:
            log_error("Cannot get user list for approval test")
            return False
        
        data = response.json()
        users = data.get('users', [])
        
        # Find a waitlisted user
        waitlist_user = None
        for user in users:
            if user.get('status') == 'waitlist' and user.get('username') != 'adminuser':
                waitlist_user = user
                break
        
        if not waitlist_user:
            log_warning("No waitlisted users found to test approval")
            return True
        
        # Test approval
        approval_data = {
            "action": "approve",
            "user_id": waitlist_user.get('user_id')
        }
        
        response = session.post(f"{AUTH_SERVICE_URL}/admin/api/user-action", 
                              json=approval_data)
        
        if response.status_code == 200:
            log_success(f"User {waitlist_user.get('username')} approved successfully")
            return True
        else:
            log_error(f"User approval failed: {response.status_code}")
            
        return False
        
    except Exception as e:
        log_error(f"User approval API error: {e}")
        return False

def test_approved_user_login():
    """Test that approved user can now login."""
    log_info("Testing approved user login...")
    
    session = requests.Session()
    
    try:
        response = session.post(f"{AUTH_SERVICE_URL}/login", 
                              data={"username": "testuser1", "password": "password123"}, 
                              allow_redirects=False)
        
        if response.status_code == 302:
            location = response.headers.get('Location', '')
            if '/chat' in location:
                log_success("Approved user can now login successfully")
                return True
            elif 'account_pending' in location:
                log_warning("User still shows as pending - approval may not have taken effect")
            else:
                log_error(f"Approved user login redirected to: {location}")
        else:
            log_error(f"Approved user login failed: {response.status_code}")
        
        return False
        
    except Exception as e:
        log_error(f"Approved user login error: {e}")
        return False

def test_chat_access():
    """Test that approved user can access chat."""
    log_info("Testing chat access for approved user...")
    
    session = requests.Session()
    
    try:
        # Login first
        response = session.post(f"{AUTH_SERVICE_URL}/login", 
                              data={"username": "testuser1", "password": "password123"}, 
                              allow_redirects=True)
        
        if response.status_code == 200:
            # Check if we're at the chat interface
            if 'chainlit' in response.text.lower() or 'chat' in response.text.lower():
                log_success("Approved user can access chat interface")
                return True
            else:
                log_warning("User logged in but chat interface not confirmed")
        else:
            log_error(f"Chat access test failed: {response.status_code}")
        
        return False
        
    except Exception as e:
        log_error(f"Chat access error: {e}")
        return False

def main():
    """Run comprehensive authorization flow test."""
    print(f"\n{Colors.BOLD}{Colors.PURPLE}Lightning Chat Authorization Flow Test{Colors.END}")
    print(f"{Colors.PURPLE}=" * 50 + Colors.END)
    
    # Test sequence
    tests = [
        ("Service Health", test_service_health),
        ("User Registration", test_user_registration),
        ("Waitlist Login Block", test_waitlist_login_attempt),
        ("Admin User Creation", create_admin_user),
    ]
    
    # Run basic tests
    all_passed = True
    for test_name, test_func in tests:
        log_info(f"Running: {test_name}")
        if not test_func():
            all_passed = False
            log_error(f"Test failed: {test_name}")
        else:
            log_success(f"Test passed: {test_name}")
        print()
    
    if not all_passed:
        log_error("Basic tests failed. Please fix issues before continuing.")
        return
    
    # Manual step reminder
    print(f"{Colors.YELLOW}{Colors.BOLD}MANUAL STEP REQUIRED:{Colors.END}")
    print(f"{Colors.YELLOW}Please manually set 'adminuser' role to 'admin' and status to 'approved' in the database{Colors.END}")
    print(f"{Colors.YELLOW}Then press Enter to continue with admin tests...{Colors.END}")
    input()
    
    # Admin tests
    admin_session, admin_token = test_admin_login()
    
    if admin_session:
        admin_tests = [
            ("Admin Panel Access", lambda: test_admin_panel_access(admin_session, admin_token)),
            ("User List API", lambda: test_user_list_api(admin_session)),
            ("User Approval API", lambda: test_user_approval_api(admin_session)),
            ("Approved User Login", test_approved_user_login),
            ("Chat Access", test_chat_access),
        ]
        
        for test_name, test_func in admin_tests:
            log_info(f"Running: {test_name}")
            if not test_func():
                all_passed = False
                log_error(f"Test failed: {test_name}")
            else:
                log_success(f"Test passed: {test_name}")
            print()
    else:
        log_error("Admin tests skipped due to login failure")
        all_passed = False
    
    # Final result
    print(f"\n{Colors.BOLD}Final Result:{Colors.END}")
    if all_passed:
        log_success("All authorization flow tests passed! 🎉")
    else:
        log_error("Some tests failed. Please review the issues above.")
    
    print(f"\n{Colors.PURPLE}Test completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.END}")

if __name__ == "__main__":
    main()
