"""Unit tests for the self-healing fleet supervisor (response_ops).

Proves, against *real* ports:
  * the TCP probe detects an UP service on the live multiplayer port :8788
    (cross-checked against a raw socket so the test passes whether or not the
    multiplayer server is running in this environment),
  * the probe detects DOWN on an unbound (closed) TCP port,
  * the facade ``check()`` / ``run_once()`` / ``restart()`` behaviour including
    EventBus event publishing and dry-run semantics.
"""
from __future__ import annotations

import socket
from typing import List

from enterprise.modules.response_ops import (
    FleetSupervisor,
    ProbeResult,
    ServiceSpec,
    default_services,
    probe_port,
)
from enterprise.platform_kernel import EventBus, Event


# ── helpers ──────────────────────────────────────────────────────────────────

def _tcp_up(host: str, port: int, timeout: float = 1.0) -> bool:
    """Cross-check using a raw socket (independent of probe_port)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _unbound_port() -> int:
    """Return a port that is currently unbound (bind to 0, then close)."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _captured_events():
    captured: List[Event] = []

    def handler(event: Event) -> None:
        captured.append(event)

    return captured, handler


# ── probe: UP vs DOWN on real ports ──────────────────────────────────────────

def test_probe_detects_up_on_live_multiplayer_port_8788():
    """Probe the real multiplayer endpoint :8788 and cross-check the verdict."""
    up, latency, err = probe_port("127.0.0.1", 8788)
    assert isinstance(up, bool)
    # Probe must agree with an independent raw-socket check on the SAME port.
    assert up is _tcp_up("127.0.0.1", 8788)
    if up:  # when the multiplay server really is up, latency must be reported
        assert latency is not None and latency >= 0.0
    else:
        assert err is not None


def test_probe_detects_down_on_unbound_port():
    """A closed/unbound port must be reported DOWN promptly."""
    port = _unbound_port()
    up, latency, err = probe_port("127.0.0.1", port, timeout=1.0)
    assert up is False
    assert latency is None
    assert err is not None  # connection refused or timeout surfaced as error


def test_probe_detects_up_on_bound_listener():
    """Deterministic UP detection: bind our own socket and probe it."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        up, latency, _ = probe_port("127.0.0.1", port)
        assert up is True
        assert latency is not None and latency >= 0.0
    finally:
        srv.close()


# ── default fleet ────────────────────────────────────────────────────────────

def test_default_fleet_contains_expected_service_ports():
    specs = default_services()
    by_name = {s.name: s.port for s in specs}
    assert by_name["multiplayer"] == 8788
    assert by_name["controller"] == 8913
    assert by_name["dashboard"] == 8421


# ── facade behaviour ─────────────────────────────────────────────────────────

def test_facade_check_returns_one_result_per_service(tmp_path):
    sup = FleetSupervisor(
        services=[ServiceSpec("a", 1), ServiceSpec("b", 2)],
        dry_run=True,
        log_path=tmp_path / "supervisor.log",
    )
    results: List[ProbeResult] = sup.check()
    assert len(results) == 2
    assert all(isinstance(r, ProbeResult) for r in results)
    assert (tmp_path / "supervisor.log").exists()


def test_run_once_heals_down_service_and_publishes_events(tmp_path):
    bus = EventBus()
    captured, handler = _captured_events()
    bus.subscribe("response_ops.service_down")(handler)
    bus.subscribe("response_ops.service_restarted")(handler)

    restarted: List[str] = []

    def fake_probe(host, port, timeout):
        # multiplayer (8788) DOWN, everything else UP
        if port == 8788:
            return False, None, "connection refused"
        return True, 0.5, None

    def fake_restart(spec: ServiceSpec) -> bool:
        restarted.append(spec.name)
        return True

    sup = FleetSupervisor(
        services=default_services(),
        bus=bus,
        probe_fn=fake_probe,
        restart_fn=fake_restart,
        log_path=tmp_path / "supervisor.log",
    )
    report = sup.run_once()

    assert report["down"] == 1
    assert restarted == ["multiplayer"]
    assert report["healed"] == ["multiplayer"]
    # both a service_down and a service_restarted event should have been emitted
    topics = {e.topic for e in captured}
    assert "response_ops.service_down" in topics
    assert "response_ops.service_restarted" in topics


def test_restart_failure_is_recorded_and_event_emitted(tmp_path):
    bus = EventBus()
    captured, handler = _captured_events()
    bus.subscribe("response_ops.restart_failed")(handler)

    sup = FleetSupervisor(
        services=[ServiceSpec("ghost", 1, restart_cmd=None)],
        bus=bus,
        probe_fn=lambda h, p, t: (False, None, "boom"),
        restart_fn=lambda spec: False,
        log_path=tmp_path / "supervisor.log",
    )
    report = sup.run_once()
    assert report["failed"] == ["ghost"]
    assert any(e.topic == "response_ops.restart_failed" for e in captured)


def test_dry_run_never_launches_side_effect(tmp_path):
    """dry_run=True must replace the restart launcher with a safe no-op."""
    sup = FleetSupervisor(
        services=[ServiceSpec("multiplayer", 8788, restart_cmd=["/bin/false"])],
        dry_run=True,
        probe_fn=lambda h, p, t: (False, None, "down"),
        log_path=tmp_path / "supervisor.log",
    )
    # internal restart fn must be the no-op (not subprocess) under dry_run
    assert sup.dry_run is True
    assert sup.restart(sup.services[0]) is True
    assert sup._restart_fn.__name__ == "<lambda>"


def test_watch_runs_bounded_iterations(tmp_path):
    calls = {"n": 0}

    def fake_probe(host, port, timeout):
        calls["n"] += 1
        return (True, 0.5, None)

    sup = FleetSupervisor(
        services=[ServiceSpec("a", 1)],
        dry_run=True,
        probe_fn=fake_probe,
        log_path=tmp_path / "supervisor.log",
    )
    sup.watch(interval=0.0, iterations=3)
    assert calls["n"] == 3
