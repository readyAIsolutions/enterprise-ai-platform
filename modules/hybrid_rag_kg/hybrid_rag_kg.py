"""hybrid_rag_kg — Agentic RAG + Knowledge Graph Hybrid Retrieval Module.

Grounded in ColeMedin's "Introducing RAG 2.0: Agentic RAG + Knowledge Graphs"
(https://www.youtube.com/watch?v=p0FERNkpyHE).

Core thesis from transcript:
- Combine AGENTIC RAG (vector/semantic search where the AGENT decides which tool
  to call and can do multiple searches) with KNOWLEDGE GRAPHS (entities +
  relationships, temporal/multi-hop facts) into one hybrid retrieval system.
- The agent chooses between vector search (semantic similarity over chunks) and
  graph search (entity relationships, "how are X and Y related", temporal queries)
  depending on the question.
- Vector DB: good for broad lookups like "what are AI initiatives for Google"
- Knowledge Graph: good for relational queries like "how are Amazon and Anthropic
  related", multi-hop paths, temporal facts
- Agent can also combine both approaches when needed
"""

from __future__ import annotations

import math
import re
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


__all__ = [
    "tokenize",
    "VectorStore",
    "KnowledgeGraph",
    "AgenticRouter",
    "RetrievalResult",
    "RELATIONAL_CUES",
]


_WORD_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> List[str]:
    """Lowercase + split a string into alphanumeric word tokens (stdlib only)."""
    return _WORD_RE.findall((text or "").lower())


# ── Vector / semantic RAG stand-in ──────────────────────────────────────────
class VectorStore:
    """Deterministic local 'vector' store for semantic chunk retrieval.

    Stands in for an embedding model: each chunk is a TF bag-of-words vector,
    and relevance is the cosine similarity between query and chunk TF vectors.
    This is deterministic, offline, and needs no external model or numpy.
    """

    def __init__(self) -> None:
        self._chunks: Dict[str, str] = {}          # chunk_id -> text
        self._vecs: Dict[str, Counter] = {}        # chunk_id -> TF vector
        self._metadata: Dict[str, Dict[str, Any]] = {}  # chunk_id -> metadata

    def add_chunk(self, chunk_id: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Ingest a text chunk into the vector store."""
        if not chunk_id:
            raise ValueError("chunk_id must be a non-empty string")
        self._chunks[chunk_id] = text
        self._vecs[chunk_id] = Counter(tokenize(text))
        self._metadata[chunk_id] = dict(metadata or {})

    def add_document(self, doc_id: str, text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> List[str]:
        """Split a document into overlapping chunks and add them. Returns chunk IDs."""
        if not doc_id:
            raise ValueError("doc_id must be a non-empty string")
        tokens = text.split()
        chunk_ids: List[str] = []
        for i in range(0, len(tokens), chunk_size - chunk_overlap):
            chunk_tokens = tokens[i : i + chunk_size]
            if not chunk_tokens:
                break
            chunk_text = " ".join(chunk_tokens)
            chunk_id = f"{doc_id}#chunk{len(chunk_ids)}"
            self.add_chunk(chunk_id, chunk_text, {"doc_id": doc_id, "chunk_index": len(chunk_ids)})
            chunk_ids.append(chunk_id)
        return chunk_ids

    @property
    def chunks(self) -> Dict[str, str]:
        return dict(self._chunks)

    def __len__(self) -> int:
        return len(self._chunks)

    @staticmethod
    def _cosine(a: Counter, b: Counter) -> float:
        if not a or not b:
            return 0.0
        shared = set(a) & set(b)
        dot = sum(a[k] * b[k] for k in shared)
        if dot == 0:
            return 0.0
        na = math.sqrt(sum(v * v for v in a.values()))
        nb = math.sqrt(sum(v * v for v in b.values()))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def search(self, query: str, top_k: int = 5) -> List[Tuple[str, float, Dict[str, Any]]]:
        """Return up to top_k (chunk_id, score, metadata) ranked by cosine, desc."""
        qvec = Counter(tokenize(query))
        scored = [
            (chunk_id, self._cosine(qvec, dvec), self._metadata.get(chunk_id, {}))
            for chunk_id, dvec in self._vecs.items()
        ]
        scored = [(c, s, m) for c, s, m in scored if s > 0.0]
        scored.sort(key=lambda t: (-t[1], t[0]))
        return scored[: max(0, top_k)]


# ── Knowledge graph ─────────────────────────────────────────────────────────
@dataclass
class _KGEntity:
    id: str
    type: str
    props: Dict[str, Any] = field(default_factory=dict)


class KnowledgeGraph:
    """In-memory typed directed graph of entities + typed relationships.

    Supports:
    - add_entity(id, type, props)
    - add_relation(src, rel, dst) with optional temporal 'valid_at' on facts
    - neighbors(id, rel) - direct outgoing neighbors
    - query_relations(entity) - all triples touching entity
    - multi_hop(start, max_hops, rel) - BFS up to max_hops
    - find_path(start, end, max_hops) - shortest directed path
    """

    def __init__(self) -> None:
        self._entities: Dict[str, _KGEntity] = {}
        # adjacency: src -> list of (rel, dst, props)
        self._out: Dict[str, List[Tuple[str, str, Dict[str, Any]]]] = {}
        # reverse adjacency: dst -> list of (rel, src, props)
        self._in: Dict[str, List[Tuple[str, str, Dict[str, Any]]]] = {}

    def add_entity(self, id: str, type: str = "", props: Optional[Dict[str, Any]] = None) -> None:
        if not id:
            raise ValueError("entity id must be a non-empty string")
        self._entities[id] = _KGEntity(id=id, type=type, props=dict(props or {}))
        self._out.setdefault(id, [])
        self._in.setdefault(id, [])

    def add_relation(
        self,
        src: str,
        rel: str,
        dst: str,
        props: Optional[Dict[str, Any]] = None,
        valid_at: Optional[str] = None,
    ) -> None:
        """Add a typed directed edge src --rel--> dst with optional properties and temporal validity."""
        # auto-create endpoints so callers can build graphs loosely
        if src not in self._entities:
            self.add_entity(src)
        if dst not in self._entities:
            self.add_entity(dst)
        edge_props = dict(props or {})
        if valid_at is not None:
            edge_props["valid_at"] = valid_at
        if (rel, dst, edge_props) not in self._out[src]:
            self._out[src].append((rel, dst, edge_props))
        if (rel, src, edge_props) not in self._in[dst]:
            self._in[dst].append((rel, src, edge_props))

    def has_entity(self, id: str) -> bool:
        return id in self._entities

    def get_entity(self, id: str) -> Optional[_KGEntity]:
        return self._entities.get(id)

    @property
    def entities(self) -> Dict[str, _KGEntity]:
        return dict(self._entities)

    def neighbors(self, id: str, rel: Optional[str] = None) -> List[str]:
        """Direct outgoing neighbors of ``id``, optionally filtered by rel."""
        edges = self._out.get(id, [])
        return [dst for r, dst, _p in edges if rel is None or r == rel]

    def query_relations(self, entity: str) -> List[Tuple[str, str, str, Dict[str, Any]]]:
        """All (src, rel, dst, props) quadruples touching ``entity`` (out + in)."""
        out = [(entity, r, dst, p) for r, dst, p in self._out.get(entity, [])]
        inc = [(src, r, entity, p) for r, src, p in self._in.get(entity, [])]
        return out + inc

    def multi_hop(
        self, start: str, max_hops: int = 2, rel: Optional[str] = None
    ) -> Dict[str, int]:
        """BFS up to max_hops. Returns {entity_id: hop_distance} excluding start."""
        if start not in self._entities:
            return {}
        dist: Dict[str, int] = {start: 0}
        q: deque = deque([start])
        while q:
            cur = q.popleft()
            if dist[cur] >= max_hops:
                continue
            for r, dst, _p in self._out.get(cur, []):
                if rel is not None and r != rel:
                    continue
                if dst not in dist:
                    dist[dst] = dist[cur] + 1
                    q.append(dst)
        dist.pop(start, None)
        return dist

    def find_path(
        self, start: str, end: str, max_hops: int = 5
    ) -> Optional[List[str]]:
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
            for _r, dst, _p in self._out.get(cur, []):
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

    def temporal_query(self, entity: str, at_time: str) -> List[Tuple[str, str, str, Dict[str, Any]]]:
        """Return relations for entity that are valid at the given time.

        Compares 'valid_at' property on edges. Assumes ISO-like date strings
        that are lexicographically comparable (e.g., '2024-01-15').
        """
        result = []
        for src, rel, dst, props in self.query_relations(entity):
            valid_at = props.get("valid_at")
            if valid_at is None or valid_at <= at_time:
                result.append((src, rel, dst, props))
        return result


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
    "how are",
    "who is",
    "temporal",
    "when did",
    "history of",
)


@dataclass
class RetrievalResult:
    """A single fused retrieval hit with provenance back to its strategy."""

    ref: str                      # chunk_id (vector) or entity_id (graph)
    source: str                   # 'vector' | 'graph'
    score: float                  # fused score
    detail: Dict[str, Any] = field(default_factory=dict)


class AgenticRouter:
    """Agentic router that decides vector-vs-graph per query.

    Uses simple deterministic rules grounded in the transcript:
    - Relational cues ('how related', 'who', 'depends on', 'path between',
      temporal words) -> graph
    - Otherwise semantic/lookup -> vector
    - Can combine both for hybrid queries

    This mirrors the transcript's system prompt logic: "use the knowledge graph
    tool only when the user asks about two companies in the same question
    because then we want to analyze the relationship between two companies...
    Otherwise, just use the vector store tool. And combine both approaches only
    when you are asked to do so."
    """

    def __init__(
        self,
        vector_store: Optional[VectorStore] = None,
        graph: Optional[KnowledgeGraph] = None,
    ) -> None:
        self.vector_store = vector_store or VectorStore()
        self.graph = graph or KnowledgeGraph()

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
            # Relational intent. If no known entities, need semantic search
            # to find starting point: hybrid.
            if not has_entities:
                return "hybrid"
            return "graph"

        # Non-relational. Plain lookup -> vector. But if it names a known
        # entity AND is a reasonably broad query, blend both for recall.
        if has_entities and len(tokenize(query)) >= 4:
            return "hybrid"
        return "vector"

    def _vector_hits(self, query: str, top_k: int) -> List[RetrievalResult]:
        out: List[RetrievalResult] = []
        for rank, (chunk_id, score, metadata) in enumerate(
            self.vector_store.search(query, top_k)
        ):
            out.append(
                RetrievalResult(
                    ref=chunk_id,
                    source="vector",
                    score=score,
                    detail={"rank": rank, "similarity": score, "metadata": metadata},
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

    def _rrf(self, result_lists: List[List[RetrievalResult]], top_k: int) -> List[RetrievalResult]:
        """Reciprocal Rank Fusion over ranked result lists, keyed by (source,ref)."""
        RRF_K = 60
        fused: Dict[Tuple[str, str], RetrievalResult] = {}
        for results in result_lists:
            for rank, r in enumerate(results):
                key = (r.source, r.ref)
                contrib = 1.0 / (RRF_K + rank + 1)
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