"""
Local serverless runtime implementation.

Simulates serverless functions using asyncio tasks and subprocess.
"""

import asyncio
import json
import logging
import subprocess
import sys
import tempfile
import shutil
from typing import Any, Dict, List, Optional, Callable, Awaitable
from datetime import datetime
from pathlib import Path
import uuid
import inspect
import pickle
import base64
from concurrent.futures import ThreadPoolExecutor

from lightning_core.abstractions.serverless import (
    ServerlessRuntime, FunctionConfig, FunctionContext, FunctionResponse,
    FunctionHandler, TriggerType, RuntimeType
)
from lightning_core.abstractions.event_bus import EventMessage


logger = logging.getLogger(__name__)


class LocalFunction:
    """Local function wrapper."""
    
    def __init__(
        self,
        function_id: str,
        config: FunctionConfig,
        handler: Optional[FunctionHandler] = None,
        code_path: Optional[Path] = None
    ):
        self.function_id = function_id
        self.config = config
        self.handler = handler
        self.code_path = code_path
        self.invocation_count = 0
        self.last_invocation = None
        self.created_at = datetime.utcnow()
        self.logs: List[Dict[str, Any]] = []
        self._executor = ThreadPoolExecutor(max_workers=10)
    
    async def invoke(self, payload: Dict[str, Any]) -> FunctionResponse:
        """Invoke the function."""
        invocation_id = str(uuid.uuid4())
        self.invocation_count += 1
        self.last_invocation = datetime.utcnow()
        
        # Create context
        context = FunctionContext(
            function_name=self.config.name,
            invocation_id=invocation_id,
            trigger_type=TriggerType.MANUAL,
            trigger_data=payload,
            environment=self.config.environment_variables,
            metadata={"local": True}
        )
        
        # Log invocation
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "invocation_id": invocation_id,
            "type": "start",
            "payload": payload
        }
        self.logs.append(log_entry)
        
        try:
            if self.handler:
                # Use the provided handler
                response = await self.handler(context)
            else:
                # Execute external code
                response = await self._execute_external(context)
            
            # Log response
            log_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "invocation_id": invocation_id,
                "type": "end",
                "status_code": response.status_code,
                "is_error": response.is_error
            }
            self.logs.append(log_entry)
            
            return response
            
        except Exception as e:
            # Log error
            log_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "invocation_id": invocation_id,
                "type": "error",
                "error": str(e)
            }
            self.logs.append(log_entry)
            
            return FunctionResponse(
                status_code=500,
                is_error=True,
                error_message=str(e),
                logs=[f"Error: {e}"]
            )
    
    async def _execute_external(self, context: FunctionContext) -> FunctionResponse:
        """Execute external code (Python script, etc.)."""
        if not self.code_path or not self.code_path.exists():
            raise ValueError(f"Code path not found: {self.code_path}")
        
        # Prepare execution based on runtime
        if self.config.runtime == RuntimeType.PYTHON:
            return await self._execute_python(context)
        else:
            raise NotImplementedError(f"Runtime {self.config.runtime} not supported in local mode")
    
    async def _execute_python(self, context: FunctionContext) -> FunctionResponse:
        """Execute Python function."""
        # Create temporary directory for execution
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Copy code to temp directory
            if self.code_path.is_dir():
                shutil.copytree(self.code_path, temp_path / "function")
                work_dir = temp_path / "function"
            else:
                shutil.copy2(self.code_path, temp_path / "function.py")
                work_dir = temp_path
            
            # Write context to file
            context_file = work_dir / "context.json"
            with open(context_file, "w") as f:
                json.dump({
                    "function_name": context.function_name,
                    "invocation_id": context.invocation_id,
                    "trigger_type": context.trigger_type.value,
                    "trigger_data": context.trigger_data,
                    "environment": context.environment,
                    "metadata": context.metadata
                }, f)
            
            # Create wrapper script
            wrapper_script = work_dir / "wrapper.py"
            wrapper_code = """
import sys
import json
import importlib.util

# Load context
with open('context.json', 'r') as f:
    context_data = json.load(f)

# Create context object
class Context:
    def __init__(self, data):
        self.function_name = data['function_name']
        self.invocation_id = data['invocation_id']
        self.trigger_type = data['trigger_type']
        self.trigger_data = data['trigger_data']
        self.environment = data['environment']
        self.metadata = data['metadata']

context = Context(context_data)

# Load and execute handler
handler_parts = '{handler}'.split('.')
module_name = '.'.join(handler_parts[:-1])
function_name = handler_parts[-1]

if module_name:
    spec = importlib.util.spec_from_file_location(module_name, f'{module_name.replace(".", "/")}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    handler = getattr(module, function_name)
else:
    # Import from function.py
    spec = importlib.util.spec_from_file_location('function', 'function.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    handler = getattr(module, function_name)

# Execute handler
import asyncio
if asyncio.iscoroutinefunction(handler):
    result = asyncio.run(handler(context))
else:
    result = handler(context)

# Write result
with open('result.json', 'w') as f:
    if hasattr(result, 'to_dict'):
        json.dump(result.to_dict(), f)
    else:
        json.dump({
            'status_code': 200,
            'body': result,
            'headers': {},
            'is_error': False,
            'error_message': None,
            'logs': []
        }, f)
""".format(handler=self.config.handler)
            
            with open(wrapper_script, "w") as f:
                f.write(wrapper_code)
            
            # Prepare environment
            env = {
                **self.config.environment_variables,
                "PYTHONPATH": str(work_dir)
            }
            
            # Execute wrapper script
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "wrapper.py",
                cwd=str(work_dir),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            # Read result
            result_file = work_dir / "result.json"
            if result_file.exists():
                with open(result_file, "r") as f:
                    result_data = json.load(f)
                
                response = FunctionResponse(**result_data)
                if stderr:
                    response.logs.append(stderr.decode())
                return response
            else:
                # Error occurred
                return FunctionResponse(
                    status_code=500,
                    is_error=True,
                    error_message="Function execution failed",
                    logs=[
                        stdout.decode() if stdout else "",
                        stderr.decode() if stderr else ""
                    ]
                )


class LocalServerlessRuntime(ServerlessRuntime):
    """Local serverless runtime implementation."""
    
    def __init__(self, **kwargs: Any):
        self._functions: Dict[str, LocalFunction] = {}
        self._event_handlers: Dict[str, List[str]] = {}  # event_type -> function_ids
        self._base_url = kwargs.get("endpoint", "http://localhost:8080")
        self._function_dir = Path(kwargs.get("function_dir", "./functions"))
        self._function_dir.mkdir(parents=True, exist_ok=True)
    
    async def deploy_function(
        self,
        config: FunctionConfig,
        handler: Optional[FunctionHandler] = None
    ) -> str:
        """Deploy a serverless function."""
        function_id = f"local-{config.name}-{uuid.uuid4().hex[:8]}"
        
        # Save code if provided
        code_path = None
        if config.code_path:
            source_path = Path(config.code_path)
            if source_path.exists():
                # Copy code to function directory
                function_code_dir = self._function_dir / function_id
                function_code_dir.mkdir(parents=True, exist_ok=True)
                
                if source_path.is_dir():
                    shutil.copytree(source_path, function_code_dir, dirs_exist_ok=True)
                else:
                    shutil.copy2(source_path, function_code_dir / source_path.name)
                
                code_path = function_code_dir
        
        # Create local function
        local_function = LocalFunction(
            function_id=function_id,
            config=config,
            handler=handler,
            code_path=code_path
        )
        
        self._functions[function_id] = local_function
        
        # Register event handlers
        for trigger in config.triggers:
            if trigger["type"] == TriggerType.EVENT.value:
                for event_type in trigger["event_types"]:
                    if event_type not in self._event_handlers:
                        self._event_handlers[event_type] = []
                    self._event_handlers[event_type].append(function_id)
        
        logger.info(f"Deployed function {config.name} with ID {function_id}")
        return function_id
    
    async def invoke_function(
        self,
        function_id: str,
        payload: Dict[str, Any],
        async_invoke: bool = False
    ) -> FunctionResponse:
        """Invoke a serverless function."""
        if function_id not in self._functions:
            return FunctionResponse(
                status_code=404,
                is_error=True,
                error_message=f"Function {function_id} not found"
            )
        
        local_function = self._functions[function_id]
        
        if async_invoke:
            # Invoke asynchronously
            asyncio.create_task(local_function.invoke(payload))
            return FunctionResponse(
                status_code=202,
                body={"message": "Function invoked asynchronously"}
            )
        else:
            # Invoke synchronously
            return await local_function.invoke(payload)
    
    async def update_function(
        self,
        function_id: str,
        config: Optional[FunctionConfig] = None,
        handler: Optional[FunctionHandler] = None
    ) -> None:
        """Update function configuration or code."""
        if function_id not in self._functions:
            raise ValueError(f"Function {function_id} not found")
        
        local_function = self._functions[function_id]
        
        if config:
            # Update configuration
            local_function.config = config
            
            # Re-register event handlers
            # First, remove old handlers
            for event_handlers in self._event_handlers.values():
                if function_id in event_handlers:
                    event_handlers.remove(function_id)
            
            # Then add new handlers
            for trigger in config.triggers:
                if trigger["type"] == TriggerType.EVENT.value:
                    for event_type in trigger["event_types"]:
                        if event_type not in self._event_handlers:
                            self._event_handlers[event_type] = []
                        self._event_handlers[event_type].append(function_id)
        
        if handler:
            local_function.handler = handler
        
        logger.info(f"Updated function {function_id}")
    
    async def delete_function(self, function_id: str) -> None:
        """Delete a serverless function."""
        if function_id not in self._functions:
            return
        
        # Remove from event handlers
        for event_handlers in self._event_handlers.values():
            if function_id in event_handlers:
                event_handlers.remove(function_id)
        
        # Remove code directory
        local_function = self._functions[function_id]
        if local_function.code_path and local_function.code_path.exists():
            shutil.rmtree(local_function.code_path)
        
        # Remove function
        del self._functions[function_id]
        
        logger.info(f"Deleted function {function_id}")
    
    async def list_functions(
        self,
        name_prefix: Optional[str] = None,
        labels: Optional[Dict[str, str]] = None
    ) -> List[Dict[str, Any]]:
        """List deployed functions."""
        functions = []
        
        for function_id, local_function in self._functions.items():
            # Filter by name prefix
            if name_prefix and not local_function.config.name.startswith(name_prefix):
                continue
            
            # Filter by labels
            if labels:
                if not all(
                    local_function.config.labels.get(k) == v
                    for k, v in labels.items()
                ):
                    continue
            
            functions.append({
                "function_id": function_id,
                "name": local_function.config.name,
                "runtime": local_function.config.runtime.value,
                "memory_mb": local_function.config.memory_mb,
                "timeout_seconds": local_function.config.timeout_seconds,
                "created_at": local_function.created_at.isoformat(),
                "last_invocation": local_function.last_invocation.isoformat() if local_function.last_invocation else None,
                "invocation_count": local_function.invocation_count,
                "triggers": local_function.config.triggers,
                "labels": local_function.config.labels
            })
        
        return functions
    
    async def get_function(self, function_id: str) -> Optional[Dict[str, Any]]:
        """Get function information."""
        if function_id not in self._functions:
            return None
        
        local_function = self._functions[function_id]
        
        return {
            "function_id": function_id,
            "name": local_function.config.name,
            "runtime": local_function.config.runtime.value,
            "memory_mb": local_function.config.memory_mb,
            "timeout_seconds": local_function.config.timeout_seconds,
            "created_at": local_function.created_at.isoformat(),
            "last_invocation": local_function.last_invocation.isoformat() if local_function.last_invocation else None,
            "invocation_count": local_function.invocation_count,
            "triggers": local_function.config.triggers,
            "labels": local_function.config.labels,
            "environment_variables": list(local_function.config.environment_variables.keys())
        }
    
    async def get_function_logs(
        self,
        function_id: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        max_items: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get function execution logs."""
        if function_id not in self._functions:
            return []
        
        local_function = self._functions[function_id]
        logs = local_function.logs
        
        # Filter by time
        if start_time:
            start_dt = datetime.fromisoformat(start_time)
            logs = [
                log for log in logs
                if datetime.fromisoformat(log["timestamp"]) >= start_dt
            ]
        
        if end_time:
            end_dt = datetime.fromisoformat(end_time)
            logs = [
                log for log in logs
                if datetime.fromisoformat(log["timestamp"]) <= end_dt
            ]
        
        # Limit results
        if max_items:
            logs = logs[-max_items:]
        
        return logs
    
    async def set_function_concurrency(
        self,
        function_id: str,
        reserved_concurrency: Optional[int] = None
    ) -> None:
        """Set function concurrency limits."""
        if function_id not in self._functions:
            raise ValueError(f"Function {function_id} not found")
        
        # In local mode, this is a no-op
        # Could implement actual concurrency limiting if needed
        logger.info(f"Set concurrency for {function_id} to {reserved_concurrency} (no-op in local mode)")
    
    async def create_function_url(
        self,
        function_id: str,
        cors_config: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create a public URL for the function."""
        if function_id not in self._functions:
            raise ValueError(f"Function {function_id} not found")
        
        # Return a mock URL for local development
        return f"{self._base_url}/functions/{function_id}"
    
    async def register_event_source(
        self,
        function_id: str,
        event_source_config: Dict[str, Any]
    ) -> str:
        """Register an event source for the function."""
        if function_id not in self._functions:
            raise ValueError(f"Function {function_id} not found")
        
        # Create event source mapping ID
        mapping_id = f"mapping-{uuid.uuid4().hex[:8]}"
        
        # In local mode, we track event mappings in memory
        # Real implementation would integrate with event bus
        logger.info(f"Registered event source {mapping_id} for function {function_id}")
        
        return mapping_id
    
    async def unregister_event_source(
        self,
        event_source_id: str
    ) -> None:
        """Unregister an event source."""
        # In local mode, this is a no-op
        logger.info(f"Unregistered event source {event_source_id} (no-op in local mode)")
    
    async def handle_event(self, event: EventMessage) -> None:
        """Handle an event by invoking matching functions."""
        # Find functions registered for this event type
        function_ids = self._event_handlers.get(event.event_type, [])
        
        # Also check wildcard handlers
        for pattern, handlers in self._event_handlers.items():
            if "*" in pattern:
                import re
                regex_pattern = pattern.replace(".", r"\.").replace("*", ".*")
                if re.match(f"^{regex_pattern}$", event.event_type):
                    function_ids.extend(handlers)
        
        # Invoke all matching functions
        for function_id in set(function_ids):
            if function_id in self._functions:
                asyncio.create_task(
                    self.invoke_function(
                        function_id,
                        {
                            "event": event.to_json(),
                            "event_type": event.event_type,
                            "data": event.data
                        },
                        async_invoke=True
                    )
                )