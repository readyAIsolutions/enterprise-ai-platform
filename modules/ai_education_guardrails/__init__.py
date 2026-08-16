"""AI Education Guardrails — responsible & effective AI use in academics/edtech.

Distilled from four pulled JE Van Clief transcripts:

  * "AI in Academics: How NOT to Use It" (czIBNYeiAuw) — learning how NOT to use
    AI is the most important skill; AI as chisel vs crutch; the THINK writing
    process; equity/access (AI overwhelm, tool deficiency, community void).
  * "AI Cheating in Class? Redefining What 'Challenging' Means in Education"
    (iY_j0VKimQI) — raise the bar; redesign assessments to grade the critique
    and the prompts rather than the AI product; generic-AI-texture detection.
  * "Perils of AI and Ed-Tech" (THQH6Uc6PNU) — grade the process not the product;
    top-down critique method & structured dialogue; editable/deletable data;
    tools not meeting assessment goals erode trust.
  * "Artificial Minds, Real Ideas Ep. 1: Who Controls EdTech?" (wpM-c--FE04) —
    mini-public / bottom-up governance; process AND outcome metrics; equity —
    tools not built with diverse learners widen the achievement gap.

Export surface:
  * UsagePolicyClassifier   — labels an AI use-case MISUSE / ASSISTIVE / LEGITIMATE
                              with matched signals and rationale.
  * AssignmentRobustnessChecker — does an assessment hold up against AI / test
                              durable skills (robust / at_risk / fragile).
  * detect_submission       — misuse-detection heuristics (AI-texture, disclosure,
                              citation).
  * EdTechGovernanceChecker — who controls the tool; inclusive vs top-down.
  * AIEducationGuardrailsEngine — facade engine composing every check.
  * Module + factory:       AiEducationGuardrailsModule / create_ai_education_guardrails_module.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from enterprise.platform_kernel import HealthStatus, Module, module

# Core (pure, unit-testable) engine — re-export the full public surface.
from .guardrails import (  # noqa: F401
    AIEducationGuardrailsEngine,
    AssignmentAssessment,
    AssignmentDesign,
    AssignmentRobustnessChecker,
    EdTechGovernanceChecker,
    GovernanceAssessment,
    GovernanceModel,
    MisuseReport,
    ThinkFramework,
    ThinkStage,
    UsageClass,
    UsagePolicyClassifier,
    UsageVerdict,
    Verdict,
    GovernanceVerdict,
    build_assignment,
    detect_submission,
    __version__,
)

logger = logging.getLogger("eni.ai_education_guardrails")


def make_engine(config: Optional[Dict[str, Any]] = None) -> AIEducationGuardrailsEngine:
    """Build the core pure-logic guardrails engine (facade)."""
    cfg = config or {}
    return AIEducationGuardrailsEngine(
        policy_default=cfg.get("policy_default", "disclosure-based"),
        robust_threshold=float(cfg.get("robustness_threshold", 0.6)),
        at_risk_threshold=float(cfg.get("at_risk_threshold", 0.3)),
    )


@module(
    name="ai_education_guardrails",
    version="1.0.0",
    config_defaults={
        "policy_default": "disclosure-based",
        "robustness_threshold": 0.6,
        "at_risk_threshold": 0.3,
        "detection_flag_threshold": 0.6,
        "governance_inclusive_threshold": 0.65,
    },
)
class AiEducationGuardrailsModule(Module):
    """Enterprise module exposing responsible-AI-in-academics guardrails."""

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._engine: Optional[AIEducationGuardrailsEngine] = None

    async def initialize(self) -> None:
        try:
            self._engine = make_engine(self.config)
            self.status = HealthStatus.HEALTHY
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("ai_education_guardrails init failed")
            self.status = HealthStatus.UNHEALTHY
            raise

    async def health_check(self) -> HealthStatus:
        healthy = self._engine is not None
        self.status = HealthStatus.HEALTHY if healthy else HealthStatus.UNHEALTHY
        return self.status

    async def shutdown(self) -> None:
        self.status = HealthStatus.UNKNOWN

    # ---- facade: construct/return the core engine ----
    def engine(self) -> AIEducationGuardrailsEngine:
        """Return the core pure-logic engine (constructs on demand)."""
        if self._engine is None:
            self._engine = make_engine(self.config)
        return self._engine

    # convenience delegations so callers can use the module directly
    def classify_usage(self, usage: str) -> UsageVerdict:
        return self.engine().classify_usage(usage)

    def assess_assignment(self, design: AssignmentDesign) -> AssignmentAssessment:
        return self.engine().assess_assignment(design)

    def detect(self, text: str, disclosed: bool = False) -> MisuseReport:
        return self.engine().detect(text, disclosed=disclosed)

    def assess_governance(self, model: GovernanceModel) -> GovernanceAssessment:
        return self.engine().assess_governance(model)


def create_ai_education_guardrails_module(config: Optional[dict[str, Any]] = None) -> AiEducationGuardrailsModule:
    return AiEducationGuardrailsModule(config=config or {})


__all__ = [
    "AIEducationGuardrailsEngine",
    "AssignmentAssessment", "AssignmentDesign", "AssignmentRobustnessChecker",
    "EdTechGovernanceChecker", "GovernanceAssessment", "GovernanceModel",
    "MisuseReport", "ThinkFramework", "ThinkStage",
    "UsageClass", "UsagePolicyClassifier", "UsageVerdict",
    "Verdict", "GovernanceVerdict",
    "build_assignment", "detect_submission",
    "AiEducationGuardrailsModule", "create_ai_education_guardrails_module",
    "make_engine", "__version__",
]
