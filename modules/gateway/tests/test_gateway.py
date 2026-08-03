"""Unit tests for the ENI gateway enterprise module.

Covers:
  - Module registration via @module decorator (name/version/registry).
  - Gateway register/broadcast/route using an in-memory FakeChannel (no network).
  - ChannelRegistry metric accounting.
  - Pure cron_next() with known UTC cases.
  - Scheduler.due + mark_run ordering and semantics.
  - Telegram/Discord/Webhook adapters building correct URL/body via an injected
    fake opener — proving NO real network is ever touched.
  - Module lifecycle (initialize/health_check/shutdown) with event emission.

All channel transports are exercised through injected fakes; no sockets are
opened by these tests.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

_PROJECT_ROOT: Path = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from enterprise.modules.gateway import (  # noqa: E402
    DiscordChannel,
    Gateway,
    GatewayModule,
    Scheduler,
    TelegramChannel,
    WebhookChannel,
    cron_next,
    interval_next,
)
from enterprise.modules.gateway.gateway import (  # noqa: E402
    Channel,
    GatewayResult,
    Job,
)
from enterprise.platform_kernel import _MODULE_REGISTRY, HealthStatus  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def utc_ts(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> float:
    """Build a UTC timezone-aware epoch timestamp."""
    return datetime(year, month, day, hour, minute, tzinfo=UTC).timestamp()


class FakeChannel(Channel):
    """In-memory capturing channel: records messages, never hits the network."""

    def __init__(self, name: str = "", ok: bool = True) -> None:
        self.name = name
        self._ok = ok
        self.messages: list[str] = []

    @property
    def enabled(self) -> bool:
        return True

    @property
    def recipient(self) -> str:
        return f"fake:{self.name}"

    def send(self, message: str) -> GatewayResult:
        if self._ok:
            self.messages.append(message)
            return GatewayResult(ok=True, channel=self.name, recipient=self.recipient, message=message)
        return GatewayResult(
            ok=False, channel=self.name, recipient=self.recipient,
            error="fake failure", message=message,
        )


class RecordingOpener:
    """Fake http opener that records requests and returns a 200-like response."""

    def __init__(self, status: int = 200) -> None:
        self.status = status
        self.calls: list[dict[str, Any]] = []

    def __call__(self, url: str, data: bytes, headers: dict[str, str]) -> Any:
        self.calls.append({"url": url, "data": data, "headers": headers})
        return self._FakeResponse(self.status)

    class _FakeResponse:
        def __init__(self, status: int) -> None:
            self.status = status

        def read(self) -> bytes:
            return b"{}"

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def last(self) -> dict[str, Any]:
        return self.calls[-1]


# ===========================================================================
# Module registration
# ===========================================================================


class TestModuleRegistration:
    def test_module_decorator_registers(self):
        assert "gateway" in _MODULE_REGISTRY
        assert _MODULE_REGISTRY["gateway"] is GatewayModule

    def test_module_instance_metadata(self):
        mod = GatewayModule()
        assert mod.name == "gateway"
        assert mod.version == "1.0.0"

    def test_module_initial_status_unknown(self):
        mod = GatewayModule()
        assert mod.status == HealthStatus.UNKNOWN

    def test_exports_as_documented(self):
        import enterprise.modules.gateway as gw

        expected = {
            "GatewayModule", "Gateway", "Scheduler", "Job",
            "TelegramChannel", "DiscordChannel", "WebhookChannel",
        }
        assert expected <= set(gw.__all__)

    def test_module_has_semver_version(self):
        import enterprise.modules.gateway as gw

        parts = gw.__version__.split(".")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)


# ===========================================================================
# Gateway: register / send / broadcast / route (FakeChannel)
# ===========================================================================


class TestGateway:
    def test_register_and_get_channels(self):
        gw = Gateway()
        gw.register_channel("alerts", FakeChannel("alerts"))
        gw.register_channel("ops", FakeChannel("ops"))
        assert set(gw.get_channels().keys()) == {"alerts", "ops"}

    def test_unregister_channel(self):
        gw = Gateway()
        gw.register_channel("a", FakeChannel("a"))
        removed = gw.unregister_channel("a")
        assert removed is not None
        assert list(gw.get_channels().keys()) == []
        assert gw.unregister_channel("a") is None  # idempotent

    def test_send_delivers_to_channel(self):
        gw = Gateway()
        ch = FakeChannel("a")
        gw.register_channel("a", ch)
        result = gw.send("a", "hello")
        assert result.ok is True
        assert ch.messages == ["hello"]
        assert gw.registry.send_count("a") == 1

    def test_send_unknown_channel_returns_error_result(self):
        gw = Gateway()
        result = gw.send("nope", "hi")
        assert result.ok is False
        assert result.error is not None

    def test_broadcast_to_all_channels(self):
        gw = Gateway()
        a, b, c = FakeChannel("a"), FakeChannel("b"), FakeChannel("c")
        gw.register_channel("a", a)
        gw.register_channel("b", b)
        gw.register_channel("c", c)
        results = gw.broadcast("everyone")
        assert all(r.ok for r in results)
        assert len(results) == 3
        assert a.messages == ["everyone"]
        assert b.messages == ["everyone"]
        assert c.messages == ["everyone"]

    def test_route_sends_to_matching_channels_only(self):
        gw = Gateway()
        a, b, c = FakeChannel("a"), FakeChannel("b"), FakeChannel("c")
        gw.register_channel("a", a)
        gw.register_channel("b", b)
        gw.register_channel("c", c)
        routing = {"alert.critical": ["a", "c"]}
        results = gw.route(routing, "alert.critical", "p1")
        assert len(results) == 2
        assert a.messages == ["p1"]
        assert c.messages == ["p1"]
        assert b.messages == []

    def test_route_unknown_topic_returns_empty(self):
        gw = Gateway()
        gw.register_channel("a", FakeChannel("a"))
        results = gw.route({"x": ["a"]}, "not.here", "hi")
        assert results == []

    def test_failed_channel_counts_error_not_send(self):
        gw = Gateway()
        bad = FakeChannel("bad", ok=False)
        gw.register_channel("bad", bad)
        result = gw.send("bad", "boom")
        assert result.ok is False
        assert gw.registry.error_count("bad") == 1
        assert gw.registry.send_count("bad") == 0

    def test_channel_registry_metrics(self):
        gw = Gateway()
        gw.register_channel("a", FakeChannel("a"))
        gw.send("a", "m1")
        gw.send("a", "m2")
        metrics = gw.registry.metrics()
        assert metrics["total_sends"] == 2
        assert metrics["sends"]["a"] == 2


# ===========================================================================
# cron_next (pure, UTC)
# ===========================================================================


class TestCronNext:
    def test_every_minute_advances_60s(self):
        base = utc_ts(2025, 1, 1, 0, 0)
        nxt = cron_next("* * * * *", base)
        assert nxt == base + 60

    def test_every_minute_from_mid_minute(self):
        base = utc_ts(2025, 1, 1, 0, 0) + 30
        nxt = cron_next("* * * * *", base)
        assert nxt == utc_ts(2025, 1, 1, 0, 1)

    def test_top_of_hour(self):
        # '0 * * * *' means minute==0 of every hour.
        base = utc_ts(2025, 1, 1, 10, 5)
        nxt = cron_next("0 * * * *", base)
        assert nxt == utc_ts(2025, 1, 1, 11, 0)

    def test_specific_minute_each_hour(self):
        base = utc_ts(2025, 1, 1, 10, 0)
        nxt = cron_next("30 * * * *", base)
        assert nxt == utc_ts(2025, 1, 1, 10, 30)

    def test_daily_at_midnight(self):
        base = utc_ts(2025, 1, 1, 12, 0)
        nxt = cron_next("0 0 * * *", base)
        assert nxt == utc_ts(2025, 1, 2, 0, 0)

    def test_dow_sunday_zero(self):
        # 2025-01-05 is a Sunday. '0 9 * * 0' -> next Sunday 09:00.
        base = utc_ts(2025, 1, 1, 0, 0)  # Wednesday
        nxt = cron_next("0 9 * * 0", base)
        assert nxt == utc_ts(2025, 1, 5, 9, 0)

    def test_dow_seven_equals_sunday(self):
        base = utc_ts(2025, 1, 1, 0, 0)
        nxt = cron_next("0 9 * * 7", base)
        assert nxt == utc_ts(2025, 1, 5, 9, 0)

    def test_dow_monday_matches(self):
        # 2025-01-06 is Monday.
        base = utc_ts(2025, 1, 1, 0, 0)
        nxt = cron_next("0 0 * * 1", base)
        assert nxt == utc_ts(2025, 1, 6, 0, 0)

    def test_weekday_dow(self):
        # dow 1-5 handled as simple list.
        base = utc_ts(2025, 1, 1, 0, 0)  # Wednesday
        nxt = cron_next("0 9 * * 1,2,3,4,5", base)
        assert nxt == utc_ts(2025, 1, 1, 9, 0)

    def test_list_minutes(self):
        base = utc_ts(2025, 1, 1, 0, 0)
        nxt = cron_next("0,30 * * * *", base)
        # 00:00 is exactly the base; strictly after => 00:30
        assert nxt == utc_ts(2025, 1, 1, 0, 30)

    def test_list_months(self):
        base = utc_ts(2025, 12, 1, 0, 0)
        nxt = cron_next("0 0 1 1,7 *", base)
        assert nxt == utc_ts(2026, 1, 1, 0, 0)

    def test_feb_30_impossible_returns_none(self):
        base = utc_ts(2025, 1, 1, 0, 0)
        assert cron_next("0 0 30 2 *", base) is None

    def test_invalid_field_count_returns_none(self):
        assert cron_next("0 0 * *", 0.0) is None

    def test_matches_are_strictly_after_from_ts(self):
        base = utc_ts(2025, 1, 1, 0, 0)
        nxt = cron_next("0 0 * * *", base)
        assert nxt > base


# ===========================================================================
# interval_next helper
# ===========================================================================


class TestIntervalNext:
    def test_first_run_from_never_run(self):
        # never run => next interval is at from_ts + interval
        assert interval_next(60, None, 1000.0) == 1060.0

    def test_next_after_last_run(self):
        assert interval_next(60, 1000.0, 1000.0) == 1060.0

    def test_aligns_past_due(self):
        # last run 1000, interval 60, now 1090 => next multiple >= now is 1120
        assert interval_next(60, 1000.0, 1090.0) == 1120.0

    def test_zero_interval_returns_from_ts(self):
        assert interval_next(0, 100.0, 500.0) == 500.0


# ===========================================================================
# Scheduler
# ===========================================================================


class TestScheduler:
    def test_upsert_and_get(self):
        s = Scheduler()
        job = Job(id="j1", kind="cron", expr="* * * * *", callback="cb")
        s.upsert(job)
        assert s.get("j1") is job
        assert len(s.all()) == 1

    def test_upsert_replaces_same_id(self):
        s = Scheduler()
        s.upsert(Job(id="j1", kind="cron", expr="* * * * *"))
        s.upsert(Job(id="j1", kind="interval", interval=10))
        assert len(s.all()) == 1
        assert s.get("j1").kind == "interval"

    def test_remove(self):
        s = Scheduler()
        s.upsert(Job(id="j1", kind="cron", expr="* * * * *"))
        assert s.remove("j1") is not None
        assert s.get("j1") is None
        assert s.remove("j1") is None

    def test_due_every_minute_job_never_run_is_due(self):
        s = Scheduler()
        s.upsert(Job(id="j1", kind="cron", expr="* * * * *", callback="cb"))
        now = utc_ts(2025, 1, 1, 0, 0)
        # never run => due immediately (first fire scheduled for now)
        assert [j.id for j in s.due(now)] == ["j1"]

    def test_mark_run_prevents_refire_at_same_time(self):
        s = Scheduler()
        job = Job(id="j1", kind="cron", expr="* * * * *")
        s.upsert(job)
        now = utc_ts(2025, 1, 1, 0, 0)
        # fire it at 00:00
        s.mark_run(job, now)
        # next occurrence is 00:01 > now => not due at 00:00
        assert s.due(now) == []
        # at 00:00:10 the 00:01 run still hasn't arrived => not due yet
        assert s.due(now + 10) == []
        # as soon as we pass 00:01 it becomes due again
        assert [j.id for j in s.due(now + 60)] == ["j1"]
        assert s.get("j1").last_run == now

    def test_due_interval_job(self):
        s = Scheduler()
        job = Job(id="hb", kind="interval", interval=60)
        s.upsert(job)
        now = 1000.0
        # never run => due immediately
        assert [j.id for j in s.due(now)] == ["hb"]
        # after running at now, not due again until now+interval
        s.mark_run(job, now)
        assert s.due(now) == []
        assert s.due(now + 59) == []
        assert [j.id for j in s.due(now + 60)] == ["hb"]

    def test_disabled_job_not_due(self):
        s = Scheduler()
        s.upsert(Job(id="off", kind="interval", interval=0, enabled=False))
        assert s.due(10**9) == []

    def test_due_orders_by_next_run(self):
        s = Scheduler()
        base = utc_ts(2025, 1, 1, 0, 0)
        # minutely next at 00:01; 0,30-minutely next at 00:30
        s.upsert(Job(id="d0", kind="cron", expr="0,30 * * * *"))
        s.upsert(Job(id="m", kind="cron", expr="* * * * *"))
        for job in s.all():
            s.mark_run(job, base)
        # at 00:30 both are due; minutely (next=00:01) fires before 0,30 (00:30)
        due = s.due(base + 30 * 60)
        assert [j.id for j in due] == ["m", "d0"]

    def test_due_cron_at_tight_boundary(self):
        s = Scheduler()
        job = Job(id="top", kind="cron", expr="0 * * * *")
        s.upsert(job)
        now = utc_ts(2025, 1, 1, 10, 0)
        s.mark_run(job, now - 3600)  # ran at 09:00
        # next occurrence is 10:00 (after last) => not due before 10:00
        assert s.due(now - 1) == []
        # at exactly 10:00 the job is due
        assert [j.id for j in s.due(now)] == ["top"]
        s.mark_run(job, now)
        assert s.due(now) == []


# ===========================================================================
# Channel adapters via injected fake opener (no real network)
# ===========================================================================


class TestTelegramChannel:
    def test_builds_correct_url_body(self):
        opener = RecordingOpener(200)
        ch = TelegramChannel(token="TOK123", chat_id="5678", opener=opener)
        result = ch.send("hi there")
        assert result.ok is True
        assert opener.call_count == 1
        call = opener.last()
        assert call["url"] == "https://api.telegram.org/botTOK123/sendMessage"
        import json

        assert json.loads(call["data"]) == {"chat_id": "5678", "text": "hi there"}
        assert call["headers"]["Content-Type"] == "application/json"

    def test_not_configured_returns_error_no_network(self):
        opener = RecordingOpener()
        ch = TelegramChannel(token=None, chat_id=None, opener=opener)
        result = ch.send("x")
        assert result.ok is False
        assert opener.call_count == 0

    def test_opener_error_returns_result_not_raise(self):
        def bad_opener(url, data, headers):
            raise OSError("connection refused")

        ch = TelegramChannel(token="T", chat_id="1", opener=bad_opener)
        result = ch.send("hi")
        assert result.ok is False
        assert "connection refused" in result.error


class TestDiscordChannel:
    def test_builds_correct_url_body(self):
        opener = RecordingOpener(200)
        ch = DiscordChannel(webhook_url="https://discord.com/api/webhooks/abc/xyz", opener=opener)
        result = ch.send("discord msg")
        assert result.ok is True
        call = opener.last()
        assert call["url"] == "https://discord.com/api/webhooks/abc/xyz"
        import json

        assert json.loads(call["data"]) == {"content": "discord msg"}

    def test_not_configured_returns_error(self):
        opener = RecordingOpener()
        ch = DiscordChannel(webhook_url=None, opener=opener)
        result = ch.send("x")
        assert result.ok is False
        assert opener.call_count == 0


class TestWebhookChannel:
    def test_builds_correct_url_body_headers(self):
        opener = RecordingOpener(200)
        ch = WebhookChannel(
            url="https://example.com/hook",
            headers={"Authorization": "Bearer sekret"},
            opener=opener,
        )
        result = ch.send("webhook msg")
        assert result.ok is True
        call = opener.last()
        assert call["url"] == "https://example.com/hook"
        import json

        assert json.loads(call["data"]) == {"text": "webhook msg"}
        assert call["headers"]["Authorization"] == "Bearer sekret"


# ===========================================================================
# Module lifecycle + event emission
# ===========================================================================


class TestGatewayModuleLifecycle:
    async def test_initialize_builds_channels_and_jobs(self):
        mod = GatewayModule(
            config={
                "channels": {
                    "alerts": {"type": "telegram", "token": "T", "chat_id": "1"},
                    "ops": {"type": "discord", "webhook_url": "https://x/y"},
                    "web": {"type": "webhook", "url": "https://example.com/h"},
                },
                "jobs": [
                    {"id": "j1", "kind": "cron", "expr": "* * * * *", "callback": "cb1"},
                    {"id": "j2", "kind": "interval", "interval": 300, "callback": "cb2"},
                ],
            }
        )
        await mod.initialize()
        assert mod.status == HealthStatus.HEALTHY
        assert set(mod.gateway.get_channels().keys()) == {"alerts", "ops", "web"}
        assert len(mod.scheduler.all()) == 2

    async def test_initialize_tolerates_missing_config(self):
        mod = GatewayModule(config={})
        await mod.initialize()
        assert mod.status == HealthStatus.HEALTHY
        assert mod.gateway.get_channels() == {}
        assert mod.scheduler.all() == []

    async def test_initialize_skips_invalid_channels_but_keeps_valid(self):
        mod = GatewayModule(
            config={
                "channels": {
                    "bad": {"type": "slack"},  # unknown type -> skipped
                    "noconfig": "not a dict",  # invalid shape -> skipped
                    "good": {"type": "telegram", "token": "T", "chat_id": "1"},
                }
            }
        )
        await mod.initialize()
        assert set(mod.gateway.get_channels().keys()) == {"good"}

    async def test_initialize_skips_unconfigured_channel(self):
        mod = GatewayModule(
            config={"channels": {"empty": {"type": "telegram"}}}  # missing token/chat_id
        )
        await mod.initialize()
        assert mod.gateway.get_channels() == {}

    async def test_health_check_after_initialize(self):
        mod = GatewayModule(config={})
        await mod.initialize()
        assert await mod.health_check() == HealthStatus.HEALTHY

    async def test_health_check_before_initialize_unknown(self):
        mod = GatewayModule(config={})
        assert await mod.health_check() == HealthStatus.UNKNOWN

    async def test_shutdown_clears_state(self):
        mod = GatewayModule(config={})
        await mod.initialize()
        await mod.shutdown()
        assert mod.gateway is None
        assert mod.scheduler is None

    async def test_send_emits_gateway_message_sent_event(self):
        mock_bus = MagicMock()
        mod = GatewayModule(config={})
        mod.set_event_bus(mock_bus)
        await mod.initialize()
        # Register an in-memory channel so sending never touches the network.
        fake = FakeChannel("alerts")
        mod.gateway.register_channel("alerts", fake)
        result = mod.gateway.send("alerts", "boom")
        assert result.ok is True
        assert fake.messages == ["boom"]
        assert mock_bus.publish.call_count >= 1

    async def test_send_without_event_bus_is_noop(self):
        mod = GatewayModule(config={})
        await mod.initialize()
        # no event bus wired; sending to unknown channel must not raise
        result = mod.gateway.send("nope", "x")
        assert result.ok is False
