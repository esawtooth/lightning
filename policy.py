import json
import os
from typing import Dict, List

__all__ = ["PolicyViolationError", "get_policy_prompt", "validate_command"]


class PolicyViolationError(RuntimeError):
    """Raised when a command violates the active security policy."""


_policies: Dict[str, List[str]] = {}
_prompt: str = ""
_current_file: str | None = None


def _load_policies(force: bool = False) -> None:
    global _policies, _prompt, _current_file
    policy_file = os.environ.get("SAFETY_POLICY_FILE")
    if not force and _current_file == policy_file and _prompt:
        return
    _current_file = policy_file
    if not policy_file:
        _policies = {"blocked_patterns": []}
        _prompt = ""
        return
    try:
        with open(policy_file, "r") as f:
            data = json.load(f)
    except Exception:
        _policies = {"blocked_patterns": []}
        _prompt = ""
        return
    patterns = data.get("blocked_patterns")
    if isinstance(patterns, list):
        _policies = {"blocked_patterns": [str(p) for p in patterns]}
    else:
        _policies = {"blocked_patterns": []}
    _prompt = str(data.get("prompt", ""))


def get_policy_prompt() -> str:
    _load_policies()
    return _prompt


def validate_command(cmd: str) -> None:
    """Raise PolicyViolationError if cmd violates the policy."""
    _load_policies()
    for pattern in _policies.get("blocked_patterns", []):
        if pattern and pattern in cmd:
            raise PolicyViolationError(f"command contains disallowed pattern: {pattern}")
