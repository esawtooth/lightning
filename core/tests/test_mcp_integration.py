"""Tests for MCP integration."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

from lightning_core.mcp import (
    MCPClient,
    MCPConnectionType,
    MCPRegistry,
    MCPServerConfig,
    MCPSecurityProxy,
    MCPSandbox,
    MCPToolAdapter,
    SANDBOX_PRESETS,
)
from lightning_core.mcp.client import MCPTool, create_mcp_client
from lightning_core.abstractions import RuntimeConfig, ExecutionMode
from lightning_core.abstractions.storage import ProviderFactory


class TestMCPClient:
    """Test MCP client implementations."""
    
    @pytest.mark.asyncio
    async def test_create_client(self):
        """Test client factory function."""
        # Test SSE client creation
        sse_client = create_mcp_client(
            "test_sse",
            MCPConnectionType.SSE,
            "https://example.com/mcp"
        )
        assert sse_client.server_id == "test_sse"
        assert sse_client.endpoint == "https://example.com/mcp"
        
        # Test stdio client creation
        stdio_client = create_mcp_client(
            "test_stdio",
            MCPConnectionType.STDIO,
            "echo hello"
        )
        assert stdio_client.server_id == "test_stdio"
        assert stdio_client.endpoint == "echo hello"
    
    @pytest.mark.asyncio
    async def test_sse_client_connection(self):
        """Test SSE client connection handling."""
        from lightning_core.mcp.client import SSEMCPClient
        
        client = SSEMCPClient("test_server", "https://example.com/mcp")
        
        # Mock the session
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "capabilities": [
                {"name": "tools", "version": "1.0", "features": ["list", "execute"]}
            ]
        })
        
        with patch('aiohttp.ClientSession') as mock_client_session:
            mock_client_session.return_value = mock_session
            mock_session.post.return_value.__aenter__.return_value = mock_response
            mock_session.get.return_value.__aenter__.return_value = mock_response
            
            # Test connection
            await client.connect()
            assert client.connected
            assert len(client.capabilities) == 1
            
            # Test disconnection
            await client.disconnect()
            assert not client.connected


class TestMCPRegistry:
    """Test MCP registry functionality."""
    
    @pytest.mark.asyncio
    async def test_registry_initialization(self):
        """Test registry initialization."""
        # Create mock storage
        config = RuntimeConfig(mode=ExecutionMode.LOCAL)
        storage = ProviderFactory.create_storage_provider(config)
        
        registry = MCPRegistry(storage)
        await registry.initialize()
        
        # Should start with no servers
        assert len(registry.list_servers()) == 0
    
    @pytest.mark.asyncio
    async def test_server_registration(self):
        """Test server registration and management."""
        config = RuntimeConfig(mode=ExecutionMode.LOCAL)
        storage = ProviderFactory.create_storage_provider(config)
        
        registry = MCPRegistry(storage)
        await registry.initialize()
        
        # Create server config
        server_config = MCPServerConfig(
            id="test_server",
            name="Test Server",
            connection_type=MCPConnectionType.STDIO,
            endpoint="echo test",
            capabilities=["test"],
            sandbox_config=SANDBOX_PRESETS["moderate"],
            access_scopes=["AGENT_ALL"],
            auto_start=False
        )
        
        # Register server
        await registry.register_server(server_config)
        
        # Verify registration
        servers = registry.list_servers()
        assert len(servers) == 1
        assert servers[0].id == "test_server"
        
        # Test get_server
        server = await registry.get_server("test_server")
        assert server is not None
        assert server.name == "Test Server"
        
        # Test unregister
        await registry.unregister_server("test_server")
        assert len(registry.list_servers()) == 0
    
    @pytest.mark.asyncio
    async def test_agent_scope_filtering(self):
        """Test filtering servers by agent scope."""
        config = RuntimeConfig(mode=ExecutionMode.LOCAL)
        storage = ProviderFactory.create_storage_provider(config)
        
        registry = MCPRegistry(storage)
        await registry.initialize()
        
        # Register servers with different scopes
        conseil_server = MCPServerConfig(
            id="conseil_server",
            name="Conseil Server",
            connection_type=MCPConnectionType.STDIO,
            endpoint="echo conseil",
            capabilities=["test"],
            sandbox_config=SANDBOX_PRESETS["moderate"],
            access_scopes=["AGENT_CONSEIL"],
            auto_start=False
        )
        
        all_server = MCPServerConfig(
            id="all_server",
            name="All Agents Server",
            connection_type=MCPConnectionType.STDIO,
            endpoint="echo all",
            capabilities=["test"],
            sandbox_config=SANDBOX_PRESETS["moderate"],
            access_scopes=["AGENT_ALL"],
            auto_start=False
        )
        
        await registry.register_server(conseil_server)
        await registry.register_server(all_server)
        
        # Test filtering
        conseil_servers = registry.get_servers_for_agent("conseil_agent_123")
        assert len(conseil_servers) == 2  # conseil_server and all_server
        
        vex_servers = registry.get_servers_for_agent("vex_agent_456")
        assert len(vex_servers) == 1  # only all_server
        assert vex_servers[0].id == "all_server"


class TestMCPSecurityProxy:
    """Test MCP security proxy."""
    
    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        """Test rate limiting functionality."""
        from lightning_core.vextir_os.security.manager import SecurityManager
        
        security_manager = SecurityManager()
        proxy = MCPSecurityProxy(security_manager)
        
        # Test rate limit checking
        result = await proxy.validate_tool_call(
            agent_id="test_agent",
            server_id="test_server",
            tool_name="test_tool",
            parameters={"test": "value"}
        )
        
        assert result.allowed  # First call should be allowed
        
        # Simulate many calls to trigger rate limit
        proxy.default_rate_limits["per_minute"] = 5  # Lower limit for testing
        
        for _ in range(5):
            await proxy.validate_tool_call(
                agent_id="test_agent",
                server_id="test_server",
                tool_name="test_tool",
                parameters={"test": "value"}
            )
        
        # Next call should be rate limited
        result = await proxy.validate_tool_call(
            agent_id="test_agent",
            server_id="test_server",
            tool_name="test_tool",
            parameters={"test": "value"}
        )
        
        assert not result.allowed
        assert "rate limit" in result.reason.lower()
    
    @pytest.mark.asyncio
    async def test_parameter_sanitization(self):
        """Test parameter sanitization."""
        from lightning_core.vextir_os.security.manager import SecurityManager
        
        security_manager = SecurityManager()
        proxy = MCPSecurityProxy(security_manager)
        
        # Test with sensitive parameters
        result = await proxy.validate_tool_call(
            agent_id="test_agent",
            server_id="test_server",
            tool_name="test_tool",
            parameters={
                "safe_param": "value",
                "api_key": "secret123",
                "password": "mypassword",
                "path": "/etc/shadow"
            }
        )
        
        # Check sanitization
        assert result.sanitized_parameters["safe_param"] == "value"
        assert result.sanitized_parameters["api_key"] == "[REDACTED]"
        assert result.sanitized_parameters["password"] == "[REDACTED]"
        assert result.sanitized_parameters["path"] == "[BLOCKED_PATH]"


class TestMCPSandbox:
    """Test MCP sandboxing functionality."""
    
    @pytest.mark.asyncio
    async def test_sandbox_creation(self):
        """Test sandbox environment creation."""
        sandbox = MCPSandbox()
        
        # Create environment with moderate preset
        env = await sandbox.create_environment(
            "test_server",
            SANDBOX_PRESETS["moderate"]
        )
        
        assert env.server_id == "test_server"
        assert env.sandbox_config.enabled
        assert env.temp_dir is not None
        
        # Cleanup
        await sandbox.destroy_environment("test_server")
        assert sandbox.get_environment("test_server") is None
    
    def test_sandbox_presets(self):
        """Test sandbox configuration presets."""
        # Test strict preset
        strict = SANDBOX_PRESETS["strict"]
        assert strict.enabled
        assert strict.use_containers
        assert strict.network_config.policy.value == "deny_all"
        assert strict.resource_limits.max_cpu_percent == 20
        
        # Test moderate preset
        moderate = SANDBOX_PRESETS["moderate"]
        assert moderate.enabled
        assert moderate.use_containers
        assert moderate.network_config.policy.value == "restricted"
        assert len(moderate.network_config.allowed_domains) > 0
        
        # Test relaxed preset
        relaxed = SANDBOX_PRESETS["relaxed"]
        assert relaxed.enabled
        assert not relaxed.use_containers
        assert relaxed.network_config.policy.value == "allow_all"
        
        # Test disabled preset
        disabled = SANDBOX_PRESETS["disabled"]
        assert not disabled.enabled


class TestMCPToolAdapter:
    """Test MCP tool adapter."""
    
    @pytest.mark.asyncio
    async def test_tool_discovery(self):
        """Test tool discovery and conversion."""
        # Create mock client
        mock_client = AsyncMock()
        mock_client.list_tools = AsyncMock(return_value=[
            MCPTool(
                name="read_file",
                description="Read a file from the filesystem",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"}
                    },
                    "required": ["path"]
                }
            ),
            MCPTool(
                name="search_code",
                description="Search for code patterns",
                input_schema={
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string"},
                        "path": {"type": "string"}
                    },
                    "required": ["pattern"]
                }
            )
        ])
        
        # Create server config
        server_config = MCPServerConfig(
            id="test_server",
            name="Test Server",
            connection_type=MCPConnectionType.STDIO,
            endpoint="test",
            capabilities=["test"],
            sandbox_config=SANDBOX_PRESETS["moderate"],
            access_scopes=["AGENT_ALL"],
            auto_start=False
        )
        
        # Create adapter
        adapter = MCPToolAdapter(mock_client, server_config)
        
        # Discover tools
        tools = await adapter.discover_tools()
        
        assert len(tools) == 2
        
        # Check first tool
        tool1 = tools[0]
        assert tool1.id == "mcp_test_server_read_file"
        assert tool1.name == "read_file"
        assert tool1.description == "Read a file from the filesystem"
        assert tool1.type.value == "MCP_SERVER"
        assert tool1.provider == "mcp:test_server"
        
        # Check metadata
        assert tool1.metadata["server_id"] == "test_server"
        assert tool1.metadata["original_name"] == "read_file"
    
    @pytest.mark.asyncio
    async def test_tool_execution(self):
        """Test tool execution through adapter."""
        # Create mock client
        mock_client = AsyncMock()
        mock_client.execute_tool = AsyncMock(return_value={"content": "file contents"})
        
        # Create server config
        server_config = MCPServerConfig(
            id="test_server",
            name="Test Server",
            connection_type=MCPConnectionType.STDIO,
            endpoint="test",
            capabilities=["test"],
            sandbox_config=SANDBOX_PRESETS["moderate"],
            access_scopes=["AGENT_ALL"],
            auto_start=False
        )
        
        # Create adapter
        adapter = MCPToolAdapter(mock_client, server_config)
        
        # Execute tool
        result = await adapter.execute_tool(
            "mcp_test_server_read_file",
            {"path": "/tmp/test.txt"}
        )
        
        assert result["success"]
        assert result["result"] == {"content": "file contents"}
        assert result["server_id"] == "test_server"
        assert result["tool_name"] == "read_file"
        
        # Verify client was called correctly
        mock_client.execute_tool.assert_called_once_with(
            "read_file",
            {"path": "/tmp/test.txt"}
        )


@pytest.mark.asyncio
async def test_end_to_end_integration():
    """Test end-to-end MCP integration."""
    from lightning_core.runtime import LightningRuntime
    
    # Create runtime
    config = RuntimeConfig(mode=ExecutionMode.LOCAL)
    runtime = LightningRuntime(config)
    
    # Initialize runtime
    await runtime.initialize()
    
    try:
        # Initialize MCP (without loading config files)
        await runtime.initialize_mcp(load_config=False)
        
        # Register a test server
        server_config = MCPServerConfig(
            id="test_integration_server",
            name="Test Integration Server",
            connection_type=MCPConnectionType.STDIO,
            endpoint="echo test",
            capabilities=["echo"],
            sandbox_config=SANDBOX_PRESETS["moderate"],
            access_scopes=["AGENT_ALL"],
            auto_start=False
        )
        
        await runtime.mcp_registry.register_server(server_config)
        
        # Verify registration
        servers = runtime.mcp_registry.list_servers()
        assert len(servers) == 1
        assert servers[0].id == "test_integration_server"
        
        # Test security proxy
        validation = await runtime.mcp_security_proxy.validate_tool_call(
            agent_id="test_agent",
            server_id="test_integration_server",
            tool_name="echo",
            parameters={"message": "hello"}
        )
        
        assert validation.allowed
        
    finally:
        # Cleanup
        await runtime.shutdown()