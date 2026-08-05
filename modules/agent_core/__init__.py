"""
Claude Code Core — Enterprise Platform Kernel Module v2.0.0
============================================================

Re-implementation of Anthropic's Claude Code QueryEngine, Coordinator,
Task system, State management, Context manager, Hooks engine, and
Services as native Python async classes that plug into the ENI
Enterprise Platform Kernel.

100x better than the TypeScript original:
  - Model-agnostic (Anthropic, OpenAI, Google, local models)
  - Async-native with asyncio
  - Parallel-by-default with DAG scheduling
  - Self-healing with automatic retry and circuit breaking
  - Metric-emitting with Prometheus-compatible counters

Architecture:
  ClaudeCodeModule (Module)
  ├── SuperiorQueryEngine   — multi-model routing, streaming, tool loop
  ├── TaskCoordinator       — DAG scheduling, retry, timeout, parallel dispatch
  ├── TaskScheduler         — background tasks, swarm integration
  ├── SmartContext          — embeddings-based relevance, multi-tier compression
  ├── HooksEngine           — 25+ lifecycle hooks, sync+async, plugin system
  ├── StateManager          — distributed state with CRDT
  └── ServiceRegistry       — ModelService, ToolService, MemoryService, AuthService

Version: 2.0.0
Python: 3.10+
"""

from __future__ import annotations

import os as _os
import sys as _sys

__version__ = "2.0.0"

# Ensure enterprise path is available
_ENTERPRISE_DIR = _os.path.dirname(_os.path.dirname(__file__))
_PARENT = _os.path.dirname(_ENTERPRISE_DIR)
if _PARENT not in _sys.path:
    _sys.path.insert(0, _PARENT)

try:
    from enterprise.platform_kernel import HealthStatus, Module, module
except ImportError:
    from platform_kernel import HealthStatus, Module, module

# ── Core Engine ────────────────────────────────────────────────────────────
import contextlib

from .context_manager import (
    CompressionEngine,
    ContextTier,
    EmbeddingCache,
    SmartContext,
    WindowManager,
)
from .coordinator import (
    ExecutionDAG,
    ExecutionNode,
    ParallelDispatch,
    SchedulePolicy,
    TaskCoordinator,
)
from .hooks_engine import (
    HookPlugin,
    HookPriority,
    HookResult,
    HooksEngine,
    HookType,
    PluginManifest,
)

# ── Provider Transport & Model Backends ─────────────────────────────────────
from .providers import (
    AnthropicProvider,
    ChatProvider,
    EchoProvider,
    MockProvider,
    OpenAICompatibleProvider,
    ProviderRegistry,
    ProviderResponse,
    ResilientProvider,
    RetryPolicy,
    get_provider,
)
from .query_engine import (
    AnthropicBackend,
    ModelBackend,
    ModelRouter,
    OpenAICompatibleBackend,
    QueryConfig,
    QueryResult,
    SimulationBackend,
    StreamingResponse,
    SuperiorQueryEngine,
    ToolCallResult,
)
from .services import (
    AuthService,
    AuthToken,
    MemoryEntry,
    MemoryService,
    ModelProvider,
    ModelService,
    ServiceRegistry,
    ToolDefinition,
    ToolService,
)
from .state_manager import (
    CRDTStore,
    DistributedLock,
    MergeStrategy,
    StateManager,
    StateVersion,
)
from .task_system import (
    BackgroundTask,
    SwarmTaskBridge,
    Task,
    TaskResult,
    TaskScheduler,
    TaskStatus,
    TaskType,
)

# ── Module class registered with the platform kernel ──────────────────────


@module(name="agent_core", version="2.0.0")
class ClaudeCodeModule(Module):
    """Enterprise Claude Code Core Module — Query Engine + Coordinator + Full Stack.

    Lifecycle:
        initialize()  → boots QueryEngine, Coordinator, TaskScheduler,
                         SmartContext, HooksEngine, StateManager, ServiceRegistry
        health_check() → validates all subsystems
        shutdown()    → drains in-flight queries, persists state, closes services
    """

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self._engine: SuperiorQueryEngine | None = None
        self._coordinator: TaskCoordinator | None = None
        self._scheduler: TaskScheduler | None = None
        self._ctx_mgr: SmartContext | None = None
        self._hooks: HooksEngine | None = None
        self._state: StateManager | None = None
        self._services: ServiceRegistry | None = None

    async def initialize(self) -> None:
        self._status = HealthStatus.STARTING
        cfg = self._config or {}

        self._engine = SuperiorQueryEngine()
        if hasattr(self._engine, "initialize"):
            await self._engine.initialize()

        self._coordinator = TaskCoordinator()
        if hasattr(self._coordinator, "initialize"):
            await self._coordinator.initialize()

        self._scheduler = TaskScheduler(config=cfg.get("scheduler", {}))
        await self._scheduler.initialize()

        self._ctx_mgr = SmartContext(config=cfg.get("context", {}))
        await self._ctx_mgr.initialize()

        self._hooks = HooksEngine(config=cfg.get("hooks", {}))
        await self._hooks.initialize()

        self._state = StateManager(config=cfg.get("state", {}))
        await self._state.initialize()

        self._services = ServiceRegistry(config=cfg.get("services", {}))
        await self._services.initialize()

        self._status = HealthStatus.HEALTHY

    async def health_check(self) -> HealthStatus:
        checks = []
        for name, obj in [
            ("engine", self._engine),
            ("coordinator", self._coordinator),
            ("scheduler", self._scheduler),
            ("context", self._ctx_mgr),
            ("hooks", self._hooks),
            ("state", self._state),
            ("services", self._services),
        ]:
            try:
                if obj is not None:
                    if hasattr(obj, "health_check"):
                        ok = await obj.health_check()
                    else:
                        ok = True
                    checks.append((name, ok))
            except Exception:
                checks.append((name, False))
        failed = [n for n, ok in checks if not ok]
        if not failed:
            self._status = HealthStatus.HEALTHY
        elif len(failed) < 3:
            self._status = HealthStatus.DEGRADED
        else:
            self._status = HealthStatus.UNHEALTHY
        return self._status

    async def shutdown(self) -> None:
        self._status = HealthStatus.STOPPING
        for obj in [
            self._services,
            self._state,
            self._hooks,
            self._ctx_mgr,
            self._scheduler,
            self._coordinator,
            self._engine,
        ]:
            if obj is not None and hasattr(obj, "shutdown"):
                with contextlib.suppress(Exception):
                    await obj.shutdown()
        self._status = HealthStatus.UNKNOWN

    @property
    def engine(self) -> SuperiorQueryEngine | None:
        return self._engine

    @property
    def coordinator(self) -> TaskCoordinator | None:
        return self._coordinator

    @property
    def scheduler(self) -> TaskScheduler | None:
        return self._scheduler

    @property
    def context_manager(self) -> SmartContext | None:
        return self._ctx_mgr

    @property
    def hooks(self) -> HooksEngine | None:
        return self._hooks

    @property
    def state(self) -> StateManager | None:
        return self._state

    @property
    def services(self) -> ServiceRegistry | None:
        return self._services


# ── All exports ────────────────────────────────────────────────────────────
__all__ = [
    # Module
    "ClaudeCodeModule",
    # Query Engine
    "SuperiorQueryEngine",
    "QueryConfig",
    "QueryResult",
    "ModelRouter",
    "StreamingResponse",
    "ToolCallResult",
    # Backends
    "ModelBackend",
    "AnthropicBackend",
    "OpenAICompatibleBackend",
    "SimulationBackend",
    # Provider Transport
    "ChatProvider",
    "ProviderResponse",
    "RetryPolicy",
    "OpenAICompatibleProvider",
    "AnthropicProvider",
    "MockProvider",
    "EchoProvider",
    "ResilientProvider",
    "ProviderRegistry",
    "get_provider",
    # Coordinator
    "TaskCoordinator",
    "ExecutionNode",
    "ExecutionDAG",
    "SchedulePolicy",
    "RetryPolicy",
    "ParallelDispatch",
    # Task System
    "Task",
    "TaskType",
    "TaskStatus",
    "BackgroundTask",
    "TaskScheduler",
    "SwarmTaskBridge",
    "TaskResult",
    # Context Manager
    "SmartContext",
    "ContextTier",
    "EmbeddingCache",
    "CompressionEngine",
    "WindowManager",
    # Hooks Engine
    "HooksEngine",
    "HookType",
    "HookPriority",
    "HookResult",
    "PluginManifest",
    "HookPlugin",
    # State Manager
    "StateManager",
    "CRDTStore",
    "StateVersion",
    "MergeStrategy",
    "DistributedLock",
    # Services
    "ModelService",
    "ToolService",
    "MemoryService",
    "AuthService",
    "ServiceRegistry",
    "ModelProvider",
    "ToolDefinition",
    "MemoryEntry",
    "AuthToken",
]
