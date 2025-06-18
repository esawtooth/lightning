import json
import os
import sys
from datetime import datetime
import time
import asyncio

from agents import AGENT_REGISTRY
from lightning_core.events.models import WorkerTaskEvent
from lightning_core.abstractions import Document
from lightning_core.runtime import LightningRuntime


async def main() -> int:
    event_json = os.environ.get("WORKER_EVENT")
    if not event_json:
        print("WORKER_EVENT not set", file=sys.stderr)
        return 1
    try:
        data = json.loads(event_json)
        event = WorkerTaskEvent.from_dict(data)
    except Exception as e:
        print(f"Invalid WORKER_EVENT: {e}", file=sys.stderr)
        return 1

    agent_name = event.metadata.get("agent", "conseil")
    agent = AGENT_REGISTRY.get(agent_name)
    if not agent:
        print(f"Unknown agent: {agent_name}", file=sys.stderr)
        return 1

    start_time = time.time()
    if event.task:
        result = agent.run(event.task)
    else:
        result = agent.run(event.commands)
    runtime = time.time() - start_time

    usage = getattr(agent, "last_usage", {}) or {}
    tokens = usage.get("total_tokens", 0)
    model = os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo")
    cost_rate = float(os.environ.get("OPENAI_PRICE_PER_1K_TOKENS", "0.002")) / 1000
    cost_usd = tokens * cost_rate
    event.cost = {
        "cost": cost_usd,
        "tokens": tokens,
        "model": model,
        "runtime_sec": runtime,
        "event_count": len(event.history) + 1,
    }

    task_id = os.environ.get("TASK_ID")
    if task_id:
        container_name = os.environ.get("TASK_CONTAINER", "tasks")
        runtime = LightningRuntime()
        
        try:
            # Try to get existing document
            doc = await runtime.storage.get_document(container_name, task_id)
            if not doc:
                # Create new document if doesn't exist
                doc = Document(
                    id=task_id,
                    partition_key=event.user_id,
                    data={"id": task_id, "pk": event.user_id}
                )
            
            # Update with cost data
            doc.data["cost"] = event.cost
            doc.data["updated_at"] = datetime.utcnow().isoformat()
            
            # Use Lightning's storage abstraction
            if await runtime.storage.get_document(container_name, task_id):
                await runtime.storage.update_document(container_name, doc)
            else:
                await runtime.storage.create_document(container_name, doc)
                
        except Exception as e:
            print(f"Failed to update task cost: {e}", file=sys.stderr)

    if result:
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
