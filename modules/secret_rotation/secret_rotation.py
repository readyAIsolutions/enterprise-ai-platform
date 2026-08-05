#!/usr/bin/env python3
"""Enterprise Secret Rotation Module (credential hygiene).

A security-model-first, stdlib-only credential hygiene engine for the ENI
Enterprise AI Platform. Tracks secrets by their SHA-256 value hash only ---
the raw secret is *never* stored or retained --- and manages rotation
policies, expiry detection, rotation scheduling, and breach revocation.

Core capabilities:

* ``SecretRecord``  --- a stored record holding only the SHA-256 value hash of
  a secret plus its lifecycle metadata. Raw values never persist.
* ``RotationPolicy`` --- a declarative policy mapping ``policy_id`` to a max
  credential age, an alert lead time, a rotation window and arbitrary tags.
* ``RotationManager`` --- the engine: policy registration, secret intake
  (hashing only), age/expiry/due computation, rotation (which bumps the
  created/expiry timestamps and preserves the full history of value hashes),
  breach revocation, listing, and an audit of the rotation/revocation trail.
* ``DueReport``       --- categorised view of every secret that is *expired*,
  *due* (inside its alert window) or *at-risk* (breach-revoked).
* ``LocalReKey``      --- abstract provider / plan abstraction for rotation
  scheduling (what to rotate next, when, and how).

Design notes for testability:
  * Time is injectable. The manager accepts an optional ``clock`` callable
    (returning epoch seconds) so tests can drive age/expiry deterministically
    without sleeping. Defaults to ``time.time``.

All components are stdlib-only (``hashlib`` + ``dataclasses`` + ``abc``).
Python 3.11+.

Version: 1.0.0
"""

from __future__ import annotations

import abc
import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from enterprise.platform_kernel import (
    EventBus,
    HealthStatus,
    Module,
    module,
)

logger = logging.getLogger("enterprise.secret_rotation")

__all__ = [
    "SecretRecord",
    "RotationPolicy",
    "DueReport",
    "LocalReKey",
    "RotationManager",
    "SecretRotationFacade",
    "SecretRotationModule",
    "hash_secret",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Seconds in one day (used for all policy age/window arithmetic).
SECONDS_PER_DAY: float = 86400.0

# Default alert lead time when a policy does not specify one.
DEFAULT_ALERT_BEFORE_DAYS: float = 7.0

# Default maximum credential age (days) when a policy does not specify one.
DEFAULT_MAX_AGE_DAYS: float = 90.0


def hash_secret(raw: str) -> str:
    """Return the SHA-256 hex digest of a raw secret value.

    This is the *only* representation of a secret the module ever retains.
    The raw input is hashed and immediately discarded.
    """
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Data records
# ---------------------------------------------------------------------------


@dataclass
class SecretRecord:
    """A stored credential record.

    Only the SHA-256 ``value_hash`` of the secret is retained --- never the
    raw value. ``history`` holds the value hashes of all previously retired
    versions of the secret (pure hash history, no raw data).
    """

    name: str
    value_hash: str
    created_at: float
    expires_at: float
    policy_id: str
    revoked: bool = False
    revoked_at: Optional[float] = None
    rotation_count: int = 0
    history: List[str] = field(default_factory=list)

    @property
    def is_revoked(self) -> bool:
        return self.revoked


@dataclass
class RotationPolicy:
    """Declarative rotation policy.

    Args:
        policy_id: Unique identifier referenced by secrets.
        max_age_days: Credential is considered expired after this many days.
        alert_before_days: Begin alerting (mark ``due``) this many days
            before expiry.
        rotation_window: Preferred scheduling window (days) in which rotation
            should be actioned (advisory for the scheduler).
        tags: Arbitrary free-form tags for grouping/policy matching.
    """

    policy_id: str
    max_age_days: float = DEFAULT_MAX_AGE_DAYS
    alert_before_days: float = DEFAULT_ALERT_BEFORE_DAYS
    rotation_window: int = 1
    tags: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.alert_before_days < 0:
            raise ValueError("alert_before_days must be >= 0")
        if self.max_age_days <= 0:
            raise ValueError("max_age_days must be > 0")


@dataclass
class DueReport:
    """Categorised view of all secrets needing attention."""

    expired: List[SecretRecord] = field(default_factory=list)
    due: List[SecretRecord] = field(default_factory=list)
    at_risk: List[SecretRecord] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.expired) + len(self.due) + len(self.at_risk)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "expired": [r.name for r in self.expired],
            "due": [r.name for r in self.due],
            "at_risk": [r.name for r in self.at_risk],
            "total": self.total,
        }


# ---------------------------------------------------------------------------
# Rotation scheduling abstraction
# ---------------------------------------------------------------------------


class LocalReKey(abc.ABC):
    """Abstract re-key provider / rotation scheduler.

    This is a **plan** abstraction: a provider computes *what* should be
    rotated (``plan_rotation``) and *how* new values are produced
    (``generate_secret``) and applied (``apply_rotation``). Concrete
    implementations may couple to a local secrets store, vault, or KMS.
    """

    def __init__(self, max_rotations_per_run: int = 5) -> None:
        self.max_rotations_per_run = max_rotations_per_run

    @abc.abstractmethod
    def generate_secret(self, name: str) -> str:
        """Produce a fresh raw secret value for ``name``."""

    @abc.abstractmethod
    def apply_rotation(self, manager: "RotationManager", name: str) -> SecretRecord:
        """Synchronise a new value back into the manager for ``name``."""

    def plan_rotation(
        self,
        manager: "RotationManager",
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Compute a rotation plan for the secrets owned by ``manager``.

        Returns a dict::

            {
                "candidates": [names due/expired, capped by max_rotations_per_run],
                "due_count": int,
                "expired_count": int,
            }
        """
        report = manager.due_report(now=now)
        ordered = []
        seen = set()
        for bucket in (report.expired, report.due):
            for rec in bucket:
                if rec.name not in seen:
                    ordered.append(rec.name)
                    seen.add(rec.name)
        return {
            "candidates": ordered[: self.max_rotations_per_run],
            "due_count": len(report.due),
            "expired_count": len(report.expired),
        }


class SequentialReKey(LocalReKey):
    """Concrete re-key provider that generates random values and applies
    them via the manager's :meth:`RotationManager.rotate`.

    Intended for local/offline or test use; production deployments would
    substitute a real vault-backed provider.
    """

    def generate_secret(self, name: str) -> str:
        import secrets as _secrets

        return f"rekey-{name}-{_secrets.token_hex(16)}"

    def apply_rotation(self, manager: "RotationManager", name: str) -> SecretRecord:
        return manager.rotate(name, self.generate_secret(name))


# ---------------------------------------------------------------------------
# Rotation manager
# ---------------------------------------------------------------------------


class RotationManager:
    """Core credential-hygiene engine.

    Thread-safe. Stores only SHA-256 hashes of secret values, never the raw
    secret. Time is injectable via ``clock`` for deterministic tests.
    """

    def __init__(
        self,
        clock: Optional[Callable[[], float]] = None,
        policies: Optional[Iterable[RotationPolicy]] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._clock: Callable[[], float] = clock or time.time
        self._policies: Dict[str, RotationPolicy] = {}
        self._secrets: Dict[str, SecretRecord] = {}
        self._revocations: int = 0
        if policies:
            for policy in policies:
                self.register_policy(policy)

    # -- clock/helpers ------------------------------------------------------

    def now(self) -> float:
        """Return the current time (epoch seconds) from the injected clock."""
        return self._clock()

    def _policy_for(self, policy_id: str) -> RotationPolicy:
        if policy_id not in self._policies:
            raise KeyError(f"unknown policy_id: {policy_id!r}")
        return self._policies[policy_id]

    # -- policies -----------------------------------------------------------

    def register_policy(self, policy: RotationPolicy) -> RotationPolicy:
        """Register (or replace) a rotation policy."""
        with self._lock:
            self._policies[policy.policy_id] = policy
            return policy

    def get_policy(self, policy_id: str) -> Optional[RotationPolicy]:
        return self._policies.get(policy_id)

    def list_policies(self) -> List[RotationPolicy]:
        with self._lock:
            return list(self._policies.values())

    # -- secret intake ------------------------------------------------------

    def set_secret(
        self,
        name: str,
        raw: str,
        policy_id: Optional[str] = None,
        now: Optional[float] = None,
    ) -> SecretRecord:
        """Store a new secret (hash-only) under ``name``.

        The raw value is hashed and never retained. If ``name`` already
        exists its record is replaced with a fresh lifecycle.
        """
        ts = now if now is not None else self.now()
        policy = self._policy_for(policy_id) if policy_id else None
        effective_policy_id = policy.policy_id if policy else "default"
        max_age_days = policy.max_age_days if policy else DEFAULT_MAX_AGE_DAYS
        with self._lock:
            record = SecretRecord(
                name=name,
                value_hash=hash_secret(raw),
                created_at=ts,
                expires_at=ts + max_age_days * SECONDS_PER_DAY,
                policy_id=effective_policy_id,
            )
            self._secrets[name] = record
            return record

    def get_secret(self, name: str) -> Optional[SecretRecord]:
        with self._lock:
            return self._secrets.get(name)

    def list_secrets(self) -> List[SecretRecord]:
        with self._lock:
            return sorted(self._secrets.values(), key=lambda r: r.name)

    # -- age / expiry / due -------------------------------------------------

    def secret_age(self, name: str) -> float:
        """Return the age (in days) since a secret was created."""
        with self._lock:
            record = self._secrets[name]
        return (self.now() - record.created_at) / SECONDS_PER_DAY

    def secret_age_at(self, name: str, now: float) -> float:
        """Age (in days) computed against an explicit timestamp."""
        with self._lock:
            record = self._secrets[name]
        return (now - record.created_at) / SECONDS_PER_DAY

    def _expires_at(self, record: SecretRecord) -> float:
        return record.expires_at

    def is_expired(self, name: str, now: Optional[float] = None) -> bool:
        """True if the secret is past its policy expiry."""
        ts = now if now is not None else self.now()
        with self._lock:
            record = self._secrets[name]
        if record.revoked:
            return False
        return ts >= record.expires_at

    def is_due(self, name: str, now: Optional[float] = None) -> bool:
        """True if the secret is inside its alert window (due soon), but not
        yet expired.

        A secret is *due* when the remaining lifetime is at or below the
        policy ``alert_before_days`` threshold (and it is not revoked and not
        already expired).
        """
        ts = now if now is not None else self.now()
        with self._lock:
            record = self._secrets[name]
            policy = self._policies.get(record.policy_id)
        if record.revoked:
            return False
        alert_before = (
            (policy.alert_before_days if policy else DEFAULT_ALERT_BEFORE_DAYS)
            * SECONDS_PER_DAY
        )
        if ts >= record.expires_at:
            return False
        return (record.expires_at - ts) <= alert_before

    # -- rotation -----------------------------------------------------------

    def rotate(self, name: str, new_raw: str, now: Optional[float] = None) -> SecretRecord:
        """Rotate the secret under ``name`` to a fresh value.

        The previous value hash is pushed onto ``history``, and created/expiry
        timestamps are bumped according to the record's policy. A rotated
        (possibly breach-revoked) record is cleared of its revoked flag.
        """
        ts = now if now is not None else self.now()
        with self._lock:
            record = self._secrets[name]
            policy = self._policies.get(record.policy_id)
            max_age_days = (
                policy.max_age_days if policy else DEFAULT_MAX_AGE_DAYS
            )
            if record.value_hash:
                record.history.append(record.value_hash)
            record.value_hash = hash_secret(new_raw)
            record.created_at = ts
            record.expires_at = ts + max_age_days * SECONDS_PER_DAY
            record.rotation_count += 1
            record.revoked = False
            record.revoked_at = None
            return record

    # -- breach revocation --------------------------------------------------

    def breached(self, name: str, now: Optional[float] = None) -> SecretRecord:
        """Mark a secret as breach-revoked.

        The secret stays in the registry (so no stale rotations re-use its
        name) but is flagged revoked with a revocation timestamp. The hash
        history is preserved for forensics.
        """
        ts = now if now is not None else self.now()
        with self._lock:
            record = self._secrets[name]
            record.revoked = True
            record.revoked_at = ts
            self._revocations += 1
            return record

    def revoke(self, name: str, now: Optional[float] = None) -> SecretRecord:
        """Alias for :meth:`breached`."""
        return self.breached(name, now=now)

    @property
    def revocation_count(self) -> int:
        with self._lock:
            return self._revocations

    # -- reporting ----------------------------------------------------------

    def due_report(self, now: Optional[float] = None) -> DueReport:
        """Categorise every secret into expired / due / at-risk buckets."""
        ts = now if now is not None else self.now()
        report = DueReport()
        with self._lock:
            records = list(self._secrets.values())
            policies = dict(self._policies)
        for rec in records:
            policy = policies.get(rec.policy_id)
            alert_before = (
                (policy.alert_before_days if policy else DEFAULT_ALERT_BEFORE_DAYS)
                * SECONDS_PER_DAY
            )
            if rec.revoked:
                report.at_risk.append(rec)
            elif ts >= rec.expires_at:
                report.expired.append(rec)
            elif (rec.expires_at - ts) <= alert_before:
                report.due.append(rec)
        return report

    def audit(self) -> Dict[str, Any]:
        """Return a summary audit of the rotation / revocation trail."""
        with self._lock:
            records = list(self._secrets.values())
        total = len(records)
        active = sum(1 for r in records if not r.revoked)
        revoked = total - active
        rotations = sum(r.rotation_count for r in records)
        report = self.due_report()
        return {
            "total_secrets": total,
            "active_secrets": active,
            "revoked_secrets": revoked,
            "rotations": rotations,
            "revocations": self.revocation_count,
            "expired": len(report.expired),
            "due": len(report.due),
            "at_risk": len(report.at_risk),
        }


# ---------------------------------------------------------------------------
# Facade
# ---------------------------------------------------------------------------


class SecretRotationFacade:
    """High-level, convenience surface over a :class:`RotationManager`.

    Exposes the most common operations (register_policy, add_secret,
    check_status, rotate, revoke, due_report) without exposing internals.
    """

    def __init__(self, manager: Optional[RotationManager] = None) -> None:
        self._manager = manager or RotationManager()

    @property
    def manager(self) -> RotationManager:
        return self._manager

    def register_policy(self, policy: RotationPolicy) -> RotationPolicy:
        return self._manager.register_policy(policy)

    def add_secret(self, name: str, raw: str, policy_id: Optional[str] = None) -> SecretRecord:
        return self._manager.set_secret(name, raw, policy_id=policy_id)

    def check_status(self, name: str) -> Dict[str, Any]:
        """Return a status dict for a single secret."""
        record = self._manager.get_secret(name)
        if record is None:
            return {"name": name, "exists": False}
        return {
            "name": name,
            "exists": True,
            "age_days": self._manager.secret_age(name),
            "expired": self._manager.is_expired(name),
            "due": self._manager.is_due(name),
            "revoked": record.revoked,
            "rotation_count": record.rotation_count,
            "policy_id": record.policy_id,
        }

    def rotate(self, name: str, new_raw: str) -> SecretRecord:
        return self._manager.rotate(name, new_raw)

    def revoke(self, name: str) -> SecretRecord:
        return self._manager.breached(name)

    def breached(self, name: str) -> SecretRecord:
        return self._manager.breached(name)

    def due_report(self) -> DueReport:
        return self._manager.due_report()

    def audit(self) -> Dict[str, Any]:
        return self._manager.audit()


# ---------------------------------------------------------------------------
# Kernel module
# ---------------------------------------------------------------------------


@module(name="secret_rotation", version="1.0.0")
class SecretRotationModule(Module):
    """Enterprise Secret Rotation Module.

    Registers the credential-hygiene engine as a kernel service so it can be
    auto-discovered, health-checked, and wired onto the platform EventBus.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._lock = threading.RLock()
        self._event_bus: Optional[EventBus] = None
        self._manager: Optional[RotationManager] = None
        self._facade: Optional[SecretRotationFacade] = None

    async def initialize(self) -> None:
        with self._lock:
            self._status = HealthStatus.STARTING
            logger.info("Initializing Secret Rotation Module...")
            default_defaults = {
                "max_age_days": DEFAULT_MAX_AGE_DAYS,
                "alert_before_days": DEFAULT_ALERT_BEFORE_DAYS,
            }
            config = {**default_defaults, **(self._config or {})}
            self._manager = RotationManager()
            # If provided via config, register any declarative policies.
            for entry in config.get("policies", []) or []:
                if isinstance(entry, RotationPolicy):
                    self._manager.register_policy(entry)
                elif isinstance(entry, dict):
                    self._manager.register_policy(
                        RotationPolicy(
                            policy_id=entry["policy_id"],
                            max_age_days=entry.get(
                                "max_age_days", config.get("max_age_days")
                            ),
                            alert_before_days=entry.get(
                                "alert_before_days", config.get("alert_before_days")
                            ),
                            rotation_window=entry.get("rotation_window", 1),
                            tags=tuple(entry.get("tags", [])),
                        )
                    )
            self._facade = SecretRotationFacade(self._manager)
            self._status = HealthStatus.HEALTHY
            logger.info("Secret Rotation Module initialized")

    async def health_check(self) -> HealthStatus:
        with self._lock:
            if self._manager is not None and self._status == HealthStatus.HEALTHY:
                return HealthStatus.HEALTHY
            return HealthStatus.UNHEALTHY

    async def shutdown(self) -> None:
        with self._lock:
            self._status = HealthStatus.STOPPING
            logger.info("Shutting down Secret Rotation Module...")
            self._manager = None
            self._facade = None
            self._status = HealthStatus.HEALTHY

    def set_event_bus(self, event_bus: EventBus) -> None:
        with self._lock:
            self._event_bus = event_bus

    def get_event_bus(self) -> Optional[EventBus]:
        with self._lock:
            return self._event_bus

    # -- facade passthrough -------------------------------------------------

    def manager(self) -> Optional[RotationManager]:
        with self._lock:
            return self._manager

    def facade(self) -> SecretRotationFacade:
        if self._facade is None:
            raise RuntimeError("Module not initialized")
        return self._facade

    def register_policy(self, policy: RotationPolicy) -> RotationPolicy:
        return self.facade().register_policy(policy)

    def add_secret(self, name: str, raw: str, policy_id: Optional[str] = None) -> SecretRecord:
        return self.facade().add_secret(name, raw, policy_id=policy_id)

    def check_status(self, name: str) -> Dict[str, Any]:
        return self.facade().check_status(name)

    def rotate(self, name: str, new_raw: str) -> SecretRecord:
        return self.facade().rotate(name, new_raw)

    def revoke(self, name: str) -> SecretRecord:
        return self.facade().revoke(name)

    def due_report(self) -> DueReport:
        return self.facade().due_report()

    def audit(self) -> Dict[str, Any]:
        return self.facade().audit()
