# Flexible Agent System Summary

## Overview

I've created a flexible agent system that extends Conseil beyond its original coding-focused purpose. The system allows Conseil to operate in various professional roles while maintaining its core capabilities.

## Key Changes

### 1. **Flexible Agent Loop** (`agent-loop-flexible.ts`)
- Replaced hardcoded coding-specific system prompt with dynamic role-based prompts
- Added support for configurable job roles and custom descriptions
- Made sandboxing optional (controlled by `enableSandbox` parameter)
- Preserved all original functionality while adding flexibility

### 2. **Job Role System** (`job-roles.ts`)
- Defined 9 pre-configured professional roles:
  - Coding Assistant (preserves original functionality)
  - Legal Document Assistant
  - Personal Assistant
  - Financial Assistant
  - Research Assistant
  - Technical Writer
  - Project Manager
  - Data Analyst
  - Custom (user-defined)
- Each role includes:
  - Tailored description and capabilities
  - Role-specific guidelines
  - Recommended file patterns
  - Appropriate tool sets

### 3. **Flexible Command Handling** (`handle-exec-command-flexible.ts`)
- Modified to respect sandbox preferences
- Added `forceSandbox` and `disableSandbox` configuration options
- Maintains security by default while allowing flexibility when needed

### 4. **CLI Interface** (`cli-flexible.tsx`)
- New command-line interface with role selection
- Options for:
  - `--role`: Select job role
  - `--no-sandbox`: Disable sandboxing
  - `--description`: Custom role description
  - `--guidelines`: Custom role guidelines
  - `--list-roles`: Show available roles

### 5. **Lightning Integration** (`conseil_flexible_agent.py`)
- Python wrapper for Lightning integration
- Factory functions for common agent types
- Support for multiple agents with different roles in workflows

## Usage Examples

### Command Line
```bash
# Legal assistant
conseil --role legal --no-sandbox

# Personal assistant with auto-approval
conseil --role personal --no-sandbox --approval auto

# Custom HR assistant
conseil --role custom \
  --description "HR assistant for employee documentation" \
  --guidelines "Maintain confidentiality, follow compliance"
```

### Lightning Integration
```python
from lightning_agents import FlexibleConseilAgent, JobRole

# Create specialized agents
legal = FlexibleConseilAgent(role=JobRole.LEGAL, enable_sandbox=False)
research = FlexibleConseilAgent(role=JobRole.RESEARCH)
finance = FlexibleConseilAgent(role=JobRole.FINANCE)

# Use in workflows
contract_review = await legal.process_request("Review NDA for issues")
market_analysis = await research.process_request("Research AI trends")
```

## Benefits

1. **Versatility**: Single tool for multiple professional tasks
2. **Specialization**: Role-specific prompts and guidelines improve performance
3. **Safety**: Sandboxing remains default, with opt-out for trusted operations
4. **Integration**: Works seamlessly with Lightning's event-driven architecture
5. **Extensibility**: Easy to add new roles or customize existing ones

## Security Considerations

- Sandboxing is enabled by default for all roles
- `--no-sandbox` flag required for direct file system access
- Manual approval policy by default for sensitive roles (legal, finance)
- Auto-approval available for trusted operations

## Migration Path

The changes are designed to be backwards compatible:
- Original `AgentLoop` functionality preserved
- Default behavior remains coding-focused
- Existing integrations continue to work
- New features are opt-in via configuration

## Next Steps

To use the flexible agent system:

1. Install the updated Conseil package
2. Choose appropriate role for your task
3. Configure sandbox and approval settings
4. Run commands or integrate with Lightning workflows

The system is ready for use across various professional domains while maintaining the security and reliability of the original design.