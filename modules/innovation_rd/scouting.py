"""
Technology scouting engine.

Scans, ranks, and tracks emerging technologies, standards, OSS projects,
papers, models, security developments, regulations, competitors, patents,
and vendor risks across multiple target domains.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger("enterprise.innovation_rd.scouting")


class ScoutTarget(Enum):
    """Target categories for technology scouting."""

    STANDARDS = "standards"
    OSS_PROJECTS = "oss_projects"
    PAPERS = "papers"
    MODELS = "models"
    SECURITY = "security"
    REGULATIONS = "regulations"
    COMPETITORS = "competitors"
    PATENTS = "patents"
    VENDOR_RISK = "vendor_risk"
    MATURITY = "maturity"


class ScoutStatus(Enum):
    """Status of a scouted finding."""

    NEW = "new"
    MONITORING = "monitoring"
    EVALUATING = "evaluating"
    ADOPTED = "adopted"
    DISMISSED = "dismissed"
    ARCHIVED = "archived"


class RiskLevel(Enum):
    """Risk level of a scouted finding."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


@dataclass
class ScoutEntry:
    """A single scouting finding.

    Attributes:
        target: The scout target category.
        name: Short name of the finding.
        description: Detailed description.
        source_url: URL of the source.
        discovered_date: When the finding was discovered.
        relevance_score: Relevance (0.0 to 1.0).
        risk_level: Assessed risk level.
        status: Current tracking status.
        tags: Optional tags for categorization.
        entry_id: Unique identifier (auto-generated).
    """

    target: ScoutTarget
    name: str
    description: str
    source_url: str = ""
    discovered_date: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    relevance_score: float = 0.5
    risk_level: RiskLevel = RiskLevel.MEDIUM
    status: ScoutStatus = ScoutStatus.NEW
    tags: List[str] = field(default_factory=list)
    entry_id: str = ""

    def __post_init__(self) -> None:
        if not self.entry_id:
            self.entry_id = f"scout-{uuid4().hex[:12]}"

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "entry_id": self.entry_id,
            "target": self.target.value,
            "name": self.name,
            "description": self.description,
            "source_url": self.source_url,
            "discovered_date": self.discovered_date.isoformat(),
            "relevance_score": self.relevance_score,
            "risk_level": self.risk_level.value,
            "status": self.status.value,
            "tags": self.tags,
        }


@dataclass
class ScoutEngine:
    """Technology scouting engine for discovering and tracking technologies.

    Scans across multiple target domains, ranks findings by relevance,
    assesses risk, generates reports, and tracks emerging technologies.
    """

    entries: Dict[str, ScoutEntry] = field(default_factory=dict)
    name: str = "default"

    def scan(
        self,
        target: ScoutTarget,
        query: str = "",
        min_relevance: float = 0.5,
        limit: int = 20,
    ) -> List[ScoutEntry]:
        """Scan for technologies matching a target category and query.

        In production, this would query external APIs, RSS feeds, and databases.
        Here we search the existing entries collection.

        Args:
            target: ScoutTarget category to scan.
            query: Optional search query string.
            min_relevance: Minimum relevance score filter.
            limit: Maximum results to return.

        Returns:
            List of matching ScoutEntry objects, sorted by relevance descending.
        """
        results = [
            e
            for e in self.entries.values()
            if e.target == target and e.relevance_score >= min_relevance
        ]

        if query:
            q = query.lower()
            results = [
                e
                for e in results
                if q in e.name.lower()
                or q in e.description.lower()
                or any(q in tag.lower() for tag in e.tags)
            ]

        results.sort(key=lambda e: e.relevance_score, reverse=True)
        logger.info(
            "Scan for target=%s query='%s': %d results",
            target.value,
            query,
            len(results),
        )
        return results[:limit]

    def add_finding(self, entry: ScoutEntry) -> str:
        """Add a scouting finding to the engine.

        Args:
            entry: The ScoutEntry to add.

        Returns:
            The entry_id of the added finding.
        """
        self.entries[entry.entry_id] = entry
        logger.info(
            "Added scout finding '%s' (target=%s, risk=%s)",
            entry.name,
            entry.target.value,
            entry.risk_level.value,
        )
        return entry.entry_id

    def rank_by_relevance(
        self, target: Optional[ScoutTarget] = None
    ) -> List[ScoutEntry]:
        """Rank all findings (or within a target) by relevance score.

        Args:
            target: Optional ScoutTarget to filter by.

        Returns:
            List of ScoutEntry objects sorted by relevance descending.
        """
        entries = (
            [e for e in self.entries.values() if e.target == target]
            if target
            else list(self.entries.values())
        )
        entries.sort(key=lambda e: e.relevance_score, reverse=True)
        logger.debug("Ranked %d entries by relevance", len(entries))
        return entries

    def assess_risk(self, entry_id: str) -> RiskLevel:
        """Assess the risk level of a specific scouting finding.

        Re-evaluates and updates the risk level based on current context.

        Args:
            entry_id: The ScoutEntry ID to assess.

        Returns:
            The assessed RiskLevel.
        """
        entry = self.entries.get(entry_id)
        if entry is None:
            logger.warning("Cannot assess risk: entry %s not found", entry_id)
            return RiskLevel.NONE

        # Risk assessment heuristics
        new_risk = entry.risk_level

        # High-risk targets get elevated risk
        high_risk_targets = {ScoutTarget.SECURITY, ScoutTarget.VENDOR_RISK}
        if entry.target in high_risk_targets and entry.risk_level == RiskLevel.LOW:
            new_risk = RiskLevel.MEDIUM

        # High relevance + competitor = elevated risk
        if (
            entry.target == ScoutTarget.COMPETITORS
            and entry.relevance_score > 0.8
        ):
            if entry.risk_level in (RiskLevel.MEDIUM, RiskLevel.LOW):
                new_risk = RiskLevel.HIGH

        if new_risk != entry.risk_level:
            logger.info(
                "Risk level for '%s' reassessed: %s -> %s",
                entry.name,
                entry.risk_level.value,
                new_risk.value,
            )
            entry.risk_level = new_risk

        return entry.risk_level

    def generate_report(
        self, target: Optional[ScoutTarget] = None
    ) -> Dict[str, any]:
        """Generate a scouting report.

        Args:
            target: Optional ScoutTarget to filter the report.

        Returns:
            Dictionary with summary statistics and ranked findings.
        """
        entries = (
            [e for e in self.entries.values() if e.target == target]
            if target
            else list(self.entries.values())
        )

        risk_counts: Dict[str, int] = {}
        status_counts: Dict[str, int] = {}
        for e in entries:
            risk_counts[e.risk_level.value] = risk_counts.get(e.risk_level.value, 0) + 1
            status_counts[e.status.value] = status_counts.get(e.status.value, 0) + 1

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "target_filter": target.value if target else "all",
            "total_findings": len(entries),
            "risk_distribution": risk_counts,
            "status_distribution": status_counts,
            "average_relevance": (
                sum(e.relevance_score for e in entries) / max(len(entries), 1)
            ),
            "top_findings": [
                e.to_dict()
                for e in sorted(
                    entries, key=lambda x: x.relevance_score, reverse=True
                )[:10]
            ],
        }
        logger.info("Generated scouting report with %d findings", len(entries))
        return report

    def track_emerging(self, days: int = 90) -> List[ScoutEntry]:
        """Track emerging technologies discovered within recent days.

        Args:
            days: Lookback window in days.

        Returns:
            List of recently discovered ScoutEntry objects.
        """
        cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
        emerging = [
            e
            for e in self.entries.values()
            if e.discovered_date.timestamp() >= cutoff
            and e.status in (ScoutStatus.NEW, ScoutStatus.MONITORING)
        ]
        emerging.sort(key=lambda e: e.relevance_score, reverse=True)
        logger.info(
            "Tracked %d emerging technologies (within %d days)", len(emerging), days
        )
        return emerging

    def update_status(self, entry_id: str, new_status: ScoutStatus) -> bool:
        """Update the status of a scouting entry.

        Args:
            entry_id: The entry to update.
            new_status: The new ScoutStatus.

        Returns:
            True if updated, False if not found.
        """
        entry = self.entries.get(entry_id)
        if entry is None:
            logger.warning("Cannot update status: entry %s not found", entry_id)
            return False
        old_status = entry.status
        entry.status = new_status
        logger.info(
            "Updated entry '%s' status: %s -> %s",
            entry.name,
            old_status.value,
            new_status.value,
        )
        return True

    def get_stats(self) -> dict:
        """Return summary statistics for the scouting engine."""
        targets = {}
        for e in self.entries.values():
            targets[e.target.value] = targets.get(e.target.value, 0) + 1
        return {
            "total_entries": len(self.entries),
            "by_target": targets,
            "high_risk_count": sum(
                1 for e in self.entries.values()
                if e.risk_level in (RiskLevel.CRITICAL, RiskLevel.HIGH)
            ),
        }