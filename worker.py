import json
import os
import sys

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

    if event.task:
        result = agent.run(event.task)
    else:
        result = agent.run(event.commands)

    if result:
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
