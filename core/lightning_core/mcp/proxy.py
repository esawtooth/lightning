"""Security proxy for MCP tool calls."""

import asyncio
import json
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Deque
import logging

from ..vextir_os.security.manager import SecurityManager
from ..vextir_os.security.models import SecurityContext

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of security validation."""
    allowed: bool
    reason: Optional[str] = None
    restrictions: Optional[Dict[str, Any]] = None
    sanitized_parameters: Optional[Dict[str, Any]] = None


@dataclass
class MCPCallRecord:
    """Record of an MCP tool call."""
    timestamp: datetime
    agent_id: str
    server_id: str
    tool_name: str
    parameters: Dict[str, Any]
    allowed: bool
    reason: Optional[str] = None
    execution_time_ms: Optional[int] = None
    result_size_bytes: Optional[int] = None


class RateLimiter:
    """Rate limiter for MCP tool calls."""
    
    def __init__(self):
        self.call_history: Dict[str, Deque[datetime]] = {}
        self._lock = asyncio.Lock()
    
    async def check_rate_limit(self,
                              key: str,
                              max_calls: int,
                              window_seconds: int) -> bool:
        """Check if a call is within rate limits."""
        async with self._lock:
            now = datetime.utcnow()
            cutoff = now - timedelta(seconds=window_seconds)
            
            # Get or create history for this key
            if key not in self.call_history:
                self.call_history[key] = deque()
            
            history = self.call_history[key]
            
            # Remove old entries
            while history and history[0] < cutoff:
                history.popleft()
            
            # Check limit
            if len(history) >= max_calls:
                return False
            
            # Add current call
            history.append(now)
            return True


class ParameterSanitizer:
    """Sanitize parameters for MCP tool calls."""
    
    # Patterns that might indicate sensitive data
    SENSITIVE_PATTERNS = [
        r"password",
        r"secret",
        r"token",
        r"api[_-]?key",
        r"private[_-]?key",
        r"auth",
        r"credential",
    ]
    
    # Dangerous path patterns
    DANGEROUS_PATHS = [
        r"\.\.\/",  # Path traversal
        r"\/etc\/shadow",
        r"\/etc\/passwd",
        r"\.ssh\/",
        r"\.aws\/",
        r"\.config\/",
        r"\/root\/",
    ]
    
    @classmethod
    def sanitize_parameters(cls, 
                          tool_name: str,
                          parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize parameters to remove sensitive or dangerous content."""
        import re
        
        sanitized = parameters.copy()
        
        # Check for sensitive keys
        for key in list(sanitized.keys()):
            for pattern in cls.SENSITIVE_PATTERNS:
                if re.search(pattern, key, re.IGNORECASE):
                    sanitized[key] = "[REDACTED]"
                    logger.warning(f"Redacted sensitive parameter: {key}")
        
        # Check for dangerous paths in string values
        def check_value(value: Any) -> Any:
            if isinstance(value, str):
                for pattern in cls.DANGEROUS_PATHS:
                    if re.search(pattern, value):
                        logger.warning(f"Dangerous path pattern detected: {pattern}")
                        return "[BLOCKED_PATH]"
                return value
            elif isinstance(value, dict):
                return {k: check_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [check_value(item) for item in value]
            return value
        
        sanitized = check_value(sanitized)
        
        return sanitized


class MCPSecurityProxy:
    """Security proxy that intercepts and validates all MCP tool calls."""
    
    def __init__(self, security_manager: SecurityManager):
        self.security_manager = security_manager
        self.rate_limiter = RateLimiter()
        self.call_history: Deque[MCPCallRecord] = deque(maxlen=10000)
        self._lock = asyncio.Lock()
        
        # Default rate limits
        self.default_rate_limits = {
            "per_minute": 60,
            "per_hour": 1000,
            "per_day": 10000,
        }
    
    async def validate_tool_call(self,
                                agent_id: str,
                                server_id: str,
                                tool_name: str,
                                parameters: Dict[str, Any],
                                context: Optional[SecurityContext] = None) -> ValidationResult:
        """Validate a tool call against security policies."""
        start_time = datetime.utcnow()
        
        try:
            # Create security context if not provided
            if not context:
                context = SecurityContext(
                    user_id=agent_id,
                    session_id=f"{agent_id}_{int(start_time.timestamp())}",
                    ip_address="127.0.0.1",  # Local for agents
                    user_agent=f"Agent/{agent_id}",
                )
            
            # Check rate limits
            rate_limit_result = await self._check_rate_limits(agent_id, server_id, tool_name)
            if not rate_limit_result.allowed:
                return rate_limit_result
            
            # Sanitize parameters
            sanitized_params = ParameterSanitizer.sanitize_parameters(tool_name, parameters)
            
            # Check security policies
            policy_result = await self._check_security_policies(
                agent_id, server_id, tool_name, sanitized_params, context
            )
            
            if not policy_result.allowed:
                return policy_result
            
            # Apply additional restrictions based on tool type
            restricted_params = await self._apply_tool_restrictions(
                tool_name, sanitized_params, policy_result.restrictions
            )
            
            # Record the call
            await self._record_call(
                agent_id, server_id, tool_name, parameters,
                allowed=True, start_time=start_time
            )
            
            return ValidationResult(
                allowed=True,
                sanitized_parameters=restricted_params,
                restrictions=policy_result.restrictions
            )
            
        except Exception as e:
            logger.error(f"Error validating MCP tool call: {e}")
            await self._record_call(
                agent_id, server_id, tool_name, parameters,
                allowed=False, reason=str(e), start_time=start_time
            )
            return ValidationResult(allowed=False, reason=f"Validation error: {e}")
    
    async def _check_rate_limits(self, 
                               agent_id: str,
                               server_id: str,
                               tool_name: str) -> ValidationResult:
        """Check rate limits for the tool call."""
        # Check per-agent limits
        agent_key = f"agent:{agent_id}"
        if not await self.rate_limiter.check_rate_limit(
            agent_key, self.default_rate_limits["per_minute"], 60
        ):
            return ValidationResult(allowed=False, reason="Agent rate limit exceeded (per minute)")
        
        if not await self.rate_limiter.check_rate_limit(
            agent_key, self.default_rate_limits["per_hour"], 3600
        ):
            return ValidationResult(allowed=False, reason="Agent rate limit exceeded (per hour)")
        
        # Check per-server limits
        server_key = f"server:{server_id}"
        if not await self.rate_limiter.check_rate_limit(
            server_key, self.default_rate_limits["per_minute"] * 2, 60
        ):
            return ValidationResult(allowed=False, reason="Server rate limit exceeded")
        
        # Check per-tool limits (more restrictive for certain tools)
        if tool_name in ["execute_command", "write_file", "delete_file"]:
            tool_key = f"tool:{tool_name}"
            if not await self.rate_limiter.check_rate_limit(tool_key, 10, 60):
                return ValidationResult(
                    allowed=False,
                    reason=f"Rate limit exceeded for sensitive tool: {tool_name}"
                )
        
        return ValidationResult(allowed=True)
    
    async def _check_security_policies(self,
                                     agent_id: str,
                                     server_id: str,
                                     tool_name: str,
                                     parameters: Dict[str, Any],
                                     context: SecurityContext) -> ValidationResult:
        """Check security policies for the tool call."""
        # Create event data for policy evaluation
        event_data = {
            "event_type": "mcp.tool.execute",
            "agent_id": agent_id,
            "server_id": server_id,
            "tool_name": tool_name,
            "parameters": parameters,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        # Evaluate policies
        result = await self.security_manager.evaluate_policies(
            event_type="mcp.tool.execute",
            event_data=event_data,
            context=context
        )
        
        if not result.allowed:
            return ValidationResult(
                allowed=False,
                reason=result.reason or "Blocked by security policy",
                restrictions=result.applied_restrictions
            )
        
        return ValidationResult(
            allowed=True,
            restrictions=result.applied_restrictions
        )
    
    async def _apply_tool_restrictions(self,
                                     tool_name: str,
                                     parameters: Dict[str, Any],
                                     restrictions: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Apply tool-specific restrictions to parameters."""
        restricted_params = parameters.copy()
        
        # Apply general restrictions
        if restrictions:
            # Example: Limit file operations to specific directories
            if "allowed_paths" in restrictions and "path" in restricted_params:
                path = restricted_params["path"]
                allowed = any(path.startswith(p) for p in restrictions["allowed_paths"])
                if not allowed:
                    restricted_params["path"] = restrictions["allowed_paths"][0] + "/restricted"
            
            # Example: Limit command execution
            if "allowed_commands" in restrictions and "command" in restricted_params:
                command = restricted_params["command"].split()[0]
                if command not in restrictions["allowed_commands"]:
                    restricted_params["command"] = "echo 'Command not allowed'"
        
        # Tool-specific restrictions
        if tool_name == "read_file":
            # Limit file size for reads
            restricted_params["max_size"] = min(
                restricted_params.get("max_size", 1048576),  # 1MB default
                1048576  # 1MB max
            )
        elif tool_name == "write_file":
            # Limit file size for writes
            if "content" in restricted_params:
                max_size = 1048576  # 1MB
                if len(restricted_params["content"]) > max_size:
                    restricted_params["content"] = restricted_params["content"][:max_size]
        
        return restricted_params
    
    async def _record_call(self,
                         agent_id: str,
                         server_id: str,
                         tool_name: str,
                         parameters: Dict[str, Any],
                         allowed: bool,
                         reason: Optional[str] = None,
                         start_time: Optional[datetime] = None) -> None:
        """Record a tool call for auditing."""
        if start_time:
            execution_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        else:
            execution_time_ms = None
        
        record = MCPCallRecord(
            timestamp=datetime.utcnow(),
            agent_id=agent_id,
            server_id=server_id,
            tool_name=tool_name,
            parameters=parameters,
            allowed=allowed,
            reason=reason,
            execution_time_ms=execution_time_ms,
        )
        
        async with self._lock:
            self.call_history.append(record)
        
        # Log significant events
        if not allowed:
            logger.warning(
                f"MCP tool call blocked: agent={agent_id}, server={server_id}, "
                f"tool={tool_name}, reason={reason}"
            )
        elif execution_time_ms and execution_time_ms > 5000:
            logger.warning(
                f"Slow MCP tool call: agent={agent_id}, server={server_id}, "
                f"tool={tool_name}, time={execution_time_ms}ms"
            )
    
    async def get_call_history(self,
                             agent_id: Optional[str] = None,
                             server_id: Optional[str] = None,
                             limit: int = 100) -> List[MCPCallRecord]:
        """Get call history with optional filtering."""
        async with self._lock:
            history = list(self.call_history)
        
        # Filter by agent
        if agent_id:
            history = [r for r in history if r.agent_id == agent_id]
        
        # Filter by server
        if server_id:
            history = [r for r in history if r.server_id == server_id]
        
        # Return most recent
        return history[-limit:]
    
    async def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about MCP tool usage."""
        async with self._lock:
            history = list(self.call_history)
        
        if not history:
            return {
                "total_calls": 0,
                "blocked_calls": 0,
                "agents": {},
                "servers": {},
                "tools": {},
            }
        
        # Calculate statistics
        total_calls = len(history)
        blocked_calls = sum(1 for r in history if not r.allowed)
        
        # Per-agent stats
        agent_stats = {}
        for record in history:
            if record.agent_id not in agent_stats:
                agent_stats[record.agent_id] = {
                    "total": 0,
                    "blocked": 0,
                    "avg_execution_time_ms": 0,
                }
            
            stats = agent_stats[record.agent_id]
            stats["total"] += 1
            if not record.allowed:
                stats["blocked"] += 1
            if record.execution_time_ms:
                # Running average
                stats["avg_execution_time_ms"] = (
                    (stats["avg_execution_time_ms"] * (stats["total"] - 1) + 
                     record.execution_time_ms) / stats["total"]
                )
        
        # Per-server stats
        server_stats = {}
        for record in history:
            if record.server_id not in server_stats:
                server_stats[record.server_id] = {"total": 0, "blocked": 0}
            
            server_stats[record.server_id]["total"] += 1
            if not record.allowed:
                server_stats[record.server_id]["blocked"] += 1
        
        # Per-tool stats
        tool_stats = {}
        for record in history:
            if record.tool_name not in tool_stats:
                tool_stats[record.tool_name] = {"total": 0, "blocked": 0}
            
            tool_stats[record.tool_name]["total"] += 1
            if not record.allowed:
                tool_stats[record.tool_name]["blocked"] += 1
        
        return {
            "total_calls": total_calls,
            "blocked_calls": blocked_calls,
            "block_rate": blocked_calls / total_calls if total_calls > 0 else 0,
            "agents": agent_stats,
            "servers": server_stats,
            "tools": tool_stats,
            "time_range": {
                "start": history[0].timestamp.isoformat(),
                "end": history[-1].timestamp.isoformat(),
            }
        }