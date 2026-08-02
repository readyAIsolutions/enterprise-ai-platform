"""
Privacy Controls Engine
Implements privacy rights and controls:
  Consent Management, Right of Access, Right to Delete,
  Data Export, Data Correction, Restrict Processing,
  Data Residency, Purpose Limitation, Retention Management,
  Legal Hold
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


# ─── Enums ────────────────────────────────────────────────────────────────────

class ConsentStatus(str, Enum):
    """Consent lifecycle status."""
    GRANTED = "granted"
    DENIED = "denied"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"
    PENDING = "pending"
    NOT_APPLICABLE = "not_applicable"


class PrivacyRequestType(str, Enum):
    """Types of data subject requests."""
    ACCESS = "access"
    DELETE = "delete"
    EXPORT = "export"
    CORRECT = "correct"
    RESTRICT_PROCESSING = "restrict_processing"
    OBJECT_TO_PROCESSING = "object_to_processing"
    PORTABILITY = "portability"


class PrivacyRequestStatus(str, Enum):
    """Status of a privacy request."""
    RECEIVED = "received"
    VERIFIED = "verified"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DENIED = "denied"
    PARTIALLY_COMPLETED = "partially_completed"
    EXPIRED = "expired"


class RetentionPolicy(str, Enum):
    """Data retention policies."""
    DELETE_AFTER_PERIOD = "delete_after_period"
    ARCHIVE_AFTER_PERIOD = "archive_after_period"
    RETAIN_INDEFINITELY = "retain_indefinitely"
    LEGAL_HOLD = "legal_hold"
    DELETE_ON_REQUEST = "delete_on_request"
    ANONYMIZE_AFTER_PERIOD = "anonymize_after_period"


class PurposeCategory(str, Enum):
    """Data processing purpose categories."""
    SERVICE_DELIVERY = "service_delivery"
    MARKETING = "marketing"
    ANALYTICS = "analytics"
    AI_TRAINING = "ai_training"
    AI_INFERENCE = "ai_inference"
    SECURITY = "security"
    LEGAL_COMPLIANCE = "legal_compliance"
    RESEARCH = "research"
    PERSONALIZATION = "personalization"
    COMMUNICATION = "communication"


class DataResidency(str, Enum):
    """Data residency regions."""
    US = "us"
    EU = "eu"
    UK = "uk"
    CANADA = "canada"
    AUSTRALIA = "australia"
    JAPAN = "japan"
    SINGAPORE = "singapore"
    INDIA = "india"
    BRAZIL = "brazil"
    SWITZERLAND = "switzerland"


# ─── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class ConsentRecord:
    """Record of a data subject's consent."""
    consent_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    subject_id: str = ""
    purpose: PurposeCategory = PurposeCategory.SERVICE_DELIVERY
    status: ConsentStatus = ConsentStatus.PENDING
    granted_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    withdrawn_at: Optional[datetime] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    consent_version: str = "1.0"
    consent_text: str = ""
    proof_hash: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "consent_id": self.consent_id,
            "subject_id": self.subject_id,
            "purpose": self.purpose.value,
            "status": self.status.value,
            "granted_at": self.granted_at.isoformat() if self.granted_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "withdrawn_at": self.withdrawn_at.isoformat() if self.withdrawn_at else None,
            "consent_version": self.consent_version,
        }

    def compute_proof(self) -> str:
        """Compute tamper-evident proof of consent."""
        payload = f"{self.consent_id}|{self.subject_id}|{self.purpose.value}|{self.status.value}|{self.granted_at}"
        self.proof_hash = hashlib.sha256(payload.encode()).hexdigest()
        return self.proof_hash

    @property
    def is_valid(self) -> bool:
        """Check if consent is currently valid."""
        if self.status not in (ConsentStatus.GRANTED,):
            return False
        if self.expires_at and datetime.utcnow() > self.expires_at:
            self.status = ConsentStatus.EXPIRED
            return False
        return True


@dataclass
class PrivacyRequest:
    """A data subject privacy rights request."""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    subject_id: str = ""
    request_type: PrivacyRequestType = PrivacyRequestType.ACCESS
    status: PrivacyRequestStatus = PrivacyRequestStatus.RECEIVED
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None
    verification_method: str = ""
    due_date: Optional[datetime] = None
    data_locations: List[str] = field(default_factory=list)
    affected_fields: List[str] = field(default_factory=list)
    notes: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    audit_log: List[Dict[str, Any]] = field(default_factory=list)

    def add_audit_entry(self, action: str, details: str) -> None:
        self.audit_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "details": details,
        })

    @property
    def is_overdue(self) -> bool:
        if not self.due_date:
            return False
        return datetime.utcnow() > self.due_date and self.status not in (
            PrivacyRequestStatus.COMPLETED,
            PrivacyRequestStatus.DENIED,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "subject_id": self.subject_id,
            "request_type": self.request_type.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "is_overdue": self.is_overdue,
        }


@dataclass
class RetentionRule:
    """A data retention rule."""
    rule_id: str
    data_type: str  # Matches DataType values
    retention_period_days: int
    policy: RetentionPolicy
    archive_location: Optional[str] = None
    archive_retention_days: Optional[int] = None
    legal_basis: str = ""
    applies_to_fields: List[str] = field(default_factory=list)
    exceptions: List[str] = field(default_factory=list)
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "data_type": self.data_type,
            "retention_period_days": self.retention_period_days,
            "policy": self.policy.value,
            "archive_location": self.archive_location,
            "enabled": self.enabled,
        }


@dataclass
class LegalHold:
    """Legal hold on data preventing deletion."""
    hold_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    subject_ids: List[str] = field(default_factory=list)
    data_types: List[str] = field(default_factory=list)
    placed_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    placed_by: str = ""
    case_reference: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hold_id": self.hold_id,
            "name": self.name,
            "subject_ids": self.subject_ids,
            "data_types": self.data_types,
            "placed_at": self.placed_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_active": self.is_active,
        }


# ─── Privacy Manager ──────────────────────────────────────────────────────────

class PrivacyManager:
    """
    Enterprise privacy controls manager.

    Handles consent management, data subject requests (DSAR),
    retention policies, legal holds, and data residency.

    Usage:
        pm = PrivacyManager()
        pm.record_consent(subject_id="user123", purpose=PurposeCategory.MARKETING)
        pm.submit_request(PrivacyRequest(subject_id="user123", type=PrivacyRequestType.ACCESS))
        pm.add_retention_rule(RetentionRule(...))
    """

    def __init__(self, residency_region: DataResidency = DataResidency.US):
        self._consent_records: Dict[str, ConsentRecord] = {}
        self._privacy_requests: Dict[str, PrivacyRequest] = {}
        self._retention_rules: Dict[str, RetentionRule] = {}
        self._retention_by_type: Dict[str, str] = {}  # data_type -> rule_id
        self._legal_holds: Dict[str, LegalHold] = {}
        self._residency_region = residency_region
        self._purpose_restrictions: Dict[str, Set[PurposeCategory]] = {}
        self._corrected_fields: Dict[str, List[Dict[str, Any]]] = {}
        self._setup_default_retention_rules()

    def _setup_default_retention_rules(self) -> None:
        """Initialize default retention rules."""
        defaults = [
            RetentionRule("RET-001", "pii", 365 * 3, RetentionPolicy.DELETE_AFTER_PERIOD,
                         legal_basis="GDPR Art.5.1(e)"),
            RetentionRule("RET-002", "financial", 365 * 7, RetentionPolicy.ARCHIVE_AFTER_PERIOD,
                         archive_location="cold-storage", archive_retention_days=365 * 10,
                         legal_basis="Financial regulations"),
            RetentionRule("RET-003", "medical", 365 * 10, RetentionPolicy.ARCHIVE_AFTER_PERIOD,
                         archive_location="hipaa-archive", archive_retention_days=365 * 21,
                         legal_basis="HIPAA"),
            RetentionRule("RET-004", "legal", 365 * 10, RetentionPolicy.ARCHIVE_AFTER_PERIOD,
                         legal_basis="Statute of limitations"),
            RetentionRule("RET-005", "ai_training", 365, RetentionPolicy.DELETE_ON_REQUEST,
                         legal_basis="AI Governance"),
            RetentionRule("RET-006", "ai_memory", 90, RetentionPolicy.DELETE_AFTER_PERIOD,
                         legal_basis="AI Data Minimization"),
            RetentionRule("RET-007", "operational", 365, RetentionPolicy.DELETE_AFTER_PERIOD),
            RetentionRule("RET-008", "customer", 365 * 3, RetentionPolicy.ANONYMIZE_AFTER_PERIOD,
                         legal_basis="Customer relationship"),
        ]
        for rule in defaults:
            self._retention_rules[rule.rule_id] = rule
            self._retention_by_type[rule.data_type] = rule.rule_id

    def add_retention_rule(self, rule: RetentionRule) -> None:
        self._retention_rules[rule.rule_id] = rule
        self._retention_by_type[rule.data_type] = rule.rule_id

    def get_retention_rule(self, data_type: str) -> Optional[RetentionRule]:
        """Get the retention rule for a given data type."""
        rule_id = self._retention_by_type.get(data_type)
        if rule_id:
            return self._retention_rules.get(rule_id)
        return None

    # ── Consent Management ────────────────────────────────────────────────

    def record_consent(
        self,
        subject_id: str,
        purpose: PurposeCategory,
        status: ConsentStatus = ConsentStatus.GRANTED,
        duration_days: Optional[int] = None,
        consent_text: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ConsentRecord:
        """Record a consent action for a data subject."""
        record = ConsentRecord(
            subject_id=subject_id,
            purpose=purpose,
            status=status,
            granted_at=datetime.utcnow() if status == ConsentStatus.GRANTED else None,
            withdrawn_at=datetime.utcnow() if status == ConsentStatus.WITHDRAWN else None,
            expires_at=(
                datetime.utcnow() + timedelta(days=duration_days)
                if duration_days and status == ConsentStatus.GRANTED
                else None
            ),
            consent_text=consent_text,
            metadata=metadata or {},
        )
        record.compute_proof()
        key = f"{subject_id}:{purpose.value}"
        self._consent_records[key] = record
        return record

    def get_consent(self, subject_id: str, purpose: PurposeCategory) -> ConsentStatus:
        """Get current consent status for a subject/purpose pair."""
        key = f"{subject_id}:{purpose.value}"
        record = self._consent_records.get(key)
        if not record:
            return ConsentStatus.NOT_APPLICABLE
        if not record.is_valid:
            return ConsentStatus.EXPIRED
        return record.status

    def check_consent(
        self, subject_id: str, purpose: PurposeCategory
    ) -> Tuple[bool, str]:
        """Check if processing is allowed under consent. Returns (allowed, reason)."""
        status = self.get_consent(subject_id, purpose)

        if status == ConsentStatus.GRANTED:
            return True, "Consent granted"
        elif status == ConsentStatus.DENIED:
            return False, "Consent denied by subject"
        elif status == ConsentStatus.WITHDRAWN:
            return False, "Consent withdrawn"
        elif status == ConsentStatus.EXPIRED:
            return False, "Consent expired"
        elif status == ConsentStatus.NOT_APPLICABLE:
            # Check if this purpose is essential (always allowed)
            if purpose in (PurposeCategory.SECURITY, PurposeCategory.LEGAL_COMPLIANCE):
                return True, "Legitimate interest / legal obligation"
            return False, "No consent on file"
        return False, "Consent pending"

    def withdraw_consent(self, subject_id: str, purpose: PurposeCategory) -> bool:
        """Withdraw consent for a specific purpose."""
        key = f"{subject_id}:{purpose.value}"
        record = self._consent_records.get(key)
        if record:
            record.status = ConsentStatus.WITHDRAWN
            record.withdrawn_at = datetime.utcnow()
            record.compute_proof()
            return True
        return False

    def withdraw_all_consent(self, subject_id: str) -> int:
        """Withdraw all consent for a subject. Returns count of withdrawals."""
        count = 0
        for key, record in list(self._consent_records.items()):
            if record.subject_id == subject_id and record.status == ConsentStatus.GRANTED:
                record.status = ConsentStatus.WITHDRAWN
                record.withdrawn_at = datetime.utcnow()
                record.compute_proof()
                count += 1
        return count

    def get_consent_records(self, subject_id: str) -> List[ConsentRecord]:
        """Get all consent records for a subject."""
        return [r for r in self._consent_records.values() if r.subject_id == subject_id]

    def get_purposes_with_consent(self, subject_id: str) -> Set[PurposeCategory]:
        """Get all purposes for which a subject has valid consent."""
        purposes: Set[PurposeCategory] = set()
        for record in self._consent_records.values():
            if record.subject_id == subject_id and record.is_valid:
                purposes.add(record.purpose)
        return purposes

    # ── Data Subject Requests (DSAR) ──────────────────────────────────────

    def submit_request(self, request: PrivacyRequest) -> PrivacyRequest:
        """Submit a privacy rights request (access, delete, export, correct, restrict)."""
        # Validate
        if not request.subject_id:
            raise ValueError("subject_id is required")

        # Set due date based on request type
        if request.request_type in (
            PrivacyRequestType.ACCESS,
            PrivacyRequestType.DELETE,
            PrivacyRequestType.EXPORT,
        ):
            request.due_date = datetime.utcnow() + timedelta(days=30)  # GDPR 30-day requirement

        request.add_audit_entry("SUBMITTED", f"Request {request.request_id} submitted")
        self._privacy_requests[request.request_id] = request
        return request

    def verify_request(
        self,
        request_id: str,
        verification_method: str = "identity_confirmed",
    ) -> bool:
        """Verify a data subject request (identity verification)."""
        request = self._privacy_requests.get(request_id)
        if not request:
            return False
        if request.status != PrivacyRequestStatus.RECEIVED:
            return False
        request.status = PrivacyRequestStatus.VERIFIED
        request.verified_at = datetime.utcnow()
        request.verification_method = verification_method
        request.add_audit_entry("VERIFIED", f"Verified via {verification_method}")
        return True

    def complete_request(
        self,
        request_id: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Mark a request as completed."""
        request = self._privacy_requests.get(request_id)
        if not request:
            return False
        request.status = PrivacyRequestStatus.COMPLETED
        request.completed_at = datetime.utcnow()
        request.add_audit_entry("COMPLETED", f"Request completed with {len(data or {} )} fields")
        if data:
            request.metadata["result"] = data
        return True

    def deny_request(self, request_id: str, reason: str) -> bool:
        """Deny a privacy request with reasoning."""
        request = self._privacy_requests.get(request_id)
        if not request:
            return False
        request.status = PrivacyRequestStatus.DENIED
        request.completed_at = datetime.utcnow()
        request.add_audit_entry("DENIED", reason)
        return True

    def get_request(self, request_id: str) -> Optional[PrivacyRequest]:
        return self._privacy_requests.get(request_id)

    def get_requests_by_subject(self, subject_id: str) -> List[PrivacyRequest]:
        return [r for r in self._privacy_requests.values() if r.subject_id == subject_id]

    def get_overdue_requests(self) -> List[PrivacyRequest]:
        return [r for r in self._privacy_requests.values() if r.is_overdue]

    # ── Data Export ───────────────────────────────────────────────────────

    def export_data(
        self,
        subject_id: str,
        data_store: Dict[str, Any],
        format: str = "json",
    ) -> Dict[str, Any]:
        """Export all data for a subject in a portable format."""
        exported: Dict[str, Any] = {
            "subject_id": subject_id,
            "exported_at": datetime.utcnow().isoformat(),
            "format": format,
            "data": {},
            "metadata": {},
            "consent_records": [r.to_dict() for r in self.get_consent_records(subject_id)],
        }

        # Extract subject data from data store
        for key, value in data_store.items():
            if isinstance(value, dict):
                # Check if this record belongs to the subject
                if value.get("subject_id") == subject_id or value.get("user_id") == subject_id:
                    exported["data"][key] = value
            elif isinstance(value, list):
                subject_records = [
                    v for v in value
                    if isinstance(v, dict) and (
                        v.get("subject_id") == subject_id
                        or v.get("user_id") == subject_id
                    )
                ]
                if subject_records:
                    exported["data"][key] = subject_records

        # Include processing purposes
        exported["metadata"]["processed_for_purposes"] = [
            p.value for p in self.get_purposes_with_consent(subject_id)
        ]

        return exported

    # ── Data Correction ───────────────────────────────────────────────────

    def record_correction(
        self,
        subject_id: str,
        field: str,
        old_value: Any,
        new_value: Any,
        source: str = "subject_request",
    ) -> Dict[str, Any]:
        """Record a data correction with audit trail."""
        correction = {
            "correction_id": str(uuid.uuid4()),
            "subject_id": subject_id,
            "field": field,
            "old_value_hash": hashlib.sha256(str(old_value).encode()).hexdigest(),
            "new_value_hash": hashlib.sha256(str(new_value).encode()).hexdigest(),
            "corrected_at": datetime.utcnow().isoformat(),
            "source": source,
        }
        key = f"{subject_id}:{field}"
        self._corrected_fields.setdefault(key, []).append(correction)
        return correction

    def get_corrections(self, subject_id: str) -> List[Dict[str, Any]]:
        """Get all corrections for a subject."""
        return [
            c for key, corrections in self._corrected_fields.items()
            for c in corrections
            if c["subject_id"] == subject_id
        ]

    # ── Restrict Processing ───────────────────────────────────────────────

    def restrict_processing(
        self,
        subject_id: str,
        purpose: PurposeCategory,
        reason: str = "subject_request",
    ) -> None:
        """Restrict processing for a specific purpose."""
        self._purpose_restrictions.setdefault(subject_id, set()).add(purpose)
        # Also withdraw consent
        self.withdraw_consent(subject_id, purpose)

    def lift_restriction(
        self, subject_id: str, purpose: PurposeCategory
    ) -> bool:
        """Lift a processing restriction."""
        if subject_id in self._purpose_restrictions:
            self._purpose_restrictions[subject_id].discard(purpose)
            return True
        return False

    def is_processing_restricted(
        self, subject_id: str, purpose: PurposeCategory
    ) -> bool:
        """Check if processing is restricted for a subject/purpose."""
        return purpose in self._purpose_restrictions.get(subject_id, set())

    # ── Retention Management ──────────────────────────────────────────────

    def add_retention_rule(self, rule: RetentionRule) -> None:
        self._retention_rules[rule.rule_id] = rule

    def get_retention_rule(self, data_type: str) -> Optional[RetentionRule]:
        """Get the retention rule for a given data type."""
        return self._retention_rules.get(data_type)

    def get_retention_days(self, data_type: str) -> Optional[int]:
        """Get retention period in days for a data type."""
        rule = self.get_retention_rule(data_type)
        return rule.retention_period_days if rule else None

    def should_delete(
        self,
        data_type: str,
        created_at: datetime,
        subject_id: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Determine if data should be deleted based on retention rules."""
        # Check legal hold first
        if subject_id:
            for hold in self._legal_holds.values():
                if hold.is_active and subject_id in hold.subject_ids:
                    if data_type in hold.data_types or not hold.data_types:
                        return False, f"Legal hold: {hold.name}"

        rule = self.get_retention_rule(data_type)
        if not rule:
            return False, "No retention rule defined"

        if rule.policy == RetentionPolicy.RETAIN_INDEFINITELY:
            return False, "Indefinite retention"
        if rule.policy == RetentionPolicy.LEGAL_HOLD:
            return False, "Legal hold applies"

        age_days = (datetime.utcnow() - created_at).days
        if age_days > rule.retention_period_days:
            return True, f"Retention period ({rule.retention_period_days} days) exceeded by {age_days - rule.retention_period_days} days"

        return False, f"Within retention period ({rule.retention_period_days - age_days} days remaining)"

    def get_retention_rules(self) -> List[RetentionRule]:
        return list(self._retention_rules.values())

    # ── Legal Hold ────────────────────────────────────────────────────────

    def place_legal_hold(self, hold: LegalHold) -> LegalHold:
        """Place a legal hold preventing data deletion."""
        self._legal_holds[hold.hold_id] = hold
        return hold

    def release_legal_hold(self, hold_id: str) -> bool:
        """Release a legal hold."""
        hold = self._legal_holds.get(hold_id)
        if hold:
            hold.expires_at = datetime.utcnow()
            return True
        return False

    def get_active_holds(self, subject_id: str) -> List[LegalHold]:
        """Get all active legal holds for a subject."""
        return [
            h for h in self._legal_holds.values()
            if h.is_active and subject_id in h.subject_ids
        ]

    def get_all_holds(self) -> List[LegalHold]:
        return list(self._legal_holds.values())

    # ── Data Residency ────────────────────────────────────────────────────

    def set_residency_region(self, region: DataResidency) -> None:
        self._residency_region = region

    def get_residency_region(self) -> DataResidency:
        return self._residency_region

    def check_residency_compliance(
        self, data_region: DataResidency, data_type: str
    ) -> Tuple[bool, List[str]]:
        """
        Check if data can reside in a given region based on compliance.
        Returns (compliant, violations).
        """
        violations: List[str] = []

        # GDPR: EU personal data must stay in EU or adequate country
        gdpr_adequate = {
            DataResidency.EU, DataResidency.UK, DataResidency.SWITZERLAND,
            DataResidency.JAPAN, DataResidency.CANADA,
        }
        if data_type in ("pii", "medical", "ai_memory"):
            if self._residency_region == DataResidency.EU and data_region not in gdpr_adequate:
                violations.append("GDPR: Personal data transferred outside adequate jurisdictions")

        # HIPAA: Medical data should stay in US
        if data_type == "medical" and data_region != DataResidency.US:
            violations.append("HIPAA: PHI may require US residency")

        return len(violations) == 0, violations

    # ── Purpose Limitation ────────────────────────────────────────────────

    def validate_purpose(
        self, subject_id: str, purpose: PurposeCategory, data_types: List[str]
    ) -> Tuple[bool, str]:
        """Validate that data processing aligns with stated purpose."""
        allowed, reason = self.check_consent(subject_id, purpose)
        if not allowed:
            return False, reason

        if self.is_processing_restricted(subject_id, purpose):
            return False, "Processing restricted by subject"

        # Check data proportionality for purpose
        excessive_data: List[str] = []
        for dt in data_types:
            if dt == "ip" and purpose not in (
                PurposeCategory.SECURITY, PurposeCategory.LEGAL_COMPLIANCE
            ):
                excessive_data.append(dt)

        if excessive_data:
            return False, f"Excessive data types for purpose: {excessive_data}"

        return True, "Purpose validation passed"

    # ── Statistics ────────────────────────────────────────────────────────

    @property
    def stats(self) -> Dict[str, Any]:
        consent_counts = Counter(r.status.value for r in self._consent_records.values())
        request_counts = Counter(r.status.value for r in self._privacy_requests.values())
        return {
            "total_consent_records": len(self._consent_records),
            "consent_by_status": dict(consent_counts),
            "active_consents": consent_counts.get("granted", 0),
            "total_requests": len(self._privacy_requests),
            "requests_by_status": dict(request_counts),
            "overdue_requests": len(self.get_overdue_requests()),
            "active_legal_holds": sum(1 for h in self._legal_holds.values() if h.is_active),
            "retention_rules": len(self._retention_rules),
            "residency_region": self._residency_region.value,
        }