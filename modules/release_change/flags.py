"""Runtime Feature-Flag & Canary/A-B Engine.

Master-class runtime counterpart to the descriptive deployment strategies in
``strategies.py``. While strategies describe *how* to ship (canary, blue-green,
staged rollout), this module provides the actual runtime machinery that decides,
at request time, whether a feature is live for a given user/context and which
variant they get.

Provides:
  - ``FeatureFlag``  -- immutable-ish flag definition (name, rollout %, variants
    by weight, default variant, targeting rules).
  - ``FlagEngine``   -- register/query flags; deterministic hash-bucket rollout
    and weight-based variant selection.
  - ``Canary``       -- models a live canary rollout with % promotion/rollback
    gated by an injectable health-check callback.
  - ``ReleaseGate``  -- a gate a change must pass before "go": flag exists,
    canary healthy, rollout % within policy.
  - ``AuditLog``     -- append-only log of every flag/rollout/gate decision.

Everything is deterministic: rollout buckets and variant selection use SHA-256
over ``(seed, flag_name, context_key)`` so the same context always maps to the
same bucket (A/B assignment is stable across calls and processes).

Stdlib only.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger("enterprise.release_change.flags")

# --------------------------------------------------------------------------- #
# Helpers: deterministic hash-bucket
# --------------------------------------------------------------------------- #

_BUCKET_MOD = 10_000  # 0.01% granularity


def _digest(*parts: Any) -> str:
    """Deterministic SHA-256 digest over stringified parts."""
    raw = ":".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def hash_bucket(*parts: Any) -> int:
    """Return a stable bucket in [0, _BUCKET_MOD).

    The same ``*parts`` always yields the same bucket, regardless of process,
    call order or timestamp. Used for percent-rollout and weighted variants.
    """
    return int(_digest(*parts), 16) % _BUCKET_MOD


def _rollout_hit(percent: float, seed: str, name: str, context_key: str) -> bool:
    """True when ``context_key`` falls inside the ``percent`` rollout."""
    percent = max(0.0, min(100.0, float(percent)))
    bucket = hash_bucket(seed, "rollout", name, context_key)
    return bucket < int(round(percent * (_BUCKET_MOD / 100.0)))


# --------------------------------------------------------------------------- #
# Targeting rules
# --------------------------------------------------------------------------- #


class RuleOp(StrEnum):
    """Comparison operators available in a targeting rule."""

    IN = "in"
    NOT_IN = "not_in"
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"


@dataclass
class TargetingRule:
    """A single rule against a context field.

    ``context_key`` selects the field from the evaluation ``context`` dict,
    ``op`` the comparison, ``values`` the set/list of accepted values (or a
    single scalar for ``equals``/``greater_than``/``less_than``).
    """

    context_key: str
    op: RuleOp = RuleOp.IN
    values: Any = field(default_factory=list)

    def matches(self, context: dict[str, Any]) -> bool:
        actual = context.get(self.context_key) if isinstance(context, dict) else None
        if self.op is RuleOp.IN:
            return actual in self.values
        if self.op is RuleOp.NOT_IN:
            return actual not in self.values
        if self.op is RuleOp.EQUALS:
            return actual == self.values
        if self.op is RuleOp.NOT_EQUALS:
            return actual != self.values
        if self.op is RuleOp.CONTAINS:
            return self.values in actual if isinstance(actual, (str, list, tuple)) else False
        if self.op is RuleOp.GREATER_THAN:
            try:
                return actual > self.values
            except TypeError:
                return False
        if self.op is RuleOp.LESS_THAN:
            try:
                return actual < self.values
            except TypeError:
                return False
        return False


# --------------------------------------------------------------------------- #
# FeatureFlag
# --------------------------------------------------------------------------- #


@dataclass
class FeatureFlag:
    """Definition of a single feature flag.

    Attributes:
        name: Unique flag name.
        enabled: Whether the flag is currently switched on.
        rollout_percent: Percent of eligible contexts the feature is live for.
        variants: Mapping variant-name -> relative weight. When empty the flag
            is boolean-only (on/off). When non-empty, ``get_variant`` returns a
            weighted variant and ``is_enabled`` is true when a variant is served.
        default_variant: Variant returned when context matches no bucket (e.g.
            non-rolled-out contexts, or targeting excludes the context).
        targeting_rules: Optional list of rules; if present, ALL must match for
            the flag to be considered applicable to a context.
        seed: Salt for the deterministic hash-bucket (stable A/B assignment).
    """

    name: str
    enabled: bool = True
    rollout_percent: float = 100.0
    variants: dict[str, int] = field(default_factory=dict)
    default_variant: str | None = None
    targeting_rules: list[TargetingRule] = field(default_factory=list)
    seed: str = "eni-release-change"

    def _total_weight(self) -> int:
        return sum(int(w) for w in self.variants.values())

    def applies_to(self, context: dict[str, Any] | None) -> bool:
        """True when targeting rules (if any) all match the context."""
        ctx = context or {}
        return all(rule.matches(ctx) for rule in self.targeting_rules)

    def variant_for(self, context: dict[str, Any] | None) -> str | None:
        """Deterministically choose a variant by weight for this context.

        Returns ``None`` when the flag has no variants (boolean flag) or when the
        context is not eligible (targeting miss / not rolled out).
        """
        if not self.variants:
            return None
        ctx = context or {}
        context_key = self._context_key(ctx)
        total = self._total_weight()
        if total <= 0:
            return self.default_variant
        bucket = hash_bucket(self.seed, "variant", self.name, context_key) % total
        running = 0
        for variant, weight in self.variants.items():
            running += int(weight)
            if bucket < running:
                return variant
        return self.default_variant

    @staticmethod
    def _context_key(context: dict[str, Any]) -> str:
        if "id" in context:
            return str(context["id"])
        if "user_id" in context:
            return str(context["user_id"])
        if "tenant" in context:
            return str(context["tenant"])
        # Fall back to a stable fingerprint of the whole context.
        return _digest("ctx", sorted((str(k), str(v)) for k, v in context.items()))


# --------------------------------------------------------------------------- #
# FlagEngine
# --------------------------------------------------------------------------- #


class FlagEngine:
    """Registry + evaluation engine for feature flags.

    Thread-safe via an RLock. All decisions are deterministic given the same
    seed, flag name and context key. Every decision is appended to the audit log.
    """

    def __init__(self, seed: str = "eni-release-change") -> None:
        self.seed = seed
        self._flags: dict[str, FeatureFlag] = {}
        self._lock = __import__("threading").RLock()
        self.audit: AuditLog = AuditLog()

    # -- registration ------------------------------------------------------- #

    def register_flag(
        self,
        name: str,
        enabled: bool = True,
        rollout_percent: float = 100.0,
        variants: dict[str, int] | None = None,
        default_variant: str | None = None,
        targeting_rules: list[TargetingRule] | None = None,
        seed: str | None = None,
    ) -> FeatureFlag:
        flag = FeatureFlag(
            name=name,
            enabled=enabled,
            rollout_percent=rollout_percent,
            variants=variants or {},
            default_variant=default_variant,
            targeting_rules=targeting_rules or [],
            seed=seed or self.seed,
        )
        with self._lock:
            self._flags[name] = flag
        self.audit.log(
            "flag.register",
            name=name,
            details={"rollout_percent": rollout_percent, "enabled": enabled},
        )
        return flag

    def unregister_flag(self, name: str) -> bool:
        with self._lock:
            removed = self._flags.pop(name, None) is not None
        if removed:
            self.audit.log("flag.unregister", name=name)
        return removed

    def get_flag(self, name: str) -> FeatureFlag | None:
        with self._lock:
            return self._flags.get(name)

    def flags(self) -> list[str]:
        with self._lock:
            return sorted(self._flags.keys())

    # -- mutation ----------------------------------------------------------- #

    def enable(self, name: str) -> bool:
        with self._lock:
            flag = self._flags.get(name)
            if flag is None:
                return False
            flag.enabled = True
        self.audit.log("flag.enable", name=name)
        return True

    def disable(self, name: str) -> bool:
        with self._lock:
            flag = self._flags.get(name)
            if flag is None:
                return False
            flag.enabled = False
        self.audit.log("flag.disable", name=name)
        return True

    def set_rollout(self, name: str, percent: float) -> bool:
        percent = max(0.0, min(100.0, float(percent)))
        with self._lock:
            flag = self._flags.get(name)
            if flag is None:
                return False
            flag.rollout_percent = percent
        self.audit.log("flag.set_rollout", name=name, details={"rollout_percent": percent})
        return True

    # -- evaluation --------------------------------------------------------- #

    def is_enabled(self, name: str, context: dict[str, Any] | None = None) -> bool:
        """Evaluate whether the flag is enabled for a context.

        Flag must be registered + enabled, must pass targeting, and the context
        must fall inside the rollout percent (deterministic hash bucket).
        """
        ctx = context or {}
        flag = self.get_flag(name)
        if flag is None:
            self.audit.log("flag.miss", name=name, decision=False, reason="not_registered")
            return False
        if not flag.enabled:
            self.audit.log("flag.disabled", name=name, decision=False, reason="disabled")
            return False
        if not flag.applies_to(ctx):
            self.audit.log("flag.no_target", name=name, decision=False, reason="targeting_miss")
            return False
        context_key = FeatureFlag._context_key(ctx)
        decision = _rollout_hit(flag.rollout_percent, flag.seed, name, context_key)
        self.audit.log(
            "flag.evaluate",
            name=name,
            decision=decision,
            details={"rollout_percent": flag.rollout_percent, "context_key": context_key},
        )
        return decision

    def get_variant(self, name: str, context: dict[str, Any] | None = None) -> str | None:
        """Return the weighted variant for a context, or the default.

        For boolean flags (no variants) returns ``None``. For variant flags the
        context must be enabled (rolled out) to receive a variant, otherwise the
        default_variant is returned.
        """
        ctx = context or {}
        flag = self.get_flag(name)
        if flag is None or not flag.variants:
            return None
        if not self.is_enabled(name, ctx):
            return flag.default_variant
        variant = flag.variant_for(ctx)
        self.audit.log(
            "flag.variant",
            name=name,
            decision=variant is not None,
            details={"variant": variant},
        )
        return variant


# --------------------------------------------------------------------------- #
# Canary
# --------------------------------------------------------------------------- #


class CanaryState(StrEnum):
    """Lifecycle states of a canary rollout."""

    NOT_STARTED = "not_started"
    SENDING = "sending"
    PROMOTING = "promoting"
    FULL = "full"
    ROLLED_BACK = "rolled_back"
    BLOCKED = "blocked"


class Canary:
    """Models a live canary rollout with a traffic-percentage ramp.

    ``promote()`` and ``send_traffic()`` are gated by an injectable health-check
    callback; a failing check blocks promotion. ``rollback()`` drops traffic to 0
    (instant rollback). All transitions are audited.
    """

    def __init__(
        self,
        name: str,
        initial_percent: float = 5.0,
        increment_step: float = 10.0,
        target_percent: float = 100.0,
        current_percent: float = 0.0,
        health_check: Callable[[], bool] | None = None,
        audit: AuditLog | None = None,
    ) -> None:
        self.name = name
        self.initial_percent = float(initial_percent)
        self.increment_step = float(increment_step)
        self.target_percent = float(target_percent)
        self.current_percent = float(current_percent)
        self.health_check = health_check
        self.state = CanaryState.NOT_STARTED
        self.audit = audit or AuditLog()

    # -- traffic ------------------------------------------------------------ #

    def send_traffic(self) -> dict[str, Any]:
        """Begin serving the canary at its initial percent.

        No-op if already sending. Raises if the canary was rolled back.
        """
        if self.state is CanaryState.ROLLED_BACK:
            msg = f"canary {self.name} is rolled back; re-issue a new canary"
            raise RuntimeError(msg)
        if self.state is CanaryState.FULL:
            result = self._snapshot()
            self.audit.log("canary.already_full", name=self.name, details=result)
            return result
        if self.state is CanaryState.NOT_STARTED:
            self.current_percent = self.initial_percent
            self.state = CanaryState.SENDING
        result = self._snapshot()
        self.audit.log("canary.send_traffic", name=self.name, details=result)
        return result

    def promote(self, health_check: Callable[[], bool] | None = None) -> dict[str, Any]:
        """Promote the canary by ``increment_step``, gated by health.

        Uses the instance health_check unless an explicit one is passed. When the
        health check fails (or is absent), promotion is blocked. When it passes,
        traffic increases by ``increment_step`` up to ``target_percent``.
        """
        checker = health_check or self.health_check
        if self.state is CanaryState.NOT_STARTED:
            self.send_traffic()
        if self.state is CanaryState.ROLLED_BACK:
            msg = f"canary {self.name} is rolled back"
            raise RuntimeError(msg)
        healthy = checker() if checker else None
        if healthy is False:
            self.state = CanaryState.BLOCKED
            result = self._snapshot(reason="health_check_failed")
            result["decision"] = False
            self.audit.log(
                "canary.promote_blocked",
                name=self.name,
                decision=False,
                details=result,
            )
            return result
        if healthy is True or checker is None:
            self.current_percent = min(
                self.target_percent, self.current_percent + self.increment_step
            )
            self.state = (
                CanaryState.FULL
                if self.current_percent >= self.target_percent
                else CanaryState.PROMOTING
            )
        result = self._snapshot()
        self.audit.log(
            "canary.promote",
            name=self.name,
            decision=True,
            details=result,
        )
        return result

    def rollback(self) -> dict[str, Any]:
        """Drop canary traffic to 0 immediately (instant rollback)."""
        self.current_percent = 0.0
        self.state = CanaryState.ROLLED_BACK
        result = self._snapshot()
        self.audit.log(
            "canary.rollback",
            name=self.name,
            decision=True,
            details=result,
        )
        return result

    # -- health ------------------------------------------------------------- #

    @property
    def healthy(self) -> bool:
        """Run the injectable health check (True when absent/None)."""
        if self.health_check is None:
            return True
        try:
            return bool(self.health_check())
        except Exception:  # pragma: no cover - defensive
            logger.exception("canary %s health check raised", self.name)
            return False

    def _snapshot(self, **extra: Any) -> dict[str, Any]:
        snap = {
            "name": self.name,
            "current_percent": self.current_percent,
            "target_percent": self.target_percent,
            "increment_step": self.increment_step,
            "state": self.state.value,
            "healthy": self.healthy,
        }
        snap.update(extra)
        return snap

    def to_dict(self) -> dict[str, Any]:
        return self._snapshot()


# --------------------------------------------------------------------------- #
# ReleaseGate
# --------------------------------------------------------------------------- #


class GateDecision(StrEnum):
    """Outcome of a release gate evaluation."""

    PASS = "pass"
    FAIL = "fail"
    BLOCKED = "blocked"


@dataclass
class ReleaseGate:
    """A gate a change must pass before "go".

    Combines the runtime engine with a canary and policy limits: the feature
    flag must exist, the canary must be healthy, and the live rollout percent
    must be within ``max_rollout_percent``.
    """

    name: str
    max_rollout_percent: float = 100.0
    require_canary_healthy: bool = True
    audit: AuditLog | None = None

    def evaluate(
        self,
        engine: FlagEngine,
        flag_name: str,
        canary: Canary | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Evaluate the gate for a change.

        Returns a dict with ``decision`` (PASS/FAIL/BLOCKED), a list of
        ``checks`` (each with pass/ok + reason), and ``go`` (bool).
        """
        audit = self.audit or engine.audit
        checks: list[dict[str, Any]] = []

        # 1. Flag must exist.
        flag = engine.get_flag(flag_name)
        checks.append(
            {
                "check": "flag_exists",
                "ok": flag is not None,
                "reason": "flag_registered" if flag else "flag_missing",
            }
        )

        # 2. Flag must be enabled.
        if flag is not None:
            checks.append(
                {
                    "check": "flag_enabled",
                    "ok": flag.enabled,
                    "reason": "enabled" if flag.enabled else "disabled",
                }
            )

        # 3. Rollout percent within policy.
        rollout_ok = flag is not None and flag.rollout_percent <= self.max_rollout_percent
        checks.append(
            {
                "check": "rollout_within_policy",
                "ok": rollout_ok,
                "reason": (
                    f"rollout={flag.rollout_percent}<=max={self.max_rollout_percent}"
                    if rollout_ok
                    else "rollout_exceeds_policy"
                ),
            }
        )

        # 4. Canary healthy (if required).
        canary_ok = True
        canary_reason = "no_canary_required"
        if self.require_canary_healthy and canary is not None:
            canary_ok = canary.healthy and canary.state is not CanaryState.ROLLED_BACK
            canary_reason = (
                "canary_healthy"
                if canary_ok
                else f"canary_unhealthy_or_rolled_back:state={canary.state.value}"
            )
            checks.append({"check": "canary_healthy", "ok": canary_ok, "reason": canary_reason})

        all_ok = all(c["ok"] for c in checks)
        decision = GateDecision.PASS if all_ok else GateDecision.BLOCKED
        result = {
            "gate": self.name,
            "flag_name": flag_name,
            "decision": decision.value,
            "go": all_ok,
            "checks": checks,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        audit.log(
            "gate.evaluate",
            name=self.name,
            decision=all_ok,
            details=result,
        )
        return result


# --------------------------------------------------------------------------- #
# AuditLog
# --------------------------------------------------------------------------- #


@dataclass
class AuditEntry:
    """A single audited decision."""

    action: str
    name: str
    timestamp: str
    decision: bool | None = None
    reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class AuditLog:
    """Append-only, thread-safe audit log of every flag/rollout/gate decision."""

    def __init__(self, capacity: int = 10_000) -> None:
        self._entries: list[AuditEntry] = []
        self._lock = __import__("threading").RLock()
        self._capacity = capacity

    def log(
        self,
        action: str,
        name: str,
        decision: bool | None = None,
        reason: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditEntry:
        entry = AuditEntry(
            action=action,
            name=name,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            decision=decision,
            reason=reason,
            details=details or {},
        )
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self._capacity:
                self._entries = self._entries[-self._capacity :]
        return entry

    @property
    def entries(self) -> list[AuditEntry]:
        with self._lock:
            return list(self._entries)

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def find(self, action: str | None = None, name: str | None = None) -> list[AuditEntry]:
        out = []
        for e in self._entries:
            if action is not None and e.action != action:
                continue
            if name is not None and e.name != name:
                continue
            out.append(e)
        return out
