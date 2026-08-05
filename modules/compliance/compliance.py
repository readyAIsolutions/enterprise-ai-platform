#!/usr/bin/env python3
"""
Enterprise Compliance Module
============================
Security-control mapping & audit evidence for the ENI Enterprise AI Platform.

Implements an offline control catalogue drawn from:

  * OWASP LLM Top 10 (2025)
      LLM01 Prompt Injection, LLM02 Sensitive Information Disclosure,
      LLM03 Supply Chain, LLM04 Data and Model Poisoning,
      LLM05 Improper Output Handling, LLM06 Excessive Agency,
      LLM07 System Prompt Leakage, LLM08 Vector and Embedding Weaknesses,
      LLM09 Misinformation, LLM10 Unbounded Consumption
  * NIST AI Risk Management Framework (AI RMF 1.0) core functions
      GOVERN, MAP, MEASURE, MANAGE
  * MITRE ATLAS (Adversarial Threat Landscape for AI Systems)

The module is entirely offline and stdlib-only: it maps controls to an
implementation posture, computes coverage, quantifies residual risk, and
produces a PASS/FAIL decision against a configurable target.

Components
----------
* Control            - immutable catalogue entry (id, framework, category, ...)
* CompControl        - implementation posture for a single control
* ComplianceEvaluator - computes coverage / risk / per-control status / PASS/FAIL
* GapAnalyzer        - returns the controls that are still missing
* ComplianceReport   - a full snapshot of an assessment
* ComplianceModule   - kernel @module wrapper with lifecycle + event bus
* ComplianceFacade   - convenience surface for external callers

Stdlib-only, zero external dependencies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from enterprise.platform_kernel import (
    EventBus,
    HealthStatus,
    Module,
    module,
)

logger = logging.getLogger("enterprise.compliance")

# =============================================================================
# Status vocabulary
# =============================================================================

STATUS_IMPLEMENTED = "implemented"
STATUS_PARTIAL = "partial"
STATUS_MISSING = "missing"
STATUS_NOT_APPLICABLE = "not_applicable"

VALID_STATUSES = frozenset(
    {STATUS_IMPLEMENTED, STATUS_PARTIAL, STATUS_MISSING, STATUS_NOT_APPLICABLE}
)

# Framework identifiers (lowercase, used for filtering).
FRAMEWORK_OWASP = "owasp"
FRAMEWORK_NIST = "nist"
FRAMEWORK_MITRE = "mitre"

# Default evaluation target: every applicable control must be implemented.
DEFAULT_TARGET = "require_all_implemented"

# =============================================================================
# Control catalogue dataclasses
# =============================================================================


@dataclass(frozen=True)
class Control:
    """A single security control in the compliance catalogue.

    Attributes:
        id:          Stable identifier (e.g. "LLM01", "NIST-GOVERN-01").
        framework:   Owning framework ("owasp" | "nist" | "mitre").
        category:    Control category / NIST function / ATLAS tactic.
        title:       Short human-readable title.
        description: Longer description of what the control requires.
        required:    Whether the control is mandatory (not optional/best-effort).
    """

    id: str
    framework: str
    category: str
    title: str
    description: str
    required: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "framework": self.framework,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "required": self.required,
        }


@dataclass
class CompControl:
    """Implementation posture recorded for a single control.

    Attributes:
        category: One of 'implemented' | 'partial' | 'missing' | 'not_applicable'.
        evidence: List of audit-evidence references backing the category.
        notes:    Free-form notes captured during the assessment.
    """

    category: str = STATUS_MISSING
    evidence: List[str] = field(default_factory=list)
    notes: str = ""

    def __post_init__(self) -> None:
        if self.category not in VALID_STATUSES:
            raise ValueError(
                f"Invalid control category {self.category!r}; expected one of "
                f"{sorted(VALID_STATUSES)}"
            )

    @property
    def implemented(self) -> bool:
        return self.category == STATUS_IMPLEMENTED

    @property
    def risk_weight(self) -> float:
        """Residual-risk weight of this posture (0=implemented .. 1=missing)."""
        return {
            STATUS_IMPLEMENTED: 0.0,
            STATUS_PARTIAL: 0.5,
            STATUS_MISSING: 1.0,
            STATUS_NOT_APPLICABLE: 0.0,
        }[self.category]


# =============================================================================
# Built-in control catalogue
# =============================================================================

BUILTIN_CONTROLS: List[Control] = [
    # ------------------------------------------------------------------ OWASP
    Control(
        id="LLM01",
        framework=FRAMEWORK_OWASP,
        category="Prompt Injection",
        title="Prompt Injection",
        description="Prevent both direct and indirect prompt injection "
        "from overriding system instructions or untrusted data.",
        required=True,
    ),
    Control(
        id="LLM02",
        framework=FRAMEWORK_OWASP,
        category="Sensitive Information Disclosure",
        title="Sensitive Information Disclosure",
        description="Prevent LLM output from disclosing sensitive information "
        "or proprietary data in responses.",
        required=True,
    ),
    Control(
        id="LLM03",
        framework=FRAMEWORK_OWASP,
        category="Supply Chain",
        title="Supply Chain",
        description="Secure the software supply chain for models, weights, "
        "plugins and data sources against tampered dependencies.",
        required=True,
    ),
    Control(
        id="LLM04",
        framework=FRAMEWORK_OWASP,
        category="Data and Model Poisoning",
        title="Data and Model Poisoning",
        description="Detect and prevent poisoning of training/fine-tuning data "
        "and models via malicious content or feedback loops.",
        required=True,
    ),
    Control(
        id="LLM05",
        framework=FRAMEWORK_OWASP,
        category="Improper Output Handling",
        title="Improper Output Handling",
        description="Validate, sanitize, and handle LLM output before it is "
        "passed to downstream systems (e.g. RCE, XSS).",
        required=True,
    ),
    Control(
        id="LLM06",
        framework=FRAMEWORK_OWASP,
        category="Excessive Agency",
        title="Excessive Agency",
        description="Limit the permissions/functions granted to an LLM agent "
        "to the minimum needed, with human approval gates where appropriate.",
        required=True,
    ),
    Control(
        id="LLM07",
        framework=FRAMEWORK_OWASP,
        category="System Prompt Leakage",
        title="System Prompt Leakage",
        description="Prevent disclosure of confidential system prompts, "
        "instructions and chain-of-thought to end users.",
        required=True,
    ),
    Control(
        id="LLM08",
        framework=FRAMEWORK_OWASP,
        category="Vector and Embedding Weaknesses",
        title="Vector and Embedding Weaknesses",
        description="Protect vector databases and embedding pipelines against "
        "poisoning, inversion, and extraction attacks.",
        required=True,
    ),
    Control(
        id="LLM09",
        framework=FRAMEWORK_OWASP,
        category="Misinformation",
        title="Misinformation",
        description="Mitigate hallucinations and misinformation to prevent "
        "the system from producing false or misleading content.",
        required=True,
    ),
    Control(
        id="LLM10",
        framework=FRAMEWORK_OWASP,
        category="Unbounded Consumption",
        title="Unbounded Consumption",
        description="Apply limits on resource consumption (tokens, compute, "
        "cost, concurrency) to prevent DoS and cost-exhaustion attacks.",
        required=True,
    ),
    # ------------------------------------------------------------------- NIST
    Control(
        id="NIST-GOVERN-01",
        framework=FRAMEWORK_NIST,
        category="GOVERN",
        title="AI Risk Governance Structure",
        description="Establish governance structure, roles, responsibilities "
        "and policies to manage AI risks across the organization.",
        required=True,
    ),
    Control(
        id="NIST-MAP-01",
        framework=FRAMEWORK_NIST,
        category="MAP",
        title="AI Risk Context Mapping",
        description="Contextualize the AI system and map the AI risk "
        "landscape, including intended use, assets and threat actors.",
        required=True,
    ),
    Control(
        id="NIST-MEASURE-01",
        framework=FRAMEWORK_NIST,
        category="MEASURE",
        title="AI Risk Measurement",
        description="Identify, analyze and measure AI risks using quantitative "
        "and qualitative metrics and test/evaluation evidence.",
        required=True,
    ),
    Control(
        id="NIST-MANAGE-01",
        framework=FRAMEWORK_NIST,
        category="MANAGE",
        title="AI Risk Management",
        description="Plan, prioritize, respond to, and recover from AI risks, "
        "including incident response and continuous monitoring.",
        required=True,
    ),
    # ------------------------------------------------------------------ MITRE
    Control(
        id="ATLAS-AML-T0010",
        framework=FRAMEWORK_MITRE,
        category="Reconnaissance",
        title="ATLAS Reconnaissance Tactic Controls",
        description="Detect and mitigate reconnaissance of ML assets, "
        "including model discovery, data harvesting and capability probing.",
        required=True,
    ),
    Control(
        id="ATLAS-AML-T0020",
        framework=FRAMEWORK_MITRE,
        category="Attacks on ML",
        title="ML Model Poisoning Controls",
        description="Detect and mitigate poisoning of models, datasets and "
        "machine-learning operations pipelines.",
        required=True,
    ),
    Control(
        id="ATLAS-AML-T0030",
        framework=FRAMEWORK_MITRE,
        category="Attacks on ML",
        title="Evasion Controls",
        description="Detect and mitigate evasion of ML models via adversarial "
        "examples and input perturbation.",
        required=True,
    ),
    Control(
        id="ATLAS-AML-T0040",
        framework=FRAMEWORK_MITRE,
        category="Attacks on ML",
        title="ML Model Inference Controls",
        description="Detect and mitigate model extraction and inference "
        "attacks that reconstruct model behavior or training data.",
        required=True,
    ),
]

# Convenience index by control id.
_BUILTIN_INDEX: Dict[str, Control] = {c.id: c for c in BUILTIN_CONTROLS}


def controls_for_framework(framework: Optional[str]) -> List[Control]:
    """Return the built-in controls for the given framework (case-insensitive).

    ``None`` returns the full catalogue across all frameworks.
    """
    if framework is None:
        return list(BUILTIN_CONTROLS)
    fw = str(framework).lower()
    return [c for c in BUILTIN_CONTROLS if c.framework.lower() == fw]


# =============================================================================
# Evaluation results
# =============================================================================


@dataclass
class ControlEvaluation:
    """Evaluated posture for a single control."""

    control: Control
    status: str
    evidence: List[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class EvaluationResult:
    """Aggregate output of a ComplianceEvaluator assessment."""

    framework: Optional[str]
    results: List[ControlEvaluation]
    coverage: float
    risk_score: float
    passed: bool
    implemented: int
    partial: int
    missing: int
    not_applicable: int

    @property
    def total_applicable(self) -> int:
        return self.implemented + self.partial + self.missing


# =============================================================================
# ComplianceEvaluator
# =============================================================================


class ComplianceEvaluator:
    """Compute an overall compliance posture from a per-control status map.

    Input ``status_map`` maps a control id to one of:

      * a string status ("implemented" | "partial" | "missing" | "not_applicable")
      * a :class:`CompControl` carrying category + evidence + notes

    Controls present in the catalogue but absent from the map default to
    ``missing`` (no evidence), so omitting a control lowers coverage and can
    fail the assessment. ``not_applicable`` controls are excluded from the
    coverage / risk denominators.

    Targets (``target`` argument):
      * ``"require_all_implemented"`` (default) - every applicable control
        must be ``implemented``; any partial or missing fails.
      * ``"no_missing"`` - passes unless at least one applicable control is
        missing (partial is tolerated).
      * a number ``0..100`` - passes iff ``coverage >= target``.
    """

    def __init__(
        self,
        target: Union[str, float] = DEFAULT_TARGET,
        controls: Optional[List[Control]] = None,
    ) -> None:
        self._controls = list(controls) if controls is not None else BUILTIN_CONTROLS
        self._target = target

    # -- per-control posture -------------------------------------------------

    def _resolve(
        self, control: Control, raw: Any
    ) -> ControlEvaluation:
        """Coerce a raw map value into a normalized ControlEvaluation."""
        if isinstance(raw, CompControl):
            comp = raw
        elif raw in VALID_STATUSES:
            comp = CompControl(category=raw)  # type: ignore[arg-type]
        else:
            comp = CompControl(
                category=STATUS_MISSING,
                notes="No valid status or evidence supplied",
            )
        return ControlEvaluation(
            control=control,
            status=comp.category,
            evidence=list(comp.evidence),
            notes=comp.notes,
        )

    def _applicable(self, results: List[ControlEvaluation]):
        return [r for r in results if r.status != STATUS_NOT_APPLICABLE]

    # -- aggregate metrics ---------------------------------------------------

    def evaluate(
        self,
        status_map: Optional[Dict[str, Any]] = None,
        framework: Optional[str] = None,
        target: Optional[Union[str, float]] = None,
    ) -> EvaluationResult:
        """Produce a full per-control + aggregate evaluation."""
        status_map = status_map or {}
        tgt = DEFAULT_TARGET if target is None else target

        considered = [
            c for c in self._controls
            if framework is None or c.framework.lower() == str(framework).lower()
        ]
        results = [self._resolve(c, status_map.get(c.id)) for c in considered]
        applicable = self._applicable(results)

        n = len(applicable)
        implemented = sum(1 for r in applicable if r.status == STATUS_IMPLEMENTED)
        partial = sum(1 for r in applicable if r.status == STATUS_PARTIAL)
        missing = sum(1 for r in applicable if r.status == STATUS_MISSING)
        not_applicable = len(results) - n

        coverage = (implemented + partial) / n * 100.0 if n else 100.0
        risk_score = (
            (0.0 * implemented + 0.5 * partial + 1.0 * missing) / n * 100.0
            if n
            else 0.0
        )
        passed = self._compute_passed(
            implemented, partial, missing, coverage, applicable, tgt
        )

        return EvaluationResult(
            framework=framework,
            results=results,
            coverage=round(coverage, 2),
            risk_score=round(risk_score, 2),
            passed=passed,
            implemented=implemented,
            partial=partial,
            missing=missing,
            not_applicable=not_applicable,
        )

    def _compute_passed(
        self,
        implemented: int,
        partial: int,
        missing: int,
        coverage: float,
        applicable: List[ControlEvaluation],
        target: Union[str, float],
    ) -> bool:
        if not applicable:
            # No applicable controls -> trivially compliant.
            return True
        if isinstance(target, (int, float)) and not isinstance(target, bool):
            return coverage >= float(target)
        if target == "no_missing":
            return missing == 0
        # default: require_all_implemented
        return missing == 0 and partial == 0

    def compute_coverage(
        self,
        status_map: Optional[Dict[str, Any]] = None,
        framework: Optional[str] = None,
    ) -> float:
        """Return coverage percentage (implemented + partial over applicable)."""
        return self.evaluate(status_map, framework).coverage

    def compute_risk(
        self,
        status_map: Optional[Dict[str, Any]] = None,
        framework: Optional[str] = None,
    ) -> float:
        """Return residual risk score 0..100."""
        return self.evaluate(status_map, framework).risk_score

    def passes(
        self,
        status_map: Optional[Dict[str, Any]] = None,
        framework: Optional[str] = None,
        target: Optional[Union[str, float]] = None,
    ) -> bool:
        """Return True if the assessment passes the (possibly overridden) target."""
        return self.evaluate(status_map, framework, target).passed


# =============================================================================
# GapAnalyzer
# =============================================================================


class GapAnalyzer:
    """Identify compliance gaps (missing controls) from a status map."""

    def find_missing(
        self,
        status_map: Optional[Dict[str, Any]] = None,
        framework: Optional[str] = None,
    ) -> List[Control]:
        """Return controls assessed as ``missing`` (or omitted from the map)."""
        status_map = status_map or {}
        missing: List[Control] = []
        for c in controls_for_framework(framework):
            raw = status_map.get(c.id)
            if isinstance(raw, CompControl):
                status = raw.category
            else:
                status = raw if raw in VALID_STATUSES else STATUS_MISSING
            if status == STATUS_MISSING:
                missing.append(c)
        return missing

    def find_partial(
        self,
        status_map: Optional[Dict[str, Any]] = None,
        framework: Optional[str] = None,
    ) -> List[Control]:
        status_map = status_map or {}
        partial: List[Control] = []
        for c in controls_for_framework(framework):
            raw = status_map.get(c.id)
            if isinstance(raw, CompControl):
                status = raw.category
            else:
                status = raw if raw in VALID_STATUSES else STATUS_MISSING
            if status == STATUS_PARTIAL:
                partial.append(c)
        return partial


# =============================================================================
# ComplianceReport
# =============================================================================


@dataclass
class ComplianceReport:
    """A complete snapshot of a single compliance assessment."""

    framework: Optional[str]
    controls: List[ControlEvaluation]
    coverage: float
    risk_score: float
    passed: bool
    gaps: List[Control]
    timestamp: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            "framework": self.framework,
            "controls": [
                {
                    "id": r.control.id,
                    "framework": r.control.framework,
                    "category": r.control.category,
                    "title": r.control.title,
                    "status": r.status,
                    "evidence": r.evidence,
                    "notes": r.notes,
                }
                for r in self.controls
            ],
            "coverage": self.coverage,
            "risk_score": self.risk_score,
            "passed": self.passed,
            "gaps": [c.id for c in self.gaps],
            "timestamp": self.timestamp.isoformat(),
        }


# =============================================================================
# ComplianceFacade
# =============================================================================


class ComplianceFacade:
    """Convenience facade for programmatic access to the compliance module.

    Example:
        facade = ComplianceFacade()
        facade.list_controls("owasp")
        facade.evaluate({"LLM01": "implemented", ...}, "owasp")
        facade.gap_analysis(status_map, "nist")
        facade.report(status_map, framework="owasp")
    """

    def __init__(
        self,
        evaluator: Optional[ComplianceEvaluator] = None,
        analyzer: Optional[GapAnalyzer] = None,
        register: Optional["EvidenceRegister"] = None,
    ) -> None:
        self._evaluator = evaluator or ComplianceEvaluator()
        self._analyzer = analyzer or GapAnalyzer()
        from .evidence import EvidenceRegister, GapAnalysis
        self._register = register if register is not None else EvidenceRegister()
        self._gap_analysis = GapAnalysis(self._register)

    @property
    def evaluator(self) -> ComplianceEvaluator:
        return self._evaluator

    @property
    def register(self) -> "EvidenceRegister":
        """The live evidence register backing evidence-based assessment."""
        return self._register

    def add_evidence(self, evidence) -> int:
        """Record a :class:`ControlEvidence` (or dict) into the register."""
        return self._register.add(evidence)

    def ingest(self, results, source: str = "scan",
               framework: Optional[str] = None) -> int:
        """Bulk-add evidence from a scan-results mapping."""
        from .evidence import ingest as _ingest
        return _ingest(results, self._register, source=source, framework=framework)

    def assess(self, framework: Optional[str] = None,
               top_n: int = 5) -> Dict[str, Any]:
        """Produce a live evidence-based gap report for a framework (or all)."""
        return self._gap_analysis.analyze(framework=framework, top_n=top_n)


    def list_controls(self, framework: Optional[str] = None) -> List[Control]:
        """Return the control catalogue, optionally filtered by framework."""
        return controls_for_framework(framework)

    def evaluate(
        self,
        status_map: Optional[Dict[str, Any]] = None,
        framework: Optional[str] = None,
        target: Optional[Union[str, float]] = None,
    ) -> EvaluationResult:
        return self._evaluator.evaluate(status_map, framework, target)

    def gap_analysis(
        self,
        status_map: Optional[Dict[str, Any]] = None,
        framework: Optional[str] = None,
    ) -> Dict[str, List[Control]]:
        """Return a breakdown of gaps: only the missing controls."""
        return {
            "missing": self._analyzer.find_missing(status_map, framework),
            "partial": self._analyzer.find_partial(status_map, framework),
        }

    def report(
        self,
        status_map: Optional[Dict[str, Any]] = None,
        framework: Optional[str] = None,
        target: Optional[Union[str, float]] = None,
        now: Optional[datetime] = None,
    ) -> ComplianceReport:
        """Produce a full :class:`ComplianceReport`."""
        result = self._evaluator.evaluate(status_map, framework, target)
        gaps = self._analyzer.find_missing(status_map, framework)
        return ComplianceReport(
            framework=result.framework,
            controls=result.results,
            coverage=result.coverage,
            risk_score=result.risk_score,
            passed=result.passed,
            gaps=gaps,
            timestamp=now or datetime.now(timezone.utc),
        )


# =============================================================================
# Module wrapper - Platform Kernel integration
# =============================================================================


@module(name="compliance", version="1.0.0")
class ComplianceModule(Module):
    """Enterprise Compliance Module (OWASP / NIST AI RMF / MITRE ATLAS)."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        from .evidence import EvidenceRegister
        self._evaluator = ComplianceEvaluator()
        self._analyzer = GapAnalyzer()
        db_path = (config or {}).get("db_path")
        self._register = EvidenceRegister(db_path=db_path)
        self._facade = ComplianceFacade(
            self._evaluator, self._analyzer, self._register
        )
        self._event_bus: Optional[EventBus] = None

    async def initialize(self) -> None:
        self._status = HealthStatus.STARTING
        logger.info("Initializing Compliance Module...")
        default_config = {
            "framework": None,
            "target": DEFAULT_TARGET,
            "db_path": None,
        }
        default_config.update(self._config or {})
        target = default_config.get("target", DEFAULT_TARGET)
        db_path = default_config.get("db_path")
        from .evidence import EvidenceRegister, GapAnalysis
        self._evaluator = ComplianceEvaluator(target=target)
        # Recreate register on re-init (keeps db_path from config).
        self._register = EvidenceRegister(db_path=db_path)
        self._facade = ComplianceFacade(
            self._evaluator, self._analyzer, self._register
        )
        self._gap_analysis = GapAnalysis(self._register)
        self._status = HealthStatus.HEALTHY
        logger.info("Compliance Module initialized")

    async def health_check(self) -> HealthStatus:
        if self._evaluator is not None and self._status == HealthStatus.HEALTHY:
            return HealthStatus.HEALTHY
        return HealthStatus.UNHEALTHY

    async def shutdown(self) -> None:
        self._status = HealthStatus.STOPPING
        logger.info("Shutting down Compliance Module...")
        self._status = HealthStatus.HEALTHY

    def set_event_bus(self, event_bus: Optional[EventBus]) -> None:
        self._event_bus = event_bus

    @property
    def facade(self) -> ComplianceFacade:
        return self._facade

    # -- delegate facade methods --------------------------------------------

    def list_controls(self, framework: Optional[str] = None) -> List[Control]:
        return self._facade.list_controls(framework)

    def evaluate(
        self,
        status_map: Optional[Dict[str, Any]] = None,
        framework: Optional[str] = None,
        target: Optional[Union[str, float]] = None,
    ) -> EvaluationResult:
        return self._facade.evaluate(status_map, framework, target)

    def gap_analysis(
        self,
        status_map: Optional[Dict[str, Any]] = None,
        framework: Optional[str] = None,
    ) -> Dict[str, List[Control]]:
        return self._facade.gap_analysis(status_map, framework)

    def report(
        self,
        status_map: Optional[Dict[str, Any]] = None,
        framework: Optional[str] = None,
        target: Optional[Union[str, float]] = None,
    ) -> ComplianceReport:
        return self._facade.report(status_map, framework, target)

    # -- live evidence-based assessment -------------------------------------

    @property
    def register(self):
        """The module's live :class:`EvidenceRegister`."""
        return self._register

    def add_evidence(self, evidence) -> int:
        """Record evidence into the module's register."""
        return self._facade.add_evidence(evidence)

    def ingest(self, results, source: str = "scan",
               framework: Optional[str] = None) -> int:
        """Bulk-add evidence from a scan-results mapping."""
        return self._facade.ingest(results, source=source, framework=framework)

    def assess(self, framework: Optional[str] = None,
               top_n: int = 5) -> Dict[str, Any]:
        """Produce a live evidence-based gap report."""
        return self._facade.assess(framework=framework, top_n=top_n)


__all__ = [
    "STATUS_IMPLEMENTED",
    "STATUS_PARTIAL",
    "STATUS_MISSING",
    "STATUS_NOT_APPLICABLE",
    "VALID_STATUSES",
    "FRAMEWORK_OWASP",
    "FRAMEWORK_NIST",
    "FRAMEWORK_MITRE",
    "DEFAULT_TARGET",
    "Control",
    "CompControl",
    "BUILTIN_CONTROLS",
    "controls_for_framework",
    "ControlEvaluation",
    "EvaluationResult",
    "ComplianceEvaluator",
    "GapAnalyzer",
    "ComplianceReport",
    "ComplianceFacade",
    "ComplianceModule",
]
