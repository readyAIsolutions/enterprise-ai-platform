"""
Comprehensive tests for the Release & Change Management OS module.

Covers: workflow, changes, strategies, quality gates, and deliverables.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from enterprise.modules.release_change import (
    # Workflow
    ChangeStage,
    ChangeRecord,
    ChangeWorkflow,
    # Changes
    ChangeType,
    RiskLevel,
    ChangeTemplate,
    ChangeClassifier,
    # Strategies
    StrategyType,
    DeploymentStrategy,
    StrategyEngine,
    # Quality Gates
    GateType,
    GateStatus,
    QualityGate,
    QualityGateEngine,
    # Deliverables
    DeliverableType,
    Deliverable,
    DeliverableManager,
)


# ═══════════════════════════════════════════════════════════════════════════════
# ChangeWorkflow Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestChangeWorkflow(unittest.TestCase):
    """Tests for the ChangeWorkflow class."""

    def setUp(self):
        self.wf = ChangeWorkflow()
        self.change = self.wf.register_change(
            title="Deploy auth v2.3",
            description="Upgrade auth service to v2.3 with OAuth2 support",
            requester="platform-team",
        )

    def test_register_change(self):
        """Test change registration creates a valid record."""
        self.assertIsNotNone(self.change.change_id)
        self.assertEqual(self.change.title, "Deploy auth v2.3")
        self.assertEqual(self.change.stage, ChangeStage.REGISTER)
        self.assertEqual(self.change.status, "open")

    def test_classify_risk(self):
        """Test risk classification stage."""
        self.wf.classify_risk(self.change, risk_level="HIGH", reason="DB changes")
        self.assertEqual(self.change.risk_level, "HIGH")
        self.assertEqual(self.change.stage, ChangeStage.CLASSIFY_RISK)

    def test_identify_affected_systems(self):
        """Test identifying affected systems."""
        self.wf.identify_affected_systems(self.change, ["auth-svc", "api-gateway", "db"])
        self.assertEqual(self.change.affected_systems, ["auth-svc", "api-gateway", "db"])
        self.assertEqual(self.change.stage, ChangeStage.IDENTIFY_AFFECTED)

    def test_define_acceptance_criteria(self):
        """Test defining acceptance criteria."""
        criteria = ["Login works", "Token refresh works", "Latency < 200ms"]
        self.wf.define_acceptance_criteria(self.change, criteria)
        self.assertEqual(self.change.acceptance_criteria, criteria)
        self.assertEqual(self.change.stage, ChangeStage.DEFINE_ACCEPTANCE)

    def test_run_tests_passing(self):
        """Test running tests that all pass."""
        results = {"unit": "pass", "integration": "pass", "e2e": "pass"}
        self.wf.run_tests(self.change, results)
        self.assertEqual(self.change.test_results, results)
        self.assertEqual(self.change.stage, ChangeStage.TEST)

    def test_run_tests_failing(self):
        """Test running tests with failures raises ValueError."""
        results = {"unit": "pass", "integration": "fail", "e2e": "pass"}
        with self.assertRaises(ValueError) as ctx:
            self.wf.run_tests(self.change, results)
        self.assertIn("Tests failed", str(ctx.exception))
        self.assertEqual(self.change.stage, ChangeStage.TEST)

    def test_security_review_passed(self):
        """Test security review passing."""
        self.wf.security_review(self.change, True, reviewer="alice")
        self.assertTrue(self.change.security_review_passed)
        self.assertEqual(self.change.stage, ChangeStage.SECURITY_REVIEW)

    def test_security_review_failed(self):
        """Test security review failing raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            self.wf.security_review(self.change, False, reviewer="alice")
        self.assertIn("Security review failed", str(ctx.exception))

    def test_request_approvals_sufficient(self):
        """Test approvals with sufficient count."""
        approvers = [
            {"name": "alice", "role": "lead", "status": "approved"},
            {"name": "bob", "role": "manager", "status": "approved"},
        ]
        self.wf.request_approvals(self.change, approvers, required_count=2)
        self.assertEqual(len(self.change.approvals), 2)
        self.assertEqual(self.change.stage, ChangeStage.APPROVALS)

    def test_request_approvals_insufficient(self):
        """Test insufficient approvals raises ValueError."""
        approvers = [
            {"name": "alice", "role": "lead", "status": "approved"},
            {"name": "bob", "role": "manager", "status": "pending"},
        ]
        with self.assertRaises(ValueError) as ctx:
            self.wf.request_approvals(self.change, approvers, required_count=2)
        self.assertIn("Insufficient approvals", str(ctx.exception))

    def test_create_rollback_plan(self):
        """Test rollback plan creation."""
        plan = {
            "steps": ["Stop new pods", "Restart old pods", "Restore DB snapshot"],
            "trigger_conditions": ["Error rate > 5%", "Latency > 1s"],
            "estimated_time_minutes": 15,
            "responsible_team": "sre",
        }
        self.wf.create_rollback_plan(self.change, plan)
        self.assertEqual(self.change.rollback_plan, plan)
        self.assertEqual(self.change.stage, ChangeStage.ROLLBACK_PLAN)

    def test_deploy_progressively(self):
        """Test progressive deployment."""
        self.wf.deploy_progressively(
            self.change,
            strategy="canary",
            target="k8s-prod",
            config={"initial_percent": 5},
        )
        self.assertEqual(self.change.deployment_strategy, "canary")
        self.assertEqual(self.change.stage, ChangeStage.DEPLOY_PROGRESSIVELY)

    def test_monitor_deployment(self):
        """Test deployment monitoring."""
        metrics = {"error_rate": 0.1, "latency_p99": 180, "throughput": 5000}
        alerts = [{"severity": "info", "message": "Deployment observed"}]
        self.wf.monitor_deployment(self.change, metrics, alerts)
        self.assertEqual(self.change.monitoring_plan["metrics"], metrics)
        self.assertEqual(self.change.monitoring_plan["alerts"], alerts)
        self.assertEqual(self.change.stage, ChangeStage.MONITOR)

    def test_validate_deployment_passing(self):
        """Test validation passing."""
        results = {"login_works": True, "latency_ok": True, "tokens_ok": True}
        self.wf.validate_deployment(self.change, results)
        self.assertEqual(self.change.validation_results, results)
        self.assertEqual(self.change.stage, ChangeStage.VALIDATE)

    def test_validate_deployment_failing(self):
        """Test validation failing raises ValueError."""
        results = {"login_works": True, "latency_ok": False}
        with self.assertRaises(ValueError) as ctx:
            self.wf.validate_deployment(self.change, results)
        self.assertIn("Validation failed", str(ctx.exception))

    def test_close_change(self):
        """Test closing a change."""
        self.wf.close_change(self.change)
        self.assertEqual(self.change.status, "completed")
        self.assertEqual(self.change.stage, ChangeStage.CLOSE)

    def test_execute_rollback(self):
        """Test executing a rollback."""
        self.change.rollback_plan = {"steps": ["Revert"]}
        self.wf.execute_rollback(self.change, reason="Error rate spike", executed_by="oncall")
        self.assertEqual(self.change.status, "rolled_back")
        self.assertEqual(self.change.stage, ChangeStage.ROLLBACK)

    def test_document_lessons(self):
        """Test documenting lessons learned."""
        lessons = ["Test more thoroughly", "Add more monitoring", "Staged rollout helped"]
        self.wf.document_lessons(self.change, lessons)
        self.assertEqual(self.change.lessons_learned, lessons)
        self.assertEqual(self.change.stage, ChangeStage.DOCUMENT_LESSONS)

    def test_full_workflow_success(self):
        """Test the complete happy-path workflow."""
        result = self.wf.run_full_workflow(
            title="Deploy auth v2.4",
            description="OAuth2.1 upgrade",
            requester="platform-team",
            risk_level="MEDIUM",
            affected_systems=["auth-svc", "api-gw"],
            acceptance_criteria=["Login works", "Latency < 200ms"],
            test_results={"unit": "pass", "integration": "pass", "e2e": "pass"},
            security_passed=True,
            approvers=[
                {"name": "alice", "role": "lead", "status": "approved"},
                {"name": "bob", "role": "manager", "status": "approved"},
            ],
            rollback_plan={"steps": ["Revert"], "trigger_conditions": ["Error > 5%"]},
            deployment_strategy="canary",
            monitor_metrics={"error_rate": 0.1},
            validation_results={"criterion_1": True, "criterion_2": True},
            lessons=["Good deployment"],
        )
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.stage, ChangeStage.CLOSE)
        self.assertEqual(result.lessons_learned, ["Good deployment"])
        self.assertTrue(len(self.wf.get_history()) > 10)

    def test_full_workflow_rollback_path(self):
        """Test workflow that goes to rollback."""
        change = self.wf.register_change("Emergency fix", "Hotfix", "oncall")
        self.wf.classify_risk(change, "CRITICAL")
        self.wf.identify_affected_systems(change, ["payment-svc"])
        self.wf.define_acceptance_criteria(change, ["Payments work"])
        self.wf.run_tests(change, {"smoke": "pass"})
        self.wf.security_review(change, True, "alice")
        self.wf.request_approvals(change, [
            {"name": "alice", "role": "lead", "status": "approved"}
        ])
        self.wf.create_rollback_plan(change, {"steps": ["Revert"]})
        self.wf.deploy_progressively(change, "immediate")
        self.wf.monitor_deployment(change, {"error_rate": 25.0})
        # Simulate rollback trigger — rollback terminates the workflow
        self.wf.execute_rollback(change, "Error rate > threshold")
        self.assertEqual(change.status, "rolled_back")
        self.assertEqual(change.stage, ChangeStage.ROLLBACK)
        # Document lessons after rollback
        self.wf.document_lessons(change, ["Need better testing"])

    def test_list_changes_filtered(self):
        """Test listing changes with filters."""
        c1 = self.change
        c2 = self.wf.register_change("Change 2", "Description 2", "user2")
        self.wf.classify_risk(c2, "LOW")
        self.wf.close_change(c2)

        # Filter by status
        completed = self.wf.list_changes(status="completed")
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0].change_id, c2.change_id)

        # Filter by stage
        registered = self.wf.list_changes(stage=ChangeStage.REGISTER)
        self.assertEqual(len(registered), 1)

    def test_get_change(self):
        """Test retrieving a change by ID."""
        found = self.wf.get_change(self.change.change_id)
        self.assertIsNotNone(found)
        self.assertEqual(found.title, "Deploy auth v2.3")

        not_found = self.wf.get_change("nonexistent")
        self.assertIsNone(not_found)

    def test_change_record_to_dict(self):
        """Test serializing a ChangeRecord to dict."""
        d = self.change.to_dict()
        self.assertEqual(d["change_id"], self.change.change_id)
        self.assertEqual(d["title"], "Deploy auth v2.3")
        self.assertEqual(d["stage"], "register")


# ═══════════════════════════════════════════════════════════════════════════════
# ChangeClassifier Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestChangeClassifier(unittest.TestCase):
    """Tests for the ChangeClassifier class."""

    def setUp(self):
        self.classifier = ChangeClassifier()

    def test_classify_standard(self):
        """Test classifying a standard change."""
        result = self.classifier.classify_change(ChangeType.STANDARD)
        self.assertEqual(result["change_type"], "standard")
        self.assertEqual(result["default_risk"], "low")
        self.assertEqual(result["required_approvals"], 1)
        self.assertFalse(result["cab_approval_required"])

    def test_classify_major(self):
        """Test classifying a major change."""
        result = self.classifier.classify_change(ChangeType.MAJOR)
        self.assertEqual(result["default_risk"], "high")
        self.assertEqual(result["required_approvals"], 2)
        self.assertTrue(result["cab_approval_required"])
        self.assertIn("e2e", result["required_tests"])

    def test_classify_emergency(self):
        """Test classifying an emergency change."""
        result = self.classifier.classify_change(ChangeType.EMERGENCY)
        self.assertEqual(result["default_risk"], "critical")
        self.assertTrue(result["is_high_stakes"])
        self.assertIn("smoke", result["required_tests"])

    def test_classify_security(self):
        """Test classifying a security change."""
        result = self.classifier.classify_change(ChangeType.SECURITY)
        self.assertEqual(result["default_risk"], "critical")
        self.assertIn("security_scan", result["required_tests"])
        self.assertIn("penetration", result["required_tests"])

    def test_classify_ai_model(self):
        """Test classifying an AI model change."""
        result = self.classifier.classify_change(ChangeType.AI_MODEL)
        self.assertEqual(result["default_risk"], "medium")
        self.assertIn("evaluation", result["required_tests"])
        self.assertIn("fairness", result["required_tests"])

    def test_classify_prompt(self):
        """Test classifying a prompt change."""
        result = self.classifier.classify_change(ChangeType.PROMPT)
        self.assertEqual(result["default_risk"], "low")
        self.assertIn("prompt_eval", result["required_tests"])
        self.assertEqual(result["max_downtime_minutes"], 0)

    def test_determine_risk_low(self):
        """Test risk determination for low-risk scenario."""
        risk = self.classifier.determine_risk(
            ChangeType.STANDARD,
            affected_systems=1,
            data_changes=False,
            user_facing=False,
        )
        self.assertEqual(risk, RiskLevel.LOW)

    def test_determine_risk_high(self):
        """Test risk determination for high-risk scenario."""
        risk = self.classifier.determine_risk(
            ChangeType.MAJOR,
            affected_systems=30,
            data_changes=True,
            user_facing=True,
            dependency_count=20,
            past_incidents=4,
        )
        # MAJOR base is HIGH, plus many aggravating factors
        self.assertIn(risk, (RiskLevel.HIGH, RiskLevel.CRITICAL),
                      f"Expected HIGH or CRITICAL, got {risk}")

    def test_determine_risk_critical(self):
        """Test risk determination for critical-risk scenario."""
        # Use extreme/maximum parameters to push score above critical threshold
        from enterprise.modules.release_change.changes import ChangeClassifier as CC
        risk = self.classifier.determine_risk(
            ChangeType.EMERGENCY,
            affected_systems=50,
            data_changes=True,
            user_facing=True,
            dependency_count=30,
            past_incidents=10,
        )
        self.assertEqual(risk, RiskLevel.CRITICAL,
                         f"Expected CRITICAL, got {risk}")

    def test_get_template(self):
        """Test getting a template returns a copy."""
        tmpl = self.classifier.get_template(ChangeType.DATABASE)
        self.assertEqual(tmpl.default_risk, RiskLevel.HIGH)
        self.assertIn("migration", tmpl.required_tests)
        self.assertIn("rollback", tmpl.required_tests)

    def test_register_custom_template(self):
        """Test registering a custom template."""
        custom = ChangeTemplate(
            change_type=ChangeType.CONFIGURATION,
            default_risk=RiskLevel.HIGH,
            required_approvals=3,
            required_tests=["config_validation"],
        )
        self.classifier.register_template(custom)
        tmpl = self.classifier.get_template(ChangeType.CONFIGURATION)
        self.assertEqual(tmpl.default_risk, RiskLevel.HIGH)
        self.assertEqual(tmpl.required_approvals, 3)

    def test_get_required_approvals(self):
        """Test getting required approvals count."""
        self.assertEqual(self.classifier.get_required_approvals(ChangeType.COMPLIANCE), 3)
        self.assertEqual(self.classifier.get_required_approvals(ChangeType.STANDARD), 1)

    def test_assess_urgency_immediate(self):
        """Test urgency assessment for emergency."""
        urgency = self.classifier.assess_urgency(ChangeType.EMERGENCY)
        self.assertEqual(urgency, "immediate")

    def test_assess_urgency_with_incident(self):
        """Test urgency with active incident."""
        urgency = self.classifier.assess_urgency(
            ChangeType.NORMAL, incident_active=True
        )
        self.assertEqual(urgency, "immediate")

    def test_assess_urgency_scheduled(self):
        """Test urgency for standard change."""
        urgency = self.classifier.assess_urgency(
            ChangeType.STANDARD, sla_hours_remaining=100
        )
        self.assertEqual(urgency, "scheduled")

    def test_calculate_impact_radius(self):
        """Test impact radius calculation with dependencies."""
        systems = ["auth-svc", "api-gateway"]
        deps = {
            "auth-svc": ["user-svc", "session-svc"],
            "api-gateway": ["rate-limiter", "cdn"],
            "user-svc": ["notification-svc"],
        }
        result = self.classifier.calculate_impact_radius(systems, deps)
        self.assertEqual(result["direct_count"], 2)
        self.assertGreaterEqual(result["indirect_count"], 3)
        self.assertGreater(result["total_affected"], 2)
        self.assertIn("user-svc", result["indirect_impact"])

    def test_calculate_impact_radius_no_deps(self):
        """Test impact radius with no dependencies."""
        result = self.classifier.calculate_impact_radius(["standalone-svc"])
        self.assertEqual(result["direct_count"], 1)
        self.assertEqual(result["indirect_count"], 0)
        self.assertEqual(result["total_affected"], 1)


# ═══════════════════════════════════════════════════════════════════════════════
# StrategyEngine Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestStrategyEngine(unittest.TestCase):
    """Tests for the StrategyEngine class."""

    def setUp(self):
        self.engine = StrategyEngine()

    def test_select_strategy(self):
        """Test selecting a deployment strategy."""
        strategy = self.engine.select_strategy(
            StrategyType.CANARY,
            traffic_split_percent=10,
            observation_period_minutes=15,
            health_check_endpoint="/healthz",
        )
        self.assertEqual(strategy.strategy_type, StrategyType.CANARY)
        self.assertEqual(strategy.traffic_split_percent, 10)
        self.assertEqual(strategy.observation_period_minutes, 15)

    def test_configure_feature_flags(self):
        """Test configuring feature flags."""
        strategy = self.engine.select_strategy(StrategyType.FEATURE_FLAGS)
        result = self.engine.configure_feature_flags(
            strategy,
            flag_key="new-auth-flow",
            rollout_percent=25,
            target_segments=["internal", "beta"],
            enabled=True,
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["config"]["flag_key"], "new-auth-flow")
        self.assertEqual(strategy.feature_flag_key, "new-auth-flow")

    def test_execute_canary_success(self):
        """Test canary deployment succeeding."""
        strategy = self.engine.select_strategy(StrategyType.CANARY, traffic_split_percent=5)

        def mock_deploy():
            return True

        def mock_health(endpoint):
            return True

        result = self.engine.execute_canary(strategy, deploy_fn=mock_deploy, health_check_fn=mock_health)
        self.assertTrue(result["success"])

    def test_execute_canary_deploy_failure(self):
        """Test canary deployment when deploy function fails."""
        strategy = self.engine.select_strategy(StrategyType.CANARY)

        def mock_deploy():
            return False

        result = self.engine.execute_canary(strategy, deploy_fn=mock_deploy)
        self.assertFalse(result["success"])
        self.assertIn("Canary deploy", result["error"])

    def test_execute_canary_health_failure(self):
        """Test canary deployment when health check fails."""
        strategy = self.engine.select_strategy(StrategyType.CANARY)

        def mock_deploy():
            return True

        def mock_health(endpoint):
            return False

        result = self.engine.execute_canary(strategy, deploy_fn=mock_deploy, health_check_fn=mock_health)
        self.assertFalse(result["success"])
        self.assertIn("Health check failed", result["error"])

    def test_execute_blue_green_success(self):
        """Test blue-green deployment succeeding."""
        strategy = self.engine.select_strategy(StrategyType.BLUE_GREEN)

        def mock_deploy():
            return True

        def mock_health(endpoint):
            return True

        def mock_smoke():
            return True

        result = self.engine.execute_blue_green(
            strategy, deploy_fn=mock_deploy,
            health_check_fn=mock_health, smoke_test_fn=mock_smoke,
        )
        self.assertTrue(result["success"])
        self.assertTrue(result["traffic_switched"])

    def test_execute_blue_green_smoke_failure(self):
        """Test blue-green deployment when smoke tests fail."""
        strategy = self.engine.select_strategy(StrategyType.BLUE_GREEN)

        def mock_deploy():
            return True

        def mock_health(endpoint):
            return True

        def mock_smoke():
            return False

        result = self.engine.execute_blue_green(
            strategy, deploy_fn=mock_deploy,
            health_check_fn=mock_health, smoke_test_fn=mock_smoke,
        )
        self.assertFalse(result["success"])
        self.assertIn("Smoke tests failed", result["error"])

    def test_execute_rolling_success(self):
        """Test rolling deployment succeeding."""
        strategy = self.engine.select_strategy(StrategyType.ROLLING)

        def mock_deploy(batch_num):
            return True

        def mock_health(endpoint):
            return True

        result = self.engine.execute_rolling(
            strategy, instance_count=6, batch_size=2,
            deploy_fn=mock_deploy, health_check_fn=mock_health,
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["batches_completed"], 3)

    def test_execute_rolling_batch_failure(self):
        """Test rolling deployment with batch failure."""
        strategy = self.engine.select_strategy(StrategyType.ROLLING)
        call_count = [0]

        def mock_deploy(batch_num):
            call_count[0] += 1
            return call_count[0] < 3  # fail on batch 3

        def mock_health(endpoint):
            return True

        result = self.engine.execute_rolling(
            strategy, instance_count=6, batch_size=2,
            deploy_fn=mock_deploy, health_check_fn=mock_health,
        )
        self.assertFalse(result["success"])

    def test_execute_shadow(self):
        """Test shadow deployment."""
        strategy = self.engine.select_strategy(StrategyType.SHADOW)

        def mock_compare():
            return {"match_rate": 0.99, "diff_count": 3}

        result = self.engine.execute_shadow(strategy, mirror_traffic_percent=10, compare_fn=mock_compare)
        self.assertTrue(result["success"])
        self.assertEqual(result["mirror_percent"], 10)
        self.assertEqual(result["comparison"]["match_rate"], 0.99)

    def test_execute_staged(self):
        """Test staged rollout."""
        strategy = self.engine.select_strategy(StrategyType.STAGED_ROLLOUT)

        def mock_deploy(stage_cfg):
            return True

        result = self.engine.execute_staged(strategy, deploy_fn=mock_deploy)
        self.assertTrue(result["success"])
        self.assertEqual(len(result["stages"]), 3)

    def test_execute_staged_failure(self):
        """Test staged rollout with a stage failure."""
        strategy = self.engine.select_strategy(StrategyType.STAGED_ROLLOUT)

        call_count = [0]

        def mock_deploy(stage_cfg):
            call_count[0] += 1
            return call_count[0] < 2  # fail after first stage

        result = self.engine.execute_staged(strategy, deploy_fn=mock_deploy)
        self.assertFalse(result["success"])

    def test_execute_tenant_based(self):
        """Test tenant-based deployment."""
        strategy = self.engine.select_strategy(StrategyType.TENANT_BASED)

        def mock_deploy(tenant):
            return tenant != "fail-tenant"

        result = self.engine.execute_tenant_based(
            strategy,
            tenant_ids=["tenant-a", "tenant-b"],
            deploy_fn=mock_deploy,
        )
        self.assertTrue(result["success"])
        self.assertEqual(len(result["tenants"]), 2)

    def test_execute_tenant_based_failure(self):
        """Test tenant-based deployment with failure."""
        strategy = self.engine.select_strategy(StrategyType.TENANT_BASED)

        def mock_deploy(tenant):
            return tenant != "tenant-b"

        result = self.engine.execute_tenant_based(
            strategy,
            tenant_ids=["tenant-a", "tenant-b"],
            deploy_fn=mock_deploy,
        )
        self.assertFalse(result["success"])

    def test_execute_regional(self):
        """Test regional deployment."""
        strategy = self.engine.select_strategy(StrategyType.REGIONAL)

        def mock_deploy(region):
            return True

        result = self.engine.execute_regional(
            strategy,
            regions=["us-east-1", "eu-west-1"],
            deploy_fn=mock_deploy,
        )
        self.assertTrue(result["success"])
        self.assertEqual(len(result["regions"]), 2)

    def test_execute_regional_failure(self):
        """Test regional deployment with failure."""
        strategy = self.engine.select_strategy(StrategyType.REGIONAL)

        def mock_deploy(region):
            return region != "eu-west-1"

        result = self.engine.execute_regional(
            strategy,
            regions=["us-east-1", "eu-west-1"],
            deploy_fn=mock_deploy,
        )
        self.assertFalse(result["success"])

    def test_validate_strategy_applied_success(self):
        """Test validating a successfully applied strategy."""
        strategy = self.engine.select_strategy(StrategyType.ROLLING)
        result = self.engine.validate_strategy_applied(
            strategy,
            error_rate=1.5,
            latency_ms=100,
            health_ok=True,
        )
        self.assertTrue(result["validated"])

    def test_validate_strategy_applied_failure(self):
        """Test validating a strategy that fails checks."""
        strategy = self.engine.select_strategy(StrategyType.ROLLING)
        result = self.engine.validate_strategy_applied(
            strategy,
            error_rate=15.0,
            latency_ms=100,
            health_ok=False,
        )
        self.assertFalse(result["validated"])

    def test_validate_with_latency_threshold(self):
        """Test validation with latency threshold."""
        strategy = self.engine.select_strategy(
            StrategyType.ROLLING,
            latency_threshold_ms=200,
        )
        result = self.engine.validate_strategy_applied(
            strategy,
            error_rate=1.0,
            latency_ms=500,
            health_ok=True,
        )
        self.assertFalse(result["validated"])


# ═══════════════════════════════════════════════════════════════════════════════
# QualityGateEngine Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestQualityGateEngine(unittest.TestCase):
    """Tests for the QualityGateEngine class."""

    def setUp(self):
        self.engine = QualityGateEngine()

    def test_check_tests_passing_success(self):
        """Test tests passing gate with all passing."""
        gate = self.engine.check_tests_passing(
            {"unit": "pass", "integration": "pass", "e2e": "pass"},
            reviewer="qa-team",
        )
        self.assertEqual(gate.status, GateStatus.PASSED)
        self.assertEqual(gate.reviewer, "qa-team")

    def test_check_tests_passing_failure(self):
        """Test tests passing gate with failures."""
        gate = self.engine.check_tests_passing(
            {"unit": "pass", "integration": "fail", "e2e": "error"},
            reviewer="qa-team",
        )
        self.assertEqual(gate.status, GateStatus.FAILED)
        self.assertIn("Failures", gate.evidence["failure_reason"])

    def test_verify_security_approved(self):
        """Test security gate approved."""
        gate = self.engine.verify_security(True, reviewer="sec-team")
        self.assertEqual(gate.status, GateStatus.PASSED)

    def test_verify_security_rejected(self):
        """Test security gate rejected."""
        gate = self.engine.verify_security(False, reviewer="sec-team")
        self.assertEqual(gate.status, GateStatus.FAILED)

    def test_verify_dependencies_compatible(self):
        """Test dependency verification with compatible deps."""
        gate = self.engine.verify_dependencies(
            {"auth-lib": "2.3.0", "db-driver": "1.5.0"},
            reviewer="architect",
        )
        self.assertEqual(gate.status, GateStatus.PASSED)

    def test_verify_dependencies_incompatible(self):
        """Test dependency verification with incompatible deps."""
        gate = self.engine.verify_dependencies(
            {"auth-lib": "2.3.0", "db-driver": "incompatible-version"},
            reviewer="architect",
        )
        self.assertEqual(gate.status, GateStatus.FAILED)

    def test_validate_migration_valid(self):
        """Test migration validation with valid plan."""
        gate = self.engine.validate_migration(
            {"steps": ["Backup", "Migrate"], "rollback": ["Restore"], "tested": True},
            reviewer="dba",
        )
        self.assertEqual(gate.status, GateStatus.PASSED)

    def test_validate_migration_missing_fields(self):
        """Test migration validation with missing fields."""
        gate = self.engine.validate_migration(
            {"steps": ["Backup"]},
            reviewer="dba",
        )
        self.assertEqual(gate.status, GateStatus.FAILED)

    def test_validate_migration_not_tested(self):
        """Test migration validation with untested plan."""
        gate = self.engine.validate_migration(
            {"steps": ["Backup"], "rollback": ["Restore"], "tested": False},
            reviewer="dba",
        )
        self.assertEqual(gate.status, GateStatus.FAILED)

    def test_check_monitoring_configured(self):
        """Test monitoring gate with everything configured."""
        gate = self.engine.check_monitoring(
            dashboards_configured=True,
            alerts_configured=True,
            reviewer="sre",
            alert_rules=["HighErrorRate", "HighLatency"],
        )
        self.assertEqual(gate.status, GateStatus.PASSED)

    def test_check_monitoring_missing(self):
        """Test monitoring gate with missing configuration."""
        gate = self.engine.check_monitoring(
            dashboards_configured=False,
            alerts_configured=True,
            reviewer="sre",
        )
        self.assertEqual(gate.status, GateStatus.FAILED)

    def test_verify_rollback_valid(self):
        """Test rollback gate with valid tested plan."""
        gate = self.engine.verify_rollback(
            {"steps": ["Revert"], "trigger_conditions": ["Error > 5%"]},
            tested=True,
            reviewer="sre",
        )
        self.assertEqual(gate.status, GateStatus.PASSED)

    def test_verify_rollback_not_tested(self):
        """Test rollback gate with untested plan."""
        gate = self.engine.verify_rollback(
            {"steps": ["Revert"], "trigger_conditions": ["Error > 5%"]},
            tested=False,
            reviewer="sre",
        )
        self.assertEqual(gate.status, GateStatus.FAILED)

    def test_verify_rollback_missing(self):
        """Test rollback gate with missing fields."""
        gate = self.engine.verify_rollback(
            {"steps": ["Revert"]},
            tested=True,
            reviewer="sre",
        )
        self.assertEqual(gate.status, GateStatus.FAILED)

    def test_confirm_owner_approved(self):
        """Test owner approval gate approved."""
        gate = self.engine.confirm_owner(True, owner="alice", reviewer="manager")
        self.assertEqual(gate.status, GateStatus.PASSED)

    def test_confirm_owner_rejected(self):
        """Test owner approval gate rejected."""
        gate = self.engine.confirm_owner(False, owner="alice", reviewer="manager")
        self.assertEqual(gate.status, GateStatus.FAILED)

    def test_validate_change_record_valid(self):
        """Test change record validation with complete record."""
        gate = self.engine.validate_change_record(
            {"title": "Fix", "description": "A fix", "requester": "dev", "risk_level": "LOW"},
            reviewer="qa",
        )
        self.assertEqual(gate.status, GateStatus.PASSED)

    def test_validate_change_record_incomplete(self):
        """Test change record validation with incomplete record."""
        gate = self.engine.validate_change_record(
            {"title": "", "description": "A fix", "requester": "", "risk_level": ""},
            reviewer="qa",
        )
        self.assertEqual(gate.status, GateStatus.FAILED)

    def test_assess_user_impact_low(self):
        """Test user impact assessment for low severity."""
        gate = self.engine.assess_user_impact(
            users_affected=10, severity="low", reviewer="pm"
        )
        self.assertEqual(gate.status, GateStatus.PASSED)

    def test_assess_user_impact_critical_no_mitigation(self):
        """Test user impact assessment for critical severity without mitigation."""
        gate = self.engine.assess_user_impact(
            users_affected=100000, severity="critical", reviewer="pm"
        )
        self.assertEqual(gate.status, GateStatus.FAILED)

    def test_assess_user_impact_critical_with_mitigation(self):
        """Test user impact assessment for critical severity with mitigation."""
        gate = self.engine.assess_user_impact(
            users_affected=100000, severity="critical",
            reviewer="pm", mitigation_plan="Gradual rollout with monitoring",
        )
        self.assertEqual(gate.status, GateStatus.PASSED)

    def test_verify_communication_valid(self):
        """Test communication plan verification with valid plan."""
        gate = self.engine.verify_communication(
            {"stakeholders": ["all"], "channels": ["email", "slack"]},
            reviewer="comms",
        )
        self.assertEqual(gate.status, GateStatus.PASSED)

    def test_verify_communication_invalid(self):
        """Test communication plan verification with missing fields."""
        gate = self.engine.verify_communication(
            {"stakeholders": ["all"]},
            reviewer="comms",
        )
        self.assertEqual(gate.status, GateStatus.FAILED)

    def test_run_all_gates_success(self):
        """Test running all gates successfully."""
        gates = self.engine.run_all_gates(
            test_results={"unit": "pass", "integration": "pass"},
            security_approved=True,
            dependencies={"lib": "1.0"},
            migration_plan={"steps": ["Do"], "rollback": ["Undo"], "tested": True},
            dashboards_ok=True,
            alerts_ok=True,
            rollback_plan={"steps": ["Revert"], "trigger_conditions": ["Error"]},
            rollback_tested=True,
            owner_approved=True,
            owner="alice",
            change_data={
                "title": "Fix", "description": "Desc",
                "requester": "dev", "risk_level": "LOW",
            },
            users_affected=10,
            impact_severity="low",
            communication_plan={"stakeholders": ["all"], "channels": ["email"]},
        )
        self.assertEqual(len(gates), 10)
        report = self.engine.generate_gate_report()
        self.assertTrue(report["summary"]["all_passed"])
        self.assertTrue(report["summary"]["ready_to_proceed"])

    def test_run_all_gates_partial_failure(self):
        """Test running all gates with some failures."""
        self.engine.run_all_gates(
            test_results={"unit": "fail"},
            security_approved=False,
            dependencies={"lib": "incompatible"},
            migration_plan={"steps": ["Do"]},
            dashboards_ok=False,
            alerts_ok=False,
            rollback_plan={"steps": []},
            rollback_tested=False,
            owner_approved=False,
            owner="bob",
            change_data={"title": ""},
            users_affected=100000,
            impact_severity="critical",
            communication_plan={},
        )
        report = self.engine.generate_gate_report()
        self.assertFalse(report["summary"]["all_passed"])
        self.assertGreater(report["summary"]["failed"], 0)
        self.assertGreater(report["summary"]["blocking_failed"], 0)

    def test_gate_pass_fail_waive(self):
        """Test pass, fail, and waive operations on QualityGate."""
        gate = QualityGate(gate_type=GateType.MONITORING)
        self.assertEqual(gate.status, GateStatus.PENDING)

        gate.pass_gate("reviewer1", {"evidence": "ok"})
        self.assertEqual(gate.status, GateStatus.PASSED)

        gate.fail_gate("reviewer2", "it broke")
        self.assertEqual(gate.status, GateStatus.FAILED)
        self.assertEqual(gate.evidence["failure_reason"], "it broke")

        gate.waive_gate("reviewer3", "not applicable")
        self.assertEqual(gate.status, GateStatus.WAIVED)
        self.assertEqual(gate.waiver_reason, "not applicable")

    def test_all_gates_satisfied(self):
        """Test all_gates_satisfied check."""
        # Initially all pending
        self.assertFalse(self.engine.all_gates_satisfied())

        # Pass all
        for gate in self.engine.get_all_gates():
            gate.pass_gate("auto")
        self.assertTrue(self.engine.all_gates_satisfied())

    def test_get_blocking_failures(self):
        """Test getting blocking failures."""
        self.engine.check_tests_passing({"unit": "fail"})
        self.engine.verify_security(False)
        self.engine.verify_dependencies({"lib": "1.0"})  # passes

        failures = self.engine.get_blocking_failures()
        self.assertEqual(len(failures), 2)

    def test_waived_gates_satisfied(self):
        """Test that waived gates count as satisfied."""
        self.engine.get_gate(GateType.TESTS_PASSING).waive_gate("reviewer", "N/A")
        self.engine.get_gate(GateType.SECURITY_APPROVAL).pass_gate("auto")
        self.engine.get_gate(GateType.DEPENDENCY_VERIFICATION).pass_gate("auto")
        self.engine.get_gate(GateType.DB_MIGRATION_PLAN).pass_gate("auto")
        self.engine.get_gate(GateType.MONITORING).pass_gate("auto")
        self.engine.get_gate(GateType.ROLLBACK_PLAN).pass_gate("auto")
        self.engine.get_gate(GateType.OWNER_APPROVAL).pass_gate("auto")
        self.engine.get_gate(GateType.CHANGE_RECORD).pass_gate("auto")
        self.engine.get_gate(GateType.USER_IMPACT_ASSESSMENT).pass_gate("auto")
        self.engine.get_gate(GateType.COMMUNICATION_PLAN).pass_gate("auto")
        self.assertTrue(self.engine.all_gates_satisfied())

    def test_generate_gate_report_structure(self):
        """Test gate report has correct structure."""
        self.engine.check_tests_passing({"unit": "pass"})
        report = self.engine.generate_gate_report()
        self.assertIn("summary", report)
        self.assertIn("gates", report)
        self.assertIn("generated_at", report)
        self.assertEqual(report["summary"]["total"], 10)
        self.assertIsInstance(report["gates"], list)
        self.assertEqual(len(report["gates"]), 10)


# ═══════════════════════════════════════════════════════════════════════════════
# DeliverableManager Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeliverableManager(unittest.TestCase):
    """Tests for the DeliverableManager class."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.mgr = DeliverableManager(storage_dir=self.tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_create_release_plan(self):
        """Test creating a release plan."""
        d = self.mgr.create_release_plan(
            release_name="v2.0 Mega Release",
            version="2.0.0",
            author="pm",
            schedule={"start": "2024-03-01", "end": "2024-03-15"},
            scope=["auth", "payment", "ui"],
            stakeholders=["product", "engineering", "sre"],
            risks=["DB migration risk"],
        )
        self.assertEqual(d.deliverable_type, DeliverableType.RELEASE_PLAN)
        self.assertEqual(d.content["release_name"], "v2.0 Mega Release")
        self.assertEqual(d.content["version"], "2.0.0")
        self.assertEqual(len(d.content["scope"]), 3)
        self.assertTrue(os.path.exists(d.storage_path))

    def test_generate_change_record(self):
        """Test generating a change record."""
        d = self.mgr.generate_change_record(
            change_id="CHG-001",
            title="Upgrade DB",
            description="Upgrade to PostgreSQL 16",
            author="dba",
            requester="platform",
            risk_level="HIGH",
            affected_systems=["postgres-primary", "postgres-replica"],
        )
        self.assertEqual(d.deliverable_type, DeliverableType.CHANGE_RECORD)
        self.assertEqual(d.content["change_id"], "CHG-001")
        self.assertEqual(d.content["risk_level"], "HIGH")

    def test_document_risk(self):
        """Test documenting risk classification."""
        d = self.mgr.document_risk(
            change_id="CHG-002",
            risk_level="CRITICAL",
            author="security",
            risk_factors={"data_exposure": True, "user_facing": True},
            mitigation=["Encrypt data", "Gradual rollout"],
        )
        self.assertEqual(d.deliverable_type, DeliverableType.RISK_CLASSIFICATION)
        self.assertEqual(d.content["risk_level"], "CRITICAL")
        self.assertEqual(len(d.content["mitigation"]), 2)

    def test_collect_testing_evidence(self):
        """Test collecting testing evidence."""
        d = self.mgr.collect_testing_evidence(
            change_id="CHG-003",
            test_results={"unit": "pass", "integration": "pass", "e2e": "pass"},
            author="qa",
            test_types=["unit", "integration", "e2e"],
            coverage_percent=87.5,
        )
        self.assertTrue(d.content["all_passed"])
        self.assertEqual(d.content["coverage_percent"], 87.5)

    def test_collect_testing_evidence_with_failures(self):
        """Test testing evidence with failures."""
        d = self.mgr.collect_testing_evidence(
            change_id="CHG-004",
            test_results={"unit": "pass", "integration": "fail"},
            author="qa",
        )
        self.assertFalse(d.content["all_passed"])

    def test_record_approvals_sufficient(self):
        """Test recording approvals with sufficient count."""
        d = self.mgr.record_approvals(
            change_id="CHG-005",
            approvals=[
                {"name": "alice", "role": "lead", "status": "approved"},
                {"name": "bob", "role": "manager", "status": "approved"},
            ],
            author="pm",
            required_count=2,
        )
        self.assertTrue(d.content["sufficient"])
        self.assertEqual(d.content["approved_count"], 2)

    def test_record_approvals_insufficient(self):
        """Test recording approvals with insufficient count."""
        d = self.mgr.record_approvals(
            change_id="CHG-006",
            approvals=[
                {"name": "alice", "role": "lead", "status": "approved"},
                {"name": "bob", "role": "manager", "status": "pending"},
            ],
            author="pm",
            required_count=2,
        )
        self.assertFalse(d.content["sufficient"])
        self.assertEqual(d.content["approved_count"], 1)

    def test_generate_checklist(self):
        """Test generating a deployment checklist."""
        items = [
            {"task": "Backup database", "completed": True, "assigned_to": "dba"},
            {"task": "Deploy to staging", "completed": True, "assigned_to": "devops"},
            {"task": "Smoke tests", "completed": False, "assigned_to": "qa"},
            {"task": "Switch traffic", "completed": False, "assigned_to": "sre"},
        ]
        d = self.mgr.generate_checklist("CHG-007", items, author="release-mgr")
        self.assertEqual(d.content["completed"], 2)
        self.assertEqual(d.content["total"], 4)
        self.assertEqual(d.content["progress_percent"], 50.0)

    def test_generate_checklist_empty(self):
        """Test generating an empty checklist."""
        d = self.mgr.generate_checklist("CHG-008", [], author="release-mgr")
        self.assertEqual(d.content["completed"], 0)
        self.assertEqual(d.content["progress_percent"], 0)

    def test_document_rollback(self):
        """Test documenting rollback procedure."""
        d = self.mgr.document_rollback(
            change_id="CHG-009",
            steps=["Stop new version", "Start old version", "Restore DB", "Validate"],
            author="sre",
            trigger_conditions=["Error rate > 5%", "P99 latency > 1s"],
            estimated_time_minutes=20,
            responsible_team="platform-sre",
        )
        self.assertEqual(d.deliverable_type, DeliverableType.ROLLBACK_PROCEDURE)
        self.assertEqual(d.content["step_count"], 4)
        self.assertEqual(d.content["estimated_time_minutes"], 20)
        self.assertEqual(len(d.content["trigger_conditions"]), 2)

    def test_create_monitoring_plan(self):
        """Test creating a monitoring plan."""
        d = self.mgr.create_monitoring_plan(
            change_id="CHG-010",
            metrics=["error_rate", "latency_p99", "throughput", "cpu_usage"],
            author="sre",
            alert_rules=[
                {"name": "HighErrorRate", "threshold": 5, "severity": "critical"},
                {"name": "HighLatency", "threshold": 500, "severity": "warning"},
            ],
            dashboards=["https://grafana/d/release-dashboard"],
            observation_period_minutes=60,
        )
        self.assertEqual(len(d.content["metrics"]), 4)
        self.assertEqual(len(d.content["alert_rules"]), 2)
        self.assertEqual(d.content["observation_period_minutes"], 60)

    def test_generate_release_notes(self):
        """Test generating release notes."""
        d = self.mgr.generate_release_notes(
            release_name="Auth Service v2.3",
            version="2.3.0",
            author="platform-team",
            features=["OAuth2.1 support", "PKCE flow"],
            fixes=["Token refresh race condition", "Session timeout bug"],
            breaking_changes=["Deprecated v1 endpoints removed"],
            known_issues=["Slow first login with large user tables"],
            upgrade_instructions="Run migration script v2.3-upgrade.sql",
        )
        self.assertEqual(d.deliverable_type, DeliverableType.RELEASE_NOTES)
        self.assertEqual(d.content["release_name"], "Auth Service v2.3")
        self.assertEqual(len(d.content["features"]), 2)
        self.assertEqual(len(d.content["fixes"]), 2)
        self.assertEqual(len(d.content["breaking_changes"]), 1)

    def test_compile_post_release_report(self):
        """Test compiling a post-release report."""
        d = self.mgr.compile_post_release_report(
            change_id="CHG-011",
            author="sre",
            deployment_result="success",
            incident_count=0,
            user_feedback="Users reported faster login",
            metrics_summary={"error_rate_avg": 0.05, "latency_p99": 120},
            lessons_learned=["Staged rollout reduced risk", "Monitoring caught anomaly early"],
        )
        self.assertEqual(d.deliverable_type, DeliverableType.POST_RELEASE_REPORT)
        self.assertEqual(d.content["deployment_result"], "success")
        self.assertEqual(d.content["incident_count"], 0)
        self.assertEqual(len(d.content["lessons_learned"]), 2)

    def test_archive_deliverables(self):
        """Test archiving all deliverables."""
        # Create several deliverables
        self.mgr.create_release_plan("Test", "1.0", author="me")
        self.mgr.generate_change_record("CHG-001", "Fix", "Desc", author="me")
        self.mgr.document_risk("CHG-001", "MEDIUM", author="me")

        archive_path = os.path.join(self.tmpdir, "archive.json")
        result = self.mgr.archive_deliverables(archive_path)
        self.assertTrue(result["success"])
        self.assertEqual(result["deliverable_count"], 3)
        self.assertTrue(os.path.exists(archive_path))

        # Verify archive content
        with open(archive_path) as f:
            data = json.load(f)
            self.assertEqual(data["deliverable_count"], 3)
            self.assertIsInstance(data["deliverables"], list)

    def test_get_deliverable(self):
        """Test getting a deliverable by type."""
        self.mgr.create_release_plan("R1", "1.0", author="me")
        self.mgr.create_release_plan("R2", "2.0", author="me")

        d = self.mgr.get_deliverable(DeliverableType.RELEASE_PLAN)
        self.assertIsNotNone(d)
        # Should return the most recent (R2)
        self.assertEqual(d.content["release_name"], "R2")

    def test_get_deliverable_none(self):
        """Test getting a deliverable type that doesn't exist."""
        d = self.mgr.get_deliverable(DeliverableType.RELEASE_NOTES)
        self.assertIsNone(d)

    def test_list_deliverables_filtered(self):
        """Test listing deliverables with filters."""
        self.mgr.create_release_plan("R1", "1.0", author="me")
        self.mgr.generate_change_record("CHG-001", "Fix", "Desc", author="me")

        all_d = self.mgr.list_deliverables()
        self.assertEqual(len(all_d), 2)

        plans = self.mgr.list_deliverables(deliverable_type=DeliverableType.RELEASE_PLAN)
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0].deliverable_type, DeliverableType.RELEASE_PLAN)

    def test_approve_and_reject_deliverable(self):
        """Test approving and rejecting a deliverable."""
        d = self.mgr.create_release_plan("R1", "1.0", author="me")
        self.assertFalse(d.approved)

        d.approve("reviewer1")
        self.assertTrue(d.approved)

        # List approved only
        approved = self.mgr.list_deliverables(approved_only=True)
        self.assertEqual(len(approved), 1)

        d.reject("reviewer2", "Needs more detail")
        self.assertFalse(d.approved)
        self.assertEqual(d.metadata.get("rejection_reason"), "Needs more detail")

    def test_get_compliance_status(self):
        """Test getting compliance status."""
        # No required deliverables yet
        status = self.mgr.get_compliance_status()
        self.assertFalse(status["compliant"])

        # Create and approve all required deliverables
        self.mgr.generate_change_record("CHG-C", "C", "D", author="me")
        self.mgr.document_risk("CHG-C", "LOW", author="me")
        self.mgr.record_approvals("CHG-C", [
            {"name": "alice", "role": "lead", "status": "approved"}
        ], author="me")
        self.mgr.document_rollback("CHG-C", ["Revert"], author="me")
        self.mgr.compile_post_release_report("CHG-C", author="me")

        for dt in [DeliverableType.CHANGE_RECORD, DeliverableType.RISK_CLASSIFICATION,
                    DeliverableType.APPROVAL_RECORD, DeliverableType.ROLLBACK_PROCEDURE,
                    DeliverableType.POST_RELEASE_REPORT]:
            d = self.mgr.get_deliverable(dt)
            if d:
                d.approve("compliance-officer")

        status = self.mgr.get_compliance_status()
        self.assertTrue(status["compliant"])


# ═══════════════════════════════════════════════════════════════════════════════
# Enum and Dataclass Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestEnums(unittest.TestCase):
    """Tests for enum properties and behavior."""

    def test_change_stage_progression(self):
        """Test ChangeStage progression chain."""
        stage = ChangeStage.REGISTER
        stages = []
        while stage:
            stages.append(stage)
            stage = stage.next_stage
        # Should go through all 12 non-terminal stages + DOCUMENT_LESSONS -> CLOSE
        self.assertIn(ChangeStage.CLOSE, stages)
        self.assertEqual(stages[-1], ChangeStage.CLOSE)

    def test_change_stage_is_terminal(self):
        """Test terminal stage detection."""
        self.assertTrue(ChangeStage.CLOSE.is_terminal)
        self.assertTrue(ChangeStage.ROLLBACK.is_terminal)
        self.assertFalse(ChangeStage.REGISTER.is_terminal)

    def test_change_type_is_high_stakes(self):
        """Test high stakes change types."""
        self.assertTrue(ChangeType.EMERGENCY.is_high_stakes)
        self.assertTrue(ChangeType.SECURITY.is_high_stakes)
        self.assertTrue(ChangeType.COMPLIANCE.is_high_stakes)
        self.assertFalse(ChangeType.STANDARD.is_high_stakes)

    def test_risk_level_from_score(self):
        """Test RiskLevel.from_score thresholds."""
        self.assertEqual(RiskLevel.from_score(0.95), RiskLevel.CRITICAL)
        self.assertEqual(RiskLevel.from_score(0.85), RiskLevel.CRITICAL)
        self.assertEqual(RiskLevel.from_score(0.75), RiskLevel.HIGH)
        self.assertEqual(RiskLevel.from_score(0.50), RiskLevel.MEDIUM)
        self.assertEqual(RiskLevel.from_score(0.20), RiskLevel.LOW)

    def test_strategy_supports_instant_rollback(self):
        """Test instant rollback support detection."""
        self.assertTrue(StrategyType.FEATURE_FLAGS.supports_instant_rollback)
        self.assertTrue(StrategyType.BLUE_GREEN.supports_instant_rollback)
        self.assertFalse(StrategyType.ROLLING.supports_instant_rollback)
        self.assertFalse(StrategyType.CANARY.supports_instant_rollback)

    def test_gate_type_is_blocking(self):
        """Test blocking gate detection."""
        self.assertTrue(GateType.TESTS_PASSING.is_blocking)
        self.assertTrue(GateType.SECURITY_APPROVAL.is_blocking)
        self.assertTrue(GateType.OWNER_APPROVAL.is_blocking)
        self.assertTrue(GateType.CHANGE_RECORD.is_blocking)
        self.assertFalse(GateType.MONITORING.is_blocking)
        self.assertFalse(GateType.COMMUNICATION_PLAN.is_blocking)

    def test_deliverable_required_for_compliance(self):
        """Test compliance-required deliverable types."""
        self.assertTrue(DeliverableType.CHANGE_RECORD.required_for_compliance)
        self.assertTrue(DeliverableType.RISK_CLASSIFICATION.required_for_compliance)
        self.assertTrue(DeliverableType.APPROVAL_RECORD.required_for_compliance)
        self.assertTrue(DeliverableType.ROLLBACK_PROCEDURE.required_for_compliance)
        self.assertTrue(DeliverableType.POST_RELEASE_REPORT.required_for_compliance)
        self.assertFalse(DeliverableType.RELEASE_PLAN.required_for_compliance)

    def test_gate_status_is_satisfied(self):
        """Test GateStatus.is_satisfied."""
        self.assertTrue(GateStatus.PASSED.is_satisfied)
        self.assertTrue(GateStatus.WAIVED.is_satisfied)
        self.assertFalse(GateStatus.FAILED.is_satisfied)
        self.assertFalse(GateStatus.PENDING.is_satisfied)

    def test_deployment_strategy_to_dict(self):
        """Test DeploymentStrategy serialization."""
        strategy = DeploymentStrategy(
            name="test-canary",
            strategy_type=StrategyType.CANARY,
            traffic_split_percent=5,
            health_check_endpoint="/health",
            feature_flag_key="test-flag",
        )
        d = strategy.to_dict()
        self.assertEqual(d["name"], "test-canary")
        self.assertEqual(d["strategy_type"], "canary")
        self.assertEqual(d["traffic_split_percent"], 5)

    def test_change_template_to_dict(self):
        """Test ChangeTemplate serialization."""
        tmpl = ChangeTemplate(
            change_type=ChangeType.SECURITY,
            default_risk=RiskLevel.CRITICAL,
            required_approvals=2,
            required_tests=["security_scan"],
        )
        d = tmpl.to_dict()
        self.assertEqual(d["change_type"], "security")
        self.assertEqual(d["default_risk"], "critical")
        self.assertEqual(d["required_approvals"], 2)


if __name__ == "__main__":
    unittest.main()