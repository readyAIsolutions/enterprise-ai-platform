#!/usr/bin/env python3
"""
ENI Threat Model Module — MITRE ATLAS / STRIDE threat modeling.

Offline, stdlib-only attack-surface analysis for LLM systems. Provides a
curated catalogue of threats mapped to real MITRE ATLAS techniques, a
threat library with category/technique lookups, an assessor that turns an
asset inventory into a risk register (risk = likelihood * impact, with
LOW/MEDIUM/HIGH/CRITICAL severities), a STRIDE mapper that catalogs the six
STRIDE threat categories per asset, and a reporter that produces sorted risk
registers, top-N risks, and mitigation coverage.

All components are stdlib-only, zero external dependencies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from enterprise.platform_kernel import (
    EventBus,
    Event,
    EventPriority,
    HealthStatus,
    Module,
    module,
)

from .risk import ThreatAssessment

_logger = logging.getLogger("enterprise.threat_model")


# =============================================================================
# Severity
# =============================================================================


class Severity(str, Enum):
    """Risk severity bands derived from the numerical risk score.

    risk = likelihood * impact  (each 1-5, so risk is 1-25).

    Bands:
        CRITICAL : risk >= 20
        HIGH     : 15 <= risk < 20
        MEDIUM   : 8  <= risk < 15
        LOW      : risk < 8
    """

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @classmethod
    def from_risk(cls, risk: int) -> "Severity":
        """Map a numeric risk score to a severity band."""
        if risk >= 20:
            return cls.CRITICAL
        if risk >= 15:
            return cls.HIGH
        if risk >= 8:
            return cls.MEDIUM
        return cls.LOW


# =============================================================================
# Threat model
# =============================================================================


@dataclass
class Threat:
    """A single threat against an asset.

    Attributes:
        id:            Stable, unique identifier (e.g. ``AML-001``).
        name:          Human readable threat name.
        category:      Threat category / ATLAS tactic label.
        technique:     MITRE ATLAS technique name and ID.
        likelihood:    Likelihood of occurrence, 1 (rare) to 5 (near certain).
        impact:        Impact if realized, 1 (negligible) to 5 (catastrophic).
        mitigations:   List of mitigation measures.
        asset:         Target asset type (or ``any`` when generic).
    """

    id: str
    name: str
    category: str
    technique: str
    likelihood: int
    impact: int
    mitigations: List[str] = field(default_factory=list)
    asset: str = "any"

    @property
    def risk(self) -> int:
        """Numerical risk score = likelihood * impact (1-25)."""
        return self.likelihood * self.impact

    @property
    def severity(self) -> Severity:
        """Severity band for this threat's intrinsic risk."""
        return Severity.from_risk(self.risk)

    def applies_to(self, asset: str) -> bool:
        """True if this threat targets ``asset`` (or is generic)."""
        return self.asset in ("any", "*", "platform") or self.asset == asset


# =============================================================================
# Built-in Threat Catalogue (MITRE ATLAS techniques for LLM systems)
# =============================================================================

# Each entry keys map directly onto Threat fields. ``asset`` is the target
# asset type token; ``any`` means the threat applies to every asset in scope.
BUILTIN_THREATS: List[Dict[str, Any]] = [
    # ---- Prompt / injection -------------------------------------------------
    {
        "id": "AML-001",
        "name": "Direct Prompt Injection",
        "category": "Prompt Injection",
        "technique": "AML.T0051 Prompt Injection",
        "likelihood": 5,
        "impact": 4,
        "mitigations": [
            "Injection-detection guard (OWASP LLM01)",
            "Delimiter & instruction hardening",
            "Least-privilege tool access",
        ],
        "asset": "any",
    },
    {
        "id": "AML-002",
        "name": "Indirect Prompt Injection",
        "category": "Prompt Injection",
        "technique": "AML.T0051 Prompt Injection",
        "likelihood": 4,
        "impact": 4,
        "mitigations": [
            "Sanitize external/RAG content",
            "Trust boundary on tool output",
            "Reject embedded instructions",
        ],
        "asset": "rag_pipeline",
    },
    {
        "id": "AML-003",
        "name": "Jailbreak",
        "category": "Jailbreak",
        "technique": "AML.T0058 Jailbreak",
        "likelihood": 4,
        "impact": 4,
        "mitigations": [
            "Jailbreak shield heuristics",
            "Role-play / hypothetical detection",
            "Safety-alignment reinforcement",
        ],
        "asset": "any",
    },
    {
        "id": "AML-004",
        "name": "Prompt Theft",
        "category": "Info Disclosure",
        "technique": "AML.T0056 Prompt Theft",
        "likelihood": 3,
        "impact": 3,
        "mitigations": [
            "System-prompt watermarking",
            "Output PII/sensitive filtering",
            "Rate limiting on repeated probes",
        ],
        "asset": "llm_model",
    },
    {
        "id": "AML-005",
        "name": "System Prompt Leak",
        "category": "Info Disclosure",
        "technique": "AML.T0055 System Prompt Leak",
        "likelihood": 3,
        "impact": 3,
        "mitigations": [
            "Prompt embedded as hidden instruction",
            "Monitor for prompt-exfil phrasing",
            "App-level secret separation",
        ],
        "asset": "llm_model",
    },
    # ---- Data / training ----------------------------------------------------
    {
        "id": "AML-006",
        "name": "Data Poisoning",
        "category": "Data Integrity",
        "technique": "AML.T0043 Craft Adversarial Data",
        "likelihood": 2,
        "impact": 5,
        "mitigations": [
            "Training-data provenance & vetting",
            "Anomaly detection on curated corpora",
            "Continuous evaluation on holdout sets",
        ],
        "asset": "data_pipeline",
    },
    {
        "id": "AML-007",
        "name": "Model Backdoor",
        "category": "Data Integrity",
        "technique": "AML.T0043 Craft Adversarial Data",
        "likelihood": 2,
        "impact": 5,
        "mitigations": [
            "Supply-chain artifact signing",
            "Model provenance & reproducibility",
            "Red-team testing before deploy",
        ],
        "asset": "supply_chain",
    },
    {
        "id": "AML-008",
        "name": "Member Inference",
        "category": "Model Extraction",
        "technique": "AML.T0010 ML Model Inference",
        "likelihood": 3,
        "impact": 3,
        "mitigations": [
            "Differential privacy training",
            "Output memorization checks",
            "PII minimization",
        ],
        "asset": "llm_model",
    },
    {
        "id": "AML-009",
        "name": "Model Extraction",
        "category": "Model Extraction",
        "technique": "AML.T0017 Model Extraction",
        "likelihood": 3,
        "impact": 4,
        "mitigations": [
            "Query rate limiting",
            "Output watermarking",
            "Knowledge-distillation guards",
        ],
        "asset": "llm_model",
    },
    # ---- Supply chain / infra ----------------------------------------------
    {
        "id": "AML-010",
        "name": "ML Supply Chain Compromise",
        "category": "Supply Chain",
        "technique": "AML.T0034 Supply Chain Compromise",
        "likelihood": 2,
        "impact": 5,
        "mitigations": [
            "Software bill of materials (SBOM)",
            "Signed model & dependency artifacts",
            "Vulnerability scanning pipeline",
        ],
        "asset": "supply_chain",
    },
    {
        "id": "AML-011",
        "name": "Malicious Model Deployment",
        "category": "Supply Chain",
        "technique": "AML.T0019 ML Model Inference? Publish Poisoned",
        "likelihood": 2,
        "impact": 4,
        "mitigations": [
            "Registry allow-listing",
            "Deployment gates & review",
            "Reproducible-build checks",
        ],
        "asset": "supply_chain",
    },
    # ---- Agency / exfiltration ----------------------------------------------
    {
        "id": "AML-012",
        "name": "Excessive Agency",
        "category": "Agency Abuse",
        "technique": "AML.T0059 Excessive Agency",
        "likelihood": 3,
        "impact": 5,
        "mitigations": [
            "Least-privilege tool scoping",
            "Human-in-the-loop for critical actions",
            "Tool-call allow-lists",
        ],
        "asset": "agent",
    },
    {
        "id": "AML-013",
        "name": "Data Exfiltration",
        "category": "Data Exfiltration",
        "technique": "AML.T0020 Data Exfiltration",
        "likelihood": 3,
        "impact": 5,
        "mitigations": [
            "Outbound-secret monitoring",
            "DLP on model output",
            "Egress filtering",
        ],
        "asset": "any",
    },
    {
        "id": "AML-014",
        "name": "Exfiltration via Tool Abuse",
        "category": "Data Exfiltration",
        "technique": "AML.T0020 Data Exfiltration",
        "likelihood": 3,
        "impact": 4,
        "mitigations": [
            "Audit tool calls",
            "Network egress controls",
            "Per-tool data caps",
        ],
        "asset": "agent",
    },
    # ---- Evasion / other -----------------------------------------------------
    {
        "id": "AML-015",
        "name": "Adversarial Evasion",
        "category": "Evasion",
        "technique": "AML.T0028 Evade ML Model",
        "likelihood": 2,
        "impact": 3,
        "mitigations": [
            "Adversarial robustness evaluation",
            "Input perturbation resistance",
            "Fallback classifiers",
        ],
        "asset": "llm_model",
    },
    {
        "id": "AML-016",
        "name": "Denial of Service",
        "category": "DoS",
        "technique": "AML.T0020 Extreme Inputs / Resource Exhaustion",
        "likelihood": 3,
        "impact": 3,
        "mitigations": [
            "Request budgets & quotas",
            "Input length caps",
            "Backpressure & autoscaling",
        ],
        "asset": "api_gateway",
    },
    {
        "id": "AML-017",
        "name": "Unsafe Content Generation",
        "category": "Content Hazard",
        "technique": "AML.T0058 Jailbreak // Unsafe Output",
        "likelihood": 4,
        "impact": 3,
        "mitigations": [
            "Output toxicity filter",
            "Content policy enforcement",
            "Refusal fallbacks",
        ],
        "asset": "any",
    },
]

CATALOGUE_TACTICS = [
    "Prompt Injection",
    "Jailbreak",
    "Data Integrity",
    "Model Extraction",
    "Supply Chain",
    "Info Disclosure",
    "Agency Abuse",
    "Data Exfiltration",
]


# =============================================================================
# Threat Library
# =============================================================================


class ThreatLibrary:
    """Indexed store of threats with category/technique/asset lookups.

    Populated from :data:`BUILTIN_THREATS` by default and extensible via
    :meth:`register`.
    """

    def __init__(self, threats: Optional[Iterable[Threat]] = None) -> None:
        self._threats: Dict[str, Threat] = {}
        if threats is not None:
            for t in threats:
                self.register(t)
        else:
            for entry in BUILTIN_THREATS:
                self.register(Threat(**entry))

    # -- mutation ------------------------------------------------------------

    def register(self, threat: Threat) -> Threat:
        """Add (or replace) a threat, keyed by its unique id."""
        if not threat.id:
            raise ValueError("Threat id must not be empty")
        self._threats[threat.id] = threat
        return threat

    def remove(self, threat_id: str) -> bool:
        """Remove a threat by id. Returns True if it existed."""
        return self._threats.pop(threat_id, None) is not None

    # -- access ---------------------------------------------------------------

    def all(self) -> List[Threat]:
        """Return all threats in insertion order."""
        return list(self._threats.values())

    def get(self, threat_id: str) -> Optional[Threat]:
        """Return a threat by id, or None."""
        return self._threats.get(threat_id)

    def __len__(self) -> int:
        return len(self._threats)

    def __iter__(self):
        return iter(self._threats.values())

    # -- lookups --------------------------------------------------------------

    def by_category(self, category: str) -> List[Threat]:
        """Return all threats in a category (case-insensitive)."""
        cat = category.strip().lower()
        return [t for t in self._threats.values() if t.category.lower() == cat]

    def by_technique(self, technique: str) -> List[Threat]:
        """Return threats whose ATLAS technique name/ID matches (fuzzy).

        Matches if the query appears in the technique string, or the
        technique string contains the query — either direction works.
        """
        query = technique.strip().lower()
        out: List[Threat] = []
        for t in self._threats.values():
            tech = t.technique.lower()
            if query in tech or tech in query:
                out.append(t)
        return out

    def matching(self, asset: str) -> List[Threat]:
        """Return threats applicable to a given asset (generic or specific)."""
        return [t for t in self._threats.values() if t.applies_to(asset)]

    def categories(self) -> Set[str]:
        """Return the set of distinct threat categories."""
        return {t.category for t in self._threats.values()}

    def techniques(self) -> Set[str]:
        """Return the set of distinct ATLAS techniques."""
        return {t.technique for t in self._threats.values()}

    def assets(self) -> Set[str]:
        """Return the set of distinct targeted asset tokens."""
        return {t.asset for t in self._threats.values()}


# =============================================================================
# Threat Assessor
# =============================================================================

FILTER_ALL = "all"
FILTER_HIGH_RISK = "high_risk"
FILTER_BY_CATEGORY = "by_category"

VALID_FILTERS = {FILTER_ALL, FILTER_HIGH_RISK, FILTER_BY_CATEGORY}


class ThreatAssessor:
    """Computes a risk register from an asset inventory.

    For every asset in the inventory the assessor collects the applicable
    threats, computes risk = likelihood * impact, derives a severity band,
    and optionally filters the result.
    """

    def __init__(self, library: Optional[ThreatLibrary] = None) -> None:
        self.library = library or ThreatLibrary()

    def _entry(self, threat: Threat, asset: str) -> Dict[str, Any]:
        return {
            "threat_id": threat.id,
            "name": threat.name,
            "category": threat.category,
            "technique": threat.technique,
            "asset": asset,
            "likelihood": threat.likelihood,
            "impact": threat.impact,
            "risk": threat.risk,
            "severity": threat.severity,
            "mitigations": list(threat.mitigations),
        }

    def assess(
        self,
        assets: Sequence[str],
        filter_mode: str = FILTER_ALL,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Build a risk register for the given asset inventory.

        Args:
            assets:       Iterable of asset names to analyze.
            filter_mode:  ``all`` (default), ``high_risk`` or ``by_category``.
            category:     Required category when ``filter_mode='by_category'``.

        Returns:
            List of risk-register entries (dicts), each carrying risk and
            severity alongside the underlying threat details.
        """
        if filter_mode not in VALID_FILTERS:
            raise ValueError(f"Unknown filter_mode: {filter_mode!r}")

        register: List[Dict[str, Any]] = []
        for asset in assets:
            for threat in self.library.matching(asset):
                register.append(self._entry(threat, asset))

        if filter_mode == FILTER_HIGH_RISK:
            register = [e for e in register if e["severity"] in (Severity.HIGH, Severity.CRITICAL)]
        elif filter_mode == FILTER_BY_CATEGORY:
            if not category:
                raise ValueError("filter_mode='by_category' requires a 'category'")
            want = category.strip().lower()
            register = [e for e in register if e["category"].lower() == want]

        register.sort(key=lambda e: e["risk"], reverse=True)
        return register


# =============================================================================
# Threat Model Reporter
# =============================================================================


class ThreatModelReporter:
    """Produces ordered threat registers, top risks, and mitigation coverage."""

    @staticmethod
    def sorted_register(register: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Return the register sorted by risk (descending)."""
        return sorted(register, key=lambda e: e["risk"], reverse=True)

    @staticmethod
    def top_n(register: Sequence[Dict[str, Any]], n: int = 5) -> List[Dict[str, Any]]:
        """Return the top ``n`` highest-risk entries (clamped to the register)."""
        n = max(0, int(n))
        return ThreatModelReporter.sorted_register(register)[:n]

    @staticmethod
    def mitigation_coverage(register: Sequence[Dict[str, Any]]) -> float:
        """Fraction (0.0-1.0) of entries that list at least one mitigation."""
        if not register:
            return 0.0
        covered = sum(1 for e in register if e.get("mitigations"))
        return round(covered / len(register), 4)

    def report(
        self,
        register: Sequence[Dict[str, Any]],
        top_n: int = 5,
    ) -> Dict[str, Any]:
        """Build a full report dict from a register."""
        ordered = self.sorted_register(register)
        risks = [e["risk"] for e in ordered]
        return {
            "register": ordered,
            "total_threats": len(ordered),
            "top_risks": self.top_n(ordered, top_n),
            "top_n": top_n,
            "max_risk": max(risks) if risks else 0,
            "mitigation_coverage": self.mitigation_coverage(ordered),
            "severity_counts": {
                "LOW": sum(1 for e in ordered if e["severity"] == Severity.LOW),
                "MEDIUM": sum(1 for e in ordered if e["severity"] == Severity.MEDIUM),
                "HIGH": sum(1 for e in ordered if e["severity"] == Severity.HIGH),
                "CRITICAL": sum(1 for e in ordered if e["severity"] == Severity.CRITICAL),
            },
        }


# =============================================================================
# STRIDE Threat Mapper
# =============================================================================


class STRIDEThreatMapper:
    """Maps an asset to the six STRIDE threat categories with examples."""

    STRIDE_CATEGORIES: List[str] = [
        "Spoofing",
        "Tampering",
        "Repudiation",
        "Information Disclosure",
        "Denial of Service",
        "Elevation of Privilege",
    ]

    _EXAMPLES: List[Dict[str, Any]] = [
        {
            "spoofing": (
                "Attacker spoofs a trusted system identity to trick the agent "
                "into treating injected instructions as authoritative."
            ),
            "tampering": (
                "Attacker tampers with tool output or RAG context to corrupt "
                "the model's decision inputs."
            ),
            "repudiation": (
                "Destructive or harmful model actions lack a non-repudiable "
                "audit trail, allowing denial of responsibility."
            ),
            "information_disclosure": (
                "Sensitive data (PII, secrets, system prompt) leaks through "
                "model responses or tool outputs."
            ),
            "denial_of_service": (
                "Resource exhaustion via extreme inputs floods the inference "
                "service and degrades availability."
            ),
            "elevation_of_privilege": (
                "Excessive tool agency lets the model escalate to privileged "
                "operations beyond its intended scope."
            ),
        }
    ]

    # map each STRIDE category to a matching ATLAS technique string so every
    # mapped entry carries a meaningful technique reference
    _TECHNIQUE_BY_STRIDE: Dict[str, str] = {
        "Spoofing": "AML.T0051 Prompt Injection",
        "Tampering": "AML.T0043 Craft Adversarial Data",
        "Repudiation": "AML.T0010 ML Model Inference",
        "Information Disclosure": "AML.T0020 Data Exfiltration",
        "Denial of Service": "AML.T0020 Extreme Inputs / Resource Exhaustion",
        "Elevation of Privilege": "AML.T0059 Excessive Agency",
    }

    def map(self, asset: str) -> Dict[str, List[Dict[str, Any]]]:
        """Return a dict of the six STRIDE categories, each with example threats."""
        result: Dict[str, List[Dict[str, Any]]] = {}
        examples = self._EXAMPLES[0]
        for cat in self.STRIDE_CATEGORIES:
            key = cat.lower().replace(" ", "_")
            description = examples.get(key, f"STRIDE threat for {asset}.")
            result[cat] = [
                {
                    "category": cat,
                    "asset": asset,
                    "description": description,
                    "technique": self._TECHNIQUE_BY_STRIDE.get(cat, ""),
                    "mitigations": self._mitigations_for(cat),
                }
            ]
        return result

    @staticmethod
    def _mitigations_for(category: str) -> List[str]:
        _BASE: Dict[str, List[str]] = {
            "Spoofing": ["Mutual TLS / identity verification", "Prompt-injection guard"],
            "Tampering": ["Output hashing & integrity checks", "Context sanitization"],
            "Repudiation": ["Hash-chained audit logging", "Tool-call attestation"],
            "Information Disclosure": ["DLP on output", "PII redaction"],
            "Denial of Service": ["Request quotas", "Input length caps"],
            "Elevation of Privilege": ["Least-privilege tool scoping", "Human-in-the-loop"],
        }
        return list(_BASE.get(category, []))

    def categories(self) -> List[str]:
        """Return the six STRIDE category names."""
        return list(self.STRIDE_CATEGORIES)


# =============================================================================
# Facade
# =============================================================================


class ThreatModelFacade:
    """High-level entry point combining library, assessor, mapper and reporter."""

    def __init__(
        self,
        library: Optional[ThreatLibrary] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.config = config or {}
        self.library = library or ThreatLibrary()
        self.assessor = ThreatAssessor(self.library)
        self.mapper = STRIDEThreatMapper()
        self.reporter = ThreatModelReporter()
        # Master-class risk register, mitigation planning & severity scoring.
        self.risk = ThreatAssessment()

    # -- library delegations -------------------------------------------------

    def by_category(self, category: str) -> List[Threat]:
        return self.library.by_category(category)

    def by_technique(self, technique: str) -> List[Threat]:
        return self.library.by_technique(technique)

    def catalogue(self) -> List[Threat]:
        return self.library.all()

    # -- analysis ------------------------------------------------------------

    def assess(
        self,
        assets: Sequence[str],
        filter_mode: str = FILTER_ALL,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Compute a risk register for the given asset inventory."""
        return self.assessor.assess(assets, filter_mode=filter_mode, category=category)

    def stride(self, asset: str) -> Dict[str, List[Dict[str, Any]]]:
        """Map an asset to its six STRIDE categories with example threats."""
        return self.mapper.map(asset)

    def report(
        self,
        assets: Sequence[str],
        filter_mode: str = FILTER_ALL,
        category: Optional[str] = None,
        top_n: int = 5,
    ) -> Dict[str, Any]:
        """Assess ``assets`` and return a full threat-model report."""
        register = self.assess(assets, filter_mode=filter_mode, category=category)
        return self.reporter.report(register, top_n=top_n)


# =============================================================================
# Platform Module
# =============================================================================


@module(name="threat_model", version="1.0.0")
class ThreatModelModule(Module):
    """ENI Threat Model Module.

    Provides offline MITRE ATLAS / STRIDE threat modeling over the asset
    inventory. Wraps a :class:`ThreatModelFacade` and exposes its analysis
    through a clean lifecycle.

    Events published (when an event bus is wired via ``set_event_bus``):
        - threat.report.ready — a threat-model report was produced
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._library = ThreatLibrary()
        self._facade: Optional[ThreatModelFacade] = None
        self._event_bus: Optional[EventBus] = None

    # -- properties ----------------------------------------------------------

    @property
    def facade(self) -> Optional[ThreatModelFacade]:
        """Return the active facade, if initialized."""
        return self._facade

    @property
    def library(self) -> ThreatLibrary:
        """Return the backing threat library."""
        return self._library

    # -- lifecycle -----------------------------------------------------------

    async def initialize(self) -> None:
        """Build the threat-model facade.

        On success the module status becomes HEALTHY; on failure UNHEALTHY and
        the error is re-raised so the platform can react.
        """
        self._status = HealthStatus.STARTING
        try:
            self._facade = ThreatModelFacade(library=self._library)
            self._status = HealthStatus.HEALTHY
            _logger.info("Threat model module initialized (%d catalogue threats)",
                         len(self._library))
        except Exception as exc:  # pragma: no cover - defensive
            _logger.exception("Failed to initialize threat model module: %s", exc)
            self._status = HealthStatus.UNHEALTHY
            raise

    async def health_check(self) -> HealthStatus:
        """Return module health: HEALTHY when the facade is built."""
        if self._facade is not None and self._status is HealthStatus.HEALTHY:
            return HealthStatus.HEALTHY
        if self._status is HealthStatus.UNHEALTHY:
            return HealthStatus.UNHEALTHY
        self._status = HealthStatus.UNKNOWN
        return self._status

    async def shutdown(self) -> None:
        """Gracefully shut down, releasing the facade."""
        self._status = HealthStatus.STOPPING
        self._facade = None
        self._status = HealthStatus.HEALTHY
        _logger.info("Shutting down threat model module...")

    # -- event bus wiring ----------------------------------------------------

    def set_event_bus(self, event_bus: EventBus) -> None:
        """Wire the platform EventBus into this module."""
        self._event_bus = event_bus

    # -- public operations ---------------------------------------------------

    def require_facade(self) -> ThreatModelFacade:
        """Return the facade or raise if the module is not initialized."""
        if self._facade is None:
            raise RuntimeError("Threat model module is not initialized")
        return self._facade

    def assess(
        self,
        assets: Sequence[str],
        filter_mode: str = FILTER_ALL,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Compute a risk register for the given assets."""
        register = self.require_facade().assess(assets, filter_mode, category)
        self._publish("threat.register.assessed",
                      {"assets": list(assets), "count": len(register)})
        return register

    def stride(self, asset: str) -> Dict[str, List[Dict[str, Any]]]:
        """Map an asset to STRIDE categories."""
        return self.require_facade().stride(asset)

    def report(
        self,
        assets: Sequence[str],
        top_n: int = 5,
    ) -> Dict[str, Any]:
        """Build a full threat-model report for the given assets."""
        rep = self.require_facade().report(assets, top_n=top_n)
        self._publish("threat.report.ready",
                      {"assets": list(assets), "total": rep["total_threats"]})
        return rep

    def _publish(self, topic: str, payload: Dict[str, Any]) -> None:
        """Publish an event on the wired event bus, if any."""
        if self._event_bus is not None:
            self._event_bus.publish(
                Event.create(topic, source="threat_model", payload=payload,
                             priority=EventPriority.NORMAL)
            )


__all__ = [
    "Threat",
    "Severity",
    "ThreatLibrary",
    "ThreatAssessor",
    "ThreatModelReporter",
    "STRIDEThreatMapper",
    "ThreatModelFacade",
    "ThreatModelModule",
    "BUILTIN_THREATS",
    "CATALOGUE_TACTICS",
    "FILTER_ALL",
    "FILTER_HIGH_RISK",
    "FILTER_BY_CATEGORY",
]
