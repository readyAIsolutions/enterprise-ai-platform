"""ENI Vuln Scanner OS Module — offline LLM vulnerability scanning (garak-style).

Local, stdlib-only, black-box vulnerability scanning of LLM endpoints using
deterministic heuristic probes (keywords / regex / entropy). Each probe scores
model responses in 0..1 (higher = more vulnerable). Mirrors the ``eval_gate``
and ``model_security`` philosophy of fully unit-testable offline metrics.

Built-in probes:
  - PromptInjectionProbe   — output follows injected directives.
  - JailbreakProbe         — output drops guardrails.
  - PIILeakProbe           — output leaks emails / phones / SSNs / cards.
  - PromptExtractionProbe  — output reveals the system prompt.
  - ToxicityProbe          — output is toxic / profane.
  - DataExfilProbe         — output leaks secrets / credentials.
  - RefusalEchoProbe       — output is an (over-)refusal / defensive echo.

A :class:`ProbeRegistry` lists probes by name, :class:`Rescorer` tunes their
pass thresholds, and :class:`Scanner` runs them against a ``scanner_fn`` or a
canned victim dict, producing a :class:`ScanReport` with a risk level and
stop-rate. :class:`VulnScannerFacade` exposes the public surface behind the
@module-decorated :class:`VulnScannerModule`.

All components are stdlib-only, zero external dependencies.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from enterprise.platform_kernel import (
    EventBus,
    HealthStatus,
    Module,
    module,
)

from .vuln_scanner import (
    DEFAULT_THRESHOLD,
    DataExfilProbe,
    JailbreakProbe,
    PIILeakProbe,
    Probe,
    ProbeRegistry,
    ProbeResult,
    PromptExtractionProbe,
    PromptInjectionProbe,
    RefusalEchoProbe,
    Rescorer,
    ScanReport,
    Scanner,
    ToxicityProbe,
    VulnScannerFacade,
    VulnScannerModule,
    classify_risk,
    default_probes,
)

__version__ = "1.0.0"
__module__ = "vuln_scanner"

__all__ = [
    "__version__",
    "VulnScannerModule",
    "VulnScannerFacade",
    # Framework
    "Probe",
    "ProbeRegistry",
    "Rescorer",
    "Scanner",
    "default_probes",
    "classify_risk",
    "DEFAULT_THRESHOLD",
    # Probes
    "PromptInjectionProbe",
    "JailbreakProbe",
    "PIILeakProbe",
    "PromptExtractionProbe",
    "ToxicityProbe",
    "DataExfilProbe",
    "RefusalEchoProbe",
    # Types
    "ProbeResult",
    "ScanReport",
]

_logger = logging.getLogger("enterprise.vuln_scanner")


def create_scanner(
    config: Optional[Dict[str, Any]] = None,
) -> Scanner:
    """Create a :class:`Scanner` with the built-in probes and optional tuning.

    Args:
        config: Optional dict with ``probes`` (list of probe names to keep) and
            ``thresholds`` ({probe_name: pass_threshold}) overrides.
    """
    cfg = config or {}
    registry = ProbeRegistry()
    allowed = cfg.get("probes")
    if allowed:
        names = set(allowed)
        for name in list(registry.names):
            if name not in names:
                registry.remove(name)
    rescorer = Rescorer(registry)
    for name, val in (cfg.get("thresholds") or {}).items():
        rescorer.set_threshold(name, val)
    return Scanner(victim={}, registry=registry, rescorer=rescorer)
