"""Configuration system for MCP servers."""

import os
import yaml
import json
from pathlib import Path
from typing import Dict, List, Optional, Union
import logging

from .registry import MCPServerConfig
from .sandbox import SandboxConfig, SANDBOX_PRESETS
from .client import MCPConnectionType

logger = logging.getLogger(__name__)


class MCPConfigLoader:
    """Loader for MCP server configurations."""
    
    def __init__(self, config_dir: Optional[str] = None):
        if config_dir:
            self.config_dir = Path(config_dir)
        else:
            # Default config locations
            self.config_dir = Path.home() / ".lightning" / "mcp"
        
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # Standard config file names
        self.server_config_file = self.config_dir / "servers.yaml"
        self.security_config_file = self.config_dir / "security.yaml"
        self.sandbox_config_file = self.config_dir / "sandbox.yaml"
    
    def load_server_configs(self) -> List[MCPServerConfig]:
        """Load server configurations from YAML file."""
        configs = []
        
        if self.server_config_file.exists():
            try:
                with open(self.server_config_file, 'r') as f:
                    data = yaml.safe_load(f)
                    
                if data and 'mcp_servers' in data:
                    for server_data in data['mcp_servers']:
                        config = self._parse_server_config(server_data)
                        if config:
                            configs.append(config)
                            
                logger.info(f"Loaded {len(configs)} MCP server configurations")
                
            except Exception as e:
                logger.error(f"Error loading server configurations: {e}")
        
        # Also load from environment variables
        env_configs = self._load_from_env()
        configs.extend(env_configs)
        
        return configs
    
    def _parse_server_config(self, data: Dict) -> Optional[MCPServerConfig]:
        """Parse a single server configuration."""
        try:
            # Parse connection type
            connection_type = MCPConnectionType(data['connection_type'])
            
            # Parse sandbox config
            sandbox_data = data.get('sandbox_config', {})
            if isinstance(sandbox_data, str):
                # Use preset
                sandbox_config = SANDBOX_PRESETS.get(sandbox_data, SANDBOX_PRESETS['moderate'])
            else:
                # Parse full config
                sandbox_config = SandboxConfig.from_dict(sandbox_data)
            
            return MCPServerConfig(
                id=data['id'],
                name=data['name'],
                connection_type=connection_type,
                endpoint=data['endpoint'],
                capabilities=data.get('capabilities', []),
                sandbox_config=sandbox_config,
                access_scopes=data.get('access_scopes', ['AGENT_ALL']),
                auto_start=data.get('auto_start', False),
                restart_policy=data.get('restart_policy', 'never'),
                metadata=data.get('metadata', {})
            )
            
        except Exception as e:
            logger.error(f"Error parsing server config: {e}")
            return None
    
    def _load_from_env(self) -> List[MCPServerConfig]:
        """Load server configurations from environment variables."""
        configs = []
        
        # Look for MCP_SERVER_* environment variables
        for key, value in os.environ.items():
            if key.startswith('MCP_SERVER_') and key.endswith('_CONFIG'):
                server_id = key[11:-7].lower()  # Extract ID from MCP_SERVER_XXX_CONFIG
                
                try:
                    # Parse JSON config
                    data = json.loads(value)
                    data['id'] = data.get('id', server_id)
                    
                    config = self._parse_server_config(data)
                    if config:
                        configs.append(config)
                        logger.info(f"Loaded MCP server config from env: {server_id}")
                        
                except Exception as e:
                    logger.error(f"Error parsing env config {key}: {e}")
        
        return configs
    
    def save_server_config(self, config: MCPServerConfig) -> None:
        """Save a server configuration to file."""
        # Load existing configs
        existing_data = {}
        if self.server_config_file.exists():
            with open(self.server_config_file, 'r') as f:
                existing_data = yaml.safe_load(f) or {}
        
        # Ensure mcp_servers list exists
        if 'mcp_servers' not in existing_data:
            existing_data['mcp_servers'] = []
        
        # Update or add the config
        server_data = config.to_dict()
        
        # Find and update existing config or append new one
        updated = False
        for i, existing in enumerate(existing_data['mcp_servers']):
            if existing.get('id') == config.id:
                existing_data['mcp_servers'][i] = server_data
                updated = True
                break
        
        if not updated:
            existing_data['mcp_servers'].append(server_data)
        
        # Save back to file
        with open(self.server_config_file, 'w') as f:
            yaml.safe_dump(existing_data, f, default_flow_style=False)
        
        logger.info(f"Saved MCP server config: {config.id}")
    
    def remove_server_config(self, server_id: str) -> None:
        """Remove a server configuration from file."""
        if not self.server_config_file.exists():
            return
        
        with open(self.server_config_file, 'r') as f:
            data = yaml.safe_load(f) or {}
        
        if 'mcp_servers' in data:
            data['mcp_servers'] = [
                s for s in data['mcp_servers'] 
                if s.get('id') != server_id
            ]
        
        with open(self.server_config_file, 'w') as f:
            yaml.safe_dump(data, f, default_flow_style=False)
        
        logger.info(f"Removed MCP server config: {server_id}")
    
    def load_security_policies(self) -> List[Dict]:
        """Load security policies for MCP operations."""
        if not self.security_config_file.exists():
            # Return default policies
            return self._get_default_security_policies()
        
        try:
            with open(self.security_config_file, 'r') as f:
                data = yaml.safe_load(f)
                return data.get('mcp_security_policies', [])
        except Exception as e:
            logger.error(f"Error loading security policies: {e}")
            return self._get_default_security_policies()
    
    def _get_default_security_policies(self) -> List[Dict]:
        """Get default security policies."""
        return [
            {
                "name": "rate_limit_mcp_calls",
                "conditions": {"event_type": "mcp.tool.execute"},
                "actions": ["RESTRICT"],
                "restrictions": {
                    "max_calls_per_minute": 60,
                    "max_calls_per_hour": 1000
                }
            },
            {
                "name": "deny_sensitive_filesystem_access",
                "conditions": {
                    "event_type": "mcp.tool.execute",
                    "tool_name_pattern": "filesystem.*",
                    "parameter_path_pattern": "/etc/.*|/root/.*|.*/.ssh/.*"
                },
                "actions": ["DENY", "LOG", "NOTIFY"]
            },
            {
                "name": "sandbox_stdio_servers",
                "conditions": {
                    "event_type": "mcp.server.start",
                    "connection_type": "stdio"
                },
                "actions": ["SANDBOX"],
                "sandbox_config": {
                    "use_containers": True,
                    "network_isolation": True
                }
            }
        ]
    
    def create_example_configs(self) -> None:
        """Create example configuration files."""
        # Example server configuration
        example_servers = {
            'mcp_servers': [
                {
                    'id': 'filesystem_server',
                    'name': 'Filesystem MCP Server',
                    'connection_type': 'stdio',
                    'endpoint': 'npx @modelcontextprotocol/server-filesystem',
                    'capabilities': ['read', 'write', 'list'],
                    'sandbox_config': 'strict',
                    'access_scopes': ['AGENT_CONSEIL', 'AGENT_ALL'],
                    'auto_start': True,
                    'metadata': {
                        'description': 'Provides filesystem access with strict sandboxing'
                    }
                },
                {
                    'id': 'github_server',
                    'name': 'GitHub MCP Server',
                    'connection_type': 'sse',
                    'endpoint': 'https://mcp-github.example.com/sse',
                    'capabilities': ['search', 'read', 'create_issue'],
                    'sandbox_config': {
                        'enabled': True,
                        'use_containers': False,
                        'network_config': {
                            'policy': 'restricted',
                            'allowed_domains': ['api.github.com']
                        },
                        'filesystem_config': {
                            'policy': 'deny_all'
                        },
                        'resource_limits': {
                            'max_cpu_percent': 50,
                            'max_memory_mb': 512
                        }
                    },
                    'access_scopes': ['AGENT_CONSEIL'],
                    'auto_start': False
                }
            ]
        }
        
        example_file = self.config_dir / "servers.example.yaml"
        with open(example_file, 'w') as f:
            yaml.safe_dump(example_servers, f, default_flow_style=False)
        
        logger.info(f"Created example configuration at {example_file}")


# Configuration schema for validation
MCP_SERVER_SCHEMA = {
    "type": "object",
    "required": ["id", "name", "connection_type", "endpoint"],
    "properties": {
        "id": {"type": "string", "pattern": "^[a-zA-Z0-9_-]+$"},
        "name": {"type": "string"},
        "connection_type": {"type": "string", "enum": ["sse", "stdio", "websocket"]},
        "endpoint": {"type": "string"},
        "capabilities": {
            "type": "array",
            "items": {"type": "string"}
        },
        "sandbox_config": {
            "oneOf": [
                {"type": "string", "enum": ["strict", "moderate", "relaxed", "disabled"]},
                {"type": "object"}
            ]
        },
        "access_scopes": {
            "type": "array",
            "items": {"type": "string", "enum": ["AGENT_CONSEIL", "AGENT_VEX", "AGENT_ALL", "SYSTEM", "USER"]}
        },
        "auto_start": {"type": "boolean"},
        "restart_policy": {"type": "string", "enum": ["never", "on-failure", "always"]},
        "metadata": {"type": "object"}
    }
}