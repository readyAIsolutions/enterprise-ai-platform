"""
ENI Enterprise Integration Layer — Service Mesh
================================================
Production-grade service mesh providing service discovery, health checking,
circuit breaking, load balancing, and resilience patterns for inter-module
communication within the ENI platform.

Architecture:
    ServiceRegistry    — Service discovery and registration
    HealthChecker      — Periodic health probing with configurable thresholds
    CircuitBreaker     — Failure-aware circuit breaker with half-open recovery
    LoadBalancer       — Round-robin, least-connections, and weighted strategies
    ResilienceManager  — Retry, timeout, bulkhead, and rate limiting
    ServiceProxy       — Transparent proxy with mesh capabilities
    MeshTopology       — Service dependency graph visualization

Features:
    - Auto-discovery of modules from kernel registry
    - Periodic health checks with rolling window metrics
    - Circuit breaker: CLOSED → OPEN → HALF_OPEN → CLOSED
    - Exponential backoff retry with jitter
    - Bulkhead isolation (max concurrent requests per service)
    - Request timeout enforcement
    - Service dependency graph
    - Prometheus-compatible metrics export
"""

import asyncio
import logging
import random
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
)

logger = logging.getLogger("eni.integration.service_mesh")

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class HealthStatus(str, Enum):
    """Service health status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class CircuitState(str, Enum):
    """Circuit breaker states.

    CLOSED:     Requests flow normally. Failures are counted.
    OPEN:       Requests are rejected immediately. Timer counts down.
    HALF_OPEN:  A limited number of probe requests are allowed through.
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class LoadBalanceStrategy(str, Enum):
    """Load balancing algorithm."""

    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_connections"
    WEIGHTED = "weighted"
    RANDOM = "random"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass
class ServiceInstance:
    """A single instance of a service.

    Attributes:
        instance_id: Unique instance identifier
        service_name: Logical service name
        host: Hostname or IP address
        port: TCP port
        version: Service version string
        status: Current health status
        weight: Load balancing weight (for weighted strategy)
        metadata: Arbitrary key-value metadata
        registered_at: UTC timestamp of registration
        last_heartbeat: UTC timestamp of last heartbeat
    """

    instance_id: str
    service_name: str
    host: str = "localhost"
    port: int = 8000
    version: str = "0.0.0"
    status: HealthStatus = HealthStatus.UNKNOWN
    weight: int = 1
    metadata: Dict[str, str] = field(default_factory=dict)
    registered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_heartbeat: Optional[str] = None


@dataclass
class HealthCheckConfig:
    """Configuration for health checking.

    Attributes:
        interval_seconds: How often to probe
        timeout_seconds: Probe timeout
        failure_threshold: Consecutive failures before marking unhealthy
        success_threshold: Consecutive successes to recover from unhealthy
        endpoint: Health check endpoint path (default: /api/v1/health/live)
    """

    interval_seconds: float = 10.0
    timeout_seconds: float = 5.0
    failure_threshold: int = 3
    success_threshold: int = 2
    endpoint: str = "/api/v1/health/live"


@dataclass
class HealthRecord:
    """Rolling health metrics for a service instance."""

    instance_id: str
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    total_checks: int = 0
    total_failures: int = 0
    last_check_time: Optional[str] = None
    last_latency_ms: float = 0.0
    last_error: Optional[str] = None
    window_latencies: List[float] = field(default_factory=list)  # Last N latencies
    status: HealthStatus = HealthStatus.UNKNOWN


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration.

    Attributes:
        failure_threshold: Consecutive or ratio failures to open
        recovery_timeout_seconds: Time before attempting half-open
        half_open_max_requests: Max requests allowed in half-open state
        sliding_window_size: Number of requests in the sliding window
        failure_rate_threshold: Failure rate (0-1) that triggers opening
    """

    failure_threshold: int = 5
    recovery_timeout_seconds: float = 30.0
    half_open_max_requests: int = 3
    sliding_window_size: int = 100
    failure_rate_threshold: float = 0.5


@dataclass
class RetryConfig:
    """Retry policy configuration.

    Attributes:
        max_retries: Maximum retry attempts
        base_delay_seconds: Base delay before first retry
        max_delay_seconds: Maximum delay cap
        backoff_multiplier: Exponential backoff multiplier
        jitter: Whether to add random jitter
        retryable_exceptions: Exception types that trigger retry
    """

    max_retries: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    backoff_multiplier: float = 2.0
    jitter: bool = True
    retryable_exceptions: Tuple[type, ...] = (Exception,)


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------


class CircuitBreaker:
    """Failure-aware circuit breaker for service calls.

    Implements the standard CLOSED → OPEN → HALF_OPEN → CLOSED state machine
    with a sliding window of recent outcomes for rate-based tripping.
    """

    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._success_count: int = 0
        self._last_failure_time: Optional[float] = None
        self._opened_at: Optional[float] = None
        self._half_open_requests: int = 0
        self._window: List[bool] = []  # True = success, False = failure
        self._lock = threading.Lock()
        self._total_successes: int = 0
        self._total_failures: int = 0
        self._total_rejected: int = 0

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a call through the circuit breaker."""
        if not self._allow_request():
            self._total_rejected += 1
            raise CircuitOpenError(
                f"Circuit breaker '{self.name}' is OPEN. "
                f"Rejecting request. Retry after {self._recovery_remaining():.0f}s."
            )

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as exc:
            self._on_failure()
            raise exc

    async def acall(self, coro_func: Callable, *args, **kwargs) -> Any:
        """Execute an async call through the circuit breaker."""
        if not self._allow_request():
            self._total_rejected += 1
            raise CircuitOpenError(
                f"Circuit breaker '{self.name}' is OPEN."
            )

        try:
            result = await coro_func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as exc:
            self._on_failure()
            raise exc

    def _allow_request(self) -> bool:
        with self._lock:
            if self.state == CircuitState.CLOSED:
                return True
            if self.state == CircuitState.OPEN:
                # Check if recovery timeout has elapsed
                if self._opened_at and (time.monotonic() - self._opened_at) >= self.config.recovery_timeout_seconds:
                    self.state = CircuitState.HALF_OPEN
                    self._half_open_requests = 0
                    logger.info("Circuit breaker '%s' transitioning to HALF_OPEN", self.name)
                    return True
                return False
            if self.state == CircuitState.HALF_OPEN:
                if self._half_open_requests < self.config.half_open_max_requests:
                    self._half_open_requests += 1
                    return True
                return False
            return False

    def _on_success(self):
        with self._lock:
            self._total_successes += 1
            self._window.append(True)
            if len(self._window) > self.config.sliding_window_size:
                self._window.pop(0)

            if self.state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.failure_threshold:
                    self.state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    self._last_failure_time = None
                    logger.info("Circuit breaker '%s' RESET to CLOSED", self.name)

            # Check rate threshold on success too (window may cross threshold from prior failures)
            if self.state == CircuitState.CLOSED:
                failure_rate = self._current_failure_rate()
                if (len(self._window) >= 3 and failure_rate >= self.config.failure_rate_threshold):
                    import time as _time
                    self.state = CircuitState.OPEN
                    self._opened_at = _time.monotonic()
                    logger.warning(
                        "Circuit breaker '%s' OPENED via rate (rate=%.2f on success check)",
                        self.name, failure_rate,
                    )

    def _on_failure(self):
        with self._lock:
            self._total_failures += 1
            self._window.append(False)
            if len(self._window) > self.config.sliding_window_size:
                self._window.pop(0)

            now = time.monotonic()
            self._last_failure_time = now

            if self.state == CircuitState.HALF_OPEN:
                # Any failure in half-open reopens the circuit
                self.state = CircuitState.OPEN
                self._opened_at = now
                logger.warning("Circuit breaker '%s' reopened (failure in HALF_OPEN)", self.name)
                return

            if self.state == CircuitState.CLOSED:
                self._failure_count += 1
                # Check both absolute threshold and rate threshold
                failure_rate = self._current_failure_rate()
                if (self._failure_count >= self.config.failure_threshold or
                        (len(self._window) >= 5 and failure_rate >= self.config.failure_rate_threshold)):
                    self.state = CircuitState.OPEN
                    self._opened_at = now
                    logger.warning(
                        "Circuit breaker '%s' OPENED (failures=%d, rate=%.2f)",
                        self.name, self._failure_count, failure_rate,
                    )

    def _current_failure_rate(self) -> float:
        if not self._window:
            return 0.0
        failures = sum(1 for ok in self._window if not ok)
        return failures / len(self._window)

    def _recovery_remaining(self) -> float:
        if self._opened_at is None:
            return 0.0
        elapsed = time.monotonic() - self._opened_at
        return max(0.0, self.config.recovery_timeout_seconds - elapsed)

    def force_close(self):
        """Administratively reset the circuit breaker."""
        with self._lock:
            self.state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._half_open_requests = 0
            self._last_failure_time = None
            self._opened_at = None

    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics."""
        with self._lock:
            return {
                "name": self.name,
                "state": self.state.value,
                "total_successes": self._total_successes,
                "total_failures": self._total_failures,
                "total_rejected": self._total_rejected,
                "failure_rate": round(self._current_failure_rate(), 4),
                "recovery_remaining_seconds": round(self._recovery_remaining(), 1),
            }


class CircuitOpenError(Exception):
    """Raised when a request is rejected due to an open circuit breaker."""
    pass


# ---------------------------------------------------------------------------
# Service Registry (Discovery)
# ---------------------------------------------------------------------------


class ServiceRegistry:
    """Service discovery and registration.

    Maintains a registry of all service instances with their metadata
    and health status. Integrates with the kernel ModuleRegistry for
    auto-discovery of enterprise modules.
    """

    def __init__(self):
        self._services: Dict[str, Dict[str, ServiceInstance]] = defaultdict(dict)
        self._lock = threading.Lock()
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._health_records: Dict[str, HealthRecord] = {}

    # ── Registration ─────────────────────────────────────────────────────

    def register(self, instance: ServiceInstance) -> str:
        """Register a service instance."""
        with self._lock:
            self._services[instance.service_name][instance.instance_id] = instance
            # Create default circuit breaker for this service
            if instance.service_name not in self._circuit_breakers:
                self._circuit_breakers[instance.service_name] = CircuitBreaker(
                    instance.service_name
                )
            if instance.instance_id not in self._health_records:
                self._health_records[instance.instance_id] = HealthRecord(
                    instance_id=instance.instance_id
                )
        logger.info(
            "Registered service: %s/%s at %s:%d v%s",
            instance.service_name,
            instance.instance_id,
            instance.host,
            instance.port,
            instance.version,
        )
        return instance.instance_id

    def deregister(self, service_name: str, instance_id: str):
        """Remove a service instance."""
        with self._lock:
            removed = self._services[service_name].pop(instance_id, None)
            if not self._services[service_name]:
                del self._services[service_name]
            self._health_records.pop(instance_id, None)
        if removed:
            logger.info("Deregistered service: %s/%s", service_name, instance_id)

    def heartbeat(self, instance_id: str):
        """Record a heartbeat for an instance."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            for svc_instances in self._services.values():
                if instance_id in svc_instances:
                    svc_instances[instance_id].last_heartbeat = now
                    return

    # ── Discovery ────────────────────────────────────────────────────────

    def get_instance(self, service_name: str, instance_id: str) -> Optional[ServiceInstance]:
        """Get a specific service instance."""
        with self._lock:
            return self._services.get(service_name, {}).get(instance_id)

    def get_instances(self, service_name: str, healthy_only: bool = True) -> List[ServiceInstance]:
        """Get all instances of a service, optionally only healthy ones."""
        with self._lock:
            instances = list(self._services.get(service_name, {}).values())
        if healthy_only:
            instances = [i for i in instances if i.status == HealthStatus.HEALTHY]
        return instances

    def list_services(self) -> Dict[str, Dict[str, Any]]:
        """List all registered services with instance counts and health."""
        with self._lock:
            result = {}
            for svc_name, instances in self._services.items():
                healthy = sum(1 for i in instances.values() if i.status == HealthStatus.HEALTHY)
                cb = self._circuit_breakers.get(svc_name)
                result[svc_name] = {
                    "instance_count": len(instances),
                    "healthy_count": healthy,
                    "instances": [
                        {
                            "instance_id": i.instance_id,
                            "host": i.host,
                            "port": i.port,
                            "version": i.version,
                            "status": i.status.value,
                            "last_heartbeat": i.last_heartbeat,
                        }
                        for i in instances.values()
                    ],
                    "circuit_breaker": cb.get_stats() if cb else None,
                }
            return result

    # ── Circuit Breakers ─────────────────────────────────────────────────

    def get_circuit_breaker(self, service_name: str) -> CircuitBreaker:
        """Get or create a circuit breaker for a service."""
        with self._lock:
            if service_name not in self._circuit_breakers:
                self._circuit_breakers[service_name] = CircuitBreaker(service_name)
            return self._circuit_breakers[service_name]

    def get_all_circuit_breakers(self) -> Dict[str, Dict[str, Any]]:
        """Get all circuit breaker stats."""
        with self._lock:
            return {name: cb.get_stats() for name, cb in self._circuit_breakers.items()}

    # ── Auto-Discovery from Kernel ────────────────────────────────────────

    def discover_from_kernel(self):
        """Auto-register all kernel-discovered modules as services."""
        try:
            from enterprise.kernel.registry import ModuleRegistry

            for mod_id, mod_name in ModuleRegistry.list_all().items():
                spec = ModuleRegistry.get(mod_id)
                if spec:
                    instance = ServiceInstance(
                        instance_id=f"{mod_id}-default",
                        service_name=mod_id,
                        host="localhost",
                        port=8000,
                        version=spec.version,
                        metadata={
                            "description": spec.description,
                            "blocking": str(spec.blocking),
                        },
                    )
                    self.register(instance)
            logger.info("Auto-discovered %d modules from kernel", len(self._services))
        except ImportError:
            logger.debug("Kernel not available; skip auto-discovery")
        except Exception as e:
            logger.warning("Auto-discovery failed: %s", e)

    # ── Health Records ───────────────────────────────────────────────────

    def update_health(self, instance_id: str, healthy: bool, latency_ms: float = 0.0, error: str = ""):
        """Update health record for an instance."""
        with self._lock:
            record = self._health_records.get(instance_id)
            if record is None:
                return

            record.last_check_time = datetime.now(timezone.utc).isoformat()
            record.last_latency_ms = latency_ms
            record.total_checks += 1

            if healthy:
                record.consecutive_successes += 1
                record.consecutive_failures = 0
            else:
                record.consecutive_failures += 1
                record.consecutive_successes = 0
                record.total_failures += 1
                record.last_error = error

            record.window_latencies.append(latency_ms)
            if len(record.window_latencies) > 100:
                record.window_latencies.pop(0)

            # Update instance status
            for svc_instances in self._services.values():
                if instance_id in svc_instances:
                    if healthy:
                        svc_instances[instance_id].status = HealthStatus.HEALTHY
                    elif record.consecutive_failures >= 3:
                        svc_instances[instance_id].status = HealthStatus.UNHEALTHY
                    elif record.consecutive_failures >= 1:
                        svc_instances[instance_id].status = HealthStatus.DEGRADED
                    break


# ---------------------------------------------------------------------------
# Health Checker
# ---------------------------------------------------------------------------


class HealthChecker:
    """Periodic health checking for all registered services.

    Probes each service's health endpoint and updates the registry
    with results. Supports configurable thresholds and intervals.
    """

    def __init__(
        self,
        registry: ServiceRegistry,
        config: Optional[HealthCheckConfig] = None,
    ):
        self.registry = registry
        self.config = config or HealthCheckConfig()
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._check_callbacks: List[Callable[[str, HealthStatus], None]] = []

    def on_health_change(self, callback: Callable[[str, HealthStatus], None]):
        """Register a callback for health status changes."""
        self._check_callbacks.append(callback)

    async def start(self):
        """Start periodic health checking."""
        self._running = True
        logger.info(
            "HealthChecker started (interval=%.1fs, timeout=%.1fs)",
            self.config.interval_seconds,
            self.config.timeout_seconds,
        )
        self._tasks = [asyncio.create_task(self._check_loop())]

    async def stop(self):
        """Stop health checking."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("HealthChecker stopped")

    async def _check_loop(self):
        """Main health check loop."""
        while self._running:
            try:
                await self._check_all_services()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Health check loop error")
            await asyncio.sleep(self.config.interval_seconds)

    async def _check_all_services(self):
        """Check all registered service instances."""
        services = self.registry.list_services()
        tasks = []

        for svc_name, svc_info in services.items():
            for instance in svc_info.get("instances", []):
                tasks.append(self._check_instance(
                    svc_name, instance["instance_id"],
                    instance["host"], instance["port"],
                ))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _check_instance(self, service_name: str, instance_id: str, host: str, port: int):
        """Check a single service instance."""
        start = time.monotonic()
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=self.config.timeout_seconds,
            )

            # Send a minimal HTTP health check request
            request = (
                f"GET {self.config.endpoint} HTTP/1.1\r\n"
                f"Host: {host}:{port}\r\n"
                f"User-Agent: ENI-HealthChecker/1.0\r\n"
                f"Connection: close\r\n"
                f"\r\n"
            )
            writer.write(request.encode())
            await writer.drain()

            # Read response
            response = b""
            while True:
                try:
                    chunk = await asyncio.wait_for(reader.read(4096), timeout=self.config.timeout_seconds)
                    if not chunk:
                        break
                    response += chunk
                except asyncio.TimeoutError:
                    break

            writer.close()
            await writer.wait_closed()

            latency_ms = (time.monotonic() - start) * 1000
            status_line = response.split(b"\r\n")[0].decode(errors="ignore") if response else ""

            if "200" in status_line or "204" in status_line:
                self.registry.update_health(instance_id, healthy=True, latency_ms=latency_ms)
            else:
                self.registry.update_health(instance_id, healthy=False, latency_ms=latency_ms, error=f"HTTP {status_line}")

        except (asyncio.TimeoutError, ConnectionRefusedError, OSError) as exc:
            latency_ms = (time.monotonic() - start) * 1000
            self.registry.update_health(instance_id, healthy=False, latency_ms=latency_ms, error=str(exc))


# ---------------------------------------------------------------------------
# Load Balancer
# ---------------------------------------------------------------------------


class LoadBalancer:
    """Client-side load balancer for service instances.

    Supports multiple strategies: round-robin, least-connections,
    weighted, and random.
    """

    def __init__(self, strategy: LoadBalanceStrategy = LoadBalanceStrategy.ROUND_ROBIN):
        self.strategy = strategy
        self._round_robin_counters: Dict[str, int] = defaultdict(int)
        self._connection_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._lock = threading.Lock()

    def select(self, instances: List[ServiceInstance]) -> Optional[ServiceInstance]:
        """Select an instance using the configured strategy."""
        if not instances:
            return None
        if len(instances) == 1:
            return instances[0]

        if self.strategy == LoadBalanceStrategy.ROUND_ROBIN:
            return self._round_robin(instances)
        elif self.strategy == LoadBalanceStrategy.LEAST_CONNECTIONS:
            return self._least_connections(instances)
        elif self.strategy == LoadBalanceStrategy.WEIGHTED:
            return self._weighted(instances)
        elif self.strategy == LoadBalanceStrategy.RANDOM:
            return random.choice(instances)
        return instances[0]

    def _round_robin(self, instances: List[ServiceInstance]) -> ServiceInstance:
        service_name = instances[0].service_name
        with self._lock:
            idx = self._round_robin_counters[service_name] % len(instances)
            self._round_robin_counters[service_name] += 1
        return instances[idx]

    def _least_connections(self, instances: List[ServiceInstance]) -> ServiceInstance:
        service_name = instances[0].service_name
        best = instances[0]
        min_conns = float("inf")
        with self._lock:
            for inst in instances:
                conns = self._connection_counts[service_name].get(inst.instance_id, 0)
                if conns < min_conns:
                    min_conns = conns
                    best = inst
            self._connection_counts[service_name][best.instance_id] += 1
        return best

    def _weighted(self, instances: List[ServiceInstance]) -> ServiceInstance:
        total_weight = sum(i.weight for i in instances)
        if total_weight <= 0:
            return instances[0]
        rand = random.uniform(0, total_weight)
        cumulative = 0.0
        for inst in instances:
            cumulative += inst.weight
            if rand <= cumulative:
                return inst
        return instances[-1]

    def increment_connections(self, service_name: str, instance_id: str):
        """Track an active connection."""
        with self._lock:
            self._connection_counts[service_name][instance_id] += 1

    def decrement_connections(self, service_name: str, instance_id: str):
        """Release a tracked connection."""
        with self._lock:
            count = self._connection_counts[service_name].get(instance_id, 0)
            if count > 0:
                self._connection_counts[service_name][instance_id] -= 1


# ---------------------------------------------------------------------------
# Resilience Manager
# ---------------------------------------------------------------------------


class ResilienceManager:
    """Centralized resilience policy enforcement.

    Wraps service calls with retry logic, timeouts, bulkhead isolation,
    and circuit breaker integration.
    """

    def __init__(
        self,
        registry: ServiceRegistry,
        retry_config: Optional[RetryConfig] = None,
    ):
        self.registry = registry
        self.retry_config = retry_config or RetryConfig()
        self._bulkheads: Dict[str, asyncio.Semaphore] = {}
        self._lock = threading.Lock()

    def set_bulkhead(self, service_name: str, max_concurrent: int):
        """Set a bulkhead limit for a service."""
        with self._lock:
            self._bulkheads[service_name] = asyncio.Semaphore(max_concurrent)

    async def call(
        self,
        service_name: str,
        func: Callable,
        *args,
        timeout_seconds: float = 30.0,
        **kwargs,
    ) -> Any:
        """Execute a resilient service call with all protections.

        Applies in order: bulkhead → timeout → circuit breaker → retry.
        """
        # Bulkhead check
        bulkhead = self._bulkheads.get(service_name)
        if bulkhead:
            async with bulkhead:
                return await self._execute_with_protections(service_name, func, timeout_seconds, *args, **kwargs)
        else:
            return await self._execute_with_protections(service_name, func, timeout_seconds, *args, **kwargs)

    async def _execute_with_protections(
        self,
        service_name: str,
        func: Callable,
        timeout_seconds: float,
        *args,
        **kwargs,
    ) -> Any:
        """Core execution with timeout, circuit breaker, and retries."""
        cb = self.registry.get_circuit_breaker(service_name)
        last_exception = None

        for attempt in range(self.retry_config.max_retries + 1):
            try:
                # Apply timeout
                result = await asyncio.wait_for(
                    self._call_through_circuit(cb, func, *args, **kwargs),
                    timeout=timeout_seconds,
                )
                return result
            except CircuitOpenError:
                raise  # Don't retry when circuit is open
            except asyncio.TimeoutError as exc:
                last_exception = exc
                logger.warning(
                    "Service '%s' timeout after %.1fs (attempt %d/%d)",
                    service_name, timeout_seconds, attempt + 1, self.retry_config.max_retries + 1,
                )
                if attempt < self.retry_config.max_retries:
                    await self._retry_delay(attempt)
            except Exception as exc:
                last_exception = exc
                if attempt < self.retry_config.max_retries:
                    logger.warning(
                        "Service '%s' call failed (attempt %d/%d): %s",
                        service_name, attempt + 1, self.retry_config.max_retries + 1, exc,
                    )
                    await self._retry_delay(attempt)
                else:
                    raise

        if last_exception:
            raise last_exception

    async def _call_through_circuit(self, cb: CircuitBreaker, func: Callable, *args, **kwargs) -> Any:
        """Execute through circuit breaker."""
        if asyncio.iscoroutinefunction(func):
            return await cb.acall(func, *args, **kwargs)
        else:
            # Run sync function in executor
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, lambda: cb.call(func, *args, **kwargs))

    async def _retry_delay(self, attempt: int):
        """Calculate and wait for retry delay."""
        delay = min(
            self.retry_config.base_delay_seconds * (self.retry_config.backoff_multiplier ** attempt),
            self.retry_config.max_delay_seconds,
        )
        if self.retry_config.jitter:
            delay = delay * (0.5 + random.random())
        await asyncio.sleep(delay)


# ---------------------------------------------------------------------------
# Service Mesh (Top-Level Facade)
# ---------------------------------------------------------------------------


class ServiceMesh:
    """Top-level service mesh facade.

    Coordinates service discovery, health checking, circuit breaking,
    load balancing, and resilience as a unified mesh layer.
    """

    def __init__(self):
        self.registry = ServiceRegistry()
        self.health_checker = HealthChecker(self.registry)
        self.load_balancer = LoadBalancer()
        self.resilience = ResilienceManager(self.registry)
        self._health_task: Optional[asyncio.Task] = None
        self._running = False

    # ── Lifecycle ────────────────────────────────────────────────────────

    def start_health_checks(self):
        """Start the health checker in a background asyncio task."""
        if self._running:
            return
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                self._health_task = asyncio.create_task(self.health_checker.start())
            else:
                # Start in a new event loop
                import threading
                def _run():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    new_loop.run_until_complete(self.health_checker.start())

                t = threading.Thread(target=_run, daemon=True, name="health-checker")
                t.start()
        except RuntimeError:
            import threading

            def _run():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                new_loop.run_until_complete(self.health_checker.start())

            t = threading.Thread(target=_run, daemon=True, name="health-checker")
            t.start()
        self._running = True
        logger.info("ServiceMesh health checks started")

    def stop_health_checks(self):
        """Stop health checking."""
        self._running = False
        if self._health_task:
            self._health_task.cancel()

    # ── Service Discovery ────────────────────────────────────────────────

    def register(self, service_name: str, host: str = "localhost", port: int = 8000,
                 version: str = "0.0.0", instance_id: Optional[str] = None, **metadata) -> str:
        """Register a service in the mesh."""
        import uuid

        instance = ServiceInstance(
            instance_id=instance_id or str(uuid.uuid4())[:8],
            service_name=service_name,
            host=host,
            port=port,
            version=version,
            metadata=metadata,
        )
        return self.registry.register(instance)

    def deregister(self, service_name: str, instance_id: str):
        """Remove a service from the mesh."""
        self.registry.deregister(service_name, instance_id)

    def discover_from_kernel(self):
        """Auto-discover services from the kernel."""
        self.registry.discover_from_kernel()

    def list_services(self) -> Dict[str, Dict[str, Any]]:
        """List all services in the mesh."""
        return self.registry.list_services()

    async def resolve(self, service_name: str) -> Optional[ServiceInstance]:
        """Resolve a service name to the best available instance.

        Uses load balancing to select among healthy instances.
        Returns None if no healthy instances are available.
        """
        instances = self.registry.get_instances(service_name, healthy_only=True)
        if not instances:
            logger.warning("No healthy instances for service: %s", service_name)
            return None
        return self.load_balancer.select(instances)

    # ── Resilience ──────────────────────────────────────────────────────

    async def call_service(self, service_name: str, func: Callable, *args,
                           timeout_seconds: float = 30.0, **kwargs) -> Any:
        """Call a service with full resilience protections."""
        return await self.resilience.call(
            service_name, func, *args, timeout_seconds=timeout_seconds, **kwargs
        )

    # ── Bulkheads ───────────────────────────────────────────────────────

    def set_bulkhead(self, service_name: str, max_concurrent: int):
        """Set a bulkhead concurrency limit for a service."""
        self.resilience.set_bulkhead(service_name, max_concurrent)

    # ── Stats ────────────────────────────────────────────────────────────

    def get_mesh_stats(self) -> Dict[str, Any]:
        """Get comprehensive mesh statistics."""
        services = self.list_services()
        cb_stats = self.registry.get_all_circuit_breakers()

        total_instances = sum(s["instance_count"] for s in services.values())
        total_healthy = sum(s["healthy_count"] for s in services.values())
        open_circuits = sum(1 for cb in cb_stats.values() if cb["state"] == "open")

        return {
            "services_count": len(services),
            "total_instances": total_instances,
            "healthy_instances": total_healthy,
            "degraded_instances": total_instances - total_healthy,
            "open_circuits": open_circuits,
            "services": services,
            "circuit_breakers": cb_stats,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_service_health(self, service_name: str) -> Dict[str, Any]:
        """Get detailed health for a specific service."""
        services = self.list_services()
        cb = self.registry.get_circuit_breaker(service_name)
        return {
            "service": service_name,
            "info": services.get(service_name, {}),
            "circuit_breaker": cb.get_stats(),
        }


# ---------------------------------------------------------------------------
# Dependency Graph
# ---------------------------------------------------------------------------


class MeshTopology:
    """Service dependency graph for visualization and analysis.

    Builds a directed graph of service dependencies from the kernel
    ModuleRegistry and exposes paths, fan-in/fan-out metrics.
    """

    def __init__(self, registry: ServiceRegistry):
        self.registry = registry

    def build_dependency_graph(self) -> Dict[str, List[str]]:
        """Build a dependency graph: {service_name: [dependent_service_names]}."""
        graph: Dict[str, List[str]] = defaultdict(list)
        try:
            from enterprise.kernel.registry import ModuleRegistry

            for mod_id in ModuleRegistry.list_all():
                spec = ModuleRegistry.get(mod_id)
                if spec:
                    graph[mod_id] = spec.dependencies
        except ImportError:
            pass
        return dict(graph)

    def get_dependents(self, service_name: str) -> List[str]:
        """Get all services that depend on a given service."""
        graph = self.build_dependency_graph()
        return [s for s, deps in graph.items() if service_name in deps]

    def get_fan_out(self, service_name: str) -> int:
        """Number of services this service depends on."""
        graph = self.build_dependency_graph()
        return len(graph.get(service_name, []))

    def get_fan_in(self, service_name: str) -> int:
        """Number of services that depend on this service."""
        return len(self.get_dependents(service_name))

    def get_topology_report(self) -> Dict[str, Any]:
        """Generate a full topology report."""
        graph = self.build_dependency_graph()
        nodes = []
        for svc, deps in graph.items():
            nodes.append({
                "service": svc,
                "dependencies": deps,
                "dependents": self.get_dependents(svc),
                "fan_in": self.get_fan_in(svc),
                "fan_out": self.get_fan_out(svc),
            })

        # Find root services (no dependencies)
        roots = [svc for svc, deps in graph.items() if not deps]
        # Find leaf services (no dependents)
        leaves = [svc for svc in graph if not self.get_dependents(svc)]

        return {
            "total_services": len(graph),
            "root_services": roots,
            "leaf_services": leaves,
            "nodes": nodes,
            "edges": [(svc, dep) for svc, deps in graph.items() for dep in deps],
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_mesh_instance: Optional[ServiceMesh] = None


def get_service_mesh() -> ServiceMesh:
    """Get the singleton ServiceMesh instance."""
    global _mesh_instance
    if _mesh_instance is None:
        _mesh_instance = ServiceMesh()
        _mesh_instance.discover_from_kernel()
    return _mesh_instance