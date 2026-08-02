"""
Quality Gate Engine

Enforces 10 quality gates that must be passed before a change
can proceed through its lifecycle. Generates comprehensive gate reports.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("enterprise.release_change")


class GateType(str, Enum):
    """Types of quality gates in the change pipeline."""
    TESTS_PASSING = "tests_passing"
    SECURITY_APPROVAL = "security_approval"
    DEPENDENCY_VERIFICATION = "dependency_verification"
    DB_MIGRATION_PLAN = "db_migration_plan"
    MONITORING = "monitoring"
    ROLLBACK_PLAN = "rollback_plan"
    OWNER_APPROVAL = "owner_approval"
    CHANGE_RECORD = "change_record"
    USER_IMPACT_ASSESSMENT = "user_impact_assessment"
    COMMUNICATION_PLAN = "communication_plan"

    @property
    def is_blocking(self) -> bool:
        """Whether failing this gate blocks the release."""
        return self in (
            GateType.TESTS_PASSING, GateType.SECURITY_APPROVAL,
            GateType.OWNER_APPROVAL, GateType.CHANGE_RECORD,
        )

    @property
    def description(self) -> str:
        """Human-readable description of the gate."""
        return {
            GateType.TESTS_PASSING: "All required tests must pass",
            GateType.SECURITY_APPROVAL: "Security team must approve the change",
            GateType.DEPENDENCY_VERIFICATION: "All dependencies verified compatible",
            GateType.DB_MIGRATION_PLAN: "Database migration plan documented and reviewed",
            GateType.MONITORING: "Monitoring dashboards and alerts configured",
            GateType.ROLLBACK_PLAN: "Rollback plan documented and tested",
            GateType.OWNER_APPROVAL: "Service/component owner has approved",
            GateType.CHANGE_RECORD: "Change record is complete and accurate",
            GateType.USER_IMPACT_ASSESSMENT: "User impact has been assessed",
            GateType.COMMUNICATION_PLAN: "Communication plan for stakeholders exists",
        }.get(self, "Unknown gate")


class GateStatus(str, Enum):
    """Possible statuses for a quality gate."""
    PASSED = "passed"
    FAILED = "failed"
    PENDING = "pending"
    WAIVED = "waived"

    @property
    def is_satisfied(self) -> bool:
        """Whether this status satisfies the gate (passed or waived)."""
        return self in (GateStatus.PASSED, GateStatus.WAIVED)


@dataclass
class QualityGate:
    """Represents a single quality gate check.

    Attributes:
        gate_type: The type of quality gate.
        status: Current status (passed, failed, pending, waived).
        evidence: Supporting evidence for the gate result.
        reviewer: Name of the person who reviewed the gate.
        timestamp: When the gate was evaluated.
        waiver_reason: Reason if the gate was waived.
        metadata: Additional metadata.
    """
    gate_type: GateType
    status: GateStatus = GateStatus.PENDING
    evidence: Dict[str, Any] = field(default_factory=dict)
    reviewer: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    waiver_reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def pass_gate(self, reviewer: str = "", evidence: Optional[Dict[str, Any]] = None) -> None:
        """Mark the gate as passed with evidence."""
        self.status = GateStatus.PASSED
        self.reviewer = reviewer
        self.evidence = evidence or {}
        self.timestamp = datetime.utcnow().isoformat()

    def fail_gate(self, reviewer: str = "", reason: str = "") -> None:
        """Mark the gate as failed."""
        self.status = GateStatus.FAILED
        self.reviewer = reviewer
        self.evidence = {"failure_reason": reason}
        self.timestamp = datetime.utcnow().isoformat()

    def waive_gate(self, reviewer: str = "", reason: str = "") -> None:
        """Waive the gate with a justification."""
        self.status = GateStatus.WAIVED
        self.reviewer = reviewer
        self.waiver_reason = reason
        self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "gate_type": self.gate_type.value,
            "status": self.status.value,
            "evidence": self.evidence,
            "reviewer": self.reviewer,
            "timestamp": self.timestamp,
            "waiver_reason": self.waiver_reason,
            "is_blocking": self.gate_type.is_blocking,
        }


class QualityGateEngine:
    """Engine for running and managing all quality gates in a change pipeline.

    Usage:
        engine = QualityGateEngine()
        engine.check_tests_passing({"unit": "pass", "integration": "pass"})
        engine.verify_security(True, "alice")
        report = engine.generate_gate_report()
    """

    def __init__(self) -> None:
        self._gates: Dict[GateType, QualityGate] = {}
        self._initialize_gates()

    def _initialize_gates(self) -> None:
        """Initialize all gates to PENDING state."""
        for gate_type in GateType:
            self._gates[gate_type] = QualityGate(gate_type=gate_type)

    def get_gate(self, gate_type: GateType) -> QualityGate:
        """Get a specific gate by type."""
        return self._gates[gate_type]

    def get_all_gates(self) -> List[QualityGate]:
        """Get all gates."""
        return list(self._gates.values())

    def reset(self) -> None:
        """Reset all gates to PENDING."""
        self._initialize_gates()

    # ── Gate 1: Tests Passing ──────────────────────────────────────────────

    def check_tests_passing(
        self,
        test_results: Dict[str, str],
        reviewer: str = "",
    ) -> QualityGate:
        """Check that all required tests are passing.

        Args:
            test_results: Dict of test_name -> status ('pass', 'fail', 'error').
            reviewer: Name of the reviewer.

        Returns:
            The evaluated QualityGate.
        """
        gate = self._gates[GateType.TESTS_PASSING]
        failures = {k: v for k, v in test_results.items() if v not in ("pass", "passed")}

        if not failures:
            gate.pass_gate(reviewer, {"test_results": test_results, "total": len(test_results)})
        else:
            gate.fail_gate(reviewer, f"Failures: {failures}")
            gate.evidence["test_results"] = test_results
            gate.evidence["failures"] = failures

        logger.info("Tests gate: %s (failures: %d)", gate.status.value, len(failures))
        return gate

    # ── Gate 2: Security Approval ──────────────────────────────────────────

    def verify_security(
        self,
        approved: bool,
        reviewer: str = "",
        scan_results: Optional[Dict[str, Any]] = None,
    ) -> QualityGate:
        """Verify security approval for the change.

        Args:
            approved: Whether security has approved.
            reviewer: Name of the security reviewer.
            scan_results: Optional security scan results.

        Returns:
            The evaluated QualityGate.
        """
        gate = self._gates[GateType.SECURITY_APPROVAL]
        if approved:
            gate.pass_gate(reviewer, {"scan_results": scan_results or {}})
        else:
            gate.fail_gate(reviewer, "Security review not approved")
        logger.info("Security gate: %s", gate.status.value)
        return gate

    # ── Gate 3: Dependency Verification ────────────────────────────────────

    def verify_dependencies(
        self,
        dependencies: Dict[str, str],
        reviewer: str = "",
    ) -> QualityGate:
        """Verify all dependencies are compatible and available.

        Args:
            dependencies: Dict of dependency_name -> version.
            reviewer: Name of the reviewer.

        Returns:
            The evaluated QualityGate.
        """
        gate = self._gates[GateType.DEPENDENCY_VERIFICATION]
        incompatible = {}
        for dep, version in dependencies.items():
            if "incompatible" in version.lower() or "blocked" in version.lower():
                incompatible[dep] = version

        if not incompatible:
            gate.pass_gate(reviewer, {"dependencies": dependencies, "count": len(dependencies)})
        else:
            gate.fail_gate(reviewer, f"Incompatible: {incompatible}")
            gate.evidence["dependencies"] = dependencies
            gate.evidence["incompatible"] = incompatible

        logger.info("Dependency gate: %s", gate.status.value)
        return gate

    # ── Gate 4: DB Migration Plan ──────────────────────────────────────────

    def validate_migration(
        self,
        migration_plan: Dict[str, Any],
        reviewer: str = "",
    ) -> QualityGate:
        """Validate that a database migration plan exists and is sound.

        Args:
            migration_plan: Dict with keys like 'steps', 'rollback', 'tested'.
            reviewer: Name of the reviewer.

        Returns:
            The evaluated QualityGate.
        """
        gate = self._gates[GateType.DB_MIGRATION_PLAN]
        required_keys = ["steps", "rollback"]
        missing = [k for k in required_keys if k not in migration_plan]

        if not missing:
            tested = migration_plan.get("tested", False)
            if tested:
                gate.pass_gate(reviewer, {"migration_plan": migration_plan})
            else:
                gate.fail_gate(reviewer, "Migration plan not tested")
        else:
            gate.fail_gate(reviewer, f"Missing required sections: {missing}")

        logger.info("Migration gate: %s", gate.status.value)
        return gate

    # ── Gate 5: Monitoring ─────────────────────────────────────────────────

    def check_monitoring(
        self,
        dashboards_configured: bool,
        alerts_configured: bool,
        reviewer: str = "",
        alert_rules: Optional[List[str]] = None,
    ) -> QualityGate:
        """Check that monitoring dashboards and alerts are configured.

        Args:
            dashboards_configured: Whether monitoring dashboards are set up.
            alerts_configured: Whether alert rules are configured.
            reviewer: Name of the reviewer.
            alert_rules: List of alert rule names.

        Returns:
            The evaluated QualityGate.
        """
        gate = self._gates[GateType.MONITORING]
        if dashboards_configured and alerts_configured:
            gate.pass_gate(reviewer, {
                "dashboards": dashboards_configured,
                "alerts": alerts_configured,
                "alert_rules": alert_rules or [],
            })
        else:
            failures = []
            if not dashboards_configured:
                failures.append("dashboards not configured")
            if not alerts_configured:
                failures.append("alerts not configured")
            gate.fail_gate(reviewer, "; ".join(failures))

        logger.info("Monitoring gate: %s", gate.status.value)
        return gate

    # ── Gate 6: Rollback Plan ──────────────────────────────────────────────

    def verify_rollback(
        self,
        rollback_plan: Dict[str, Any],
        tested: bool = False,
        reviewer: str = "",
    ) -> QualityGate:
        """Verify that a rollback plan exists and has been tested.

        Args:
            rollback_plan: Dict with rollback steps, triggers, and owners.
            tested: Whether the rollback has been tested.
            reviewer: Name of the reviewer.

        Returns:
            The evaluated QualityGate.
        """
        gate = self._gates[GateType.ROLLBACK_PLAN]
        required = ["steps", "trigger_conditions"]
        missing = [k for k in required if k not in rollback_plan]

        if missing:
            gate.fail_gate(reviewer, f"Missing required fields: {missing}")
        elif not tested:
            gate.fail_gate(reviewer, "Rollback plan not tested")
        else:
            gate.pass_gate(reviewer, {"rollback_plan": rollback_plan, "tested": tested})

        logger.info("Rollback gate: %s", gate.status.value)
        return gate

    # ── Gate 7: Owner Approval ─────────────────────────────────────────────

    def confirm_owner(
        self,
        approved: bool,
        owner: str = "",
        reviewer: str = "",
    ) -> QualityGate:
        """Confirm that the service/component owner has approved.

        Args:
            approved: Whether the owner has approved.
            owner: The owner's name/identifier.
            reviewer: Name of the person recording this confirmation.

        Returns:
            The evaluated QualityGate.
        """
        gate = self._gates[GateType.OWNER_APPROVAL]
        if approved:
            gate.pass_gate(reviewer, {"owner": owner, "approved_at": datetime.utcnow().isoformat()})
        else:
            gate.fail_gate(reviewer, f"Owner {owner} has not approved")
        logger.info("Owner approval gate: %s", gate.status.value)
        return gate

    # ── Gate 8: Change Record ──────────────────────────────────────────────

    def validate_change_record(
        self,
        change_data: Dict[str, Any],
        reviewer: str = "",
    ) -> QualityGate:
        """Validate that the change record is complete and accurate.

        Args:
            change_data: Dict containing change record fields.
            reviewer: Name of the reviewer.

        Returns:
            The evaluated QualityGate.
        """
        gate = self._gates[GateType.CHANGE_RECORD]
        required = ["title", "description", "requester", "risk_level"]
        missing = [k for k in required if not change_data.get(k)]

        if missing:
            gate.fail_gate(reviewer, f"Missing required fields: {missing}")
        else:
            gate.pass_gate(reviewer, {"change_fields_present": list(change_data.keys())})

        logger.info("Change record gate: %s", gate.status.value)
        return gate

    # ── Gate 9: User Impact Assessment ─────────────────────────────────────

    def assess_user_impact(
        self,
        users_affected: int,
        severity: str = "low",
        reviewer: str = "",
        mitigation_plan: Optional[str] = None,
    ) -> QualityGate:
        """Assess user impact of the change.

        Args:
            users_affected: Estimated number of users affected.
            severity: Impact severity ('low', 'medium', 'high', 'critical').
            reviewer: Name of the reviewer.
            mitigation_plan: Description of mitigation measures.

        Returns:
            The evaluated QualityGate.
        """
        gate = self._gates[GateType.USER_IMPACT_ASSESSMENT]
        if severity in ("critical", "high") and not mitigation_plan:
            gate.fail_gate(reviewer, f"{severity} severity impact without mitigation plan")
        else:
            gate.pass_gate(reviewer, {
                "users_affected": users_affected,
                "severity": severity,
                "mitigation_plan": mitigation_plan,
            })

        logger.info("User impact gate: %s", gate.status.value)
        return gate

    # ── Gate 10: Communication Plan ────────────────────────────────────────

    def verify_communication(
        self,
        plan: Dict[str, Any],
        reviewer: str = "",
    ) -> QualityGate:
        """Verify that a communication plan exists for stakeholders.

        Args:
            plan: Dict with keys like 'stakeholders', 'channels', 'schedule', 'message'.
            reviewer: Name of the reviewer.

        Returns:
            The evaluated QualityGate.
        """
        gate = self._gates[GateType.COMMUNICATION_PLAN]
        required = ["stakeholders", "channels"]
        missing = [k for k in required if k not in plan]

        if missing:
            gate.fail_gate(reviewer, f"Missing required sections: {missing}")
        else:
            gate.pass_gate(reviewer, {"communication_plan": plan})

        logger.info("Communication gate: %s", gate.status.value)
        return gate

    # ── Bulk Operations ────────────────────────────────────────────────────

    def run_all_gates(
        self,
        test_results: Dict[str, str],
        security_approved: bool,
        dependencies: Dict[str, str],
        migration_plan: Dict[str, Any],
        dashboards_ok: bool,
        alerts_ok: bool,
        rollback_plan: Dict[str, Any],
        rollback_tested: bool,
        owner_approved: bool,
        owner: str,
        change_data: Dict[str, Any],
        users_affected: int,
        impact_severity: str,
        communication_plan: Dict[str, Any],
        reviewer: str = "auto",
        mitigation_plan: Optional[str] = None,
    ) -> List[QualityGate]:
        """Run all 10 quality gates in sequence.

        Returns:
            List of all evaluated QualityGates.
        """
        self.check_tests_passing(test_results, reviewer)
        self.verify_security(security_approved, reviewer)
        self.verify_dependencies(dependencies, reviewer)
        self.validate_migration(migration_plan, reviewer)
        self.check_monitoring(dashboards_ok, alerts_ok, reviewer)
        self.verify_rollback(rollback_plan, rollback_tested, reviewer)
        self.confirm_owner(owner_approved, owner, reviewer)
        self.validate_change_record(change_data, reviewer)
        self.assess_user_impact(users_affected, impact_severity, reviewer, mitigation_plan)
        self.verify_communication(communication_plan, reviewer)
        return self.get_all_gates()

    def generate_gate_report(self) -> Dict[str, Any]:
        """Generate a comprehensive report of all quality gates.

        Returns:
            Dict with summary and per-gate details.
        """
        gates = self.get_all_gates()
        passed = sum(1 for g in gates if g.status == GateStatus.PASSED)
        failed = sum(1 for g in gates if g.status == GateStatus.FAILED)
        pending = sum(1 for g in gates if g.status == GateStatus.PENDING)
        waived = sum(1 for g in gates if g.status == GateStatus.WAIVED)
        blocking_failed = sum(
            1 for g in gates
            if g.status == GateStatus.FAILED and g.gate_type.is_blocking
        )

        return {
            "summary": {
                "total": len(gates),
                "passed": passed,
                "failed": failed,
                "pending": pending,
                "waived": waived,
                "blocking_failed": blocking_failed,
                "all_passed": failed == 0 and pending == 0,
                "ready_to_proceed": blocking_failed == 0,
            },
            "gates": [g.to_dict() for g in gates],
            "generated_at": datetime.utcnow().isoformat(),
        }

    def get_blocking_failures(self) -> List[QualityGate]:
        """Get all blocking gates that have failed."""
        return [
            g for g in self._gates.values()
            if g.status == GateStatus.FAILED and g.gate_type.is_blocking
        ]

    def all_gates_satisfied(self) -> bool:
        """Check if all gates are either passed or waived."""
        return all(g.status.is_satisfied for g in self._gates.values())