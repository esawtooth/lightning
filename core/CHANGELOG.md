# Changelog

All notable changes to Lightning Core will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2025-01-17

### Added
- Initial release of Lightning Core library
- **Lightning Planner** module with workflow planning and validation
  - Pydantic-based schema validation for plans
  - Tool registry for managing available capabilities
  - Event registry for external event definitions
  - Plan validation using Petri net theory
  - JSON schema generation and validation
  - Simplified PM4Py integration with clean imports
- **Vextir OS** module with event-driven architecture
  - Comprehensive event system with typed events
  - Asynchronous event bus with filtering and streaming
  - Driver framework with pluggable architecture
  - Agent, Tool, IO, and UI driver types
  - Security manager with policy-based authorization
  - Universal event processor for centralized processing
- **Testing Suite**
  - 61 comprehensive tests covering all major functionality
  - Unit tests for events, event bus, and schema validation
  - Async test support with pytest-asyncio
  - Mock-based testing for external dependencies
- **Documentation**
  - Comprehensive README with examples and architecture diagrams
  - API documentation with usage examples
  - Development setup and contribution guidelines
- **Examples**
  - Basic usage examples demonstrating all major features
  - Event system demonstration
  - Driver system demonstration
  - Schema validation examples
  - Event streaming examples

### Features
- **Event System**
  - Type-safe event definitions with categories
  - Asynchronous event bus with subscription management
  - Event filtering by type, source, user, and category
  - Event streaming with async context managers
  - Event history with configurable limits
  - Global event bus singleton pattern

- **Driver Framework**
  - Abstract base classes for different driver types
  - Resource specification and management
  - Driver registry with capability mapping
  - Event routing to capable drivers
  - Driver lifecycle management (start/stop/status)
  - Error handling and recovery

- **Security & Policy**
  - Policy-based authorization system
  - Configurable security policies
  - Audit logging for all authorization decisions
  - Cost control and rate limiting policies
  - PII protection policies

- **Schema Validation**
  - Pydantic v2 models for type safety
  - JSON schema generation
  - Plan validation with external event checking
  - Tool registry integration
  - Comprehensive error reporting
  - Clean PM4Py 2.7.x integration without complex import logic

### Technical Details
- Python 3.10+ support
- Async/await throughout for performance
- Type hints for better IDE support
- Pydantic v2 for data validation
- OpenAI integration for LLM planning
- Modular architecture for extensibility
- Simplified dependencies with pinned versions

### Dependencies
- pydantic >= 2.0.0
- openai >= 1.0.0
- asyncio-mqtt >= 0.13.0
- aiohttp >= 3.8.0
- jsonschema >= 4.0.0
- croniter >= 1.3.0
- python-dateutil >= 2.8.0
- typing-extensions >= 4.0.0
- pm4py >= 2.7.0

### Development Dependencies
- pytest >= 7.0.0
- pytest-asyncio >= 0.21.0
- black >= 23.0.0
- isort >= 5.12.0
- flake8 >= 6.0.0
- mypy >= 1.0.0

### Fixed
- Simplified PM4Py validator imports to use stable 2.7.x interface
- Removed complex version-specific import logic
- Pinned PM4Py to latest stable version (2.7.15.3)
- Clean, maintainable validator code without fallback mechanisms

[0.1.0]: https://github.com/lightning-ai/lightning-core/releases/tag/v0.1.0
