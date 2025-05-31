from typing import List

from . import Agent, register


@register
class EchoAgent(Agent):
    """Simple agent that echoes the received commands."""

    name = "echo"

    def run(self, commands: List[str]) -> str:
        return "\n".join(commands)
