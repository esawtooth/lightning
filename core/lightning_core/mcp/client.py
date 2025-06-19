"""MCP client implementation supporting SSE and stdio connections."""

import asyncio
import json
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import aiohttp
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class MCPConnectionType(str, Enum):
    """Types of MCP server connections."""
    SSE = "sse"
    STDIO = "stdio"
    WEBSOCKET = "websocket"


@dataclass
class MCPTool:
    """Represents a tool exposed by an MCP server."""
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Optional[Dict[str, Any]] = None


@dataclass
class MCPCapability:
    """Represents a capability of an MCP server."""
    name: str
    version: str
    features: List[str]


class MCPClient(ABC):
    """Abstract base class for MCP client implementations."""
    
    def __init__(self, server_id: str, endpoint: str):
        self.server_id = server_id
        self.endpoint = endpoint
        self.connected = False
        self.capabilities: List[MCPCapability] = []
        self.tools: Dict[str, MCPTool] = {}
        
    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the MCP server."""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the MCP server."""
        pass
    
    @abstractmethod
    async def list_tools(self) -> List[MCPTool]:
        """List all available tools from the server."""
        pass
    
    @abstractmethod
    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Any:
        """Execute a tool on the MCP server."""
        pass
    
    @abstractmethod
    async def get_capabilities(self) -> List[MCPCapability]:
        """Get server capabilities."""
        pass


class SSEMCPClient(MCPClient):
    """MCP client for Server-Sent Events (SSE) connections."""
    
    def __init__(self, server_id: str, endpoint: str):
        super().__init__(server_id, endpoint)
        self.session: Optional[aiohttp.ClientSession] = None
        self._event_stream = None
        
    async def connect(self) -> None:
        """Establish SSE connection to the MCP server."""
        if self.connected:
            return
            
        try:
            self.session = aiohttp.ClientSession()
            
            # Initialize connection
            async with self.session.post(f"{self.endpoint}/initialize") as resp:
                if resp.status != 200:
                    raise ConnectionError(f"Failed to initialize MCP server: {resp.status}")
                    
                init_data = await resp.json()
                self.capabilities = [
                    MCPCapability(**cap) for cap in init_data.get("capabilities", [])
                ]
            
            # List tools
            await self._refresh_tools()
            
            self.connected = True
            logger.info(f"Connected to SSE MCP server {self.server_id} at {self.endpoint}")
            
        except Exception as e:
            if self.session:
                await self.session.close()
            raise ConnectionError(f"Failed to connect to MCP server: {e}")
    
    async def disconnect(self) -> None:
        """Close SSE connection."""
        if self.session:
            await self.session.close()
            self.session = None
        self.connected = False
        logger.info(f"Disconnected from SSE MCP server {self.server_id}")
    
    async def list_tools(self) -> List[MCPTool]:
        """List all available tools from the server."""
        if not self.connected:
            raise RuntimeError("Not connected to MCP server")
        
        await self._refresh_tools()
        return list(self.tools.values())
    
    async def _refresh_tools(self) -> None:
        """Refresh the tool list from the server."""
        async with self.session.get(f"{self.endpoint}/tools") as resp:
            if resp.status != 200:
                raise RuntimeError(f"Failed to list tools: {resp.status}")
                
            tools_data = await resp.json()
            self.tools = {
                tool["name"]: MCPTool(**tool) 
                for tool in tools_data.get("tools", [])
            }
    
    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Any:
        """Execute a tool on the MCP server via SSE."""
        if not self.connected:
            raise RuntimeError("Not connected to MCP server")
            
        if tool_name not in self.tools:
            raise ValueError(f"Tool '{tool_name}' not found on server")
        
        # Send tool execution request
        request_data = {
            "tool": tool_name,
            "parameters": parameters,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        async with self.session.post(
            f"{self.endpoint}/tools/execute",
            json=request_data,
            headers={"Accept": "text/event-stream"}
        ) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise RuntimeError(f"Tool execution failed: {error_text}")
            
            # Process SSE stream
            result = None
            async for line in resp.content:
                line = line.decode('utf-8').strip()
                if line.startswith("data: "):
                    data = json.loads(line[6:])
                    if data.get("type") == "result":
                        result = data.get("content")
                    elif data.get("type") == "error":
                        raise RuntimeError(f"Tool execution error: {data.get('error')}")
            
            return result
    
    async def get_capabilities(self) -> List[MCPCapability]:
        """Get server capabilities."""
        if not self.connected:
            raise RuntimeError("Not connected to MCP server")
        return self.capabilities


class StdioMCPClient(MCPClient):
    """MCP client for stdio (subprocess) connections."""
    
    def __init__(self, server_id: str, endpoint: str):
        super().__init__(server_id, endpoint)
        self.process: Optional[asyncio.subprocess.Process] = None
        self._read_task: Optional[asyncio.Task] = None
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._request_counter = 0
        
    async def connect(self) -> None:
        """Start the MCP server subprocess."""
        if self.connected:
            return
            
        try:
            # Parse command from endpoint
            cmd_parts = self.endpoint.split()
            
            # Start subprocess
            self.process = await asyncio.create_subprocess_exec(
                *cmd_parts,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Start reading from stdout
            self._read_task = asyncio.create_task(self._read_output())
            
            # Initialize connection
            response = await self._send_request("initialize", {})
            self.capabilities = [
                MCPCapability(**cap) for cap in response.get("capabilities", [])
            ]
            
            # List tools
            await self._refresh_tools()
            
            self.connected = True
            logger.info(f"Connected to stdio MCP server {self.server_id}")
            
        except Exception as e:
            if self.process:
                self.process.terminate()
                await self.process.wait()
            raise ConnectionError(f"Failed to connect to MCP server: {e}")
    
    async def disconnect(self) -> None:
        """Terminate the subprocess."""
        if self._read_task:
            self._read_task.cancel()
            
        if self.process:
            self.process.terminate()
            await self.process.wait()
            self.process = None
            
        self.connected = False
        logger.info(f"Disconnected from stdio MCP server {self.server_id}")
    
    async def _read_output(self) -> None:
        """Read output from the subprocess."""
        while self.connected and self.process:
            try:
                line = await self.process.stdout.readline()
                if not line:
                    break
                    
                # Parse JSON-RPC response
                try:
                    response = json.loads(line.decode('utf-8').strip())
                    request_id = response.get("id")
                    
                    if request_id in self._pending_requests:
                        future = self._pending_requests.pop(request_id)
                        if "error" in response:
                            future.set_exception(RuntimeError(response["error"]))
                        else:
                            future.set_result(response.get("result"))
                            
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from MCP server: {line}")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error reading from MCP server: {e}")
    
    async def _send_request(self, method: str, params: Dict[str, Any]) -> Any:
        """Send a JSON-RPC request to the subprocess."""
        if not self.process:
            raise RuntimeError("Not connected to MCP server")
            
        # Create request
        self._request_counter += 1
        request_id = str(self._request_counter)
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params
        }
        
        # Create future for response
        future = asyncio.Future()
        self._pending_requests[request_id] = future
        
        # Send request
        request_line = json.dumps(request) + "\n"
        self.process.stdin.write(request_line.encode('utf-8'))
        await self.process.stdin.drain()
        
        # Wait for response
        try:
            return await asyncio.wait_for(future, timeout=30.0)
        except asyncio.TimeoutError:
            self._pending_requests.pop(request_id, None)
            raise RuntimeError(f"Request timeout for method {method}")
    
    async def list_tools(self) -> List[MCPTool]:
        """List all available tools from the server."""
        if not self.connected:
            raise RuntimeError("Not connected to MCP server")
            
        await self._refresh_tools()
        return list(self.tools.values())
    
    async def _refresh_tools(self) -> None:
        """Refresh the tool list from the server."""
        response = await self._send_request("tools/list", {})
        self.tools = {
            tool["name"]: MCPTool(**tool)
            for tool in response.get("tools", [])
        }
    
    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Any:
        """Execute a tool on the MCP server via stdio."""
        if not self.connected:
            raise RuntimeError("Not connected to MCP server")
            
        if tool_name not in self.tools:
            raise ValueError(f"Tool '{tool_name}' not found on server")
        
        response = await self._send_request("tools/execute", {
            "tool": tool_name,
            "parameters": parameters
        })
        
        return response.get("result")
    
    async def get_capabilities(self) -> List[MCPCapability]:
        """Get server capabilities."""
        if not self.connected:
            raise RuntimeError("Not connected to MCP server")
        return self.capabilities


def create_mcp_client(
    server_id: str,
    connection_type: MCPConnectionType,
    endpoint: str
) -> MCPClient:
    """Factory function to create appropriate MCP client."""
    if connection_type == MCPConnectionType.SSE:
        return SSEMCPClient(server_id, endpoint)
    elif connection_type == MCPConnectionType.STDIO:
        return StdioMCPClient(server_id, endpoint)
    else:
        raise ValueError(f"Unsupported connection type: {connection_type}")