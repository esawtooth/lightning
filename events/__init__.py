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
    cost: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkerTaskEvent":
        base = Event.from_dict(data)
        cmds = base.metadata.get("commands") or []
        task = base.metadata.get("task")
        if not cmds and not task:
            raise ValueError("metadata.commands or metadata.task required")
        repo = base.metadata.get("repo_url")
        cost = base.metadata.get("cost")
        if cost is not None and not isinstance(cost, dict):
            cost = {"cost": float(cost)}
        return cls(
            **asdict(base),
            commands=cmds,
            task=task,
            repo_url=repo,
            cost=cost,
        )

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        meta = dict(d.get("metadata", {}))
        if self.commands:
            meta["commands"] = self.commands
        if self.task is not None:
            meta["task"] = self.task
        if self.repo_url is not None:
            meta["repo_url"] = self.repo_url
        if self.cost is not None:
            meta["cost"] = self.cost
        d["metadata"] = meta
        return d


@dataclass
class VoiceCallEvent(Event):
    """Event requesting an outbound voice call."""

    phone: str = ""
    objective: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VoiceCallEvent":
        base = Event.from_dict(data)
        phone = base.metadata.get("phone")
        if not phone:
            raise ValueError("metadata.phone required")
        obj = base.metadata.get("objective")
        return cls(**asdict(base), phone=phone, objective=obj)

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        meta = dict(d.get("metadata", {}))
        meta["phone"] = self.phone
        if self.objective is not None:
            meta["objective"] = self.objective
        d["metadata"] = meta
        return d


@dataclass
class EmailEvent(Event):
    """Event for email operations across providers."""

    operation: str = ""  # "fetch", "send", "reply", "forward", "received"
    provider: str = ""  # "gmail", "outlook", "icloud"
    email_data: Dict[str, Any] = field(default_factory=dict)
    filters: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EmailEvent":
        base = Event.from_dict(data)
        operation = base.metadata.get("operation")
        if not operation:
            raise ValueError("metadata.operation required")
        provider = base.metadata.get("provider")
        if not provider:
            raise ValueError("metadata.provider required")
        email_data = base.metadata.get("email_data", {})
        filters = base.metadata.get("filters")
        return cls(
            **asdict(base),
            operation=operation,
            provider=provider,
            email_data=email_data,
            filters=filters,
        )

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        meta = dict(d.get("metadata", {}))
        meta["operation"] = self.operation
        meta["provider"] = self.provider
        meta["email_data"] = self.email_data
        if self.filters is not None:
            meta["filters"] = self.filters
        d["metadata"] = meta
        return d


@dataclass
class CalendarEvent(Event):
    """Event for calendar operations across providers."""

    operation: str = ""  # "fetch", "create", "update", "delete", "send_invite", "received"
    provider: str = ""  # "gmail", "outlook", "icloud"
    calendar_data: Dict[str, Any] = field(default_factory=dict)
    time_range: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CalendarEvent":
        base = Event.from_dict(data)
        operation = base.metadata.get("operation")
        if not operation:
            raise ValueError("metadata.operation required")
        provider = base.metadata.get("provider")
        if not provider:
            raise ValueError("metadata.provider required")
        calendar_data = base.metadata.get("calendar_data", {})
        time_range = base.metadata.get("time_range")
        return cls(
            **asdict(base),
            operation=operation,
            provider=provider,
            calendar_data=calendar_data,
            time_range=time_range,
        )

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        meta = dict(d.get("metadata", {}))
        meta["operation"] = self.operation
        meta["provider"] = self.provider
        meta["calendar_data"] = self.calendar_data
        if self.time_range is not None:
            meta["time_range"] = self.time_range
        d["metadata"] = meta
        return d


@dataclass
class InstructionEvent(Event):
    """Event for managing user instructions."""

    instruction_operation: str = ""  # "create", "update", "delete", "execute"
    instruction_data: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InstructionEvent":
        base = Event.from_dict(data)
        instruction_operation = base.metadata.get("instruction_operation")
        if not instruction_operation:
            raise ValueError("metadata.instruction_operation required")
        instruction_data = base.metadata.get("instruction_data", {})
        return cls(
            **asdict(base),
            instruction_operation=instruction_operation,
            instruction_data=instruction_data,
        )

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        meta = dict(d.get("metadata", {}))
        meta["instruction_operation"] = self.instruction_operation
        meta["instruction_data"] = self.instruction_data
        d["metadata"] = meta
        return d


@dataclass
class ContextUpdateEvent(Event):
    """Event for updating user context in the context hub."""

    context_key: str = ""
    update_operation: str = ""  # "append", "replace", "synthesize", "merge"
    content: str = ""
    synthesis_prompt: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextUpdateEvent":
        base = Event.from_dict(data)
        context_key = base.metadata.get("context_key")
        if not context_key:
            raise ValueError("metadata.context_key required")
        update_operation = base.metadata.get("update_operation")
        if not update_operation:
            raise ValueError("metadata.update_operation required")
        content = base.metadata.get("content", "")
        synthesis_prompt = base.metadata.get("synthesis_prompt")
        return cls(
            **asdict(base),
            context_key=context_key,
            update_operation=update_operation,
            content=content,
            synthesis_prompt=synthesis_prompt,
        )

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        meta = dict(d.get("metadata", {}))
        meta["context_key"] = self.context_key
        meta["update_operation"] = self.update_operation
        meta["content"] = self.content
        if self.synthesis_prompt is not None:
            meta["synthesis_prompt"] = self.synthesis_prompt
        d["metadata"] = meta
        return d
