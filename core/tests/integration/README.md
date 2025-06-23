# Integration Tests

This directory contains integration tests for Lightning Core components.

## Test Files

- `test_simple_cron_integration.py` - Tests cron scheduling functionality end-to-end
- `test_cron_integration.py` - Advanced cron integration tests  
- `test_integration_demo.py` - Comprehensive demo of planner-VextirOS integration
- `test_cli_chat.py` - Tests CLI chat through event-driven architecture
- `test_simple_cli_chat.py` - Basic CLI chat functionality tests
- `test_event_chat.py` - Pure event-driven chat communication tests
- `test_chat_with_index_guides.py` - Chat tests with index guide integration

## Running Integration Tests

These are executable scripts that can be run individually:

```bash
# Run a specific integration test
python tests/integration/test_simple_cron_integration.py

# Run all integration tests (requires pytest with integration marker)
pytest tests/integration/ -m integration

# Run all tests except integration tests
pytest -m "not integration"
```

## Note

These tests require external dependencies and may need specific environment configuration.
They are designed for manual testing and system validation during development.
