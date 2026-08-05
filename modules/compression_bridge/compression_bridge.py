"""
CompressionBridge — Enterprise-grade bridge between the ENI Platform OS and the
core ENI Compression Engine.

Provides a unified, event-emitting, metrics-collecting, health-checked API for
all 12 compression modes plus OMEGA transcendence.

Capabilities:
    compress(data, mode)         — single compression operation
    decompress(data, mode)       — single decompression operation
    batch_compress(files)        — batch compression with progress
    get_algorithm_stats()        — per-algorithm & per-mode statistics
    omega_transcend(data)        — OMEGA mode transcendence
    health_check()               — validate all algorithms loadable, OMEGA reachable

Events:
    compression.completed         — after every compress()
    compression.omega.transcended — after every omega_transcend()
    compression.algorithm.selected— emitted when AdaptiveCompressorSelector picks a mode

Metrics:
    compression ratios per mode, throughput, omega efficiency, selector distribution
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from core.algorithms import (
    BrotliCompressor,
    ClawCompactorCompressor,
    GlyphCache,
    HeadroomCompressor,
    LLMLinguaCompressor,
    LZ4Compressor,
    PAQ8Compressor,
    PXPipeSteganography,
    WenyanEncoder,
    ZstdCompressor,
)

# ── Core ENI Compression imports ──────────────────────────────────────────
from core.engine import CompressionEngine, CompressionMode, CompressionResult
from core.selector import AdaptiveCompressorSelector

# OMEGA
try:
    from core.omega import (
        OMEGA_MODE,
        OMEGAEncoder,
        OMEGAResult,
        get_omega,
        transcend,
    )

    HAS_OMEGA = True
except ImportError:
    OMEGAEncoder = OMEGA_MODE = OMEGAResult = None  # type: ignore[assignment,misc]
    transcend = get_omega = None  # type: ignore[assignment,misc]
    HAS_OMEGA = False

# ── Platform kernel types (lightweight, avoid circular deps) ──────────────
try:
    from enterprise.platform_kernel import Event, EventBus, HealthStatus  # noqa: F401
except ImportError:
    import os as _os
    import sys as _sys

    _enterprise_dir = _os.path.dirname(
        _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    )
    _parent = _os.path.dirname(_enterprise_dir)
    if _parent not in _sys.path:
        _sys.path.insert(0, _parent)
    from enterprise.platform_kernel import Event

# ── Pluggable codec registry + ratio negotiation (stdlib, no engine dep) ───
from .codecs import (
    CodecRegistry,
    _as_bytes as _as_raw_bytes,
    _measure as _data_size,
    negotiate_ratio,
)

if TYPE_CHECKING:
    from collections.abc import Callable

# ==========================================================================
# Logger
# ==========================================================================
_log = logging.getLogger("enterprise.compression")

# ==========================================================================
# Enums
# ==========================================================================


class BridgeHealth(Enum):
    """Bridge component health states."""

    OK = "ok"
    DEGRADED = "degraded"
    FAILED = "failed"
    UNKNOWN = "unknown"


# ==========================================================================
# Dataclasses
# ==========================================================================


@dataclass
class CompressionMetric:
    """A single compression metric snapshot."""

    mode: str
    original_size: int
    compressed_size: int
    ratio: float
    algorithm: str
    duration_ms: float
    throughput_mbps: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class BridgeStats:
    """Aggregated bridge statistics."""

    total_compressions: int = 0
    total_decompressions: int = 0
    total_omega_transcendence: int = 0
    total_bytes_processed: int = 0
    total_bytes_saved: int = 0
    ratios_by_mode: dict[str, list[float]] = field(default_factory=dict)
    throughput_by_mode: dict[str, list[float]] = field(default_factory=dict)
    algorithm_counts: dict[str, int] = field(default_factory=dict)
    omega_efficiency: list[float] = field(default_factory=list)
    selector_distribution: dict[str, int] = field(default_factory=dict)
    errors: int = 0
    last_compress_at: datetime | None = None
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_compressions": self.total_compressions,
            "total_decompressions": self.total_decompressions,
            "total_omega_transcendence": self.total_omega_transcendence,
            "total_bytes_processed": self.total_bytes_processed,
            "total_bytes_saved": self.total_bytes_saved,
            "avg_ratios_by_mode": {
                m: round(sum(r) / len(r), 3) if r else 0.0 for m, r in self.ratios_by_mode.items()
            },
            "avg_throughput_by_mode": {
                m: round(sum(t) / len(t), 2) if t else 0.0
                for m, t in self.throughput_by_mode.items()
            },
            "algorithm_counts": dict(self.algorithm_counts),
            "omega_avg_efficiency": (
                round(sum(self.omega_efficiency) / len(self.omega_efficiency), 2)
                if self.omega_efficiency
                else 0.0
            ),
            "selector_distribution": dict(self.selector_distribution),
            "errors": self.errors,
            "last_compress_at": (
                self.last_compress_at.isoformat() if self.last_compress_at else None
            ),
            "last_error": self.last_error,
        }


# ==========================================================================
# Event emitter (lightweight; integrates with platform EventBus when available)
# ==========================================================================


class _EventEmitter:
    """Thin wrapper over the platform EventBus.  Falls back to log-only mode."""

    def __init__(self, bus: Any = None, source: str = "compression_bridge") -> None:
        self._bus = bus
        self._source = source
        self._handlers: dict[str, list[Callable[..., Any]]] = defaultdict(list)

    def on(self, topic: str, handler: Callable[..., Any]) -> None:
        """Register a callback handler for a topic."""
        self._handlers[topic].append(handler)

    def emit(self, topic: str, payload: dict[str, Any]) -> None:
        """Emit an event on the bus and invoke any local handlers."""
        # Local handlers
        for handler in self._handlers.get(topic, []):
            try:
                handler(payload)
            except Exception:
                _log.exception("Local handler for %s failed", topic)

        # Platform EventBus
        if self._bus is not None:
            try:
                if Event is not None:
                    evt = Event.create(
                        topic=topic,
                        source=self._source,
                        payload=payload,
                    )
                    self._bus.publish(evt)
                else:
                    _log.debug("EventBus not available, skipping publish: %s", topic)
            except Exception:
                _log.exception("Failed to publish event: %s", topic)
        else:
            _log.debug("No EventBus configured, event logged: %s payload=%s", topic, payload)


# ==========================================================================
# CompressionBridge
# ==========================================================================


class CompressionBridge:
    """Enterprise Compression Bridge — unified API for all compression operations.

    Wraps the core CompressionEngine, adding:
      - Event emission on every compression/omega/selection event
      - Metrics collection (ratios, throughput, efficiency)
      - Parallel batch compression
      - Algorithm health reporting
      - OMEGA transcendence with layer-level details
    """

    # All known algorithm classes (for health checks)
    ALGORITHM_CLASSES: ClassVar[list[type]] = [
        PAQ8Compressor,
        ZstdCompressor,
        LZ4Compressor,
        BrotliCompressor,
        LLMLinguaCompressor,
        HeadroomCompressor,
        ClawCompactorCompressor,
        WenyanEncoder,
        PXPipeSteganography,
        GlyphCache,
    ]

    # Mode → readable label
    MODE_LABELS: ClassVar[dict[CompressionMode, str]] = {
        CompressionMode.MAXIMUM: "PAQ8 - Maximum Ratio",
        CompressionMode.BALANCED: "zstd - Balanced",
        CompressionMode.FAST: "LZ4 - Fast",
        CompressionMode.ULTRA_FAST: "LZ4 - Ultra Fast",
        CompressionMode.LLM_OPTIMIZED: "LLMLingua + Headroom",
        CompressionMode.CODE_AWARE: "Claw-Compactor AST",
        CompressionMode.STEGANOGRAPHY: "PXPipe Steganography",
        CompressionMode.WENYAN: "Wenyan Encoding",
        CompressionMode.GLYPH: "Glyph Cache",
        CompressionMode.ADAPTIVE: "Adaptive ML Selector",
        CompressionMode.IMPOSSIBLE: "IMPOSSIBLE (Wenyan+PAQ8+PXPipe+Glyph)",
    }

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        event_bus: Any = None,
    ) -> None:
        """Initialise the CompressionBridge.

        Args:
            config: Optional configuration dict (carriers_dir, max_batch_workers, etc.).
            event_bus: Optional platform EventBus instance for event publishing.
        """
        cfg = config or {}
        self._config = cfg
        self._engine: CompressionEngine | None = None
        self._selector: AdaptiveCompressorSelector | None = None
        self._omega: Any = None  # OMEGAEncoder instance
        self._events = _EventEmitter(bus=event_bus, source="compression_bridge")
        self._stats = BridgeStats()
        self._lock = threading.RLock()
        self._max_batch_workers = cfg.get("max_batch_workers", 8)
        self._carriers_dir = cfg.get(
            "carriers_dir",
            str(Path(__file__).parent.parent.parent.parent / "compression_bridge" / "carriers"),
        )
        self._initialized = False
        # Pluggable stdlib codec registry (independent of the heavy core engine)
        self._codec_registry = CodecRegistry()

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Asynchronously prime the bridge: create engine, pre-warm algorithms."""
        _log.info("Initializing CompressionBridge v3.0.0")
        self._engine = CompressionEngine(config={"carriers_dir": self._carriers_dir})
        self._selector = self._engine.selector  # force lazy-load

        # Pre-warm OMEGA if available
        if HAS_OMEGA:
            try:
                self._omega = await self._load_omega()
                _log.info("OMEGA transcendent layer loaded")
            except Exception:
                _log.warning("OMEGA loader raised, omega will be unavailable", exc_info=True)
                self._omega = None

        self._initialized = True
        _log.info("CompressionBridge initialized")

    async def shutdown(self) -> None:
        """Gracefully tear down the bridge."""
        _log.info("Shutting down CompressionBridge")
        self._engine = None
        self._selector = None
        self._omega = None
        self._initialized = False

    async def _load_omega(self) -> Any:
        """Load or create the OMEGA encoder."""
        if get_omega is not None:
            return await get_omega()
        if OMEGAEncoder is not None:
            return OMEGAEncoder()
        return None

    @property
    def engine(self) -> CompressionEngine:
        """Return the underlying CompressionEngine (lazy-create if needed)."""
        if self._engine is None:
            self._engine = CompressionEngine(config={"carriers_dir": self._carriers_dir})
        return self._engine

    # ── Core Operations ────────────────────────────────────────────────────

    def compress(
        self,
        data: bytes,
        mode: CompressionMode | str = CompressionMode.ADAPTIVE,
        carrier_name: str | None = None,
        codec: str | None = None,
    ) -> CompressionResult:
        """Compress *data* using the given *mode*.

        Args:
            data: Raw bytes to compress.
            mode: A CompressionMode enum value or its string name.
            carrier_name: Optional filename for carrier-based modes.
            codec: Optional stdlib codec name ("auto", "xz", "gzip", "bz2",
                "json", "noop"). When provided, compression is routed through
                the pluggable codec registry instead of the core engine.
                ``"auto"`` negotiates the best codec for *data*.

        Returns:
            A CompressionResult with .success, .ratio, .algorithm_used, etc.

        Events:
            - ``compression.algorithm.selected``  (when ADAPTIVE picks a mode)
            - ``compression.completed``  (after every compression)
        """
        if codec is not None:
            return self._compress_with_codec(data, codec=codec)

        mode = self._resolve_mode(mode)

        # For ADAPTIVE mode, tap the selector to emit the selection event
        if mode == CompressionMode.ADAPTIVE:
            selected = self.engine.selector.select(data)
            self._events.emit(
                "compression.algorithm.selected",
                {
                    "original_mode": "adaptive",
                    "selected_mode": selected.value,
                    "data_size": len(data),
                },
            )
            mode = selected

        start = time.perf_counter()
        result = self.engine.compress(data, mode, carrier_name=carrier_name)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Throughput in MB/s
        throughput = (len(data) / (elapsed_ms / 1000) / (1024 * 1024)) if elapsed_ms > 0 else 0.0

        # Emit completion event
        self._events.emit(
            "compression.completed",
            {
                "mode": mode.value,
                "algorithm": result.algorithm_used,
                "original_size": result.original_size,
                "compressed_size": result.compressed_size,
                "ratio": round(result.ratio, 3),
                "success": result.success,
                "duration_ms": round(elapsed_ms, 2),
                "throughput_mbps": round(throughput, 2),
            },
        )

        # Update stats
        self._record_metric(
            CompressionMetric(
                mode=mode.value,
                original_size=result.original_size,
                compressed_size=result.compressed_size,
                ratio=result.ratio,
                algorithm=result.algorithm_used or "unknown",
                duration_ms=elapsed_ms,
                throughput_mbps=throughput,
            )
        )

        return result

    # ── Pluggable codec registry + ratio negotiation ───────────────────────

    @property
    def codec_registry(self) -> CodecRegistry:
        """The pluggable stdlib codec registry attached to this bridge."""
        return self._codec_registry

    def select_codec(self, data: Any, codec: str = "auto") -> str:
        """Negotiate (or resolve) the best codec name for *data*.

        Args:
            data: The payload to compress.
            codec: ``"auto"`` to negotiate the best codec, or an explicit
                codec name from the registry.

        Returns:
            The selected codec name.
        """
        if codec in (None, "", "auto"):
            return self._codec_registry.best_codec(data).name
        self._codec_registry.get(codec)  # raises KeyError if unknown
        return codec

    def negotiate_ratio(self, source_payload: Any) -> dict[str, Any]:
        """Negotiate the best codec and report achievable savings.

        Returns a dict with codec / ratio / original_size / compressed_size /
        saved_bytes (see ``codecs.negotiate_ratio``).
        """
        return negotiate_ratio(source_payload)

    def compress_best(self, data: Any) -> CompressionResult:
        """Compress *data* using the auto-negotiated best stdlib codec."""
        return self._compress_with_codec(data, codec="auto")

    def _compress_with_codec(self, data: Any, codec: str = "auto") -> CompressionResult:
        """Compress *data* through the pluggable codec registry.

        Returns a ``CompressionResult`` (Drop-in compatible with the core
        engine path) describing the negotiated codec operation.
        """
        name = self.select_codec(data, codec=codec)
        selected = self._codec_registry.get(name)

        start = time.perf_counter()
        try:
            encoded = selected.encode(data)
            success = True
            error = None
        except Exception as exc:  # pragma: no cover - defensive
            encoded = _as_raw_bytes(data)
            success = False
            error = str(exc)
        elapsed_ms = (time.perf_counter() - start) * 1000

        original_size = _data_size(data)
        compressed_size = len(encoded)
        ratio = (original_size / max(compressed_size, 1)) if original_size else 1.0

        result = CompressionResult(
            success=success,
            original_size=original_size,
            compressed_size=compressed_size,
            ratio=ratio,
            mode=CompressionMode.ADAPTIVE,
            algorithm_used=f"codec:{name}",
            metadata={
                "codec": name,
                "mime": selected.mime,
                "saved_bytes": original_size - compressed_size,
                "lossless": True,
            },
            error=error,
            compression_time_ms=elapsed_ms,
        )

        self._events.emit(
            "compression.completed",
            {
                "mode": "codec",
                "codec": name,
                "algorithm": result.algorithm_used,
                "original_size": original_size,
                "compressed_size": compressed_size,
                "ratio": round(ratio, 3),
                "success": success,
                "duration_ms": round(elapsed_ms, 2),
                "codec_mime": selected.mime,
            },
        )

        self._record_metric(
            CompressionMetric(
                mode=f"codec:{name}",
                original_size=original_size,
                compressed_size=compressed_size,
                ratio=ratio,
                algorithm=result.algorithm_used or "unknown",
                duration_ms=elapsed_ms,
            )
        )
        return result

    def decompress(
        self,
        data: bytes,
        mode: CompressionMode | str,
        carrier_path: str | None = None,
    ) -> CompressionResult:
        """Decompress data previously compressed with *mode*.

        Args:
            data: Compressed bytes.
            mode: The CompressionMode used for compression.
            carrier_path: Required for IMPOSSIBLE/STEGANOGRAPHY modes.

        Returns:
            CompressionResult with decompressed data size.
        """
        mode = self._resolve_mode(mode)
        start = time.perf_counter()
        result = self.engine.decompress(data, mode, carrier_path=carrier_path)
        elapsed_ms = (time.perf_counter() - start) * 1000

        self._emit_decompress(mode, result, elapsed_ms)
        with self._lock:
            self._stats.total_decompressions += 1
            if result.success:
                self._stats.total_bytes_processed += result.compressed_size
        return result

    def batch_compress(
        self,
        files: list[str],
        mode: CompressionMode | str = CompressionMode.ADAPTIVE,
        max_workers: int | None = None,
    ) -> list[CompressionResult]:
        """Compress multiple files in parallel.

        Args:
            files: List of file paths to compress.
            mode: Compression mode to apply to every file.
            max_workers: Override default max parallel workers.

        Returns:
            List of CompressionResult in file order.
        """
        import concurrent.futures

        workers = max_workers or self._max_batch_workers
        mode_enum = self._resolve_mode(mode)
        results: list[CompressionResult | BaseException] = [None] * len(files)  # type: ignore[assignment]

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures: dict[Any, int] = {}
            for idx, path in enumerate(files):
                fut = pool.submit(self._compress_file, path, mode_enum)
                futures[fut] = idx

            for fut in concurrent.futures.as_completed(futures):
                idx = futures[fut]
                try:
                    results[idx] = fut.result()
                except Exception as exc:
                    results[idx] = exc

        out: list[CompressionResult] = []
        for i, r in enumerate(results):
            if isinstance(r, CompressionResult):
                out.append(r)
            else:
                # Synthesise an error result for failed files
                path = files[i]
                try:
                    size = Path(path).stat().st_size
                except OSError:
                    size = 0
                out.append(
                    CompressionResult(
                        success=False,
                        original_size=size,
                        compressed_size=0,
                        ratio=0.0,
                        mode=mode_enum,
                        error=str(r),
                    )
                )
        return out

    def _compress_file(self, path: str, mode: CompressionMode) -> CompressionResult:
        """Compress a single file (internal pool worker)."""
        data = Path(path).read_bytes()
        return self.compress(data, mode, carrier_name=Path(path).name + ".carrier")

    # ── OMEGA Transcendence ────────────────────────────────────────────────

    def omega_transcend(self, data: bytes | str) -> dict[str, Any]:
        """Transcend data through OMEGA — the final compression form.

        Combines all layers: semantic extraction, evolutionary PAQ8,
        Wenyan encoding, glycoph compression, PXPipe steganography.

        Args:
            data: Raw bytes or text to transcend.

        Returns:
            Dict with keys: success, original_size, compressed_size, ratio,
            space_savings_pct, carrier_path, shannon_efficiency_pct,
            transcendence_proof, error.

        Events:
            ``compression.omega.transcended`` with full layer details.
        """
        if not HAS_OMEGA or self._omega is None:
            return self._omega_fallback(data, "OMEGA module not available")

        # Determine original size before any conversion
        len(data.encode()) if isinstance(data, str) else len(data)

        try:
            result = self._run_omega(data)
        except Exception as exc:
            _log.exception("OMEGA transcendence failed")
            return self._omega_fallback(data, str(exc))

        payload = {
            "success": result.success,
            "original_size": result.original_size,
            "compressed_size": result.compressed_size,
            "ratio": round(result.ratio, 3) if hasattr(result, "ratio") else 0.0,
            "space_savings_pct": round(getattr(result, "space_savings_pct", 0.0), 2),
            "shannon_efficiency_pct": round(getattr(result, "shannon_efficiency_pct", 0.0), 2),
            "genome_fitness": round(getattr(result, "genome_fitness", 0.0), 4),
            "transcendence_proof": getattr(result, "transcendence_proof", ""),
            "carrier_path": getattr(result, "carrier_path", None),
            "error": getattr(result, "error", None),
        }

        self._events.emit("compression.omega.transcended", payload)

        with self._lock:
            self._stats.total_omega_transcendence += 1
            if result.success:
                self._stats.total_bytes_processed += result.original_size
                self._stats.total_bytes_saved += result.original_size - result.compressed_size
                efficiency = getattr(result, "shannon_efficiency_pct", 0.0)
                self._stats.omega_efficiency.append(efficiency)
                if len(self._stats.omega_efficiency) > 1000:
                    self._stats.omega_efficiency = self._stats.omega_efficiency[-1000:]

        return payload

    def _omega_fallback(self, data: bytes | str, error: str) -> dict[str, Any]:
        """Return a failure dict for OMEGA errors."""
        orig = len(data.encode()) if isinstance(data, str) else len(data)
        return {
            "success": False,
            "original_size": orig,
            "compressed_size": 0,
            "ratio": 0.0,
            "space_savings_pct": 0.0,
            "error": error,
        }

    def _run_omega(self, data: bytes | str) -> Any:
        """Run OMEGA transcendence, handling nested event loops.

        Uses a separate thread when inside an existing event loop.
        """
        try:
            asyncio.get_running_loop()
            # We're inside a running event loop — run in a background thread
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(self._sync_transcend, data)
                return future.result(timeout=300)
        except RuntimeError:
            # No running event loop — safe to call asyncio.run directly
            return self._sync_transcend(data)

    def _sync_transcend(self, data: bytes | str) -> Any:
        """Synchronous OMEGA transcend — always safe to call."""
        if transcend is not None:
            return asyncio.run(transcend(data))
        if self._omega is not None and hasattr(self._omega, "transcend"):
            return asyncio.run(self._omega.transcend(data))
        msg = "OMEGA encoder not callable"
        raise RuntimeError(msg)

    # ── Statistics ─────────────────────────────────────────────────────────

    def get_algorithm_stats(self) -> dict[str, Any]:
        """Return per-algorithm and per-mode statistics.

        Includes:
          - Mode-level: count, avg ratio, avg throughput
          - Algorithm-level: usage counts
          - Selector: distribution of ADAPTIVE decisions
          - OMEGA: average efficiency, total transcendence count
        """
        with self._lock:
            base = self._stats.to_dict()

        # Merge core engine stats
        if self._engine is not None:
            engine_stats = self._engine.get_stats()
            base["engine"] = engine_stats

        # Selector stats
        if self._selector is not None:
            base["selector"] = self._selector.get_stats()

        return base

    def get_stats(self) -> dict[str, Any]:
        """Alias for get_algorithm_stats()."""
        return self.get_algorithm_stats()

    def _record_metric(self, metric: CompressionMetric) -> None:
        """Record a compression metric into aggregate stats."""
        with self._lock:
            self._stats.total_compressions += 1
            self._stats.total_bytes_processed += metric.original_size
            self._stats.total_bytes_saved += metric.original_size - metric.compressed_size

            mode = metric.mode
            self._stats.ratios_by_mode.setdefault(mode, []).append(metric.ratio)
            self._stats.throughput_by_mode.setdefault(mode, []).append(metric.throughput_mbps)

            algo = metric.algorithm
            self._stats.algorithm_counts[algo] = self._stats.algorithm_counts.get(algo, 0) + 1

            # Selector distribution (tracked separately for ADAPTIVE)
            if metric.mode == "adaptive":
                sel_algo = metric.algorithm or "unknown"
                self._stats.selector_distribution[sel_algo] = (
                    self._stats.selector_distribution.get(sel_algo, 0) + 1
                )

            self._stats.last_compress_at = datetime.now(UTC)

            # Trim lists
            for lst in (self._stats.ratios_by_mode, self._stats.throughput_by_mode):
                for k in list(lst.keys()):
                    if len(lst[k]) > 10000:
                        lst[k] = lst[k][-10000:]

    def _emit_decompress(
        self, mode: CompressionMode, result: CompressionResult, elapsed_ms: float
    ) -> None:
        """Emit a decompression completion event."""
        self._events.emit(
            "compression.decompressed",
            {
                "mode": mode.value,
                "algorithm": result.algorithm_used,
                "original_size": result.original_size,
                "decompressed_size": result.compressed_size,
                "success": result.success,
                "duration_ms": round(elapsed_ms, 2),
            },
        )

    # ── Health ─────────────────────────────────────────────────────────────

    async def health_check(self) -> dict[str, Any]:
        """Validate all algorithms are loadable and OMEGA is accessible.

        Returns:
            Dict with 'healthy' (bool), 'algorithms' (dict of class→status),
            'omega' (dict), 'engine' (bool), 'details' (list of issues).
        """
        alg_status: dict[str, str] = {}
        issues: list[str] = []

        # Check each algorithm class
        for cls in self.ALGORITHM_CLASSES:
            try:
                instance = cls()
                # Quick sanity: can we get the name?
                _ = instance.name if hasattr(instance, "name") else cls.__name__
                alg_status[cls.__name__] = BridgeHealth.OK.value
            except Exception as exc:
                alg_status[cls.__name__] = BridgeHealth.FAILED.value
                issues.append(f"{cls.__name__}: {exc}")

        # Check selector
        try:
            AdaptiveCompressorSelector()
            alg_status["AdaptiveCompressorSelector"] = BridgeHealth.OK.value
        except Exception as exc:
            alg_status["AdaptiveCompressorSelector"] = BridgeHealth.FAILED.value
            issues.append(f"AdaptiveCompressorSelector: {exc}")

        # Check OMEGA
        omega_status = BridgeHealth.UNKNOWN.value
        if HAS_OMEGA:
            try:
                omega = await self._load_omega()
                if omega is not None:
                    omega_status = BridgeHealth.OK.value
                else:
                    omega_status = BridgeHealth.FAILED.value
                    issues.append("OMEGA encoder is None after load")
            except Exception as exc:
                omega_status = BridgeHealth.FAILED.value
                issues.append(f"OMEGA: {exc}")
        else:
            omega_status = "unavailable"
            issues.append("OMEGA module not importable")

        # Check engine
        engine_ok = False
        try:
            eng = self.engine
            if eng is not None:
                # Perform one trivial compression
                result = eng.compress(b"health-check", CompressionMode.FAST)
                engine_ok = result.success
                if not engine_ok:
                    issues.append(f"Engine health compression failed: {result.error}")
        except Exception as exc:
            issues.append(f"Engine: {exc}")

        all_ok = all(s == BridgeHealth.OK.value for s in alg_status.values()) and engine_ok

        return {
            "healthy": all_ok and not issues,
            "algorithms": alg_status,
            "omega": {"available": HAS_OMEGA, "status": omega_status},
            "engine": engine_ok,
            "details": issues or ["All systems operational"],
        }

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_mode(mode: CompressionMode | str) -> CompressionMode:
        """Resolve a mode from either an enum value or a string name."""
        if isinstance(mode, CompressionMode):
            return mode
        # Case-insensitive lookup
        upper = mode.upper().strip()
        mapping: dict[str, CompressionMode] = {m.name: m for m in CompressionMode}
        if upper in mapping:
            return mapping[upper]
        # Try value level match
        for m in CompressionMode:
            if m.value == mode.lower():
                return m
        msg = f"Unknown compression mode: {mode!r}. Valid: {[m.name for m in CompressionMode]}"
        raise ValueError(msg)

    def register_event_handler(self, topic: str, handler: Callable[..., Any]) -> None:
        """Register a callback for bridge events (compression.completed, etc.)."""
        self._events.on(topic, handler)

    @property
    def stats(self) -> BridgeStats:
        """Direct access to bridge statistics."""
        return self._stats

    @property
    def initialized(self) -> bool:
        """Whether the bridge has been fully initialized."""
        return self._initialized


# ==========================================================================
# CompressionHealthCheck
# ==========================================================================


@dataclass
class CompressionHealthCheck:
    """Self-contained health check for the ENI Compression module.

    Validates:
      - All 10 algorithm classes are importable and instantiable
      - AdaptiveCompressorSelector is operational
      - OMEGA transcendent layer is reachable
      - Core CompressionEngine can perform a trivial round-trip
    """

    bridge: CompressionBridge | None = None

    async def run(self) -> dict[str, Any]:
        """Execute the full health check.

        Returns a platform-compatible HealthReport-style dict.
        """
        start = time.perf_counter()

        if self.bridge is None:
            elapsed = (time.perf_counter() - start) * 1000
            return {
                "module_name": "compression_bridge",
                "status": "unhealthy",
                "response_time_ms": round(elapsed, 2),
                "timestamp": datetime.now(UTC).isoformat(),
                "details": {"error": "No CompressionBridge available"},
            }

        try:
            report = await self.bridge.health_check()
            elapsed = (time.perf_counter() - start) * 1000
            return {
                "module_name": "compression_bridge",
                "status": "healthy" if report["healthy"] else "degraded",
                "response_time_ms": round(elapsed, 2),
                "timestamp": datetime.now(UTC).isoformat(),
                "details": report,
            }
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            return {
                "module_name": "compression_bridge",
                "status": "unhealthy",
                "response_time_ms": round(elapsed, 2),
                "timestamp": datetime.now(UTC).isoformat(),
                "details": {"error": str(exc)},
            }
