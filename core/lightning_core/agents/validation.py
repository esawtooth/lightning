"""
Agent Configuration Validation and Testing Framework

Provides validation and testing capabilities for agent configurations.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from .schemas import AgentConfig, AgentType, PromptConfig, ToolConfig
from .config_manager import AgentConfigManager

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of a validation check"""
    is_valid: bool
    message: str
    severity: str = "error"  # error, warning, info
    context: Optional[Dict[str, Any]] = None


@dataclass
class TestResult:
    """Result of a configuration test"""
    test_name: str
    passed: bool
    message: str
    execution_time: float
    details: Optional[Dict[str, Any]] = None


class AgentConfigValidator:
    """Validates agent configurations for correctness and best practices"""
    
    def __init__(self):
        self.validators = {
            "basic": self._validate_basic_structure,
            "prompt": self._validate_prompt_config,
            "tools": self._validate_tool_config,
            "model": self._validate_model_config,
            "environment": self._validate_environment_config,
            "behavior": self._validate_behavior_config,
            "type_specific": self._validate_type_specific,
        }
    
    async def validate_config(self, config: AgentConfig) -> List[ValidationResult]:
        """Validate an agent configuration"""
        results = []
        
        for validator_name, validator_func in self.validators.items():
            try:
                validator_results = await validator_func(config)
                if isinstance(validator_results, list):
                    results.extend(validator_results)
                else:
                    results.append(validator_results)
            except Exception as e:
                results.append(ValidationResult(
                    is_valid=False,
                    message=f"Validation error in {validator_name}: {str(e)}",
                    severity="error",
                    context={"validator": validator_name, "exception": str(e)}
                ))
        
        return results
    
    async def _validate_basic_structure(self, config: AgentConfig) -> List[ValidationResult]:
        """Validate basic configuration structure"""
        results = []
        
        # Check required fields
        if not config.id:
            results.append(ValidationResult(
                is_valid=False,
                message="Agent ID is required",
                severity="error"
            ))
        elif not config.id.replace("-", "").replace("_", "").isalnum():
            results.append(ValidationResult(
                is_valid=False,
                message="Agent ID should contain only alphanumeric characters, hyphens, and underscores",
                severity="warning"
            ))
        
        if not config.name:
            results.append(ValidationResult(
                is_valid=False,
                message="Agent name is required",
                severity="error"
            ))
        
        if not config.description:
            results.append(ValidationResult(
                is_valid=False,
                message="Agent description is recommended",
                severity="warning"
            ))
        
        # Check metadata
        if config.version and not config.version.count('.') >= 1:
            results.append(ValidationResult(
                is_valid=False,
                message="Version should follow semantic versioning (e.g., '1.0.0')",
                severity="warning"
            ))
        
        return results
    
    async def _validate_prompt_config(self, config: AgentConfig) -> List[ValidationResult]:
        """Validate system prompt configuration"""
        results = []
        prompt = config.system_prompt
        
        if not prompt:
            results.append(ValidationResult(
                is_valid=False,
                message="System prompt is required",
                severity="error"
            ))
            return results
        
        if not prompt.template:
            results.append(ValidationResult(
                is_valid=False,
                message="Prompt template is required",
                severity="error"
            ))
        else:
            # Check prompt length
            if len(prompt.template) < 50:
                results.append(ValidationResult(
                    is_valid=False,
                    message="Prompt template seems too short (< 50 characters)",
                    severity="warning"
                ))
            elif len(prompt.template) > 10000:
                results.append(ValidationResult(
                    is_valid=False,
                    message="Prompt template is very long (> 10,000 characters), consider breaking it down",
                    severity="warning"
                ))
            
            # Validate parameter placeholders
            try:
                # Check if template can be rendered with default parameters
                params = {name: param.default_value for name, param in prompt.parameters.items()}
                rendered = prompt.template.format(**params)
                
                results.append(ValidationResult(
                    is_valid=True,
                    message="Prompt template renders successfully with default parameters",
                    severity="info"
                ))
            except KeyError as e:
                results.append(ValidationResult(
                    is_valid=False,
                    message=f"Prompt template has undefined parameter: {e}",
                    severity="error"
                ))
            except Exception as e:
                results.append(ValidationResult(
                    is_valid=False,
                    message=f"Prompt template formatting error: {e}",
                    severity="error"
                ))
        
        # Validate parameters
        for param_name, param in prompt.parameters.items():
            if not param.name:
                results.append(ValidationResult(
                    is_valid=False,
                    message=f"Parameter {param_name} missing name",
                    severity="error"
                ))
            
            if not param.description:
                results.append(ValidationResult(
                    is_valid=False,
                    message=f"Parameter {param_name} missing description",
                    severity="warning"
                ))
            
            if param.type == "select" and not param.options:
                results.append(ValidationResult(
                    is_valid=False,
                    message=f"Select parameter {param_name} has no options",
                    severity="error"
                ))
        
        return results
    
    async def _validate_tool_config(self, config: AgentConfig) -> List[ValidationResult]:
        """Validate tool configurations"""
        results = []
        
        if not config.tools:
            results.append(ValidationResult(
                is_valid=False,
                message="No tools configured (this may be intentional)",
                severity="info"
            ))
            return results
        
        tool_names = set()
        for tool in config.tools:
            # Check for duplicate tool names
            if tool.name in tool_names:
                results.append(ValidationResult(
                    is_valid=False,
                    message=f"Duplicate tool name: {tool.name}",
                    severity="error"
                ))
            tool_names.add(tool.name)
            
            # Check tool name format
            if not tool.name.replace("_", "").isalnum():
                results.append(ValidationResult(
                    is_valid=False,
                    message=f"Tool name should be alphanumeric with underscores: {tool.name}",
                    severity="warning"
                ))
            
            # Validate tool-specific requirements
            if tool.name == "shell" and tool.enabled and not tool.sandbox:
                results.append(ValidationResult(
                    is_valid=False,
                    message="Shell tool should use sandbox for security",
                    severity="warning"
                ))
        
        return results
    
    async def _validate_model_config(self, config: AgentConfig) -> List[ValidationResult]:
        """Validate model configuration"""
        results = []
        model = config.model_config
        
        if not model:
            results.append(ValidationResult(
                is_valid=False,
                message="Model configuration is required",
                severity="error"
            ))
            return results
        
        # Validate temperature
        if not 0.0 <= model.temperature <= 2.0:
            results.append(ValidationResult(
                is_valid=False,
                message=f"Temperature should be between 0.0 and 2.0, got {model.temperature}",
                severity="error"
            ))
        
        # Validate max_tokens
        if model.max_tokens and model.max_tokens <= 0:
            results.append(ValidationResult(
                is_valid=False,
                message="Max tokens should be positive",
                severity="error"
            ))
        
        # Validate model ID format
        if not model.model_id:
            results.append(ValidationResult(
                is_valid=False,
                message="Model ID is required",
                severity="error"
            ))
        
        return results
    
    async def _validate_environment_config(self, config: AgentConfig) -> List[ValidationResult]:
        """Validate environment configuration"""
        results = []
        env = config.environment
        
        if not env:
            results.append(ValidationResult(
                is_valid=False,
                message="Environment configuration is required",
                severity="error"
            ))
            return results
        
        # Validate working directory
        if env.working_directory and not env.working_directory.startswith(("./", "/")):
            results.append(ValidationResult(
                is_valid=False,
                message="Working directory should be absolute or relative path",
                severity="warning"
            ))
        
        # Validate file patterns
        for pattern in env.file_patterns:
            if not pattern.startswith("*.") and not pattern.startswith("/"):
                results.append(ValidationResult(
                    is_valid=False,
                    message=f"File pattern should start with '*.' or '/': {pattern}",
                    severity="warning"
                ))
        
        return results
    
    async def _validate_behavior_config(self, config: AgentConfig) -> List[ValidationResult]:
        """Validate behavior configuration"""
        results = []
        behavior = config.behavior_config
        
        if not behavior:
            results.append(ValidationResult(
                is_valid=False,
                message="Behavior configuration is required",
                severity="error"
            ))
            return results
        
        # Validate timeout
        if behavior.timeout_seconds <= 0:
            results.append(ValidationResult(
                is_valid=False,
                message="Timeout should be positive",
                severity="error"
            ))
        elif behavior.timeout_seconds > 3600:
            results.append(ValidationResult(
                is_valid=False,
                message="Timeout is very long (> 1 hour), consider reducing it",
                severity="warning"
            ))
        
        # Validate max iterations
        if behavior.max_iterations <= 0:
            results.append(ValidationResult(
                is_valid=False,
                message="Max iterations should be positive",
                severity="error"
            ))
        elif behavior.max_iterations > 20:
            results.append(ValidationResult(
                is_valid=False,
                message="Max iterations is very high (> 20), consider reducing it",
                severity="warning"
            ))
        
        return results
    
    async def _validate_type_specific(self, config: AgentConfig) -> List[ValidationResult]:
        """Validate type-specific requirements"""
        results = []
        
        if config.type == AgentType.CONSEIL:
            # Conseil agents should have file-related tools
            tool_names = {tool.name for tool in config.tools if tool.enabled}
            if "apply_patch" not in tool_names and "shell" not in tool_names:
                results.append(ValidationResult(
                    is_valid=False,
                    message="Conseil agents should have file manipulation tools (apply_patch or shell)",
                    severity="warning"
                ))
        
        elif config.type == AgentType.CHAT:
            # Chat agents should have context tools
            tool_names = {tool.name for tool in config.tools if tool.enabled}
            context_tools = {"search_user_context", "read_document", "write_document"}
            if not any(tool in tool_names for tool in context_tools):
                results.append(ValidationResult(
                    is_valid=False,
                    message="Chat agents should have context hub tools",
                    severity="warning"
                ))
        
        elif config.type == AgentType.VOICE:
            # Voice agents should have audio modality
            if "audio" not in config.environment.modalities:
                results.append(ValidationResult(
                    is_valid=False,
                    message="Voice agents should support audio modality",
                    severity="error"
                ))
        
        elif config.type == AgentType.PLANNER:
            # Planner agents should use planning-optimized models
            if config.model_config.model_id not in ["o3-mini", "gpt-4o", "claude-3-sonnet"]:
                results.append(ValidationResult(
                    is_valid=False,
                    message="Consider using planning-optimized models (o3-mini, gpt-4o, claude-3-sonnet)",
                    severity="info"
                ))
        
        return results


class AgentConfigTester:
    """Tests agent configurations in a safe environment"""
    
    def __init__(self, config_manager: Optional[AgentConfigManager] = None):
        self.config_manager = config_manager or AgentConfigManager()
    
    async def test_config(self, config: AgentConfig, test_cases: Optional[List[str]] = None) -> List[TestResult]:
        """Test an agent configuration with sample inputs"""
        results = []
        
        # Default test cases if none provided
        if not test_cases:
            test_cases = [
                "Hello, can you help me?",
                "What can you do?",
                "Please explain your capabilities."
            ]
        
        # Test prompt rendering
        results.append(await self._test_prompt_rendering(config))
        
        # Test tool validation
        results.append(await self._test_tool_validation(config))
        
        # Test model configuration
        results.append(await self._test_model_config(config))
        
        # Test sample inputs (mock)
        for i, test_case in enumerate(test_cases):
            results.append(await self._test_sample_input(config, test_case, i))
        
        return results
    
    async def _test_prompt_rendering(self, config: AgentConfig) -> TestResult:
        """Test that the prompt can be rendered successfully"""
        import time
        start_time = time.time()
        
        try:
            prompt = config.system_prompt
            params = {name: param.default_value for name, param in prompt.parameters.items()}
            rendered = prompt.render(**params)
            
            execution_time = time.time() - start_time
            
            return TestResult(
                test_name="prompt_rendering",
                passed=True,
                message=f"Prompt rendered successfully ({len(rendered)} characters)",
                execution_time=execution_time,
                details={"rendered_length": len(rendered), "parameters_used": len(params)}
            )
        
        except Exception as e:
            execution_time = time.time() - start_time
            return TestResult(
                test_name="prompt_rendering",
                passed=False,
                message=f"Prompt rendering failed: {str(e)}",
                execution_time=execution_time,
                details={"error": str(e)}
            )
    
    async def _test_tool_validation(self, config: AgentConfig) -> TestResult:
        """Test tool configuration validity"""
        import time
        start_time = time.time()
        
        try:
            enabled_tools = [tool for tool in config.tools if tool.enabled]
            tool_names = [tool.name for tool in enabled_tools]
            
            execution_time = time.time() - start_time
            
            return TestResult(
                test_name="tool_validation",
                passed=True,
                message=f"Tool configuration valid ({len(enabled_tools)} enabled tools)",
                execution_time=execution_time,
                details={"enabled_tools": tool_names, "total_tools": len(config.tools)}
            )
        
        except Exception as e:
            execution_time = time.time() - start_time
            return TestResult(
                test_name="tool_validation",
                passed=False,
                message=f"Tool validation failed: {str(e)}",
                execution_time=execution_time,
                details={"error": str(e)}
            )
    
    async def _test_model_config(self, config: AgentConfig) -> TestResult:
        """Test model configuration"""
        import time
        start_time = time.time()
        
        try:
            model = config.model_config
            
            # Basic validation checks
            checks_passed = (
                0.0 <= model.temperature <= 2.0 and
                (model.max_tokens is None or model.max_tokens > 0) and
                bool(model.model_id)
            )
            
            execution_time = time.time() - start_time
            
            return TestResult(
                test_name="model_config",
                passed=checks_passed,
                message="Model configuration is valid" if checks_passed else "Model configuration has issues",
                execution_time=execution_time,
                details={
                    "model_id": model.model_id,
                    "temperature": model.temperature,
                    "max_tokens": model.max_tokens
                }
            )
        
        except Exception as e:
            execution_time = time.time() - start_time
            return TestResult(
                test_name="model_config",
                passed=False,
                message=f"Model config test failed: {str(e)}",
                execution_time=execution_time,
                details={"error": str(e)}
            )
    
    async def _test_sample_input(self, config: AgentConfig, test_input: str, test_index: int) -> TestResult:
        """Test with a sample input (mock simulation)"""
        import time
        start_time = time.time()
        
        try:
            # This is a mock test - in a real implementation, you might:
            # 1. Create a temporary agent instance
            # 2. Send the test input
            # 3. Validate the response
            
            # For now, we'll just validate that the prompt could handle this input
            prompt = config.system_prompt
            params = {name: param.default_value for name, param in prompt.parameters.items()}
            rendered_prompt = prompt.render(**params)
            
            # Simple heuristic: check if the rendered prompt is substantial
            response_likely = len(rendered_prompt) > 100 and any(
                keyword in rendered_prompt.lower() 
                for keyword in ["help", "assist", "you", "can", "do"]
            )
            
            execution_time = time.time() - start_time
            
            return TestResult(
                test_name=f"sample_input_{test_index}",
                passed=response_likely,
                message=f"Input '{test_input[:30]}...' would likely generate a response",
                execution_time=execution_time,
                details={
                    "input": test_input,
                    "prompt_length": len(rendered_prompt),
                    "has_helpful_keywords": response_likely
                }
            )
        
        except Exception as e:
            execution_time = time.time() - start_time
            return TestResult(
                test_name=f"sample_input_{test_index}",
                passed=False,
                message=f"Sample input test failed: {str(e)}",
                execution_time=execution_time,
                details={"input": test_input, "error": str(e)}
            )


async def validate_and_test_config(
    config: AgentConfig, 
    test_cases: Optional[List[str]] = None
) -> Tuple[List[ValidationResult], List[TestResult]]:
    """Validate and test an agent configuration"""
    
    validator = AgentConfigValidator()
    tester = AgentConfigTester()
    
    # Run validation and testing concurrently
    validation_task = validator.validate_config(config)
    testing_task = tester.test_config(config, test_cases)
    
    validation_results, test_results = await asyncio.gather(validation_task, testing_task)
    
    return validation_results, test_results


def print_validation_results(results: List[ValidationResult]):
    """Print validation results in a formatted way"""
    
    errors = [r for r in results if r.severity == "error" and not r.is_valid]
    warnings = [r for r in results if r.severity == "warning" and not r.is_valid]
    info = [r for r in results if r.severity == "info"]
    
    print(f"\n📋 Validation Results:")
    print(f"   ✅ {len([r for r in results if r.is_valid])} passed")
    print(f"   ❌ {len(errors)} errors")
    print(f"   ⚠️  {len(warnings)} warnings")
    print(f"   ℹ️  {len(info)} info")
    
    if errors:
        print(f"\n❌ Errors:")
        for result in errors:
            print(f"   • {result.message}")
    
    if warnings:
        print(f"\n⚠️  Warnings:")
        for result in warnings:
            print(f"   • {result.message}")
    
    if info:
        print(f"\nℹ️  Information:")
        for result in info:
            print(f"   • {result.message}")


def print_test_results(results: List[TestResult]):
    """Print test results in a formatted way"""
    
    passed = [r for r in results if r.passed]
    failed = [r for r in results if not r.passed]
    
    print(f"\n🧪 Test Results:")
    print(f"   ✅ {len(passed)} passed")
    print(f"   ❌ {len(failed)} failed")
    
    total_time = sum(r.execution_time for r in results)
    print(f"   ⏱️  Total execution time: {total_time:.3f}s")
    
    if failed:
        print(f"\n❌ Failed Tests:")
        for result in failed:
            print(f"   • {result.test_name}: {result.message}")
    
    if passed:
        print(f"\n✅ Passed Tests:")
        for result in passed:
            print(f"   • {result.test_name}: {result.message} ({result.execution_time:.3f}s)")