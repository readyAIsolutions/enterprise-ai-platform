"""
Disaster scenario catalog and simulation.

Covers 17 distinct disaster scenarios with detection methods, recovery procedures,
prevention measures, and readiness evaluation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger("enterprise.disaster_recovery.scenarios")


class ScenarioType(str, Enum):
    """Categorized disaster scenario types."""

    CLOUD_REGION_FAILURE = "cloud_region_failure"
    CLOUD_PROVIDER_FAILURE = "cloud_provider_failure"
    DB_CORRUPTION = "db_corruption"
    RANSOMWARE = "ransomware"
    CREDENTIAL_COMPROMISE = "credential_compromise"
    INSIDER_THREAT = "insider_threat"
    SUPPLY_CHAIN = "supply_chain"
    DNS_CERT_FAILURE = "dns_cert_failure"
    NETWORK_OUTAGE = "network_outage"
    MODEL_PROVIDER_OUTAGE = "model_provider_outage"
    AI_MALFUNCTION = "ai_malfunction"
    ACCIDENTAL_DELETION = "accidental_deletion"
    FAILED_DEPLOYMENT = "failed_deployment"
    HARDWARE_POWER_FAILURE = "hardware_power_failure"
    NATURAL_DISASTER = "natural_disaster"
    VENDOR_SHUTDOWN = "vendor_shutdown"
    KEY_PERSONNEL_LOSS = "key_personnel_loss"


@dataclass
class Scenario:
    """A single disaster scenario with metadata and procedures."""

    type: ScenarioType
    title: str
    description: str
    likelihood: float               # 0.0 - 1.0
    impact_severity: float          # 0.0 - 1.0
    affected_services: List[str] = field(default_factory=list)
    detection_method: str = ""
    recovery_procedure: str = ""
    estimated_recovery_time: str = ""
    prevention_measures: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    last_reviewed: Optional[datetime] = None

    @property
    def risk_score(self) -> float:
        """Composite risk = likelihood * impact."""
        return self.likelihood * self.impact_severity

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "title": self.title,
            "description": self.description,
            "likelihood": self.likelihood,
            "impact_severity": self.impact_severity,
            "risk_score": self.risk_score,
            "affected_services": self.affected_services,
            "estimated_recovery_time": self.estimated_recovery_time,
        }


class ScenarioLibrary:
    """
    Managed library of disaster scenarios.

    Supports CRUD, risk ranking, runbook generation, and readiness evaluation.
    """

    def __init__(self) -> None:
        self._scenarios: Dict[ScenarioType, Scenario] = {}

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add_scenario(self, scenario: Scenario) -> Scenario:
        """Add or update a scenario in the library."""
        self._scenarios[scenario.type] = scenario
        scenario.last_reviewed = datetime.utcnow()
        logger.info("Added scenario: %s (risk=%.2f)", scenario.title, scenario.risk_score)
        return scenario

    def get_by_type(self, scenario_type: ScenarioType) -> Optional[Scenario]:
        """Retrieve a scenario by its type."""
        return self._scenarios.get(scenario_type)

    def list_all(self) -> List[Scenario]:
        """Return all scenarios."""
        return list(self._scenarios.values())

    def remove(self, scenario_type: ScenarioType) -> bool:
        """Remove a scenario; returns True if it existed."""
        existed = self._scenarios.pop(scenario_type, None) is not None
        if existed:
            logger.info("Removed scenario: %s", scenario_type.value)
        return existed

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def rank_by_risk(self) -> List[Scenario]:
        """Return scenarios sorted descending by risk score."""
        return sorted(self._scenarios.values(), key=lambda s: s.risk_score, reverse=True)

    def top_risks(self, n: int = 5) -> List[Scenario]:
        """Return the top-N highest-risk scenarios."""
        return self.rank_by_risk()[:n]

    def filter_by_service(self, service_name: str) -> List[Scenario]:
        """Find all scenarios that affect a given service."""
        return [
            s for s in self._scenarios.values()
            if service_name in s.affected_services
        ]

    # ------------------------------------------------------------------
    # Runbooks & readiness
    # ------------------------------------------------------------------

    def generate_runbook(self) -> str:
        """Generate a consolidated runbook for all scenarios."""
        scenarios = self.rank_by_risk()
        lines: List[str] = []
        lines.append("=" * 72)
        lines.append(" DISASTER SCENARIO RUNBOOK")
        lines.append(f" Generated: {datetime.utcnow().isoformat()}")
        lines.append(f" Total scenarios: {len(scenarios)}")
        lines.append("=" * 72)
        lines.append("")

        for idx, scenario in enumerate(scenarios, 1):
            lines.append(f"{idx}. {scenario.title} ({scenario.type.value})")
            lines.append(f"   Risk Score: {scenario.risk_score:.2f} | Likelihood: {scenario.likelihood:.2f} | Impact: {scenario.impact_severity:.2f}")
            lines.append(f"   Est. Recovery: {scenario.estimated_recovery_time}")
            lines.append(f"   Detection: {scenario.detection_method}")
            lines.append(f"   Affected services: {', '.join(scenario.affected_services) or 'all'}")
            if scenario.prevention_measures:
                lines.append(f"   Prevention: {', '.join(scenario.prevention_measures[:3])}")
            lines.append("")

        return "\n".join(lines)

    def evaluate_readiness(
        self,
        available_services: List[str],
        backup_coverage: Dict[str, bool],
    ) -> Dict[str, str]:
        """Evaluate readiness against each scenario.

        Returns dict mapping scenario type -> readiness status.
        """
        statuses: Dict[str, str] = {}
        for stype, scenario in self._scenarios.items():
            uncovered = [
                svc for svc in scenario.affected_services
                if svc not in available_services or not backup_coverage.get(svc, False)
            ]
            if not uncovered:
                statuses[stype.value] = "ready"
            elif len(uncovered) <= len(scenario.affected_services) // 2:
                statuses[stype.value] = "partial"
            else:
                statuses[stype.value] = "not_ready"
        logger.info("Readiness evaluated: %d scenarios", len(statuses))
        return statuses

    def seed_defaults(self) -> None:
        """Populate the library with common disaster scenarios."""
        defaults = [
            Scenario(
                type=ScenarioType.CLOUD_REGION_FAILURE,
                title="Cloud Region Failure",
                description="Complete outage of a primary cloud region (e.g., us-east-1).",
                likelihood=0.05,
                impact_severity=0.95,
                affected_services=["api", "database", "storage"],
                detection_method="Cloud provider status page, synthetic health checks",
                recovery_procedure="Activate multi-region failover; promote read replicas; update DNS.",
                estimated_recovery_time="15-30 minutes",
                prevention_measures=["Multi-region active-active", "Regular region-failure drills"],
            ),
            Scenario(
                type=ScenarioType.RANSOMWARE,
                title="Ransomware Attack",
                description="Encryption of production data by malicious actors demanding payment.",
                likelihood=0.15,
                impact_severity=0.98,
                affected_services=["database", "storage", "backup"],
                detection_method="File integrity monitoring alerts, unusual encryption activity",
                recovery_procedure="Isolate affected systems; restore from immutable backups; rotate all credentials.",
                estimated_recovery_time="4-24 hours",
                prevention_measures=["Immutable backups", "Air-gapped copies", "Endpoint protection"],
            ),
            Scenario(
                type=ScenarioType.CREDENTIAL_COMPROMISE,
                title="Credential Compromise",
                description="Production credentials leaked or stolen, giving attacker infrastructure access.",
                likelihood=0.12,
                impact_severity=0.90,
                affected_services=["iam", "infrastructure", "secrets"],
                detection_method="Unusual API patterns, credential scanning alerts",
                recovery_procedure="Immediately rotate all credentials; audit recent activity; enable MFA everywhere.",
                estimated_recovery_time="1-4 hours",
                prevention_measures=["MFA enforcement", "Short-lived tokens", "Secrets rotation automation"],
            ),
            Scenario(
                type=ScenarioType.MODEL_PROVIDER_OUTAGE,
                title="AI Model Provider Outage",
                description="Primary LLM/ML provider experiences a prolonged outage.",
                likelihood=0.08,
                impact_severity=0.75,
                affected_services=["ai_gateway", "inference"],
                detection_method="Provider status page, model health endpoint monitoring",
                recovery_procedure="Switch to fallback provider; activate cached responses; reduce feature set.",
                estimated_recovery_time="5-30 minutes",
                prevention_measures=["Multi-provider routing", "Fallback model chains", "Cached common queries"],
            ),
            Scenario(
                type=ScenarioType.DB_CORRUPTION,
                title="Database Corruption",
                description="Primary database becomes corrupted due to bug, bad migration, or hardware error.",
                likelihood=0.06,
                impact_severity=0.85,
                affected_services=["database", "api"],
                detection_method="Query failures, integrity check failures, replication lag spikes",
                recovery_procedure="Fail over to replica; restore from point-in-time backup; run integrity checks.",
                estimated_recovery_time="30-120 minutes",
                prevention_measures=["Continuous backup", "Replication", "Pre-migration snapshots"],
            ),
        ]
        for scenario in defaults:
            self.add_scenario(scenario)
        logger.info("Seeded %d default scenarios", len(defaults))