"""
ENI Enterprise Platform Kernel — Central Orchestration Layer
=============================================================

The Platform Kernel is the beating heart of the ENI Enterprise AI OS.
It wires every enterprise module together through a unified orchestration
layer providing module discovery, event-driven communication, health
monitoring, lifecycle management, logging aggregation, and metrics collection.

Architecture:
  PlatformOS (singleton orchestrator)
  ├── ModuleRegistry   — auto-discovers modules in enterprise/modules/*/
  ├── EventBus         — pub/sub event system for cross-module communication
  ├── HealthChecker    — periodic health pings across all modules
  ├── MetricsCollector — cross-module metrics aggregation
  ├── LoggingBridge    — unified logging from all modules
  └── LifecycleManager — startup, running, shutdown, degraded state machine

Version: 1.0.0
Python: 3.10+
"""

from __future__ import annotations

import abc
import asyncio
import contextlib
import importlib
import importlib.util
import json
import logging
import os
import signal
import sys
import threading
import time
import traceback
import uuid
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    ParamSpec,
    TypeVar,
)

if TYPE_CHECKING:
    from types import ModuleType

# =============================================================================
# Type variables
# =============================================================================

P = ParamSpec("P")
T = TypeVar("T")
R = TypeVar("R")
ModuleT = TypeVar("ModuleT", bound="Module")

# =============================================================================
# Enums
# =============================================================================


class HealthStatus(Enum):
    """Health status of a module or the entire platform."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    STARTING = "starting"
    STOPPING = "stopping"
    UNKNOWN = "unknown"

    def is_operational(self) -> bool:
        """Return True if the system is operational (healthy or degraded)."""
        return self in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)

    def is_terminal(self) -> bool:
        """Return True if the system has reached a terminal state."""
        return self in (HealthStatus.UNHEALTHY, HealthStatus.UNKNOWN)


class LifecycleState(Enum):
    """Platform lifecycle state machine."""

    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    DISCOVERING = "discovering"
    CONFIGURING = "configuring"
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    PAUSING = "pausing"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    CRASHED = "crashed"
    RECOVERING = "recovering"

    def can_transition_to(self, target: LifecycleState) -> bool:
        """Validate state machine transitions."""
        _TRANSITIONS: dict[LifecycleState, set[LifecycleState]] = {
            LifecycleState.UNINITIALIZED: {
                LifecycleState.INITIALIZING,
                LifecycleState.STOPPED,
            },
            LifecycleState.INITIALIZING: {
                LifecycleState.DISCOVERING,
                LifecycleState.CRASHED,
                LifecycleState.STOPPING,
            },
            LifecycleState.DISCOVERING: {
                LifecycleState.CONFIGURING,
                LifecycleState.CRASHED,
                LifecycleState.STOPPING,
            },
            LifecycleState.CONFIGURING: {
                LifecycleState.STARTING,
                LifecycleState.CRASHED,
                LifecycleState.STOPPING,
            },
            LifecycleState.STARTING: {
                LifecycleState.RUNNING,
                LifecycleState.DEGRADED,
                LifecycleState.CRASHED,
                LifecycleState.STOPPING,
            },
            LifecycleState.RUNNING: {
                LifecycleState.DEGRADED,
                LifecycleState.PAUSING,
                LifecycleState.STOPPING,
            },
            LifecycleState.DEGRADED: {
                LifecycleState.RUNNING,
                LifecycleState.CRASHED,
                LifecycleState.STOPPING,
                LifecycleState.RECOVERING,
            },
            LifecycleState.PAUSING: {
                LifecycleState.PAUSED,
                LifecycleState.CRASHED,
                LifecycleState.STOPPING,
            },
            LifecycleState.PAUSED: {
                LifecycleState.RUNNING,
                LifecycleState.RECOVERING,
                LifecycleState.STOPPING,
            },
            LifecycleState.STOPPING: {
                LifecycleState.STOPPED,
                LifecycleState.CRASHED,
            },
            LifecycleState.STOPPED: set(),
            LifecycleState.CRASHED: {
                LifecycleState.RECOVERING,
                LifecycleState.STOPPING,
            },
            LifecycleState.RECOVERING: {
                LifecycleState.RUNNING,
                LifecycleState.DEGRADED,
                LifecycleState.CRASHED,
                LifecycleState.STOPPING,
            },
        }
        return target in _TRANSITIONS.get(self, set())


# Numeric index for metrics gauges (lower = earlier in lifecycle).
_STATE_INDEX: dict[LifecycleState, int] = {state: idx for idx, state in enumerate(LifecycleState)}


# =============================================================================
# Event System
# =============================================================================


class EventPriority(Enum):
    """Event priority for the EventBus."""

    LOW = 0
    NORMAL = 50
    HIGH = 100
    CRITICAL = 200


@dataclass
class Event:
    """An event emitted on the EventBus for cross-module pub/sub communication.

    Attributes:
        event_id: Unique event identifier (UUID4).
        topic: Event topic/name.
        source: Module or component that emitted the event.
        payload: Arbitrary data attached to the event.
        timestamp: UTC timestamp of event creation.
        priority: Event priority (default NORMAL).
        correlation_id: Optional correlation ID for tracing event chains.
        metadata: Optional key-value metadata.
    """

    event_id: str
    topic: str
    source: str
    payload: dict[str, Any]
    timestamp: datetime
    priority: EventPriority = EventPriority.NORMAL
    correlation_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        topic: str,
        source: str,
        payload: dict[str, Any],
        priority: EventPriority = EventPriority.NORMAL,
        correlation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Event:
        """Factory method to create a new Event with a UUID4 and UTC timestamp."""
        return cls(
            event_id=str(uuid.uuid4()),
            topic=topic,
            source=source,
            payload=payload,
            timestamp=datetime.now(UTC),
            priority=priority,
            correlation_id=correlation_id,
            metadata=metadata or {},
        )


# Callback type: async or sync
EventHandler = Callable[[Event], Any | None]


@dataclass
class Subscription:
    """A subscription to an event topic in the EventBus.

    Attributes:
        id: Unique subscription identifier.
        topic: Event topic to subscribe to.
        handler: Callback function invoked when event arrives.
        subscriber_name: Human-readable name for debugging.
        priority_filter: If set, only events with this priority or higher are delivered.
        once: If True, the subscription is auto-removed after the first invocation.
    """

    id: str
    topic: str
    handler: EventHandler
    subscriber_name: str
    priority_filter: EventPriority | None = None
    once: bool = False


class EventBus:
    """Thread-safe publish/subscribe event bus for cross-module communication.

    Supports asynchronous dispatch via a thread pool, prioritized delivery,
    dead-letter queue for failed handlers, event history, and topic-based
    filtering.

    Usage::

        bus = EventBus()


        @bus.subscribe("user.created")
        def handle_user_created(event: Event) -> None:
            print(f"User created: {event.payload['user_id']}")


        bus.publish(Event.create("user.created", "auth", {"user_id": "u1"}))
    """

    _SEEN_HISTORY_MAX: ClassVar[int] = 10000

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize the EventBus.

        Args:
            config: Configuration dict, supports 'max_queue_size', 'async_dispatch',
                    'max_workers', 'dead_letter_enabled'.
        """
        cfg = config or {}
        self._lock: threading.RLock = threading.RLock()
        self._subscriptions: dict[str, list[Subscription]] = defaultdict(list)
        self._subscriptions_by_id: dict[str, Subscription] = {}
        self._async_dispatch: bool = cfg.get("async_dispatch", True)
        self._max_workers: int = cfg.get("max_workers", 8)
        self._executor: ThreadPoolExecutor | None = None
        if self._async_dispatch:
            self._executor = ThreadPoolExecutor(
                max_workers=self._max_workers,
                thread_name_prefix="eventbus-",
            )
        self._event_history: list[Event] = []
        self._dead_letter_enabled: bool = cfg.get("dead_letter_enabled", True)
        self._dead_letter: list[tuple[Event, Subscription, Exception]] = []
        self._total_published: int = 0
        self._total_delivered: int = 0
        self._total_failed: int = 0
        self._started_at: datetime = datetime.now(UTC)

    # ── Subscribe ────────────────────────────────────────────────────────────

    def subscribe(
        self,
        topic: str,
        priority_filter: EventPriority | None = None,
        once: bool = False,
        subscriber_name: str | None = None,
    ) -> Callable[[EventHandler], EventHandler]:
        """Decorator to subscribe a handler to a topic.

        Usage::

            @bus.subscribe("*.alerts")
            def handle_alert(event: Event) -> None: ...

        Args:
            topic: Topic string. Supports wildcard '*' for all topics.
            priority_filter: Only deliver events with this priority or higher.
            once: If True, unsubscribe after first delivery.
            subscriber_name: Human-readable name (inferred from function if omitted).

        Returns:
            A decorator that registers the handler.
        """

        def decorator(handler: EventHandler) -> EventHandler:
            name = subscriber_name or handler.__name__
            sub = Subscription(
                id=str(uuid.uuid4()),
                topic=topic,
                handler=handler,
                subscriber_name=name,
                priority_filter=priority_filter,
                once=once,
            )
            with self._lock:
                self._subscriptions[topic].append(sub)
                self._subscriptions_by_id[sub.id] = sub
            return handler

        return decorator

    def unsubscribe(self, subscription_id: str) -> bool:
        """Remove a subscription by its ID.

        Returns:
            True if the subscription was found and removed.
        """
        with self._lock:
            sub = self._subscriptions_by_id.pop(subscription_id, None)
            if sub is None:
                return False
            topic_subs = self._subscriptions.get(sub.topic, [])
            self._subscriptions[sub.topic] = [s for s in topic_subs if s.id != subscription_id]
            return True

    def _get_matching_subscriptions(self, topic: str) -> list[Subscription]:
        """Return all subscriptions matching a topic, including wildcard matches.

        Supports:
          - Exact topic match (e.g., "foo.bar" matches "foo.bar")
          - Glob wildcard "*" matches ALL topics
          - Prefix wildcard "prefix.*" matches any topic starting with "prefix."
          - Suffix wildcard "*.suffix" matches any topic ending with ".suffix"
        """
        with self._lock:
            result: list[Subscription] = []
            # Exact match
            result.extend(self._subscriptions.get(topic, []))
            # Wildcard: match all
            result.extend(self._subscriptions.get("*", []))
            # Prefix glob: "platform.*" matches "platform.started", "platform.state_change", etc.
            for sub_topic, subs in self._subscriptions.items():
                if (
                    sub_topic.endswith(".*")
                    and topic.startswith(sub_topic[:-2])
                    or sub_topic.startswith("*.")
                    and topic.endswith(sub_topic[2:])
                ):
                    result.extend(subs)
            return list(result)

    # ── Publish ──────────────────────────────────────────────────────────────

    def publish(self, event: Event) -> None:
        """Publish an event to all matching subscribers.

        If async_dispatch is enabled, handlers run in the thread pool.
        Otherwise, they run synchronously.

        Args:
            event: The Event to publish.
        """
        self._record_event(event)
        subs = self._get_matching_subscriptions(event.topic)
        if subs:
            for sub in subs:
                # Priority filter
                if (
                    sub.priority_filter is not None
                    and event.priority.value < sub.priority_filter.value
                ):
                    continue

                if self._async_dispatch and self._executor is not None:
                    self._executor.submit(self._dispatch_one, event, sub)
                else:
                    self._dispatch_one(event, sub)

        with self._lock:
            self._total_published += 1

    def publish_sync(self, event: Event) -> None:
        """Publish an event synchronously (blocking), regardless of async config."""
        self._record_event(event)
        subs = self._get_matching_subscriptions(event.topic)
        for sub in subs:
            if sub.priority_filter is not None and event.priority.value < sub.priority_filter.value:
                continue
            self._dispatch_one(event, sub)
        with self._lock:
            self._total_published += 1

    def _dispatch_one(self, event: Event, sub: Subscription) -> None:
        """Dispatch a single event to a single subscriber. Handles errors."""
        try:
            sub.handler(event)
            with self._lock:
                self._total_delivered += 1
        except Exception as exc:
            with self._lock:
                self._total_failed += 1
            if self._dead_letter_enabled:
                with self._lock:
                    self._dead_letter.append((event, sub, exc))
            logging.getLogger("eni.eventbus").error(
                "Event dispatch failed: topic=%s subscriber=%s error=%s",
                event.topic,
                sub.subscriber_name,
                exc,
                exc_info=True,
            )

        # Auto-unsubscribe once-only
        if sub.once:
            self.unsubscribe(sub.id)

    def _record_event(self, event: Event) -> None:
        """Add event to history, trimming if necessary."""
        with self._lock:
            self._event_history.append(event)
            if len(self._event_history) > self._SEEN_HISTORY_MAX:
                self._event_history = self._event_history[-self._SEEN_HISTORY_MAX :]

    # ── Query ────────────────────────────────────────────────────────────────

    def get_history(
        self,
        topic: str | None = None,
        limit: int = 100,
    ) -> list[Event]:
        """Return recent events, optionally filtered by topic."""
        with self._lock:
            events = self._event_history
            if topic:
                events = [e for e in events if e.topic == topic]
            return events[-limit:]

    def get_dead_letter(self) -> list[tuple[Event, Subscription, Exception]]:
        """Return events that failed to dispatch."""
        with self._lock:
            return list(self._dead_letter)

    def get_stats(self) -> dict[str, Any]:
        """Return statistics about the event bus."""
        with self._lock:
            return {
                "total_published": self._total_published,
                "total_delivered": self._total_delivered,
                "total_failed": self._total_failed,
                "active_subscriptions": len(self._subscriptions_by_id),
                "unique_topics": len(self._subscriptions),
                "dead_letter_count": len(self._dead_letter),
                "history_size": len(self._event_history),
                "uptime_seconds": (datetime.now(UTC) - self._started_at).total_seconds(),
            }

    def shutdown(self) -> None:
        """Gracefully shut down the thread pool."""
        if self._executor is not None:
            self._executor.shutdown(wait=True)
            self._executor = None


# =============================================================================
# Module abstraction
# =============================================================================


class Module(abc.ABC):
    """Abstract base class for all enterprise modules.

    Every module must implement this interface, providing a name, version,
    initialize(), health_check(), and shutdown().

    Subclasses registered via the @module decorator are auto-discovered
    by the ModuleRegistry.
    """

    # Set by the @module decorator
    _meta_name: str = ""
    _meta_version: str = "0.0.0"
    _meta_config: dict[str, Any] = field(default_factory=dict)

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config: dict[str, Any] = config or {}
        self._status: HealthStatus = HealthStatus.UNKNOWN
        self._started_at: datetime | None = None
        self._module_id: str = str(uuid.uuid4())

    @property
    def name(self) -> str:
        """Module name."""
        return self._meta_name or self.__class__.__name__

    @property
    def version(self) -> str:
        """Module version."""
        return self._meta_version

    @property
    def status(self) -> HealthStatus:
        """Current health status."""
        return self._status

    @status.setter
    def status(self, value: HealthStatus) -> None:
        self._status = value

    @property
    def module_id(self) -> str:
        """Unique module instance ID."""
        return self._module_id

    @property
    def config(self) -> dict[str, Any]:
        """Module-specific configuration."""
        return self._config

    @abc.abstractmethod
    async def initialize(self) -> None:
        """Initialize the module. Called during platform startup."""
        ...

    @abc.abstractmethod
    async def health_check(self) -> HealthStatus:
        """Perform a health check and return the module's health status."""
        ...

    @abc.abstractmethod
    async def shutdown(self) -> None:
        """Gracefully shut down the module. Called during platform shutdown."""
        ...

    def __repr__(self) -> str:
        return f"<Module {self.name} v{self.version} [{self.status.value}]>"


# Decorator
_MODULE_REGISTRY: dict[str, type[Module]] = {}


def module(
    name: str | None = None,
    version: str = "0.0.0",
    config_defaults: dict[str, Any] | None = None,
) -> Callable[[type[ModuleT]], type[ModuleT]]:
    """Decorator to register a module class with the platform.

    Usage::

        @module(name="safety_governance", version="1.0.0")
        class SafetyGovernanceModule(Module):
            async def initialize(self) -> None: ...

    Args:
        name: Module name (defaults to class name).
        version: Module version string.
        config_defaults: Default configuration for the module.

    Returns:
        A decorator that registers the class.
    """

    def decorator(cls: type[ModuleT]) -> type[ModuleT]:
        mod_name = name or cls.__name__
        cls._meta_name = mod_name
        cls._meta_version = version
        cls._meta_config = config_defaults or {}
        _MODULE_REGISTRY[mod_name] = cls
        return cls

    return decorator


# =============================================================================
# Module Registry
# =============================================================================


@dataclass
class ModuleRecord:
    """Metadata record for a discovered module."""

    name: str
    path: Path
    version: str
    module_class: type[Module] | None = None
    instance: Module | None = None
    enabled: bool = True
    required: bool = False
    priority: int = 100
    config: dict[str, Any] = field(default_factory=dict)
    discovered_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class ModuleRegistry:
    """Auto-discovers and manages enterprise modules.

    Scans enterprise/modules/*/__init__.py and loads them. Modules are
    ordered by priority for startup/shutdown sequencing. Supports both
    import-based discovery and decorator-based registration.

    Usage::

        registry = ModuleRegistry(modules_path, config)
        registry.discover()
        await registry.initialize_all()
    """

    DEFAULT_MODULES_PATH: ClassVar[Path] = Path(__file__).parent / "modules"

    def __init__(
        self,
        modules_path: Path | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the ModuleRegistry.

        Args:
            modules_path: Path to the modules directory.
            config: Platform configuration dict (reads 'modules' section).
        """
        self._modules_path: Path = modules_path or self.DEFAULT_MODULES_PATH
        self._config: dict[str, Any] = config or {}
        self._lock: threading.RLock = threading.RLock()
        self._records: dict[str, ModuleRecord] = {}
        self._discovered: bool = False

    # ── Discovery ────────────────────────────────────────────────────────────

    def discover(self) -> list[str]:
        """Scan the modules directory and discover all available modules.

        Reads each module's __init__.py to extract __version__. Falls back
        to decorator-registered classes if the module has been imported.

        Returns:
            List of discovered module names.
        """
        with self._lock:
            discovered: list[str] = []

            if not self._modules_path.exists() or not self._modules_path.is_dir():
                logging.getLogger("eni.registry").warning(
                    "Modules path does not exist: %s", self._modules_path
                )
                return discovered

            for entry in sorted(self._modules_path.iterdir()):
                if not entry.is_dir() or entry.name.startswith("_"):
                    continue
                init_file = entry / "__init__.py"
                if not init_file.exists():
                    continue

                name = entry.name
                version = self._extract_version(init_file)
                module_cfg = self._config.get("modules", {}).get(name, {})

                record = ModuleRecord(
                    name=name,
                    path=entry,
                    version=version,
                    enabled=module_cfg.get("enabled", True),
                    required=module_cfg.get("required", False),
                    priority=module_cfg.get("priority", 100),
                    config=module_cfg.get("config", {}),
                )

                self._records[name] = record

                # Import the module package so the @module decorator registers
                # its class in _MODULE_REGISTRY, then bind the record to it.
                # Without the import, module_class stays None and initialize_all()
                # silently skips the module (nothing ever boots).
                self.import_module(name)
                if name in _MODULE_REGISTRY:
                    record.module_class = _MODULE_REGISTRY[name]

                discovered.append(name)

                logging.getLogger("eni.registry").info(
                    "Discovered module: %s v%s (enabled=%s, required=%s, priority=%d)",
                    name,
                    version,
                    record.enabled,
                    record.required,
                    record.priority,
                )

            self._discovered = True
            return discovered

    @staticmethod
    def _extract_version(init_file: Path) -> str:
        """Extract __version__ from a module's __init__.py."""
        try:
            text = init_file.read_text(encoding="utf-8")
            for line in text.split("\n"):
                stripped = line.strip()
                if stripped.startswith("__version__"):
                    parts = stripped.split("=", 1)
                    if len(parts) == 2:
                        return parts[1].strip().strip("\"'")
        except Exception:
            pass
        return "0.0.0"

    # ── Import ───────────────────────────────────────────────────────────────

    def import_module(self, name: str) -> ModuleType | None:
        """Dynamically import a module by name.

        Attempts: enterprise.modules.<name>
        """
        record = self._records.get(name)
        if record is None:
            return None

        import_path = f"enterprise.modules.{name}"
        try:
            return importlib.import_module(import_path)
        except ImportError as e:
            logging.getLogger("eni.registry").warning("Failed to import module %s: %s", name, e)
            return None

    # ── Initialization ───────────────────────────────────────────────────────

    async def initialize_all(self) -> dict[str, HealthStatus]:
        """Initialize all enabled modules in priority order.

        Returns:
            Dict mapping module name to its post-initialization health status.
        """
        if not self._discovered:
            self.discover()

        results: dict[str, HealthStatus] = {}

        # Sort by priority (ascending) for startup
        ordered = sorted(
            [r for r in self._records.values() if r.enabled and r.module_class is not None],
            key=lambda r: r.priority,
        )

        startup_timeout = float(
            (self._config.get("lifecycle", {}) or {}).get("startup_timeout_sec", 30)
        )

        for record in ordered:
            try:
                instance = record.module_class(config=record.config)  # type: ignore[misc]
                record.instance = instance
                # Honor a per-module startup timeout so a hung initialize()
                # cannot block the entire platform boot forever.
                await asyncio.wait_for(instance.initialize(), timeout=startup_timeout)
                instance._started_at = datetime.now(UTC)
                instance.status = HealthStatus.HEALTHY
                results[record.name] = HealthStatus.HEALTHY
                logging.getLogger("eni.registry").info("Initialized module: %s", record.name)
            except TimeoutError:
                logging.getLogger("eni.registry").error(
                    "Module %s initialize() timed out after %ss; marking UNHEALTHY",
                    record.name,
                    startup_timeout,
                )
                results[record.name] = HealthStatus.UNHEALTHY
                if record.instance:
                    record.instance.status = HealthStatus.UNHEALTHY
            except Exception as exc:
                logging.getLogger("eni.registry").error(
                    "Failed to initialize module %s: %s\n%s",
                    record.name,
                    exc,
                    traceback.format_exc(),
                )
                results[record.name] = HealthStatus.UNHEALTHY
                if record.instance:
                    record.instance.status = HealthStatus.UNHEALTHY

        return results

    # ── Shutdown ─────────────────────────────────────────────────────────────

    async def shutdown_all(self) -> dict[str, bool]:
        """Shut down all initialized modules in reverse priority order.

        Returns:
            Dict mapping module name to shutdown success.
        """
        results: dict[str, bool] = {}

        ordered = sorted(
            [r for r in self._records.values() if r.instance is not None],
            key=lambda r: r.priority,
            reverse=True,  # Reverse order for shutdown
        )

        for record in ordered:
            try:
                if record.instance:
                    await record.instance.shutdown()
                results[record.name] = True
                logging.getLogger("eni.registry").info("Shut down module: %s", record.name)
            except Exception as exc:
                logging.getLogger("eni.registry").error(
                    "Failed to shut down module %s: %s", record.name, exc
                )
                results[record.name] = False

        return results

    # ── Query ────────────────────────────────────────────────────────────────

    def list_modules(self) -> list[ModuleRecord]:
        """Return all module records."""
        with self._lock:
            return list(self._records.values())

    def get_record(self, name: str) -> ModuleRecord | None:
        """Get a module record by name."""
        with self._lock:
            return self._records.get(name)

    def get_instance(self, name: str) -> Module | None:
        """Get the initialized module instance by name."""
        record = self._records.get(name)
        if record:
            return record.instance
        return None

    @property
    def discovered(self) -> bool:
        """Whether discovery has been run."""
        return self._discovered


# =============================================================================
# Health Check System
# =============================================================================


def _json_safe(value: Any, depth: int = 0) -> Any:
    """Best-effort coercion of arbitrary probe/metric values to JSON types.

    Used by functional health checks and status reporting so raw Python
    objects (datetimes, enums, sets, nested structures) never break the
    dashboard JSON resposnes. Deeply nested or opaque values are stringified.
    """
    if depth > 12:
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(v, depth + 1) for v in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


@dataclass
class HealthReport:
    """Aggregate health report for a single module or the entire platform.

    Attributes:
        module_name: Name of the module or "platform" for the overall report.
        status: Health status.
        response_time_ms: Milliseconds taken to complete the check.
        timestamp: UTC timestamp of the check.
        details: Arbitrary details from the check.
        consecutive_failures: Number of consecutive failures (module only).
        consecutive_successes: Number of consecutive successes (module only).
    """

    module_name: str
    status: HealthStatus
    response_time_ms: float
    timestamp: datetime
    details: dict[str, Any] = field(default_factory=dict)
    consecutive_failures: int = 0
    consecutive_successes: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "module_name": self.module_name,
            "status": self.status.value,
            "response_time_ms": self.response_time_ms,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details,
            "consecutive_failures": self.consecutive_failures,
            "consecutive_successes": self.consecutive_successes,
        }


class HealthChecker:
    """Periodic health check system that pings every registered module.

    Tracks consecutive failures/successes, applies thresholds to determine
    degraded/unhealthy status, and emits health events on the EventBus.

    Usage::

        checker = HealthChecker(registry, event_bus, config)
        await checker.run_all_checks()
    """

    def __init__(
        self,
        registry: ModuleRegistry,
        event_bus: EventBus | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the HealthChecker.

        Args:
            registry: ModuleRegistry with initialized modules.
            event_bus: EventBus for emitting health events.
            config: Health configuration section.
        """
        self._registry: ModuleRegistry = registry
        self._event_bus: EventBus | None = event_bus
        cfg = config or {}
        self._failure_threshold: int = cfg.get("failure_threshold", 3)
        self._recovery_threshold: int = cfg.get("recovery_threshold", 2)
        self._timeout_sec: float = cfg.get("timeout_sec", 10.0)
        self._lock: threading.RLock = threading.RLock()
        self._reports: dict[str, list[HealthReport]] = defaultdict(list)
        self._failure_counts: dict[str, int] = defaultdict(int)
        self._success_counts: dict[str, int] = defaultdict(int)

    async def run_all_checks(self, functional: bool = False) -> list[HealthReport]:
        """Run health checks on all initialized modules.

        Args:
            functional: When True, also run a real (non-mutating) functional
                probe on every module that exposes one, so health reflects
                real capability rather than just successful construction.
                Degrades gracefully for modules without a probe.

        Returns:
            List of HealthReports, one per module plus a platform aggregate.
        """
        reports: list[HealthReport] = []
        records = self._registry.list_modules()

        for record in records:
            if record.instance is None:
                continue

            if functional:
                report = await self.functional_health_check(record.name)
                if report is None:
                    # Extremely defensive: instance vanished between listing and
                    # lookup. Fall back to a structural check so we never emit
                    # a missing report into the stream.
                    report = await self._check_one(record.instance, record.name)
            else:
                report = await self._check_one(record.instance, record.name)
            self._update_tracking(report)
            reports.append(report)

            if self._event_bus:
                self._event_bus.publish(
                    Event.create(
                        topic="platform.health_check",
                        source="health_checker",
                        payload=report.to_dict(),
                    )
                )

        # Platform aggregate
        platform_report = self._aggregate(reports)
        reports.append(platform_report)
        return reports

    async def run_check_for(self, module_name: str) -> HealthReport | None:
        """Run a health check for a single module by name."""
        instance = self._registry.get_instance(module_name)
        if instance is None:
            return None
        report = await self._check_one(instance, module_name)
        self._update_tracking(report)
        return report

    # ── Functional Health ────────────────────────────────────────────────────

    async def functional_health_check(
        self,
        module_name: str,
        timeout_sec: float | None = None,
    ) -> HealthReport | None:
        """Run a structural + functional health check for a single module.

        In addition to the structural ``health_check()`` (which only proves the
        module was constructed), runs a real, non-mutating functional probe when
        the module exposes one (``probe()`` or ``functional_probe()``) and folds
        the result into the report details. Health therefore reflects real
        capability, not just successful construction.

        Degrades gracefully: modules without a probe return a purely structural
        report with ``functional.reason == "no_probe"``; a probe that raises or
        times out marks the module ``UNHEALTHY``. This method never mutates the
        module and never updates the internal failure/success tracking (it is a
        read-only inspection mode).

        Args:
            module_name: Name of the registered module to check.
            timeout_sec: Optional per-call timeout, defaults to the checker's.

        Returns:
            A HealthReport enriched with functional details, or None if the
            module is not registered.
        """
        instance = self._registry.get_instance(module_name)
        if instance is None:
            return None

        timeout = self._timeout_sec if timeout_sec is None else timeout_sec
        start = time.perf_counter()

        # Structural check (unchanged semantics from _check_one).
        try:
            status = await asyncio.wait_for(instance.health_check(), timeout=timeout)
        except TimeoutError:
            status = HealthStatus.UNHEALTHY
        except Exception:
            status = HealthStatus.UNHEALTHY

        # Optional functional probe — real, non-mutating capability check.
        functional: dict[str, Any] = {"enabled": False, "reason": "no_probe"}
        probe = getattr(instance, "probe", None)
        if not callable(probe):
            probe = getattr(instance, "functional_probe", None)
        if callable(probe):
            functional = {"enabled": True, "ran": True, "ok": None, "error": None}
            try:
                if asyncio.iscoroutinefunction(probe):
                    raw = await asyncio.wait_for(probe(), timeout=timeout)
                else:
                    raw = await asyncio.wait_for(asyncio.to_thread(probe), timeout=timeout)
                functional["ok"] = raw is not False and raw is not None
                functional["result"] = _json_safe(raw)
            except TimeoutError:
                functional.update({"ok": False, "error": "timeout"})
                status = HealthStatus.UNHEALTHY
            except Exception as exc:  # noqa: BLE001 - probe failure degrades health
                functional.update({"ok": False, "error": str(exc)})
                status = HealthStatus.UNHEALTHY

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return HealthReport(
            module_name=module_name,
            status=status,
            response_time_ms=round(elapsed_ms, 2),
            timestamp=datetime.now(UTC),
            details={
                "module_id": instance.module_id,
                "version": instance.version,
                "check_mode": "functional",
                "functional": functional,
            },
        )

    async def _check_one(self, instance: Module, module_name: str) -> HealthReport:
        """Run a single module health check with timeout."""
        start = time.perf_counter()
        try:
            status = await asyncio.wait_for(instance.health_check(), timeout=self._timeout_sec)
        except TimeoutError:
            status = HealthStatus.UNHEALTHY
        except Exception:
            status = HealthStatus.UNHEALTHY

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return HealthReport(
            module_name=module_name,
            status=status,
            response_time_ms=round(elapsed_ms, 2),
            timestamp=datetime.now(UTC),
            details={
                "module_id": instance.module_id,
                "version": instance.version,
            },
        )

    def _update_tracking(self, report: HealthReport) -> None:
        """Update consecutive failure/success counters."""
        name = report.module_name
        with self._lock:
            self._reports[name].append(report)
            # Keep last 100 reports
            if len(self._reports[name]) > 100:
                self._reports[name] = self._reports[name][-100:]

            if report.status == HealthStatus.HEALTHY:
                self._success_counts[name] += 1
                self._failure_counts[name] = 0
            else:
                self._failure_counts[name] += 1
                self._success_counts[name] = 0

            report.consecutive_failures = self._failure_counts[name]
            report.consecutive_successes = self._success_counts[name]

    def _aggregate(self, reports: list[HealthReport]) -> HealthReport:
        """Aggregate all module reports into a platform-level report."""
        if not reports:
            return HealthReport(
                module_name="platform",
                status=HealthStatus.UNKNOWN,
                response_time_ms=0.0,
                timestamp=datetime.now(UTC),
            )

        unhealthy = [r for r in reports if r.status == HealthStatus.UNHEALTHY]
        total = len(reports)

        if not unhealthy:
            status = HealthStatus.HEALTHY
        elif len(unhealthy) < total:
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.UNHEALTHY

        return HealthReport(
            module_name="platform",
            status=status,
            response_time_ms=sum(r.response_time_ms for r in reports),
            timestamp=datetime.now(UTC),
            details={
                "modules_checked": total,
                "healthy": total - len(unhealthy),
                "unhealthy": len(unhealthy),
                "unhealthy_modules": [r.module_name for r in unhealthy],
            },
        )

    def get_failure_count(self, module_name: str) -> int:
        """Return the consecutive failure count for a module."""
        with self._lock:
            return self._failure_counts.get(module_name, 0)

    def is_degraded(self, module_name: str) -> bool:
        """Return True if a module has exceeded the failure threshold."""
        return self.get_failure_count(module_name) >= self._failure_threshold

    def get_latest_report(self, module_name: str) -> HealthReport | None:
        """Return the most recent health report for a module."""
        with self._lock:
            reports = self._reports.get(module_name, [])
            return reports[-1] if reports else None

    def get_all_reports(self) -> dict[str, list[HealthReport]]:
        """Return all health reports."""
        with self._lock:
            return {k: list(v) for k, v in self._reports.items()}


# =============================================================================
# Metrics Collector
# =============================================================================


@dataclass
class MetricPoint:
    """A single metric data point."""

    name: str
    value: float
    tags: dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    module: str = "platform"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "name": self.name,
            "value": self.value,
            "tags": self.tags,
            "timestamp": self.timestamp.isoformat(),
            "module": self.module,
        }


class MetricsCollector:
    """Cross-module metrics collector.

    Provides counter, gauge, and histogram metric types. Aggregates metrics
    from all modules into a central store. Supports Prometheus and JSON
    export formats.

    Usage::

        collector = MetricsCollector()
        collector.increment("requests.total", module="api")
        collector.gauge("memory.bytes", 1073741824)
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize the MetricsCollector.

        Args:
            config: Metrics configuration section.
        """
        cfg = config or {}
        self._enabled: bool = cfg.get("enabled", True)
        self._lock: threading.RLock = threading.RLock()
        self._counters: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._history: list[MetricPoint] = []
        self._history_limit: int = 100000

    def increment(
        self,
        name: str,
        value: float = 1.0,
        tags: dict[str, str] | None = None,
        module: str = "platform",
    ) -> None:
        """Increment a counter metric."""
        if not self._enabled:
            return
        tag_key = json.dumps(tags or {}, sort_keys=True)
        with self._lock:
            self._counters[name][tag_key] += value
            self._record(MetricPoint(name=name, value=value, tags=tags or {}, module=module))

    def set_gauge(
        self,
        name: str,
        value: float,
        tags: dict[str, str] | None = None,
        module: str = "platform",
    ) -> None:
        """Set a gauge metric to a specific value."""
        if not self._enabled:
            return
        with self._lock:
            self._gauges[name] = value
            self._record(MetricPoint(name=name, value=value, tags=tags or {}, module=module))

    def observe(
        self,
        name: str,
        value: float,
        tags: dict[str, str] | None = None,
        module: str = "platform",
    ) -> None:
        """Record an observation in a histogram metric."""
        if not self._enabled:
            return
        with self._lock:
            self._histograms[name].append(value)
            self._record(MetricPoint(name=name, value=value, tags=tags or {}, module=module))

    def _record(self, point: MetricPoint) -> None:
        """Store a metric point in history."""
        self._history.append(point)
        if len(self._history) > self._history_limit:
            self._history = self._history[-self._history_limit :]

    def get_counter(self, name: str, tags: dict[str, str] | None = None) -> float:
        """Get the current value of a counter."""
        tag_key = json.dumps(tags or {}, sort_keys=True)
        with self._lock:
            return self._counters.get(name, {}).get(tag_key, 0.0)

    def get_gauge(self, name: str) -> float:
        """Get the current value of a gauge."""
        with self._lock:
            return self._gauges.get(name, 0.0)

    def get_histogram_stats(self, name: str) -> dict[str, float]:
        """Get statistics for a histogram metric."""
        with self._lock:
            values = self._histograms.get(name, [])
            if not values:
                return {"count": 0, "sum": 0.0, "min": 0.0, "max": 0.0, "avg": 0.0}
            return {
                "count": len(values),
                "sum": sum(values),
                "min": min(values),
                "max": max(values),
                "avg": sum(values) / len(values),
            }

    def snapshot(self) -> dict[str, Any]:
        """Take a full snapshot of all metrics."""
        with self._lock:
            return {
                "counters": {name: dict(tags) for name, tags in self._counters.items()},
                "gauges": dict(self._gauges),
                "histograms": {name: self.get_histogram_stats(name) for name in self._histograms},
                "history_count": len(self._history),
            }

    def get_recent(
        self,
        name: str | None = None,
        limit: int = 100,
    ) -> list[MetricPoint]:
        """Get recent metric data points, optionally filtered by name."""
        with self._lock:
            points = self._history
            if name:
                points = [p for p in points if p.name == name]
            return points[-limit:]

    def reset(self) -> None:
        """Reset all metrics (useful for testing)."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self._history.clear()


# =============================================================================
# Logging Bridge
# =============================================================================


class LoggingBridge:
    """Aggregates logs from all modules into a unified logging system.

    Provides structured logging with module attribution, correlation IDs,
    and configurable output sinks (console, file, syslog).

    Usage::

        bridge = LoggingBridge(config)
        logger = bridge.get_logger("safety_governance")
        logger.info("Guardrail check passed", extra={"correlation_id": "abc"})
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize the LoggingBridge.

        Args:
            config: Logging configuration section.
        """
        cfg = config or {}
        self._level: str = cfg.get("level", "INFO")
        self._loggers: dict[str, logging.Logger] = {}
        self._root_logger: logging.Logger = logging.getLogger("eni.platform")
        self._configure_root(cfg)

    def _configure_root(self, cfg: dict[str, Any]) -> None:
        """Set up the root logger with configured handlers."""
        level = getattr(logging, self._level.upper(), logging.INFO)
        self._root_logger.setLevel(level)
        self._root_logger.handlers.clear()

        outputs = cfg.get("outputs", [{"type": "console", "level": "INFO"}])
        for output in outputs:
            handler = self._create_handler(output)
            if handler:
                self._root_logger.addHandler(handler)

    def _create_handler(self, output_cfg: dict[str, Any]) -> logging.Handler | None:
        """Create a logging handler from configuration."""
        output_type = output_cfg.get("type", "console")
        level = getattr(logging, output_cfg.get("level", "INFO").upper(), logging.INFO)

        if output_type == "console":
            handler: logging.Handler = logging.StreamHandler(sys.stderr)
            handler.setLevel(level)
            handler.setFormatter(self._formatter(output_cfg))
            return handler

        if output_type == "file":
            path = output_cfg.get("path", "logs/platform.log")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            from logging.handlers import RotatingFileHandler

            handler = RotatingFileHandler(
                path,
                maxBytes=output_cfg.get("max_bytes", 10_485_760),
                backupCount=output_cfg.get("backup_count", 10),
            )
            handler.setLevel(level)
            handler.setFormatter(self._formatter(output_cfg))
            return handler

        if output_type == "syslog":
            try:
                from logging.handlers import SysLogHandler

                handler = SysLogHandler(address="/dev/log")
                handler.setLevel(level)
                handler.setFormatter(self._formatter(output_cfg))
                return handler
            except Exception:
                logging.getLogger("eni").warning("SysLogHandler unavailable, skipping")
                return None

        return None

    @staticmethod
    def _formatter(cfg: dict[str, Any]) -> logging.Formatter:
        """Create a formatter based on config."""
        fmt_type = cfg.get("format", "text")
        if fmt_type == "json":
            return _JsonFormatter()
        return logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )

    def get_logger(
        self, module_name: str, correlation_id: str | None = None
    ) -> logging.LoggerAdapter:
        """Get a logger for a specific module with optional correlation ID.

        Args:
            module_name: Name of the module requesting a logger.
            correlation_id: Optional correlation ID for request tracing.

        Returns:
            A LoggerAdapter configured with module context.
        """
        logger = logging.getLogger(f"eni.{module_name}")
        extra = {
            "module_name": module_name,
            "module_correlation": correlation_id or "-",
        }
        return logging.LoggerAdapter(logger, extra)

    def bridge_module_logger(self, module_name: str) -> logging.Logger:
        """Get a raw logger for a module, bridged into the platform logging tree.

        Useful for modules that already create their own loggers.
        """
        return logging.getLogger(f"eni.modules.{module_name}")

    def set_level(self, level: str) -> None:
        """Dynamically change the root log level."""
        lvl = getattr(logging, level.upper(), logging.INFO)
        self._root_logger.setLevel(lvl)
        self._level = level

    @property
    def level(self) -> str:
        """Current log level."""
        return self._level


class _JsonFormatter(logging.Formatter):
    """JSON log formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a JSON string."""
        log_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": getattr(record, "module_name", "-"),
            "correlation_id": getattr(record, "module_correlation", "-"),
            "path": record.pathname,
            "line": record.lineno,
            "function": record.funcName,
        }
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = str(record.exc_info[1])
            log_entry["traceback"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, default=str)


# =============================================================================
# Configuration Loader
# =============================================================================


class ConfigurationLoader:
    """Loads and validates platform configuration from YAML.

    Supports merging with environment variable overrides. Falls back to
    sensible defaults if the config file is missing.

    Usage::

        loader = ConfigurationLoader()
        config = loader.load()
    """

    DEFAULT_CONFIG_PATH: ClassVar[Path] = Path(__file__).parent / "config.yaml"

    def __init__(self, config_path: Path | None = None) -> None:
        """Initialize the ConfigurationLoader.

        Args:
            config_path: Path to the config YAML file. Defaults to
                         enterprise/config.yaml.
        """
        self._config_path: Path = config_path or self.DEFAULT_CONFIG_PATH
        self._config: dict[str, Any] = {}
        self._loaded: bool = False

    def load(self) -> dict[str, Any]:
        """Load configuration from YAML file.

        Falls back to defaults if YAML is unavailable or file missing.

        Returns:
            Parsed configuration dict.
        """
        if self._loaded:
            return self._config

        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError:
            logging.getLogger("eni.config").warning(
                "PyYAML not installed, loading JSON config or defaults"
            )
            return self._load_defaults()

        if not self._config_path.exists():
            logging.getLogger("eni.config").warning(
                "Config file not found at %s, using defaults", self._config_path
            )
            return self._load_defaults()

        try:
            with open(self._config_path, encoding="utf-8") as f:
                self._config = yaml.safe_load(f) or {}
            self._loaded = True
            logging.getLogger("eni.config").info("Loaded configuration from %s", self._config_path)
        except Exception as exc:
            logging.getLogger("eni.config").error("Failed to load config: %s, using defaults", exc)
            self._config = self._load_defaults()
            self._loaded = True

        self._apply_env_overrides()
        return self._config

    def reload(self) -> dict[str, Any]:
        """Force reload configuration from disk."""
        self._loaded = False
        return self.load()

    @staticmethod
    def _load_defaults() -> dict[str, Any]:
        """Return sensible default configuration."""
        return {
            "platform": {
                "name": "ENI Enterprise Platform",
                "version": "1.0.0",
                "environment": "development",
            },
            "modules": {},
            "logging": {"level": "INFO", "outputs": [{"type": "console", "level": "INFO"}]},
            "metrics": {"enabled": True, "collection_interval_sec": 15},
            "health": {
                "enabled": True,
                "global_interval_sec": 30,
                "failure_threshold": 3,
                "recovery_threshold": 2,
                "timeout_sec": 10,
            },
            "event_bus": {
                "max_queue_size": 100000,
                "async_dispatch": True,
                "max_workers": 8,
            },
            "lifecycle": {
                "startup_grace_period_sec": 60,
                "shutdown_timeout_sec": 30,
            },
        }

    def _apply_env_overrides(self) -> None:
        """Apply environment variable overrides to configuration.

        Supports:
          ENI_ENV -> platform.environment
          ENI_LOG_LEVEL -> logging.level
          ENI_MODULES_PATH -> overrides modules path
        """
        env = os.environ.get("ENI_ENV")
        if env:
            self._config.setdefault("platform", {})["environment"] = env

        log_level = os.environ.get("ENI_LOG_LEVEL")
        if log_level and "logging" in self._config:
            self._config["logging"]["level"] = log_level.upper()

    def get(self, key: str, default: Any = None) -> Any:
        """Get a nested config value using dot notation.

        Example: loader.get('modules.safety_governance.enabled', True)
        """
        if not self._loaded:
            self.load()
        parts = key.split(".")
        node = self._config
        for part in parts:
            if isinstance(node, dict):
                node = node.get(part)
                if node is None:
                    return default
            else:
                return default
        return node

    @property
    def config(self) -> dict[str, Any]:
        """The loaded configuration dict."""
        if not self._loaded:
            self.load()
        return self._config


# =============================================================================
# Platform OS — Main Singleton Orchestrator
# =============================================================================


class PlatformOS:
    """Central orchestration singleton for the ENI Enterprise Platform.

    PlatformOS wires together all enterprise modules through:
    - Module registration and discovery (ModuleRegistry)
    - Event-driven communication (EventBus)
    - Health monitoring (HealthChecker)
    - Metrics collection (MetricsCollector)
    - Unified logging (LoggingBridge)
    - Lifecycle state machine management
    - Configuration loading (ConfigurationLoader)

    This is a **thread-safe singleton** — only one instance exists per process.
    Use PlatformOS.instance() to access it.

    Usage::

        platform = PlatformOS.instance()
        platform.initialize()
        await platform.start()
        # ... platform is running ...
        await platform.shutdown()
    """

    _instance: ClassVar[PlatformOS | None] = None
    _instance_lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self) -> None:
        """Direct construction is discouraged — use PlatformOS.instance()."""
        if not getattr(self, "_init_by_instance", False):
            msg = "Use PlatformOS.instance() to get the singleton instance"
            raise RuntimeError(msg)
        self._logger: logging.LoggerAdapter = logging.getLogger("eni.platform")  # type: ignore[assignment]
        self._state_lock: threading.RLock = threading.RLock()
        self._state: LifecycleState = LifecycleState.UNINITIALIZED
        self._state_history: list[tuple[LifecycleState, datetime]] = []
        self._config_loader: ConfigurationLoader | None = None
        self._config: dict[str, Any] = {}
        self._module_registry: ModuleRegistry | None = None
        self._event_bus: EventBus | None = None
        self._health_checker: HealthChecker | None = None
        self._metrics_collector: MetricsCollector | None = None
        self._logging_bridge: LoggingBridge | None = None
        self._platform_id: str = str(uuid.uuid4())
        self._started_at: datetime | None = None
        self._health_poll_task: asyncio.Task[None] | None = None
        self._health_poll_interval: float = 30.0

    @classmethod
    def instance(cls) -> PlatformOS:
        """Get or create the singleton PlatformOS instance (thread-safe)."""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    instance = cls.__new__(cls)
                    object.__setattr__(instance, "_init_by_instance", True)
                    cls.__init__(instance)  # type: ignore[misc]
                    cls._instance = instance
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton (primarily for testing)."""
        with cls._instance_lock:
            cls._instance = None

    # ── Lifecycle Management ─────────────────────────────────────────────────

    def initialize(
        self,
        config_path: Path | None = None,
        modules_path: Path | None = None,
    ) -> None:
        """Initialize the platform: load config, discover modules, set up subsystems.

        This is the first step — call before start().

        Args:
            config_path: Path to config YAML (default: enterprise/config.yaml).
            modules_path: Path to modules directory (default: enterprise/modules/).
        """
        self._transition_to(LifecycleState.INITIALIZING)

        # Load configuration
        self._config_loader = ConfigurationLoader(config_path)
        self._config = self._config_loader.load()

        # Set up logging bridge
        self._logging_bridge = LoggingBridge(self._config.get("logging", {}))
        self._logger = self._logging_bridge.get_logger("platform")  # type: ignore[assignment]
        self._logger.info("Platform %s initializing...", self._platform_id)

        # Create EventBus
        self._event_bus = EventBus(self._config.get("event_bus", {}))

        # Create MetricsCollector
        self._metrics_collector = MetricsCollector(self._config.get("metrics", {}))

        # Discover modules
        self._transition_to(LifecycleState.DISCOVERING)
        self._module_registry = ModuleRegistry(
            modules_path=modules_path or ModuleRegistry.DEFAULT_MODULES_PATH,
            config=self._config,
        )
        discovered = self._module_registry.discover()
        self._logger.info("Discovered %d modules: %s", len(discovered), discovered)

        # Create health checker
        self._transition_to(LifecycleState.CONFIGURING)
        self._health_checker = HealthChecker(
            registry=self._module_registry,
            event_bus=self._event_bus,
            config=self._config.get("health", {}),
        )
        self._health_poll_interval = float(
            self._config.get("health", {}).get("global_interval_sec", 30)
        )

        self._logger.info(
            "Platform initialized: %d modules discovered, config loaded",
            len(discovered),
        )

    async def start(self) -> None:
        """Start the platform: initialize all modules, begin health polling.

        Transitions: CONFIGURING -> STARTING -> RUNNING (or DEGRADED).
        """
        if self._state not in (
            LifecycleState.CONFIGURING,
            LifecycleState.STOPPED,
        ):
            msg = f"Cannot start from state {self._state.value}. Call initialize() first."
            raise RuntimeError(msg)

        self._transition_to(LifecycleState.STARTING)
        self._started_at = datetime.now(UTC)

        # Initialize all modules
        if self._module_registry is None:
            msg = "ModuleRegistry not initialized"
            raise RuntimeError(msg)

        results = await self._module_registry.initialize_all()
        self._logger.info(
            "Module initialization complete: %s",
            {k: v.value for k, v in results.items()},
        )

        # Determine initial state
        required_failed = [
            name
            for name, status in results.items()
            if status != HealthStatus.HEALTHY
            and self._module_registry.get_record(name) is not None
            and self._module_registry.get_record(name).required  # type: ignore[union-attr]
        ]

        if required_failed:
            self._transition_to(LifecycleState.DEGRADED)
            self._logger.warning(
                "Platform started DEGRADED — failed required modules: %s",
                required_failed,
            )
        else:
            self._transition_to(LifecycleState.RUNNING)

        # Record lifecycle + module metrics so the (previously decorative)
        # MetricsCollector actually reflects platform reality.
        if self._metrics_collector:
            self._metrics_collector.set_gauge(
                "platform.state",
                float(_STATE_INDEX.get(self._state, 0)),
                module="platform_os",
            )
            self._metrics_collector.set_gauge(
                "platform.modules.initialized",
                len(results),
                module="platform_os",
            )
            self._metrics_collector.set_gauge(
                "platform.modules.healthy",
                sum(1 for s in results.values() if s == HealthStatus.HEALTHY),
                module="platform_os",
            )
            self._metrics_collector.increment("platform.lifecycle.starts", module="platform_os")

        # Start background health polling (only if we have a running loop)
        try:
            loop = asyncio.get_running_loop()
            self._health_poll_task = loop.create_task(self._health_poll_loop())
        except RuntimeError:
            # No running loop; health checks must be invoked manually
            self._logger.info("No running event loop; health polling not started")

        # Publish platform.started event
        if self._event_bus:
            self._event_bus.publish(
                Event.create(
                    topic="platform.started",
                    source="platform_os",
                    payload={
                        "platform_id": self._platform_id,
                        "state": self._state.value,
                        "modules": list(results.keys()),
                    },
                )
            )

        self._logger.info(
            "Platform started in state %s (id=%s)", self._state.value, self._platform_id
        )

    async def shutdown(self) -> None:
        """Gracefully shut down the platform: stop health polling, shut down modules.

        Transitions: any non-terminal -> STOPPING -> STOPPED.
        """
        if self._state in (LifecycleState.STOPPED, LifecycleState.STOPPING):
            return

        self._transition_to(LifecycleState.STOPPING)
        self._logger.info("Platform shutting down...")

        # Stop health polling
        if self._health_poll_task and not self._health_poll_task.done():
            self._health_poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._health_poll_task

        # Publish platform.stopping event
        if self._event_bus:
            self._event_bus.publish(
                Event.create(
                    topic="platform.stopping",
                    source="platform_os",
                    payload={"platform_id": self._platform_id},
                )
            )

        # Shut down all modules
        if self._module_registry:
            results = await self._module_registry.shutdown_all()
            self._logger.info("Module shutdown complete: %s", results)

        # Shut down event bus
        if self._event_bus:
            float(self._config.get("lifecycle", {}).get("shutdown_timeout_sec", 30))
            self._event_bus.shutdown()

        self._transition_to(LifecycleState.STOPPED)
        self._logger.info("Platform stopped.")

    # ── Pause / Resume ───────────────────────────────────────────────────────

    async def pause(self) -> None:
        """Pause the platform: stop health polling and background work.

        Transitions RUNNING/DEGRADED/RECOVERING -> PAUSING -> PAUSED.
        """
        if self._state not in (
            LifecycleState.RUNNING,
            LifecycleState.DEGRADED,
            LifecycleState.RECOVERING,
        ):
            msg = f"Cannot pause from state {self._state.value}"
            raise RuntimeError(msg)

        self._transition_to(LifecycleState.PAUSING)
        self._logger.info("Platform pausing...")
        if self._health_poll_task and not self._health_poll_task.done():
            self._health_poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._health_poll_task
            self._health_poll_task = None
        self._transition_to(LifecycleState.PAUSED)
        self._logger.info("Platform paused.")

    async def resume(self) -> None:
        """Resume the platform from PAUSED: restart health polling and recover.

        Transitions PAUSED -> RECOVERING -> RUNNING (or DEGRADED).
        """
        if self._state != LifecycleState.PAUSED:
            msg = f"Cannot resume from state {self._state.value}"
            raise RuntimeError(msg)

        self._transition_to(LifecycleState.RECOVERING)
        self._logger.info("Platform resuming...")

        # Attempt to re-initialize any failed/UNHEALTHY required modules.
        if self._module_registry is not None:
            for record in self._module_registry.list_modules():
                if not record.enabled:
                    continue
                inst = record.instance
                if inst is not None and inst.status in (
                    HealthStatus.UNHEALTHY,
                    HealthStatus.UNKNOWN,
                ):
                    try:
                        await inst.initialize()
                        inst.status = HealthStatus.HEALTHY
                        self._logger.info("Recovered module: %s", record.name)
                    except Exception as exc:
                        self._logger.error("Failed to recover module %s: %s", record.name, exc)

        # Restart health polling
        try:
            loop = asyncio.get_running_loop()
            self._health_poll_task = loop.create_task(self._health_poll_loop())
        except RuntimeError:
            self._logger.info("No running event loop; health polling not restarted")

        self._transition_to(LifecycleState.RUNNING)
        self._logger.info("Platform resumed.")

    # ── Health Poll Loop ─────────────────────────────────────────────────────

    async def _health_poll_loop(self) -> None:
        """Background loop that periodically runs health checks."""
        self._logger.debug("Health poll loop started (interval=%.1fs)", self._health_poll_interval)
        while self._state in (
            LifecycleState.RUNNING,
            LifecycleState.DEGRADED,
            LifecycleState.RECOVERING,
        ):
            try:
                await asyncio.sleep(self._health_poll_interval)
                if self._health_checker:
                    reports = await self._health_checker.run_all_checks()
                    self._evaluate_platform_health(reports)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._logger.error("Health poll error: %s", exc, exc_info=True)

    def _evaluate_platform_health(self, reports: list[HealthReport]) -> None:
        """Evaluate overall platform health from a set of reports.

        May transition to DEGRADED or RECOVERING based on required module status.
        """
        if self._module_registry is None:
            return

        # Find the platform aggregate report (last in list)
        platform_report = next((r for r in reports if r.module_name == "platform"), None)
        if platform_report is None:
            return

        if (
            platform_report.status == HealthStatus.UNHEALTHY
            and self._state != LifecycleState.DEGRADED
        ):
            self._transition_to(LifecycleState.DEGRADED)
            self._logger.error("Platform health degraded!")
        elif (
            platform_report.status == HealthStatus.HEALTHY
            and self._state == LifecycleState.DEGRADED
        ):
            self._transition_to(LifecycleState.RECOVERING)
            self._logger.info("Platform recovering from degraded state...")
            # If everything is healthy, transition back to RUNNING
            self._transition_to(LifecycleState.RUNNING)

    async def run_health_check(self) -> list[HealthReport]:
        """Manually trigger a full health check.

        Returns:
            List of HealthReports.
        """
        if self._health_checker is None:
            return []
        return await self._health_checker.run_all_checks()

    async def run_module_health_check(self, module_name: str) -> HealthReport | None:
        """Run a health check for a single module."""
        if self._health_checker is None:
            return None
        return await self._health_checker.run_check_for(module_name)

    # ── State Machine ────────────────────────────────────────────────────────

    def _transition_to(self, target: LifecycleState) -> None:
        """Transition the platform to a new lifecycle state.

        Validates the transition and records it in the state history.
        """
        with self._state_lock:
            if not self._state.can_transition_to(target):
                msg = f"Invalid state transition: {self._state.value} -> {target.value}"
                raise RuntimeError(msg)
            old = self._state
            self._state = target
            self._state_history.append((target, datetime.now(UTC)))

            if self._event_bus:
                self._event_bus.publish(
                    Event.create(
                        topic="platform.state_change",
                        source="platform_os",
                        payload={
                            "from": old.value,
                            "to": target.value,
                            "platform_id": self._platform_id,
                        },
                    )
                )

            self._logger.info("Platform state: %s -> %s", old.value, target.value)

    @property
    def state(self) -> LifecycleState:
        """Current platform lifecycle state."""
        with self._state_lock:
            return self._state

    @property
    def state_history(self) -> list[tuple[LifecycleState, datetime]]:
        """History of state transitions."""
        with self._state_lock:
            return list(self._state_history)

    # ── Accessors ────────────────────────────────────────────────────────────

    @property
    def event_bus(self) -> EventBus | None:
        """The platform EventBus."""
        return self._event_bus

    @property
    def module_registry(self) -> ModuleRegistry | None:
        """The platform ModuleRegistry."""
        return self._module_registry

    @property
    def health_checker(self) -> HealthChecker | None:
        """The platform HealthChecker."""
        return self._health_checker

    @property
    def metrics(self) -> MetricsCollector | None:
        """The platform MetricsCollector."""
        return self._metrics_collector

    @property
    def logging(self) -> LoggingBridge | None:
        """The platform LoggingBridge."""
        return self._logging_bridge

    @property
    def config(self) -> dict[str, Any]:
        """The loaded platform configuration."""
        return self._config

    @property
    def platform_id(self) -> str:
        """Unique platform instance ID."""
        return self._platform_id

    @property
    def uptime_seconds(self) -> float | None:
        """Platform uptime in seconds, or None if not started."""
        if self._started_at is None:
            return None
        return (datetime.now(UTC) - self._started_at).total_seconds()

    # ── Status Report ────────────────────────────────────────────────────────

    def status_report(self) -> dict[str, Any]:
        """Generate a comprehensive status report for the platform."""
        mc = self._metrics_collector
        eb = self._event_bus
        mr = self._module_registry

        return {
            "platform_id": self._platform_id,
            "state": self._state.value,
            "uptime_seconds": self.uptime_seconds,
            "config": {
                "environment": self._config.get("platform", {}).get("environment", "unknown"),
                "version": self._config.get("platform", {}).get("version", "0.0.0"),
            },
            "modules": {
                "total_discovered": len(mr.list_modules()) if mr else 0,
                "initialized": len(
                    [r for r in (mr.list_modules() if mr else []) if r.instance is not None]
                )
                if mr
                else 0,
            },
            "events": eb.get_stats() if eb else {},
            "metrics": mc.snapshot() if mc else {},
            "state_history": [
                {"state": s[0].value, "timestamp": s[1].isoformat()}
                for s in self._state_history[-20:]
            ],
        }

    # ── Signal Handling ──────────────────────────────────────────────────────

    def register_signal_handlers(self) -> None:
        """Register OS signal handlers for graceful shutdown (SIGINT, SIGTERM)."""

        def _handle_signal(signum: int, frame: Any) -> None:
            sig_name = signal.Signals(signum).name
            self._logger.info("Received signal %s, initiating shutdown...", sig_name)
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                return
            if loop.is_running():
                loop.create_task(self.shutdown())

        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)
        self._logger.info("Signal handlers registered (SIGINT, SIGTERM)")

    def __repr__(self) -> str:
        return (
            f"<PlatformOS id={self._platform_id[:8]} "
            f"state={self._state.value} "
            f"modules={len(self._module_registry.list_modules()) if self._module_registry else 0}>"
        )


# =============================================================================
# Convenience: create a platform instance
# =============================================================================


def create_platform(
    config_path: Path | None = None,
    modules_path: Path | None = None,
) -> PlatformOS:
    """Create and initialize a PlatformOS instance.

    Convenience function that calls instance() and initialize() in one step.

    Args:
        config_path: Path to config.yaml.
        modules_path: Path to modules directory.

    Returns:
        An initialized PlatformOS instance.
    """
    platform = PlatformOS.instance()
    platform.initialize(config_path=config_path, modules_path=modules_path)
    return platform


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Core
    "PlatformOS",
    "create_platform",
    # Module System
    "Module",
    "ModuleRegistry",
    "ModuleRecord",
    "module",
    # Events
    "EventBus",
    "Event",
    "EventPriority",
    "Subscription",
    # Health
    "HealthChecker",
    "HealthReport",
    "HealthStatus",
    # Metrics
    "MetricsCollector",
    "MetricPoint",
    # Logging
    "LoggingBridge",
    # Config
    "ConfigurationLoader",
    # Enums
    "LifecycleState",
]

__version__ = "1.0.0"
__author__ = "Eni Builder Enterprise"
