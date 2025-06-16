from typing import List, Union
import subprocess

from . import Agent, register

@register
class ConseilAgent(Agent):
    """Agent that delegates commands to the `conseil` CLI."""

    name = "conseil"

    def run(self, commands: Union[List[str], str]) -> str:
        if isinstance(commands, str):
            cmd = ["conseil", commands]
        else:
            cmd = ["conseil"] + list(commands)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.stderr:
                # stderr is forwarded to the user to mimic CLI behaviour
                print(result.stderr)
            result.check_returncode()
            return result.stdout
        except subprocess.CalledProcessError as exc:
            # surface the error message in the returned string instead of
            # raising the exception further
            return exc.stderr or exc.output or str(exc)
