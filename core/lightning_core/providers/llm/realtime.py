"""OpenAI Realtime API provider for voice interactions."""

import os
import json
import logging
import asyncio
from typing import Any, Dict, Optional, Set, Callable
from datetime import datetime
import websockets
from websockets.client import WebSocketClientProtocol

from lightning_core.abstractions.llm import LLMProvider, LLMProviderConfig
from lightning_core.vextir_os.registries import UsageRecord

logger = logging.getLogger(__name__)


class RealtimeSession:
    """Represents an active Realtime API session."""
    
    def __init__(
        self,
        session_id: str,
        user_id: str,
        websocket: WebSocketClientProtocol,
        on_usage: Optional[Callable[[UsageRecord], None]] = None
    ):
        self.session_id = session_id
        self.user_id = user_id
        self.websocket = websocket
        self.on_usage = on_usage
        self.created_at = datetime.now()
        self.total_tokens = 0
        self.audio_duration_seconds = 0.0
        self.closed = False
        
    async def send(self, event: Dict[str, Any]):
        """Send an event to the OpenAI Realtime API."""
        if not self.closed:
            await self.websocket.send(json.dumps(event))
            
    async def close(self):
        """Close the session."""
        if not self.closed:
            self.closed = True
            await self.websocket.close()
            
            # Report usage if handler provided
            if self.on_usage and (self.total_tokens > 0 or self.audio_duration_seconds > 0):
                # Calculate approximate cost
                # GPT-4o Realtime pricing (as of Dec 2024):
                # Audio input: $100/1M tokens (~$0.06/minute)
                # Audio output: $200/1M tokens (~$0.24/minute)
                audio_cost = (self.audio_duration_seconds / 60) * 0.15  # Average of input/output
                
                usage = UsageRecord(
                    model_id="gpt-4o-realtime",
                    user_id=self.user_id,
                    timestamp=datetime.now(),
                    prompt_tokens=0,  # Realtime doesn't separate prompt/completion
                    completion_tokens=0,
                    total_tokens=self.total_tokens,
                    cost=audio_cost,
                    request_id=self.session_id,
                    metadata={
                        "session_type": "realtime",
                        "audio_duration_seconds": self.audio_duration_seconds,
                    }
                )
                self.on_usage(usage)


class OpenAIRealtimeProvider:
    """Provider for OpenAI's Realtime API for voice interactions."""
    
    BASE_URL = "wss://api.openai.com/v1/realtime"
    
    # Supported models
    SUPPORTED_MODELS = {
        "gpt-4o-realtime-preview",
        "gpt-4o-realtime-preview-2024-12-17",
        "gpt-4o-realtime",  # Future stable version
    }
    
    def __init__(self, config: LLMProviderConfig):
        """Initialize Realtime provider."""
        self.config = config
        self.api_key = config.api_key or os.getenv("OPENAI_API_KEY")
        
        if not self.api_key:
            raise ValueError("OpenAI API key is required for Realtime API")
            
        self.sessions: Dict[str, RealtimeSession] = {}
        self._usage_handler: Optional[Callable[[UsageRecord], None]] = None
        
    def set_usage_handler(self, handler: Callable[[UsageRecord], None]):
        """Set handler for usage tracking."""
        self._usage_handler = handler
        
    async def create_session(
        self,
        user_id: str,
        model: str = "gpt-4o-realtime-preview-2024-12-17",
        voice: str = "ash",
        instructions: Optional[str] = None,
        input_audio_format: str = "g711_ulaw",
        output_audio_format: str = "g711_ulaw",
        turn_detection: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> RealtimeSession:
        """
        Create a new Realtime API session.
        
        Args:
            user_id: User ID for tracking
            model: Model to use (must be a realtime model)
            voice: Voice to use (alloy, ash, echo, fable, nova, onyx, shimmer)
            instructions: System instructions
            input_audio_format: Format for input audio
            output_audio_format: Format for output audio
            turn_detection: Turn detection configuration
            tools: Available function tools
            **kwargs: Additional session parameters
            
        Returns:
            RealtimeSession object
        """
        if model not in self.SUPPORTED_MODELS:
            raise ValueError(f"Model {model} is not supported for Realtime API")
            
        # Build WebSocket URL
        url = f"{self.BASE_URL}?model={model}"
        
        # Connect to OpenAI Realtime API
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1",
        }
        
        try:
            websocket = await websockets.connect(url, extra_headers=headers)
            
            # Create session
            session_id = f"realtime_{user_id}_{datetime.now().timestamp()}"
            session = RealtimeSession(
                session_id=session_id,
                user_id=user_id,
                websocket=websocket,
                on_usage=self._usage_handler
            )
            
            # Send initial configuration
            config_event = {
                "type": "session.update",
                "session": {
                    "voice": voice,
                    "input_audio_format": input_audio_format,
                    "output_audio_format": output_audio_format,
                    "input_audio_transcription": {
                        "model": "whisper-1"
                    }
                }
            }
            
            if instructions:
                config_event["session"]["instructions"] = instructions
                
            if turn_detection:
                config_event["session"]["turn_detection"] = turn_detection
            else:
                # Default to server VAD
                config_event["session"]["turn_detection"] = {
                    "type": "server_vad"
                }
                
            if tools:
                config_event["session"]["tools"] = tools
                
            # Add any additional session parameters
            for key, value in kwargs.items():
                if key not in config_event["session"]:
                    config_event["session"][key] = value
                    
            await session.send(config_event)
            
            # Store session
            self.sessions[session_id] = session
            
            logger.info(f"Created Realtime session {session_id} for user {user_id}")
            
            return session
            
        except Exception as e:
            logger.error(f"Failed to create Realtime session: {e}")
            raise
            
    async def close_session(self, session_id: str):
        """Close a Realtime session."""
        if session_id in self.sessions:
            session = self.sessions[session_id]
            await session.close()
            del self.sessions[session_id]
            logger.info(f"Closed Realtime session {session_id}")
            
    async def close_all_sessions(self):
        """Close all active sessions."""
        session_ids = list(self.sessions.keys())
        for session_id in session_ids:
            await self.close_session(session_id)
            
    def get_session(self, session_id: str) -> Optional[RealtimeSession]:
        """Get an active session by ID."""
        return self.sessions.get(session_id)
        
    def list_sessions(self) -> List[str]:
        """List all active session IDs."""
        return list(self.sessions.keys())
        
    def supports_model(self, model_id: str) -> bool:
        """Check if this provider supports the given model."""
        return model_id in self.SUPPORTED_MODELS


class RealtimeProxy:
    """
    Proxy server for OpenAI Realtime API that integrates with Lightning Core.
    
    This proxy allows voice agents to connect through Lightning Core,
    enabling usage tracking, access control, and centralized management.
    """
    
    def __init__(
        self,
        provider: OpenAIRealtimeProvider,
        host: str = "0.0.0.0",
        port: int = 8001,
    ):
        """Initialize the Realtime proxy server."""
        self.provider = provider
        self.host = host
        self.port = port
        self.client_sessions: Dict[str, RealtimeSession] = {}
        
    async def handle_client(self, websocket, path):
        """Handle a client WebSocket connection."""
        client_id = f"client_{datetime.now().timestamp()}"
        session = None
        
        try:
            # Extract user ID and configuration from path or first message
            # For now, we'll get it from the first message
            first_message = await websocket.recv()
            config = json.loads(first_message)
            
            # Create OpenAI session
            session = await self.provider.create_session(
                user_id=config.get("user_id", "anonymous"),
                model=config.get("model", "gpt-4o-realtime-preview-2024-12-17"),
                voice=config.get("voice", "ash"),
                instructions=config.get("instructions"),
                input_audio_format=config.get("input_audio_format", "g711_ulaw"),
                output_audio_format=config.get("output_audio_format", "g711_ulaw"),
                turn_detection=config.get("turn_detection"),
                tools=config.get("tools"),
            )
            
            self.client_sessions[client_id] = session
            
            # Send confirmation
            await websocket.send(json.dumps({
                "type": "session.created",
                "session_id": session.session_id,
            }))
            
            # Create tasks for bidirectional proxying
            client_to_openai = asyncio.create_task(
                self._proxy_client_to_openai(websocket, session)
            )
            openai_to_client = asyncio.create_task(
                self._proxy_openai_to_client(websocket, session)
            )
            
            # Wait for either task to complete
            done, pending = await asyncio.wait(
                [client_to_openai, openai_to_client],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Cancel pending tasks
            for task in pending:
                task.cancel()
                
        except Exception as e:
            logger.error(f"Error handling client {client_id}: {e}")
            
        finally:
            # Clean up
            if session:
                await self.provider.close_session(session.session_id)
            if client_id in self.client_sessions:
                del self.client_sessions[client_id]
                
    async def _proxy_client_to_openai(self, client_ws, session: RealtimeSession):
        """Proxy messages from client to OpenAI."""
        try:
            async for message in client_ws:
                if isinstance(message, str):
                    data = json.loads(message)
                    
                    # Track audio duration for billing
                    if data.get("type") == "input_audio_buffer.append":
                        # Estimate duration based on audio format
                        # G.711 μ-law is 8kHz, 8-bit mono
                        audio_data = data.get("audio", "")
                        duration = len(audio_data) / 16000  # Approximate
                        session.audio_duration_seconds += duration
                        
                    await session.send(data)
                else:
                    # Binary audio data
                    await session.websocket.send(message)
                    
        except websockets.exceptions.ConnectionClosed:
            pass
            
    async def _proxy_openai_to_client(self, client_ws, session: RealtimeSession):
        """Proxy messages from OpenAI to client."""
        try:
            async for message in session.websocket:
                if isinstance(message, str):
                    data = json.loads(message)
                    
                    # Track usage
                    if data.get("type") == "response.audio_transcript.done":
                        # Track completion
                        transcript = data.get("transcript", "")
                        # Estimate tokens (rough approximation)
                        session.total_tokens += len(transcript.split()) * 1.3
                        
                    elif data.get("type") == "response.audio.delta":
                        # Track audio generation
                        audio_data = data.get("delta", "")
                        duration = len(audio_data) / 16000  # Approximate
                        session.audio_duration_seconds += duration
                        
                    await client_ws.send(message)
                else:
                    # Binary audio data
                    await client_ws.send(message)
                    
        except websockets.exceptions.ConnectionClosed:
            pass
            
    async def start(self):
        """Start the proxy server."""
        logger.info(f"Starting Realtime proxy server on {self.host}:{self.port}")
        
        async with websockets.serve(self.handle_client, self.host, self.port):
            await asyncio.Future()  # Run forever