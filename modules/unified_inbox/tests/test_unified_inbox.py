"""Tests for ENI Unified Inbox module (zero-AI cross-channel inbox).

Grounded in the JEVanClief "Clawdbot (Moltbot) Has 100K Stars. It Has Zero AI."
transcript.  Covers the deterministic, rule-based gateway pipeline: channel
registry, attention/priority triage, rule-based routing, cross-channel dedup,
authentication (allowlist), conversation sessions, the unified inbox listing,
scheduled output actions, and the optional (never required) external model hook.

All async tests use plain ``async def`` (project pytest asyncio_mode=auto).
No network, no external services, no file IO.
"""

from __future__ import annotations

import pytest

from enterprise.platform_kernel import HealthStatus, _MODULE_REGISTRY

from enterprise.modules.unified_inbox import (
    ChannelAdapter,
    CrossChannelInbox,
    InboundMessage,
    TriageDecision,
    UnifiedInboxModule,
    create_unified_inbox_module,
)


# ── Channel registry (transcript's "channel layer") ──────────────────────


def test_named_channels_match_transcript():
    """All platforms named in the transcript are registered channel adapters."""
    inbox = CrossChannelInbox()
    channels = set(inbox.list_channels())
    for expected in (
        "slack",
        "discord",
        "whatsapp",
        "telegram",
        "email",
        "calendar",
        "teams",
        "signal",
    ):
        assert expected in channels, f"missing channel: {expected}"


def test_channel_weights_override():
    inbox = CrossChannelInbox()
    assert inbox.channel_weight("whatsapp") == 70
    inbox.set_channel_weight("whatsapp", 90)
    assert inbox.channel_weight("whatsapp") == 90


def test_register_custom_channel():
    inbox = CrossChannelInbox()
    inbox.register_channel(ChannelAdapter(name="matrix", weight=33))
    assert "matrix" in inbox.list_channels()
    assert inbox.channel_weight("matrix") == 33


# ── Zero-AI: no model required ───────────────────────────────────────────


def test_routing_works_without_any_model():
    """The gateway must work with zero AI — no model hook ever required."""
    inbox = CrossChannelInbox()
    d = inbox.ingest(InboundMessage(channel="slack", sender="alice", text="hello"))
    assert d.accepted is True
    assert d.score >= 0  # deterministic score, never raises with no model


def test_optional_model_hook_is_external_and_non_blocking():
    """Moltbot keeps its AI external (bring-your-own key). Hook never required."""
    calls = []

    def hook(text, ctx):
        calls.append((text, ctx))
        return "ok"

    inbox = CrossChannelInbox()
    inbox.set_model_hook(hook)
    d = inbox.ingest(InboundMessage(channel="slack", sender="alice", text="@moltbot hi"))
    assert d.accepted is True
    assert len(calls) == 1
    assert "model-hook" in d.rules_fired

    # Without a hook the pipeline still routes perfectly (zero-AI thesis).
    inbox2 = CrossChannelInbox()
    d2 = inbox2.ingest(InboundMessage(channel="telegram", sender="bob", text="hi there"))
    assert d2.accepted is True


# ── Attention / priority triage ("every app wants your attention") ───────


def test_urgency_keyword_raises_attention():
    inbox = CrossChannelInbox()
    urgent = inbox.ingest(
        InboundMessage(channel="slack", sender="alice", text="URGENT: outage on prod")
    )
    calm = inbox.ingest(
        InboundMessage(channel="slack", sender="alice", text="just a friendly hello")
    )
    assert urgent.score > calm.score
    assert urgent.priority in ("critical", "high")
    assert any(r.startswith("kw:") for r in urgent.rules_fired)


def test_addressed_and_priority_sender_bonuses():
    inbox = CrossChannelInbox()
    add = inbox.ingest(InboundMessage(channel="slack", sender="bob", text="@moltbot status?"))
    plain = inbox.ingest(InboundMessage(channel="slack", sender="bob", text="status?"))
    assert add.score > plain.score
    assert "addressed" in add.rules_fired

    boss = inbox.ingest(InboundMessage(channel="slack", sender="boss", text="hi"))
    assert "sender:priority" in boss.rules_fired


def test_priority_labels_bracket_scores():
    inbox = CrossChannelInbox()
    critical = inbox.ingest(
        InboundMessage(channel="whatsapp", sender="oncall", text="P1 CRITICAL outage now @moltbot")
    )
    low = inbox.ingest(InboundMessage(channel="email", sender="newsletter", text="weekly digest"))
    assert critical.priority == "critical"
    assert low.priority == "low"


# ── Rule-based routing (gateway: "it decides where it goes") ─────────────


def test_calendar_intent_routes_to_calendar_channel():
    inbox = CrossChannelInbox()
    d = inbox.ingest(
        InboundMessage(channel="slack", sender="alice", text="please check my calendar for tomorrow")
    )
    assert d.route_channel == "calendar"
    assert d.action == "schedule"


def test_critical_routes_as_alert_to_top_channel():
    inbox = CrossChannelInbox()
    d = inbox.ingest(
        InboundMessage(channel="email", sender="oncall", text="CRITICAL P1 incident NOW")
    )
    assert d.action == "alert"
    # Highest-weight non-doc channel (whatsapp=70), not the source email.
    assert d.route_channel == "whatsapp"


def test_addressed_message_routes_back_to_source_as_reply():
    inbox = CrossChannelInbox()
    d = inbox.ingest(
        InboundMessage(channel="telegram", sender="carol", text="@assistant what's my schedule")
    )
    assert d.action in ("reply", "schedule")
    if d.action == "reply":
        assert d.route_channel == "telegram"


def test_default_message_is_a_notification_on_source():
    inbox = CrossChannelInbox()
    d = inbox.ingest(InboundMessage(channel="discord", sender="dev", text="deploy looks green"))
    assert d.action == "notification"
    assert d.route_channel == "discord"


# ── Cross-channel dedup (one assistant everywhere you already are) ───────


def test_identical_message_deduplicated_within_window():
    inbox = CrossChannelInbox()
    m1 = InboundMessage(channel="slack", sender="alice", text="same ping")
    d1 = inbox.ingest(m1)
    m2 = InboundMessage(channel="telegram", sender="alice", text="same ping")
    d2 = inbox.ingest(m2)
    assert d1.accepted is True
    assert d2.duplicate is True  # gateway sees both copies -> drops the dup
    assert inbox.stats()["duplicates"] == 1


def test_distinct_messages_are_kept():
    inbox = CrossChannelInbox()
    inbox.ingest(InboundMessage(channel="slack", sender="alice", text="one thing"))
    d2 = inbox.ingest(InboundMessage(channel="slack", sender="alice", text="another thing"))
    assert d2.accepted is True
    assert d2.duplicate is False


def test_dedup_expires_after_window():
    inbox = CrossChannelInbox()
    # A new inbox with a zero window: identical text passes (no longer a dup).
    inbox._dedup_window = 0
    d1 = inbox.ingest(InboundMessage(channel="slack", sender="alice", text="repeat"))
    d2 = inbox.ingest(InboundMessage(channel="slack", sender="alice", text="repeat"))
    assert d1.accepted is True
    assert d2.accepted is True


# ── Authentication (gateway: "random people can't message your AI") ──────


def test_allowlist_rejects_unknown_senders_and_accepts_allowed():
    inbox = CrossChannelInbox(
        config={
            "allowlist_enabled": True,
            "allowed_senders": ["alice", "bob@acme.com"],
        }
    )
    ok = inbox.ingest(InboundMessage(channel="slack", sender="alice", text="hi"))
    denied = inbox.ingest(InboundMessage(channel="slack", sender="mallory", text="hi"))
    assert ok.accepted is True
    assert denied.accepted is False
    assert denied.authenticated is False
    assert inbox.stats()["rejected"] == 1


def test_allowlist_disabled_accepts_everyone():
    inbox = CrossChannelInbox()
    d = inbox.ingest(InboundMessage(channel="slack", sender="stranger", text="hello"))
    assert d.accepted is True


# ── Conversation sessions (gateway: "remembers your context") ────────────


def test_session_accumulates_context():
    inbox = CrossChannelInbox()
    inbox.ingest(InboundMessage(channel="slack", sender="alice", text="first thing"))
    inbox.ingest(InboundMessage(channel="slack", sender="alice", text="second thing"))
    msg = InboundMessage(channel="slack", sender="alice", text="third thing")
    d = inbox.ingest(msg)
    sess = inbox.session(msg)
    assert d.session_id == "slack::alice"
    assert len(sess["messages"]) == 3


# ── Unified inbox listing ("one assistant, one place") ───────────────────


def test_unified_inbox_consolidates_and_sorts_by_attention():
    inbox = CrossChannelInbox()
    inbox.ingest(InboundMessage(channel="email", sender="news", text="weekly digest"))
    inbox.ingest(
        InboundMessage(channel="whatsapp", sender="boss", text="URGENT check prod now")
    )
    listing = inbox.unified_inbox()
    assert len(listing) == 2
    # Consolidated view is attention-sorted (urgent whatsapp first).
    assert listing[0]["channel"] == "whatsapp"
    assert listing[0]["priority"] == "critical"


def test_unified_inbox_can_filter_by_channel_and_limit():
    inbox = CrossChannelInbox()
    inbox.ingest(InboundMessage(channel="slack", sender="a", text="s1"))
    inbox.ingest(InboundMessage(channel="telegram", sender="b", text="t1"))
    inbox.ingest(InboundMessage(channel="telegram", sender="c", text="t2"))
    only_slack = inbox.unified_inbox(channel="slack")
    assert len(only_slack) == 1 and only_slack[0]["channel"] == "slack"
    assert len(inbox.unified_inbox(limit=2)) == 2


# ── Scheduled / output actions (tools: cron / webhook / notify) ──────────


def test_schedule_action_queues_deterministic_record():
    inbox = CrossChannelInbox()
    inbox.schedule_action("notify", "calendar", {"when": "09:00", "what": "standup"})
    inbox.schedule_action("notify", "whatsapp", {"text": "reminder"})
    actions = inbox.pending_actions()
    assert len(actions) == 2
    assert actions[0]["action"] == "notify"
    assert "at" in actions[0] and "seq" in actions[0]


# ── Stats & health ───────────────────────────────────────────────────────


def test_stats_and_health_report():
    inbox = CrossChannelInbox()
    inbox.ingest(InboundMessage(channel="slack", sender="alice", text="hi"))
    inbox.ingest(InboundMessage(channel="slack", sender="alice", text="hi"))  # dup
    stats = inbox.stats()
    assert stats["ingested"] == 1
    assert stats["duplicates"] == 1
    health = inbox.health()
    assert health["healthy"] is True
    assert health["channels"] == 8  # all transcript channels
    assert health["sessions"] == 1


def test_clear_resets_state():
    inbox = CrossChannelInbox()
    inbox.ingest(InboundMessage(channel="slack", sender="alice", text="hi"))
    inbox.clear()
    assert inbox.stats()["ingested"] == 0
    assert inbox.health()["sessions"] == 0


# ── Module lifecycle & registration ──────────────────────────────────────


async def test_factory_returns_registered_module():
    mod = create_unified_inbox_module()
    assert isinstance(mod, UnifiedInboxModule)
    assert mod.name == "unified_inbox"
    assert mod.version == "1.0.0"


async def test_module_init_health_and_shutdown_lifecycle():
    mod = create_unified_inbox_module({"inbox": {"weights": {"slack": 80}}})
    assert mod.status == HealthStatus.UNKNOWN

    await mod.initialize()
    assert mod.status == HealthStatus.HEALTHY
    assert await mod.health_check() == HealthStatus.HEALTHY
    assert mod.inbox is not None
    assert mod.inbox.channel_weight("slack") == 80  # core config wired through

    await mod.shutdown()
    assert mod.inbox is None
    assert await mod.health_check() == HealthStatus.UNKNOWN


async def test_module_routes_through_wired_core():
    mod = create_unified_inbox_module()
    await mod.initialize()
    d = mod.inbox.ingest(
        InboundMessage(channel="slack", sender="alice", text="URGENT please help")
    )
    assert d.accepted is True
    # slack(60) base 18 + urgent 30 + fresh 5 = 53 -> at least medium priority.
    assert d.score >= 50
    assert d.priority in ("medium", "high")
    await mod.shutdown()


async def test_module_registered_with_kernel():
    assert "unified_inbox" in _MODULE_REGISTRY
    assert _MODULE_REGISTRY["unified_inbox"] is UnifiedInboxModule


async def test_set_event_bus_stores_and_publish_is_guarded():
    mod = create_unified_inbox_module()
    # Before wiring a bus, the sink is a no-op (no crash). Publish nothing.
    import enterprise.modules.unified_inbox as pkg

    pkg_mod = mod
    assert pkg_mod._event_bus is None

    # Provide a minimal faux bus to verify the guard logic path tolerates it.
    from enterprise.platform_kernel import EventBus

    bus = EventBus(config={"async_dispatch": False})
    mod.set_event_bus(bus)
    assert mod._event_bus is bus
