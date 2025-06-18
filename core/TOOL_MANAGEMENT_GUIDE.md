# Lightning Core Tool Management System

## Overview

Lightning Core now uses a **unified tool registry** with sophisticated access control to manage tools across different components. This eliminates the confusion of multiple registries and provides a single source of truth for all tool management.

## Architecture

### 1. Unified Tool Registry (`lightning_core/tools/registry.py`)

The central registry that manages all tools in the system with:

- **Access Control**: Define which tools are available to planner vs specific agents
- **User Permissions**: Support user-specific tool enablement  
- **Tool Types**: Native, MCP Server, API, Function, and Agent tools
- **Capabilities**: Semantic tagging for tool discovery

### 2. Access Control System

Tools are controlled through `AccessScope` definitions:

```python
class AccessScope(Enum):
    PLANNER = "planner"           # Available to workflow planner
    AGENT_CONSEIL = "agent_conseil"  # Available to Conseil agent  
    AGENT_VEX = "agent_vex"       # Available to Vex agent
    AGENT_ALL = "agent_all"       # Available to all agents
    SYSTEM = "system"             # System-level tools
    USER = "user"                 # User-facing tools
```

### 3. Component Bridges

- **Planner Bridge** (`lightning_core/tools/planner_bridge.py`): Provides planner-compatible interface
- **Vextir Bridge** (`lightning_core/tools/vextir_bridge.py`): Provides VextirOS-compatible interface

## Current Tool Access Configuration

### Tools Available to Planner (6 tools)
- `agent.conseil` - Requests Conseil agent for task execution
- `agent.vex` - Requests Vex agent for phone calls
- `llm.summarize` - Text summarization
- `cron.configure` - Cron job configuration
- `event.schedule.create` - Event scheduling
- `event.timer.start` - Timer events

### Tools Available to Agents Only (12 tools)
- `chat.sendTeamsMessage` - Teams messaging
- `email.send` - Email sending
- `web.search` - Web search
- `llm.general_prompt` - General LLM prompting
- Plus various context, calendar, and GitHub tools

## Managing Tools

### CLI Tool Management

Use the comprehensive CLI tool to view and manage the registry:

```bash
# List all tools in system
python -m lightning_core.tools.cli list-all

# List tools available to planner
python -m lightning_core.tools.cli list-planner

# List tools by type
python -m lightning_core.tools.cli list-by-type agent

# List tools by capability
python -m lightning_core.tools.cli list-by-capability web_search

# Show detailed tool information
python -m lightning_core.tools.cli show-tool web.search

# Compare what's available to planner vs all tools
python -m lightning_core.tools.cli compare

# Get help
python -m lightning_core.tools.cli --help
```

### Programmatic Access

```python
from lightning_core.tools.registry import get_tool_registry, AccessScope

# Get the unified registry
registry = get_tool_registry()

# Get tools for planner
planner_tools = registry.get_planner_tools()

# Get tools for specific agent
conseil_tools = registry.get_agent_tools("conseil")
vex_tools = registry.get_agent_tools("vex")

# Get tools by capability
search_tools = registry.list_tools(capability="web_search")

# Get tools by type
agent_tools = registry.list_tools(tool_type=ToolType.AGENT)
```

### Adding New Tools

```python
from lightning_core.tools.registry import get_tool_registry, ToolSpec, ToolType, AccessControl, AccessScope

# Create a new tool
new_tool = ToolSpec(
    id="my.custom.tool",
    name="My Custom Tool",
    description="Does something useful",
    tool_type=ToolType.NATIVE,
    inputs={"param1": "string", "param2": "integer"},
    produces=["event.custom.complete"],
    capabilities=["custom_capability"],
    access_control=AccessControl(scopes={AccessScope.AGENT_ALL})
)

# Register it
registry = get_tool_registry()
registry.register_tool(new_tool)
```

### Modifying Tool Access

To change which tools are available to the planner, modify the access control in `lightning_core/tools/registry.py`:

```python
# In _load_default_tools() method
my_tool = ToolSpec(
    id="my.tool",
    # ... other fields ...
    access_control=AccessControl(scopes={
        AccessScope.PLANNER,      # Available to planner
        AccessScope.AGENT_ALL     # Available to all agents
    })
)
```

### User-Specific Permissions

```python
# Create access control with user permissions
access_control = AccessControl(
    scopes={AccessScope.AGENT_ALL},
    user_permissions={
        "user123": True,   # Enabled for user123
        "user456": False   # Disabled for user456
    }
)
```

## Migration from Old System

### What Changed

1. **No More JSON File Dependency**: The planner no longer relies on `registry.tools.json`
2. **Unified Registry**: Single source of truth for all tools
3. **Access Control**: Systematic control over tool availability
4. **Better Organization**: Clear separation between planner and agent tools

### Backward Compatibility

- The planner registry interface remains the same
- JSON sync is still available but deprecated
- Existing code continues to work without changes

### Removing JSON File (Optional)

The `lightning_core/planner/registry.tools.json` file is no longer needed and can be removed:

```bash
rm lightning_core/planner/registry.tools.json
```

## Benefits

1. **Single Source of Truth**: All tools managed in one place
2. **Clear Access Control**: Explicit definition of what tools are available where
3. **User Permissions**: Support for user-specific tool access
4. **Better Maintainability**: No more sync issues between registries
5. **Extensible**: Easy to add new access scopes and permissions
6. **Type Safety**: Full type checking and validation

## Troubleshooting

### Tool Not Available to Planner

Check the tool's access control:

```python
registry = get_tool_registry()
tool = registry.get_tool("my.tool.id")
print(f"Access scopes: {tool.access_control.scopes}")
```

### Adding Tool to Planner

Modify the tool's access control to include `AccessScope.PLANNER`:

```python
tool.access_control.scopes.add(AccessScope.PLANNER)
```

### Debugging Tool Access

Use the CLI to understand tool availability:

```bash
python -m lightning_core.tools.cli show-tool my.tool.id
python -m lightning_core.tools.cli compare
```

## Future Enhancements

- **Dynamic Tool Loading**: Load tools from external sources
- **Role-Based Access**: More sophisticated permission system
- **Tool Versioning**: Support multiple versions of tools
- **Usage Analytics**: Track tool usage patterns
- **Tool Dependencies**: Define tool dependencies and requirements
