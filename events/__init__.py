from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class Event:
    timestamp: datetime
    source: str
    type: str
    user_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    id: Optional[str] = None

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
            timestamp = datetime.fromisoformat(ts)
        elif isinstance(ts, (int, float)):
            timestamp = datetime.fromtimestamp(ts)
        else:
            raise ValueError("invalid timestamp")
        return cls(
            timestamp=timestamp,
            source=data["source"],
            type=data["type"],
            user_id=data["userID"],
            metadata=data.get("metadata", {}),
            id=data.get("id"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "type": self.type,
            "userID": self.user_id,
            "metadata": self.metadata,
            "id": self.id,
        }
