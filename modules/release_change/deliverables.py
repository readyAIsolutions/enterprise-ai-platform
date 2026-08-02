"""
Release Deliverables Manager

Creates, manages, and archives the 10 types of deliverables required
for a compliant release and change management process.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("enterprise.release_change")


class DeliverableType(str, Enum):
    """Types of release/change deliverables."""
    RELEASE_PLAN = "release_plan"
    CHANGE_RECORD = "change_record"
    RISK_CLASSIFICATION = "risk_classification"
    TESTING_EVIDENCE = "testing_evidence"
    APPROVAL_RECORD = "approval_record"
    DEPLOYMENT_CHECKLIST = "deployment_checklist"
    ROLLBACK_PROCEDURE = "rollback_procedure"
    MONITORING_PLAN = "monitoring_plan"
    RELEASE_NOTES = "release_notes"
    POST_RELEASE_REPORT = "post_release_report"

    @property
    def required_for_compliance(self) -> bool:
        """Whether this deliverable is required for compliance."""
        return self in (
            DeliverableType.CHANGE_RECORD, DeliverableType.RISK_CLASSIFICATION,
            DeliverableType.APPROVAL_RECORD, DeliverableType.ROLLBACK_PROCEDURE,
            DeliverableType.POST_RELEASE_REPORT,
        )

    @property
    def default_filename(self) -> str:
        """Suggested filename for this deliverable type."""
        return {
            DeliverableType.RELEASE_PLAN: "release_plan.json",
            DeliverableType.CHANGE_RECORD: "change_record.json",
            DeliverableType.RISK_CLASSIFICATION: "risk_classification.json",
            DeliverableType.TESTING_EVIDENCE: "testing_evidence.json",
            DeliverableType.APPROVAL_RECORD: "approval_record.json",
            DeliverableType.DEPLOYMENT_CHECKLIST: "deployment_checklist.json",
            DeliverableType.ROLLBACK_PROCEDURE: "rollback_procedure.json",
            DeliverableType.MONITORING_PLAN: "monitoring_plan.json",
            DeliverableType.RELEASE_NOTES: "release_notes.md",
            DeliverableType.POST_RELEASE_REPORT: "post_release_report.json",
        }.get(self, "deliverable.json")


@dataclass
class Deliverable:
    """Represents a single release/change deliverable document.

    Attributes:
        deliverable_type: The type of deliverable.
        content: The content of the deliverable (dict or string).
        author: Who created the deliverable.
        created_at: When the deliverable was created.
        reviewed_by: Who reviewed the deliverable.
        approved: Whether the deliverable has been approved.
        version: Version number of the deliverable.
        storage_path: Filesystem path where the deliverable is stored.
        metadata: Additional metadata.
    """
    deliverable_type: DeliverableType
    content: Any = field(default_factory=dict)
    author: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    reviewed_by: str = ""
    approved: bool = False
    version: str = "1.0"
    storage_path: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the deliverable to a dictionary."""
        return {
            "deliverable_type": self.deliverable_type.value,
            "content": self.content,
            "author": self.author,
            "created_at": self.created_at,
            "reviewed_by": self.reviewed_by,
            "approved": self.approved,
            "version": self.version,
            "storage_path": self.storage_path,
            "metadata": self.metadata,
        }

    def approve(self, reviewer: str) -> None:
        """Approve the deliverable."""
        self.approved = True
        self.reviewed_by = reviewer
        logger.info("Deliverable %s approved by %s", self.deliverable_type.value, reviewer)

    def reject(self, reviewer: str, reason: str = "") -> None:
        """Reject the deliverable."""
        self.approved = False
        self.reviewed_by = reviewer
        self.metadata["rejection_reason"] = reason
        logger.warning("Deliverable %s rejected by %s: %s", self.deliverable_type.value, reviewer, reason)


class DeliverableManager:
    """Manager for creating, storing, and archiving release deliverables.

    Usage:
        mgr = DeliverableManager(storage_dir="/var/releases")
        plan = mgr.create_release_plan("My Release", {"version": "1.2.3"})
        mgr.archive_deliverables("/archive/releases/2024-q1/")
    """

    def __init__(self, storage_dir: str = "/tmp/enterprise_deliverables") -> None:
        self.storage_dir = storage_dir
        self._deliverables: Dict[str, Deliverable] = {}
        os.makedirs(self.storage_dir, exist_ok=True)

    def _save(self, deliverable: Deliverable) -> None:
        """Persist a deliverable to disk."""
        if not deliverable.storage_path:
            filename = f"{deliverable.deliverable_type.value}_{deliverable.created_at.replace(':', '-')}.json"
            deliverable.storage_path = os.path.join(self.storage_dir, filename)
        try:
            with open(deliverable.storage_path, "w") as f:
                json.dump(deliverable.to_dict(), f, indent=2, default=str)
            logger.debug("Saved deliverable to %s", deliverable.storage_path)
        except (IOError, OSError) as e:
            logger.error("Failed to save deliverable %s: %s", deliverable.deliverable_type.value, e)

    def _register(self, deliverable: Deliverable) -> Deliverable:
        """Register and persist a deliverable."""
        key = f"{deliverable.deliverable_type.value}_{deliverable.created_at}"
        self._deliverables[key] = deliverable
        self._save(deliverable)
        return deliverable

    # ── Deliverable 1: Release Plan ────────────────────────────────────────

    def create_release_plan(
        self,
        release_name: str,
        version: str,
        author: str = "",
        schedule: Optional[Dict[str, Any]] = None,
        scope: Optional[List[str]] = None,
        stakeholders: Optional[List[str]] = None,
        risks: Optional[List[str]] = None,
    ) -> Deliverable:
        """Create a release plan deliverable.

        Args:
            release_name: Name of the release.
            version: Version string.
            author: Author of the plan.
            schedule: Deployment schedule details.
            scope: Items in scope for this release.
            stakeholders: Key stakeholders.
            risks: Identified risks.

        Returns:
            The created Deliverable.
        """
        content = {
            "release_name": release_name,
            "version": version,
            "schedule": schedule or {},
            "scope": scope or [],
            "stakeholders": stakeholders or [],
            "risks": risks or [],
        }
        deliverable = Deliverable(
            deliverable_type=DeliverableType.RELEASE_PLAN,
            content=content,
            author=author,
            version=version,
        )
        deliverable = self._register(deliverable)
        logger.info("Created release plan for %s v%s", release_name, version)
        return deliverable

    # ── Deliverable 2: Change Record ───────────────────────────────────────

    def generate_change_record(
        self,
        change_id: str,
        title: str,
        description: str,
        author: str = "",
        requester: str = "",
        risk_level: str = "",
        affected_systems: Optional[List[str]] = None,
        status: str = "open",
    ) -> Deliverable:
        """Generate a change record deliverable.

        Args:
            change_id: Unique change identifier.
            title: Change title.
            description: Change description.
            author: Author of the record.
            requester: Who requested the change.
            risk_level: Assessed risk level.
            affected_systems: Systems affected.
            status: Current status.

        Returns:
            The created Deliverable.
        """
        content = {
            "change_id": change_id,
            "title": title,
            "description": description,
            "requester": requester,
            "risk_level": risk_level,
            "affected_systems": affected_systems or [],
            "status": status,
        }
        deliverable = Deliverable(
            deliverable_type=DeliverableType.CHANGE_RECORD,
            content=content,
            author=author,
        )
        deliverable = self._register(deliverable)
        logger.info("Generated change record for %s", change_id)
        return deliverable

    # ── Deliverable 3: Risk Classification ─────────────────────────────────

    def document_risk(
        self,
        change_id: str,
        risk_level: str,
        author: str = "",
        risk_factors: Optional[Dict[str, Any]] = None,
        mitigation: Optional[List[str]] = None,
    ) -> Deliverable:
        """Document the risk classification for a change.

        Args:
            change_id: Associated change ID.
            risk_level: Assessed risk level.
            author: Author of the classification.
            risk_factors: Factors considered in risk assessment.
            mitigation: Proposed mitigation measures.

        Returns:
            The created Deliverable.
        """
        content = {
            "change_id": change_id,
            "risk_level": risk_level,
            "risk_factors": risk_factors or {},
            "mitigation": mitigation or [],
            "classified_at": datetime.utcnow().isoformat(),
        }
        deliverable = Deliverable(
            deliverable_type=DeliverableType.RISK_CLASSIFICATION,
            content=content,
            author=author,
        )
        deliverable = self._register(deliverable)
        logger.info("Documented risk for %s: %s", change_id, risk_level)
        return deliverable

    # ── Deliverable 4: Testing Evidence ────────────────────────────────────

    def collect_testing_evidence(
        self,
        change_id: str,
        test_results: Dict[str, Any],
        author: str = "",
        test_types: Optional[List[str]] = None,
        coverage_percent: float = 0.0,
    ) -> Deliverable:
        """Collect and document testing evidence.

        Args:
            change_id: Associated change ID.
            test_results: Results from testing.
            author: Author.
            test_types: Types of tests executed.
            coverage_percent: Code coverage percentage.

        Returns:
            The created Deliverable.
        """
        content = {
            "change_id": change_id,
            "test_results": test_results,
            "test_types": test_types or [],
            "coverage_percent": coverage_percent,
            "all_passed": all(
                v in ("pass", "passed") for v in test_results.values()
            ) if test_results else True,
            "tested_at": datetime.utcnow().isoformat(),
        }
        deliverable = Deliverable(
            deliverable_type=DeliverableType.TESTING_EVIDENCE,
            content=content,
            author=author,
        )
        deliverable = self._register(deliverable)
        logger.info("Collected testing evidence for %s", change_id)
        return deliverable

    # ── Deliverable 5: Approval Record ─────────────────────────────────────

    def record_approvals(
        self,
        change_id: str,
        approvals: List[Dict[str, str]],
        author: str = "",
        required_count: int = 1,
    ) -> Deliverable:
        """Record approvals for a change.

        Args:
            change_id: Associated change ID.
            approvals: List of approval records (each with 'name', 'role', 'status').
            author: Author.
            required_count: Number of approvals required.

        Returns:
            The created Deliverable.
        """
        approved_count = sum(1 for a in approvals if a.get("status") == "approved")
        content = {
            "change_id": change_id,
            "approvals": approvals,
            "approved_count": approved_count,
            "required_count": required_count,
            "sufficient": approved_count >= required_count,
        }
        deliverable = Deliverable(
            deliverable_type=DeliverableType.APPROVAL_RECORD,
            content=content,
            author=author,
        )
        deliverable = self._register(deliverable)
        logger.info("Recorded %d approvals for %s (need %d)", approved_count, change_id, required_count)
        return deliverable

    # ── Deliverable 6: Deployment Checklist ────────────────────────────────

    def generate_checklist(
        self,
        change_id: str,
        items: Optional[List[Dict[str, Any]]] = None,
        author: str = "",
    ) -> Deliverable:
        """Generate a deployment checklist.

        Each item is a dict with 'task', 'completed', 'assigned_to'.

        Args:
            change_id: Associated change ID.
            items: List of checklist items.
            author: Author.

        Returns:
            The created Deliverable.
        """
        items = items or []
        completed = sum(1 for i in items if i.get("completed", False))
        total = len(items)
        content = {
            "change_id": change_id,
            "items": items,
            "completed": completed,
            "total": total,
            "progress_percent": (completed / total * 100) if total > 0 else 0,
        }
        deliverable = Deliverable(
            deliverable_type=DeliverableType.DEPLOYMENT_CHECKLIST,
            content=content,
            author=author,
        )
        deliverable = self._register(deliverable)
        logger.info("Generated checklist for %s (%d/%d)", change_id, completed, total)
        return deliverable

    # ── Deliverable 7: Rollback Procedure ──────────────────────────────────

    def document_rollback(
        self,
        change_id: str,
        steps: List[str],
        author: str = "",
        trigger_conditions: Optional[List[str]] = None,
        estimated_time_minutes: int = 30,
        responsible_team: str = "",
    ) -> Deliverable:
        """Document the rollback procedure.

        Args:
            change_id: Associated change ID.
            steps: Ordered list of rollback steps.
            author: Author.
            trigger_conditions: Conditions that trigger rollback.
            estimated_time_minutes: Estimated time to complete rollback.
            responsible_team: Team responsible for executing rollback.

        Returns:
            The created Deliverable.
        """
        content = {
            "change_id": change_id,
            "steps": steps,
            "step_count": len(steps),
            "trigger_conditions": trigger_conditions or [],
            "estimated_time_minutes": estimated_time_minutes,
            "responsible_team": responsible_team,
        }
        deliverable = Deliverable(
            deliverable_type=DeliverableType.ROLLBACK_PROCEDURE,
            content=content,
            author=author,
        )
        deliverable = self._register(deliverable)
        logger.info("Documented rollback for %s (%d steps)", change_id, len(steps))
        return deliverable

    # ── Deliverable 8: Monitoring Plan ─────────────────────────────────────

    def create_monitoring_plan(
        self,
        change_id: str,
        metrics: List[str],
        author: str = "",
        alert_rules: Optional[List[Dict[str, Any]]] = None,
        dashboards: Optional[List[str]] = None,
        observation_period_minutes: int = 60,
    ) -> Deliverable:
        """Create a monitoring plan for the deployment.

        Args:
            change_id: Associated change ID.
            metrics: List of metrics to monitor.
            author: Author.
            alert_rules: Alert configurations.
            dashboards: Dashboard URLs or names.
            observation_period_minutes: How long to observe post-deployment.

        Returns:
            The created Deliverable.
        """
        content = {
            "change_id": change_id,
            "metrics": metrics,
            "alert_rules": alert_rules or [],
            "dashboards": dashboards or [],
            "observation_period_minutes": observation_period_minutes,
            "plan_created_at": datetime.utcnow().isoformat(),
        }
        deliverable = Deliverable(
            deliverable_type=DeliverableType.MONITORING_PLAN,
            content=content,
            author=author,
        )
        deliverable = self._register(deliverable)
        logger.info("Created monitoring plan for %s", change_id)
        return deliverable

    # ── Deliverable 9: Release Notes ───────────────────────────────────────

    def generate_release_notes(
        self,
        release_name: str,
        version: str,
        author: str = "",
        features: Optional[List[str]] = None,
        fixes: Optional[List[str]] = None,
        breaking_changes: Optional[List[str]] = None,
        known_issues: Optional[List[str]] = None,
        upgrade_instructions: str = "",
    ) -> Deliverable:
        """Generate release notes.

        Args:
            release_name: Name of the release.
            version: Version string.
            author: Author.
            features: New features.
            fixes: Bug fixes.
            breaking_changes: Breaking changes.
            known_issues: Known issues.
            upgrade_instructions: Instructions for upgrading.

        Returns:
            The created Deliverable.
        """
        content = {
            "release_name": release_name,
            "version": version,
            "features": features or [],
            "fixes": fixes or [],
            "breaking_changes": breaking_changes or [],
            "known_issues": known_issues or [],
            "upgrade_instructions": upgrade_instructions,
            "released_at": datetime.utcnow().isoformat(),
        }
        deliverable = Deliverable(
            deliverable_type=DeliverableType.RELEASE_NOTES,
            content=content,
            author=author,
            version=version,
        )
        deliverable = self._register(deliverable)
        logger.info("Generated release notes for %s v%s", release_name, version)
        return deliverable

    # ── Deliverable 10: Post-Release Report ────────────────────────────────

    def compile_post_release_report(
        self,
        change_id: str,
        author: str = "",
        deployment_result: str = "success",
        incident_count: int = 0,
        user_feedback: str = "",
        metrics_summary: Optional[Dict[str, Any]] = None,
        lessons_learned: Optional[List[str]] = None,
    ) -> Deliverable:
        """Compile a post-release report.

        Args:
            change_id: Associated change ID.
            author: Author.
            deployment_result: Overall result ('success', 'partial', 'failure').
            incident_count: Number of incidents during/after release.
            user_feedback: User feedback summary.
            metrics_summary: Key metrics from the release.
            lessons_learned: Lessons learned.

        Returns:
            The created Deliverable.
        """
        content = {
            "change_id": change_id,
            "deployment_result": deployment_result,
            "incident_count": incident_count,
            "user_feedback": user_feedback,
            "metrics_summary": metrics_summary or {},
            "lessons_learned": lessons_learned or [],
            "report_compiled_at": datetime.utcnow().isoformat(),
        }
        deliverable = Deliverable(
            deliverable_type=DeliverableType.POST_RELEASE_REPORT,
            content=content,
            author=author,
        )
        deliverable = self._register(deliverable)
        logger.info("Compiled post-release report for %s", change_id)
        return deliverable

    # ── Bulk Operations ────────────────────────────────────────────────────

    def archive_deliverables(self, archive_path: str) -> Dict[str, Any]:
        """Archive all deliverables to a specified path.

        Creates a combined archive file containing all deliverables.

        Args:
            archive_path: Path to write the archive.

        Returns:
            Dict with archive details.
        """
        os.makedirs(os.path.dirname(archive_path) or ".", exist_ok=True)
        archive_data = {
            "archive_created_at": datetime.utcnow().isoformat(),
            "deliverable_count": len(self._deliverables),
            "deliverables": [
                d.to_dict() for d in self._deliverables.values()
            ],
        }
        try:
            with open(archive_path, "w") as f:
                json.dump(archive_data, f, indent=2, default=str)
            logger.info("Archived %d deliverables to %s", len(self._deliverables), archive_path)
        except (IOError, OSError) as e:
            logger.error("Failed to archive deliverables: %s", e)
            return {"success": False, "error": str(e)}

        return {
            "success": True,
            "archive_path": archive_path,
            "deliverable_count": len(self._deliverables),
            "archived_at": archive_data["archive_created_at"],
        }

    def get_deliverable(self, deliverable_type: DeliverableType) -> Optional[Deliverable]:
        """Get the most recent deliverable of a given type."""
        matching = [
            d for d in self._deliverables.values()
            if d.deliverable_type == deliverable_type
        ]
        if not matching:
            return None
        return sorted(matching, key=lambda d: d.created_at, reverse=True)[0]

    def list_deliverables(
        self,
        deliverable_type: Optional[DeliverableType] = None,
        approved_only: bool = False,
    ) -> List[Deliverable]:
        """List deliverables, optionally filtered by type and approval status."""
        results = list(self._deliverables.values())
        if deliverable_type:
            results = [d for d in results if d.deliverable_type == deliverable_type]
        if approved_only:
            results = [d for d in results if d.approved]
        return sorted(results, key=lambda d: d.created_at, reverse=True)

    def get_compliance_status(self) -> Dict[str, Any]:
        """Check compliance status across all required deliverables."""
        required_types = [dt for dt in DeliverableType if dt.required_for_compliance]
        status = {}
        all_present = True
        for dt in required_types:
            latest = self.get_deliverable(dt)
            status[dt.value] = {
                "exists": latest is not None,
                "approved": latest.approved if latest else False,
            }
            if not latest or not latest.approved:
                all_present = False
        return {
            "compliant": all_present,
            "deliverables": status,
            "checked_at": datetime.utcnow().isoformat(),
        }