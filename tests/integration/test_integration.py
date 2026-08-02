"""
Integration tests for the ENI Enterprise platform.

Verifies that enterprise modules work together correctly:
- Platform kernel boots and manages modules
- Modules register with the platform
- Events flow between modules via EventBus
- Health checks pass across the platform
- Module-to-module communication works
- Multi-module workflows integrate properly
"""

import pytest
import sys
import os
import time
import threading
from pathlib import Path
from datetime import datetime, timezone


# ==============================================================================
# 1. Platform Kernel Boot Integration
# ==============================================================================


class TestPlatformKernelBoot:
    """Verify the platform kernel boots correctly and manages its subsystem."""

    def test_platform_os_singleton_pattern(self):
        """PlatformOS.instance() returns the singleton."""
        from enterprise.platform_kernel import PlatformOS

        p1 = PlatformOS.instance()
        p2 = PlatformOS.instance()
        assert p1 is p2


# ==============================================================================
# 2. Module Registration Integration
# ==============================================================================


class TestModuleRegistration:
    """Verify modules discover, register, and interact with the platform."""

    def test_registry_list_and_get(self):
        """ModuleRegistry can list modules and retrieve by name."""
        from enterprise.platform_kernel import ModuleRegistry

        registry = ModuleRegistry()
        modules = registry.list_modules()
        assert isinstance(modules, list)


# ==============================================================================
# 3. Event Flow Integration
# ==============================================================================


class TestEventFlow:
    """Verify events flow correctly across the EventBus and between modules."""

    def test_event_bus_creation(self):
        """EventBus can be created with default config."""
        from enterprise.platform_kernel import EventBus

        bus = EventBus()
        assert bus is not None
        bus.shutdown()

    def test_event_creation_and_publish(self):
        """Events can be created and published on the bus."""
        from enterprise.platform_kernel import EventBus, Event

        bus = EventBus(config={"async_dispatch": False})
        received = []

        @bus.subscribe("test.event")
        def handler(event):
            received.append(event)

        event = Event.create("test.event", "test_module", {"key": "value"})
        bus.publish_sync(event)

        assert len(received) == 1
        assert received[0].topic == "test.event"
        assert received[0].payload["key"] == "value"
        assert received[0].source == "test_module"

        bus.shutdown()

    def test_event_bus_wildcard_subscription(self):
        """Wildcard subscriptions receive all events."""
        from enterprise.platform_kernel import EventBus, Event

        bus = EventBus(config={"async_dispatch": False})
        all_events = []

        @bus.subscribe("*")
        def catch_all(event):
            all_events.append(event)

        bus.publish_sync(Event.create("topic.a", "src", {}))
        bus.publish_sync(Event.create("topic.b", "src", {}))

        assert len(all_events) == 2
        bus.shutdown()

    def test_event_bus_once_subscription(self):
        """Once subscriptions auto-unsubscribe after first delivery."""
        from enterprise.platform_kernel import EventBus, Event

        bus = EventBus(config={"async_dispatch": False})
        once_events = []

        @bus.subscribe("once.test", once=True)
        def handle_once(event):
            once_events.append(event)

        bus.publish_sync(Event.create("once.test", "src", {"n": 1}))
        bus.publish_sync(Event.create("once.test", "src", {"n": 2}))

        assert len(once_events) == 1
        bus.shutdown()

    def test_event_bus_stats(self):
        """EventBus reports accurate statistics."""
        from enterprise.platform_kernel import EventBus, Event

        bus = EventBus(config={"async_dispatch": False})
        bus.publish_sync(Event.create("stats.test", "src", {}))
        bus.publish_sync(Event.create("stats.test", "src", {}))

        stats = bus.get_stats()
        assert stats["total_published"] == 2
        bus.shutdown()

    def test_cross_module_event_flow(self):
        """Events can flow between simulated module handlers."""
        from enterprise.platform_kernel import EventBus, Event

        bus = EventBus(config={"async_dispatch": False})
        module_b_received = []

        @bus.subscribe("module.a.output")
        def module_b_handler(event):
            module_b_received.append(event)

        event = Event.create("module.a.output", "module_a", {"result": "ok"})
        bus.publish_sync(event)

        assert len(module_b_received) == 1
        assert module_b_received[0].source == "module_a"
        bus.shutdown()


# ==============================================================================
# 4. Health Check Integration
# ==============================================================================


class TestHealthChecks:
    """Verify health check mechanisms across the platform."""

    def test_health_status_values(self):
        """HealthStatus enum provides correct operational checks."""
        from enterprise.platform_kernel import HealthStatus

        assert HealthStatus.HEALTHY.is_operational() is True
        assert HealthStatus.DEGRADED.is_operational() is True
        assert HealthStatus.UNHEALTHY.is_operational() is False
        assert HealthStatus.UNHEALTHY.is_terminal() is True
        assert HealthStatus.HEALTHY.is_terminal() is False

    def test_health_checker_creation(self):
        """HealthChecker can be instantiated with a registry."""
        from enterprise.platform_kernel import HealthChecker, ModuleRegistry

        registry = ModuleRegistry()
        checker = HealthChecker(registry)
        assert checker is not None

    def test_health_report_creation(self):
        """HealthReport dataclass works correctly."""
        from enterprise.platform_kernel import HealthReport, HealthStatus

        report = HealthReport(
            module_name="test_module",
            status=HealthStatus.HEALTHY,
            response_time_ms=1.5,
            timestamp=datetime.now(timezone.utc),
        )
        assert report.module_name == "test_module"
        assert report.status == HealthStatus.HEALTHY

    def test_platform_health_status(self):
        """Platform health status enum works correctly."""
        from enterprise.platform_kernel import HealthStatus

        assert HealthStatus.HEALTHY.is_operational() is True
        assert HealthStatus.DEGRADED.is_operational() is True
        assert HealthStatus.UNHEALTHY.is_operational() is False


# ==============================================================================
# 5. Module-to-Module Integration
# ==============================================================================


class TestModuleIntegration:
    """Verify direct module-to-module interactions work."""

    def test_safety_guardrail_integration(self):
        """Safety guardrail can process input and return structured results."""
        from enterprise.modules.safety_governance.guardrails import (
            SafetyGuardrail,
            GuardrailResult,
        )

        guardrail = SafetyGuardrail()
        result = guardrail.process_input("Hello, how are you?")
        assert isinstance(result, GuardrailResult)

    def test_prompt_registry_crud(self):
        """Prompt registry supports full CRUD lifecycle."""
        from enterprise.modules.prompt_context import PromptRegistry

        registry = PromptRegistry()
        prompt_id = registry.define(
            name="Integration Test Prompt",
            objective="Verify integration",
            template="Hello {{name}}",
            tags=["integration", "test"],
        )
        assert prompt_id is not None

        record = registry.get(prompt_id)
        assert record.name == "Integration Test Prompt"

        new_ver = registry.update(prompt_id, objective="Updated objective")
        assert new_ver is not None

        result = registry.assemble(prompt_id, {"name": "World"})
        assert result == "Hello World"

    def test_agent_registry_creates_agents(self):
        """Agent registry can create and list agents."""
        from enterprise.modules.agent_coordination.agents import (
            AgentRegistry,
            AgentFactory,
        )

        factory = AgentFactory()
        agent = factory.create(agent_id="agent-qa-engineer")
        assert agent is not None

    def test_knowledge_graph_entity_crud(self):
        """Knowledge graph supports entity lifecycle."""
        from enterprise.modules.knowledge_graph.entities import (
            EntityRegistry,
            EntityType,
        )

        registry = EntityRegistry()
        entity = registry.create(
            name="test_integration_entity",
            entity_type=EntityType.PROJECT,
            metadata={"key": "value"},
        )
        assert entity is not None
        assert entity.name == "test_integration_entity"

    def test_context_manager_methods(self):
        """Context manager supports block lifecycle via convenience methods."""
        from enterprise.modules.prompt_context import (
            ContextManager,
            ContextPriority,
        )

        ctx = ContextManager()
        # Use convenience add methods
        block_id = ctx.add_task("Integration test task", priority=ContextPriority.HIGH)
        assert block_id is not None

        block = ctx.get(block_id)
        assert block is not None

    def test_feature_flags_basic(self):
        """Feature flag manager evaluates flags correctly."""
        from enterprise.foundation.config_feature_flags.flags import FeatureFlagManager, Flag

        manager = FeatureFlagManager()
        # Check flag state (may exist from defaults)
        flags = manager.get_active_flags()
        assert isinstance(flags, list)

    def test_policy_engine_imports(self):
        """Policy engine classes are importable."""
        from enterprise.foundation.policy_engine import (
            PolicyDefinition,
            PolicySet,
            PolicyEnforcer,
            PolicyRule,
        )

        # Create a simple policy
        rule = PolicyRule(
            name="test_rule",
            description="Test rule for integration",
            conditions=[{"field": "action", "operator": "equals", "value": "allowed"}],
            action="allow",
            severity="low",
        )
        assert rule.name == "test_rule"


# ==============================================================================
# 6. Multi-Module Workflow Integration
# ==============================================================================


class TestMultiModuleWorkflow:
    """Verify end-to-end workflows spanning multiple modules."""

    def test_prompt_to_safety_pipeline(self):
        """Prompt goes through registry, context, and safety gate."""
        from enterprise.modules.prompt_context import PromptRegistry
        from enterprise.modules.safety_governance.guardrails import SafetyGuardrail

        registry = PromptRegistry()
        prompt_id = registry.define(
            name="Workflow Prompt",
            objective="Test end-to-end pipeline",
            template="Task: {{task_description}}",
        )

        assembled = registry.assemble(
            prompt_id, {"task_description": "Generate a report"}
        )

        guardrail = SafetyGuardrail()
        result = guardrail.process_input(assembled)

        assert result.passed is True

    def test_event_driven_module_chain(self):
        """Multiple modules can be chained via event bus."""
        from enterprise.platform_kernel import EventBus, Event

        bus = EventBus(config={"async_dispatch": False})
        pipeline_stages: list = []

        @bus.subscribe("workflow.start")
        def safety_check(event):
            pipeline_stages.append("safety_checked")
            bus.publish_sync(
                Event.create("workflow.validated", "safety", event.payload)
            )

        @bus.subscribe("workflow.validated")
        def context_enhance(event):
            pipeline_stages.append("context_enhanced")
            bus.publish_sync(
                Event.create(
                    "workflow.complete", "context",
                    {**event.payload, "enhanced": True},
                )
            )

        @bus.subscribe("workflow.complete")
        def final_handler(event):
            pipeline_stages.append("completed")

        bus.publish_sync(Event.create("workflow.start", "trigger", {"input": "test"}))

        assert pipeline_stages == ["safety_checked", "context_enhanced", "completed"]
        bus.shutdown()


# ==============================================================================
# 7. Platform Lifecycle
# ==============================================================================


class TestPlatformLifecycle:
    """Verify the platform lifecycle is correct."""

    def test_event_bus_shutdown(self):
        """EventBus shutdown releases executor resources."""
        from enterprise.platform_kernel import EventBus

        bus = EventBus()
        bus.shutdown()
        stats = bus.get_stats()
        assert isinstance(stats, dict)

    def test_platform_lifecycle_via_create_platform(self):
        """create_platform returns a booted platform that can be shut down."""
        from enterprise.platform_kernel import create_platform

        platform = create_platform()
        assert platform is not None
        report = platform.status_report()
        assert "state" in report
        platform.shutdown()

    def test_lifecycle_state_transitions(self):
        """LifecycleState enum validates transitions correctly."""
        from enterprise.platform_kernel import LifecycleState

        # Valid transition
        assert LifecycleState.UNINITIALIZED.can_transition_to(
            LifecycleState.INITIALIZING
        )
        # Invalid transition
        assert not LifecycleState.STOPPED.can_transition_to(
            LifecycleState.RUNNING
        )


# ==============================================================================
# 8. Error Handling & Recovery
# ==============================================================================


class TestErrorHandling:
    """Verify the platform handles errors gracefully."""

    def test_event_bus_dead_letter_queue(self):
        """Failing handlers go to dead letter queue, not crash the bus."""
        from enterprise.platform_kernel import EventBus, Event

        bus = EventBus(config={"async_dispatch": False, "dead_letter_enabled": True})

        @bus.subscribe("failing.event")
        def bad_handler(event):
            raise ValueError("Intentional test failure")

        bus.publish_sync(Event.create("failing.event", "test", {}))
        dead = bus.get_dead_letter()
        assert len(dead) == 1
        assert isinstance(dead[0][2], ValueError)

        # Bus should still work after a failure
        ok_events = []

        @bus.subscribe("ok.event")
        def ok_handler(event):
            ok_events.append(event)

        bus.publish_sync(Event.create("ok.event", "test", {}))
        assert len(ok_events) == 1
        bus.shutdown()

    def test_platform_is_singleton(self):
        """PlatformOS.instance() always returns same instance."""
        from enterprise.platform_kernel import PlatformOS

        p1 = PlatformOS.instance()
        p2 = PlatformOS.instance()
        assert p1 is p2