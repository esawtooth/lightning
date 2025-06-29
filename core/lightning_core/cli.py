"""
Lightning Core CLI - Main command-line interface
"""

import click

# Import CLI modules
from .agents.cli import agents
from .planner.cli import main as planner_cli
from .tools.cli import tools
from .mcp.cli import mcp


@click.group()
@click.version_option()
def lightning():
    """Lightning Core - AI Operating System"""
    pass


# Add subcommands
lightning.add_command(agents)
# lightning.add_command(tools)  # Uncomment when tools CLI is ready
# lightning.add_command(mcp)    # Uncomment when MCP CLI is ready


@lightning.command()
@click.argument('instruction')
@click.option('--model', help='Model to use for planning')
@click.option('--user-id', help='User ID for tracking')
@click.option('--output', help='Output file for the plan')
@click.option('--verbose', is_flag=True, help='Verbose output')
def plan(instruction: str, model: str, user_id: str, output: str, verbose: bool):
    """Generate a Lightning workflow plan"""
    import asyncio
    import json
    from .planner.planner import call_planner_llm
    
    async def _plan():
        try:
            plan = await call_planner_llm(
                instruction=instruction,
                registry_subset={},
                model=model,
                user_id=user_id
            )
            
            if output:
                with open(output, 'w') as f:
                    json.dump(plan, f, indent=2)
                click.echo(f"✅ Plan saved to: {output}")
            else:
                click.echo(json.dumps(plan, indent=2))
                
        except Exception as e:
            click.echo(f"❌ Error generating plan: {e}", err=True)
    
    asyncio.run(_plan())


@lightning.command()
@click.argument('event_json')
def process(event_json: str):
    """Process a Lightning event (JSON string or file path)"""
    import asyncio
    import json
    from pathlib import Path
    from .vextir_os.universal_processor import process_event_message
    
    async def _process():
        try:
            # Try to parse as JSON first
            try:
                event = json.loads(event_json)
            except json.JSONDecodeError:
                # Try as file path
                event_file = Path(event_json)
                if event_file.exists():
                    with open(event_file, 'r') as f:
                        event = json.load(f)
                else:
                    raise ValueError("Invalid JSON and file does not exist")
            
            result = await process_event_message(event)
            click.echo(json.dumps(result, indent=2))
            
        except Exception as e:
            click.echo(f"❌ Error processing event: {e}", err=True)
    
    asyncio.run(_process())


@lightning.command()
def version():
    """Show Lightning Core version information"""
    try:
        from lightning_core import __version__
        click.echo(f"Lightning Core v{__version__}")
    except ImportError:
        click.echo("Lightning Core (version unknown)")
    
    # Show component versions
    click.echo("\nComponents:")
    click.echo("  - Agent Configuration Platform: v1.0.0")
    click.echo("  - Workflow Planner: v1.0.0")
    click.echo("  - Vextir OS: v1.0.0")


if __name__ == "__main__":
    lightning()