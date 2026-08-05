"""
Research & Verification OS — Enterprise Platform Kernel Module v1.0.0
======================================================================

Enterprise-grade module implementing the Research & Verification Operating
System for the ENI Enterprise AI platform, per the Research OS spec.

Produces trustworthy, evidence-based outputs by retrieving, validating,
comparing, ranking, and synthesizing information before it is accepted
into organizational memory or engineering decisions.

Core components (aligned with Research OS spec):
  - ResearchPlanner       — plan research, classify domain, scope investigation
  - SourceRanker          — rank sources by authority (internal > vendor > standard > academic > tech pub > community)
  - ClaimDetector         — detect conflicting claims, distinguish facts from assumptions
  - ConfidenceAssigner    — assign confidence levels to findings with transparent reasoning
  - EvidenceSynthesizer   — synthesize evidence into unified findings with recommendations
  - ProvenanceTracker     — preserve provenance chains, version research, trace lineage

Workflow (per spec):  Understand → Classify → Check internal → Retrieve external →
                       Rank → Compare → Detect conflicts → Assign confidence →
                       Produce findings → Recommend actions → Store validated knowledge.

Core Principles:
  - Truth before speed
  - Verify before concluding
  - Prefer authoritative sources
  - Distinguish facts from assumptions
  - Preserve provenance
  - Version research
  - Never fabricate evidence

Events emitted:
  - research.plan.created        — a new research plan created
  - research.sources.ranked      — sources have been ranked
  - research.claims.detected     — claims extracted and classified
  - research.confidence.assigned — confidence scores assigned
  - research.evidence.synthesized— findings synthesized into report
  - research.provenance.recorded — provenance chain stored
  - research.completed           — full research pipeline finished

Metrics tracked:
  - sources_ranked              — count of ranked sources
  - claims_detected             — count of detected claims
  - conflicts_found             — count of conflicting claims
  - average_confidence          — avg confidence score across findings
  - pipeline_duration_ms        — end-to-end research pipeline time

Architecture:
    __init__.py              — Module housekeeping, @module registration, exports
    research_engine.py       — ResearchPlanner, SourceRanker, ClaimDetector,
                                ConfidenceAssigner, EvidenceSynthesizer, ProvenanceTracker
    source_ranker.py         — SourceRanker standalone with authority tiers
    claim_detector.py        — ClaimDetector standalone with fact/assumption classification
    confidence.py            — ConfidenceAssigner standalone with score computation
    evidence_synthesizer.py  — EvidenceSynthesizer standalone with narrative generation
    tests/tests_research.py  — 25+ production-quality tests
"""

from __future__ import annotations

import sys
import os

# Ensure enterprise path is available
_ENTERPRISE_DIR = os.path.dirname(os.path.dirname(__file__))
_PARENT = os.path.dirname(_ENTERPRISE_DIR)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

# Platform kernel imports
try:
    from enterprise.platform_kernel import Module, module, HealthStatus
except ImportError:
    from platform_kernel import Module, module, HealthStatus

# Core research engine
from .research_engine import (
    ResearchPlanner,
    SourceRanker,
    ClaimDetector,
    ConfidenceAssigner,
    EvidenceSynthesizer,
    ProvenanceTracker,
    ResearchPlan,
    RankedSource,
    DetectedClaim,
    ConfidenceAssessment,
    SynthesizedEvidence,
    ProvenanceRecord,
    ResearchDomain,
    SourceTier,
    ClaimType,
    ConfidenceLevel,
    ResearchFindings,
)

# Standalone components
from .source_ranker import (
    SourceRanker as StandaloneSourceRanker,
    SourcePriorities,
    rank_source,
)

from .claim_detector import (
    ClaimDetector as StandaloneClaimDetector,
    classify_claim,
    extract_claims,
)

from .confidence import (
    ConfidenceAssigner as StandaloneConfidenceAssigner,
    compute_confidence,
    aggregate_confidence,
)

from .evidence_synthesizer import (
    EvidenceSynthesizer as StandaloneEvidenceSynthesizer,
    synthesize_evidence,
    generate_recommendations,
)

# Hardened verifier + evidence-chain report layer
from .verifier import (
    Source,
    SourceCredibility,
    Verdict,
    EvidenceChain,
    Verifier,
    VerificationReport,
    verify_report,
    verify_claim,
    VALID_TIERS,
    TIER_BASE_CREDIBILITY,
    PRIMARY_TIER,
    GOV_TIER,
    ACADEMIC_TIER,
    NEWS_TIER,
    UNKNOWN_TIER,
    BANNED_TIER,
)

# ── Module class registered with the platform kernel ──────────────────────


@module(name="research_verification", version="1.0.0")
class ResearchVerificationModule(Module):
    """Enterprise Research & Verification OS Module.

    Implements the full Research OS workflow: plan research, rank sources,
    detect claims, assign confidence, synthesize evidence, track provenance.

    Lifecycle:
        initialize()  → primes engines, validates component integrity
        health_check() → verifies all 6 core engines operational
        shutdown()    → flushes pending research, preserves provenance
    """

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self._planner: ResearchPlanner | None = None
        self._ranker: SourceRanker | None = None
        self._detector: ClaimDetector | None = None
        self._conf_assigner: ConfidenceAssigner | None = None
        self._synthesizer: EvidenceSynthesizer | None = None
        self._tracker: ProvenanceTracker | None = None

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def planner(self) -> ResearchPlanner | None:
        """The active ResearchPlanner instance."""
        return self._planner

    @property
    def ranker(self) -> SourceRanker | None:
        """The active SourceRanker instance."""
        return self._ranker

    @property
    def detector(self) -> ClaimDetector | None:
        """The active ClaimDetector instance."""
        return self._detector

    @property
    def confidence(self) -> ConfidenceAssigner | None:
        """The active ConfidenceAssigner instance."""
        return self._conf_assigner

    @property
    def synthesizer(self) -> EvidenceSynthesizer | None:
        """The active EvidenceSynthesizer instance."""
        return self._synthesizer

    @property
    def tracker(self) -> ProvenanceTracker | None:
        """The active ProvenanceTracker instance."""
        return self._tracker

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Initialize all six Research OS engines.

        Creates and validates ResearchPlanner, SourceRanker, ClaimDetector,
        ConfidenceAssigner, EvidenceSynthesizer, and ProvenanceTracker.
        """
        self._status = HealthStatus.STARTING

        self._planner = ResearchPlanner(config=self._config.get("planner", {}))
        self._ranker = SourceRanker(config=self._config.get("ranker", {}))
        self._detector = ClaimDetector(config=self._config.get("detector", {}))
        self._conf_assigner = ConfidenceAssigner(config=self._config.get("confidence", {}))
        self._synthesizer = EvidenceSynthesizer(config=self._config.get("synthesizer", {}))
        self._tracker = ProvenanceTracker(config=self._config.get("tracker", {}))

        self._status = HealthStatus.HEALTHY

    async def health_check(self) -> HealthStatus:
        """Validate all six components are operational."""
        components = [
            self._planner,
            self._ranker,
            self._detector,
            self._conf_assigner,
            self._synthesizer,
            self._tracker,
        ]
        none_count = sum(1 for c in components if c is None)
        if none_count == 0:
            self._status = HealthStatus.HEALTHY
        elif none_count <= 2:
            self._status = HealthStatus.DEGRADED
        else:
            self._status = HealthStatus.UNHEALTHY
        return self._status

    async def shutdown(self) -> None:
        """Gracefully shut down all research engines."""
        self._status = HealthStatus.STOPPING
        self._planner = None
        self._ranker = None
        self._detector = None
        self._conf_assigner = None
        self._synthesizer = None
        self._tracker = None
        self._status = HealthStatus.HEALTHY

    # ── Convenience: full pipeline execution ─────────────────────────────

    async def execute_pipeline(self, objective: str, domain_hint: str | None = None) -> ResearchFindings:
        """Run the full Research OS pipeline on a given objective.

        Returns a complete ResearchFindings object with plan, ranked sources,
        claims, confidence assessment, synthesized evidence, and provenance.
        """
        if not all([self._planner, self._ranker, self._detector,
                     self._conf_assigner, self._synthesizer, self._tracker]):
            raise RuntimeError("ResearchVerificationModule not initialized")

        plan = self._planner.create_plan(objective, domain_hint)
        sources = self._ranker.rank(plan.sources)
        claims = self._detector.detect(plan.sources, plan.domain)
        confidence = self._conf_assigner.assess(claims, sources)
        evidence = self._synthesizer.synthesize(plan, sources, claims, confidence)
        provenance = self._tracker.record(plan, sources, claims, confidence, evidence)

        return ResearchFindings(
            plan=plan,
            sources=sources,
            claims=claims,
            confidence=confidence,
            evidence=evidence,
            provenance=provenance,
        )


# ── Public API surface ──────────────────────────────────────────────────────

__all__ = [
    # Module
    "ResearchVerificationModule",
    # Core engines
    "ResearchPlanner",
    "SourceRanker",
    "ClaimDetector",
    "ConfidenceAssigner",
    "EvidenceSynthesizer",
    "ProvenanceTracker",
    # Data classes
    "ResearchPlan",
    "RankedSource",
    "DetectedClaim",
    "ConfidenceAssessment",
    "SynthesizedEvidence",
    "ProvenanceRecord",
    "ResearchFindings",
    # Enums
    "ResearchDomain",
    "SourceTier",
    "ClaimType",
    "ConfidenceLevel",
    # Standalone functions
    "rank_source",
    "classify_claim",
    "extract_claims",
    "compute_confidence",
    "aggregate_confidence",
    "synthesize_evidence",
    "generate_recommendations",
    # Verifier / evidence-chain layer
    "Source",
    "SourceCredibility",
    "Verdict",
    "EvidenceChain",
    "Verifier",
    "VerificationReport",
    "verify_report",
    "verify_claim",
    "VALID_TIERS",
    "TIER_BASE_CREDIBILITY",
    "PRIMARY_TIER",
    "GOV_TIER",
    "ACADEMIC_TIER",
    "NEWS_TIER",
    "UNKNOWN_TIER",
    "BANNED_TIER",
]

__version__ = "1.0.0"