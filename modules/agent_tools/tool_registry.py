"""
ToolRegistry — Central registry for all Claude Code tools.

Provides discovery, registration, permission gating, metrics collection,
progress reporting, cancellation, and execution lifecycle management for
25+ enterprise-grade async Pydantic-based tools.

Key features:
  - Register/unregister tools with Pydantic schema validation
  - Permission gating (allow/deny by tool, category, or pattern)
  - Async execution with cancellation via asyncio.Task
  - Streaming progress via AsyncIterator[ProgressEvent]
  - Comprehensive metrics (duration, success/failure, bytes processed)
  - ENI Compression bridge auto-compression on all outputs
  - Health-check all tools with a single call
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import logging
import threading
import time
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from pathlib import Path
from typing import (
    Any, AsyncIterator, Awaitable, Callable, ClassVar, Dict,
    Generic, List, Optional, Set, Tuple, Type, TypeVar, Union,
)

from pydantic import BaseModel, ConfigDict, Field, ValidationError

# ── Master-class tool gate + audit ─────────────────────────────────────────
try:
    from .gate import ToolGate, ToolPolicy, ToolAudit, Decision, GateResult
except ImportError:  # pragma: no cover - fallback for loose-import environments
    from agent_tools.gate import ToolGate, ToolPolicy, ToolAudit, Decision, GateResult

# ── Platform imports ───────────────────────────────────────────────────────
try:
    from enterprise.platform_kernel import EventBus, Event, EventPriority, HealthStatus
except ImportError:
    import sys as _sys, os as _os
    _enterprise_dir = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    _parent = _os.path.dirname(_enterprise_dir)
    if _parent not in _sys.path:
        _sys.path.insert(0, _parent)
    from enterprise.platform_kernel import EventBus, Event, EventPriority, HealthStatus

# ── ENI Compression bridge (auto-compress all outputs) ─────────────────────
try:
    from enterprise.modules.compression_bridge.compression_bridge import CompressionBridge
    _COMPRESSION_AVAILABLE = True
except ImportError:
    try:
        from compression_bridge.compression_bridge import CompressionBridge
        _COMPRESSION_AVAILABLE = True
    except ImportError:
        _COMPRESSION_AVAILABLE = False

_log = logging.getLogger("enterprise.agent_tools.registry")

# ============================================================================
# Progress Event — streaming progress reporting
# ============================================================================


class ProgressStatus(str, Enum):
    """Progress status for streaming tool execution."""
    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    STREAMING = "streaming"
    COMPRESSING = "compressing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class ProgressEvent:
    """Progress event emitted during tool execution.

    Attributes:
        tool_name: Name of the tool being executed.
        status: Current progress status.
        message: Human-readable progress message.
        percent: Optional completion percentage (0.0-100.0).
        bytes_processed: Optional bytes processed so far.
        metadata: Arbitrary additional data.
        timestamp: UTC timestamp of this event.
        execution_id: Unique ID for this execution.
    """
    tool_name: str
    status: ProgressStatus
    message: str
    percent: Optional[float] = None
    bytes_processed: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))


# ============================================================================
# Tool Permission System
# ============================================================================


class PermissionLevel(Enum):
    """Permission levels for tool access."""
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"  # Prompt user for confirmation


@dataclass
class ToolPermission:
    """Permission rule for a tool or category of tools.

    Attributes:
        tool_name: Exact tool name, or '*' for all tools.
        category: Tool category (e.g., 'file', 'web', 'system').
        level: Permission level for matching tools.
        pattern: Optional glob pattern for resource-level permissions.
    """
    tool_name: str = "*"
    category: Optional[str] = None
    level: PermissionLevel = PermissionLevel.ALLOW
    pattern: Optional[str] = None

    def matches(self, tool_name: str, category: Optional[str] = None) -> bool:
        """Check if this permission rule matches a tool invocation."""
        if self.tool_name != "*" and self.tool_name != tool_name:
            return False
        if self.category is not None and category != self.category:
            return False
        return True


class PermissionGate:
    """Permission gate that evaluates access rules for tool execution.

    Supports layered rules: default policy + per-tool overrides + pattern matching.
    Deny rules take precedence over allow rules.

    Usage::
        gate = PermissionGate(default_level=PermissionLevel.ALLOW)
        gate.deny("BashTool")
        gate.allow("FileReadTool", pattern="*.py")
        result = gate.check("BashTool", "system")
    """

    def __init__(
        self,
        default_level: PermissionLevel = PermissionLevel.ALLOW,
        rules: Optional[List[ToolPermission]] = None,
    ) -> None:
        self._default_level = default_level
        self._rules: List[ToolPermission] = rules or []
        self._lock = threading.RLock()

    def add_rule(self, rule: ToolPermission) -> None:
        """Add a permission rule."""
        with self._lock:
            self._rules.append(rule)

    def allow(
        self,
        tool_name: str = "*",
        category: Optional[str] = None,
        pattern: Optional[str] = None,
    ) -> None:
        """Add an allow rule."""
        self.add_rule(ToolPermission(
            tool_name=tool_name,
            category=category,
            level=PermissionLevel.ALLOW,
            pattern=pattern,
        ))

    def deny(
        self,
        tool_name: str = "*",
        category: Optional[str] = None,
        pattern: Optional[str] = None,
    ) -> None:
        """Add a deny rule."""
        self.add_rule(ToolPermission(
            tool_name=tool_name,
            category=category,
            level=PermissionLevel.DENY,
            pattern=pattern,
        ))

    def check(self, tool_name: str, category: Optional[str] = None) -> PermissionLevel:
        """Evaluate permission for a tool invocation. Deny wins over allow."""
        with self._lock:
            result = self._default_level
            for rule in self._rules:
                if rule.matches(tool_name, category):
                    if rule.level == PermissionLevel.DENY:
                        return PermissionLevel.DENY
                    result = rule.level
            return result

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "default": self._default_level.value,
                "rules": [
                    {
                        "tool": r.tool_name,
                        "category": r.category,
                        "level": r.level.value,
                        "pattern": r.pattern,
                    }
                    for r in self._rules
                ],
            }


# ============================================================================
# Tool Metrics
# ============================================================================


@dataclass
class ToolMetrics:
    """Aggregated metrics for a single tool.

    Attributes:
        tool_name: Name of the tool.
        invocations: Total invocation count.
        successes: Successful invocations.
        failures: Failed invocations.
        cancellations: Cancelled invocations.
        total_duration_ms: Cumulative execution time in milliseconds.
        total_bytes_input: Total bytes of input processed.
        total_bytes_output: Total bytes of output produced.
        total_bytes_compressed: Total bytes after ENI compression.
        last_invoked_at: Timestamp of last invocation.
        last_error: Last error message if any.
    """
    tool_name: str
    invocations: int = 0
    successes: int = 0
    failures: int = 0
    cancellations: int = 0
    total_duration_ms: float = 0.0
    total_bytes_input: int = 0
    total_bytes_output: int = 0
    total_bytes_compressed: int = 0
    last_invoked_at: Optional[datetime] = None
    last_error: Optional[str] = None

    @property
    def success_rate(self) -> float:
        if self.invocations == 0:
            return 1.0
        return self.successes / self.invocations

    @property
    def avg_duration_ms(self) -> float:
        if self.invocations == 0:
            return 0.0
        return self.total_duration_ms / self.invocations

    @property
    def compression_ratio(self) -> float:
        if self.total_bytes_output == 0:
            return 0.0
        return 1.0 - (self.total_bytes_compressed / self.total_bytes_output)

    def record_success(self, duration_ms: float, bytes_in: int = 0,
                       bytes_out: int = 0, bytes_compressed: int = 0) -> None:
        self.invocations += 1
        self.successes += 1
        self.total_duration_ms += duration_ms
        self.total_bytes_input += bytes_in
        self.total_bytes_output += bytes_out
        self.total_bytes_compressed += bytes_compressed
        self.last_invoked_at = datetime.now(timezone.utc)

    def record_failure(self, duration_ms: float, error: str = "") -> None:
        self.invocations += 1
        self.failures += 1
        self.total_duration_ms += duration_ms
        self.last_invoked_at = datetime.now(timezone.utc)
        self.last_error = error

    def record_cancellation(self) -> None:
        self.invocations += 1
        self.cancellations += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "invocations": self.invocations,
            "successes": self.successes,
            "failures": self.failures,
            "cancellations": self.cancellations,
            "success_rate": round(self.success_rate, 4),
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "total_bytes_input": self.total_bytes_input,
            "total_bytes_output": self.total_bytes_output,
            "total_bytes_compressed": self.total_bytes_compressed,
            "compression_ratio": round(self.compression_ratio, 4),
            "last_invoked_at": (
                self.last_invoked_at.isoformat() if self.last_invoked_at else None
            ),
            "last_error": self.last_error,
        }


# ============================================================================
# Base Tool — abstract base for all tools
# ============================================================================

# Pydantic models for tool schemas
TParams = TypeVar("TParams", bound=BaseModel)
TResult = TypeVar("TResult", bound=BaseModel)


class BaseTool(ABC, Generic[TParams, TResult]):
    """Abstract base for all Claude Code tools.

    Every tool must define:
      - name: Unique tool name string
      - description: Human-readable description
      - category: Tool category (system, file, web, agent, mcp_lsp, specialty, meta)
      - parameters_schema: Pydantic model for input validation
      - result_schema: Pydantic model for output validation

    Tools implement:
      - execute(params, context): Core execution logic (must be async)
      - execute_streaming(params, context): Optional streaming execution

    Built-in features:
      - Permission gating via PermissionGate
      - Progress reporting via ProgressEvent emitter
      - Cancellation via asyncio.Task cancellation
      - Metrics collection
      - ENI Compression auto-compression on outputs
    """

    # ── Tool metadata ──────────────────────────────────────────────────
    name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    category: ClassVar[str] = "misc"
    version: ClassVar[str] = "1.0.0"
    parameters_schema: ClassVar[Type[BaseModel]]
    result_schema: ClassVar[Type[BaseModel]]

    def __init__(self) -> None:
        self._metrics = ToolMetrics(tool_name=self.name)
        self._cancelled = False
        self._event_bus: Optional[EventBus] = None

        # Initialize ENI Compression bridge
        self._compression: Any = None
        if _COMPRESSION_AVAILABLE:
            try:
                self._compression = CompressionBridge()
            except Exception:
                _log.debug("Compression bridge unavailable for %s", self.name)

    @property
    def metrics(self) -> ToolMetrics:
        return self._metrics

    def set_event_bus(self, bus: EventBus) -> None:
        self._event_bus = bus

    def cancel(self) -> None:
        """Request cancellation of the current execution."""
        self._cancelled = True

    def reset_cancellation(self) -> None:
        """Reset the cancellation flag before a new execution."""
        self._cancelled = False

    def check_cancelled(self) -> None:
        """Raise if execution has been cancelled."""
        if self._cancelled:
            raise asyncio.CancelledError(f"Tool {self.name} execution cancelled")

    @abstractmethod
    async def execute(
        self,
        params: TParams,
        context: Optional[ToolExecutionContext] = None,
    ) -> TResult:
        """Execute the tool with the given parameters.

        Args:
            params: Validated input parameters (Pydantic model).
            context: Optional execution context (permissions, callbacks, etc.).

        Returns:
            Tool result (Pydantic model).

        Must call self.check_cancelled() periodically for long-running operations.
        """
        ...

    async def execute_streaming(
        self,
        params: TParams,
        context: Optional[ToolExecutionContext] = None,
    ) -> AsyncIterator[Union[ProgressEvent, TResult]]:
        """Execute with streaming progress updates.

        Default implementation wraps execute() with start/complete progress events.
        Override for true streaming (e.g., BashTool streams stdout line-by-line).

        Yields:
            ProgressEvent for progress updates, then final TResult.
        """
        exec_id = str(uuid.uuid4())
        yield ProgressEvent(
            tool_name=self.name,
            status=ProgressStatus.STARTING,
            message=f"Starting {self.name}",
            execution_id=exec_id,
        )

        try:
            result = await self.execute(params, context)
            yield ProgressEvent(
                tool_name=self.name,
                status=ProgressStatus.COMPLETED,
                message=f"Completed {self.name}",
                percent=100.0,
                execution_id=exec_id,
            )
            yield result
        except asyncio.CancelledError:
            yield ProgressEvent(
                tool_name=self.name,
                status=ProgressStatus.CANCELLED,
                message=f"Cancelled {self.name}",
                execution_id=exec_id,
            )
            raise
        except Exception as exc:
            yield ProgressEvent(
                tool_name=self.name,
                status=ProgressStatus.FAILED,
                message=str(exc),
                execution_id=exec_id,
            )
            raise

    def validate_params(self, raw_params: Dict[str, Any]) -> TParams:
        """Validate raw parameters against the tool's schema."""
        return self.parameters_schema(**raw_params)

    async def compress_output(self, data: bytes) -> Tuple[bytes, float]:
        """Auto-compress output using ENI Compression bridge.

        Returns:
            Tuple of (compressed_data, compression_ratio).
        """
        if self._compression is None:
            return data, 0.0
        try:
            result = self._compression.compress(data)
            ratio = 1.0 - (result.compressed_size / result.original_size) if result.original_size > 0 else 0.0
            return result.data, ratio
        except Exception:
            return data, 0.0

    def _emit_event(self, topic: str, payload: Dict[str, Any]) -> None:
        """Emit an event on the EventBus if wired."""
        if self._event_bus is not None:
            try:
                evt = Event.create(
                    topic=topic,
                    source=self.name,
                    payload=payload,
                )
                self._event_bus.publish(evt)
            except Exception:
                _log.debug("Failed to emit event %s for %s", topic, self.name)


# ============================================================================
# Execution Context
# ============================================================================


@dataclass
class ToolExecutionContext:
    """Execution context passed to tools during invocation.

    Attributes:
        user_id: Authenticated user/agent ID.
        session_id: Unique session identifier.
        permissions: Permission gate to evaluate access.
        timeout_seconds: Maximum execution time before cancellation.
        max_output_bytes: Maximum output size before truncation.
        compress_output: Whether to auto-compress outputs via ENI.
        metadata: Arbitrary additional context.
    """
    user_id: str = "anonymous"
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    permissions: Optional[PermissionGate] = None
    timeout_seconds: float = 300.0
    max_output_bytes: int = 10 * 1024 * 1024  # 10 MB
    compress_output: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# Tool Registry
# ============================================================================


class ToolRegistry:
    """Central registry for discovering, registering, and executing tools.

    Manages the full lifecycle:
      1. Register tools with their schemas and metadata
      2. Gate execution through permission rules
      3. Execute tools with progress reporting, cancellation, and metrics
      4. Auto-compress outputs via ENI Compression bridge

    Usage::
        registry = ToolRegistry()
        registry.register(BashTool())
        result = await registry.invoke("BashTool", {"command": "ls -la"})
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        cfg = config or {}
        self._config = cfg
        self._event_bus = event_bus
        self._lock = threading.RLock()
        self._tools: Dict[str, BaseTool] = {}
        self._tool_categories: Dict[str, str] = {}  # name -> category
        self._permission_gate = PermissionGate(
            default_level=PermissionLevel(cfg.get("default_permission", "allow"))
        )

        # ── Master-class tool gate + audit (declarative policy sandbox) ──
        # Default: a permissive policy (allow everything) + a live audit log.
        # Config may supply {"tool_gate": {"policy": {...}}} to restrict tools.
        self._tool_audit = ToolAudit()
        try:
            gate_cfg = cfg.get("tool_gate") or cfg.get("gate") or {}
            if gate_cfg and gate_cfg.get("policy"):
                self._tool_gate: ToolGate = ToolGate.from_config(
                    {"policy": gate_cfg.get("policy", {})}
                )
            else:
                self._tool_gate = ToolGate(audit=self._tool_audit)
        except Exception:
            _log.debug("Tool gate disabled; defaulting to permissive gate", exc_info=True)
            self._tool_gate = ToolGate(audit=self._tool_audit)
        self._active_executions: Dict[str, asyncio.Task] = {}
        self._total_invocations: int = 0
        self._started_at: datetime = datetime.now(timezone.utc)

        # Initialize compression bridge for registry-level compression
        self._compression: Any = None
        if _COMPRESSION_AVAILABLE:
            try:
                self._compression = CompressionBridge()
            except Exception:
                _log.debug("Registry-level compression bridge unavailable")

    # ── Registration ────────────────────────────────────────────────────

    def register(self, tool: BaseTool) -> None:
        """Register a single tool."""
        with self._lock:
            if tool.name in self._tools:
                _log.warning("Re-registering tool %s", tool.name)
            self._tools[tool.name] = tool
            self._tool_categories[tool.name] = tool.category
            if self._event_bus:
                tool.set_event_bus(self._event_bus)
            _log.info("Registered tool: %s (category: %s)", tool.name, tool.category)

    async def register_all(self, tools: List[BaseTool]) -> None:
        """Register multiple tools."""
        for tool in tools:
            self.register(tool)
        _log.info("Registered %d tools total", len(self._tools))

    def unregister(self, tool_name: str) -> None:
        """Remove a tool from the registry."""
        with self._lock:
            self._tools.pop(tool_name, None)
            self._tool_categories.pop(tool_name, None)

    def get(self, tool_name: str) -> Optional[BaseTool]:
        """Get a registered tool by name."""
        return self._tools.get(tool_name)

    def list_tools(self) -> List[Dict[str, Any]]:
        """List all registered tools with metadata."""
        with self._lock:
            return [
                {
                    "name": name,
                    "description": tool.description,
                    "category": tool.category,
                    "version": tool.version,
                    "parameters_schema": tool.parameters_schema.model_json_schema(),
                    "metrics": tool.metrics.to_dict(),
                }
                for name, tool in sorted(self._tools.items())
            ]

    def list_categories(self) -> Dict[str, List[str]]:
        """List tools grouped by category."""
        grouped: Dict[str, List[str]] = defaultdict(list)
        for name, cat in self._tool_categories.items():
            grouped[cat].append(name)
        return dict(grouped)

    # ── Permission Management ───────────────────────────────────────────

    def set_permission_gate(self, gate: PermissionGate) -> None:
        """Replace the permission gate."""
        with self._lock:
            self._permission_gate = gate

    def allow_tool(self, tool_name: str) -> None:
        """Allow a specific tool."""
        self._permission_gate.allow(tool_name=tool_name)

    def deny_tool(self, tool_name: str) -> None:
        """Deny a specific tool."""
        self._permission_gate.deny(tool_name=tool_name)

    def check_permission(self, tool_name: str) -> PermissionLevel:
        """Check if a tool is permitted for execution."""
        category = self._tool_categories.get(tool_name)
        return self._permission_gate.check(tool_name, category)

    # ── Master-class Tool Gate & Audit access ───────────────────────────

    def set_tool_gate(self, gate: ToolGate) -> None:
        """Replace the master-class tool gate (policy sandbox)."""
        with self._lock:
            self._tool_gate = gate

    def get_tool_gate(self) -> ToolGate:
        """Access the active tool gate (policy sandbox)."""
        return self._tool_gate

    def get_tool_audit(self) -> ToolAudit:
        """Access the append-only tool audit log."""
        return self._tool_audit

    def tool_gate_decision(self, tool_name: str, params: Dict[str, Any]) -> GateResult:
        """Evaluate the tool gate policy for a call without executing it."""
        return self._tool_gate.evaluate(tool_name, params)

    # ── Execution ───────────────────────────────────────────────────────

    async def invoke(
        self,
        tool_name: str,
        params: Dict[str, Any],
        context: Optional[ToolExecutionContext] = None,
    ) -> Any:
        """Invoke a tool by name with parameters.

        Args:
            tool_name: Name of the registered tool.
            params: Raw parameter dict (will be validated against schema).
            context: Optional execution context.

        Returns:
            Tool result (Pydantic model instance).

        Raises:
            ValueError: Tool not found.
            PermissionError: Tool is denied by permission gate.
            ValidationError: Parameters fail schema validation.
            asyncio.TimeoutError: Execution exceeds timeout.
            asyncio.CancelledError: Execution was cancelled.
        """
        ctx = context or ToolExecutionContext()

        # 1. Lookup
        tool = self.get(tool_name)
        if tool is None:
            raise ValueError(f"Tool not found: {tool_name}")

        # 2. Permission check
        perm = self.check_permission(tool_name)
        if perm == PermissionLevel.DENY:
            tool._emit_event("tool.permission.denied", {
                "tool_name": tool_name,
                "user_id": ctx.user_id,
            })
            raise PermissionError(f"Tool {tool_name} is denied by permission gate")

        # 2b. Master-class tool gate (policy sandbox) + audit
        g_res = self._tool_gate.evaluate(tool_name, params)
        if g_res.decision == Decision.DENY:
            self._tool_audit.record(
                tool_name, params, allowed=False, decision=Decision.DENY,
                outcome="blocked", caller=ctx.user_id, reason=g_res.reason,
            )
            raise PermissionError(
                f"Tool {tool_name} blocked by policy: {g_res.reason}"
            )
        if g_res.decision == Decision.ASK:
            self._tool_audit.record(
                tool_name, params, allowed=False, decision=Decision.ASK,
                outcome="pending", caller=ctx.user_id, reason=g_res.reason,
            )
            raise PermissionError(
                f"Tool {tool_name} requires human approval: {g_res.reason}"
            )

        # 3. Validate parameters
        try:
            validated = tool.validate_params(params)
        except ValidationError as e:
            tool._emit_event("tool.execution.failed", {
                "tool_name": tool_name,
                "error": "validation_error",
                "details": str(e),
            })
            raise

        # 4. Reset cancellation, wire event bus
        tool.reset_cancellation()

        # 5. Execute with timeout
        tool._emit_event("tool.execution.started", {
            "tool_name": tool_name,
            "user_id": ctx.user_id,
            "session_id": ctx.session_id,
        })

        start = time.perf_counter()
        exec_id = str(uuid.uuid4())

        try:
            # Create task for cancellation support
            task = asyncio.ensure_future(tool.execute(validated, ctx))
            self._active_executions[exec_id] = task

            try:
                result = await asyncio.wait_for(task, timeout=ctx.timeout_seconds)
            except asyncio.TimeoutError:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                tool.metrics.record_failure(
                    (time.perf_counter() - start) * 1000,
                    error="timeout",
                )
                tool._emit_event("tool.execution.failed", {
                    "tool_name": tool_name,
                    "error": "timeout",
                    "duration_ms": (time.perf_counter() - start) * 1000,
                })
                raise asyncio.TimeoutError(
                    f"Tool {tool_name} exceeded timeout of {ctx.timeout_seconds}s"
                )

            # 6. Auto-compress output if applicable
            elapsed_ms = (time.perf_counter() - start) * 1000
            bytes_out = 0
            bytes_compressed = 0

            if ctx.compress_output and hasattr(result, 'model_dump_json'):
                raw_json = result.model_dump_json().encode()
                bytes_out = len(raw_json)
                compressed, ratio = await tool.compress_output(raw_json)
                bytes_compressed = len(compressed)

            tool.metrics.record_success(
                elapsed_ms,
                bytes_out=bytes_out,
                bytes_compressed=bytes_compressed
            )

            tool._emit_event("tool.execution.completed", {
                "tool_name": tool_name,
                "duration_ms": elapsed_ms,
                "bytes_out": bytes_out,
                "bytes_compressed": bytes_compressed,
            })

            # Master-class audit: record successful execution
            self._tool_audit.record(
                tool_name, params, allowed=True, decision=Decision.ALLOW,
                outcome="success", duration_ms=elapsed_ms,
                caller=ctx.user_id, reason="allowed",
            )

            self._total_invocations += 1
            return result

        except asyncio.CancelledError:
            tool.metrics.record_cancellation()
            tool._emit_event("tool.execution.failed", {
                "tool_name": tool_name,
                "error": "cancelled",
            })
            raise

        except (ValidationError, PermissionError):
            raise

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            tool.metrics.record_failure(elapsed_ms, error=str(exc))
            tool._emit_event("tool.execution.failed", {
                "tool_name": tool_name,
                "error": str(exc),
                "duration_ms": elapsed_ms,
            })
            # Master-class audit: record execution error
            self._tool_audit.record(
                tool_name, params, allowed=True, decision=Decision.ALLOW,
                outcome="error", duration_ms=elapsed_ms,
                caller=ctx.user_id, reason="allowed", error=str(exc),
            )
            self._total_invocations += 1
            raise

        finally:
            self._active_executions.pop(exec_id, None)

    async def invoke_streaming(
        self,
        tool_name: str,
        params: Dict[str, Any],
        context: Optional[ToolExecutionContext] = None,
    ) -> AsyncIterator[Union[ProgressEvent, Any]]:
        """Invoke a tool with streaming progress updates.

        Yields ProgressEvent updates, then the final result.
        """
        ctx = context or ToolExecutionContext()
        tool = self.get(tool_name)
        if tool is None:
            raise ValueError(f"Tool not found: {tool_name}")

        perm = self.check_permission(tool_name)
        if perm == PermissionLevel.DENY:
            raise PermissionError(f"Tool {tool_name} is denied by permission gate")

        validated = tool.validate_params(params)
        tool.reset_cancellation()

        exec_id = str(uuid.uuid4())
        task = asyncio.ensure_future(
            self._consume_stream(tool, validated, ctx, exec_id)
        )
        self._active_executions[exec_id] = task

        try:
            async for item in tool.execute_streaming(validated, ctx):
                yield item
        finally:
            self._active_executions.pop(exec_id, None)

    async def _consume_stream(
        self,
        tool: BaseTool,
        params: BaseModel,
        ctx: ToolExecutionContext,
        exec_id: str,
    ) -> None:
        """Background consumer for streaming execution."""
        try:
            async for _ in tool.execute_streaming(params, ctx):
                pass
        except Exception:
            pass

    def cancel_execution(self, exec_id: str) -> bool:
        """Cancel an in-flight execution by its execution ID."""
        task = self._active_executions.get(exec_id)
        if task and not task.done():
            task.cancel()
            return True
        return False

    def cancel_all(self) -> int:
        """Cancel all in-flight executions. Returns count cancelled."""
        count = 0
        for task in list(self._active_executions.values()):
            if not task.done():
                task.cancel()
                count += 1
        return count

    # ── Health & Stats ──────────────────────────────────────────────────

    def health_check(self) -> Dict[str, Any]:
        """Perform a health check on all registered tools."""
        with self._lock:
            tool_count = len(self._tools)
            healthy = tool_count >= 1
            return {
                "healthy": healthy,
                "total_tools": tool_count,
                "categories": len(self._tool_categories),
                "tools": sorted(self._tools.keys()),
                "uptime_seconds": (
                    datetime.now(timezone.utc) - self._started_at
                ).total_seconds(),
                "total_invocations": self._total_invocations,
            }

    def get_metrics(self) -> Dict[str, Any]:
        """Get aggregated metrics for all tools."""
        with self._lock:
            tool_metrics = {
                name: tool.metrics.to_dict()
                for name, tool in self._tools.items()
            }
            return {
                "total_tools": len(self._tools),
                "total_invocations": self._total_invocations,
                "tools": tool_metrics,
                "permissions": self._permission_gate.to_dict(),
                "active_executions": len(self._active_executions),
                "uptime_seconds": (
                    datetime.now(timezone.utc) - self._started_at
                ).total_seconds(),
            }

    async def shutdown(self) -> None:
        """Gracefully shut down: cancel all executions, clear registry."""
        _log.info("Shutting down ToolRegistry with %d tools", len(self._tools))
        self.cancel_all()
        # Give a moment for cancellations to propagate
        await asyncio.sleep(0.1)
        with self._lock:
            self._tools.clear()
            self._tool_categories.clear()
            self._active_executions.clear()
        _log.info("ToolRegistry shut down")

    # ── Properties ──────────────────────────────────────────────────────

    @property
    def tool_count(self) -> int:
        return len(self._tools)

    @property
    def total_invocations(self) -> int:
        return self._total_invocations