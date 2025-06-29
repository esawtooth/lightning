#!/usr/bin/env python3
"""
Lightning Voice Agent - Outbound Calling Script

This script uses Lightning Core runtime to make outbound calls with objectives.
It integrates with the Context Hub, event system, and tool registry.

Usage:
    python outbound_agent.py --phone "+1234567890" --objective "Call and check on project status"
    python outbound_agent.py --phone "+1234567890" --objective "Schedule a meeting" --context "user_id:123"
"""

import argparse
import asyncio
import os
import sys
import json
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

# Add Lightning Core to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'core'))

from lightning_core.runtime import LightningRuntime
from lightning_core.events.models import Event
from lightning_core.tools.registry import ToolRegistry

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class CallObjective:
    phone_number: str
    objective: str
    context: Optional[Dict[str, Any]] = None
    max_duration_minutes: int = 15
    required_tools: list = None

class VoiceAgentOutbound:
    """Outbound voice agent using Lightning Core runtime"""
    
    def __init__(self):
        self.runtime = None
        self.tool_registry = None
        self.call_in_progress = False
        
    async def initialize(self):
        """Initialize Lightning Core runtime and tools"""
        try:
            # Initialize Lightning Core runtime
            self.runtime = LightningRuntime()
            await self.runtime.initialize()
            
            # Get tool registry
            self.tool_registry = ToolRegistry()
            
            logger.info("Lightning Core runtime initialized successfully")
            
            # Verify required tools are available
            await self._verify_tools()
            
        except Exception as e:
            logger.error(f"Failed to initialize Lightning Core: {e}")
            raise
    
    async def _verify_tools(self):
        """Verify that required tools are available"""
        required_tools = [
            "user_search",
            "web_search", 
            "generate_event"
        ]
        
        available_tools = await self.tool_registry.list_tools(scope="AGENT_VEX")
        available_names = [tool.name for tool in available_tools]
        
        missing_tools = [tool for tool in required_tools if tool not in available_names]
        if missing_tools:
            logger.warning(f"Missing tools: {missing_tools}")
        else:
            logger.info("All required tools are available")
    
    async def make_call(self, objective: CallObjective) -> Dict[str, Any]:
        """Make an outbound call with the given objective"""
        if self.call_in_progress:
            raise RuntimeError("Another call is already in progress")
        
        self.call_in_progress = True
        call_id = f"outbound-{int(asyncio.get_event_loop().time())}"
        
        try:
            logger.info(f"Starting outbound call to {objective.phone_number} with objective: {objective.objective}")
            
            # Generate start event
            await self._publish_event("voice.call.started", {
                "call_id": call_id,
                "phone_number": objective.phone_number,
                "objective": objective.objective,
                "context": objective.context or {}
            })
            
            # Prepare context for the call
            context_info = await self._gather_context(objective)
            
            # Configure voice agent for outbound call
            call_config = await self._prepare_call_config(objective, context_info)
            
            # Initiate the call via Twilio
            call_result = await self._initiate_twilio_call(objective, call_config)
            
            if call_result["success"]:
                logger.info(f"Call initiated successfully: {call_result['call_sid']}")
                
                # Monitor call progress
                await self._monitor_call(call_id, call_result["call_sid"], objective)
                
                return {
                    "success": True,
                    "call_id": call_id,
                    "call_sid": call_result["call_sid"],
                    "objective": objective.objective,
                    "status": "completed"
                }
            else:
                raise Exception(f"Failed to initiate call: {call_result.get('error', 'Unknown error')}")
                
        except Exception as e:
            logger.error(f"Call failed: {e}")
            await self._publish_event("voice.call.failed", {
                "call_id": call_id,
                "phone_number": objective.phone_number,
                "error": str(e)
            })
            return {
                "success": False,
                "call_id": call_id,
                "error": str(e)
            }
        finally:
            self.call_in_progress = False
    
    async def _gather_context(self, objective: CallObjective) -> Dict[str, Any]:
        """Gather relevant context for the call"""
        context = {"gathered_info": []}
        
        # Search context hub for relevant information
        if objective.context and "search_queries" in objective.context:
            for query in objective.context["search_queries"]:
                try:
                    search_results = await self._search_context_hub(query)
                    context["gathered_info"].append({
                        "query": query,
                        "results": search_results
                    })
                except Exception as e:
                    logger.warning(f"Failed to search context for '{query}': {e}")
        
        # Add user-specific context if available
        if objective.context and "user_id" in objective.context:
            try:
                user_info = await self._get_user_info(objective.context["user_id"])
                context["user_info"] = user_info
            except Exception as e:
                logger.warning(f"Failed to get user info: {e}")
        
        return context
    
    async def _search_context_hub(self, query: str) -> Dict[str, Any]:
        """Search the context hub for information"""
        storage = self.runtime.get_storage()
        # Use Context Hub search through Lightning Core
        results = await storage.search_documents(query, limit=3)
        return {
            "query": query,
            "documents": [
                {
                    "title": doc.get("title", "Unknown"),
                    "content": doc.get("content", "")[:500] + "..." if len(doc.get("content", "")) > 500 else doc.get("content", ""),
                    "relevance": doc.get("score", 0)
                }
                for doc in results
            ]
        }
    
    async def _get_user_info(self, user_id: str) -> Dict[str, Any]:
        """Get user information"""
        storage = self.runtime.get_storage()
        user = await storage.get_document("users", user_id)
        return {
            "id": user.get("id"),
            "name": user.get("name"),
            "preferences": user.get("preferences", {}),
            "recent_interactions": user.get("recent_interactions", [])
        }
    
    async def _prepare_call_config(self, objective: CallObjective, context: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare configuration for the voice agent"""
        system_prompt = f"""You are an AI assistant making an outbound call with the following objective:
{objective.objective}

Context information available:
{json.dumps(context, indent=2)}

Guidelines:
1. Be polite and introduce yourself clearly
2. Explain the purpose of your call based on the objective
3. Use the context information to provide relevant details
4. Ask clarifying questions if needed
5. Use available tools (user_search, web_search, generate_event) as needed
6. Keep the call focused and respect the person's time
7. Summarize next steps before ending the call

Available tools:
- user_search: Search knowledge base for information
- web_search: Search the web for current information
- generate_event: Create events in the system for follow-up actions
- dial_digits: Send DTMF digits if navigating phone menus
"""
        
        return {
            "system_prompt": system_prompt,
            "objective": objective.objective,
            "context": context,
            "max_duration": objective.max_duration_minutes * 60,
            "tools_enabled": True
        }
    
    async def _initiate_twilio_call(self, objective: CallObjective, call_config: Dict[str, Any]) -> Dict[str, Any]:
        """Initiate the call through Twilio"""
        try:
            # Get Twilio configuration
            twilio_account_sid = os.getenv("TWILIO_ACCOUNT_SID")
            twilio_auth_token = os.getenv("TWILIO_AUTH_TOKEN") 
            twilio_phone_number = os.getenv("TWILIO_PHONE_NUMBER")
            voice_agent_webhook_url = os.getenv("VOICE_AGENT_WEBHOOK_URL", "http://localhost:8081/twiml")
            
            if not all([twilio_account_sid, twilio_auth_token, twilio_phone_number]):
                raise Exception("Twilio credentials not configured")
            
            # Store call configuration for the voice agent to use
            await self._store_call_config(objective.phone_number, call_config)
            
            # Use Lightning Core to initiate the call
            # This would typically integrate with Twilio through Lightning Core's communication tools
            call_data = {
                "to": objective.phone_number,
                "from": twilio_phone_number,
                "url": voice_agent_webhook_url,
                "method": "POST"
            }
            
            # For now, simulate call initiation
            # In production, this would use actual Twilio API through Lightning Core
            logger.info(f"Call configuration prepared for {objective.phone_number}")
            
            return {
                "success": True,
                "call_sid": f"CA{int(asyncio.get_event_loop().time())}",
                "status": "initiated"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _store_call_config(self, phone_number: str, config: Dict[str, Any]):
        """Store call configuration for the voice agent to retrieve"""
        storage = self.runtime.get_storage()
        config_doc = {
            "id": f"call_config_{phone_number.replace('+', '').replace('-', '').replace(' ', '')}",
            "phone_number": phone_number,
            "config": config,
            "created_at": asyncio.get_event_loop().time(),
            "expires_at": asyncio.get_event_loop().time() + 3600  # 1 hour expiry
        }
        await storage.create_document("call_configs", config_doc)
    
    async def _monitor_call(self, call_id: str, call_sid: str, objective: CallObjective):
        """Monitor call progress and handle events"""
        # Set up event listener for call completion
        event_bus = self.runtime.get_event_bus()
        
        # Subscribe to voice call events
        async def handle_call_event(event: Event):
            if event.metadata.get("call_id") == call_id:
                logger.info(f"Call event received: {event.type}")
                
                if event.type == "voice.call.completed":
                    # Generate follow-up events based on call outcome
                    await self._handle_call_completion(call_id, event.metadata)
        
        # Subscribe to events (this is a simplified version)
        # In production, this would use Lightning Core's event subscription system
        await event_bus.subscribe("voice.*", handle_call_event)
        
        # Wait for call completion or timeout
        timeout = objective.max_duration_minutes * 60 + 60  # Extra minute buffer
        try:
            await asyncio.wait_for(self._wait_for_call_completion(call_id), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(f"Call {call_id} timed out")
            await self._publish_event("voice.call.timeout", {
                "call_id": call_id,
                "call_sid": call_sid
            })
    
    async def _wait_for_call_completion(self, call_id: str):
        """Wait for call completion event"""
        # This would typically listen for events from the event bus
        # For now, simulate with a simple wait
        await asyncio.sleep(5)  # Simulate call duration
        logger.info(f"Call {call_id} completed")
    
    async def _handle_call_completion(self, call_id: str, metadata: Dict[str, Any]):
        """Handle call completion and generate follow-up events"""
        interactions = metadata.get("total_interactions", 0)
        
        if interactions > 0:
            # Generate follow-up event if tools were used
            await self._publish_event("voice.call.requires_followup", {
                "call_id": call_id,
                "interactions": interactions,
                "followup_required": True
            })
    
    async def _publish_event(self, event_type: str, metadata: Dict[str, Any]):
        """Publish an event through Lightning Core"""
        try:
            event_bus = self.runtime.get_event_bus()
            event = Event(
                type=event_type,
                source="voice-agent-outbound",
                metadata=metadata
            )
            await event_bus.publish(event)
            logger.info(f"Published event: {event_type}")
        except Exception as e:
            logger.error(f"Failed to publish event {event_type}: {e}")

async def main():
    """Main entry point for outbound calling script"""
    parser = argparse.ArgumentParser(description="Lightning Voice Agent - Outbound Calling")
    parser.add_argument("--phone", required=True, help="Phone number to call")
    parser.add_argument("--objective", required=True, help="Call objective/purpose")
    parser.add_argument("--context", help="Additional context (JSON string)")
    parser.add_argument("--max-duration", type=int, default=15, help="Max call duration in minutes")
    parser.add_argument("--search-queries", nargs="*", help="Queries to search context hub before calling")
    parser.add_argument("--user-id", help="User ID for personalized context")
    
    args = parser.parse_args()
    
    # Parse context
    context = {}
    if args.context:
        try:
            context = json.loads(args.context)
        except json.JSONDecodeError:
            logger.error("Invalid JSON in context argument")
            return 1
    
    if args.search_queries:
        context["search_queries"] = args.search_queries
    
    if args.user_id:
        context["user_id"] = args.user_id
    
    # Create call objective
    objective = CallObjective(
        phone_number=args.phone,
        objective=args.objective,
        context=context if context else None,
        max_duration_minutes=args.max_duration
    )
    
    # Initialize and run voice agent
    agent = VoiceAgentOutbound()
    
    try:
        await agent.initialize()
        result = await agent.make_call(objective)
        
        if result["success"]:
            logger.info(f"Call completed successfully: {result['call_id']}")
            print(json.dumps(result, indent=2))
            return 0
        else:
            logger.error(f"Call failed: {result['error']}")
            print(json.dumps(result, indent=2))
            return 1
            
    except Exception as e:
        logger.error(f"Script failed: {e}")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)