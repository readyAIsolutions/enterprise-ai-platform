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

from typing import Any, Dict, Optional  # noqa: F401

from enterprise.platform_kernel import (
    EventBus,  # noqa: F401
    HealthStatus,  # noqa: F401
    Module,  # noqa: F401
    module,  # noqa: F401
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
from .vault import (
    DEFAULT_PBKDF2_ITERATIONS,
    AccessAudit,
    RotationScheduler,
    SecretVault,
    VaultFacade,
)

__version__ = "1.1.0"
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
    # Master-class encrypted vault
    "SecretVault",
    "RotationScheduler",
    "AccessAudit",
    "VaultFacade",
    "DEFAULT_PBKDF2_ITERATIONS",
    "create_secret_rotation_module",
    "create_vault_facade",
]


def create_rotation_facade(config: dict[str, Any] | None = None) -> SecretRotationFacade:
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
                msg = "each policy dict requires 'policy_id'"
                raise ValueError(msg)
            facade.register_policy(
                RotationPolicy(
                    policy_id=policy_id,
                    max_age_days=entry.get("max_age_days", DEFAULT_MAX_AGE_DAYS),
                    alert_before_days=entry.get("alert_before_days", DEFAULT_ALERT_BEFORE_DAYS),
                    rotation_window=entry.get("rotation_window", 1),
                    tags=tuple(entry.get("tags", [])),
                )
            )
    return facade


def create_vault_facade(
    db_path: str,
    master_key: str,
    config: dict[str, Any] | None = None,
) -> VaultFacade:
    """Create an encrypted-at-rest :class:`VaultFacade`.

    ``config`` may carry ``iterations`` (PBKDF2 cost) and ``actor``.
    """
    cfg = config or {}
    return VaultFacade(
        db_path=db_path,
        master_key=master_key,
        iterations=cfg.get("iterations", DEFAULT_PBKDF2_ITERATIONS),
        actor=cfg.get("actor", "system"),
    )


def create_secret_rotation_module(
    config: dict[str, Any] | None = None,
) -> SecretRotationModule:
    """Create (but do not initialize) a :class:`SecretRotationModule`.

    Satisfies the standard ``create_<name>_module`` module contract so a
    platform kernel can auto-discover and lifecycle-manage this module.

    ``config`` currently wraps the same keys as :class:`SecretRotationModule`
    (``max_age_days``, ``alert_before_days``, ``policies``).  The encrypted
    vault is available separately via :class:`VaultFacade` /
    :func:`create_vault_facade`.
    """
    return SecretRotationModule(config=config or {})
