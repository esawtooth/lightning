# Context Hub Integration Guide

## Overview

The Vextir CLI now includes comprehensive Context Hub integration, providing a complete subcli that wraps the existing contexthub-cli.py with enhanced user management and auto-configuration.

## Key Features

### 1. Integrated Context Hub CLI
All contexthub-cli functionality is now available as `vextir hub` commands:

```bash
# Initialize your personal Context Hub store
vextir hub init

# Navigate and explore
vextir hub status          # Show hub status
vextir hub ls              # List current directory
vextir hub ls /projects    # List specific directory
vextir hub cd projects     # Change directory
vextir hub pwd             # Show current directory

# File operations
vextir hub cat README.md   # View file content
vextir hub new myfile.txt  # Create new file
vextir hub new myfolder --folder  # Create new folder
vextir hub mv old.txt new.txt     # Rename/move
vextir hub rm unwanted.txt        # Delete

# Search and query
vextir hub search "project alpha"  # Search content
```

### 2. Local Development Workflow
Pull Context Hub folders to work locally, then push changes back:

```bash
# Pull a project for local editing
vextir hub pull /projects/myproject ./local-myproject

# Work locally with your favorite tools
cd local-myproject
# ... edit files ...

# Check what changed
vextir hub status ./local-myproject

# Push changes back
vextir hub push ./local-myproject

# Or push to a different location
vextir hub push ./local-myproject /projects/myproject-v2
```

### 3. Collaboration Features
Share folders and manage permissions:

```bash
# Share a folder with read access
vextir hub share /projects/alpha colleague@company.com

# Share with write access
vextir hub share /projects/alpha colleague@company.com --write

# View all shared folders
vextir hub shared
```

### 4. Auto-sync for Real-time Collaboration
Keep local directories synchronized automatically:

```bash
# Start auto-sync (watches for changes every 5 seconds)
vextir hub auto-sync ./local-myproject

# Custom interval
vextir hub auto-sync ./local-myproject --interval 10
```

## User Store Auto-Creation

### Automatic Initialization
When you first use Context Hub commands, the CLI automatically:

1. **Detects your Azure CLI user** - Uses `az account show` to get your username
2. **Auto-configures endpoints** - Sets up Context Hub endpoint based on your Vextir OS endpoint
3. **Creates personal store** - Initializes your user-specific Context Hub store
4. **Sets up folder structure** - Creates initial folders: `projects/`, `documents/`, `notes/`

### Manual Initialization
You can also explicitly initialize your Context Hub store:

```bash
vextir hub init
```

This will:
- Create your personal Context Hub store
- Set up initial folder structure
- Configure authentication and endpoints

## Configuration Management

### View Context Hub Configuration
```bash
vextir hub config show
```

### Set Configuration Options
```bash
vextir hub config set verbose true
vextir hub config set json false
```

### Reset Configuration
```bash
vextir hub config reset
```

## Integration with Main CLI

### Seamless Authentication
The Context Hub integration uses the same Azure CLI authentication as the main Vextir CLI:

```bash
# Check authentication (works for both main CLI and Context Hub)
vextir auth whoami

# Login if needed
vextir auth login
```

### Unified Configuration
Context Hub settings are part of the main CLI configuration:

```bash
# View all configuration including Context Hub settings
vextir config get

# Set Context Hub specific settings
vextir config set context_hub.endpoint https://my-hub.example.com
vextir config set context_hub.default_path /my-workspace
```

## Practical Usage Examples

### Daily Development Workflow
```bash
# Morning: Check what's new
vextir hub status
vextir hub ls /projects

# Pull current project
vextir hub pull /projects/current-sprint ./work

# Work locally all day...
cd work
# ... coding, editing, etc ...

# Evening: Push changes back
vextir hub push ./work --no-confirm
```

### Project Collaboration
```bash
# Set up shared project
vextir hub new shared-project --folder
vextir hub cd shared-project
vextir hub new README.md --content "# Shared Project"
vextir hub share /shared-project team@company.com --write

# Team members can now:
vextir hub pull /shared-project ./local-shared
# ... work locally ...
vextir hub push ./local-shared
```

### Research and Documentation
```bash
# Organize research
vextir hub cd /documents
vextir hub new research --folder
vextir hub cd research
vextir hub new "AI Trends 2024.md" --content "# AI Trends Research"

# Search across all documents
vextir hub search "machine learning"
vextir hub search "project timeline"
```

### Backup and Sync
```bash
# Pull everything for backup
vextir hub pull / ./full-backup

# Sync specific folders
vextir hub pull /projects ./projects-backup
vextir hub auto-sync ./projects-backup --interval 30
```

## Advanced Features

### Dry Run Operations
Test changes before applying:

```bash
vextir hub push ./local-project --dry-run
```

### Force Operations
Overwrite existing local directories:

```bash
vextir hub pull /projects/alpha ./alpha --force
```

### Batch Operations
Work with multiple files and folders efficiently through the integrated CLI.

## Error Handling and Troubleshooting

### Common Issues

1. **Authentication Errors**
   ```bash
   # Ensure Azure CLI is logged in
   az login
   vextir auth whoami
   ```

2. **Context Hub Not Initialized**
   ```bash
   # Initialize your store
   vextir hub init
   ```

3. **Network Connectivity**
   ```bash
   # Check system status
   vextir system status
   ```

4. **Sync Conflicts**
   ```bash
   # Check sync status
   vextir hub status ./local-directory
   
   # Force push if needed
   vextir hub push ./local-directory --no-confirm
   ```

### Debug Mode
Enable verbose output for troubleshooting:

```bash
vextir --verbose hub status
vextir hub config set verbose true
```

## Benefits of Integration

### 1. Unified Experience
- Single CLI for all Vextir OS operations
- Consistent authentication and configuration
- Integrated help and documentation

### 2. Enhanced Productivity
- Git-like workflow for Context Hub
- Local development with familiar tools
- Real-time collaboration features

### 3. Automation Ready
- Scriptable operations
- CI/CD integration
- Batch processing capabilities

### 4. User-Centric Design
- Auto-initialization of user stores
- Intelligent defaults and configuration
- Seamless Azure CLI integration

## Next Steps

1. **Initialize your Context Hub**: `vextir hub init`
2. **Explore the interface**: `vextir hub ls`
3. **Try local development**: `vextir hub pull /projects/demo ./demo`
4. **Set up collaboration**: `vextir hub share /projects/demo colleague@company.com`

The Context Hub integration transforms the Vextir CLI into a complete development and collaboration platform, providing both the power of command-line operations and the convenience of modern development workflows.
