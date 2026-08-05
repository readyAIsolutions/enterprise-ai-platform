"""ENI Enterprise Compliance OS Module.

Offline security-control mapping & audit evidence for the ENI platform across:

* OWASP LLM Top 10 (2025)
* NIST AI RMF 1.0 core functions (GOVERN / MAP / MEASURE / MANAGE)
* MITRE ATLAS (Adversarial Threat Landscape for AI Systems)

Provides a control catalogue, a ComplianceEvaluator that computes coverage,
residual risk and PASS/FAIL against a target, a GapAnalyzer for missing
controls, and a ComplianceReport for audit snapshots.

All components are stdlib-only, zero external dependencies.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional  # noqa: F401  (re-exported API types)

from enterprise.platform_kernel import (
    EventBus,  # noqa: F401
    HealthStatus,  # noqa: F401
    Module,  # noqa: F401
    module,  # noqa: F401
)

from .compliance import (
    BUILTIN_CONTROLS,
    DEFAULT_TARGET,
    FRAMEWORK_MITRE,
    FRAMEWORK_NIST,
    FRAMEWORK_OWASP,
    STATUS_IMPLEMENTED,
    STATUS_MISSING,
    STATUS_NOT_APPLICABLE,
    STATUS_PARTIAL,
    VALID_STATUSES,
    CompControl,
    ComplianceEvaluator,
    ComplianceFacade,
    ComplianceModule,
    ComplianceReport,
    Control,
    ControlEvaluation,
    EvaluationResult,
    GapAnalyzer,
    controls_for_framework,
)
from .evidence import (
    ControlEvidence,
    EvidenceRegister,
    GapAnalysis,
    assess,
    ingest,
)

__version__ = "1.1.0"
__module__ = "compliance"


def create_compliance_module(config=None):
    """Factory: build a :class:`ComplianceModule` instance from a config dict."""
    return ComplianceModule(config)


__all__ = [
    "__version__",
    "ComplianceModule",
    "ComplianceFacade",
    "create_compliance_module",
    # Core classes
    "Control",
    "CompControl",
    "EvaluationResult",
    "ControlEvaluation",
    "ComplianceEvaluator",
    "GapAnalyzer",
    "ComplianceReport",
    "controls_for_framework",
    # Live evidence classes
    "ControlEvidence",
    "EvidenceRegister",
    "GapAnalysis",
    "assess",
    "ingest",
    # Constants
    "BUILTIN_CONTROLS",
    "STATUS_IMPLEMENTED",
    "STATUS_PARTIAL",
    "STATUS_MISSING",
    "STATUS_NOT_APPLICABLE",
    "VALID_STATUSES",
    "FRAMEWORK_OWASP",
    "FRAMEWORK_NIST",
    "FRAMEWORK_MITRE",
    "DEFAULT_TARGET",
]

_logger = logging.getLogger("enterprise.compliance")
