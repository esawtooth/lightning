"""
Vextir CLI API Client
"""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

import aiohttp
from aiohttp import ClientSession, ClientTimeout

from vextir_cli.config import Config


class VextirClientError(Exception):
    """Base exception for Vextir client errors"""
    pass


class VextirClient:
    """HTTP client for Vextir OS API"""
    
    def __init__(self, config: Config):
        self.config = config
        self.session: Optional[ClientSession] = None
        self._user_id: Optional[str] = None
    
    async def _get_session(self) -> ClientSession:
        """Get or create HTTP session"""
        if self.session is None or self.session.closed:
            timeout = ClientTimeout(total=30)
            self.session = ClientSession(
                timeout=timeout,
                headers=self.config.get_auth_headers()
            )
        return self.session
    
    async def close(self):
        """Close HTTP session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        """Make HTTP request to Vextir API"""
        session = await self._get_session()
        url = f"{self.config.get_endpoint()}{path}"
        
        try:
            async with session.request(method, url, **kwargs) as response:
                if response.status == 401:
                    raise VextirClientError("Authentication failed. Please check your credentials.")
                elif response.status == 403:
                    raise VextirClientError("Access denied. Insufficient permissions.")
                elif response.status == 404:
                    raise VextirClientError("Resource not found.")
                elif response.status >= 400:
                    error_text = await response.text()
                    raise VextirClientError(f"API error {response.status}: {error_text}")
                
                if response.content_type == 'application/json':
                    return await response.json()
                else:
                    return {"data": await response.text()}
                    
        except aiohttp.ClientError as e:
            raise VextirClientError(f"Network error: {e}")
    
    async def get_current_user_id(self) -> str:
        """Get current user ID"""
        if self._user_id is None:
            # Try to get from Azure CLI
            try:
                import subprocess
                result = subprocess.run(
                    ['az', 'account', 'show', '--query', 'user.name', '-o', 'tsv'],
                    capture_output=True,
                    text=True,
                    check=True
                )
                self._user_id = result.stdout.strip()
            except (subprocess.CalledProcessError, FileNotFoundError):
                # Fallback to a generated ID
                self._user_id = f"cli-user-{uuid.uuid4().hex[:8]}"
        
        return self._user_id
    
    # Event Management
    async def emit_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Emit an event to the event bus"""
        return await self._request('POST', '/api/PutEvent', json=event_data)
    
    async def get_events(self, limit: int = 50, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Get recent events"""
        params = {'limit': limit}
        if filters:
            params.update(filters)
        
        # For now, return mock data since we don't have a direct event history API
        # In a real implementation, this would call an actual API endpoint
        return []
    
    async def stream_events(self, filters: Optional[Dict[str, Any]] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream events in real-time"""
        # Mock implementation - in reality this would use WebSockets or Server-Sent Events
        # For demonstration, we'll simulate some events
        await asyncio.sleep(1)
        
        sample_events = [
            {
                'id': str(uuid.uuid4()),
                'type': 'system.startup',
                'source': 'vextir_os',
                'userID': await self.get_current_user_id(),
                'timestamp': datetime.utcnow().isoformat(),
                'metadata': {'message': 'System started successfully'}
            },
            {
                'id': str(uuid.uuid4()),
                'type': 'driver.registered',
                'source': 'driver_registry',
                'userID': await self.get_current_user_id(),
                'timestamp': datetime.utcnow().isoformat(),
                'metadata': {'driver_id': 'email_agent', 'type': 'agent'}
            }
        ]
        
        for event in sample_events:
            yield event
            await asyncio.sleep(2)
    
    # Driver Management
    async def get_drivers(self) -> List[Dict[str, Any]]:
        """Get list of registered drivers"""
        # Mock implementation - would call actual driver registry API
        return [
            {
                'id': 'email_agent',
                'name': 'Email Assistant Agent',
                'type': 'agent',
                'status': 'running',
                'capabilities': ['email.process', 'email.summarize', 'email.reply'],
                'event_count': 42,
                'last_activity': datetime.utcnow().isoformat()
            },
            {
                'id': 'web_search_tool',
                'name': 'Web Search Tool',
                'type': 'tool',
                'status': 'running',
                'capabilities': ['web.search', 'web.scrape'],
                'event_count': 15,
                'last_activity': datetime.utcnow().isoformat()
            },
            {
                'id': 'context_manager',
                'name': 'Context Hub Manager',
                'type': 'io',
                'status': 'running',
                'capabilities': ['context.read', 'context.write', 'context.query'],
                'event_count': 128,
                'last_activity': datetime.utcnow().isoformat()
            }
        ]
    
    async def get_driver_status(self, driver_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed driver status"""
        drivers = await self.get_drivers()
        for driver in drivers:
            if driver['id'] == driver_id:
                return driver
        return None
    
    async def start_driver(self, driver_id: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Start a driver"""
        # Mock implementation
        return {'status': 'running', 'driver_id': driver_id}
    
    async def stop_driver(self, driver_id: str) -> Dict[str, Any]:
        """Stop a driver"""
        # Mock implementation
        return {'status': 'stopped', 'driver_id': driver_id}
    
    # Model Management
    async def get_models(self) -> List[Dict[str, Any]]:
        """Get list of available models"""
        return [
            {
                'id': 'gpt-4',
                'name': 'GPT-4',
                'provider': 'openai',
                'capabilities': ['chat', 'function_calling'],
                'cost_per_1k_tokens': {'input': 0.03, 'output': 0.06},
                'context_window': 8192,
                'enabled': True
            },
            {
                'id': 'gpt-4-turbo',
                'name': 'GPT-4 Turbo',
                'provider': 'openai',
                'capabilities': ['chat', 'function_calling', 'vision'],
                'cost_per_1k_tokens': {'input': 0.01, 'output': 0.03},
                'context_window': 128000,
                'enabled': True
            },
            {
                'id': 'claude-3-sonnet',
                'name': 'Claude 3 Sonnet',
                'provider': 'anthropic',
                'capabilities': ['chat', 'vision'],
                'cost_per_1k_tokens': {'input': 0.003, 'output': 0.015},
                'context_window': 200000,
                'enabled': True
            }
        ]
    
    async def get_model_info(self, model_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed model information"""
        models = await self.get_models()
        for model in models:
            if model['id'] == model_id:
                return model
        return None
    
    # Tool Management
    async def get_tools(self) -> List[Dict[str, Any]]:
        """Get list of available tools"""
        return [
            {
                'id': 'web_search',
                'name': 'Web Search',
                'description': 'Search the web for information',
                'tool_type': 'mcp_server',
                'capabilities': ['search', 'scrape'],
                'enabled': True
            },
            {
                'id': 'context_read',
                'name': 'Context Read',
                'description': 'Read from user context hub',
                'tool_type': 'native',
                'capabilities': ['context_read', 'search'],
                'enabled': True
            },
            {
                'id': 'email_send',
                'name': 'Email Send',
                'description': 'Send emails via connected providers',
                'tool_type': 'native',
                'capabilities': ['email_send'],
                'enabled': True
            }
        ]
    
    async def get_tool_info(self, tool_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed tool information"""
        tools = await self.get_tools()
        for tool in tools:
            if tool['id'] == tool_id:
                return tool
        return None
    
    # Context Hub Operations
    async def context_read(self, path: str) -> Dict[str, Any]:
        """Read from context hub"""
        # Mock implementation
        return {
            'path': path,
            'content': f'Content at {path}',
            'metadata': {'last_updated': datetime.utcnow().isoformat()},
            'permissions': ['read', 'write']
        }
    
    async def context_write(self, path: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Write to context hub"""
        # Mock implementation
        return {
            'path': path,
            'status': 'success',
            'timestamp': datetime.utcnow().isoformat()
        }
    
    async def context_query(self, query: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Query context hub with SQL"""
        # Mock implementation
        return [
            {
                'path': '/Projects/Alpha',
                'content': 'Project Alpha details...',
                'score': 0.95
            },
            {
                'path': '/Tasks/Current',
                'content': 'Current task list...',
                'score': 0.87
            }
        ]
    
    # Instruction Management
    async def get_instructions(self) -> List[Dict[str, Any]]:
        """Get list of user instructions"""
        return [
            {
                'id': 'daily_standup',
                'name': 'Daily Standup Assistant',
                'description': 'Prepares daily standup summary',
                'status': 'active',
                'trigger': {'schedule': '0 9 * * MON-FRI'},
                'last_run': datetime.utcnow().isoformat()
            },
            {
                'id': 'email_summary',
                'name': 'Morning Email Summary',
                'description': 'Summarizes overnight emails',
                'status': 'active',
                'trigger': {'schedule': '0 8 * * *'},
                'last_run': datetime.utcnow().isoformat()
            }
        ]
    
    async def create_instruction(self, instruction_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new instruction"""
        # Mock implementation
        instruction_id = str(uuid.uuid4())
        return {
            'id': instruction_id,
            'status': 'created',
            'timestamp': datetime.utcnow().isoformat()
        }
    
    async def execute_instruction(self, instruction_id: str) -> Dict[str, Any]:
        """Execute an instruction"""
        # Mock implementation
        return {
            'instruction_id': instruction_id,
            'execution_id': str(uuid.uuid4()),
            'status': 'started',
            'timestamp': datetime.utcnow().isoformat()
        }
    
    # System Management
    async def get_system_status(self) -> Dict[str, Any]:
        """Get system status and health"""
        return {
            'status': 'healthy',
            'uptime': '2d 14h 32m',
            'version': '1.0.0',
            'components': {
                'event_bus': 'healthy',
                'driver_registry': 'healthy',
                'context_hub': 'healthy',
                'scheduler': 'healthy'
            },
            'metrics': {
                'events_processed': 1247,
                'active_drivers': 8,
                'error_rate': 0.02
            }
        }
    
    async def get_system_metrics(self) -> Dict[str, Any]:
        """Get detailed system metrics"""
        return {
            'events': {
                'total_processed': 1247,
                'events_per_minute': 2.3,
                'error_rate': 0.02,
                'avg_processing_time_ms': 145
            },
            'drivers': {
                'total_registered': 12,
                'active': 8,
                'stopped': 2,
                'error': 2
            },
            'resources': {
                'memory_usage_mb': 512,
                'cpu_usage_percent': 23.5,
                'disk_usage_gb': 2.1
            }
        }
    
    # Authentication Methods
    async def register_user(self, username: str, email: str, password: str) -> Dict[str, Any]:
        """Register a new user account"""
        user_data = {
            'username': username,
            'email': email,
            'password': password
        }
        return await self._request('POST', '/api/auth/register', json=user_data)
    
    async def login(self, username: str, password: str) -> Dict[str, Any]:
        """Login to Vextir OS"""
        login_data = {
            'username': username,
            'password': password
        }
        result = await self._request('POST', '/api/auth/login', json=login_data)
        
        # Store token in config for future requests
        if 'token' in result:
            self.config.set('auth.token', result['token'])
            self.config.set('auth.username', username)
        
        return result
    
    async def logout(self) -> Dict[str, Any]:
        """Logout from Vextir OS"""
        try:
            result = await self._request('POST', '/api/auth/logout')
        except VextirClientError:
            # Even if logout fails on server, clear local auth
            result = {'status': 'logged_out'}
        
        # Clear local auth data
        self.config.delete('auth.token')
        self.config.delete('auth.username')
        
        return result
    
    async def get_current_user(self) -> Dict[str, Any]:
        """Get current user information"""
        return await self._request('GET', '/api/auth/me')
    
    async def init_user_context_store(self, username: str) -> Dict[str, Any]:
        """Initialize user's Context Hub store"""
        store_data = {
            'username': username,
            'store_type': 'personal',
            'auto_create_folders': True
        }
        return await self._request('POST', '/api/context-hub/init', json=store_data)
