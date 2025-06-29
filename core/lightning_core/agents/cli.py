"""
CLI interface for Lightning Agent Configuration Platform
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

import click

from lightning_core.agents import (
    AgentConfigManager,
    AgentType,
    AgentConfig,
    ConseilAgentConfig,
    VoiceAgentConfig,
    ChatAgentConfig,
    PlannerAgentConfig,
)


@click.group()
def agents():
    """Manage Lightning agent configurations"""
    pass


@agents.command()
@click.option('--type', 'agent_type', type=click.Choice(['conseil', 'voice', 'chat', 'planner']), 
              help='Filter by agent type')
@click.option('--user', 'user_id', help='Show user-specific configurations')
@click.option('--defaults/--no-defaults', default=True, help='Include default configurations')
def list(agent_type: Optional[str], user_id: Optional[str], defaults: bool):
    """List available agent configurations"""
    async def _list():
        manager = AgentConfigManager()
        
        type_filter = None
        if agent_type:
            type_filter = AgentType(agent_type)
        
        configs = await manager.list_agent_configs(
            agent_type=type_filter,
            user_id=user_id,
            include_defaults=defaults
        )
        
        if not configs:
            click.echo("No agent configurations found.")
            return
        
        # Display configurations
        for config in configs:
            click.echo(f"\n📋 {config.name} ({config.id})")
            click.echo(f"   Type: {config.type.value}")
            click.echo(f"   Description: {config.description}")
            click.echo(f"   Created by: {config.created_by}")
            click.echo(f"   Version: {config.version}")
            
            if config.is_default:
                click.echo("   🏷️  Default configuration")
            if config.is_system:
                click.echo("   🏷️  System configuration")
            
            click.echo(f"   Tags: {', '.join(config.tags)}")
    
    asyncio.run(_list())


@agents.command()
@click.argument('agent_id')
@click.option('--user', 'user_id', help='Load user-specific configuration')
def show(agent_id: str, user_id: Optional[str]):
    """Show detailed configuration for an agent"""
    async def _show():
        manager = AgentConfigManager()
        
        try:
            config = await manager.get_agent_config(agent_id, user_id)
            
            click.echo(f"\n📋 Agent Configuration: {config.name}")
            click.echo("=" * 50)
            
            # Basic info
            click.echo(f"ID: {config.id}")
            click.echo(f"Type: {config.type.value}")
            click.echo(f"Description: {config.description}")
            click.echo(f"Created by: {config.created_by}")
            click.echo(f"Created at: {config.created_at}")
            click.echo(f"Version: {config.version}")
            
            # System prompt
            click.echo(f"\n🗣️  System Prompt:")
            click.echo(f"Name: {config.system_prompt.name}")
            click.echo(f"Description: {config.system_prompt.description}")
            click.echo(f"Template: {config.system_prompt.template[:200]}...")
            
            if config.system_prompt.parameters:
                click.echo(f"\nParameters:")
                for name, param in config.system_prompt.parameters.items():
                    click.echo(f"  - {name}: {param.description} (default: {param.default_value})")
            
            # Tools
            click.echo(f"\n🔧 Tools ({len(config.tools)}):")
            for tool in config.tools:
                status = "✅" if tool.enabled else "❌"
                approval = "🔒" if tool.approval_required else "🔓"
                click.echo(f"  {status} {approval} {tool.name}: {tool.description}")
            
            # Model config
            click.echo(f"\n🤖 Model Configuration:")
            click.echo(f"  Model: {config.model_config.model_id}")
            click.echo(f"  Temperature: {config.model_config.temperature}")
            click.echo(f"  Max tokens: {config.model_config.max_tokens}")
            
            # Environment
            click.echo(f"\n🌍 Environment:")
            click.echo(f"  Working dir: {config.environment.working_directory}")
            click.echo(f"  Sandbox: {'✅' if config.environment.sandbox_enabled else '❌'}")
            click.echo(f"  Context hub: {'✅' if config.environment.context_hub_enabled else '❌'}")
            
        except ValueError as e:
            click.echo(f"❌ Error: {e}", err=True)
            sys.exit(1)
    
    asyncio.run(_show())


@agents.command()
@click.argument('agent_type', type=click.Choice(['conseil', 'voice', 'chat', 'planner']))
@click.argument('agent_id')
@click.argument('name')
@click.option('--user', 'user_id', required=True, help='User ID for the custom agent')
@click.option('--description', help='Description for the agent')
def create(agent_type: str, agent_id: str, name: str, user_id: str, description: Optional[str]):
    """Create a new custom agent configuration"""
    async def _create():
        manager = AgentConfigManager()
        
        type_enum = AgentType(agent_type)
        desc = description or f"Custom {agent_type} agent"
        
        try:
            new_id = await manager.create_custom_agent(
                base_type=type_enum,
                agent_id=agent_id,
                name=name,
                user_id=user_id,
                customizations={"description": desc}
            )
            
            click.echo(f"✅ Created custom agent: {new_id}")
            click.echo(f"   Name: {name}")
            click.echo(f"   Type: {agent_type}")
            click.echo(f"   User: {user_id}")
            
        except Exception as e:
            click.echo(f"❌ Error creating agent: {e}", err=True)
            sys.exit(1)
    
    asyncio.run(_create())


@agents.command()
@click.argument('source_id')
@click.argument('new_id')
@click.argument('new_name')
@click.option('--user', 'user_id', help='User ID for the cloned agent')
def clone(source_id: str, new_id: str, new_name: str, user_id: Optional[str]):
    """Clone an existing agent configuration"""
    async def _clone():
        manager = AgentConfigManager()
        
        try:
            cloned_id = await manager.clone_agent_config(
                source_id=source_id,
                new_id=new_id,
                new_name=new_name,
                user_id=user_id
            )
            
            click.echo(f"✅ Cloned agent configuration")
            click.echo(f"   Source: {source_id}")
            click.echo(f"   New ID: {cloned_id}")
            click.echo(f"   New name: {new_name}")
            
        except Exception as e:
            click.echo(f"❌ Error cloning agent: {e}", err=True)
            sys.exit(1)
    
    asyncio.run(_clone())


@agents.command()
@click.argument('agent_id')
@click.option('--user', 'user_id', help='User ID for user-specific configuration')
@click.option('--confirm', is_flag=True, help='Skip confirmation prompt')
def delete(agent_id: str, user_id: Optional[str], confirm: bool):
    """Delete an agent configuration"""
    async def _delete():
        manager = AgentConfigManager()
        
        if not confirm:
            if not click.confirm(f"Are you sure you want to delete agent '{agent_id}'?"):
                click.echo("Cancelled.")
                return
        
        try:
            success = await manager.delete_agent_config(agent_id, user_id)
            
            if success:
                click.echo(f"✅ Deleted agent configuration: {agent_id}")
            else:
                click.echo(f"❌ Failed to delete agent: {agent_id}", err=True)
                sys.exit(1)
                
        except Exception as e:
            click.echo(f"❌ Error deleting agent: {e}", err=True)
            sys.exit(1)
    
    asyncio.run(_delete())


@agents.command()
@click.argument('agent_id')
@click.option('--user', 'user_id', help='User ID for user-specific configuration')
@click.option('--editor', default='nano', help='Editor to use for editing')
def edit(agent_id: str, user_id: Optional[str], editor: str):
    """Edit an agent configuration interactively"""
    async def _edit():
        import tempfile
        import subprocess
        
        manager = AgentConfigManager()
        
        try:
            # Load current configuration
            config = await manager.get_agent_config(agent_id, user_id)
            
            # Create temporary file with current config
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(config.to_dict(), f, indent=2)
                temp_file = f.name
            
            # Open editor
            subprocess.run([editor, temp_file])
            
            # Read edited configuration
            with open(temp_file, 'r') as f:
                edited_data = json.load(f)
            
            # Update configuration
            success = await manager.update_agent_config(
                agent_id=agent_id,
                updates=edited_data,
                user_id=user_id
            )
            
            if success:
                click.echo(f"✅ Updated agent configuration: {agent_id}")
            else:
                click.echo(f"❌ Failed to update agent: {agent_id}", err=True)
                sys.exit(1)
            
            # Clean up temp file
            Path(temp_file).unlink()
            
        except Exception as e:
            click.echo(f"❌ Error editing agent: {e}", err=True)
            sys.exit(1)
    
    asyncio.run(_edit())


@agents.command()
@click.argument('agent_id')
@click.argument('output_file')
@click.option('--user', 'user_id', help='User ID for user-specific configuration')
def export(agent_id: str, output_file: str, user_id: Optional[str]):
    """Export an agent configuration to a file"""
    async def _export():
        manager = AgentConfigManager()
        
        try:
            config = await manager.get_agent_config(agent_id, user_id)
            
            with open(output_file, 'w') as f:
                json.dump(config.to_dict(), f, indent=2)
            
            click.echo(f"✅ Exported agent configuration to: {output_file}")
            
        except Exception as e:
            click.echo(f"❌ Error exporting agent: {e}", err=True)
            sys.exit(1)
    
    asyncio.run(_export())


@agents.command()
@click.argument('input_file')
@click.option('--user', 'user_id', help='User ID to import the configuration for')
def import_config(input_file: str, user_id: Optional[str]):
    """Import an agent configuration from a file"""
    async def _import():
        manager = AgentConfigManager()
        
        try:
            with open(input_file, 'r') as f:
                config_data = json.load(f)
            
            config = AgentConfig.from_dict(config_data)
            
            agent_id = await manager.create_agent_config(config, user_id)
            
            click.echo(f"✅ Imported agent configuration: {agent_id}")
            click.echo(f"   Name: {config.name}")
            click.echo(f"   Type: {config.type.value}")
            
        except Exception as e:
            click.echo(f"❌ Error importing agent: {e}", err=True)
            sys.exit(1)
    
    asyncio.run(_import())


@agents.command()
@click.argument('agent_id')
@click.option('--user', 'user_id', help='User ID for user-specific configuration')
@click.option('--verbose', is_flag=True, help='Show detailed validation results')
def validate(agent_id: str, user_id: Optional[str], verbose: bool):
    """Validate an agent configuration"""
    async def _validate():
        from .validation import AgentConfigValidator, print_validation_results
        
        manager = AgentConfigManager()
        validator = AgentConfigValidator()
        
        try:
            config = await manager.get_agent_config(agent_id, user_id)
            
            click.echo(f"🔍 Validating agent: {config.name}")
            click.echo("=" * 50)
            
            # Run validation
            results = await validator.validate_config(config)
            
            # Print results
            if verbose:
                print_validation_results(results)
            else:
                errors = len([r for r in results if r.severity == "error" and not r.is_valid])
                warnings = len([r for r in results if r.severity == "warning" and not r.is_valid])
                
                if errors == 0 and warnings == 0:
                    click.echo("✅ Configuration is valid")
                elif errors == 0:
                    click.echo(f"⚠️  Configuration has {warnings} warnings")
                else:
                    click.echo(f"❌ Configuration has {errors} errors and {warnings} warnings")
            
        except Exception as e:
            click.echo(f"❌ Error validating agent: {e}", err=True)
            sys.exit(1)
    
    asyncio.run(_validate())


@agents.command()
@click.argument('agent_id')
@click.option('--user', 'user_id', help='User ID for user-specific configuration')
@click.option('--input', 'test_inputs', multiple=True, help='Test inputs (can be specified multiple times)')
@click.option('--verbose', is_flag=True, help='Show detailed test results')
def test(agent_id: str, user_id: Optional[str], test_inputs: Tuple[str], verbose: bool):
    """Test an agent configuration with sample inputs"""
    async def _test():
        from .validation import AgentConfigTester, print_test_results
        
        manager = AgentConfigManager()
        tester = AgentConfigTester(manager)
        
        try:
            config = await manager.get_agent_config(agent_id, user_id)
            
            click.echo(f"🧪 Testing agent: {config.name}")
            click.echo("=" * 50)
            
            # Use provided inputs or defaults
            test_cases = list(test_inputs) if test_inputs else None
            
            # Run tests
            results = await tester.test_config(config, test_cases)
            
            # Print results
            if verbose:
                print_test_results(results)
            else:
                passed = len([r for r in results if r.passed])
                total = len(results)
                
                if passed == total:
                    click.echo(f"✅ All {total} tests passed")
                else:
                    click.echo(f"❌ {passed}/{total} tests passed")
            
        except Exception as e:
            click.echo(f"❌ Error testing agent: {e}", err=True)
            sys.exit(1)
    
    asyncio.run(_test())


@agents.command()
@click.argument('agent_id')
@click.option('--user', 'user_id', help='User ID for user-specific configuration')
@click.option('--fix', is_flag=True, help='Attempt to automatically fix common issues')
def check(agent_id: str, user_id: Optional[str], fix: bool):
    """Comprehensive validation and testing of an agent configuration"""
    async def _check():
        from .validation import validate_and_test_config, print_validation_results, print_test_results
        
        manager = AgentConfigManager()
        
        try:
            config = await manager.get_agent_config(agent_id, user_id)
            
            click.echo(f"🔍 Comprehensive check for agent: {config.name}")
            click.echo("=" * 50)
            
            # Run validation and testing
            validation_results, test_results = await validate_and_test_config(config)
            
            # Print results
            print_validation_results(validation_results)
            print_test_results(test_results)
            
            # Summary
            validation_errors = len([r for r in validation_results if r.severity == "error" and not r.is_valid])
            test_failures = len([r for r in test_results if not r.passed])
            
            click.echo(f"\n📊 Summary:")
            if validation_errors == 0 and test_failures == 0:
                click.echo("✅ Agent configuration is ready for use")
            else:
                click.echo(f"❌ Found {validation_errors} validation errors and {test_failures} test failures")
                
                if fix:
                    click.echo("\n🔧 Automatic fixes are not yet implemented")
                    click.echo("   Please review the issues above and update the configuration manually")
            
        except Exception as e:
            click.echo(f"❌ Error checking agent: {e}", err=True)
            sys.exit(1)
    
    asyncio.run(_check())


if __name__ == "__main__":
    agents()