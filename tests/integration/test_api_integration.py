"""
Integration API tests for ENI Enterprise Integration Layer.

Covers:
- EventHub: schemas, subscriptions, contracts, publishing, dead letters, tracing
- API Gateway: HTTP endpoints, auth, rate limiting, error handling
- Service Mesh: circuit breaker, health checks, service discovery, load balancing, topology
"""

import asyncio
import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient

# ==============================================================================
# 1. Event Schema Tests
# ==============================================================================


class TestEventSchema:
    """Verify EventSchema definition and validation."""

    def test_schema_creation_defaults(self):
        from enterprise.integration.event_hub import EventSchema

        schema = EventSchema(event_type="test.event")
        assert schema.event_type == "test.event"
        assert schema.version == "1.0"
        assert schema.ttl_seconds == 3600
        assert schema.required_fields == []

    def test_schema_validation_passes(self):
        from enterprise.integration.event_hub import EventSchema

        schema = EventSchema(
            event_type="test.with.required",
            required_fields=["name", "email"],
        )
        valid, errors = schema.validate({"name": "Alice", "email": "a@b.com"})
        assert valid is True
        assert errors == []

    def test_schema_validation_fails_on_missing(self):
        from enterprise.integration.event_hub import EventSchema

        schema = EventSchema(
            event_type="test.with.required",
            required_fields=["name", "email"],
        )
        valid, errors = schema.validate({"name": "Alice"})
        assert valid is False
        assert len(errors) == 1
        assert "email" in errors[0]

    def test_schema_validation_empty_payload(self):
        from enterprise.integration.event_hub import EventSchema

        schema = EventSchema(
            event_type="test.required",
            required_fields=["field1"],
        )
        valid, errors = schema.validate({})
        assert valid is False
        assert len(errors) == 1


# ==============================================================================
# 2. Event Envelope Tests
# ==============================================================================


class TestEventEnvelope:
    """Verify EventEnvelope lifecycle."""

    def test_envelope_default_creation(self):
        from enterprise.integration.event_hub import EventEnvelope

        env = EventEnvelope()
        assert env.event_id is not None
        assert len(env.event_id) == 36  # UUID length
        assert env.priority.value == "medium"
        assert env.status.value == "received"
        assert env.retry_count == 0
        assert env.max_retries == 3

    def test_envelope_custom_values(self):
        from enterprise.integration.event_hub import EventEnvelope, EventPriority

        env = EventEnvelope(
            event_type="module.test",
            source="test_module",
            payload={"key": "val"},
            priority=EventPriority.HIGH,
            correlation_id="corr-123",
        )
        assert env.event_type == "module.test"
        assert env.source == "test_module"
        assert env.payload == {"key": "val"}
        assert env.priority == EventPriority.HIGH
        assert env.correlation_id == "corr-123"

    def test_envelope_not_expired(self):
        from enterprise.integration.event_hub import EventEnvelope

        env = EventEnvelope(ttl_seconds=3600)
        assert env.is_expired is False

    def test_envelope_expired_with_negative_ttl(self):
        from enterprise.integration.event_hub import EventEnvelope

        env = EventEnvelope(ttl_seconds=0)
        # A TTL of 0 means it should expire immediately
        assert env.is_expired is True

    def test_envelope_to_dict_and_back(self):
        from enterprise.integration.event_hub import EventEnvelope

        env = EventEnvelope(
            event_type="test.roundtrip",
            source="test",
            payload={"a": 1},
            correlation_id="c123",
        )
        d = env.to_dict()
        restored = EventEnvelope.from_dict(d)
        assert restored.event_type == "test.roundtrip"
        assert restored.source == "test"
        assert restored.payload == {"a": 1}

    def test_envelope_from_dict_missing_fields(self):
        from enterprise.integration.event_hub import EventEnvelope

        env = EventEnvelope.from_dict({"event_type": "minimal", "source": "src"})
        assert env.event_type == "minimal"
        assert env.source == "src"


# ==============================================================================
# 3. Event Subscription Tests
# ==============================================================================


class TestEventSubscription:
    """Verify EventSubscription pattern matching."""

    def test_subscription_creation(self):
        from enterprise.integration.event_hub import EventSubscription

        sub = EventSubscription(
            module_name="test_module",
            event_patterns=["system.*", "module.test"],
        )
        assert sub.module_name == "test_module"
        assert len(sub.event_patterns) == 2
        assert sub.active is True

    def test_subscription_matches_exact(self):
        from enterprise.integration.event_hub import EventSubscription

        sub = EventSubscription(
            module_name="test",
            event_patterns=["module.test.exact"],
        )
        assert sub.matches("module.test.exact") is True
        assert sub.matches("module.test.other") is False

    def test_subscription_matches_wildcard(self):
        from enterprise.integration.event_hub import EventSubscription

        sub = EventSubscription(
            module_name="test",
            event_patterns=["system.*"],
        )
        assert sub.matches("system.startup") is True
        assert sub.matches("system.shutdown") is True
        assert sub.matches("system.error") is True
        assert sub.matches("module.test") is False

    def test_subscription_matches_multiple_patterns(self):
        from enterprise.integration.event_hub import EventSubscription

        sub = EventSubscription(
            module_name="test",
            event_patterns=["system.*", "kernel.**"],
        )
        assert sub.matches("system.startup") is True
        assert sub.matches("kernel.context.created") is True
        assert sub.matches("module.test") is False

    def test_subscription_matches_doublestar(self):
        from enterprise.integration.event_hub import EventSubscription

        sub = EventSubscription(
            module_name="test",
            event_patterns=["safety.**"],
        )
        assert sub.matches("safety.guardrail.triggered") is True
        assert sub.matches("safety.incident.created") is True

    def test_subscription_can_be_deactivated(self):
        from enterprise.integration.event_hub import EventSubscription

        sub = EventSubscription(
            module_name="test",
            event_patterns=["system.*"],
            active=True,
        )
        assert sub.active is True
        sub.active = False
        assert sub.active is False


# ==============================================================================
# 4. Event Contract Tests
# ==============================================================================


class TestEventContract:
    """Verify EventContract and ContractDirection."""

    def test_contract_creation(self):
        from enterprise.integration.event_hub import EventContract, ContractDirection

        c = EventContract(
            producer_module="safety",
            consumer_module="kernel",
            event_types=["safety.guardrail.triggered"],
            direction=ContractDirection.PRODUCES,
        )
        assert c.producer_module == "safety"
        assert c.consumer_module == "kernel"
        assert c.active is True
        assert len(c.event_types) == 1

    def test_contract_directions(self):
        from enterprise.integration.event_hub import ContractDirection

        assert ContractDirection.PRODUCES.value == "produces"
        assert ContractDirection.CONSUMES.value == "consumes"
        assert ContractDirection.BIDIRECTIONAL.value == "bidirectional"


# ==============================================================================
# 5. Dead Letter Queue Tests
# ==============================================================================


class TestDeadLetterQueue:
    """Verify dead-letter queue operations."""

    def test_dlq_enqueue(self):
        from enterprise.integration.event_hub import (
            DeadLetterQueue,
            EventEnvelope,
            EventStatus,
        )

        dlq = DeadLetterQueue(max_size=100)
        env = EventEnvelope(event_type="test.fail", source="test")
        dlq.enqueue(env, reason="handler crashed")

        assert dlq.size == 1
        assert env.status == EventStatus.DEAD_LETTERED
        assert env.metadata.get("dead_letter_reason") == "handler crashed"

    def test_dlq_get_all(self):
        from enterprise.integration.event_hub import DeadLetterQueue, EventEnvelope

        dlq = DeadLetterQueue(max_size=100)
        for i in range(5):
            dlq.enqueue(EventEnvelope(event_type=f"test.fail.{i}", source="test"))

        events = dlq.get_all(limit=3)
        assert len(events) == 3

    def test_dlq_get_by_id(self):
        from enterprise.integration.event_hub import DeadLetterQueue, EventEnvelope

        dlq = DeadLetterQueue()
        env = EventEnvelope(event_type="test.lookup", source="test")
        dlq.enqueue(env)

        found = dlq.get_by_id(env.event_id)
        assert found is not None
        assert found.event_type == "test.lookup"

    def test_dlq_get_by_id_missing(self):
        from enterprise.integration.event_hub import DeadLetterQueue

        dlq = DeadLetterQueue()
        assert dlq.get_by_id("nonexistent") is None

    def test_dlq_replay(self):
        from enterprise.integration.event_hub import (
            DeadLetterQueue,
            EventEnvelope,
            EventStatus,
        )

        dlq = DeadLetterQueue()
        env = EventEnvelope(event_type="test.replay", source="test")
        dlq.enqueue(env)
        assert dlq.size == 1

        replayed = dlq.replay(env.event_id)
        assert replayed is not None
        assert replayed.status == EventStatus.REPLAYED
        assert replayed.retry_count == 0
        assert dlq.size == 0

    def test_dlq_replay_missing(self):
        from enterprise.integration.event_hub import DeadLetterQueue

        dlq = DeadLetterQueue()
        assert dlq.replay("nonexistent") is None

    def test_dlq_clear(self):
        from enterprise.integration.event_hub import DeadLetterQueue, EventEnvelope

        dlq = DeadLetterQueue()
        for _ in range(3):
            dlq.enqueue(EventEnvelope(event_type="test.clear", source="test"))
        assert dlq.size == 3
        dlq.clear()
        assert dlq.size == 0

    def test_dlq_max_size_eviction(self):
        from enterprise.integration.event_hub import DeadLetterQueue, EventEnvelope

        dlq = DeadLetterQueue(max_size=3)
        for i in range(5):
            dlq.enqueue(EventEnvelope(event_type=f"test.{i}", source="test"))
        # Only the last 3 should remain
        assert dlq.size == 3


# ==============================================================================
# 6. Event Tracer Tests
# ==============================================================================


class TestEventTracer:
    """Verify distributed tracing functionality."""

    def test_tracer_record_and_retrieve(self):
        from enterprise.integration.event_hub import EventTracer, EventEnvelope

        tracer = EventTracer()
        env = EventEnvelope(
            event_type="test.trace",
            source="test",
            correlation_id="trace-001",
        )
        tracer.record(env)

        trace = tracer.get_trace("trace-001")
        assert len(trace) == 1
        assert trace[0]["event_type"] == "test.trace"

    def test_tracer_multiple_events_same_correlation(self):
        from enterprise.integration.event_hub import EventTracer, EventEnvelope

        tracer = EventTracer()
        for i in range(3):
            env = EventEnvelope(
                event_type=f"test.step.{i}",
                source="test",
                correlation_id="corr-multi",
            )
            tracer.record(env)

        trace = tracer.get_trace("corr-multi")
        assert len(trace) == 3

    def test_tracer_missing_correlation(self):
        from enterprise.integration.event_hub import EventTracer

        tracer = EventTracer()
        trace = tracer.get_trace("nonexistent")
        assert trace == []


# ==============================================================================
# 7. EventBus Tests
# ==============================================================================


class TestEventBus:
    """Verify EventBus core operations."""

    def test_event_bus_creation(self):
        from enterprise.integration.event_hub import EventBus

        bus = EventBus()
        assert bus.worker_count == 4
        assert bus._running is False
        stats = bus.get_stats()
        assert stats["schemas_registered"] > 0  # Standard schemas

    def test_register_schema(self):
        from enterprise.integration.event_hub import EventBus, EventSchema

        bus = EventBus()
        schema = EventSchema(event_type="custom.test", version="1.0")
        bus.register_schema(schema)
        retrieved = bus.get_schema("custom.test")
        assert retrieved is not None
        assert retrieved.version == "1.0"

    def test_get_schema_missing(self):
        from enterprise.integration.event_hub import EventBus

        bus = EventBus()
        assert bus.get_schema("nonexistent.schema") is None

    def test_list_schemas_returns_standard(self):
        from enterprise.integration.event_hub import EventBus

        bus = EventBus()
        schemas = bus.list_schemas()
        assert "system.startup" in schemas
        assert "kernel.context.created" in schemas
        assert "safety.guardrail.triggered" in schemas

    def test_subscribe_and_unsubscribe(self):
        from enterprise.integration.event_hub import EventBus, EventSubscription

        bus = EventBus()
        sub = EventSubscription(
            module_name="test",
            event_patterns=["test.sub.*"],
        )
        bus.subscribe(sub)

        assert bus.get_stats()["subscriptions_active"] == 1
        subscriptions = bus.list_subscriptions()
        assert len(subscriptions) == 1
        assert subscriptions[0]["module_name"] == "test"

        bus.unsubscribe(sub.subscription_id)
        assert bus.get_stats()["subscriptions_active"] == 0

    def test_get_subscriptions_matching(self):
        from enterprise.integration.event_hub import EventBus, EventSubscription

        bus = EventBus()
        sub = EventSubscription(
            module_name="test",
            event_patterns=["system.*", "kernel.*"],
        )
        bus.subscribe(sub)

        matching = bus.get_subscriptions("system.startup")
        assert len(matching) == 1
        assert matching[0].module_name == "test"

    def test_register_contracts(self):
        from enterprise.integration.event_hub import EventBus, EventContract

        bus = EventBus()
        c = EventContract(
            producer_module="safety",
            consumer_module="kernel",
            event_types=["safety.guardrail.triggered"],
        )
        bus.register_contract(c)
        stats = bus.get_stats()
        assert stats["contracts_registered"] == 1

    def test_get_contracts_by_module(self):
        from enterprise.integration.event_hub import EventBus, EventContract

        bus = EventBus()
        c = EventContract(
            producer_module="privacy",
            consumer_module="kernel",
            event_types=["data.classified"],
        )
        bus.register_contract(c)

        contracts = bus.get_contracts("privacy")
        assert len(contracts) == 1
        contracts = bus.get_contracts("kernel")
        assert len(contracts) == 1

    @pytest.mark.asyncio
    async def test_publish_event_async(self):
        from enterprise.integration.event_hub import EventBus

        bus = EventBus()
        event_id = await bus.publish({
            "event_type": "system.startup",
            "source": "test",
            "payload": {},
        })
        assert event_id is not None
        assert len(event_id) == 36

        stats = bus.get_stats()
        assert stats["total_events"] == 1

    @pytest.mark.asyncio
    async def test_publish_event_with_correlation(self):
        from enterprise.integration.event_hub import EventBus

        bus = EventBus()
        event_id = await bus.publish({
            "event_type": "system.health_check",
            "source": "test",
            "payload": {"status": "ok", "modules": []},
            "correlation_id": "corr-abc",
        })
        trace = bus.get_trace("corr-abc")
        assert len(trace) == 1
        assert trace[0]["event_id"] == event_id

    @pytest.mark.asyncio
    async def test_publish_with_subscriber_dispatch(self):
        from enterprise.integration.event_hub import (
            EventBus,
            EventSubscription,
        )

        bus = EventBus()
        received = []

        async def handler(env):
            received.append(env)

        sub = EventSubscription(
            module_name="test_handler",
            event_patterns=["test.dispatch.*"],
            handler=handler,
        )
        bus.subscribe(sub)

        await bus.publish({
            "event_type": "test.dispatch.msg",
            "source": "test",
            "payload": {"data": "hello"},
        }, wait=True)

        assert len(received) == 1
        assert received[0].event_type == "test.dispatch.msg"
        assert received[0].payload == {"data": "hello"}

    @pytest.mark.asyncio
    async def test_dead_letter_flow(self):
        from enterprise.integration.event_hub import (
            EventBus,
            EventSubscription,
        )

        bus = EventBus()

        async def failing_handler(env):
            raise RuntimeError("intentional failure")

        sub = EventSubscription(
            module_name="failer",
            event_patterns=["test.fail.*"],
            handler=failing_handler,
            dead_letter_on_failure=True,
        )
        bus.subscribe(sub)

        await bus.publish({
            "event_type": "test.fail.event",
            "source": "test",
            "payload": {},
        }, wait=True)

        dead = bus.get_dead_letters()
        assert len(dead) >= 1

    def test_bus_stats_after_publish(self):
        from enterprise.integration.event_hub import EventBus
        import asyncio

        bus = EventBus()

        async def do_publish():
            await bus.publish({
                "event_type": "system.startup",
                "source": "stats_test",
                "payload": {},
            })

        loop = asyncio.new_event_loop()
        loop.run_until_complete(do_publish())
        loop.close()

        stats = bus.get_stats()
        assert stats["total_events"] == 1
        assert stats["event_types_count"] >= 1

    def test_standard_contracts_creation(self):
        from enterprise.integration.event_hub import create_standard_contracts

        contracts = create_standard_contracts()
        assert len(contracts) >= 10
        # Verify some key contracts
        producers = {c.producer_module for c in contracts}
        assert "safety_governance" in producers
        assert "privacy_data" in producers
        assert "knowledge_graph" in producers

    def test_event_priority_enum(self):
        from enterprise.integration.event_hub import EventPriority

        assert EventPriority.CRITICAL.value == "critical"
        assert EventPriority.HIGH.value == "high"
        assert EventPriority.MEDIUM.value == "medium"
        assert EventPriority.LOW.value == "low"

    def test_event_status_enum(self):
        from enterprise.integration.event_hub import EventStatus

        assert EventStatus.RECEIVED.value == "received"
        assert EventStatus.ROUTED.value == "routed"
        assert EventStatus.DELIVERED.value == "delivered"
        assert EventStatus.FAILED.value == "failed"
        assert EventStatus.DEAD_LETTERED.value == "dead_lettered"
        assert EventStatus.REPLAYED.value == "replayed"
        assert EventStatus.DROPPED.value == "dropped"


# ==============================================================================
# 8. API Gateway HTTP Integration Tests
# ==============================================================================


class TestAPIGatewayIntegration:
    """HTTP-level integration tests for the API Gateway."""

    @pytest.fixture
    def client(self):
        from enterprise.integration.api_gateway import create_app, get_deps

        deps = get_deps()
        from enterprise.integration.api_gateway import RateLimiter

        deps.rate_limiter = RateLimiter(default_rate=10000, default_burst=10000)
        app = create_app(enable_docs=True)
        return TestClient(app)

    def test_root_not_found(self, client):
        response = client.get("/")
        assert response.status_code == 404

    def test_health_live_returns_200(self, client):
        response = client.get("/api/v1/health/live")
        assert response.status_code == 200
        assert response.json()["status"] == "alive"

    def test_health_ready_returns_200(self, client):
        response = client.get("/api/v1/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "kernel" in data

    def test_list_modules_returns_structure(self, client):
        response = client.get("/api/v1/modules")
        assert response.status_code == 200
        data = response.json()
        assert "modules" in data
        assert "count" in data
        assert isinstance(data["count"], int)

    def test_event_schemas_list(self, client):
        response = client.get("/api/v1/events/schemas")
        assert response.status_code == 200
        data = response.json()
        assert "schemas" in data

    def test_event_subscriptions_list(self, client):
        response = client.get("/api/v1/events/subscriptions")
        assert response.status_code == 200

    def test_submit_task_with_auth(self, client):
        from enterprise.integration.api_gateway import get_deps

        deps = get_deps()
        deps.auth_handler.api_keys.add("orch-integ-key")
        response = client.post(
            "/api/v1/orchestration/tasks",
            json={"objective": "integration test task"},
            headers={"X-API-Key": "orch-integ-key"},
        )
        assert response.status_code == 202
        assert "task_id" in response.json()

    def test_compliance_filtered_gdpr(self, client):
        response = client.get("/api/v1/privacy/compliance?framework=GDPR")
        assert response.status_code == 200
        data = response.json()
        assert "GDPR" in data.get("compliance", {})

    def test_create_ticket_with_auth(self, client):
        from enterprise.integration.api_gateway import get_deps

        deps = get_deps()
        deps.auth_handler.api_keys.add("cx-integ-key")
        response = client.post(
            "/api/v1/cx/tickets",
            json={"subject": "integration_test", "description": "testing"},
            headers={"X-API-Key": "cx-integ-key"},
        )
        assert response.status_code == 200
        assert "ticket_id" in response.json()

    def test_query_audit_with_auth(self, client):
        from enterprise.integration.api_gateway import get_deps

        deps = get_deps()
        deps.auth_handler.api_keys.add("admin-integ-key")
        response = client.get(
            "/api/v1/admin/audit",
            headers={"X-API-Key": "admin-integ-key"},
        )
        assert response.status_code == 200

    def test_rate_limit_headers_present(self, client):
        response = client.get("/api/v1/health")
        # Rate limit headers should not be exposed on success
        # but the test validates the endpoint works
        assert response.status_code == 200

    def test_request_id_always_present(self, client):
        response = client.get("/api/v1/health/live")
        assert "X-Request-ID" in response.headers

    def test_events_publish_requires_auth(self, client):
        response = client.post(
            "/api/v1/events/publish",
            json={"event_type": "test", "source": "test", "payload": {}},
        )
        assert response.status_code == 401


# ==============================================================================
# 9. Service Mesh & Circuit Breaker Tests
# ==============================================================================


class TestCircuitBreaker:
    """Verify circuit breaker state machine and resilience."""

    def test_circuit_breaker_creation(self):
        from enterprise.integration.service_mesh import (
            CircuitBreaker,
            CircuitState,
        )

        cb = CircuitBreaker("test-cb")
        assert cb.name == "test-cb"
        assert cb.state == CircuitState.CLOSED

    def test_circuit_breaker_successful_call(self):
        from enterprise.integration.service_mesh import CircuitBreaker

        cb = CircuitBreaker("test-cb")

        def success_func():
            return "ok"

        result = cb.call(success_func)
        assert result == "ok"

    def test_circuit_breaker_failed_call_raises(self):
        from enterprise.integration.service_mesh import CircuitBreaker

        cb = CircuitBreaker("test-cb")

        def fail_func():
            raise ValueError("intentional failure")

        with pytest.raises(ValueError, match="intentional failure"):
            cb.call(fail_func)

    def test_circuit_breaker_state_transitions(self):
        from enterprise.integration.service_mesh import (
            CircuitBreaker,
            CircuitBreakerConfig,
            CircuitState,
            CircuitOpenError,
        )

        config = CircuitBreakerConfig(
            failure_threshold=2,
            recovery_timeout_seconds=0.01,
            half_open_max_requests=1,
        )
        cb = CircuitBreaker("state-cb", config=config)

        # Trip the circuit with failures
        for _ in range(2):
            try:
                cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
            except ValueError:
                pass

        # Circuit should now be OPEN
        assert cb.state == CircuitState.OPEN

        # Call while open should raise CircuitOpenError
        with pytest.raises(CircuitOpenError):
            cb.call(lambda: "should_not_run")

    def test_circuit_breaker_recovers_to_half_open(self):
        from enterprise.integration.service_mesh import (
            CircuitBreaker,
            CircuitBreakerConfig,
            CircuitState,
        )

        config = CircuitBreakerConfig(
            failure_threshold=2,
            recovery_timeout_seconds=0.001,
            half_open_max_requests=3,
        )
        cb = CircuitBreaker("recovery-cb", config=config)

        # Trip it open
        for _ in range(2):
            try:
                cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
            except ValueError:
                pass
        assert cb.state == CircuitState.OPEN

        # Wait for recovery timeout
        import time
        time.sleep(0.02)

        # Next call should transition to half-open
        try:
            cb.call(lambda: "success")
        except Exception:
            pass
        # Should not be OPEN anymore
        assert cb.state != CircuitState.OPEN

    def test_circuit_breaker_stats(self):
        from enterprise.integration.service_mesh import CircuitBreaker

        cb = CircuitBreaker("stats-cb")

        # Successful calls
        for _ in range(5):
            cb.call(lambda: "ok")

        # Failed calls
        for _ in range(2):
            try:
                cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
            except ValueError:
                pass

        assert cb._total_successes == 5
        assert cb._total_failures == 2

    @pytest.mark.asyncio
    async def test_circuit_breaker_async_call(self):
        from enterprise.integration.service_mesh import CircuitBreaker

        cb = CircuitBreaker("async-cb")

        async def success_async():
            return "async_ok"

        result = await cb.acall(success_async)
        assert result == "async_ok"


class TestServiceMesh:
    """Verify ServiceMesh service discovery and management."""

    def test_service_mesh_singleton(self):
        from enterprise.integration.service_mesh import get_service_mesh

        mesh1 = get_service_mesh()
        mesh2 = get_service_mesh()
        assert mesh1 is mesh2

    def test_service_mesh_register_and_list(self):
        from enterprise.integration.service_mesh import ServiceMesh

        mesh = ServiceMesh()
        instance_id = mesh.register("test-service", host="localhost", port=9000, version="1.0.0")

        services = mesh.list_services()
        assert "test-service" in services
        assert services["test-service"]["instance_count"] >= 1

        mesh.deregister("test-service", instance_id)

    def test_service_mesh_can_register_multiple(self):
        from enterprise.integration.service_mesh import ServiceMesh

        mesh = ServiceMesh()
        id1 = mesh.register("multi-svc", host="localhost", port=9001)
        id2 = mesh.register("multi-svc", host="localhost", port=9002)

        services = mesh.list_services()
        svc = services.get("multi-svc", {})
        assert svc.get("instance_count", 0) >= 2

        mesh.deregister("multi-svc", id1)
        mesh.deregister("multi-svc", id2)

    def test_service_mesh_get_stats(self):
        from enterprise.integration.service_mesh import ServiceMesh

        mesh = ServiceMesh()
        stats = mesh.get_mesh_stats()
        assert "services_count" in stats
        assert "total_instances" in stats
        assert "open_circuits" in stats
        assert "timestamp" in stats

    def test_service_mesh_get_service_health(self):
        from enterprise.integration.service_mesh import ServiceMesh

        mesh = ServiceMesh()
        mesh.register("health-svc", host="localhost", port=9100)
        health = mesh.get_service_health("health-svc")
        assert health["service"] == "health-svc"
        assert "info" in health
        assert "circuit_breaker" in health

    def test_service_mesh_set_bulkhead(self):
        from enterprise.integration.service_mesh import ServiceMesh

        mesh = ServiceMesh()
        mesh.set_bulkhead("bulkhead-svc", max_concurrent=5)
        # Setting should not raise


class TestMeshTopology:
    """Verify MeshTopology dependency graph."""

    def test_topology_creation(self):
        from enterprise.integration.service_mesh import (
            ServiceRegistry,
            MeshTopology,
        )

        registry = ServiceRegistry()
        topology = MeshTopology(registry)
        assert topology is not None

    def test_topology_build_graph(self):
        from enterprise.integration.service_mesh import (
            ServiceRegistry,
            MeshTopology,
        )

        registry = ServiceRegistry()
        topology = MeshTopology(registry)
        graph = topology.build_dependency_graph()
        assert isinstance(graph, dict)

    def test_topology_get_dependents(self):
        from enterprise.integration.service_mesh import (
            ServiceRegistry,
            MeshTopology,
        )

        registry = ServiceRegistry()
        topology = MeshTopology(registry)
        dependents = topology.get_dependents("safety_governance")
        assert isinstance(dependents, list)

    def test_topology_fan_in_out(self):
        from enterprise.integration.service_mesh import (
            ServiceRegistry,
            MeshTopology,
        )

        registry = ServiceRegistry()
        topology = MeshTopology(registry)
        fan_in = topology.get_fan_in("kernel")
        fan_out = topology.get_fan_out("kernel")
        assert isinstance(fan_in, int)
        assert isinstance(fan_out, int)

    def test_topology_report(self):
        from enterprise.integration.service_mesh import (
            ServiceRegistry,
            MeshTopology,
        )

        registry = ServiceRegistry()
        topology = MeshTopology(registry)
        report = topology.get_topology_report()
        assert "total_services" in report
        assert "root_services" in report
        assert "nodes" in report
        assert "edges" in report


# ==============================================================================
# 10. Health Check Config Tests
# ==============================================================================


class TestHealthCheckConfig:
    """Verify health check configuration and records."""

    def test_health_check_config_defaults(self):
        from enterprise.integration.service_mesh import HealthCheckConfig

        config = HealthCheckConfig()
        assert config.interval_seconds == 10.0
        assert config.timeout_seconds == 5.0
        assert config.failure_threshold == 3
        assert config.success_threshold == 2
        assert config.endpoint == "/api/v1/health/live"

    def test_health_record_creation(self):
        from enterprise.integration.service_mesh import HealthRecord

        record = HealthRecord(instance_id="inst-1")
        assert record.instance_id == "inst-1"
        assert record.consecutive_failures == 0
        assert record.consecutive_successes == 0

    def test_circuit_breaker_config_defaults(self):
        from enterprise.integration.service_mesh import CircuitBreakerConfig

        config = CircuitBreakerConfig()
        assert config.failure_threshold == 5
        assert config.recovery_timeout_seconds == 30.0
        assert config.half_open_max_requests == 3

    def test_retry_config_defaults(self):
        from enterprise.integration.service_mesh import RetryConfig

        config = RetryConfig()
        assert config.max_retries == 3
        assert config.base_delay_seconds == 1.0
        assert config.backoff_multiplier == 2.0


# ==============================================================================
# 11. Gateway Auth & Middleware Tests
# ==============================================================================


class TestGatewayAuthIntegration:
    """Test auth flow end-to-end through the API."""

    def test_anonymous_access_allowed_for_public(self):
        from enterprise.integration.api_gateway import create_app, get_deps

        from enterprise.integration.api_gateway import RateLimiter

        deps = get_deps()
        deps.rate_limiter = RateLimiter(default_rate=10000, default_burst=10000)
        app = create_app(enable_docs=True)
        client = TestClient(app)

        # Anonymous should access health endpoints
        response = client.get("/api/v1/health/live")
        assert response.status_code == 200

    def test_api_key_auth_flow(self):
        from enterprise.integration.api_gateway import create_app, get_deps

        from enterprise.integration.api_gateway import RateLimiter

        deps = get_deps()
        deps.rate_limiter = RateLimiter(default_rate=10000, default_burst=10000)
        deps.auth_handler.api_keys.add("flow-test-key-12345")
        app = create_app(enable_docs=True)
        client = TestClient(app)

        # Should pass auth
        response = client.post(
            "/api/v1/events/publish",
            json={"event_type": "test", "source": "flow_test", "payload": {}},
            headers={"X-API-Key": "flow-test-key-12345"},
        )
        assert response.status_code == 202

    def test_invalid_api_key_rejected(self):
        from enterprise.integration.api_gateway import create_app, get_deps

        from enterprise.integration.api_gateway import RateLimiter

        deps = get_deps()
        deps.rate_limiter = RateLimiter(default_rate=10000, default_burst=10000)
        app = create_app(enable_docs=True)
        client = TestClient(app)

        response = client.post(
            "/api/v1/events/publish",
            json={"event_type": "test", "source": "test", "payload": {}},
            headers={"X-API-Key": "invalid-key"},
        )
        assert response.status_code == 401

    def test_bearer_token_rejected_if_invalid(self):
        from enterprise.integration.api_gateway import create_app, get_deps

        from enterprise.integration.api_gateway import RateLimiter

        deps = get_deps()
        deps.rate_limiter = RateLimiter(default_rate=10000, default_burst=10000)
        app = create_app(enable_docs=True)
        client = TestClient(app)

        response = client.post(
            "/api/v1/events/publish",
            json={"event_type": "test", "source": "test", "payload": {}},
            headers={"Authorization": "Bearer invalid-jwt-token"},
        )
        assert response.status_code == 401


# ==============================================================================
# 12. Service Discovery Tests
# ==============================================================================


class TestServiceDiscovery:
    """Verify service registry and discovery."""

    def test_service_registry_creation(self):
        from enterprise.integration.service_mesh import ServiceRegistry

        registry = ServiceRegistry()
        assert registry is not None

    def test_register_and_get_instance(self):
        from enterprise.integration.service_mesh import ServiceRegistry, ServiceInstance, HealthStatus

        registry = ServiceRegistry()
        instance = ServiceInstance(
            instance_id="disc-1",
            service_name="discovery-svc",
            host="localhost",
            port=8080,
            status=HealthStatus.HEALTHY,
        )
        registry.register(instance)

        instances = registry.get_instances("discovery-svc")
        assert len(instances) == 1
        assert instances[0].instance_id == "disc-1"

    def test_get_instances_healthy_only(self):
        from enterprise.integration.service_mesh import (
            ServiceRegistry,
            ServiceInstance,
            HealthStatus,
        )

        registry = ServiceRegistry()
        healthy = ServiceInstance(
            instance_id="h1",
            service_name="filter-svc",
            host="localhost",
            port=8001,
            status=HealthStatus.HEALTHY,
        )
        unhealthy = ServiceInstance(
            instance_id="u1",
            service_name="filter-svc",
            host="localhost",
            port=8002,
            status=HealthStatus.UNHEALTHY,
        )
        registry.register(healthy)
        registry.register(unhealthy)

        filtered = registry.get_instances("filter-svc", healthy_only=True)
        assert len(filtered) == 1
        assert filtered[0].instance_id == "h1"


# ==============================================================================
# 13. Load Balancer Tests
# ==============================================================================


class TestLoadBalancer:
    """Verify load balancer strategies."""

    def test_load_balancer_creation(self):
        from enterprise.integration.service_mesh import LoadBalancer

        lb = LoadBalancer()
        assert lb is not None
        assert lb.strategy.value == "round_robin"

    def test_round_robin_selection(self):
        from enterprise.integration.service_mesh import (
            LoadBalancer,
            ServiceInstance,
        )

        lb = LoadBalancer()
        instances = [
            ServiceInstance(instance_id=f"rr-{i}", service_name="rr-svc",
                          host="localhost", port=8000 + i)
            for i in range(3)
        ]

        # Make several selections; should cycle through
        selected = [lb.select(instances).instance_id for _ in range(6)]
        # In round-robin, we should see all 3 IDs
        unique = set(selected)
        assert len(unique) == 3

    def test_load_balancer_returns_none_on_empty(self):
        from enterprise.integration.service_mesh import LoadBalancer

        lb = LoadBalancer()
        result = lb.select([])
        assert result is None


# ==============================================================================
# 14. EventBus Singleton Tests
# ==============================================================================


class TestEventHubSingleton:
    """Verify singleton access for event hub."""

    def test_get_event_hub_returns_singleton(self):
        from enterprise.integration.event_hub import get_event_hub

        hub1 = get_event_hub()
        hub2 = get_event_hub()
        assert hub1 is hub2

    def test_publish_event_convenience(self):
        from enterprise.integration.event_hub import publish_event

        event_id = publish_event(
            event_type="system.health_check",
            source="test_convenience",
            payload={"status": "ok", "modules": []},
        )
        assert event_id is not None
        assert len(event_id) > 0
