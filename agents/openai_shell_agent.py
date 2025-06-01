from typing import List, Union
import os
import subprocess
import json
import sys

from . import Agent, register


@register
class OpenAIShellAgent(Agent):
    """Agent that uses OpenAI's tool calling to run bash commands."""

    name = "openai-shell"

    def run(self, commands: Union[List[str], str]) -> str:
        try:
            import openai
        except ModuleNotFoundError as e:
            raise RuntimeError("openai library required") from e

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        openai.api_key = api_key
        model = os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo")

        bash_tool = {
            "type": "function",
            "function": {
                "name": "bash",
                "description": "Execute a bash command",
                "parameters": {
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                },
            },
        }

        if isinstance(commands, str):
            instructions = [commands]
        else:
            instructions = commands

        outputs = []
        for instruction in instructions:
            response = openai.ChatCompletion.create(
                messages=[{"role": "user", "content": instruction}],
                model=model,
                tools=[bash_tool],
                tool_choice={"type": "function", "function": {"name": "bash"}},
            )
            tool_calls = response["choices"][0]["message"].get("tool_calls")
            if tool_calls:
                args_json = tool_calls[0]["function"].get("arguments", "{}")
                try:
                    args = json.loads(args_json)
                    cmd = args.get("command", "")
                except json.JSONDecodeError:
                    cmd = ""
            else:
                cmd = response["choices"][0]["message"].get("content", "")

            print(f"$ {cmd}", flush=True)
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if proc.stdout:
                print(proc.stdout, flush=True)
            if proc.stderr:
                print(proc.stderr, file=sys.stderr, flush=True)
            outputs.append(proc.stdout)
        return "".join(outputs)
