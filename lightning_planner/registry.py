from pathlib import Path
import json
from typing import Dict, Any

_REGISTRY_PATH = Path(__file__).with_suffix('.tools.json')


class ToolRegistry:
    """Lazy singleton exposing primitive capabilities."""

    _tools: Dict[str, Any] | None = None

    @classmethod
    def load(cls, path: Path | None = None) -> Dict[str, Any]:
        if cls._tools is None:
            path = path or _REGISTRY_PATH
            with path.open() as fh:
                cls._tools = json.load(fh)
        return cls._tools

    @classmethod
    def subset(cls, query: str) -> Dict[str, Any]:
        """Very naive semantic search; replace with vector search later."""
        q = query.lower()
        return {
            name: meta
            for name, meta in cls.load().items()
            if q in name.lower() or q in meta.get('description', '').lower()
        }
