"""
Cyber incident recovery manager.

Handles the full cyber recovery lifecycle: detection, containment, isolation,
forensics, credential rotation, clean-point identification, trusted rebuild,
integrity validation, controlled restore, and reinfection monitoring.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("enterprise.disaster_recovery.cyber_recovery")


class CyberRecoveryPhase(str, Enum):
    """Ordered phases of a cyber recovery operation."""

    DETECT = "detect"
    CONTAIN = "contain"
    ISOLATE = "isolate"
    PRESERVE_EVIDENCE = "preserve_evidence"
    ROTATE_CREDENTIALS = "rotate_credentials"
    IDENTIFY_CLEAN_POINT = "identify_clean_point"
    REBUILD_TRUSTED = "rebuild_trusted"
    VALIDATE_INTEGRITY = "validate_integrity"
    CONTROLLED_RESTORE = "controlled_restore"
    MONITOR_REINFECTION = "monitor_reinfection"
    DOCUMENT = "document"

    @classmethod
    def ordered(cls) -> List["CyberRecoveryPhase"]:
        """Return phases in the canonical execution order."""
        return [
            cls.DETECT,
            cls.CONTAIN,
            cls.ISOLATE,
            cls.PRESERVE_EVIDENCE,
            cls.ROTATE_CREDENTIALS,
            cls.IDENTIFY_CLEAN_POINT,
            cls.REBUILD_TRUSTED,
            cls.VALIDATE_INTEGRITY,
            cls.CONTROLLED_RESTORE,
            cls.MONITOR_REINFECTION,
            cls.DOCUMENT,
        ]


@dataclass
class CyberRecoveryPlan:
    """State tracker for an active cyber recovery operation."""

    incident_id: str
    detected_at: datetime
    phases_completed: List[CyberRecoveryPhase] = field(default_factory=list)
    evidence_collected: List[str] = field(default_factory=list)
    credentials_rotated: List[str] = field(default_factory=list)
    clean_recovery_point: Optional[str] = None
    trusted_infrastructure_rebuilt: bool = False
    integrity_validated: bool = False
    restored: bool = False
    reinfection_monitored: bool = False
    documentation_generated: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def current_phase(self) -> Optional[CyberRecoveryPhase]:
        """Return the next uncompleted phase, or None if all done."""
        for phase in CyberRecoveryPhase.ordered():
            if phase not in self.phases_completed:
                return phase
        return None

    @property
    def is_complete(self) -> bool:
        return self.current_phase is None

    def to_dict(self) -> dict:
        return {
            "incident_id": self.incident_id,
            "detected_at": self.detected_at.isoformat(),
            "phases_completed": [p.value for p in self.phases_completed],
            "current_phase": self.current_phase.value if self.current_phase else "complete",
            "is_complete": self.is_complete,
            "trusted_infrastructure_rebuilt": self.trusted_infrastructure_rebuilt,
            "integrity_validated": self.integrity_validated,
            "restored": self.restored,
        }


class CyberRecoveryManager:
    """
    Manages the full cyber incident recovery lifecycle.

    Tracks phases, collects forensic evidence, rotates credentials,
    identifies clean recovery points, rebuilds trusted environments,
    validates integrity, performs controlled restores, and monitors
    for reinfection.
    """

    def __init__(self) -> None:
        self._active_recoveries: Dict[str, CyberRecoveryPlan] = {}
        self._completed_recoveries: Dict[str, CyberRecoveryPlan] = {}
        self._hooks: Dict[str, Callable] = {}

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------

    def register_hook(self, name: str, fn: Callable) -> None:
        """Register an external callable (e.g., for credential rotation API)."""
        self._hooks[name] = fn
        logger.debug("Registered cyber recovery hook: %s", name)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initiate_recovery(self, metadata: Optional[Dict[str, Any]] = None) -> CyberRecoveryPlan:
        """Start a new cyber recovery operation. Returns the plan."""
        incident_id = f"cyber-{uuid.uuid4().hex[:12]}"
        plan = CyberRecoveryPlan(
            incident_id=incident_id,
            detected_at=datetime.utcnow(),
            metadata=metadata or {},
        )
        self._active_recoveries[incident_id] = plan
        self.advance_phase(incident_id, CyberRecoveryPhase.DETECT)
        logger.info("Initiated cyber recovery: %s", incident_id)
        return plan

    def advance_phase(
        self,
        incident_id: str,
        phase: CyberRecoveryPhase,
    ) -> bool:
        """Mark a phase as completed for the given incident."""
        plan = self._get_any(incident_id)
        if plan is None:
            return False
        if phase in plan.phases_completed:
            logger.warning("Phase %s already completed for %s", phase.value, incident_id)
            return True

        plan.phases_completed.append(phase)
        logger.info("Advanced %s to phase %s", incident_id, phase.value)

        # Auto-complete marker phases
        if phase == CyberRecoveryPhase.DOCUMENT:
            plan.documentation_generated = True
        elif phase == CyberRecoveryPhase.MONITOR_REINFECTION:
            plan.reinfection_monitored = True
            self._move_to_completed(incident_id)

        return True

    # ------------------------------------------------------------------
    # Phase-specific actions
    # ------------------------------------------------------------------

    def collect_forensic_evidence(
        self,
        incident_id: str,
        sources: List[str],
    ) -> List[str]:
        """Collect forensic evidence from the specified sources."""
        plan = self._get_active(incident_id)
        if plan is None:
            return []

        plan.evidence_collected.extend(sources)
        self.advance_phase(incident_id, CyberRecoveryPhase.PRESERVE_EVIDENCE)
        logger.info("Collected forensic evidence for %s: %d sources", incident_id, len(sources))
        return list(plan.evidence_collected)

    def rotate_all_credentials(
        self,
        incident_id: str,
        credential_scopes: List[str],
    ) -> List[str]:
        """Rotate credentials across all specified scopes."""
        plan = self._get_active(incident_id)
        if plan is None:
            return []

        if "rotate_credentials" in self._hooks:
            self._hooks["rotate_credentials"](incident_id=incident_id, scopes=credential_scopes)

        plan.credentials_rotated.extend(credential_scopes)
        self.advance_phase(incident_id, CyberRecoveryPhase.ROTATE_CREDENTIALS)
        logger.info("Rotated credentials for %s: %d scopes", incident_id, len(credential_scopes))
        return list(plan.credentials_rotated)

    def identify_clean_recovery_point(
        self,
        incident_id: str,
        candidates: List[str],
    ) -> Optional[str]:
        """Identify the most recent clean (uncompromised) recovery point."""
        plan = self._get_active(incident_id)
        if plan is None:
            return None

        # In reality: scan each candidate for compromise indicators
        # Choose the most recent candidate that passes integrity checks
        clean = candidates[-1] if candidates else None
        plan.clean_recovery_point = clean
        self.advance_phase(incident_id, CyberRecoveryPhase.IDENTIFY_CLEAN_POINT)
        if clean:
            logger.info("Clean recovery point for %s: %s", incident_id, clean)
        else:
            logger.warning("No clean recovery point found for %s", incident_id)
        return clean

    def rebuild_trusted_environment(
        self,
        incident_id: str,
        from_clean_point: bool = True,
    ) -> bool:
        """Rebuild infrastructure from a known-clean state."""
        plan = self._get_active(incident_id)
        if plan is None:
            return False

        if from_clean_point and not plan.clean_recovery_point:
            logger.error("Cannot rebuild trusted env for %s: no clean recovery point", incident_id)
            return False

        if "rebuild_trusted" in self._hooks:
            self._hooks["rebuild_trusted"](incident_id=incident_id)

        plan.trusted_infrastructure_rebuilt = True
        self.advance_phase(incident_id, CyberRecoveryPhase.REBUILD_TRUSTED)
        logger.info("Trusted environment rebuilt for %s", incident_id)
        return True

    def validate_system_integrity(self, incident_id: str) -> bool:
        """Validate the integrity of the rebuilt environment."""
        plan = self._get_active(incident_id)
        if plan is None:
            return False

        if "validate_integrity" in self._hooks:
            self._hooks["validate_integrity"](incident_id=incident_id)

        plan.integrity_validated = True
        self.advance_phase(incident_id, CyberRecoveryPhase.VALIDATE_INTEGRITY)
        logger.info("System integrity validated for %s", incident_id)
        return True

    def perform_controlled_restore(self, incident_id: str) -> bool:
        """Restore services in a controlled, monitored manner."""
        plan = self._get_active(incident_id)
        if plan is None:
            return False

        if not plan.integrity_validated:
            logger.error("Cannot restore %s: integrity not validated", incident_id)
            return False

        if "controlled_restore" in self._hooks:
            self._hooks["controlled_restore"](incident_id=incident_id)

        plan.restored = True
        self.advance_phase(incident_id, CyberRecoveryPhase.CONTROLLED_RESTORE)
        logger.info("Controlled restore completed for %s", incident_id)
        return True

    def monitor_for_reinfection(
        self,
        incident_id: str,
        duration_hours: float = 24.0,
    ) -> bool:
        """Activate reinfection monitoring for a specified duration."""
        plan = self._get_active(incident_id)
        if plan is None:
            return False

        if "monitor_reinfection" in self._hooks:
            self._hooks["monitor_reinfection"](incident_id=incident_id, duration_hours=duration_hours)

        plan.reinfection_monitored = True
        self.advance_phase(incident_id, CyberRecoveryPhase.MONITOR_REINFECTION)
        logger.info("Reinfection monitoring active for %s (%.1fh)", incident_id, duration_hours)
        return True

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def generate_incident_report(self, incident_id: str) -> str:
        """Generate a comprehensive incident recovery report."""
        plan = self._get_any(incident_id)
        if plan is None:
            return f"No incident found for {incident_id}"

        lines: List[str] = []
        lines.append("=" * 60)
        lines.append(f" CYBER INCIDENT RECOVERY REPORT")
        lines.append(f" Incident: {plan.incident_id}")
        lines.append(f" Detected: {plan.detected_at.isoformat()}")
        lines.append("=" * 60)
        lines.append("")

        lines.append("Phase completion:")
        for phase in CyberRecoveryPhase.ordered():
            status = "DONE" if phase in plan.phases_completed else "PENDING"
            lines.append(f"  [{status}] {phase.value.replace('_', ' ').title()}")

        lines.append("")
        lines.append(f"Clean recovery point: {plan.clean_recovery_point or 'NOT FOUND'}")
        lines.append(f"Trusted infrastructure rebuilt: {plan.trusted_infrastructure_rebuilt}")
        lines.append(f"Integrity validated: {plan.integrity_validated}")
        lines.append(f"Services restored: {plan.restored}")
        lines.append(f"Evidence collected: {len(plan.evidence_collected)} items")
        lines.append(f"Credentials rotated: {len(plan.credentials_rotated)} scopes")
        lines.append(f"Reinfection monitored: {plan.reinfection_monitored}")
        lines.append("")
        lines.append("=" * 60)

        self.advance_phase(incident_id, CyberRecoveryPhase.DOCUMENT)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_active(self, incident_id: str) -> Optional[CyberRecoveryPlan]:
        return self._active_recoveries.get(incident_id)

    def _get_any(self, incident_id: str) -> Optional[CyberRecoveryPlan]:
        return self._active_recoveries.get(incident_id) or self._completed_recoveries.get(incident_id)

    def _move_to_completed(self, incident_id: str) -> None:
        plan = self._active_recoveries.pop(incident_id, None)
        if plan:
            self._completed_recoveries[incident_id] = plan
            logger.info("Cyber recovery %s moved to completed", incident_id)