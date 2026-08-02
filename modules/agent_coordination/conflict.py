"""
ENI Enterprise Conflict Resolution — Evidence-based, multi-agent conflict
detection, resolution, escalation, and prevention.

Resolution always follows the evidence hierarchy, never authority alone.
Full audit trail for every resolution decision.

Tie-breaking rules:
  - Compare evidence quality (source reliability × confidence)
  - Evaluate trade-offs against project requirements
  - Request independent verification before escalation
  - Escalate to Executive Orchestrator only when evidence is genuinely equal
  - NEVER resolve by authority alone
"""

import json
import time
import uuid
import logging
from typing import Dict, Any, List, Optional, Callable, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

logger = logging.getLogger("enterprise.conflict")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ConflictStatus(Enum):
    """Lifecycle status of a conflict."""
    DETECTED = "detected"          # Identified, not yet processed
    ANALYZING = "analyzing"        # Gathering evidence, comparing positions
    VERIFICATION_REQUESTED = "verification_requested"  # Independent review needed
    ESCALATED = "escalated"        # Sent to Executive Orchestrator
    RESOLVED = "resolved"          # Resolution reached
    UNRESOLVABLE = "unresolvable"  # Cannot resolve — requires human intervention
    DISMISSED = "dismissed"        # False alarm, no actual conflict


class ResolutionStrategy(Enum):
    """Strategies for resolving conflicts, in order of preference."""
    EVIDENCE_COMPARISON = "evidence_comparison"
    TRADE_OFF_EVALUATION = "trade_off_evaluation"
    INDEPENDENT_VERIFICATION = "independent_verification"
    ESCALATION = "escalation"
    HUMAN_INTERVENTION = "human_intervention"


class TradeOffDimension(Enum):
    """Dimensions along which trade-offs are evaluated."""
    CORRECTNESS = "correctness"            # Technical accuracy
    COMPLETENESS = "completeness"          # How thorough
    PERFORMANCE = "performance"            # Speed, resource usage
    SECURITY = "security"                  # Safety, vulnerability
    MAINTAINABILITY = "maintainability"    # Ease of future changes
    CONSISTENCY = "consistency"            # Alignment with existing patterns
    SIMPLICITY = "simplicity"              # Complexity vs benefit
    COMPLIANCE = "compliance"              # Regulatory/standards adherence
    USER_EXPERIENCE = "user_experience"    # End-user impact
    BUSINESS_VALUE = "business_value"      # Alignment with business goals
    ADOPTABILITY = "adoptability"          # How easily the team can adopt it
    TESTABILITY = "testability"            # How easily it can be verified


class EvidenceSourceType(Enum):
    """Types of evidence sources with inherent reliability ratings."""
    PRODUCTION_METRICS = "production_metrics"        # reliability: 0.95
    BENCHMARK = "benchmark"                          # reliability: 0.90
    DOCUMENTED_STANDARD = "documented_standard"       # reliability: 0.85
    PEER_REVIEWED = "peer_reviewed"                  # reliability: 0.80
    EXPERT_OPINION = "expert_opinion"                # reliability: 0.70
    HISTORICAL_PRECEDENT = "historical_precedent"     # reliability: 0.65
    SIMULATION = "simulation"                        # reliability: 0.60
    AGENT_ANALYSIS = "agent_analysis"                # reliability: 0.55
    HEURISTIC = "heuristic"                          # reliability: 0.40
    SPECULATION = "speculation"                      # reliability: 0.20
    UNKNOWN = "unknown"                              # reliability: 0.10


# Reliability weights per source type
_SOURCE_RELIABILITY: Dict[EvidenceSourceType, float] = {
    EvidenceSourceType.PRODUCTION_METRICS: 0.95,
    EvidenceSourceType.BENCHMARK: 0.90,
    EvidenceSourceType.DOCUMENTED_STANDARD: 0.85,
    EvidenceSourceType.PEER_REVIEWED: 0.80,
    EvidenceSourceType.EXPERT_OPINION: 0.70,
    EvidenceSourceType.HISTORICAL_PRECEDENT: 0.65,
    EvidenceSourceType.SIMULATION: 0.60,
    EvidenceSourceType.AGENT_ANALYSIS: 0.55,
    EvidenceSourceType.HEURISTIC: 0.40,
    EvidenceSourceType.SPECULATION: 0.20,
    EvidenceSourceType.UNKNOWN: 0.10,
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Evidence:
    """A piece of evidence supporting an agent's position in a conflict.

    Each piece is weighted by source reliability × agent authority.
    """

    evidence_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    description: str = ""
    source_type: EvidenceSourceType = EvidenceSourceType.UNKNOWN
    source_detail: str = ""  # URL, doc reference, experiment name, etc.
    provided_by: str = ""    # Agent name
    provided_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"))
    confidence: float = 0.5  # Agent's own confidence in this evidence (0.0-1.0)
    content: Dict[str, Any] = field(default_factory=dict)  # Raw evidence data

    def reliability(self) -> float:
        """Compute evidence reliability: source_type_weight × confidence."""
        base = _SOURCE_RELIABILITY.get(self.source_type, 0.10)
        return round(base * self.confidence, 4)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "description": self.description,
            "source_type": self.source_type.value,
            "source_detail": self.source_detail,
            "provided_by": self.provided_by,
            "provided_at": self.provided_at,
            "confidence": self.confidence,
            "reliability": self.reliability(),
            "content": self.content,
        }


@dataclass
class AgentPosition:
    """An agent's stated position in a conflict, with supporting evidence."""

    agent_name: str = ""
    agent_role: str = ""
    position_summary: str = ""
    evidence: List[Evidence] = field(default_factory=list)
    trade_off_scores: Dict[str, float] = field(default_factory=dict)  # dimension -> score 0-10
    stated_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"))

    def combined_reliability(self) -> float:
        """Aggregate reliability of all evidence supporting this position."""
        if not self.evidence:
            return 0.0
        return round(
            sum(e.reliability() for e in self.evidence) / len(self.evidence), 4
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "agent_role": self.agent_role,
            "position_summary": self.position_summary,
            "evidence": [e.to_dict() for e in self.evidence],
            "trade_off_scores": self.trade_off_scores,
            "stated_at": self.stated_at,
            "combined_reliability": self.combined_reliability(),
        }


@dataclass
class Conflict:
    """A detected conflict between two or more agent positions.

    Conflicts are resolved through an ordered process:
        1. Compare evidence
        2. Evaluate trade-offs
        3. Request independent verification
        4. Escalate to Executive Orchestrator
        5. Document rationale (always)

    Tie-breaking is NEVER done by authority alone — it is always
    evidence-based.  When the evidence is genuinely equal, the conflict
    is escalated or flagged for human intervention.
    """

    conflict_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    description: str = ""
    positions: List[AgentPosition] = field(default_factory=list)
    status: ConflictStatus = ConflictStatus.DETECTED
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"))
    resolved_at: Optional[str] = None
    resolution: Optional[str] = None
    rationale: str = ""
    resolution_strategy: Optional[ResolutionStrategy] = None
    resolver: str = ""  # Agent who resolved it (or "executive_orchestrator")
    resolution_history: List[Dict[str, Any]] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    domain: str = ""    # Related knowledge domain
    severity: str = "medium"  # low, medium, high, critical

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "description": self.description,
            "positions": [p.to_dict() for p in self.positions],
            "status": self.status.value,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "resolution": self.resolution,
            "rationale": self.rationale,
            "resolution_strategy": (
                self.resolution_strategy.value if self.resolution_strategy else None
            ),
            "resolver": self.resolver,
            "resolution_history": self.resolution_history,
            "tags": self.tags,
            "domain": self.domain,
            "severity": self.severity,
        }


# ---------------------------------------------------------------------------
# Trade-off evaluation matrix
# ---------------------------------------------------------------------------

class TradeOffMatrix:
    """Evaluates positions across multiple dimensions and computes scores.

    Each dimension can be weighted by importance for the current context.
    """

    DEFAULT_WEIGHTS: Dict[TradeOffDimension, float] = {
        TradeOffDimension.CORRECTNESS: 1.0,
        TradeOffDimension.COMPLETENESS: 0.8,
        TradeOffDimension.PERFORMANCE: 0.7,
        TradeOffDimension.SECURITY: 1.0,
        TradeOffDimension.MAINTAINABILITY: 0.8,
        TradeOffDimension.CONSISTENCY: 0.7,
        TradeOffDimension.SIMPLICITY: 0.7,
        TradeOffDimension.COMPLIANCE: 0.9,
        TradeOffDimension.USER_EXPERIENCE: 0.6,
        TradeOffDimension.BUSINESS_VALUE: 0.8,
        TradeOffDimension.ADOPTABILITY: 0.5,
        TradeOffDimension.TESTABILITY: 0.6,
    }

    def __init__(
        self,
        weights: Optional[Dict[TradeOffDimension, float]] = None,
    ) -> None:
        self._weights: Dict[TradeOffDimension, float] = (
            weights or dict(self.DEFAULT_WEIGHTS)
        )

    def set_weight(self, dimension: TradeOffDimension, weight: float) -> None:
        """Override the weight for a specific dimension."""
        if weight < 0.0 or weight > 1.0:
            raise ValueError(f"Weight must be between 0.0 and 1.0, got {weight}")
        self._weights[dimension] = weight

    def get_weight(self, dimension: TradeOffDimension) -> float:
        """Get the current weight for a dimension."""
        return self._weights.get(dimension, 0.5)

    def evaluate_position(
        self, position: AgentPosition
    ) -> Tuple[float, Dict[str, float]]:
        """Score a position across all weighted dimensions.

        Args:
            position: The agent position to evaluate.

        Returns:
            Tuple of (total_weighted_score, per_dimension_weighted_scores).
        """
        total = 0.0
        total_weight = 0.0
        per_dim: Dict[str, float] = {}

        for dim, weight in self._weights.items():
            dim_key = dim.value
            score = position.trade_off_scores.get(dim_key, 5.0)  # default neutral
            weighted = score * weight
            total += weighted
            total_weight += weight
            per_dim[dim_key] = weighted

        # Normalize
        normalized = round(total / total_weight, 3) if total_weight > 0 else 5.0
        return normalized, per_dim

    def compare_positions(
        self, positions: List[AgentPosition]
    ) -> List[Tuple[AgentPosition, float, Dict[str, float]]]:
        """Evaluate and rank multiple positions.

        Returns:
            List of (position, total_score, per_dim_scores) sorted best-first.
        """
        scored = []
        for pos in positions:
            score, per_dim = self.evaluate_position(pos)
            scored.append((pos, score, per_dim))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored


# ---------------------------------------------------------------------------
# Evidence comparison engine
# ---------------------------------------------------------------------------

class EvidenceComparisonEngine:
    """Compares evidence across agent positions and ranks by reliability.

    Evidence is weighted by:
        - Source type reliability (e.g. production metrics > speculation)
        - Agent's stated confidence in the evidence
        - Amount and diversity of evidence
    """

    def compare(
        self, positions: List[AgentPosition]
    ) -> Dict[str, Any]:
        """Compare evidence across positions and produce a ranked assessment.

        Args:
            positions: List of positions with their evidence.

        Returns:
            Dict with comparison results including per-position reliability
            scores and an overall ranking.
        """
        if not positions:
            return {"ranking": [], "winner": None, "tie": False, "verdict": "no_positions"}

        ranked: List[Dict[str, Any]] = []
        for pos in positions:
            reliability = pos.combined_reliability()
            evidence_count = len(pos.evidence)
            source_types = [e.source_type.value for e in pos.evidence]
            ranked.append({
                "agent": pos.agent_name,
                "role": pos.agent_role,
                "reliability": reliability,
                "evidence_count": evidence_count,
                "source_types": source_types,
                "position": pos.position_summary,
            })

        ranked.sort(key=lambda x: x["reliability"], reverse=True)

        # Determine winner or tie
        winner = None
        is_tie = False
        if len(ranked) >= 2:
            if ranked[0]["reliability"] == ranked[1]["reliability"]:
                is_tie = True
            else:
                winner = ranked[0]

        verdict = "tie" if is_tie else "clear_winner" if winner else "insufficient_evidence"

        return {
            "ranking": ranked,
            "winner": winner,
            "tie": is_tie,
            "verdict": verdict,
            "compared_at": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        }

    def evidence_strength_report(self, position: AgentPosition) -> Dict[str, Any]:
        """Generate a detailed report on the strength of a position's evidence.

        Args:
            position: The agent position to analyze.

        Returns:
            Dict with breakdown by source type, overall score, and gaps.
        """
        if not position.evidence:
            return {
                "agent": position.agent_name,
                "overall_reliability": 0.0,
                "evidence_count": 0,
                "source_breakdown": {},
                "gaps": ["no_evidence_provided"],
            }

        breakdown: Dict[str, int] = {}
        for e in position.evidence:
            breakdown[e.source_type.value] = breakdown.get(e.source_type.value, 0) + 1

        gaps = []
        for source_type in EvidenceSourceType:
            if source_type.value not in breakdown:
                gaps.append(f"missing_{source_type.value}")

        return {
            "agent": position.agent_name,
            "overall_reliability": position.combined_reliability(),
            "evidence_count": len(position.evidence),
            "source_breakdown": breakdown,
            "gaps": gaps,
        }


# ---------------------------------------------------------------------------
# Conflict Resolver
# ---------------------------------------------------------------------------

class ConflictResolver:
    """Enterprise-grade conflict resolution system for multi-agent coordination.

    Resolution process (always in this order):
        1. Compare evidence (weight by source reliability)
        2. Evaluate trade-offs across dimensions
        3. Request verification from an independent agent
        4. Escalate to Executive Orchestrator if unresolved
        5. Document rationale with full audit trail

    Key principle: NEVER resolve by authority alone.  When the evidence is
    genuinely equal, the conflict is escalated rather than broken arbitrarily.

    Usage::

        resolver = ConflictResolver()

        # Register a conflict
        conflict = resolver.detect_conflicts(
            "Which database should we use?",
            positions=[pos_a, pos_b],
            domain="architecture"
        )

        # Attempt resolution
        result = resolver.resolve(conflict.conflict_id)
        print(result["resolution"])

        # If needed, escalate
        resolver.escalate(conflict.conflict_id)
    """

    def __init__(self) -> None:
        self._conflicts: Dict[str, Conflict] = {}
        self._resolution_log: List[Dict[str, Any]] = []
        self._evidence_engine = EvidenceComparisonEngine()
        self._trade_off_matrix = TradeOffMatrix()
        self._escalation_handler: Optional[Callable[[Conflict], Dict[str, Any]]] = None
        logger.info("ConflictResolver initialized")

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def detect_conflicts(
        self,
        description: str,
        positions: List[AgentPosition],
        domain: str = "",
        tags: Optional[List[str]] = None,
        severity: str = "medium",
    ) -> Conflict:
        """Register a new conflict between agent positions.

        Args:
            description: Clear description of what the conflict is about.
            positions: List of 2+ conflicting agent positions.
            domain: Related knowledge domain.
            tags: Categorization tags.
            severity: "low", "medium", "high", or "critical".

        Returns:
            The registered Conflict object.

        Raises:
            ValueError: If fewer than 2 positions are provided.
        """
        if len(positions) < 2:
            raise ValueError(
                f"At least 2 positions required to form a conflict; got {len(positions)}"
            )

        conflict = Conflict(
            description=description,
            positions=positions,
            domain=domain,
            tags=tags or [],
            severity=severity,
            status=ConflictStatus.DETECTED,
        )

        self._conflicts[conflict.conflict_id] = conflict
        self._log_step(
            conflict.conflict_id,
            "detected",
            f"Conflict detected between {', '.join(p.agent_name for p in positions)}",
        )

        logger.info(
            f"CONFLICT DETECTED [{conflict.conflict_id}]: {description[:80]}..."
        )
        return conflict

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def resolve(self, conflict_id: str) -> Dict[str, Any]:
        """Attempt to resolve a conflict through the ordered resolution process.

        Steps:
            1. Evidence comparison
            2. Trade-off evaluation
            3. Independent verification (if tie)
            4. Escalation (if still unresolved)

        Args:
            conflict_id: ID of the conflict to resolve.

        Returns:
            Dict with keys: resolution, rationale, strategy, winner, tie, escalated.

        Raises:
            KeyError: If conflict_id not found.
        """
        if conflict_id not in self._conflicts:
            raise KeyError(f"Conflict not found: {conflict_id}")

        conflict = self._conflicts[conflict_id]

        if conflict.status == ConflictStatus.RESOLVED:
            return {
                "resolution": conflict.resolution,
                "rationale": conflict.rationale,
                "strategy": (
                    conflict.resolution_strategy.value
                    if conflict.resolution_strategy
                    else "already_resolved"
                ),
                "already_resolved": True,
            }

        conflict.status = ConflictStatus.ANALYZING

        # ---- Step 1: Evidence comparison ----
        evidence_result = self._evidence_engine.compare(conflict.positions)
        self._log_step(
            conflict_id,
            "evidence_comparison",
            f"Verdict: {evidence_result['verdict']}",
            evidence_result,
        )

        if evidence_result["verdict"] == "clear_winner":
            winner = evidence_result["winner"]
            conflict.resolution = (
                f"Position by {winner['agent']} ({winner['role']}) selected "
                f"based on superior evidence reliability "
                f"({winner['reliability']:.3f})"
            )
            conflict.rationale = self._build_evidence_rationale(evidence_result)
            conflict.resolution_strategy = ResolutionStrategy.EVIDENCE_COMPARISON
            conflict.resolver = "evidence_comparison_engine"
            self._finalize_resolution(conflict)
            return self._resolution_response(conflict, winner=winner["agent"])

        # ---- Step 2: Trade-off evaluation ----
        if evidence_result["verdict"] == "tie":
            trade_off_result = self._trade_off_matrix.compare_positions(
                conflict.positions
            )
            self._log_step(
                conflict_id,
                "trade_off_evaluation",
                f"Scores: {[(p.agent_name, s) for p, s, _ in trade_off_result]}",
                {
                    "scores": [
                        {"agent": p.agent_name, "score": s, "per_dim": d}
                        for p, s, d in trade_off_result
                    ]
                },
            )

            if trade_off_result and (
                len(trade_off_result) < 2
                or trade_off_result[0][1] > trade_off_result[1][1]
            ):
                best_pos, best_score, best_dim = trade_off_result[0]
                conflict.resolution = (
                    f"Position by {best_pos.agent_name} selected via trade-off "
                    f"evaluation (score: {best_score:.2f})"
                )
                conflict.rationale = self._build_tradeoff_rationale(trade_off_result)
                conflict.resolution_strategy = ResolutionStrategy.TRADE_OFF_EVALUATION
                conflict.resolver = "trade_off_matrix"
                self._finalize_resolution(conflict)
                return self._resolution_response(
                    conflict, winner=best_pos.agent_name
                )

        # ---- Step 3: Independent verification required ----
        conflict.status = ConflictStatus.VERIFICATION_REQUESTED
        self._log_step(
            conflict_id,
            "verification_requested",
            "Evidence comparison and trade-off evaluation both resulted in a tie. "
            "Independent agent verification is required.",
        )

        return {
            "resolution": None,
            "rationale": (
                "Tie after evidence comparison and trade-off evaluation. "
                "Independent verification required."
            ),
            "strategy": ResolutionStrategy.INDEPENDENT_VERIFICATION.value,
            "status": ConflictStatus.VERIFICATION_REQUESTED.value,
            "conflict_id": conflict_id,
            "escalated": False,
            "requires_verification": True,
        }

    def verify_and_resolve(
        self,
        conflict_id: str,
        verifier_agent: str,
        verifier_role: str,
        recommendation: str,
        rationale: str,
        verifier_evidence: Optional[List[Evidence]] = None,
    ) -> Dict[str, Any]:
        """Accept verification from an independent agent and apply resolution.

        This is called after ``resolve()`` returns ``requires_verification=True``.

        Args:
            conflict_id: Conflict ID.
            verifier_agent: Name of the independent verifying agent.
            verifier_role: Role of the verifying agent.
            recommendation: Which position the verifier recommends.
            rationale: The verifier's rationale.
            verifier_evidence: Optional additional evidence from the verifier.

        Returns:
            Resolution result dict.
        """
        if conflict_id not in self._conflicts:
            raise KeyError(f"Conflict not found: {conflict_id}")

        conflict = self._conflicts[conflict_id]

        if conflict.status != ConflictStatus.VERIFICATION_REQUESTED:
            return {
                "error": f"Conflict not in verification state; current: {conflict.status.value}"
            }

        self._log_step(
            conflict_id,
            "verification_received",
            f"Verifier {verifier_agent} recommends: {recommendation}",
            {
                "verifier": verifier_agent,
                "verifier_role": verifier_role,
                "recommendation": recommendation,
                "rationale": rationale,
                "evidence": [e.to_dict() for e in (verifier_evidence or [])],
            },
        )

        conflict.resolution = (
            f"Position recommended by independent verifier {verifier_agent} "
            f"({verifier_role}): {recommendation}"
        )
        conflict.rationale = (
            f"Independent verification by {verifier_agent}: {rationale}"
        )
        conflict.resolution_strategy = ResolutionStrategy.INDEPENDENT_VERIFICATION
        conflict.resolver = verifier_agent
        self._finalize_resolution(conflict)
        return self._resolution_response(conflict, winner=recommendation)

    # ------------------------------------------------------------------
    # Escalation
    # ------------------------------------------------------------------

    def escalate(self, conflict_id: str) -> Dict[str, Any]:
        """Escalate an unresolved conflict to the Executive Orchestrator.

        This should only happen after evidence comparison, trade-off
        evaluation, and independent verification have all failed to
        produce a clear winner.

        Args:
            conflict_id: Conflict ID.

        Returns:
            Dict with escalation details.
        """
        if conflict_id not in self._conflicts:
            raise KeyError(f"Conflict not found: {conflict_id}")

        conflict = self._conflicts[conflict_id]

        if conflict.status == ConflictStatus.RESOLVED:
            return {
                "error": f"Conflict {conflict_id} is already resolved",
                "resolution": conflict.resolution,
            }

        if conflict.status == ConflictStatus.ESCALATED:
            return {
                "error": f"Conflict {conflict_id} is already escalated",
            }

        conflict.status = ConflictStatus.ESCALATED
        self._log_step(
            conflict_id,
            "escalated",
            "Escalated to Executive Orchestrator — all resolution strategies exhausted",
            {
                "reason": "all_strategies_exhausted",
                "positions": [p.to_dict() for p in conflict.positions],
            },
        )

        escalation_payload: Dict[str, Any] = {
            "conflict_id": conflict_id,
            "description": conflict.description,
            "positions": [p.to_dict() for p in conflict.positions],
            "resolution_history": list(conflict.resolution_history),
            "domain": conflict.domain,
            "severity": conflict.severity,
        }

        # Notify external escalation handler if registered
        if self._escalation_handler is not None:
            try:
                result = self._escalation_handler(conflict)
                escalation_payload["handler_result"] = result
            except Exception as exc:
                logger.exception("Escalation handler failed")
                escalation_payload["handler_error"] = str(exc)

        logger.warning(
            f"CONFLICT ESCALATED [{conflict_id}]: {conflict.description[:80]}..."
        )

        return {
            "escalated": True,
            "conflict_id": conflict_id,
            "status": ConflictStatus.ESCALATED.value,
            "payload": escalation_payload,
            "message": (
                "Conflict escalated to Executive Orchestrator. "
                "Resolution pending external decision."
            ),
        }

    def register_escalation_handler(
        self, handler: Callable[[Conflict], Dict[str, Any]]
    ) -> None:
        """Register a callback for escalated conflicts.

        Args:
            handler: Function that receives a Conflict and returns a
                dict with resolution details.
        """
        self._escalation_handler = handler

    # ------------------------------------------------------------------
    # Resolution history / audit
    # ------------------------------------------------------------------

    def get_resolution_history(
        self, conflict_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get the full audit trail for a specific conflict or all conflicts.

        Args:
            conflict_id: Specific conflict ID, or None for all.

        Returns:
            List of history entries (step records).
        """
        if conflict_id is not None:
            if conflict_id not in self._conflicts:
                raise KeyError(f"Conflict not found: {conflict_id}")
            return list(self._conflicts[conflict_id].resolution_history)

        # All conflicts
        all_history: List[Dict[str, Any]] = []
        for cid, conflict in sorted(
            self._conflicts.items(), key=lambda x: x[1].created_at
        ):
            all_history.append({
                "conflict_id": cid,
                "description": conflict.description,
                "status": conflict.status.value,
                "resolution": conflict.resolution,
                "steps": conflict.resolution_history,
            })
        return all_history

    def get_conflict(self, conflict_id: str) -> Optional[Conflict]:
        """Retrieve a conflict by ID."""
        return self._conflicts.get(conflict_id)

    def list_conflicts(
        self, status: Optional[ConflictStatus] = None
    ) -> List[Conflict]:
        """List conflicts, optionally filtered by status.

        Args:
            status: Filter by status; None returns all.

        Returns:
            List of Conflict objects.
        """
        if status is None:
            return list(self._conflicts.values())
        return [c for c in self._conflicts.values() if c.status == status]

    # ------------------------------------------------------------------
    # Conflict prevention hints
    # ------------------------------------------------------------------

    def detect_potential_conflicts(
        self,
        upcoming_decisions: List[Dict[str, Any]],
        knowledge_base_snapshot: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Proactively detect potential conflicts before they arise.

        Scans upcoming decisions for:
            - Overlapping domains with divergent preferences
            - Contradictory requirements
            - Agents with known opposing positions on related topics
            - Historical conflict patterns

        Args:
            upcoming_decisions: List of planned decision descriptions with
                proposed agent positions.
            knowledge_base_snapshot: Optional snapshot of shared knowledge
                for detecting requirement conflicts.

        Returns:
            List of potential conflict warnings with severity and suggestions.
        """
        warnings: List[Dict[str, Any]] = []

        # Check for overlapping domains
        domain_agents: Dict[str, List[str]] = defaultdict(list)
        for i, decision in enumerate(upcoming_decisions):
            domain = decision.get("domain", "general")
            agent = decision.get("proposed_by", f"agent_{i}")
            domain_agents[domain].append(agent)

        for domain, agents in domain_agents.items():
            if len(agents) > 1:
                warnings.append({
                    "type": "domain_overlap",
                    "severity": "medium",
                    "domain": domain,
                    "agents_involved": agents,
                    "message": (
                        f"Multiple agents ({', '.join(agents)}) plan decisions "
                        f"in domain '{domain}'. Coordinate to avoid conflicts."
                    ),
                    "suggestion": (
                        f"Pre-coordinate domain '{domain}' decisions via "
                        f"shared knowledge base before proceeding."
                    ),
                })

        # Check historical conflict patterns
        conflict_domains: Dict[str, int] = defaultdict(int)
        for c in self._conflicts.values():
            if c.domain:
                conflict_domains[c.domain] += 1

        for decision in upcoming_decisions:
            domain = decision.get("domain", "general")
            if conflict_domains.get(domain, 0) >= 2:
                warnings.append({
                    "type": "historical_pattern",
                    "severity": "high",
                    "domain": domain,
                    "past_conflicts": conflict_domains[domain],
                    "message": (
                        f"Domain '{domain}' has had {conflict_domains[domain]} "
                        f"prior conflicts. High risk of recurrence."
                    ),
                    "suggestion": (
                        f"Review past resolutions in domain '{domain}' before "
                        f"finalizing decisions."
                    ),
                })

        # Check for contradictory requirements
        if knowledge_base_snapshot and "entries" in knowledge_base_snapshot:
            requirements = [
                e for e in knowledge_base_snapshot.get("entries", [])
                if e.get("domain") == "project_requirements"
            ]
            for i, req_a in enumerate(requirements):
                for req_b in requirements[i + 1:]:
                    if self._check_contradiction(req_a, req_b):
                        warnings.append({
                            "type": "contradictory_requirements",
                            "severity": "critical",
                            "requirement_a": req_a.get("key"),
                            "requirement_b": req_b.get("key"),
                            "message": (
                                f"Requirements '{req_a.get('key')}' and "
                                f"'{req_b.get('key')}' may be contradictory."
                            ),
                            "suggestion": (
                                "Clarify and reconcile requirements before "
                                "agents take conflicting positions."
                            ),
                        })

        return warnings

    def _check_contradiction(
        self, entry_a: Dict[str, Any], entry_b: Dict[str, Any]
    ) -> bool:
        """Heuristic check for contradictory requirements.

        Looks for negation keywords and mutually exclusive constraints.
        """
        value_a = str(entry_a.get("value", "")).lower()
        value_b = str(entry_b.get("value", "")).lower()

        negation_pairs = [
            ("must", "must not"),
            ("required", "optional"),
            ("always", "never"),
            ("all", "none"),
            ("include", "exclude"),
            ("enable", "disable"),
            ("allow", "deny"),
            ("real-time", "batch"),
            ("sync", "async"),
            ("sql", "nosql"),
        ]

        for pos_word, neg_word in negation_pairs:
            if pos_word in value_a and neg_word in value_b:
                return True
            if neg_word in value_a and pos_word in value_b:
                return True

        return False

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        """Return resolution statistics."""
        status_counts: Dict[str, int] = {}
        strategy_counts: Dict[str, int] = {}
        for c in self._conflicts.values():
            status_counts[c.status.value] = status_counts.get(c.status.value, 0) + 1
            if c.resolution_strategy:
                strategy_counts[
                    c.resolution_strategy.value
                ] = strategy_counts.get(c.resolution_strategy.value, 0) + 1

        return {
            "total_conflicts": len(self._conflicts),
            "by_status": status_counts,
            "by_strategy": strategy_counts,
            "resolution_rate": (
                status_counts.get("resolved", 0) / max(len(self._conflicts), 1)
            ),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _log_step(
        self,
        conflict_id: str,
        step: str,
        description: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a step in the resolution history."""
        entry: Dict[str, Any] = {
            "step": step,
            "description": description,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "data": data or {},
        }
        if conflict_id in self._conflicts:
            self._conflicts[conflict_id].resolution_history.append(entry)

    def _finalize_resolution(self, conflict: Conflict) -> None:
        """Mark a conflict as resolved and record the timestamp."""
        conflict.status = ConflictStatus.RESOLVED
        conflict.resolved_at = time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        self._log_step(
            conflict.conflict_id,
            "resolved",
            f"Resolution: {conflict.resolution}",
            {
                "rationale": conflict.rationale,
                "strategy": (
                    conflict.resolution_strategy.value
                    if conflict.resolution_strategy
                    else None
                ),
                "resolver": conflict.resolver,
            },
        )
        logger.info(
            f"CONFLICT RESOLVED [{conflict.conflict_id}]: "
            f"{conflict.resolution_strategy.value if conflict.resolution_strategy else 'unknown'}"
        )

    def _resolution_response(
        self,
        conflict: Conflict,
        winner: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a standardized resolution response dict."""
        return {
            "conflict_id": conflict.conflict_id,
            "resolution": conflict.resolution,
            "rationale": conflict.rationale,
            "strategy": (
                conflict.resolution_strategy.value
                if conflict.resolution_strategy
                else None
            ),
            "winner": winner,
            "status": conflict.status.value,
            "resolved_at": conflict.resolved_at,
            "escalated": conflict.status == ConflictStatus.ESCALATED,
        }

    def _build_evidence_rationale(
        self, evidence_result: Dict[str, Any]
    ) -> str:
        """Build a human-readable rationale from evidence comparison results."""
        ranking = evidence_result.get("ranking", [])
        lines = ["Resolution by evidence comparison:"]
        for i, entry in enumerate(ranking):
            lines.append(
                f"  {i + 1}. {entry['agent']} ({entry['role']}): "
                f"reliability={entry['reliability']:.3f}, "
                f"evidence_count={entry['evidence_count']}, "
                f"sources={entry['source_types']}"
            )
        return "\n".join(lines)

    def _build_tradeoff_rationale(
        self,
        trade_off_result: List[Tuple[AgentPosition, float, Dict[str, float]]],
    ) -> str:
        """Build a human-readable rationale from trade-off evaluation results."""
        lines = ["Resolution by trade-off evaluation:"]
        for pos, score, per_dim in trade_off_result:
            dim_summary = ", ".join(
                f"{k}={v:.1f}" for k, v in sorted(per_dim.items())
            )
            lines.append(
                f"  {pos.agent_name}: total={score:.2f} [{dim_summary}]"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Convenience singleton
# ---------------------------------------------------------------------------

_resolver_instance: Optional[ConflictResolver] = None


def get_conflict_resolver() -> ConflictResolver:
    """Get or create the global ConflictResolver singleton."""
    global _resolver_instance
    if _resolver_instance is None:
        _resolver_instance = ConflictResolver()
    return _resolver_instance