"""Core logic for the ``rag_strategy_router`` module.

Pure, deterministic, network-free, stdlib-only intent-based RAG strategy
router grounded in the ColeMedin transcript *"Introducing RAG 2.0: Agentic
RAG + Knowledge Graphs (FREE Template)"* (``ColeMedin/p0FERNkpyHE.md``).

What the transcript actually teaches (the grounding for every signal here):

  * Two retrieval strategies are combined: a **vector database** (chunked /
    embedded documents — "traditional rag", semantic similarity lookup) and a
    **knowledge graph** (entities as nodes, typed relationships as edges, e.g.
    *Amazon --invested_in--> Anthropic*, *Anthropic --runs_on--> AWS*,
    *Microsoft --partnered_with--> OpenAI --hosted_on--> Azure*).

  * The agent gets to **"pick and choose how it explores the knowledge"** per
    query — that routing decision is exactly what THIS module models. It is a
    *dispatcher*, NOT another retriever.

  * The transcript's explicit decision rules (from the demo + the system
    prompt the author shows on screen):
      - "what are the AI initiatives for Google" -> single company / fact
        lookup -> **vector search** ("it just did a simple vector search ...
        it doesn't need to do the knowledge graph in this case").
      - "how are OpenAI and Microsoft related" -> relationship between two
        entities -> **knowledge graph** ("the kind of thing that would
        definitely call for a query to our knowledge graph").
      - The author's system prompt: *"use the knowledge graph tool only when
        the user asks about two companies in the same question ... analyze the
        relationship between two companies ... Otherwise just use the vector
        store tool. And combine both approaches only when you are asked to do
        so."*
      - "what are the initiatives for Microsoft? how does that relate to
        anthropic? use both search types" -> a question that wants BOTH a
        single-entity lookup AND a relationship lookup -> **hybrid** (vector
        first, then graph to compare).

  * There is NO temporal / point-in-time facet anywhere in this transcript, so
    this router deliberately does NOT invent one. Signals are limited to what
    the author actually describes: relational/multi-entity -> GRAPH, broad
    semantic / single-entity fact lookup -> VECTOR, both intents present (or an
    explicit "use both") -> HYBRID.

The classifier scores a query against weighted keyword / regex signal sets and
returns a deterministic :class:`RouteDecision`. The :class:`StrategyRouter`
wraps the classifier and exposes ``route`` / ``route_batch``. A tiny pluggable
registry lets a caller inject one callable retriever per strategy; ``dispatch``
selects the strategy and calls that injected retriever (no network, pure).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Mapping, Optional, Pattern, Sequence, Tuple


# =============================================================================
# Strategy enum
# =============================================================================


class Strategy(Enum):
    """The three retrieval strategies the transcript's agent chooses between.

    * ``VECTOR`` — semantic / lexical similarity lookup over chunked documents
      ("traditional rag"); used for single-entity fact lookups such as
      *"what are the AI initiatives for Google"*.
    * ``GRAPH``  — knowledge-graph traversal over entities + typed
      relationships; used for relational / multi-entity questions such as
      *"how are OpenAI and Microsoft related"*.
    * ``HYBRID`` — combine both; used when a query carries both a fact-lookup
      intent AND a relationship intent, or explicitly asks to "use both".
    """

    VECTOR = "vector"
    GRAPH = "graph"
    HYBRID = "hybrid"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value

    @classmethod
    def from_value(cls, value: "Strategy | str") -> "Strategy":
        """Coerce a string or Strategy into a Strategy (case-insensitive)."""
        if isinstance(value, cls):
            return value
        key = str(value).strip().lower()
        for member in cls:
            if member.value == key or member.name.lower() == key:
                return member
        raise ValueError(f"unknown strategy: {value!r}")


def all_strategies() -> List[Strategy]:
    """Return every strategy (helper; intentionally NOT named ``list``)."""
    return list(Strategy)


# =============================================================================
# Signal definitions
# =============================================================================


@dataclass(frozen=True)
class Signal:
    """A single named routing signal: a compiled regex + the strategy it votes
    for + a base weight. Grounded in a phrase the transcript actually uses.
    """

    name: str
    strategy: Strategy
    pattern: Pattern[str]
    weight: float
    description: str = ""

    def search(self, text: str) -> bool:
        """Return True if the signal's pattern matches ``text``."""
        return self.pattern.search(text) is not None

    def count(self, text: str) -> int:
        """Number of (non-overlapping) matches of this signal in ``text``."""
        return len(self.pattern.findall(text))


def _rx(pattern: str) -> Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


# --- GRAPH signals: relationships / multiple entities ------------------------
# From the transcript: knowledge graph is for "how two companies relate",
# "the relationship between two companies", "how these companies are coupled
# together", "a more relational lookup".
_GRAPH_SIGNALS: Tuple[Signal, ...] = (
    Signal(
        "relationship_term",
        Strategy.GRAPH,
        _rx(r"\brelationship(s)?\b"),
        3.0,
        "transcript: 'analyze the relationship between two companies'",
    ),
    Signal(
        "related_term",
        Strategy.GRAPH,
        _rx(r"\brelate(d|s)?\b"),
        3.0,
        "transcript: 'how are OpenAI and Microsoft related'",
    ),
    Signal(
        "how_connected",
        Strategy.GRAPH,
        _rx(r"\bhow\b.*\b(connect(ed|s)?|link(ed|s)?|couple(d)?|tie(d|s)?|associat)"),
        2.5,
        "transcript: 'how these companies are coupled together'",
    ),
    Signal(
        "relational_term",
        Strategy.GRAPH,
        _rx(r"\brelational\b"),
        2.5,
        "transcript: 'a more relational lookup ... explore a knowledge graph'",
    ),
    Signal(
        "connection_noun",
        Strategy.GRAPH,
        _rx(r"\b(connection(s)?|link(s)?|tie(s)?|partnership(s)?|partner(ed|s)?)\b"),
        2.0,
        "transcript: entities + typed relationships (partnered_with, invested_in)",
    ),
    Signal(
        "between_entities",
        Strategy.GRAPH,
        _rx(r"\bbetween\b"),
        1.5,
        "transcript: 'comparison between Microsoft and Anthropic'",
    ),
    Signal(
        "interaction_verb",
        Strategy.GRAPH,
        _rx(r"\b(invest(ed|s|ment)?|acquire(d|s)?|host(ed|s)?|run(s)? on|depend(s)? on|work(s)? with|collaborat)"),
        1.5,
        "transcript edges: invested_in / runs_on / hosted_on / partnered_with",
    ),
    Signal(
        "two_entity_conjunction",
        Strategy.GRAPH,
        _rx(r"\b[A-Z][\w.]+\s+(?:and|&|vs\.?|versus)\s+[A-Z][\w.]+"),
        2.0,
        "transcript: 'use the knowledge graph only when ... two companies in the same question'",
    ),
)

# --- VECTOR signals: broad semantic / single-entity fact lookup --------------
# From the transcript: vector DB is for "look up individual information on
# specific companies", "a simple vector search", "what are the AI initiatives
# for Google", "find information on a single company".
_VECTOR_SIGNALS: Tuple[Signal, ...] = (
    Signal(
        "tell_me_about",
        Strategy.VECTOR,
        _rx(r"\btell me about\b|\boverview of\b|\bsummar(y|ize|ise)\b"),
        3.0,
        "broad semantic lookup — traditional rag similarity search",
    ),
    Signal(
        "what_are_initiatives",
        Strategy.VECTOR,
        _rx(r"\bwhat (are|is)\b.*\b(initiative(s)?|strateg(y|ies)|product(s)?|plan(s)?|detail(s)?|info(rmation)?)\b"),
        2.5,
        "transcript: 'what are the AI initiatives for Google' -> vector search",
    ),
    Signal(
        "lookup_term",
        Strategy.VECTOR,
        _rx(r"\b(look ?up|find|search for|information on|info on|details on|describe)\b"),
        2.0,
        "transcript: 'look up individual information on specific companies'",
    ),
    Signal(
        "single_fact_wh",
        Strategy.VECTOR,
        _rx(r"\b(what|who|which|where|when)\b"),
        1.0,
        "fact-lookup question words -> semantic vector lookup by default",
    ),
    Signal(
        "define_term",
        Strategy.VECTOR,
        _rx(r"\b(define|definition of|explain|what does .* mean)\b"),
        1.5,
        "broad semantic / definitional lookup over chunked docs",
    ),
)

# --- HYBRID signals: explicit "use both" -------------------------------------
# From the transcript: "use both search types", "combine both approaches",
# "use the vector database and the knowledge graph".
_HYBRID_SIGNALS: Tuple[Signal, ...] = (
    Signal(
        "use_both",
        Strategy.HYBRID,
        _rx(r"\buse both\b|\bboth search\b|\bboth approach(es)?\b|\bcombine both\b"),
        4.0,
        "transcript: 'use both search types' / 'combine both approaches'",
    ),
    Signal(
        "both_sources",
        Strategy.HYBRID,
        _rx(r"\bboth\b.*\b(vector|graph|database|knowledge)\b"),
        3.0,
        "transcript: 'both the vector database and the knowledge graph'",
    ),
)


def default_signals() -> List[Signal]:
    """Return the full, transcript-grounded signal set (fresh list)."""
    return list(_GRAPH_SIGNALS) + list(_VECTOR_SIGNALS) + list(_HYBRID_SIGNALS)


# =============================================================================
# RouteDecision
# =============================================================================


@dataclass
class RouteDecision:
    """The deterministic result of routing a single query.

    Attributes
    ----------
    strategy:
        The chosen :class:`Strategy`.
    confidence:
        A ``0.0..1.0`` score — winning strategy score divided by total score
        across all strategies (``0.0`` when no signal fired / fallback used).
    matched_signals:
        Names of every signal that fired, in deterministic order.
    rationale:
        A short human-readable explanation grounded in the matched signals.
    scores:
        Raw per-strategy weighted score map (for inspection / debugging).
    query:
        The original query string.
    """

    strategy: Strategy
    confidence: float
    matched_signals: List[str] = field(default_factory=list)
    rationale: str = ""
    scores: Dict[Strategy, float] = field(default_factory=dict)
    query: str = ""

    def as_dict(self) -> Dict[str, Any]:
        """Return a plain-dict view (JSON-friendly; enums -> their values)."""
        return {
            "query": self.query,
            "strategy": self.strategy.value,
            "confidence": round(self.confidence, 6),
            "matched_signals": list(self.matched_signals),
            "rationale": self.rationale,
            "scores": {s.value: round(v, 6) for s, v in self.scores.items()},
        }


# =============================================================================
# QueryClassifier
# =============================================================================


class QueryClassifier:
    """Scores a query against the signal sets and picks a strategy.

    Decision procedure (deterministic):

    1. Each matching signal adds ``base_weight * signal_weight_multiplier`` to
       its strategy's score.
    2. If explicit HYBRID signals fire, HYBRID wins outright (the author's
       "combine both only when asked").
    3. Otherwise, if BOTH a GRAPH signal and a VECTOR signal fired and their
       scores are close (within ``hybrid_margin``), the query carries both a
       relationship intent and a fact-lookup intent -> HYBRID.
    4. Otherwise the highest-scoring strategy wins; VECTOR breaks ties as the
       transcript's default ("otherwise just use the vector store tool").
    """

    def __init__(
        self,
        signals: Optional[Sequence[Signal]] = None,
        *,
        weights: Optional[Mapping[str, float]] = None,
        hybrid_margin: float = 0.34,
        default_strategy: Strategy = Strategy.VECTOR,
    ) -> None:
        self._signals: List[Signal] = list(signals) if signals is not None else default_signals()
        self._weights: Dict[str, float] = dict(weights or {})
        self.hybrid_margin = float(hybrid_margin)
        self.default_strategy = Strategy.from_value(default_strategy)

    # ----------------------------------------------------------------- config
    @property
    def signals(self) -> List[Signal]:
        return list(self._signals)

    def signal_names(self) -> List[str]:
        return [s.name for s in self._signals]

    def effective_weight(self, signal: Signal) -> float:
        """Base weight multiplied by any per-signal override in ``weights``."""
        return signal.weight * float(self._weights.get(signal.name, 1.0))

    # ---------------------------------------------------------------- scoring
    def _score(self, query: str) -> Tuple[Dict[Strategy, float], List[str]]:
        scores: Dict[Strategy, float] = {s: 0.0 for s in Strategy}
        matched: List[str] = []
        for signal in self._signals:
            if signal.search(query):
                scores[signal.strategy] += self.effective_weight(signal)
                matched.append(signal.name)
        return scores, matched

    def classify(self, query: str) -> RouteDecision:
        """Classify a single query into a :class:`RouteDecision`."""
        if not isinstance(query, str):
            raise TypeError("query must be a string")
        text = query.strip()
        scores, matched = self._score(text)

        hybrid_score = scores[Strategy.HYBRID]
        graph_score = scores[Strategy.GRAPH]
        vector_score = scores[Strategy.VECTOR]
        total = graph_score + vector_score + hybrid_score

        # --- no signal fired: fall back to default (transcript default VECTOR)
        if total <= 0.0:
            return RouteDecision(
                strategy=self.default_strategy,
                confidence=0.0,
                matched_signals=[],
                rationale=(
                    "No routing signal matched; falling back to default "
                    f"'{self.default_strategy.value}' strategy "
                    "(transcript default: 'otherwise just use the vector store tool')."
                ),
                scores=dict(scores),
                query=query,
            )

        # --- explicit "use both" -> HYBRID wins outright
        if hybrid_score > 0.0:
            chosen = Strategy.HYBRID
            winning = hybrid_score + graph_score + vector_score
            rationale = (
                "Explicit request to combine strategies detected -> HYBRID "
                "(transcript: 'use both search types' / 'combine both approaches')."
            )
            confidence = winning / (total + graph_score + vector_score) if total else 1.0
            # keep confidence a clean ratio of hybrid-driven weight
            confidence = min(1.0, (hybrid_score + min(graph_score, vector_score)) / total)
            return RouteDecision(
                strategy=chosen,
                confidence=round(confidence, 6),
                matched_signals=matched,
                rationale=rationale,
                scores=dict(scores),
                query=query,
            )

        # --- both relationship AND fact-lookup intent present & balanced -> HYBRID
        if graph_score > 0.0 and vector_score > 0.0:
            hi = max(graph_score, vector_score)
            lo = min(graph_score, vector_score)
            if (hi - lo) / hi <= self.hybrid_margin:
                confidence = min(1.0, (hi + lo) / total)
                return RouteDecision(
                    strategy=Strategy.HYBRID,
                    confidence=round(confidence, 6),
                    matched_signals=matched,
                    rationale=(
                        "Both relationship (GRAPH) and fact-lookup (VECTOR) "
                        "intents present and balanced -> HYBRID "
                        "(transcript: a question needing a single-entity lookup "
                        "AND a comparison across entities)."
                    ),
                    scores=dict(scores),
                    query=query,
                )

        # --- single clear winner (VECTOR breaks ties: transcript default)
        if graph_score > vector_score:
            chosen, win = Strategy.GRAPH, graph_score
            why = (
                "Relationship / multi-entity intent dominates -> GRAPH "
                "(transcript: 'the kind of thing that would definitely call "
                "for a query to our knowledge graph')."
            )
        else:
            chosen, win = Strategy.VECTOR, vector_score
            why = (
                "Single-entity / broad semantic fact-lookup intent dominates "
                "-> VECTOR (transcript: 'it just did a simple vector search ... "
                "it doesn't need to do the knowledge graph')."
            )

        confidence = win / total
        return RouteDecision(
            strategy=chosen,
            confidence=round(confidence, 6),
            matched_signals=matched,
            rationale=why,
            scores=dict(scores),
            query=query,
        )


# =============================================================================
# StrategyRouter + pluggable retriever registry
# =============================================================================

Retriever = Callable[[str], Any]


class StrategyRouter:
    """Holds a :class:`QueryClassifier` plus configurable signal weights and
    exposes the public routing + dispatch surface.
    """

    def __init__(
        self,
        classifier: Optional[QueryClassifier] = None,
        *,
        weights: Optional[Mapping[str, float]] = None,
        hybrid_margin: Optional[float] = None,
        default_strategy: Strategy = Strategy.VECTOR,
    ) -> None:
        if classifier is None:
            classifier = QueryClassifier(
                weights=weights,
                hybrid_margin=hybrid_margin if hybrid_margin is not None else 0.34,
                default_strategy=default_strategy,
            )
        elif weights is not None:
            # merge extra weights onto an existing classifier
            merged = dict(classifier._weights)
            merged.update(weights)
            classifier._weights = merged
        self.classifier = classifier
        self._retrievers: Dict[Strategy, Retriever] = {}

    # --------------------------------------------------------------- routing
    def route(self, query: str) -> RouteDecision:
        """Classify a single query and return its :class:`RouteDecision`."""
        return self.classifier.classify(query)

    def route_batch(self, queries: Sequence[str]) -> List[RouteDecision]:
        """Route a sequence of queries, preserving order."""
        return [self.classifier.classify(q) for q in queries]

    # ------------------------------------------------------ retriever registry
    def register_retriever(self, strategy: "Strategy | str", retriever: Retriever) -> None:
        """Register a callable retriever for a strategy."""
        strat = Strategy.from_value(strategy)
        if not callable(retriever):
            raise TypeError("retriever must be callable")
        self._retrievers[strat] = retriever

    def unregister_retriever(self, strategy: "Strategy | str") -> None:
        self._retrievers.pop(Strategy.from_value(strategy), None)

    def registered_strategies(self) -> List[Strategy]:
        """Strategies that currently have a retriever registered."""
        return [s for s in Strategy if s in self._retrievers]

    # --------------------------------------------------------------- dispatch
    def dispatch(
        self,
        query: str,
        *,
        retrievers: Optional[Mapping["Strategy | str", Retriever]] = None,
    ) -> Dict[str, Any]:
        """Route ``query`` and call the retriever for the chosen strategy.

        Retrievers may be supplied inline via ``retrievers`` (takes precedence)
        or pre-registered via :meth:`register_retriever`. Pure + deterministic:
        the injected retriever is simply invoked with the query string.

        Returns a dict with the decision plus the retriever's ``result``.
        """
        decision = self.route(query)
        table: Dict[Strategy, Retriever] = dict(self._retrievers)
        if retrievers:
            for key, fn in retrievers.items():
                table[Strategy.from_value(key)] = fn

        retriever = table.get(decision.strategy)
        if retriever is None:
            raise KeyError(
                f"no retriever registered/provided for strategy "
                f"'{decision.strategy.value}'"
            )
        result = retriever(query)
        return {
            "query": query,
            "strategy": decision.strategy.value,
            "confidence": decision.confidence,
            "matched_signals": list(decision.matched_signals),
            "rationale": decision.rationale,
            "result": result,
        }


def create_router(
    *,
    weights: Optional[Mapping[str, float]] = None,
    hybrid_margin: float = 0.34,
) -> StrategyRouter:
    """Convenience factory for a default, transcript-grounded router."""
    return StrategyRouter(weights=weights, hybrid_margin=hybrid_margin)
