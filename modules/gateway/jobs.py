"""Jobs + channel wiring extension for the ENI gateway module.

Extends the stdlib-only core in ``gateway.py`` with the REAL end-to-end push
path:

  * ``JobRegistry``      — register named scheduled jobs (interval or 5-field
    cron) that point at an *actual callable* (not just a stored name).
  * ``JobScheduler``     — computes each job's next run time, runs jobs that
    are due (injectable clock + injectable runnable for hermetic tests) and
    tracks ``last_run`` / ``next_run`` / ``success`` / ``last_error``.
  * ``ChannelConfigLoader`` — builds real ``Channel`` objects (HTTP / webhook /
    Telegram / Discord) from a channels config dict and registers them on a
    ``Gateway``.
  * ``PushTest``         — pushes a test message to a channel through the
    gateway's real ``send_with_retry`` delivery layer over a real HTTP
    endpoint.

Everything is stdlib-only (``http.server`` for the hermetic echo fixture), so it
plugs straight into the existing gateway module with zero new dependencies.

Version aligned with the gateway module: 1.0.0
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .gateway import (
    DeliveryPolicy,
    DeliveryReceipt,
    Gateway,
    build_channel,
    cron_next,
    interval_next,
)

if TYPE_CHECKING:
    from collections.abc import Callable

# ---------------------------------------------------------------------------
# Job Registry — named scheduled jobs bound to real callables
# ---------------------------------------------------------------------------


@dataclass
class RegisteredJob:
    """A named scheduled job bound to a real callable.

    Attributes:
        id: Unique job name.
        kind: ``"cron"`` (uses ``expr``) or ``"interval"`` (uses ``interval``).
        expr: 5-field cron expression for ``kind="cron"``.
        interval: Seconds between runs for ``kind="interval"``.
        func: The callable to invoke when the job runs.
        last_run: Epoch of the most recent run (None if never run).
        next_run: Epoch of the next scheduled run (None until computed/never).
        enabled: Whether the job is eligible to fire.
        success: Outcome of the most recent run (True/False/None if never run).
        last_error: Error string from the most recent failed run.
    """

    id: str
    kind: str
    func: Callable[[], Any]
    expr: str | None = None
    interval: float | None = None
    last_run: float | None = None
    next_run: float | None = None
    enabled: bool = True
    success: bool | None = None
    last_error: str | None = None

    @property
    def run_state(self) -> dict[str, Any]:
        """Snapshot of the job's scheduling state (for metrics/audit)."""
        return {
            "id": self.id,
            "kind": self.kind,
            "expr": self.expr,
            "interval": self.interval,
            "last_run": self.last_run,
            "next_run": self.next_run,
            "enabled": self.enabled,
            "success": self.success,
            "last_error": self.last_error,
        }


class JobRegistry:
    """Registry of named scheduled jobs that point at real callables."""

    def __init__(self) -> None:
        self._jobs: dict[str, RegisteredJob] = {}

    def register(
        self,
        name: str,
        func: Callable[[], Any],
        kind: str = "interval",
        expr: str | None = None,
        interval: float | None = None,
        enabled: bool = True,
    ) -> RegisteredJob:
        """Register (or replace) a named job bound to ``func``.

        Args:
            name: Unique job name (re-registering replaces the previous job).
            func: Callable invoked when the job runs.
            kind: ``"interval"`` (default) or ``"cron"``.
            expr: 5-field cron expression required when ``kind="cron"``.
            interval: Seconds between runs required when ``kind="interval"``.
            enabled: Whether the job is initially eligible to fire.

        Returns:
            The newly created ``RegisteredJob``.
        """
        job = RegisteredJob(
            id=name,
            kind=kind,
            func=func,
            expr=expr,
            interval=interval,
            enabled=enabled,
        )
        self._jobs[name] = job
        return job

    def unregister(self, name: str) -> RegisteredJob | None:
        """Remove a job by name; returns it or None."""
        return self._jobs.pop(name, None)

    def get(self, name: str) -> RegisteredJob | None:
        """Look up a job by name."""
        return self._jobs.get(name)

    def list(self) -> list[RegisteredJob]:
        """Return all jobs (insertion order)."""
        return list(self._jobs.values())

    def jobs(self) -> dict[str, RegisteredJob]:
        """Return the internal job map (copy)."""
        return dict(self._jobs)

    def names(self) -> list[str]:
        """Return registered job names."""
        return list(self._jobs.keys())

    def __len__(self) -> int:
        return len(self._jobs)


# ---------------------------------------------------------------------------
# Job Scheduler — computes next-run times and runs due jobs
# ---------------------------------------------------------------------------


class JobScheduler:
    """Runs due registered jobs with an injectable clock + runnable.

    The scheduler itself is deterministic and hermetic-friendly: the clock
    (``clock() -> epoch``) and the executor (``runnable(job) -> None``) are both
    injectable so tests can drive time and record executions without waiting.

    The default runnable executes ``job.func()`` and records ``success`` /
    ``last_error``.

    Due semantics:
      * A job that has never run is due immediately.
      * An interval job is due when ``now - last_run >= interval``.
      * A cron job is due when its next occurrence (strictly after ``last_run``)
        is at or before ``now``.
    """

    def __init__(
        self,
        registry: JobRegistry | None = None,
        clock: Callable[[], float] | None = None,
        runnable: Callable[[RegisteredJob], None] | None = None,
    ) -> None:
        self.registry = registry or JobRegistry()
        self._clock: Callable[[], float] = clock or time.time
        # The runnable is what "executes" a due job. Inject a fake in tests.
        self._runnable: Callable[[RegisteredJob], None] = runnable or self._default_runnable

    def _default_runnable(self, job: RegisteredJob) -> None:
        """Execute ``job.func()`` and record the outcome."""
        try:
            job.func()
            job.success = True
            job.last_error = None
        except Exception as exc:  # noqa: BLE001 - job failures are tracked, not raised
            job.success = False
            job.last_error = str(exc)

    # ── Registration convenience ───────────────────────────────────────────

    def register(
        self,
        name: str,
        func: Callable[[], Any],
        kind: str = "interval",
        expr: str | None = None,
        interval: float | None = None,
        enabled: bool = True,
    ) -> RegisteredJob:
        """Register a named job (delegates to the backing ``JobRegistry``)."""
        return self.registry.register(
            name, func, kind=kind, expr=expr, interval=interval, enabled=enabled
        )

    # ── Next-run computation ───────────────────────────────────────────────

    def next_run(self, job: RegisteredJob, now_ts: float | None = None) -> float | None:
        """Return the epoch of ``job``'s next scheduled run at/beyond ``now_ts``.

        Interval jobs are aligned from their ``last_run`` (or ``now_ts`` if they
        have never run). Cron jobs compute the first matching occurrence
        strictly after their ``last_run`` (or ``now_ts`` if never run).
        """
        now = now_ts if now_ts is not None else self._clock()
        if job.kind == "interval":
            return interval_next(
                job.interval if job.interval is not None else 0.0, job.last_run, now
            )
        if job.kind == "cron" and job.expr:
            base = job.last_run if job.last_run is not None else now
            return cron_next(job.expr, base)
        return None

    # ── Due detection ──────────────────────────────────────────────────────

    def _is_due(self, job: RegisteredJob, now_ts: float) -> bool:
        if not job.enabled:
            return False
        if job.last_run is None:
            return True
        if job.kind == "interval":
            interval = job.interval or 0.0
            return interval > 0 and (now_ts - job.last_run) >= interval
        if job.kind == "cron" and job.expr:
            nxt = cron_next(job.expr, job.last_run)
            return nxt is not None and nxt <= now_ts
        return False

    def due(self, now_ts: float | None = None) -> list[RegisteredJob]:
        """Return enabled jobs that are due at/before ``now_ts`` (not invoked)."""
        now = now_ts if now_ts is not None else self._clock()
        return [job for job in self.registry.list() if self._is_due(job, now)]

    # ── Execution ──────────────────────────────────────────────────────────

    def run_due(self, now_ts: float | None = None) -> list[RegisteredJob]:
        """Run every due job, advance its schedule, and return the ran jobs.

        Each due job is executed via the injectable runnable, ``last_run`` is
        advanced to the current ``now_ts``, and ``next_run`` is recomputed so the
        job won't re-fire for the same instant.
        """
        now = now_ts if now_ts is not None else self._clock()
        ran: list[RegisteredJob] = []
        for job in self.due(now):
            ran.append(self.run_job(job, now))
        return ran

    def run_job(self, job: RegisteredJob, now_ts: float | None = None) -> RegisteredJob:
        """Run a single job at ``now_ts`` and advance its schedule."""
        now = now_ts if now_ts is not None else self._clock()
        self._runnable(job)
        job.last_run = now
        job.next_run = self.next_run(job, now)
        return job

    def tick_once(self, now_ts: float | None = None) -> int:
        """One-shot convenience: run due jobs and return how many ran."""
        return len(self.run_due(now_ts))


# ---------------------------------------------------------------------------
# Channel Config Loader — build real channels from a config dict
# ---------------------------------------------------------------------------


class ChannelConfigLoader:
    """Builds real channels from a channels config dict onto a ``Gateway``.

    Each entry in the channels dict is ``name -> spec`` where ``spec`` carries a
    ``type`` (``webhook`` / ``http`` / ``telegram`` / ``discord``) plus the
    type-specific fields. Channels with insufficient config are skipped (they
    report ``enabled() == False``), matching the gateway module's tolerant
    behavior.
    """

    def __init__(self, gateway: Gateway | None = None) -> None:
        self.gateway = gateway or Gateway()

    def load(
        self,
        channels_cfg: dict[str, Any] | None,
        opener: Callable[..., Any] | None = None,
    ) -> int:
        """Build and register every usable channel; return how many registered.

        Args:
            channels_cfg: Mapping of ``name -> spec`` (e.g. from config.yaml).
            opener: Optional injected opener (passed through to ``build_channel``).

        Returns:
            The number of channels successfully built and registered.
        """
        registered = 0
        for name, spec in (channels_cfg or {}).items():
            if not isinstance(spec, dict):
                continue
            channel_type = spec.get("type")
            channel = build_channel(channel_type, spec, opener=opener)
            if channel is None or not channel.enabled:
                continue
            self.gateway.register_channel(name, channel)
            registered += 1
        return registered

    def load_from_config(self, config: dict[str, Any] | None) -> int:
        """Convenience: read the ``channels`` section of a module config dict."""
        cfg = config or {}
        return self.load(cfg.get("channels"))


# ---------------------------------------------------------------------------
# Push Test — prove the real end-to-end push path through send_with_retry
# ---------------------------------------------------------------------------


def push_test(
    gateway: Gateway,
    channel_name: str,
    message: str = "ENI gateway push test",
    policy: DeliveryPolicy | None = None,
    sleep_fn: Callable[[float], None] | None = None,
) -> DeliveryReceipt:
    """Push ``message`` to ``channel_name`` via the real delivery layer.

    Routes through ``Gateway.send_with_retry`` (retry + exponential backoff)
    against the channel's real configured endpoint. Returns the resulting
    ``DeliveryReceipt``; never raises.

    Args:
        gateway: Configured gateway with ``channel_name`` registered.
        channel_name: Name of the registered channel to push to.
        message: Text payload (defaults to a generic push test).
        policy: Retry policy override (defaults to the gateway's policy).
        sleep_fn: Injectable sleeper for hermetic timing in tests.

    Returns:
        A ``DeliveryReceipt`` describing the delivery attempt(s).
    """
    return gateway.send_with_retry(channel_name, message, policy=policy, sleep_fn=sleep_fn)


# ---------------------------------------------------------------------------
# Wiring helpers — populate a gateway + scheduler from a module config dict
# ---------------------------------------------------------------------------


def load_jobs(
    scheduler: JobScheduler,
    jobs_cfg: list[dict[str, Any]] | None,
    func_by_callback: Callable[[str], Callable[[], Any]] | None = None,
) -> int:
    """Register jobs from a ``jobs`` config list onto ``scheduler``.

    Each spec must carry ``id`` and ``kind``. For ``kind="cron"`` an ``expr`` is
    required; for ``kind="interval"`` an ``interval`` is required. The callable
    is resolved via ``func_by_callback(callback)`` when provided, otherwise a
    no-op placeholder is used (so config-only wiring stays non-destructive).

    Returns:
        The number of jobs registered.
    """
    registered = 0
    for spec in jobs_cfg or []:
        if not isinstance(spec, dict) or not spec.get("id"):
            continue
        kind = spec.get("kind", "interval")
        cb = spec.get("callback") or spec["id"]
        func: Callable[[], Any] = (
            func_by_callback(cb) if func_by_callback is not None else (lambda: None)
        )
        scheduler.register(
            spec["id"],
            func,
            kind=kind,
            expr=spec.get("expr"),
            interval=spec.get("interval"),
            enabled=spec.get("enabled", True),
        )
        registered += 1
    return registered


def wire_config(
    gateway: Gateway | None = None,
    scheduler: JobScheduler | None = None,
    config: dict[str, Any] | None = None,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Populate a ``Gateway`` and ``JobScheduler`` from a module config dict.

    Non-destructive: only builds what the config describes and registers on the
    supplied (or freshly created) objects. Returns a small summary dict.

    Args:
        gateway: Target gateway (created if None).
        scheduler: Target job scheduler (created if None).
        config: Module config with optional ``channels`` and ``jobs`` sections.
        opener: Optional injected opener for the channels.

    Returns:
        ``{"channels": n, "jobs": m}`` counts of items registered.
    """
    gateway = gateway or Gateway()
    scheduler = scheduler or JobScheduler()
    cfg = config or {}
    loader = ChannelConfigLoader(gateway=gateway)
    n_channels = loader.load(cfg.get("channels"), opener=opener)
    n_jobs = load_jobs(scheduler, cfg.get("jobs"))
    return {"channels": n_channels, "jobs": n_jobs}


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------

__all__ = [
    "RegisteredJob",
    "JobRegistry",
    "JobScheduler",
    "ChannelConfigLoader",
    "push_test",
    "load_jobs",
    "wire_config",
]
