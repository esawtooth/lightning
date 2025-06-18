"""Command line utilities for Vextir OS."""

import asyncio
import json
import sys
from typing import Any, Dict

from .universal_processor import process_event_message


def main() -> None:
    """Process a JSON event from stdin and output the result."""
    try:
        event: Dict[str, Any] = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON input: {exc}", file=sys.stderr)
        sys.exit(1)

    result = asyncio.run(process_event_message(event))
    json.dump(result, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
