"""Semantic Memory Core — dependency-free semantic retrieval.

This module provides a lightweight, dependency-free semantic retrieval
layer inspired by cognee-style persistent graph memory:

  * ``HashEmbedder`` — deterministic feature-hash bag-of-tokens embeddings
    (sparse hashing into a dense vector, sign trick, L2 normalised).
  * Pure-Python vector math helpers (``normalize``, ``dot``, ``cosine_similarity``).
  * ``SemanticIndex`` — in-memory store of documents with injectable embedder,
    cosine ranking, metadata filtering, removal, and counting.
  * ``KnowledgeGraphAdapter`` — optional thin adapter that ingests
    ``(entity_name, description, relation)`` triples into the index so the
    module can consume knowledge-graph data without depending on its internals.
  * ``SemanticMemory`` — facade combining an index and an embedder.

No external packages are required. Python 3.10+.

Version: 1.0.0
"""

from __future__ import annotations

import hashlib
import math
import re
import threading
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

__all__ = [
    "Embedder",
    "HashEmbedder",
    "Document",
    "ScoredDoc",
    "SemanticIndex",
    "KnowledgeGraphAdapter",
    "SemanticMemory",
    "normalize",
    "dot",
    "cosine_similarity",
]

# A token is a run of alphanumeric characters (letters/digits/underscore).
_TOKEN_RE = re.compile(r"[a-z0-9_]+")


class Embedder(Protocol):
    """Protocol describing any vector embedder used by the semantic index.

    Implementations must be deterministic: the same input text must always
    yield the same vector.
    """

    def embed(self, text: str) -> list[float]:
        """Embed a text string into a fixed-length float vector."""
        ...

    @property
    def dim(self) -> int:
        """Dimensionality of the produced vectors."""
        ...


class HashEmbedder:
    """Deterministic feature-hash bag-of-tokens embedder.

    Maps each lowercase alphanumeric token to a fixed bucket using
    ``sha1``, applies a sign trick (token hash parity decides the sign) to
    reduce collision interference, then L2-normalises the resulting vector
    to unit length.

    Deterministic: the same input text always produces the identical vector,
    regardless of process or invocation order.
    """

    __slots__ = ("_dim", "_salt")

    def __init__(self, dim: int = 256) -> None:
        if not isinstance(dim, int) or dim <= 0:
            raise ValueError("dim must be a positive integer")
        self._dim = dim
        self._salt = b"eni-semantic-memory-v1"

    @property
    def dim(self) -> int:
        return self._dim

    def _token_bucket(self, token: str) -> int:
        """Return the feature-hash bucket index for a token."""
        digest = hashlib.sha1(self._salt + token.encode("utf-8", "ignore")).digest()
        return int.from_bytes(digest[:8], "big") % self._dim

    def _token_sign(self, token: str) -> float:
        """Return +1.0 or -1.0 based on token hash parity (sign trick)."""
        digest = hashlib.sha1(token.encode("utf-8", "ignore")).digest()
        return 1.0 if digest[0] % 2 == 0 else -1.0

    def embed(self, text: str) -> list[float]:
        """Embed text into a unit-length vector of size ``dim``.

        Args:
            text: Arbitrary input text. Empty text yields the zero vector.

        Returns:
            A list of ``dim`` floats, L2-normalised to unit length.
        """
        vec = [0.0] * self._dim
        seen_buckets: set[int] = set()
        for token in _TOKEN_RE.findall(text.lower()):
            bucket = self._token_bucket(token)
            # Avoid double counting repeated tokens within the same document
            # (bag-of-words semantics) while keeping determinism.
            if bucket in seen_buckets:
                continue
            seen_buckets.add(bucket)
            vec[bucket] += self._token_sign(token)
        return normalize(vec)


def dot(a: Sequence[float], b: Sequence[float]) -> float:
    """Return the dot product of two equal-length vectors."""
    if len(a) != len(b):
        raise ValueError("Vector dimension mismatch in dot product")
    return float(sum(x * y for x, y in zip(a, b)))


def normalize(vec: Sequence[float]) -> list[float]:
    """Return a copy of ``vec`` scaled to unit L2 norm.

    A zero vector (or all-zero input) is returned unchanged.
    """
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return list(vec)
    return [x / norm for x in vec]


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Return the cosine similarity between two vectors in ``[-1.0, 1.0]``.

    Zero vectors (unembeddable / empty input) yield ``0.0``.
    """
    if len(a) != len(b):
        raise ValueError("Vector dimension mismatch in cosine similarity")
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (norm_a * norm_b)


@dataclass
class Document:
    """A stored document inside a :class:`SemanticIndex`.

    Attributes:
        id: Unique document identifier.
        text: Original source text.
        metadata: Arbitrary key-value metadata attached to the document.
        vector: The precomputed embedding for ``text``.
    """

    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    vector: list[float] = field(default_factory=list)


@dataclass
class ScoredDoc:
    """A search hit: a document paired with its cosine similarity score.

    Attributes:
        id: Document identifier.
        score: Cosine similarity in ``[0.0, 1.0]`` (normalised from -1..1).
        text: Original source text.
        metadata: Document metadata.
    """

    id: str
    score: float
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _matches_filter(metadata: dict[str, Any], metadata_filter: dict[str, Any]) -> bool:
    """Return True if all filter keys/values appear in ``metadata``."""
    if not metadata_filter:
        return True
    if not metadata:
        return False
    return all(metadata.get(key) == value for key, value in metadata_filter.items())


class SemanticIndex:
    """In-memory semantic search index.

    Stores documents with precomputed vectors (produced by an injectable
    embedder) and supports nearest-neighbour retrieval by cosine similarity,
    optional metadata filtering, removal, and counting.

    Args:
        embedder: Embedder used to build vectors for new documents. Defaults
            to a :class:`HashEmbedder`.
    """

    def __init__(self, embedder: Embedder | None = None) -> None:
        self._embedder: Embedder = embedder if embedder is not None else HashEmbedder()
        self._documents: dict[str, Document] = {}
        self._lock = threading.RLock()

    @property
    def embedder(self) -> Embedder:
        """The embedder in use by this index."""
        return self._embedder

    def add(self, id: str, text: str, metadata: dict[str, Any] | None = None) -> str:
        """Add (or replace) a document and return its id.

        Args:
            id: Unique identifier for the document.
            text: Source text to embed and store.
            metadata: Optional key-value metadata.

        Returns:
            The document ``id``.
        """
        vector = self._embedder.embed(text)
        with self._lock:
            self._documents[id] = Document(
                id=id,
                text=text,
                metadata=dict(metadata or {}),
                vector=vector,
            )
        return id

    def get(self, id: str) -> Document | None:
        """Return the document with ``id``, or ``None`` if absent."""
        with self._lock:
            return self._documents.get(id)

    def remove(self, id: str) -> bool:
        """Remove the document with ``id``.

        Returns:
            ``True`` if a document was removed, ``False`` otherwise.
        """
        with self._lock:
            return self._documents.pop(id, None) is not None

    def count(self) -> int:
        """Return the number of stored documents."""
        with self._lock:
            return len(self._documents)

    def search(
        self,
        query: str,
        k: int = 5,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[ScoredDoc]:
        """Search the index, returning the top-k most similar documents.

        Documents are ranked by descending cosine similarity between the
        query embedding and each stored vector. An optional metadata filter
        (exact subset match on the metadata dict) is applied *before*
        ranking, so only matching documents participate in the ranking.

        Args:
            query: Query text to embed.
            k: Maximum number of results to return (clamped to ``>= 0``).
            metadata_filter: Optional exact-match subset filter on metadata.

        Returns:
            A list of :class:`ScoredDoc` ordered most-similar first.
        """
        query_vec = self._embedder.embed(query)
        f = metadata_filter or {}
        with self._lock:
            candidates = [
                doc for doc in self._documents.values() if _matches_filter(doc.metadata, f)
            ]

        scored: list[ScoredDoc] = []
        for doc in candidates:
            sim = cosine_similarity(query_vec, doc.vector)
            # Clamp to [0, 1] for a clean similarity score.
            score = max(0.0, min(1.0, sim))
            scored.append(
                ScoredDoc(
                    id=doc.id,
                    score=score,
                    text=doc.text,
                    metadata=dict(doc.metadata),
                )
            )

        scored.sort(key=lambda s: s.score, reverse=True)
        if k <= 0:
            return []
        return scored[:k]


class KnowledgeGraphAdapter:
    """Thin adapter ingesting knowledge-graph triples into a SemanticIndex.

    The adapter is intentionally decoupled from the ``knowledge_graph``
    module internals: it accepts generic triple dictionaries shaped as
    ``{"entity_name": str, "description": str, "relation": str}`` and turns
    each triple into documents (an entity node document plus an edge/relation
    document). This lets the semantic memory layer consume graph data without
    depending on the knowledge graph implementation.
    """

    _TRIPLE_KEYS = ("entity_name", "description", "relation")

    def __init__(self, index: SemanticIndex, prefix: str = "kg") -> None:
        self._index = index
        self._prefix = prefix
        self._lock = threading.RLock()

    @property
    def index(self) -> SemanticIndex:
        """The backing semantic index."""
        return self._index

    @staticmethod
    def _validate_triple(triple: dict[str, Any]) -> None:
        """Validate that ``triple`` has the expected shape."""
        if not isinstance(triple, dict):
            raise TypeError("Each triple must be a dict with entity_name, description, relation")
        for key in KnowledgeGraphAdapter._TRIPLE_KEYS:
            if key not in triple:
                raise ValueError(f"Triple missing required key: '{key}'")
            if triple[key] is None:
                raise ValueError(f"Triple field '{key}' must not be None")

    def _build_documents(self, triple: dict[str, Any]) -> tuple[str, str, str, str]:
        """Return ``(id_entity, text_entity, id_edge, text_edge)`` for a triple."""
        entity_name = str(triple["entity_name"])
        description = str(triple["description"])
        relation = str(triple["relation"])

        entity_text = f"{entity_name}: {description}"
        edge_text = f"{entity_name} {relation}"

        id_entity = f"{self._prefix}:entity:{uuid.uuid4().hex}"
        id_edge = f"{self._prefix}:edge:{uuid.uuid4().hex}"
        return id_entity, entity_text, id_edge, edge_text

    def ingest_triples(self, triples: Sequence[dict[str, Any]]) -> list[str]:
        """Ingest a batch of triples and return the ids of indexed documents.

        For each triple, two documents are indexed:
          * an entity node document combining the entity name + description;
          * an edge document combining the entity name + relation.

        Args:
            triples: Sequence of dicts with ``entity_name``, ``description``,
                and ``relation`` keys.

        Returns:
            List of document ids created (2 per triple).
        """
        created: list[str] = []
        with self._lock:
            for triple in triples:
                self._validate_triple(triple)
                id_entity, entity_text, id_edge, edge_text = self._build_documents(triple)
                metadata: dict[str, Any] = {
                    "source": "knowledge_graph",
                    "kind": "entity",
                    "entity_name": str(triple["entity_name"]),
                    "relation": str(triple["relation"]),
                }
                self._index.add(id_entity, entity_text, metadata)
                edge_metadata: dict[str, Any] = dict(metadata)
                edge_metadata["kind"] = "edge"
                self._index.add(id_edge, edge_text, edge_metadata)
                created.extend([id_entity, id_edge])
        return created


class SemanticMemory:
    """Facade combining a :class:`SemanticIndex` and an embedder.

    Provides the high-level ``remember`` / ``recall`` API used by the
    ``semantic_memory`` module and by application code.
    """

    def __init__(self, embedder: Embedder | None = None) -> None:
        self._embedder: Embedder = embedder if embedder is not None else HashEmbedder()
        self._index = SemanticIndex(embedder=self._embedder)

    @property
    def embedder(self) -> Embedder:
        return self._embedder

    @property
    def index(self) -> SemanticIndex:
        return self._index

    @property
    def adapter(self) -> KnowledgeGraphAdapter:
        """A graph adapter bound to this memory's index."""
        return KnowledgeGraphAdapter(self._index)

    def remember(
        self,
        id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Store a text document for later semantic retrieval."""
        return self._index.add(id, text, metadata)

    def recall(
        self,
        query: str,
        k: int = 5,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[ScoredDoc]:
        """Retrieve the top-k documents most semantically similar to a query."""
        return self._index.search(query, k=k, metadata_filter=metadata_filter)
