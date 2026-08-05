"""Master-class tests for the gateway delivery-resilience layer.

Covers:
  - Stub elimination: recipient is a real configurable/derived value for the
    base Channel and every concrete channel (never a bare "" when configured).
  - DeliveryPolicy backoff timing (exponential, with a recording sleeper).
  - send_with_retry: transient failure -> retry -> success.
  - send_with_retry: permanent exhaustion -> FAILED with correct fields.
  - DeliveryReceipt fields (passed/attempts/last_error/latency_ms).
  - GatewayRouter: route by name, handoff to fallback after N failures.
  - Outbox: enqueue/dequeue/drain with delivered/failed/retried stats.
  - Gateway.send_with_retry integration.
  - Module __all__ / API surface for the new layer.

All time-dependent behavior is driven through an injected ``sleep_fn`` so no
test ever actually sleeps.
"""

from __future__ import annotations

import enterprise.modules.gateway as gw
from enterprise.modules.gateway import (
    DeliveryPolicy,
    DeliveryStatus,
    DiscordChannel,
    Gateway,
    GatewayRouter,
    Outbox,
    TelegramChannel,
    WebhookChannel,
    send_with_retry,
)
from enterprise.modules.gateway.gateway import Channel, GatewayResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class RecordingSleeper:
    """Records every sleep delay so backoff timing can be asserted."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    def __call__(self, delay: float) -> None:
        self.delays.append(delay)


class FlakyChannel(Channel):
    """A channel that fails a configurable number of times before succeeding."""

    def __init__(
        self,
        name: str = "",
        fail_times: int = 0,
        enabled: bool = True,
        recipient: str = "",
    ) -> None:
        super().__init__(recipient=recipient)
        self.name = name
        self.fail_times = fail_times
        self._enabled = enabled
        self.calls = 0
        self.messages: list[str] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    def send(self, message: str) -> GatewayResult:
        self.calls += 1
        if not self._enabled:
            return GatewayResult(
                ok=False,
                channel=self.name,
                recipient=self.recipient,
                error="permanent: channel disabled",
                message=message,
            )
        if self.calls <= self.fail_times:
            return GatewayResult(
                ok=False,
                channel=self.name,
                recipient=self.recipient,
                error="transient: upstream timeout",
                message=message,
            )
        self.messages.append(message)
        return GatewayResult(
            ok=True,
            channel=self.name,
            recipient=self.recipient,
            message=message,
        )


# ===========================================================================
# Stub elimination: real recipients
# ===========================================================================


class TestRecipientStubEliminated:
    def test_base_channel_derives_recipient(self) -> None:
        ch = FlakyChannel(name="alerts")
        assert ch.recipient != ""
        assert ch.recipient.startswith("flakychannel:")

    def test_base_channel_configurable_recipient(self) -> None:
        ch = FlakyChannel(recipient="explicit:destination")
        assert ch.recipient == "explicit:destination"

    def test_telegram_recipient_is_chat_id(self) -> None:
        ch = TelegramChannel(token="T", chat_id="123456")
        assert ch.recipient == "123456"
        assert ch.recipient != ""

    def test_discord_recipient_is_webhook_url(self) -> None:
        ch = DiscordChannel(webhook_url="https://discord.com/api/webhooks/a/b")
        assert ch.recipient == "https://discord.com/api/webhooks/a/b"

    def test_webhook_recipient_is_endpoint_url(self) -> None:
        ch = WebhookChannel(url="https://example.com/hook")
        assert ch.recipient == "https://example.com/hook"
        assert ch.recipient != ""

    def test_configured_channels_via_factory_report_recipient(self) -> None:
        spec = {"token": "T", "chat_id": "42"}
        ch = gw.build_channel("telegram", spec)
        assert ch is not None
        assert ch.enabled
        assert ch.recipient == "42"


# ===========================================================================
# DeliveryPolicy backoff timing
# ===========================================================================


class TestDeliveryPolicy:
    def test_delay_expands_exponentially(self) -> None:
        policy = DeliveryPolicy(max_retries=3, base_backoff_seconds=0.1, backoff_factor=2.0)
        assert policy.delay_for(1) == 0.1
        assert policy.delay_for(2) == 0.2
        assert policy.delay_for(3) == 0.4

    def test_delay_respects_cap(self) -> None:
        policy = DeliveryPolicy(
            max_retries=5,
            base_backoff_seconds=4.0,
            backoff_factor=2.0,
            max_backoff_seconds=5.0,
        )
        # raw would be 4, 8, 16 ... but capped at 5.0
        assert policy.delay_for(1) == 4.0
        assert policy.delay_for(2) == 5.0
        assert policy.delay_for(3) == 5.0

    def test_default_policy_is_sane(self) -> None:
        policy = DeliveryPolicy()
        assert policy.max_retries >= 1
        assert policy.base_backoff_seconds > 0
        assert policy.backoff_factor >= 1.0


# ===========================================================================
# send_with_retry: retry semantics + receipts
# ===========================================================================


class TestSendWithRetry:
    def test_success_first_try(self) -> None:
        sleeper = RecordingSleeper()
        ch = FlakyChannel(name="ok", fail_times=0)
        receipt = send_with_retry(ch, "hi", sleep_fn=sleeper)
        assert receipt.passed is True
        assert receipt.status == DeliveryStatus.DELIVERED
        assert receipt.attempts == 1
        assert sleeper.delays == []
        assert ch.messages == ["hi"]

    def test_retries_transient_then_succeeds(self) -> None:
        sleeper = RecordingSleeper()
        ch = FlakyChannel(name="flaky", fail_times=2)
        receipt = send_with_retry(
            ch,
            "msg",
            policy=DeliveryPolicy(max_retries=4, base_backoff_seconds=0.01, backoff_factor=2.0),
            sleep_fn=sleeper,
        )
        assert receipt.passed is True
        assert receipt.attempts == 3
        assert len(sleeper.delays) == 2  # before retry #1 and #2
        assert ch.messages == ["msg"]

    def test_exhausts_retries_and_fails(self) -> None:
        sleeper = RecordingSleeper()
        ch = FlakyChannel(name="down", fail_times=99)
        policy = DeliveryPolicy(max_retries=2, base_backoff_seconds=0.01, backoff_factor=2.0)
        receipt = send_with_retry(ch, "oops", policy=policy, sleep_fn=sleeper)
        assert receipt.passed is False
        assert receipt.status == DeliveryStatus.FAILED
        assert receipt.attempts == 3  # 1 + max_retries
        assert len(sleeper.delays) == 2
        assert receipt.last_error is not None

    def test_does_not_retry_permanent_config_failure(self) -> None:
        sleeper = RecordingSleeper()
        ch = FlakyChannel(name="disabled", enabled=False)
        receipt = send_with_retry(ch, "x", policy=DeliveryPolicy(max_retries=5), sleep_fn=sleeper)
        assert receipt.passed is False
        assert receipt.attempts == 1
        assert sleeper.delays == []

    def test_receipt_fields_recorded(self) -> None:
        sleeper = RecordingSleeper()
        ch = FlakyChannel(name="abc", fail_times=1)
        receipt = send_with_retry(ch, "m", sleep_fn=sleeper, message_id="mid-1")
        assert receipt.message_id == "mid-1"
        assert receipt.channel == "abc"
        assert receipt.recipient == ch.recipient
        assert receipt.passed is True
        assert receipt.attempts == 2
        assert receipt.last_error is None  # series ended in success
        assert receipt.latency_ms >= 0.0
        assert isinstance(receipt.latency_ms, float)

    def test_backoff_timing_matches_exponential_sequence(self) -> None:
        sleeper = RecordingSleeper()
        ch = FlakyChannel(name="slow", fail_times=3)
        policy = DeliveryPolicy(max_retries=3, base_backoff_seconds=0.1, backoff_factor=2.0)
        send_with_retry(ch, "m", policy=policy, sleep_fn=sleeper)
        assert sleeper.delays == [0.1, 0.2, 0.4]

    def test_gateway_send_with_retry_integration(self) -> None:
        sleeper = RecordingSleeper()
        gateway = Gateway()
        flaky = FlakyChannel(name="p", fail_times=1)
        gateway.register_channel("p", flaky)
        receipt = gateway.send_with_retry("p", "integrated", sleep_fn=sleeper)
        assert receipt.passed is True
        assert receipt.attempts == 2
        assert flaky.messages == ["integrated"]


# ===========================================================================
# GatewayRouter + handoff
# ===========================================================================


class TestGatewayRouterHandoff:
    def test_route_success_no_handoff(self) -> None:
        sleeper = RecordingSleeper()
        router = GatewayRouter()
        primary = FlakyChannel(name="primary")
        router.registry.register("primary", primary)
        receipt = router.route("primary", "go", sleep_fn=sleeper)
        assert receipt.passed is True
        assert receipt.handed_off_to is None
        assert router.handoffs() == []

    def test_route_unknown_channel_returns_failed(self) -> None:
        router = GatewayRouter()
        receipt = router.route("nope", "x")
        assert receipt.passed is False
        assert receipt.status == DeliveryStatus.FAILED

    def test_handoff_to_fallback_after_primary_failure(self) -> None:
        sleeper = RecordingSleeper()
        router = GatewayRouter(
            default_policy=DeliveryPolicy(
                max_retries=1, base_backoff_seconds=0.001, backoff_factor=2.0
            )
        )
        # primary is permanently disabled -> no retries, triggers handoff
        primary = FlakyChannel(name="primary", enabled=False)
        fallback = FlakyChannel(name="fallback", fail_times=0)
        router.registry.register("primary", primary)
        router.registry.register("fallback", fallback)
        router.register_fallback("primary", "fallback")

        receipt = router.route("primary", "rescue", sleep_fn=sleeper)
        assert receipt.passed is True
        assert receipt.handed_off_to == "fallback"
        assert fallback.messages == ["rescue"]
        assert len(router.handoffs()) == 1
        assert router.handoffs()[0]["from"] == "primary"
        assert router.handoffs()[0]["to"] == "fallback"

    def test_no_handoff_when_no_fallback_registered(self) -> None:
        sleeper = RecordingSleeper()
        router = GatewayRouter()
        primary = FlakyChannel(name="primary", enabled=False)
        router.registry.register("primary", primary)
        receipt = router.route("primary", "x", sleep_fn=sleeper)
        assert receipt.passed is False
        assert receipt.handed_off_to is None
        assert router.handoffs() == []

    def test_gateway_router_shares_gateway_registry(self) -> None:
        gateway = Gateway()
        gateway.register_channel("a", FlakyChannel(name="a"))
        assert gateway.router.registry is gateway.registry
        receipt = gateway.router.route("a", "shared")
        assert receipt.passed is True


# ===========================================================================
# Outbox: enqueue / dequeue / drain / stats
# ===========================================================================


class TestOutbox:
    def test_enqueue_and_dequeue(self) -> None:
        outbox = Outbox()
        mid = outbox.enqueue("chan", "msg")
        assert outbox.size() == 1
        item = outbox.dequeue()
        assert item is not None
        chan, message, dequeued_id = item
        assert chan == "chan"
        assert message == "msg"
        assert dequeued_id == mid
        assert outbox.size() == 0
        assert outbox.dequeue() is None  # empty -> None

    def test_drain_delivers_and_counts(self) -> None:
        sleeper = RecordingSleeper()
        gateway = Gateway()
        ch = FlakyChannel(name="ok", fail_times=0)
        gateway.register_channel("ok", ch)
        outbox = Outbox(router=gateway.router)
        outbox.enqueue("ok", "m1")
        outbox.enqueue("ok", "m2")
        receipts = outbox.drain(sleep_fn=sleeper)
        assert len(receipts) == 2
        assert all(r.passed for r in receipts)
        assert ch.messages == ["m1", "m2"]
        stats = outbox.stats()
        assert stats["delivered"] == 2
        assert stats["failed"] == 0
        assert stats["retried"] == 0
        assert stats["queued"] == 0

    def test_drain_counts_failed_and_retried(self) -> None:
        sleeper = RecordingSleeper()
        gateway = Gateway()
        flaky = FlakyChannel(name="flaky", fail_times=1)
        gateway.register_channel("flaky", flaky)
        outbox = Outbox(router=gateway.router)
        outbox.enqueue("flaky", "m1")  # succeeds after 1 retry -> retried++
        outbox.enqueue("missing", "m2")  # unknown channel -> failed++
        receipts = outbox.drain(sleep_fn=sleeper)
        assert receipts[0].passed is True
        assert receipts[1].passed is False
        stats = outbox.stats()
        assert stats["delivered"] == 1
        assert stats["failed"] == 1
        assert stats["retried"] == 1

    def test_drain_with_no_router_marks_failed(self) -> None:
        outbox = Outbox()
        outbox.enqueue("x", "m")
        receipts = outbox.drain()
        assert len(receipts) == 1
        assert receipts[0].passed is False
        assert "no router" in receipts[0].last_error


# ===========================================================================
# API surface
# ===========================================================================


class TestDeliveryAPISurface:
    def test_new_symbols_exported(self) -> None:
        expected = {
            "DeliveryStatus",
            "DeliveryPolicy",
            "DeliveryReceipt",
            "send_with_retry",
            "GatewayRouter",
            "Outbox",
        }
        assert expected <= set(gw.__all__)

    def test_receipt_to_dict(self) -> None:
        ch = FlakyChannel(name="n", fail_times=0)
        receipt = send_with_retry(ch, "m", message_id="mid")
        d = receipt.to_dict()
        assert d["message_id"] == "mid"
        assert d["passed"] is True
        assert d["status"] == "delivered"
        assert d["attempts"] == 1

    def test_status_values(self) -> None:
        assert DeliveryStatus.DELIVERED.value == "delivered"
        assert DeliveryStatus.FAILED.value == "failed"
        assert DeliveryStatus.PENDING.value == "pending"
