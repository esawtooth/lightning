"""WebSocket API for OpenAI Realtime voice interactions."""

import os
import json
import logging
import asyncio
from typing import Dict, Optional, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse

from ..providers.llm.realtime import OpenAIRealtimeProvider, RealtimeSession
from ..vextir_os.registries import get_model_registry, UsageRecord
from ..abstractions.llm import LLMProviderConfig

logger = logging.getLogger(__name__)

app = FastAPI(title="Lightning Realtime API", version="1.0.0")

# Global provider instance
realtime_provider: Optional[OpenAIRealtimeProvider] = None


def get_realtime_provider() -> OpenAIRealtimeProvider:
    """Get or create the Realtime provider."""
    global realtime_provider
    
    if realtime_provider is None:
        config = LLMProviderConfig(
            provider_type="openai-realtime",
            api_key=os.getenv("OPENAI_API_KEY"),
        )
        realtime_provider = OpenAIRealtimeProvider(config)
        
        # Set up usage tracking
        model_registry = get_model_registry()
        realtime_provider.set_usage_handler(
            lambda record: model_registry._track_usage(record)
        )
        
    return realtime_provider


@app.get("/")
async def root():
    """Root endpoint with basic info."""
    return {
        "service": "Lightning Realtime API",
        "version": "1.0.0",
        "description": "WebSocket proxy for OpenAI Realtime voice interactions",
        "endpoints": {
            "/health": "Health check",
            "/realtime": "WebSocket endpoint for Realtime sessions",
            "/sessions": "List active sessions",
            "/demo": "Demo page for testing",
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    provider = get_realtime_provider()
    return {
        "status": "healthy",
        "service": "realtime",
        "active_sessions": len(provider.sessions),
    }


@app.get("/sessions")
async def list_sessions():
    """List active Realtime sessions."""
    provider = get_realtime_provider()
    sessions = []
    
    for session_id, session in provider.sessions.items():
        sessions.append({
            "session_id": session_id,
            "user_id": session.user_id,
            "created_at": session.created_at.isoformat(),
            "duration_seconds": (datetime.now() - session.created_at).total_seconds(),
            "audio_duration_seconds": session.audio_duration_seconds,
            "total_tokens": session.total_tokens,
        })
        
    return {"sessions": sessions, "count": len(sessions)}


@app.websocket("/realtime")
async def realtime_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for Realtime voice interactions.
    
    The first message should be a configuration object:
    {
        "user_id": "user123",
        "model": "gpt-4o-realtime-preview-2024-12-17",
        "voice": "ash",
        "instructions": "You are a helpful assistant",
        "tools": [...],
        "turn_detection": {...}
    }
    """
    await websocket.accept()
    
    provider = get_realtime_provider()
    session: Optional[RealtimeSession] = None
    client_to_openai_task = None
    openai_to_client_task = None
    
    try:
        # Get configuration from first message
        config_message = await websocket.receive_text()
        config = json.loads(config_message)
        
        # Validate user_id
        user_id = config.get("user_id")
        if not user_id:
            await websocket.send_json({
                "type": "error",
                "error": "user_id is required"
            })
            await websocket.close()
            return
            
        # Create Realtime session
        session = await provider.create_session(
            user_id=user_id,
            model=config.get("model", "gpt-4o-realtime-preview-2024-12-17"),
            voice=config.get("voice", "ash"),
            instructions=config.get("instructions"),
            input_audio_format=config.get("input_audio_format", "g711_ulaw"),
            output_audio_format=config.get("output_audio_format", "g711_ulaw"),
            turn_detection=config.get("turn_detection"),
            tools=config.get("tools"),
        )
        
        # Send session created confirmation
        await websocket.send_json({
            "type": "session.created",
            "session_id": session.session_id,
            "model": config.get("model", "gpt-4o-realtime-preview-2024-12-17"),
        })
        
        # Create bidirectional proxy tasks
        client_to_openai_task = asyncio.create_task(
            proxy_client_to_openai(websocket, session)
        )
        openai_to_client_task = asyncio.create_task(
            proxy_openai_to_client(websocket, session)
        )
        
        # Wait for either task to complete
        done, pending = await asyncio.wait(
            [client_to_openai_task, openai_to_client_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # Cancel pending tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
                
    except WebSocketDisconnect:
        logger.info("Client disconnected")
    except Exception as e:
        logger.error(f"Error in realtime endpoint: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "error": str(e)
            })
        except:
            pass
    finally:
        # Clean up
        if session:
            await provider.close_session(session.session_id)
        if client_to_openai_task and not client_to_openai_task.done():
            client_to_openai_task.cancel()
        if openai_to_client_task and not openai_to_client_task.done():
            openai_to_client_task.cancel()


async def proxy_client_to_openai(websocket: WebSocket, session: RealtimeSession):
    """Proxy messages from client to OpenAI."""
    try:
        while True:
            # Receive from client
            message = await websocket.receive()
            
            if "text" in message:
                # JSON message
                data = json.loads(message["text"])
                
                # Track audio duration for billing
                if data.get("type") == "input_audio_buffer.append":
                    audio_data = data.get("audio", "")
                    # G.711 μ-law is 8kHz, estimate duration
                    duration = len(audio_data) / 16000
                    session.audio_duration_seconds += duration
                    
                # Send to OpenAI
                await session.send(data)
                
            elif "bytes" in message:
                # Binary audio data
                await session.websocket.send(message["bytes"])
                
    except WebSocketDisconnect:
        logger.info("Client disconnected during proxy")
    except Exception as e:
        logger.error(f"Error proxying client to OpenAI: {e}")
        raise


async def proxy_openai_to_client(websocket: WebSocket, session: RealtimeSession):
    """Proxy messages from OpenAI to client."""
    try:
        async for message in session.websocket:
            if isinstance(message, str):
                # JSON message
                data = json.loads(message)
                
                # Track usage for billing
                if data.get("type") == "response.audio_transcript.done":
                    transcript = data.get("transcript", "")
                    # Rough token estimation
                    session.total_tokens += int(len(transcript.split()) * 1.3)
                    
                elif data.get("type") == "response.audio.delta":
                    audio_data = data.get("delta", "")
                    # Track audio generation
                    duration = len(audio_data) / 16000
                    session.audio_duration_seconds += duration
                    
                # Send to client
                await websocket.send_text(message)
                
            else:
                # Binary audio data
                await websocket.send_bytes(message)
                
    except websockets.exceptions.ConnectionClosed:
        logger.info("OpenAI connection closed")
    except Exception as e:
        logger.error(f"Error proxying OpenAI to client: {e}")
        raise


@app.get("/demo", response_class=HTMLResponse)
async def demo_page():
    """Simple demo page for testing Realtime API."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Lightning Realtime Demo</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            button { margin: 10px; padding: 10px; }
            #status { margin: 20px 0; padding: 10px; background: #f0f0f0; }
            #log { height: 300px; overflow-y: scroll; border: 1px solid #ccc; padding: 10px; }
        </style>
    </head>
    <body>
        <h1>Lightning Realtime API Demo</h1>
        
        <div>
            <input type="text" id="userId" placeholder="User ID" value="demo_user">
            <select id="voice">
                <option value="ash">Ash</option>
                <option value="alloy">Alloy</option>
                <option value="echo">Echo</option>
                <option value="fable">Fable</option>
                <option value="nova">Nova</option>
                <option value="onyx">Onyx</option>
                <option value="shimmer">Shimmer</option>
            </select>
        </div>
        
        <div>
            <button onclick="connect()">Connect</button>
            <button onclick="disconnect()">Disconnect</button>
            <button onclick="sendText()">Send Text</button>
        </div>
        
        <div id="status">Disconnected</div>
        
        <textarea id="textInput" placeholder="Type a message..." rows="3" cols="50"></textarea>
        
        <div id="log"></div>
        
        <script>
            let ws = null;
            let sessionId = null;
            
            function log(message) {
                const logDiv = document.getElementById('log');
                logDiv.innerHTML += message + '<br>';
                logDiv.scrollTop = logDiv.scrollHeight;
            }
            
            function updateStatus(status) {
                document.getElementById('status').textContent = status;
            }
            
            async function connect() {
                if (ws) {
                    log('Already connected');
                    return;
                }
                
                const userId = document.getElementById('userId').value;
                const voice = document.getElementById('voice').value;
                
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                ws = new WebSocket(`${protocol}//${window.location.host}/realtime`);
                
                ws.onopen = () => {
                    log('WebSocket connected');
                    updateStatus('Connected - Sending config...');
                    
                    // Send configuration
                    ws.send(JSON.stringify({
                        user_id: userId,
                        voice: voice,
                        instructions: "You are a helpful assistant. Keep responses brief.",
                        model: "gpt-4o-realtime-preview-2024-12-17"
                    }));
                };
                
                ws.onmessage = (event) => {
                    const data = JSON.parse(event.data);
                    log(`Received: ${data.type}`);
                    
                    if (data.type === 'session.created') {
                        sessionId = data.session_id;
                        updateStatus(`Connected - Session: ${sessionId}`);
                    } else if (data.type === 'response.audio_transcript.done') {
                        log(`Assistant: ${data.transcript}`);
                    } else if (data.type === 'conversation.item.input_audio_transcription.completed') {
                        log(`You: ${data.transcript}`);
                    }
                };
                
                ws.onerror = (error) => {
                    log(`Error: ${error}`);
                    updateStatus('Error');
                };
                
                ws.onclose = () => {
                    log('WebSocket disconnected');
                    updateStatus('Disconnected');
                    ws = null;
                    sessionId = null;
                };
            }
            
            function disconnect() {
                if (ws) {
                    ws.close();
                }
            }
            
            function sendText() {
                if (!ws || ws.readyState !== WebSocket.OPEN) {
                    log('Not connected');
                    return;
                }
                
                const text = document.getElementById('textInput').value;
                if (!text) return;
                
                // Send text input
                ws.send(JSON.stringify({
                    type: "conversation.item.create",
                    item: {
                        type: "message",
                        role: "user",
                        content: [{
                            type: "input_text",
                            text: text
                        }]
                    }
                }));
                
                // Request response
                ws.send(JSON.stringify({
                    type: "response.create"
                }));
                
                document.getElementById('textInput').value = '';
                log(`Sent: ${text}`);
            }
        </script>
    </body>
    </html>
    """


# Import datetime for session tracking
from datetime import datetime
import websockets

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)