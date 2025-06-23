"""
Lightning UI - Clean, functional interface for the Lightning OS
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import os
import json
import asyncio
import aiohttp
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
import uuid
from collections import defaultdict

app = FastAPI(title="Lightning UI")

# Configuration
API_BASE = os.environ.get("API_BASE", "http://localhost:7071/api")
CONTEXT_HUB_URL = os.environ.get("CONTEXT_HUB_URL", "http://localhost:3000")

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mount static files
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.chat_histories: Dict[str, List[Dict]] = defaultdict(list)

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]

    async def send_message(self, message: dict, client_id: str):
        if client_id in self.active_connections:
            await self.active_connections[client_id].send_json(message)

    def add_to_history(self, client_id: str, message: dict):
        self.chat_histories[client_id].append(message)

    def get_history(self, client_id: str) -> List[Dict]:
        return self.chat_histories[client_id]

manager = ConnectionManager()

@app.get("/", response_class=HTMLResponse)
async def root():
    """Main application interface"""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Lightning OS</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
        <style>
            .tab-content { display: none; }
            .tab-content.active { display: block; }
            .tab-button.active { 
                background-color: rgb(59, 130, 246); 
                color: white; 
            }
            .message {
                margin-bottom: 1rem;
                padding: 0.75rem 1rem;
                border-radius: 0.5rem;
                max-width: 80%;
            }
            .message.user {
                background-color: rgb(59, 130, 246);
                color: white;
                margin-left: auto;
                text-align: right;
            }
            .message.assistant {
                background-color: rgb(241, 245, 249);
                color: rgb(30, 41, 59);
            }
            .message.system {
                background-color: rgb(254, 243, 199);
                color: rgb(146, 64, 14);
                text-align: center;
                margin: 0 auto;
                font-style: italic;
            }
            #chat-messages {
                height: calc(100vh - 280px);
                overflow-y: auto;
                scroll-behavior: smooth;
            }
            .context-item {
                cursor: pointer;
                transition: all 0.2s;
            }
            .context-item:hover {
                background-color: rgb(241, 245, 249);
            }
            .context-folder {
                font-weight: 500;
            }
            .event-item {
                border-left: 4px solid transparent;
                transition: all 0.2s;
            }
            .event-item.input { border-left-color: rgb(34, 197, 94); }
            .event-item.internal { border-left-color: rgb(59, 130, 246); }
            .event-item.output { border-left-color: rgb(251, 146, 60); }
        </style>
    </head>
    <body class="bg-gray-50">
        <!-- Header -->
        <div class="bg-white shadow-sm border-b">
            <div class="max-w-7xl mx-auto px-4 py-3">
                <div class="flex items-center justify-between">
                    <div class="flex items-center space-x-3">
                        <i class="fas fa-bolt text-blue-500 text-2xl"></i>
                        <h1 class="text-xl font-semibold text-gray-900">Lightning OS</h1>
                    </div>
                    <div class="flex items-center space-x-2">
                        <span id="connection-status" class="px-3 py-1 text-sm rounded-full bg-green-100 text-green-700">
                            <i class="fas fa-circle text-xs mr-1"></i> Connected
                        </span>
                    </div>
                </div>
            </div>
        </div>

        <!-- Tab Navigation -->
        <div class="bg-white border-b">
            <div class="max-w-7xl mx-auto px-4">
                <div class="flex space-x-1">
                    <button class="tab-button active px-4 py-3 text-sm font-medium rounded-t-lg transition-colors" onclick="showTab('chat')">
                        <i class="fas fa-comments mr-2"></i>Chat
                    </button>
                    <button class="tab-button px-4 py-3 text-sm font-medium rounded-t-lg transition-colors hover:bg-gray-100" onclick="showTab('context')">
                        <i class="fas fa-folder mr-2"></i>Context Hub
                    </button>
                    <button class="tab-button px-4 py-3 text-sm font-medium rounded-t-lg transition-colors hover:bg-gray-100" onclick="showTab('events')">
                        <i class="fas fa-stream mr-2"></i>Events
                    </button>
                    <button class="tab-button px-4 py-3 text-sm font-medium rounded-t-lg transition-colors hover:bg-gray-100" onclick="showTab('plans')">
                        <i class="fas fa-project-diagram mr-2"></i>Plans
                    </button>
                </div>
            </div>
        </div>

        <!-- Main Content -->
        <div class="max-w-7xl mx-auto px-4 py-6">
            <!-- Chat Tab -->
            <div id="chat-tab" class="tab-content active">
                <div class="bg-white rounded-lg shadow-lg">
                    <div class="p-4 border-b">
                        <h2 class="text-lg font-semibold">AI Assistant</h2>
                        <p class="text-sm text-gray-600">Chat with Lightning's AI to manage your workflows</p>
                    </div>
                    <div id="chat-messages" class="p-4">
                        <div class="message system">
                            Welcome to Lightning! I can help you create plans, manage tasks, and answer questions about your system.
                        </div>
                    </div>
                    <div class="p-4 border-t">
                        <div class="flex space-x-2">
                            <input type="text" id="chat-input" 
                                   class="flex-1 px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                                   placeholder="Type a message..."
                                   onkeypress="if(event.key==='Enter') sendMessage()">
                            <button onclick="sendMessage()" 
                                    class="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors">
                                <i class="fas fa-paper-plane"></i>
                            </button>
                        </div>
                        <div class="mt-2 flex flex-wrap gap-2">
                            <button onclick="quickMessage('Create a new plan')" class="text-xs px-3 py-1 bg-gray-100 rounded-full hover:bg-gray-200">
                                Create a plan
                            </button>
                            <button onclick="quickMessage('Show my active tasks')" class="text-xs px-3 py-1 bg-gray-100 rounded-full hover:bg-gray-200">
                                Active tasks
                            </button>
                            <button onclick="quickMessage('Explain how Lightning works')" class="text-xs px-3 py-1 bg-gray-100 rounded-full hover:bg-gray-200">
                                How it works
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Context Hub Tab -->
            <div id="context-tab" class="tab-content">
                <div class="bg-white rounded-lg shadow-lg">
                    <div class="p-4 border-b flex justify-between items-center">
                        <div>
                            <h2 class="text-lg font-semibold">Context Hub</h2>
                            <p class="text-sm text-gray-600">Your knowledge base and document storage</p>
                        </div>
                        <div class="flex space-x-2">
                            <button onclick="refreshContextHub()" class="px-3 py-1 text-sm bg-gray-100 rounded hover:bg-gray-200">
                                <i class="fas fa-sync-alt mr-1"></i>Refresh
                            </button>
                            <button onclick="createDocument()" class="px-3 py-1 text-sm bg-blue-500 text-white rounded hover:bg-blue-600">
                                <i class="fas fa-plus mr-1"></i>New Document
                            </button>
                        </div>
                    </div>
                    <div class="flex h-96">
                        <div class="w-1/3 border-r p-4 overflow-y-auto">
                            <div id="context-tree" class="space-y-1">
                                <div class="text-center py-8 text-gray-500">
                                    <i class="fas fa-spinner fa-spin text-2xl mb-2"></i>
                                    <p>Loading...</p>
                                </div>
                            </div>
                        </div>
                        <div class="flex-1 p-4">
                            <div id="context-viewer" class="h-full">
                                <div class="text-center py-16 text-gray-400">
                                    <i class="fas fa-file-alt text-4xl mb-2"></i>
                                    <p>Select a document to view</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Events Tab -->
            <div id="events-tab" class="tab-content">
                <div class="bg-white rounded-lg shadow-lg">
                    <div class="p-4 border-b flex justify-between items-center">
                        <div>
                            <h2 class="text-lg font-semibold">Event Stream</h2>
                            <p class="text-sm text-gray-600">Real-time system events</p>
                        </div>
                        <div class="flex space-x-2">
                            <select id="event-filter" onchange="filterEvents()" class="text-sm border rounded px-2 py-1">
                                <option value="all">All Events</option>
                                <option value="input">Input Events</option>
                                <option value="internal">Internal Events</option>
                                <option value="output">Output Events</option>
                            </select>
                            <button onclick="clearEvents()" class="px-3 py-1 text-sm bg-gray-100 rounded hover:bg-gray-200">
                                Clear
                            </button>
                        </div>
                    </div>
                    <div id="events-container" class="p-4 h-96 overflow-y-auto">
                        <div class="space-y-2" id="events-list">
                            <!-- Events will be added here -->
                        </div>
                    </div>
                </div>
            </div>

            <!-- Plans Tab -->
            <div id="plans-tab" class="tab-content">
                <div class="bg-white rounded-lg shadow-lg">
                    <div class="p-4 border-b flex justify-between items-center">
                        <div>
                            <h2 class="text-lg font-semibold">Workflow Plans</h2>
                            <p class="text-sm text-gray-600">Active and available workflow plans</p>
                        </div>
                        <button onclick="createPlan()" class="px-3 py-1 text-sm bg-blue-500 text-white rounded hover:bg-blue-600">
                            <i class="fas fa-plus mr-1"></i>New Plan
                        </button>
                    </div>
                    <div class="p-4">
                        <div id="plans-container" class="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div class="border rounded-lg p-4 hover:shadow-md transition-shadow cursor-pointer">
                                <h3 class="font-semibold mb-2">Email Processing</h3>
                                <p class="text-sm text-gray-600 mb-3">Automatically process incoming emails and trigger actions</p>
                                <div class="flex justify-between items-center">
                                    <span class="text-xs px-2 py-1 bg-green-100 text-green-700 rounded">Active</span>
                                    <button class="text-sm text-blue-500 hover:text-blue-700">Configure</button>
                                </div>
                            </div>
                            <div class="border rounded-lg p-4 hover:shadow-md transition-shadow cursor-pointer">
                                <h3 class="font-semibold mb-2">Daily Summary</h3>
                                <p class="text-sm text-gray-600 mb-3">Generate daily summaries of your activities</p>
                                <div class="flex justify-between items-center">
                                    <span class="text-xs px-2 py-1 bg-gray-100 text-gray-700 rounded">Inactive</span>
                                    <button class="text-sm text-blue-500 hover:text-blue-700">Activate</button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <script>
            // Initialize WebSocket connection
            const sessionId = generateSessionId();
            let ws = null;
            let reconnectTimer = null;
            let eventHistory = [];

            function generateSessionId() {
                return 'session_' + Math.random().toString(36).substr(2, 9);
            }

            function connectWebSocket() {
                ws = new WebSocket(`ws://${window.location.host}/ws/${sessionId}`);
                
                ws.onopen = () => {
                    console.log('WebSocket connected');
                    updateConnectionStatus(true);
                    if (reconnectTimer) {
                        clearTimeout(reconnectTimer);
                        reconnectTimer = null;
                    }
                };

                ws.onmessage = (event) => {
                    const data = JSON.parse(event.data);
                    handleWebSocketMessage(data);
                };

                ws.onerror = (error) => {
                    console.error('WebSocket error:', error);
                    updateConnectionStatus(false);
                };

                ws.onclose = () => {
                    console.log('WebSocket disconnected');
                    updateConnectionStatus(false);
                    // Attempt to reconnect after 3 seconds
                    reconnectTimer = setTimeout(connectWebSocket, 3000);
                };
            }

            function updateConnectionStatus(connected) {
                const status = document.getElementById('connection-status');
                if (connected) {
                    status.className = 'px-3 py-1 text-sm rounded-full bg-green-100 text-green-700';
                    status.innerHTML = '<i class="fas fa-circle text-xs mr-1"></i> Connected';
                } else {
                    status.className = 'px-3 py-1 text-sm rounded-full bg-red-100 text-red-700';
                    status.innerHTML = '<i class="fas fa-circle text-xs mr-1"></i> Disconnected';
                }
            }

            function handleWebSocketMessage(data) {
                if (data.type === 'chat') {
                    addChatMessage(data.message, data.role || 'assistant');
                } else if (data.type === 'event') {
                    addEvent(data.event);
                } else if (data.type === 'context_update') {
                    refreshContextHub();
                }
            }

            function showTab(tabName) {
                // Hide all tabs
                document.querySelectorAll('.tab-content').forEach(tab => {
                    tab.classList.remove('active');
                });
                document.querySelectorAll('.tab-button').forEach(btn => {
                    btn.classList.remove('active');
                });

                // Show selected tab
                document.getElementById(`${tabName}-tab`).classList.add('active');
                event.target.classList.add('active');

                // Load tab-specific data
                if (tabName === 'context') {
                    refreshContextHub();
                } else if (tabName === 'events') {
                    loadRecentEvents();
                }
            }

            // Chat functions
            function sendMessage() {
                const input = document.getElementById('chat-input');
                const message = input.value.trim();
                
                if (!message) return;
                
                addChatMessage(message, 'user');
                
                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({
                        type: 'chat',
                        message: message,
                        session_id: sessionId
                    }));
                } else {
                    addChatMessage('Connection lost. Please wait while we reconnect...', 'system');
                }
                
                input.value = '';
            }

            function addChatMessage(text, role) {
                const messagesDiv = document.getElementById('chat-messages');
                const messageDiv = document.createElement('div');
                messageDiv.className = `message ${role}`;
                messageDiv.textContent = text;
                messagesDiv.appendChild(messageDiv);
                messagesDiv.scrollTop = messagesDiv.scrollHeight;
            }

            function quickMessage(text) {
                document.getElementById('chat-input').value = text;
                sendMessage();
            }

            // Context Hub functions
            async function refreshContextHub() {
                try {
                    const response = await fetch('/api/context/tree');
                    if (response.ok) {
                        const data = await response.json();
                        renderContextTree(data);
                    }
                } catch (error) {
                    console.error('Error loading context hub:', error);
                }
            }

            function renderContextTree(data) {
                const treeDiv = document.getElementById('context-tree');
                treeDiv.innerHTML = renderFolder(data.folders || [], data.documents || [], 0);
            }

            function renderFolder(folders, documents, level) {
                let html = '';
                
                folders.forEach(folder => {
                    html += `
                        <div class="context-item context-folder pl-${level * 4}" onclick="toggleFolder('${folder.id}')">
                            <i class="fas fa-folder mr-2 text-yellow-500"></i>
                            ${folder.name}
                        </div>
                        <div id="folder-${folder.id}" class="folder-contents">
                            ${renderFolder(folder.folders || [], folder.documents || [], level + 1)}
                        </div>
                    `;
                });
                
                documents.forEach(doc => {
                    html += `
                        <div class="context-item pl-${level * 4} py-1" onclick="viewDocument('${doc.id}')">
                            <i class="fas fa-file-alt mr-2 text-gray-400"></i>
                            ${doc.name}
                        </div>
                    `;
                });
                
                return html;
            }

            async function viewDocument(docId) {
                try {
                    const response = await fetch(`/api/context/documents/${docId}`);
                    if (response.ok) {
                        const doc = await response.json();
                        const viewer = document.getElementById('context-viewer');
                        viewer.innerHTML = `
                            <div class="h-full flex flex-col">
                                <h3 class="font-semibold text-lg mb-2">${doc.name}</h3>
                                <div class="flex-1 bg-gray-50 rounded p-4 overflow-y-auto">
                                    <pre class="whitespace-pre-wrap">${doc.content}</pre>
                                </div>
                            </div>
                        `;
                    }
                } catch (error) {
                    console.error('Error loading document:', error);
                }
            }

            // Event functions
            async function loadRecentEvents() {
                try {
                    const response = await fetch('/api/events/recent');
                    if (response.ok) {
                        const events = await response.json();
                        eventHistory = events;
                        renderEvents();
                    }
                } catch (error) {
                    console.error('Error loading events:', error);
                }
            }

            function addEvent(event) {
                eventHistory.unshift(event);
                if (eventHistory.length > 100) {
                    eventHistory.pop();
                }
                renderEvents();
            }

            function renderEvents() {
                const filter = document.getElementById('event-filter').value;
                const container = document.getElementById('events-list');
                
                let filtered = eventHistory;
                if (filter !== 'all') {
                    filtered = eventHistory.filter(e => e.type.startsWith(filter));
                }
                
                container.innerHTML = filtered.map(event => `
                    <div class="event-item ${event.type.split('.')[0]} bg-gray-50 rounded p-3">
                        <div class="flex justify-between items-start">
                            <div>
                                <span class="font-medium text-sm">${event.type}</span>
                                <p class="text-xs text-gray-600 mt-1">${JSON.stringify(event.metadata || {})}</p>
                            </div>
                            <span class="text-xs text-gray-500">${new Date(event.timestamp).toLocaleTimeString()}</span>
                        </div>
                    </div>
                `).join('');
            }

            function filterEvents() {
                renderEvents();
            }

            function clearEvents() {
                eventHistory = [];
                renderEvents();
            }

            // Initialize on load
            document.addEventListener('DOMContentLoaded', () => {
                connectWebSocket();
                document.getElementById('chat-input').focus();
            });
        </script>
    </body>
    </html>
    """

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """WebSocket endpoint for real-time communication"""
    await manager.connect(websocket, client_id)
    
    try:
        while True:
            data = await websocket.receive_json()
            
            if data.get("type") == "chat":
                message = data.get("message", "")
                
                # Add to chat history
                manager.add_to_history(client_id, {"role": "user", "content": message})
                
                # Send acknowledgment
                await manager.send_message({
                    "type": "chat",
                    "role": "assistant",
                    "message": "I'm processing your request..."
                }, client_id)
                
                # Create event for processing
                async with aiohttp.ClientSession() as session:
                    event_data = {
                        "timestamp": datetime.utcnow().isoformat(),
                        "source": "lightning_ui",
                        "type": "input.user.chat",
                        "metadata": {
                            "message": message,
                            "session_id": client_id,
                            "chat_history": manager.get_history(client_id)
                        }
                    }
                    
                    try:
                        async with session.post(f"{API_BASE}/events", json=event_data) as response:
                            if response.status == 200:
                                await manager.send_message({
                                    "type": "chat",
                                    "role": "assistant",
                                    "message": f"I've received your message: '{message}'. The Lightning system is processing it now."
                                }, client_id)
                            else:
                                await manager.send_message({
                                    "type": "chat",
                                    "role": "system",
                                    "message": "Error: Could not process your message. Please try again."
                                }, client_id)
                    except Exception as e:
                        logger.error(f"Error sending event: {e}")
                        await manager.send_message({
                            "type": "chat",
                            "role": "system",
                            "message": "Connection error. Please check if the Lightning API is running."
                        }, client_id)
                        
    except WebSocketDisconnect:
        manager.disconnect(client_id)
        logger.info(f"Client {client_id} disconnected")

@app.get("/api/context/tree")
async def get_context_tree():
    """Get the context hub folder structure"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{CONTEXT_HUB_URL}/api/folders") as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {"folders": [], "documents": []}
    except Exception as e:
        logger.error(f"Error fetching context tree: {e}")
        return {"folders": [], "documents": []}

@app.get("/api/context/documents/{doc_id}")
async def get_document(doc_id: str):
    """Get a specific document from context hub"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{CONTEXT_HUB_URL}/api/documents/{doc_id}") as response:
                if response.status == 200:
                    return await response.json()
                else:
                    raise HTTPException(status_code=404, detail="Document not found")
    except Exception as e:
        logger.error(f"Error fetching document: {e}")
        raise HTTPException(status_code=500, detail="Error fetching document")

@app.get("/api/events/recent")
async def get_recent_events():
    """Get recent events from the system"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_BASE}/events?limit=50") as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return []
    except Exception as e:
        logger.error(f"Error fetching events: {e}")
        return []

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "service": "lightning-ui", "timestamp": datetime.utcnow().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)