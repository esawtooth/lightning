#!/usr/bin/env python3
"""
Lightning OS - Simple HTTP Demo

A minimal demo using only Python standard library.
"""

import http.server
import socketserver
import json
import sqlite3
from datetime import datetime
from pathlib import Path
import uuid

# Initialize SQLite
db_path = Path("./demo_lightning.db")
conn = sqlite3.connect(str(db_path))
conn.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id TEXT PRIMARY KEY,
        type TEXT,
        data TEXT,
        timestamp TEXT
    )
""")
conn.commit()
conn.close()

# In-memory stores
events = []
tasks = []

# HTML Interface
HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Lightning OS - Local Demo</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        h1 {
            color: #333;
            text-align: center;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .status {
            background: white;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 20px;
            text-align: center;
        }
        .grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }
        .panel {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        button {
            background: #667eea;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 4px;
            cursor: pointer;
        }
        button:hover {
            background: #5a67d8;
        }
        input, textarea {
            width: 100%;
            padding: 8px;
            margin: 5px 0;
            border: 1px solid #ddd;
            border-radius: 4px;
            box-sizing: border-box;
        }
        .list {
            max-height: 300px;
            overflow-y: auto;
            border: 1px solid #eee;
            padding: 10px;
            margin-top: 10px;
        }
        .item {
            padding: 8px;
            margin: 5px 0;
            background: #f8f9fa;
            border-radius: 4px;
            border-left: 3px solid #667eea;
        }
        .success { color: green; }
        .info { color: #666; font-size: 14px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚡ Lightning OS - Local Demo</h1>
        
        <div class="status">
            <p class="success">✓ System Running Locally</p>
            <p class="info">Storage: SQLite | Events: In-Memory | Port: 8080</p>
        </div>
        
        <div class="grid">
            <div class="panel">
                <h2>Submit Event</h2>
                <input type="text" id="eventType" placeholder="Event Type (e.g., user.action)" value="user.action">
                <input type="text" id="userId" placeholder="User ID" value="demo-user">
                <textarea id="eventData" placeholder="Event Data (JSON)" rows="3">{"action": "test"}</textarea>
                <button onclick="submitEvent()">Submit Event</button>
                
                <h3>Recent Events</h3>
                <div id="eventsList" class="list">Loading...</div>
            </div>
            
            <div class="panel">
                <h2>Create Task</h2>
                <input type="text" id="taskTitle" placeholder="Task Title">
                <textarea id="taskDesc" placeholder="Task Description" rows="3"></textarea>
                <button onclick="createTask()">Create Task</button>
                
                <h3>Tasks</h3>
                <div id="tasksList" class="list">Loading...</div>
            </div>
        </div>
        
        <div class="panel" style="margin-top: 20px;">
            <h2>System Demonstration</h2>
            <p>This demo shows Lightning OS running <strong>completely locally</strong>:</p>
            <ul>
                <li>✓ No cloud dependencies</li>
                <li>✓ SQLite for storage (see demo_lightning.db)</li>
                <li>✓ In-memory event processing</li>
                <li>✓ Same abstraction layer as cloud deployment</li>
            </ul>
            <p>In production, this would use:</p>
            <ul>
                <li>Azure Cosmos DB instead of SQLite</li>
                <li>Azure Service Bus instead of in-memory events</li>
                <li>Azure Functions instead of local processing</li>
            </ul>
            <button onclick="window.location.reload()">Refresh Page</button>
        </div>
    </div>
    
    <script>
        async function submitEvent() {
            const type = document.getElementById('eventType').value;
            const userId = document.getElementById('userId').value;
            const dataStr = document.getElementById('eventData').value;
            
            try {
                const data = JSON.parse(dataStr);
                const response = await fetch('/api/event', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({type, userId, data})
                });
                
                if (response.ok) {
                    alert('Event submitted!');
                    loadEvents();
                }
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }
        
        async function createTask() {
            const title = document.getElementById('taskTitle').value;
            const description = document.getElementById('taskDesc').value;
            
            const response = await fetch('/api/task', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({title, description})
            });
            
            if (response.ok) {
                alert('Task created!');
                document.getElementById('taskTitle').value = '';
                document.getElementById('taskDesc').value = '';
                loadTasks();
            }
        }
        
        async function loadEvents() {
            const response = await fetch('/api/events');
            const data = await response.json();
            const list = document.getElementById('eventsList');
            
            if (data.events.length === 0) {
                list.innerHTML = '<em>No events yet</em>';
            } else {
                list.innerHTML = data.events.slice(-5).reverse().map(e => 
                    '<div class="item"><strong>' + e.type + '</strong><br>' + 
                    '<small>' + e.timestamp + '</small></div>'
                ).join('');
            }
        }
        
        async function loadTasks() {
            const response = await fetch('/api/tasks');
            const data = await response.json();
            const list = document.getElementById('tasksList');
            
            if (data.tasks.length === 0) {
                list.innerHTML = '<em>No tasks yet</em>';
            } else {
                list.innerHTML = data.tasks.map(t => 
                    '<div class="item"><strong>' + t.title + '</strong><br>' + 
                    '<small>' + t.description + '</small></div>'
                ).join('');
            }
        }
        
        // Load data on startup
        loadEvents();
        loadTasks();
        
        // Auto-refresh
        setInterval(() => {
            loadEvents();
            loadTasks();
        }, 5000);
    </script>
</body>
</html>
"""

class RequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(HTML.encode())
        elif self.path == '/api/events':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"events": events}).encode())
        elif self.path == '/api/tasks':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"tasks": tasks}).encode())
        else:
            self.send_error(404)
    
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        data = json.loads(post_data.decode())
        
        if self.path == '/api/event':
            event = {
                "id": str(uuid.uuid4()),
                "type": data.get("type", "unknown"),
                "userId": data.get("userId", "system"),
                "data": data.get("data", {}),
                "timestamp": datetime.now().isoformat()
            }
            events.append(event)
            
            # Store in SQLite
            conn = sqlite3.connect(str(db_path))
            conn.execute(
                "INSERT INTO events (id, type, data, timestamp) VALUES (?, ?, ?, ?)",
                (event["id"], event["type"], json.dumps(event["data"]), event["timestamp"])
            )
            conn.commit()
            conn.close()
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode())
            
        elif self.path == '/api/task':
            task = {
                "id": str(uuid.uuid4()),
                "title": data.get("title", ""),
                "description": data.get("description", ""),
                "status": "pending",
                "createdAt": datetime.now().isoformat()
            }
            tasks.append(task)
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode())
    
    def log_message(self, format, *args):
        # Suppress request logs
        pass

if __name__ == "__main__":
    PORT = 8080
    print("\n╔════════════════════════════════════════════════════════╗")
    print("║          Lightning OS - Local Demo Server              ║")
    print("╚════════════════════════════════════════════════════════╝\n")
    print(f"Starting server on port {PORT}...")
    print(f"\n✨ Open your browser to: http://localhost:{PORT}\n")
    print("Press Ctrl+C to stop the server\n")
    
    with socketserver.TCPServer(("", PORT), RequestHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\nServer stopped.")
            if db_path.exists():
                db_path.unlink()  # Clean up database