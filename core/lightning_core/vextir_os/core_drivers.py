"""
Core drivers that replace existing Azure Functions
These drivers maintain backward compatibility while leveraging the Vextir OS architecture
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from lightning_core.events.models import (
    CalendarEvent,
    ContextUpdateEvent,
    EmailEvent,
    Event,
    InstructionEvent,
    LLMChatEvent,
    WorkerTaskEvent,
)
from lightning_core.abstractions import Document
from lightning_core.runtime import LightningRuntime

from .drivers import (
    AgentDriver,
    Driver,
    DriverManifest,
    DriverType,
    IODriver,
    ResourceSpec,
    ToolDriver,
    driver,
)
from .registries import get_model_registry, get_tool_registry


@driver(
    "context_hub",
    DriverType.TOOL,
    capabilities=[
        "context.read",
        "context.write",
        "context.search",
        "context.initialize",
    ],
    name="Context Hub Driver",
    description="Direct integration with Rust-based context hub",
)
class ContextHubDriver(ToolDriver):
    """Replaces ContextHubManager Azure Function"""

    def __init__(
        self, manifest: DriverManifest, config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(manifest, config)
        self.hub_url = os.environ.get("CONTEXT_HUB_URL", "http://localhost:3000")
        self.cosmos_db = os.environ.get("COSMOS_DATABASE", "vextir")
        self.user_container = os.environ.get("USER_CONTAINER", "users")

        # Initialize Lightning Runtime for provider abstraction
        self.runtime = LightningRuntime()

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
                    "count": len(results) if results else 0,
                },
            )
            output_events.append(result_event)

        elif event.type == "context.initialize":
            root_folder_id = await self._initialize_user_context(event.user_id)

            if root_folder_id:
                # Update user record
                await self._update_user_record(
                    event.user_id,
                    {
                        "context_hub_root_id": root_folder_id,
                        "context_hub_initialized": True,
                        "context_hub_initialized_at": datetime.utcnow().isoformat(),
                    },
                )

                result_event = Event(
                    timestamp=datetime.utcnow(),
                    source="ContextHubDriver",
                    type="context.initialized",
                    user_id=event.user_id,
                    metadata={"root_folder_id": root_folder_id},
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
                metadata={"document": doc},
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
                    "operation": event.update_operation,
                },
            )
            output_events.append(result_event)

        return output_events

    async def _make_hub_request(
        self, method: str, endpoint: str, user_id: str, data: Optional[Dict] = None
    ) -> Optional[Dict]:
        """Make authenticated request to context-hub"""
        try:
            url = f"{self.hub_url.rstrip('/')}/{endpoint.lstrip('/')}"
            headers = {"X-User-Id": user_id, "Content-Type": "application/json"}

            # Use aiohttp for async requests in production
            # For now, using requests with asyncio.to_thread
            if method.upper() == "GET":
                response = await asyncio.to_thread(
                    requests.get, url, headers=headers, timeout=10
                )
            elif method.upper() == "POST":
                response = await asyncio.to_thread(
                    requests.post, url, headers=headers, json=data, timeout=10
                )
            elif method.upper() == "PUT":
                response = await asyncio.to_thread(
                    requests.put, url, headers=headers, json=data, timeout=10
                )
            elif method.upper() == "DELETE":
                response = await asyncio.to_thread(
                    requests.delete, url, headers=headers, timeout=10
                )
            else:
                return None

            if response.status_code < 300:
                return response.json() if response.content else {}
            else:
                logging.error(
                    f"Hub request failed: {response.status_code} - {response.text}"
                )
                return None
        except Exception as e:
            logging.error(f"Error making hub request: {e}")
            return None

    async def _search_user_context(
        self, user_id: str, query: str, limit: int = 10
    ) -> Optional[List[Dict]]:
        """Search user's context-hub content"""
        try:
            response = await self._make_hub_request(
                "GET", f"/search?q={query}&limit={limit}", user_id
            )
            return response.get("results", []) if response else []
        except Exception as e:
            logging.error(f"Error searching user context: {e}")
            return []

    async def _initialize_user_context(self, user_id: str) -> Optional[str]:
        """Initialize context-hub structure for a new user"""
        try:
            # Create root folder for user
            root_folder = await self._make_hub_request(
                "POST",
                "/docs",
                user_id,
                {
                    "name": f"{user_id}_workspace",
                    "content": "",
                    "parent_folder_id": None,
                    "doc_type": "Folder",
                },
            )

            if not root_folder:
                logging.error(f"Failed to create root folder for user {user_id}")
                return None

            root_folder_id = root_folder.get("id")

            # Create default subfolders
            default_folders = [
                {
                    "name": "Projects",
                    "description": "Project-related documents and notes",
                },
                {"name": "Documents", "description": "General documents and files"},
                {"name": "Notes", "description": "Personal notes and thoughts"},
                {
                    "name": "Research",
                    "description": "Research materials and references",
                },
            ]

            for folder_info in default_folders:
                folder = await self._make_hub_request(
                    "POST",
                    "/docs",
                    user_id,
                    {
                        "name": folder_info["name"],
                        "content": "",
                        "parent_folder_id": root_folder_id,
                        "doc_type": "Folder",
                    },
                )

                if folder:
                    # Create index guide for each folder
                    await self._make_hub_request(
                        "POST",
                        "/docs",
                        user_id,
                        {
                            "name": "Index Guide",
                            "content": f"# {folder_info['name']} Folder\n\n{folder_info['description']}\n\nThis folder is for organizing your {folder_info['name'].lower()}.",
                            "parent_folder_id": folder.get("id"),
                            "doc_type": "IndexGuide",
                        },
                    )

            # Create welcome document
            await self._make_hub_request(
                "POST",
                "/docs",
                user_id,
                {
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
                    "doc_type": "Text",
                },
            )

            logging.info(f"Successfully initialized context hub for user {user_id}")
            return root_folder_id

        except Exception as e:
            logging.error(f"Error initializing user context: {e}")
            return None

    async def _create_document(
        self, user_id: str, name: str, content: str, folder_id: Optional[str] = None
    ) -> Optional[Dict]:
        """Create a new document in user's context-hub"""
        if not folder_id:
            user = await self._get_user_record(user_id)
            if not user or not user.get("context_hub_root_id"):
                return None
            folder_id = user["context_hub_root_id"]

        return await self._make_hub_request(
            "POST",
            "/docs",
            user_id,
            {
                "name": name,
                "content": content,
                "parent_folder_id": folder_id,
                "doc_type": "Text",
            },
        )

    async def _synthesize_context(self, event: ContextUpdateEvent):
        """Synthesize context using the context hub"""
        # This would integrate with the context synthesis logic
        # For now, just create a document with the content
        await self._create_document(
            event.user_id,
            f"Synthesis_{event.context_key}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            event.content,
        )

    async def _get_user_record(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user record from storage provider"""
        try:
            # Use Lightning's document store abstraction
            doc = await self.runtime.storage.get_document(self.user_container, user_id)
            return doc.data if doc else None
        except Exception as e:
            logging.error(f"Error fetching user record: {e}")
            return None

    async def _update_user_record(self, user_id: str, updates: Dict[str, Any]) -> bool:
        """Update user record in storage provider"""
        try:
            # Get existing document
            doc = await self.runtime.storage.get_document(self.user_container, user_id)
            if not doc:
                # Create new document if doesn't exist
                doc = Document(
                    id=user_id,
                    partition_key=user_id,
                    data={"user_id": user_id}
                )
            
            # Update data
            doc.data.update(updates)
            
            # Use Lightning's document store abstraction
            if await self.runtime.storage.get_document(self.user_container, user_id):
                await self.runtime.storage.update_document(self.user_container, doc)
            else:
                await self.runtime.storage.create_document(self.user_container, doc)
            
            return True
        except Exception as e:
            logging.error(f"Error updating user record: {e}")
            return False


@driver(
    "chat_agent",
    DriverType.AGENT,
    capabilities=["llm.chat", "context.search", "context.read", "context.write", "context.list", "conversation.manage"],
    name="Chat Agent Driver",
    description="AI chat agent with full context hub access (search, read, write)",
)
class ChatAgentDriver(AgentDriver):
    """Replaces ChatResponder Azure Function"""

    def __init__(
        self, manifest: DriverManifest, config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(manifest, config)
        self.openai_api_key = os.environ.get("OPENAI_API_KEY")
        self.default_model = os.environ.get("OPENAI_MODEL", "gpt-4")
        self.context_hub_url = os.environ.get(
            "CONTEXT_HUB_URL", "http://localhost:3000"
        )

        # Initialize completions API
        self._completions_api = None

        self.system_prompt = """
You are a helpful AI assistant with full access to the user's personal context hub. You have the following capabilities:

1. **Search Documents**: Use search_user_context to find relevant documents based on keywords
2. **Read Documents**: Use read_document to get the full content of a specific document when you have its ID
3. **Write Documents**: Use write_document to create new documents or update existing ones
4. **List Documents**: Use list_documents to see what's in a specific folder

IMPORTANT: The context hub may contain "Index Guides" that provide specific instructions on how to use and organize content within folders. Always respect and follow these guides when working with documents. The guides are automatically included with search results and document listings.

Always cite sources when referencing information from their context hub. When creating or updating documents, confirm the action with the user first unless they explicitly ask you to do so.
"""

    def get_capabilities(self) -> List[str]:
        return ["llm.chat", "context.search", "context.read", "context.write", "context.list", "conversation.manage"]

    def get_resource_requirements(self) -> ResourceSpec:
        return ResourceSpec(memory_mb=1024, timeout_seconds=60)

    async def handle_event(self, event: Event) -> List[Event]:
        """Handle chat-related events"""
        output_events = []

        if isinstance(event, LLMChatEvent):
            # Process chat request
            messages = event.data.get("messages", []).copy()

            # Add system message about context search capability
            system_message = {"role": "system", "content": self.system_prompt}

            # Insert system message at the beginning if not already present
            if not messages or messages[0]["role"] != "system":
                messages.insert(0, system_message)
            else:
                # Update existing system message to include context search info
                messages[0]["content"] += "\n\n" + system_message["content"]

            try:
                # Get completions API
                if self._completions_api is None:
                    from ..llm import get_completions_api
                    self._completions_api = get_completions_api()

                # Get model from registry
                model_registry = get_model_registry()
                model = model_registry.get_model(self.default_model)
                if not model:
                    model = model_registry.get_cheapest_model("chat")
                
                model_id = model.id if model else self.default_model

                # First attempt with function calling
                response = await self._completions_api.create(
                    model=model_id,
                    messages=messages,
                    user_id=event.user_id,
                    tools=self._get_context_tools(),
                    tool_choice="auto",
                )

                message = response.choices[0].message
                usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                if response.usage:
                    usage = {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens,
                    }

                # Check if the model wants to call a function
                if message.tool_calls:
                    # Handle function calls
                    # Convert tool_calls to dict format if needed
                    tool_calls_dict = []
                    for tc in message.tool_calls:
                        if hasattr(tc, 'function'):
                            tool_calls_dict.append({
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments
                                }
                            })
                        else:
                            tool_calls_dict.append(tc)
                    
                    messages.append({
                        "role": message.role.value if hasattr(message.role, 'value') else message.role,
                        "content": message.content,
                        "tool_calls": tool_calls_dict
                    })

                    for tool_call in message.tool_calls:
                        # Handle both dict and object formats
                        if hasattr(tool_call, 'function'):
                            function_name = tool_call.function.name
                            arguments_str = tool_call.function.arguments
                            tool_call_id = tool_call.id
                        else:
                            function_name = tool_call["function"]["name"]
                            arguments_str = tool_call["function"]["arguments"]
                            tool_call_id = tool_call.get("id", "unknown")
                        
                        try:
                            arguments = json.loads(arguments_str)
                        except json.JSONDecodeError:
                            arguments = {}

                        function_result = await self._handle_function_call(
                            function_name, arguments, event.user_id
                        )

                        # Add function result to messages
                        messages.append(
                            {
                                "tool_call_id": tool_call_id,
                                "role": "tool",
                                "name": function_name,
                                "content": function_result,
                            }
                        )

                    # Get final response with function results
                    final_response = await self._completions_api.create(
                        model=model_id,
                        messages=messages,
                        user_id=event.user_id,
                    )

                    reply = final_response.choices[0].message.content
                    if final_response.usage:
                        usage = {
                            "prompt_tokens": usage["prompt_tokens"] + final_response.usage.prompt_tokens,
                            "completion_tokens": usage["completion_tokens"] + final_response.usage.completion_tokens,
                            "total_tokens": usage["total_tokens"] + final_response.usage.total_tokens,
                        }
                else:
                    reply = message.content

                logging.info("Assistant reply: %s", reply)

                # Create response event
                response_event = Event(
                    timestamp=datetime.utcnow(),
                    source="ChatAgentDriver",
                    type="llm.chat.response",
                    user_id=event.user_id,
                    data={"response": reply, "usage": usage},
                    metadata={
                        "request_id": event.metadata.get("request_id"),
                        "chat_request_id": event.id,
                        "session_id": event.metadata.get("session_id"),
                        "turn_number": event.metadata.get("turn_number"),
                        "response_timestamp": datetime.utcnow().isoformat()
                    }
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
                    data={"error": str(e)},
                    metadata={
                        "request_id": event.metadata.get("request_id"),
                        "chat_request_id": event.id
                    }
                )
                output_events.append(error_event)

        return output_events

    def _get_context_tools(self) -> List[Dict[str, Any]]:
        """Define all context hub tools for function calling"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_user_context",
                    "description": "Search the user's personal context hub for relevant documents, notes, and information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query to find relevant content in the user's documents",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of results to return (default: 5)",
                                "default": 5,
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_document",
                    "description": "Read the full content of a specific document from the user's context hub",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "document_id": {
                                "type": "string",
                                "description": "The UUID of the document to read",
                            },
                        },
                        "required": ["document_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "write_document",
                    "description": "Create or update a document in the user's context hub",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "The name/title of the document",
                            },
                            "content": {
                                "type": "string",
                                "description": "The content of the document",
                            },
                            "document_id": {
                                "type": "string",
                                "description": "Optional: UUID of existing document to update. If not provided, creates a new document",
                            },
                            "parent_folder_id": {
                                "type": "string",
                                "description": "Optional: UUID of parent folder. If not provided, creates in root",
                            },
                        },
                        "required": ["name", "content"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_documents",
                    "description": "List documents in a specific folder or root of the user's context hub",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "folder_id": {
                                "type": "string",
                                "description": "Optional: UUID of folder to list. If not provided, lists root folder",
                            },
                        },
                    },
                },
            },
        ]

    async def _handle_function_call(
        self, function_name: str, arguments: Dict[str, Any], user_id: str
    ) -> str:
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
            index_guides = set()  # Collect unique index guides
            
            for result in results:
                # Collect index guides
                guide = result.get('index_guide')
                if guide:
                    index_guides.add(guide)
                
                # Format the result
                content_snippet = result.get('snippet', result.get('content', '')[:500])
                formatted_results.append(
                    f"**{result.get('name', 'Untitled')}** (ID: {result.get('id', 'unknown')})\n{content_snippet}..."
                )

            if formatted_results:
                response = f"Found {len(formatted_results)} relevant documents:\n\n"
                
                # Include index guides if present
                if index_guides:
                    response += "**Folder Guidelines:**\n"
                    for guide in index_guides:
                        response += f"{guide}\n\n---\n\n"
                    response += "**Search Results:**\n\n"
                
                response += "\n\n".join(formatted_results)
                return response
            else:
                return "No relevant documents found in your context hub."

        elif function_name == "read_document":
            document_id = arguments.get("document_id", "")
            if not document_id:
                return "Error: No document ID provided"

            document = await self._read_document(user_id, document_id)
            if document:
                response = f"**{document.get('name', 'Untitled')}**\n\n"
                
                # Include index guide if present
                index_guide = document.get('index_guide')
                if index_guide:
                    response += f"**Folder Guidelines:**\n{index_guide}\n\n---\n\n"
                
                response += f"**Document Content:**\n{document.get('content', '')}"
                return response
            else:
                return f"Error: Document with ID {document_id} not found or access denied"

        elif function_name == "write_document":
            name = arguments.get("name", "")
            content = arguments.get("content", "")
            document_id = arguments.get("document_id")
            parent_folder_id = arguments.get("parent_folder_id")

            if not name or not content:
                return "Error: Document name and content are required"

            result = await self._write_document(
                user_id, name, content, document_id, parent_folder_id
            )
            if result:
                if document_id:
                    return f"Document '{name}' (ID: {result['id']}) has been updated successfully"
                else:
                    return f"New document '{name}' (ID: {result['id']}) has been created successfully"
            else:
                return "Error: Failed to write document"

        elif function_name == "list_documents":
            folder_id = arguments.get("folder_id")
            documents = await self._list_documents(user_id, folder_id)
            
            if documents:
                # Get index guide from the first document (they all have the same guide for a folder)
                index_guide = None
                if documents and isinstance(documents, list) and len(documents) > 0:
                    index_guide = documents[0].get('index_guide')
                
                response = ""
                
                # Include index guide if present
                if index_guide:
                    response += f"**Folder Guidelines:**\n{index_guide}\n\n---\n\n"
                
                formatted_list = []
                for doc in documents:
                    doc_type = doc.get('doc_type', 'Text')
                    icon = "📁" if doc_type == "Folder" else "📄"
                    formatted_list.append(
                        f"{icon} {doc.get('name', 'Untitled')} (ID: {doc.get('id', 'unknown')})"
                    )
                
                response += f"**Documents in folder:**\n" + "\n".join(formatted_list)
                return response
            else:
                return "No documents found in the specified folder"

        return f"Unknown function: {function_name}"

    async def _search_user_context(
        self, user_id: str, query: str, limit: int = 5
    ) -> Optional[List[Dict]]:
        """Search user's context-hub for relevant documents"""
        try:
            url = f"{self.context_hub_url.rstrip('/')}/search"
            headers = {"X-User-Id": user_id}
            params = {"q": query, "limit": limit}

            response = await asyncio.to_thread(
                requests.get, url, headers=headers, params=params, timeout=10
            )
            if response.status_code == 200:
                # Handle both old format (results key) and new format (direct array)
                data = response.json()
                if isinstance(data, list):
                    return data
                else:
                    return data.get("results", [])
            else:
                logging.error(
                    f"Context search failed for user {user_id}: {response.status_code}"
                )
                raise RuntimeError(f"Context Hub returned error {response.status_code}")
        except Exception as e:
            logging.error(f"Context Hub connection failed for user {user_id}: {e}")
            raise RuntimeError(f"Context Hub required but unavailable: {e}") from e

    async def _read_document(
        self, user_id: str, document_id: str
    ) -> Optional[Dict[str, Any]]:
        """Read a specific document from context hub"""
        try:
            url = f"{self.context_hub_url.rstrip('/')}/docs/{document_id}"
            headers = {"X-User-Id": user_id}

            response = await asyncio.to_thread(
                requests.get, url, headers=headers, timeout=10
            )
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return None
            else:
                logging.error(
                    f"Document read failed for user {user_id}, doc {document_id}: {response.status_code}"
                )
                return None
        except Exception as e:
            logging.error(f"Context Hub read failed for user {user_id}: {e}")
            return None

    async def _write_document(
        self,
        user_id: str,
        name: str,
        content: str,
        document_id: Optional[str] = None,
        parent_folder_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Create or update a document in context hub"""
        try:
            headers = {"X-User-Id": user_id, "Content-Type": "application/json"}
            
            if document_id:
                # Update existing document
                url = f"{self.context_hub_url.rstrip('/')}/docs/{document_id}"
                data = {"content": content}
                response = await asyncio.to_thread(
                    requests.put, url, headers=headers, json=data, timeout=10
                )
                if response.status_code == 204:
                    # Successfully updated, return the document info
                    return {"id": document_id, "name": name}
                else:
                    logging.error(
                        f"Document update failed for user {user_id}, doc {document_id}: {response.status_code}"
                    )
                    return None
            else:
                # Create new document
                url = f"{self.context_hub_url.rstrip('/')}/docs"
                data = {
                    "name": name,
                    "content": content,
                    "parent_folder_id": parent_folder_id,
                    "doc_type": "Text",
                }
                response = await asyncio.to_thread(
                    requests.post, url, headers=headers, json=data, timeout=10
                )
                if response.status_code == 200:
                    return response.json()
                else:
                    logging.error(
                        f"Document creation failed for user {user_id}: {response.status_code}"
                    )
                    return None
        except Exception as e:
            logging.error(f"Context Hub write failed for user {user_id}: {e}")
            return None

    async def _list_documents(
        self, user_id: str, folder_id: Optional[str] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """List documents in a folder"""
        try:
            # If folder_id is provided, use folders endpoint
            if folder_id:
                url = f"{self.context_hub_url.rstrip('/')}/folders/{folder_id}"
            else:
                # List documents endpoint returns all documents when no folder specified
                url = f"{self.context_hub_url.rstrip('/')}/docs"
                headers = {"X-User-Id": user_id}
                response = await asyncio.to_thread(
                    requests.get, url, headers=headers, timeout=10
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logging.error(
                        f"Root folder listing failed for user {user_id}: {response.status_code}"
                    )
                    return []
            
            headers = {"X-User-Id": user_id}
            response = await asyncio.to_thread(
                requests.get, url, headers=headers, timeout=10
            )
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return []
            else:
                logging.error(
                    f"Folder listing failed for user {user_id}, folder {folder_id}: {response.status_code}"
                )
                return []
        except Exception as e:
            logging.error(f"Context Hub listing failed for user {user_id}: {e}")
            return []
    
    async def _get_folder_guide(
        self, user_id: str, folder_id: str
    ) -> Optional[str]:
        """Get the Index Guide content for a folder"""
        try:
            # Use the dedicated endpoint
            url = f"{self.context_hub_url.rstrip('/')}/folders/{folder_id}/guide"
            headers = {"X-User-Id": user_id}
            
            response = await asyncio.to_thread(
                requests.get, url, headers=headers, timeout=10
            )
            
            if response.status_code == 200:
                guide_data = response.json()
                return guide_data.get('content', '')
            elif response.status_code == 404:
                logging.info(f"No guide found for folder {folder_id}")
                return None
            else:
                logging.error(f"Failed to get folder guide: {response.status_code}")
                return None
        except Exception as e:
            logging.error(f"Failed to get folder guide for {folder_id}: {e}")
            return None


@driver(
    "authentication",
    DriverType.TOOL,
    capabilities=["auth.verify", "auth.token", "user.manage"],
    name="Authentication Driver",
    description="User authentication and authorization",
)
class AuthenticationDriver(ToolDriver):
    """Replaces UserAuth Azure Function"""

    def __init__(
        self, manifest: DriverManifest, config: Optional[Dict[str, Any]] = None
    ):
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
                metadata={"valid": bool(user_id), "user_id": user_id},
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
