"""
ENI Enterprise Log Aggregator — Centralized Log Collection
============================================================
Provides centralized log collection with structured output, correlation
ID tracking, module attribution, and multiple output sinks (console, file,
JSON, syslog). Integrates with the Platform Kernel's LoggingBridge for
unified log management across all 20 enterprise modules.

Architecture:
    LogLevel             — Standard logging levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    LogEntry             — Structured log record with module, correlation, trace context
    LogAggregationConfig — Configuration for log routing, filtering, retention
    LogAggregator        — Central collector: ingests, routes, filters, and exports logs

Features:
    - Structured JSON output for machine consumption
    - Correlation ID propagation for distributed tracing
    - Module attribution (which of the 20 modules produced the log)
    - Configurable output sinks: console, file (rotating), syslog, in-memory buffer
    - Log level filtering per module
    - Rate limiting to prevent log storms
    - In-memory ring buffer for recent log queries
    - EventBus integration: publishes log entries as events for real-time dashboards
    - Integration with Platform Kernel LoggingBridge

Integration:
    - Platform Kernel LoggingBridge (platform_kernel.py)
    - EventBus for log event streaming
    - MetricsCollector for log volume metrics
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, ClassVar, Dict, List, Optional, TextIO, Tuple

# =============================================================================
# Enums
# =============================================================================


class LogLevel(Enum):
    """Standard log levels with numeric severity."""
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50

    @classmethod
    def from_string(cls, value: str) -> "LogLevel":
        """Parse log level from case-insensitive string."""
        try:
            return cls[value.upper()]
        except KeyError:
            return cls.INFO

    def to_python_level(self) -> int:
        """Convert to Python logging level integer."""
        return self.value


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class LogEntry:
    """A single structured log entry.

    Attributes:
        entry_id: Unique log entry identifier.
        timestamp: UTC timestamp when the log was created.
        level: Log severity level.
        module: Source module name (or "platform" for kernel logs).
        message: Log message text.
        correlation_id: Correlation ID for request/transaction tracing.
        causation_id: Causation ID for event-sourced tracing.
        trace_context: Distributed tracing context (trace_id, span_id).
        logger_name: Python logger name.
        function: Function name where the log was emitted.
        file_path: Source file path.
        line_number: Source line number.
        exception: Exception string if present.
        traceback: Full traceback string if present.
        extra: Additional key-value metadata.
    """

    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    level: LogLevel = LogLevel.INFO
    module: str = "platform"
    message: str = ""
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    trace_context: Dict[str, str] = field(default_factory=dict)
    logger_name: str = ""
    function: str = ""
    file_path: str = ""
    line_number: int = 0
    exception: Optional[str] = None
    traceback: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp.isoformat(),
            "level": self.level.name,
            "module": self.module,
            "message": self.message,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "trace_context": self.trace_context,
            "logger_name": self.logger_name,
            "function": self.function,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "exception": self.exception,
            "traceback": self.traceback,
            "extra": self.extra,
        }

    def to_json(self) -> str:
        """Serialize to a JSON string."""
        return json.dumps(self.to_dict(), default=str)

    def to_text(self) -> str:
        """Format as a human-readable text line."""
        extra_str = " ".join(f"{k}={v}" for k, v in self.extra.items()) if self.extra else ""
        return (
            f"{self.timestamp.isoformat()} [{self.level.name:8s}] "
            f"{self.module:25s} | {self.message}"
            + (f" | {extra_str}" if extra_str else "")
            + (f"  corr={self.correlation_id}" if self.correlation_id else "")
        )

    def to_syslog(self) -> str:
        """Format as a syslog-compatible line."""
        facility = 1  # user-level
        severity_map = {
            LogLevel.DEBUG: 7,
            LogLevel.INFO: 6,
            LogLevel.WARNING: 4,
            LogLevel.ERROR: 3,
            LogLevel.CRITICAL: 2,
        }
        pri = facility * 8 + severity_map.get(self.level, 6)
        hostname = os.uname().nodename if hasattr(os, 'uname') else "eni"
        return f"<{pri}>{self.timestamp.strftime('%b %d %H:%M:%S')} {hostname} eni[{self.module}]: {self.message}"


@dataclass
class LogAggregationConfig:
    """Configuration for the log aggregator.

    Attributes:
        enabled: Whether log aggregation is active.
        min_level: Minimum log level to capture.
        per_module_levels: Per-module log level overrides.
        outputs: List of output sink configurations.
        history_buffer_size: Max entries in in-memory ring buffer.
        rate_limit_per_sec: Maximum log entries per second (0 = unlimited).
        rate_limit_burst: Burst size for rate limiting.
        publish_to_event_bus: Whether to publish log entries to EventBus.
        correlation_id_header: HTTP header name for correlation ID extraction.
        include_traceback: Whether to capture full tracebacks.
    """

    enabled: bool = True
    min_level: LogLevel = LogLevel.INFO
    per_module_levels: Dict[str, LogLevel] = field(default_factory=dict)
    outputs: List[Dict[str, Any]] = field(default_factory=lambda: [
        {"type": "console", "format": "text", "level": "INFO"},
    ])
    history_buffer_size: int = 10000
    rate_limit_per_sec: float = 0.0  # 0 = unlimited
    rate_limit_burst: int = 1000
    publish_to_event_bus: bool = True
    correlation_id_header: str = "X-Correlation-ID"
    include_traceback: bool = True


# =============================================================================
# Log Aggregator
# =============================================================================


class LogAggregator:
    """Centralized log collection for the ENI Enterprise Platform.

    Ingests logs from all 20 modules, routes them through configured
    output sinks, maintains an in-memory ring buffer for recent queries,
    and optionally publishes log entries to the EventBus for real-time
    dashboard streaming.

    Usage::

        aggregator = LogAggregator(config=LogAggregationConfig())
        aggregator.start()

        entry = LogEntry(
            level=LogLevel.ERROR,
            module="safety_governance",
            message="Guardrail check failed",
            correlation_id="corr-123",
        )
        aggregator.ingest(entry)

        # Query recent logs
        recent = aggregator.query(module="safety_governance", level=LogLevel.ERROR)

        # Export to file
        aggregator.export_json("logs/platform_export.json")

        aggregator.stop()
    """

    # Default log level mapping to Python logging levels
    PYTHON_LEVEL_MAP: ClassVar[Dict[LogLevel, int]] = {
        LogLevel.DEBUG: logging.DEBUG,
        LogLevel.INFO: logging.INFO,
        LogLevel.WARNING: logging.WARNING,
        LogLevel.ERROR: logging.ERROR,
        LogLevel.CRITICAL: logging.CRITICAL,
    }

    def __init__(
        self,
        config: Optional[LogAggregationConfig] = None,
        event_bus: Optional[Any] = None,
        kernel_logging_bridge: Optional[Any] = None,
    ) -> None:
        """Initialize the LogAggregator.

        Args:
            config: Log aggregation configuration.
            event_bus: Platform EventBus for publishing log events.
            kernel_logging_bridge: Platform Kernel LoggingBridge for integration.
        """
        self._config: LogAggregationConfig = config or LogAggregationConfig()
        self._event_bus = event_bus
        self._kernel_logging_bridge = kernel_logging_bridge
        self._lock: threading.RLock = threading.RLock()

        # Output sinks
        self._sinks: List[Tuple[str, Any]] = []  # (type, handler)
        self._file_sinks: Dict[str, TextIO] = {}

        # In-memory ring buffer
        self._buffer: List[LogEntry] = []
        self._buffer_max: int = self._config.history_buffer_size

        # Statistics
        self._total_ingested: int = 0
        self._total_by_level: Dict[LogLevel, int] = defaultdict(int)
        self._total_by_module: Dict[str, int] = defaultdict(int)
        self._started_at: Optional[datetime] = None

        # Rate limiting
        self._rate_limit_window: List[float] = []  # timestamps of recent entries
        self._rate_limit_dropped: int = 0

        # Python logger integration
        self._python_loggers: Dict[str, logging.Logger] = {}

        # State
        self._started: bool = False

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the log aggregator. Opens output sinks."""
        if self._started:
            return

        self._setup_sinks()
        self._started_at = datetime.now(timezone.utc)
        self._started = True

    def stop(self) -> None:
        """Stop the log aggregator. Closes output sinks."""
        self._started = False

        with self._lock:
            for sink_type, handler in self._sinks:
                if sink_type == "file" and handler is not None:
                    try:
                        handler.close()
                    except Exception:
                        pass
            self._sinks.clear()
            self._file_sinks.clear()

    def _setup_sinks(self) -> None:
        """Initialize output sinks from configuration."""
        for output_cfg in self._config.outputs:
            sink_type = output_cfg.get("type", "console")
            if sink_type == "console":
                self._sinks.append(("console", None))
            elif sink_type == "file":
                path = output_cfg.get("path", "logs/aggregated.log")
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                try:
                    fh = open(path, "a", encoding="utf-8")
                    self._sinks.append(("file", fh))
                    self._file_sinks[path] = fh
                except OSError:
                    pass
            elif sink_type == "json_file":
                path = output_cfg.get("path", "logs/aggregated.jsonl")
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                try:
                    fh = open(path, "a", encoding="utf-8")
                    self._sinks.append(("json_file", fh))
                    self._file_sinks[path] = fh
                except OSError:
                    pass
            elif sink_type == "syslog":
                self._sinks.append(("syslog", None))
            elif sink_type == "memory":
                # Already handled by the ring buffer
                pass

    # ── Ingestion ────────────────────────────────────────────────────────────

    def ingest(self, entry: LogEntry) -> None:
        """Ingest a log entry into the aggregator.

        Applies level filtering, rate limiting, and routes to all output sinks.

        Args:
            entry: The LogEntry to ingest.
        """
        if not self._config.enabled:
            return

        # Level filtering
        if not self._should_accept(entry):
            return

        # Rate limiting
        if not self._check_rate_limit():
            self._rate_limit_dropped += 1
            return

        with self._lock:
            # Store in ring buffer
            self._buffer.append(entry)
            if len(self._buffer) > self._buffer_max:
                self._buffer = self._buffer[-self._buffer_max :]

            # Update stats
            self._total_ingested += 1
            self._total_by_level[entry.level] += 1
            self._total_by_module[entry.module] += 1

        # Route to sinks
        self._route_to_sinks(entry)

        # Publish to EventBus
        self._publish_to_event_bus(entry)

    def ingest_raw(
        self,
        level: LogLevel,
        module: str,
        message: str,
        correlation_id: Optional[str] = None,
        exception: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> LogEntry:
        """Create and ingest a log entry from raw parameters.

        Returns the created LogEntry.
        """
        entry = LogEntry(
            level=level,
            module=module,
            message=message,
            correlation_id=correlation_id,
            exception=exception,
            extra=extra or {},
        )
        self.ingest(entry)
        return entry

    def _should_accept(self, entry: LogEntry) -> bool:
        """Check if an entry should be accepted based on level filters."""
        # Per-module level override
        if entry.module in self._config.per_module_levels:
            min_level = self._config.per_module_levels[entry.module]
        else:
            min_level = self._config.min_level

        return entry.level.value >= min_level.value

    def _check_rate_limit(self) -> bool:
        """Check if the entry should be accepted under rate limiting."""
        if self._config.rate_limit_per_sec <= 0:
            return True

        now = time.time()
        window_start = now - 1.0  # 1-second sliding window

        with self._lock:
            # Trim old timestamps
            self._rate_limit_window = [
                t for t in self._rate_limit_window if t >= window_start
            ]
            if len(self._rate_limit_window) < self._config.rate_limit_burst:
                # Check per-second rate
                if len(self._rate_limit_window) < self._config.rate_limit_per_sec:
                    self._rate_limit_window.append(now)
                    return True
                return False
            return False

    # ── Sink Routing ─────────────────────────────────────────────────────────

    def _route_to_sinks(self, entry: LogEntry) -> None:
        """Route a log entry to all configured output sinks."""
        for sink_type, handler in self._sinks:
            try:
                if sink_type == "console":
                    print(entry.to_text())
                elif sink_type == "file" and handler:
                    handler.write(entry.to_text() + "\n")
                    handler.flush()
                elif sink_type == "json_file" and handler:
                    handler.write(entry.to_json() + "\n")
                    handler.flush()
                elif sink_type == "syslog":
                    # Write to syslog via Python logging
                    logger = logging.getLogger(f"eni.{entry.module}")
                    py_level = self.PYTHON_LEVEL_MAP.get(entry.level, logging.INFO)
                    logger.log(py_level, entry.to_syslog())
            except Exception:
                pass  # Sink failures must not break log ingestion

    def _publish_to_event_bus(self, entry: LogEntry) -> None:
        """Publish log entry as an event on the EventBus."""
        if not self._config.publish_to_event_bus or self._event_bus is None:
            return

        try:
            from enterprise.platform_kernel import Event

            self._event_bus.publish(
                Event.create(
                    topic=f"log.{entry.level.name.lower()}",
                    source=f"log_aggregator.{entry.module}",
                    payload={
                        "entry_id": entry.entry_id,
                        "level": entry.level.name,
                        "module": entry.module,
                        "message": entry.message,
                        "correlation_id": entry.correlation_id,
                        "timestamp": entry.timestamp.isoformat(),
                    },
                )
            )
        except Exception:
            pass

    # ── Query ────────────────────────────────────────────────────────────────

    def query(
        self,
        module: Optional[str] = None,
        level: Optional[LogLevel] = None,
        min_level: Optional[LogLevel] = None,
        correlation_id: Optional[str] = None,
        message_contains: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[LogEntry]:
        """Query the in-memory log buffer with filters.

        Args:
            module: Filter by module name.
            level: Exact level match.
            min_level: Minimum level filter.
            correlation_id: Filter by correlation ID.
            message_contains: Substring match on message.
            limit: Maximum results to return.
            offset: Number of results to skip.

        Returns:
            Filtered list of LogEntry objects (newest first).
        """
        with self._lock:
            results = list(reversed(self._buffer))

        if module:
            results = [e for e in results if e.module == module]
        if level:
            results = [e for e in results if e.level == level]
        if min_level:
            results = [e for e in results if e.level.value >= min_level.value]
        if correlation_id:
            results = [e for e in results if e.correlation_id == correlation_id]
        if message_contains:
            results = [e for e in results if message_contains.lower() in e.message.lower()]

        return results[offset : offset + limit]

    def query_json(self, **kwargs: Any) -> List[Dict[str, Any]]:
        """Query logs and return as JSON-serializable dicts."""
        entries = self.query(**kwargs)
        return [e.to_dict() for e in entries]

    def get_recent(self, limit: int = 50) -> List[LogEntry]:
        """Get the most recent log entries."""
        with self._lock:
            return list(reversed(self._buffer[-limit:]))

    # ── Export ───────────────────────────────────────────────────────────────

    def export_json(self, filepath: str, **query_kwargs: Any) -> int:
        """Export filtered log entries to a JSON Lines file.

        Args:
            filepath: Output file path.
            **query_kwargs: Query filters (module, level, etc.).

        Returns:
            Number of exported entries.
        """
        entries = self.query(**query_kwargs)
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            for entry in reversed(entries):  # Chronological order
                f.write(entry.to_json() + "\n")
        return len(entries)

    def export_text(self, filepath: str, **query_kwargs: Any) -> int:
        """Export filtered log entries to a plain text file."""
        entries = self.query(**query_kwargs)
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            for entry in reversed(entries):
                f.write(entry.to_text() + "\n")
        return len(entries)

    # ── Statistics ───────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get log aggregation statistics."""
        with self._lock:
            return {
                "total_ingested": self._total_ingested,
                "buffer_size": len(self._buffer),
                "buffer_max": self._buffer_max,
                "by_level": {k.name: v for k, v in self._total_by_level.items()},
                "by_module": dict(self._total_by_module),
                "rate_limit_dropped": self._rate_limit_dropped,
                "started_at": self._started_at.isoformat() if self._started_at else None,
                "uptime_seconds": (
                    (datetime.now(timezone.utc) - self._started_at).total_seconds()
                    if self._started_at
                    else 0.0
                ),
                "output_sinks": len(self._sinks),
            }

    # ── Python Logging Integration ───────────────────────────────────────────

    def create_module_logger(
        self,
        module_name: str,
        level: LogLevel = LogLevel.INFO,
    ) -> logging.Logger:
        """Create a Python logging.Logger that routes into the aggregator.

        Args:
            module_name: Module name for log attribution.
            level: Default log level.

        Returns:
            A configured Python Logger that feeds into the aggregator.
        """
        logger_name = f"eni.aggregated.{module_name}"

        if logger_name in self._python_loggers:
            return self._python_loggers[logger_name]

        logger = logging.getLogger(logger_name)
        logger.setLevel(self.PYTHON_LEVEL_MAP.get(level, logging.INFO))
        logger.propagate = False

        # Custom handler that ingests into the aggregator
        handler = _AggregatorHandler(self, module_name)
        logger.addHandler(handler)

        self._python_loggers[logger_name] = logger
        return logger

    def bridge_from_kernel(self) -> None:
        """Bridge log aggregation into the Platform Kernel's LoggingBridge.

        If a kernel logging bridge was provided, this configures it
        to route logs through the aggregator.
        """
        if self._kernel_logging_bridge is None:
            return

        # The kernel bridge already has structured logging;
        # we add an additional handler that feeds into our buffer.
        try:
            root_logger = self._kernel_logging_bridge._root_logger
            handler = _AggregatorHandler(self, "platform")
            root_logger.addHandler(handler)
        except Exception:
            pass

    # ── Management ───────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Reset the aggregator state (useful for testing)."""
        with self._lock:
            self._buffer.clear()
            self._total_ingested = 0
            self._total_by_level.clear()
            self._total_by_module.clear()
            self._rate_limit_window.clear()
            self._rate_limit_dropped = 0
            self._started_at = datetime.now(timezone.utc)

    def flush(self) -> None:
        """Flush all file-based output sinks."""
        for _sink_type, handler in self._sinks:
            if handler is not None and hasattr(handler, 'flush'):
                try:
                    handler.flush()
                except Exception:
                    pass

    @property
    def is_started(self) -> bool:
        """Whether the aggregator has been started."""
        return self._started

    @property
    def buffer_size(self) -> int:
        """Current number of entries in the ring buffer."""
        with self._lock:
            return len(self._buffer)

    @property
    def total_ingested(self) -> int:
        """Total log entries ingested."""
        return self._total_ingested


# =============================================================================
# Aggregator Handler (Python logging bridge)
# =============================================================================


class _AggregatorHandler(logging.Handler):
    """A Python logging.Handler that routes log records into the LogAggregator."""

    def __init__(self, aggregator: LogAggregator, module_name: str) -> None:
        super().__init__()
        self._aggregator = aggregator
        self._module_name = module_name

    def emit(self, record: logging.LogRecord) -> None:
        """Convert a Python LogRecord to a LogEntry and ingest it."""
        level_map: Dict[int, LogLevel] = {
            logging.DEBUG: LogLevel.DEBUG,
            logging.INFO: LogLevel.INFO,
            logging.WARNING: LogLevel.WARNING,
            logging.ERROR: LogLevel.ERROR,
            logging.CRITICAL: LogLevel.CRITICAL,
        }
        level = level_map.get(record.levelno, LogLevel.INFO)

        entry = LogEntry(
            timestamp=datetime.fromtimestamp(record.created, tz=timezone.utc),
            level=level,
            module=self._module_name,
            message=record.getMessage(),
            correlation_id=getattr(record, "correlation_id", None)
            or getattr(record, "module_correlation", None),
            logger_name=record.name,
            function=record.funcName,
            file_path=record.pathname,
            line_number=record.lineno,
            exception=str(record.exc_info[1]) if record.exc_info else None,
            extra=getattr(record, "extra", {}),
        )
        self._aggregator.ingest(entry)


# =============================================================================
# Factory
# =============================================================================

def create_log_aggregator(
    config: Optional[LogAggregationConfig] = None,
    event_bus: Optional[Any] = None,
    kernel_logging_bridge: Optional[Any] = None,
) -> LogAggregator:
    """Create a configured LogAggregator and start it.

    Args:
        config: Aggregation configuration.
        event_bus: Platform EventBus.
        kernel_logging_bridge: Platform Kernel LoggingBridge.

    Returns:
        A started LogAggregator instance.
    """
    aggregator = LogAggregator(
        config=config,
        event_bus=event_bus,
        kernel_logging_bridge=kernel_logging_bridge,
    )
    aggregator.start()
    return aggregator