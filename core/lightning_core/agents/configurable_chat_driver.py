"""
Configurable Chat Agent Driver

A Chat Agent Driver that uses the Lightning Agent Configuration Platform
for fully customizable behavior.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from lightning_core.events.models import Event, LLMChatEvent
from lightning_core.runtime import LightningRuntime
from lightning_core.vextir_os.drivers import (
    AgentDriver,
    DriverManifest,
    DriverType,
    ResourceSpec,
    driver,
)
from lightning_core.vextir_os.registries import get_model_registry

from .config_manager import AgentConfigManager
from .schemas import ChatAgentConfig

logger = logging.getLogger(__name__)


@driver(
    "configurable_chat_agent",
    DriverType.AGENT,
    capabilities=["llm.chat", "context.search", "context.read", "context.write", "context.list", "conversation.manage"],
    name="Configurable Chat Agent Driver",
    description="AI chat agent with customizable configuration for prompts, tools, and behavior",
)
class ConfigurableChatAgentDriver(AgentDriver):
    """Chat agent driver that uses the agent configuration platform"""

    def __init__(
        self, 
        manifest: DriverManifest, 
        config: Optional[Dict[str, Any]] = None,
        agent_config_id: str = "chat-default"
    ):
        super().__init__(manifest, config)
        
        self.agent_config_id = agent_config_id
        self.config_manager = AgentConfigManager()
        self.agent_config: Optional[ChatAgentConfig] = None
        
        # Context hub settings
        self.context_hub_url = config.get("context_hub_url") if config else None
        if not self.context_hub_url:
            self.context_hub_url = os.environ.get("CONTEXT_HUB_URL", "http://localhost:3000")
        
        # Initialize completions API
        self._completions_api = None

    async def initialize(self):
        """Initialize the driver with agent configuration"""
        await super().initialize()
        
        # Load agent configuration (using default user for now)
        try:
            config = await self.config_manager.get_agent_config(self.agent_config_id)
            if not isinstance(config, ChatAgentConfig):
                # Convert to ChatAgentConfig if needed
                from .schemas import AgentType
                if config.type != AgentType.CHAT:
                    raise ValueError(f"Expected chat agent config, got {config.type}")
                
                # Create ChatAgentConfig from base config
                self.agent_config = ChatAgentConfig(
                    id=config.id,
                    name=config.name,
                    description=config.description,
                    system_prompt=config.system_prompt,
                    tools=config.tools,
                    environment=config.environment,
                    model_config=config.model_config,
                    behavior_config=config.behavior_config,
                    created_by=config.created_by,
                    created_at=config.created_at,
                    version=config.version,
                    is_default=config.is_default,
                    is_system=config.is_system,
                    tags=config.tags
                )
            else:
                self.agent_config = config
            
            logger.info(f"Loaded agent configuration: {self.agent_config.name}")
            
        except Exception as e:
            logger.error(f"Failed to load agent configuration {self.agent_config_id}: {e}")
            # Fall back to creating a default config
            self.agent_config = ChatAgentConfig(
                id="fallback-chat",
                name="Fallback Chat Agent",
                description="Fallback configuration when default config fails to load"
            )

    def get_capabilities(self) -> List[str]:
        """Return capabilities based on agent configuration"""
        if not self.agent_config:
            return self.manifest.capabilities
        
        # Build capabilities from enabled tools
        capabilities = ["llm.chat", "conversation.manage"]
        
        for tool in self.agent_config.tools:
            if tool.enabled:
                if tool.name == "search_user_context":
                    capabilities.append("context.search")
                elif tool.name == "read_document":
                    capabilities.append("context.read")
                elif tool.name == "write_document":
                    capabilities.append("context.write")
                elif tool.name == "list_documents":
                    capabilities.append("context.list")
        
        return capabilities

    def get_resource_requirements(self) -> ResourceSpec:
        """Return resource requirements based on configuration"""
        if self.agent_config and self.agent_config.behavior_config:
            return ResourceSpec(
                memory_mb=1024,
                timeout_seconds=self.agent_config.behavior_config.timeout_seconds
            )
        return ResourceSpec(memory_mb=1024, timeout_seconds=60)

    async def _handle_event_impl(self, event: Event) -> List[Event]:
        """Handle chat-related events using configurable behavior"""
        output_events = []

        if not self.agent_config:
            await self.initialize()

        logger.info(f"[TRACE] ConfigurableChatAgentDriver handling event: {event.type}")

        if isinstance(event, LLMChatEvent):
            try:
                # Process chat request using configured behavior
                messages = event.data.get("messages", []).copy()

                # Build system message from configuration
                system_prompt = self._build_system_prompt(event.user_id)
                system_message = {"role": "system", "content": system_prompt}

                # Insert system message
                if not messages or messages[0]["role"] != "system":
                    messages.insert(0, system_message)
                else:
                    messages[0]["content"] = system_message["content"]

                # Get completions API
                if self._completions_api is None:
                    from ..llm import get_completions_api
                    self._completions_api = get_completions_api()

                # Get model configuration
                model_config = self.agent_config.model_config
                model_registry = get_model_registry()
                model = model_registry.get_model(model_config.model_id)
                model_id = model.id if model else model_config.model_id

                # Get enabled tools
                tools = self._get_enabled_tools()
                
                # Process with configured behavior
                if self.agent_config.behavior_config.search_before_response and tools:
                    # Force search before responding if configured
                    response = await self._process_with_search_first(
                        messages, model_id, tools, event.user_id
                    )
                else:
                    # Standard processing
                    response = await self._process_standard(
                        messages, model_id, tools, event.user_id
                    )

                # Create response event
                response_event = Event(
                    timestamp=datetime.utcnow(),
                    source="ConfigurableChatAgentDriver",
                    type="llm.chat.response",
                    user_id=event.user_id,
                    data={"response": response.get("content", ""), "usage": response.get("usage", {})},
                    metadata={
                        "request_id": event.metadata.get("request_id"),
                        "chat_request_id": event.id,
                        "session_id": event.metadata.get("session_id"),
                        "turn_number": event.metadata.get("turn_number"),
                        "response_timestamp": datetime.utcnow().isoformat(),
                        "agent_config_id": self.agent_config.id
                    }
                )
                output_events.append(response_event)

            except Exception as e:
                logger.error(f"Chat completion failed: {e}")
                
                # Create error event
                error_event = Event(
                    timestamp=datetime.utcnow(),
                    source="ConfigurableChatAgentDriver",
                    type="llm.chat.error",
                    user_id=event.user_id,
                    data={"error": str(e)},
                    metadata={
                        "request_id": event.metadata.get("request_id"),
                        "chat_request_id": event.id,
                        "agent_config_id": self.agent_config.id if self.agent_config else "unknown"
                    }
                )
                output_events.append(error_event)

        return output_events

    def _build_system_prompt(self, user_id: str) -> str:
        """Build system prompt from configuration with user context"""
        if not self.agent_config:
            return "You are a helpful AI assistant."
        
        # Get prompt parameters from behavior config
        prompt_params = {}
        
        behavior = self.agent_config.behavior_config
        if hasattr(behavior, 'custom') and behavior.custom:
            prompt_params.update(behavior.custom)
        
        # Add default parameters
        default_params = {}
        for param_name, param in self.agent_config.system_prompt.parameters.items():
            default_params[param_name] = param.default_value
        
        # Merge parameters (custom overrides defaults)
        all_params = {**default_params, **prompt_params}
        
        try:
            return self.agent_config.system_prompt.render(**all_params)
        except Exception as e:
            logger.error(f"Failed to render system prompt: {e}")
            return self.agent_config.system_prompt.template

    def _get_enabled_tools(self) -> List[Dict[str, Any]]:
        """Get function definitions for enabled tools"""
        if not self.agent_config:
            return []
        
        tools = []
        
        for tool_config in self.agent_config.tools:
            if not tool_config.enabled:
                continue
            
            if tool_config.name == "search_user_context":
                tools.append({
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
                })
            
            elif tool_config.name == "read_document":
                tools.append({
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
                })
            
            elif tool_config.name == "write_document":
                tools.append({
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
                                    "description": "Optional: UUID of existing document to update",
                                },
                                "parent_folder_id": {
                                    "type": "string",
                                    "description": "Optional: UUID of parent folder",
                                },
                            },
                            "required": ["name", "content"],
                        },
                    },
                })
            
            elif tool_config.name == "list_documents":
                tools.append({
                    "type": "function",
                    "function": {
                        "name": "list_documents",
                        "description": "List documents in a specific folder or root of the user's context hub",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "folder_id": {
                                    "type": "string",
                                    "description": "Optional: UUID of folder to list",
                                },
                            },
                        },
                    },
                })
        
        return tools

    async def _process_standard(
        self, 
        messages: List[Dict], 
        model_id: str, 
        tools: List[Dict], 
        user_id: str
    ) -> Dict[str, Any]:
        """Standard message processing with optional function calling"""
        
        create_params = {
            "model": model_id,
            "messages": messages,
            "user_id": user_id,
            "temperature": self.agent_config.model_config.temperature,
            "max_tokens": self.agent_config.model_config.max_tokens,
        }
        
        if tools:
            create_params["tools"] = tools
            create_params["tool_choice"] = "auto"
        
        response = await self._completions_api.create(**create_params)
        
        message = response.choices[0].message
        usage = {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        }
        
        # Handle function calls if present
        if message.tool_calls:
            # Process function calls and get final response
            return await self._handle_function_calls(messages, message, model_id, tools, user_id, usage)
        
        return {
            "content": message.content,
            "usage": usage
        }

    async def _process_with_search_first(
        self, 
        messages: List[Dict], 
        model_id: str, 
        tools: List[Dict], 
        user_id: str
    ) -> Dict[str, Any]:
        """Force a context search before responding"""
        
        # Extract the user's last message for search
        last_user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_message = msg.get("content", "")
                break
        
        if last_user_message and any(tool["function"]["name"] == "search_user_context" for tool in tools):
            # Perform automatic search
            search_result = await self._handle_function_call(
                "search_user_context", 
                {"query": last_user_message[:100], "limit": 3}, 
                user_id
            )
            
            # Add search result as a system message
            search_message = {
                "role": "system",
                "content": f"Relevant context from your memory: {search_result}"
            }
            messages.append(search_message)
        
        # Now process normally
        return await self._process_standard(messages, model_id, tools, user_id)

    async def _handle_function_calls(
        self, 
        messages: List[Dict], 
        message, 
        model_id: str, 
        tools: List[Dict], 
        user_id: str,
        usage: Dict[str, int]
    ) -> Dict[str, Any]:
        """Handle function calls and return final response"""
        
        # Add assistant message with tool calls
        tool_calls_dict = []
        for tc in message.tool_calls:
            tool_calls_dict.append({
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments
                }
            })
        
        messages.append({
            "role": "assistant",
            "content": message.content,
            "tool_calls": tool_calls_dict
        })

        # Process each function call
        for tool_call in message.tool_calls:
            try:
                arguments = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                arguments = {}

            function_result = await self._handle_function_call(
                tool_call.function.name, arguments, user_id
            )

            # Add function result to messages
            messages.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": tool_call.function.name,
                "content": function_result,
            })

        # Get final response
        final_response = await self._completions_api.create(
            model=model_id,
            messages=messages,
            user_id=user_id,
            temperature=self.agent_config.model_config.temperature,
            max_tokens=self.agent_config.model_config.max_tokens,
            tools=tools,
            tool_choice="auto",
        )

        final_message = final_response.choices[0].message
        
        # Update usage stats
        if final_response.usage:
            usage["prompt_tokens"] += final_response.usage.prompt_tokens
            usage["completion_tokens"] += final_response.usage.completion_tokens
            usage["total_tokens"] += final_response.usage.total_tokens

        return {
            "content": final_message.content,
            "usage": usage
        }

    async def _handle_function_call(
        self, function_name: str, arguments: Dict[str, Any], user_id: str
    ) -> str:
        """Handle individual function calls - reuse logic from original ChatAgentDriver"""
        
        if function_name == "search_user_context":
            query = arguments.get("query", "")
            limit = arguments.get("limit", 5)

            if not query:
                return "Error: No search query provided"

            results = await self._search_user_context(user_id, query, limit)
            if not results:
                return "No relevant documents found in your context hub."

            # Format results
            formatted_results = []
            index_guides = set()
            
            for result in results:
                guide = result.get('index_guide')
                if guide:
                    index_guides.add(guide)
                
                content_snippet = result.get('snippet', result.get('content', '')[:500])
                formatted_results.append(
                    f"**{result.get('name', 'Untitled')}** (ID: {result.get('id', 'unknown')})\n{content_snippet}..."
                )

            response = f"Found {len(formatted_results)} relevant documents:\n\n"
            
            if index_guides:
                response += "**Folder Guidelines:**\n"
                for guide in index_guides:
                    response += f"{guide}\n\n---\n\n"
                response += "**Search Results:**\n\n"
            
            response += "\n\n".join(formatted_results)
            return response

        elif function_name == "read_document":
            document_id = arguments.get("document_id", "")
            if not document_id:
                return "Error: No document ID provided"

            document = await self._read_document(user_id, document_id)
            if document:
                response = f"**{document.get('name', 'Untitled')}**\n\n"
                
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
                index_guide = None
                if documents and isinstance(documents, list) and len(documents) > 0:
                    index_guide = documents[0].get('index_guide')
                
                response = ""
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

    # Context hub API methods (reused from original implementation)
    async def _search_user_context(self, user_id: str, query: str, limit: int = 5) -> Optional[List[Dict]]:
        """Search user's context-hub for relevant documents"""
        try:
            url = f"{self.context_hub_url.rstrip('/')}/search"
            headers = {"X-User-Id": user_id}
            params = {"q": query, "limit": limit}

            response = await asyncio.to_thread(
                requests.get, url, headers=headers, params=params, timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    return data
                else:
                    return data.get("results", [])
            else:
                logger.error(f"Context search failed for user {user_id}: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Context Hub connection failed for user {user_id}: {e}")
            return []

    async def _read_document(self, user_id: str, document_id: str) -> Optional[Dict[str, Any]]:
        """Read a specific document from context hub"""
        try:
            url = f"{self.context_hub_url.rstrip('/')}/docs/{document_id}"
            headers = {"X-User-Id": user_id}

            response = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                return None
        except Exception as e:
            logger.error(f"Context Hub read failed for user {user_id}: {e}")
            return None

    async def _write_document(
        self, user_id: str, name: str, content: str, 
        document_id: Optional[str] = None, parent_folder_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Create or update a document in context hub"""
        try:
            headers = {"X-User-Id": user_id, "Content-Type": "application/json"}
            
            if document_id:
                # Update existing document
                url = f"{self.context_hub_url.rstrip('/')}/docs/{document_id}"
                data = {"content": content}
                response = await asyncio.to_thread(requests.put, url, headers=headers, json=data, timeout=10)
                if response.status_code == 204:
                    return {"id": document_id, "name": name}
                else:
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
                response = await asyncio.to_thread(requests.post, url, headers=headers, json=data, timeout=10)
                if response.status_code == 200:
                    return response.json()
                else:
                    return None
        except Exception as e:
            logger.error(f"Context Hub write failed for user {user_id}: {e}")
            return None

    async def _list_documents(self, user_id: str, folder_id: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """List documents in a folder"""
        try:
            if folder_id:
                url = f"{self.context_hub_url.rstrip('/')}/folders/{folder_id}"
            else:
                url = f"{self.context_hub_url.rstrip('/')}/docs"
            
            headers = {"X-User-Id": user_id}
            response = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                return response.json()
            else:
                return []
        except Exception as e:
            logger.error(f"Context Hub listing failed for user {user_id}: {e}")
            return []


# Factory function for easy instantiation
def create_configurable_chat_agent(
    agent_config_id: str = "chat-default",
    context_hub_url: Optional[str] = None
) -> ConfigurableChatAgentDriver:
    """Create a configurable chat agent with specified configuration"""
    
    manifest = DriverManifest(
        id="configurable_chat_agent",
        name="Configurable Chat Agent",
        version="1.0.0",
        author="Lightning",
        description="Configurable chat agent using the agent configuration platform",
        driver_type=DriverType.AGENT,
        capabilities=["llm.chat", "context.search", "context.read", "context.write", "context.list"],
        resource_requirements=ResourceSpec(memory_mb=1024, timeout_seconds=60),
    )
    
    config = {}
    if context_hub_url:
        config["context_hub_url"] = context_hub_url
    
    return ConfigurableChatAgentDriver(
        manifest=manifest,
        config=config,
        agent_config_id=agent_config_id
    )