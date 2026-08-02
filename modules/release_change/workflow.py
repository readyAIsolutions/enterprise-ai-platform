"""
Release Change Workflow Engine

Implements a 14-stage structured change workflow from registration
through deployment, validation, rollback, and lessons learned.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("enterprise.release_change")


class ChangeStage(str, Enum):
    """The 14 stages of a structured change lifecycle."""
    REGISTER = "register"
    CLASSIFY_RISK = "classify_risk"
    IDENTIFY_AFFECTED = "identify_affected"
    DEFINE_ACCEPTANCE = "define_acceptance"
    TEST = "test"
    SECURITY_REVIEW = "security_review"
    APPROVALS = "approvals"
    ROLLBACK_PLAN = "rollback_plan"
    DEPLOY_PROGRESSIVELY = "deploy_progressively"
    MONITOR = "monitor"
    VALIDATE = "validate"
    CLOSE = "close"
    ROLLBACK = "rollback"
    DOCUMENT_LESSONS = "document_lessons"

    @property
    def is_terminal(self) -> bool:
        """Whether this stage is a terminal/end state."""
        return self in (ChangeStage.CLOSE, ChangeStage.ROLLBACK)

    @property
    def next_stage(self) -> Optional["ChangeStage"]:
        """Get the next stage in the normal workflow progression."""
        progression = {
            ChangeStage.REGISTER: ChangeStage.CLASSIFY_RISK,
            ChangeStage.CLASSIFY_RISK: ChangeStage.IDENTIFY_AFFECTED,
            ChangeStage.IDENTIFY_AFFECTED: ChangeStage.DEFINE_ACCEPTANCE,
            ChangeStage.DEFINE_ACCEPTANCE: ChangeStage.TEST,
            ChangeStage.TEST: ChangeStage.SECURITY_REVIEW,
            ChangeStage.SECURITY_REVIEW: ChangeStage.APPROVALS,
            ChangeStage.APPROVALS: ChangeStage.ROLLBACK_PLAN,
            ChangeStage.ROLLBACK_PLAN: ChangeStage.DEPLOY_PROGRESSIVELY,
            ChangeStage.DEPLOY_PROGRESSIVELY: ChangeStage.MONITOR,
            ChangeStage.MONITOR: ChangeStage.VALIDATE,
            ChangeStage.VALIDATE: ChangeStage.DOCUMENT_LESSONS,
            ChangeStage.DOCUMENT_LESSONS: ChangeStage.CLOSE,
        }
        return progression.get(self)


@dataclass
class ChangeRecord:
    """Central record tracking a single change through its entire lifecycle.

    Attributes:
        change_id: Unique change identifier.
        title: Short descriptive title for the change.
        description: Detailed description of what the change entails.
        requester: Person or system that requested the change.
        stage: Current stage in the change lifecycle.
        risk_level: Assessed risk level (e.g., 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW').
        affected_systems: List of systems/components impacted by this change.
        acceptance_criteria: Criteria that must be met for the change to be accepted.
        test_results: Results from testing the change.
        security_review_passed: Whether the security review was successful.
        approvals: List of approval records (approver name, role, timestamp).
        rollback_plan: Detailed plan for rolling back the change if needed.
        deployment_strategy: The deployment strategy being used.
        monitoring_plan: Plan for monitoring the change post-deployment.
        validation_results: Results from post-deployment validation.
        status: Overall status (e.g., 'open', 'in_progress', 'completed', 'rolled_back').
        lessons_learned: Post-mortem lessons learned from this change.
        metadata: Arbitrary additional metadata.
        created_at: Timestamp when the change was registered.
        updated_at: Timestamp of the last update.
    """
    change_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    title: str = ""
    description: str = ""
    requester: str = ""
    stage: ChangeStage = ChangeStage.REGISTER
    risk_level: str = ""
    affected_systems: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    test_results: Dict[str, Any] = field(default_factory=dict)
    security_review_passed: bool = False
    approvals: List[Dict[str, str]] = field(default_factory=list)
    rollback_plan: Dict[str, Any] = field(default_factory=dict)
    deployment_strategy: str = ""
    monitoring_plan: Dict[str, Any] = field(default_factory=dict)
    validation_results: Dict[str, Any] = field(default_factory=dict)
    status: str = "open"
    lessons_learned: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def _touch(self) -> None:
        """Update the last-modified timestamp."""
        self.updated_at = datetime.utcnow().isoformat()

    def advance(self, stage: ChangeStage) -> None:
        """Advance the change to the specified stage."""
        self.stage = stage
        self._touch()
        logger.info("Change %s advanced to stage %s", self.change_id, stage.value)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the change record to a dictionary."""
        return {
            "change_id": self.change_id,
            "title": self.title,
            "description": self.description,
            "requester": self.requester,
            "stage": self.stage.value,
            "risk_level": self.risk_level,
            "affected_systems": self.affected_systems,
            "acceptance_criteria": self.acceptance_criteria,
            "test_results": self.test_results,
            "security_review_passed": self.security_review_passed,
            "approvals": self.approvals,
            "rollback_plan": self.rollback_plan,
            "deployment_strategy": self.deployment_strategy,
            "monitoring_plan": self.monitoring_plan,
            "validation_results": self.validation_results,
            "status": self.status,
            "lessons_learned": self.lessons_learned,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ChangeWorkflow:
    """Orchestrates a change through its full 14-stage lifecycle.

    Usage:
        wf = ChangeWorkflow()
        record = wf.register_change(
            title="Upgrade auth service",
            description="Deploy v2.3 of auth service",
            requester="platform-team"
        )
        wf.classify_risk(record, risk_level="MEDIUM")
        wf.identify_affected_systems(record, ["auth-svc", "api-gateway"])
        # ... continue through stages ...
    """

    def __init__(self) -> None:
        self._changes: Dict[str, ChangeRecord] = {}
        self._history: List[Dict[str, Any]] = []

    def _log_event(self, change: ChangeRecord, event: str, details: Optional[Dict] = None) -> None:
        """Record an event in the workflow history."""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "change_id": change.change_id,
            "stage": change.stage.value,
            "event": event,
            "details": details or {},
        }
        self._history.append(entry)
        logger.info("CHANGE_EVENT [%s] %s: %s", change.change_id, event, details or "")

    # ─── Stage 1: REGISTER ─────────────────────────────────────────────────

    def register_change(
        self,
        title: str,
        description: str,
        requester: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ChangeRecord:
        """Register a new change and start its lifecycle.

        Args:
            title: Short descriptive title.
            description: Detailed description.
            requester: Person/system requesting the change.
            metadata: Optional additional metadata.

        Returns:
            The newly created ChangeRecord.
        """
        record = ChangeRecord(
            title=title,
            description=description,
            requester=requester,
            stage=ChangeStage.REGISTER,
            metadata=metadata or {},
        )
        self._changes[record.change_id] = record
        self._log_event(record, "change_registered", {"title": title, "requester": requester})
        logger.info("Registered change %s: %s", record.change_id, title)
        return record

    # ─── Stage 2: CLASSIFY_RISK ────────────────────────────────────────────

    def classify_risk(
        self,
        change: ChangeRecord,
        risk_level: str,
        reason: Optional[str] = None,
    ) -> ChangeRecord:
        """Classify the risk level of the change.

        Args:
            change: The change record to classify.
            risk_level: Risk level (CRITICAL, HIGH, MEDIUM, LOW).
            reason: Optional justification for the risk classification.

        Returns:
            The updated ChangeRecord.
        """
        change.risk_level = risk_level
        change.advance(ChangeStage.CLASSIFY_RISK)
        self._log_event(change, "risk_classified", {"risk_level": risk_level, "reason": reason})
        return change

    # ─── Stage 3: IDENTIFY_AFFECTED ────────────────────────────────────────

    def identify_affected_systems(
        self,
        change: ChangeRecord,
        systems: List[str],
    ) -> ChangeRecord:
        """Identify all systems and components affected by this change.

        Args:
            change: The change record.
            systems: List of affected system/component names.

        Returns:
            The updated ChangeRecord.
        """
        change.affected_systems = systems
        change.advance(ChangeStage.IDENTIFY_AFFECTED)
        self._log_event(change, "affected_systems_identified", {"systems": systems})
        return change

    # ─── Stage 4: DEFINE_ACCEPTANCE ────────────────────────────────────────

    def define_acceptance_criteria(
        self,
        change: ChangeRecord,
        criteria: List[str],
    ) -> ChangeRecord:
        """Define acceptance criteria that must pass for the change to be approved.

        Args:
            change: The change record.
            criteria: List of acceptance criteria statements.

        Returns:
            The updated ChangeRecord.
        """
        change.acceptance_criteria = criteria
        change.advance(ChangeStage.DEFINE_ACCEPTANCE)
        self._log_event(change, "acceptance_criteria_defined", {"criteria": criteria})
        return change

    # ─── Stage 5: TEST ─────────────────────────────────────────────────────

    def run_tests(
        self,
        change: ChangeRecord,
        results: Dict[str, Any],
    ) -> ChangeRecord:
        """Record test execution results for the change.

        Args:
            change: The change record.
            results: Dictionary of test results (e.g., {'unit': 'pass', 'integration': 'pass'}).

        Returns:
            The updated ChangeRecord.

        Raises:
            ValueError: If any critical test failures are detected.
        """
        change.test_results = results
        change.advance(ChangeStage.TEST)
        failures = {k: v for k, v in results.items() if v in ("fail", "error", "failed")}
        if failures:
            self._log_event(change, "tests_failed", {"failures": failures})
            raise ValueError(f"Tests failed for change {change.change_id}: {failures}")
        self._log_event(change, "tests_passed", {"results": results})
        return change

    # ─── Stage 6: SECURITY_REVIEW ──────────────────────────────────────────

    def security_review(
        self,
        change: ChangeRecord,
        passed: bool,
        reviewer: Optional[str] = None,
        findings: Optional[Dict[str, Any]] = None,
    ) -> ChangeRecord:
        """Record the security review outcome.

        Args:
            change: The change record.
            passed: Whether the security review passed.
            reviewer: Name of the security reviewer.
            findings: Any findings from the review.

        Returns:
            The updated ChangeRecord.

        Raises:
            ValueError: If the security review did not pass.
        """
        change.security_review_passed = passed
        change.advance(ChangeStage.SECURITY_REVIEW)
        self._log_event(change, "security_review", {
            "passed": passed,
            "reviewer": reviewer,
            "findings": findings,
        })
        if not passed:
            raise ValueError(
                f"Security review failed for change {change.change_id}"
            )
        return change

    # ─── Stage 7: APPROVALS ────────────────────────────────────────────────

    def request_approvals(
        self,
        change: ChangeRecord,
        approvers: List[Dict[str, str]],
        required_count: int = 1,
    ) -> ChangeRecord:
        """Request and record approvals for the change.

        Each approver dict should have keys: 'name', 'role', and optionally 'status'.
        Status defaults to 'pending'; set to 'approved' or 'rejected' as needed.

        Args:
            change: The change record.
            approvers: List of approver records.
            required_count: Minimum number of approvals required.

        Returns:
            The updated ChangeRecord.

        Raises:
            ValueError: If insufficient approvals are obtained.
        """
        for a in approvers:
            a.setdefault("status", "pending")
            a.setdefault("timestamp", datetime.utcnow().isoformat())
        change.approvals = approvers
        change.advance(ChangeStage.APPROVALS)
        approved_count = sum(1 for a in approvers if a.get("status") == "approved")
        self._log_event(change, "approvals_requested", {
            "approvers": approvers,
            "approved_count": approved_count,
            "required_count": required_count,
        })
        if approved_count < required_count:
            raise ValueError(
                f"Insufficient approvals for change {change.change_id}: "
                f"got {approved_count}, need {required_count}"
            )
        return change

    # ─── Stage 8: ROLLBACK_PLAN ────────────────────────────────────────────

    def create_rollback_plan(
        self,
        change: ChangeRecord,
        plan: Dict[str, Any],
    ) -> ChangeRecord:
        """Define the rollback plan for the change.

        The plan dict should include keys like 'steps', 'trigger_conditions',
        'estimated_time_minutes', and 'responsible_team'.

        Args:
            change: The change record.
            plan: Rollback plan details.

        Returns:
            The updated ChangeRecord.
        """
        change.rollback_plan = plan
        change.advance(ChangeStage.ROLLBACK_PLAN)
        self._log_event(change, "rollback_plan_created", {"plan": plan})
        return change

    # ─── Stage 9: DEPLOY_PROGRESSIVELY ─────────────────────────────────────

    def deploy_progressively(
        self,
        change: ChangeRecord,
        strategy: str = "rolling",
        target: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> ChangeRecord:
        """Execute progressive deployment of the change.

        Args:
            change: The change record.
            strategy: Deployment strategy name (rolling, canary, blue_green, etc.).
            target: Target infrastructure identifier.
            config: Strategy-specific configuration.

        Returns:
            The updated ChangeRecord.
        """
        change.deployment_strategy = strategy
        change.advance(ChangeStage.DEPLOY_PROGRESSIVELY)
        self._log_event(change, "deployment_started", {
            "strategy": strategy,
            "target": target,
            "config": config,
        })
        return change

    # ─── Stage 10: MONITOR ─────────────────────────────────────────────────

    def monitor_deployment(
        self,
        change: ChangeRecord,
        metrics: Dict[str, Any],
        alerts: Optional[List[Dict[str, Any]]] = None,
    ) -> ChangeRecord:
        """Record monitoring plan and observed metrics during deployment.

        Args:
            change: The change record.
            metrics: Monitoring metrics collected (e.g., error_rate, latency, throughput).
            alerts: Any alerts triggered during the monitoring window.

        Returns:
            The updated ChangeRecord.
        """
        change.monitoring_plan = {
            "metrics": metrics,
            "alerts": alerts or [],
            "monitored_at": datetime.utcnow().isoformat(),
        }
        change.advance(ChangeStage.MONITOR)
        self._log_event(change, "monitoring_completed", {
            "metrics": metrics,
            "alert_count": len(alerts) if alerts else 0,
        })
        return change

    # ─── Stage 11: VALIDATE ────────────────────────────────────────────────

    def validate_deployment(
        self,
        change: ChangeRecord,
        results: Dict[str, Any],
    ) -> ChangeRecord:
        """Validate the deployment against acceptance criteria.

        Args:
            change: The change record.
            results: Validation results keyed by criterion.

        Returns:
            The updated ChangeRecord.

        Raises:
            ValueError: If validation fails.
        """
        change.validation_results = results
        change.advance(ChangeStage.VALIDATE)
        failed = {k: v for k, v in results.items() if not v}
        if failed:
            self._log_event(change, "validation_failed", {"failures": failed})
            raise ValueError(
                f"Validation failed for change {change.change_id}: {failed}"
            )
        self._log_event(change, "validation_passed", {"results": results})
        return change

    # ─── Stage 12: CLOSE ───────────────────────────────────────────────────

    def close_change(self, change: ChangeRecord) -> ChangeRecord:
        """Close the change as successfully completed.

        Args:
            change: The change record.

        Returns:
            The updated ChangeRecord.
        """
        change.status = "completed"
        change.advance(ChangeStage.CLOSE)
        self._log_event(change, "change_closed")
        return change

    # ─── Stage 13: ROLLBACK ────────────────────────────────────────────────

    def execute_rollback(
        self,
        change: ChangeRecord,
        reason: str = "",
        executed_by: Optional[str] = None,
    ) -> ChangeRecord:
        """Execute the rollback plan and record the rollback.

        Args:
            change: The change record.
            reason: Reason for triggering the rollback.
            executed_by: Who executed the rollback.

        Returns:
            The updated ChangeRecord.
        """
        change.status = "rolled_back"
        change.advance(ChangeStage.ROLLBACK)
        self._log_event(change, "rollback_executed", {
            "reason": reason,
            "executed_by": executed_by,
            "plan_used": change.rollback_plan,
        })
        return change

    # ─── Stage 14: DOCUMENT_LESSONS ────────────────────────────────────────

    def document_lessons(
        self,
        change: ChangeRecord,
        lessons: List[str],
    ) -> ChangeRecord:
        """Document lessons learned from the change.

        Args:
            change: The change record.
            lessons: List of lessons learned.

        Returns:
            The updated ChangeRecord.
        """
        change.lessons_learned = lessons
        change.advance(ChangeStage.DOCUMENT_LESSONS)
        self._log_event(change, "lessons_documented", {"lessons": lessons})
        return change

    # ─── Convenience ───────────────────────────────────────────────────────

    def get_change(self, change_id: str) -> Optional[ChangeRecord]:
        """Retrieve a change record by ID."""
        return self._changes.get(change_id)

    def list_changes(
        self,
        status: Optional[str] = None,
        stage: Optional[ChangeStage] = None,
        risk_level: Optional[str] = None,
    ) -> List[ChangeRecord]:
        """List changes, optionally filtered by status, stage, or risk level."""
        results = list(self._changes.values())
        if status:
            results = [c for c in results if c.status == status]
        if stage:
            results = [c for c in results if c.stage == stage]
        if risk_level:
            results = [c for c in results if c.risk_level == risk_level]
        return results

    def get_history(self, change_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get workflow history, optionally filtered by change ID."""
        if change_id:
            return [e for e in self._history if e["change_id"] == change_id]
        return list(self._history)

    def run_full_workflow(
        self,
        title: str,
        description: str,
        requester: str,
        risk_level: str,
        affected_systems: List[str],
        acceptance_criteria: List[str],
        test_results: Dict[str, Any],
        security_passed: bool,
        approvers: List[Dict[str, str]],
        rollback_plan: Dict[str, Any],
        deployment_strategy: str,
        monitor_metrics: Dict[str, Any],
        validation_results: Dict[str, Any],
        lessons: List[str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ChangeRecord:
        """Run the entire change workflow from registration through closure.

        This is a convenience method that chains all stages together.
        If any stage raises (e.g., failed tests or validation), the exception
        propagates to the caller.

        Returns:
            The completed ChangeRecord with status 'completed'.
        """
        change = self.register_change(title, description, requester, metadata)
        self.classify_risk(change, risk_level)
        self.identify_affected_systems(change, affected_systems)
        self.define_acceptance_criteria(change, acceptance_criteria)
        self.run_tests(change, test_results)
        self.security_review(change, security_passed)
        self.request_approvals(change, approvers)
        self.create_rollback_plan(change, rollback_plan)
        self.deploy_progressively(change, strategy=deployment_strategy)
        self.monitor_deployment(change, monitor_metrics)
        self.validate_deployment(change, validation_results)
        self.document_lessons(change, lessons)
        self.close_change(change)
        return change