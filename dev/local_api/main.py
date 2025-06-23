"""
Lightning OS Local Development API

A local development environment that demonstrates Lightning OS concepts
and provides a fully functional API without Azure dependencies.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Any, Optional
from datetime import datetime
import json
import uuid
import asyncio
import os
import redis
import asyncpg

# FastAPI app
app = FastAPI(
    title="Lightning OS - Local Development",
    description="Local development environment for Lightning OS",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Redis connection
redis_client = None

# PostgreSQL connection
pg_pool = None

# In-memory stores (fallback)
events_store = []
tasks_store = []

# Models
class EventRequest(BaseModel):
    type: str
    userID: str
    data: Dict[str, Any] = {}
    metadata: Dict[str, Any] = {}

class TaskRequest(BaseModel):
    title: str
    description: Optional[str] = ""
    priority: str = "medium"
    assignedTo: Optional[str] = None

class PlanRequest(BaseModel):
    description: str
    type: str = "acyclic"

# Startup
@app.on_event("startup")
async def startup():
    global redis_client, pg_pool
    
    # Connect to Redis
    try:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        redis_client = redis.from_url(redis_url, decode_responses=True)
        redis_client.ping()
        print("✓ Connected to Redis")
    except Exception as e:
        print(f"Warning: Redis not available: {e}")
        redis_client = None
    
    # Connect to PostgreSQL
    try:
        db_url = os.getenv("DATABASE_URL", "postgres://lightning:lightning123@localhost:5432/lightning_db")
        pg_pool = await asyncpg.create_pool(db_url)
        
        # Create tables
        async with pg_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id UUID PRIMARY KEY,
                    type VARCHAR(255),
                    user_id VARCHAR(255),
                    data JSONB,
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id UUID PRIMARY KEY,
                    title VARCHAR(255),
                    description TEXT,
                    priority VARCHAR(50),
                    status VARCHAR(50),
                    assigned_to VARCHAR(255),
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
        print("✓ Connected to PostgreSQL")
    except Exception as e:
        print(f"Warning: PostgreSQL not available: {e}")
        pg_pool = None

# Shutdown
@app.on_event("shutdown")
async def shutdown():
    if pg_pool:
        await pg_pool.close()

# Routes
@app.get("/")
async def root():
    return {
        "service": "Lightning OS Local Development",
        "mode": "local",
        "version": "1.0.0",
        "status": "running",
        "storage": "PostgreSQL" if pg_pool else "In-Memory",
        "events": "Redis" if redis_client else "In-Memory"
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "api": "healthy",
            "postgres": "connected" if pg_pool else "unavailable",
            "redis": "connected" if redis_client else "unavailable"
        }
    }

@app.post("/api/events")
async def submit_event(event: EventRequest):
    event_id = str(uuid.uuid4())
    event_data = {
        "id": event_id,
        "type": event.type,
        "userID": event.userID,
        "data": event.data,
        "metadata": event.metadata,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    # Store in PostgreSQL
    if pg_pool:
        async with pg_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO events (id, type, user_id, data, metadata)
                VALUES ($1, $2, $3, $4, $5)
            """, 
            uuid.UUID(event_id), 
            event.type, 
            event.userID,
            json.dumps(event.data),
            json.dumps(event.metadata)
        )
    else:
        events_store.append(event_data)
    
    # Publish to Redis
    if redis_client:
        redis_client.publish(f"events:{event.type}", json.dumps(event_data))
    
    return {"success": True, "event_id": event_id}

@app.get("/api/events")
async def get_events(limit: int = 20):
    if pg_pool:
        async with pg_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, type, user_id, data, metadata, created_at
                FROM events
                ORDER BY created_at DESC
                LIMIT $1
            """, limit)
            
            events = []
            for row in rows:
                events.append({
                    "id": str(row["id"]),
                    "type": row["type"],
                    "userID": row["user_id"],
                    "data": json.loads(row["data"]) if row["data"] else {},
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                    "timestamp": row["created_at"].isoformat()
                })
            return {"events": events, "total": len(events)}
    else:
        return {"events": events_store[-limit:], "total": len(events_store)}

@app.post("/api/tasks")
async def create_task(task: TaskRequest):
    task_id = str(uuid.uuid4())
    task_data = {
        "id": task_id,
        "title": task.title,
        "description": task.description,
        "priority": task.priority,
        "status": "pending",
        "assignedTo": task.assignedTo,
        "createdAt": datetime.utcnow().isoformat()
    }
    
    # Store in PostgreSQL
    if pg_pool:
        async with pg_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO tasks (id, title, description, priority, status, assigned_to)
                VALUES ($1, $2, $3, $4, $5, $6)
            """,
            uuid.UUID(task_id),
            task.title,
            task.description,
            task.priority,
            "pending",
            task.assignedTo
        )
    else:
        tasks_store.append(task_data)
    
    # Create task event
    await submit_event(EventRequest(
        type="task.created",
        userID=task.assignedTo or "system",
        data={"task_id": task_id, "title": task.title}
    ))
    
    return {"success": True, "task": task_data}

@app.get("/api/tasks")
async def get_tasks():
    if pg_pool:
        async with pg_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, title, description, priority, status, assigned_to, created_at
                FROM tasks
                ORDER BY created_at DESC
            """)
            
            tasks = []
            for row in rows:
                tasks.append({
                    "id": str(row["id"]),
                    "title": row["title"],
                    "description": row["description"],
                    "priority": row["priority"],
                    "status": row["status"],
                    "assignedTo": row["assigned_to"],
                    "createdAt": row["created_at"].isoformat()
                })
            return {"tasks": tasks, "total": len(tasks)}
    else:
        return {"tasks": tasks_store, "total": len(tasks_store)}

@app.post("/api/plans")
async def create_plan(plan: PlanRequest):
    plan_id = f"plan-{uuid.uuid4()}"
    
    # In a real system, this would create a Petri net plan
    # For demo, we just store the request
    plan_data = {
        "id": plan_id,
        "description": plan.description,
        "type": plan.type,
        "status": "draft",
        "createdAt": datetime.utcnow().isoformat()
    }
    
    await submit_event(EventRequest(
        type="plan.created",
        userID="system",
        data=plan_data
    ))
    
    return {"success": True, "plan": plan_data}

# Demo route to show abstraction
@app.get("/api/demo/abstraction")
async def demo_abstraction():
    """Demonstrate how the abstraction layer works."""
    return {
        "message": "This API works with both local and cloud storage!",
        "current_mode": "local",
        "storage_backend": "PostgreSQL" if pg_pool else "In-Memory",
        "event_backend": "Redis" if redis_client else "In-Memory",
        "explanation": {
            "local": {
                "storage": "PostgreSQL",
                "events": "Redis Pub/Sub",
                "containers": "Docker",
                "functions": "Python processes"
            },
            "azure": {
                "storage": "Cosmos DB",
                "events": "Service Bus",
                "containers": "Container Instances",
                "functions": "Azure Functions"
            }
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)