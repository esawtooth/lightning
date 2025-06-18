# Flexible Agent Guide for Conseil

This guide explains how to use the flexible agent system that allows Conseil to operate in different professional roles beyond coding.

## Overview

The flexible agent system allows you to configure Conseil to act as different types of assistants:
- **Coding Assistant** (default): Traditional code editing and development
- **Legal Assistant**: Contract review, legal document management
- **Personal Assistant**: Task management, note-taking, scheduling
- **Finance Assistant**: Financial documentation, budgeting, reports
- **Research Assistant**: Information gathering, literature reviews
- **Technical Writer**: Documentation, guides, specifications
- **Project Manager**: Project planning, task tracking
- **Data Analyst**: Data exploration, analysis documentation
- **Custom**: Define your own role

## Basic Usage

```bash
# Default coding assistant
conseil

# Legal document assistant
conseil --role legal

# Personal assistant without sandboxing
conseil --role personal --no-sandbox

# Custom role
conseil --role custom \
  --description "You are a marketing content creator helping with blog posts and social media" \
  --guidelines "Focus on SEO-friendly content, use engaging tone, include CTAs"
```

## Command Line Options

- `--role, -r <role>`: Select the job role (coding, legal, personal, finance, research, custom)
- `--description, -d <desc>`: Custom job description (required for custom role)
- `--guidelines, -g <guide>`: Custom guidelines for the role
- `--no-sandbox`: Disable file system sandboxing (allows direct file access)
- `--model, -m <model>`: AI model to use (default: gpt-4)
- `--approval, -a <policy>`: Command approval policy (auto, manual, guided)
- `--list-roles`: List all available roles with descriptions

## Role-Specific Examples

### Legal Assistant
```bash
# Review contracts in the contracts/ directory
conseil --role legal --no-sandbox
> Review the NDA in contracts/acme-nda.md and highlight any concerning clauses

# Create a new contract template
conseil --role legal
> Create a standard consulting agreement template with hourly billing
```

### Personal Assistant
```bash
# Manage daily tasks
conseil --role personal --no-sandbox --approval auto
> Create a todo list for today based on the meetings in calendar.md

# Organize notes
conseil --role personal
> Organize all my meeting notes from this week into a summary
```

### Finance Assistant
```bash
# Budget tracking
conseil --role finance --no-sandbox
> Analyze expenses.csv and create a monthly budget summary in budgets/2024-01.md

# Financial reporting
conseil --role finance
> Create a Q4 financial report based on the data in finance/q4/
```

### Research Assistant
```bash
# Literature review
conseil --role research --approval auto
> Research recent developments in quantum computing and create a literature review

# Competitive analysis
conseil --role research
> Analyze competitors in the CRM space and create a comparison matrix
```

## Sandboxing

By default, the agent operates in a sandboxed environment for safety. This means:
- File operations are restricted to a temporary directory
- Changes must be explicitly approved before being applied
- Rollback is possible if issues occur

To disable sandboxing (useful for trusted operations):
```bash
conseil --role personal --no-sandbox
```

**Warning**: Disabling sandbox gives the agent direct file system access. Only use this when you trust the operations being performed.

## Custom Roles

Create specialized assistants for your specific needs:

```bash
# HR Assistant
conseil --role custom \
  --description "HR assistant for employee documentation and processes" \
  --guidelines "Maintain confidentiality, follow company policies, use inclusive language"

# Marketing Assistant  
conseil --role custom \
  --description "Marketing content creator and campaign planner" \
  --guidelines "Focus on brand voice, SEO optimization, track metrics"

# Academic Assistant
conseil --role custom \
  --description "Academic writing and research assistant" \
  --guidelines "Use proper citations, maintain academic tone, check for plagiarism"
```

## File Patterns

Each role is optimized for certain file types:

- **Legal**: `*.md`, `contracts/*.md`, `legal/*.md`
- **Personal**: `*.md`, `todos/*.md`, `notes/*.md`
- **Finance**: `*.md`, `*.csv`, `finance/*.md`, `reports/*.md`
- **Research**: `*.md`, `research/*.md`, `sources/*.md`

## Approval Policies

Control how commands are executed:

- `manual` (default): Approve each command individually
- `auto`: Automatically approve safe operations
- `guided`: Get suggestions but maintain control

Example:
```bash
# Auto-approve for personal tasks
conseil --role personal --approval auto

# Manual approval for financial operations
conseil --role finance --approval manual
```

## Integration with Lightning

When using Conseil as part of the Lightning system, you can configure agent drivers with specific roles:

```python
# In your Lightning configuration
conseil_agent = ConseilAgent(
    role="research",
    custom_description="Research market trends and compile reports",
    enable_sandbox=False,
    approval_policy="auto"
)
```

## Best Practices

1. **Start with sandbox enabled** until you trust the agent's operations
2. **Use specific roles** rather than custom when possible for optimized behavior
3. **Set appropriate approval policies** based on the sensitivity of operations
4. **Provide clear context** in your prompts for best results
5. **Organize files** according to role-specific patterns

## Troubleshooting

### Agent not finding files
- Check if sandbox is enabled (use `--no-sandbox` for direct access)
- Ensure you're in the correct working directory
- Verify file permissions

### Commands being rejected
- Review approval policy settings
- Check if operations are considered safe for auto-approval
- Use `--approval auto` for trusted operations

### Role not working as expected
- List available roles with `--list-roles`
- For custom roles, ensure description and guidelines are clear
- Consider using a predefined role as a starting point