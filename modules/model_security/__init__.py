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
from typing import Any, Dict, List, Optional

from enterprise.platform_kernel import (
    EventBus,
    HealthStatus,
    Module,
    module,
)

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
    SecurityPipeline,
    SecretMatch,
    ThreatCategory,
)

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
def create_security_pipeline(config: Optional[Dict[str, Any]] = None) -> SecurityPipeline:
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