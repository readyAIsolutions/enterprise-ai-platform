"""ENI Model Security OS Module.

Model-agnostic security pipeline providing infrastructure-level guards that work
regardless of whether the underlying model is compromised. Implements OWASP LLM
Top 10 mitigations at the infrastructure layer.

Features:
- Input sanitization (secrets, PII, credentials) before model sees them
- Prompt injection detection (OWASP LLM01) - infrastructure regex/heuristics
- Jailbreak detection - role-play, encoding, hypothetical, translation
- Output validation - secret leakage, PII, exfiltration, refusals, toxicity
- Tamper-evident audit logging with hash-chained entries
- Declarative policy engine (YAML) for allow/deny/transform rules
- SecurityPipeline orchestrating all guards in correct order

All components are stdlib-only, zero external dependencies.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional  # noqa: F401

from enterprise.platform_kernel import (
    EventBus,  # noqa: F401
    HealthStatus,  # noqa: F401
    Module,  # noqa: F401
    module,  # noqa: F401
)

from .deployment_gate import DeploymentSecurityError, DeploymentSecurityGate  # noqa: F401
from .model_security import (
    AuditEntry,
    AuditLogger,
    GuardAction,
    GuardFinding,
    GuardResult,
    InputSanitizer,
    JailbreakShield,
    ModelSecurityModule,
    OutputValidator,
    PipelineResult,
    PolicyEngine,
    PromptInjectionShield,
    SecretMatch,
    SecurityPipeline,
    ThreatCategory,
)
from .probe_detector import (
    AttemptResult,  # noqa: F401
    DataExfilProbe,  # noqa: F401
    Detector,  # noqa: F401
    DetectorResult,  # noqa: F401
    GenericFlagDetector,  # noqa: F401
    InjectionDetector,  # noqa: F401
    JailbreakDetector,  # noqa: F401
    JailbreakProbe,  # noqa: F401
    PIILeakDetector,  # noqa: F401
    PIILeakProbe,  # noqa: F401
    Probe,  # noqa: F401
    PromptInjectionProbe,  # noqa: F401
    ScanReport,  # noqa: F401
    SecurityScanner,  # noqa: F401
    get_detector,  # noqa: F401
    get_probe,  # noqa: F401
    list_detectors,  # noqa: F401
    list_probes,  # noqa: F401
    register_detector,  # noqa: F401
    register_probe,  # noqa: F401
)
from .redteam_bench import RedTeamBench  # noqa: F401
from .security_gate import SecurityGate  # noqa: F401
from .security_health import SecurityHealth  # noqa: F401

__version__ = "1.0.0"
__module__ = "model_security"

__all__ = [
    "__version__",
    "ModelSecurityModule",
    # Core classes
    "SecurityPipeline",
    "InputSanitizer",
    "PromptInjectionShield",
    "JailbreakShield",
    "OutputValidator",
    "AuditLogger",
    "PolicyEngine",
    # Types
    "GuardAction",
    "ThreatCategory",
    "GuardFinding",
    "GuardResult",
    "PipelineResult",
    "SecretMatch",
    "AuditEntry",
]

_logger = logging.getLogger("enterprise.model_security")


# Convenience function for external use
def create_security_pipeline(config: dict[str, Any] | None = None) -> SecurityPipeline:
    """Create a SecurityPipeline with default or custom configuration."""
    default_config = {
        "audit_path": "data/model_security_audit.log",
        "policy_path": "config/security_policies.yaml",
        "injection_threshold": 0.7,
        "jailbreak_threshold": 0.7,
        "toxicity_threshold": 0.7,
        "refusal_threshold": 0.8,
    }
    if config:
        default_config.update(config)
    return SecurityPipeline(default_config)
