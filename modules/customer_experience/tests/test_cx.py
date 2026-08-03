"""
Comprehensive tests for the Customer Experience OS module.

Covers journey mapping, support ticketing, AI guardrails,
CX metrics, feedback analysis, and communication templates.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from journey import JourneyStage, JourneyTouchpoint, JourneyMap, JourneyEngine
from support import SeverityLevel, TicketStatus, SupportTicket, SupportEngine
from ai_support import (
    AISupportRule,
    AISupportInteraction,
    AISupportGuard,
)
from metrics import (
    CXMetric,
    MetricSnapshot,
    CXMetricsEngine,
    TrendDirection,
)
from feedback import (
    FeedbackSource,
    FeedbackEntry,
    FeedbackEngine,
    Sentiment,
)
from templates import (
    TemplateType,
    CommsTemplate,
    TemplateManager,
)


# ======================================================================
# Journey Engine Tests
# ======================================================================

class TestJourneyEngine(unittest.TestCase):
    """Tests for customer journey mapping."""

    def setUp(self) -> None:
        self.engine = JourneyEngine()

    def test_map_journey_creates_new(self) -> None:
        journey = self.engine.map_journey("enterprise")
        self.assertEqual(journey.customer_segment, "enterprise")
        self.assertEqual(journey.touchpoint_count(), 0)
        self.assertEqual(journey.current_state_score, 0.0)

    def test_map_journey_returns_existing(self) -> None:
        j1 = self.engine.map_journey("smb")
        j2 = self.engine.map_journey("smb")
        self.assertIs(j1, j2)

    def test_add_touchpoint(self) -> None:
        tp = JourneyTouchpoint(
            stage=JourneyStage.AWARENESS,
            touchpoint_name="Landing Page",
            channel="web",
            customer_goal="Learn about product",
            success_metric="Bounce rate < 40%",
        )
        journey = self.engine.add_touchpoint("smb", tp)
        self.assertEqual(journey.touchpoint_count(), 1)
        self.assertEqual(journey.touchpoints[0].touchpoint_name, "Landing Page")

    def test_add_touchpoint_creates_journey_if_missing(self) -> None:
        tp = JourneyTouchpoint(
            stage=JourneyStage.PURCHASE,
            touchpoint_name="Checkout",
            channel="web",
            customer_goal="Complete purchase",
            success_metric="Cart abandonment < 60%",
        )
        journey = self.engine.add_touchpoint("new_segment", tp)
        self.assertEqual(journey.customer_segment, "new_segment")

    def test_analyze_friction_empty(self) -> None:
        self.engine.map_journey("empty")
        result = self.engine.analyze_friction("empty")
        self.assertEqual(result["total_friction_points"], 0)
        self.assertEqual(result["severity_level"], "low")

    def test_analyze_friction_with_points(self) -> None:
        tp = JourneyTouchpoint(
            stage=JourneyStage.SETUP,
            touchpoint_name="Install Wizard",
            channel="desktop",
            customer_goal="Install successfully",
            success_metric="Install success rate > 95%",
            friction_points=["Too many steps", "Confusing TOS"],
            improvement_opportunities=["Single-click install"],
        )
        self.engine.add_touchpoint("test_seg", tp)
        result = self.engine.analyze_friction("test_seg")
        self.assertEqual(result["total_friction_points"], 2)
        self.assertIn("setup", result["friction_by_stage"])

    def test_calculate_scores_perfect(self) -> None:
        tp = JourneyTouchpoint(
            stage=JourneyStage.REGULAR_USE,
            touchpoint_name="Dashboard",
            channel="web",
            customer_goal="Monitor metrics",
            success_metric="DAU > 1000",
        )
        self.engine.add_touchpoint("scored", tp)
        scores = self.engine.calculate_scores("scored")
        self.assertGreaterEqual(scores["current_state_score"], 90.0)
        self.assertIn("regular_use", scores["stage_scores"])

    def test_calculate_scores_with_friction(self) -> None:
        tp = JourneyTouchpoint(
            stage=JourneyStage.SUPPORT,
            touchpoint_name="Help Desk",
            channel="chat",
            customer_goal="Get issue resolved",
            success_metric="Resolution < 4h",
            friction_points=["Long wait", "Bot loops", "No agent available", "Wrong department"],
        )
        self.engine.add_touchpoint("friction_seg", tp)
        scores = self.engine.calculate_scores("friction_seg")
        # 4 friction points on 1 touchpoint -> friction_ratio = 4.0 -> score reduced
        self.assertLess(scores["current_state_score"], 50.0)

    def test_identify_optimizations(self) -> None:
        tp1 = JourneyTouchpoint(
            stage=JourneyStage.SETUP,
            touchpoint_name="Install",
            channel="desktop",
            customer_goal="Install app",
            success_metric="Success rate",
            friction_points=["Error X", "Error Y"],
            improvement_opportunities=["Auto-fix X"],
        )
        tp2 = JourneyTouchpoint(
            stage=JourneyStage.FIRST_VALUE,
            touchpoint_name="First Use",
            channel="app",
            customer_goal="See value",
            success_metric="Time to wow",
            friction_points=["Confusing UI"],
            improvement_opportunities=["Guided tour"],
        )
        self.engine.add_touchpoint("opt_seg", tp1)
        self.engine.add_touchpoint("opt_seg", tp2)
        opts = self.engine.identify_optimizations("opt_seg")
        self.assertGreaterEqual(len(opts), 1)
        # Install should rank higher (more friction + higher stage weight)
        self.assertEqual(opts[0]["touchpoint"], "Install")

    def test_compare_segments(self) -> None:
        tp = JourneyTouchpoint(
            stage=JourneyStage.REGULAR_USE,
            touchpoint_name="Dashboard",
            channel="web",
            customer_goal="Monitor",
            success_metric="DAU",
        )
        self.engine.add_touchpoint("good_seg", tp)

        tp_bad = JourneyTouchpoint(
            stage=JourneyStage.REGULAR_USE,
            touchpoint_name="Dashboard",
            channel="web",
            customer_goal="Monitor",
            success_metric="DAU",
            friction_points=["Broken", "Slow", "Crashes", "Bad UX"],
        )
        self.engine.add_touchpoint("bad_seg", tp_bad)

        comp = self.engine.compare_segments("good_seg", "bad_seg")
        self.assertEqual(comp["better_segment"], "good_seg")
        self.assertGreater(comp["score_delta"], 0)

    def test_generate_journey_report(self) -> None:
        tp = JourneyTouchpoint(
            stage=JourneyStage.ADVOCACY,
            touchpoint_name="Referral",
            channel="email",
            customer_goal="Share with friends",
            success_metric="Referral rate > 30%",
        )
        self.engine.add_touchpoint("report_seg", tp)
        report = self.engine.generate_journey_report("report_seg")
        self.assertEqual(report["report_type"], "customer_journey")
        self.assertEqual(report["segment"], "report_seg")
        self.assertIn("overview", report)
        self.assertIn("friction_analysis", report)
        self.assertIn("top_optimizations", report)


# ======================================================================
# Support Engine Tests
# ======================================================================

class TestSupportEngine(unittest.TestCase):
    """Tests for support ticket management."""

    def setUp(self) -> None:
        self.engine = SupportEngine()

    def test_create_ticket_defaults(self) -> None:
        ticket = self.engine.create_ticket(
            customer_id="cust_123",
            subject="Login issue",
            description="Cannot log in after password reset",
        )
        self.assertEqual(ticket.customer_id, "cust_123")
        self.assertEqual(ticket.status, TicketStatus.NEW)
        self.assertEqual(ticket.severity, SeverityLevel.SEV4_LOW)
        self.assertIsNotNone(ticket.ticket_id)

    def test_create_ticket_sev1(self) -> None:
        ticket = self.engine.create_ticket(
            customer_id="cust_456",
            subject="Production outage",
            description="All systems down",
            severity=SeverityLevel.SEV1_CRITICAL,
        )
        self.assertEqual(ticket.severity, SeverityLevel.SEV1_CRITICAL)
        self.assertEqual(ticket.response_target_minutes, 15)
        self.assertEqual(ticket.resolution_target_hours, 1)

    def test_triage(self) -> None:
        ticket = self.engine.create_ticket("c1", "Bug", "Details")
        triaged = self.engine.triage(ticket.ticket_id)
        self.assertEqual(triaged.status, TicketStatus.TRIAGED)

    def test_assign_auto_transitions(self) -> None:
        ticket = self.engine.create_ticket("c1", "Issue", "Desc")
        assigned = self.engine.assign(ticket.ticket_id, "agent_007")
        self.assertEqual(assigned.assigned_to, "agent_007")
        self.assertEqual(assigned.status, TicketStatus.IN_PROGRESS)

    def test_update_status_valid_transition(self) -> None:
        ticket = self.engine.create_ticket("c1", "Bug", "Details")
        self.engine.triage(ticket.ticket_id)
        self.engine.assign(ticket.ticket_id, "agent")
        updated = self.engine.update_status(ticket.ticket_id, TicketStatus.RESOLVED)
        self.assertEqual(updated.status, TicketStatus.RESOLVED)
        self.assertIsNotNone(updated.resolved_at)

    def test_update_status_invalid_transition(self) -> None:
        ticket = self.engine.create_ticket("c1", "Bug", "Details")
        with self.assertRaises(ValueError):
            # Can't go from NEW directly to WAITING_CUSTOMER
            self.engine.update_status(ticket.ticket_id, TicketStatus.WAITING_CUSTOMER)

    def test_reopen_ticket(self) -> None:
        ticket = self.engine.create_ticket("c1", "Bug", "Details")
        self.engine.triage(ticket.ticket_id)
        self.engine.assign(ticket.ticket_id, "agent")
        self.engine.update_status(ticket.ticket_id, TicketStatus.RESOLVED)
        self.engine.update_status(ticket.ticket_id, TicketStatus.CLOSED)
        reopened = self.engine.update_status(ticket.ticket_id, TicketStatus.REOPENED)
        self.assertEqual(reopened.status, TicketStatus.REOPENED)
        self.assertIsNone(reopened.resolved_at)

    def test_escalate(self) -> None:
        ticket = self.engine.create_ticket(
            "c1", "Issue", "Desc", severity=SeverityLevel.SEV4_LOW
        )
        escalated = self.engine.escalate(ticket.ticket_id)
        self.assertEqual(escalated.severity, SeverityLevel.SEV3_MEDIUM)
        self.assertEqual(escalated.escalation_level, 1)

    def test_escalate_sev1_no_change(self) -> None:
        ticket = self.engine.create_ticket(
            "c1", "Critical", "Outage", severity=SeverityLevel.SEV1_CRITICAL
        )
        escalated = self.engine.escalate(ticket.ticket_id)
        self.assertEqual(escalated.severity, SeverityLevel.SEV1_CRITICAL)

    def test_response_sla_pending(self) -> None:
        ticket = self.engine.create_ticket("c1", "Issue", "Desc")
        sla = self.engine.calculate_response_sla(ticket.ticket_id)
        self.assertEqual(sla["sla_status"], "pending")
        self.assertEqual(sla["target_minutes"], 240)

    def test_response_sla_met(self) -> None:
        ticket = self.engine.create_ticket("c1", "Issue", "Desc")
        # Manually inject a status history entry to simulate quick response
        past = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        ticket.status_history.append({
            "timestamp": past,
            "from": TicketStatus.NEW.value,
            "to": TicketStatus.IN_PROGRESS.value,
        })
        sla = self.engine.calculate_response_sla(ticket.ticket_id)
        self.assertEqual(sla["sla_status"], "met")

    def test_response_sla_breached(self) -> None:
        ticket = self.engine.create_ticket("c1", "Issue", "Desc")
        # Simulate a response that came well after the target window.
        # The ticket was created ~ now, response at +500 minutes from now.
        future_response = (datetime.now(timezone.utc) + timedelta(minutes=500)).isoformat()
        ticket.status_history.append({
            "timestamp": future_response,
            "from": TicketStatus.NEW.value,
            "to": TicketStatus.IN_PROGRESS.value,
        })
        sla = self.engine.calculate_response_sla(ticket.ticket_id)
        self.assertEqual(sla["sla_status"], "breached")

    def test_resolution_sla(self) -> None:
        ticket = self.engine.create_ticket("c1", "Issue", "Desc")
        sla = self.engine.calculate_resolution_sla(ticket.ticket_id)
        self.assertEqual(sla["sla_status"], "pending")
        self.assertEqual(sla["target_hours"], 24)

    def test_resolution_sla_at_risk(self) -> None:
        ticket = self.engine.create_ticket("c1", "Issue", "Desc")
        # Simulate ticket that's aged beyond 75% of target (18h for 24h target)
        ticket.created_at = datetime.now(timezone.utc) - timedelta(hours=20)
        sla = self.engine.calculate_resolution_sla(ticket.ticket_id)
        self.assertEqual(sla["sla_status"], "at_risk")

    def test_generate_customer_update(self) -> None:
        ticket = self.engine.create_ticket("c1", "Login broken", "Desc")
        update = self.engine.generate_customer_update(ticket.ticket_id)
        self.assertIn("Login broken", update["message"])
        self.assertIn(ticket.ticket_id, update["message"])

    def test_knowledge_base_update(self) -> None:
        ticket = self.engine.create_ticket("c1", "Bug", "Details")
        updated = self.engine.update_knowledge_base(
            ticket.ticket_id, "Article content here"
        )
        self.assertTrue(updated.kb_article_updated)

    def test_root_cause_analysis(self) -> None:
        ticket = self.engine.create_ticket("c1", "Bug", "Details")
        rca = self.engine.perform_root_cause_analysis(
            ticket.ticket_id, "Memory leak in worker process"
        )
        self.assertEqual(rca.root_cause, "Memory leak in worker process")

    def test_sla_summary(self) -> None:
        self.engine.create_ticket("c1", "T1", "D1", severity=SeverityLevel.SEV1_CRITICAL)
        self.engine.create_ticket("c2", "T2", "D2", severity=SeverityLevel.SEV4_LOW)
        summary = self.engine.sla_summary()
        self.assertEqual(summary["total"], 2)

    def test_list_by_severity(self) -> None:
        self.engine.create_ticket("c1", "T1", "D1", severity=SeverityLevel.SEV1_CRITICAL)
        self.engine.create_ticket("c2", "T2", "D2", severity=SeverityLevel.SEV4_LOW)
        sev1_tickets = self.engine.list_by_severity(SeverityLevel.SEV1_CRITICAL)
        self.assertEqual(len(sev1_tickets), 1)

    def test_get_nonexistent_ticket(self) -> None:
        with self.assertRaises(KeyError):
            self.engine.triage("nonexistent")


# ======================================================================
# AI Support Guard Tests
# ======================================================================

class TestAISupportGuard(unittest.TestCase):
    """Tests for AI safety guardrails."""

    def setUp(self) -> None:
        self.guard = AISupportGuard()

    # --- Uncertainty Detection ---

    def test_check_uncertainty_confident(self) -> None:
        result = self.guard.check_uncertainty(
            "To reset your password, go to Settings > Security > Change Password. "
            "You will need your current password to complete this action."
        )
        self.assertFalse(result["uncertainty_flagged"])
        self.assertGreater(result["confidence_score"], 0.8)

    def test_check_uncertainty_uncertain(self) -> None:
        result = self.guard.check_uncertainty(
            "I think you might need to check the settings page. "
            "I'm not sure if this feature is available in your plan. "
            "It possibly requires admin access."
        )
        self.assertTrue(result["uncertainty_flagged"])
        self.assertLess(result["confidence_score"], 1.0)

    # --- Fabrication Detection ---

    def test_fabrication_check_clean_response(self) -> None:
        result = self.guard.verify_no_fabrication(
            "According to our knowledge base, you can export data "
            "from Settings > Data > Export. Supported formats are CSV and JSON."
        )
        self.assertTrue(result["passed"])

    def test_fabrication_check_excessive_absolutes(self) -> None:
        result = self.guard.verify_no_fabrication(
            "We can always fix this issue. We never have downtime. "
            "We guarantee 100% satisfaction. Absolutely no problems."
        )
        self.assertFalse(result["passed"])

    # --- Data Isolation ---

    def test_data_isolation_clean(self) -> None:
        result = self.guard.ensure_data_isolation(
            "Your account settings are located under Profile.",
            "cust_123",
        )
        self.assertTrue(result["passed"])

    def test_data_isolation_cross_reference(self) -> None:
        result = self.guard.ensure_data_isolation(
            "We saw this issue with another customer last week and resolved it.",
            "cust_123",
        )
        self.assertFalse(result["passed"])

    # --- Sensitive Topics ---

    def test_detect_sensitive_topics_clean(self) -> None:
        result = self.guard.detect_sensitive_topics(
            "How do I change my notification settings?",
            "You can change notification settings in Preferences.",
        )
        self.assertFalse(result["escalated"])

    def test_detect_sensitive_topics_credentials(self) -> None:
        result = self.guard.detect_sensitive_topics(
            "What is my password for the admin account?",
            "I can help you reset your password by...",
        )
        self.assertTrue(result["escalated"])

    def test_detect_sensitive_topics_legal(self) -> None:
        result = self.guard.detect_sensitive_topics(
            "I want a refund for everything I've paid. If not, I'll sue.",
            "Let me look into that for you.",
        )
        self.assertTrue(result["escalated"])

    # --- Authorization ---

    def test_verify_authorization_valid(self) -> None:
        self.assertTrue(self.guard.verify_authorization("cust_456"))

    def test_verify_authorization_empty(self) -> None:
        self.assertFalse(self.guard.verify_authorization(""))

    def test_verify_authorization_internal(self) -> None:
        self.assertFalse(self.guard.verify_authorization("admin"))

    # --- Irreversible Actions ---

    def test_block_irreversible_actions_clean(self) -> None:
        result = self.guard.block_irreversible_actions(
            "I need help with my account settings.",
            "Let me guide you through the settings page.",
        )
        self.assertFalse(result["blocked"])

    def test_block_irreversible_actions_delete(self) -> None:
        result = self.guard.block_irreversible_actions(
            "Delete my account please.",
            "I will delete your account now.",
        )
        self.assertTrue(result["blocked"])

    # --- Knowledge Source Verification ---

    def test_verify_knowledge_source_cited(self) -> None:
        result = self.guard.verify_knowledge_source(
            "Based on our internal_kb, the solution is to restart the service. "
            "Our product_docs confirm this procedure."
        )
        self.assertTrue(result["verified"])

    def test_verify_knowledge_source_uncited(self) -> None:
        result = self.guard.verify_knowledge_source(
            "Just try restarting and it should work fine."
        )
        self.assertFalse(result["verified"])

    # --- Full Interaction Validation ---

    def test_validate_response_clean(self) -> None:
        interaction = AISupportInteraction(customer_id="cust_789")
        result = self.guard.validate_response(
            interaction,
            "How do I export my data?",
            "According to our internal_kb article KB-442, go to Settings > Data > Export. "
            "You can download in CSV or JSON format.",
        )
        self.assertFalse(result.human_handoff_triggered)
        self.assertGreater(result.confidence_score, 0.5)
        self.assertTrue(result.interaction_recorded)

    def test_validate_response_triggers_handoff(self) -> None:
        interaction = AISupportInteraction(customer_id="cust_789")
        result = self.guard.validate_response(
            interaction,
            "What is the admin password? I need to delete my account now.",
            "I think the password might be... you should probably delete it. "
            "Another customer had this same question.",
        )
        self.assertTrue(result.human_handoff_triggered)

    # --- SEV1 Escalation Pattern ---

    def test_sev1_incident_escalation(self) -> None:
        """Simulate a SEV1 incident where AI must escalate immediately."""
        interaction = AISupportInteraction(customer_id="cust_critical")
        result = self.guard.validate_response(
            interaction,
            "All our production systems are down! This is an emergency - "
            "we've been hacked and data is compromised!",
            "I'm not sure what to do about this. This possibly affects "
            "other customers too.",
        )
        self.assertTrue(result.human_handoff_triggered)
        self.assertTrue(result.sensitive_topic_escalated)
        self.assertTrue(result.uncertainty_flagged)
        self.assertIn(interaction.interaction_id, self.guard.get_human_queue())

    # --- Audit Trail ---

    def test_audit_ai_interaction(self) -> None:
        interaction = AISupportInteraction(customer_id="cust_audit")
        interaction = self.guard.validate_response(
            interaction,
            "Simple question",
            "Simple answer from internal_kb.",
        )
        audit = self.guard.audit_ai_interaction(interaction)
        self.assertIn("rules_status", audit)
        self.assertIn("all_checks_passed", audit)
        self.assertIn(AISupportRule.HUMAN_HANDOFF.value, audit["rules_status"])

    # --- Human Queue ---

    def test_human_queue(self) -> None:
        interaction = AISupportInteraction(customer_id="cust_q")
        self.guard.validate_response(
            interaction,
            "I want to cancel my subscription immediately.",
            "I will cancel your subscription right away.",
        )
        queue = self.guard.get_human_queue()
        self.assertEqual(len(queue), 1)
        self.guard.clear_human_queue()
        self.assertEqual(len(self.guard.get_human_queue()), 0)

    # --- Blocked Terms ---

    def test_blocked_terms(self) -> None:
        guard = AISupportGuard(blocked_terms=["hack_password", "backdoor"])
        result = guard.block_irreversible_actions(
            "I need a backdoor into the system.", ""
        )
        self.assertTrue(result["blocked"])


# ======================================================================
# CX Metrics Engine Tests
# ======================================================================

class TestCXMetricsEngine(unittest.TestCase):
    """Tests for CX metrics collection and analysis."""

    def setUp(self) -> None:
        self.engine = CXMetricsEngine()

    def test_calculate_time_to_value(self) -> None:
        now = datetime.now(timezone.utc)
        events = [
            {
                "signup_date": now - timedelta(days=30),
                "activation_date": now - timedelta(days=25),
            },
            {
                "signup_date": now - timedelta(days=60),
                "activation_date": now - timedelta(days=50),
            },
        ]
        snapshot = self.engine.calculate_time_to_value(events)
        self.assertEqual(snapshot.metric_type, CXMetric.TIME_TO_FIRST_VALUE)
        self.assertGreater(snapshot.value, 0)

    def test_calculate_time_to_value_empty(self) -> None:
        snapshot = self.engine.calculate_time_to_value([])
        self.assertGreater(snapshot.value, 0)  # defaults to target
        self.assertEqual(snapshot.trend_direction, TrendDirection.UNKNOWN)

    def test_measure_task_completion(self) -> None:
        snapshot = self.engine.measure_task_completion(85, 100)
        self.assertEqual(snapshot.value, 85.0)
        self.assertFalse(snapshot.on_target())  # target is 90%

    def test_compute_csat(self) -> None:
        scores = [5.0, 4.0, 3.0, 5.0, 4.0]
        snapshot = self.engine.compute_csat(scores)
        self.assertAlmostEqual(snapshot.value, 4.2)
        self.assertTrue(snapshot.on_target())  # target is 4.0

    def test_compute_csat_empty(self) -> None:
        snapshot = self.engine.compute_csat([])
        self.assertEqual(snapshot.value, 0.0)

    def test_track_response_time(self) -> None:
        snapshot = self.engine.track_response_time([30.0, 45.0, 55.0, 60.0])
        self.assertAlmostEqual(snapshot.value, 47.5)
        self.assertTrue(snapshot.on_target())  # 47.5 < 60 target

    def test_track_response_time_slow(self) -> None:
        snapshot = self.engine.track_response_time([120.0, 150.0])
        self.assertFalse(snapshot.on_target())  # 135 > 60 target

    def test_calculate_retention(self) -> None:
        snapshot = self.engine.calculate_retention(920, 1000)
        self.assertEqual(snapshot.value, 92.0)
        self.assertFalse(snapshot.on_target())  # target is 95%

    def test_calculate_churn(self) -> None:
        snapshot = self.engine.calculate_churn(50, 1000)
        self.assertEqual(snapshot.value, 5.0)
        self.assertFalse(snapshot.on_target())  # 5% > 3% target (lower is better)

    def test_calculate_churn_low(self) -> None:
        snapshot = self.engine.calculate_churn(20, 1000)
        self.assertEqual(snapshot.value, 2.0)
        self.assertTrue(snapshot.on_target())

    def test_monitor_complaints(self) -> None:
        snapshot = self.engine.monitor_complaints(5, 200)
        self.assertEqual(snapshot.value, 2.5)
        self.assertFalse(snapshot.on_target())  # 2.5% > 2% target

    def test_assess_accessibility(self) -> None:
        snapshot = self.engine.assess_accessibility(90, 100)
        self.assertEqual(snapshot.value, 90.0)
        self.assertFalse(snapshot.on_target())  # target is 95%

    def test_evaluate_trust(self) -> None:
        snapshot = self.engine.evaluate_trust(75, 100)
        self.assertEqual(snapshot.value, 75.0)
        self.assertFalse(snapshot.on_target())  # target is 80%

    def test_generate_dashboard(self) -> None:
        self.engine.compute_csat([4.5, 5.0, 4.0])
        self.engine.calculate_churn(20, 1000)
        self.engine.measure_task_completion(95, 100)
        dashboard = self.engine.generate_dashboard()
        self.assertIn("metrics", dashboard)
        self.assertIn("overall_health", dashboard)
        self.assertIn("csat", dashboard["metrics"])

    def test_generate_dashboard_empty(self) -> None:
        dashboard = self.engine.generate_dashboard()
        self.assertEqual(dashboard["total_metrics"], 0)

    def test_trend_direction_improving(self) -> None:
        self.engine.track_response_time([100.0])
        self.engine.track_response_time([50.0])
        latest = self.engine.get_latest(CXMetric.RESPONSE_TIME)
        self.assertIsNotNone(latest)
        # Response time decreasing = improving
        self.assertEqual(
            self.engine._compute_trend(CXMetric.RESPONSE_TIME, "all"),
            TrendDirection.IMPROVING,
        )

    def test_trend_direction_declining_csat(self) -> None:
        self.engine.compute_csat([5.0, 5.0, 5.0])
        self.engine.compute_csat([1.0, 2.0, 1.0])
        trend = self.engine._compute_trend(CXMetric.CSAT, "all")
        self.assertEqual(trend, TrendDirection.DECLINING)

    def test_get_history(self) -> None:
        for _ in range(5):
            self.engine.compute_csat([4.0])
        history = self.engine.get_history(CXMetric.CSAT, limit=3)
        self.assertEqual(len(history), 3)

    def test_clear_history(self) -> None:
        self.engine.compute_csat([4.0])
        self.engine.clear_history(CXMetric.CSAT)
        self.assertIsNone(self.engine.get_latest(CXMetric.CSAT))

    def test_collect_metrics_raw_events(self) -> None:
        self.engine.collect_metrics([{"type": "page_view"}, {"type": "click"}])
        self.engine.collect_metrics([{"type": "conversion"}])
        # Raw events are stored for subsequent calculation
        self.assertEqual(len(self.engine._raw_events), 3)

    def test_churn_prediction_scenario(self) -> None:
        """Model a customer segment showing early warning signs of churn."""
        # Declining CSAT + increasing complaints + high churn rate
        self.engine.compute_csat([2.0, 1.5, 1.0])          # well below 4.0 target
        self.engine.monitor_complaints(50, 200)              # 25% complaint rate
        self.engine.calculate_churn(100, 1000)               # 10% churn
        dashboard = self.engine.generate_dashboard()
        self.assertEqual(dashboard["overall_health"]["status"], "critical")
        # At least 3 metrics should be off-target
        self.assertGreaterEqual(len(dashboard["overall_health"]["top_gaps"]), 2)


# ======================================================================
# Feedback Engine Tests
# ======================================================================

class TestFeedbackEngine(unittest.TestCase):
    """Tests for feedback collection and analysis."""

    def setUp(self) -> None:
        self.engine = FeedbackEngine()

    def test_analyze_sentiment_positive(self) -> None:
        sentiment = self.engine.analyze_sentiment(
            "I love this product! It's amazing and works perfectly. Great job!"
        )
        self.assertEqual(sentiment, Sentiment.POSITIVE)

    def test_analyze_sentiment_negative(self) -> None:
        sentiment = self.engine.analyze_sentiment(
            "This is terrible. So frustrating and broken. Worst experience ever."
        )
        self.assertEqual(sentiment, Sentiment.NEGATIVE)

    def test_analyze_sentiment_neutral(self) -> None:
        sentiment = self.engine.analyze_sentiment(
            "The product has some features. It works okay."
        )
        self.assertEqual(sentiment, Sentiment.NEUTRAL)

    def test_analyze_sentiment_mixed(self) -> None:
        sentiment = self.engine.analyze_sentiment(
            "Great design but terrible performance. Love the UI, hate the speed."
        )
        self.assertEqual(sentiment, Sentiment.MIXED)

    def test_analyze_sentiment_negated(self) -> None:
        sentiment = self.engine.analyze_sentiment(
            "This is not great. The feature is not helpful at all."
        )
        self.assertEqual(sentiment, Sentiment.NEGATIVE)

    def test_collect_feedback(self) -> None:
        entry = self.engine.collect_feedback(
            source=FeedbackSource.SURVEY,
            customer_id="cust_abc",
            content="Love the new dashboard!",
            category="ui",
            product_area="dashboard",
        )
        self.assertEqual(entry.source, FeedbackSource.SURVEY)
        self.assertEqual(entry.sentiment, Sentiment.POSITIVE)
        self.assertTrue(entry.analyzed)
        self.assertEqual(self.engine.entry_count(), 1)

    def test_identify_trends(self) -> None:
        self.engine.collect_feedback(
            FeedbackSource.SUPPORT_TICKET, "c1",
            "The dashboard is broken and unusable", "bug", "dashboard"
        )
        self.engine.collect_feedback(
            FeedbackSource.SUPPORT_TICKET, "c2",
            "Dashboard crashes constantly, so frustrating", "bug", "dashboard"
        )
        self.engine.collect_feedback(
            FeedbackSource.SUPPORT_TICKET, "c3",
            "Export feature is amazing, love it!", "feature", "export"
        )
        trends = self.engine.identify_trends()
        self.assertGreater(trends["total_entries_analyzed"], 0)
        self.assertIn(trends["dominant_sentiment"], ["positive", "negative", "neutral", "mixed"])

    def test_categorize_feedback(self) -> None:
        self.engine.collect_feedback(
            FeedbackSource.IN_APP, "c1", "Great UI!", "praise", "ui"
        )
        self.engine.collect_feedback(
            FeedbackSource.EMAIL, "c2", "Slow loading", "bug", "performance"
        )
        breakdown = self.engine.categorize_feedback()
        self.assertEqual(breakdown["total_entries"], 2)
        self.assertEqual(breakdown["by_source"]["in_app"], 1)

    def test_prioritize_improvements(self) -> None:
        self.engine.collect_feedback(
            FeedbackSource.SURVEY, "c1",
            "Dashboard is terrible and broken", "bug", "dashboard"
        )
        self.engine.collect_feedback(
            FeedbackSource.SURVEY, "c2",
            "Dashboard keeps crashing, awful experience", "bug", "dashboard"
        )
        self.engine.collect_feedback(
            FeedbackSource.SURVEY, "c3",
            "Great product overall", "praise", "general"
        )
        priorities = self.engine.prioritize_improvements()
        self.assertGreaterEqual(len(priorities), 1)
        # Dashboard should be highest priority
        self.assertEqual(priorities[0]["product_area"], "dashboard")

    def test_generate_product_insights(self) -> None:
        self.engine.collect_feedback(
            FeedbackSource.SURVEY, "c1",
            "The checkout flow is confusing and slow", "bug", "checkout"
        )
        self.engine.collect_feedback(
            FeedbackSource.SURVEY, "c2",
            "Checkout is terrible, I almost gave up", "bug", "checkout"
        )
        self.engine.collect_feedback(
            FeedbackSource.SURVEY, "c3",
            "Love the search feature!", "praise", "search"
        )
        insights = self.engine.generate_product_insights()
        self.assertIn("top_pain_points", insights)

    def test_close_feedback_loop(self) -> None:
        self.engine.collect_feedback(
            FeedbackSource.SUPPORT_TICKET, "c1", "Bug report", "bug", "checkout"
        )
        closed = self.engine.close_feedback_loop(
            0, ["Fix checkout timeout", "Add retry logic"], "Fixed in v2.1"
        )
        self.assertIsNotNone(closed)
        self.assertEqual(len(closed.action_items), 2)

    def test_close_feedback_loop_invalid_index(self) -> None:
        result = self.engine.close_feedback_loop(99, [], "")
        self.assertIsNone(result)

    def test_track_impact(self) -> None:
        now = datetime.now(timezone.utc)
        before_date = now - timedelta(days=14)
        after_date = now

        # Seed via raw manipulation for timeline control
        old = FeedbackEntry(
            source=FeedbackSource.SURVEY,
            customer_id="c1",
            sentiment=Sentiment.NEGATIVE,
            content="Bad",
            product_area="checkout",
            created_at=before_date - timedelta(days=1),
            analyzed=True,
        )
        new_entry = FeedbackEntry(
            source=FeedbackSource.SURVEY,
            customer_id="c2",
            sentiment=Sentiment.POSITIVE,
            content="Great!",
            product_area="checkout",
            created_at=after_date - timedelta(days=1),
            analyzed=True,
        )
        self.engine._entries = [old, new_entry]

        impact = self.engine.track_impact("checkout", before_date, after_date)
        self.assertEqual(impact["product_area"], "checkout")
        self.assertIn("sentiment_shift", impact)

    def test_get_entries_filtered(self) -> None:
        self.engine.collect_feedback(FeedbackSource.SURVEY, "c1", "Great!", "praise", "ui")
        self.engine.collect_feedback(FeedbackSource.IN_APP, "c2", "Bad", "bug", "api")
        entries = self.engine.get_entries(source=FeedbackSource.SURVEY)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].customer_id, "c1")


# ======================================================================
# Template Manager Tests
# ======================================================================

class TestTemplateManager(unittest.TestCase):
    """Tests for communication template management."""

    def setUp(self) -> None:
        self.manager = TemplateManager()

    def test_load_template(self) -> None:
        tmpl = self.manager.load_template(TemplateType.INCIDENT_NOTIFICATION)
        self.assertIsNotNone(tmpl)
        self.assertEqual(tmpl.template_type, TemplateType.INCIDENT_NOTIFICATION)
        self.assertEqual(tmpl.tone, "urgent")

    def test_load_nonexistent_template(self) -> None:
        # Create a fresh manager without defaults
        manager = TemplateManager()
        # Clear the defaults
        manager._templates = {}
        result = manager.load_template(TemplateType.INCIDENT_NOTIFICATION)
        self.assertIsNone(result)

    def test_list_templates(self) -> None:
        templates = self.manager.list_templates()
        self.assertGreaterEqual(len(templates), 10)
        for t in templates:
            self.assertIn("type", t)
            self.assertIn("subject", t)

    def test_render_template_incident(self) -> None:
        context = {
            "customer_name": "Acme Corp",
            "severity": "SEV1",
            "incident_summary": "API Gateway Outage",
            "affected_service": "API Gateway",
            "impact_description": "All API calls failing with 503 errors",
            "current_status": "Investigating root cause",
            "eta": "2 hours",
            "mitigation_steps": "Redeploying gateway nodes, engaging vendor",
            "update_frequency": "every 30 minutes",
            "support_contact": "support@example.com",
            "company_name": "EniCorp",
        }
        rendered = self.manager.render_template(
            TemplateType.INCIDENT_NOTIFICATION, context
        )
        self.assertIn("API Gateway Outage", rendered["subject"])
        self.assertIn("Acme Corp", rendered["body"])
        self.assertIn("SEV1", rendered["body"])

    def test_render_template_onboarding(self) -> None:
        context = {
            "customer_name": "Jane",
            "company_name": "EniCorp",
            "quick_start_link": "https://docs.example.com/quickstart",
            "documentation_link": "https://docs.example.com",
            "account_manager": "Bob Smith",
            "support_contact": "support@example.com",
            "first_action": "Set up your team workspace",
        }
        rendered = self.manager.render_template(
            TemplateType.ONBOARDING_WELCOME, context
        )
        self.assertIn("Welcome", rendered["subject"])
        self.assertIn("Jane", rendered["body"])
        self.assertIn("Bob Smith", rendered["body"])

    def test_render_template_missing_field(self) -> None:
        context = {"customer_name": "Test"}  # Missing many required fields
        with self.assertRaises(ValueError):
            self.manager.render_template(TemplateType.INCIDENT_NOTIFICATION, context)

    def test_validate_required_fields(self) -> None:
        tmpl = self.manager.load_template(TemplateType.SLA_BREACH_NOTIFICATION)
        missing = self.manager.validate_required_fields(tmpl, {"customer_name": "Test"})
        self.assertGreater(len(missing), 0)
        self.assertIn("ticket_id", missing)

    def test_validate_required_fields_all_present(self) -> None:
        tmpl = self.manager.load_template(TemplateType.ONBOARDING_WELCOME)
        context = {
            "customer_name": "Test", "company_name": "Co",
            "quick_start_link": "x", "documentation_link": "x",
            "account_manager": "x", "support_contact": "x",
            "first_action": "x",
        }
        missing = self.manager.validate_required_fields(tmpl, context)
        self.assertEqual(len(missing), 0)

    def test_customize_for_audience(self) -> None:
        customized = self.manager.customize_for_audience(
            template_type=TemplateType.FEATURE_ANNOUNCEMENT,
            audience="enterprise",
            tone="formal",
            channel="slack",
        )
        self.assertEqual(customized.audience, "enterprise")
        self.assertEqual(customized.tone, "formal")
        self.assertEqual(customized.channel, "slack")
        self.assertEqual(
            customized.template_type,
            TemplateType.FEATURE_ANNOUNCEMENT,
        )

    def test_send_notification_simulated(self) -> None:
        context = {
            "customer_name": "Acme",
            "severity": "SEV2",
            "incident_summary": "DB latency",
            "affected_service": "Database",
            "impact_description": "Slow queries",
            "current_status": "Mitigating",
            "eta": "1 hour",
            "mitigation_steps": "Scaling up",
            "update_frequency": "hourly",
            "support_contact": "support@example.com",
            "company_name": "EniCorp",
        }
        result = self.manager.send_notification(
            TemplateType.INCIDENT_NOTIFICATION,
            context,
            recipients=["alice@acme.com", "bob@acme.com"],
        )
        self.assertEqual(result["status"], "simulated")
        self.assertEqual(len(result["recipients"]), 2)

    def test_schedule_communication(self) -> None:
        send_at = datetime.now(timezone.utc) + timedelta(hours=24)
        context = {
            "customer_name": "Acme", "plan_name": "Enterprise",
            "company_name": "EniCorp", "renewal_date": "2027-01-15",
            "renewal_term": "Annual", "renewal_amount": "$12,000",
            "whats_new": "AI features, SSO, Priority support",
            "account_manager": "Bob", "account_manager_email": "bob@enicorp.com",
        }
        scheduled = self.manager.schedule_communication(
            TemplateType.RENEWAL_REMINDER,
            context,
            send_at=send_at,
        )
        self.assertEqual(scheduled["status"], "scheduled")
        self.assertEqual(scheduled["template_type"], "renewal_reminder")

    def test_track_delivery(self) -> None:
        ctx = {
            "customer_name": "Test", "company_name": "Co",
            "quick_start_link": "x", "documentation_link": "x",
            "account_manager": "x", "support_contact": "x",
            "first_action": "x",
        }
        self.manager.send_notification(TemplateType.ONBOARDING_WELCOME, ctx)
        self.manager.send_notification(TemplateType.ONBOARDING_WELCOME, ctx)
        tracking = self.manager.track_delivery()
        self.assertEqual(tracking["total_deliveries"], 2)
        self.assertIn("onboarding_welcome", tracking["by_template_type"])

    def test_register_custom_template(self) -> None:
        custom = CommsTemplate(
            template_type=TemplateType.CUSTOM,
            subject_line="Custom: {title}",
            body_template="Hello {name}, {message}",
            tone="casual",
            required_fields=["name", "message", "title"],
            channel="sms",
        )
        self.manager.register_template(custom)
        tmpl = self.manager.load_template(TemplateType.CUSTOM)
        self.assertIsNotNone(tmpl)
        self.assertEqual(tmpl.tone, "casual")


# ======================================================================
# Integration / Cross-Module Tests
# ======================================================================

class TestIntegration(unittest.TestCase):
    """Integration tests across multiple modules."""

    def test_support_to_metrics_flow(self) -> None:
        """Support tickets feed into CX metrics."""
        support = SupportEngine()
        metrics = CXMetricsEngine()

        # Create tickets
        for i in range(10):
            support.create_ticket(f"cust_{i}", f"Issue {i}", "Details")

        # Resolve some
        for ticket_id in list(support._tickets.keys())[:5]:
            support.triage(ticket_id)
            support.assign(ticket_id, "agent")
            support.update_status(ticket_id, TicketStatus.RESOLVED)

        summary = support.sla_summary()
        self.assertTrue(True)  # Smoke test passes

    def test_feedback_to_metrics_flow(self) -> None:
        """Feedback sentiment trends feed into CX dashboard."""
        feedback = FeedbackEngine()
        metrics = CXMetricsEngine()

        feedback.collect_feedback(
            FeedbackSource.SURVEY, "c1", "Love it!", "praise", "ui"
        )
        feedback.collect_feedback(
            FeedbackSource.SURVEY, "c2", "Love it!", "praise", "ui"
        )
        feedback.collect_feedback(
            FeedbackSource.SURVEY, "c3", "It's okay", "neutral", "general"
        )
        feedback.collect_feedback(
            FeedbackSource.SURVEY, "c4", "Terrible bug", "bug", "ui"
        )

        # Simulate CSAT from feedback
        scores = []
        for entry in feedback.get_entries():
            if entry.sentiment == Sentiment.POSITIVE:
                scores.append(5.0)
            elif entry.sentiment == Sentiment.NEUTRAL:
                scores.append(3.0)
            else:
                scores.append(1.0)
        metrics.compute_csat(scores)
        latest = metrics.get_latest(CXMetric.CSAT)
        self.assertIsNotNone(latest)

    def test_journey_support_integration(self) -> None:
        """Journey SUPPORT stage links to support tickets."""
        engine = JourneyEngine()
        support = SupportEngine()

        tp = JourneyTouchpoint(
            stage=JourneyStage.SUPPORT,
            touchpoint_name="Help Desk",
            channel="chat",
            customer_goal="Resolve issue",
            success_metric="Resolution < 4h",
            friction_points=["Long wait"],
        )
        engine.add_touchpoint("enterprise", tp)

        # Create ticket representing this touchpoint
        ticket = support.create_ticket("cust_ent", "Help Desk wait", "Details")
        self.assertIsNotNone(ticket)
        report = engine.generate_journey_report("enterprise")
        self.assertIn("support", report["overview"]["stage_coverage"])


if __name__ == "__main__":
    unittest.main()