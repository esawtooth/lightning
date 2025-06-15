# Project Organization

This document describes the current organization of the Lightning project after reorganization on 2025-06-15.

## Root Directory Structure

The root directory now contains only essential files and directories:

### Essential Files (Kept in Root)
- `README.md` - Main project documentation
- `product-spec.md` - Product specification document
- `Cargo.toml` / `Cargo.lock` - Rust project configuration
- `Pulumi.dev.yaml` - Pulumi configuration
- `.gitignore` / `.dockerignore` - Git and Docker ignore files

### Main Directories
- `docs/` - All project documentation
- `tests/` - All test files and utilities
- `vextir_os/` - Vextir OS implementation
- `azure-function/` - Azure Functions
- `agents/` - Agent implementations
- `ui/` - User interface components
- `scripts/` - Deployment and utility scripts
- `infra/` - Infrastructure as code
- `context-hub/` - Context hub implementation
- `events/` - Event handling
- `common/` - Shared utilities

## Documentation Organization (`docs/`)

All markdown documentation files have been moved to the `docs/` directory:

- `AGENTS.md` - Agent system documentation
- `AUTH_SYSTEM_GUIDE.md` - Authentication system guide
- `CONTEXT_HUB_INTEGRATION_SUMMARY.md` - Context hub integration summary
- `DEPLOYMENT_FIX_SUMMARY.md` - Deployment fixes documentation
- `EMAIL_CALENDAR_INTEGRATION_COMPLETE.md` - Email/calendar integration docs
- `EMAIL_CALENDAR_INTEGRATION_GUIDE.md` - Email/calendar integration guide
- `EMAIL_CALENDAR_SYSTEM_COMPLETE.md` - Email/calendar system completion docs
- `VEXTIR_OS_IMPLEMENTATION.md` - Vextir OS implementation documentation
- `VEXTIR_OS_MIGRATION_COMPLETE.md` - Vextir OS migration summary

## Test Organization (`tests/`)

All test files are now consolidated in the `tests/` directory:

### Main Test Files
- `test_conseil_agent.py` - Conseil agent tests
- `test_driver_migration.py` - Driver migration tests
- `test_email_calendar_integration.py` - Email/calendar integration tests
- `test_vextir_os.py` - Vextir OS tests
- Plus all existing test files for various components

### Utilities (`tests/utilities/`)
- `cleanup_redundant_functions.py` - Function cleanup utility
- `get_url.py` - URL retrieval utility
- `web_search.py` - Web search utility

## Benefits of This Organization

1. **Cleaner Root Directory**: Only essential files remain in the root
2. **Better Documentation Discovery**: All docs are in one place
3. **Consolidated Testing**: All tests and test utilities are together
4. **Improved Navigation**: Logical grouping makes the project easier to navigate
5. **Standard Practices**: Follows common project organization patterns

## Migration Notes

- All file references and imports have been preserved
- No functionality has been changed, only file locations
- The reorganization maintains backward compatibility
- Essential files (README.md, product-spec.md) remain easily accessible in root
