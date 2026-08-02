"""
Knowledge Graph Provenance

Every fact in the knowledge graph carries a provenance record documenting
its origin, trustworthiness, and lifecycle. This module provides the
provenance data model, chain tracking, and trust scoring.

Design principles:
- Every fact (entity + relationship) must have provenance.
- Sources are classified by type and trust level.
- Confidence is quantified, not binary.
- Provenance chains enable full audit trails.
- Facts expire unless re-verified.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class SourceType(str, Enum):
    """Classification of information sources by origin and trust model."""

    # Human sources
    USER_INPUT = "user_input"
    EXPERT_REVIEW = "expert_review"
    MANUAL_ENTRY = "manual_entry"
    INTERVIEW = "interview"

    # Automated sources
    CODE_ANALYSIS = "code_analysis"
    AST_PARSER = "ast_parser"
    API_DISCOVERY = "api_discovery"
    DATABASE_SCHEMA = "database_schema"
    CONFIG_SCAN = "config_scan"
    DEPENDENCY_SCAN = "dependency_scan"
    INFRA_SCAN = "infra_scan"
    LOG_ANALYSIS = "log_analysis"

    # Integration sources
    GIT_HISTORY = "git_history"
    CI_CD_PIPELINE = "ci_cd_pipeline"
    TICKET_SYSTEM = "ticket_system"
    MONITORING_SYSTEM = "monitoring_system"
    DOCS_PARSER = "docs_parser"
    THIRD_PARTY_API = "third_party_api"

    # Derived / inferred
    ML_INFERENCE = "ml_inference"
    HEURISTIC = "heuristic"
    TRANSITIVE = "transitive"
    AGGREGATION = "aggregation"

    # Governance
    POLICY_ENGINE = "policy_engine"
    COMPLIANCE_SCAN = "compliance_scan"
    AUDIT_LOG = "audit_log"


class ConfidenceLevel(str, Enum):
    """Confidence tier for facts in the graph."""

    VERIFIED = "verified"       # 0.95-1.0: Independently confirmed
    HIGH = "high"               # 0.80-0.94: Strong evidence
    MEDIUM = "medium"           # 0.50-0.79: Reasonable but unverified
    LOW = "low"                 # 0.20-0.49: Weak or single-source
    UNCERTAIN = "uncertain"     # 0.0-0.19: Unreliable or speculative


# Default confidence values by source type
DEFAULT_SOURCE_CONFIDENCE: Dict[SourceType, float] = {
    SourceType.USER_INPUT: 0.60,
    SourceType.EXPERT_REVIEW: 0.90,
    SourceType.MANUAL_ENTRY: 0.50,
    SourceType.INTERVIEW: 0.55,
    SourceType.CODE_ANALYSIS: 0.85,
    SourceType.AST_PARSER: 0.90,
    SourceType.API_DISCOVERY: 0.80,
    SourceType.DATABASE_SCHEMA: 0.95,
    SourceType.CONFIG_SCAN: 0.85,
    SourceType.DEPENDENCY_SCAN: 0.85,
    SourceType.INFRA_SCAN: 0.80,
    SourceType.LOG_ANALYSIS: 0.75,
    SourceType.GIT_HISTORY: 0.80,
    SourceType.CI_CD_PIPELINE: 0.85,
    SourceType.TICKET_SYSTEM: 0.70,
    SourceType.MONITORING_SYSTEM: 0.80,
    SourceType.DOCS_PARSER: 0.65,
    SourceType.THIRD_PARTY_API: 0.60,
    SourceType.ML_INFERENCE: 0.55,
    SourceType.HEURISTIC: 0.40,
    SourceType.TRANSITIVE: 0.35,
    SourceType.AGGREGATION: 0.70,
    SourceType.POLICY_ENGINE: 0.90,
    SourceType.COMPLIANCE_SCAN: 0.85,
    SourceType.AUDIT_LOG: 0.90,
}

# Default expiration by classification
DEFAULT_EXPIRATION_DAYS: Dict[str, int] = {
    "public": 365,
    "internal": 180,
    "confidential": 90,
    "restricted": 60,
    "secret": 30,
}


def confidence_to_level(score: float) -> ConfidenceLevel:
    """Map a numeric confidence score to a confidence level."""
    if score >= 0.95:
        return ConfidenceLevel.VERIFIED
    elif score >= 0.80:
        return ConfidenceLevel.HIGH
    elif score >= 0.50:
        return ConfidenceLevel.MEDIUM
    elif score >= 0.20:
        return ConfidenceLevel.LOW
    return ConfidenceLevel.UNCERTAIN


@dataclass
class Provenance:
    """
    Record documenting the origin and trustworthiness of a fact.

    Every entity and relationship in the graph must have at least one
    provenance record. Multiple records can be chained for facts that
    have been verified or updated through different sources.

    Attributes:
        id: Unique provenance record ID.
        source: Description or identifier of the information source.
        source_type: Classification from SourceType enum.
        author: Identity of the person/system that created this record.
        creation_date: When this provenance record was created.
        last_verified: When the fact was last independently verified.
        confidence: Numeric score 0.0-1.0.
        confidence_level: Derived tier from confidence score.
        classification: Data classification (public, internal, confidential, etc.).
        version: Version of the fact this provenance applies to.
        project: Project context.
        expiration: Date after which this fact is considered stale.
        parent_provenance_id: For chained provenance (linking to a prior record).
        evidence_hash: Content hash of the evidence/source data.
        evidence_url: Optional URL to the source evidence.
        metadata: Arbitrary extensions.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source: str = ""
    source_type: SourceType = SourceType.USER_INPUT
    author: str = ""
    creation_date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_verified: Optional[datetime] = None
    confidence: float = 0.5
    confidence_level: ConfidenceLevel = ConfidenceLevel.MEDIUM
    classification: str = "internal"
    version: int = 1
    project: str = ""
    expiration: Optional[datetime] = None
    parent_provenance_id: Optional[str] = None
    evidence_hash: str = ""
    evidence_url: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Auto-derive confidence level and set defaults."""
        self.confidence = max(0.0, min(1.0, self.confidence))
        self.confidence_level = confidence_to_level(self.confidence)

        if self.expiration is None:
            days = DEFAULT_EXPIRATION_DAYS.get(self.classification, 180)
            self.expiration = self.creation_date + timedelta(days=days)

        if not self.evidence_hash and self.source:
            self.evidence_hash = hashlib.sha256(
                f"{self.source}:{self.source_type.value}:{self.creation_date.isoformat()}".encode()
            ).hexdigest()[:16]

    @property
    def is_expired(self) -> bool:
        """Check if this fact has passed its expiration date."""
        if self.expiration is None:
            return False
        return datetime.now(timezone.utc) > self.expiration

    @property
    def needs_verification(self) -> bool:
        """Check if this fact needs re-verification (never verified or near expiry)."""
        if self.last_verified is None:
            return True
        # Re-verify if it's been more than half the expiration window
        if self.expiration:
            window = self.expiration - self.creation_date
            half_window = window / 2
            return datetime.now(timezone.utc) > (self.last_verified + half_window)
        return False

    def verify(self, verifier: str = "", new_confidence: Optional[float] = None) -> Provenance:
        """
        Create a new provenance record verifying this one.
        Returns the child provenance (chain link).
        """
        child = Provenance(
            source=f"Verification by {verifier}" if verifier else "Independent verification",
            source_type=SourceType.EXPERT_REVIEW,
            author=verifier,
            confidence=new_confidence if new_confidence is not None else min(1.0, self.confidence + 0.15),
            classification=self.classification,
            version=self.version + 1,
            project=self.project,
            parent_provenance_id=self.id,
            last_verified=datetime.now(timezone.utc),
            metadata={"verified_from": self.id, **self.metadata},
        )
        return child

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "source": self.source,
            "source_type": self.source_type.value,
            "author": self.author,
            "creation_date": self.creation_date.isoformat(),
            "last_verified": self.last_verified.isoformat() if self.last_verified else None,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level.value,
            "classification": self.classification,
            "version": self.version,
            "project": self.project,
            "expiration": self.expiration.isoformat() if self.expiration else None,
            "parent_provenance_id": self.parent_provenance_id,
            "evidence_hash": self.evidence_hash,
            "evidence_url": self.evidence_url,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Provenance":
        """Deserialize from dictionary."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            source=data.get("source", ""),
            source_type=SourceType(data.get("source_type", "user_input")),
            author=data.get("author", ""),
            creation_date=datetime.fromisoformat(data["creation_date"]) if data.get("creation_date") else datetime.now(timezone.utc),
            last_verified=datetime.fromisoformat(data["last_verified"]) if data.get("last_verified") else None,
            confidence=data.get("confidence", 0.5),
            classification=data.get("classification", "internal"),
            version=data.get("version", 1),
            project=data.get("project", ""),
            expiration=datetime.fromisoformat(data["expiration"]) if data.get("expiration") else None,
            parent_provenance_id=data.get("parent_provenance_id"),
            evidence_hash=data.get("evidence_hash", ""),
            evidence_url=data.get("evidence_url", ""),
            metadata=data.get("metadata", {}),
        )

    def __repr__(self) -> str:
        return (
            f"Provenance(id={self.id!r}, source={self.source!r}, "
            f"confidence={self.confidence:.2f}, level={self.confidence_level.value})"
        )


class ProvenanceChain:
    """
    Tracks the full provenance lineage of a fact.

    Supports chaining: when a fact is verified, updated, or re-sourced,
    the new provenance links back to the previous one, forming an
    immutable audit trail.
    """

    def __init__(self, root_provenance: Provenance) -> None:
        self._chain: Dict[str, Provenance] = {}
        self._root_id = root_provenance.id
        self._add(root_provenance)

    def _add(self, prov: Provenance) -> None:
        """Internal: add a provenance record to the chain."""
        self._chain[prov.id] = prov

    def append(self, prov: Provenance) -> None:
        """Add a child provenance. Sets parent if not already set."""
        if prov.parent_provenance_id is None:
            latest = self.latest()
            if latest:
                prov.parent_provenance_id = latest.id
        self._add(prov)

    def get(self, prov_id: str) -> Optional[Provenance]:
        """Retrieve a specific provenance record by ID."""
        return self._chain.get(prov_id)

    def root(self) -> Provenance:
        """Get the root (original) provenance record."""
        return self._chain[self._root_id]

    def latest(self) -> Provenance:
        """Get the most recent provenance record in the chain."""
        # Walk the chain to find the leaf
        current = self._chain[self._root_id]
        while True:
            children = [
                p for p in self._chain.values()
                if p.parent_provenance_id == current.id
            ]
            if not children:
                return current
            current = children[0]  # Take the first child (linear chain)

    def lineage(self) -> List[Provenance]:
        """Return the full chain from root to latest in order."""
        result: List[Provenance] = []
        current: Optional[Provenance] = self._chain[self._root_id]
        seen: set = set()
        while current is not None and current.id not in seen:
            result.append(current)
            seen.add(current.id)
            # Find child
            children = [
                p for p in self._chain.values()
                if p.parent_provenance_id == current.id  # type: ignore[union-attr]
            ]
            current = children[0] if children else None
        return result

    def aggregate_confidence(self) -> float:
        """
        Compute aggregate confidence across the chain.

        Recent verifications boost confidence; stale records degrade it.
        Returns a score 0.0-1.0.
        """
        lineage = self.lineage()
        if not lineage:
            return 0.0

        # Weighted: latest records have more weight
        total_weight = 0.0
        weighted_sum = 0.0
        n = len(lineage)
        for i, prov in enumerate(lineage):
            # Weight increases for more recent entries
            weight = (i + 1) / n
            # Penalize expired records
            if prov.is_expired:
                weight *= 0.5
            total_weight += weight
            weighted_sum += prov.confidence * weight

        return weighted_sum / total_weight if total_weight > 0 else 0.0

    def has_verification(self) -> bool:
        """Check if any record in the chain has been independently verified."""
        return any(p.last_verified is not None for p in self._chain.values())

    def __len__(self) -> int:
        return len(self._chain)

    def __repr__(self) -> str:
        return f"ProvenanceChain(root={self._root_id!r}, length={len(self)})"