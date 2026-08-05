"""ENI Multi-Gateway Remote Control & Automations Module

Connects the ENI Enterprise platform to external messaging channels
(Telegram, Discord, generic webhooks) and provides a cron/interval scheduler
for running scheduled automations — enabling outbound alerts, notifications,
and remote-controlled automation.

Exports:
  GatewayModule      — @module-decorated Module subclass
  Gateway            — multi-channel registry: register/send/broadcast/route
  Scheduler          — pure cron + interval scheduler
  build_channel      — config-driven channel factory

Version: 1.0.0
Python: 3.10+
"""

from __future__ import annotations

__version__ = "1.0.0"
__module__ = "gateway"

import logging
from typing import Any, Dict, List, Optional  # noqa: F401

from enterprise.platform_kernel import (
    Event,
    EventBus,
    EventPriority,
    HealthStatus,
    Module,
    module,
)

from .gateway import (
    Channel,
    ChannelRegistry,
    DeliveryPolicy,
    DeliveryReceipt,
    DeliveryStatus,
    DiscordChannel,
    Gateway,
    GatewayResult,
    GatewayRouter,
    HTTPChannel,
    Job,
    Outbox,
    Scheduler,
    TelegramChannel,
    WebhookChannel,
    build_channel,
    cron_next,
    interval_next,
    send_with_retry,
)
from .jobs import (
    ChannelConfigLoader,
    JobRegistry,
    JobScheduler,
    RegisteredJob,
    load_jobs,
    push_test,
    wire_config,
)

__all__ = [
    "__version__",
    "GatewayModule",
    "Gateway",
    "Scheduler",
    "Job",
    "Channel",
    "ChannelRegistry",
    "TelegramChannel",
    "DiscordChannel",
    "WebhookChannel",
    "HTTPChannel",
    "GatewayResult",
    "build_channel",
    "cron_next",
    "interval_next",
    "DeliveryStatus",
    "DeliveryPolicy",
    "DeliveryReceipt",
    "send_with_retry",
    "GatewayRouter",
    "Outbox",
    # Real channel + scheduled-job wiring
    "RegisteredJob",
    "JobRegistry",
    "JobScheduler",
    "ChannelConfigLoader",
    "push_test",
    "load_jobs",
    "wire_config",
]

_logger: logging.Logger = logging.getLogger("enterprise.gateway")


@module(name="gateway", version="1.0.0")
class GatewayModule(Module):
    """Enterprise Multi-Gateway Remote Control & Automations Module.

    Builds a ``Gateway`` from the ``channels`` config section and a ``Scheduler``
    from the ``jobs`` section. Tolerates missing/invalid channel or job specs
    without crashing — problematic entries are skipped and logged.

    Config schema::

        {
            "channels": {
                "alerts": {"type": "telegram", "token": "...", "chat_id": "..."},
                "ops": {"type": "discord", "webhook_url": "..."},
                "infra": {"type": "webhook", "url": "...", "headers": {...}},
            },
            "jobs": [
                {
                    "id": "daily-report",
                    "kind": "cron",
                    "expr": "0 9 * * 1-5",
                    "callback": "send_daily_report",
                },
                {"id": "heartbeat", "kind": "interval", "interval": 300, "callback": "heartbeat"},
            ],
        }

    Events published:
      - gateway.message.sent
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._gateway: Gateway | None = None
        self._scheduler: Scheduler | None = None
        self._event_bus: EventBus | None = None

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def gateway(self) -> Gateway | None:
        """The active Gateway instance (None before initialization)."""
        return self._gateway

    @property
    def scheduler(self) -> Scheduler | None:
        """The active Scheduler instance (None before initialization)."""
        return self._scheduler

    # ── Event bus wiring ──────────────────────────────────────────────────

    def set_event_bus(self, event_bus: EventBus) -> None:
        """Store the platform EventBus for outbound event publishing."""
        self._event_bus = event_bus

    def _emit(self, topic: str, payload: dict[str, Any]) -> None:
        """Publish an event on the platform bus (no-op if bus is absent)."""
        if self._event_bus is not None:
            try:
                self._event_bus.publish(
                    Event.create(topic, "gateway", payload, priority=EventPriority.NORMAL)
                )
            except Exception:  # noqa: BLE001 - event publishing must not break sends
                _logger.exception("Failed to publish gateway event %s", topic)

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Build the Gateway and Scheduler from configuration."""
        self._status = HealthStatus.STARTING
        try:
            self._gateway = Gateway(event_sink=self._emit)
            self._scheduler = Scheduler()

            self._build_channels()
            self._build_jobs()

            self._status = HealthStatus.HEALTHY
            _logger.info(
                "Gateway module initialized: %d channel(s), %d job(s)",
                len(self._gateway.get_channels()),
                len(self._scheduler.all()),
            )
        except Exception as exc:  # noqa: BLE001 - lifecycle must report UNHEALTHY
            _logger.exception("Gateway module initialization failed: %s", exc)
            self._status = HealthStatus.UNHEALTHY
            raise

    def _build_channels(self) -> None:
        """Register every usable channel from config; skip invalid entries."""
        assert self._gateway is not None
        channels_cfg = self._config.get("channels", {}) or {}
        if not isinstance(channels_cfg, dict):
            _logger.warning("gateway.channels config is not a dict; ignoring")
            return

        for name, spec in channels_cfg.items():
            if not isinstance(spec, dict):
                _logger.warning("Skipping channel %r: config is not a dict", name)
                continue
            channel_type = spec.get("type")
            channel = build_channel(channel_type, spec)
            if channel is None:
                _logger.warning("Skipping channel %r: unknown type %r", name, channel_type)
                continue
            if not channel.enabled:
                _logger.warning(
                    "Skipping channel %r: insufficient config for type %r",
                    name,
                    channel_type,
                )
                continue
            self._gateway.register_channel(name, channel)
            _logger.info("Registered channel %r (%s)", name, channel_type)

    def _build_jobs(self) -> None:
        """Upsert every valid job from config; skip invalid entries."""
        assert self._scheduler is not None
        jobs_cfg = self._config.get("jobs", []) or []
        if not isinstance(jobs_cfg, list):
            _logger.warning("gateway.jobs config is not a list; ignoring")
            return

        for spec in jobs_cfg:
            if not isinstance(spec, dict) or not spec.get("id"):
                _logger.warning("Skipping invalid job spec: %r", spec)
                continue
            job = Job(
                id=spec["id"],
                kind=spec.get("kind", "cron"),
                expr=spec.get("expr"),
                interval=spec.get("interval"),
                callback=spec.get("callback", spec["id"]),
                enabled=spec.get("enabled", True),
            )
            self._scheduler.upsert(job)

    async def health_check(self) -> HealthStatus:
        """A gateway is healthy when its core objects are built.

        Returns:
            HEALTHY if the Gateway and Scheduler are initialized, UNKNOWN
            otherwise.
        """
        if self._gateway is not None and self._scheduler is not None:
            self._status = HealthStatus.HEALTHY
        else:
            self._status = HealthStatus.UNKNOWN
        return self._status

    async def shutdown(self) -> None:
        """Gracefully stop the gateway module.

        Gateway/scheduler hold no sockets or background threads (all transports
        are synchronous per-send), so shutdown is deterministic and idempotent.
        """
        self._status = HealthStatus.STOPPING
        self._gateway = None
        self._scheduler = None
        self._status = HealthStatus.HEALTHY
        _logger.info("Gateway module shut down")
