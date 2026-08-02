"""
Research Engine — Core components for the Research & Verification OS.

Implements the six primary engines specified in the Research OS architecture:
  1. ResearchPlanner      — plan research, classify domain, scope investigation
  2. SourceRanker         — rank sources by authority tier (internal > vendor > ...)
  3. ClaimDetector        — detect conflicting claims, distinguish facts from assumptions
  4. ConfidenceAssigner   — assign confidence scores with transparent reasoning
  5. EvidenceSynthesizer  — synthesize evidence into narrative findings
  6. ProvenanceTracker    — track provenance chains, version research
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# =============================================================================
# Enums
# =============================================================================


class ResearchDomain(Enum):
    """Research domains for classifying objectives."""

    ENGINEERING = "engineering"
    ARCHITECTURE = "architecture"
    SECURITY = "security"
    COMPLIANCE = "compliance"
    PERFORMANCE = "performance"
    DATA_SCIENCE = "data_science"
    OPERATIONS = "operations"
    PRODUCT = "product"
    GENERAL = "general"
    UNKNOWN = "unknown"

    @classmethod
    def classify(cls, objective: str) -> "ResearchDomain":
        """Classify an objective string into a research domain."""
        objective_lower = objective.lower()
        if any(kw in objective_lower for kw in ["code", "engineer", "build", "implement", "api", "function", "class"]):
            return cls.ENGINEERING
        if any(kw in objective_lower for kw in ["architect", "design", "system", "pattern", "structure"]):
            return cls.ARCHITECTURE
        if any(kw in objective_lower for kw in ["security", "vulnerability", "cve", "exploit", "auth", "encrypt"]):
            return cls.SECURITY
        if any(kw in objective_lower for kw in ["compliance", "regulation", "gdpr", "hipaa", "soc2", "iso"]):
            return cls.COMPLIANCE
        if any(kw in objective_lower for kw in ["performance", "latency", "throughput", "benchmark", "scale"]):
            return cls.PERFORMANCE
        if any(kw in objective_lower for kw in ["data", "analyze", "model", "train", "predict", "ml"]):
            return cls.DATA_SCIENCE
        if any(kw in objective_lower for kw in ["deploy", "monitor", "operate", "infra", "sre"]):
            return cls.OPERATIONS
        if any(kw in objective_lower for kw in ["product", "feature", "roadmap", "user", "ux"]):
            return cls.PRODUCT
        return cls.GENERAL


class SourceTier(Enum):
    """Source authority tiers per Research OS spec priority order."""

    INTERNAL_DOCS = 1      # Internal project documentation
    VENDOR_OFFICIAL = 2    # Official vendor documentation
    STANDARDS_ORG = 3      # Standards organizations
    ACADEMIC = 4           # Academic literature
    TECH_PUBLICATION = 5   # High-quality technical publications
    COMMUNITY = 6          # Established community resources
    UNVERIFIED = 7         # Unverified / unknown sources


class ClaimType(Enum):
    """Classification of a detected claim."""

    FACT = "fact"
    ASSUMPTION = "assumption"
    OPINION = "opinion"
    SPECULATION = "speculation"
    CONFLICTING = "conflicting"


class ConfidenceLevel(Enum):
    """Confidence levels for research findings."""

    HIGH = "high"           # 80-100% confidence
    MODERATE = "moderate"   # 60-79% confidence
    LOW = "low"             # 40-59% confidence
    UNCERTAIN = "uncertain" # 20-39% confidence
    SPECULATIVE = "speculative"  # <20% confidence


# =============================================================================
# Data classes
# =============================================================================


@dataclass
class ResearchPlan:
    """A research plan defining the investigation scope, domain, and goals."""

    plan_id: str
    objective: str
    domain: ResearchDomain
    sources: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    questions: list[str] = field(default_factory=list)
    scope: str = ""
    assumptions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "objective": self.objective,
            "domain": self.domain.value,
            "sources": self.sources,
            "created_at": self.created_at.isoformat(),
            "questions": self.questions,
            "scope": self.scope,
            "assumptions": self.assumptions,
        }


@dataclass
class RankedSource:
    """A source that has been ranked by authority tier."""

    source_id: str
    name: str
    url: str
    tier: SourceTier
    score: float           # 0.0 - 1.0 normalized rank score
    relevance: float       # 0.0 - 1.0 relevance to the research objective
    credibility: float     # 0.0 - 1.0 credibility assessment
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "name": self.name,
            "url": self.url,
            "tier": self.tier.name,
            "score": self.score,
            "relevance": self.relevance,
            "credibility": self.credibility,
            "last_updated": self.last_updated.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class DetectedClaim:
    """A claim detected from research sources."""

    claim_id: str
    text: str
    claim_type: ClaimType
    source_id: str
    supporting_evidence: list[str] = field(default_factory=list)
    contradicting_evidence: list[str] = field(default_factory=list)
    confidence: float = 0.0
    extracted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "text": self.text,
            "claim_type": self.claim_type.value,
            "source_id": self.source_id,
            "supporting_evidence": self.supporting_evidence,
            "contradicting_evidence": self.contradicting_evidence,
            "confidence": self.confidence,
            "extracted_at": self.extracted_at.isoformat(),
        }


@dataclass
class ConfidenceAssessment:
    """Confidence assessment for a set of claims/findings."""

    assessment_id: str
    findings: dict[str, float] = field(default_factory=dict)  # claim_id -> confidence score
    aggregate_confidence: float = 0.0
    level: ConfidenceLevel = ConfidenceLevel.UNCERTAIN
    reasoning: str = ""
    risk_factors: list[str] = field(default_factory=list)
    assessed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "findings": self.findings,
            "aggregate_confidence": self.aggregate_confidence,
            "level": self.level.value,
            "reasoning": self.reasoning,
            "risk_factors": self.risk_factors,
            "assessed_at": self.assessed_at.isoformat(),
        }


@dataclass
class SynthesizedEvidence:
    """Synthesized evidence report with narrative findings and recommendations."""

    synthesis_id: str
    summary: str
    key_findings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    risk_assessment: str = ""
    synthesized_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "synthesis_id": self.synthesis_id,
            "summary": self.summary,
            "key_findings": self.key_findings,
            "recommendations": self.recommendations,
            "conflicts": self.conflicts,
            "gaps": self.gaps,
            "risk_assessment": self.risk_assessment,
            "synthesized_at": self.synthesized_at.isoformat(),
        }


@dataclass
class ProvenanceRecord:
    """Provenance chain tracking the full research lineage."""

    record_id: str
    plan_id: str
    version: int = 1
    source_chain: list[dict[str, Any]] = field(default_factory=list)
    transformation_log: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    predecessors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "plan_id": self.plan_id,
            "version": self.version,
            "source_chain": self.source_chain,
            "transformation_log": self.transformation_log,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "predecessors": self.predecessors,
        }


@dataclass
class ResearchFindings:
    """Complete research findings aggregating all pipeline outputs."""

    plan: ResearchPlan
    sources: list[RankedSource]
    claims: list[DetectedClaim]
    confidence: ConfidenceAssessment
    evidence: SynthesizedEvidence
    provenance: ProvenanceRecord
    completed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "sources": [s.to_dict() for s in self.sources],
            "claims": [c.to_dict() for c in self.claims],
            "confidence": self.confidence.to_dict(),
            "evidence": self.evidence.to_dict(),
            "provenance": self.provenance.to_dict(),
            "completed_at": self.completed_at.isoformat(),
        }


# =============================================================================
# 1. ResearchPlanner
# =============================================================================


class ResearchPlanner:
    """Plans research: defines objective, classifies domain, scopes investigation.

    Responsibility (per spec):
      - Understand objective
      - Classify domain
      - Check internal knowledge
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._plans: dict[str, ResearchPlan] = {}

    def create_plan(self, objective: str, domain_hint: str | None = None) -> ResearchPlan:
        """Create a research plan from an objective.

        Args:
            objective: The research objective/question.
            domain_hint: Optional domain hint (bypasses auto-classification).

        Returns:
            A fully populated ResearchPlan.
        """
        plan_id = str(uuid.uuid4())
        domain = ResearchDomain.classify(objective)

        if domain_hint:
            try:
                domain = ResearchDomain(domain_hint)
            except ValueError:
                pass

        # Generate guiding questions based on domain
        questions = self._generate_questions(objective, domain)

        plan = ResearchPlan(
            plan_id=plan_id,
            objective=objective,
            domain=domain,
            sources=[],  # populated after internal/external retrieval
            questions=questions,
            scope=f"Research into: {objective}",
        )
        self._plans[plan_id] = plan
        return plan

    def get_plan(self, plan_id: str) -> ResearchPlan | None:
        """Retrieve a previously created plan."""
        return self._plans.get(plan_id)

    def add_source(self, plan_id: str, source: str) -> bool:
        """Add a source URL/name to a plan."""
        plan = self._plans.get(plan_id)
        if plan is None:
            return False
        plan.sources.append(source)
        return True

    @staticmethod
    def _generate_questions(objective: str, domain: ResearchDomain) -> list[str]:
        """Generate guiding research questions based on the objective and domain."""
        base = [
            f"What is the current state of knowledge regarding: {objective}?",
            f"What are the key risks associated with: {objective}?",
        ]
        domain_questions: dict[ResearchDomain, list[str]] = {
            ResearchDomain.ENGINEERING: [
                "What are the implementation dependencies?",
                "Are there known limitations or edge cases?",
                "What testing strategies are recommended?",
            ],
            ResearchDomain.SECURITY: [
                "What are the known threat vectors?",
                "Are there existing CVEs or security advisories?",
                "What mitigation strategies are recommended?",
            ],
            ResearchDomain.PERFORMANCE: [
                "What are the benchmark results under load?",
                "Are there known bottlenecks or scaling limits?",
                "What optimization strategies exist?",
            ],
            ResearchDomain.ARCHITECTURE: [
                "What are the design trade-offs?",
                "How does it integrate with existing systems?",
                "What are the scaling characteristics?",
            ],
        }
        return base + domain_questions.get(domain, [
            "What are best practices in this area?",
            "What are common pitfalls to avoid?",
        ])


# =============================================================================
# 2. SourceRanker
# =============================================================================


class SourceRanker:
    """Ranks sources by authority tier.

    Responsibility (per spec):
      - Rank sources
      - Apply Source Priority (internal > vendor > standard > academic > tech > community)

    Source Priority order:
      1. Internal project documentation
      2. Official vendor documentation
      3. Standards organizations
      4. Academic literature
      5. High-quality technical publications
      6. Established community resources
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        # Tier → base score (higher tier = higher base)
        self._tier_scores: dict[SourceTier, float] = {
            SourceTier.INTERNAL_DOCS: 1.0,
            SourceTier.VENDOR_OFFICIAL: 0.9,
            SourceTier.STANDARDS_ORG: 0.85,
            SourceTier.ACADEMIC: 0.7,
            SourceTier.TECH_PUBLICATION: 0.6,
            SourceTier.COMMUNITY: 0.4,
            SourceTier.UNVERIFIED: 0.1,
        }

    def rank(self, source_names: list[str]) -> list[RankedSource]:
        """Rank a list of source names into ordered RankedSource objects.

        Sources are classified by tier based on URL/name heuristics,
        then scored and sorted by descending score.

        Args:
            source_names: List of source names or URLs.

        Returns:
            List of RankedSource sorted by score (highest first).
        """
        ranked: list[RankedSource] = []
        for name in source_names:
            tier = self._classify_tier(name)
            base = self._tier_scores[tier]
            credibility = self._estimate_credibility(name, tier)
            score = (base * 0.6) + (credibility * 0.4)
            ranked.append(RankedSource(
                source_id=str(uuid.uuid4()),
                name=name,
                url=name if name.startswith(("http://", "https://")) else "",
                tier=tier,
                score=round(score, 2),
                relevance=0.8,  # default; refined with intent matching
                credibility=credibility,
            ))
        ranked.sort(key=lambda s: s.score, reverse=True)
        return ranked

    def _classify_tier(self, name: str) -> SourceTier:
        """Classify a source name/URL into a SourceTier.

        Uses heuristics: internal paths, vendor domains, standards orgs, etc.
        """
        n = name.lower()

        # Internal documentation
        if any(kw in n for kw in ["/docs/", "/wiki/", "confluence", "notion", "sharepoint"]):
            return SourceTier.INTERNAL_DOCS

        # Vendor documentation
        vendor_domains = ["docs.python.org", "docs.docker.com", "kubernetes.io/docs",
                          "docs.aws.amazon.com", "learn.microsoft.com", "developer.apple.com"]
        if any(vd in n for vd in vendor_domains):
            return SourceTier.VENDOR_OFFICIAL

        # Standards organizations
        standard_domains = ["ietf.org", "w3.org", "iso.org", "nist.gov", "ieee.org",
                            "opengroup.org", "ecma-international.org"]
        if any(sd in n for sd in standard_domains):
            return SourceTier.STANDARDS_ORG

        # Academic
        if ".edu" in n or "scholar.google" in n or "arxiv.org" in n or "acm.org" in n:
            return SourceTier.ACADEMIC

        # Tech publications
        tech_domains = ["lwn.net", "infoq.com", "thenewstack.io", "dev.to",
                        "medium.com", "stackoverflow.com"]
        if any(td in n for td in tech_domains):
            return SourceTier.TECH_PUBLICATION

        # Community
        if "github.com" in n or "gitlab.com" in n or "reddit.com" in n:
            return SourceTier.COMMUNITY

        # Default unverified
        return SourceTier.UNVERIFIED

    @staticmethod
    def _estimate_credibility(name: str, tier: SourceTier) -> float:
        """Estimate source credibility (0.0-1.0) based on tier and heuristics."""
        base_cred: dict[SourceTier, float] = {
            SourceTier.INTERNAL_DOCS: 0.9,
            SourceTier.VENDOR_OFFICIAL: 0.95,
            SourceTier.STANDARDS_ORG: 0.9,
            SourceTier.ACADEMIC: 0.75,
            SourceTier.TECH_PUBLICATION: 0.6,
            SourceTier.COMMUNITY: 0.35,
            SourceTier.UNVERIFIED: 0.1,
        }
        cred = base_cred.get(tier, 0.1)
        # Boost for well-known domains
        if any(d in name.lower() for d in ["python.org", "docker.com", "github.com/kubernetes"]):
            cred = min(cred + 0.05, 1.0)
        return cred


# =============================================================================
# 3. ClaimDetector
# =============================================================================


class ClaimDetector:
    """Detects and classifies claims from research sources.

    Responsibility (per spec):
      - Retrieve external evidence if needed
      - Compare evidence
      - Detect conflicts
      - Distinguish facts from assumptions
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        # Keywords that indicate assumptions vs facts
        self._assumption_indicators = [
            "assume", "might", "could", "maybe", "perhaps", "likely",
            "probably", "should", "typically", "generally", "in theory",
            "thought to be", "believed to be",
        ]
        self._fact_indicators = [
            "is", "are", "was", "were", "has been", "have been",
            "confirmed", "verified", "documented", "proven",
            "according to", "as stated in", "as documented by",
        ]

    def detect(self, raw_sources: list[str], domain: ResearchDomain) -> list[DetectedClaim]:
        """Detect claims from raw source content.

        Args:
            raw_sources: List of raw source text/names.
            domain: Research domain for contextual classification.

        Returns:
            List of detected claims with classification.
        """
        claims: list[DetectedClaim] = []
        for source in raw_sources:
            extracted = self._extract_claims_from_text(source)
            claims.extend(extracted)

        # Detect conflicts among claims
        self._detect_conflicts(claims)

        return claims

    def classify(self, text: str) -> ClaimType:
        """Classify a single claim text into a ClaimType."""
        text_lower = text.lower()

        # Check for conflict indicators
        conflict_words = ["however", "but", "contrary", "disagree", "conflicting",
                          "on the other hand", "disputed", "controversial"]
        if any(cw in text_lower for cw in conflict_words):
            return ClaimType.CONFLICTING

        # Check for speculation
        speculation_words = ["might be", "could be", "possibly", "unknown",
                             "speculative", "unclear", "hypothetically"]
        if any(sw in text_lower for sw in speculation_words):
            return ClaimType.SPECULATION

        # Check for opinion
        opinion_words = ["i think", "in my opinion", "i believe", "we believe",
                         "arguably", "preferable"]
        if any(ow in text_lower for ow in opinion_words):
            return ClaimType.OPINION

        # Check for assumptions
        if any(ai in text_lower for ai in self._assumption_indicators):
            return ClaimType.ASSUMPTION

        # Check for facts
        if any(fi in text_lower for fi in self._fact_indicators) or not any(
            ai in text_lower for ai in self._assumption_indicators + opinion_words + speculation_words
        ):
            return ClaimType.FACT

        return ClaimType.ASSUMPTION

    def _extract_claims_from_text(self, text: str) -> list[DetectedClaim]:
        """Extract individual claims from a source text."""
        # Split on sentence boundaries
        import re
        sentences = re.split(r'(?<=[.!?])\s+', text)
        claims: list[DetectedClaim] = []
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 15:  # skip very short fragments
                continue
            claim_type = self.classify(sentence)
            claims.append(DetectedClaim(
                claim_id=str(uuid.uuid4()),
                text=sentence,
                claim_type=claim_type,
                source_id="unknown",
            ))
        return claims

    def _detect_conflicts(self, claims: list[DetectedClaim]) -> None:
        """Detect conflicting claims and mark them.

        Two claims are conflicting if they have opposing sentiment
        or make mutually exclusive statements on the same topic.
        """
        for i, claim_a in enumerate(claims):
            for j, claim_b in enumerate(claims):
                if j <= i:
                    continue
                # Simple heuristic: if one has "is/does" and other has "is not/does not"
                a_lower, b_lower = claim_a.text.lower(), claim_b.text.lower()
                if ("is not" in a_lower and "is " in b_lower.replace("is not", "")) or \
                   ("is not" in b_lower and "is " in a_lower.replace("is not", "")):
                    claim_a.claim_type = ClaimType.CONFLICTING
                    claim_b.claim_type = ClaimType.CONFLICTING
                    claim_a.contradicting_evidence.append(claim_b.text[:100])
                    claim_b.contradicting_evidence.append(claim_a.text[:100])


# =============================================================================
# 4. ConfidenceAssigner
# =============================================================================


class ConfidenceAssigner:
    """Assigns confidence scores to research claims.

    Responsibility (per spec):
      - Assign confidence
      - Document reasoning
      - Identify risk factors
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}

    def assess(self, claims: list[DetectedClaim], sources: list[RankedSource]) -> ConfidenceAssessment:
        """Assess confidence for a set of claims given ranked sources.

        Confidence is computed based on:
          - Claim type (facts get higher base confidence)
          - Source tier of supporting sources
          - Number of corroborating sources
          - Presence of contradictory evidence

        Args:
            claims: List of detected claims.
            sources: List of ranked sources.

        Returns:
            A ConfidenceAssessment with per-claim and aggregate scores.
        """
        assessment_id = str(uuid.uuid4())
        findings: dict[str, float] = {}
        risk_factors: list[str] = []

        # Build source lookup by ID
        source_map: dict[str, RankedSource] = {s.source_id: s for s in sources}

        for claim in claims:
            score = self._compute_claim_confidence(claim, source_map)
            findings[claim.claim_id] = round(score, 2)

            if score < 0.4:
                risk_factors.append(f"Low confidence on: {claim.text[:80]}...")
            if claim.claim_type == ClaimType.CONFLICTING:
                risk_factors.append(f"Conflicting claim detected: {claim.text[:80]}...")

        # Aggregate
        if findings:
            aggregate = sum(findings.values()) / len(findings)
        else:
            aggregate = 0.0

        level = self._score_to_level(aggregate)
        reasoning = self._generate_reasoning(findings, aggregate, level, risk_factors)

        return ConfidenceAssessment(
            assessment_id=assessment_id,
            findings=findings,
            aggregate_confidence=round(aggregate, 2),
            level=level,
            reasoning=reasoning,
            risk_factors=risk_factors,
        )

    def _compute_claim_confidence(
        self, claim: DetectedClaim, source_map: dict[str, RankedSource]
    ) -> float:
        """Compute confidence score for a single claim (0.0-1.0)."""
        # Base confidence by claim type
        type_scores: dict[ClaimType, float] = {
            ClaimType.FACT: 0.85,
            ClaimType.ASSUMPTION: 0.5,
            ClaimType.OPINION: 0.4,
            ClaimType.SPECULATION: 0.25,
            ClaimType.CONFLICTING: 0.2,
        }
        base = type_scores.get(claim.claim_type, 0.3)

        # Boost from supporting evidence
        support_boost = min(len(claim.supporting_evidence) * 0.05, 0.3)

        # Penalty for contradictory evidence
        contradict_penalty = len(claim.contradicting_evidence) * 0.1

        # Source credibility boost
        source = source_map.get(claim.source_id)
        source_boost = source.credibility * 0.15 if source else 0.0

        score = base + support_boost + source_boost - contradict_penalty
        return max(0.0, min(1.0, score))

    @staticmethod
    def _score_to_level(score: float) -> ConfidenceLevel:
        """Map a numeric confidence score to a ConfidenceLevel."""
        if score >= 0.8:
            return ConfidenceLevel.HIGH
        elif score >= 0.6:
            return ConfidenceLevel.MODERATE
        elif score >= 0.4:
            return ConfidenceLevel.LOW
        elif score >= 0.2:
            return ConfidenceLevel.UNCERTAIN
        return ConfidenceLevel.SPECULATIVE

    @staticmethod
    def _generate_reasoning(
        findings: dict[str, float],
        aggregate: float,
        level: ConfidenceLevel,
        risks: list[str],
    ) -> str:
        """Generate human-readable reasoning for the confidence assessment."""
        parts: list[str] = [
            f"Aggregate confidence: {aggregate:.2f} ({level.value}).",
            f"{len(findings)} claims assessed.",
        ]
        if risks:
            parts.append(f"{len(risks)} risk factors identified.")
        if aggregate >= 0.8:
            parts.append("High overall confidence — findings are well-supported.")
        elif aggregate >= 0.6:
            parts.append("Moderate confidence — findings generally reliable but verify key claims.")
        else:
            parts.append("Low confidence — further research recommended.")
        return " ".join(parts)


# =============================================================================
# 5. EvidenceSynthesizer
# =============================================================================


class EvidenceSynthesizer:
    """Synthesizes evidence into narrative findings and recommendations.

    Responsibility (per spec):
      - Summarize findings
      - Recommend actions
      - Feed validated knowledge into Memory OS
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}

    def synthesize(
        self,
        plan: ResearchPlan,
        sources: list[RankedSource],
        claims: list[DetectedClaim],
        confidence: ConfidenceAssessment,
    ) -> SynthesizedEvidence:
        """Synthesize all research inputs into a coherent evidence report.

        Produces summary, key findings, recommendations, conflicts, and gaps.

        Args:
            plan: The research plan.
            sources: Ranked sources.
            claims: Detected claims.
            confidence: Confidence assessment.

        Returns:
            SynthesizedEvidence report.
        """
        synthesis_id = str(uuid.uuid4())

        # Extract key findings from high-confidence claims
        key_findings: list[str] = []
        for claim in claims:
            score = confidence.findings.get(claim.claim_id, 0.0)
            if score >= 0.6:
                key_findings.append(f"[{claim.claim_type.value.upper()}] {claim.text} (confidence: {score:.2f})")

        # Identify conflicts
        conflicts: list[str] = [
            claim.text for claim in claims
            if claim.claim_type == ClaimType.CONFLICTING
        ]

        # Identify gaps (low-scoring areas)
        gaps: list[str] = []
        for claim in claims:
            score = confidence.findings.get(claim.claim_id, 0.0)
            if score < 0.4:
                gaps.append(f"Low confidence area: {claim.text[:120]}...")

        # Generate summary
        fact_count = sum(1 for c in claims if c.claim_type == ClaimType.FACT)
        assumption_count = sum(1 for c in claims if c.claim_type == ClaimType.ASSUMPTION)
        conflict_count = len(conflicts)
        summary = (
            f"Research on '{plan.objective}' ({plan.domain.value}) synthesized "
            f"{len(claims)} claims from {len(sources)} sources. "
            f"Found {fact_count} facts, {assumption_count} assumptions, "
            f"and {conflict_count} conflicts. "
            f"Aggregate confidence: {confidence.aggregate_confidence:.2f} ({confidence.level.value})."
        )

        # Generate recommendations
        recommendations = self._generate_recommendations(
            plan, confidence, conflicts, gaps
        )

        # Risk assessment
        risk = self._assess_risks(confidence, conflicts, gaps)

        return SynthesizedEvidence(
            synthesis_id=synthesis_id,
            summary=summary,
            key_findings=key_findings,
            recommendations=recommendations,
            conflicts=conflicts,
            gaps=gaps,
            risk_assessment=risk,
        )

    @staticmethod
    def _generate_recommendations(
        plan: ResearchPlan,
        confidence: ConfidenceAssessment,
        conflicts: list[str],
        gaps: list[str],
    ) -> list[str]:
        """Generate actionable recommendations from research findings."""
        recs: list[str] = []

        if confidence.aggregate_confidence >= 0.8:
            recs.append("Proceed with implementation based on high-confidence findings.")
        elif confidence.aggregate_confidence >= 0.6:
            recs.append("Proceed with caution — verify key claims before committing.")
        else:
            recs.append("Delay decision — conduct additional research to raise confidence.")

        if conflicts:
            recs.append(f"Resolve {len(conflicts)} conflicting claims before finalizing.")

        if gaps:
            recs.append(f"Investigate {len(gaps)} low-confidence areas with additional evidence.")

        if plan.domain == ResearchDomain.SECURITY:
            recs.append("Prioritize security review of all findings before deployment.")
        elif plan.domain == ResearchDomain.PERFORMANCE:
            recs.append("Run benchmarks to validate performance claims under expected load.")

        return recs

    @staticmethod
    def _assess_risks(
        confidence: ConfidenceAssessment,
        conflicts: list[str],
        gaps: list[str],
    ) -> str:
        """Assess overall risk based on confidence, conflicts, and gaps."""
        risk_level = "LOW"
        reasons: list[str] = []

        if confidence.aggregate_confidence < 0.5:
            risk_level = "HIGH"
            reasons.append("low aggregate confidence")
        elif confidence.aggregate_confidence < 0.7:
            risk_level = "MEDIUM"
            reasons.append("moderate aggregate confidence")

        if conflicts:
            risk_level = "HIGH" if risk_level == "MEDIUM" else risk_level
            reasons.append(f"{len(conflicts)} unresolved conflicts")

        if len(gaps) > 3:
            risk_level = "HIGH"
            reasons.append(f"{len(gaps)} significant knowledge gaps")

        if not reasons:
            reasons.append("No significant risk factors identified")

        return f"Risk Level: {risk_level} — {'; '.join(reasons)}."


# =============================================================================
# 6. ProvenanceTracker
# =============================================================================


class ProvenanceTracker:
    """Tracks provenance chains and versions research.

    Responsibility (per spec):
      - Preserve provenance
      - Version research
      - Never fabricate evidence
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._records: dict[str, ProvenanceRecord] = {}
        self._version_map: dict[str, list[str]] = defaultdict(list)  # plan_id → record_ids

    def record(
        self,
        plan: ResearchPlan,
        sources: list[RankedSource],
        claims: list[DetectedClaim],
        confidence: ConfidenceAssessment,
        evidence: SynthesizedEvidence,
    ) -> ProvenanceRecord:
        """Record provenance for a completed research pipeline.

        Creates a full provenance chain with source lineage,
        transformation log, and version tracking.

        Args:
            plan: The research plan.
            sources: Ranked sources.
            claims: Detected claims.
            confidence: Confidence assessment.
            evidence: Synthesized evidence.

        Returns:
            A ProvenanceRecord with full traceability.
        """
        record_id = str(uuid.uuid4())

        # Build source chain
        source_chain: list[dict[str, Any]] = []
        for source in sources:
            source_chain.append({
                "source_id": source.source_id,
                "name": source.name,
                "tier": source.tier.name,
                "credibility": source.credibility,
                "used_in_claims": [
                    c.claim_id for c in claims
                    if c.source_id == source.source_id
                ],
            })

        # Build transformation log
        transformations: list[str] = [
            f"Plan created: {plan.plan_id} (domain: {plan.domain.value})",
            f"Sources ranked: {len(sources)} sources across tiers",
            f"Claims detected: {len(claims)} claims ({sum(1 for c in claims if c.claim_type == ClaimType.FACT)} facts, {sum(1 for c in claims if c.claim_type == ClaimType.ASSUMPTION)} assumptions)",
            f"Confidence assessed: aggregate {confidence.aggregate_confidence:.2f} ({confidence.level.value})",
            f"Evidence synthesized: {evidence.synthesis_id}",
        ]

        # Version tracking
        previous = self._version_map.get(plan.plan_id, [])
        version = len(previous) + 1
        predecessors = previous[-1:] if previous else []

        record = ProvenanceRecord(
            record_id=record_id,
            plan_id=plan.plan_id,
            version=version,
            source_chain=source_chain,
            transformation_log=transformations,
            predecessors=predecessors,
        )

        self._records[record_id] = record
        self._version_map[plan.plan_id].append(record_id)

        return record

    def get_record(self, record_id: str) -> ProvenanceRecord | None:
        """Retrieve a provenance record by ID."""
        return self._records.get(record_id)

    def get_version_history(self, plan_id: str) -> list[ProvenanceRecord]:
        """Get all versioned records for a given plan."""
        record_ids = self._version_map.get(plan_id, [])
        return [self._records[rid] for rid in record_ids if rid in self._records]

    def audit_trail(self, plan_id: str) -> list[dict[str, Any]]:
        """Generate a complete audit trail for a research plan."""
        history = self.get_version_history(plan_id)
        trail: list[dict[str, Any]] = []
        for record in history:
            trail.append({
                "record_id": record.record_id,
                "version": record.version,
                "transformations": record.transformation_log,
                "created_at": record.created_at.isoformat(),
            })
        return trail