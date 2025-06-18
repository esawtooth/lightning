#!/usr/bin/env python3
"""
Lightning OS - Quick Local Demo Server

A standalone demo that runs the Lightning OS locally with a web UI.
No Docker or external dependencies required (except FastAPI).
"""

import asyncio
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import uuid
import logging

# Try to import FastAPI, provide instructions if not available
try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse, JSONResponse
    import uvicorn
except ImportError:
    print("FastAPI not installed. Please run:")
    print("pip install fastapi uvicorn")
    exit(1)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="Lightning OS - Local Demo")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage
events_store = []
tasks_store = []
plans_store = []
functions_store = {}

# Simple event bus
event_handlers = {}
event_queue = asyncio.Queue()

# Initialize SQLite for persistent storage
db_path = Path("./demo_lightning.db")
conn = sqlite3.connect(str(db_path))
conn.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        type TEXT,
        data TEXT,
        created_at TEXT,
        updated_at TEXT
    )
""")
conn.commit()
conn.close()


# HTML UI
HTML_UI = """
<!DOCTYPE html>
<html>
<head>
    <title>Lightning OS - Local Demo</title>
    <style>
        * { box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 0;
            background: #f0f2f5;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            text-align: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .header h1 { margin: 0; font-size: 2em; }
        .header p { margin: 5px 0 0 0; opacity: 0.9; }
        .container {
            max-width: 1200px;
            margin: 20px auto;
            padding: 0 20px;
        }
        .status-bar {
            background: white;
            padding: 15px 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .status { display: flex; gap: 20px; }
        .status-item { display: flex; align-items: center; gap: 5px; }
        .status-light {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #10b981;
        }
        .grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }
        .panel {
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            padding: 20px;
        }
        .panel h2 {
            margin: 0 0 15px 0;
            color: #1f2937;
            font-size: 1.3em;
        }
        .form-group {
            margin-bottom: 15px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            color: #4b5563;
            font-weight: 500;
        }
        input, textarea, select {
            width: 100%;
            padding: 8px 12px;
            border: 1px solid #d1d5db;
            border-radius: 6px;
            font-size: 14px;
        }
        button {
            background: #667eea;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 6px;
            font-weight: 500;
            cursor: pointer;
            transition: background 0.2s;
        }
        button:hover { background: #5a67d8; }
        button:active { transform: translateY(1px); }
        .items-list {
            max-height: 300px;
            overflow-y: auto;
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            padding: 10px;
        }
        .item {
            padding: 10px;
            margin-bottom: 8px;
            background: #f9fafb;
            border-radius: 4px;
            border-left: 3px solid #667eea;
        }
        .item-header {
            font-weight: 600;
            color: #1f2937;
            margin-bottom: 4px;
        }
        .item-meta {
            font-size: 12px;
            color: #6b7280;
        }
        .item-data {
            font-size: 13px;
            color: #4b5563;
            margin-top: 4px;
        }
        .tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            border-bottom: 2px solid #e5e7eb;
        }
        .tab {
            padding: 10px 20px;
            cursor: pointer;
            border-bottom: 2px solid transparent;
            transition: all 0.2s;
        }
        .tab.active {
            color: #667eea;
            border-bottom-color: #667eea;
        }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .console {
            background: #1f2937;
            color: #10b981;
            padding: 15px;
            border-radius: 6px;
            font-family: 'Courier New', monospace;
            font-size: 13px;
            max-height: 200px;
            overflow-y: auto;
        }
        .console-line { margin: 2px 0; }
        .badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
        }
        .badge.high { background: #fee2e2; color: #dc2626; }
        .badge.medium { background: #fef3c7; color: #d97706; }
        .badge.low { background: #dbeafe; color: #2563eb; }
    </style>
</head>
<body>
    <div class="header">
        <h1>⚡ Lightning OS</h1>
        <p>Local Development Environment</p>
    </div>
    
    <div class="container">
        <div class="status-bar">
            <div class="status">
                <div class="status-item">
                    <div class="status-light"></div>
                    <span>System: <strong>Running</strong></span>
                </div>
                <div class="status-item">
                    <div class="status-light"></div>
                    <span>Mode: <strong>Local</strong></span>
                </div>
                <div class="status-item">
                    <div class="status-light"></div>
                    <span>Storage: <strong>SQLite</strong></span>
                </div>
            </div>
            <div>
                <button onclick="refreshAll()">🔄 Refresh</button>
            </div>
        </div>
        
        <div class="tabs">
            <div class="tab active" onclick="switchTab('events')">Events</div>
            <div class="tab" onclick="switchTab('tasks')">Tasks</div>
            <div class="tab" onclick="switchTab('plans')">Plans</div>
            <div class="tab" onclick="switchTab('functions')">Functions</div>
            <div class="tab" onclick="switchTab('console')">Console</div>
        </div>
        
        <!-- Events Tab -->
        <div id="events-tab" class="tab-content active">
            <div class="grid">
                <div class="panel">
                    <h2>📤 Submit Event</h2>
                    <div class="form-group">
                        <label>Event Type</label>
                        <input type="text" id="event-type" placeholder="e.g., user.action" value="user.action">
                    </div>
                    <div class="form-group">
                        <label>User ID</label>
                        <input type="text" id="user-id" placeholder="User ID" value="demo-user">
                    </div>
                    <div class="form-group">
                        <label>Event Data (JSON)</label>
                        <textarea id="event-data" rows="4">{"action": "test", "timestamp": "now"}</textarea>
                    </div>
                    <button onclick="submitEvent()">Submit Event</button>
                </div>
                <div class="panel">
                    <h2>📥 Recent Events</h2>
                    <div id="events-list" class="items-list">
                        <div style="color: #9ca3af; text-align: center;">No events yet</div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Tasks Tab -->
        <div id="tasks-tab" class="tab-content">
            <div class="grid">
                <div class="panel">
                    <h2>➕ Create Task</h2>
                    <div class="form-group">
                        <label>Title</label>
                        <input type="text" id="task-title" placeholder="Task title">
                    </div>
                    <div class="form-group">
                        <label>Description</label>
                        <textarea id="task-description" rows="3" placeholder="Task description"></textarea>
                    </div>
                    <div class="form-group">
                        <label>Priority</label>
                        <select id="task-priority">
                            <option value="low">Low</option>
                            <option value="medium" selected>Medium</option>
                            <option value="high">High</option>
                        </select>
                    </div>
                    <button onclick="createTask()">Create Task</button>
                </div>
                <div class="panel">
                    <h2>📋 Tasks</h2>
                    <div id="tasks-list" class="items-list">
                        <div style="color: #9ca3af; text-align: center;">No tasks yet</div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Plans Tab -->
        <div id="plans-tab" class="tab-content">
            <div class="grid">
                <div class="panel">
                    <h2>🎯 Create Plan</h2>
                    <div class="form-group">
                        <label>Plan Description</label>
                        <textarea id="plan-description" rows="4" placeholder="Describe what you want to accomplish..."></textarea>
                    </div>
                    <div class="form-group">
                        <label>Type</label>
                        <select id="plan-type">
                            <option value="acyclic">One-time (Acyclic)</option>
                            <option value="reactive">Continuous (Reactive)</option>
                        </select>
                    </div>
                    <button onclick="createPlan()">Create Plan</button>
                </div>
                <div class="panel">
                    <h2>📊 Plans</h2>
                    <div id="plans-list" class="items-list">
                        <div style="color: #9ca3af; text-align: center;">No plans yet</div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Functions Tab -->
        <div id="functions-tab" class="tab-content">
            <div class="grid">
                <div class="panel">
                    <h2>⚡ Deploy Function</h2>
                    <div class="form-group">
                        <label>Function Name</label>
                        <input type="text" id="func-name" placeholder="my-function">
                    </div>
                    <div class="form-group">
                        <label>Handler Code</label>
                        <textarea id="func-code" rows="6">async function handler(event) {
    return {
        status: 'success',
        message: 'Function executed',
        input: event
    };
}</textarea>
                    </div>
                    <button onclick="deployFunction()">Deploy Function</button>
                </div>
                <div class="panel">
                    <h2>🔧 Deployed Functions</h2>
                    <div id="functions-list" class="items-list">
                        <div style="color: #9ca3af; text-align: center;">No functions deployed</div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Console Tab -->
        <div id="console-tab" class="tab-content">
            <div class="panel">
                <h2>🖥️ System Console</h2>
                <div id="console" class="console">
                    <div class="console-line">Lightning OS Local Demo Started...</div>
                    <div class="console-line">Storage: SQLite (./demo_lightning.db)</div>
                    <div class="console-line">Event Bus: In-Memory</div>
                    <div class="console-line">Ready for connections.</div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        const API_URL = '';
        
        function log(message) {
            const console = document.getElementById('console');
            const line = document.createElement('div');
            line.className = 'console-line';
            line.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
            console.appendChild(line);
            console.scrollTop = console.scrollHeight;
        }
        
        function switchTab(tab) {
            // Hide all tabs
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            
            // Show selected tab
            document.getElementById(`${tab}-tab`).classList.add('active');
            event.target.classList.add('active');
        }
        
        async function submitEvent() {
            const type = document.getElementById('event-type').value;
            const userID = document.getElementById('user-id').value;
            const dataStr = document.getElementById('event-data').value;
            
            try {
                const data = JSON.parse(dataStr);
                const response = await fetch('/api/events', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ type, userID, data })
                });
                
                if (response.ok) {
                    log(`Event submitted: ${type}`);
                    loadEvents();
                }
            } catch (error) {
                log(`Error: ${error.message}`);
            }
        }
        
        async function createTask() {
            const title = document.getElementById('task-title').value;
            const description = document.getElementById('task-description').value;
            const priority = document.getElementById('task-priority').value;
            
            try {
                const response = await fetch('/api/tasks', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ title, description, priority })
                });
                
                if (response.ok) {
                    log(`Task created: ${title}`);
                    document.getElementById('task-title').value = '';
                    document.getElementById('task-description').value = '';
                    loadTasks();
                }
            } catch (error) {
                log(`Error: ${error.message}`);
            }
        }
        
        async function createPlan() {
            const description = document.getElementById('plan-description').value;
            const type = document.getElementById('plan-type').value;
            
            try {
                const response = await fetch('/api/plans', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ description, type })
                });
                
                if (response.ok) {
                    log(`Plan created: ${type} plan`);
                    document.getElementById('plan-description').value = '';
                    loadPlans();
                }
            } catch (error) {
                log(`Error: ${error.message}`);
            }
        }
        
        async function deployFunction() {
            const name = document.getElementById('func-name').value;
            const code = document.getElementById('func-code').value;
            
            try {
                const response = await fetch('/api/functions', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ name, code })
                });
                
                if (response.ok) {
                    log(`Function deployed: ${name}`);
                    document.getElementById('func-name').value = '';
                    loadFunctions();
                }
            } catch (error) {
                log(`Error: ${error.message}`);
            }
        }
        
        async function loadEvents() {
            const response = await fetch('/api/events');
            const data = await response.json();
            const list = document.getElementById('events-list');
            
            if (data.events.length === 0) {
                list.innerHTML = '<div style="color: #9ca3af; text-align: center;">No events yet</div>';
            } else {
                list.innerHTML = data.events.map(event => `
                    <div class="item">
                        <div class="item-header">${event.type}</div>
                        <div class="item-meta">User: ${event.userID} | ${new Date(event.timestamp).toLocaleString()}</div>
                        <div class="item-data">${JSON.stringify(event.data)}</div>
                    </div>
                `).join('');
            }
        }
        
        async function loadTasks() {
            const response = await fetch('/api/tasks');
            const data = await response.json();
            const list = document.getElementById('tasks-list');
            
            if (data.tasks.length === 0) {
                list.innerHTML = '<div style="color: #9ca3af; text-align: center;">No tasks yet</div>';
            } else {
                list.innerHTML = data.tasks.map(task => `
                    <div class="item">
                        <div class="item-header">${task.title} <span class="badge ${task.priority}">${task.priority}</span></div>
                        <div class="item-meta">Status: ${task.status} | ${new Date(task.createdAt).toLocaleString()}</div>
                        <div class="item-data">${task.description}</div>
                    </div>
                `).join('');
            }
        }
        
        async function loadPlans() {
            const response = await fetch('/api/plans');
            const data = await response.json();
            const list = document.getElementById('plans-list');
            
            if (data.plans.length === 0) {
                list.innerHTML = '<div style="color: #9ca3af; text-align: center;">No plans yet</div>';
            } else {
                list.innerHTML = data.plans.map(plan => `
                    <div class="item">
                        <div class="item-header">Plan ${plan.id}</div>
                        <div class="item-meta">Type: ${plan.type} | Status: ${plan.status}</div>
                        <div class="item-data">${plan.description}</div>
                    </div>
                `).join('');
            }
        }
        
        async function loadFunctions() {
            const response = await fetch('/api/functions');
            const data = await response.json();
            const list = document.getElementById('functions-list');
            
            if (data.functions.length === 0) {
                list.innerHTML = '<div style="color: #9ca3af; text-align: center;">No functions deployed</div>';
            } else {
                list.innerHTML = data.functions.map(func => `
                    <div class="item">
                        <div class="item-header">${func.name}</div>
                        <div class="item-meta">ID: ${func.id} | Invocations: ${func.invocations}</div>
                        <button onclick="invokeFunction('${func.id}')">Invoke</button>
                    </div>
                `).join('');
            }
        }
        
        async function invokeFunction(funcId) {
            try {
                const response = await fetch(`/api/functions/${funcId}/invoke`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ test: true })
                });
                
                const result = await response.json();
                log(`Function result: ${JSON.stringify(result)}`);
            } catch (error) {
                log(`Error: ${error.message}`);
            }
        }
        
        function refreshAll() {
            log('Refreshing all data...');
            loadEvents();
            loadTasks();
            loadPlans();
            loadFunctions();
        }
        
        // Initial load
        refreshAll();
        
        // Auto-refresh every 5 seconds
        setInterval(refreshAll, 5000);
    </script>
</body>
</html>
"""

# API Routes

@app.get("/", response_class=HTMLResponse)
async def home():
    """Serve the web UI."""
    return HTML_UI

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "mode": "local",
        "services": {
            "storage": "SQLite",
            "event_bus": "In-Memory",
            "api": "Running"
        }
    }

@app.post("/api/events")
async def submit_event(request: Dict[str, Any]):
    """Submit an event."""
    event = {
        "id": str(uuid.uuid4()),
        "type": request.get("type", "unknown"),
        "userID": request.get("userID", "system"),
        "data": request.get("data", {}),
        "timestamp": datetime.utcnow().isoformat()
    }
    events_store.append(event)
    
    # Process event (simplified)
    await event_queue.put(event)
    
    logger.info(f"Event submitted: {event['type']}")
    return {"success": True, "event_id": event["id"]}

@app.get("/api/events")
async def get_events():
    """Get recent events."""
    return {"events": events_store[-20:], "total": len(events_store)}

@app.post("/api/tasks")
async def create_task(request: Dict[str, Any]):
    """Create a task."""
    task = {
        "id": str(uuid.uuid4()),
        "title": request.get("title", ""),
        "description": request.get("description", ""),
        "priority": request.get("priority", "medium"),
        "status": "pending",
        "createdAt": datetime.utcnow().isoformat()
    }
    tasks_store.append(task)
    
    # Store in SQLite
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO documents (id, type, data, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (task["id"], "task", json.dumps(task), task["createdAt"], task["createdAt"])
    )
    conn.commit()
    conn.close()
    
    logger.info(f"Task created: {task['title']}")
    return {"success": True, "task": task}

@app.get("/api/tasks")
async def get_tasks():
    """Get all tasks."""
    return {"tasks": tasks_store, "total": len(tasks_store)}

@app.post("/api/plans")
async def create_plan(request: Dict[str, Any]):
    """Create a plan."""
    plan = {
        "id": str(uuid.uuid4()),
        "description": request.get("description", ""),
        "type": request.get("type", "acyclic"),
        "status": "draft",
        "createdAt": datetime.utcnow().isoformat()
    }
    plans_store.append(plan)
    
    logger.info(f"Plan created: {plan['type']}")
    return {"success": True, "plan": plan}

@app.get("/api/plans")
async def get_plans():
    """Get all plans."""
    return {"plans": plans_store, "total": len(plans_store)}

@app.post("/api/functions")
async def deploy_function(request: Dict[str, Any]):
    """Deploy a function."""
    func_id = str(uuid.uuid4())
    function = {
        "id": func_id,
        "name": request.get("name", ""),
        "code": request.get("code", ""),
        "invocations": 0,
        "createdAt": datetime.utcnow().isoformat()
    }
    functions_store[func_id] = function
    
    logger.info(f"Function deployed: {function['name']}")
    return {"success": True, "function_id": func_id}

@app.get("/api/functions")
async def get_functions():
    """Get all functions."""
    return {
        "functions": list(functions_store.values()),
        "total": len(functions_store)
    }

@app.post("/api/functions/{func_id}/invoke")
async def invoke_function(func_id: str, request: Dict[str, Any]):
    """Invoke a function."""
    if func_id not in functions_store:
        raise HTTPException(status_code=404, detail="Function not found")
    
    function = functions_store[func_id]
    function["invocations"] += 1
    
    # Simulate function execution
    result = {
        "status": "success",
        "function_id": func_id,
        "result": {
            "message": f"Function {function['name']} executed",
            "input": request,
            "timestamp": datetime.utcnow().isoformat()
        }
    }
    
    logger.info(f"Function invoked: {function['name']}")
    return result

# Event processor (runs in background)
async def process_events():
    """Background event processor."""
    while True:
        try:
            event = await event_queue.get()
            logger.info(f"Processing event: {event['type']}")
            # Simulate event processing
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Error processing event: {e}")

# Startup event
@app.on_event("startup")
async def startup():
    """Start background tasks."""
    asyncio.create_task(process_events())
    logger.info("Lightning OS Local Demo started")
    logger.info("Access the UI at http://localhost:8080")

if __name__ == "__main__":
    print("\n╔════════════════════════════════════════════════════════╗")
    print("║          Lightning OS - Local Demo Server              ║")
    print("╚════════════════════════════════════════════════════════╝\n")
    print("Starting server...")
    print("\n✨ Access the UI at: http://localhost:8080\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8080)