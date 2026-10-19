"""hybrid_kg_retrieval.core — pure-stdlib agentic hybrid retrieval engine.

Grounded in ColeMedin's "Introducing RAG 2.0: Agentic RAG + Knowledge Graphs".

The transcript's core idea: give an AI agent TWO retrieval strategies over its
knowledge and let the agent decide, per query, which to use and then fuse the
results:

  (A) VECTOR / SEMANTIC RAG — chunk documents, retrieve by semantic similarity;
      good for broad "find me relevant passages" lookups.
  (B) KNOWLEDGE-GRAPH retrieval — entities + typed relationships; good for
      multi-hop / relational questions ("how does X relate to Y", "what depends
      on Z").

RAG 2.0 == an AGENTIC retriever that routes each query to vector, graph, or
BOTH and fuses the outputs with provenance.

This module implements the HYBRID architecture + routing + fusion determinist.
locally. No network, no real embeddings, no LLM calls. The "vector" stand-in is
a deterministic TF cosine over bag-of-words implemented with collections.Counter
and math; the graph is a real in-memory typed graph.
"""
from __future__ import annotations

import math
import re
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

__all__ = [
    "tokenize",
    "VectorIndex",
    "KnowledgeGraph",
    "HybridRetriever",
    "RetrievalResult",
    "RELATIONAL_CUES",
]

_WORD_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> List[str]:
    """Lowercase + split a string into alphanumeric word tokens (stdlib only)."""
    return _WORD_RE.findall((text or "").lower())


# ── Vector / semantic RAG stand-in ──────────────────────────────────────────
class VectorIndex:
    """Deterministic local 'vector' index.

    Stands in for an embedding model: each document is a TF bag-of-words vector,
    and relevance is the cosine similarity between query and document TF vectors.
    This is deterministic, offline, and needs no external model.
    """

    def __init__(self) -> None:
        self._docs: Dict[str, str] = {}
        self._vecs: Dict[str, Counter] = {}

    def add_document(self, doc_id: str, text: str) -> None:
        if not doc_id:
            raise ValueError("doc_id must be a non-empty string")
        self._docs[doc_id] = text
        self._vecs[doc_id] = Counter(tokenize(text))

    @property
    def documents(self) -> Dict[str, str]:
        return dict(self._docs)

    def __len__(self) -> int:
        return len(self._docs)

    @staticmethod
    def _cosine(a: Counter, b: Counter) -> float:
        if not a or not b:
            return 0.0
        # dot product over shared keys
        shared = set(a) & set(b)
        dot = sum(a[k] * b[k] for k in shared)
        if dot == 0:
            return 0.0
        na = math.sqrt(sum(v * v for v in a.values()))
        nb = math.sqrt(sum(v * v for v in b.values()))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def search(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """Return up to top_k (doc_id, score) pairs ranked by cosine, desc."""
        qvec = Counter(tokenize(query))
        scored = [
            (doc_id, self._cosine(qvec, dvec))
            for doc_id, dvec in self._vecs.items()
        ]
        scored = [(d, s) for d, s in scored if s > 0.0]
        # deterministic tie-break on doc_id
        scored.sort(key=lambda t: (-t[1], t[0]))
        return scored[: max(0, top_k)]


# ── Knowledge graph ─────────────────────────────────────────────────────────
@dataclass
class _Entity:
    id: str
    type: str
    props: Dict[str, Any] = field(default_factory=dict)


class KnowledgeGraph:
    """A real in-memory typed directed graph of entities + typed relations."""

    def __init__(self) -> None:
        self._entities: Dict[str, _Entity] = {}
        # adjacency: src -> list of (rel, dst)
        self._out: Dict[str, List[Tuple[str, str]]] = {}
        # reverse adjacency: dst -> list of (rel, src)
        self._in: Dict[str, List[Tuple[str, str]]] = {}

    def add_entity(self, id: str, type: str = "", props: Optional[Dict[str, Any]] = None) -> None:
        if not id:
            raise ValueError("entity id must be a non-empty string")
        self._entities[id] = _Entity(id=id, type=type, props=dict(props or {}))
        self._out.setdefault(id, [])
        self._in.setdefault(id, [])

    def add_relation(self, src: str, rel: str, dst: str) -> None:
        # auto-create endpoints so callers can build graphs loosely
        if src not in self._entities:
            self.add_entity(src)
        if dst not in self._entities:
            self.add_entity(dst)
        if (rel, dst) not in self._out[src]:
            self._out[src].append((rel, dst))
        if (rel, src) not in self._in[dst]:
            self._in[dst].append((rel, src))

    def has_entity(self, id: str) -> bool:
        return id in self._entities

    def get_entity(self, id: str) -> Optional[_Entity]:
        return self._entities.get(id)

    @property
    def entities(self) -> Dict[str, _Entity]:
        return dict(self._entities)

    def neighbors(self, id: str, rel: Optional[str] = None) -> List[str]:
        """Direct outgoing neighbors of ``id``, optionally filtered by rel."""
        edges = self._out.get(id, [])
        return [dst for r, dst in edges if rel is None or r == rel]

    def query_relations(self, entity: str) -> List[Tuple[str, str, str]]:
        """All (src, rel, dst) triples touching ``entity`` (out + in)."""
        out = [(entity, r, dst) for r, dst in self._out.get(entity, [])]
        inc = [(src, r, entity) for r, src in self._in.get(entity, [])]
        return out + inc

    def multi_hop(self, start: str, max_hops: int = 2, rel: Optional[str] = None) -> Dict[str, int]:
        """BFS up to max_hops. Returns {entity_id: hop_distance} excluding start."""
        if start not in self._entities:
            return {}
        dist: Dict[str, int] = {start: 0}
        q: deque = deque([start])
        while q:
            cur = q.popleft()
            if dist[cur] >= max_hops:
                continue
            for r, dst in self._out.get(cur, []):
                if rel is not None and r != rel:
                    continue
                if dst not in dist:
                    dist[dst] = dist[cur] + 1
                    q.append(dst)
        dist.pop(start, None)
        return dist

    def find_path(self, start: str, end: str, max_hops: int = 5) -> Optional[List[str]]:
        """Shortest directed path (list of entity ids) from start to end, or None."""
        if start not in self._entities or end not in self._entities:
            return None
        if start == end:
            return [start]
        prev: Dict[str, str] = {start: start}
        q: deque = deque([(start, 0)])
        while q:
            cur, hops = q.popleft()
            if hops >= max_hops:
                continue
            for _r, dst in self._out.get(cur, []):
                if dst not in prev:
                    prev[dst] = cur
                    if dst == end:
                        # reconstruct
                        path = [end]
                        while path[-1] != start:
                            path.append(prev[path[-1]])
                        path.reverse()
                        return path
                    q.append((dst, hops + 1))
        return None


# ── Router + hybrid fusion ──────────────────────────────────────────────────
RELATIONAL_CUES: Tuple[str, ...] = (
    "related to",
    "relate to",
    "relates to",
    "how does",
    "how do",
    "depends on",
    "depend on",
    "connected to",
    "connected",
    "connection between",
    "relationship between",
    "linked to",
    "path from",
    "path between",
    "what depends",
    "who depends",
    "impact of",
    "affects",
    "between",
)


@dataclass
class RetrievalResult:
    """A single fused retrieval hit with provenance back to its strategy."""

    ref: str                      # doc_id (vector) or entity_id (graph)
    source: str                   # 'vector' | 'graph'
    score: float                  # fused score
    detail: Dict[str, Any] = field(default_factory=dict)


class HybridRetriever:
    """Agentic RAG 2.0 retriever: route per-query to vector / graph / both, fuse.

    The router classifies the query into one of {'vector', 'graph', 'hybrid'}
    using deterministic heuristics grounded in the transcript: relational cue
    words route to the graph, plain lookups to the vector index, and queries
    that both mention known graph entities AND look like broad lookups route to
    hybrid. Results are fused with Reciprocal Rank Fusion (RRF).
    """

    RRF_K = 60  # standard RRF constant

    def __init__(
        self,
        vector_index: Optional[VectorIndex] = None,
        graph: Optional[KnowledgeGraph] = None,
    ) -> None:
        self.vector_index = vector_index or VectorIndex()
        self.graph = graph or KnowledgeGraph()

    # -- routing -------------------------------------------------------------
    def _mentions_entity(self, query: str) -> List[str]:
        """Return known graph entity ids whose id/tokens appear in the query."""
        qtokens = set(tokenize(query))
        hits: List[str] = []
        for eid in self.graph.entities:
            etokens = set(tokenize(eid))
            if etokens and etokens <= qtokens:
                hits.append(eid)
        return hits

    def classify(self, query: str) -> str:
        """Classify a query into 'vector', 'graph', or 'hybrid'."""
        q = (query or "").lower()
        relational = any(cue in q for cue in RELATIONAL_CUES)
        entity_hits = self._mentions_entity(query)
        has_entities = len(entity_hits) > 0

        if relational:
            # Relational intent. If it also reads like a broad lookup
            # (mentions multiple known entities is still graph), keep graph —
            # unless there are NO known entities at all, in which case we still
            # need semantic search to find a starting point: hybrid.
            if not has_entities:
                return "hybrid"
            return "graph"

        # Non-relational. Plain lookup -> vector. But if it names a known
        # entity AND is a reasonably broad query, blend both for recall.
        if has_entities and len(tokenize(query)) >= 4:
            return "hybrid"
        return "vector"

    # -- strategies ----------------------------------------------------------
    def _vector_hits(self, query: str, top_k: int) -> List[RetrievalResult]:
        out: List[RetrievalResult] = []
        for rank, (doc_id, score) in enumerate(self.vector_index.search(query, top_k)):
            out.append(
                RetrievalResult(
                    ref=doc_id,
                    source="vector",
                    score=score,
                    detail={"rank": rank, "similarity": score},
                )
            )
        return out

    def _graph_hits(self, query: str, top_k: int) -> List[RetrievalResult]:
        seeds = self._mentions_entity(query)
        out: List[RetrievalResult] = []
        seen: Set[str] = set()
        rank = 0
        for seed in seeds:
            dist = self.graph.multi_hop(seed, max_hops=2)
            # closer neighbors rank higher
            for eid, hops in sorted(dist.items(), key=lambda t: (t[1], t[0])):
                if eid in seen:
                    continue
                seen.add(eid)
                out.append(
                    RetrievalResult(
                        ref=eid,
                        source="graph",
                        score=1.0 / (1 + hops),
                        detail={"rank": rank, "seed": seed, "hops": hops},
                    )
                )
                rank += 1
                if rank >= top_k:
                    return out
        return out

    # -- fusion --------------------------------------------------------------
    def _rrf(self, result_lists: Iterable[List[RetrievalResult]], top_k: int) -> List[RetrievalResult]:
        """Reciprocal Rank Fusion over ranked result lists, keyed by (source,ref)."""
        fused: Dict[Tuple[str, str], RetrievalResult] = {}
        for results in result_lists:
            for rank, r in enumerate(results):
                key = (r.source, r.ref)
                contrib = 1.0 / (self.RRF_K + rank + 1)
                if key in fused:
                    fused[key].score += contrib
                else:
                    fused[key] = RetrievalResult(
                        ref=r.ref,
                        source=r.source,
                        score=contrib,
                        detail=dict(r.detail),
                    )
        merged = list(fused.values())
        merged.sort(key=lambda r: (-r.score, r.source, r.ref))
        return merged[: max(0, top_k)]

    def retrieve(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        """Route, run the chosen strategy/ies, fuse, and return a ranked bundle."""
        strategy = self.classify(query)
        if strategy == "vector":
            results = self._vector_hits(query, top_k)
        elif strategy == "graph":
            results = self._graph_hits(query, top_k)
        else:  # hybrid
            vhits = self._vector_hits(query, top_k)
            ghits = self._graph_hits(query, top_k)
            results = self._rrf([vhits, ghits], top_k)
        return {
            "query": query,
            "strategy": strategy,
            "results": results,
        }
