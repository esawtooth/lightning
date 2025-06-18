#!/usr/bin/env python3
"""
Lightning OS - Abstraction Layer Demonstration

This shows how the abstraction layer concept works, allowing the same code
to run both locally and in the cloud.
"""

import asyncio
import json
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional


# ============================================================================
# ABSTRACTION LAYER
# ============================================================================

class StorageProvider(ABC):
    """Abstract storage provider interface."""
    
    @abstractmethod
    async def store(self, key: str, data: Dict[str, Any]) -> None:
        """Store data with a key."""
        pass
    
    @abstractmethod
    async def retrieve(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve data by key."""
        pass
    
    @abstractmethod
    async def list_keys(self) -> List[str]:
        """List all keys."""
        pass


class EventBus(ABC):
    """Abstract event bus interface."""
    
    @abstractmethod
    async def publish(self, event_type: str, data: Dict[str, Any]) -> None:
        """Publish an event."""
        pass
    
    @abstractmethod
    async def subscribe(self, event_type: str, handler) -> str:
        """Subscribe to events. Returns subscription ID."""
        pass


# ============================================================================
# LOCAL IMPLEMENTATIONS
# ============================================================================

class LocalStorage(StorageProvider):
    """Local file-based storage implementation."""
    
    def __init__(self, path: str = "./local_data"):
        self.path = Path(path)
        self.path.mkdir(exist_ok=True)
        self.db_path = self.path / "storage.db"
        self._init_db()
    
    def _init_db(self):
        """Initialize SQLite database."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS storage (
                key TEXT PRIMARY KEY,
                data TEXT,
                created_at TEXT
            )
        """)
        conn.commit()
        conn.close()
    
    async def store(self, key: str, data: Dict[str, Any]) -> None:
        """Store data locally in SQLite."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT OR REPLACE INTO storage (key, data, created_at) VALUES (?, ?, ?)",
            (key, json.dumps(data), datetime.utcnow().isoformat())
        )
        conn.commit()
        conn.close()
        print(f"   [LOCAL] Stored: {key}")
    
    async def retrieve(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve data from SQLite."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT data FROM storage WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            print(f"   [LOCAL] Retrieved: {key}")
            return json.loads(row[0])
        return None
    
    async def list_keys(self) -> List[str]:
        """List all keys in storage."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT key FROM storage")
        keys = [row[0] for row in cursor.fetchall()]
        conn.close()
        return keys


class LocalEventBus(EventBus):
    """Local in-memory event bus implementation."""
    
    def __init__(self):
        self.handlers = {}
        self.events = []
    
    async def publish(self, event_type: str, data: Dict[str, Any]) -> None:
        """Publish event locally."""
        event = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.events.append(event)
        print(f"   [LOCAL] Published event: {event_type}")
        
        # Call handlers
        if event_type in self.handlers:
            for handler in self.handlers[event_type]:
                await handler(event)
    
    async def subscribe(self, event_type: str, handler) -> str:
        """Subscribe to events locally."""
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append(handler)
        sub_id = f"local-sub-{len(self.handlers)}"
        print(f"   [LOCAL] Subscribed to: {event_type}")
        return sub_id


# ============================================================================
# MOCK CLOUD IMPLEMENTATIONS
# ============================================================================

class AzureStorage(StorageProvider):
    """Mock Azure Cosmos DB implementation."""
    
    async def store(self, key: str, data: Dict[str, Any]) -> None:
        """Simulate storing in Cosmos DB."""
        print(f"   [AZURE] Storing to Cosmos DB: {key}")
        # In real implementation: cosmos_client.create_item(...)
    
    async def retrieve(self, key: str) -> Optional[Dict[str, Any]]:
        """Simulate retrieving from Cosmos DB."""
        print(f"   [AZURE] Retrieving from Cosmos DB: {key}")
        # In real implementation: cosmos_client.read_item(...)
        return {"mock": "data", "from": "cosmos"}
    
    async def list_keys(self) -> List[str]:
        """Simulate listing keys from Cosmos DB."""
        print("   [AZURE] Listing keys from Cosmos DB")
        return ["mock-key-1", "mock-key-2"]


class AzureEventBus(EventBus):
    """Mock Azure Service Bus implementation."""
    
    async def publish(self, event_type: str, data: Dict[str, Any]) -> None:
        """Simulate publishing to Service Bus."""
        print(f"   [AZURE] Publishing to Service Bus: {event_type}")
        # In real implementation: service_bus_client.send_message(...)
    
    async def subscribe(self, event_type: str, handler) -> str:
        """Simulate subscribing to Service Bus."""
        print(f"   [AZURE] Subscribing to Service Bus topic: {event_type}")
        # In real implementation: service_bus_client.get_subscription_receiver(...)
        return f"azure-sub-{event_type}"


# ============================================================================
# FACTORY PATTERN
# ============================================================================

class ProviderFactory:
    """Factory to create providers based on configuration."""
    
    @staticmethod
    def create_storage(mode: str) -> StorageProvider:
        if mode == "local":
            return LocalStorage()
        elif mode == "azure":
            return AzureStorage()
        else:
            raise ValueError(f"Unknown mode: {mode}")
    
    @staticmethod
    def create_event_bus(mode: str) -> EventBus:
        if mode == "local":
            return LocalEventBus()
        elif mode == "azure":
            return AzureEventBus()
        else:
            raise ValueError(f"Unknown mode: {mode}")


# ============================================================================
# APPLICATION CODE (Works with any provider)
# ============================================================================

class LightningApplication:
    """Main application that uses abstracted providers."""
    
    def __init__(self, mode: str = "local"):
        self.mode = mode
        self.storage = ProviderFactory.create_storage(mode)
        self.event_bus = ProviderFactory.create_event_bus(mode)
    
    async def process_user_action(self, user_id: str, action: str) -> None:
        """Process a user action - same code for local and cloud!"""
        print(f"\nProcessing user action: {action}")
        
        # Store action data
        action_data = {
            "user_id": user_id,
            "action": action,
            "timestamp": datetime.utcnow().isoformat()
        }
        await self.storage.store(f"action:{user_id}:{action}", action_data)
        
        # Publish event
        await self.event_bus.publish("user.action", action_data)
        
        print(f"✓ Action processed successfully\n")
    
    async def create_task(self, task_id: str, title: str, assignee: str) -> None:
        """Create a task - same code for local and cloud!"""
        print(f"\nCreating task: {title}")
        
        # Store task data
        task_data = {
            "task_id": task_id,
            "title": title,
            "assignee": assignee,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat()
        }
        await self.storage.store(f"task:{task_id}", task_data)
        
        # Publish event
        await self.event_bus.publish("task.created", task_data)
        
        print(f"✓ Task created successfully\n")
    
    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a task."""
        return await self.storage.retrieve(f"task:{task_id}")


# ============================================================================
# DEMONSTRATION
# ============================================================================

async def demonstrate_abstraction():
    """Demonstrate how the same code works in different modes."""
    
    print("╔════════════════════════════════════════════════════════╗")
    print("║     Lightning OS - Abstraction Layer Demonstration     ║")
    print("╚════════════════════════════════════════════════════════╝")
    print()
    
    # Demo 1: Local Mode
    print("=== RUNNING IN LOCAL MODE ===")
    local_app = LightningApplication(mode="local")
    
    # Set up event handler
    async def local_event_handler(event):
        print(f"   [HANDLER] Received: {event['type']}")
    
    await local_app.event_bus.subscribe("user.action", local_event_handler)
    await local_app.event_bus.subscribe("task.created", local_event_handler)
    
    # Process actions
    await local_app.process_user_action("user123", "login")
    await local_app.create_task("task001", "Implement feature X", "user123")
    
    # Retrieve data
    task = await local_app.get_task("task001")
    if task:
        print(f"Retrieved task: {task['title']} (status: {task['status']})")
    
    # Demo 2: Azure Mode (Mock)
    print("\n=== RUNNING IN AZURE MODE (MOCK) ===")
    azure_app = LightningApplication(mode="azure")
    
    # Same exact code!
    await azure_app.process_user_action("user456", "logout")
    await azure_app.create_task("task002", "Deploy to production", "user456")
    
    # Show stored data
    print("\n=== LOCAL STORAGE CONTENTS ===")
    if isinstance(local_app.storage, LocalStorage):
        keys = await local_app.storage.list_keys()
        print(f"Stored keys: {keys}")
    
    print("\n=== KEY BENEFITS ===")
    print("✓ Same application code for both local and cloud")
    print("✓ Easy development and testing without cloud resources")
    print("✓ Switch deployment target with configuration only")
    print("✓ No vendor lock-in - can switch cloud providers")
    print("✓ Cost savings during development")
    print()
    
    # Clean up
    if Path("./local_data").exists():
        import shutil
        shutil.rmtree("./local_data")


if __name__ == "__main__":
    asyncio.run(demonstrate_abstraction())