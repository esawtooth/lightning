"""
Vextir CLI Configuration Management
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


class Config:
    """Configuration manager for Vextir CLI"""
    
    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file or self._get_default_config_path()
        self._config: Dict[str, Any] = {}
        self._load_config()
    
    def _get_default_config_path(self) -> str:
        """Get default configuration file path"""
        config_dir = Path.home() / ".vextir"
        config_dir.mkdir(exist_ok=True)
        return str(config_dir / "config.json")
    
    def _load_config(self):
        """Load configuration from file"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    self._config = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Failed to load config file {self.config_file}: {e}")
                self._config = {}
        else:
            self._config = self._get_default_config()
            self._save_config()
    
    def _save_config(self):
        """Save configuration to file"""
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(self._config, f, indent=2)
        except IOError as e:
            print(f"Warning: Failed to save config file {self.config_file}: {e}")
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration"""
        return {
            "endpoint": "https://func20015b83.azurewebsites.net",
            "auth": {
                "method": "azure_cli",
                "tenant_id": None,
                "client_id": "26583e36-a836-478f-a4af-7b6c6d355043",
                "scope": "https://graph.microsoft.com/.default"
            },
            "output": {
                "format": "table",
                "colors": True,
                "verbose": False
            },
            "event_streaming": {
                "buffer_size": 100,
                "timeout": 30
            },
            "context_hub": {
                "default_path": "/",
                "max_query_results": 1000,
                "endpoint": "http://10.0.1.4:3000"
            }
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        keys = key.split('.')
        value = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any):
        """Set configuration value"""
        keys = key.split('.')
        config = self._config
        
        # Navigate to the parent of the target key
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        # Set the value
        config[keys[-1]] = value
        self._save_config()
    
    def delete(self, key: str) -> bool:
        """Delete configuration key"""
        keys = key.split('.')
        config = self._config
        
        # Navigate to the parent of the target key
        for k in keys[:-1]:
            if k not in config:
                return False
            config = config[k]
        
        # Delete the key if it exists
        if keys[-1] in config:
            del config[keys[-1]]
            self._save_config()
            return True
        
        return False
    
    def list_keys(self, prefix: str = "") -> Dict[str, Any]:
        """List all configuration keys with optional prefix"""
        if not prefix:
            return self._config.copy()
        
        keys = prefix.split('.')
        config = self._config
        
        for k in keys:
            if isinstance(config, dict) and k in config:
                config = config[k]
            else:
                return {}
        
        return config if isinstance(config, dict) else {}
    
    def reset(self):
        """Reset configuration to defaults"""
        self._config = self._get_default_config()
        self._save_config()
    
    def validate(self) -> bool:
        """Validate configuration"""
        required_keys = ['endpoint']
        
        for key in required_keys:
            if not self.get(key):
                return False
        
        return True
    
    def get_endpoint(self) -> str:
        """Get API endpoint URL"""
        endpoint = self.get('endpoint')
        if not endpoint:
            raise ValueError("No endpoint configured. Use 'vextir config set endpoint <url>' to configure.")
        return endpoint.rstrip('/')
    
    def get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers"""
        auth_method = self.get('auth.method', 'azure_cli')
        
        if auth_method == 'azure_cli':
            # Use Azure CLI token
            try:
                import subprocess
                result = subprocess.run(
                    ['az', 'account', 'get-access-token', '--query', 'accessToken', '-o', 'tsv'],
                    capture_output=True,
                    text=True,
                    check=True
                )
                token = result.stdout.strip()
                return {'Authorization': f'Bearer {token}'}
            except (subprocess.CalledProcessError, FileNotFoundError):
                raise ValueError("Failed to get Azure CLI token. Please run 'az login' first.")
        
        elif auth_method == 'token':
            token = self.get('auth.token')
            if not token:
                raise ValueError("No auth token configured. Use 'vextir config set auth.token <token>' to configure.")
            return {'Authorization': f'Bearer {token}'}
        
        else:
            raise ValueError(f"Unsupported auth method: {auth_method}")
