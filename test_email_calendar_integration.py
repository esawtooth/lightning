#!/usr/bin/env python3
"""
Test script for the Email/Calendar Integration System

This script demonstrates how to:
1. Create instructions for email and calendar processing
2. Simulate incoming events
3. Test the instruction matching and context synthesis

Usage:
    python test_email_calendar_integration.py
"""

import json
import requests
from datetime import datetime, timedelta
from typing import Dict, Any

# Configuration - update these with your actual endpoints
BASE_URL = "https://your-function-app.azurewebsites.net/api"
AUTH_TOKEN = "your-jwt-token-here"

HEADERS = {
    "Authorization": f"Bearer {AUTH_TOKEN}",
    "Content-Type": "application/json"
}


def create_instruction(instruction_data: Dict[str, Any]) -> str:
    """Create a new instruction and return its ID."""
    response = requests.post(
        f"{BASE_URL}/instructions",
        headers=HEADERS,
        json=instruction_data
    )
    
    if response.status_code == 201:
        result = response.json()
        print(f"✅ Created instruction: {instruction_data['name']} (ID: {result['id']})")
        return result["id"]
    else:
        print(f"❌ Failed to create instruction: {response.status_code} - {response.text}")
        return None


def simulate_email_event(email_data: Dict[str, Any]) -> bool:
    """Simulate an incoming email event."""
    event_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "source": "TestScript",
        "type": "email.received",
        "metadata": {
            "operation": "received",
            "provider": "gmail",
            "email_data": email_data
        }
    }
    
    response = requests.post(
        f"{BASE_URL}/events",
        headers=HEADERS,
        json=event_data
    )
    
    if response.status_code == 202:
        print(f"✅ Simulated email event: {email_data['subject']}")
        return True
    else:
        print(f"❌ Failed to simulate email event: {response.status_code} - {response.text}")
        return False


def simulate_calendar_event(calendar_data: Dict[str, Any]) -> bool:
    """Simulate an incoming calendar event."""
    event_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "source": "TestScript",
        "type": "calendar.received",
        "metadata": {
            "operation": "received",
            "provider": "outlook",
            "calendar_data": calendar_data
        }
    }
    
    response = requests.post(
        f"{BASE_URL}/events",
        headers=HEADERS,
        json=event_data
    )
    
    if response.status_code == 202:
        print(f"✅ Simulated calendar event: {calendar_data['title']}")
        return True
    else:
        print(f"❌ Failed to simulate calendar event: {response.status_code} - {response.text}")
        return False


def list_instructions() -> list:
    """List all user instructions."""
    response = requests.get(
        f"{BASE_URL}/instructions",
        headers=HEADERS
    )
    
    if response.status_code == 200:
        instructions = response.json()
        print(f"📋 Found {len(instructions)} instructions:")
        for inst in instructions:
            print(f"   - {inst['name']} (Enabled: {inst['enabled']}, Executions: {inst['execution_count']})")
        return instructions
    else:
        print(f"❌ Failed to list instructions: {response.status_code} - {response.text}")
        return []


def check_context_status() -> Dict[str, Any]:
    """Check the context hub status."""
    response = requests.get(
        f"{BASE_URL}/context/status",
        headers=HEADERS
    )
    
    if response.status_code == 200:
        status = response.json()
        print(f"🏠 Context Hub Status:")
        print(f"   - Initialized: {status.get('initialized', False)}")
        print(f"   - Root Folder: {status.get('root_folder_id', 'None')}")
        return status
    else:
        print(f"❌ Failed to check context status: {response.status_code} - {response.text}")
        return {}


def main():
    """Run the integration test."""
    print("🚀 Email/Calendar Integration Test")
    print("=" * 50)
    
    # 1. Check context status
    print("\n1. Checking Context Hub Status...")
    check_context_status()
    
    # 2. List existing instructions
    print("\n2. Listing Existing Instructions...")
    list_instructions()
    
    # 3. Create email summary instruction
    print("\n3. Creating Email Summary Instruction...")
    email_instruction = {
        "name": "Project Email Tracker",
        "description": "Track emails related to project work",
        "trigger": {
            "event_type": "email.received",
            "providers": ["gmail", "outlook"],
            "conditions": {
                "content_filters": {
                    "subject_contains": ["project", "meeting", "update"]
                }
            }
        },
        "action": {
            "type": "update_context_summary",
            "config": {
                "context_key": "project_emails",
                "synthesis_prompt": "Update the project email summary with key information: action items, deadlines, and important decisions."
            }
        },
        "enabled": True
    }
    
    email_instruction_id = create_instruction(email_instruction)
    
    # 4. Create calendar instruction
    print("\n4. Creating Calendar Instruction...")
    calendar_instruction = {
        "name": "Meeting Context Builder",
        "description": "Build context from calendar meetings",
        "trigger": {
            "event_type": "calendar.received",
            "providers": ["outlook", "gmail"]
        },
        "action": {
            "type": "update_context_summary",
            "config": {
                "context_key": "meeting_schedule",
                "synthesis_prompt": "Maintain an overview of upcoming meetings, attendees, and important agenda items."
            }
        },
        "enabled": True
    }
    
    calendar_instruction_id = create_instruction(calendar_instruction)
    
    # 5. Create notification instruction
    print("\n5. Creating Notification Instruction...")
    notification_instruction = {
        "name": "Urgent Email Notifier",
        "description": "Send notifications for urgent emails",
        "trigger": {
            "event_type": "email.received",
            "conditions": {
                "content_filters": {
                    "subject_contains": ["urgent", "asap", "emergency"]
                }
            }
        },
        "action": {
            "type": "send_email",
            "config": {
                "email": {
                    "to": "admin@example.com",
                    "subject": "Urgent Email Alert",
                    "body_template": "Urgent email received from {from}: {subject}"
                }
            }
        },
        "enabled": True
    }
    
    notification_instruction_id = create_instruction(notification_instruction)
    
    # 6. Simulate some events
    print("\n6. Simulating Email Events...")
    
    # Project-related email (should match email instruction)
    simulate_email_event({
        "from": "alice@company.com",
        "to": ["user@example.com"],
        "subject": "Project Alpha Update - Q2 Milestone",
        "body": "Hi team, we've reached our Q2 milestone for Project Alpha. Next steps: 1) Review budget, 2) Plan Q3 features, 3) Schedule client demo.",
        "timestamp": datetime.utcnow().isoformat()
    })
    
    # Urgent email (should match notification instruction)
    simulate_email_event({
        "from": "boss@company.com",
        "to": ["user@example.com"],
        "subject": "URGENT: Server Issue Needs Immediate Attention",
        "body": "We have a critical server issue that needs immediate attention. Please check the monitoring dashboard and respond ASAP.",
        "timestamp": datetime.utcnow().isoformat()
    })
    
    # Regular email (should not match any instructions)
    simulate_email_event({
        "from": "newsletter@example.com",
        "to": ["user@example.com"],
        "subject": "Weekly Newsletter - Tech Updates",
        "body": "Here are this week's tech updates and industry news...",
        "timestamp": datetime.utcnow().isoformat()
    })
    
    print("\n7. Simulating Calendar Events...")
    
    # Team meeting (should match calendar instruction)
    tomorrow = datetime.utcnow() + timedelta(days=1)
    simulate_calendar_event({
        "title": "Project Alpha Review Meeting",
        "description": "Review Q2 progress and plan Q3 roadmap",
        "start_time": tomorrow.replace(hour=14, minute=0).isoformat(),
        "end_time": tomorrow.replace(hour=15, minute=0).isoformat(),
        "attendees": ["alice@company.com", "bob@company.com", "user@example.com"],
        "location": "Conference Room A"
    })
    
    # Client demo (should match calendar instruction)
    next_week = datetime.utcnow() + timedelta(days=7)
    simulate_calendar_event({
        "title": "Client Demo - Project Alpha",
        "description": "Demonstrate Q2 features to client stakeholders",
        "start_time": next_week.replace(hour=10, minute=0).isoformat(),
        "end_time": next_week.replace(hour=11, minute=30).isoformat(),
        "attendees": ["client@customer.com", "sales@company.com", "user@example.com"],
        "location": "Virtual Meeting"
    })
    
    # 8. Wait and check results
    print("\n8. Test Complete!")
    print("\nNext Steps:")
    print("- Check Azure Function logs to see event processing")
    print("- Monitor Service Bus for message flow")
    print("- Check Context Hub for updated summaries")
    print("- Verify instruction execution counts")
    
    print(f"\nCreated Instructions:")
    if email_instruction_id:
        print(f"- Email Tracker: {email_instruction_id}")
    if calendar_instruction_id:
        print(f"- Calendar Builder: {calendar_instruction_id}")
    if notification_instruction_id:
        print(f"- Urgent Notifier: {notification_instruction_id}")
    
    print("\n✅ Integration test completed successfully!")


if __name__ == "__main__":
    main()
