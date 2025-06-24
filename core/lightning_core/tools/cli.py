#!/usr/bin/env python3
"""
CLI tool for managing Lightning Core tool registries.
Provides visibility into the simplified tool registry.
"""

import argparse
import asyncio
import json
from typing import Any, Dict, List

from .registry import AccessScope, ToolType, get_tool_registry, load_planner_tools


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


async def list_all_tools(format_type: str = "table") -> None:
    """List all tools in the simplified registry"""
    registry = get_tool_registry()
    tools = await registry.list_tools()

    if format_type == "json":
        tool_data = [
            {
                "id": tool.id,
                "name": tool.name,
                "description": tool.description,
                "type": tool.tool_type.value,
                "capabilities": list(tool.capabilities),
                "access_scopes": [scope.value for scope in tool.access_scopes],
                "enabled": tool.enabled,
            }
            for tool in tools
        ]
        print(json.dumps(tool_data, indent=2))
        return

    # Table format
    headers = ["Tool ID", "Type", "Description", "Capabilities", "Access Scopes"]
    rows = []

    for tool in tools:
        capabilities = ", ".join(tool.capabilities) if tool.capabilities else "None"
        scopes = ", ".join(scope.value for scope in tool.access_scopes)

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
                scopes[:30] + "..." if len(scopes) > 30 else scopes,
            ]
        )

    print(f"\n=== ALL TOOLS IN SYSTEM ({len(tools)} total) ===")
    print(simple_table(headers, rows))


async def list_planner_tools(format_type: str = "table") -> None:
    """List tools available to the planner"""
    tools = await load_planner_tools()

    if format_type == "json":
        print(json.dumps(tools, indent=2))
        return

    # Table format
    headers = ["Tool ID", "Description", "Inputs", "Produces"]
    rows = []

    for tool_id, tool_data in tools.items():
        inputs = ", ".join(tool_data.get("inputs", {}).keys()) or "None"
        produces = ", ".join(tool_data.get("produces", [])) or "None"

        rows.append(
            [
                tool_id,
                (
                    tool_data.get("description", "")[:50] + "..."
                    if len(tool_data.get("description", "")) > 50
                    else tool_data.get("description", "")
                ),
                inputs[:30] + "..." if len(inputs) > 30 else inputs,
                produces[:30] + "..." if len(produces) > 30 else produces,
            ]
        )

    print(f"\n=== PLANNER TOOLS ({len(tools)} total) ===")
    print(simple_table(headers, rows))


async def list_tools_by_type(tool_type: str, format_type: str = "table") -> None:
    """List tools of a specific type"""
    try:
        type_enum = ToolType(tool_type)
    except ValueError:
        print(f"Invalid tool type: {tool_type}")
        print(f"Valid types: {[t.value for t in ToolType]}")
        return

    registry = get_tool_registry()
    tools = await registry.list_tools(tool_type=type_enum)

    if format_type == "json":
        tool_data = [
            {
                "id": tool.id,
                "name": tool.name,
                "description": tool.description,
                "capabilities": list(tool.capabilities),
            }
            for tool in tools
        ]
        print(json.dumps(tool_data, indent=2))
        return

    # Table format
    headers = ["Tool ID", "Name", "Description", "Capabilities"]
    rows = []

    for tool in tools:
        capabilities = ", ".join(tool.capabilities) if tool.capabilities else "None"

        rows.append(
            [
                tool.id,
                tool.name,
                (
                    tool.description[:50] + "..."
                    if len(tool.description) > 50
                    else tool.description
                ),
                capabilities,
            ]
        )

    print(f"\n=== TOOLS OF TYPE '{tool_type}' ({len(tools)} total) ===")
    print(simple_table(headers, rows))


async def list_tools_by_capability(capability: str, format_type: str = "table") -> None:
    """List tools with a specific capability"""
    registry = get_tool_registry()
    tools = await registry.list_tools(capability=capability)

    if format_type == "json":
        tool_data = [
            {
                "id": tool.id,
                "name": tool.name,
                "description": tool.description,
                "type": tool.tool_type.value,
            }
            for tool in tools
        ]
        print(json.dumps(tool_data, indent=2))
        return

    # Table format
    headers = ["Tool ID", "Type", "Description"]
    rows = []

    for tool in tools:
        rows.append(
            [
                tool.id,
                tool.tool_type.value,
                (
                    tool.description[:50] + "..."
                    if len(tool.description) > 50
                    else tool.description
                ),
            ]
        )

    print(f"\n=== TOOLS WITH '{capability}' CAPABILITY ({len(tools)} total) ===")
    print(simple_table(headers, rows))


async def show_tool_details(tool_id: str) -> None:
    """Show detailed information about a specific tool"""
    registry = get_tool_registry()
    tool = await registry.get_tool(tool_id)

    if not tool:
        print(f"Tool '{tool_id}' not found")
        return

    print(f"\n=== TOOL DETAILS: {tool_id} ===")
    print(f"Name: {tool.name}")
    print(f"Type: {tool.tool_type.value}")
    print(f"Description: {tool.description}")
    print(f"Enabled: {'Yes' if tool.enabled else 'No'}")
    print(f"Version: {tool.version}")

    if tool.access_scopes:
        print(f"\nAccess Scopes:")
        for scope in tool.access_scopes:
            print(f"  - {scope.value}")

    if tool.capabilities:
        print(f"\nCapabilities:")
        for cap in tool.capabilities:
            print(f"  - {cap}")

    if tool.inputs:
        print(f"\nInputs:")
        for arg, arg_type in tool.inputs.items():
            print(f"  - {arg}: {arg_type}")

    if tool.produces:
        print(f"\nProduces Events:")
        for event in tool.produces:
            print(f"  - {event}")

    if tool.config:
        print(f"\nConfiguration:")
        print(json.dumps(tool.config, indent=2))


async def main_async():
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
  python -m lightning_core.tools.cli show-tool agent.conseil
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
    subparsers.add_parser("list-all", help="List all tools in the registry")

    # List planner tools
    subparsers.add_parser("list-planner", help="List tools available to planner")

    # List by type
    type_parser = subparsers.add_parser("list-by-type", help="List tools by type")
    type_parser.add_argument(
        "type", help="Tool type (native, mcp, api, llm, agent)"
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

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    try:
        if args.command == "list-all":
            await list_all_tools(args.format)
        elif args.command == "list-planner":
            await list_planner_tools(args.format)
        elif args.command == "list-by-type":
            await list_tools_by_type(args.type, args.format)
        elif args.command == "list-by-capability":
            await list_tools_by_capability(args.capability, args.format)
        elif args.command == "show-tool":
            await show_tool_details(args.tool_id)
    except Exception as e:
        print(f"Error: {e}")
        return 1

    return 0


def main():
    """Main entry point that runs the async main function"""
    return asyncio.run(main_async())


if __name__ == "__main__":
    exit(main())
