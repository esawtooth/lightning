"""
Health check abstractions for Lightning Core providers.

Provides health checking and circuit breaker patterns for provider resilience.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Awaitable
import logging

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status of a provider."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, rejecting requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class HealthCheckResult:
    """Result of a health check."""
    status: HealthStatus
    latency_ms: float
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 3  # Successes to close from half-open
    timeout_seconds: int = 60   # Time before trying half-open
    half_open_requests: int = 3  # Requests allowed in half-open


class HealthCheckable:
    """Interface for providers that support health checks."""
    
    async def health_check(self) -> HealthCheckResult:
        """
        Perform a health check on the provider.
        
        Returns:
            HealthCheckResult indicating the provider's health
        """
        raise NotImplementedError("Subclasses must implement health_check()")
    
    async def detailed_health_check(self) -> Dict[str, Any]:
        """
        Perform a detailed health check with additional diagnostics.
        
        Returns:
            Dictionary with detailed health information
        """
        result = await self.health_check()
        return {
            "status": result.status.value,
            "latency_ms": result.latency_ms,
            "timestamp": result.timestamp.isoformat(),
            "details": result.details,
            "error": result.error,
        }


class CircuitBreaker:
    """Circuit breaker implementation for provider resilience."""
    
    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.half_open_requests = 0
        self._lock = asyncio.Lock()
        
    async def call(self, func: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        """
        Execute a function through the circuit breaker.
        
        Args:
            func: Async function to execute
            *args, **kwargs: Arguments for the function
            
        Returns:
            Result of the function
            
        Raises:
            CircuitBreakerOpenError: If circuit is open
        """
        async with self._lock:
            if self.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_requests = 0
                    logger.info("Circuit breaker transitioning to HALF_OPEN")
                else:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker is OPEN. Retry after "
                        f"{self.config.timeout_seconds - (time.time() - self.last_failure_time):.0f}s"
                    )
            
            if self.state == CircuitState.HALF_OPEN:
                if self.half_open_requests >= self.config.half_open_requests:
                    raise CircuitBreakerOpenError(
                        "Circuit breaker is HALF_OPEN and has reached request limit"
                    )
                self.half_open_requests += 1
        
        try:
            result = await func(*args, **kwargs)
            await self._record_success()
            return result
        except Exception as e:
            await self._record_failure()
            raise
    
    async def _record_success(self):
        """Record a successful call."""
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.config.success_threshold:
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.success_count = 0
                    logger.info("Circuit breaker closed after successful recovery")
            elif self.state == CircuitState.CLOSED:
                self.failure_count = 0  # Reset on success
    
    async def _record_failure(self):
        """Record a failed call."""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.state == CircuitState.CLOSED:
                if self.failure_count >= self.config.failure_threshold:
                    self.state = CircuitState.OPEN
                    logger.warning(
                        f"Circuit breaker opened after {self.failure_count} failures"
                    )
            elif self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                self.success_count = 0
                logger.warning("Circuit breaker reopened after failure in HALF_OPEN state")
    
    def _should_attempt_reset(self) -> bool:
        """Check if we should attempt to reset the circuit."""
        return (
            self.last_failure_time is not None and
            time.time() - self.last_failure_time >= self.config.timeout_seconds
        )
    
    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self.state == CircuitState.CLOSED
    
    @property
    def is_open(self) -> bool:
        """Check if circuit is open (failing)."""
        return self.state == CircuitState.OPEN
    
    def get_state(self) -> Dict[str, Any]:
        """Get current circuit breaker state."""
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time,
            "is_operational": self.state != CircuitState.OPEN,
        }


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass


class HealthMonitor:
    """Monitors provider health and manages circuit breakers."""
    
    def __init__(self, check_interval_seconds: int = 30):
        self.check_interval = check_interval_seconds
        self.providers: Dict[str, tuple[HealthCheckable, CircuitBreaker]] = {}
        self.health_history: Dict[str, List[HealthCheckResult]] = {}
        self.max_history = 100
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
    def register_provider(
        self, 
        name: str, 
        provider: HealthCheckable,
        circuit_config: Optional[CircuitBreakerConfig] = None
    ):
        """Register a provider for health monitoring."""
        circuit_breaker = CircuitBreaker(circuit_config)
        self.providers[name] = (provider, circuit_breaker)
        self.health_history[name] = []
        logger.info(f"Registered provider '{name}' for health monitoring")
    
    async def check_health(self, name: str) -> HealthCheckResult:
        """Check health of a specific provider."""
        if name not in self.providers:
            raise ValueError(f"Provider '{name}' not registered")
        
        provider, _ = self.providers[name]
        
        try:
            result = await provider.health_check()
        except Exception as e:
            result = HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                latency_ms=0,
                error=str(e)
            )
        
        # Store in history
        history = self.health_history[name]
        history.append(result)
        if len(history) > self.max_history:
            history.pop(0)
        
        return result
    
    async def start(self):
        """Start the health monitoring loop."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Health monitor started")
    
    async def stop(self):
        """Stop the health monitoring loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Health monitor stopped")
    
    async def _monitor_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                # Check all providers
                for name in list(self.providers.keys()):
                    try:
                        result = await self.check_health(name)
                        
                        # Update circuit breaker based on health
                        _, circuit_breaker = self.providers[name]
                        if result.status == HealthStatus.HEALTHY:
                            # Healthy providers should have closed circuits
                            if circuit_breaker.is_open:
                                logger.info(f"Provider '{name}' recovered, circuit may close")
                        elif result.status == HealthStatus.UNHEALTHY:
                            # Unhealthy providers may need circuit opened
                            logger.warning(f"Provider '{name}' is unhealthy: {result.error}")
                            
                    except Exception as e:
                        logger.error(f"Error checking health for '{name}': {e}")
                
                await asyncio.sleep(self.check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health monitor loop: {e}")
                await asyncio.sleep(self.check_interval)
    
    def get_provider_status(self, name: str) -> Dict[str, Any]:
        """Get current status of a provider."""
        if name not in self.providers:
            raise ValueError(f"Provider '{name}' not registered")
        
        _, circuit_breaker = self.providers[name]
        history = self.health_history.get(name, [])
        
        latest_health = history[-1] if history else None
        
        return {
            "name": name,
            "health": {
                "status": latest_health.status.value if latest_health else "unknown",
                "last_check": latest_health.timestamp.isoformat() if latest_health else None,
                "error": latest_health.error if latest_health else None,
            },
            "circuit_breaker": circuit_breaker.get_state(),
            "history_size": len(history),
        }
    
    def get_all_status(self) -> Dict[str, Any]:
        """Get status of all providers."""
        return {
            name: self.get_provider_status(name)
            for name in self.providers
        }