# Testing Guide for Context Hub

## Overview

The Context Hub includes comprehensive unit tests, integration tests, and end-to-end tests to ensure reliability and correctness.

## Test Structure

```
tests/
├── unit/                    # Unit tests for individual components
│   ├── wal_tests.rs        # Write-ahead log tests
│   ├── shard_tests.rs      # Sharding and routing tests
│   ├── storage_tests.rs    # Storage layer tests
│   └── auth_tests.rs       # Authentication tests
├── integration/            # Integration tests
│   └── integration_test.rs # Full system integration tests
└── e2e/                   # End-to-end API tests
```

## Running Tests

### Quick Test

Run all tests with the provided script:

```bash
./test.sh
```

### Unit Tests Only

```bash
cargo test --lib
```

### Integration Tests

```bash
# Start test infrastructure
docker-compose -f docker-compose.test.yml up -d

# Run integration tests
cargo test --test integration_test

# Clean up
docker-compose -f docker-compose.test.yml down -v
```

### Specific Test

```bash
# Run a specific test
cargo test test_wal_recovery

# Run tests in a specific module
cargo test wal::tests::

# Run with output
cargo test -- --nocapture
```

## Test Coverage

Generate test coverage report:

```bash
# Install tarpaulin
cargo install cargo-tarpaulin

# Generate coverage
cargo tarpaulin --out Html

# Open coverage report
open tarpaulin-report.html
```

## Benchmarks

Run performance benchmarks:

```bash
cargo bench
```

## Test Infrastructure

The `docker-compose.test.yml` provides:

- **etcd cluster**: 3 nodes for coordination
- **PostgreSQL**: With Citus extension
- **Redis**: For caching
- **MinIO**: S3-compatible storage
- **Context Hub shards**: 3 test shards

## Writing Tests

### Unit Test Example

```rust
#[cfg(test)]
mod tests {
    use super::*;
    
    #[tokio::test]
    async fn test_document_create() {
        let store = setup_test_store().await;
        
        let doc_id = store.create(
            "user1",
            "test.txt",
            "content",
            None,
            DocumentType::Text,
        ).await.unwrap();
        
        assert_ne!(doc_id, Uuid::nil());
    }
}
```

### Integration Test Example

```rust
#[tokio::test]
#[ignore] // Requires running services
async fn test_cross_shard_operation() {
    let client = setup_test_client().await;
    
    // Test cross-shard document sharing
    let doc = client.create_document("shared.txt").await.unwrap();
    client.share_document(doc.id, "other-user").await.unwrap();
    
    // Verify from other shard
    let other_client = setup_client_for_user("other-user").await;
    let shared_doc = other_client.get_document(doc.id).await.unwrap();
    assert_eq!(shared_doc.id, doc.id);
}
```

## Continuous Integration

GitHub Actions runs tests on every push:

1. Format check
2. Clippy lints
3. Unit tests
4. Integration tests
5. Security audit

## Troubleshooting

### Tests Failing

1. Check Docker services are running:
   ```bash
   docker-compose -f docker-compose.test.yml ps
   ```

2. Check logs:
   ```bash
   docker-compose -f docker-compose.test.yml logs
   ```

3. Reset test data:
   ```bash
   docker-compose -f docker-compose.test.yml down -v
   ```

### Memory Issues

For large tests, increase Docker memory:
```bash
docker-compose -f docker-compose.test.yml up -d --memory 4g
```

### Port Conflicts

If ports are in use, modify `docker-compose.test.yml` to use different ports.

## Test Data

Test fixtures are in `tests/fixtures/`:
- Sample documents
- Test certificates
- Mock configuration

## Performance Testing

Load test with k6:

```bash
# Install k6
brew install k6

# Run load test
k6 run tests/load/stress-test.js
```

## Security Testing

Run security audit:

```bash
cargo audit
```

## Test Best Practices

1. **Isolation**: Each test should be independent
2. **Cleanup**: Always clean up test data
3. **Timeouts**: Use reasonable timeouts
4. **Assertions**: Test both success and failure cases
5. **Documentation**: Document what each test verifies

## Known Issues

- Integration tests require Docker
- Some tests are marked `#[ignore]` as they require external services
- Windows support is limited for some tests