import json
import os
import sys
from datetime import datetime
import time

from azure.cosmos import CosmosClient, PartitionKey

from agents import AGENT_REGISTRY
from events import WorkerTaskEvent


def main() -> int:
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

    agent_name = event.metadata.get("agent", "openai-shell")
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

    cosmos_conn = os.environ.get("COSMOS_CONNECTION")
    task_id = os.environ.get("TASK_ID")
    if cosmos_conn and task_id:
        db_name = os.environ.get("COSMOS_DATABASE", "lightning")
        container_name = os.environ.get("TASK_CONTAINER", "tasks")
        client = CosmosClient.from_connection_string(cosmos_conn)
        db = client.create_database_if_not_exists(db_name)
        container = db.create_container_if_not_exists(
            id=container_name, partition_key=PartitionKey(path="/pk")
        )
        try:
            item = container.read_item(task_id, partition_key=event.user_id)
        except Exception:
            item = {"id": task_id, "pk": event.user_id}
        item["cost"] = event.cost
        item["updated_at"] = datetime.utcnow().isoformat()
        container.upsert_item(item)

    if result:
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
