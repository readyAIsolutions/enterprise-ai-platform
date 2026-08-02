"""
AI-Assisted Support Guardrails.

Enforces safety and compliance rules for AI-powered customer
support interactions, ensuring ethical handling, data isolation,
and appropriate human handoff triggers.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("enterprise.customer_experience")


class AISupportRule(Enum):
    """Safety and compliance rules for AI support interactions."""

    IDENTIFY_UNCERTAINTY = "identify_uncertainty"
    NO_FABRICATION = "no_fabrication"
    NO_CROSS_CUSTOMER_DATA = "no_cross_customer_data"
    ESCALATE_SENSITIVE = "escalate_sensitive"
    RESPECT_AUTH = "respect_auth"
    NO_IRREVERSIBLE_ACTIONS = "no_irreversible_actions"
    RECORD_INTERACTIONS = "record_interactions"
    USE_APPROVED_KNOWLEDGE = "use_approved_knowledge"
    HUMAN_HANDOFF = "human_handoff"


# Sensitive topic indicators for escalation
_SENSITIVE_PATTERNS: List[str] = [
    r"\b(password|credentials|pii|social security|credit card)\b",
    r"\b(delet(e|ing)\s+(all|my|account|data|everything))\b",
    r"\b(refund|chargeback|legal|sue|attorney|lawyer)\b",
    r"\b(security\s+breach|data\s+breach|hacked|compromised)\b",
    r"\b(gdpr|ccpa|privacy\s+request|data\s+subject)\b",
    r"\b(mental\s+health|crisis|suicide|self.harm|emergency)\b",
]

# Uncertainty markers in AI-generated text
_UNCERTAINTY_MARKERS: List[str] = [
    r"\bI('?m|\s+am)\s+not\s+sure\b",
    r"\bI\s+(think|believe|guess|assume|suppose)\b",
    r"\b(possibly|maybe|perhaps|might|could be|may be)\b",
    r"\b(uncertain|unclear|unknown|unsure)\b",
    r"\bto\s+the\s+best\s+of\s+my\s+knowledge\b",
]


@dataclass
class AISupportInteraction:
    """Records a single AI-assisted support interaction with guard results."""

    interaction_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    customer_id: str = ""
    query: str = ""
    ai_response: str = ""
    confidence_score: float = 1.0
    uncertainty_flagged: bool = False
    fabrication_check_passed: bool = True
    cross_customer_check_passed: bool = True
    sensitive_topic_escalated: bool = False
    auth_verified: bool = False
    irreversible_action_blocked: bool = False
    interaction_recorded: bool = False
    knowledge_source_verified: bool = True
    human_handoff_triggered: bool = False
    guard_audit: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AISupportGuard:
    """Safety guardrails for AI-powered customer support.

    Every customer-facing AI interaction must pass through these checks
    before the response is delivered.
    """

    # Actions that should never be executed automatically
    _IRREVERSIBLE_ACTIONS: Set[str] = {
        "delete_account",
        "cancel_subscription",
        "refund",
        "modify_billing",
        "change_email",
        "close_ticket",
        "wipe_data",
        "downgrade_plan",
    }

    # Additional patterns for detecting irreversible actions in natural language
    _IRREVERSIBLE_PATTERNS: List[str] = [
        r"\bdelete\s+(my\s+)?account\b",
        r"\bcancel\s+(my\s+)?subscription\b",
        r"\brefund\b",
        r"\bwipe\s+(my\s+)?data\b",
        r"\bdowngrade\s+(my\s+)?plan\b",
        r"\bclose\s+(my\s+)?(ticket|account)\b",
        r"\bmodify\s+billing\b",
        r"\bchange\s+(my\s+)?email\b",
    ]

    def __init__(
        self,
        allowed_knowledge_sources: Optional[List[str]] = None,
        blocked_terms: Optional[List[str]] = None,
    ) -> None:
        self._interactions: Dict[str, AISupportInteraction] = {}
        self._human_queue: List[str] = []
        self.allowed_knowledge_sources = allowed_knowledge_sources or [
            "internal_kb",
            "product_docs",
            "approved_faq",
            "support_playbook",
        ]
        self.blocked_terms = blocked_terms or []
        logger.info("AISupportGuard initialized with %d knowledge sources", len(self.allowed_knowledge_sources))

    # ------------------------------------------------------------------
    # Rule checks (one per AISupportRule)
    # ------------------------------------------------------------------

    def check_uncertainty(self, response_text: str) -> Dict[str, Any]:
        """Scan an AI-generated response for markers of uncertainty."""
        lowered = response_text.lower()
        matches: List[str] = []
        for pattern in _UNCERTAINTY_MARKERS:
            found = re.findall(pattern, lowered)
            if found:
                matches.append(pattern)

        flagged = len(matches) > 0
        confidence = max(0.0, 1.0 - (len(matches) * 0.25))
        return {
            "uncertainty_flagged": flagged,
            "confidence_score": round(confidence, 2),
            "matched_markers": matches,
            "recommendation": (
                "Verify and rephrase with higher confidence or escalate to human"
                if flagged
                else "Response appears confident"
            ),
        }

    def validate_response(
        self,
        interaction: AISupportInteraction,
        query: str,
        response: str,
    ) -> AISupportInteraction:
        """Run all guard checks on an interaction in sequence."""
        interaction.query = query
        interaction.ai_response = response

        # 1. Uncertainty
        unc = self.check_uncertainty(response)
        interaction.uncertainty_flagged = unc["uncertainty_flagged"]
        interaction.confidence_score = unc["confidence_score"]

        # 2. Fabrication
        fab = self.verify_no_fabrication(response)
        interaction.fabrication_check_passed = fab["passed"]

        # 3. Cross-customer data
        iso = self.ensure_data_isolation(response, interaction.customer_id)
        interaction.cross_customer_check_passed = iso["passed"]

        # 4. Sensitive topics
        sens = self.detect_sensitive_topics(query, response)
        interaction.sensitive_topic_escalated = sens["escalated"]

        # 5. Auth
        interaction.auth_verified = self.verify_authorization(interaction.customer_id)

        # 6. Irreversible actions
        irr = self.block_irreversible_actions(query, response)
        interaction.irreversible_action_blocked = irr["blocked"]

        # 7. Knowledge source
        ks = self.verify_knowledge_source(response)
        interaction.knowledge_source_verified = ks["verified"]

        # 8. Record
        interaction.interaction_recorded = self.record_interaction(interaction)

        # 9. Human handoff
        interaction.human_handoff_triggered = self.trigger_human_handoff(interaction)

        interaction.guard_audit = self.audit_ai_interaction(interaction)

        if interaction.human_handoff_triggered:
            self._human_queue.append(interaction.interaction_id)

        return interaction

    def verify_no_fabrication(self, response: str) -> Dict[str, Any]:
        """Check response for signs of hallucination or fabrication."""
        # Heuristic checks for common hallucination patterns
        flags: List[str] = []
        lowered = response.lower()

        # Fake dates/times that don't exist
        fake_date_patterns = [r"as\s+of\s+(january|february|march)\s+\d{1,2},\s+20(2[7-9]|[3-9]\d)"]
        for pattern in fake_date_patterns:
            if re.search(pattern, lowered):
                flags.append("future_date")

        # Hallucinated feature names (capitalized non-standard terms)
        hallucinated_features = re.findall(r'\b(?:magic|automatic|instant)\s+(?:AI|auto)?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', response)
        if hallucinated_features:
            flags.append("unsubstantiated_features")

        # Absolute claims without qualification
        absolute_claims = re.findall(
            r'\b(always|never|guarantee|100%|absolutely|certainly|definitely)\b',
            lowered,
        )
        if len(absolute_claims) > 2:
            flags.append("excessive_absolute_claims")

        # Made-up metrics
        if re.search(r'\b\d{2,3}%\s+(?:of\s+)?(?:our|customers|users)\b', lowered):
            if "according to" not in lowered and "survey" not in lowered:
                flags.append("unattributed_statistic")

        passed = len(flags) == 0
        return {
            "passed": passed,
            "flags": flags,
            "recommendation": (
                "Response appears factual"
                if passed
                else "Review for potential fabrication markers"
            ),
        }

    def ensure_data_isolation(
        self,
        response: str,
        current_customer_id: str,
    ) -> Dict[str, Any]:
        """Ensure response does not leak data about other customers."""
        lowered = response.lower()
        cross_flags: List[str] = []

        # Check for references to other customers
        other_customer_patterns = [
            r"\b(another\s+customer|other\s+user|different\s+account)\b",
            r"\b(similar\s+issue\s+from\s+(another|a\s+different))\b",
            r"\b(we\s+saw\s+this\s+with\s+(a|another))\b",
        ]
        for pattern in other_customer_patterns:
            if re.search(pattern, lowered):
                cross_flags.append("cross_customer_reference")

        # Check for specific identifiers that aren't the current customer's
        ident_patterns = [
            r"\b(customer[_\s]?id[:\s]+(?!{})\S+)\b".format(current_customer_id),
        ]

        passed = len(cross_flags) == 0
        return {
            "passed": passed,
            "flags": cross_flags,
            "recommendation": (
                "No cross-customer data detected"
                if passed
                else "Response may contain cross-customer references"
            ),
        }

    def detect_sensitive_topics(
        self,
        query: str,
        response: str,
    ) -> Dict[str, Any]:
        """Detect sensitive topics that require escalation or special handling."""
        combined = (query + " " + response).lower()
        matched: List[str] = []
        for pattern in _SENSITIVE_PATTERNS:
            if re.search(pattern, combined):
                matched.append(pattern)

        escalated = len(matched) > 0
        return {
            "escalated": escalated,
            "matched_sensitive_topics": matched,
            "recommendation": (
                "Escalate to human agent for sensitive topic handling"
                if escalated
                else "No sensitive topics detected"
            ),
        }

    def verify_authorization(self, customer_id: str) -> bool:
        """Verify the customer is authorized for AI-assisted support.

        In production this would check against an IAM system.
        Here we implement a heuristic: known (non-empty) customer IDs pass.
        """
        if not customer_id or customer_id.strip() == "":
            logger.warning("Authorization failed: empty customer_id")
            return False
        # Block known test/internal IDs that shouldn't use AI support
        if customer_id.lower() in ("internal", "admin", "test", "demo"):
            logger.warning("Authorization blocked for restricted ID: %s", customer_id)
            return False
        return True

    def block_irreversible_actions(
        self,
        query: str,
        response: str,
    ) -> Dict[str, Any]:
        """Scan for and block irreversible actions in AI responses."""
        combined = (query + " " + response).lower()
        blocked: List[str] = []

        # Check set-based actions
        for action in self._IRREVERSIBLE_ACTIONS:
            if action.replace("_", " ") in combined or action in combined:
                blocked.append(action)

        # Check regex patterns for natural language variants
        for pattern in self._IRREVERSIBLE_PATTERNS:
            if re.search(pattern, combined):
                blocked.append(pattern)

        for term in self.blocked_terms:
            if term.lower() in combined:
                blocked.append(term)

        should_block = len(blocked) > 0
        return {
            "blocked": should_block,
            "blocked_actions": blocked,
            "recommendation": (
                "Response contains irreversible actions - require human confirmation"
                if should_block
                else "No irreversible actions detected"
            ),
        }

    def record_interaction(self, interaction: AISupportInteraction) -> bool:
        """Persist the interaction for audit and quality purposes."""
        self._interactions[interaction.interaction_id] = interaction
        logger.debug("Recorded interaction %s", interaction.interaction_id)
        return True

    def verify_knowledge_source(self, response: str) -> Dict[str, Any]:
        """Verify the response is grounded in approved knowledge sources."""
        sources_mentioned: List[str] = []
        for source in self.allowed_knowledge_sources:
            if source.lower() in response.lower():
                sources_mentioned.append(source)

        verified = len(sources_mentioned) > 0 or len(self.allowed_knowledge_sources) == 0
        return {
            "verified": verified,
            "sources_mentioned": sources_mentioned,
            "recommendation": (
                "Response references approved knowledge sources"
                if verified
                else "Response may not cite approved sources - review"
            ),
        }

    def trigger_human_handoff(self, interaction: AISupportInteraction) -> bool:
        """Determine if a human handoff is required.

        Returns True if any safety check indicates human intervention needed.
        """
        reasons: List[str] = []

        if interaction.uncertainty_flagged:
            reasons.append("uncertainty_detected")
        if not interaction.fabrication_check_passed:
            reasons.append("fabrication_flagged")
        if not interaction.cross_customer_check_passed:
            reasons.append("cross_customer_risk")
        if interaction.sensitive_topic_escalated:
            reasons.append("sensitive_topic")
        if not interaction.auth_verified:
            reasons.append("auth_failed")
        if interaction.irreversible_action_blocked:
            reasons.append("irreversible_action_detected")
        if interaction.confidence_score < 0.5:
            reasons.append("low_confidence")

        should_handoff = len(reasons) > 0
        if should_handoff:
            logger.warning(
                "Human handoff triggered for %s: %s",
                interaction.interaction_id,
                reasons,
            )

        return should_handoff

    def audit_ai_interaction(
        self,
        interaction: AISupportInteraction,
    ) -> Dict[str, Any]:
        """Produce a full audit trail for an AI support interaction."""
        rules_status = {
            AISupportRule.IDENTIFY_UNCERTAINTY.value: interaction.uncertainty_flagged,
            AISupportRule.NO_FABRICATION.value: interaction.fabrication_check_passed,
            AISupportRule.NO_CROSS_CUSTOMER_DATA.value: interaction.cross_customer_check_passed,
            AISupportRule.ESCALATE_SENSITIVE.value: interaction.sensitive_topic_escalated,
            AISupportRule.RESPECT_AUTH.value: interaction.auth_verified,
            AISupportRule.NO_IRREVERSIBLE_ACTIONS.value: interaction.irreversible_action_blocked,
            AISupportRule.RECORD_INTERACTIONS.value: interaction.interaction_recorded,
            AISupportRule.USE_APPROVED_KNOWLEDGE.value: interaction.knowledge_source_verified,
            AISupportRule.HUMAN_HANDOFF.value: interaction.human_handoff_triggered,
        }

        all_checks_passed = all((
            not interaction.uncertainty_flagged,
            interaction.fabrication_check_passed,
            interaction.cross_customer_check_passed,
            not interaction.sensitive_topic_escalated,
            interaction.auth_verified,
            not interaction.irreversible_action_blocked,
            interaction.interaction_recorded,
            interaction.knowledge_source_verified,
            not interaction.human_handoff_triggered,
        ))

        return {
            "interaction_id": interaction.interaction_id,
            "customer_id": interaction.customer_id,
            "timestamp": interaction.timestamp.isoformat(),
            "confidence_score": interaction.confidence_score,
            "rules_status": rules_status,
            "all_checks_passed": all_checks_passed,
            "human_handoff_triggered": interaction.human_handoff_triggered,
            "recommendation": (
                "Interaction passed all guard checks"
                if all_checks_passed
                else "Interaction requires review or human handoff"
            ),
        }

    # ------------------------------------------------------------------
    # Queue management
    # ------------------------------------------------------------------

    def get_human_queue(self) -> List[str]:
        """Return list of interaction IDs queued for human review."""
        return list(self._human_queue)

    def clear_human_queue(self) -> None:
        """Clear the human review queue."""
        self._human_queue.clear()
        logger.info("Human handoff queue cleared")