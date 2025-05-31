from typing import List
import os
import subprocess

from . import Agent, register


@register
class OpenAIShellAgent(Agent):
    """Agent that uses OpenAI to translate instructions into shell commands and
    executes them in the local bash environment."""

    name = "openai-shell"

    def run(self, commands: List[str]) -> str:
        try:
            import openai
        except ModuleNotFoundError as e:
            raise RuntimeError("openai library required") from e

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        openai.api_key = api_key
        model = os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo")

        outputs = []
        for instruction in commands:
            response = openai.ChatCompletion.create(
                messages=[
                    {"role": "system", "content": "Return a bash command for the given instruction."},
                    {"role": "user", "content": instruction},
                ],
                model=model,
            )
            cmd = response["choices"][0]["message"]["content"]
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            outputs.append(proc.stdout)
        return "".join(outputs)
