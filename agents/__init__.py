"""Agents available to run worker tasks."""

from typing import Dict, List


class Agent:
    """Base class for task agents."""

    name: str = "base"

    def run(self, commands: List[str]) -> str:
        """Execute the provided commands and return a result string."""
        raise NotImplementedError()


AGENT_REGISTRY: Dict[str, Agent] = {}


def register(agent_cls: type) -> type:
    """Class decorator to register an agent in the registry."""
    instance = agent_cls()
    if not isinstance(instance, Agent):
        raise TypeError("agent_cls must inherit from Agent")
    AGENT_REGISTRY[instance.name] = instance
    return agent_cls


from . import echo_agent  # noqa: F401  # register built-in agents
