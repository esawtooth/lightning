# Lightning Planner CLI Guide

The Lightning Planner CLI provides a comprehensive command-line interface for generating, validating, and visualizing workflow plans using natural language instructions.

## Installation

```bash
# Install the package with visualization support
pip install lightning-core[visualization]

# Or install all optional dependencies
pip install lightning-core[all]
```

## Quick Start

```bash
# List available tools and events
lightning-planner list-tools
lightning-planner list-events

# Generate a plan from natural language
lightning-planner generate "Create a daily email summary workflow" -o my_plan.json

# Validate the generated plan
lightning-planner validate my_plan.json

# Create a visual diagram
lightning-planner mermaid my_plan.json -o my_plan_diagram.md
```

## Commands

### 1. Generate Plans

Generate workflow plans from natural language instructions:

```bash
# Basic generation (outputs to stdout)
lightning-planner generate "Create a weekly report generation workflow"

# Save to file
lightning-planner generate "Customer feedback analysis pipeline" -o feedback_plan.json

# Verbose output
lightning-planner generate "Daily monitoring system" -o monitor.json -v
```

**Example Instructions:**
- "Create a daily email summary workflow using LLM summarization"
- "Build a customer outreach campaign with phone calls and Teams notifications"
- "Set up a weekly content creation pipeline with research and distribution"
- "Design a system monitoring workflow that analyzes alerts and notifies teams"

### 2. Validate Plans

Validate existing plan files against all validation rules:

```bash
# Basic validation
lightning-planner validate my_plan.json

# Verbose validation with detailed output
lightning-planner validate my_plan.json -v
```

**Validation Checks:**
- ✅ JSON Schema compliance
- ✅ External event registry validation
- ✅ Tool/action availability and argument validation
- ✅ Pydantic model validation
- ⚠️ Petri net validation (currently has PM4Py compatibility issues)

### 3. Visual Diagrams

#### Mermaid Diagrams

Generate Mermaid flowchart diagrams that can be viewed online:

```bash
# Generate Mermaid diagram
lightning-planner mermaid my_plan.json -o workflow_diagram.md

# View at https://mermaid.live/
```

**Mermaid Features:**
- Color-coded nodes (external events: blue, internal events: purple, steps: orange)
- Clear flow visualization with arrows
- Schedule and event type information
- Compatible with GitHub, GitLab, and documentation platforms

#### Graphviz Visualizations

Generate high-quality visual diagrams (requires graphviz installation):

```bash
# Install graphviz system dependency first
# macOS: brew install graphviz
# Ubuntu: sudo apt-get install graphviz
# Windows: Download from https://graphviz.org/download/

# Generate PNG visualization
lightning-planner visualize my_plan.json -o workflow.png

# Generate SVG (scalable)
lightning-planner visualize my_plan.json -o workflow.svg -f svg

# Generate PDF
lightning-planner visualize my_plan.json -o workflow.pdf -f pdf
```

### 4. List Available Resources

#### List Tools

View all available tools/actions that can be used in plans:

```bash
lightning-planner list-tools
```

**Available Tools:**
- `agent.conseil` - Research and analysis agent
- `agent.vex` - Phone call agent
- `llm.summarize` - Text summarization
- `llm.general_prompt` - General LLM calls
- `chat.sendTeamsMessage` - Teams notifications
- `event.schedule.create` - Scheduled events
- `event.timer.start` - Timer-based events

#### List Events

View all available external events that can trigger workflows:

```bash
lightning-planner list-events
```

**Available External Events:**
- `event.email.check` - Email monitoring (time.interval)
- `event.calendar.sync` - Calendar synchronization (time.cron)
- `event.webhook.github` - GitHub webhooks
- `event.manual.trigger` - Manual triggers

## Example Workflows

### 1. Daily Email Summary

```bash
lightning-planner generate "Create a workflow that checks emails every hour, summarizes them, and sends a Teams notification" -o email_summary.json
```

### 2. Weekly Business Intelligence

```bash
lightning-planner generate "Build a comprehensive weekly business intelligence workflow that researches market trends, analyzes data with multiple LLM models, schedules stakeholder calls, and distributes executive reports" -o business_intel.json
```

### 3. Customer Feedback Pipeline

```bash
lightning-planner generate "Design a customer feedback analysis system triggered by webhooks that analyzes sentiment, creates summaries, and schedules follow-up calls" -o feedback_pipeline.json
```

## Plan Structure

Generated plans follow this JSON structure:

```json
{
  "plan_name": "workflow_name",
  "graph_type": "acyclic|reactive",
  "events": [
    {
      "name": "event.name",
      "kind": "manual|webhook|time.interval|time.cron",
      "schedule": "PT1H|0 9 * * *",
      "description": "Event description"
    }
  ],
  "steps": [
    {
      "name": "step_name",
      "action": "tool.name",
      "args": {
        "param1": "value1",
        "param2": "value2"
      },
      "on": ["triggering_event"],
      "emits": ["emitted_event"],
      "guard": "optional_condition"
    }
  ]
}
```

## Advanced Usage

### Environment Variables

Set OpenAI API key for plan generation:

```bash
export OPENAI_API_KEY="your-api-key-here"
lightning-planner generate "Your instruction"
```

### Batch Processing

Process multiple plans:

```bash
# Generate multiple plans
for instruction in "Daily reports" "Weekly analysis" "Monthly summaries"; do
  lightning-planner generate "$instruction" -o "${instruction// /_}.json"
done

# Validate all plans
for plan in *.json; do
  echo "Validating $plan"
  lightning-planner validate "$plan"
done
```

### Integration with CI/CD

```yaml
# GitHub Actions example
- name: Validate Workflow Plans
  run: |
    pip install lightning-core[all]
    lightning-planner validate plans/*.json
```

## Troubleshooting

### Common Issues

1. **OpenAI API Key Missing**
   ```
   Error: OpenAI API key not found
   Solution: Set OPENAI_API_KEY environment variable
   ```

2. **Graphviz Not Installed**
   ```
   Error: Graphviz not installed
   Solution: Install graphviz system package
   ```

3. **Plan Validation Fails**
   ```
   Check the validation output for specific errors:
   - Unknown tools/actions
   - Missing required arguments
   - Invalid event references
   ```

### Getting Help

```bash
# General help
lightning-planner --help

# Command-specific help
lightning-planner generate --help
lightning-planner validate --help
lightning-planner visualize --help
```

## Examples Directory

The `examples/` directory contains:
- `sample_plan.json` - Example workflow plan
- `sample_plan_diagram.md` - Generated Mermaid diagram
- `basic_usage.py` - Python API usage examples

## Next Steps

1. **Explore the API**: Use the Python API directly for programmatic access
2. **Custom Tools**: Extend the tool registry with your own actions
3. **Event Integration**: Connect external systems to trigger workflows
4. **Deployment**: Deploy workflows to production environments

For more information, see the full documentation and API reference.
