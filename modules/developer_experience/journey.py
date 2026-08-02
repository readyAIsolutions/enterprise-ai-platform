"""
Developer Journey
=================
Models and manages the end-to-end developer lifecycle journey from
onboarding through offboarding. Each stage has defined entry/exit
criteria, dependencies, duration expectations, and owners.

Journey Stages:
    1.  Access Request
    2.  Account Setup
    3.  Local Environment Setup
    4.  Repository Discovery
    5.  Project Understanding
    6.  Dependency Installation
    7.  Development
    8.  Testing
    9.  Debugging
    10. Code Review
    11. Security Review
    12. Deployment
    13. Monitoring
    14. Incident Response
    15. Documentation
    16. Offboarding
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set
import json
import logging
import threading

logger = logging.getLogger(__name__)


class JourneyStage(Enum):
    """All stages in the developer journey lifecycle."""
    ACCESS_REQUEST = "access_request"
    ACCOUNT_SETUP = "account_setup"
    LOCAL_ENV_SETUP = "local_env_setup"
    REPO_DISCOVERY = "repo_discovery"
    PROJECT_UNDERSTANDING = "project_understanding"
    DEPS_INSTALLATION = "deps_installation"
    DEVELOPMENT = "development"
    TESTING = "testing"
    DEBUGGING = "debugging"
    CODE_REVIEW = "code_review"
    SECURITY_REVIEW = "security_review"
    DEPLOYMENT = "deployment"
    MONITORING = "monitoring"
    INCIDENT_RESPONSE = "incident_response"
    DOCUMENTATION = "documentation"
    OFFBOARDING = "offboarding"


class JourneyStageStatus(Enum):
    """Status of a journey stage."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    SKIPPED = "skipped"


# Journey stage ordering and dependencies
STAGE_ORDER: List[JourneyStage] = [
    JourneyStage.ACCESS_REQUEST,
    JourneyStage.ACCOUNT_SETUP,
    JourneyStage.LOCAL_ENV_SETUP,
    JourneyStage.REPO_DISCOVERY,
    JourneyStage.PROJECT_UNDERSTANDING,
    JourneyStage.DEPS_INSTALLATION,
    JourneyStage.DEVELOPMENT,
    JourneyStage.TESTING,
    JourneyStage.DEBUGGING,
    JourneyStage.CODE_REVIEW,
    JourneyStage.SECURITY_REVIEW,
    JourneyStage.DEPLOYMENT,
    JourneyStage.MONITORING,
    JourneyStage.INCIDENT_RESPONSE,
    JourneyStage.DOCUMENTATION,
    JourneyStage.OFFBOARDING,
]

STAGE_DEPENDENCIES: Dict[JourneyStage, List[JourneyStage]] = {
    JourneyStage.ACCOUNT_SETUP: [JourneyStage.ACCESS_REQUEST],
    JourneyStage.LOCAL_ENV_SETUP: [JourneyStage.ACCOUNT_SETUP],
    JourneyStage.REPO_DISCOVERY: [JourneyStage.ACCOUNT_SETUP],
    JourneyStage.PROJECT_UNDERSTANDING: [JourneyStage.REPO_DISCOVERY],
    JourneyStage.DEPS_INSTALLATION: [JourneyStage.LOCAL_ENV_SETUP, JourneyStage.REPO_DISCOVERY],
    JourneyStage.DEVELOPMENT: [JourneyStage.DEPS_INSTALLATION, JourneyStage.PROJECT_UNDERSTANDING],
    JourneyStage.TESTING: [JourneyStage.DEVELOPMENT],
    JourneyStage.DEBUGGING: [JourneyStage.DEVELOPMENT],
    JourneyStage.CODE_REVIEW: [JourneyStage.TESTING],
    JourneyStage.SECURITY_REVIEW: [JourneyStage.CODE_REVIEW],
    JourneyStage.DEPLOYMENT: [JourneyStage.CODE_REVIEW, JourneyStage.SECURITY_REVIEW],
    JourneyStage.MONITORING: [JourneyStage.DEPLOYMENT],
    JourneyStage.INCIDENT_RESPONSE: [JourneyStage.MONITORING],
    JourneyStage.DOCUMENTATION: [JourneyStage.DEVELOPMENT],
    JourneyStage.OFFBOARDING: [],  # Can happen from any stage
}

STAGE_DURATION_TARGETS: Dict[JourneyStage, timedelta] = {
    JourneyStage.ACCESS_REQUEST: timedelta(hours=4),
    JourneyStage.ACCOUNT_SETUP: timedelta(hours=8),
    JourneyStage.LOCAL_ENV_SETUP: timedelta(hours=4),
    JourneyStage.REPO_DISCOVERY: timedelta(hours=2),
    JourneyStage.PROJECT_UNDERSTANDING: timedelta(days=3),
    JourneyStage.DEPS_INSTALLATION: timedelta(hours=2),
    JourneyStage.DEVELOPMENT: timedelta(hours=0),  # Ongoing
    JourneyStage.TESTING: timedelta(hours=0),       # Ongoing
    JourneyStage.DEBUGGING: timedelta(hours=0),     # Ongoing
    JourneyStage.CODE_REVIEW: timedelta(hours=4),
    JourneyStage.SECURITY_REVIEW: timedelta(hours=8),
    JourneyStage.DEPLOYMENT: timedelta(hours=2),
    JourneyStage.MONITORING: timedelta(hours=0),    # Ongoing
    JourneyStage.INCIDENT_RESPONSE: timedelta(hours=1),
    JourneyStage.DOCUMENTATION: timedelta(hours=0), # Ongoing
    JourneyStage.OFFBOARDING: timedelta(hours=4),
}

STAGE_OWNERS: Dict[JourneyStage, str] = {
    JourneyStage.ACCESS_REQUEST: "IT Support",
    JourneyStage.ACCOUNT_SETUP: "IT Support",
    JourneyStage.LOCAL_ENV_SETUP: "Developer",
    JourneyStage.REPO_DISCOVERY: "Developer",
    JourneyStage.PROJECT_UNDERSTANDING: "Developer + Tech Lead",
    JourneyStage.DEPS_INSTALLATION: "Developer",
    JourneyStage.DEVELOPMENT: "Developer",
    JourneyStage.TESTING: "Developer",
    JourneyStage.DEBUGGING: "Developer",
    JourneyStage.CODE_REVIEW: "Peer Developer",
    JourneyStage.SECURITY_REVIEW: "Security Team",
    JourneyStage.DEPLOYMENT: "DevOps / Developer",
    JourneyStage.MONITORING: "DevOps / SRE",
    JourneyStage.INCIDENT_RESPONSE: "SRE + Developer",
    JourneyStage.DOCUMENTATION: "Developer",
    JourneyStage.OFFBOARDING: "IT Support + Manager",
}

STAGE_DESCRIPTIONS: Dict[JourneyStage, str] = {
    JourneyStage.ACCESS_REQUEST: (
        "Submit access requests for required systems: source control, CI/CD, "
        "cloud console, monitoring, communication tools, and project management."
    ),
    JourneyStage.ACCOUNT_SETUP: (
        "Receive credentials and set up accounts. Configure MFA, SSH keys, "
        "GPG signing, and profile settings across all required platforms."
    ),
    JourneyStage.LOCAL_ENV_SETUP: (
        "Set up local development environment using standardized tooling. "
        "Install runtime, package manager, IDE, linters, formatters, and "
        "project-specific toolchain. Verify with one-command setup script."
    ),
    JourneyStage.REPO_DISCOVERY: (
        "Discover and clone relevant repositories. Review service catalog. "
        "Understand repository structure, branch strategy, and contribution workflow."
    ),
    JourneyStage.PROJECT_UNDERSTANDING: (
        "Deep-dive into project architecture, domain model, data flow, API contracts, "
        "and key design decisions. Review architecture decision records (ADRs). "
        "Pair with a senior team member."
    ),
    JourneyStage.DEPS_INSTALLATION: (
        "Install project dependencies using the project's package manager. "
        "Verify pinned versions. Set up seed data and local service dependencies."
    ),
    JourneyStage.DEVELOPMENT: (
        "Active feature development. Write code following team standards, "
        "run tests locally, use feature flags for work-in-progress. "
        "Keep PRs small and reviewable."
    ),
    JourneyStage.TESTING: (
        "Write and run unit tests, integration tests, and end-to-end tests. "
        "Achieve required code coverage thresholds. Test edge cases and error paths."
    ),
    JourneyStage.DEBUGGING: (
        "Use debugging tools to diagnose issues. Leverage local observability stack. "
        "Reproduce issues from production logs/traces. Fix root causes, not symptoms."
    ),
    JourneyStage.CODE_REVIEW: (
        "Submit PR with clear description, linked issue, test results, and screenshots. "
        "Respond to review feedback. Review others' code with empathy and thoroughness."
    ),
    JourneyStage.SECURITY_REVIEW: (
        "Automated SAST/DAST scanning. Manual security review for high-risk changes. "
        "Dependency vulnerability scanning. Secrets detection. Threat modeling for new features."
    ),
    JourneyStage.DEPLOYMENT: (
        "Deploy to staging, run smoke tests, then promote to production. "
        "Use canary or blue-green deployment strategy. Monitor dashboards during rollout."
    ),
    JourneyStage.MONITORING: (
        "Monitor service health via dashboards, alerts, and SLOs. "
        "Review error budgets. Set up new alerts and dashboards for new features."
    ),
    JourneyStage.INCIDENT_RESPONSE: (
        "Respond to production incidents. Follow runbooks. Escalate appropriately. "
        "Write blameless postmortems. Implement preventive actions."
    ),
    JourneyStage.DOCUMENTATION: (
        "Write and maintain documentation: architecture, APIs, runbooks, "
        "setup guides, troubleshooting. Documentation lives alongside code."
    ),
    JourneyStage.OFFBOARDING: (
        "Revoke access, transfer ownership of code and knowledge, "
        "update documentation, conduct exit interview. Archive accounts gracefully."
    ),
}


@dataclass
class StageEntry:
    """Represents a single stage in the developer's journey with tracking data."""
    stage: JourneyStage
    status: JourneyStageStatus = JourneyStageStatus.NOT_STARTED
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    blocked_reason: Optional[str] = None
    notes: str = ""
    artifacts: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def start(self) -> None:
        """Mark the stage as in progress."""
        if self.status == JourneyStageStatus.COMPLETED:
            logger.warning(f"Stage {self.stage.value} already completed; restarting")
        self.status = JourneyStageStatus.IN_PROGRESS
        self.started_at = datetime.utcnow()
        self.blocked_reason = None

    def complete(self, notes: str = "", artifacts: Optional[List[str]] = None) -> None:
        """Mark the stage as completed."""
        self.status = JourneyStageStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        self.notes = notes
        if artifacts:
            self.artifacts = artifacts

    def block(self, reason: str) -> None:
        """Block the stage with a reason."""
        self.status = JourneyStageStatus.BLOCKED
        self.blocked_reason = reason

    def skip(self, reason: str = "") -> None:
        """Skip this stage with optional reason."""
        self.status = JourneyStageStatus.SKIPPED
        self.notes = reason

    @property
    def duration(self) -> Optional[timedelta]:
        """Calculate duration if completed."""
        if self.completed_at and self.started_at:
            return self.completed_at - self.started_at
        if self.started_at:
            return datetime.utcnow() - self.started_at
        return None

    @property
    def is_overdue(self) -> bool:
        """Check if stage has exceeded its target duration."""
        target = STAGE_DURATION_TARGETS.get(self.stage)
        if target and target.total_seconds() == 0:
            return False  # Ongoing stages have no target
        if self.duration and target:
            return self.duration > target
        return False


@dataclass
class DeveloperJourney:
    """Complete developer journey tracking from hire to offboarding."""
    developer_id: str
    developer_name: str
    team: str
    role: str
    stages: Dict[JourneyStage, StageEntry] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self) -> None:
        """Initialize all journey stages on creation."""
        for stage in STAGE_ORDER:
            self.stages[stage] = StageEntry(stage=stage)

    def get_stage(self, stage: JourneyStage) -> StageEntry:
        """Get a specific stage entry."""
        if stage not in self.stages:
            raise ValueError(f"Unknown journey stage: {stage.value}")
        return self.stages[stage]

    def advance(self, stage: JourneyStage, notes: str = "",
                artifacts: Optional[List[str]] = None) -> StageEntry:
        """Advance to a stage, completing the current one if needed.

        Validates dependencies are met before advancing.
        """
        with self._lock:
            current = self.stages[stage]

            # Check dependencies
            unmet = self._unmet_dependencies(stage)
            if unmet:
                names = [s.value for s in unmet]
                raise ValueError(
                    f"Cannot advance to {stage.value}: "
                    f"dependencies not met: {names}"
                )

            current.complete(notes, artifacts)

            # Auto-start the next sequential stage if one exists
            self._auto_start_next(stage)

            return current

    def advance_to(self, stage: JourneyStage) -> StageEntry:
        """Advance the journey to a specific stage, starting it."""
        with self._lock:
            entry = self.stages[stage]
            if entry.status == JourneyStageStatus.COMPLETED:
                logger.info(f"Stage {stage.value} already completed")
                return entry

            # Complete all previous incomplete stages in order
            target_idx = STAGE_ORDER.index(stage)
            for i in range(target_idx):
                prev = STAGE_ORDER[i]
                if self.stages[prev].status == JourneyStageStatus.NOT_STARTED:
                    self.stages[prev].complete(notes="Auto-completed via advance_to")

            entry.start()
            return entry

    def block_stage(self, stage: JourneyStage, reason: str) -> StageEntry:
        """Block a stage with a specific reason."""
        entry = self.stages[stage]
        entry.block(reason)
        return entry

    def unblock_stage(self, stage: JourneyStage) -> StageEntry:
        """Remove a block from a stage."""
        entry = self.stages[stage]
        if entry.status == JourneyStageStatus.BLOCKED:
            entry.start()
        return entry

    def _unmet_dependencies(self, stage: JourneyStage) -> List[JourneyStage]:
        """Return list of dependencies not yet completed."""
        deps = STAGE_DEPENDENCIES.get(stage, [])
        unmet = []
        for dep in deps:
            dep_entry = self.stages.get(dep)
            if dep_entry and dep_entry.status not in (
                JourneyStageStatus.COMPLETED,
                JourneyStageStatus.SKIPPED,
            ):
                unmet.append(dep)
        return unmet

    def _auto_start_next(self, completed_stage: JourneyStage) -> None:
        """Auto-start the next sequential stage if dependencies are met."""
        try:
            current_idx = STAGE_ORDER.index(completed_stage)
            if current_idx + 1 < len(STAGE_ORDER):
                next_stage = STAGE_ORDER[current_idx + 1]
                next_entry = self.stages[next_stage]
                if (next_entry.status == JourneyStageStatus.NOT_STARTED and
                        not self._unmet_dependencies(next_stage)):
                    next_entry.start()
        except ValueError:
            pass

    @property
    def current_stage(self) -> Optional[JourneyStage]:
        """Return the currently active stage."""
        for stage in STAGE_ORDER:
            if self.stages[stage].status == JourneyStageStatus.IN_PROGRESS:
                return stage
        return None

    @property
    def progress_percentage(self) -> float:
        """Calculate overall journey progress as percentage."""
        completed = sum(
            1 for s in self.stages.values()
            if s.status in (JourneyStageStatus.COMPLETED, JourneyStageStatus.SKIPPED)
        )
        return (completed / len(STAGE_ORDER)) * 100

    @property
    def blocked_stages(self) -> List[StageEntry]:
        """Return all currently blocked stages."""
        return [
            s for s in self.stages.values()
            if s.status == JourneyStageStatus.BLOCKED
        ]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize journey to dictionary."""
        return {
            "developer_id": self.developer_id,
            "developer_name": self.developer_name,
            "team": self.team,
            "role": self.role,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "current_stage": self.current_stage.value if self.current_stage else None,
            "progress_percentage": round(self.progress_percentage, 1),
            "stages": {
                stage.value: {
                    "status": entry.status.value,
                    "started_at": entry.started_at.isoformat() if entry.started_at else None,
                    "completed_at": entry.completed_at.isoformat() if entry.completed_at else None,
                    "blocked_reason": entry.blocked_reason,
                    "is_overdue": entry.is_overdue,
                    "owner": STAGE_OWNERS.get(stage, "Unknown"),
                }
                for stage, entry in self.stages.items()
            },
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def complete_journey(self) -> None:
        """Mark the entire journey as completed (sets offboarding as complete)."""
        with self._lock:
            for stage in STAGE_ORDER:
                if self.stages[stage].status not in (
                    JourneyStageStatus.COMPLETED,
                    JourneyStageStatus.SKIPPED,
                ):
                    self.stages[stage].complete(notes="Journey completed")
            self.completed_at = datetime.utcnow()


# In-memory journey storage (enterprise would use database)
_journey_store: Dict[str, DeveloperJourney] = {}
_store_lock = threading.Lock()


def get_journey(developer_id: str) -> Optional[DeveloperJourney]:
    """Retrieve a developer's journey by ID."""
    return _journey_store.get(developer_id)


def get_all_journeys() -> List[DeveloperJourney]:
    """Retrieve all developer journeys."""
    return list(_journey_store.values())


def get_stage(developer_id: str, stage: JourneyStage) -> Optional[StageEntry]:
    """Get a specific stage entry for a developer."""
    journey = _journey_store.get(developer_id)
    if journey:
        return journey.stages.get(stage)
    return None


def advance_stage(developer_id: str, stage: JourneyStage,
                  notes: str = "",
                  artifacts: Optional[List[str]] = None) -> StageEntry:
    """Advance a developer to the next stage."""
    journey = _journey_store.get(developer_id)
    if not journey:
        raise ValueError(f"No journey found for developer: {developer_id}")
    return journey.advance(stage, notes, artifacts)


def create_journey(developer_id: str, developer_name: str,
                   team: str, role: str) -> DeveloperJourney:
    """Create a new developer journey."""
    with _store_lock:
        if developer_id in _journey_store:
            raise ValueError(f"Journey already exists for developer: {developer_id}")
        journey = DeveloperJourney(
            developer_id=developer_id,
            developer_name=developer_name,
            team=team,
            role=role,
        )
        # Auto-start the first stage
        journey.stages[JourneyStage.ACCESS_REQUEST].start()
        _journey_store[developer_id] = journey
        return journey


def get_journey_summary(developer_id: str) -> Optional[Dict[str, Any]]:
    """Get a summary of a developer's journey progress."""
    journey = _journey_store.get(developer_id)
    if not journey:
        return None
    return journey.to_dict()


def find_blocked_journeys() -> List[Dict[str, Any]]:
    """Find all journeys with blocked stages."""
    blocked = []
    for journey in _journey_store.values():
        blocked_stages = journey.blocked_stages
        if blocked_stages:
            blocked.append({
                "developer_id": journey.developer_id,
                "developer_name": journey.developer_name,
                "blocked_stages": [
                    {"stage": s.stage.value, "reason": s.blocked_reason}
                    for s in blocked_stages
                ],
            })
    return blocked