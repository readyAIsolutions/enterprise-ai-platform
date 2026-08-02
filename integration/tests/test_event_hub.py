"""
Tests for ENI Enterprise Integration Layer — Event Hub
======================================================
Comprehensive tests for event schemas, bus, subscriptions,
contracts, dead-letter queue, tracing, and sync publisher.
"""

import asyncio
import pytest
import time
import uuid

from enterprise.integration.event_hub import (
    # Core
    EventBus,
    EventEnvelope,
    EventPriority,
    EventSchema,
    EventStatus,
    EventSubscription,
    EventTracer,
    # Contracts
    ContractDirection,
    EventContract,
    # Queues
    DeadLetterQueue,
    # Sync bridge
    SyncEventPublisher,
    # Convenience
    create_standard_contracts,
    get_event_hub,
    publish_event,
)


# ---------------------------------------------------------------------------
# EventSchema Tests
# ---------------------------------------------------------------------------


class TestEventSchema:
    """Tests for event schema definition and validation."""

    def test_schema_creation(self):
        schema = EventSchema(
            event_type="test.event",
            version="1.0",
            description="A test event",
            required_fields=["field_a", "field_b"],
            category="test",
        )
        assert schema.event_type == "test.event"
        assert schema.version == "1.0"
        assert len(schema.required_fields) == 2
        assert schema.ttl_seconds == 3600

    def test_schema_validation_passes(self):
        schema = EventSchema(
            event_type="test.event",
            required_fields=["key1", "key2"],
        )
        valid, errors = schema.validate({"key1": "val1", "key2": "val2"})
        assert valid is True
        assert len(errors) == 0

    def test_schema_validation_fails(self):
        schema = EventSchema(
            event_type="test.event",
            required_fields=["key1", "key2"],
        )
        valid, errors = schema.validate({"key1": "val1"})
        assert valid is False
        assert len(errors) == 1
        assert "key2" in errors[0]

    def test_schema_validation_empty_payload(self):
        schema = EventSchema(
            event_type="test.event",
            required_fields=[],
        )
        valid, errors = schema.validate({})
        assert valid is True
        assert len(errors) == 0

    def test_schema_defaults(self):
        schema = EventSchema(event_type="minimal.event")
        assert schema.version == "1.0"
        assert schema.description == ""
        assert schema.required_fields == []
        assert schema.optional_fields == []
        assert schema.category == ""


# ---------------------------------------------------------------------------
# EventEnvelope Tests
# ---------------------------------------------------------------------------


class TestEventEnvelope:
    """Tests for event envelope creation and expiration."""

    def test_envelope_creation(self):
        envelope = EventEnvelope(
            event_type="test.event",
            source="test_module",
            payload={"data": "hello"},
        )
        assert envelope.event_id != ""
        assert envelope.event_type == "test.event"
        assert envelope.source == "test_module"
        assert envelope.status == EventStatus.RECEIVED
        assert envelope.priority == EventPriority.MEDIUM

    def test_envelope_not_expired(self):
        envelope = EventEnvelope(
            event_type="test.event",
            source="test",
            ttl_seconds=999999,
        )
        assert envelope.is_expired is False

    def test_envelope_expired(self):
        envelope = EventEnvelope(
            event_type="test.event",
            source="test",
            timestamp="2000-01-01T00:00:00Z",
            ttl_seconds=1,
        )
        assert envelope.is_expired is True

    def test_envelope_to_from_dict(self):
        original = EventEnvelope(
            event_type="test.event",
            source="test",
            payload={"x": 1},
            priority=EventPriority.HIGH,
            correlation_id="corr-123",
        )
        d = original.to_dict()
        restored = EventEnvelope.from_dict(d)
        assert restored.event_type == original.event_type
        assert restored.source == original.source
        assert restored.payload == original.payload
        assert restored.priority == original.priority
        assert restored.correlation_id == original.correlation_id

    def test_envelope_unique_ids(self):
        e1 = EventEnvelope(event_type="a", source="x")
        e2 = EventEnvelope(event_type="a", source="x")
        assert e1.event_id != e2.event_id


# ---------------------------------------------------------------------------
# EventSubscription Tests
# ---------------------------------------------------------------------------


class TestEventSubscription:
    """Tests for subscription pattern matching."""

    def test_exact_match(self):
        sub = EventSubscription(
            module_name="test",
            event_patterns=["test.exact.event"],
        )
        assert sub.matches("test.exact.event") is True
        assert sub.matches("test.other.event") is False

    def test_wildcard_match(self):
        sub = EventSubscription(
            module_name="test",
            event_patterns=["test.*"],
        )
        assert sub.matches("test.foo") is True
        assert sub.matches("test.bar.baz") is False

    def test_double_wildcard_match(self):
        sub = EventSubscription(
            module_name="test",
            event_patterns=["test.**"],
        )
        assert sub.matches("test.foo") is True
        assert sub.matches("test.foo.bar") is True
        assert sub.matches("other.event") is False

    def test_multi_pattern(self):
        sub = EventSubscription(
            module_name="test",
            event_patterns=["safety.*", "data.classified"],
        )
        assert sub.matches("safety.guardrail") is True
        assert sub.matches("data.classified") is True
        assert sub.matches("data.access") is False

    def test_inactive_subscription(self):
        sub = EventSubscription(
            module_name="test",
            event_patterns=["test.*"],
            active=False,
        )
        assert sub.matches("test.event") is True


# ---------------------------------------------------------------------------
# DeadLetterQueue Tests
# ---------------------------------------------------------------------------


class TestDeadLetterQueue:
    """Tests for dead-letter queue operations."""

    def test_enqueue(self):
        dlq = DeadLetterQueue(max_size=10)
        event = EventEnvelope(event_type="test", source="src")
        dlq.enqueue(event, reason="test failure")
        assert dlq.size == 1
        assert event.status == EventStatus.DEAD_LETTERED
        assert event.metadata.get("dead_letter_reason") == "test failure"

    def test_get_all(self):
        dlq = DeadLetterQueue(max_size=10)
        for i in range(3):
            dlq.enqueue(EventEnvelope(event_type=f"test.{i}", source="s"), f"fail {i}")
        events = dlq.get_all()
        assert len(events) == 3

    def test_max_size_eviction(self):
        dlq = DeadLetterQueue(max_size=5)
        for i in range(10):
            dlq.enqueue(EventEnvelope(event_type=f"test.{i}", source="s"), f"fail {i}")
        assert dlq.size == 5

    def test_replay(self):
        dlq = DeadLetterQueue(max_size=10)
        event = EventEnvelope(event_type="test", source="s")
        event_id = event.event_id
        dlq.enqueue(event, "fail")
        replayed = dlq.replay(event_id)
        assert replayed is not None
        assert replayed.event_id == event_id
        assert replayed.status == EventStatus.REPLAYED
        assert dlq.size == 0

    def test_replay_not_found(self):
        dlq = DeadLetterQueue(max_size=10)
        result = dlq.replay("nonexistent")
        assert result is None

    def test_clear(self):
        dlq = DeadLetterQueue(max_size=10)
        for i in range(5):
            dlq.enqueue(EventEnvelope(event_type="t", source="s"), "fail")
        dlq.clear()
        assert dlq.size == 0

    def test_get_by_id(self):
        dlq = DeadLetterQueue(max_size=10)
        event = EventEnvelope(event_type="test", source="s")
        dlq.enqueue(event, "fail")
        found = dlq.get_by_id(event.event_id)
        assert found is not None
        assert found.event_id == event.event_id
        not_found = dlq.get_by_id("nonexistent")
        assert not_found is None


# ---------------------------------------------------------------------------
# EventTracer Tests
# ---------------------------------------------------------------------------


class TestEventTracer:
    """Tests for distributed event tracing."""

    def test_record_and_retrieve(self):
        tracer = EventTracer()
        event = EventEnvelope(
            event_type="test.event",
            source="test",
            correlation_id="trace-123",
        )
        tracer.record(event)
        trace = tracer.get_trace("trace-123")
        assert len(trace) == 1
        assert trace[0]["event_id"] == event.event_id
        assert trace[0]["event_type"] == "test.event"

    def test_multiple_events_same_correlation(self):
        tracer = EventTracer()
        corr_id = "trace-456"
        for i in range(5):
            event = EventEnvelope(
                event_type=f"test.{i}",
                source="test",
                correlation_id=corr_id,
            )
            tracer.record(event)
        trace = tracer.get_trace(corr_id)
        assert len(trace) == 5

    def test_no_correlation_id_uses_event_id(self):
        tracer = EventTracer()
        event = EventEnvelope(event_type="test", source="test")
        tracer.record(event)
        trace = tracer.get_trace(event.event_id)
        assert len(trace) == 1


# ---------------------------------------------------------------------------
# EventBus Tests
# ---------------------------------------------------------------------------


class TestEventBus:
    """Tests for the central event bus."""

    @pytest.fixture
    def bus(self):
        return EventBus()

    def test_register_schema(self, bus):
        schema = EventSchema(
            event_type="custom.event",
            required_fields=["foo"],
        )
        bus.register_schema(schema)
        retrieved = bus.get_schema("custom.event")
        assert retrieved is not None
        assert retrieved.event_type == "custom.event"

    def test_list_schemas(self, bus):
        schemas = bus.list_schemas()
        assert len(schemas) > 0
        assert "system.startup" in schemas
        assert "data.classified" in schemas
        assert "safety.guardrail.triggered" in schemas

    def test_subscribe_and_list(self, bus):
        sub = EventSubscription(
            module_name="test_module",
            event_patterns=["test.*"],
        )
        bus.subscribe(sub)
        subs = bus.list_subscriptions()
        assert len(subs) == 1
        assert subs[0]["module_name"] == "test_module"
        assert subs[0]["active"] is True

    def test_unsubscribe(self, bus):
        sub = EventSubscription(
            module_name="test_module",
            event_patterns=["test.*"],
        )
        bus.subscribe(sub)
        bus.unsubscribe(sub.subscription_id)
        assert len(bus.list_subscriptions()) == 0

    def test_get_subscriptions_matching(self, bus):
        sub = EventSubscription(
            module_name="matcher",
            event_patterns=["safety.**"],
        )
        bus.subscribe(sub)
        matching = bus.get_subscriptions("safety.guardrail.triggered")
        assert len(matching) == 1
        assert matching[0].module_name == "matcher"
        not_matching = bus.get_subscriptions("data.classified")
        assert len(not_matching) == 0

    def test_register_contract(self, bus):
        contract = EventContract(
            producer_module="mod_a",
            consumer_module="mod_b",
            event_types=["test.event"],
            direction=ContractDirection.PRODUCES,
            description="Test contract",
        )
        bus.register_contract(contract)
        contracts = bus.get_contracts("mod_a")
        assert len(contracts) == 1
        assert contracts[0].producer_module == "mod_a"
        contracts_b = bus.get_contracts("mod_b")
        assert len(contracts_b) == 1

    async def test_publish_with_subscriber(self, bus):
        received = []

        async def handler(event: EventEnvelope):
            received.append(event)

        sub = EventSubscription(
            module_name="receiver",
            event_patterns=["test.data"],
            handler=handler,
        )
        bus.subscribe(sub)

        await bus.publish({
            "event_type": "test.data",
            "source": "test",
            "payload": {"key": "value"},
        }, wait=True)

        assert len(received) == 1
        assert received[0].event_type == "test.data"
        assert received[0].payload == {"key": "value"}
        assert received[0].status == EventStatus.DELIVERED

    async def test_publish_no_subscribers(self, bus):
        event_id = await bus.publish({
            "event_type": "no.match.event",
            "source": "test",
            "payload": {},
        })
        assert event_id != ""

    async def test_publish_multiple_subscribers(self, bus):
        received_1 = []
        received_2 = []

        async def handler_1(event):
            received_1.append(event)

        async def handler_2(event):
            received_2.append(event)

        sub1 = EventSubscription(module_name="r1", event_patterns=["test.**"], handler=handler_1)
        sub2 = EventSubscription(module_name="r2", event_patterns=["test.multi"], handler=handler_2)
        bus.subscribe(sub1)
        bus.subscribe(sub2)

        await bus.publish({
            "event_type": "test.multi",
            "source": "test",
            "payload": {},
        }, wait=True)

        assert len(received_1) == 1
        assert len(received_2) == 1

    async def test_priority_filter(self, bus):
        received = []

        async def handler(event):
            received.append(event)

        sub = EventSubscription(
            module_name="filter",
            event_patterns=["test.*"],
            handler=handler,
            priority=EventPriority.HIGH,
        )
        bus.subscribe(sub)

        await bus.publish({
            "event_type": "test.event",
            "source": "test",
            "payload": {},
            "priority": "low",
        }, wait=True)

        assert len(received) == 0

    def test_get_event_stats(self, bus):
        stats = bus.get_stats()
        assert "total_events" in stats
        assert "schemas_registered" in stats
        assert "subscriptions_active" in stats
        assert "contracts_registered" in stats
        assert "dead_letter_count" in stats

    def test_dead_letter_flow(self, bus):
        events = bus.get_dead_letters()
        assert isinstance(events, list)


# ---------------------------------------------------------------------------
# EventContract Tests
# ---------------------------------------------------------------------------


class TestEventContract:
    """Tests for module-to-module event contracts."""

    def test_contract_creation(self):
        contract = EventContract(
            producer_module="safety",
            consumer_module="kernel",
            event_types=["safety.incident.created"],
            direction=ContractDirection.PRODUCES,
            description="Safety to kernel",
            sla_ms=500,
        )
        assert contract.producer_module == "safety"
        assert contract.consumer_module == "kernel"
        assert contract.sla_ms == 500
        assert contract.active is True

    def test_create_standard_contracts(self):
        contracts = create_standard_contracts()
        assert len(contracts) > 0
        contract_pairs = [(c.producer_module, c.consumer_module) for c in contracts]
        assert ("safety_governance", "kernel") in contract_pairs
        assert ("privacy_data", "kernel") in contract_pairs
        assert ("release_change", "kernel") in contract_pairs


# ---------------------------------------------------------------------------
# SyncEventPublisher Tests
# ---------------------------------------------------------------------------


class TestSyncEventPublisher:
    """Tests for the synchronous event publisher bridge."""

    def test_publish_convenience_function(self):
        event_id = publish_event(
            "test.event",
            "test_source",
            {"data": "hello"},
            priority="medium",
        )
        assert event_id != ""
        assert isinstance(event_id, str)

    def test_sync_publisher_lifecycle(self):
        bus = EventBus()
        publisher = SyncEventPublisher(bus)
        publisher.start()
        assert publisher._loop is not None
        publisher.stop()


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


class TestIntegration:
    """End-to-end integration tests for the event hub."""

    async def test_full_event_lifecycle(self):
        bus = EventBus()
        delivered = []

        async def handler(event: EventEnvelope):
            delivered.append(event)

        sub = EventSubscription(
            module_name="lifecycle_test",
            event_patterns=["integration.test"],
            handler=handler,
        )
        bus.subscribe(sub)

        await bus.publish({
            "event_type": "integration.test",
            "source": "test",
            "payload": {"step": 1},
            "correlation_id": "test-correlation-1",
        }, wait=True)

        assert len(delivered) == 1
        assert delivered[0].status == EventStatus.DELIVERED

        trace = bus.get_trace("test-correlation-1")
        assert len(trace) >= 1

    async def test_delivery_order(self):
        bus = EventBus()
        order = []

        async def handler(event):
            order.append(event.payload.get("seq"))

        sub = EventSubscription(
            module_name="order_test",
            event_patterns=["order.*"],
            handler=handler,
        )
        bus.subscribe(sub)

        for i in range(3):
            await bus.publish({
                "event_type": "order.event",
                "source": "test",
                "payload": {"seq": i},
            }, wait=True)

        assert len(order) == 3
        assert 0 in order
        assert 2 in order

    async def test_handler_error_dead_letters(self):
        bus = EventBus()

        async def failing_handler(event):
            raise RuntimeError("Intentional failure")

        sub = EventSubscription(
            module_name="failing",
            event_patterns=["fail.*"],
            handler=failing_handler,
            dead_letter_on_failure=True,
        )
        bus.subscribe(sub)

        await bus.publish({
            "event_type": "fail.event",
            "source": "test",
            "payload": {},
        }, wait=True)

        dead_letters = bus.get_dead_letters()
        assert len(dead_letters) >= 1
        assert dead_letters[0]["event_type"] == "fail.event"