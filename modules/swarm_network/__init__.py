"""
Swarm Network Optimization OS — Enterprise Module
==================================================
Enterprise-grade connection multiplexer for maximum agent concurrency.
Integrates the Swarm Turbocharger proxy as a first-class enterprise module.
The registered module name is 'swarm_network' (registered exactly ONCE at the
class definition via the @module decorator).

Capabilities:
  - 5-layer connection optimization (kernel TCP, token bucket, pooling, pacing, health)
  - Aggressive concurrency tiers: 80 max at -48 dBm, 50 at -59 dBm
  - Turbo mode: overrides conservative limits for burst workloads
  - Auto-discovery of Turbocharger proxy
  - Real-time metrics and health monitoring
  - Graceful degradation on WiFi drops
"""

from __future__ import annotations

import asyncio  # noqa: F401
import json
import logging
import socket  # noqa: F401
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum  # noqa: F401
from pathlib import Path
from typing import Any

# Platform kernel import (handles both import contexts)
try:
    from enterprise.platform_kernel import EventBus, HealthStatus, Module, module
except ImportError:
    import sys

    _parent = str(Path(__file__).resolve().parents[3])
    if _parent not in sys.path:
        sys.path.insert(0, _parent)
    from enterprise.platform_kernel import EventBus, HealthStatus, Module, module

logger = logging.getLogger("enterprise.swarm_network")

from .mux import (  # noqa: E402
    MUX_NOT_AVAILABLE,
    ConnectionScorer,
    Link,
    LinkManager,
    Muxer,
    select_route,
)

# ═══════════════════════════════════════════════════════════════════════════
# Aggressive Concurrency Tiers
# ═══════════════════════════════════════════════════════════════════════════


def get_aggressive_concurrency(signal_dbm: int, turbo_mode: bool = False) -> int:
    """Return max concurrent agents based on WiFi signal strength.

    TURBO MODE: Pushes 25% beyond conservative limits.
    """
    if signal_dbm > -48:
        base = 80
    elif signal_dbm > -52:
        base = 70
    elif signal_dbm > -56:
        base = 60
    elif signal_dbm > -60:
        base = 50
    elif signal_dbm > -65:
        base = 40
    elif signal_dbm > -70:
        base = 25
    elif signal_dbm > -75:
        base = 15
    else:
        base = 8

    if turbo_mode:
        base = int(base * 1.25)
    return base


def get_sustained_rate(concurrency: int) -> float:
    """Sustained requests per second based on concurrency.

    Formula: 0.6 req/sec per slot (was 0.5, pushed to 0.6)
    """
    return concurrency * 0.6


def get_burst_capacity(concurrency: int) -> int:
    """Max instant burst = 4x sustained rate."""
    return int(get_sustained_rate(concurrency) * 4)


# ═══════════════════════════════════════════════════════════════════════════
# WiFi Reader (shared with turbocharger)
# ═══════════════════════════════════════════════════════════════════════════


class WiFiReader:
    """Read WiFi signal and stats without blocking."""

    def __init__(self, interface: str = "wlp4s0") -> None:
        self.interface = interface
        self.signal_dbm: int = -60
        self.concurrency: int = 40
        self.turbo_available: bool = False
        self.turbo_port: int = 8922
        self._lock = threading.Lock()

    def read_signal(self) -> int:
        try:
            out = subprocess.check_output(
                ["iw", "dev", self.interface, "link"], timeout=2, stderr=subprocess.DEVNULL
            ).decode(errors="replace")
            import re

            m = re.search(r"signal:\s*(-?\d+)\s*dBm", out)
            if m:
                with self._lock:
                    self.signal_dbm = int(m.group(1))
        except Exception:
            pass
        with self._lock:
            return self.signal_dbm

    def check_turbocharger(self) -> bool:
        """Check if the turbocharger proxy is running."""
        try:
            import urllib.request

            r = urllib.request.urlopen(f"http://127.0.0.1:{self.turbo_port}/health", timeout=2)
            data = json.loads(r.read())
            with self._lock:
                self.turbo_available = True
                self.concurrency = data.get("concurrency", 40)
            return True
        except Exception:
            with self._lock:
                self.turbo_available = False
            return False

    def get_concurrency(self, turbo_mode: bool = False) -> int:
        self.read_signal()
        return get_aggressive_concurrency(self.signal_dbm, turbo_mode)

    def get_status(self) -> dict:
        with self._lock:
            return {
                "interface": self.interface,
                "signal_dbm": self.signal_dbm,
                "concurrency": self.concurrency,
                "turbocharger_running": self.turbo_available,
                "turbocharger_port": self.turbo_port,
                "aggressive_tier": get_aggressive_concurrency(self.signal_dbm, False),
                "turbo_tier": get_aggressive_concurrency(self.signal_dbm, True),
                "sustained_rate": get_sustained_rate(self.concurrency),
                "burst_capacity": get_burst_capacity(self.concurrency),
            }


# ═══════════════════════════════════════════════════════════════════════════
# Swarm Network Bridge
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class NetworkHealth:
    healthy: bool
    signal_dbm: int
    max_concurrency: int
    sustained_req_per_sec: float
    burst_capacity: int
    turbocharger_running: bool
    turbo_mode: bool = False
    recommendations: list[str] = field(default_factory=list)


class SwarmNetworkBridge:
    """Enterprise bridge to the Swarm Turbocharger.

    Provides:
    - Full lifecycle management (start, stop, restart, auto-recovery)
    - Real-time WiFi health monitoring
    - Aggressive concurrency calculation
    - Turbo mode for burst workloads
    - Metrics for observability
    """

    TURBOCHARGER_SCRIPT = Path("~/.hermes/scripts/swarm_turbocharger.py").expanduser()

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or {}
        self._wifi = WiFiReader(interface=self.config.get("wifi_interface", "wlp4s0"))
        self._wifi.turbo_port = self.config.get("turbocharger_port", 8922)
        self._turbo_mode = self.config.get("turbo_mode", False)
        self._started = False
        self._process: subprocess.Popen | None = None
        self._auto_recovery = self.config.get("auto_recovery", True)
        self._monitor_thread: threading.Thread | None = None

    async def initialize(self) -> None:
        """Initialize — start turbocharger if not running, read signal."""
        if not self._wifi.check_turbocharger():
            self.start_turbocharger()
            time.sleep(3)  # Wait for startup
            self._wifi.check_turbocharger()
        self._wifi.read_signal()
        self._started = True
        if self._auto_recovery:
            self._start_monitor()

        try:
            bus = EventBus()
            bus.publish(
                "swarm.network.initialized",
                {
                    "signal": self._wifi.signal_dbm,
                    "concurrency": self._wifi.get_concurrency(self._turbo_mode),
                    "turbocharger": self._wifi.turbo_available,
                },
            )
        except Exception:
            pass

    def start_turbocharger(self) -> bool:
        """Start the turbocharger proxy process."""
        if not self.TURBOCHARGER_SCRIPT.exists():
            logger.error(f"Turbocharger script not found: {self.TURBOCHARGER_SCRIPT}")
            return False
        try:
            self._process = subprocess.Popen(
                [sys.executable, self.TURBOCHARGER_SCRIPT, "--port", str(self._wifi.turbo_port)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(2)
            return self._wifi.check_turbocharger()
        except Exception as e:
            logger.error(f"Failed to start turbocharger: {e}")
            return False

    def stop_turbocharger(self) -> bool:
        """Stop the turbocharger proxy."""
        try:
            if self._process:
                self._process.terminate()
                self._process.wait(timeout=5)
                self._process = None
            # Also kill by port
            subprocess.run(
                ["fuser", "-k", f"{self._wifi.turbo_port}/tcp"], capture_output=True, timeout=5
            )
            time.sleep(1)
            return not self._wifi.check_turbocharger()
        except Exception:
            return True  # Assume stopped

    def restart_turbocharger(self) -> bool:
        """Restart the turbocharger."""
        self.stop_turbocharger()
        time.sleep(1)
        return self.start_turbocharger()

    def _start_monitor(self) -> None:
        """Background thread that restarts turbocharger if it crashes."""

        def monitor() -> None:
            while self._started:
                time.sleep(10)
                if not self._started:
                    break
                if not self._wifi.check_turbocharger():
                    logger.warning("Turbocharger down — restarting...")
                    self.start_turbocharger()

        self._monitor_thread = threading.Thread(target=monitor, daemon=True)
        self._monitor_thread.start()

    async def health_check(self) -> NetworkHealth:
        """Full health check with recommendations."""
        self._wifi.check_turbocharger()
        signal = self._wifi.read_signal()
        concurrency = self._wifi.get_concurrency(self._turbo_mode)
        turbo = self._wifi.turbo_available

        recs = []
        if signal < -75:
            recs.append("Signal critically weak — move closer to AP or use Ethernet")
        if not turbo:
            recs.append(
                "Turbocharger not running — start: python3 ~/.hermes/scripts/swarm_turbocharger.py"
            )
        if concurrency < 30:
            recs.append(f"Only {concurrency} concurrent — improve signal for more agents")
        if self._turbo_mode:
            recs.append("TURBO MODE active — 25% above conservative limits")

        return NetworkHealth(
            healthy=signal > -85 and turbo,
            signal_dbm=signal,
            max_concurrency=concurrency,
            sustained_req_per_sec=get_sustained_rate(concurrency),
            burst_capacity=get_burst_capacity(concurrency),
            turbocharger_running=turbo,
            turbo_mode=self._turbo_mode,
            recommendations=recs,
        )

    def enable_turbo(self) -> int:
        """Enable turbo mode — returns new concurrency limit."""
        self._turbo_mode = True
        return self._wifi.get_concurrency(turbo_mode=True)

    def disable_turbo(self) -> int:
        """Disable turbo mode — returns standard concurrency."""
        self._turbo_mode = False
        return self._wifi.get_concurrency(turbo_mode=False)

    @property
    def max_concurrency(self) -> int:
        return self._wifi.get_concurrency(self._turbo_mode)

    @property
    def status(self) -> dict:
        return self._wifi.get_status()

    async def shutdown(self) -> None:
        self._started = False
        if self._process:
            self.stop_turbocharger()


# ═══════════════════════════════════════════════════════════════════════════
# Module Registration
# ═══════════════════════════════════════════════════════════════════════════


@module(name="swarm_network", version="2.0.0")
class SwarmNetworkModule(Module):
    """Enterprise Swarm Network Optimization Module.

    Lifecycle:
        initialize() → discovers turbocharger, reads signal, sets concurrency
        health_check() → returns NetworkHealth with recommendations
        shutdown() → cleans up
    """

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self._bridge: SwarmNetworkBridge | None = None

    async def initialize(self) -> None:
        self._bridge = SwarmNetworkBridge(config=self._config)
        await self._bridge.initialize()
        self._status = HealthStatus.HEALTHY

    async def health_check(self) -> HealthStatus:
        if not self._bridge:
            return HealthStatus.UNHEALTHY
        health = await self._bridge.health_check()
        return HealthStatus.HEALTHY if health.healthy else HealthStatus.DEGRADED

    async def shutdown(self) -> None:
        self._started = False
        if self._bridge:
            self._bridge._started = False
            if self._bridge._process:
                self._bridge.stop_turbocharger()
            await self._bridge.shutdown()
        self._status = HealthStatus.UNHEALTHY

    @property
    def bridge(self) -> SwarmNetworkBridge | None:
        return self._bridge


__all__ = [
    "SwarmNetworkModule",
    "SwarmNetworkBridge",
    "NetworkHealth",
    "WiFiReader",
    "get_aggressive_concurrency",
    "get_sustained_rate",
    "get_burst_capacity",
    # Connection multiplexing (mux.py)
    "Link",
    "ConnectionScorer",
    "LinkManager",
    "Muxer",
    "select_route",
    "MUX_NOT_AVAILABLE",
]


def create_swarm_network_module(
    config: dict[str, Any] | None = None,
) -> SwarmNetworkModule:
    """Factory: create a swarm_network module instance (not yet initialized).

    Supported config keys (all optional):
        - wifi_interface: WiFi interface to monitor (default "wlp4s0").
        - turbocharger_port: Turbocharger proxy health port (default 8922).
        - turbo_mode: bool, enable aggressive concurrency (default False).
        - auto_recovery: bool, restart turbocharger if it drops (default True).
    """
    return SwarmNetworkModule(config=config or {})


__version__ = "2.0.0"
