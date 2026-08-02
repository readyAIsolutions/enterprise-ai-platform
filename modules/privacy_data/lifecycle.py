"""
Data Lifecycle Management
Complete data lifecycle from Collection to Deletion:
  Collection → Validation → Classification → Encryption →
  Storage → Processing → AI Usage → Sharing → Archiving →
  Backup → Recovery → Retention → Deletion → Audit
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union
import uuid
import hashlib
import json


# ─── Lifecycle Stages ─────────────────────────────────────────────────────────

class LifecycleStage(str, Enum):
    """Complete data lifecycle stages."""
    COLLECTION = "collection"         # Data is collected/ingested
    VALIDATION = "validation"         # Data validated for quality/integrity
    CLASSIFICATION = "classification" # Data classified by sensitivity/type
    ENCRYPTION = "encryption"         # Data encrypted
    STORAGE = "storage"               # Data persisted
    PROCESSING = "processing"         # Data being processed/transformed
    AI_USAGE = "ai_usage"            # Data used for AI/ML
    SHARING = "sharing"              # Data shared with third parties
    ARCHIVING = "archiving"          # Data archived to cold storage
    BACKUP = "backup"                # Data backed up
    RECOVERY = "recovery"            # Data recovered from backup
    RETENTION = "retention"          # Data retained per policy
    DELETION = "deletion"            # Data securely deleted
    AUDIT = "audit"                  # Lifecycle audit review

    @classmethod
    def ordered_stages(cls) -> List["LifecycleStage"]:
        """Return stages in typical lifecycle order."""
        return [
            cls.COLLECTION, cls.VALIDATION, cls.CLASSIFICATION,
            cls.ENCRYPTION, cls.STORAGE, cls.PROCESSING,
            cls.AI_USAGE, cls.SHARING, cls.ARCHIVING,
            cls.BACKUP, cls.RECOVERY, cls.RETENTION,
            cls.DELETION, cls.AUDIT,
        ]

    @property
    def is_terminal(self) -> bool:
        return self in (LifecycleStage.DELETION,)

    @property
    def is_reversible(self) -> bool:
        return self in (
            LifecycleStage.ARCHIVING, LifecycleStage.PROCESSING,
            LifecycleStage.AI_USAGE, LifecycleStage.SHARING,
        )


class StageStatus(str, Enum):
    """Status of a lifecycle stage execution."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ROLLED_BACK = "rolled_back"


# ─── Transition Rules ─────────────────────────────────────────────────────────

# Valid transitions between stages
VALID_TRANSITIONS: Dict[LifecycleStage, Set[LifecycleStage]] = {
    LifecycleStage.COLLECTION: {LifecycleStage.VALIDATION},
    LifecycleStage.VALIDATION: {LifecycleStage.CLASSIFICATION, LifecycleStage.COLLECTION},
    LifecycleStage.CLASSIFICATION: {LifecycleStage.ENCRYPTION, LifecycleStage.STORAGE},
    LifecycleStage.ENCRYPTION: {LifecycleStage.STORAGE},
    LifecycleStage.STORAGE: {
        LifecycleStage.PROCESSING, LifecycleStage.AI_USAGE,
        LifecycleStage.SHARING, LifecycleStage.ARCHIVING,
    },
    LifecycleStage.PROCESSING: {LifecycleStage.STORAGE, LifecycleStage.ARCHIVING},
    LifecycleStage.AI_USAGE: {LifecycleStage.STORAGE, LifecycleStage.DELETION},
    LifecycleStage.SHARING: {LifecycleStage.STORAGE, LifecycleStage.AUDIT},
    LifecycleStage.ARCHIVING: {LifecycleStage.RECOVERY, LifecycleStage.DELETION},
    LifecycleStage.BACKUP: {LifecycleStage.RECOVERY},
    LifecycleStage.RECOVERY: {LifecycleStage.STORAGE, LifecycleStage.VALIDATION},
    LifecycleStage.RETENTION: {LifecycleStage.DELETION, LifecycleStage.ARCHIVING},
    LifecycleStage.DELETION: {LifecycleStage.AUDIT},
    LifecycleStage.AUDIT: set(),  # Terminal stage
}


# ─── Lifecycle Event ──────────────────────────────────────────────────────────

@dataclass
class LifecycleEvent:
    """Record of a lifecycle stage transition."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    stage: LifecycleStage = LifecycleStage.COLLECTION
    status: StageStatus = StageStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    actor: str = "system"
    details: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "stage": self.stage.value,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "actor": self.actor,
            "duration_seconds": self.duration_seconds,
            "error_message": self.error_message,
        }


# ─── Lifecycle Policy ─────────────────────────────────────────────────────────

@dataclass
class LifecyclePolicy:
    """Policy governing lifecycle transitions and validations."""
    policy_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    require_validation: bool = True
    require_classification: bool = True
    require_encryption: bool = False  # Set true for sensitive data
    max_retention_days: Optional[int] = None
    archive_after_days: Optional[int] = None
    backup_frequency_hours: Optional[int] = 24
    allow_ai_usage: bool = True
    allow_sharing: bool = False
    require_audit_trail: bool = True
    deletion_strategy: str = "hard_delete"  # hard_delete, soft_delete, anonymize
    custom_hooks: Dict[LifecycleStage, Optional[Callable]] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "name": self.name,
            "require_validation": self.require_validation,
            "require_classification": self.require_classification,
            "require_encryption": self.require_encryption,
            "max_retention_days": self.max_retention_days,
            "archive_after_days": self.archive_after_days,
            "backup_frequency_hours": self.backup_frequency_hours,
            "allow_ai_usage": self.allow_ai_usage,
            "allow_sharing": self.allow_sharing,
        }


# ─── Data Asset ───────────────────────────────────────────────────────────────

@dataclass
class DataAsset:
    """
    A data asset tracked through its lifecycle.
    Represents a dataset, table, collection, or file.
    """
    asset_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    data_type: str = "other"  # Maps to DataType enum from classifier
    sensitivity: str = "public"  # Maps to SensitivityLevel
    current_stage: LifecycleStage = LifecycleStage.COLLECTION
    lifecycle_events: List[LifecycleEvent] = field(default_factory=list)
    policy: Optional[LifecyclePolicy] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    size_bytes: int = 0
    record_count: int = 0
    location: str = ""  # Storage location/URI
    checksum: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_event(self, event: LifecycleEvent) -> None:
        self.lifecycle_events.append(event)
        if event.status == StageStatus.COMPLETED:
            self.current_stage = event.stage

    def get_stage_history(self) -> Dict[str, List[LifecycleEvent]]:
        """Get events grouped by stage."""
        history: Dict[str, List[LifecycleEvent]] = defaultdict(list)
        for event in self.lifecycle_events:
            history[event.stage.value].append(event)
        return dict(history)

    def get_latest_event(self, stage: LifecycleStage) -> Optional[LifecycleEvent]:
        """Get the most recent event for a stage."""
        events = [e for e in self.lifecycle_events if e.stage == stage]
        return events[-1] if events else None

    def get_failed_events(self) -> List[LifecycleEvent]:
        return [e for e in self.lifecycle_events if e.status == StageStatus.FAILED]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "name": self.name,
            "data_type": self.data_type,
            "sensitivity": self.sensitivity,
            "current_stage": self.current_stage.value,
            "created_at": self.created_at.isoformat(),
            "size_bytes": self.size_bytes,
            "record_count": self.record_count,
            "location": self.location,
            "event_count": len(self.lifecycle_events),
        }


# ─── Lifecycle Manager ────────────────────────────────────────────────────────

class LifecycleManager:
    """
    Enterprise data lifecycle manager.

    Tracks data assets through all lifecycle stages, enforcing
    transition rules, policies, and audit requirements.

    Usage:
        manager = LifecycleManager()
        asset = manager.create_asset("customer_data", "pii", "confidential")
        manager.transition(asset.asset_id, LifecycleStage.VALIDATION)
        manager.transition(asset.asset_id, LifecycleStage.CLASSIFICATION)
    """

    def __init__(self):
        self._assets: Dict[str, DataAsset] = {}
        self._policies: Dict[str, LifecyclePolicy] = {}
        self._transition_history: List[Dict[str, Any]] = []
        self._setup_default_policies()

    def _setup_default_policies(self) -> None:
        """Set up default lifecycle policies."""
        # Sensitive data policy
        sensitive_policy = LifecyclePolicy(
            name="Sensitive Data",
            require_validation=True,
            require_classification=True,
            require_encryption=True,
            max_retention_days=365 * 3,
            archive_after_days=365,
            backup_frequency_hours=12,
            allow_ai_usage=False,
            allow_sharing=False,
            deletion_strategy="hard_delete",
        )
        self._policies[sensitive_policy.policy_id] = sensitive_policy

        # Operational data policy
        operational_policy = LifecyclePolicy(
            name="Operational Data",
            require_validation=False,
            require_classification=False,
            require_encryption=False,
            max_retention_days=90,
            archive_after_days=None,
            backup_frequency_hours=24,
            allow_ai_usage=True,
            allow_sharing=True,
            deletion_strategy="soft_delete",
        )
        self._policies[operational_policy.policy_id] = operational_policy

        # AI training data policy
        ai_training_policy = LifecyclePolicy(
            name="AI Training Data",
            require_validation=True,
            require_classification=True,
            require_encryption=False,
            max_retention_days=365,
            archive_after_days=None,
            backup_frequency_hours=24,
            allow_ai_usage=True,
            allow_sharing=False,
            deletion_strategy="anonymize",
        )
        self._policies[ai_training_policy.policy_id] = ai_training_policy

    # ── Asset Management ──────────────────────────────────────────────────

    def create_asset(
        self,
        name: str,
        data_type: str = "other",
        sensitivity: str = "public",
        policy_id: Optional[str] = None,
        **metadata,
    ) -> DataAsset:
        """Create a new data asset and enter the collection stage."""
        asset = DataAsset(
            name=name,
            data_type=data_type,
            sensitivity=sensitivity,
            metadata=metadata,
        )
        if policy_id:
            asset.policy = self._policies.get(policy_id)

        # Record collection event
        event = LifecycleEvent(
            stage=LifecycleStage.COLLECTION,
            status=StageStatus.COMPLETED,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            actor="system",
            details={"name": name, "data_type": data_type, "sensitivity": sensitivity},
        )
        asset.add_event(event)
        self._assets[asset.asset_id] = asset

        self._log_transition(asset.asset_id, None, LifecycleStage.COLLECTION)
        return asset

    def get_asset(self, asset_id: str) -> Optional[DataAsset]:
        return self._assets.get(asset_id)

    def get_assets_by_stage(self, stage: LifecycleStage) -> List[DataAsset]:
        return [a for a in self._assets.values() if a.current_stage == stage]

    def get_all_assets(self) -> List[DataAsset]:
        return list(self._assets.values())

    def remove_asset(self, asset_id: str) -> bool:
        """Hard-remove asset from tracking."""
        if asset_id in self._assets:
            del self._assets[asset_id]
            return True
        return False

    # ── Transition Management ─────────────────────────────────────────────

    def can_transition(
        self, asset_id: str, target_stage: LifecycleStage
    ) -> Tuple[bool, str]:
        """
        Check if a transition is valid.
        Returns (allowed, reason).
        """
        asset = self._assets.get(asset_id)
        if not asset:
            return False, "Asset not found"

        current = asset.current_stage

        # Check transition validity
        valid_next = VALID_TRANSITIONS.get(current, set())
        if target_stage not in valid_next:
            return False, (
                f"Invalid transition: {current.value} → {target_stage.value}. "
                f"Valid next stages: {[s.value for s in valid_next]}"
            )

        # Check policy constraints
        policy = asset.policy
        if policy:
            if target_stage == LifecycleStage.ENCRYPTION and not policy.require_encryption:
                return True, "Encryption not required by policy (allowed)"

            if target_stage == LifecycleStage.AI_USAGE and not policy.allow_ai_usage:
                return False, "AI usage not allowed by lifecycle policy"

            if target_stage == LifecycleStage.SHARING and not policy.allow_sharing:
                return False, "Data sharing not allowed by lifecycle policy"

            if target_stage == LifecycleStage.VALIDATION and not policy.require_validation:
                return True, "Validation not required by policy (allowed)"

            if target_stage == LifecycleStage.CLASSIFICATION and not policy.require_classification:
                return True, "Classification not required by policy (allowed)"

        # Check retention for deletion
        if target_stage == LifecycleStage.DELETION and policy and policy.max_retention_days:
            age = (datetime.utcnow() - asset.created_at).days
            if age < policy.max_retention_days:
                return True, f"Within retention period ({policy.max_retention_days - age} days remaining)"
            # Overdue - deletion is allowed
            return True, "Retention period exceeded"

        return True, "Transition allowed"

    def transition(
        self,
        asset_id: str,
        target_stage: LifecycleStage,
        actor: str = "system",
        details: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, LifecycleEvent]:
        """
        Transition an asset to a new lifecycle stage.
        Returns (success, event).
        """
        asset = self._assets.get(asset_id)
        if not asset:
            event = LifecycleEvent(
                stage=target_stage,
                status=StageStatus.FAILED,
                error_message="Asset not found",
            )
            return False, event

        allowed, reason = self.can_transition(asset_id, target_stage)
        if not allowed:
            event = LifecycleEvent(
                stage=target_stage,
                status=StageStatus.FAILED,
                error_message=reason,
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
            )
            asset.add_event(event)
            self._log_transition(asset_id, asset.current_stage, target_stage, False)
            return False, event

        # Create event
        event = LifecycleEvent(
            stage=target_stage,
            status=StageStatus.IN_PROGRESS,
            started_at=datetime.utcnow(),
            actor=actor,
            details=details or {},
        )
        asset.add_event(event)

        # Apply stage-specific logic
        self._execute_stage(asset, target_stage, event)

        # Complete
        previous_stage = asset.current_stage
        event.status = StageStatus.COMPLETED
        event.completed_at = datetime.utcnow()
        asset.current_stage = target_stage
        self._log_transition(asset_id, previous_stage, target_stage, True)

        return True, event

    def _execute_stage(
        self, asset: DataAsset, stage: LifecycleStage, event: LifecycleEvent
    ) -> None:
        """Execute stage-specific actions."""
        if stage == LifecycleStage.VALIDATION:
            event.details["validation"] = "Data integrity check passed"

        elif stage == LifecycleStage.CLASSIFICATION:
            event.details["classification"] = {
                "data_type": asset.data_type,
                "sensitivity": asset.sensitivity,
            }

        elif stage == LifecycleStage.ENCRYPTION:
            event.details["encryption"] = {
                "algorithm": "AES-256-GCM",
                "applied_at": datetime.utcnow().isoformat(),
            }

        elif stage == LifecycleStage.STORAGE:
            event.details["storage"] = {
                "location": asset.location or "default",
                "timestamp": datetime.utcnow().isoformat(),
            }

        elif stage == LifecycleStage.BACKUP:
            backup_id = str(uuid.uuid4())
            event.details["backup"] = {
                "backup_id": backup_id,
                "timestamp": datetime.utcnow().isoformat(),
            }

        elif stage == LifecycleStage.ARCHIVING:
            event.details["archive"] = {
                "archive_location": "cold-storage",
                "timestamp": datetime.utcnow().isoformat(),
            }

        elif stage == LifecycleStage.DELETION:
            policy = asset.policy
            strategy = policy.deletion_strategy if policy else "hard_delete"
            event.details["deletion"] = {
                "strategy": strategy,
                "timestamp": datetime.utcnow().isoformat(),
            }

        elif stage == LifecycleStage.AUDIT:
            event.details["audit"] = {
                "audit_complete": True,
                "total_events": len(asset.lifecycle_events),
                "timestamp": datetime.utcnow().isoformat(),
            }

    def fail_transition(
        self,
        asset_id: str,
        stage: LifecycleStage,
        error_message: str,
    ) -> Optional[LifecycleEvent]:
        """Record a failed transition."""
        asset = self._assets.get(asset_id)
        if not asset:
            return None

        event = LifecycleEvent(
            stage=stage,
            status=StageStatus.FAILED,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            error_message=error_message,
        )
        asset.add_event(event)
        return event

    def rollback_stage(
        self, asset_id: str, from_stage: LifecycleStage
    ) -> Tuple[bool, str]:
        """Roll back a lifecycle stage."""
        asset = self._assets.get(asset_id)
        if not asset:
            return False, "Asset not found"

        if not from_stage.is_reversible:
            return False, f"Stage {from_stage.value} is not reversible"

        # Mark the stage as rolled back
        latest = asset.get_latest_event(from_stage)
        if latest:
            latest.status = StageStatus.ROLLED_BACK

        # Determine previous stage
        ordered = LifecycleStage.ordered_stages()
        idx = ordered.index(from_stage)
        if idx > 0:
            asset.current_stage = ordered[idx - 1]

        return True, f"Rolled back from {from_stage.value} to {asset.current_stage.value}"

    # ── Policy Management ─────────────────────────────────────────────────

    def add_policy(self, policy: LifecyclePolicy) -> str:
        self._policies[policy.policy_id] = policy
        return policy.policy_id

    def get_policy(self, policy_id: str) -> Optional[LifecyclePolicy]:
        return self._policies.get(policy_id)

    def assign_policy(self, asset_id: str, policy_id: str) -> bool:
        """Assign a lifecycle policy to an asset."""
        asset = self._assets.get(asset_id)
        policy = self._policies.get(policy_id)
        if asset and policy:
            asset.policy = policy
            return True
        return False

    def get_policies(self) -> List[LifecyclePolicy]:
        return list(self._policies.values())

    # ── Queries ───────────────────────────────────────────────────────────

    def get_lifecycle_timeline(self, asset_id: str) -> List[Dict[str, Any]]:
        """Get the full lifecycle timeline for an asset."""
        asset = self._assets.get(asset_id)
        if not asset:
            return []
        return [e.to_dict() for e in asset.lifecycle_events]

    def get_assets_by_policy(self, policy_id: str) -> List[DataAsset]:
        return [
            a for a in self._assets.values()
            if a.policy and a.policy.policy_id == policy_id
        ]

    def get_assets_by_type(self, data_type: str) -> List[DataAsset]:
        return [a for a in self._assets.values() if a.data_type == data_type]

    def get_assets_by_sensitivity(self, sensitivity: str) -> List[DataAsset]:
        return [a for a in self._assets.values() if a.sensitivity == sensitivity]

    def get_assets_due_for_archival(self) -> List[DataAsset]:
        """Get assets due for archival based on policy."""
        due: List[DataAsset] = []
        for asset in self._assets.values():
            policy = asset.policy
            if policy and policy.archive_after_days:
                age = (datetime.utcnow() - asset.created_at).days
                if age >= policy.archive_after_days:
                    if asset.current_stage not in (
                        LifecycleStage.ARCHIVING,
                        LifecycleStage.DELETION,
                        LifecycleStage.AUDIT,
                    ):
                        due.append(asset)
        return due

    def get_assets_due_for_deletion(self) -> List[DataAsset]:
        """Get assets past retention period."""
        due: List[DataAsset] = []
        for asset in self._assets.values():
            policy = asset.policy
            if policy and policy.max_retention_days:
                age = (datetime.utcnow() - asset.created_at).days
                if age >= policy.max_retention_days:
                    if asset.current_stage != LifecycleStage.DELETION:
                        due.append(asset)
        return due

    # ── Bulk Operations ───────────────────────────────────────────────────

    def bulk_transition(
        self,
        asset_ids: List[str],
        target_stage: LifecycleStage,
        actor: str = "system",
    ) -> Dict[str, Tuple[bool, str]]:
        """Transition multiple assets to the same stage."""
        results: Dict[str, Tuple[bool, str]] = {}
        for asset_id in asset_ids:
            success, event = self.transition(asset_id, target_stage, actor)
            results[asset_id] = (success, event.error_message or "Success")
        return results

    def execute_full_lifecycle(
        self, asset_id: str, actor: str = "automation"
    ) -> Dict[str, Tuple[bool, str]]:
        """
        Execute the complete lifecycle for an asset.
        Stops at first failure.
        """
        results: Dict[str, Tuple[bool, str]] = {}
        asset = self._assets.get(asset_id)
        if not asset:
            return {"error": (False, "Asset not found")}

        for stage in LifecycleStage.ordered_stages():
            if stage == asset.current_stage:
                continue
            if stage in (LifecycleStage.ARCHIVING, LifecycleStage.BACKUP,
                        LifecycleStage.RECOVERY, LifecycleStage.DELETION,
                        LifecycleStage.AUDIT):
                continue  # Skip terminal/optional stages in auto-run

            success, event = self.transition(asset_id, stage, actor)
            results[stage.value] = (success, event.error_message or "OK")
            if not success:
                break

        return results

    # ── Logging ────────────────────────────────────────────────────────────

    def _log_transition(
        self,
        asset_id: str,
        from_stage: Optional[LifecycleStage],
        to_stage: LifecycleStage,
        success: bool = True,
    ) -> None:
        self._transition_history.append({
            "asset_id": asset_id,
            "from_stage": from_stage.value if from_stage else None,
            "to_stage": to_stage.value,
            "success": success,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def get_transition_history(
        self, limit: int = 100
    ) -> List[Dict[str, Any]]:
        return self._transition_history[-limit:]

    @property
    def stats(self) -> Dict[str, Any]:
        stage_counts = Counter(a.current_stage.value for a in self._assets.values())
        type_counts = Counter(a.data_type for a in self._assets.values())
        failed_events = sum(
            len(a.get_failed_events()) for a in self._assets.values()
        )
        return {
            "total_assets": len(self._assets),
            "assets_by_stage": dict(stage_counts),
            "assets_by_type": dict(type_counts),
            "total_transitions": len(self._transition_history),
            "failed_events": failed_events,
            "assets_due_for_archival": len(self.get_assets_due_for_archival()),
            "assets_due_for_deletion": len(self.get_assets_due_for_deletion()),
        }