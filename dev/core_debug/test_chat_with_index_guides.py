#!/usr/bin/env python3
"""Test ChatAgentDriver with index guide support"""

import asyncio
import os
import sys
from datetime import datetime
import logging

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from lightning_core.vextir_os.core_drivers import ChatAgentDriver, ContextHubDriver
from lightning_core.vextir_os.drivers import DriverManifest, DriverType
from lightning_core.events.models import LLMChatEvent, Event

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

async def setup_test_context(user_id: str):
    """Set up test context with index guides"""
    # Initialize Context Hub Driver
    context_manifest = DriverManifest(
        id="context_hub",
        name="Context Hub Driver",
        driver_type=DriverType.TOOL,
        capabilities=["context.read", "context.write", "context.search", "context.initialize"],
        resource_requirements=None
    )
    context_driver = ContextHubDriver(context_manifest)
    
    # Initialize user context
    print("Initializing user context...")
    init_event = Event(
        timestamp=datetime.utcnow(),
        source="test",
        type="context.initialize",
        user_id=user_id,
        metadata={}
    )
    
    results = await context_driver.handle_event(init_event)
    if results and results[0].type == "context.initialized":
        print(f"✓ Context initialized with root folder: {results[0].metadata['root_folder_id']}")
    
    # Add a custom document to the Projects folder
    print("\nAdding custom project document...")
    write_event = Event(
        timestamp=datetime.utcnow(),
        source="test",
        type="context.write",
        user_id=user_id,
        metadata={
            "name": "AI Assistant Development",
            "content": """# AI Assistant Development Project

## Overview
This project focuses on developing an advanced AI assistant with context awareness.

## Key Features
- Natural language understanding
- Context hub integration
- Multi-modal capabilities
- Tool usage and function calling

## Architecture
The system uses an event-driven architecture with drivers for different capabilities.

## Current Status
- Phase 1: Basic chat functionality ✓
- Phase 2: Context integration (in progress)
- Phase 3: Advanced features (planned)
""",
            "folder_id": None  # Will go to root, but ideally should go to Projects folder
        }
    )
    
    results = await context_driver.handle_event(write_event)
    if results and results[0].type == "context.document.created":
        print(f"✓ Document created: {results[0].metadata['document']['name']}")

async def test_chat_with_index_guides():
    """Test the ChatAgentDriver with index guide support"""
    user_id = f"test_user_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # Set up test context
    await setup_test_context(user_id)
    
    # Initialize Chat Agent Driver
    chat_manifest = DriverManifest(
        id="chat_agent",
        name="Chat Agent Driver",
        driver_type=DriverType.AGENT,
        capabilities=["llm.chat", "context.search", "context.read", "context.write", "context.list"],
        resource_requirements=None
    )
    chat_driver = ChatAgentDriver(chat_manifest)
    
    print("\n" + "="*50)
    print("Testing Chat Agent with Index Guides")
    print("="*50)
    
    # Test 1: Search for documents
    print("\n1. Testing document search...")
    chat_event = LLMChatEvent(
        timestamp=datetime.utcnow(),
        source="test",
        user_id=user_id,
        data={
            "messages": [
                {
                    "role": "user",
                    "content": "Can you search my context hub for information about AI development?"
                }
            ]
        },
        metadata={"request_id": "test_1", "session_id": "test_session"}
    )
    
    results = await chat_driver.handle_event(chat_event)
    if results:
        response = results[0].data.get("response", "")
        print(f"Response: {response[:500]}...")
        print(f"✓ Search test completed")
    
    # Test 2: List documents in a folder
    print("\n2. Testing folder listing...")
    chat_event = LLMChatEvent(
        timestamp=datetime.utcnow(),
        source="test",
        user_id=user_id,
        data={
            "messages": [
                {
                    "role": "user",
                    "content": "Can you list all the documents in my root folder?"
                }
            ]
        },
        metadata={"request_id": "test_2", "session_id": "test_session"}
    )
    
    results = await chat_driver.handle_event(chat_event)
    if results:
        response = results[0].data.get("response", "")
        print(f"Response: {response[:500]}...")
        print(f"✓ Listing test completed")
    
    # Test 3: Create a document respecting index guides
    print("\n3. Testing document creation with index guide awareness...")
    chat_event = LLMChatEvent(
        timestamp=datetime.utcnow(),
        source="test",
        user_id=user_id,
        data={
            "messages": [
                {
                    "role": "user",
                    "content": "Create a new document called 'Meeting Notes' with the content 'Discussion about project timeline and deliverables.' Please follow any folder guidelines."
                }
            ]
        },
        metadata={"request_id": "test_3", "session_id": "test_session"}
    )
    
    results = await chat_driver.handle_event(chat_event)
    if results:
        response = results[0].data.get("response", "")
        print(f"Response: {response[:500]}...")
        print(f"✓ Document creation test completed")
    
    # Test 4: Read a specific document
    print("\n4. Testing document reading with index guide context...")
    chat_event = LLMChatEvent(
        timestamp=datetime.utcnow(),
        source="test",
        user_id=user_id,
        data={
            "messages": [
                {
                    "role": "user",
                    "content": "Can you read the 'Welcome to Vextir' document and tell me what it says?"
                }
            ]
        },
        metadata={"request_id": "test_4", "session_id": "test_session"}
    )
    
    results = await chat_driver.handle_event(chat_event)
    if results:
        response = results[0].data.get("response", "")
        print(f"Response: {response[:500]}...")
        print(f"✓ Document reading test completed")
    
    print("\n" + "="*50)
    print("✅ All tests completed successfully!")
    print("="*50)

async def main():
    """Main test runner"""
    # Check for required environment variables
    if not os.environ.get("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY environment variable not set")
        sys.exit(1)
    
    if not os.environ.get("CONTEXT_HUB_URL"):
        print("⚠️  Warning: CONTEXT_HUB_URL not set, using default http://localhost:3000")
        os.environ["CONTEXT_HUB_URL"] = "http://localhost:3000"
    
    try:
        await test_chat_with_index_guides()
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())