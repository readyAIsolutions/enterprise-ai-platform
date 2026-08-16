"""AgenticRag — query planning, multi-hop knowledge-graph traversal & reranking.

Grounded in the real pulled transcript ``ColeMedin/p0FERNkpyHE.md`` —
"Introducing RAG 2.0: Agentic RAG + Knowledge Graphs (FREE Template)".
Core ideas taken straight from the talk:

* **Vanilla / naive RAG is inflexible.** A fixed pipeline embeds the user query,
  retrieves top-K chunks from a vector store and force-feeds that context to the
  LLM. The agent cannot refine its search, go deeper, or choose a different way
  to explore the knowledge base.

* **Agentic RAG lets the agent reason about *how* it explores knowledge.** The
  agent decides between a vector-store lookup (good for a *single entity / fact*
  like "Google AI initiatives") and a knowledge-graph traversal (good for a
  *relational* question about two entities — "how are OpenAI and Microsoft
  related?"), or combines both.

* **Knowledge graphs represent entities + relationships.** Nodes are entities
  (companies), edges are typed relations. Queries hop across edges for multi-hop
  reasoning: *Amazon --invested_in--> Anthropic --runs_on--> AWS* or
  *Microsoft --partnered_with--> OpenAI --hosted_on--> Azure*.

* **Reranking retrieval candidates** is essential so the agent can hone in on
  the most relevant chunks after an initial retrieval step.

This module implements that agentic loop in pure, network-free Python: it
operates entirely on in-memory documents (vector store) and an in-memory
graph (nodes + edges). There are no embedding models, databases, or LLM calls —
retrieval is lexical-overlap scoring, ranking is a composable heuristic, and the
knowledge graph is a plain adjacency structure. That keeps every piece
deterministic and unit-testable.

Public surface: ``KnowledgeGraph``, ``Chunk``, ``VectorStore``, ``AgenticRag``,
``builtin_bigtech_graph``, ``builtin_bigtech_store``, ``make_agentic_rag``.
"""

from __future__ import annotations

import re
from collections import deque
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Small text helpers
# ---------------------------------------------------------------------------


def tokenize(text: str) -> List[str]:
    """Lowercase alphanumeric token stream used by lexical scoring."""
    return re.findall(r"[a-z0-9]+", text.lower())


def overlap(query: str, doc: str) -> float:
    """Fraction of the query's unique tokens that appear in the doc (0..1)."""
    qt = set(tokenize(query))
    if not qt:
        return 0.0
    dt = set(tokenize(doc))
    return len(qt & dt) / len(qt)


# ---------------------------------------------------------------------------
# Knowledge graph
# ---------------------------------------------------------------------------


class KnowledgeGraph:
    """A minimal directed knowledge graph (entities as nodes, typed edges)."""

    def __init__(self) -> None:
        self._nodes: Dict[str, Dict[str, Any]] = {}
        self._edges: List[Dict[str, Any]] = []

    # -- mutation -----------------------------------------------------------
    def add_node(self, name: str, attrs: Optional[Dict[str, Any]] = None) -> str:
        name = name.strip()
        if not name:
            raise ValueError("node name cannot be empty")
        if name not in self._nodes:
            self._nodes[name] = dict(attrs or {})
        elif attrs:
            self._nodes[name].update(attrs)
        return name

    def add_edge(self, source: str, target: str, rel: str,
                 attrs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Add a typed, directed edge; auto-creates missing endpoint nodes."""
        source = self.add_node(source)
        target = self.add_node(target)
        edge = {
            "source": source,
            "target": target,
            "relation": rel,
            "attrs": dict(attrs or {}),
        }
        self._edges.append(edge)
        return edge

    # -- read ---------------------------------------------------------------
    @property
    def node_names(self) -> List[str]:
        return list(self._nodes.keys())

    @property
    def num_nodes(self) -> int:
        return len(self._nodes)

    @property
    def num_edges(self) -> int:
        return len(self._edges)

    def node(self, name: str) -> Optional[Dict[str, Any]]:
        return self._nodes.get(name)

    def neighbors(self, node: str) -> List[str]:
        """Outgoing neighbours of a node (single hop)."""
        return [e["target"] for e in self._edges if e["source"] == node]

    def edges(self, source: Optional[str] = None,
              target: Optional[str] = None) -> List[Dict[str, Any]]:
        result = self._edges
        if source is not None:
            result = [e for e in result if e["source"] == source]
        if target is not None:
            result = [e for e in result if e["target"] == target]
        return result

    def find_entities(self, text: str) -> List[str]:
        """Detect which known nodes are mentioned in free text (case-insensitive)."""
        low = text.lower()
        return [n for n in self._nodes if n.lower() in low]

    def shortest_path(self, start: str, goal: str,
                      max_hops: int = 5) -> List[Dict[str, Any]]:
        """Breadth-first multi-hop path from ``start`` to ``goal``.

        Returns a list of edge dicts describing the shortest directed path, or
        an empty list when no path exists within ``max_hops`` hops.
        """
        if start not in self._nodes or goal not in self._nodes:
            return []
        visited = {start}
        # queue holds: (node, path_of_edges)
        queue: deque[Tuple[str, List[Dict[str, Any]]]] = deque([(start, [])])
        while queue:
            node, path = queue.popleft()
            if len(path) >= max_hops:
                continue
            for edge in self._edges:
                if edge["source"] != node:
                    continue
                nxt = edge["target"]
                new_path = path + [edge]
                if nxt == goal:
                    return new_path
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append((nxt, new_path))
        return []

    def connected_edges(self, entities: Sequence[str],
                        max_hops: int = 3) -> List[Dict[str, Any]]:
        """Collect all edges reachable within ``max_hops`` across the entities."""
        collected: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        for entity in entities:
            if entity not in self._nodes:
                continue
            seen = {entity}
            frontier: deque[Tuple[str, int]] = deque([(entity, 0)])
            while frontier:
                node, depth = frontier.popleft()
                if depth >= max_hops:
                    continue
                for edge in self._edges:
                    if edge["source"] != node:
                        continue
                    key = (edge["source"], edge["relation"], edge["target"])
                    collected[key] = edge
                    if edge["target"] not in seen:
                        seen.add(edge["target"])
                        frontier.append((edge["target"], depth + 1))
        return list(collected.values())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [{"name": n, "attrs": a}
                      for n, a in self._nodes.items()],
            "edges": [{"source": e["source"], "relation": e["relation"],
                       "target": e["target"], "attrs": e["attrs"]}
                      for e in self._edges],
            "num_nodes": self.num_nodes,
            "num_edges": self.num_edges,
        }


# ---------------------------------------------------------------------------
# In-memory vector store (lexical stand-in for embeddings/PGVector)
# ---------------------------------------------------------------------------


class Chunk:
    """A single retrieved document chunk (like a row in the vector store)."""

    def __init__(self, chunk_id: str, text: str,
                 source: str = "", attrs: Optional[Dict[str, Any]] = None) -> None:
        self.id = chunk_id
        self.text = text
        self.source = source
        self.attrs = dict(attrs or {})

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "text": self.text, "source": self.source,
                "attrs": self.attrs}


class VectorStore:
    """In-memory collection of chunks with lexical-overlap retrieval."""

    def __init__(self) -> None:
        self._chunks: List[Chunk] = []

    def add(self, chunk: Chunk) -> Chunk:
        self._chunks.append(chunk)
        return chunk

    @property
    def chunks(self) -> List[Chunk]:
        return list(self._chunks)

    @property
    def num_chunks(self) -> int:
        return len(self._chunks)

    def search(self, query: str, k: int = 3) -> List[Chunk]:
        """Return up to ``k`` candidate chunks ranked by lexical overlap."""
        scored = sorted(
            self._chunks,
            key=lambda c: overlap(query, c.text),
            reverse=True,
        )
        return [c for c in scored if overlap(query, c.text) > 0][:k]


# ---------------------------------------------------------------------------
# Reranking
# ---------------------------------------------------------------------------


def rerank(candidates: Iterable[Chunk], query: str,
           entities: Optional[Sequence[str]] = None,
           graph: Optional[KnowledgeGraph] = None,
           top_k: Optional[int] = None) -> List[Dict[str, Any]]:
    """Rerank retrieval candidates by a composable relevance heuristic.

    Composite score (0..1+) blends:
      * lexical overlap between the chunk and the query (vanilla retrieval
        signal, from the "vector store" branch), and
      * entity coverage: how many of the detected entities appear in the chunk
        (the signal that makes relational chunks win for multi-hop questions).

    A knowledge graph boost term is added when the chunk mentions more than one
    of the query's entities — mirroring the transcript's point that relational
    questions ("two companies in the same question") should surface graph-ish
    evidence that connects the entities.

    Returns reranked chunk dicts (each with a ``score``) in descending order.
    """
    ents = list(entities or [])
    ent_low = {e.lower() for e in ents}
    scored: List[Tuple[float, Chunk]] = []
    for c in candidates:
        lex = overlap(query, c.text)
        covered = ent_low & set(tokenize(c.text)) if ent_low else set()
        coverage = len(covered) / len(ent_low) if ent_low else 0.0
        score = 0.6 * lex + 0.4 * coverage
        if len(covered) >= 2 and graph is not None:
            score += 0.25  # relational-evidence boost
        scored.append((score, c))
    scored.sort(key=lambda t: t[0], reverse=True)
    ranked = [
        {"chunk": c.to_dict(), "lexical_overlap": round(overlap(query, c.text), 4),
         "entity_coverage": round((len(ent_low & set(tokenize(c.text))) / len(ent_low))
                                  if ent_low else 0.0, 4),
         "score": round(s, 4)}
        for s, c in scored
    ]
    if top_k is not None:
        ranked = ranked[:top_k]
    return ranked


# ---------------------------------------------------------------------------
# Agentic RAG engine
# ---------------------------------------------------------------------------

# Strategy labels used by the planner (mirror the transcript's tool choices).
STRATEGY_VECTOR = "vector_store"
STRATEGY_GRAPH = "knowledge_graph"
STRATEGY_COMBINED = "combined"

# Explicit user asks to use *both* search strategies (transcript demo cue).
_COMBINE_CUES = (
    "use both", "combine", "both search", "both approaches",
    "use the knowledge graph and the vector", "use both search types",
)


def _query_type(entities: Sequence[str], text: str) -> str:
    """Choose the retrieval strategy for a query based on its detected shape.

    Entity count is the primary signal: a single entity (or none) is a fact
    lookup that goes to the vector store, while two or more entities make the
    question relational and drive a knowledge-graph traversal. The combined
    strategy is only chosen when the user *explicitly* asks to use both search
    types (exactly the demo behaviour in the transcript).
    """
    low = text.lower()
    if len(entities) >= 2:
        if any(cue in low for cue in _COMBINE_CUES):
            return STRATEGY_COMBINED
        return STRATEGY_GRAPH
    if any(cue in low for cue in _COMBINE_CUES):
        return STRATEGY_COMBINED
    return STRATEGY_VECTOR


class AgenticRag:
    """Agentic RAG + knowledge-graph retrieval engine (pure, network-free).

    Wires together query decomposition (planning), multi-hop graph traversal,
    vector-style retrieval and reranking into a single ``answer`` pipeline.
    """

    def __init__(self, graph: Optional[KnowledgeGraph] = None,
                 store: Optional[VectorStore] = None,
                 max_hops: int = 3,
                 top_k: int = 3) -> None:
        self.graph = graph if graph is not None else KnowledgeGraph()
        self.store = store if store is not None else VectorStore()
        self.max_hops = max_hops
        self.top_k = top_k

    # -- planning -----------------------------------------------------------
    def decompose_query(self, query: str) -> Dict[str, Any]:
        """Decompose a user query into an agentic retrieval plan.

        Returns a plan with the detected entities, the chosen strategy and the
        ordered sub-steps the agent would execute — the agentic-RAG "reason
        about how to explore the knowledge" behaviour from the transcript.
        """
        entities = self.graph.find_entities(query)
        strategy = _query_type(entities, query)
        sub_steps: List[str] = []
        if strategy == STRATEGY_VECTOR:
            sub_steps = [
                "1. Detect that this is a single-entity / fact lookup.",
                "2. Embed-and-match against the vector store (lexical overlap here).",
                "3. Retrieve the top-K candidate chunks.",
                "4. Rerank candidates and assemble the factual answer.",
            ]
        elif strategy == STRATEGY_GRAPH:
            sub_steps = [
                "1. Detect multiple entities -> relational question.",
                "2. Locate the entities as graph nodes.",
                f"3. Traverse the knowledge graph (max {self.max_hops} hops) "
                "linking the entities.",
                "4. Collect the connecting relationship edges as evidence.",
            ]
        else:  # combined
            sub_steps = [
                "1. Detect entities AND relational cues -> combine both tools.",
                "2. Retrieve per-entity chunks from the vector store.",
                "3. Traverse the knowledge graph between the entities.",
                "4. Merge graph edges with reranked chunk evidence.",
            ]
        return {
            "query": query,
            "entities": entities,
            "strategy": strategy,
            "sub_steps": sub_steps,
        }

    # -- multi-hop graph traversal ------------------------------------------
    def traverse(self, start: str, goal: Optional[str] = None,
                 max_hops: Optional[int] = None) -> List[Dict[str, Any]]:
        """Multi-hop traversal between two entities (or around a single one).

        With a ``goal``, returns the shortest directed path of edges; without
        one, returns the sub-graph reachable around ``start`` — useful for the
        relational "how do X and Y relate" case.
        """
        hops = max_hops or self.max_hops
        if goal is not None:
            path = self.graph.shortest_path(start, goal, max_hops=hops)
            return [{"source": e["source"], "relation": e["relation"],
                     "target": e["target"]} for e in path]
        return [
            {"source": e["source"], "relation": e["relation"],
             "target": e["target"]}
            for e in self.graph.connected_edges([start], max_hops=hops)
        ]

    # -- retrieval + rerank --------------------------------------------------
    def retrieve(self, query: str, k: Optional[int] = None) -> List[Dict[str, Any]]:
        """Vector-store style retrieval of candidate chunks (as dicts)."""
        return [c.to_dict() for c in
                self.store.search(query, k=k or self.top_k)]

    def rerank(self, query: str, entities: Optional[Sequence[str]] = None,
               top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        """Rerank all store chunks against ``query`` with graph-aware scoring."""
        ents = list(entities) if entities is not None else self.graph.find_entities(query)
        return rerank(self.store.chunks, query, entities=ents,
                      graph=self.graph, top_k=top_k or self.top_k)

    # -- full agentic answer --------------------------------------------------
    def answer(self, query: str, top_k: Optional[int] = None) -> Dict[str, Any]:
        """Run the full agentic RAG loop and assemble an answer plan.

        Returns a dict with the retrieval plan, retrieved chunk evidence,
        any knowledge-graph path used, and a synthesized plain-text answer.
        """
        plan = self.decompose_query(query)
        strategy = plan["strategy"]
        entities = plan["entities"]
        k = top_k or self.top_k

        evidence: List[Dict[str, Any]] = []
        graph_path: List[Dict[str, Any]] = []
        graph_edges: List[Dict[str, Any]] = []

        if strategy in (STRATEGY_VECTOR, STRATEGY_COMBINED):
            evidence = self.rerank(query, entities=entities, top_k=k)

        if strategy in (STRATEGY_GRAPH, STRATEGY_COMBINED) and len(entities) >= 2:
            graph_path = self.traverse(entities[0], entities[1])
            graph_edges = self.graph.connected_edges(entities, max_hops=self.max_hops)

        answer_text = self._synthesize(query, plan, evidence, graph_path)
        return {
            "query": query,
            "plan": plan,
            "evidence": evidence,
            "graph_path": graph_path,
            "graph_edges": graph_edges,
            "answer": answer_text,
        }

    def _synthesize(self, query: str, plan: Dict[str, Any],
                    evidence: Sequence[Dict[str, Any]],
                    graph_path: Sequence[Dict[str, Any]]) -> str:
        """Assemble a deterministic answer from the collected evidence."""
        ent_list = plan["entities"]
        strategy = plan["strategy"]

        if strategy == STRATEGY_GRAPH and graph_path:
            chain = " -> ".join(
                f"{e['source']} [{e['relation']}] {e['target']}" for e in graph_path
            )
            return (
                f"Relational answer for \"{query}\": the knowledge graph links "
                f"{ent_list[0]} to {ent_list[1]} via the path: {chain}."
            )

        if strategy == STRATEGY_COMBINED:
            bits = []
            if graph_path:
                chain = " -> ".join(
                    f"{e['source']} [{e['relation']}] {e['target']}" for e in graph_path
                )
                bits.append(f"graph edge chain {chain}")
            if evidence:
                top = evidence[0]["chunk"]["text"]
                bits.append(f"best chunk: \"{top}\"")
            joined = "; " .join(bits) if bits else "no evidence found"
            return f"Combined answer for \"{query}\": {joined}."

        best = evidence[0]["chunk"]["text"] if evidence else "no matching chunk found"
        return f"Factual answer for \"{query}\": {best}"


# ---------------------------------------------------------------------------
# Realistic fixtures grounded in the transcript's Big-Tech demo
# ---------------------------------------------------------------------------

# The transcript demo is a knowledge base of AI initiatives for big tech
# companies, stored both in a vector store and in a knowledge graph. The
# relationships below are exactly the ones shown on screen in the talk:
#   - Amazon has invested into Anthropic; Anthropic infra runs on AWS.
#   - Microsoft and OpenAI are partnered; OpenAI solely uses Azure to host.
def builtin_bigtech_graph() -> KnowledgeGraph:
    g = KnowledgeGraph()
    g.add_edge("Amazon", "Anthropic", "invested_in",
               {"detail": "Amazon has invested into Anthropic"})
    g.add_edge("Anthropic", "AWS", "runs_on",
               {"detail": "Anthropic infrastructure runs on AWS"})
    g.add_edge("Microsoft", "OpenAI", "partnered_with",
               {"detail": "Microsoft and OpenAI are partnered together"})
    g.add_edge("OpenAI", "Azure", "hosted_on",
               {"detail": "OpenAI solely uses Azure for hosting OpenAI models"})
    g.add_edge("Google", "DeepMind", "owns",
               {"detail": "Google owns DeepMind for advanced AI research"})
    return g


def builtin_bigtech_store() -> VectorStore:
    store = VectorStore()
    store.add(Chunk("c1",
                    "OpenAI and Microsoft are partnered; OpenAI solely uses "
                    "Azure for hosting OpenAI models.",
                    source="bigtech/ai-initiatives"))
    store.add(Chunk("c2",
                    "Amazon has invested into Anthropic and all of the "
                    "Anthropic infrastructure runs on AWS.",
                    source="bigtech/ai-initiatives"))
    store.add(Chunk("c3",
                    "Google is pushing Gemini and DeepMind for its AI "
                    "initiatives across search and cloud.",
                    source="bigtech/ai-initiatives"))
    store.add(Chunk("c4",
                    "Microsoft's AI initiatives center on Azure OpenAI "
                    "services and Copilot across productivity apps.",
                    source="bigtech/ai-initiatives"))
    return store


def make_agentic_rag() -> AgenticRag:
    """Factory for a fresh engine wired to the built-in Big-Tech demo data."""
    return AgenticRag(graph=builtin_bigtech_graph(),
                      store=builtin_bigtech_store())


__all__ = [
    "KnowledgeGraph", "Chunk", "VectorStore", "AgenticRag", "rerank",
    "tokenize", "overlap", "STRATEGY_VECTOR", "STRATEGY_GRAPH",
    "STRATEGY_COMBINED", "builtin_bigtech_graph", "builtin_bigtech_store",
    "make_agentic_rag",
]
