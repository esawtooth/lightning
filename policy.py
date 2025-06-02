import json
import json
import os
from typing import Dict, List

try:
    from azure.cosmos import CosmosClient, PartitionKey  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    CosmosClient = None  # type: ignore
    PartitionKey = None  # type: ignore

__all__ = ["PolicyViolationError", "get_policy_prompt", "validate_command"]


class PolicyViolationError(RuntimeError):
    """Raised when a command violates the active security policy."""


_policies: Dict[str, List[str]] = {}
_prompt: str = ""
_current_file: str | None = None
_current_user: str | None = None

_cosmos_client = None
_cosmos_container = None


def _get_cosmos_container():
    global _cosmos_client, _cosmos_container
    if _cosmos_container is not None:
        return _cosmos_container
    if CosmosClient is None:
        return None
    conn = os.environ.get("COSMOS_CONNECTION")
    if not conn:
        return None
    db_name = os.environ.get("COSMOS_DATABASE", "lightning")
    container_name = os.environ.get("POLICY_CONTAINER", "policies")
    _cosmos_client = CosmosClient.from_connection_string(conn)
    db = _cosmos_client.create_database_if_not_exists(db_name)
    _cosmos_container = db.create_container_if_not_exists(
        id=container_name, partition_key=PartitionKey(path="/pk")
    )
    return _cosmos_container


def _load_policies(force: bool = False) -> None:
    global _policies, _prompt, _current_file, _current_user
    user_id = os.environ.get("USER_ID")
    container = _get_cosmos_container()

    if container and user_id:
        if not force and _current_user == user_id and _policies:
            return
        _current_user = user_id
        try:
            entity = container.read_item("policy", partition_key=user_id)
            data = entity.get("policy", {})
        except Exception:
            data = {}
        patterns = data.get("blocked_patterns")
        if isinstance(patterns, list):
            _policies = {"blocked_patterns": [str(p) for p in patterns]}
        else:
            _policies = {"blocked_patterns": []}
        _prompt = str(data.get("prompt", ""))
        return

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
