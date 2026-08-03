"""Multi-Gateway Remote Control & Automations — core implementation.

Provides a stdlib-only gateway for connecting the ENI platform to external
messaging channels (Telegram, Discord) and generic webhooks, plus a pure
cron/interval scheduler for running scheduled automations.

Design goals:
  * ZERO third-party runtime dependencies — HTTP uses only ``urllib.request``.
  * All channel adapters are injectable with a custom ``opener`` so tests can
    record requests without hitting the network.
  * Channel failures are captured as ``GatewayResult(ok=False, error=...)``
    rather than raised, so a slow/down channel never takes down the module.
  * The scheduler is a pure cron implementation (no ``croniter``) that is
    fully unit-testable without ever firing a callback.

Version: 1.0.0
Python: 3.10+
"""

from __future__ import annotations

import abc
import json
import time
import urllib.request
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class GatewayResult:
    """Outcome of a single gateway send operation.

    Attributes:
        ok: True if the underlying transport accepted the message.
        channel: Name of the channel that was targeted.
        recipient: Transport-specific recipient (chat_id / webhook url).
        error: Human-readable error when ``ok`` is False.
        message: The text that was sent (for audit / event payloads).
        timestamp: Epoch (UTC) at which the attempt was made.
    """

    ok: bool
    channel: str = ""
    recipient: str = ""
    error: str | None = None
    message: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (useful for event payloads)."""
        return {
            "ok": self.ok,
            "channel": self.channel,
            "recipient": self.recipient,
            "error": self.error,
            "message": self.message,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Default HTTP opener (stdlib)
# ---------------------------------------------------------------------------


def _default_opener(
    url: str, data: bytes, headers: dict[str, str]
) -> Any:
    """Send a POST via ``urllib.request`` and return the response object.

    The returned object must expose ``.read()`` (like ``http.client`` /
    ``urllib`` responses). Wired as the real transport by default; tests inject
    a fake opener to avoid any network I/O.

    Args:
        url: Destination URL.
        data: UTF-8 encoded JSON payload.
        headers: HTTP request headers.

    Returns:
        The HTTP response object.
    """
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    return urllib.request.urlopen(req, timeout=10)


# ---------------------------------------------------------------------------
# Channel abstraction
# ---------------------------------------------------------------------------


class Channel(abc.ABC):
    """Abstract messaging channel.

    A channel is any destination that can receive a plain-text message.
    Implementations translate ``send`` into the transport-specific wire
    format and must never raise — they return a ``GatewayResult`` instead.
    """

    name: str = ""

    @property
    def enabled(self) -> bool:
        """True if the channel has enough configuration to operate."""
        return True

    @property
    def recipient(self) -> str:
        """Human-facing recipient identifier for metrics/audit."""
        return ""

    @abc.abstractmethod
    def send(self, message: str) -> GatewayResult:
        """Send ``message`` and return a non-raising ``GatewayResult``."""
        raise NotImplementedError


class HTTPChannel(Channel):
    """Base class for JSON-over-HTTP POST channels (Telegram/Discord/webhook).

    Uses an injectable ``opener`` so tests can short-circuit real networking.
    """

    def __init__(self, opener: Callable[..., Any] | None = None) -> None:
        self._opener: Callable[..., Any] = opener or _default_opener

    def _post(
        self,
        url: str,
        payload: dict[str, Any],
        extra_headers: dict[str, str] | None = None,
    ) -> GatewayResult:
        """POST ``payload`` as JSON; returns a non-raising result."""
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if extra_headers:
            headers.update(extra_headers)
        data = json.dumps(payload).encode("utf-8")
        try:
            resp = self._opener(url, data, headers)
            # Consume the body so the opener's response is fully read; pokes
            # lazy/invalid openers to surface connection errors.
            resp.read()
            return GatewayResult(
                ok=True,
                channel=self.name,
                recipient=self.recipient,
                message=str(payload),
                timestamp=time.time(),
            )
        except Exception as exc:  # noqa: BLE001 - external transport
            return GatewayResult(
                ok=False,
                channel=self.name,
                recipient=self.recipient,
                error=str(exc),
                message=str(payload),
                timestamp=time.time(),
            )


class TelegramChannel(HTTPChannel):
    """Telegram Bot API channel.

    Posts to ``https://api.telegram.org/bot<token>/sendMessage`` with a JSON
    body ``{chat_id, text}``.
    """

    def __init__(
        self,
        token: str | None = None,
        chat_id: str | None = None,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        super().__init__(opener=opener)
        self.token = token
        self.chat_id = chat_id

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    @property
    def recipient(self) -> str:
        return str(self.chat_id or "")

    def send(self, message: str) -> GatewayResult:
        if not self.enabled:
            return GatewayResult(
                ok=False,
                channel=self.name,
                recipient=self.recipient,
                error="Telegram channel not configured (token and chat_id required)",
                message=message,
            )
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": message}
        return self._post(url, payload)


class DiscordChannel(HTTPChannel):
    """Discord webhook channel.

    Posts ``{content: message}`` to the given webhook URL.
    """

    def __init__(
        self,
        webhook_url: str | None = None,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        super().__init__(opener=opener)
        self.webhook_url = webhook_url

    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url)

    @property
    def recipient(self) -> str:
        return str(self.webhook_url or "")

    def send(self, message: str) -> GatewayResult:
        if not self.enabled:
            return GatewayResult(
                ok=False,
                channel=self.name,
                recipient=self.recipient,
                error="Discord channel not configured (webhook_url required)",
                message=message,
            )
        payload = {"content": message}
        return self._post(str(self.webhook_url), payload)


class WebhookChannel(HTTPChannel):
    """Generic JSON webhook channel.

    Posts ``{text: message}`` to an arbitrary URL, optionally with custom
    headers (e.g. auth tokens).
    """

    def __init__(
        self,
        url: str | None = None,
        headers: dict[str, str] | None = None,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        super().__init__(opener=opener)
        self.url = url
        self.custom_headers: dict[str, str] = headers or {}

    @property
    def enabled(self) -> bool:
        return bool(self.url)

    @property
    def recipient(self) -> str:
        return str(self.url or "")

    def send(self, message: str) -> GatewayResult:
        if not self.enabled:
            return GatewayResult(
                ok=False,
                channel=self.name,
                recipient=self.recipient,
                error="Webhook channel not configured (url required)",
                message=message,
            )
        payload = {"text": message}
        return self._post(str(self.url), payload, extra_headers=self.custom_headers)


# ---------------------------------------------------------------------------
# Channel registry + Gateway
# ---------------------------------------------------------------------------


class ChannelRegistry:
    """Registered channels plus per-channel send/error metrics.

    Channels are keyed by unique name; sending is counted for observability.
    """

    def __init__(self) -> None:
        self._channels: dict[str, Channel] = {}
        self._sends: dict[str, int] = defaultdict(int)
        self._errors: dict[str, int] = defaultdict(int)

    def register(self, name: str, channel: Channel) -> None:
        """Register a channel under ``name`` (stamped onto the channel)."""
        channel.name = name
        self._channels[name] = channel

    def unregister(self, name: str) -> Channel | None:
        """Remove and return a channel by name (None if absent)."""
        return self._channels.pop(name, None)

    def get(self, name: str) -> Channel | None:
        """Look up a channel by name."""
        return self._channels.get(name)

    def get_channels(self) -> dict[str, Channel]:
        """Return a shallow copy of all registered channels."""
        return dict(self._channels)

    def names(self) -> list[str]:
        """Return the registered channel names."""
        return list(self._channels)

    def record_send(self, name: str) -> None:
        """Increment the send counter for a channel."""
        self._sends[name] += 1

    def record_error(self, name: str) -> None:
        """Increment the error counter for a channel."""
        self._errors[name] += 1

    def send_count(self, name: str | None = None) -> int:
        """Return total sends, optionally filtered by channel name."""
        if name is not None:
            return self._sends.get(name, 0)
        return sum(self._sends.values())

    def error_count(self, name: str | None = None) -> int:
        """Return total errors, optionally filtered by channel name."""
        if name is not None:
            return self._errors.get(name, 0)
        return sum(self._errors.values())

    def metrics(self) -> dict[str, Any]:
        """Return a metrics snapshot (useful for the platform metrics hook)."""
        return {
            "channels": len(self._channels),
            "names": list(self._channels),
            "sends": dict(self._sends),
            "errors": dict(self._errors),
            "total_sends": self.send_count(),
            "total_errors": self.error_count(),
        }


class Gateway:
    """Multi-channel gateway: registration, send, broadcast and topic routing.

    Args:
        event_sink: Optional callback ``(topic, payload_dict)`` invoked after a
            successful send. The module wires this to the platform EventBus so
            messages produce ``gateway.message.sent`` events.
    """

    def __init__(
        self,
        event_sink: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.registry = ChannelRegistry()
        self._event_sink = event_sink

    # ── Registration ───────────────────────────────────────────────────────

    def register_channel(self, name: str, channel: Channel) -> Channel:
        """Register ``channel`` under ``name`` and return it."""
        self.registry.register(name, channel)
        return channel

    def unregister_channel(self, name: str) -> Channel | None:
        """Unregister a channel; returns the removed channel or None."""
        return self.registry.unregister(name)

    def get_channels(self) -> dict[str, Channel]:
        """Return all registered channels keyed by name."""
        return self.registry.get_channels()

    # ── Sending ────────────────────────────────────────────────────────────

    def send(self, channel_name: str, message: str) -> GatewayResult:
        """Send ``message`` to a single named channel.

        Returns an error result if the channel is unknown or the transport
        fails; never raises.
        """
        channel = self.registry.get(channel_name)
        if channel is None:
            return GatewayResult(
                ok=False,
                channel=channel_name,
                error=f"Unknown channel: {channel_name}",
                message=message,
            )
        result = channel.send(message)
        self._tally(channel_name, result)
        return result

    def broadcast(self, message: str) -> list[GatewayResult]:
        """Send ``message`` to every registered channel."""
        results: list[GatewayResult] = []
        for name in self.registry.names():
            results.append(self.send(name, message))
        return results

    def route(
        self,
        routing_map: dict[str, list[str]],
        topic: str,
        message: str,
    ) -> list[GatewayResult]:
        """Route ``message`` to the channels mapped to ``topic``.

        Args:
            routing_map: ``topic -> [channel_name, ...]`` mapping. Entries that
                reference unknown channels degrade gracefully (error result).
            topic: The routing key (e.g. ``"alert.critical"``).
            message: Text to deliver.

        Returns:
            One ``GatewayResult`` per targeted channel. Unknown topic yields an
            empty list.
        """
        targets = routing_map.get(topic, [])
        results: list[GatewayResult] = []
        for name in targets:
            results.append(self.send(name, message))
        return results

    # ── Metrics / events ───────────────────────────────────────────────────

    def _tally(self, channel_name: str, result: GatewayResult) -> None:
        if result.ok:
            self.registry.record_send(channel_name)
            if self._event_sink is not None:
                self._event_sink(
                    "gateway.message.sent",
                    {"channel": channel_name, "result": result.to_dict()},
                )
        else:
            self.registry.record_error(channel_name)

    def metrics(self) -> dict[str, Any]:
        """Return gateway-level metrics."""
        return self.registry.metrics()


# ---------------------------------------------------------------------------
# Pure cron / interval scheduler (stdlib only)
# ---------------------------------------------------------------------------


def _parse_field(field: str, low: int, high: int) -> set[int]:
    """Parse a cron field segment into a set of allowed values.

    Supports ``*`` and comma-separated numeric lists (e.g. ``0,30``).
    Out-of-range / non-numeric entries are ignored.
    """
    field = field.strip()
    if field == "*":
        return set(range(low, high + 1))
    values: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if not part.isdigit():
            continue
        value = int(part)
        if low <= value <= high:
            values.add(value)
    return values


def _parse_dow(field: str) -> set[int]:
    """Parse a day-of-week field (0-6, with 7 normalized to 0 = Sunday)."""
    values = _parse_field(field, 0, 7)
    if 7 in values:
        values.add(0)
        values.discard(7)
    return values


def cron_next(expr: str, from_ts: float) -> float | None:
    """Compute the next UTC epoch strictly after ``from_ts`` matching a cron expr.

    Supports the 5 standard fields (min hour dom mon dow). Only ``*`` and simple
    numeric lists are handled (no ranges or step values). ``dow`` accepts 0-6 or
    0-7 where 7 is normalized to 0 (Sunday). Standard cron day semantics apply:
    when both dom and dow are restricted, a day matches if EITHER matches.

    Args:
        expr: Five space-separated cron fields.
        from_ts: Epoch timestamp (float) to search after.

    Returns:
        Next matching epoch in UTC, or ``None`` if the expression cannot be
        satisfied within the search horizon (e.g. ``0 0 30 2 *`` — Feb 30).
    """
    parts = expr.split()
    if len(parts) != 5:
        return None

    minutes, hours = _parse_field(parts[0], 0, 59), _parse_field(parts[1], 0, 23)
    days_of_month = _parse_field(parts[2], 1, 31)
    months = _parse_field(parts[3], 1, 12)
    days_of_week = _parse_dow(parts[4])

    if not (minutes and hours and days_of_month and months and days_of_week):
        return None

    dom_full = days_of_month == set(range(1, 32))
    dow_full = days_of_week == set(range(0, 7))

    start = (
        datetime.fromtimestamp(from_ts, tz=UTC)
        .replace(second=0, microsecond=0)
        + timedelta(minutes=1)
    )
    horizon = start + timedelta(days=366 * 5)

    candidate = start
    while candidate <= horizon:
        if (
            candidate.month in months
            and candidate.minute in minutes
            and candidate.hour in hours
        ):
            dom_match = candidate.day in days_of_month
            # Python weekday(): Mon=0..Sun=6; cron dow 0 => Sunday.
            cron_dow = (candidate.weekday() + 1) % 7
            dow_match = cron_dow in days_of_week

            if dom_full or dow_full:
                day_ok = dom_match and dow_match
            else:
                day_ok = dom_match or dow_match

            if day_ok:
                return candidate.timestamp()
        candidate += timedelta(minutes=1)
    return None


def interval_next(
    interval_seconds: float,
    last_run_ts: float | None,
    from_ts: float,
) -> float:
    """Compute the next interval-based run time at or just after ``from_ts``.

    Args:
        interval_seconds: Positive interval between runs.
        last_run_ts: Last execution time (None if never run).
        from_ts: Reference timestamp to align against.

    Returns:
        The earliest epoch ``>= from_ts`` that is a valid next interval.
    """
    if interval_seconds <= 0:
        return from_ts
    ref = last_run_ts if last_run_ts is not None else from_ts
    if from_ts >= ref:
        delta = ((from_ts - ref) // interval_seconds) + 1
        return ref + delta * interval_seconds
    return ref + interval_seconds


@dataclass
class Job:
    """A scheduled automation job.

    Attributes:
        id: Unique job identifier.
        kind: ``"cron"`` (uses ``expr``) or ``"interval"`` (uses ``interval``).
        expr: 5-field cron expression for ``kind="cron"``.
        interval: Seconds between runs for ``kind="interval"``.
        callback: Name of the handler to invoke (stored, not a live ref).
        last_run: Epoch of the last successful run (None if never run).
        enabled: Whether the job is eligible to fire.
    """

    id: str
    kind: str
    expr: str | None = None
    interval: float | None = None
    callback: str = ""
    last_run: float | None = None
    enabled: bool = True


class Scheduler:
    """In-memory cron/interval scheduler.

    Jobs are upserted by id; ``due`` reports which jobs should fire at a given
    time without actually invoking callbacks, keeping the scheduler fully
    testable. ``mark_run`` records execution so a job won't re-fire.

    Due semantics:
      * A job that has never run (``last_run is None``) is due immediately —
        its first fire is scheduled for now.
      * An interval job is due when ``now - last_run >= interval``.
      * A cron job is due when its next occurrence (strictly after ``last_run``)
        is at or before ``now``.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    # ── Management ─────────────────────────────────────────────────────────

    def upsert(self, job: Job) -> Job:
        """Insert or replace a job by its id."""
        self._jobs[job.id] = job
        return job

    def remove(self, job_id: str) -> Job | None:
        """Remove a job; returns it or None."""
        return self._jobs.pop(job_id, None)

    def get(self, job_id: str) -> Job | None:
        """Look up a job by id."""
        return self._jobs.get(job_id)

    def all(self) -> list[Job]:
        """Return all jobs."""
        return list(self._jobs.values())

    def jobs(self) -> dict[str, Job]:
        """Return the internal job map (copy)."""
        return dict(self._jobs)

    # ── Scheduling logic ───────────────────────────────────────────────────

    def _is_due(self, job: Job, now_ts: float) -> bool:
        if not job.enabled:
            return False
        if job.last_run is None:
            return True
        if job.kind == "interval":
            interval = job.interval or 0.0
            return interval > 0 and (now_ts - job.last_run) >= interval
        if job.kind == "cron":
            if not job.expr:
                return False
            nxt = cron_next(job.expr, job.last_run)
            return nxt is not None and nxt <= now_ts
        return False

    def _sort_key(self, job: Job, now_ts: float) -> float:
        """Return the next-run timestamp used to order due jobs."""
        if job.last_run is None:
            return now_ts
        if job.kind == "interval":
            return (job.last_run or 0.0) + (job.interval or 0.0)
        if job.kind == "cron" and job.expr:
            nxt = cron_next(job.expr, job.last_run)
            if nxt is not None:
                return nxt
        return now_ts

    def due(self, now_ts: float) -> list[Job]:
        """Return enabled jobs that are due at (or before) ``now_ts``.

        Jobs are returned sorted by their next scheduled run, then by id, so
        callers see a deterministic fire order. No callbacks are invoked here.

        Args:
            now_ts: The epoch to evaluate against.

        Returns:
            List of due jobs (never invoked here).
        """
        due_jobs = [job for job in self._jobs.values() if self._is_due(job, now_ts)]
        due_jobs.sort(key=lambda job: (self._sort_key(job, now_ts), job.id))
        return due_jobs

    def mark_run(self, job: Job, ts: float) -> Job:
        """Record that ``job`` ran at ``ts``.

        This advances ``last_run`` so ``due`` at the same time no longer returns
        the job.
        """
        job.last_run = ts
        return job


# ---------------------------------------------------------------------------
# Config-driven channel factory
# ---------------------------------------------------------------------------


def build_channel(
    channel_type: str,
    spec: dict[str, Any],
    opener: Callable[..., Any] | None = None,
) -> Channel | None:
    """Construct a channel from a config spec dict.

    Args:
        channel_type: ``telegram``, ``discord``, or ``webhook``.
        spec: Config dict with the type-specific fields.
        opener: Optional injected opener (for tests).

    Returns:
        A configured channel, or ``None`` if the type is unknown.
    """
    spec = spec or {}
    if channel_type == "telegram":
        return TelegramChannel(
            token=spec.get("token"),
            chat_id=spec.get("chat_id"),
            opener=opener,
        )
    if channel_type == "discord":
        return DiscordChannel(webhook_url=spec.get("webhook_url"), opener=opener)
    if channel_type == "webhook":
        return WebhookChannel(
            url=spec.get("url"),
            headers=spec.get("headers"),
            opener=opener,
        )
    return None


__all__ = [
    "GatewayResult",
    "Channel",
    "HTTPChannel",
    "TelegramChannel",
    "DiscordChannel",
    "WebhookChannel",
    "ChannelRegistry",
    "Gateway",
    "Job",
    "Scheduler",
    "cron_next",
    "interval_next",
    "build_channel",
]
