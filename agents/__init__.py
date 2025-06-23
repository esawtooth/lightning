"""Agents available to run worker tasks."""

from typing import Dict, List
import subprocess
import sys


class Agent:
    """Base class for task agents."""

    name: str = "base"

    hub_cli: str = "contexthub"

    def run(self, commands: List[str]) -> str:
        """Execute the provided commands and return a result string."""
        raise NotImplementedError()

    def hub(self, *args: str) -> str:
        """Invoke the context hub CLI with the given arguments."""
        cmd = [self.hub_cli, *args]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        result.check_returncode()
        return result.stdout


AGENT_REGISTRY: Dict[str, Agent] = {}


def register(agent_cls: type) -> type:
    """Class decorator to register an agent in the registry."""
    instance = agent_cls()
    if not isinstance(instance, Agent):
        raise TypeError("agent_cls must inherit from Agent")
    AGENT_REGISTRY[instance.name] = instance
    return agent_cls


from . import conseil_agent  # noqa: F401
