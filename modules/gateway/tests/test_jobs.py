"""Hermetic tests for the gateway channel + scheduled-job wiring (jobs.py).

Proves the REAL end-to-end push path:
  * JobRegistry registers/list/unregisters named jobs bound to real callables.
  * JobScheduler runs due jobs on an injectable clock, tracking
    last_run / next_run / success, with interval + cron next-run math.
  * ChannelConfigLoader builds real Webhook/Telegram/Discord channels from a
    config dict (Telegram/Discord go through an injected fake opener so no
    third-party network is touched for those).
  * PushTest pushes a message through Gateway.send_with_retry to a LOCAL
    stdlib ``http.server`` echo on an **ephemeral port** — the real HTTP
    transport carries the payload end-to-end and the server records it.

These tests never touch the public internet; the only sockets opened are to
``127.0.0.1`` on an ephemeral port the test itself selects.
"""

from __future__ import annotations

import json
import sys
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_PROJECT_ROOT: Path = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from typing import TYPE_CHECKING, Never

from enterprise.modules.gateway import (  # noqa: E402
    ChannelConfigLoader,
    Gateway,
    JobRegistry,
    JobScheduler,
    push_test,
    wire_config,
)

if TYPE_CHECKING:
    from enterprise.modules.gateway.jobs import RegisteredJob

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def utc_ts(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> float:
    """Build a UTC timezone-aware epoch timestamp."""
    return datetime(year, month, day, hour, minute, tzinfo=UTC).timestamp()


class FakeClock:
    """Mutable injectable clock for the scheduler."""

    def __init__(self, start: float = 1_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, dt: float) -> None:
        self.now += dt


class RecordingRunnable:
    """Injectable runnable that records which jobs were executed."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, job: RegisteredJob) -> None:
        self.calls.append(job.id)


class RecordingOpener:
    """Fake opener that records requests without any network I/O.

    Imitates a urllib response with a ``.read()`` returning empty bytes.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes, dict]] = []

    def __call__(self, url: str, data: bytes, headers: dict):
        self.calls.append((url, data, headers))
        return _FakeResponse()


class _FakeResponse:
    def read(self) -> bytes:
        return b"{}"


@dataclass
class EchoServer:
    """A local stdlib http.server echo on an ephemeral port (hermetic)."""

    _httpd: ThreadingHTTPServer
    _thread: threading.Thread
    _payloads: list[dict] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def url(self) -> str:
        host, port = self._httpd.server_address
        return f"http://{host}:{port}/echo"

    def received(self) -> list[dict]:
        with self._lock:
            return list(self._payloads)

    def shutdown(self) -> None:
        self._httpd.shutdown()
        self._thread.join(timeout=5)
        self._httpd.server_close()


def start_echo_server() -> EchoServer:
    """Start an echo HTTP server bound to 127.0.0.1 on an ephemeral port."""

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 (stdlib handler naming)
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b""
            try:
                payload = json.loads(body.decode("utf-8"))
            except Exception:  # noqa: BLE001
                payload = {"raw": body.decode("utf-8", "replace")}
            server._payloads.append(payload)  # type: ignore[attr-defined]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

        def log_message(self, *args) -> None:  # silence stdlib request logging
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server = EchoServer(_httpd=httpd, _thread=threading.Thread())
    httpd.payloads = server._payloads  # type: ignore[attr-defined]
    server._thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server._thread.start()
    return server


# ===========================================================================
# JobRegistry — register / list / unregister real-callable jobs
# ===========================================================================


def _sentinel_job() -> list[str]:
    return []


class TestJobRegistry:
    def test_register_and_list(self) -> None:
        reg = JobRegistry()
        ran: list[str] = []

        def a() -> None:
            ran.append("a")

        def b() -> None:
            ran.append("b")

        reg.register("alpha", a, kind="interval", interval=60)
        reg.register("beta", b, kind="cron", expr="0 9 * * *")

        assert set(reg.names()) == {"alpha", "beta"}
        assert len(reg.list()) == 2
        assert {j.id for j in reg.list()} == {"alpha", "beta"}

    def test_register_replaces_duplicate(self) -> None:
        reg = JobRegistry()
        reg.register("dup", lambda: None, kind="interval", interval=1)
        reg.register("dup", lambda: None, kind="cron", expr="* * * * *")
        jobs = reg.list()
        assert len(jobs) == 1
        assert jobs[0].kind == "cron"

    def test_unregister_and_get(self) -> None:
        reg = JobRegistry()
        reg.register("x", lambda: None, kind="interval", interval=5)
        job = reg.get("x")
        assert job is not None
        assert job.id == "x"
        removed = reg.unregister("x")
        assert removed is not None
        assert reg.get("x") is None
        assert len(reg) == 0

    def test_job_run_state_snapshot(self) -> None:
        reg = JobRegistry()
        job = reg.register("s", lambda: None, kind="interval", interval=10)
        job.last_run = 100.0
        job.next_run = 110.0
        job.success = True
        state = job.run_state
        assert state["id"] == "s"
        assert state["interval"] == 10
        assert state["last_run"] == 100.0
        assert state["next_run"] == 110.0
        assert state["success"] is True


# ===========================================================================
# JobScheduler — due detection, injected clock, last_run/next_run/success
# ===========================================================================


class TestJobScheduler:
    def test_never_run_job_is_due_immediately(self) -> None:
        clock = FakeClock(1000.0)
        sched = JobScheduler(clock=clock)
        sched.register("j", lambda: None, kind="interval", interval=60)
        assert [j.id for j in sched.due(1000.0)] == ["j"]

    def test_runs_due_interval_job_and_tracks_last_run(self) -> None:
        clock = FakeClock(1000.0)
        ran: list[str] = []
        sched = JobScheduler(clock=clock, runnable=RecordingRunnable())
        sched.register("j", lambda: ran.append("x"), kind="interval", interval=60)

        result = sched.run_due(1000.0)
        assert [j.id for j in result] == ["j"]
        job = sched.registry.get("j")
        assert job is not None
        assert job.last_run == 1000.0
        assert job.next_run == 1060.0

        # Not due again until the interval elapses.
        assert sched.due(1059.0) == []
        assert [j.id for j in sched.due(1060.0)] == ["j"]

    def test_injectable_runnable_records_calls(self) -> None:
        recorder = RecordingRunnable()
        sched = JobScheduler(runnable=recorder)
        sched.register("a", lambda: None, kind="interval", interval=60)
        sched.register("b", lambda: None, kind="cron", expr="* * * * *")
        sched.run_due(2000.0)
        assert recorder.calls == ["a", "b"]

    def test_run_job_tracks_success_and_next_run(self) -> None:
        calls: list[str] = []

        def ok() -> None:
            calls.append("ok")

        def bad() -> Never:
            msg = "boom"
            raise RuntimeError(msg)

        sched = JobScheduler()
        good = sched.register("g", ok, kind="interval", interval=30)
        bad_job = sched.register("b", bad, kind="interval", interval=30)
        sched.run_job(good, 5000.0)
        sched.run_job(bad_job, 5000.0)
        assert good.success is True
        assert good.last_error is None
        assert bad_job.success is False
        assert bad_job.last_error == "boom"

    def test_disabled_job_is_never_due(self) -> None:
        sched = JobScheduler()
        sched.register("d", lambda: None, kind="interval", interval=60, enabled=False)
        assert sched.due(1234.0) == []

    def test_tick_once_returns_run_count(self) -> None:
        sched = JobScheduler()
        sched.register("a", lambda: None, kind="interval", interval=60)
        assert sched.tick_once(3000.0) == 1
        assert sched.tick_once(3000.0) == 0  # just ran, not due again


# ===========================================================================
# Next-run computation — interval + cron
# ===========================================================================


class TestNextRun:
    def test_interval_next_run_computation(self) -> None:
        sched = JobScheduler()
        job = sched.register("i", lambda: None, kind="interval", interval=300)
        job.last_run = 1000.0
        assert sched.next_run(job, 1000.0) == 1300.0
        assert sched.next_run(job, 1299.0) == 1300.0

    def test_cron_next_run_computation(self) -> None:
        sched = JobScheduler()
        job = sched.register("c", lambda: None, kind="cron", expr="0 9 * * *")
        base = utc_ts(2026, 1, 1, 8, 0)  # before 09:00
        nxt = sched.next_run(job, base)
        assert nxt == utc_ts(2026, 1, 1, 9, 0)

    def test_cron_next_run_strictly_after_last_run(self) -> None:
        sched = JobScheduler()
        job = sched.register("c", lambda: None, kind="cron", expr="30 14 * * *")
        job.last_run = utc_ts(2026, 1, 1, 14, 30)
        nxt = sched.next_run(job, job.last_run)
        assert nxt == utc_ts(2026, 1, 2, 14, 30)

    def test_cron_job_due_at_scheduled_time(self) -> None:
        clock = FakeClock(utc_ts(2026, 1, 1, 9, 0))
        sched = JobScheduler(clock=clock, runnable=RecordingRunnable())
        job = sched.register("c", lambda: None, kind="cron", expr="0 9 * * *")
        assert [j.id for j in sched.due(clock.now)] == ["c"]
        sched.run_due(clock.now)
        assert job.last_run == utc_ts(2026, 1, 1, 9, 0)
        # Not due again until tomorrow 09:00
        assert sched.due(clock.now) == []


# ===========================================================================
# ChannelConfigLoader — build real channels from a config dict
# ===========================================================================


class TestChannelConfigLoader:
    def test_loads_webhook_channel(self) -> None:
        loader = ChannelConfigLoader(Gateway())
        n = loader.load({"alerts": {"type": "webhook", "url": "http://example.test/h"}})
        assert n == 1
        ch = loader.gateway.get_channels().get("alerts")
        assert ch is not None
        assert ch.recipient == "http://example.test/h"

    def test_loads_telegram_and_discord(self) -> None:
        loader = ChannelConfigLoader(Gateway())
        cfg = {
            "tg": {"type": "telegram", "token": "t", "chat_id": "42"},
            "dc": {"type": "discord", "webhook_url": "http://discord.test/w"},
        }
        assert loader.load(cfg) == 2
        assert set(loader.gateway.get_channels().keys()) == {"tg", "dc"}

    def test_skips_unconfigured_channels(self) -> None:
        loader = ChannelConfigLoader(Gateway())
        cfg = {
            "badtype": {"type": "carrier-pigeon"},
            "notg": {"type": "telegram"},  # missing token/chat_id -> disabled
            "ok": {"type": "webhook", "url": "http://example.test/w"},
        }
        assert loader.load(cfg) == 1
        assert set(loader.gateway.get_channels().keys()) == {"ok"}

    def test_load_from_config_section(self) -> None:
        loader = ChannelConfigLoader(Gateway())
        n = loader.load_from_config(
            {"channels": {"ops": {"type": "webhook", "url": "http://e.test/o"}}}
        )
        assert n == 1


# ===========================================================================
# PushTest — REAL end-to-end push over the HTTP transport (hermetic)
# ===========================================================================


class TestPushTestRealHttp:
    def test_push_test_delivers_over_real_http_and_server_receives_payload(self) -> None:
        server = start_echo_server()
        try:
            gateway = Gateway()
            loader = ChannelConfigLoader(gateway=gateway)
            assert loader.load({"echo": {"type": "webhook", "url": server.url}}) == 1

            receipt = push_test(gateway, "echo", "hello over real http")

            assert receipt.passed is True
            assert receipt.status.value == "delivered"
            # The local echo server actually received the payload bytes.
            received = server.received()
            assert len(received) == 1
            assert received[0]["text"] == "hello over real http"
        finally:
            server.shutdown()

    def test_send_with_retry_succeeds_over_real_http(self) -> None:
        server = start_echo_server()
        try:
            gateway = Gateway()
            from enterprise.modules.gateway import build_channel

            gateway.register_channel("echo", build_channel("webhook", {"url": server.url}))
            receipt = gateway.send_with_retry("echo", "retried payload")
            assert receipt.passed is True
            assert receipt.attempts == 1
            assert len(server.received()) == 1
            assert server.received()[0]["text"] == "retried payload"
        finally:
            server.shutdown()

    def test_telegram_discord_use_fake_opener_no_network(self) -> None:
        # Telegram/Discord cannot talk to a real public API in a hermetic test,
        # so we prove they route through an injected opener that records instead.
        gateway = Gateway()
        loader = ChannelConfigLoader(gateway=gateway)
        opener = RecordingOpener()
        loader.load(
            {
                "tg": {"type": "telegram", "token": "T", "chat_id": "1"},
                "dc": {"type": "discord", "webhook_url": "http://dc.test/w"},
            },
            opener=opener,
        )
        gateway.send("tg", "tg msg")
        gateway.send("dc", "dc msg")
        assert len(opener.calls) == 2
        assert "api.telegram.org" in opener.calls[0][0]
        assert opener.calls[1][0] == "http://dc.test/w"


# ===========================================================================
# End-to-end wiring — wire_config
# ===========================================================================


class TestWireConfig:
    def test_wire_config_populates_gateway_and_jobs(self) -> None:
        gateway = Gateway()
        sched = JobScheduler()
        summary = wire_config(
            gateway,
            sched,
            {
                "channels": {"ops": {"type": "webhook", "url": "http://example.test/o"}},
                "jobs": [
                    {
                        "id": "daily_universal_score",
                        "kind": "cron",
                        "expr": "0 9 * * *",
                        "callback": "report_universal_score",
                    }
                ],
            },
        )
        assert summary == {"channels": 1, "jobs": 1}
        assert "ops" in gateway.get_channels()
        assert sched.registry.get("daily_universal_score") is not None
        assert sched.registry.get("daily_universal_score").kind == "cron"

    def test_wire_config_is_non_destructive_when_empty(self) -> None:
        gateway = Gateway()
        sched = JobScheduler()
        summary = wire_config(gateway, sched, {})
        assert summary == {"channels": 0, "jobs": 0}
        assert gateway.get_channels() == {}
        assert len(sched.registry) == 0
