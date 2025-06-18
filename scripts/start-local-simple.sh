#!/bin/bash
#
# Start Lightning OS locally with individual Docker containers
# (Alternative to Docker Compose)
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Create network
create_network() {
    if ! docker network inspect lightning-network >/dev/null 2>&1; then
        print_info "Creating Docker network..."
        docker network create lightning-network
    else
        print_info "Docker network already exists"
    fi
}

# Start PostgreSQL
start_postgres() {
    if docker ps -a | grep -q lightning-postgres; then
        print_info "Removing existing PostgreSQL container..."
        docker rm -f lightning-postgres
    fi
    
    print_info "Starting PostgreSQL..."
    docker run -d \
        --name lightning-postgres \
        --network lightning-network \
        -e POSTGRES_USER=lightning \
        -e POSTGRES_PASSWORD=lightning123 \
        -e POSTGRES_DB=lightning_db \
        -p 5432:5432 \
        postgres:15-alpine
    
    print_info "Waiting for PostgreSQL to be ready..."
    sleep 5
}

# Start Redis
start_redis() {
    if docker ps -a | grep -q lightning-redis; then
        print_info "Removing existing Redis container..."
        docker rm -f lightning-redis
    fi
    
    print_info "Starting Redis..."
    docker run -d \
        --name lightning-redis \
        --network lightning-network \
        -p 6379:6379 \
        redis:7-alpine
}

# Create simple API server
create_simple_api() {
    print_info "Creating simple API server..."
    
    # Create a simple Python API server
    mkdir -p /tmp/lightning-demo
    cat > /tmp/lightning-demo/app.py << 'EOF'
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import os
import json

app = FastAPI(title="Lightning OS Local Demo")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class EventRequest(BaseModel):
    type: str
    userID: str
    data: dict = {}

class TaskRequest(BaseModel):
    title: str
    description: str = ""
    priority: str = "medium"

# In-memory storage
events = []
tasks = []

@app.get("/")
def root():
    return {
        "service": "Lightning OS API (Demo)",
        "version": "1.0.0",
        "mode": "local",
        "endpoints": {
            "health": "/health",
            "events": "/api/events",
            "tasks": "/api/tasks"
        }
    }

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "api": "healthy",
            "mode": "demo"
        }
    }

@app.post("/api/events")
def submit_event(event: EventRequest):
    event_data = {
        "id": f"evt-{len(events) + 1}",
        "timestamp": datetime.utcnow().isoformat(),
        **event.dict()
    }
    events.append(event_data)
    return {
        "success": True,
        "event_id": event_data["id"],
        "message": f"Event {event.type} submitted"
    }

@app.get("/api/events")
def get_events():
    return {"events": events[-10:], "total": len(events)}

@app.post("/api/tasks")
def create_task(task: TaskRequest):
    task_data = {
        "id": f"task-{len(tasks) + 1}",
        "createdAt": datetime.utcnow().isoformat(),
        "status": "pending",
        **task.dict()
    }
    tasks.append(task_data)
    return {"success": True, "task": task_data}

@app.get("/api/tasks")
def get_tasks():
    return {"tasks": tasks, "total": len(tasks)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
EOF

    # Create requirements.txt
    cat > /tmp/lightning-demo/requirements.txt << 'EOF'
fastapi==0.104.1
uvicorn==0.24.0
pydantic==2.5.0
EOF

    # Create Dockerfile
    cat > /tmp/lightning-demo/Dockerfile << 'EOF'
FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app.py .
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
EOF
}

# Build and run API
start_api() {
    create_simple_api
    
    if docker ps -a | grep -q lightning-api; then
        print_info "Removing existing API container..."
        docker rm -f lightning-api
    fi
    
    print_info "Building API container..."
    docker build -t lightning-api-demo /tmp/lightning-demo
    
    print_info "Starting API server..."
    docker run -d \
        --name lightning-api \
        --network lightning-network \
        -p 8000:8000 \
        -e LIGHTNING_MODE=local \
        lightning-api-demo
}

# Create simple UI
create_simple_ui() {
    print_info "Creating simple UI..."
    
    mkdir -p /tmp/lightning-ui
    cat > /tmp/lightning-ui/index.html << 'EOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Lightning OS - Local Demo</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        h1 {
            color: #333;
            text-align: center;
        }
        .status {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 20px;
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
            background: #007bff;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 4px;
            cursor: pointer;
        }
        button:hover {
            background: #0056b3;
        }
        input, textarea {
            width: 100%;
            padding: 8px;
            margin: 5px 0;
            border: 1px solid #ddd;
            border-radius: 4px;
        }
        .event-list, .task-list {
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
        }
        .healthy { color: green; }
        .error { color: red; }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚡ Lightning OS - Local Demo</h1>
        
        <div class="status">
            <h2>System Status</h2>
            <p>API Status: <span id="api-status" class="healthy">Checking...</span></p>
            <p>Mode: <span id="mode">Local Development</span></p>
            <p>API URL: <a href="http://localhost:8000" target="_blank">http://localhost:8000</a></p>
        </div>
        
        <div class="grid">
            <div class="panel">
                <h2>Submit Event</h2>
                <input type="text" id="event-type" placeholder="Event Type (e.g., user.action)">
                <input type="text" id="user-id" placeholder="User ID" value="demo-user">
                <textarea id="event-data" placeholder="Event Data (JSON)" rows="3">{}</textarea>
                <button onclick="submitEvent()">Submit Event</button>
                
                <h3>Recent Events</h3>
                <div id="events" class="event-list">No events yet</div>
            </div>
            
            <div class="panel">
                <h2>Create Task</h2>
                <input type="text" id="task-title" placeholder="Task Title">
                <textarea id="task-description" placeholder="Task Description" rows="3"></textarea>
                <select id="task-priority">
                    <option value="low">Low Priority</option>
                    <option value="medium" selected>Medium Priority</option>
                    <option value="high">High Priority</option>
                </select>
                <button onclick="createTask()">Create Task</button>
                
                <h3>Tasks</h3>
                <div id="tasks" class="task-list">No tasks yet</div>
            </div>
        </div>
    </div>
    
    <script>
        const API_URL = 'http://localhost:8000';
        
        async function checkHealth() {
            try {
                const response = await fetch(`${API_URL}/health`);
                const data = await response.json();
                document.getElementById('api-status').textContent = data.status;
                document.getElementById('api-status').className = 'healthy';
            } catch (error) {
                document.getElementById('api-status').textContent = 'Offline';
                document.getElementById('api-status').className = 'error';
            }
        }
        
        async function submitEvent() {
            const type = document.getElementById('event-type').value;
            const userID = document.getElementById('user-id').value;
            const dataStr = document.getElementById('event-data').value;
            
            try {
                const data = JSON.parse(dataStr || '{}');
                const response = await fetch(`${API_URL}/api/events`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ type, userID, data })
                });
                
                if (response.ok) {
                    document.getElementById('event-type').value = '';
                    document.getElementById('event-data').value = '{}';
                    loadEvents();
                }
            } catch (error) {
                alert('Error submitting event: ' + error.message);
            }
        }
        
        async function createTask() {
            const title = document.getElementById('task-title').value;
            const description = document.getElementById('task-description').value;
            const priority = document.getElementById('task-priority').value;
            
            try {
                const response = await fetch(`${API_URL}/api/tasks`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ title, description, priority })
                });
                
                if (response.ok) {
                    document.getElementById('task-title').value = '';
                    document.getElementById('task-description').value = '';
                    loadTasks();
                }
            } catch (error) {
                alert('Error creating task: ' + error.message);
            }
        }
        
        async function loadEvents() {
            try {
                const response = await fetch(`${API_URL}/api/events`);
                const data = await response.json();
                const eventsDiv = document.getElementById('events');
                
                if (data.events.length === 0) {
                    eventsDiv.innerHTML = 'No events yet';
                } else {
                    eventsDiv.innerHTML = data.events.map(event => 
                        `<div class="item">
                            <strong>${event.type}</strong> - ${event.userID}
                            <br><small>${new Date(event.timestamp).toLocaleString()}</small>
                        </div>`
                    ).join('');
                }
            } catch (error) {
                console.error('Error loading events:', error);
            }
        }
        
        async function loadTasks() {
            try {
                const response = await fetch(`${API_URL}/api/tasks`);
                const data = await response.json();
                const tasksDiv = document.getElementById('tasks');
                
                if (data.tasks.length === 0) {
                    tasksDiv.innerHTML = 'No tasks yet';
                } else {
                    tasksDiv.innerHTML = data.tasks.map(task => 
                        `<div class="item">
                            <strong>${task.title}</strong> - ${task.priority}
                            <br><small>${task.description}</small>
                        </div>`
                    ).join('');
                }
            } catch (error) {
                console.error('Error loading tasks:', error);
            }
        }
        
        // Initial load
        checkHealth();
        loadEvents();
        loadTasks();
        
        // Refresh every 5 seconds
        setInterval(() => {
            checkHealth();
            loadEvents();
            loadTasks();
        }, 5000);
    </script>
</body>
</html>
EOF
}

# Start UI
start_ui() {
    create_simple_ui
    
    if docker ps -a | grep -q lightning-ui; then
        print_info "Removing existing UI container..."
        docker rm -f lightning-ui
    fi
    
    print_info "Starting UI server..."
    docker run -d \
        --name lightning-ui \
        --network lightning-network \
        -p 8080:80 \
        -v /tmp/lightning-ui:/usr/share/nginx/html:ro \
        nginx:alpine
}

# Show status
show_status() {
    echo ""
    print_info "Lightning OS is running locally!"
    echo ""
    echo "Access points:"
    echo "  • Web UI:    http://localhost:8080"
    echo "  • API:       http://localhost:8000"
    echo "  • API Docs:  http://localhost:8000/docs"
    echo ""
    echo "Services:"
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep lightning
    echo ""
    print_info "To stop all services: docker rm -f \$(docker ps -a | grep lightning | awk '{print \$1}')"
}

# Main execution
main() {
    echo "╔════════════════════════════════════════════════════════╗"
    echo "║     Lightning OS - Simple Local Demo (No Compose)      ║"
    echo "╚════════════════════════════════════════════════════════╝"
    echo ""
    
    create_network
    start_postgres
    start_redis
    start_api
    start_ui
    
    # Wait for services to be ready
    print_info "Waiting for services to start..."
    sleep 3
    
    show_status
}

# Run main
main