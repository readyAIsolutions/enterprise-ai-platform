"""ENI Self-Healing Fleet Supervisor — response_ops.core.

A lightweight, stdlib-only supervisor that probes a set of known local service
endpoints over TCP and, when a service is discovered down, attempts to restart
it by launching its command, logging every decision to ``logs/supervisor.log``
and publishing an event on the kernel :class:`EventBus` when one is available.

Design goals:
  * Fully unit-testable offline (probe is injectable; restart is injectable).
  * Zero third-party dependencies — uses ``socket``, ``subprocess`` and stdlib
    logging only, so it can be run from a bare ``python3``.
  * A :class:`FleetSupervisor` facade owns the public surface; the module-level
    :func:`main` drives the CLI (``scripts/fleet_supervisor.py``).

The default fleet mirrors the platform's known local endpoints:

  ============  =========  =====
  name          host       port
  ============  =========  =====
  multiplayer   127.0.0.1  8788
  controller    127.0.0.1  8913
  dashboard     127.0.0.1  8421
  ============  =========  =====

Version: 1.0.0 | Python: 3.11+
"""
from __future__ import annotations

import logging
import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from enterprise.platform_kernel import Event, EventBus, EventPriority, HealthStatus, Module, module

logger = logging.getLogger("enterprise.response_ops")

DEFAULT_TIMEOUT = 1.0
"""TCP connect timeout (seconds) used by :func:`probe_port`."""

# Absolute path to the directory that CONTAINS the ``enterprise`` package.
# Used as the working directory when launching ``python3 -m enterprise.<mod>``
# restart commands so the package resolves the same way systemd / boot_all.sh
# resolve it.
_ENTERPRISE_ROOT = Path(__file__).resolve().parent.parent.parent
_WORKDIR = _ENTERPRISE_ROOT.parent


@dataclass(frozen=True)
class ServiceSpec:
    """Descriptor for one monitored service endpoint.

    Attributes:
        name: Human-readable service name (also used as the event source).
        host: Hostname / IP to probe (defaults to the loopback interface).
        port: TCP port that the service is expected to listen on.
        restart_cmd: Command (argv list) used to relaunch the service. May be
            ``None`` if the service has no known restart path.
    """

    name: str
    port: int
    host: str = "127.0.0.1"
    restart_cmd: Optional[Sequence[str]] = None


@dataclass
class ProbeResult:
    """Result of probing a single service endpoint.

    Attributes:
        spec: The :class:`ServiceSpec` that was probed.
        up: ``True`` when the endpoint accepted a TCP connection.
        latency_ms: Connect round-trip latency in milliseconds (``None`` if down).
        error: Human-readable failure reason when the probe failed.
        at: UTC timestamp of the probe.
    """

    spec: ServiceSpec
    up: bool
    latency_ms: Optional[float] = None
    error: Optional[str] = None
    at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ─────────────────────────────────────────────────────────────────────────────
# Probe primitive
# ─────────────────────────────────────────────────────────────────────────────

def default_services() -> List[ServiceSpec]:
    """Return the default fleet of monitored local services.

    Mirrors the platform's known local endpoints (multiplayer :8788,
    controller :8913, dashboard :8421) with restart commands matching the
    systemd / boot_all launch vocabulary, using the active ``python``.
    """
    py = sys.executable or "python3"
    return [
        ServiceSpec(
            "multiplayer",
            8788,
            restart_cmd=[py, "-m", "enterprise.multiplayer.server.server", "8787"],
        ),
        ServiceSpec(
            "controller",
            8913,
            restart_cmd=[py, "-m", "enterprise.local_controller.controller", "--port", "8913"],
        ),
        ServiceSpec(
            "dashboard",
            8421,
            restart_cmd=[py, "-m", "dashboard.server"],
        ),
    ]


def probe_port(
    host: str, port: int, timeout: float = DEFAULT_TIMEOUT
) -> tuple[bool, Optional[float], Optional[str]]:
    """Probe a TCP endpoint; return ``(up, latency_ms, error)``.

    A service is considered "up" when a TCP connection can be established
    within ``timeout`` seconds. This is the transport-level health signal that
    the supervisor uses for both the up/down decision and the restart trigger.
    """
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            latency_ms = (time.perf_counter() - start) * 1000.0
            return True, latency_ms, None
    except OSError as exc:  # connection refused, timeout, unreachable, ...
        return False, None, str(exc)
    except Exception as exc:  # pragma: no cover - defensive
        return False, None, str(exc)


# ─────────────────────────────────────────────────────────────────────────────
# Supervisor facade
# ─────────────────────────────────────────────────────────────────────────────

RestartFn = Callable[[ServiceSpec], bool]
"""Signature of the restart launcher used by :class:`FleetSupervisor`."""


class FleetSupervisor:
    """Facade for the self-healing fleet supervisor.

    The supervisor owns the probe/restart loop and can be used programmatically
    (``check()`` / ``run_once()`` / ``watch()``) or driven from the CLI via
    :func:`main`. Everything that touches the outside world (probing,
    restarting, logging, event publishing) is injectable so unit tests can run
    fully offline.
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        services: Optional[Sequence[ServiceSpec]] = None,
        bus: Optional[EventBus] = None,
        probe_fn: Optional[Callable[..., tuple[bool, Optional[float], Optional[str]]]] = None,
        restart_fn: Optional[RestartFn] = None,
        log_path: Optional[Path] = None,
        dry_run: bool = False,
    ) -> None:
        """Initialize the supervisor.

        Args:
            config: Optional ``dict``; recognised keys are ``timeout`` (float)
                and ``services`` (list of dicts). ``services`` passed directly
                takes precedence.
            services: Explicit list of :class:`ServiceSpec` to monitor. Defaults
                to :func:`default_services`.
            bus: Optional kernel :class:`EventBus`. When ``None`` the supervisor
                lazily creates its own local bus for event publishing.
            probe_fn: Inject a probe callable ``(host, port, timeout) -> (up,
                latency_ms, error)``. Defaults to :func:`probe_port`.
            restart_fn: Inject a restart launcher ``(spec) -> bool``. Defaults to
                :meth:`_restart_subprocess` unless ``dry_run=True`` (no-op True).
            log_path: Where to write supervisor logs (defaults to
                ``<repo>/logs/supervisor.log``).
            dry_run: When True, never actually launch processes (restart is a
                no-op that logs intent).
        """
        cfg = config or {}
        self.timeout: float = float(cfg.get("timeout", DEFAULT_TIMEOUT))
        self.services: List[ServiceSpec] = list(
            services if services is not None else self._coerce_services(cfg.get("services"))
        )
        self.dry_run: bool = bool(dry_run)

        self._probe_fn = probe_fn or probe_port
        if restart_fn is not None:
            self._restart_fn = restart_fn
        elif dry_run:
            self._restart_fn = lambda spec: True  # never touch the outside world
        else:
            self._restart_fn = self._restart_subprocess

        self._event_bus = bus
        self._owns_bus = bus is None
        self._log_path = Path(
            log_path or (_ENTERPRISE_ROOT / "logs" / "supervisor.log")
        )
        self._configure_logging()

    # -- config helpers -----------------------------------------------------

    @staticmethod
    def _coerce_services(raw: Any) -> List[ServiceSpec]:
        if raw is None:
            return default_services()
        out: List[ServiceSpec] = []
        for item in raw:
            if isinstance(item, ServiceSpec):
                out.append(item)
            elif isinstance(item, dict):
                out.append(
                    ServiceSpec(
                        name=str(item.get("name", "svc")),
                        host=str(item.get("host", "127.0.0.1")),
                        port=int(item["port"]),
                        restart_cmd=list(item["restart_cmd"])
                        if item.get("restart_cmd")
                        else None,
                    )
                )
        return out or default_services()

    # -- logging ------------------------------------------------------------

    def _configure_logging(self) -> None:
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        # File handler for the supervisor log (the durable audit trail).
        fh = logging.FileHandler(self._log_path, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        self._file_handler = fh
        logger.addHandler(fh)
        logger.setLevel(logging.INFO)
        # Also mirror to stderr in development so the CLI is self-documenting.
        has_console = any(
            isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)
            for h in logger.handlers
        )
        if not has_console:
            sh = logging.StreamHandler(sys.stderr)
            sh.setFormatter(logging.Formatter("[fleet-supervisor] %(levelname)s %(message)s"))
            logger.addHandler(sh)

    # -- probing ------------------------------------------------------------

    def check(self) -> List[ProbeResult]:
        """Probe every configured service; return per-service results."""
        results: List[ProbeResult] = []
        for spec in self.services:
            try:
                up, latency_ms, error = self._probe_fn(spec.host, spec.port, self.timeout)
            except Exception as exc:  # pragma: no cover - defensive
                up, latency_ms, error = False, None, str(exc)
            result = ProbeResult(spec=spec, up=up, latency_ms=latency_ms, error=error)
            logger.info(
                "probe %s %s:%s -> %s%s",
                spec.name, spec.host, spec.port,
                "UP" if up else "DOWN",
                f" ({latency_ms:.1f}ms)" if latency_ms is not None else f" ({error})",
            )
            results.append(result)
        return results

    # -- restart ------------------------------------------------------------

    def _restart_subprocess(self, spec: ServiceSpec) -> bool:
        """Launch ``spec.restart_cmd`` as a detached subprocess.

        Uses ``start_new_session=True`` so the child survives the supervisor's
        lifetime, appends its output to an per-service log and returns True on
        successful spawn (not on successful startup — the next probe decides).
        """
        cmd = list(spec.restart_cmd) if spec.restart_cmd else []
        if not cmd:
            logger.warning("no restart_cmd for %s; skipping relaunch", spec.name)
            return False
        log_dir = _ENTERPRISE_ROOT / "logs" / "boot"
        log_dir.mkdir(parents=True, exist_ok=True)
        out_path = log_dir / f"{spec.name}.log"
        try:
            with open(out_path, "ab") as out:
                subprocess.Popen(
                    cmd,
                    cwd=str(_WORKDIR),
                    stdout=out,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            logger.info("relaunched %s via %s", spec.name, " ".join(cmd))
            return True
        except Exception as exc:  # pragma: no cover - OSError etc.
            logger.error("failed to relaunch %s: %s", spec.name, exc)
            return False

    def restart(self, spec: ServiceSpec) -> bool:
        """Attempt to restart a service; publish an event and log the outcome."""
        ok = self._restart_fn(spec)
        self._publish(
            "response_ops.service_restarted" if ok else "response_ops.restart_failed",
            {"service": spec.name, "port": spec.port, "ok": ok},
            priority=EventPriority.HIGH,
        )
        logger.info("restart %s -> %s", spec.name, "OK" if ok else "FAILED")
        return ok

    # -- events -------------------------------------------------------------

    def _get_bus(self) -> EventBus:
        if self._event_bus is None:
            self._event_bus = EventBus()
        return self._event_bus

    def _publish(self, topic: str, payload: Dict[str, Any], priority: EventPriority) -> None:
        try:
            event = Event.create(
                topic=topic,
                source="response_ops",
                payload=dict(payload),
                priority=priority,
            )
            bus = self._get_bus()
            # Supervisor events (service down / restarted) must be *delivered*,
            # not merely queued, so use the blocking path when available. This
            # also keeps unit tests deterministic (no async-dispatch race).
            publisher = getattr(bus, "publish_sync", bus.publish)
            publisher(event)
        except Exception as exc:  # pragma: no cover - bus must never crash us
            logger.warning("event publish failed for %s: %s", topic, exc)

    # -- aggregate actions ---------------------------------------------------

    def run_once(self) -> Dict[str, Any]:
        """Probe the whole fleet and heal whatever is down; return a report."""
        results = self.check()
        healed: List[str] = []
        failed: List[str] = []
        for r in results:
            if not r.up:
                self._publish(
                    "response_ops.service_down",
                    {"service": r.spec.name, "port": r.spec.port, "error": r.error},
                    priority=EventPriority.CRITICAL,
                )
                if self.restart(r.spec):
                    healed.append(r.spec.name)
                else:
                    failed.append(r.spec.name)
        summary = {
            "checked": len(results),
            "up": sum(1 for r in results if r.up),
            "down": sum(1 for r in results if not r.up),
            "healed": healed,
            "failed": failed,
            "results": results,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        logger.info(
            "fleet run: %d up / %d down / healed=%s / failed=%s",
            summary["up"], summary["down"], healed, failed,
        )
        return summary

    def watch(self, interval: float = 30.0, iterations: Optional[int] = None) -> None:
        """Run the probe-and-heal loop forever (or for ``iterations`` passes)."""
        logger.info("watch started (interval=%ss, dry_run=%s)", interval, self.dry_run)
        i = 0
        while iterations is None or i < iterations:
            i += 1
            try:
                self.run_once()
            except Exception as exc:  # pragma: no cover
                logger.exception("watch iteration %d failed: %s", i, exc)
            if iterations is None or i < iterations:
                time.sleep(interval)

    def close(self) -> None:
        """Detach the file logger (used by the CLI in watch mode)."""
        try:
            logger.removeHandler(self._file_handler)
            self._file_handler.close()
        except Exception:  # pragma: no cover
            pass


@module(name="response_ops", version="1.0.0")
class ResponseOpsModule(Module):
    """Platform Kernel module wrapper exposing the fleet supervisor facade."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._supervisor: Optional[FleetSupervisor] = None

    async def initialize(self) -> None:
        self.status = HealthStatus.HEALTHY
        self._supervisor = FleetSupervisor(config=dict(self._config))
        logger.info("response_ops initialized with %d services", len(self._supervisor.services))

    async def health_check(self) -> HealthStatus:
        if self._supervisor is not None:
            results = self._supervisor.check()
            return HealthStatus.HEALTHY if any(r.up for r in results) else HealthStatus.DEGRADED
        return self.status

    async def shutdown(self) -> None:
        if self._supervisor is not None:
            self._supervisor.close()
        self.status = HealthStatus.STOPPED

    @property
    def supervisor(self) -> Optional[FleetSupervisor]:
        return self._supervisor


def create_response_ops_module(config: Optional[Dict[str, Any]] = None) -> ResponseOpsModule:
    """Create (but do not initialize) a :class:`ResponseOpsModule`."""
    return ResponseOpsModule(config=config or {})


# ─────────────────────────────────────────────────────────────────────────────
# CLI-friendly entrypoint (used by scripts/fleet_supervisor.py)
# ─────────────────────────────────────────────────────────────────────────────

def _format_result(r: ProbeResult) -> str:
    status = "UP  " if r.up else "DOWN"
    detail = f"{r.latency_ms:.1f}ms" if r.latency_ms is not None else (r.error or "-")
    return f"  {status}  {r.spec.name:<12} {r.spec.host}:{r.spec.port:<5}  {detail}"


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entrypoint.

    ``--check`` lists every service and its status (one probe pass).
    ``--watch`` runs the probe-and-heal loop until Ctrl-C.

    Returns a process exit code (0 = all healthy; 1 = something down).
    """
    import argparse

    parser = argparse.ArgumentParser(prog="fleet_supervisor", description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Probe every service once and list name/status.",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Run the probe-and-heal loop (ala '--check' on a timer).",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=30.0,
        help="Seconds between watch passes (default: 30).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="TCP connect timeout per probe in seconds (default: 1.0).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect problems but never actually launch restart commands.",
    )
    args = parser.parse_args(argv)

    if not (args.check or args.watch):
        # Default behaviour matches --check so bare invocation is useful.
        args.check = True

    supervisor = FleetSupervisor(
        config={"timeout": args.timeout}, dry_run=args.dry_run
    )

    def one_pass() -> int:
        report = supervisor.run_once()
        print(f"\nFleet status ({report['at']}):  {report['up']}/{report['checked']} up")
        for r in report["results"]:
            print(_format_result(r))
        if report["down"]:
            print(f"\n  healed: {report['healed'] or 'none'}")
            print(f"  failed: {report['failed'] or 'none'}")
        return 0 if report["down"] == 0 else 1

    try:
        if args.watch:
            print(f"Watching fleet every {args.interval}s  (Ctrl-C to stop)")
            supervisor.watch(interval=args.interval)
            return 0
        return one_pass()
    except KeyboardInterrupt:  # pragma: no cover - interactive
        print("\nStopped.")
        return 130
    finally:
        supervisor.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
