#!/usr/bin/env python3
"""
Script to create the first admin user in the Vextir Chat system.
This script manually promotes a user to admin status in the database.
"""

import os
import json
import crypt
import asyncio
from datetime import datetime
from lightning_core.abstractions import Document
from lightning_core.runtime import LightningRuntime

# Configuration
DATABASE_NAME = os.environ.get("COSMOS_DATABASE", "vextir")
CONTAINER_NAME = os.environ.get("COSMOS_CONTAINER", "users")

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'
    BOLD = '\033[1m'

def log(message, color=Colors.BLUE):
    print(f"{color}{message}{Colors.END}")

def log_success(message):
    log(f"✅ {message}", Colors.GREEN)

def log_error(message):
    log(f"❌ {message}", Colors.RED)

def log_warning(message):
    log(f"⚠️  {message}", Colors.YELLOW)

def _hash_password(password: str, salt: str) -> str:
    """Hash password using bcrypt via the `crypt` module."""
    return crypt.crypt(password, salt)

async def create_admin_user():
    """Create or promote a user to admin status."""
    
    print(f"\n{Colors.BOLD}Vextir Chat - Admin User Creator{Colors.END}")
    print("=" * 40)
    
    # Initialize Lightning Runtime
    runtime = LightningRuntime()
    
    try:
        # Connect to storage provider
        log("Connecting to storage provider...")
        await runtime.initialize()
        log_success("Connected to storage provider")
        
        # Get admin user details
        print(f"\n{Colors.BOLD}Enter admin user details:{Colors.END}")
        username = input("Username: ").strip()
        email = input("Email: ").strip()
        password = input("Password: ").strip()
        
        if not all([username, email, password]):
            log_error("All fields are required")
            return
        
        # Check if user already exists
        try:
            existing_doc = await runtime.storage.get_document(CONTAINER_NAME, "user")
            if existing_doc and existing_doc.data.get("pk") == username:
                log_warning(f"User '{username}' already exists")
                
                # Ask if we should promote to admin
                promote = input("Promote existing user to admin? (y/N): ").strip().lower()
                if promote != 'y':
                    log("Operation cancelled")
                    return
                
                # Update existing user
                existing_doc.data["role"] = "admin"
                existing_doc.data["status"] = "approved"
                existing_doc.data["approved_at"] = datetime.utcnow().isoformat()
                existing_doc.data["approved_by"] = "system"
                
                if email and email != existing_doc.data.get("email", ""):
                    existing_doc.data["email"] = email
                
                await runtime.storage.update_document(CONTAINER_NAME, existing_doc)
                log_success(f"User '{username}' promoted to admin")
            else:
                raise Exception("User not found")
            
        except Exception:
            # User doesn't exist, create new one
            log(f"Creating new admin user '{username}'...")
            
            # Generate salt and hash password
            salt = crypt.mksalt(crypt.METHOD_BLOWFISH)
            password_hash = _hash_password(password, salt)
            
            # Create user document
            user_doc = Document(
                id="user",
                partition_key=username,
                data={
                    "id": "user",
                    "pk": username,
                    "hash": password_hash,
                    "salt": salt,
                    "email": email,
                    "role": "admin",
                    "status": "approved",
                    "created_at": datetime.utcnow().isoformat(),
                    "approved_at": datetime.utcnow().isoformat(),
                    "approved_by": "system"
                }
            )
            
            await runtime.storage.create_document(CONTAINER_NAME, user_doc)
            log_success(f"Admin user '{username}' created successfully")
        
        # Verify the user
        log("Verifying admin user...")
        user_doc = await runtime.storage.get_document(CONTAINER_NAME, "user")
        user = user_doc.data if user_doc else {}
        
        print(f"\n{Colors.BOLD}Admin User Details:{Colors.END}")
        print(f"Username: {user.get('pk')}")
        print(f"Email: {user.get('email', 'N/A')}")
        print(f"Role: {user.get('role')}")
        print(f"Status: {user.get('status')}")
        print(f"Created: {user.get('created_at')}")
        print(f"Approved: {user.get('approved_at')}")
        
        if user.get('role') == 'admin' and user.get('status') == 'approved':
            log_success("Admin user is ready to use!")
            print(f"\n{Colors.GREEN}You can now login to the admin panel at:{Colors.END}")
            print(f"{Colors.GREEN}https://localhost/auth/admin{Colors.END}")
        else:
            log_error("Admin user setup incomplete")
            
    except Exception as e:
        log_error(f"Error: {e}")
        return

async def list_users():
    """List all users in the database."""
    
    print(f"\n{Colors.BOLD}Vextir Chat - User List{Colors.END}")
    print("=" * 30)
    
    # Initialize Lightning Runtime
    runtime = LightningRuntime()
    
    try:
        # Connect to storage provider
        await runtime.initialize()
        
        # Query all users (simplified - storage abstraction doesn't support complex queries yet)
        # This would need to be enhanced based on the actual storage provider capabilities
        try:
            user_doc = await runtime.storage.get_document(CONTAINER_NAME, "user")
            users = [user_doc.data] if user_doc else []
        except Exception:
            users = []
        
        if not users:
            log_warning("No users found in database")
            return
        
        print(f"\n{Colors.BOLD}Found {len(users)} users:{Colors.END}")
        print("-" * 80)
        
        for user in users:
            status_color = Colors.GREEN if user.get('status') == 'approved' else Colors.YELLOW if user.get('status') == 'waitlist' else Colors.RED
            role_indicator = " [ADMIN]" if user.get('role') == 'admin' else ""
            
            print(f"Username: {user.get('pk')}{role_indicator}")
            print(f"Email: {user.get('email', 'N/A')}")
            print(f"Status: {status_color}{user.get('status', 'unknown')}{Colors.END}")
            print(f"Role: {user.get('role', 'user')}")
            print(f"Created: {user.get('created_at', 'N/A')}")
            print("-" * 80)
            
    except Exception as e:
        log_error(f"Error listing users: {e}")

async def main():
    """Main menu."""
    
    while True:
        print(f"\n{Colors.BOLD}Vextir Chat - Database Admin Tool{Colors.END}")
        print("1. Create/Promote Admin User")
        print("2. List All Users")
        print("3. Exit")
        
        choice = input("\nSelect an option (1-3): ").strip()
        
        if choice == "1":
            await create_admin_user()
        elif choice == "2":
            await list_users()
        elif choice == "3":
            log("Goodbye!")
            break
        else:
            log_warning("Invalid choice. Please select 1-3.")

if __name__ == "__main__":
    asyncio.run(main())
