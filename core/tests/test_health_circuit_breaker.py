"""
Tests for provider health checks and circuit breakers.
"""

import asyncio
import pytest
from datetime import datetime
from typing import Any, Dict

from lightning_core.abstractions import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitState,
    HealthCheckResult,
    HealthMonitor,
    HealthStatus,
    StorageProvider,
    Document,
    DocumentStore,
)
from lightning_core.runtime import LightningRuntime
from lightning_core.abstractions.configuration import ExecutionMode, RuntimeConfig


class MockFailingProvider:
    """Mock provider that fails after a certain number of calls."""
    
    def __init__(self, fail_after: int = 3):
        self.call_count = 0
        self.fail_after = fail_after
        
    async def some_operation(self) -> str:
        self.call_count += 1
        if self.call_count > self.fail_after:
            raise Exception("Provider failure")
        return "success"


@pytest.mark.asyncio
async def test_circuit_breaker_opens_on_failures():
    """Test that circuit breaker opens after threshold failures."""
    config = CircuitBreakerConfig(
        failure_threshold=3,
        success_threshold=2,
        timeout_seconds=1
    )
    
    breaker = CircuitBreaker(config)
    provider = MockFailingProvider(fail_after=2)
    
    # First two calls succeed
    result1 = await breaker.call(provider.some_operation)
    assert result1 == "success"
    
    result2 = await breaker.call(provider.some_operation)
    assert result2 == "success"
    
    # Next calls fail and open the circuit
    with pytest.raises(Exception):
        await breaker.call(provider.some_operation)
    
    with pytest.raises(Exception):
        await breaker.call(provider.some_operation)
    
    with pytest.raises(Exception):
        await breaker.call(provider.some_operation)
    
    # Circuit should be open now
    assert breaker.is_open
    
    # Further calls should be rejected immediately
    with pytest.raises(CircuitBreakerOpenError):
        await breaker.call(provider.some_operation)


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_recovery():
    """Test circuit breaker recovery through half-open state."""
    config = CircuitBreakerConfig(
        failure_threshold=2,
        success_threshold=2,
        timeout_seconds=0.5,  # Short timeout for testing
        half_open_requests=3
    )
    
    breaker = CircuitBreaker(config)
    
    # Always failing provider
    async def failing_op():
        raise Exception("Always fails")
    
    # Recovering provider
    recovery_count = 0
    async def recovering_op():
        nonlocal recovery_count
        recovery_count += 1
        if recovery_count <= 1:
            raise Exception("Still failing")
        return "recovered"
    
    # Open the circuit with failures
    for _ in range(2):
        with pytest.raises(Exception):
            await breaker.call(failing_op)
    
    assert breaker.state == CircuitState.OPEN
    
    # Wait for timeout
    await asyncio.sleep(0.6)
    
    # Switch to recovering provider
    # First call in half-open fails, reopening circuit
    with pytest.raises(Exception):
        await breaker.call(recovering_op)
    
    # Wait again for timeout
    await asyncio.sleep(0.6)
    
    # Now calls succeed and close the circuit
    result1 = await breaker.call(recovering_op)
    assert result1 == "recovered"
    
    result2 = await breaker.call(recovering_op)
    assert result2 == "recovered"
    
    # Circuit should be closed
    assert breaker.is_closed


@pytest.mark.asyncio
async def test_health_monitor():
    """Test health monitoring of providers."""
    
    class MockHealthyProvider:
        async def health_check(self) -> HealthCheckResult:
            return HealthCheckResult(
                status=HealthStatus.HEALTHY,
                latency_ms=10.5,
                details={"version": "1.0"}
            )
    
    class MockUnhealthyProvider:
        async def health_check(self) -> HealthCheckResult:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                latency_ms=100.0,
                error="Connection failed"
            )
    
    monitor = HealthMonitor(check_interval_seconds=0.1)
    
    # Register providers
    monitor.register_provider("healthy", MockHealthyProvider())
    monitor.register_provider("unhealthy", MockUnhealthyProvider())
    
    # Start monitoring
    await monitor.start()
    
    # Let it run a check cycle
    await asyncio.sleep(0.2)
    
    # Check status
    healthy_status = monitor.get_provider_status("healthy")
    assert healthy_status["health"]["status"] == "healthy"
    assert healthy_status["circuit_breaker"]["state"] == "closed"
    
    unhealthy_status = monitor.get_provider_status("unhealthy")
    assert unhealthy_status["health"]["status"] == "unhealthy"
    assert unhealthy_status["health"]["error"] == "Connection failed"
    
    # Stop monitoring
    await monitor.stop()


@pytest.mark.asyncio
async def test_runtime_with_health_checks():
    """Test Lightning runtime with health check enabled."""
    config = RuntimeConfig(
        mode=ExecutionMode.LOCAL,
        storage_provider="local",
        event_bus_provider="local",
        storage_path="/tmp/test_health"
    )
    
    runtime = LightningRuntime(config, use_resilient_providers=True)
    
    async with runtime.session():
        # Providers should be wrapped with circuit breakers
        storage = runtime.storage
        event_bus = runtime.event_bus
        
        # Check health status
        health_status = await runtime.get_health_status()
        
        # Should have registered providers
        assert len(health_status) > 0
        
        # Perform some operations
        await event_bus.create_topic("test_topic")
        exists = await event_bus.topic_exists("test_topic")
        assert exists
        
        # Clean up
        await event_bus.delete_topic("test_topic")


@pytest.mark.asyncio
async def test_provider_health_check_implementations():
    """Test that providers implement health checks correctly."""
    from lightning_core.providers.local.storage import LocalStorageProvider
    from lightning_core.providers.local.event_bus import LocalEventBus
    
    # Test storage provider health check
    storage = LocalStorageProvider(path="/tmp/test_health_storage")
    await storage.initialize()
    
    health_result = await storage.health_check()
    assert health_result.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]
    assert health_result.latency_ms >= 0
    
    await storage.close()
    
    # Test event bus health check
    event_bus = LocalEventBus()
    await event_bus.start()
    
    health_result = await event_bus.health_check()
    assert health_result.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]
    assert health_result.latency_ms >= 0
    
    await event_bus.stop()


@pytest.mark.asyncio
async def test_circuit_breaker_state_tracking():
    """Test circuit breaker state tracking."""
    config = CircuitBreakerConfig(
        failure_threshold=2,
        success_threshold=1,
        timeout_seconds=60
    )
    
    breaker = CircuitBreaker(config)
    
    # Initial state
    state = breaker.get_state()
    assert state["state"] == "closed"
    assert state["failure_count"] == 0
    assert state["is_operational"] is True
    
    # Cause failures
    async def failing_op():
        raise Exception("Test failure")
    
    for _ in range(2):
        with pytest.raises(Exception):
            await breaker.call(failing_op)
    
    # Check open state
    state = breaker.get_state()
    assert state["state"] == "open"
    assert state["failure_count"] == 2
    assert state["is_operational"] is False
    assert state["last_failure_time"] is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])