"""AI Systems Thinking — a pure evaluation engine for AI system designs.

Grounded in the pulled JE Van Clief transcripts:

* ``NWyTsKTKka8`` — *Systems Thinking for People Who Build With AI*:
    - "map the structure underneath" / "it's not the whole book, it's not the
      whole bookshelf, it's just a description of what should be there" — the
      whole-vs-parts lens.
    - "Each program does one thing well" / "plain text is a universal
      interface" / "if Claude goes down, you just hop over to the other one
      [model]" — component cohesion, coupling, decoupling.
    - "if you ask why agent 7 did what it did, how much it costs, who approved
      it, a lot of the times it's hard to track all of that" — traceability.
    - "if you don't know why you need it, you probably don't need it" — the
      over-optimization / needless-complexity trap.
    - the folder write-back loop across sessions ("close that session... that
      file's now there... opening up a new session... the memory's there") —
      persistent feedback loops and ground-truth verification.

* ``jjV1ckgPzI0`` — *I Charged $2000 For This AI Lecture*:
    - "The Ariane 5 rocket exploded due to integer overflow error... a
      deterministic system that caused the failure because it was acting in
      probabilistic ways" — second-order effects / unintended consequences.
    - "an agent is simply some sort of AI model with access to tools and
      data... another layer of abstraction" and "the evaluation layer...
      whether these agents, these steps, these processes... are doing well" —
      evaluation & traceability at scale.
    - "think about how probabilistic and unvariable [unpredictable] a single
      human can be" — human-in-the-loop variability.

* ``g3eWjeZPFiM`` — *Life, Liberty and the pursuit of Artificial Intelligence*:
    - "emergent property in sufficiently advanced machines" (Turing) and the
      fallacy that "all consequences of that fact spring into the Mind
      simultaneously" — emergence & consequence-blindness.
    - "governance aligning technological capabilities with ethical
      imperatives" / stakeholder perception — systemic integration risk.

This module turns those heuristics into a deterministic, network-free scoring
engine that evaluates a description of an AI system design and emits a
structured assessment: per-dimension scores, identified feedback loops
(declared *and* implicit ones found in the coupling graph), leverage points,
coupling analysis, unintended-consequence risks, contradictions, and an overall
read.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

__version__ = "1.0.0"


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class CouplingStrength(str, Enum):
    """How tightly two components are bound together (transcript: decoupling
    models/backends via a universal plain-text interface)."""

    LOOSE = "loose"
    MODERATE = "moderate"
    TIGHT = "tight"


class LoopType(str, Enum):
    """A feedback loop either reinforces growth/behavior or balances it."""

    REINFORCING = "reinforcing"
    BALANCING = "balancing"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class OverallRead(str, Enum):
    """Overall systems-health verdict for the design."""

    EXCELLENT = "excellent"
    SOUND = "sound"
    REMEDIABLE = "remediable"
    FRAGILE = "fragile"


# --------------------------------------------------------------------------- #
# Input model
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Component:
    """A single part of the AI system (an agent, retriever, store, UI, model...)."""

    name: str
    function: str = ""
    coupling: CouplingStrength = CouplingStrength.MODERATE
    responsibilities: int = 1          # >1 means the part tries to do many things
    self_evaluates: bool = False       # has a self/ROI evaluation loop
    logged: bool = False               # observable/logged behaviour
    cost_tracked: bool = False         # cost attribution exists
    approved: bool = False             # a human/sign-off gate exists


@dataclass(frozen=True)
class Connection:
    """A directed coupling edge between two components (a data/control flow)."""

    source: str
    target: str


@dataclass(frozen=True)
class FeedbackLoop:
    """A declared feedback loop in the system.

    ``implicit`` marks a loop the engine found in the coupling graph but the
    designer did not declare (i.e. a loop the designer was blind to).
    """

    name: str
    components: Tuple[str, ...]
    loop_type: LoopType = LoopType.BALANCING
    persistent: bool = False           # survives session restarts (file write-back)
    verifies_ground_truth: bool = False
    described_second_order: bool = False
    implicit: bool = False


@dataclass(frozen=True)
class DesignContext:
    """How the design treats context and complexity."""

    progressive_disclosure: bool = False   # reads only what it needs, not everything
    minimal_complexity: bool = False       # avoids needless harnesses/LangGraph bloat
    universal_interface: bool = False      # plain-text/portable interface (swap models)
    interface_count: int = 1


@dataclass(frozen=True)
class Governance:
    """Oversight, side-effect awareness and stakeholder consideration."""

    human_in_the_loop: bool = False
    accounts_for_human_variability: bool = False
    second_order_analysis: bool = False    # planned-for unintended consequences
    emergence_documented: bool = False     # acknowledged emergent behaviour
    stakeholder_viewed: bool = False       # whole-system/societal view taken


@dataclass(frozen=True)
class AISystemDesign:
    """The full system description the engine evaluates."""

    name: str
    components: Sequence[Component] = ()
    connections: Sequence[Connection] = ()
    feedback_loops: Sequence[FeedbackLoop] = ()
    context: DesignContext = field(default_factory=DesignContext)
    governance: Governance = field(default_factory=Governance)
    explicit_marks: Optional[Dict[str, float]] = None  # optional designer marks


# --------------------------------------------------------------------------- #
# Output model
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CouplingAnalysis:
    edge: Tuple[str, str]
    strength: CouplingStrength


@dataclass(frozen=True)
class LeveragePoint:
    """A point where a small, well-placed change moves the whole system."""

    target: str
    reason: str
    magnitude: float  # 0..1


@dataclass(frozen=True)
class Risk:
    code: str
    message: str
    severity: RiskLevel


@dataclass(frozen=True)
class Contradiction:
    dimension: str
    message: str


@dataclass(frozen=True)
class SystemsAssessment:
    """Structured result of a systems-thinking evaluation."""

    design_name: str
    dimensions: Dict[str, float]
    overall_score: float
    overall: OverallRead
    implicit_feedback_loops: Tuple[FeedbackLoop, ...]
    leverage_points: Tuple[LeveragePoint, ...]
    couplings: Tuple[CouplingAnalysis, ...]
    risks: Tuple[Risk, ...]
    contradictions: Tuple[Contradiction, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "design_name": self.design_name,
            "dimensions": dict(self.dimensions),
            "overall_score": round(self.overall_score, 4),
            "overall": self.overall.value,
            "implicit_feedback_loops": [
                {"name": l.name, "components": list(l.components),
                 "loop_type": l.loop_type.value, "persistent": l.persistent,
                 "verifies_ground_truth": l.verifies_ground_truth}
                for l in self.implicit_feedback_loops
            ],
            "leverage_points": [
                {"target": lp.target, "reason": lp.reason,
                 "magnitude": round(lp.magnitude, 3)}
                for lp in self.leverage_points
            ],
            "couplings": [
                {"edge": list(c.edge), "strength": c.strength.value}
                for c in self.couplings
            ],
            "risks": [
                {"code": r.code, "message": r.message, "severity": r.severity.value}
                for r in self.risks
            ],
            "contradictions": [
                {"dimension": c.dimension, "message": c.message}
                for c in self.contradictions
            ],
        }


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #
def _clamp(x: float) -> float:
    return min(1.0, max(0.0, x))


_COUPLING_NUM = {
    CouplingStrength.LOOSE: 0.25,
    CouplingStrength.MODERATE: 0.55,
    CouplingStrength.TIGHT: 0.9,
}


class SystemsThinker:
    """Pure, network-free systems-thinking evaluator for AI system designs."""

    # dimension weights for the overall read (sums to 1.0)
    WEIGHTS = {
        "holistic_view": 0.15,
        "modularity": 0.15,
        "feedback_loops": 0.20,
        "traceability": 0.15,
        "context_leverage": 0.15,
        "unintended_consequences": 0.10,
        "emergence_awareness": 0.10,
    }

    # ------------------------------------------------------------------ #
    # Evaluation entry point
    # ------------------------------------------------------------------ #
    def evaluate(self, design: AISystemDesign) -> SystemsAssessment:
        comps = list(design.components)
        conns = list(design.connections)
        declared = list(design.feedback_loops)
        ctx = design.context
        gov = design.governance

        # implicit loops found by walking the coupling graph (cycles)
        implicit = self._find_implicit_feedback_loops(comps, conns, declared)

        couplings = self._coupling_analysis(comps, conns)

        dimensions = self._dimension_scores(
            design, comps, conns, declared, implicit,
        )
        contradictions, adjusted = self._cross_check(design, dimensions)

        risks = self._risks(comps, conns, declared, implicit, gov, couplings)
        leverage = self._leverage_points(comps, conns, declared, implicit, ctx)

        overall_score = self._overall(adjusted)
        overall = self._verdict(overall_score)

        return SystemsAssessment(
            design_name=design.name,
            dimensions=adjusted,
            overall_score=overall_score,
            overall=overall,
            implicit_feedback_loops=tuple(implicit),
            leverage_points=tuple(leverage),
            couplings=tuple(couplings),
            risks=tuple(risks),
            contradictions=tuple(contradictions),
        )

    # ------------------------------------------------------------------ #
    # Cycle detection -> implicit feedback loops (the "see the whole" step)
    # ------------------------------------------------------------------ #
    def _find_implicit_feedback_loops(
        self,
        comps: Sequence[Component],
        conns: Sequence[Connection],
        declared: Sequence[FeedbackLoop],
    ) -> List[FeedbackLoop]:
        names = {c.name for c in comps}
        adj: Dict[str, List[str]] = {c.name: [] for c in comps}
        for e in conns:
            if e.source in adj and e.target in adj:
                adj[e.source].append(e.target)

        declared_sets = [frozenset(l.components) for l in declared]
        found: List[FeedbackLoop] = []
        seen: set = set()
        path: List[str] = []

        def dfs(node: str) -> None:
            if node in seen:
                return
            idx = path.index(node) if node in path else -1
            if idx >= 0:
                cycle = tuple(path[idx:])
                key = frozenset(cycle)
                if key not in seen and len(cycle) >= 2:
                    seen.add(key)
                    if key not in declared_sets:
                        found.append(FeedbackLoop(
                            name="implicit-loop-" + "-".join(sorted(cycle)),
                            components=cycle,
                            loop_type=LoopType.BALANCING,  # unknown polarity
                            implicit=True,
                        ))
                return
            path.append(node)
            for nxt in adj.get(node, []):
                dfs(nxt)
            path.pop()

        for c in comps:
            dfs(c.name)
            # reset path traversal markers for a fresh DFS from next root
            path = []
        return found

    # ------------------------------------------------------------------ #
    # Coupling analysis
    # ------------------------------------------------------------------ #
    def _coupling_analysis(
        self,
        comps: Sequence[Component],
        conns: Sequence[Connection],
    ) -> List[CouplingAnalysis]:
        strength = {c.name: c.coupling for c in comps}
        out = []
        for e in conns:
            s = strength.get(e.source) or strength.get(e.target) or CouplingStrength.MODERATE
            out.append(CouplingAnalysis(edge=(e.source, e.target), strength=s))
        # self-contained components with no edges are "free" (decoupled)
        return out

    # ------------------------------------------------------------------ #
    # Dimension scoring (0..1 each)
    # ------------------------------------------------------------------ #
    def _dimension_scores(
        self,
        design: AISystemDesign,
        comps: Sequence[Component],
        conns: Sequence[Connection],
        declared: Sequence[FeedbackLoop],
        implicit: Sequence[FeedbackLoop],
    ) -> Dict[str, float]:
        n = len(comps)
        ctx = design.context
        gov = design.governance
        all_loops = list(declared) + list(implicit)

        # --- holistic_view: whole vs parts (whole book vs description) ---
        loop_span = 0.0
        if all_loops:
            in_loops = {c for l in all_loops for c in l.components}
            loop_span = len(in_loops) / n if n else 0.0
        connected = len({c.name for c in comps if any(
            e.source == c.name or e.target == c.name for e in conns)})
        multi = connected / n if n else 0.0
        holistic = _clamp(
            0.4 * loop_span + 0.4 * multi + (0.2 if gov.stakeholder_viewed else 0.0)
        )

        # --- modularity: each program does one thing well + decoupling ---
        if n:
            avg_c = sum(_COUPLING_NUM[c.coupling] for c in comps) / n
        else:
            avg_c = 0.5
        multi_resp = sum(1 for c in comps if c.responsibilities > 1)
        modularity = _clamp(
            1.0 - avg_c
            - 0.15 * (multi_resp / n if n else 0.0)
            + 0.15 * (1 if ctx.universal_interface else 0.0)
            + 0.10 * (1 if ctx.minimal_complexity else 0.0)
        )

        # --- feedback_loops: quality of declared + implicit loops ---
        if all_loops:
            qualities = []
            for l in all_loops:
                q = 0.45
                q += 0.25 if l.persistent else 0.0
                q += 0.20 if l.verifies_ground_truth else 0.0
                q += 0.10 if l.described_second_order else 0.0
                if l.loop_type == LoopType.REINFORCING:
                    q -= 0.05  # unchecked reinforcing loops can run away
                qualities.append(_clamp(q))
            feedback = sum(qualities) / len(qualities)
        else:
            feedback = 0.0

        # --- traceability: "why agent 7 did what it did, how much it costs ---
        if n:
            traces = []
            for c in comps:
                t = 0.25
                t += 0.25 if c.logged else 0.0
                t += 0.25 if c.cost_tracked else 0.0
                t += 0.25 if c.approved else 0.0
                t += 0.25 if c.self_evaluates else 0.0
                traces.append(_clamp(t))
            traceability = sum(traces) / n
        else:
            traceability = 0.0
        if gov.accounts_for_human_variability:
            traceability = _clamp(traceability + 0.1)

        # --- context_leverage: progressive disclosure, avoid over-build ---
        context_leverage = _clamp(
            0.2
            + 0.30 * (1 if ctx.progressive_disclosure else 0.0)
            + 0.25 * (1 if ctx.minimal_complexity else 0.0)
            + 0.25 * (1 if ctx.universal_interface else 0.0)
        )

        # --- unintended_consequences: second-order awareness minus coupling risk ---
        unintended = _clamp(
            0.2
            + 0.30 * (1 if gov.second_order_analysis else 0.0)
            + 0.20 * (1 if gov.emergence_documented else 0.0)
            + 0.15 * (1 if gov.stakeholder_viewed else 0.0)
            + 0.15 * (1 if gov.accounts_for_human_variability else 0.0)
            - 0.10 * sum(1 for c in comps if c.coupling == CouplingStrength.TIGHT)
        )

        # --- emergence_awareness: emergent behaviour acknowledged ---
        emergence = _clamp(
            0.3
            + 0.30 * (1 if gov.emergence_documented else 0.0)
            + 0.20 * (1 if gov.human_in_the_loop else 0.0)
            + 0.20 * (1 if gov.accounts_for_human_variability else 0.0)
        )

        return {
            "holistic_view": holistic,
            "modularity": modularity,
            "feedback_loops": feedback,
            "traceability": traceability,
            "context_leverage": context_leverage,
            "unintended_consequences": unintended,
            "emergence_awareness": emergence,
        }

    # ------------------------------------------------------------------ #
    # Cross-check: blend explicit marks, flag contradictions
    # ------------------------------------------------------------------ #
    def _cross_check(
        self,
        design: AISystemDesign,
        computed: Dict[str, float],
    ) -> Tuple[List[Contradiction], Dict[str, float]]:
        marks = design.explicit_marks or {}
        adjusted = dict(computed)
        contradictions: List[Contradiction] = []

        for dim, mark in marks.items():
            base = computed.get(dim)
            if base is None:
                continue
            adjusted[dim] = _clamp(0.5 * base + 0.5 * mark)
            if abs(base - mark) > 0.35:
                contradictions.append(Contradiction(
                    dimension=dim,
                    message=(
                        f"designer mark ({mark:.2f}) disagrees sharply with "
                        f"structural evidence ({base:.2f}) for '{dim}'"
                    ),
                ))
        return contradictions, adjusted

    # ------------------------------------------------------------------ #
    # Risks (unintended consequences / over-optimization)
    # ------------------------------------------------------------------ #
    def _risks(
        self,
        comps: Sequence[Component],
        conns: Sequence[Connection],
        declared: Sequence[FeedbackLoop],
        implicit: Sequence[FeedbackLoop],
        gov: Governance,
        couplings: Sequence[CouplingAnalysis],
    ) -> List[Risk]:
        risks: List[Risk] = []
        n = len(comps)

        # tight couplings in the flow
        tight = [c for c in couplings if c.strength == CouplingStrength.TIGHT]
        for c in tight:
            risks.append(Risk(
                code="TIGHT_COUPLING",
                message=(
                    f"components {c.edge[0]}<->{c.edge[1]} are tightly coupled; "
                    "a change ripples through the system"
                ),
                severity=RiskLevel.HIGH if implicit else RiskLevel.MEDIUM,
            ))

        # consequence-blindness: implicit loops exist but no 2nd-order analysis
        if implicit and not gov.second_order_analysis:
            risks.append(Risk(
                code="UNANTICIPATED_SECOND_ORDER",
                message=(
                    f"{len(implicit)} implicit feedback loop(s) discovered in the "
                    "coupling graph but the design does not plan for second-order "
                    "effects (Turing's 'all consequences spring to mind' fallacy)"
                ),
                severity=RiskLevel.HIGH,
            ))

        # over-optimizing one part in isolation (see the whole vs the parts)
        connected = {e.source for e in conns} | {e.target for e in conns}
        for c in comps:
            if c.responsibilities > 2 and c.name not in connected:
                risks.append(Risk(
                    code="OVER_OPTIMIZED_ISOLATED_PART",
                    message=(
                        f"'{c.name}' is over-built (loads {c.responsibilities} "
                        "responsibilities) yet disconnected from the rest of the "
                        "system — optimizing a part at the whole's expense"
                    ),
                    severity=RiskLevel.MEDIUM,
                ))

        # human-in-the-loop variability ignored
        if gov.human_in_the_loop and not gov.accounts_for_human_variability:
            risks.append(Risk(
                code="HUMAN_LOOP_VARIABILITY",
                message="a human is in the loop but their variability is unaccounted for",
                severity=RiskLevel.LOW,
            ))

        if not risks and n == 0:
            risks.append(Risk(
                code="EMPTY_DESIGN",
                message="no components described, so the evaluation is vacuous",
                severity=RiskLevel.MEDIUM,
            ))
        return risks

    # ------------------------------------------------------------------ #
    # Leverage points
    # ------------------------------------------------------------------ #
    def _leverage_points(
        self,
        comps: Sequence[Component],
        conns: Sequence[Connection],
        declared: Sequence[FeedbackLoop],
        implicit: Sequence[FeedbackLoop],
        ctx: DesignContext,
    ) -> List[LeveragePoint]:
        out: List[LeveragePoint] = []
        degree: Dict[str, int] = {c.name: 0 for c in comps}
        for e in conns:
            if e.source in degree:
                degree[e.source] += 1
            if e.target in degree:
                degree[e.target] += 1
        max_deg = max(degree.values()) if degree else 0
        for name, d in degree.items():
            if d >= max(2, max_deg * 0.6) and d > 0:
                out.append(LeveragePoint(
                    target=name,
                    reason=f"hub with {d} connections; a change here reaches most of the system",
                    magnitude=min(1.0, d / max(2, max_deg)),
                ))

        # a balancing feedback loop is a classical leverage point
        for l in declared:
            if l.loop_type == LoopType.BALANCING and l.verifies_ground_truth:
                out.append(LeveragePoint(
                    target=l.name,
                    reason="a ground-truth-verified balancing loop — adjusting it re-centres the whole system",
                    magnitude=0.8,
                ))

        # complexity itself is a leverage point ("if you don't know why you
        # need it, you probably don't need it")
        if not ctx.minimal_complexity and len(comps) > 4:
            out.append(LeveragePoint(
                target="context",
                reason=(
                    "needless harness/complexity detected; simplifying is a "
                    "high-leverage, low-cost move"
                ),
                magnitude=0.6,
            ))
        return out

    # ------------------------------------------------------------------ #
    # Overall read
    # ------------------------------------------------------------------ #
    def _overall(self, dimensions: Dict[str, float]) -> float:
        score = sum(dimensions.get(d, 0.0) * w for d, w in self.WEIGHTS.items())
        return _clamp(score)

    @staticmethod
    def _verdict(score: float) -> OverallRead:
        if score >= 0.8:
            return OverallRead.EXCELLENT
        if score >= 0.6:
            return OverallRead.SOUND
        if score >= 0.4:
            return OverallRead.REMEDIABLE
        return OverallRead.FRAGILE


def assess(design: AISystemDesign) -> SystemsAssessment:
    """Convenience one-liner: evaluate a design with a fresh evaluator."""
    return SystemsThinker().evaluate(design)


__all__ = [
    "CouplingStrength",
    "LoopType",
    "RiskLevel",
    "OverallRead",
    "Component",
    "Connection",
    "FeedbackLoop",
    "DesignContext",
    "Governance",
    "AISystemDesign",
    "CouplingAnalysis",
    "LeveragePoint",
    "Risk",
    "Contradiction",
    "SystemsAssessment",
    "SystemsThinker",
    "assess",
    "__version__",
]
