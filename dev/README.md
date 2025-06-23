# Development Tools

This directory contains development tools and utilities for Lightning OS.

## Structure

### `local_api/`
Local development API server - a FastAPI application that provides Lightning OS functionality without Azure dependencies.
- **Purpose**: Local development and testing
- **Usage**: `cd local_api && python main.py`
- **Features**: PostgreSQL + Redis storage with in-memory fallbacks

### `docker/`
Development Docker Compose files for specific environments:
- `docker-compose.local.yml` - Local development stack  
- `docker-compose.lightning-ui.yml` - Lightning UI development

**Note**: The main development environment is now in the root `docker-compose.local.yml` file.

### `core_debug/`
Core development and debugging tools:
- `debug_event_bus.py` - Event bus debugging utilities
- `demo_vextir.py` - Vextir development demo
- `test_*.py` - Development test scripts
- `run_*.sh` - Development run scripts

### Root Development Tools
- `check-gh-actions.py` - GitHub Actions debugging and log fetcher
- `planner_test.py` - Planner development test script

## Usage

### Start Local Development Environment
```bash
# From dev/docker directory
docker-compose -f docker-compose.local.yml up

# Or from root directory  
docker-compose -f dev/docker/docker-compose-local.yml up
```

### Run Local API Server
```bash
cd dev/local_api
python main.py
```

### Debug Event Bus
```bash
cd dev/core_debug
python debug_event_bus.py
```

### Check GitHub Actions
```bash
cd dev
python check-gh-actions.py
```
