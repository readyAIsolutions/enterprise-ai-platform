"""Enterprise Prompt Guard OS Module — injection / jailbreak / policy guarding.

A stdlib-only facade that inspects an inbound prompt and returns a
:class:`GuardVerdict` deciding whether it may proceed to a model. Chains
prompt-injection detection, jailbreak detection and declarative policy
enforcement in short-circuit order, and records every decision in an
append-only :class:`AuditLog`.

All components are stdlib-only with zero external dependencies.
"""

from __future__ import annotations

from typing import Any, Dict, Optional  # noqa: F401

from enterprise.platform_kernel import HealthStatus, Module, module  # noqa: F401

from .prompt_guard import (
    AuditEntry,
    AuditLog,
    GuardFinding,
    GuardVerdict,
    Policy,
    PolicyGuard,
    PromptGuard,
    PromptGuardModule,
    PromptInjectionGuard,
)

__version__ = "1.0.0"
__module__ = "prompt_guard"

__all__ = [
    "__version__",
    "PromptGuardModule",
    "PromptGuard",
    "PromptInjectionGuard",
    "PolicyGuard",
    "Policy",
    "GuardVerdict",
    "GuardFinding",
    "AuditLog",
    "AuditEntry",
]


def create_prompt_guard_module(config: dict[str, Any] | None = None) -> PromptGuardModule:
    """Create a :class:`PromptGuardModule` from an optional config dict.

    Args:
        config: dict optionally containing ``injection`` (injection_threshold /
            jailbreak_threshold / allowlist), ``risk_threshold`` and/or
            ``audit_capacity``.
    """
    return PromptGuardModule(config or {})


_installed = PromptGuardModule  # noqa: F841  (ensures @module registration on import)
