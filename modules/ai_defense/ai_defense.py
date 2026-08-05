#!/usr/bin/env python3
"""Enterprise AI Defense Module (defend against AI-driven attacks).

A security-model-first, stdlib-only layer purpose-built to defend the ENI
Enterprise AI Platform against *automated / AI-driven* attackers --- the class of
attacker that uses an LLM or a scripted agent to attack at machine speed and
volume, in ways a human-centric defense misses.

This module does NOT replace the existing `model_security` guards (prompt
injection / jailbreak shields, sanitizer, output validator). It complements them
with the OFFENSE-DEFENSE facets aimed at the *attacker* side:

* ``BehavioralAnomalyDetector`` --- statistical anomaly detection over a stream of
  events (requests, auth attempts, token usage). Flags z-score bursts, high-rate
  floods and variance spikes that indicate an automated/AI attacker, not a human.
* ``BotTrafficClassifier`` --- heuristic fingerprinting of an HTTP/agent request
  to decide whether it is HUMAN vs SCRIPTED/AI-AGENT, from pacing signals (fixed
  inter-arrival timing), uniformity, presence of automation markers, and absence
  of organic human variance. Model-agnostic, no external services.
* ``ModelExtractionShield`` --- defends the platform's *models* from extraction /
  probing: detects volumetric, high-uniqueness query patterns typical of an agent
  trying to recover private model weights or behaviours via many distinct probes.
* ``CredentialStuffingGuard`` --- per-account + per-IP thresholds that lock out
  and cool down after repeated auth failures (brute force / stuffing by agents).
* ``IndirectPromptInjectionGuard`` --- detects indirect prompt injection arriving
  through *content* (agent-read documents, tool outputs, fetched pages) — the
  OWASP LLM01 "indirect" variant -- by scanning text for embedded instruction
  chains, priority-overrides, output-structure demands, and exfiltration verbs.

Design notes for testability:
  * Time is injectable (``clock`` callable returning epoch seconds) on every
    windowed detector so tests drive bursts/lockouts deterministically.
  * Detection thresholds are configurable per facet; every facet is pure and
    deterministic given its inputs.
  * Everything is stdlib-only (collections, math, statistics, dataclasses, abc).
    Zero network calls, zero external dependencies.

Version: 1.0.0
"""

from __future__ import annotations

import abc
import logging
import math
import statistics
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from enterprise.platform_kernel import (
    HealthStatus,
    Module,
    module,
)

from .rate_limit import (
    Allowance,
    AttackerStore,
    SlidingWindowRateLimiter,
    ThrottleGate,
)

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger("enterprise.ai_defense")

__all__ = [
    "Judgement",
    "BehavioralAnomalyDetector",
    "BotTrafficClassifier",
    "ModelExtractionShield",
    "CredentialStuffingGuard",
    "IndirectPromptInjectionGuard",
    "AIDefenseFacade",
    "AIDefenseModule",
    "DEFAULT_CLOCK",
    # Rate-limit / persistent attacker state (wired in but OFF by default)
    "Allowance",
    "AttackerStore",
    "SlidingWindowRateLimiter",
    "ThrottleGate",
]


# ---------------------------------------------------------------------------
# Constants / defaults
# ---------------------------------------------------------------------------


def DEFAULT_CLOCK() -> float:  # noqa: N802 - public API name kept for backwards compatibility
    return time.time()


# Detection verdicts shared across facets.
class Judgement(abc.ABC):  # noqa: B024 - intentional marker base; behavior emerges in concrete subclasses
    """Base classification result for a single defense decision."""

    def __init__(self, malicious: bool, reason: str = "", score: float = 0.0) -> None:
        self.malicious = malicious
        self.reason = reason
        self.score = float(score)

    def to_dict(self) -> dict[str, Any]:
        return {"malicious": self.malicious, "reason": self.reason, "score": self.score}

    def __bool__(self) -> bool:
        return self.malicious


# ---------------------------------------------------------------------------
# 1. BehavioralAnomalyDetector
# ---------------------------------------------------------------------------


@dataclass
class AnomalyConfig:
    """Tunables for the behavioral anomaly detector."""

    window: float = 60.0  # seconds of history considered
    z_threshold: float = 4.0  # z-score beyond which a burst is anomalous
    min_samples: int = 5  # need this many samples before judging
    flood_events_per_sec: float = 20.0  # event rate beyond this = flood


class BehavioralAnomalyDetector:
    """Detect automated/AI bursts via sliding-window statistical anomaly detection.

    Maintains a per-key (e.g. per-IP or per-endpoint) rolling window of event
    timestamps. Computes instantaneous event rate and compares it against the
    window's own baseline (mean + std). A rate that is a large z-score above the
    mean, or an absolute flood threshold, is flagged as an automated attack.
    """

    def __init__(
        self, config: AnomalyConfig | None = None, clock: Callable[[], float] = DEFAULT_CLOCK
    ) -> None:
        self.cfg = config or AnomalyConfig()
        self.clock = clock
        self._events: dict[str, deque[float]] = defaultdict(deque)
        # Slow EWMA baseline (decoupled from the live burst so a burst can't
        # pollute its own baseline).
        self._ewma_gap: dict[str, float] = defaultdict(lambda: 0.0)
        self._ewma_gap2: dict[str, float] = defaultdict(lambda: 0.0)
        self._ewma_n: dict[str, int] = defaultdict(int)
        self._last: dict[str, float] = {}
        self._ALPHA = 0.05

    def _prune(self, key: str, now: float) -> None:
        cutoff = now - self.cfg.window
        deq = self._events[key]
        while deq and deq[0] < cutoff:
            deq.popleft()
        if not deq:
            self._events.pop(key, None)

    def observe(self, key: str, at: float | None = None) -> Judgement:
        """Record an event for `key` and return whether it is anomalous."""
        now = at if at is not None else self.clock()
        deq = self._events[key]

        # True current cadence = the most recent inter-arrival gap.
        prev = self._last.get(key)
        cur_gap = max(now - prev, 1e-06) if prev is not None else 0.0

        # Update the slow EWMA baseline FIRST (reflects history, not this burst).
        alpha = self._ALPHA
        if prev is not None:
            n = self._ewma_n[key]
            if n == 0:
                self._ewma_gap[key] = cur_gap
                self._ewma_gap2[key] = cur_gap * cur_gap
            else:
                self._ewma_gap[key] = alpha * cur_gap + (1 - alpha) * self._ewma_gap[key]
                self._ewma_gap2[key] = (
                    alpha * cur_gap * cur_gap + (1 - alpha) * self._ewma_gap2[key]
                )
            self._ewma_n[key] = n + 1
        self._last[key] = now

        # Live short-window rate (span over the min(now-first, window)).
        self._z_prune(key, now)
        deq = self._events[key]
        if deq:
            span = max(now - deq[0], 0.001)
            live_rate = len(deq) / span
        else:
            live_rate = 0.0
        deq.append(now)

        # --- Absolute flood floor (true short-window rate) ---
        if live_rate >= self.cfg.flood_events_per_sec:
            return Judgement(
                True,
                f"flood: {live_rate:.1f} events/s >= {self.cfg.flood_events_per_sec}",
                score=live_rate,
            )

        # --- Baseline anomaly: is the last gap a sharp speedup vs EWMA? ---
        if cur_gap > 0 and self._ewma_n[key] >= self.cfg.min_samples:
            mean_gap = self._ewma_gap[key]
            var_gap = max(self._ewma_gap2[key] - mean_gap * mean_gap, 0.0)
            std_gap = math.sqrt(var_gap)
            if std_gap > 0:
                z = (mean_gap - cur_gap) / std_gap
            else:
                # No-variance baseline: flag only on a large speedup ratio.
                z = (mean_gap / cur_gap) if mean_gap > 0 and mean_gap > cur_gap else 0.0
            if z >= self.cfg.z_threshold:
                return Judgement(
                    True, f"anomaly burst z={z:.2f} >= {self.cfg.z_threshold}", score=z
                )
        return Judgement(False, "within baseline")

    def _z_prune(self, key: str, now: float) -> None:
        cutoff = now - self.cfg.window
        deq = self._events[key]
        while deq and deq[0] < cutoff:
            deq.popleft()
        if not deq:
            self._events.pop(key, None)

    def reset(self, key: str) -> None:
        self._events.pop(key, None)

    def snapshot(self) -> dict[str, Any]:
        return {"active_keys": len(self._events)}


# ---------------------------------------------------------------------------
# 2. BotTrafficClassifier
# ---------------------------------------------------------------------------


@dataclass
class BotConfig:
    """Tunables for the bot/agent traffic classifier."""

    pacing_sd_threshold: float = 0.05  # inter-arrival SD (as fraction of mean) below this = machine
    min_intervals: int = 6  # intervals needed to classify pacing
    uniform_entropy_threshold: float = 0.2  # low entropy => scripted
    automation_hits: int = 1  # automation markers seen => bot


class BotTrafficClassifier:
    """Classify a request stream as human vs scripted/AI-agent.

    Relies on statistical fingerprints of the traffic itself (fixed pacing,
    uniformity, automation user-agent markers) rather than any external service.
    Streaming: keep inter-arrival intervals per key; once enough are seen, judge.
    """

    def __init__(
        self, config: BotConfig | None = None, clock: Callable[[], float] = DEFAULT_CLOCK
    ) -> None:
        self.cfg = config or BotConfig()
        self.clock = clock
        self._last_seen: dict[str, float] = {}
        self._intervals: dict[str, deque[float]] = defaultdict(deque)
        self._automation_hits: dict[str, int] = defaultdict(int)

    _AUTOMATION_MARKERS = (
        "python-requests",
        "curl/",
        "go-http",
        "httpx",
        "aiohttp",
        "okhttp",
        "headlesschrome",
        "phantomjs",
        "selenium",
        "playwright",
        "puppeteer",
        "scrapy",
        "pyppeteer",
        "node-fetch",
        "googlebot",
        "bingbot",
        "petalbot",
        "semrushbot",
        "ahrefsbot",
        "mj12bot",
        "dotbot",
        "axios",
    )

    def observe_headers(
        self, key: str, user_agent: str = "", headers: dict[str, str] | None = None
    ) -> Judgement:
        """Cheap first-line check on HTTP headers."""
        ua = (user_agent or "").lower()
        low_ua = ua
        for marker in self._AUTOMATION_MARKERS:
            if marker in low_ua:
                self._automation_hits[key] += 1
        # Also scan common headers.
        hdrs = headers or {}
        for v in hdrs.values():
            if isinstance(v, str):
                lv = v.lower()
                for marker in self._AUTOMATION_MARKERS:
                    if marker in lv:
                        self._automation_hits[key] += 1
                        break
        if self._automation_hits[key] >= self.cfg.automation_hits:
            return Judgement(True, "automation user-agent/header marker", score=1.0)
        return Judgement(False, "no automation header")

    def observe_pacing(self, key: str, at: float | None = None) -> Judgement:
        """Feed a request timestamp; classify pacing when enough intervals exist."""
        now = at if at is not None else self.clock()
        prev = self._last_seen.get(key)
        if prev is not None:
            self._intervals[key].append(max(0.0, now - prev))
        self._last_seen[key] = now

        deq = self._intervals[key]
        if len(deq) < self.cfg.min_intervals:
            return Judgement(False, "collecting intervals")
        mean = statistics.mean(deq)
        if mean <= 0:
            return Judgement(False, "degenerate")
        sd = statistics.pstdev(deq)
        frac = sd / mean
        if frac < self.cfg.pacing_sd_threshold:
            return Judgement(True, f"machine-fixed pacing (sd/mean={frac:.4f})", score=frac)
        return Judgement(False, "organic pacing")

    def reset(self, key: str) -> None:
        self._last_seen.pop(key, None)
        self._intervals.pop(key, None)
        self._automation_hits.pop(key, None)

    def snapshot(self) -> dict[str, Any]:
        return {"keys": len(self._intervals)}


# ---------------------------------------------------------------------------
# 3. ModelExtractionShield
# ---------------------------------------------------------------------------


@dataclass
class ExtractionConfig:
    """Tunables for the model-extraction shield."""

    max_queries_per_window: int = 200  # beyond this rate/volume => suspect
    window: float = 60.0
    high_uniqueness_ratio: float = 0.95  # fraction of distinct queries >= this => probing
    min_queries: int = 50  # need this many before uniqueness judgement
    max_distinct_tokens: int = 3000  # cumulative distinct queries trigger hard flag


class ModelExtractionShield:
    """Detect efforts to extract/model-probe a deployed model.

    An attacker probing a model for weights/behaviour fires many *distinct*,
    rapid queries (high uniqueness + high rate). A legitimate user repeats
    queries and has bounded volume. Track per-key distinct-question set cardinality
    and query rate; flag volumetric high-uniqueness probing.
    """

    def __init__(
        self, config: ExtractionConfig | None = None, clock: Callable[[], float] = DEFAULT_CLOCK
    ) -> None:
        self.cfg = config or ExtractionConfig()
        self.clock = clock
        self._seen: dict[str, set] = defaultdict(set)
        self._total: dict[str, int] = defaultdict(int)
        self._window_start: dict[str, deque[float]] = defaultdict(deque)

    def observe(self, key: str, query: str = "", at: float | None = None) -> Judgement:
        now = at if at is not None else self.clock()
        cutoff = now - self.cfg.window
        deq = self._window_start[key]
        while deq and deq[0] < cutoff:
            deq.popleft()
        deq.append(now)

        if query:
            self._seen[key].add(query)
        self._total[key] += 1

        total = self._total[key]
        distinct = len(self._seen[key])
        rate = len(deq) / self.cfg.window

        if total >= self.cfg.min_queries:
            uniqueness = distinct / total
            if uniqueness >= self.cfg.high_uniqueness_ratio and rate >= (
                self.cfg.max_queries_per_window / self.cfg.window
            ):
                return Judgement(
                    True,
                    f"high-volume high-uniqueness probing (u={uniqueness:.2f}, r={rate:.1f}/s)",
                    score=uniqueness,
                )

        if distinct >= self.cfg.max_distinct_tokens:
            return Judgement(
                True, f"cumulative distinct-query threshold ({distinct}) exceeded", score=1.0
            )

        return Judgement(False, "normal query pattern")

    def reset(self, key: str) -> None:
        self._seen.pop(key, None)
        self._total.pop(key, None)
        self._window_start.pop(key, None)

    def snapshot(self) -> dict[str, Any]:
        return {"keys": len(self._seen)}


# ---------------------------------------------------------------------------
# 4. CredentialStuffingGuard
# ---------------------------------------------------------------------------


@dataclass
class StuffingConfig:
    """Tunables for the credential-stuffing guard."""

    max_failures: int = 5  # failures before lockout
    lockout_seconds: float = 300.0  # how long the lockout lasts
    per_ip_max_failures: int = 20  # IP-wide threshold


class CredentialStuffingGuard:
    """Per-account + per-IP lockout after repeated auth failures.

    Protects login endpoints from agent-driven brute force / credential stuffing.
    Tracks failures per account and per IP; after thresholds, further attempts are
    refused until the lockout window elapses.
    """

    def __init__(
        self, config: StuffingConfig | None = None, clock: Callable[[], float] = DEFAULT_CLOCK
    ) -> None:
        self.cfg = config or StuffingConfig()
        self.clock = clock
        self._fail_count: dict[str, int] = defaultdict(int)
        self._first_fail: dict[str, float] = {}
        self._lock_until: dict[str, float] = {}
        self._ip_fail: dict[str, int] = defaultdict(int)

    def _locked(self, key: str, now: float) -> bool:
        until = self._lock_until.get(key, 0.0)
        if until and now < until:
            return True
        if until and now >= until:  # expiry clears both sides
            self._lock_until.pop(key, None)
            self._fail_count.pop(key, None)
            self._ip_fail.pop(key, None)
            self._first_fail.pop(key, None)
        return False

    def check(self, account: str, ip: str = "", at: float | None = None) -> Judgement:
        """True if the attempt must be blocked (account or IP currently locked)."""
        now = at if at is not None else self.clock()
        if self._locked(f"acct:{account}", now):
            return Judgement(True, "account lockout active", score=1.0)
        if ip and self._locked(f"ip:{ip}", now):
            return Judgement(True, "IP lockout active", score=1.0)
        return Judgement(False, "allowed")

    def record_failure(self, account: str, ip: str = "", at: float | None = None) -> Judgement:
        now = at if at is not None else self.clock()

        acct_key = f"acct:{account}"
        if now - self._first_fail.get(acct_key, now) > self.cfg.lockout_seconds:
            self._fail_count[acct_key] = 0
            self._first_fail[acct_key] = now
        self._fail_count[acct_key] += 1
        if (
            self._fail_count[acct_key] >= self.cfg.max_failures
            and now - self._first_fail.get(acct_key, now) < self.cfg.lockout_seconds
        ):
            self._lock_until[acct_key] = now + self.cfg.lockout_seconds
            return Judgement(
                True,
                f"account {account} locked after {self._fail_count[acct_key]} failures",
                score=1.0,
            )

        if ip:
            ip_key = f"ip:{ip}"
            if now - self._first_fail.get(ip_key, now) > self.cfg.lockout_seconds:
                self._ip_fail[ip_key] = 0
                self._first_fail[ip_key] = now
            self._ip_fail[ip_key] += 1
            if (
                self._ip_fail[ip_key] >= self.cfg.per_ip_max_failures
                and now - self._first_fail.get(ip_key, now) < self.cfg.lockout_seconds
            ):
                self._lock_until[ip_key] = now + self.cfg.lockout_seconds
                return Judgement(
                    True, f"IP {ip} locked after {self._ip_fail[ip_key]} failures", score=1.0
                )

        return Judgement(False, "failure recorded")

    def record_success(self, account: str, ip: str = "") -> None:
        self._fail_count.pop(f"acct:{account}", None)
        self._lock_until.pop(f"acct:{account}", None)
        self._first_fail.pop(f"acct:{account}", None)
        if ip:
            self._fail_count.pop(f"ip:{ip}", None)
            self._lock_until.pop(f"ip:{ip}", None)
            self._ip_fail.pop(f"ip:{ip}", None)
            self._first_fail.pop(f"ip:{ip}", None)

    def reset(self, account: str, ip: str = "") -> None:
        self.record_success(account, ip)

    def snapshot(self) -> dict[str, Any]:
        return {"locked": len(self._lock_until)}


# ---------------------------------------------------------------------------
# 5. IndirectPromptInjectionGuard
# ---------------------------------------------------------------------------


@dataclass
class InjectionConfig:
    """Tunables for the indirect prompt-injection guard."""

    instruction_markers: tuple[str, ...] = (
        "ignore all previous instructions",
        "ignore all prior instructions",
        "disregard previous instructions",
        "forget everything",
        "you are now",
        "your new role is",
        "act as",
        "from now on, you",
        "you must follow",
        "override system",
        "system prompt",
        "jailbreak",
        "output only",
        "respond in the format",
    )
    steal_verbs: tuple[str, ...] = (
        "secret",
        "api key",
        "password",
        "token",
        "credentials",
        "env",
        "reveal",
        "exfiltrate",
        "send to",
        "post to",
        "paste",
        "leak",
    )
    priority_flags: tuple[str, ...] = ("important:", "urgent:", "top priority:", "before anything:")


class IndirectPromptInjectionGuard:
    """Detect indirect prompt injection arriving through content (OWASP LLM01-indirect).

    Scans untrusted content (fetched documents, tool outputs, web pages) for the
    language of embedded instruction chains: "ignore previous instructions",
    role-reassignment, output-structure demands, and exfiltration verbs. Returns a
    per-document risk judgement so the caller can quarantine/refuse it.
    """

    def __init__(self, config: InjectionConfig | None = None) -> None:
        self.cfg = config or InjectionConfig()

    def judge(self, content: str) -> Judgement:
        text = (content or "").lower()
        if not text:
            return Judgement(False, "empty")
        score = 0.0
        reasons: list[str] = []
        lowered = text
        for marker in self.cfg.instruction_markers:
            if marker in lowered:
                score += 1.0
                reasons.append(f"instruction-marker:{marker}")
        steal_hits = sum(1 for v in self.cfg.steal_verbs if v in lowered)
        if steal_hits:
            score += steal_hits * 0.5
            reasons.append(f"exfil-verbs:{steal_hits}")
        priority_hits = sum(1 for p in self.cfg.priority_flags if p in lowered)
        if priority_hits:
            score += priority_hits * 0.25

        # A genuinely injected instruction chain needs >= 2 instruction markers
        # OR an instruction marker + exfil verbs together.
        if any("instruction-marker" in r for r in reasons) and (len(reasons) >= 2 or steal_hits):
            return Judgement(True, ";".join(reasons), score=score)
        return Judgement(False, ";".join(reasons) or "clean", score=score)

    def snapshot(self) -> dict[str, Any]:
        return {"rules": len(self.cfg.instruction_markers)}


# ---------------------------------------------------------------------------
# 6. Facade + Kernel Module
# ---------------------------------------------------------------------------


class AIDefenseFacade:
    """Composable facade over every AI-defense facet.

    Wires the five detectors together and keeps a shared result/trigger history so
    callers get one object to consult for a combined posture. Stdlib-only, thread-safe.
    """

    def __init__(
        self,
        clock: Callable[[], float] = DEFAULT_CLOCK,
        db_path: str | None = None,
        throttle: ThrottleGate | None = None,
        throttle_on: bool = False,
    ) -> None:
        self.anomaly = BehavioralAnomalyDetector(clock=clock)
        self.bot = BotTrafficClassifier(clock=clock)
        self.extraction = ModelExtractionShield(clock=clock)
        self.stuffing = CredentialStuffingGuard(clock=clock)
        self.injection = IndirectPromptInjectionGuard()
        # Rate-limiting / persistent attacker state. OFF by default (offline):
        # it is wired in but is NOT consulted by the detectors unless the caller
        # opts in via with_throttle() or throttle_on=True. This keeps existing
        # behavior unchanged while exposing real throttling to callers.
        self.throttle_on = throttle_on
        self.throttle = (
            throttle or ThrottleGate(db_path=db_path, clock=clock)
            if throttle_on or throttle is not None
            else None
        )
        self._triggers: deque[dict[str, Any]] = deque(maxlen=500)

    @classmethod
    def with_throttle(
        cls,
        clock: Callable[[], float] = DEFAULT_CLOCK,
        db_path: str | None = None,
        **throttle_kwargs: Any,  # noqa: ANN401 - forwarded verbatim to ThrottleGate
    ) -> AIDefenseFacade:
        """Build a facade with an enabled :class:`ThrottleGate`.

        ``db_path`` defaults to ``None`` (in-memory store) unless the caller
        supplies a file path for durable attacker state.
        """
        fac = cls(clock=clock, db_path=db_path, throttle_on=True)
        fac.throttle = ThrottleGate(db_path=db_path, clock=clock, **throttle_kwargs)
        return fac

    def throttle_request(self, key: str, cost: int = 1, now: float | None = None) -> Allowance:
        """Rate-limit one request from ``key``.

        Returns an :class:`Allowance`. When throttling is offline (default) this
        is a no-op allowance (``allowed=True``, ``reason="offline"``) so existing
        callers keep working.
        """
        if self.throttle is None:
            return Allowance(True, 0, 0.0, blocked=False, reason="offline")
        return self.throttle.allow(key, cost, now)

    def attacker_state(self, key: str) -> dict[str, Any] | None:
        """Durable attacker record for ``key`` (``None`` when offline/unknown)."""
        if self.throttle is None:
            return None
        return self.throttle.store.get(key)

    def _record(self, facet: str, judgement: Judgement, context: str = "") -> None:
        if judgement.malicious:
            self._triggers.append(
                {
                    "facet": facet,
                    "reason": judgement.reason,
                    "score": judgement.score,
                    "ts": DEFAULT_CLOCK(),
                    "context": context,
                }
            )

    # -- request-level combined gate over an HTTP-ish request -- #
    def gate_request(
        self,
        key: str,
        user_agent: str = "",
        headers: dict[str, str] | None = None,
        now: float | None = None,
    ) -> Judgement:
        """Combined check for a single inbound request (anomaly + bot + extraction)."""
        a = self.anomaly.observe(key, at=now)
        if a.malicious:
            self._record("anomaly", a, key)
            return a
        b = self.bot.observe_headers(key, user_agent, headers)
        if b.malicious:
            self._record("bot", b, key)
            return b
        b2 = self.bot.observe_pacing(key, at=now)
        if b2.malicious:
            self._record("bot", b2, key)
            return b2
        return Judgement(False, "allowed")

    def check_auth(self, account: str, ip: str = "", now: float | None = None) -> Judgement:
        return self.stuffing.check(account, ip, at=now)

    def record_auth_failure(
        self, account: str, ip: str = "", now: float | None = None
    ) -> Judgement:
        j = self.stuffing.record_failure(account, ip, at=now)
        self._record("stuffing", j, account)
        return j

    def record_auth_success(self, account: str, ip: str = "") -> None:
        self.stuffing.record_success(account, ip)

    def guard_model_query(self, key: str, query: str = "", now: float | None = None) -> Judgement:
        j = self.extraction.observe(key, query, at=now)
        self._record("extraction", j, key)
        return j

    def scan_content(self, content: str) -> Judgement:
        j = self.injection.judge(content)
        self._record("injection", j)
        return j

    def posture(self) -> dict[str, Any]:
        """Quantified live posture: healthy if no facets are imminently breached."""
        out = {
            "triggers_in_buffer": len(self._triggers),
            "anomaly_keys": self.anomaly.snapshot(),
            "bot_keys": self.bot.snapshot(),
            "extraction_keys": self.extraction.snapshot(),
            "locked_accounts_ips": self.stuffing.snapshot(),
            "injection_rules": self.injection.snapshot(),
        }
        if self.throttle is not None:
            out["throttle"] = {
                "active": True,
                "limit": self.throttle.limiter.limit,
                "window": self.throttle.limiter.window,
                "threshold": self.throttle.threshold,
                "block_seconds": self.throttle.block_seconds,
            }
        return out

    def healthy(self) -> bool:
        # A facade is healthy as long as it is operating; individual blocks are
        # the expected outcome of defense, not a facade malfunction.
        return True

    def recent_triggers(self, limit: int = 20) -> list[dict[str, Any]]:
        return list(self._triggers)[-limit:]


@module(name="ai_defense", version="1.0.0")
class AIDefenseModule(Module):
    """Kernel-registered module exposing the AI-defense facade to the platform."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._config = config or {}
        self.facade = self._build_facade()

    def _build_facade(self) -> AIDefenseFacade:
        """Build the facade honouring the optional ``throttle`` config block.

        Throttling stays OFF (offline) unless ``config["throttle"]["enabled"]``
        is truthy, so the module's existing behaviour is unchanged by default.
        """
        thr = (self._config or {}).get("throttle", {}) or {}
        if not thr.get("enabled"):
            return AIDefenseFacade()
        kwargs = {k: v for k, v in thr.items() if k != "enabled"}
        return AIDefenseFacade.with_throttle(**kwargs)

    async def initialize(self) -> None:
        """Initializes the module (stdlib-only; no external startup work)."""
        self._status = HealthStatus.STARTING
        self.facade = self._build_facade()
        self._status = HealthStatus.HEALTHY
        logger.info("Initializing AI Defense Module...")

    async def health_check(self) -> HealthStatus:
        return HealthStatus.HEALTHY

    async def shutdown(self) -> None:
        """Graceful shutdown (nothing to tear down beyond state)."""
        # Kernel's Module.shutdown() sets terminal state; do not reference
        # HealthStatus.STOPPED (does not exist — it's a LifecycleState).
        logger.info("AI Defense Module shutdown complete.")

    def gate_request(self, key: str, **kw: Any) -> Judgement:  # noqa: ANN401 - kwargs forwarded to facade
        return self.facade.gate_request(key, **kw)

    def check_auth(self, account: str, ip: str = "", **kw: Any) -> Judgement:  # noqa: ANN401 - kwargs forwarded to facade
        return self.facade.check_auth(account, ip, **kw)

    def scan_content(self, content: str) -> Judgement:
        return self.facade.scan_content(content)

    def guard_model_query(self, key: str, query: str = "", **kw: Any) -> Judgement:  # noqa: ANN401 - kwargs forwarded to facade
        return self.facade.guard_model_query(key, query, **kw)

    def posture(self) -> dict[str, Any]:
        return self.facade.posture()

    def throttle_request(self, key: str, cost: int = 1, **kw: Any) -> Allowance:  # noqa: ANN401 - kwargs forwarded to facade
        return self.facade.throttle_request(key, cost, **kw)

    def attacker_state(self, key: str) -> dict[str, Any] | None:
        return self.facade.attacker_state(key)
