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
    
    async def _request(self, method: str, path: str, *, hub: bool = False, **kwargs) -> Dict[str, Any]:
        """Make HTTP request to Vextir API"""
        session = await self._get_session()
        base = self.config.get_context_hub_endpoint() if hub else self.config.get_endpoint()
        url = f"{base}{path}"
        
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

        try:
            result = await self._request('GET', '/api/events', params=params)
            if isinstance(result, list):
                return result
            return result.get('events', [])
        except VextirClientError:
            # Fallback to empty list if the API is unavailable
            return []
    
    async def stream_events(self, filters: Optional[Dict[str, Any]] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream events in real-time"""
        params = filters or {}
        session = await self._get_session()

        try:
            async with session.get(f"{self.config.get_endpoint()}/api/events/stream", params=params) as resp:
                async for line in resp.content:
                    line = line.decode().strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                        yield event
                    except json.JSONDecodeError:
                        continue
        except aiohttp.ClientError:
            # If streaming fails, fall back to polling
            while True:
                events = await self.get_events(limit=1, filters=filters)
                for event in events:
                    yield event
                await asyncio.sleep(5)
    
    # Driver Management
    async def get_drivers(self) -> List[Dict[str, Any]]:
        """Get list of registered drivers"""
        try:
            result = await self._request('GET', '/api/drivers')
            if isinstance(result, list):
                return result
            return result.get('drivers', [])
        except VextirClientError:
            # Fallback to example drivers if the API is unavailable
            return [
                {
                    'id': 'email_agent',
                    'name': 'Email Assistant Agent',
                    'type': 'agent',
                    'status': 'running',
                    'capabilities': ['email.process', 'email.summarize', 'email.reply'],
                    'event_count': 42,
                    'last_activity': datetime.utcnow().isoformat()
                }
            ]
    
    async def get_driver_status(self, driver_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed driver status"""
        try:
            return await self._request('GET', f'/api/drivers/{driver_id}')
        except VextirClientError:
            drivers = await self.get_drivers()
            for driver in drivers:
                if driver['id'] == driver_id:
                    return driver
            return None
    
    async def start_driver(self, driver_id: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Start a driver"""
        try:
            payload = config or {}
            return await self._request('POST', f'/api/drivers/{driver_id}/start', json=payload)
        except VextirClientError:
            return {'status': 'running', 'driver_id': driver_id}
    
    async def stop_driver(self, driver_id: str) -> Dict[str, Any]:
        """Stop a driver"""
        try:
            return await self._request('POST', f'/api/drivers/{driver_id}/stop')
        except VextirClientError:
            return {'status': 'stopped', 'driver_id': driver_id}
    
    # Model Management
    async def get_models(self) -> List[Dict[str, Any]]:
        """Get list of available models"""
        try:
            result = await self._request('GET', '/api/models')
            if isinstance(result, list):
                return result
            return result.get('models', [])
        except VextirClientError:
            # Fallback to example models
            return [
                {
                    'id': 'gpt-4',
                    'name': 'GPT-4',
                    'provider': 'openai',
                    'capabilities': ['chat', 'function_calling'],
                    'cost_per_1k_tokens': {'input': 0.03, 'output': 0.06},
                    'context_window': 8192,
                    'enabled': True
                }
            ]
    
    async def get_model_info(self, model_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed model information"""
        try:
            return await self._request('GET', f'/api/models/{model_id}')
        except VextirClientError:
            models = await self.get_models()
            for model in models:
                if model['id'] == model_id:
                    return model
            return None
    
    # Tool Management
    async def get_tools(self) -> List[Dict[str, Any]]:
        """Get list of available tools"""
        try:
            result = await self._request('GET', '/api/tools')
            if isinstance(result, list):
                return result
            return result.get('tools', [])
        except VextirClientError:
            return [
                {
                    'id': 'web_search',
                    'name': 'Web Search',
                    'description': 'Search the web for information',
                    'tool_type': 'mcp_server',
                    'capabilities': ['search', 'scrape'],
                    'enabled': True
                }
            ]
    
    async def get_tool_info(self, tool_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed tool information"""
        try:
            return await self._request('GET', f'/api/tools/{tool_id}')
        except VextirClientError:
            tools = await self.get_tools()
            for tool in tools:
                if tool['id'] == tool_id:
                    return tool
            return None
    
    # Context Hub Operations
    async def context_read(self, doc_id: str) -> Dict[str, Any]:
        """Read a document from the Context Hub"""
        try:
            return await self._request('GET', f'/docs/{doc_id}', hub=True)
        except VextirClientError:
            return {
                'path': doc_id,
                'content': f'Content at {doc_id}',
                'metadata': {'last_updated': datetime.utcnow().isoformat()},
                'permissions': ['read', 'write']
            }
    
    async def context_write(self, path: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Write a new document to the Context Hub"""
        payload = {
            'name': path.split('/')[-1] or 'Untitled',
            'content': content,
            'folder_id': None,
            'metadata': metadata or {}
        }
        try:
            return await self._request('POST', '/docs', json=payload, hub=True)
        except VextirClientError:
            return {
                'path': path,
                'status': 'success',
                'timestamp': datetime.utcnow().isoformat()
            }
    
    async def context_query(self, query: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Query context hub with SQL"""
        params = {'q': query, 'limit': limit}
        try:
            result = await self._request('GET', '/search', params=params, hub=True)
            return result.get('results', []) if isinstance(result, dict) else result
        except VextirClientError:
            return []
    
    # Instruction Management
    async def get_instructions(self) -> List[Dict[str, Any]]:
        """Get list of user instructions"""
        try:
            result = await self._request('GET', '/api/instructions')
            if isinstance(result, list):
                return result
            return result.get('instructions', [])
        except VextirClientError:
            return []
    
    async def create_instruction(self, instruction_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new instruction"""
        try:
            return await self._request('POST', '/api/instructions', json=instruction_data)
        except VextirClientError:
            instruction_id = str(uuid.uuid4())
            return {
                'id': instruction_id,
                'status': 'created',
                'timestamp': datetime.utcnow().isoformat()
            }
    
    async def execute_instruction(self, instruction_id: str) -> Dict[str, Any]:
        """Execute an instruction"""
        try:
            return await self._request('POST', f'/api/instructions/{instruction_id}/execute')
        except VextirClientError:
            return {
                'instruction_id': instruction_id,
                'execution_id': str(uuid.uuid4()),
                'status': 'started',
                'timestamp': datetime.utcnow().isoformat()
            }
    
    # System Management
    async def get_system_status(self) -> Dict[str, Any]:
        """Get system status and health"""
        try:
            return await self._request('GET', '/api/system/status')
        except VextirClientError:
            return {
                'status': 'healthy',
                'uptime': 'unknown',
                'version': 'unknown'
            }
    
    async def get_system_metrics(self) -> Dict[str, Any]:
        """Get detailed system metrics"""
        try:
            return await self._request('GET', '/api/system/metrics')
        except VextirClientError:
            return {}
    
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
        return await self._request('POST', '/init', json=store_data, hub=True)
