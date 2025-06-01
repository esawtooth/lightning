from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, Optional, List
import uuid


@dataclass
class Event:
    timestamp: datetime
    source: str
    type: str
    user_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    id: Optional[str] = None
    history: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        if "timestamp" not in data:
            raise ValueError("timestamp required")
        if "source" not in data:
            raise ValueError("source required")
        if "type" not in data:
            raise ValueError("type required")
        if "userID" not in data:
            raise ValueError("userID required")
        ts = data["timestamp"]
        if isinstance(ts, str):
            if ts.endswith("Z"):
                ts = ts[:-1] + "+00:00"
            try:
                timestamp = datetime.fromisoformat(ts)
            except ValueError:
                raise ValueError("invalid timestamp")
        elif isinstance(ts, (int, float)):
            timestamp = datetime.fromtimestamp(ts)
        else:
            raise ValueError("invalid timestamp")
        history = data.get("history", [])
        if not isinstance(history, list):
            raise ValueError("history must be a list")

        return cls(
            timestamp=timestamp,
            source=data["source"],
            type=data["type"],
            user_id=data["userID"],
            metadata=data.get("metadata", {}),
            id=data.get("id") or uuid.uuid4().hex,
            history=history,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "type": self.type,
            "userID": self.user_id,
            "metadata": self.metadata,
            "id": self.id,
            "history": self.history,
        }


@dataclass
class LLMChatEvent(Event):
    """Event representing an LLM chat interaction."""

    messages: List[Any] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LLMChatEvent":
        base = Event.from_dict(data)
        msgs = base.metadata.get("messages")
        if not msgs:
            raise ValueError("metadata.messages required")
        if not isinstance(msgs, list):
            raise ValueError("metadata.messages must be a list")
        for msg in msgs:
            if not isinstance(msg, dict) or "role" not in msg or "content" not in msg:
                raise ValueError("invalid message entry")
        return cls(**asdict(base), messages=msgs)

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        meta = dict(d.get("metadata", {}))
        meta["messages"] = self.messages
        d["metadata"] = meta
        return d


@dataclass
class WorkerTaskEvent(Event):
    """Event describing a task to run against a user's repository."""

    commands: List[str] = field(default_factory=list)
    task: Optional[str] = None
    repo_url: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkerTaskEvent":
        base = Event.from_dict(data)
        cmds = base.metadata.get("commands") or []
        task = base.metadata.get("task")
        if not cmds and not task:
            raise ValueError("metadata.commands or metadata.task required")
        repo = base.metadata.get("repo_url")
        return cls(**asdict(base), commands=cmds, task=task, repo_url=repo)

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        meta = dict(d.get("metadata", {}))
        if self.commands:
            meta["commands"] = self.commands
        if self.task is not None:
            meta["task"] = self.task
        if self.repo_url is not None:
            meta["repo_url"] = self.repo_url
        d["metadata"] = meta
        return d
