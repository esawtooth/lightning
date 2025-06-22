"""
Chat persistence module for storing chat conversations in the context hub.

This module handles saving and retrieving chat threads, including messages,
tool calls, and conversation metadata.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ChatMessage(BaseModel):
    """Represents a single message in a chat conversation."""
    role: str = Field(..., description="Message sender role (user/assistant/system)")
    content: str = Field(..., description="Message content")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ChatToolCall(BaseModel):
    """Represents a tool call made during the conversation."""
    tool_name: str
    input_data: Dict[str, Any]
    output_data: Optional[Dict[str, Any]] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    summary: Optional[str] = None


class ChatThread(BaseModel):
    """Represents a complete chat conversation thread."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: Optional[str] = None
    messages: List[ChatMessage] = Field(default_factory=list)
    tool_calls: List[ChatToolCall] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    user_id: str
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    def generate_title(self) -> str:
        """Generate a title from the first user message."""
        for msg in self.messages:
            if msg.role == "user" and msg.content:
                # Take first 50 chars of first user message
                title = msg.content[:50]
                if len(msg.content) > 50:
                    title += "..."
                return title
        return f"Chat from {self.created_at}"


class ChatPersistence:
    """Handles chat persistence operations with the context hub."""
    
    def __init__(self, context_hub_url: str = "http://localhost:3000"):
        self.context_hub_url = context_hub_url
        self.chat_folder_id = None  # Will be created/retrieved on first use
        
    async def _ensure_chat_folder(self, user_id: str) -> str:
        """Ensure the Chat History folder exists for the user."""
        if self.chat_folder_id:
            return self.chat_folder_id
            
        async with httpx.AsyncClient() as client:
            # Search for existing Chat History folder
            response = await client.get(
                f"{self.context_hub_url}/docs",
                params={"owner": user_id}
            )
            
            if response.status_code == 200:
                docs = response.json()
                # Handle if docs is a list directly
                if isinstance(docs, list):
                    for doc in docs:
                        if doc.get("name") == "Chat History" and doc.get("doc_type") == "Folder":
                            self.chat_folder_id = doc["id"]
                            return self.chat_folder_id
                else:
                    # Handle if docs is a dict with a 'docs' key
                    for doc in docs.get("docs", []):
                        if doc.get("name") == "Chat History" and doc.get("doc_type") == "Folder":
                            self.chat_folder_id = doc["id"]
                            return self.chat_folder_id
            
            # Create Chat History folder if it doesn't exist
            response = await client.post(
                f"{self.context_hub_url}/docs",
                json={
                    "name": "Chat History",
                    "content": "",  # Empty folder content
                    "doc_type": "Folder"
                },
                headers={"X-User-ID": user_id}
            )
            
            if response.status_code in (200, 201):
                data = response.json()
                self.chat_folder_id = data["id"]
                return self.chat_folder_id
            else:
                logger.error(f"Failed to create Chat History folder: {response.text}")
                raise Exception("Failed to create Chat History folder")
    
    async def save_chat(self, thread: ChatThread) -> str:
        """Save a chat thread to the context hub."""
        folder_id = await self._ensure_chat_folder(thread.user_id)
        
        # Generate title if not set
        if not thread.title:
            thread.title = thread.generate_title()
        
        # Create document name with timestamp
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        doc_name = f"chat_{timestamp}_{thread.id[:8]}.json"
        
        async with httpx.AsyncClient() as client:
            # Check if this chat already exists (for updates)
            existing_doc_id = None
            if thread.metadata.get("doc_id"):
                existing_doc_id = thread.metadata["doc_id"]
            
            # Prepare chat data
            chat_data = {
                "thread": thread.dict(),
                "summary": self._generate_summary(thread)
            }
            
            if existing_doc_id:
                # Update existing document
                response = await client.put(
                    f"{self.context_hub_url}/docs/{existing_doc_id}",
                    json={"content": json.dumps(chat_data, indent=2)},
                    headers={"X-User-ID": thread.user_id}
                )
            else:
                # Create new document
                response = await client.post(
                    f"{self.context_hub_url}/docs",
                    json={
                        "name": doc_name,
                        "content": json.dumps(chat_data, indent=2),
                        "parent_folder_id": folder_id,
                        "doc_type": "Text"
                    },
                    headers={"X-User-ID": thread.user_id}
                )
            
            if response.status_code in (200, 201):
                data = response.json()
                doc_id = data["id"]
                thread.metadata["doc_id"] = doc_id
                return doc_id
            else:
                logger.error(f"Failed to save chat: {response.text}")
                raise Exception("Failed to save chat")
    
    async def load_chat(self, chat_id: str, user_id: str) -> Optional[ChatThread]:
        """Load a chat thread from the context hub."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.context_hub_url}/docs/{chat_id}",
                headers={"X-User-ID": user_id}
            )
            
            if response.status_code == 200:
                doc = response.json()
                content = json.loads(doc["content"])
                thread_data = content.get("thread", content)  # Handle both formats
                thread = ChatThread(**thread_data)
                thread.metadata["doc_id"] = chat_id
                return thread
            else:
                logger.error(f"Failed to load chat {chat_id}: {response.text}")
                return None
    
    async def list_chats(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """List recent chat threads for a user."""
        folder_id = await self._ensure_chat_folder(user_id)
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.context_hub_url}/folders/{folder_id}",
                headers={"X-User-ID": user_id}
            )
            
            if response.status_code == 200:
                data = response.json()
                # Handle if data is a list directly (folder contents)
                if isinstance(data, list):
                    documents = data
                else:
                    documents = data.get("documents", [])
                
                # Filter and sort chat documents
                chats = []
                for doc in documents:
                    # Check if it's a chat document by name pattern or doc_type
                    if (doc.get("doc_type") == "Text" and doc.get("name", "").startswith("chat_")) or doc.get("doc_type") == "chat":
                        # Try to load the document to get the actual title
                        try:
                            doc_response = await client.get(
                                f"{self.context_hub_url}/docs/{doc['id']}",
                                headers={"X-User-ID": user_id}
                            )
                            if doc_response.status_code == 200:
                                doc_data = doc_response.json()
                                content = json.loads(doc_data.get("content", "{}"))
                                thread_data = content.get("thread", {})
                                title = thread_data.get("title") or thread_data.get("messages", [{}])[0].get("content", "Untitled Chat")[:50]
                                if len(title) > 50:
                                    title += "..."
                            else:
                                title = doc.get("name", "Untitled Chat")
                        except Exception as e:
                            logger.warning(f"Failed to load chat title for {doc['id']}: {e}")
                            title = doc.get("name", "Untitled Chat")
                        
                        chats.append({
                            "id": doc["id"],
                            "title": title,
                            "created_at": doc.get("created_at"),
                            "updated_at": doc.get("updated_at")
                        })
                
                # Sort by updated_at descending
                chats.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
                return chats[:limit]
            else:
                logger.error(f"Failed to list chats: {response.text}")
                return []
    
    async def get_latest_chat(self, user_id: str) -> Optional[ChatThread]:
        """Get the most recently updated chat thread."""
        chats = await self.list_chats(user_id, limit=1)
        if chats:
            return await self.load_chat(chats[0]["id"], user_id)
        return None
    
    def _generate_summary(self, thread: ChatThread) -> str:
        """Generate a summary of the chat including tool calls."""
        summary_parts = []
        
        # Count messages by role
        user_messages = sum(1 for msg in thread.messages if msg.role == "user")
        assistant_messages = sum(1 for msg in thread.messages if msg.role == "assistant")
        
        summary_parts.append(f"Conversation with {user_messages} user messages and {assistant_messages} assistant responses.")
        
        # Summarize tool calls
        if thread.tool_calls:
            tool_summary = {}
            for tool_call in thread.tool_calls:
                tool_name = tool_call.tool_name
                if tool_name not in tool_summary:
                    tool_summary[tool_name] = 0
                tool_summary[tool_name] += 1
            
            tools_used = ", ".join([f"{name} ({count}x)" for name, count in tool_summary.items()])
            summary_parts.append(f"Tools used: {tools_used}")
        
        # Add first user message as context
        if thread.messages:
            first_user_msg = next((msg for msg in thread.messages if msg.role == "user"), None)
            if first_user_msg:
                summary_parts.append(f"Started with: \"{first_user_msg.content[:100]}...\"")
        
        return " ".join(summary_parts)