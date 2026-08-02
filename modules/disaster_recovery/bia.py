"""
Business Impact Analysis (BIA) engine.

Identifies, classifies, and prioritizes services by criticality, financial exposure,
and dependency chains to inform recovery prioritization.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger("enterprise.disaster_recovery.bia")


class CriticalityLevel(str, Enum):
    """Service criticality classification."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ImpactCategory(str, Enum):
    """Types of impact a service disruption can cause."""

    FINANCIAL = "financial"
    LEGAL = "legal"
    CUSTOMER = "customer"
    SAFETY = "safety"
    REPUTATIONAL = "reputational"
    OPERATIONAL = "operational"


@dataclass
class BIAAsset:
    """A single asset (service, system, or component) under BIA assessment."""

    name: str
    service_type: str
    criticality: CriticalityLevel
    max_downtime_hours: float
    financial_impact_per_hour: float = 0.0
    legal_risk: bool = False
    customer_impact: bool = False
    safety_impact: bool = False
    dependencies: List[str] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)
    assessed_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        if self.assessed_at is None:
            self.assessed_at = datetime.utcnow()

    @property
    def annual_financial_risk(self) -> float:
        """Estimated annual financial exposure at max downtime."""
        return self.financial_impact_per_hour * self.max_downtime_hours * 365

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "service_type": self.service_type,
            "criticality": self.criticality.value,
            "max_downtime_hours": self.max_downtime_hours,
            "financial_impact_per_hour": self.financial_impact_per_hour,
            "legal_risk": self.legal_risk,
            "customer_impact": self.customer_impact,
            "safety_impact": self.safety_impact,
            "dependencies": self.dependencies,
            "annual_financial_risk": self.annual_financial_risk,
        }


class BIAEngine:
    """
    Business Impact Analysis engine.

    Assesses services, calculates financial exposure, maps dependency chains,
    and generates prioritized recovery recommendations.
    """

    # Severity scoring matrix: (legal, customer, safety) -> weight multiplier
    _SEVERITY_WEIGHTS: Dict[Tuple[bool, bool, bool], float] = {
        (True, True, True): 5.0,
        (True, True, False): 4.0,
        (True, False, True): 4.5,
        (False, True, True): 4.5,
        (True, False, False): 3.0,
        (False, True, False): 2.5,
        (False, False, True): 3.5,
        (False, False, False): 1.0,
    }

    def __init__(self) -> None:
        self._assets: Dict[str, BIAAsset] = {}

    # ------------------------------------------------------------------
    # Asset management
    # ------------------------------------------------------------------

    def assess_service(
        self,
        name: str,
        service_type: str,
        max_downtime_hours: float,
        financial_impact_per_hour: float = 0.0,
        legal_risk: bool = False,
        customer_impact: bool = False,
        safety_impact: bool = False,
        dependencies: Optional[List[str]] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> BIAAsset:
        """Register and assess a service; returns the BIAAsset with auto-determined criticality."""
        criticality = self.determine_criticality(
            financial_impact_per_hour=financial_impact_per_hour,
            max_downtime_hours=max_downtime_hours,
            legal_risk=legal_risk,
            customer_impact=customer_impact,
            safety_impact=safety_impact,
        )
        asset = BIAAsset(
            name=name,
            service_type=service_type,
            criticality=criticality,
            max_downtime_hours=max_downtime_hours,
            financial_impact_per_hour=financial_impact_per_hour,
            legal_risk=legal_risk,
            customer_impact=customer_impact,
            safety_impact=safety_impact,
            dependencies=dependencies or [],
            metadata=metadata or {},
        )
        self._assets[name] = asset
        logger.info(
            "Assessed service %s: criticality=%s, financial_impact/hr=%.2f",
            name,
            criticality.value,
            financial_impact_per_hour,
        )
        return asset

    def get_asset(self, name: str) -> Optional[BIAAsset]:
        """Return a previously assessed asset by name, or None."""
        return self._assets.get(name)

    def list_assets(self) -> List[BIAAsset]:
        """Return all assessed assets."""
        return list(self._assets.values())

    # ------------------------------------------------------------------
    # Criticality & impact
    # ------------------------------------------------------------------

    def determine_criticality(
        self,
        financial_impact_per_hour: float,
        max_downtime_hours: float,
        legal_risk: bool,
        customer_impact: bool,
        safety_impact: bool,
    ) -> CriticalityLevel:
        """Determine criticality from financial, legal, customer, and safety signals."""
        severity_key = (legal_risk, customer_impact, safety_impact)
        weight = self._SEVERITY_WEIGHTS.get(severity_key, 1.0)
        score = financial_impact_per_hour * weight * (1.0 + 100.0 / max(1.0, max_downtime_hours))

        if score >= 100_000 or safety_impact:
            return CriticalityLevel.CRITICAL
        elif score >= 10_000:
            return CriticalityLevel.HIGH
        elif score >= 1_000:
            return CriticalityLevel.MEDIUM
        return CriticalityLevel.LOW

    def calculate_financial_impact(
        self,
        asset_name: str,
        downtime_hours: float,
    ) -> float:
        """Calculate financial impact for a given asset over a downtime duration."""
        asset = self._assets.get(asset_name)
        if asset is None:
            logger.warning("calculate_financial_impact: unknown asset %s", asset_name)
            return 0.0
        return asset.financial_impact_per_hour * downtime_hours

    # ------------------------------------------------------------------
    # Dependency analysis
    # ------------------------------------------------------------------

    def map_dependency_chain(
        self,
        asset_name: str,
        visited: Optional[Set[str]] = None,
    ) -> List[str]:
        """Return the full transitive dependency chain for an asset (DFS)."""
        if visited is None:
            visited = set()

        asset = self._assets.get(asset_name)
        if asset is None or asset_name in visited:
            return []

        visited.add(asset_name)
        chain: List[str] = [asset_name]

        for dep in asset.dependencies:
            chain.extend(self.map_dependency_chain(dep, visited))
        return chain

    def find_dependents(self, asset_name: str) -> List[str]:
        """Find all services that depend on the given asset."""
        dependents: List[str] = []
        for name, asset in self._assets.items():
            if asset_name in asset.dependencies:
                dependents.append(name)
                dependents.extend(self.find_dependents(name))
        return dependents

    # ------------------------------------------------------------------
    # Reporting & prioritization
    # ------------------------------------------------------------------

    def prioritize_recovery(self) -> List[BIAAsset]:
        """
        Rank assets by recovery priority.

        Priority order: CRITICAL > HIGH > MEDIUM > LOW; within same level,
        higher financial_impact_per_hour and shorter max_downtime rank first.
        """
        order = {
            CriticalityLevel.CRITICAL: 0,
            CriticalityLevel.HIGH: 1,
            CriticalityLevel.MEDIUM: 2,
            CriticalityLevel.LOW: 3,
        }
        return sorted(
            self._assets.values(),
            key=lambda a: (
                order.get(a.criticality, 99),
                -a.financial_impact_per_hour,
                a.max_downtime_hours,
            ),
        )

    def generate_bia_report(self) -> str:
        """Generate a human-readable BIA report with recovery priorities."""
        assets = self.prioritize_recovery()
        lines: List[str] = []
        lines.append("=" * 66)
        lines.append(" BUSINESS IMPACT ANALYSIS REPORT")
        lines.append(f" Generated: {datetime.utcnow().isoformat()}")
        lines.append(f" Assets assessed: {len(assets)}")
        lines.append("=" * 66)
        lines.append("")

        total_annual_risk = sum(a.annual_financial_risk for a in assets)
        lines.append(f"Total annual financial exposure: ${total_annual_risk:,.2f}")
        lines.append("")

        lines.append(f"{'Priority':<10} {'Service':<25} {'Criticality':<12} {'$/hr':>12} {'Max DT':>8}")
        lines.append("-" * 66)

        for idx, asset in enumerate(assets, 1):
            lines.append(
                f"{idx:<10} {asset.name:<25} {asset.criticality.value:<12} "
                f"${asset.financial_impact_per_hour:>11,.2f} {asset.max_downtime_hours:>7.1f}h"
            )

        lines.append("")
        lines.append("Dependency analysis:")
        for asset in assets:
            deps = self.map_dependency_chain(asset.name)
            if len(deps) > 1:
                lines.append(f"  {asset.name}: chain -> {' -> '.join(deps)}")
            else:
                lines.append(f"  {asset.name}: no dependencies")

        lines.append("")
        lines.append("=" * 66)
        return "\n".join(lines)