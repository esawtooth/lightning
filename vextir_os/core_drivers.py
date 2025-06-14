"""
Core drivers that replace existing Azure Functions
These drivers maintain backward compatibility while leveraging the Vextir OS architecture
"""

import asyncio
import json
import logging
import os
import requests
from datetime import datetime
from typing import Any, Dict, List, Optional

import openai
from azure.cosmos import CosmosClient

from events import Event, EmailEvent, CalendarEvent, ContextUpdateEvent, LLMChatEvent, InstructionEvent, WorkerTaskEvent
from .drivers import Driver, AgentDriver, ToolDriver, IODriver, DriverManifest, DriverType, ResourceSpec, driver
from .registries import get_model_registry, get_tool_registry


@driver("context_hub", DriverType.TOOL,
        capabilities=["context.read", "context.write", "context.search", "context.initialize"],
        name="Context Hub Driver",
        description="Direct integration with Rust-based context hub")
class ContextHubDriver(ToolDriver):
    """Replaces ContextHubManager Azure Function"""
    
    def __init__(self, manifest: DriverManifest, config: Optional[Dict[str, Any]] = None):
        super().__init__(manifest, config)
        self.hub_url = os.environ.get("CONTEXT_HUB_URL", "http://localhost:3000")
        self.cosmos_conn = os.environ.get("COSMOS_CONNECTION")
        self.cosmos_db = os.environ.get("COSMOS_DATABASE", "vextir")
        self.user_container = os.environ.get("USER_CONTAINER", "users")
        
        # Initialize Cosmos client
        self._client = CosmosClient.from_connection_string(self.cosmos_conn) if self.cosmos_conn else None
        self._db = self._client.create_database_if_not_exists(self.cosmos_db) if self._client else None
        self._container = self._db.create_container_if_not_exists(
            id=self.user_container, partition_key="/pk"
        ) if self._db else None
    
    def get_capabilities(self) -> List[str]:
        return ["context.read", "context.write", "context.search", "context.initialize"]
    
    def get_resource_requirements(self) -> ResourceSpec:
        return ResourceSpec(memory_mb=512, timeout_seconds=30)
    
    async def handle_event(self, event: Event) -> List[Event]:
        """Handle context-related events"""
        output_events = []
        
        if event.type == "context.search":
            query = event.metadata.get("query", "")
            limit = event.metadata.get("limit", 10)
            
            results = await self._search_user_context(event.user_id, query, limit)
            
            result_event = Event(
                timestamp=datetime.utcnow(),
                source="ContextHubDriver",
                type="context.search.result",
                user_id=event.user_id,
                metadata={
                    "query": query,
                    "results": results,
                    "count": len(results) if results else 0
                }
            )
            output_events.append(result_event)
        
        elif event.type == "context.initialize":
            root_folder_id = await self._initialize_user_context(event.user_id)
            
            if root_folder_id:
                # Update user record
                await self._update_user_record(event.user_id, {
                    "context_hub_root_id": root_folder_id,
                    "context_hub_initialized": True,
                    "context_hub_initialized_at": datetime.utcnow().isoformat()
                })
                
                result_event = Event(
                    timestamp=datetime.utcnow(),
                    source="ContextHubDriver",
                    type="context.initialized",
                    user_id=event.user_id,
                    metadata={"root_folder_id": root_folder_id}
                )
                output_events.append(result_event)
        
        elif event.type == "context.write":
            name = event.metadata.get("name", "Untitled")
            content = event.metadata.get("content", "")
            folder_id = event.metadata.get("folder_id")
            
            doc = await self._create_document(event.user_id, name, content, folder_id)
            
            result_event = Event(
                timestamp=datetime.utcnow(),
                source="ContextHubDriver",
                type="context.document.created",
                user_id=event.user_id,
                metadata={"document": doc}
            )
            output_events.append(result_event)
        
        elif isinstance(event, ContextUpdateEvent):
            # Handle context synthesis
            await self._synthesize_context(event)
            
            result_event = Event(
                timestamp=datetime.utcnow(),
                source="ContextHubDriver",
                type="context.synthesized",
                user_id=event.user_id,
                metadata={
                    "context_key": event.context_key,
                    "operation": event.update_operation
                }
            )
            output_events.append(result_event)
        
        return output_events
    
    async def _make_hub_request(self, method: str, endpoint: str, user_id: str, data: Optional[Dict] = None) -> Optional[Dict]:
        """Make authenticated request to context-hub"""
        try:
            url = f"{self.hub_url.rstrip('/')}/{endpoint.lstrip('/')}"
            headers = {
                "X-User-Id": user_id,
                "Content-Type": "application/json"
            }
            
            # Use aiohttp for async requests in production
            # For now, using requests with asyncio.to_thread
            if method.upper() == "GET":
                response = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
            elif method.upper() == "POST":
                response = await asyncio.to_thread(requests.post, url, headers=headers, json=data, timeout=10)
            elif method.upper() == "PUT":
                response = await asyncio.to_thread(requests.put, url, headers=headers, json=data, timeout=10)
            elif method.upper() == "DELETE":
                response = await asyncio.to_thread(requests.delete, url, headers=headers, timeout=10)
            else:
                return None
            
            if response.status_code < 300:
                return response.json() if response.content else {}
            else:
                logging.error(f"Hub request failed: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logging.error(f"Error making hub request: {e}")
            return None
    
    async def _search_user_context(self, user_id: str, query: str, limit: int = 10) -> Optional[List[Dict]]:
        """Search user's context-hub content"""
        try:
            response = await self._make_hub_request("GET", f"/search?q={query}&limit={limit}", user_id)
            return response.get("results", []) if response else []
        except Exception as e:
            logging.error(f"Error searching user context: {e}")
            return []
    
    async def _initialize_user_context(self, user_id: str) -> Optional[str]:
        """Initialize context-hub structure for a new user"""
        try:
            # Create root folder for user
            root_folder = await self._make_hub_request("POST", "/docs", user_id, {
                "name": f"{user_id}_workspace",
                "content": "",
                "parent_folder_id": None,
                "doc_type": "Folder"
            })
            
            if not root_folder:
                logging.error(f"Failed to create root folder for user {user_id}")
                return None
            
            root_folder_id = root_folder.get("id")
            
            # Create default subfolders
            default_folders = [
                {"name": "Projects", "description": "Project-related documents and notes"},
                {"name": "Documents", "description": "General documents and files"},
                {"name": "Notes", "description": "Personal notes and thoughts"},
                {"name": "Research", "description": "Research materials and references"}
            ]
            
            for folder_info in default_folders:
                folder = await self._make_hub_request("POST", "/docs", user_id, {
                    "name": folder_info["name"],
                    "content": "",
                    "parent_folder_id": root_folder_id,
                    "doc_type": "Folder"
                })
                
                if folder:
                    # Create index guide for each folder
                    await self._make_hub_request("POST", "/docs", user_id, {
                        "name": "Index Guide",
                        "content": f"# {folder_info['name']} Folder\n\n{folder_info['description']}\n\nThis folder is for organizing your {folder_info['name'].lower()}.",
                        "parent_folder_id": folder.get("id"),
                        "doc_type": "IndexGuide"
                    })
            
            # Create welcome document
            await self._make_hub_request("POST", "/docs", user_id, {
                "name": "Welcome to Vextir",
                "content": f"""# Welcome to Vextir, {user_id}!

This is your personal context hub where you can store and organize your documents, notes, and project files.

## Getting Started

Your workspace includes the following folders:
- **Projects**: For project-related documents and notes
- **Documents**: For general documents and files  
- **Notes**: For personal notes and thoughts
- **Research**: For research materials and references

## Features

- **Search**: Use the search functionality to quickly find content across all your documents
- **Chat Integration**: Your AI assistant can access and reference your documents during conversations
- **Organization**: Create additional folders and organize your content as needed

Start by uploading some documents or creating new notes to build your personal knowledge base!
""",
                "parent_folder_id": root_folder_id,
                "doc_type": "Text"
            })
            
            logging.info(f"Successfully initialized context hub for user {user_id}")
            return root_folder_id
            
        except Exception as e:
            logging.error(f"Error initializing user context: {e}")
            return None
    
    async def _create_document(self, user_id: str, name: str, content: str, folder_id: Optional[str] = None) -> Optional[Dict]:
        """Create a new document in user's context-hub"""
        if not folder_id:
            user = await self._get_user_record(user_id)
            if not user or not user.get("context_hub_root_id"):
                return None
            folder_id = user["context_hub_root_id"]
        
        return await self._make_hub_request("POST", "/docs", user_id, {
            "name": name,
            "content": content,
            "parent_folder_id": folder_id,
            "doc_type": "Text"
        })
    
    async def _synthesize_context(self, event: ContextUpdateEvent):
        """Synthesize context using the context hub"""
        # This would integrate with the context synthesis logic
        # For now, just create a document with the content
        await self._create_document(
            event.user_id,
            f"Synthesis_{event.context_key}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            event.content
        )
    
    async def _get_user_record(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user record from Cosmos DB"""
        if not self._container:
            return None
        
        try:
            items = list(await asyncio.to_thread(
                self._container.query_items,
                query="SELECT * FROM c WHERE c.user_id=@user_id",
                parameters=[{"name": "@user_id", "value": user_id}],
                enable_cross_partition_query=True,
            ))
            return items[0] if items else None
        except Exception as e:
            logging.error(f"Error fetching user record: {e}")
            return None
    
    async def _update_user_record(self, user_id: str, updates: Dict[str, Any]) -> bool:
        """Update user record in Cosmos DB"""
        if not self._container:
            return False
        
        try:
            user = await self._get_user_record(user_id)
            if not user:
                return False
            
            user.update(updates)
            await asyncio.to_thread(self._container.upsert_item, user)
            return True
        except Exception as e:
            logging.error(f"Error updating user record: {e}")
            return False


@driver("chat_agent", DriverType.AGENT,
        capabilities=["llm.chat", "context.search", "conversation.manage"],
        name="Chat Agent Driver",
        description="AI chat agent with context integration")
class ChatAgentDriver(AgentDriver):
    """Replaces ChatResponder Azure Function"""
    
    def __init__(self, manifest: DriverManifest, config: Optional[Dict[str, Any]] = None):
        super().__init__(manifest, config)
        self.openai_api_key = os.environ.get("OPENAI_API_KEY")
        self.default_model = os.environ.get("OPENAI_MODEL", "gpt-4")
        self.context_hub_url = os.environ.get("CONTEXT_HUB_URL", "http://localhost:3000")
        
        # Set OpenAI API key
        if self.openai_api_key:
            openai.api_key = self.openai_api_key
        
        self.system_prompt = """
You are a helpful AI assistant with access to the user's personal context hub. You can search their documents, notes, and files using the search_user_context function when relevant to their questions. Always cite sources when referencing information from their context hub.
"""
    
    def get_capabilities(self) -> List[str]:
        return ["llm.chat", "context.search", "conversation.manage"]
    
    def get_resource_requirements(self) -> ResourceSpec:
        return ResourceSpec(memory_mb=1024, timeout_seconds=60)
    
    async def handle_event(self, event: Event) -> List[Event]:
        """Handle chat-related events"""
        output_events = []
        
        if isinstance(event, LLMChatEvent):
            # Process chat request
            messages = event.messages.copy()
            
            # Add system message about context search capability
            system_message = {
                "role": "system",
                "content": self.system_prompt
            }
            
            # Insert system message at the beginning if not already present
            if not messages or messages[0]["role"] != "system":
                messages.insert(0, system_message)
            else:
                # Update existing system message to include context search info
                messages[0]["content"] += "\n\n" + system_message["content"]
            
            try:
                # Get model from registry
                model_registry = get_model_registry()
                model = model_registry.get_model(self.default_model)
                if not model:
                    model = model_registry.get_cheapest_model("chat")
                
                # First attempt with function calling
                response = await asyncio.to_thread(
                    openai.ChatCompletion.create,
                    messages=messages,
                    model=model.id if model else self.default_model,
                    tools=[self._get_context_search_tool()],
                    tool_choice="auto"
                )
                
                message = response["choices"][0]["message"]
                usage = response.get("usage", {})
                
                # Check if the model wants to call a function
                if message.get("tool_calls"):
                    # Handle function calls
                    messages.append(message)
                    
                    for tool_call in message["tool_calls"]:
                        function_name = tool_call["function"]["name"]
                        try:
                            arguments = json.loads(tool_call["function"]["arguments"])
                        except json.JSONDecodeError:
                            arguments = {}
                        
                        function_result = await self._handle_function_call(function_name, arguments, event.user_id)
                        
                        # Add function result to messages
                        messages.append({
                            "tool_call_id": tool_call["id"],
                            "role": "tool",
                            "name": function_name,
                            "content": function_result
                        })
                    
                    # Get final response with function results
                    final_response = await asyncio.to_thread(
                        openai.ChatCompletion.create,
                        messages=messages,
                        model=model.id if model else self.default_model,
                    )
                    
                    reply = final_response["choices"][0]["message"]["content"]
                    usage.update(final_response.get("usage", {}))
                else:
                    reply = message["content"]
                
                logging.info("Assistant reply: %s", reply)
                
                # Create response event
                response_event = Event(
                    timestamp=datetime.utcnow(),
                    source="ChatAgentDriver",
                    type="llm.chat.response",
                    user_id=event.user_id,
                    metadata={"reply": reply, "usage": usage},
                    history=event.history + [event.to_dict()],
                )
                output_events.append(response_event)
                
            except Exception as e:
                logging.error(f"ChatCompletion failed: {e}")
                
                # Create error event
                error_event = Event(
                    timestamp=datetime.utcnow(),
                    source="ChatAgentDriver",
                    type="llm.chat.error",
                    user_id=event.user_id,
                    metadata={"error": str(e)},
                    history=event.history + [event.to_dict()],
                )
                output_events.append(error_event)
        
        return output_events
    
    def _get_context_search_tool(self) -> Dict[str, Any]:
        """Define the context search tool for function calling"""
        return {
            "type": "function",
            "function": {
                "name": "search_user_context",
                "description": "Search the user's personal context hub for relevant documents, notes, and information",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query to find relevant content in the user's documents"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results to return (default: 5)",
                            "default": 5
                        }
                    },
                    "required": ["query"]
                }
            }
        }
    
    async def _handle_function_call(self, function_name: str, arguments: Dict[str, Any], user_id: str) -> str:
        """Handle function calls from the LLM"""
        if function_name == "search_user_context":
            query = arguments.get("query", "")
            limit = arguments.get("limit", 5)
            
            if not query:
                return "Error: No search query provided"
            
            results = await self._search_user_context(user_id, query, limit)
            if not results:
                return "No relevant documents found in your context hub."
            
            # Format results for the LLM
            formatted_results = []
            for result in results:
                formatted_results.append(f"**{result.get('name', 'Untitled')}**\n{result.get('content', '')[:500]}...")
            
            if formatted_results:
                return f"Found {len(formatted_results)} relevant documents:\n\n" + "\n\n".join(formatted_results)
            else:
                return "No relevant documents found in your context hub."
        
        return f"Unknown function: {function_name}"
    
    async def _search_user_context(self, user_id: str, query: str, limit: int = 5) -> Optional[List[Dict]]:
        """Search user's context-hub for relevant documents"""
        try:
            url = f"{self.context_hub_url.rstrip('/')}/search"
            headers = {"X-User-Id": user_id}
            params = {"q": query, "limit": limit}
            
            response = await asyncio.to_thread(requests.get, url, headers=headers, params=params, timeout=10)
            if response.status_code == 200:
                return response.json().get("results", [])
            else:
                logging.warning(f"Context search failed for user {user_id}: {response.status_code}")
                return []
        except Exception as e:
            logging.error(f"Error searching context for user {user_id}: {e}")
            return []


@driver("authentication", DriverType.TOOL,
        capabilities=["auth.verify", "auth.token", "user.manage"],
        name="Authentication Driver",
        description="User authentication and authorization")
class AuthenticationDriver(ToolDriver):
    """Replaces UserAuth Azure Function"""
    
    def __init__(self, manifest: DriverManifest, config: Optional[Dict[str, Any]] = None):
        super().__init__(manifest, config)
        # Initialize authentication components
        # This would integrate with Azure Entra ID or other auth providers
    
    def get_capabilities(self) -> List[str]:
        return ["auth.verify", "auth.token", "user.manage"]
    
    def get_resource_requirements(self) -> ResourceSpec:
        return ResourceSpec(memory_mb=256, timeout_seconds=15)
    
    async def handle_event(self, event: Event) -> List[Event]:
        """Handle authentication events"""
        output_events = []
        
        if event.type == "auth.verify":
            token = event.metadata.get("token")
            user_id = await self._verify_token(token)
            
            result_event = Event(
                timestamp=datetime.utcnow(),
                source="AuthenticationDriver",
                type="auth.verified" if user_id else "auth.failed",
                user_id=user_id or "unknown",
                metadata={
                    "valid": bool(user_id),
                    "user_id": user_id
                }
            )
            output_events.append(result_event)
        
        return output_events
    
    async def _verify_token(self, token: str) -> Optional[str]:
        """Verify JWT token and return user ID"""
        # This would integrate with the existing JWT verification logic
        # from common.jwt_utils import verify_token
        try:
            from common.jwt_utils import verify_token
            return verify_token(token)
        except Exception as e:
            logging.warning(f"Token verification failed: {e}")
            return None
