"""
AI Data Governance
Governs AI-specific data:
  Trusted training data, RAG knowledge, Versioned embeddings,
  Embedding lifecycle, Hallucination risk reduction,
  Source attribution, Confidence scoring,
  AI memory validation/expiration/versioning
"""
from __future__ import annotations

import hashlib
import json
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union


# ─── Enums ────────────────────────────────────────────────────────────────────

class EmbeddingStatus(str, Enum):
    """Status of an embedding in its lifecycle."""
    GENERATED = "generated"
    VALIDATED = "validated"
    DEPRECATED = "deprecated"
    EXPIRED = "expired"
    CORRUPTED = "corrupted"
    REGENERATED = "regenerated"


class MemoryStatus(str, Enum):
    """AI memory status."""
    ACTIVE = "active"
    STALE = "stale"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"
    ARCHIVED = "archived"
    DELETED = "deleted"


class HallucinationRisk(str, Enum):
    """Risk level for hallucination in AI outputs."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DataSourceQuality(str, Enum):
    """Quality rating for data sources used in AI."""
    TRUSTED = "trusted"
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    DEPRECATED = "deprecated"
    FLAGGED = "flagged"


class ValidationStatus(str, Enum):
    """AI memory validation status."""
    VALID = "valid"
    INVALID = "invalid"
    PENDING = "pending"
    STALE = "stale"
    NEEDS_REVIEW = "needs_review"


# ─── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class TrainingDataRecord:
    """Metadata and governance for a training data record."""
    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source: str = ""
    source_quality: DataSourceQuality = DataSourceQuality.UNVERIFIED
    content_hash: str = ""
    pii_scan_completed: bool = False
    pii_scan_result: Dict[str, Any] = field(default_factory=dict)
    bias_assessment: Optional[Dict[str, Any]] = None
    toxicity_score: float = 0.0
    classification: str = "unclassified"
    collected_at: datetime = field(default_factory=datetime.utcnow)
    verified_at: Optional[datetime] = None
    verified_by: str = ""
    license_info: str = ""
    attribution: str = ""
    retention_days: int = 365
    is_trusted: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    @property
    def is_due_for_review(self) -> bool:
        if self.is_trusted and not self.verified_at:
            return True
        if self.verified_at:
            return (datetime.utcnow() - self.verified_at).days > 180
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "source": self.source,
            "source_quality": self.source_quality.value,
            "pii_scan_completed": self.pii_scan_completed,
            "toxicity_score": self.toxicity_score,
            "classification": self.classification,
            "collected_at": self.collected_at.isoformat(),
            "is_trusted": self.is_trusted,
            "license_info": self.license_info,
            "tags": self.tags,
        }


@dataclass
class EmbeddingVersion:
    """A versioned embedding with lifecycle tracking."""
    embedding_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    version: int = 1
    model_name: str = ""           # e.g., "text-embedding-3-large"
    model_version: str = ""
    dimensions: int = 0
    content_hash: str = ""         # Hash of the source content
    embedding_hash: str = ""       # Hash of the actual embedding
    status: EmbeddingStatus = EmbeddingStatus.GENERATED
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    accuracy_score: float = 0.0
    source_attribution: str = ""
    chunk_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_current(self) -> bool:
        return self.status in (EmbeddingStatus.GENERATED, EmbeddingStatus.VALIDATED)

    @property
    def is_expired(self) -> bool:
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return True
        return self.status == EmbeddingStatus.EXPIRED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "embedding_id": self.embedding_id,
            "version": self.version,
            "model_name": self.model_name,
            "dimensions": self.dimensions,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "source_attribution": self.source_attribution,
        }


@dataclass
class AIMemory:
    """AI agent memory with validation and expiration."""
    memory_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    memory_type: str = "conversation"  # conversation, preference, fact, context
    content: str = ""
    embedding_id: Optional[str] = None
    source: str = ""
    confidence: float = 1.0
    validation_status: ValidationStatus = ValidationStatus.PENDING
    status: MemoryStatus = MemoryStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    version: int = 1
    ttl_days: int = 30
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    hallucination_risk: HallucinationRisk = HallucinationRisk.LOW
    source_attribution: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_stale(self) -> bool:
        if self.status == MemoryStatus.STALE:
            return True
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return True
        return False

    @property
    def needs_refresh(self) -> bool:
        return (datetime.utcnow() - self.updated_at).days > self.ttl_days

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "memory_type": self.memory_type,
            "confidence": self.confidence,
            "validation_status": self.validation_status.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "version": self.version,
            "ttl_days": self.ttl_days,
            "hallucination_risk": self.hallucination_risk.value,
            "source_attribution": self.source_attribution,
        }


@dataclass
class RAGKnowledgeEntry:
    """A knowledge entry for RAG (Retrieval-Augmented Generation)."""
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    content: str = ""
    source_url: str = ""
    source_quality: DataSourceQuality = DataSourceQuality.UNVERIFIED
    content_hash: str = ""
    embedding_version: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    last_verified_at: Optional[datetime] = None
    is_deprecated: bool = False
    access_count: int = 0
    confidence_threshold: float = 0.7
    attribution: str = ""
    tags: List[str] = field(default_factory=list)
    citations: List[Dict[str, str]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "title": self.title,
            "source_url": self.source_url,
            "source_quality": self.source_quality.value,
            "created_at": self.created_at.isoformat(),
            "last_verified_at": self.last_verified_at.isoformat() if self.last_verified_at else None,
            "is_deprecated": self.is_deprecated,
            "access_count": self.access_count,
            "confidence_threshold": self.confidence_threshold,
            "tags": self.tags,
        }


@dataclass
class SourceAttribution:
    """Detailed source attribution for AI-generated content."""
    attribution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_url: str = ""
    source_title: str = ""
    source_author: str = ""
    source_date: Optional[datetime] = None
    retrieval_score: float = 0.0
    relevance_score: float = 0.0
    content_snippet: str = ""
    license_info: str = ""
    is_verified: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


# ─── AI Data Governor ─────────────────────────────────────────────────────────

class AIDataGovernor:
    """
    Enterprise AI data governance engine.

    Manages:
      - Trusted training data with PII/bias/toxicity scanning
      - RAG knowledge base governance
      - Embedding versioning and lifecycle
      - Hallucination risk assessment
      - Source attribution and confidence scoring
      - AI memory validation, expiration, and versioning

    Usage:
        gov = AIDataGovernor()
        gov.register_training_data(record)
        gov.create_embedding_version(content, model_info)
        gov.store_memory(memory)
        gov.assess_hallucination_risk(memory)
    """

    def __init__(self):
        self._training_records: Dict[str, TrainingDataRecord] = {}
        self._rag_entries: Dict[str, RAGKnowledgeEntry] = {}
        self._embeddings: Dict[str, List[EmbeddingVersion]] = defaultdict(list)
        self._memories: Dict[str, AIMemory] = {}
        self._attributions: Dict[str, List[SourceAttribution]] = defaultdict(list)

    # ── Training Data Governance ──────────────────────────────────────────

    def register_training_data(
        self,
        source: str,
        content: str,
        source_quality: DataSourceQuality = DataSourceQuality.UNVERIFIED,
        license_info: str = "",
        attribution: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TrainingDataRecord:
        """Register a training data record with governance metadata."""
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        record = TrainingDataRecord(
            source=source,
            source_quality=source_quality,
            content_hash=content_hash,
            license_info=license_info,
            attribution=attribution,
            metadata=metadata or {},
        )
        self._training_records[record.record_id] = record
        return record

    def scan_for_pii(
        self, record_id: str, pii_detector: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """Scan training data for PII using the classifier."""
        record = self._training_records.get(record_id)
        if not record:
            return {"error": "Record not found"}

        # Use built-in basic scan
        pii_patterns = {
            "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b',
            "phone": r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
            "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
        }
        import re
        findings = {}
        for pii_type, pattern in pii_patterns.items():
            matches = re.findall(pattern, record.metadata.get("content", ""))
            if matches:
                findings[pii_type] = len(matches)

        record.pii_scan_completed = True
        record.pii_scan_result = {
            "findings": findings,
            "has_pii": len(findings) > 0,
            "scanned_at": datetime.utcnow().isoformat(),
        }
        return record.pii_scan_result

    def assess_bias(
        self, record_id: str, bias_score: Optional[float] = None
    ) -> Dict[str, Any]:
        """Record bias assessment for training data."""
        record = self._training_records.get(record_id)
        if not record:
            return {"error": "Record not found"}

        assessment = {
            "bias_score": bias_score or 0.0,
            "assessed_at": datetime.utcnow().isoformat(),
            "risk_level": "low" if (bias_score or 0) < 0.3 else "medium" if (bias_score or 0) < 0.7 else "high",
        }
        record.bias_assessment = assessment
        return assessment

    def assess_toxicity(
        self, record_id: str, toxicity_score: float
    ) -> None:
        """Record toxicity assessment."""
        record = self._training_records.get(record_id)
        if record:
            record.toxicity_score = toxicity_score

    def verify_training_data(
        self, record_id: str, verified_by: str
    ) -> bool:
        """Mark training data as verified/trusted."""
        record = self._training_records.get(record_id)
        if record:
            record.is_trusted = True
            record.verified_at = datetime.utcnow()
            record.verified_by = verified_by
            record.source_quality = DataSourceQuality.TRUSTED
            return True
        return False

    def flag_training_data(self, record_id: str, reason: str) -> bool:
        """Flag training data as problematic."""
        record = self._training_records.get(record_id)
        if record:
            record.source_quality = DataSourceQuality.FLAGGED
            record.is_trusted = False
            record.metadata["flag_reason"] = reason
            record.metadata["flagged_at"] = datetime.utcnow().isoformat()
            return True
        return False

    def get_trusted_training_data(self) -> List[TrainingDataRecord]:
        return [r for r in self._training_records.values() if r.is_trusted]

    def get_training_records_due_for_review(self) -> List[TrainingDataRecord]:
        return [r for r in self._training_records.values() if r.is_due_for_review]

    # ── RAG Knowledge Governance ──────────────────────────────────────────

    def add_rag_entry(
        self,
        title: str,
        content: str,
        source_url: str = "",
        attribution: str = "",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RAGKnowledgeEntry:
        """Add a knowledge entry to the RAG knowledge base."""
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        entry = RAGKnowledgeEntry(
            title=title,
            content=content,
            source_url=source_url,
            content_hash=content_hash,
            attribution=attribution,
            tags=tags or [],
            metadata=metadata or {},
        )
        self._rag_entries[entry.entry_id] = entry
        return entry

    def verify_rag_entry(self, entry_id: str, verifier: str) -> bool:
        """Verify a RAG knowledge entry."""
        entry = self._rag_entries.get(entry_id)
        if entry:
            entry.last_verified_at = datetime.utcnow()
            entry.source_quality = DataSourceQuality.VERIFIED
            return True
        return False

    def deprecate_rag_entry(self, entry_id: str, reason: str) -> bool:
        """Deprecate a RAG knowledge entry."""
        entry = self._rag_entries.get(entry_id)
        if entry:
            entry.is_deprecated = True
            entry.metadata["deprecation_reason"] = reason
            entry.metadata["deprecated_at"] = datetime.utcnow().isoformat()
            return True
        return False

    def search_rag(
        self,
        query: str,
        min_confidence: float = 0.7,
        exclude_deprecated: bool = True,
    ) -> List[RAGKnowledgeEntry]:
        """Search RAG knowledge base (basic keyword search)."""
        query_lower = query.lower()
        results: List[RAGKnowledgeEntry] = []

        for entry in self._rag_entries.values():
            if exclude_deprecated and entry.is_deprecated:
                continue
            if entry.confidence_threshold < min_confidence:
                continue
            # Simple keyword match
            score = 0
            if query_lower in entry.title.lower():
                score += 10
            if query_lower in entry.content.lower():
                score += 5
            for tag in entry.tags:
                if query_lower in tag.lower():
                    score += 3
            if score > 0:
                results.append((score, entry))

        results.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in results]

    def get_rag_stats(self) -> Dict[str, Any]:
        return {
            "total_entries": len(self._rag_entries),
            "verified_entries": sum(
                1 for e in self._rag_entries.values()
                if e.source_quality == DataSourceQuality.VERIFIED
            ),
            "deprecated_entries": sum(1 for e in self._rag_entries.values() if e.is_deprecated),
            "total_accesses": sum(e.access_count for e in self._rag_entries.values()),
        }

    # ── Embedding Lifecycle ───────────────────────────────────────────────

    def create_embedding_version(
        self,
        content: str,
        model_name: str,
        model_version: str,
        dimensions: int,
        source_attribution: str = "",
        chunk_id: str = "",
        ttl_days: int = 90,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> EmbeddingVersion:
        """Create a new embedding version."""
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        # Find latest version for this content
        existing = self._embeddings.get(content_hash, [])
        version = len(existing) + 1

        embedding = EmbeddingVersion(
            version=version,
            model_name=model_name,
            model_version=model_version,
            dimensions=dimensions,
            content_hash=content_hash,
            embedding_hash="pending",  # Would be set by embedding generator
            source_attribution=source_attribution,
            chunk_id=chunk_id,
            expires_at=datetime.utcnow() + timedelta(days=ttl_days),
            metadata=metadata or {},
        )
        self._embeddings[content_hash].append(embedding)
        return embedding

    def validate_embedding(
        self, content_hash: str, version: int
    ) -> bool:
        """Validate an embedding version."""
        versions = self._embeddings.get(content_hash, [])
        for emb in versions:
            if emb.version == version:
                emb.status = EmbeddingStatus.VALIDATED
                return True
        return False

    def deprecate_embedding(
        self, content_hash: str, version: int, reason: str
    ) -> bool:
        """Deprecate an embedding version."""
        versions = self._embeddings.get(content_hash, [])
        for emb in versions:
            if emb.version == version:
                emb.status = EmbeddingStatus.DEPRECATED
                emb.metadata["deprecation_reason"] = reason
                emb.metadata["deprecated_at"] = datetime.utcnow().isoformat()
                return True
        return False

    def get_current_embedding(
        self, content_hash: str
    ) -> Optional[EmbeddingVersion]:
        """Get the current (latest valid) embedding for content."""
        versions = self._embeddings.get(content_hash, [])
        for emb in reversed(versions):
            if emb.is_current:
                return emb
        return None

    def get_embedding_versions(
        self, content_hash: str
    ) -> List[EmbeddingVersion]:
        """Get all versions of embeddings for content."""
        return self._embeddings.get(content_hash, [])

    def expire_embeddings(self) -> int:
        """Expire embeddings past their TTL. Returns count of expired."""
        count = 0
        for versions in self._embeddings.values():
            for emb in versions:
                if emb.is_expired and emb.status != EmbeddingStatus.EXPIRED:
                    emb.status = EmbeddingStatus.EXPIRED
                    count += 1
        return count

    # ── AI Memory Management ──────────────────────────────────────────────

    def store_memory(
        self,
        content: str,
        memory_type: str = "conversation",
        session_id: str = "",
        source: str = "",
        confidence: float = 1.0,
        ttl_days: int = 30,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AIMemory:
        """Store an AI memory entry."""
        memory = AIMemory(
            session_id=session_id,
            memory_type=memory_type,
            content=content,
            source=source,
            confidence=confidence,
            validation_status=ValidationStatus.PENDING,
            status=MemoryStatus.ACTIVE,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=ttl_days),
            ttl_days=ttl_days,
            metadata=metadata or {},
        )
        self._memories[memory.memory_id] = memory
        return memory

    def validate_memory(
        self, memory_id: str, validation_result: ValidationStatus
    ) -> bool:
        """Update validation status of a memory."""
        memory = self._memories.get(memory_id)
        if memory:
            memory.validation_status = validation_result
            memory.updated_at = datetime.utcnow()
            if validation_result == ValidationStatus.INVALID:
                memory.status = MemoryStatus.INVALIDATED
            return True
        return False

    def access_memory(self, memory_id: str) -> Optional[AIMemory]:
        """Record access to a memory."""
        memory = self._memories.get(memory_id)
        if memory:
            memory.access_count += 1
            memory.last_accessed = datetime.utcnow()
            return memory
        return None

    def update_memory(
        self, memory_id: str, new_content: str, confidence: float = 1.0
    ) -> Optional[AIMemory]:
        """Update a memory, creating a new version."""
        memory = self._memories.get(memory_id)
        if not memory:
            return None
        # Archive old version
        memory.status = MemoryStatus.ARCHIVED
        # Create new version
        new_memory = AIMemory(
            session_id=memory.session_id,
            memory_type=memory.memory_type,
            content=new_content,
            source=memory.source,
            confidence=confidence,
            validation_status=ValidationStatus.PENDING,
            status=MemoryStatus.ACTIVE,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=memory.ttl_days),
            version=memory.version + 1,
            ttl_days=memory.ttl_days,
            metadata=memory.metadata,
        )
        self._memories[new_memory.memory_id] = new_memory
        return new_memory

    def delete_memory(self, memory_id: str) -> bool:
        """Delete an AI memory."""
        memory = self._memories.get(memory_id)
        if memory:
            memory.status = MemoryStatus.DELETED
            memory.updated_at = datetime.utcnow()
            return True
        return False

    def expire_memories(self) -> int:
        """Expire stale/deleted memories. Returns count."""
        count = 0
        for memory in self._memories.values():
            if memory.is_stale and memory.status == MemoryStatus.ACTIVE:
                memory.status = MemoryStatus.EXPIRED
                count += 1
        return count

    def get_memories_by_session(self, session_id: str) -> List[AIMemory]:
        return [m for m in self._memories.values() if m.session_id == session_id]

    def get_active_memories(self) -> List[AIMemory]:
        return [
            m for m in self._memories.values()
            if m.status == MemoryStatus.ACTIVE and not m.is_stale
        ]

    # ── Hallucination Risk Reduction ──────────────────────────────────────

    def assess_hallucination_risk(
        self,
        memory: Optional[AIMemory] = None,
        source_quality: Optional[DataSourceQuality] = None,
        confidence: Optional[float] = None,
        has_attribution: Optional[bool] = None,
        content_age_days: Optional[int] = None,
    ) -> HallucinationRisk:
        """
        Assess hallucination risk for an AI memory or output context.

        Factors:
          - Source quality (trusted > verified > unverified > deprecated)
          - Confidence score
          - Source attribution presence
          - Content freshness
        """
        risk_score = 0.0

        if memory:
            source_quality = (
                DataSourceQuality.UNVERIFIED if memory.source else None
            )
            confidence = memory.confidence
            has_attribution = bool(memory.source_attribution)
            content_age_days = (
                (datetime.utcnow() - memory.created_at).days
            )

        # Source quality factor
        if source_quality:
            quality_scores = {
                DataSourceQuality.TRUSTED: 0.0,
                DataSourceQuality.VERIFIED: 0.1,
                DataSourceQuality.UNVERIFIED: 0.3,
                DataSourceQuality.DEPRECATED: 0.5,
                DataSourceQuality.FLAGGED: 0.7,
            }
            risk_score += quality_scores.get(source_quality, 0.3)

        # Confidence penalty
        if confidence is not None:
            risk_score += (1.0 - confidence) * 0.4

        # Attribution bonus (reduces risk)
        if has_attribution is not None and not has_attribution:
            risk_score += 0.2

        # Content age
        if content_age_days is not None:
            if content_age_days > 180:
                risk_score += 0.3
            elif content_age_days > 90:
                risk_score += 0.2
            elif content_age_days > 30:
                risk_score += 0.1

        # Map to risk level
        if risk_score >= 0.7:
            return HallucinationRisk.CRITICAL
        elif risk_score >= 0.5:
            return HallucinationRisk.HIGH
        elif risk_score >= 0.3:
            return HallucinationRisk.MEDIUM
        return HallucinationRisk.LOW

    def get_hallucination_mitigation(
        self, risk: HallucinationRisk
    ) -> List[str]:
        """Get mitigation strategies for a hallucination risk level."""
        strategies = {
            HallucinationRisk.LOW: [
                "Standard confidence scoring applied",
                "Basic attribution included",
            ],
            HallucinationRisk.MEDIUM: [
                "Use verified sources only",
                "Include explicit source citations",
                "Flag output with confidence score",
            ],
            HallucinationRisk.HIGH: [
                "Require human review before use",
                "Limit to trusted sources only",
                "Add prominent confidence warning",
                "Cross-reference with verified knowledge",
            ],
            HallucinationRisk.CRITICAL: [
                "DO NOT USE - High hallucination risk",
                "Require mandatory human verification",
                "Source is deprecated or flagged",
                "Content is stale/outdated",
                "Recommend regenerating from trusted source",
            ],
        }
        return strategies.get(risk, [])

    # ── Confidence Scoring ────────────────────────────────────────────────

    def compute_confidence(
        self,
        source_quality: DataSourceQuality,
        has_attribution: bool,
        is_verified: bool,
        content_freshness_days: int,
        cross_referenced: bool = False,
    ) -> Dict[str, Any]:
        """Compute a composite confidence score."""
        scores = {}

        # Source quality
        quality_map = {
            DataSourceQuality.TRUSTED: 1.0,
            DataSourceQuality.VERIFIED: 0.85,
            DataSourceQuality.UNVERIFIED: 0.5,
            DataSourceQuality.DEPRECATED: 0.3,
            DataSourceQuality.FLAGGED: 0.1,
        }
        scores["source_quality"] = quality_map.get(source_quality, 0.5)

        # Attribution
        scores["attribution"] = 1.0 if has_attribution else 0.5

        # Verification
        scores["verification"] = 1.0 if is_verified else 0.6

        # Freshness
        if content_freshness_days <= 7:
            scores["freshness"] = 1.0
        elif content_freshness_days <= 30:
            scores["freshness"] = 0.9
        elif content_freshness_days <= 90:
            scores["freshness"] = 0.7
        elif content_freshness_days <= 180:
            scores["freshness"] = 0.5
        else:
            scores["freshness"] = 0.3

        # Cross-referencing
        scores["cross_referenced"] = 0.9 if cross_referenced else 0.5

        # Weighted aggregate
        weights = {
            "source_quality": 0.35,
            "attribution": 0.15,
            "verification": 0.20,
            "freshness": 0.20,
            "cross_referenced": 0.10,
        }
        composite = sum(scores[k] * weights[k] for k in scores)

        confidence_level = (
            "high" if composite >= 0.85
            else "medium" if composite >= 0.65
            else "low"
        )

        return {
            "composite_score": round(composite, 4),
            "confidence_level": confidence_level,
            "component_scores": scores,
        }

    # ── Source Attribution ────────────────────────────────────────────────

    def add_attribution(
        self,
        output_id: str,
        source_url: str,
        source_title: str = "",
        source_author: str = "",
        retrieval_score: float = 0.0,
        relevance_score: float = 0.0,
        content_snippet: str = "",
        license_info: str = "",
        is_verified: bool = False,
    ) -> SourceAttribution:
        """Add source attribution for AI-generated content."""
        attribution = SourceAttribution(
            source_url=source_url,
            source_title=source_title,
            source_author=source_author,
            retrieval_score=retrieval_score,
            relevance_score=relevance_score,
            content_snippet=content_snippet,
            license_info=license_info,
            is_verified=is_verified,
        )
        self._attributions[output_id].append(attribution)
        return attribution

    def get_attributions(
        self, output_id: str
    ) -> List[SourceAttribution]:
        """Get all source attributions for an output."""
        return self._attributions.get(output_id, [])

    def generate_citation(
        self, attribution: SourceAttribution, style: str = "inline"
    ) -> str:
        """Generate a citation from attribution data."""
        if style == "inline":
            return f"[{attribution.source_title or attribution.source_url}]({attribution.source_url})"
        elif style == "footnote":
            author = attribution.source_author or "Unknown"
            return f"{author}. \"{attribution.source_title}\". {attribution.source_url}"
        elif style == "apa":
            author = attribution.source_author or "Unknown"
            date = attribution.source_date.strftime("%Y") if attribution.source_date else "n.d."
            return f"{author} ({date}). {attribution.source_title}. Retrieved from {attribution.source_url}"
        return str(attribution.source_url)

    # ── Statistics ────────────────────────────────────────────────────────

    @property
    def stats(self) -> Dict[str, Any]:
        active_memories = self.get_active_memories()
        expired_memories = sum(
            1 for m in self._memories.values()
            if m.status == MemoryStatus.EXPIRED
        )
        training_quality = Counter(
            r.source_quality.value for r in self._training_records.values()
        )
        return {
            "training_records": {
                "total": len(self._training_records),
                "trusted": len(self.get_trusted_training_data()),
                "due_for_review": len(self.get_training_records_due_for_review()),
                "by_quality": dict(training_quality),
            },
            "rag_entries": self.get_rag_stats(),
            "embeddings": {
                "content_hashes": len(self._embeddings),
                "total_versions": sum(len(v) for v in self._embeddings.values()),
            },
            "memories": {
                "total": len(self._memories),
                "active": len(active_memories),
                "expired": expired_memories,
                "invalidated": sum(
                    1 for m in self._memories.values()
                    if m.status == MemoryStatus.INVALIDATED
                ),
            },
            "memory_types": Counter(
                m.memory_type for m in self._memories.values()
            ),
        }