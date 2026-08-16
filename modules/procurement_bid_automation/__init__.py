"""Procurement Bid Automation module — deterministic government/RFP bid
assistant.

Grounded in the real JE Van Clief transcripts:

* ``data/transcripts/JEVanClief/I-enT6szVQQ.md`` — "I Used AI to Fix Government
  Contracting": Bidnet Direct / SAM.gov portals, RFQ/RFP/IFB/RFI solicitation
  types, NAICS / NIGP / PSC code selection, CAGE codes, capability statements
  ("a one to two page PDF, government buyers expect this format"), vendor
  profile optimization and profile grading, and company-info -> apply/codes
  guidance. Central to the talk is using a *deterministic reference list* of
  codes/terms ("instead of having to fine-tune a model ... the AI references
  this list ... for accuracy").

* ``data/transcripts/JEVanClief/AjzBaEkWkNA.md`` — "AI Agency and Consulting
  Models are DEAD": the ROI/fit critique (some solutions "thousands of percent
  of ROI. Other ones are absolutely negative"), "provide value beyond what the
  individual ... can do themselves", and knowing when a solution genuinely fits
  before investing. Here that critique powers the bid/no-bid fit assessment.

Pure core lives in :mod:`enterprise.modules.procurement_bid_automation
.procurement_bid_automation` (stdlib-only). This module exposes the ENI platform
facade around it.

Export surface:
  * CodeMatcher / Code / ScoredCode  — NAICS/NIGP/PSC code taxonomy scoring.
  * CompanyProfile / CapabilityStatement / generate_capability_statement
  * grade_profile / ProfileGrade    — vendor profile optimization.
  * Solicitation / analyze_solicitation / SolicitationAnalysis — RFP decoder.
  * assess_opportunity / OpportunityAssessment — bid/no-bid fit & ROI.
  * ProcurementBidAutomationModule — the ENI platform Module wrapper.
  * create_procurement_bid_automation_module(config) — platform factory.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from enterprise.platform_kernel import Event, HealthStatus, Module, module

from .procurement_bid_automation import (  # noqa: F401
    BUILTIN_TAXONOMY, CapabilityStatement, Code, CodeMatcher, CompanyProfile,
    OpportunityAssessment, ProfileGrade, ScoredCode, Solicitation,
    SolicitationAnalysis, analyze_solicitation, assess_opportunity,
    company_info_to_guidance, generate_capability_statement, grade_profile,
)

logger = logging.getLogger("eni.procurement_bid_automation")
__version__ = "1.0.0"

_SOURCE = "procurement_bid_automation"


@module(
    name="procurement_bid_automation",
    version="1.0.0",
    config_defaults={
        "top_codes": 5,          # default number of code recommendations
        "min_code_score": 1,     # minimum keyword hits for a recommended code
        "default_capacity": 0.5,  # neutral delivery-capacity prior for fit
        "weights": {},           # opportunity-assessment weight overrides
        "event_topic_prefix": "procurement.bid",  # event bus topic prefix
    },
)
class ProcurementBidAutomationModule(Module):
    """ENI platform wrapper around the procurement/bid pure-core engine."""

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._event_bus: Any = None
        self._matcher: Optional[CodeMatcher] = None

    async def initialize(self) -> None:
        try:
            self._matcher = CodeMatcher()
            self.status = HealthStatus.HEALTHY
            logger.info("procurement_bid_automation module initialized")
            self._publish("initialized", {"version": __version__})
        except Exception as exc:  # noqa: BLE001
            self.status = HealthStatus.UNHEALTHY
            logger.exception("procurement_bid_automation initialize failed")
            raise

    async def health_check(self) -> HealthStatus:
        return (HealthStatus.HEALTHY if self._matcher is not None
                else HealthStatus.UNHEALTHY)

    async def shutdown(self) -> None:
        self._matcher = None
        self.status = HealthStatus.UNKNOWN

    # ------------------------------------------------------------- events
    def set_event_bus(self, event_bus: Any) -> None:
        """Wire the platform EventBus into the module (events are only emitted
        once a non-None bus is present)."""
        self._event_bus = event_bus

    def _publish(self, topic_suffix: str, payload: Dict[str, Any]) -> None:
        """Publish an event on the bus if one is wired — otherwise no-op."""
        if self._event_bus is None:
            return
        prefix = str(self._config.get("event_topic_prefix", "procurement.bid"))
        event = Event.create(f"{prefix}.{topic_suffix}", _SOURCE, payload)
        self._event_bus.publish(event)

    # ------------------------------------------------------------- facade
    def recommend_codes(self, description: str,
                        limit: Optional[int] = None,
                        min_score: Optional[int] = None) -> List[Dict[str, Any]]:
        """Score and recommend procurement codes for a capability description."""
        matcher = self._require_matcher()
        lim = limit if limit is not None else int(self._config.get("top_codes", 5))
        ms = (min_score if min_score is not None
              else int(self._config.get("min_code_score", 1)))
        ranked = matcher.recommend_codes(description, limit=lim, min_score=ms)
        result = [
            {"id": s.code.id, "family": s.code.family, "title": s.code.title,
             "score": s.score, "matched": list(s.matched)}
            for s in ranked
        ]
        self._publish("codes_recommended", {"n": len(result)})
        return result

    def generate_capability_statement(
        self, profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build a structured capability statement from a company profile."""
        prof = CompanyProfile.from_dict(profile)
        stmt = generate_capability_statement(prof)
        self._publish("capability_statement_generated",
                      {"company": stmt.company_name})
        return {
            "text": stmt.render(),
            "pages": stmt.page_estimate(),
            "company_name": stmt.company_name,
        }

    def grade_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """Grade a vendor profile for completeness / competitiveness."""
        prof = CompanyProfile.from_dict(profile)
        grade = grade_profile(prof)
        self._publish("profile_graded", {"score": grade.score})
        return grade.to_dict()

    def analyze_solicitation(
        self, solicitation: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Decode a solicitation/RFP into requirements, deadline, eligibility
        and do/don't bid signals."""
        sol = Solicitation(
            id=str(solicitation.get("id", "")),
            title=str(solicitation.get("title", "")),
            agency=str(solicitation.get("agency", "")),
            source=str(solicitation.get("source", "")),
            text=str(solicitation.get("text", "")),
            response_deadline=str(solicitation.get("response_deadline", "")),
            set_aside=str(solicitation.get("set_aside", "")),
            naics_codes=[str(c) for c in solicitation.get("naics_codes", [])],
            published=str(solicitation.get("published", "")),
        )
        analysis = analyze_solicitation(sol)
        self._publish("solicitation_analyzed",
                      {"id": analysis.id, "deadline": analysis.deadline})
        return analysis.to_dict()

    def assess_opportunity(
        self,
        profile: Dict[str, Any],
        solicitation: Dict[str, Any],
        capacity: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Bid/no-bid ROI & fit assessment for THIS company vs an opportunity."""
        prof = CompanyProfile.from_dict(profile)
        sol = Solicitation(
            id=str(solicitation.get("id", "")),
            title=str(solicitation.get("title", "")),
            agency=str(solicitation.get("agency", "")),
            source=str(solicitation.get("source", "")),
            text=str(solicitation.get("text", "")),
            response_deadline=str(solicitation.get("response_deadline", "")),
            set_aside=str(solicitation.get("set_aside", "")),
            naics_codes=[str(c) for c in solicitation.get("naics_codes", [])],
            published=str(solicitation.get("published", "")),
        )
        cap = (capacity if capacity is not None
               else float(self._config.get("default_capacity", 0.5)))
        weights = dict(self._config.get("weights") or {})
        result = assess_opportunity(prof, sol, weights=weights, capacity=cap)
        self._publish("opportunity_assessed",
                      {"id": sol.id, "verdict": result.verdict})
        return result.to_dict()

    # ------------------------------------------------------------- internal
    def _require_matcher(self) -> CodeMatcher:
        if self._matcher is None:
            raise RuntimeError("procurement_bid_automation not initialized")
        return self._matcher


def create_procurement_bid_automation_module(
    config: Optional[dict[str, Any]] = None,
) -> ProcurementBidAutomationModule:
    return ProcurementBidAutomationModule(config=config or {})


__all__ = [
    "BUILTIN_TAXONOMY",
    "CapabilityStatement",
    "Code",
    "CodeMatcher",
    "CompanyProfile",
    "OpportunityAssessment",
    "ProcurementBidAutomationModule",
    "ProfileGrade",
    "ScoredCode",
    "Solicitation",
    "SolicitationAnalysis",
    "analyze_solicitation",
    "assess_opportunity",
    "company_info_to_guidance",
    "create_procurement_bid_automation_module",
    "generate_capability_statement",
    "grade_profile",
    "__version__",
]
