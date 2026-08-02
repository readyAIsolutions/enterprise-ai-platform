"""
Research domain tracking and library management.

Tracks research across multiple domains, maintains a searchable library,
and provides trend analysis and maturity assessments.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger("enterprise.innovation_rd.research")


class ResearchDomain(Enum):
    """Primary research domains tracked by the Innovation R&D OS."""

    AI_MODELS = "ai_models"
    AGENT_ARCHITECTURES = "agent_architectures"
    MODEL_ROUTING = "model_routing"
    RAG = "rag"
    MEMORY = "memory"
    KNOWLEDGE_GRAPHS = "knowledge_graphs"
    MULTIMODAL = "multimodal"
    EDGE_AI = "edge_ai"
    PRIVACY_PRESERVING = "privacy_preserving"
    CONFIDENTIAL_COMPUTING = "confidential_computing"
    POST_QUANTUM_CRYPTO = "post_quantum_crypto"
    DISTRIBUTED_SYSTEMS = "distributed_systems"
    DATABASES = "databases"
    TOOLS = "tools"
    SECURITY = "security"
    HCI = "hci"
    AUTOMATION = "automation"
    COMPRESSION = "compression"
    INFERENCE_OPTIMIZATION = "inference_optimization"


class MaturityLevel(Enum):
    """Maturity assessment of a research finding or technology."""

    EMERGING = "emerging"
    EXPERIMENTAL = "experimental"
    PROVEN = "proven"
    MATURE = "mature"
    DECLINING = "declining"
    UNKNOWN = "unknown"


@dataclass
class ResearchEntry:
    """A single research entry in the R&D library.

    Each entry captures a research finding, paper, article, or observation
    with full metadata for searchability and trend analysis.

    Attributes:
        domain: Primary research domain.
        title: Descriptive title.
        source: Origin of the finding (URL, paper DOI, internal report ref).
        summary: Concise summary of the finding.
        findings: Detailed findings or key takeaways.
        maturity: Assessed maturity level.
        relevance: Relevance score (0.0 to 1.0).
        date: Date of discovery or publication.
        tags: Optional list of tags for categorization.
        authors: Optional list of authors.
        related_entries: Optional list of related entry IDs.
        entry_id: Unique identifier (auto-generated if not provided).
    """

    domain: ResearchDomain
    title: str
    source: str
    summary: str
    findings: str
    maturity: MaturityLevel = MaturityLevel.UNKNOWN
    relevance: float = 0.5
    date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tags: List[str] = field(default_factory=list)
    authors: List[str] = field(default_factory=list)
    related_entries: List[str] = field(default_factory=list)
    entry_id: str = ""

    def __post_init__(self) -> None:
        if not self.entry_id:
            self.entry_id = f"{self.domain.value}-{self.date.strftime('%Y%m%d%H%M%S')}"

    def to_dict(self) -> dict:
        """Serialize the entry to a dictionary."""
        return {
            "entry_id": self.entry_id,
            "domain": self.domain.value,
            "title": self.title,
            "source": self.source,
            "summary": self.summary,
            "findings": self.findings,
            "maturity": self.maturity.value,
            "relevance": self.relevance,
            "date": self.date.isoformat(),
            "tags": self.tags,
            "authors": self.authors,
            "related_entries": self.related_entries,
        }


@dataclass
class ResearchLibrary:
    """Manages a collection of research entries with search and analysis.

    The library is the primary knowledge base for the Innovation R&D OS,
    supporting keyword/domain search, trend analysis, and maturity scoring.
    """

    entries: Dict[str, ResearchEntry] = field(default_factory=dict)
    name: str = "default"

    def add_entry(self, entry: ResearchEntry) -> str:
        """Add a research entry to the library.

        Args:
            entry: The ResearchEntry to add.

        Returns:
            The entry_id of the added entry.
        """
        self.entries[entry.entry_id] = entry
        logger.info(
            "Added research entry '%s' in domain %s", entry.title, entry.domain.value
        )
        return entry.entry_id

    def remove_entry(self, entry_id: str) -> bool:
        """Remove an entry by ID.

        Args:
            entry_id: The entry ID to remove.

        Returns:
            True if removed, False if not found.
        """
        if entry_id in self.entries:
            del self.entries[entry_id]
            logger.info("Removed research entry %s", entry_id)
            return True
        logger.warning("Research entry %s not found for removal", entry_id)
        return False

    def get_entry(self, entry_id: str) -> Optional[ResearchEntry]:
        """Retrieve a single entry by ID."""
        return self.entries.get(entry_id)

    def search_by_domain(
        self, domain: ResearchDomain, min_relevance: float = 0.0
    ) -> List[ResearchEntry]:
        """Retrieve all entries in a given domain.

        Args:
            domain: The ResearchDomain to filter by.
            min_relevance: Minimum relevance score threshold.

        Returns:
            List of matching ResearchEntry objects, sorted by relevance descending.
        """
        results = [
            e
            for e in self.entries.values()
            if e.domain == domain and e.relevance >= min_relevance
        ]
        results.sort(key=lambda e: e.relevance, reverse=True)
        logger.debug("Domain search for %s returned %d results", domain.value, len(results))
        return results

    def search_by_keyword(self, keyword: str) -> List[ResearchEntry]:
        """Search entries by keyword across title, summary, findings, and tags.

        Args:
            keyword: Case-insensitive search term.

        Returns:
            List of matching ResearchEntry objects sorted by relevance descending.
        """
        kw = keyword.lower()
        results = [
            e
            for e in self.entries.values()
            if kw in e.title.lower()
            or kw in e.summary.lower()
            or kw in e.findings.lower()
            or any(kw in tag.lower() for tag in e.tags)
        ]
        results.sort(key=lambda e: e.relevance, reverse=True)
        logger.debug("Keyword search for '%s' returned %d results", keyword, len(results))
        return results

    def get_trends(self, domain: Optional[ResearchDomain] = None) -> Dict[MaturityLevel, int]:
        """Analyze maturity distribution to identify trends.

        Args:
            domain: Optional domain filter. If None, analyzes all entries.

        Returns:
            Dictionary mapping MaturityLevel to count of entries at that level.
        """
        entries = (
            self.search_by_domain(domain) if domain else list(self.entries.values())
        )
        distribution: Dict[MaturityLevel, int] = {m: 0 for m in MaturityLevel}
        for entry in entries:
            distribution[entry.maturity] += 1
        logger.info("Trend analysis complete: %s", distribution)
        return distribution

    def assess_maturity(self, entry_id: str) -> MaturityLevel:
        """Assess and return the maturity level of a specific entry.

        Args:
            entry_id: The entry to assess.

        Returns:
            The MaturityLevel of the entry, or UNKNOWN if not found.
        """
        entry = self.get_entry(entry_id)
        if entry is None:
            logger.warning("Cannot assess maturity: entry %s not found", entry_id)
            return MaturityLevel.UNKNOWN
        return entry.maturity

    def get_recent_entries(
        self, days: int = 30, limit: int = 50
    ) -> List[ResearchEntry]:
        """Retrieve entries from the last N days.

        Args:
            days: Number of days to look back.
            limit: Maximum entries to return.

        Returns:
            List of recent ResearchEntry objects, newest first.
        """
        cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
        recent = [e for e in self.entries.values() if e.date.timestamp() >= cutoff]
        recent.sort(key=lambda e: e.date, reverse=True)
        logger.debug("Retrieved %d recent entries (within %d days)", len(recent), days)
        return recent[:limit]

    def stats(self) -> dict:
        """Return summary statistics for the library."""
        domains = {}
        for e in self.entries.values():
            domains[e.domain.value] = domains.get(e.domain.value, 0) + 1
        return {
            "total_entries": len(self.entries),
            "domains": domains,
            "avg_relevance": (
                sum(e.relevance for e in self.entries.values()) / max(len(self.entries), 1)
            ),
        }

    def __len__(self) -> int:
        return len(self.entries)