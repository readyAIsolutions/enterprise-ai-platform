"""
Tests for ENI Enterprise Integration Layer — Service Mesh
=========================================================
Tests for service registry, circuit breaker, load balancer,
health checker, resilience manager, and mesh topology.
"""

import asyncio
import pytest
import time
import uuid
import threading

from enterprise.integration.service_mesh import (
    # Core
    ServiceMesh,
    ServiceRegistry,
    HealthChecker,
    HealthCheckConfig,
    HealthRecord,
    HealthStatus,
    # Circuit Breaker
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitOpenError,
    CircuitState,
    # Load Balancing
    LoadBalancer,
    LoadBalanceStrategy,
    # Resilience
    ResilienceManager,
    RetryConfig,
    # Data Models
    ServiceInstance,
    # Topology
    MeshTopology,
    # Singleton
    get_service_mesh,
)


# ---------------------------------------------------------------------------
# ServiceInstance Tests
# ---------------------------------------------------------------------------


class TestServiceInstance:
    """Tests for service instance data model."""

    def test_creation(self):
        instance = ServiceInstance(
            instance_id="test-1",
            service_name="test_svc",
            host="10.0.0.1",
            port=9000,
            version="2.1.0",
            weight=5,
            metadata={"region": "us-east"},
        )
        assert instance.instance_id == "test-1"
        assert instance.service_name == "test_svc"
        assert instance.host == "10.0.0.1"
        assert instance.port == 9000
        assert instance.version == "2.1.0"
        assert instance.weight == 5
        assert instance.metadata["region"] == "us-east"
        assert instance.status == HealthStatus.UNKNOWN

    def test_defaults(self):
        instance = ServiceInstance(
            instance_id="default-test",
            service_name="default_svc",
        )
        assert instance.host == "localhost"
        assert instance.port == 8000
        assert instance.version == "0.0.0"
        assert instance.weight == 1
        assert instance.registered_at is not None


# ---------------------------------------------------------------------------
# CircuitBreaker Tests
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    """Tests for the circuit breaker state machine."""

    def test_initial_state(self):
        cb = CircuitBreaker("test-cb")
        assert cb.state == CircuitState.CLOSED
        assert cb._failure_count == 0

    def test_successful_calls(self):
        cb = CircuitBreaker("test-cb")
        result = cb.call(lambda x: x * 2, 21)
        assert result == 42
        assert cb.state == CircuitState.CLOSED
        assert cb._total_successes == 1

    def test_circuit_opens_on_failures(self):
        config = CircuitBreakerConfig(failure_threshold=3, failure_rate_threshold=1.0)
        cb = CircuitBreaker("test-cb", config)

        for i in range(3):
            try:
                cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
            except RuntimeError:
                pass

        assert cb.state == CircuitState.OPEN

    def test_circuit_rejects_when_open(self):
        config = CircuitBreakerConfig(failure_threshold=1, recovery_timeout_seconds=9999)
        cb = CircuitBreaker("test-cb", config)

        # Open the circuit
        try:
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("f")))
        except RuntimeError:
            pass
        assert cb.state == CircuitState.OPEN

        # Should reject
        with pytest.raises(CircuitOpenError):
            cb.call(lambda: 42)

        assert cb._total_rejected == 1

    def test_half_open_and_recovery(self):
        # Use a very short recovery timeout
        config = CircuitBreakerConfig(
            failure_threshold=2,
            recovery_timeout_seconds=0.01,
            half_open_max_requests=5,
            failure_rate_threshold=1.0,
        )
        cb = CircuitBreaker("test-cb", config)

        # Open the circuit
        for _ in range(2):
            try:
                cb.call(lambda: (_ for _ in ()).throw(RuntimeError("f")))
            except RuntimeError:
                pass
        assert cb.state == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(0.02)

        # Should now allow requests in HALF_OPEN
        result = cb.call(lambda: 100)
        assert result == 100
        # Need enough successes to close
        for _ in range(5):
            cb.call(lambda: 1)
        assert cb.state == CircuitState.CLOSED

    def test_half_open_refails(self):
        config = CircuitBreakerConfig(
            failure_threshold=2,
            recovery_timeout_seconds=0.01,
            failure_rate_threshold=1.0,
        )
        cb = CircuitBreaker("test-cb", config)

        for _ in range(2):
            try:
                cb.call(lambda: (_ for _ in ()).throw(RuntimeError("f")))
            except RuntimeError:
                pass
        assert cb.state == CircuitState.OPEN

        time.sleep(0.02)

        # First call in half-open fails
        try:
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("f2")))
        except RuntimeError:
            pass

        assert cb.state == CircuitState.OPEN  # Should reopen

    def test_force_close(self):
        config = CircuitBreakerConfig(failure_threshold=1, recovery_timeout_seconds=999)
        cb = CircuitBreaker("test-cb", config)
        try:
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("f")))
        except RuntimeError:
            pass
        assert cb.state == CircuitState.OPEN
        cb.force_close()
        assert cb.state == CircuitState.CLOSED

    def test_get_stats(self):
        cb = CircuitBreaker("stats-cb")
        cb.call(lambda: 1)
        try:
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("f")))
        except RuntimeError:
            pass
        stats = cb.get_stats()
        assert stats["name"] == "stats-cb"
        assert stats["total_successes"] == 1
        assert stats["total_failures"] == 1
        assert "state" in stats

    def test_rate_based_opening(self):
        config = CircuitBreakerConfig(
            failure_threshold=100,  # Won't trigger by count
            failure_rate_threshold=0.3,
            sliding_window_size=10,
        )
        cb = CircuitBreaker("rate-cb", config)

        # 4 failures out of 5 = 0.8 > 0.3 threshold — should trip on the first success
        for i in range(4):
            try:
                cb.call(lambda: (_ for _ in ()).throw(RuntimeError("f")))
            except RuntimeError:
                pass

        # This success should trigger the rate-based opening
        try:
            cb.call(lambda: 1)
        except CircuitOpenError:
            pass  # Expected — circuit opened on the rate check

        assert cb.state == CircuitState.OPEN

    async def test_async_call(self):
        cb = CircuitBreaker("async-cb")

        async def async_func(x):
            return x * 3

        result = await cb.acall(async_func, 7)
        assert result == 21
        assert cb._total_successes == 1

    async def test_async_call_failure(self):
        config = CircuitBreakerConfig(failure_threshold=1, recovery_timeout_seconds=999)
        cb = CircuitBreaker("async-fail-cb", config)

        async def failing_async():
            raise RuntimeError("async fail")

        try:
            await cb.acall(failing_async)
        except RuntimeError:
            pass
        assert cb.state == CircuitState.OPEN


# ---------------------------------------------------------------------------
# ServiceRegistry Tests
# ---------------------------------------------------------------------------


class TestServiceRegistry:
    """Tests for service discovery and registration."""

    def test_register_and_discover(self):
        registry = ServiceRegistry()
        instance = ServiceInstance(
            instance_id="svc-1",
            service_name="api_gateway",
            host="0.0.0.0",
            port=8000,
            version="1.0.0",
        )
        registry.register(instance)
        services = registry.list_services()
        assert "api_gateway" in services
        assert services["api_gateway"]["instance_count"] == 1

    def test_get_instances_healthy_only(self):
        registry = ServiceRegistry()
        i1 = ServiceInstance(instance_id="a", service_name="svc")
        i2 = ServiceInstance(instance_id="b", service_name="svc")
        registry.register(i1)
        registry.register(i2)

        # Mark only one healthy
        registry.update_health("a", healthy=True)
        registry.update_health("b", healthy=False)

        healthy = registry.get_instances("svc", healthy_only=True)
        assert len(healthy) == 1
        assert healthy[0].instance_id == "a"

        all_instances = registry.get_instances("svc", healthy_only=False)
        assert len(all_instances) == 2

    def test_deregister(self):
        registry = ServiceRegistry()
        instance = ServiceInstance(instance_id="tmp", service_name="tmp_svc")
        registry.register(instance)
        registry.deregister("tmp_svc", "tmp")
        assert len(registry.list_services()) == 0

    def test_heartbeat(self):
        registry = ServiceRegistry()
        instance = ServiceInstance(instance_id="hb", service_name="hb_svc")
        registry.register(instance)
        registry.heartbeat("hb")
        inst = registry.get_instance("hb_svc", "hb")
        assert inst.last_heartbeat is not None

    def test_circuit_breaker_auto_creation(self):
        registry = ServiceRegistry()
        instance = ServiceInstance(instance_id="cb", service_name="cb_svc")
        registry.register(instance)
        cb = registry.get_circuit_breaker("cb_svc")
        assert cb is not None
        assert cb.state == CircuitState.CLOSED

    def test_update_health_consecutive_failures(self):
        registry = ServiceRegistry()
        instance = ServiceInstance(instance_id="flaky", service_name="flaky_svc")
        registry.register(instance)

        for _ in range(3):
            registry.update_health("flaky", healthy=False, error="timeout")

        instances = registry.get_instances("flaky_svc", healthy_only=True)
        assert len(instances) == 0

        # Recover
        for _ in range(3):
            registry.update_health("flaky", healthy=True, latency_ms=5.0)

        instances = registry.get_instances("flaky_svc", healthy_only=True)
        assert len(instances) == 1

    def test_health_record_tracking(self):
        registry = ServiceRegistry()
        instance = ServiceInstance(instance_id="track", service_name="track_svc")
        registry.register(instance)

        registry.update_health("track", healthy=True, latency_ms=12.5)
        registry.update_health("track", healthy=False, latency_ms=50.0, error="timeout")

        record = registry._health_records.get("track")
        assert record is not None
        assert record.total_checks == 2
        assert record.total_failures == 1
        assert record.last_latency_ms == 50.0
        assert record.last_error == "timeout"


# ---------------------------------------------------------------------------
# LoadBalancer Tests
# ---------------------------------------------------------------------------


class TestLoadBalancer:
    """Tests for load balancing strategies."""

    def test_round_robin(self):
        lb = LoadBalancer(strategy=LoadBalanceStrategy.ROUND_ROBIN)
        instances = [
            ServiceInstance(instance_id=f"r{i}", service_name="svc", weight=1)
            for i in range(3)
        ]
        # Select 6 times, each should come up twice in order
        selected = [lb.select(instances).instance_id for _ in range(6)]
        assert selected.count("r0") == 2
        assert selected.count("r1") == 2
        assert selected.count("r2") == 2

    def test_weighted(self):
        lb = LoadBalancer(strategy=LoadBalanceStrategy.WEIGHTED)
        instances = [
            ServiceInstance(instance_id="heavy", service_name="svc", weight=10),
            ServiceInstance(instance_id="light", service_name="svc", weight=1),
        ]
        # Heavy instance should be selected much more often
        results = [lb.select(instances).instance_id for _ in range(100)]
        assert results.count("heavy") > results.count("light")

    def test_random(self):
        lb = LoadBalancer(strategy=LoadBalanceStrategy.RANDOM)
        instances = [
            ServiceInstance(instance_id=f"r{i}", service_name="svc")
            for i in range(5)
        ]
        selected = lb.select(instances)
        assert selected is not None

    def test_empty_instances(self):
        lb = LoadBalancer()
        result = lb.select([])
        assert result is None

    def test_single_instance(self):
        lb = LoadBalancer()
        instance = ServiceInstance(instance_id="only", service_name="svc")
        result = lb.select([instance])
        assert result.instance_id == "only"

    def test_least_connections(self):
        lb = LoadBalancer(strategy=LoadBalanceStrategy.LEAST_CONNECTIONS)
        instances = [
            ServiceInstance(instance_id="a", service_name="svc"),
            ServiceInstance(instance_id="b", service_name="svc"),
        ]
        lb.increment_connections("svc", "a")  # a has 1, b has 0
        result = lb.select(instances)
        assert result.instance_id == "b"  # Should pick least busy


# ---------------------------------------------------------------------------
# ResilienceManager Tests
# ---------------------------------------------------------------------------


class TestResilienceManager:
    """Tests for resilience patterns."""

    def test_retry_config(self):
        config = RetryConfig(
            max_retries=5,
            base_delay_seconds=0.1,
            max_delay_seconds=10.0,
            backoff_multiplier=2.0,
            jitter=True,
        )
        assert config.max_retries == 5
        assert config.base_delay_seconds == 0.1
        assert config.backoff_multiplier == 2.0
        assert config.jitter is True

    async def test_successful_call(self):
        registry = ServiceRegistry()
        registry.register(ServiceInstance(instance_id="ok", service_name="ok_svc"))
        rm = ResilienceManager(registry)

        async def ok_func():
            return "success"

        result = await rm.call("ok_svc", ok_func, timeout_seconds=5.0)
        assert result == "success"

    async def test_call_with_timeout(self):
        registry = ServiceRegistry()
        registry.register(ServiceInstance(instance_id="slow", service_name="slow_svc"))
        rm = ResilienceManager(registry, RetryConfig(max_retries=0))

        async def slow_func():
            await asyncio.sleep(10)
            return "too late"

        with pytest.raises(asyncio.TimeoutError):
            await rm.call("slow_svc", slow_func, timeout_seconds=0.01)

    async def test_circuit_open_rejection(self):
        registry = ServiceRegistry()
        config = CircuitBreakerConfig(failure_threshold=1, recovery_timeout_seconds=999)
        registry._circuit_breakers["fail_svc"] = CircuitBreaker("fail_svc", config)
        registry.register(ServiceInstance(instance_id="f", service_name="fail_svc"))
        rm = ResilienceManager(registry, RetryConfig(max_retries=0))

        async def fail_func():
            raise RuntimeError("fail")

        # Open the circuit
        try:
            await rm.call("fail_svc", fail_func, timeout_seconds=5.0)
        except RuntimeError:
            pass

        # Second call should be rejected
        with pytest.raises(CircuitOpenError):
            await rm.call("fail_svc", fail_func, timeout_seconds=5.0)

    def test_bulkhead(self):
        registry = ServiceRegistry()
        instance = ServiceInstance(instance_id="bh", service_name="bh_svc")
        registry.register(instance)
        rm = ResilienceManager(registry)
        rm.set_bulkhead("bh_svc", max_concurrent=5)
        assert "bh_svc" in rm._bulkheads
        assert rm._bulkheads["bh_svc"]._value == 5


# ---------------------------------------------------------------------------
# MeshTopology Tests
# ---------------------------------------------------------------------------


class TestMeshTopology:
    """Tests for service dependency graph."""

    def test_build_graph(self):
        registry = ServiceRegistry()
        topo = MeshTopology(registry)
        graph = topo.build_dependency_graph()
        assert isinstance(graph, dict)
        # If kernel is available, graph should have entries
        # If not, graph may be empty (graceful degradation)

    def test_get_dependents_empty(self):
        registry = ServiceRegistry()
        topo = MeshTopology(registry)
        deps = topo.get_dependents("nonexistent")
        assert isinstance(deps, list)
        assert len(deps) == 0

    def test_topology_report(self):
        registry = ServiceRegistry()
        topo = MeshTopology(registry)
        report = topo.get_topology_report()
        assert "total_services" in report
        assert "root_services" in report
        assert "leaf_services" in report
        assert "nodes" in report
        assert "edges" in report


# ---------------------------------------------------------------------------
# ServiceMesh (Facade) Tests
# ---------------------------------------------------------------------------


class TestServiceMesh:
    """Tests for the top-level ServiceMesh facade."""

    def test_register_and_list(self):
        mesh = ServiceMesh()
        mesh.register("test_svc", host="127.0.0.1", port=9999, version="3.0.0", region="local")
        services = mesh.list_services()
        assert "test_svc" in services
        assert services["test_svc"]["instance_count"] == 1

    def test_deregister(self):
        mesh = ServiceMesh()
        inst_id = mesh.register("temp_svc")
        mesh.deregister("temp_svc", inst_id)
        assert "temp_svc" not in mesh.list_services()

    def test_set_bulkhead(self):
        mesh = ServiceMesh()
        mesh.set_bulkhead("bh_svc", 10)
        assert "bh_svc" in mesh.resilience._bulkheads

    def test_get_mesh_stats(self):
        mesh = ServiceMesh()
        mesh.register("stats_svc", host="localhost", port=8000)
        stats = mesh.get_mesh_stats()
        assert stats["services_count"] >= 1
        assert "circuit_breakers" in stats
        assert "timestamp" in stats

    def test_get_service_health(self):
        mesh = ServiceMesh()
        mesh.register("health_svc", host="localhost", port=8000)
        health = mesh.get_service_health("health_svc")
        assert health["service"] == "health_svc"
        assert "circuit_breaker" in health

    def test_discover_from_kernel(self):
        mesh = ServiceMesh()
        # This should gracefully handle missing kernel
        mesh.discover_from_kernel()
        # Should not raise

    async def test_resolve_no_healthy(self):
        mesh = ServiceMesh()
        result = await mesh.resolve("nonexistent")
        assert result is None

    async def test_resolve_with_healthy(self):
        mesh = ServiceMesh()
        inst_id = mesh.register("resolvable", host="localhost", port=8000)
        mesh.registry.update_health(inst_id, healthy=True)
        result = await mesh.resolve("resolvable")
        assert result is not None
        assert result.service_name == "resolvable"


# ---------------------------------------------------------------------------
# Singleton Tests
# ---------------------------------------------------------------------------


class TestSingleton:
    """Tests for singleton access patterns."""

    def test_get_service_mesh_singleton(self):
        mesh1 = get_service_mesh()
        mesh2 = get_service_mesh()
        assert mesh1 is mesh2

    def test_singleton_is_service_mesh(self):
        mesh = get_service_mesh()
        assert isinstance(mesh, ServiceMesh)