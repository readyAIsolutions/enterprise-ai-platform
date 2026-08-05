"""ENI Enterprise Secret Rotation OS Module.

Credential hygiene for the ENI Enterprise AI Platform: rotation policies,
expiry tracking, rotation scheduling, and breach revocation. All secrets are
stored as SHA-256 value hashes only --- raw credentials are never retained.

The module exposes a ``@module``-registered kernel Module
(:class:`SecretRotationModule`) alongside a plain convenience facade
(:class:`SecretRotationFacade`) for direct, dependency-free use.

All components are stdlib-only with zero external dependencies.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from enterprise.platform_kernel import (
    EventBus,
    HealthStatus,
    Module,
    module,
)

from .secret_rotation import (
    DEFAULT_ALERT_BEFORE_DAYS,
    DEFAULT_MAX_AGE_DAYS,
    DueReport,
    LocalReKey,
    RotationManager,
    RotationPolicy,
    SecretRecord,
    SecretRotationFacade,
    SecretRotationModule,
    SequentialReKey,
    hash_secret,
)

__version__ = "1.0.0"
__module__ = "secret_rotation"

__all__ = [
    "__version__",
    "SecretRotationModule",
    "SecretRotationFacade",
    "RotationManager",
    "RotationPolicy",
    "SecretRecord",
    "DueReport",
    "LocalReKey",
    "SequentialReKey",
    "hash_secret",
    "DEFAULT_MAX_AGE_DAYS",
    "DEFAULT_ALERT_BEFORE_DAYS",
]


def create_rotation_facade(config: Optional[Dict[str, Any]] = None) -> SecretRotationFacade:
    """Create a standalone :class:`SecretRotationFacade`.

    If ``config`` contains ``policies`` (a list of :class:`RotationPolicy`
    instances or dicts), they are pre-registered.
    """
    facade = SecretRotationFacade()
    for entry in (config or {}).get("policies", []) or []:
        if isinstance(entry, RotationPolicy):
            facade.register_policy(entry)
        elif isinstance(entry, dict):
            policy_id = entry.get("policy_id")
            if not policy_id:
                raise ValueError("each policy dict requires 'policy_id'")
            facade.register_policy(
                RotationPolicy(
                    policy_id=policy_id,
                    max_age_days=entry.get("max_age_days", DEFAULT_MAX_AGE_DAYS),
                    alert_before_days=entry.get(
                        "alert_before_days", DEFAULT_ALERT_BEFORE_DAYS
                    ),
                    rotation_window=entry.get("rotation_window", 1),
                    tags=tuple(entry.get("tags", [])),
                )
            )
    return facade
