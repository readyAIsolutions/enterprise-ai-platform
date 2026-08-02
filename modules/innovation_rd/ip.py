"""
Intellectual Property (IP) management.

Manages patentable inventions, proprietary datasets, unique workflows,
trade secrets, novel architectures, and licensing obligations.
Provides registration, patentability checking, licensing tracking,
novelty assessment, disclosure generation, and trade secret maintenance.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger("enterprise.innovation_rd.ip")


class IPCategory(Enum):
    """Categories of intellectual property."""

    PATENTABLE_INVENTION = "patentable_invention"
    PROPRIETARY_DATASET = "proprietary_dataset"
    UNIQUE_WORKFLOW = "unique_workflow"
    TRADE_SECRET = "trade_secret"
    NOVEL_ARCHITECTURE = "novel_architecture"
    LICENSING_OBLIGATION = "licensing_obligation"


class IPStatus(Enum):
    """Status of an IP entry."""

    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    DISCLOSED = "disclosed"
    PATENT_PENDING = "patent_pending"
    PATENT_GRANTED = "patent_granted"
    LICENSED = "licensed"
    TRADE_SECRET = "trade_secret"
    ABANDONED = "abandoned"
    EXPIRED = "expired"


@dataclass
class IPEntry:
    """A single IP asset entry.

    Attributes:
        category: The type of IP.
        title: Title of the IP asset.
        description: Detailed description.
        inventors: List of inventor names.
        date_created: When the IP was first documented.
        status: Current IP status.
        disclosure_date: Date of public disclosure (if any).
        patent_filing: Patent filing number or reference.
        license_terms: Licensing terms description.
        ip_id: Unique identifier (auto-generated).
        related_modules: Modules or components this IP relates to.
        notes: Additional notes.
    """

    category: IPCategory
    title: str
    description: str
    inventors: List[str] = field(default_factory=list)
    date_created: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: IPStatus = IPStatus.DRAFT
    disclosure_date: Optional[datetime] = None
    patent_filing: str = ""
    license_terms: str = ""
    ip_id: str = ""
    related_modules: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.ip_id:
            self.ip_id = f"ip-{uuid4().hex[:12]}"

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "ip_id": self.ip_id,
            "category": self.category.value,
            "title": self.title,
            "description": self.description,
            "inventors": self.inventors,
            "date_created": self.date_created.isoformat(),
            "status": self.status.value,
            "disclosure_date": self.disclosure_date.isoformat()
            if self.disclosure_date
            else None,
            "patent_filing": self.patent_filing,
            "license_terms": self.license_terms,
            "related_modules": self.related_modules,
            "notes": self.notes,
        }


@dataclass
class IPManager:
    """Manages the full IP lifecycle.

    Handles registration, patentability assessment, licensing tracking,
    novelty assessment, disclosure generation, and trade secret maintenance.
    """

    assets: Dict[str, IPEntry] = field(default_factory=dict)

    def register_invention(
        self,
        category: IPCategory,
        title: str,
        description: str,
        inventors: Optional[List[str]] = None,
        related_modules: Optional[List[str]] = None,
        status: IPStatus = IPStatus.DRAFT,
        license_terms: str = "",
        disclosure_date: Optional[datetime] = None,
    ) -> IPEntry:
        """Register a new invention or IP asset.

        Args:
            category: IP category.
            title: Title of the invention.
            description: Detailed description.
            inventors: List of inventor names.
            related_modules: Modules this IP relates to.
            status: Initial IP status.
            license_terms: License terms if applicable.
            disclosure_date: Disclosure date if already disclosed.

        Returns:
            The newly created IPEntry.
        """
        entry = IPEntry(
            category=category,
            title=title,
            description=description,
            inventors=inventors or [],
            related_modules=related_modules or [],
            status=status,
            license_terms=license_terms,
            disclosure_date=disclosure_date,
        )
        self.assets[entry.ip_id] = entry
        logger.info(
            "Registered IP '%s' (category=%s, inventors=%d)",
            title,
            category.value,
            len(inventors or []),
        )
        return entry

    def check_patentability(self, ip_id: str) -> Dict[str, Any]:
        """Assess patentability of an IP asset.

        Evaluates novelty, non-obviousness, and utility. In production, this
        would integrate with patent databases and prior-art search tools.

        Args:
            ip_id: The IP asset to check.

        Returns:
            Dictionary with patentability assessment results.
        """
        entry = self.assets.get(ip_id)
        if entry is None:
            logger.error("Cannot check patentability: IP %s not found", ip_id)
            return {"ip_id": ip_id, "patentable": False, "reason": "not_found"}

        issues: List[str] = []

        patentable_categories = {
            IPCategory.PATENTABLE_INVENTION,
            IPCategory.NOVEL_ARCHITECTURE,
            IPCategory.UNIQUE_WORKFLOW,
        }
        if entry.category not in patentable_categories:
            issues.append(
                f"Category '{entry.category.value}' is not typically patentable"
            )

        if len(entry.description) < 100:
            issues.append("Description too short for patent filing")

        if entry.disclosure_date is not None:
            days_since_disclosure = (
                datetime.now(timezone.utc) - entry.disclosure_date
            ).days
            if days_since_disclosure > 365:
                issues.append(
                    f"Publicly disclosed {days_since_disclosure} days ago; "
                    "may have exceeded grace period"
                )

        if not entry.inventors:
            issues.append("No inventors listed")

        assessment = {
            "ip_id": ip_id,
            "patentable": len(issues) == 0,
            "issues": issues,
            "recommendation": (
                "Proceed with patent filing"
                if len(issues) == 0
                else f"Address {len(issues)} issues before filing"
            ),
        }
        logger.info(
            "Patentability check for %s: patentable=%s, issues=%d",
            ip_id,
            assessment["patentable"],
            len(issues),
        )
        return assessment

    def track_licensing(self, ip_id: str) -> Dict[str, Any]:
        """Track licensing status and obligations for an IP asset.

        Args:
            ip_id: The IP asset to track.

        Returns:
            Dictionary with licensing tracking information.
        """
        entry = self.assets.get(ip_id)
        if entry is None:
            logger.error("Cannot track licensing: IP %s not found", ip_id)
            return {"ip_id": ip_id, "found": False}

        tracking = {
            "ip_id": ip_id,
            "found": True,
            "title": entry.title,
            "status": entry.status.value,
            "has_license_terms": bool(entry.license_terms),
            "license_terms": entry.license_terms if entry.license_terms else None,
            "is_licensed": entry.status == IPStatus.LICENSED,
            "category": entry.category.value,
        }

        if entry.category == IPCategory.LICENSING_OBLIGATION:
            tracking["warning"] = (
                "This asset carries third-party licensing obligations. "
                "Ensure compliance with all license terms."
            )

        logger.debug(
            "Licensing tracked for %s: licensed=%s", ip_id, tracking["is_licensed"]
        )
        return tracking

    def assess_novelty(self, ip_id: str) -> Dict[str, Any]:
        """Assess the novelty of an IP asset.

        Evaluates uniqueness of the described invention compared to known
        prior art in the internal repository.

        Args:
            ip_id: The IP asset to assess.

        Returns:
            Dictionary with novelty assessment results.
        """
        entry = self.assets.get(ip_id)
        if entry is None:
            logger.error("Cannot assess novelty: IP %s not found", ip_id)
            return {"ip_id": ip_id, "novel": False, "reason": "not_found"}

        novelty_score: float = 1.0
        concerns: List[str] = []

        same_category = [
            a
            for aid, a in self.assets.items()
            if a.category == entry.category and aid != ip_id
        ]

        if len(same_category) > 0:
            entry_words = set(entry.description.lower().split())
            for other in same_category:
                other_words = set(other.description.lower().split())
                union_size = max(len(entry_words | other_words), 1)
                overlap = len(entry_words & other_words) / union_size
                if overlap > 0.5:
                    concerns.append(
                        f"High similarity ({overlap:.0%}) with existing asset "
                        f"'{other.title}' ({other.ip_id})"
                    )
                    novelty_score = min(novelty_score, 1.0 - overlap)

        if len(entry.description) < 50:
            concerns.append("Description too brief to establish novelty")
            novelty_score = min(novelty_score, 0.5)

        assessment = {
            "ip_id": ip_id,
            "title": entry.title,
            "novelty_score": round(novelty_score, 3),
            "is_novel": novelty_score >= 0.6,
            "concerns": concerns,
            "total_similar_assets": len(same_category),
        }
        logger.info(
            "Novelty assessment for %s: score=%s, novel=%s",
            ip_id,
            assessment["novelty_score"],
            assessment["is_novel"],
        )
        return assessment

    def generate_disclosure(self, ip_id: str) -> Optional[Dict[str, Any]]:
        """Generate an invention disclosure document.

        Produces a structured disclosure with all relevant IP information
        suitable for legal review and patent filing preparation.

        Args:
            ip_id: The IP asset to disclose.

        Returns:
            Dictionary with the disclosure document, or None if not found.
        """
        entry = self.assets.get(ip_id)
        if entry is None:
            logger.error("Cannot generate disclosure: IP %s not found", ip_id)
            return None

        disclosure = {
            "disclosure_id": f"DISCL-{entry.ip_id}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "title": entry.title,
            "inventors": entry.inventors,
            "category": entry.category.value,
            "date_of_invention": entry.date_created.isoformat(),
            "description": entry.description,
            "related_modules": entry.related_modules,
            "patent_filing": entry.patent_filing or "Not yet filed",
            "novelty_assessment": self.assess_novelty(ip_id),
            "patentability": self.check_patentability(ip_id),
            "status": entry.status.value,
            "notes": entry.notes,
        }

        if entry.status == IPStatus.DRAFT:
            entry.status = IPStatus.DISCLOSED
            entry.disclosure_date = datetime.now(timezone.utc)

        logger.info("Generated disclosure for IP %s (%s)", ip_id, entry.title)
        return disclosure

    def maintain_trade_secret(self, ip_id: str) -> Dict[str, Any]:
        """Maintain trade secret protections for an IP asset.

        Validates that trade secret safeguards are in place, including
        access controls, documentation, and non-disclosure measures.

        Args:
            ip_id: The IP asset to maintain as trade secret.

        Returns:
            Dictionary with trade secret maintenance status.
        """
        entry = self.assets.get(ip_id)
        if entry is None:
            logger.error("Cannot maintain trade secret: IP %s not found", ip_id)
            return {"ip_id": ip_id, "maintained": False, "reason": "not_found"}

        if entry.category != IPCategory.TRADE_SECRET:
            logger.warning(
                "IP %s is not classified as TRADE_SECRET (is %s)",
                ip_id,
                entry.category.value,
            )

        warnings_list: List[str] = []

        maintenance: Dict[str, Any] = {
            "ip_id": ip_id,
            "maintained": True,
            "title": entry.title,
            "status": entry.status.value,
            "access_controlled": entry.status in (
                IPStatus.TRADE_SECRET,
                IPStatus.DRAFT,
                IPStatus.UNDER_REVIEW,
            ),
            "has_inventors": len(entry.inventors) > 0,
            "warnings": warnings_list,
        }

        if not entry.inventors:
            warnings_list.append(
                "No inventors listed; access control surface unclear"
            )

        if entry.status == IPStatus.DISCLOSED:
            warnings_list.append(
                "Asset has been disclosed; trade secret protection may be compromised"
            )
            maintenance["maintained"] = False

        if entry.disclosure_date is not None:
            warnings_list.append(
                f"Asset was disclosed on {entry.disclosure_date.isoformat()}; "
                "trade secret status may be void"
            )
            maintenance["maintained"] = False

        if entry.status == IPStatus.DRAFT and entry.category == IPCategory.TRADE_SECRET:
            entry.status = IPStatus.TRADE_SECRET

        logger.info(
            "Trade secret maintenance for %s: maintained=%s",
            ip_id,
            maintenance["maintained"],
        )
        return maintenance

    def get_asset(self, ip_id: str) -> Optional[IPEntry]:
        """Retrieve an IP asset by ID."""
        return self.assets.get(ip_id)

    def list_by_category(self, category: IPCategory) -> List[IPEntry]:
        """List all IP assets in a given category."""
        return [a for a in self.assets.values() if a.category == category]

    def list_by_status(self, status: IPStatus) -> List[IPEntry]:
        """List all IP assets with a given status."""
        return [a for a in self.assets.values() if a.status == status]

    def get_stats(self) -> dict:
        """Return summary statistics for the IP portfolio."""
        categories: Dict[str, int] = {}
        statuses: Dict[str, int] = {}
        for a in self.assets.values():
            categories[a.category.value] = categories.get(a.category.value, 0) + 1
            statuses[a.status.value] = statuses.get(a.status.value, 0) + 1
        return {
            "total_assets": len(self.assets),
            "by_category": categories,
            "by_status": statuses,
        }