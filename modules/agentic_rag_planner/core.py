"""Core logic for the agentic RAG retrieval-strategy planner.

Grounded in Cole Medin's talk "Introducing RAG 2.0: Agentic RAG + Knowledge
Graphs" (YouTube p0FERNkpyHE). The talk's central idea: give an AI agent BOTH a
vector/semantic-search tool and a knowledge-graph tool, and let the AGENT "pick
and choose how it explores the knowledge". Vector/semantic search excels at
broad conceptual lookup across document chunks; knowledge graphs excel at
precise relationship / entity / temporal questions (how X relates to Y, facts
represented relationally). An agent given both tools can also use them together
(hybrid) and refine iteratively (search again / fall back) — true agentic RAG.

This module is a PLANNER/ROUTER only. It decides which retrieval tool(s) to use
and in what order, then emits a structured plan. It does NOT implement a vector
DB or a graph DB — it plans over abstract tool interfaces. Pure stdlib,
network-free, fully deterministic.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable

__all__ = [
    "RetrievalTool",
    "ToolKind",
    "VECTOR",
    "GRAPH",
    "HYBRID",
    "RetrievalStep",
    "RetrievalPlan",
    "QueryClassifier",
    "ClassificationResult",
    "RagPlanner",
    "RetrievalTool",
    "RetrievalToolABC",
    "PlanExecutor",
    "InMemoryTool",
]


# =============================================================================
# Retrieval tool kinds
# =============================================================================


class ToolKind(str, Enum):
    """Retrieval tools an agent can choose from (from the transcript).

    VECTOR : semantic / vector search over embedded document chunks — best for
             broad, conceptual "what is / explain / overview" lookups.
    GRAPH  : knowledge-graph traversal — best for precise relationship, entity,
             and temporal questions (how X relates to Y, facts over time).
    HYBRID : use both (a VECTOR step AND a GRAPH step), merge the results.
    """

    VECTOR = "vector"
    GRAPH = "graph"
    HYBRID = "hybrid"


# Convenience module-level constants.
VECTOR = ToolKind.VECTOR
GRAPH = ToolKind.GRAPH
HYBRID = ToolKind.HYBRID


# =============================================================================
# Plan data structures
# =============================================================================


@dataclass(frozen=True)
class RetrievalStep:
    """A single retrieval action in a plan.

    tool  : which concrete retrieval tool to invoke (VECTOR or GRAPH; a HYBRID
            plan is expressed as two steps, never a single HYBRID step).
    query : the query string to issue to that tool.
    reason: human-readable justification for choosing this tool.
    """

    tool: ToolKind
    query: str
    reason: str


@dataclass
class RetrievalPlan:
    """An ordered retrieval plan produced by the planner."""

    steps: list[RetrievalStep] = field(default_factory=list)
    rationale: str = ""
    strategy: ToolKind = ToolKind.VECTOR

    @property
    def tools(self) -> list[ToolKind]:
        """Tools used, in plan order."""
        return [s.tool for s in self.steps]

    def is_hybrid(self) -> bool:
        """True if the plan combines both a VECTOR and a GRAPH step."""
        kinds = {s.tool for s in self.steps}
        return ToolKind.VECTOR in kinds and ToolKind.GRAPH in kinds


# =============================================================================
# Query classification (stdlib heuristics)
# =============================================================================


# Signals that a question is about relationships / entities / time -> GRAPH.
# Grounded in the talk: knowledge graphs represent information "very
# relationally" and are used for how things connect and change over time.
_GRAPH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bhow (?:is|are|does|do)\b.*\b(?:connect|relat|link|associat)", re.I),
    re.compile(r"\brelationship(?:s)?\b", re.I),
    re.compile(r"\brelated to\b", re.I),
    re.compile(r"\bconnect(?:ed|ion|s)?\b", re.I),
    re.compile(r"\blink(?:ed|s)?\b", re.I),
    re.compile(r"\bbetween\b.*\band\b", re.I),
    re.compile(r"\bwho\b.*\b(?:founded|owns|works|reports|manages|acquired)", re.I),
    re.compile(r"\bdepend(?:s|ency|encies)?\b", re.I),
    # temporal / changed-over-time signals
    re.compile(r"\bover time\b", re.I),
    re.compile(r"\bchang(?:e|ed|es|ing)\b", re.I),
    re.compile(r"\bevolv(?:e|ed|ing)\b", re.I),
    re.compile(r"\bbefore\b|\bafter\b|\bwhen did\b", re.I),
    re.compile(r"\btimeline\b|\bhistory of\b", re.I),
    re.compile(r"\bimpact(?:ed|s)?\b.*\bon\b", re.I),
)

# Signals that a question is broad / conceptual -> VECTOR / semantic search.
_VECTOR_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bwhat (?:is|are)\b", re.I),
    re.compile(r"\bexplain\b", re.I),
    re.compile(r"\bdescribe\b", re.I),
    re.compile(r"\boverview\b", re.I),
    re.compile(r"\bsummar(?:y|ize|ise)\b", re.I),
    re.compile(r"\btell me about\b", re.I),
    re.compile(r"\bhow (?:do|does)\b.*\bwork\b", re.I),
    re.compile(r"\bwhy\b", re.I),
    re.compile(r"\bconcept(?:s)?\b", re.I),
    re.compile(r"\bdefinition\b|\bdefine\b", re.I),
)


@dataclass
class ClassificationResult:
    """Outcome of classifying a query."""

    strategy: ToolKind
    graph_score: int
    vector_score: int
    graph_hits: list[str] = field(default_factory=list)
    vector_hits: list[str] = field(default_factory=list)

    @property
    def reason(self) -> str:
        if self.strategy is ToolKind.GRAPH:
            return (
                "Relationship/entity/temporal signals dominate "
                f"(graph={self.graph_score} > vector={self.vector_score}); "
                "knowledge-graph traversal fits precise relational questions."
            )
        if self.strategy is ToolKind.VECTOR:
            return (
                "Broad/conceptual signals dominate "
                f"(vector={self.vector_score} >= graph={self.graph_score}); "
                "semantic/vector search fits broad conceptual lookup."
            )
        return (
            "Both relational and conceptual signals present "
            f"(graph={self.graph_score}, vector={self.vector_score}); "
            "use both tools (hybrid) and merge the results."
        )


class QueryClassifier:
    """Classify a query into a retrieval strategy using stdlib heuristics."""

    def __init__(self, hybrid_margin: int = 0) -> None:
        # When both tools score and neither strictly dominates past the margin,
        # prefer HYBRID. hybrid_margin tunes how close the scores must be.
        self._hybrid_margin = max(0, int(hybrid_margin))

    def classify(self, query: str) -> ClassificationResult:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")

        graph_hits = [p.pattern for p in _GRAPH_PATTERNS if p.search(query)]
        vector_hits = [p.pattern for p in _VECTOR_PATTERNS if p.search(query)]
        g = len(graph_hits)
        v = len(vector_hits)

        if g > 0 and v > 0:
            strategy = ToolKind.HYBRID
        elif g > v:
            strategy = ToolKind.GRAPH
        elif v > g:
            strategy = ToolKind.VECTOR
        else:
            # No signals at all: default to broad semantic search, the talk's
            # baseline "traditional RAG" over embedded chunks.
            strategy = ToolKind.VECTOR

        return ClassificationResult(
            strategy=strategy,
            graph_score=g,
            vector_score=v,
            graph_hits=graph_hits,
            vector_hits=vector_hits,
        )


# =============================================================================
# Planner
# =============================================================================


class RagPlanner:
    """Decide which retrieval tool(s) to use, and emit a structured plan.

    This embodies the transcript's "the agent picks and chooses how it explores
    the knowledge" idea: one planning pass routes to VECTOR, GRAPH, or HYBRID.
    """

    def __init__(self, classifier: QueryClassifier | None = None) -> None:
        self._classifier = classifier or QueryClassifier()

    def plan(self, query: str) -> RetrievalPlan:
        """Produce a single-pass retrieval plan for a query."""
        result = self._classifier.classify(query)
        steps: list[RetrievalStep] = []

        if result.strategy is ToolKind.GRAPH:
            steps.append(
                RetrievalStep(
                    tool=ToolKind.GRAPH,
                    query=query,
                    reason="Precise relationship/entity/temporal question -> "
                    "traverse the knowledge graph.",
                )
            )
        elif result.strategy is ToolKind.VECTOR:
            steps.append(
                RetrievalStep(
                    tool=ToolKind.VECTOR,
                    query=query,
                    reason="Broad/conceptual question -> semantic vector search "
                    "over document chunks.",
                )
            )
        else:  # HYBRID: a VECTOR step AND a GRAPH step, in that order.
            steps.append(
                RetrievalStep(
                    tool=ToolKind.VECTOR,
                    query=query,
                    reason="Hybrid: start broad with semantic vector search.",
                )
            )
            steps.append(
                RetrievalStep(
                    tool=ToolKind.GRAPH,
                    query=query,
                    reason="Hybrid: enrich with relational facts from the "
                    "knowledge graph.",
                )
            )

        return RetrievalPlan(
            steps=steps,
            rationale=result.reason,
            strategy=result.strategy,
        )

    def plan_multi(
        self,
        query: str,
        prior_result_counts: list[int] | None = None,
    ) -> RetrievalPlan:
        """Produce an iterative/refined plan (agentic refinement).

        Models the talk's "the agent can search again / refine" behaviour: if a
        prior step returned no (or too few) results, append a fallback step that
        tries the OTHER tool. ``prior_result_counts`` is the result count per
        step of a previously-executed base plan (same order as ``plan``).
        """
        base = self.plan(query)
        if not prior_result_counts:
            return base

        steps = list(base.steps)
        used = {s.tool for s in steps}
        extra_rationale: list[str] = []

        # If any executed step came back empty, add a fallback with another tool.
        for step, count in zip(base.steps, prior_result_counts):
            if count <= 0:
                fallback_tool = (
                    ToolKind.GRAPH if step.tool is ToolKind.VECTOR else ToolKind.VECTOR
                )
                if fallback_tool not in used:
                    steps.append(
                        RetrievalStep(
                            tool=fallback_tool,
                            query=query,
                            reason=(
                                f"Refinement: {step.tool.value} search returned "
                                f"no results; fall back to {fallback_tool.value}."
                            ),
                        )
                    )
                    used.add(fallback_tool)
                    extra_rationale.append(
                        f"{step.tool.value} empty -> added {fallback_tool.value} fallback"
                    )

        rationale = base.rationale
        if extra_rationale:
            rationale = rationale + " | Agentic refinement: " + "; ".join(extra_rationale)

        strategy = HYBRID if {s.tool for s in steps} >= {VECTOR, GRAPH} else base.strategy
        return RetrievalPlan(steps=steps, rationale=rationale, strategy=strategy)


# =============================================================================
# Abstract retrieval tool interface + executor
# =============================================================================


@runtime_checkable
class RetrievalTool(Protocol):
    """Abstract retrieval tool the planner routes over.

    Concrete tools (a vector DB, a graph DB) live outside this module; the
    planner only needs this ``search`` contract.
    """

    kind: ToolKind

    def search(self, query: str) -> list[dict]:
        """Return a list of result records (each a dict with at least 'id')."""
        ...


class RetrievalToolABC(ABC):
    """ABC convenience base for in-process retrieval tools."""

    kind: ToolKind

    @abstractmethod
    def search(self, query: str) -> list[dict]:
        ...


class InMemoryTool(RetrievalToolABC):
    """Deterministic in-memory stub tool for tests and local planning."""

    def __init__(self, kind: ToolKind, records: list[dict] | None = None) -> None:
        self.kind = kind
        self._records = list(records or [])

    def search(self, query: str) -> list[dict]:
        # Deterministic: return all records (a stub); real tools would rank.
        return [dict(r) for r in self._records]


class PlanExecutor:
    """Execute a :class:`RetrievalPlan` against injected retrieval tools.

    Runs each step in plan order against the tool matching the step's kind,
    then merges and de-duplicates results (dedup key = 'id', falling back to the
    whole record). Preserves first-seen order across steps.
    """

    def __init__(self, tools: dict[ToolKind, RetrievalTool]) -> None:
        self._tools = dict(tools)

    def execute(self, plan: RetrievalPlan) -> list[dict]:
        merged: list[dict] = []
        seen: set = set()
        for step in plan.steps:
            tool = self._tools.get(step.tool)
            if tool is None:
                continue
            for record in tool.search(step.query):
                key = record.get("id") if isinstance(record, dict) else None
                if key is None:
                    key = tuple(sorted(record.items())) if isinstance(record, dict) else record
                if key in seen:
                    continue
                seen.add(key)
                merged.append(record)
        return merged

    def execute_counts(self, plan: RetrievalPlan) -> list[int]:
        """Return the per-step result count (before dedup), in plan order."""
        counts: list[int] = []
        for step in plan.steps:
            tool = self._tools.get(step.tool)
            counts.append(len(tool.search(step.query)) if tool is not None else 0)
        return counts
