"""
Customer Communication Templates.

Manages standardized communication templates for incident
notifications, status updates, feature announcements, and
other customer-facing communications.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("enterprise.customer_experience")


class TemplateType(Enum):
    """Types of customer communication templates."""

    INCIDENT_NOTIFICATION = "incident_notification"
    STATUS_UPDATE = "status_update"
    RESOLUTION_UPDATE = "resolution_update"
    MAINTENANCE_ANNOUNCEMENT = "maintenance_announcement"
    FEATURE_ANNOUNCEMENT = "feature_announcement"
    DEPRECATION_NOTICE = "deprecation_notice"
    SECURITY_ADVISORY = "security_advisory"
    SLA_BREACH_NOTIFICATION = "sla_breach_notification"
    ONBOARDING_WELCOME = "onboarding_welcome"
    RENEWAL_REMINDER = "renewal_reminder"
    CUSTOM = "custom"


@dataclass
class CommsTemplate:
    """A reusable communication template."""

    template_type: TemplateType
    subject_line: str
    body_template: str
    tone: str = "professional"
    required_fields: List[str] = field(default_factory=list)
    channel: str = "email"
    audience: str = "all"
    metadata: Dict[str, Any] = field(default_factory=dict)


class TemplateManager:
    """Manages templating, rendering, and delivery of customer communications."""

    # Built-in templates
    _DEFAULT_TEMPLATES: Dict[TemplateType, CommsTemplate] = {}

    def __init__(self) -> None:
        self._templates: Dict[TemplateType, CommsTemplate] = {}
        self._delivery_log: List[Dict[str, Any]] = []
        self._scheduled: List[Dict[str, Any]] = []
        self._load_defaults()
        logger.info("TemplateManager initialized with %d templates", len(self._templates))

    # ------------------------------------------------------------------
    # Template management
    # ------------------------------------------------------------------

    def load_template(self, template_type: TemplateType) -> Optional[CommsTemplate]:
        """Load a template by type. Returns None if not found."""
        tmpl = self._templates.get(template_type)
        if tmpl:
            logger.debug("Loaded template: %s", template_type.value)
        else:
            logger.warning("Template not found: %s", template_type.value)
        return tmpl

    def register_template(self, template: CommsTemplate) -> None:
        """Register or overwrite a custom template."""
        self._templates[template.template_type] = template
        logger.info("Registered template: %s", template.template_type.value)

    def list_templates(self) -> List[Dict[str, str]]:
        return [
            {
                "type": t.template_type.value,
                "subject": t.subject_line,
                "tone": t.tone,
                "channel": t.channel,
                "audience": t.audience,
                "required_fields": t.required_fields,
            }
            for t in self._templates.values()
        ]

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render_template(
        self,
        template_type: TemplateType,
        context: Dict[str, str],
    ) -> Dict[str, Any]:
        """Render a template with the given context variables.

        Supports `{variable}` substitution throughout subject and body.
        Validates all required fields are present in context.

        Returns:
            dict with 'subject', 'body', 'channel', 'rendered_at'.
        """
        template = self.load_template(template_type)
        if template is None:
            raise ValueError(f"Template type '{template_type.value}' not found")

        # Validate required fields before rendering
        missing = self.validate_required_fields(template, context)
        if missing:
            raise ValueError(
                f"Template '{template_type.value}' missing "
                f"required fields: {missing}"
            )

        # Render subject
        subject = template.subject_line.format(**context)

        # Render body
        try:
            body = template.body_template.format(**context)
        except KeyError as exc:
            raise ValueError(
                f"Missing context variable '{exc.args[0]}' for template "
                f"'{template_type.value}'"
            ) from exc

        rendered = {
            "subject": subject,
            "body": body,
            "channel": template.channel,
            "audience": template.audience,
            "tone": template.tone,
            "rendered_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.debug("Rendered template: %s", template_type.value)
        return rendered

    def validate_required_fields(
        self,
        template: CommsTemplate,
        context: Dict[str, str],
    ) -> List[str]:
        """Validate that all required fields are present in context.

        Returns a list of missing field names (empty = valid).
        """
        missing = [f for f in template.required_fields if f not in context]
        if missing:
            logger.warning(
                "Template '%s' missing required fields: %s",
                template.template_type.value,
                missing,
            )
        return missing

    # ------------------------------------------------------------------
    # Customization
    # ------------------------------------------------------------------

    def customize_for_audience(
        self,
        template_type: TemplateType,
        audience: str,
        tone: Optional[str] = None,
        channel: Optional[str] = None,
        override_subject: Optional[str] = None,
        override_body: Optional[str] = None,
    ) -> CommsTemplate:
        """Create an audience-specific variant of a template.

        Returns a new template with the requested customizations while
        keeping the original intact.
        """
        original = self.load_template(template_type)
        if original is None:
            raise ValueError(f"Template '{template_type.value}' not found")

        customized = CommsTemplate(
            template_type=template_type,
            subject_line=override_subject or original.subject_line,
            body_template=override_body or original.body_template,
            tone=tone or original.tone,
            required_fields=list(original.required_fields),
            channel=channel or original.channel,
            audience=audience,
        )
        logger.info(
            "Customized template '%s' for audience '%s'",
            template_type.value,
            audience,
        )
        return customized

    # ------------------------------------------------------------------
    # Delivery
    # ------------------------------------------------------------------

    def send_notification(
        self,
        template_type: TemplateType,
        context: Dict[str, str],
        recipients: Optional[List[str]] = None,
        simulate: bool = True,
    ) -> Dict[str, Any]:
        """Render and send/deliver a notification.

        In production this would integrate with an email/SMS/push provider.
        By default runs in simulation mode for safe development.

        Args:
            template_type: Which template to use.
            context: Variable substitutions.
            recipients: List of recipient identifiers (email, user ID, etc.).
            simulate: If True, logs but doesn't actually send.

        Returns:
            Delivery result with rendered content and delivery status.
        """
        rendered = self.render_template(template_type, context)

        delivery_record = {
            "template_type": template_type.value,
            "rendered": rendered,
            "recipients": recipients or ["broadcast"],
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "simulated": simulate,
            "delivery_id": f"del_{int(datetime.now(timezone.utc).timestamp())}",
        }

        if simulate:
            delivery_record["status"] = "simulated"
            logger.info(
                "SIMULATED send of '%s' to %d recipient(s)",
                template_type.value,
                len(recipients or ["broadcast"]),
            )
        else:
            # Production path: call actual delivery provider
            delivery_record["status"] = "sent"
            logger.info(
                "Sent '%s' to %d recipient(s)",
                template_type.value,
                len(recipients or ["broadcast"]),
            )

        self._delivery_log.append(delivery_record)
        return delivery_record

    def schedule_communication(
        self,
        template_type: TemplateType,
        context: Dict[str, str],
        send_at: datetime,
        recipients: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Schedule a communication for future delivery.

        In production this integrates with a job scheduler like Celery
        or a cron-based delivery system.
        """
        schedule_entry = {
            "schedule_id": f"sched_{int(datetime.now(timezone.utc).timestamp())}",
            "template_type": template_type.value,
            "context": context,
            "send_at": send_at.isoformat(),
            "recipients": recipients or ["broadcast"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "scheduled",
        }
        self._scheduled.append(schedule_entry)
        logger.info(
            "Scheduled '%s' for %s",
            template_type.value,
            send_at.isoformat(),
        )
        return schedule_entry

    def track_delivery(
        self,
        delivery_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Track delivery status of sent/simulated communications."""
        log = self._delivery_log
        if delivery_id:
            log = [e for e in log if e.get("delivery_id") == delivery_id]

        total = len(log)
        by_status = {}
        for entry in log:
            status = entry.get("status", "unknown")
            by_status[status] = by_status.get(status, 0) + 1

        by_template = {}
        for entry in log:
            tt = entry.get("template_type", "unknown")
            by_template[tt] = by_template.get(tt, 0) + 1

        return {
            "total_deliveries": total,
            "by_status": by_status,
            "by_template_type": by_template,
            "scheduled_pending": len(self._scheduled),
            "last_delivery": log[-1] if log else None,
        }

    # ------------------------------------------------------------------
    # Default templates
    # ------------------------------------------------------------------

    def _load_defaults(self) -> None:
        """Load the built-in default templates."""
        defaults = {
            TemplateType.INCIDENT_NOTIFICATION: CommsTemplate(
                template_type=TemplateType.INCIDENT_NOTIFICATION,
                subject_line="[Action Required] {severity} Incident: {incident_summary}",
                body_template=(
                    "Dear {customer_name},\n\n"
                    "We are writing to inform you that we have identified a {severity} "
                    "incident affecting {affected_service}.\n\n"
                    "Impact: {impact_description}\n"
                    "Current Status: {current_status}\n"
                    "Estimated Resolution: {eta}\n\n"
                    "What we are doing: {mitigation_steps}\n\n"
                    "We will provide updates every {update_frequency}. "
                    "If you have urgent questions, please contact {support_contact}.\n\n"
                    "Sincerely,\n{company_name} Support Team"
                ),
                tone="urgent",
                required_fields=[
                    "customer_name", "severity", "incident_summary",
                    "affected_service", "impact_description", "current_status",
                    "eta", "mitigation_steps", "update_frequency",
                    "support_contact", "company_name",
                ],
                channel="email",
                audience="affected",
            ),
            TemplateType.STATUS_UPDATE: CommsTemplate(
                template_type=TemplateType.STATUS_UPDATE,
                subject_line="Update: {incident_summary} - Status Change",
                body_template=(
                    "Dear {customer_name},\n\n"
                    "Here is an update on the {severity} incident regarding "
                    "{affected_service}.\n\n"
                    "Previous Status: {previous_status}\n"
                    "Current Status: {current_status}\n"
                    "Progress: {progress_update}\n"
                    "Next Update: {next_update_time}\n\n"
                    "Thank you for your patience.\n\n"
                    "{company_name} Support Team"
                ),
                tone="professional",
                required_fields=[
                    "customer_name", "incident_summary", "severity",
                    "affected_service", "previous_status", "current_status",
                    "progress_update", "next_update_time", "company_name",
                ],
                channel="email",
                audience="affected",
            ),
            TemplateType.RESOLUTION_UPDATE: CommsTemplate(
                template_type=TemplateType.RESOLUTION_UPDATE,
                subject_line="Resolved: {incident_summary}",
                body_template=(
                    "Dear {customer_name},\n\n"
                    "We are pleased to inform you that the {severity} incident "
                    "regarding {affected_service} has been resolved.\n\n"
                    "Resolution: {resolution_summary}\n"
                    "Root Cause: {root_cause}\n"
                    "Preventive Measures: {preventive_measures}\n\n"
                    "We apologize for any inconvenience this may have caused. "
                    "If you continue to experience issues, please contact "
                    "{support_contact}.\n\n"
                    "{company_name} Support Team"
                ),
                tone="professional",
                required_fields=[
                    "customer_name", "incident_summary", "severity",
                    "affected_service", "resolution_summary", "root_cause",
                    "preventive_measures", "support_contact", "company_name",
                ],
                channel="email",
                audience="affected",
            ),
            TemplateType.MAINTENANCE_ANNOUNCEMENT: CommsTemplate(
                template_type=TemplateType.MAINTENANCE_ANNOUNCEMENT,
                subject_line="Scheduled Maintenance: {affected_service} on {maintenance_date}",
                body_template=(
                    "Dear {customer_name},\n\n"
                    "We will be performing scheduled maintenance on "
                    "{affected_service}.\n\n"
                    "Window: {maintenance_window}\n"
                    "Expected Downtime: {expected_downtime}\n"
                    "Impact: {impact_description}\n\n"
                    "We recommend {recommended_action} during this period.\n\n"
                    "If you have questions, please contact {support_contact}.\n\n"
                    "{company_name} Team"
                ),
                tone="informational",
                required_fields=[
                    "customer_name", "affected_service", "maintenance_date",
                    "maintenance_window", "expected_downtime",
                    "impact_description", "recommended_action",
                    "support_contact", "company_name",
                ],
                channel="email",
                audience="all",
            ),
            TemplateType.FEATURE_ANNOUNCEMENT: CommsTemplate(
                template_type=TemplateType.FEATURE_ANNOUNCEMENT,
                subject_line="New Feature: {feature_name} is now available!",
                body_template=(
                    "Dear {customer_name},\n\n"
                    "We're excited to announce {feature_name}, a new feature "
                    "designed to help you {feature_benefit}.\n\n"
                    "Key Capabilities:\n{key_capabilities}\n\n"
                    "Getting Started: {getting_started_link}\n"
                    "Documentation: {documentation_link}\n\n"
                    "We'd love to hear your feedback at {feedback_email}.\n\n"
                    "{company_name} Team"
                ),
                tone="enthusiastic",
                required_fields=[
                    "customer_name", "feature_name", "feature_benefit",
                    "key_capabilities", "getting_started_link",
                    "documentation_link", "feedback_email", "company_name",
                ],
                channel="email",
                audience="all",
            ),
            TemplateType.DEPRECATION_NOTICE: CommsTemplate(
                template_type=TemplateType.DEPRECATION_NOTICE,
                subject_line="Important: {feature_name} will be deprecated on {deprecation_date}",
                body_template=(
                    "Dear {customer_name},\n\n"
                    "We want to inform you that {feature_name} will be deprecated "
                    "effective {deprecation_date}.\n\n"
                    "Reason: {deprecation_reason}\n"
                    "Migration Path: {migration_path}\n"
                    "Action Required: {action_required}\n\n"
                    "Timeline:\n{timeline}\n\n"
                    "For assistance with migration, please contact "
                    "{support_contact}.\n\n"
                    "{company_name} Team"
                ),
                tone="professional",
                required_fields=[
                    "customer_name", "feature_name", "deprecation_date",
                    "deprecation_reason", "migration_path",
                    "action_required", "timeline", "support_contact",
                    "company_name",
                ],
                channel="email",
                audience="affected",
            ),
            TemplateType.SECURITY_ADVISORY: CommsTemplate(
                template_type=TemplateType.SECURITY_ADVISORY,
                subject_line="[CONFIDENTIAL] Security Advisory: {advisory_id}",
                body_template=(
                    "Dear {customer_name},\n\n"
                    "This is a confidential security advisory regarding "
                    "{vulnerability_summary}.\n\n"
                    "Severity: {severity}\n"
                    "CVE ID: {cve_id}\n"
                    "Affected Versions: {affected_versions}\n"
                    "Fixed Versions: {fixed_versions}\n\n"
                    "Recommended Action: {recommended_action}\n\n"
                    "We strongly recommend {urgency_action} by "
                    "{remediation_deadline}.\n\n"
                    "For questions about this advisory, contact "
                    "{security_contact}.\n\n"
                    "{company_name} Security Team"
                ),
                tone="formal",
                required_fields=[
                    "customer_name", "advisory_id", "vulnerability_summary",
                    "severity", "cve_id", "affected_versions",
                    "fixed_versions", "recommended_action", "urgency_action",
                    "remediation_deadline", "security_contact", "company_name",
                ],
                channel="email",
                audience="affected",
            ),
            TemplateType.SLA_BREACH_NOTIFICATION: CommsTemplate(
                template_type=TemplateType.SLA_BREACH_NOTIFICATION,
                subject_line="SLA Breach Notice: Ticket #{ticket_id}",
                body_template=(
                    "Dear {customer_name},\n\n"
                    "We are writing to inform you that we have not met the "
                    "agreed-upon service level for support ticket #{ticket_id}.\n\n"
                    "Ticket Subject: {ticket_subject}\n"
                    "SLA Type Breached: {sla_type}\n"
                    "Target: {sla_target}\n"
                    "Current Status: {current_status}\n\n"
                    "What we are doing: We have escalated your ticket to "
                    "{escalation_team} and are prioritizing resolution.\n\n"
                    "We take our SLAs seriously and apologize for this breach. "
                    "You will receive an updated response within "
                    "{next_response_timeframe}.\n\n"
                    "{company_name} Support Team"
                ),
                tone="apologetic",
                required_fields=[
                    "customer_name", "ticket_id", "ticket_subject",
                    "sla_type", "sla_target", "current_status",
                    "escalation_team", "next_response_timeframe",
                    "company_name",
                ],
                channel="email",
                audience="affected",
            ),
            TemplateType.ONBOARDING_WELCOME: CommsTemplate(
                template_type=TemplateType.ONBOARDING_WELCOME,
                subject_line="Welcome to {company_name}, {customer_name}!",
                body_template=(
                    "Dear {customer_name},\n\n"
                    "Welcome to {company_name}! We're thrilled to have you on board.\n\n"
                    "To help you get started, here are some resources:\n\n"
                    "- Quick Start Guide: {quick_start_link}\n"
                    "- Documentation: {documentation_link}\n"
                    "- Your Account Manager: {account_manager}\n"
                    "- Support: {support_contact}\n\n"
                    "Your next step: {first_action}\n\n"
                    "We're here to help you succeed. Don't hesitate to reach out!\n\n"
                    "{company_name} Team"
                ),
                tone="welcoming",
                required_fields=[
                    "customer_name", "company_name", "quick_start_link",
                    "documentation_link", "account_manager",
                    "support_contact", "first_action",
                ],
                channel="email",
                audience="individual",
            ),
            TemplateType.RENEWAL_REMINDER: CommsTemplate(
                template_type=TemplateType.RENEWAL_REMINDER,
                subject_line="Your {plan_name} subscription renews on {renewal_date}",
                body_template=(
                    "Dear {customer_name},\n\n"
                    "This is a friendly reminder that your {plan_name} subscription "
                    "with {company_name} will renew on {renewal_date}.\n\n"
                    "Plan Details:\n"
                    "- Plan: {plan_name}\n"
                    "- Renewal Date: {renewal_date}\n"
                    "- Renewal Term: {renewal_term}\n"
                    "- Amount: {renewal_amount}\n\n"
                    "What's new since your last renewal:\n{whats_new}\n\n"
                    "If you have questions about your renewal, please contact "
                    "{account_manager} at {account_manager_email}.\n\n"
                    "{company_name} Team"
                ),
                tone="friendly",
                required_fields=[
                    "customer_name", "plan_name", "company_name",
                    "renewal_date", "renewal_term", "renewal_amount",
                    "whats_new", "account_manager", "account_manager_email",
                ],
                channel="email",
                audience="individual",
            ),
        }

        for tt, tmpl in defaults.items():
            self._templates[tt] = tmpl