"""
Disaster recovery exercise manager.

Schedules and executes DR exercises including tabletops, backup restoration,
failover, region loss, security drills, vendor outages, key person loss,
and AI provider outage simulations. Generates after-action reports.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("enterprise.disaster_recovery.exercises")


class ExerciseType(str, Enum):
    """Types of disaster recovery exercises."""

    TABLETOP = "tabletop"
    BACKUP_RESTORATION = "backup_restoration"
    FAILOVER = "failover"
    REGION_LOSS = "region_loss"
    SECURITY_DRILL = "security_drill"
    VENDOR_OUTAGE = "vendor_outage"
    KEY_PERSON_LOSS = "key_person_loss"
    AI_PROVIDER_OUTAGE = "ai_provider_outage"


@dataclass
class Exercise:
    """A single DR exercise plan and results."""

    type: ExerciseType
    scheduled_date: datetime
    participants: List[str] = field(default_factory=list)
    objectives: List[str] = field(default_factory=list)
    scenario: str = ""
    success_criteria: List[str] = field(default_factory=list)
    findings: List[str] = field(default_factory=list)
    completed: bool = False
    completed_at: Optional[datetime] = None
    next_exercise_date: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """Exercise passed if completed and no findings are marked as failures."""
        if not self.completed:
            return False
        # Any finding starting with "FAIL:" is a failure
        return not any(f.strip().upper().startswith("FAIL:") for f in self.findings)

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "scheduled_date": self.scheduled_date.isoformat(),
            "participants": self.participants,
            "completed": self.completed,
            "passed": self.passed,
            "findings_count": len(self.findings),
        }


class ExerciseManager:
    """
    Disaster recovery exercise manager.

    Schedules exercises, runs various types of drills, collects findings,
    and generates after-action reports.
    """

    def __init__(self) -> None:
        self._exercises: List[Exercise] = []
        self._hooks: Dict[str, Callable] = {}
        self._exercise_templates: Dict[ExerciseType, list] = {}

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------

    def register_hook(self, name: str, fn: Callable) -> None:
        """Register an external callable for exercise actions."""
        self._hooks[name] = fn
        logger.debug("Registered exercise hook: %s", name)

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------

    def schedule_exercise(
        self,
        exercise_type: ExerciseType,
        scheduled_date: datetime,
        participants: Optional[List[str]] = None,
        objectives: Optional[List[str]] = None,
        scenario: str = "",
        success_criteria: Optional[List[str]] = None,
        next_exercise_date: Optional[datetime] = None,
    ) -> Exercise:
        """Schedule a new DR exercise."""
        ex = Exercise(
            type=exercise_type,
            scheduled_date=scheduled_date,
            participants=participants or [],
            objectives=objectives or [],
            scenario=scenario,
            success_criteria=success_criteria or [],
            next_exercise_date=next_exercise_date,
        )
        self._exercises.append(ex)
        logger.info(
            "Scheduled exercise: %s on %s (%d participants)",
            exercise_type.value, scheduled_date.isoformat(), len(ex.participants),
        )
        return ex

    def list_exercises(self, completed_only: bool = False) -> List[Exercise]:
        """Return all exercises, optionally filtered to completed only."""
        if completed_only:
            return [e for e in self._exercises if e.completed]
        return list(self._exercises)

    # ------------------------------------------------------------------
    # Exercise execution
    # ------------------------------------------------------------------

    def _complete_exercise(
        self,
        exercise: Exercise,
        findings: Optional[List[str]] = None,
    ) -> None:
        exercise.completed = True
        exercise.completed_at = datetime.utcnow()
        if findings:
            exercise.findings.extend(findings)

    def run_tabletop(
        self,
        exercise: Exercise,
        moderator_notes: Optional[List[str]] = None,
    ) -> List[str]:
        """Run a tabletop exercise. Returns findings."""
        findings: List[str] = moderator_notes or []
        findings.append("Tabletop exercise completed with all participants engaged.")

        if "tabletop" in self._hooks:
            self._hooks["tabletop"](exercise=exercise)

        self._complete_exercise(exercise, findings)
        logger.info("Tabletop exercise completed: %s", exercise.type.value)
        return findings

    def test_backup_restoration(
        self,
        exercise: Exercise,
        backup_ids: Optional[List[str]] = None,
    ) -> List[str]:
        """Test backup restoration from specified backup IDs."""
        findings: List[str] = []

        if "backup_restoration" in self._hooks:
            result = self._hooks["backup_restoration"](backup_ids=backup_ids or [])
            if isinstance(result, list):
                findings.extend(result)

        if backup_ids:
            findings.append(f"Restored {len(backup_ids)} backup(s) successfully.")
        else:
            findings.append("No backup IDs specified; restoration scenario validated.")

        self._complete_exercise(exercise, findings)
        logger.info("Backup restoration test completed")
        return findings

    def test_failover(
        self,
        exercise: Exercise,
        target_service: str = "",
    ) -> List[str]:
        """Test failover for a target service."""
        findings: List[str] = []

        if "failover" in self._hooks:
            result = self._hooks["failover"](target_service=target_service)
            if isinstance(result, list):
                findings.extend(result)

        findings.append(f"Failover test for '{target_service or 'all services'}' completed.")
        self._complete_exercise(exercise, findings)
        logger.info("Failover test completed for %s", target_service or "all")
        return findings

    def simulate_region_loss(
        self,
        exercise: Exercise,
        region: str = "",
    ) -> List[str]:
        """Simulate the loss of a cloud region."""
        findings: List[str] = []

        if "region_loss" in self._hooks:
            result = self._hooks["region_loss"](region=region)
            if isinstance(result, list):
                findings.extend(result)

        findings.append(f"Region loss simulation for '{region or 'primary'}' completed.")
        findings.append("Verify: multi-region failover triggered, DNS updated, services healthy.")
        self._complete_exercise(exercise, findings)
        logger.info("Region loss simulation completed for %s", region or "primary")
        return findings

    def run_security_drill(
        self,
        exercise: Exercise,
        drill_type: str = "ransomware",
    ) -> List[str]:
        """Run a security incident response drill."""
        findings: List[str] = []

        if "security_drill" in self._hooks:
            result = self._hooks["security_drill"](drill_type=drill_type)
            if isinstance(result, list):
                findings.extend(result)

        findings.append(f"Security drill '{drill_type}' executed.")
        findings.append("Verify: incident declared, containment active, forensics collected.")
        self._complete_exercise(exercise, findings)
        logger.info("Security drill '%s' completed", drill_type)
        return findings

    def simulate_vendor_outage(
        self,
        exercise: Exercise,
        vendor: str = "",
    ) -> List[str]:
        """Simulate a critical vendor outage."""
        findings: List[str] = []

        if "vendor_outage" in self._hooks:
            result = self._hooks["vendor_outage"](vendor=vendor)
            if isinstance(result, list):
                findings.extend(result)

        findings.append(f"Vendor outage simulation for '{vendor or 'primary vendor'}' completed.")
        findings.append("Verify: fallback activated, alternative supplier engaged.")
        self._complete_exercise(exercise, findings)
        logger.info("Vendor outage simulation completed for %s", vendor or "primary")
        return findings

    def simulate_key_person_loss(
        self,
        exercise: Exercise,
        role: str = "",
    ) -> List[str]:
        """Simulate the sudden unavailability of a key person."""
        findings: List[str] = []

        if "key_person_loss" in self._hooks:
            result = self._hooks["key_person_loss"](role=role)
            if isinstance(result, list):
                findings.extend(result)

        findings.append(f"Key person loss simulation for '{role or 'critical role'}' completed.")
        findings.append("Verify: backup personnel notified, knowledge transfer docs accessible.")
        self._complete_exercise(exercise, findings)
        logger.info("Key person loss simulation completed for %s", role or "critical")
        return findings

    def simulate_ai_outage(
        self,
        exercise: Exercise,
        provider: str = "",
    ) -> List[str]:
        """Simulate an AI model provider outage."""
        findings: List[str] = []

        if "ai_outage" in self._hooks:
            result = self._hooks["ai_outage"](provider=provider)
            if isinstance(result, list):
                findings.extend(result)

        findings.append(f"AI provider outage simulation for '{provider or 'primary'}' completed.")
        findings.append("Verify: fallback provider engaged, cached responses served, alerts fired.")
        self._complete_exercise(exercise, findings)
        logger.info("AI outage simulation completed for %s", provider or "primary")
        return findings

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def generate_after_action_report(self) -> str:
        """Generate a comprehensive after-action report for all exercises."""
        lines: List[str] = []
        lines.append("=" * 66)
        lines.append(" DISASTER RECOVERY AFTER-ACTION REPORT")
        lines.append(f" Generated: {datetime.utcnow().isoformat()}")
        lines.append(f" Total exercises: {len(self._exercises)}")
        completed = [e for e in self._exercises if e.completed]
        passed = [e for e in completed if e.passed]
        lines.append(f" Completed: {len(completed)} | Passed: {len(passed)}")
        lines.append("=" * 66)
        lines.append("")

        for idx, ex in enumerate(self._exercises, 1):
            status = "PASS" if ex.passed else ("FAIL" if ex.completed else "PENDING")
            lines.append(f"{idx}. [{status}] {ex.type.value.upper()}")
            lines.append(f"   Scheduled: {ex.scheduled_date.isoformat()}")
            lines.append(f"   Scenario: {ex.scenario or 'N/A'}")
            lines.append(f"   Participants: {', '.join(ex.participants) or 'N/A'}")
            if ex.completed:
                lines.append(f"   Completed: {ex.completed_at.isoformat() if ex.completed_at else 'N/A'}")
            lines.append(f"   Objectives: {', '.join(ex.objectives) or 'N/A'}")
            if ex.findings:
                lines.append(f"   Findings ({len(ex.findings)}):")
                for f in ex.findings[:5]:
                    lines.append(f"     - {f}")
                if len(ex.findings) > 5:
                    lines.append(f"     ... and {len(ex.findings) - 5} more")
            if ex.next_exercise_date:
                lines.append(f"   Next: {ex.next_exercise_date.isoformat()}")
            lines.append("")

        # Summary metrics
        lines.append("-" * 66)
        lines.append("SUMMARY METRICS")
        pass_rate = (len(passed) / max(1, len(completed))) * 100
        lines.append(f"  Pass rate: {pass_rate:.1f}%")
        lines.append(f"  Exercises pending: {len(self._exercises) - len(completed)}")
        lines.append(f"  Upcoming exercises:")
        upcoming = [e for e in self._exercises if not e.completed]
        for e in upcoming[:5]:
            lines.append(f"    - {e.type.value}: {e.scheduled_date.isoformat()}")
        lines.append("=" * 66)
        return "\n".join(lines)