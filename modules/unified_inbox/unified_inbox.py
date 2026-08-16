"""unified_inbox core — a ZERO-AI cross-channel inbox.

Pure, network-free, stdlib-only. Grounded in the JEVanClief "Clawdbot (Moltbot)
Has 100K Stars. It Has Zero AI." transcript: Moltbot is an open-source universal
assistant (100k stars, ~50k LOC) with **no model and no weights**. Its value is
architecture — the 60/30/10 split: ~60% traditional plumbing (integrations,
networking, file handling), ~30% deterministic rule-based logic (routing,
security, management — *not* AI), and ~10% actual model calls, which Moltbot
pushes entirely external (bring-your-own API key / local model).

Layers modeled here: the *channel layer* (named adapters per platform), the
*gateway* (a "routing brain" that decides where each message goes, authenticates
senders, and keeps conversation sessions), and the *output layer* (tools +
external AI hook). This core implements the 30% rule-based slice — cross-channel
consolidation, attention/notification triage ("every app wants your attention"),
rule-based routing with **zero ML**, and dedup. The 10% model slice stays an
optional external hook (``set_model_hook``), exactly as Moltbot keeps AI external.

Python: 3.10+
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

# Named channel adapters — the transcript's "channel layer".  Moltbot speaks to
# each via a dedicated maintained library; we model each as an adapter with a
# weight and address tokens.
DEFAULT_CHANNELS: tuple[str, ...] = (
    "slack",
    "discord",
    "whatsapp",
    "telegram",
    "email",
    "calendar",
    "teams",
    "signal",
)

# Baseline attention weight per channel.  WhatsApp/Telegram are personal,
# always-reachable channels (Moltbot demos respond there); email is lower by
# convention.  Engineering defaults, not fake platform telemetry.
DEFAULT_CHANNEL_WEIGHTS: dict[str, int] = {
    "slack": 60,
    "discord": 40,
    "whatsapp": 70,
    "telegram": 65,
    "email": 30,
    "calendar": 50,
    "teams": 55,
    "signal": 45,
}

# Words that steal attention / demand triage — deterministic keyword match
# (rule-based triage, per the transcript, over models for this class of decision).
DEFAULT_URGENT_KEYWORDS: tuple[str, ...] = (
    "urgent",
    "asap",
    "blocker",
    "incident",
    "outage",
    "down",
    "critical",
    "p1",
    "p2",
    "now",
    "deadline",
    "immediately",
    "broken",
    "production",
    "severe",
    "review",
)

# Calendar / scheduling intents — route to the calendar channel (the transcript's
# flagship demo is "ask it to check your calendar from Slack").
DEFAULT_CALENDAR_KEYWORDS: tuple[str, ...] = (
    "calendar",
    "meeting",
    "schedule",
    "invite",
    "availability",
    "book",
    "agenda",
    "appointment",
)

# Tokens meaning the assistant is directly addressed (the gateway "decides where
# it goes"; @-mentions are the classic address signal).
ADDRESS_TOKENS: tuple[str, ...] = ("@moltbot", "@clawdbot", "@bot", "@assistant", "hey")

# Sender titles that raise attention (e.g. your boss on slack).  Configurable.
DEFAULT_HIGH_PRIORITY_SENDERS: tuple[str, ...] = (
    "boss",
    "boss@acme",
    "ceo",
    "manager",
    "lead",
    "oncall",
    "founder",
    "exec",
    "director",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _norm(text: str) -> str:
    """Collapse whitespace and lowercase for stable rule matching/keys."""
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _fingerprint(channel: str, sender: str, text: str) -> str:
    """Channel-agnostic content hash for cross-channel dedup.

    The unified inbox consolidates every platform into one place, so the *same*
    sender sending *identical* content on any channel within the dedup window is
    one message, not many (the transcript's "every platform has its own inbox"
    is the problem this solves).
    """
    payload = f"{_norm(sender)}|{_norm(text)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class ChannelAdapter:
    """A named channel adapter (the transcript's "channel layer").

    Attributes:
        name: Canonical channel name, e.g. ``"whatsapp"``.
        weight: Baseline attention weight (0-100) for this channel.
        address_tokens: Tokens that indicate the assistant is addressed here.
    """

    name: str
    weight: int = 50
    address_tokens: tuple[str, ...] = ADDRESS_TOKENS


@dataclass
class InboundMessage:
    """A message arriving from any channel.

    Attributes:
        channel: Source channel name (one of the registered adapters).
        sender: Free-form sender id (email, handle, phone).
        text: Message body.
        message_id: Optional platform-native id used for exact dedup.
        timestamp: UTC arrival time.
    """

    channel: str
    sender: str
    text: str
    message_id: Optional[str] = None
    timestamp: datetime = field(default_factory=_utcnow)


@dataclass
class TriageDecision:
    """Deterministic routing/triage verdict for an inbound message.

    This is the gateway's output — a *routing brain*, not an AI brain.  Every
    field is produced by rule-based logic (no model).
    """

    accepted: bool = True
    duplicate: bool = False
    score: int = 0
    priority: str = "low"
    route_channel: str = ""
    action: str = "notification"
    session_id: str = ""
    authenticated: bool = True
    rules_fired: list[str] = field(default_factory=list)


class CrossChannelInbox:
    """Zero-AI cross-channel inbox: consolidate, triage, route, dedup.

    Models the Moltbot gateway: every message from every channel flows through
    here, the gateway decides where it goes (rule-based), authenticates senders,
    keeps conversation sessions, and triages attention so one assistant works
    everywhere you already are.  No neural model and no network in the core.

    Config keys (all optional):
        weights:              dict channel -> weight override.
        allowed_senders:      iterable of sender ids permitted to message.
        urgent_keywords:      extra urgency tokens.
        calendar_keywords:    extra calendar-intent tokens.
        high_priority_senders: sender titles that boost attention.
        dedup_window:         seconds within which identical text is a dup (300).
        address_tokens:       tokens meaning the assistant is addressed.
        addressed_bonus:      score added when addressed (default 20).
        urgent_bonus:         score added per urgency keyword (default 30).
        sender_bonus:         score added for known high-priority sender (15).
    """

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        cfg = config or {}

        self._adapters: dict[str, ChannelAdapter] = {
            name: ChannelAdapter(
                name=name,
                weight=int(cfg.get("weights", {}).get(name, DEFAULT_CHANNEL_WEIGHTS[name])),
                address_tokens=tuple(cfg.get("address_tokens", ADDRESS_TOKENS)),
            )
            for name in DEFAULT_CHANNELS
        }

        self._allowed_senders: set[str] = {
            s.strip().lower() for s in cfg.get("allowed_senders", []) or []
        }
        self._allowlist_enabled: bool = cfg.get("allowlist_enabled", False)

        self._urgent_keywords: tuple[str, ...] = tuple(
            cfg.get("urgent_keywords", DEFAULT_URGENT_KEYWORDS)
        )
        self._calendar_keywords: tuple[str, ...] = tuple(
            cfg.get("calendar_keywords", DEFAULT_CALENDAR_KEYWORDS)
        )
        self._priority_senders: tuple[str, ...] = tuple(
            cfg.get("high_priority_senders", DEFAULT_HIGH_PRIORITY_SENDERS)
        )
        self._address_tokens: tuple[str, ...] = tuple(
            cfg.get("address_tokens", ADDRESS_TOKENS)
        )

        self._dedup_window: float = float(cfg.get("dedup_window", 300))
        self._addressed_bonus: int = int(cfg.get("addressed_bonus", 20))
        self._urgent_bonus: int = int(cfg.get("urgent_bonus", 30))
        self._sender_bonus: int = int(cfg.get("sender_bonus", 15))
        self._freshness_bonus: int = int(cfg.get("freshness_bonus", 5))

        # Attention triage state.
        self._seen: dict[str, float] = {}  # fingerprint -> monotonic timestamp
        self._inbox: list[InboundMessage] = []
        self._sessions: dict[str, dict[str, Any]] = {}
        self._pending_actions: list[dict[str, Any]] = []
        self._model_hook: Optional[Callable[[str, dict[str, Any]], Optional[str]]] = None
        self._event_sink: Optional[Callable[[str, dict[str, Any]], None]] = None

        self._stats = {
            "ingested": 0,
            "duplicates": 0,
            "rejected": 0,
            "routed": 0,
        }

    # ── Channel registry (the transcript's "channel layer") ─────────────

    def register_channel(self, adapter: ChannelAdapter) -> None:
        """Register (or replace) a named channel adapter."""
        self._adapters[adapter.name] = adapter

    def list_channels(self) -> list[str]:
        """Return canonical channel names in registry order."""
        return list(self._adapters)

    def channel_weight(self, channel: str) -> int:
        """Return the configured attention weight for a channel (default 0)."""
        return self._adapters.get(channel, ChannelAdapter(name=channel)).weight

    def set_channel_weight(self, channel: str, weight: int) -> None:
        """Override the attention weight for an existing channel."""
        if channel in self._adapters:
            self._adapters[channel].weight = int(weight)

    # ── External hooks (the transcript's "output layer") ────────────────

    def set_model_hook(
        self, hook: Optional[Callable[[str, dict[str, Any]], Optional[str]]]
    ) -> None:
        """Attach the optional external AI hook (Moltbot keeps AI external)."""
        self._model_hook = hook

    def set_event_sink(
        self, sink: Optional[Callable[[str, dict[str, Any]], None]]
    ) -> None:
        """Attach an optional callback receiving ``(topic, payload)`` events."""
        self._event_sink = sink

    def _emit(self, topic: str, payload: dict[str, Any]) -> None:
        if self._event_sink is not None:
            try:
                self._event_sink(topic, payload)
            except Exception:  # pragma: no cover - event sink must not break flow
                pass

    # ── Authentication (gateway: "random people can't message your AI") ─

    def authenticate(self, sender: str) -> bool:
        """Allowlist check — "random people can't message your AI" (no model)."""
        if not self._allowlist_enabled:
            return True
        return _norm(sender) in self._allowed_senders

    # ── Dedup (cross-channel consolidation) ─────────────────────────────

    def _is_duplicate(self, msg: InboundMessage) -> bool:
        now = time.monotonic()
        fp = _fingerprint(msg.channel, msg.sender, msg.text)
        last = self._seen.get(fp)
        if last is not None and (now - last) <= self._dedup_window:
            return True
        self._seen[fp] = now
        # Opportunistic pruning of stale fingerprints to bound memory.
        if len(self._seen) > 8192:
            cutoff = now - self._dedup_window
            self._seen = {k: v for k, v in self._seen.items() if v >= cutoff}
        return False

    # ── Rule-based attention scoring ("every app wants your attention") ─

    def attention_score(self, msg: InboundMessage) -> tuple[int, list[str]]:
        """Compute a deterministic 0-100 attention score and the rules that fired.

        Rules (rule-based logic — the transcript's "30%" slice, zero ML):
          * urgent keyword match      -> +``urgent_bonus`` each
          * assistant is addressed    -> +``addressed_bonus``
          * high-priority sender      -> +``sender_bonus``
          * channel baseline weight   -> normalized contribution
        """
        score = 0
        fired: list[str] = []

        text = _norm(msg.text)
        for kw in self._urgent_keywords:
            if kw in text:
                score += self._urgent_bonus
                fired.append(f"kw:{kw}")

        addressed = self._is_addressed(msg)
        if addressed:
            score += self._addressed_bonus
            fired.append("addressed")

        if self._is_priority_sender(msg.sender):
            score += self._sender_bonus
            fired.append("sender:priority")

        # Channel ubiquity contributes a baseline share (weight/100 * 30 pts).
        w = max(0, min(100, self.channel_weight(msg.channel)))
        score += int(w / 100.0 * 30)
        fired.append(f"channel:{w}")

        # Freshness: recent messages are more likely to demand immediate action.
        age_s = max(0.0, (_utcnow() - msg.timestamp).total_seconds())
        if age_s <= 300:
            score += self._freshness_bonus
            fired.append("fresh")

        return min(score, 100), fired

    def _is_addressed(self, msg: InboundMessage) -> bool:
        text = _norm(msg.text)
        for tok in self._address_tokens:
            if tok in text:
                return True
        return False

    def _is_priority_sender(self, sender: str) -> bool:
        needle = _norm(sender)
        return any(p in needle for p in self._priority_senders)

    @staticmethod
    def _priority_label(score: int) -> str:
        if score >= 80:
            return "critical"
        if score >= 60:
            return "high"
        if score >= 40:
            return "medium"
        return "low"

    # ── Rule-based routing (gateway: "it decides where it goes") ───────

    def route(self, msg: InboundMessage, score: int) -> tuple[str, str]:
        """Decide the destination channel and action — deterministic, no ML.

        Rules, in priority order:
          1. Calendar intent  -> action ``schedule`` on the ``calendar`` channel.
          2. Critical score   -> action ``alert`` (highest-weight attended channel).
          3. Directly addressed -> action ``reply`` on the source channel.
          4. Otherwise        -> action ``notification`` on the source channel.
        """
        text = _norm(msg.text)
        if any(k in text for k in self._calendar_keywords):
            return "calendar", "schedule"

        if score >= 80:
            best = max(
                (c for c in self._adapters if c not in ("email", "calendar")),
                key=lambda c: self.channel_weight(c),
                default=msg.channel,
            )
            return best, "alert"

        if self._is_addressed(msg):
            return msg.channel, "reply"

        return msg.channel, "notification"

    # ── Conversation sessions (gateway: "AI remembers your context") ────

    def _session_id(self, msg: InboundMessage) -> str:
        return f"{msg.channel}::{_norm(msg.sender)}"

    def session(self, msg: InboundMessage) -> dict[str, Any]:
        """Return (creating if needed) the deterministic conversation session."""
        sid = self._session_id(msg)
        self._sessions.setdefault(
            sid,
            {
                "channel": msg.channel,
                "sender": msg.sender,
                "created": _utcnow(),
                "messages": [],
                "topic": "",
            },
        )
        return self._sessions[sid]

    def _update_session(self, msg: InboundMessage, decision: TriageDecision) -> str:
        sess = self.session(msg)
        sess["messages"].append(
            {
                "channel": msg.channel,
                "text": msg.text,
                "at": _utcnow().isoformat(),
            }
        )
        if len(sess["messages"]) > 50:  # bound memory per conversation
            sess["messages"] = sess["messages"][-50:]
        if not sess["topic"]:
            sess["topic"] = _norm(msg.text).split()[:6]
        decision.session_id = self._session_id(msg)
        return decision.session_id

    # ── Ingest pipeline ─────────────────────────────────────────────────

    def ingest(self, msg: InboundMessage) -> TriageDecision:
        """Run a message through the whole gateway pipeline.

        authenticate -> dedup -> score -> route -> session -> store -> emit.

        Returns a :class:`TriageDecision` describing what happened.  All logic is
        deterministic; no model is required (model hook is optional and external).
        """
        # 1. Authentication (gateway security rule).
        if not self.authenticate(msg.sender):
            self._stats["rejected"] += 1
            self._emit(
                "unified_inbox.rejected",
                {"channel": msg.channel, "sender": msg.sender},
            )
            return TriageDecision(accepted=False, authenticated=False)

        # 2. Cross-channel dedup.
        if self._is_duplicate(msg):
            self._stats["duplicates"] += 1
            self._emit(
                "unified_inbox.duplicate",
                {"channel": msg.channel, "sender": msg.sender},
            )
            return TriageDecision(
                accepted=False,
                duplicate=True,
                score=self.attention_score(msg)[0],
            )

        # 3. Attention scoring (rule-based triage).
        score, fired = self.attention_score(msg)

        # 4. Rule-based routing.
        route_channel, action = self.route(msg, score)

        # 5. Session / context management (gateway "remembers context").
        decision = TriageDecision(
            accepted=True,
            duplicate=False,
            score=score,
            priority=self._priority_label(score),
            route_channel=route_channel,
            action=action,
            authenticated=True,
            rules_fired=fired,
        )
        self._update_session(msg, decision)

        # 6. Store in the unified inbox list (consolidated across channels).
        self._inbox.append(msg)

        # 7. Optional external AI hook (bring-your-own model — never required).
        if self._model_hook is not None:
            reply = self._model_hook(msg.text, {"channel": msg.channel, "score": score})
            if reply:
                decision.rules_fired.append("model-hook")

        self._stats["ingested"] += 1
        self._stats["routed"] += 1

        self._emit(
            "unified_inbox.ingested",
            {
                "channel": msg.channel,
                "sender": msg.sender,
                "score": score,
                "priority": decision.priority,
            },
        )
        self._emit(
            "unified_inbox.routed",
            {"route_channel": route_channel, "action": action, "score": score},
        )
        return decision

    # ── Unified inbox listing ───────────────────────────────────────────

    def unified_inbox(
        self, channel: Optional[str] = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Attention-sorted "one assistant, one place" list, optionally per channel."""
        items = [
            m
            for m in self._inbox
            if channel is None or m.channel == channel
        ]
        scored = []
        for m in items:
            s, _ = self.attention_score(m)
            scored.append(
                {
                    "id": _fingerprint(m.channel, m.sender, m.text),
                    "channel": m.channel,
                    "sender": m.sender,
                    "text": m.text,
                    "timestamp": m.timestamp.isoformat(),
                    "score": s,
                    "priority": self._priority_label(s),
                }
            )
        scored.sort(key=lambda d: (d["score"], d["timestamp"]), reverse=True)
        return scored[:limit]

    # ── Scheduled / output actions (tools: cron, webhook, notify) ──────

    def schedule_action(self, action: str, channel: str, payload: dict[str, Any]) -> int:
        """Queue a pending output-tool action (cron/webhook/notify) for delivery."""
        record = {
            "action": action,
            "channel": channel,
            "payload": dict(payload),
            "at": _utcnow().isoformat(),
            "seq": len(self._pending_actions),
        }
        self._pending_actions.append(record)
        return len(self._pending_actions) - 1

    def pending_actions(self) -> list[dict[str, Any]]:
        """Return queued pending actions for external delivery."""
        return list(self._pending_actions)

    # ── Reporting / lifecycle helpers ───────────────────────────────────

    def stats(self) -> dict[str, int]:
        """Return cumulative deterministic statistics."""
        return dict(self._stats)

    def health(self) -> dict[str, Any]:
        """Return a deterministic health report (no network / no DB)."""
        return {
            "healthy": True,
            "channels": len(self._adapters),
            "sessions": len(self._sessions),
            "inbox_size": len(self._inbox),
            "pending_actions": len(self._pending_actions),
            "stats": dict(self._stats),
        }

    def clear(self) -> None:
        """Reset all in-memory state (used on shutdown)."""
        self._seen.clear()
        self._inbox.clear()
        self._sessions.clear()
        self._pending_actions.clear()
        self._stats = {
            "ingested": 0,
            "duplicates": 0,
            "rejected": 0,
            "routed": 0,
        }
