#!/usr/bin/env python3
"""
CLI tool for managing Lightning Core tool registries.
Provides visibility and control over tools available to different components.
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from .planner_bridge import PlannerToolBridge
from .registry import AccessScope, ToolType, get_tool_registry


def simple_table(headers: List[str], rows: List[List[str]]) -> str:
    """Simple table formatter without external dependencies"""
    if not rows:
        return "No data to display"

    # Calculate column widths
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(str(cell)))

    # Create format string
    format_str = " | ".join(f"{{:<{w}}}" for w in col_widths)

    # Build table
    lines = []
    lines.append(format_str.format(*headers))
    lines.append("-" * (sum(col_widths) + 3 * (len(headers) - 1)))

    for row in rows:
        # Ensure all cells are strings and pad to match column count
        formatted_row = [str(cell) for cell in row]
        while len(formatted_row) < len(headers):
            formatted_row.append("")
        lines.append(format_str.format(*formatted_row[: len(headers)]))

    return "\n".join(lines)


def list_all_tools(format_type: str = "table") -> None:
    """List all tools in the unified registry"""
    registry = get_tool_registry()
    tools = registry.list_tools()

    if format_type == "json":
        tool_data = [tool.to_planner_format() for tool in tools]
        print(json.dumps(tool_data, indent=2))
        return

    # Table format
    headers = ["Tool ID", "Type", "Description", "Capabilities", "Inputs", "Produces"]
    rows = []

    for tool in tools:
        inputs = ", ".join(tool.inputs.keys()) if tool.inputs else "None"
        produces = ", ".join(tool.produces) if tool.produces else "None"
        capabilities = ", ".join(tool.capabilities) if tool.capabilities else "None"

        rows.append(
            [
                tool.id,
                tool.tool_type.value,
                (
                    tool.description[:50] + "..."
                    if len(tool.description) > 50
                    else tool.description
                ),
                capabilities[:30] + "..." if len(capabilities) > 30 else capabilities,
                inputs[:30] + "..." if len(inputs) > 30 else inputs,
                produces[:30] + "..." if len(produces) > 30 else produces,
            ]
        )

    print(f"\n=== ALL TOOLS IN SYSTEM ({len(tools)} total) ===")
    print(simple_table(headers, rows))


def list_planner_tools(format_type: str = "table") -> None:
    """List tools available to the planner"""
    bridge = PlannerToolBridge()
    tools = bridge.load()

    if format_type == "json":
        print(json.dumps(tools, indent=2))
        return

    # Table format
    headers = ["Tool ID", "Description", "Inputs", "Produces"]
    rows = []

    for tool_id, tool_spec in tools.items():
        inputs = ", ".join(tool_spec.get("inputs", {}).keys())
        produces = ", ".join(tool_spec.get("produces", []))
        description = tool_spec.get("description", "")

        rows.append(
            [
                tool_id,
                description[:60] + "..." if len(description) > 60 else description,
                inputs[:40] + "..." if len(inputs) > 40 else inputs,
                produces[:40] + "..." if len(produces) > 40 else produces,
            ]
        )

    print(f"\n=== PLANNER TOOLS ({len(tools)} total) ===")
    print(simple_table(headers, rows))


def list_tools_by_type(tool_type: str, format_type: str = "table") -> None:
    """List tools filtered by type"""
    registry = get_tool_registry()

    try:
        filter_type = ToolType(tool_type.lower())
        tools = registry.list_tools(tool_type=filter_type)
    except ValueError:
        print(f"Invalid tool type: {tool_type}")
        print(f"Valid types: {[t.value for t in ToolType]}")
        return

    if format_type == "json":
        tool_data = [tool.to_planner_format() for tool in tools]
        print(json.dumps(tool_data, indent=2))
        return

    # Table format
    headers = ["Tool ID", "Description", "Capabilities", "Enabled"]
    rows = []

    for tool in tools:
        capabilities = ", ".join(tool.capabilities) if tool.capabilities else "None"

        rows.append(
            [
                tool.id,
                (
                    tool.description[:60] + "..."
                    if len(tool.description) > 60
                    else tool.description
                ),
                capabilities[:40] + "..." if len(capabilities) > 40 else capabilities,
                "✓" if tool.enabled else "✗",
            ]
        )

    print(f"\n=== {tool_type.upper()} TOOLS ({len(tools)} total) ===")
    print(simple_table(headers, rows))


def list_tools_by_capability(capability: str, format_type: str = "table") -> None:
    """List tools filtered by capability"""
    registry = get_tool_registry()
    tools = registry.list_tools(capability=capability)

    if format_type == "json":
        tool_data = [tool.to_planner_format() for tool in tools]
        print(json.dumps(tool_data, indent=2))
        return

    # Table format
    headers = ["Tool ID", "Type", "Description", "All Capabilities"]
    rows = []

    for tool in tools:
        capabilities = ", ".join(tool.capabilities) if tool.capabilities else "None"

        rows.append(
            [
                tool.id,
                tool.tool_type.value,
                (
                    tool.description[:50] + "..."
                    if len(tool.description) > 50
                    else tool.description
                ),
                capabilities,
            ]
        )

    print(f"\n=== TOOLS WITH '{capability}' CAPABILITY ({len(tools)} total) ===")
    print(simple_table(headers, rows))


def show_tool_details(tool_id: str) -> None:
    """Show detailed information about a specific tool"""
    registry = get_tool_registry()
    tool = registry.get_tool(tool_id)

    if not tool:
        print(f"Tool '{tool_id}' not found")
        return

    print(f"\n=== TOOL DETAILS: {tool_id} ===")
    print(f"Name: {tool.name}")
    print(f"Type: {tool.tool_type.value}")
    print(f"Description: {tool.description}")
    print(f"Enabled: {'Yes' if tool.enabled else 'No'}")
    print(f"Version: {tool.version}")

    if tool.inputs:
        print(f"\nInputs:")
        for arg, arg_type in tool.inputs.items():
            print(f"  - {arg}: {arg_type}")

    if tool.produces:
        print(f"\nProduces Events:")
        for event in tool.produces:
            print(f"  - {event}")

    if tool.capabilities:
        print(f"\nCapabilities:")
        for cap in tool.capabilities:
            print(f"  - {cap}")

    if tool.endpoint:
        print(f"\nEndpoint: {tool.endpoint}")

    if tool.config:
        print(f"\nConfiguration:")
        print(json.dumps(tool.config, indent=2))

    # Check if available to planner
    bridge = PlannerToolBridge()
    planner_tools = bridge.load()
    available_to_planner = tool_id in planner_tools
    print(f"\nAvailable to Planner: {'Yes' if available_to_planner else 'No'}")


def sync_planner_registry() -> None:
    """Sync the planner registry JSON file with current filtered tools"""
    bridge = PlannerToolBridge()
    json_path = Path(__file__).parent.parent / "planner" / "registry.tools.json"
    bridge.sync_to_json(json_path)
    print(f"Synced planner registry to {json_path}")

    # Show what was synced
    tools = bridge.load()
    print(f"Synced {len(tools)} tools to planner registry:")
    for tool_id in sorted(tools.keys()):
        print(f"  - {tool_id}")


def compare_registries() -> None:
    """Compare tools available in unified registry vs planner registry"""
    registry = get_tool_registry()
    bridge = PlannerToolBridge()

    all_tools = set(registry.get_planner_registry().keys())
    planner_tools = set(bridge.load().keys())

    print(f"\n=== REGISTRY COMPARISON ===")
    print(f"Total tools in system: {len(all_tools)}")
    print(f"Tools available to planner: {len(planner_tools)}")
    print(f"Tools excluded from planner: {len(all_tools - planner_tools)}")

    if all_tools - planner_tools:
        print(f"\nExcluded from planner:")
        for tool_id in sorted(all_tools - planner_tools):
            print(f"  - {tool_id}")

    print(f"\nIncluded in planner:")
    for tool_id in sorted(planner_tools):
        print(f"  - {tool_id}")


def main():
    parser = argparse.ArgumentParser(
        description="Lightning Core Tool Registry Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all tools in the system
  python -m lightning_core.tools.cli list-all
  
  # List tools available to planner
  python -m lightning_core.tools.cli list-planner
  
  # List tools by type
  python -m lightning_core.tools.cli list-by-type agent
  
  # List tools with specific capability
  python -m lightning_core.tools.cli list-by-capability web_search
  
  # Show details of a specific tool
  python -m lightning_core.tools.cli show-tool web.search
  
  # Compare registries
  python -m lightning_core.tools.cli compare
  
  # Sync planner registry
  python -m lightning_core.tools.cli sync-planner
        """,
    )

    parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # List all tools
    subparsers.add_parser("list-all", help="List all tools in the unified registry")

    # List planner tools
    subparsers.add_parser("list-planner", help="List tools available to planner")

    # List by type
    type_parser = subparsers.add_parser("list-by-type", help="List tools by type")
    type_parser.add_argument(
        "type", help="Tool type (native, mcp_server, api, function, agent)"
    )

    # List by capability
    cap_parser = subparsers.add_parser(
        "list-by-capability", help="List tools by capability"
    )
    cap_parser.add_argument(
        "capability", help="Capability name (e.g., web_search, email_send)"
    )

    # Show tool details
    show_parser = subparsers.add_parser(
        "show-tool", help="Show detailed tool information"
    )
    show_parser.add_argument("tool_id", help="Tool ID to show details for")

    # Compare registries
    subparsers.add_parser(
        "compare", help="Compare unified registry vs planner registry"
    )

    # Sync planner registry
    subparsers.add_parser("sync-planner", help="Sync planner registry JSON file")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    try:
        if args.command == "list-all":
            list_all_tools(args.format)
        elif args.command == "list-planner":
            list_planner_tools(args.format)
        elif args.command == "list-by-type":
            list_tools_by_type(args.type, args.format)
        elif args.command == "list-by-capability":
            list_tools_by_capability(args.capability, args.format)
        elif args.command == "show-tool":
            show_tool_details(args.tool_id)
        elif args.command == "compare":
            compare_registries()
        elif args.command == "sync-planner":
            sync_planner_registry()
    except Exception as e:
        print(f"Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
