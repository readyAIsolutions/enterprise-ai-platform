"""
Enterprise Platform — Compression Bridge Module v3.0.0
======================================================

Enterprise-grade compression module bridging the core Compression engine
into the Enterprise Platform OS. Provides:

  - CompressionBridge  — unified API for all 12 compression modes + OMEGA transcendent
  - CompressionHealthCheck — validates all algorithms loadable, OMEGA accessible
  - Events: compression.completed, compression.omega.transcended, compression.algorithm.selected
  - Metrics: compression ratios per mode, throughput, omega efficiency

Architecture:
    __init__.py            — Module housekeeping, @module registration, exports
    compression_bridge.py  — CompressionBridge (compress, decompress, batch,
                              omega_transcend, stats, health_check)
    tests/test_compression.py — 40+ production-quality tests
"""

from __future__ import annotations

import os
import sys

# Ensure core compression engine is importable
_ENI_CORE = os.path.join(os.path.dirname(__file__), "..", "..", "..", "eni_compression")
if _ENI_CORE not in sys.path:
    sys.path.insert(0, os.path.abspath(_ENI_CORE))

# Import from platform kernel, handling both absolute (from parent dir)
# and relative (from within enterprise/) contexts.
try:
    from enterprise.platform_kernel import HealthStatus, Module, module
except ImportError:
    # Running from inside enterprise/ — need the parent on sys.path
    _enterprise_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    _parent = os.path.dirname(_enterprise_dir)
    if _parent not in sys.path:
        sys.path.insert(0, _parent)
    from enterprise.platform_kernel import HealthStatus, Module, module

from .codecs import (
    Bz2Codec,
    Codec,
    CodecRegistry,
    GzipCodec,
    JsonCodec,
    NOOPCodec,
    XZCodec,
    negotiate_ratio,
)
from .compression_bridge import (
    CompressionBridge,
    CompressionHealthCheck,
)

# ── Module class registered with the platform kernel ──────────────────────


@module(name="compression_bridge", version="3.0.0")
class CompressionBridgeModule(Module):
    """Enterprise Compression Bridge Module — bridges core engine to platform OS.

    Lifecycle:
        initialize()  → spins up CompressionBridge, validates all algorithms
        health_check() → verifies all 10 algorithms + OMEGA are accessible
        shutdown()    → tears down bridge, clears caches
    """

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self._bridge: CompressionBridge | None = None
        self._health: CompressionHealthCheck | None = None

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Initialize the compression module.

        Bootstraps the CompressionBridge and runs an initial health validation
        to ensure all algorithms and the OMEGA transcendent layer are reachable.
        """
        self._bridge = CompressionBridge(config=self._config)
        self._health = CompressionHealthCheck(bridge=self._bridge)
        self._status = HealthStatus.STARTING

        # Prime the bridge — lazy-load all algorithm references
        await self._bridge.initialize()
        self._status = HealthStatus.HEALTHY

    async def health_check(self) -> HealthStatus:
        """Perform a full algorithmic health check.

        Verifies every compressor class, the adaptive selector, and the OMEGA
        transcendent layer are importable and instantiable.
        """
        if self._bridge is None:
            self._status = HealthStatus.UNHEALTHY
            return self._status

        try:
            report = await self._bridge.health_check()
            self._status = HealthStatus.HEALTHY if report["healthy"] else HealthStatus.DEGRADED
        except Exception:
            self._status = HealthStatus.UNHEALTHY
        return self._status

    async def shutdown(self) -> None:
        """Gracefully shut down the compression module.

        Tears down the bridge, clears internal caches, and transitions to STOPPED.
        """
        self._status = HealthStatus.STOPPING
        if self._bridge is not None:
            await self._bridge.shutdown()
            self._bridge = None
        self._health = None
        self._status = HealthStatus.UNHEALTHY  # post-shutdown

    # ── Accessors ──────────────────────────────────────────────────────────

    @property
    def bridge(self) -> CompressionBridge | None:
        """The active CompressionBridge instance."""
        return self._bridge


# ── Module factory (platform contract) ─────────────────────────────────────


def create_compression_bridge_module(config: dict | None = None) -> CompressionBridgeModule:
    """Create and return a CompressionBridgeModule instance.

    This is the standard platform factory entrypoint (see MODULE CONTRACT).
    """
    return CompressionBridgeModule(config=config)


# ── Public API surface ──────────────────────────────────────────────────────

__all__ = [
    "CompressionBridgeModule",
    "CompressionBridge",
    "CompressionHealthCheck",
    "create_compression_bridge_module",
    # Codec registry + negotiation
    "Codec",
    "XZCodec",
    "GzipCodec",
    "Bz2Codec",
    "JsonCodec",
    "NOOPCodec",
    "CodecRegistry",
    "negotiate_ratio",
]

__version__ = "3.0.0"
