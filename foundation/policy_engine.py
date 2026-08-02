"""
Policy Engine — Enterprise Policy Definition, Enforcement, and Audit System.

Provides policy definition via JSON/YAML schema, rule-based enforcement with
severity levels, comprehensive audit logging, policy conflict detection, and
compliance-framework mapping (GDPR, SOC2, HIPAA, PCI-DSS, ISO 27001).

Architecture:
    PolicyDefinition — serializable policy with metadata
    PolicyRule        — a single rule with conditions, severity, action
    PolicySet         — grouped policies with conflict detection
    PolicyEnforcer    — run-time enforcement engine
    AuditLogger       — structured audit trail with tamper-evident hashing
    ConflictDetector  — static analysis of overlapping / contradictory rules
    ComplianceMapper  — maps policies to compliance frameworks

Python 3.10+ | dataclasses | full type hints | production quality
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from abc import ABC, abstractmethod
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from functools import lru_cache
from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    FrozenSet,
    Iterator,
    List,
    Literal,
    Optional,
    Pattern,
    Sequence,
    Set,
    Tuple,
    TypeVar,
    Union,
)

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────────────────────
# Helpers (defined early — used by dataclass default_factories below)
# ────────────────────────────────────────────────────────────────────────────────

_UID_COUNTER = 0


def _short_uid() -> str:
    """Short unique ID for runtime objects."""
    global _UID_COUNTER
    _UID_COUNTER += 1
    ts = datetime.now(timezone.utc).strftime("%H%M%S%f")
    return f"PE_{ts}_{_UID_COUNTER:x}"


# ────────────────────────────────────────────────────────────────────────────────
# Enums — severity, action, compliance frameworks
# ────────────────────────────────────────────────────────────────────────────────

class Severity(int, Enum):
    """Severity of a policy violation."""
    CRITICAL = 5
    HIGH     = 4
    MEDIUM   = 3
    LOW      = 2
    INFO     = 1

    def __lt__(self, other: Severity) -> bool:
        return self.value < other.value

    def __le__(self, other: Severity) -> bool:
        return self.value <= other.value

    def __gt__(self, other: Severity) -> bool:
        return self.value > other.value

    def __ge__(self, other: Severity) -> bool:
        return self.value >= other.value

    @classmethod
    def _missing_(cls, value: object) -> Optional[Severity]:
        if isinstance(value, (int, float)):
            for member in cls:
                if member.value == int(value):
                    return member
        return None


class EnforcementAction(str, Enum):
    """Action taken when a rule is triggered."""
    DENY       = "deny"
    ALLOW      = "allow"
    WARN       = "warn"
    FLAG       = "flag"
    QUARANTINE = "quarantine"
    MASK       = "mask"
    REDACT     = "redact"


class ComplianceFramework(str, Enum):
    """Recognised compliance frameworks for mapping."""
    GDPR       = "GDPR"
    SOC2       = "SOC2"
    HIPAA      = "HIPAA"
    PCI_DSS    = "PCI-DSS"
    ISO_27001  = "ISO-27001"
    CCPA       = "CCPA"
    SOX        = "SOX"
    FEDRAMP    = "FedRAMP"
    FISMA      = "FISMA"
    NIST_800_53 = "NIST-800-53"


# ────────────────────────────────────────────────────────────────────────────────
# Errors
# ────────────────────────────────────────────────────────────────────────────────

class PolicyError(Exception):
    """Base for all policy-engine errors."""

class PolicyDefinitionError(PolicyError):
    """Invalid policy or rule definition."""

class PolicyConflictError(PolicyError):
    """Conflicting policies detected."""

class PolicyEnforcementError(PolicyError):
    """Error during enforcement."""


# ────────────────────────────────────────────────────────────────────────────────
# Rule Condition
# ────────────────────────────────────────────────────────────────────────────────

@dataclass
class RuleCondition:
    """A single evaluable condition within a policy rule.

    Supported operators:
        eq, neq       — equality / inequality
        gt, lt, gte, lte — numeric comparisons
        regex         — regex match
        contains      — substring presence
        in, not_in    — set membership
        exists, not_exists — key presence check
        any_of        — value matches any of the listed values
    """
    field: str
    operator: str
    value: Any = None
    negate: bool = False

    SUPPORTED_OPS: ClassVar[FrozenSet[str]] = frozenset({
        "eq", "neq", "gt", "lt", "gte", "lte",
        "regex", "contains", "in", "not_in",
        "exists", "not_exists", "any_of",
    })

    _cached_re: Dict[str, Pattern[str]] = field(default_factory=dict, repr=False, init=False)

    def __post_init__(self) -> None:
        if self.operator not in self.SUPPORTED_OPS:
            raise PolicyDefinitionError(
                f"Unsupported operator '{self.operator}'. "
                f"Must be one of: {self.SUPPORTED_OPS}"
            )

    def evaluate(self, data: Dict[str, Any]) -> bool:
        """Evaluate this condition against a data dictionary."""
        field_val = data.get(self.field)

        if self.operator == "exists":
            result = self.field in data
        elif self.operator == "not_exists":
            result = self.field not in data
        elif field_val is None:
            result = False
        elif self.operator == "eq":
            result = field_val == self.value
        elif self.operator == "neq":
            result = field_val != self.value
        elif self.operator == "any_of":
            result = field_val in (list(self.value) if isinstance(self.value, (list, tuple, set)) else [])
        elif self.operator == "in":
            container = self.value if isinstance(self.value, (list, tuple, set, dict)) else [self.value]
            result = field_val in container
        elif self.operator == "not_in":
            container = self.value if isinstance(self.value, (list, tuple, set, dict)) else [self.value]
            result = field_val not in container
        elif self.operator == "regex":
            try:
                result = bool(re.search(self.value, str(field_val)))
            except re.error:
                result = False
        elif self.operator == "contains":
            result = str(self.value) in str(field_val)
        elif self.operator in ("gt", "lt", "gte", "lte"):
            try:
                fv = float(field_val)
                tv = float(self.value)
                _ops = {"gt": lambda a, b: a > b, "lt": lambda a, b: a < b,
                        "gte": lambda a, b: a >= b, "lte": lambda a, b: a <= b}
                result = _ops[self.operator](fv, tv)
            except (ValueError, TypeError):
                result = False
        else:
            result = False

        return not result if self.negate else result

    def to_dict(self) -> Dict[str, Any]:
        return {"field": self.field, "operator": self.operator,
                "value": self.value, "negate": self.negate}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> RuleCondition:
        return cls(field=d["field"], operator=d["operator"],
                   value=d.get("value"), negate=d.get("negate", False))


# ────────────────────────────────────────────────────────────────────────────────
# Policy Rule
# ────────────────────────────────────────────────────────────────────────────────

@dataclass
class PolicyRule:
    """A single policy rule — conditions + enforcement action.

    Rules support:
    - Multiple conditions with AND/OR logic
    - Custom evaluator callable for complex logic beyond conditions
    - Remediation hints
    - Enable / disable toggle
    - Compliance references
    """
    name: str
    description: str = ""
    conditions: List[RuleCondition] = field(default_factory=list)
    action: EnforcementAction = EnforcementAction.WARN
    severity: Severity = Severity.MEDIUM
    rule_id: str = ""                           # auto-generated
    enabled: bool = True
    match_all: bool = True                      # AND (True) vs OR (False)
    remediation: str = ""
    custom_evaluator: Optional[Callable[[Dict[str, Any]], bool]] = None
    compliance_refs: List[ComplianceFramework] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.rule_id:
            self.rule_id = _short_uid()

    def evaluate(self, data: Dict[str, Any]) -> bool:
        """Evaluate the rule against data.

        Returns True if the rule triggers (i.e. violations detected).
        """
        if not self.enabled:
            return False
        if self.custom_evaluator is not None:
            try:
                return self.custom_evaluator(data)
            except Exception:
                return False
        if not self.conditions:
            return False
        results = [c.evaluate(data) for c in self.conditions]
        return all(results) if self.match_all else any(results)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name, "description": self.description,
            "conditions": [c.to_dict() for c in self.conditions],
            "action": self.action.value, "severity": self.severity.value,
            "rule_id": self.rule_id, "enabled": self.enabled,
            "match_all": self.match_all, "remediation": self.remediation,
            "compliance_refs": [f.value for f in self.compliance_refs],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> PolicyRule:
        return cls(
            name=d["name"], description=d.get("description", ""),
            conditions=[RuleCondition.from_dict(c) for c in d.get("conditions", [])],
            action=EnforcementAction(d.get("action", "warn")),
            severity=Severity(d.get("severity", 3)),
            rule_id=d.get("rule_id", ""), enabled=d.get("enabled", True),
            match_all=d.get("match_all", True),
            remediation=d.get("remediation", ""),
            compliance_refs=[ComplianceFramework(f) for f in d.get("compliance_refs", [])],
            metadata=d.get("metadata", {}),
        )


# ────────────────────────────────────────────────────────────────────────────────
# Policy Definition
# ────────────────────────────────────────────────────────────────────────────────

@dataclass
class PolicyDefinition:
    """A complete policy definition — metadata + rules.

    Serialisable to JSON/YAML. Can be registered with a PolicySet or
    loaded directly into a PolicyEnforcer.
    """
    name: str
    description: str = ""
    domain: str = ""                            # security, privacy, coding, org, etc.
    rules: List[PolicyRule] = field(default_factory=list)
    version: str = "1.0.0"
    policy_id: str = ""
    enabled: bool = True
    tags: List[str] = field(default_factory=list)
    author: str = ""
    compliance_frameworks: List[ComplianceFramework] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    scope: Dict[str, Any] = field(default_factory=dict)  # e.g. {"environments": ["prod"]}

    def __post_init__(self) -> None:
        if not self.policy_id:
            self.policy_id = _short_uid()

    @property
    def enabled_rules(self) -> List[PolicyRule]:
        return [r for r in self.rules if r.enabled]

    def add_rule(self, rule: PolicyRule) -> None:
        self.rules.append(rule)

    def remove_rule(self, rule_id: str) -> bool:
        n = len(self.rules)
        self.rules = [r for r in self.rules if r.rule_id != rule_id]
        return len(self.rules) < n

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name, "description": self.description,
            "domain": self.domain, "version": self.version,
            "policy_id": self.policy_id, "enabled": self.enabled,
            "tags": self.tags, "author": self.author,
            "compliance_frameworks": [f.value for f in self.compliance_frameworks],
            "metadata": self.metadata, "scope": self.scope,
            "rules": [r.to_dict() for r in self.rules],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def to_yaml(self) -> str:
        import yaml
        return yaml.dump(self.to_dict(), sort_keys=False, allow_unicode=True)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> PolicyDefinition:
        return cls(
            name=d["name"], description=d.get("description", ""),
            domain=d.get("domain", ""),
            rules=[PolicyRule.from_dict(r) for r in d.get("rules", [])],
            version=d.get("version", "1.0.0"),
            policy_id=d.get("policy_id", ""), enabled=d.get("enabled", True),
            tags=d.get("tags", []), author=d.get("author", ""),
            compliance_frameworks=[ComplianceFramework(f) for f in d.get("compliance_frameworks", [])],
            metadata=d.get("metadata", {}), scope=d.get("scope", {}),
        )

    @classmethod
    def from_json(cls, s: str) -> PolicyDefinition:
        return cls.from_dict(json.loads(s))

    @classmethod
    def from_yaml(cls, s: str) -> PolicyDefinition:
        import yaml
        return cls.from_dict(yaml.safe_load(s))


# ────────────────────────────────────────────────────────────────────────────────
# Violation Record
# ────────────────────────────────────────────────────────────────────────────────

@dataclass
class Violation:
    """Record of a rule violation detected during enforcement."""
    rule_id: str
    rule_name: str
    policy_id: str
    policy_name: str
    severity: Severity
    action: EnforcementAction
    message: str
    remediation: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    violation_id: str = field(default_factory=_short_uid)
    matched_conditions: List[int] = field(default_factory=list)
    compliance_refs: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "violation_id": self.violation_id, "rule_id": self.rule_id,
            "rule_name": self.rule_name, "policy_id": self.policy_id,
            "policy_name": self.policy_name, "severity": self.severity.value,
            "action": self.action.value, "message": self.message,
            "remediation": self.remediation, "context": self.context,
            "timestamp": self.timestamp, "compliance_refs": self.compliance_refs,
        }


# ────────────────────────────────────────────────────────────────────────────────
# Audit Log
# ────────────────────────────────────────────────────────────────────────────────

@dataclass
class AuditEntry:
    """A single tamper-evident audit log entry.

    Each entry is chronologically chained via a hash of the previous entry,
    making the entire log tamper-evident.
    """
    entry_id: str
    timestamp: str
    event_type: str                             # evaluate, enforce, deny, allow, warn, config_change
    policy_id: Optional[str] = None
    rule_id: Optional[str] = None
    action: Optional[str] = None
    severity: Optional[str] = None
    message: str = ""
    data_hash: str = ""                         # SHA256 of input data (privacy-preserving)
    context: Dict[str, Any] = field(default_factory=dict)
    prev_hash: str = ""                         # chain hash
    entry_hash: str = ""                        # self-hash

    def __post_init__(self) -> None:
        if not self.entry_id:
            self.entry_id = _short_uid()
        if not self.entry_hash:
            raw = f"{self.entry_id}|{self.timestamp}|{self.event_type}|" \
                  f"{self.policy_id or ''}|{self.rule_id or ''}|" \
                  f"{self.action or ''}|{self.severity or ''}|{self.message}|" \
                  f"{self.data_hash}|{self.prev_hash}"
            self.entry_hash = hashlib.sha256(raw.encode()).hexdigest()


class AuditLogger:
    """Tamper-evident, append-only audit log with chain hashing.

    Each entry's hash depends on the previous entry's hash, forming a
    verifiable chain. Supports filtering, export, and integrity verification.
    """

    def __init__(self, max_entries: int = 100_000) -> None:
        self._entries: List[AuditEntry] = []
        self._max = max_entries
        self._lock_hash: str = hashlib.sha256(b"GENESIS").hexdigest()

    def log(self, event_type: str, policy_id: Optional[str] = None,
            rule_id: Optional[str] = None, action: Optional[str] = None,
            severity: Optional[str] = None, message: str = "",
            data: Optional[Dict[str, Any]] = None,
            context: Optional[Dict[str, Any]] = None) -> AuditEntry:
        """Append a new audit entry."""
        data_hash = hashlib.sha256(
            json.dumps(data or {}, sort_keys=True).encode()
        ).hexdigest()[:16]

        entry = AuditEntry(
            entry_id=_short_uid(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type=event_type, policy_id=policy_id, rule_id=rule_id,
            action=action, severity=severity, message=message,
            data_hash=data_hash, context=context or {},
            prev_hash=self._lock_hash,
        )
        self._lock_hash = entry.entry_hash
        self._entries.append(entry)
        if len(self._entries) > self._max:
            self._entries = self._entries[-self._max:]
        return entry

    def query(self, event_type: Optional[str] = None,
              policy_id: Optional[str] = None,
              severity: Optional[str] = None,
              since: Optional[str] = None,
              limit: int = 100) -> List[AuditEntry]:
        """Filtered query over audit entries."""
        results = self._entries
        if event_type:
            results = [e for e in results if e.event_type == event_type]
        if policy_id:
            results = [e for e in results if e.policy_id == policy_id]
        if severity:
            results = [e for e in results if e.severity == severity]
        if since:
            results = [e for e in results if e.timestamp >= since]
        return results[-limit:]

    def verify_integrity(self) -> bool:
        """Check that the hash chain is intact (tamper-evident guarantee)."""
        expected = hashlib.sha256(b"GENESIS").hexdigest()
        for e in self._entries:
            if e.prev_hash != expected:
                return False
            raw = f"{e.entry_id}|{e.timestamp}|{e.event_type}|" \
                  f"{e.policy_id or ''}|{e.rule_id or ''}|" \
                  f"{e.action or ''}|{e.severity or ''}|{e.message}|" \
                  f"{e.data_hash}|{e.prev_hash}"
            expected = hashlib.sha256(raw.encode()).hexdigest()
        return self._lock_hash == expected

    def export(self) -> List[Dict[str, Any]]:
        return [
            {
                "entry_id": e.entry_id, "timestamp": e.timestamp,
                "event_type": e.event_type, "policy_id": e.policy_id,
                "rule_id": e.rule_id, "action": e.action, "severity": e.severity,
                "message": e.message, "data_hash": e.data_hash,
                "context": e.context, "prev_hash": e.prev_hash,
                "entry_hash": e.entry_hash,
            }
            for e in self._entries
        ]

    def __len__(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()
        self._lock_hash = hashlib.sha256(b"GENESIS").hexdigest()


# ────────────────────────────────────────────────────────────────────────────────
# Conflict Detector
# ────────────────────────────────────────────────────────────────────────────────

@dataclass
class ConflictReport:
    """Report of a policy conflict."""
    policy_a_id: str
    policy_b_id: str
    rule_a_id: str
    rule_b_id: str
    conflict_type: str            # opposite_action | overlapping_scope | redundant
    description: str
    severity: Severity = Severity.MEDIUM
    resolution_hint: str = ""


class ConflictDetector:
    """Static analysis engine that detects conflicts between policies.

    Detects:
    - Opposite-action conflicts: two rules on the same condition, one ALLOWs, one DENYs.
    - Overlapping-scope conflicts: rules that overlap but don't fully agree.
    - Redundant rules: identical conditions with same action (candidate for merging).
    """

    def detect(self, policies: List[PolicyDefinition]) -> List[ConflictReport]:
        """Run conflict detection across a set of policies."""
        reports: List[ConflictReport] = []
        rules_flat: List[Tuple[str, str, PolicyRule]] = []  # (policy_id, policy_name, rule)

        for pol in policies:
            if not pol.enabled:
                continue
            for rule in pol.enabled_rules:
                rules_flat.append((pol.policy_id, pol.name, rule))

        # pairwise comparison
        for i in range(len(rules_flat)):
            for j in range(i + 1, len(rules_flat)):
                pid_a, pname_a, ra = rules_flat[i]
                pid_b, pname_b, rb = rules_flat[j]
                rpt = self._compare(pid_a, pname_a, ra, pid_b, pname_b, rb)
                if rpt:
                    reports.append(rpt)

        return reports

    def _compare(self, pid_a: str, pname_a: str, ra: PolicyRule,
                 pid_b: str, pname_b: str, rb: PolicyRule) -> Optional[ConflictReport]:
        """Compare two rules from potentially different policies."""

        # Check for opposite actions on overlapping conditions
        if ra.action != rb.action and self._conditions_overlap(ra.conditions, rb.conditions):
            if ra.action == EnforcementAction.DENY or rb.action == EnforcementAction.DENY:
                # Opposite-action conflict when one denies and the other allows/warns
                return ConflictReport(
                    policy_a_id=pid_a, policy_b_id=pid_b,
                    rule_a_id=ra.rule_id, rule_b_id=rb.rule_id,
                    conflict_type="opposite_action",
                    description=f"'{ra.name}' ({ra.action.value}) conflicts with "
                                f"'{rb.name}' ({rb.action.value}) on overlapping conditions",
                    severity=Severity.HIGH,
                    resolution_hint="Align enforcement actions or narrow one rule's scope.",
                )

        # Check for redundancy (same conditions, same action)
        if ra.action == rb.action and self._conditions_equivalent(ra.conditions, rb.conditions):
            return ConflictReport(
                policy_a_id=pid_a, policy_b_id=pid_b,
                rule_a_id=ra.rule_id, rule_b_id=rb.rule_id,
                conflict_type="redundant",
                description=f"'{ra.name}' and '{rb.name}' are near-duplicate rules.",
                severity=Severity.LOW,
                resolution_hint="Consider merging into a single rule or removing one.",
            )

        # Overlapping scope: same field checked with different operators
        if self._scope_overlap(ra, rb):
            return ConflictReport(
                policy_a_id=pid_a, policy_b_id=pid_b,
                rule_a_id=ra.rule_id, rule_b_id=rb.rule_id,
                conflict_type="overlapping_scope",
                description=f"'{ra.name}' and '{rb.name}' have partially overlapping scope.",
                severity=Severity.MEDIUM,
                resolution_hint="Review whether the overlap is intentional; consider scoping more precisely.",
            )

        return None

    @staticmethod
    def _conditions_overlap(a: List[RuleCondition], b: List[RuleCondition]) -> bool:
        """True if any condition in `a` checks the same field with comparable operators."""
        for ca in a:
            for cb in b:
                if ca.field == cb.field:
                    return True
        return False

    @staticmethod
    def _conditions_equivalent(a: List[RuleCondition], b: List[RuleCondition]) -> bool:
        """True if condition sets are effectively equivalent."""
        if len(a) != len(b):
            return False
        a_sorted = sorted((c.field, c.operator, str(c.value)) for c in a)
        b_sorted = sorted((c.field, c.operator, str(c.value)) for c in b)
        return a_sorted == b_sorted

    @staticmethod
    def _scope_overlap(ra: PolicyRule, rb: PolicyRule) -> bool:
        """Detect overlapping but not identical scope."""
        a_fields = {c.field for c in ra.conditions}
        b_fields = {c.field for c in rb.conditions}
        intersection = a_fields & b_fields
        if not intersection:
            return False
        # Overlap if they share at least one field but aren't fully equivalent
        return not (a_fields == b_fields and ra.action == rb.action)


# ────────────────────────────────────────────────────────────────────────────────
# Compliance Mapper
# ────────────────────────────────────────────────────────────────────────────────

@dataclass
class ComplianceMapping:
    """Maps a policy to one or more compliance frameworks with specific controls."""
    policy_id: str
    framework: ComplianceFramework
    control_ids: List[str]     # e.g. ["GDPR-Art.5", "GDPR-Art.32"]
    coverage: float = 1.0      # 0–1 how fully the policy covers the control
    notes: str = ""


class ComplianceMapper:
    """Maps policies to compliance frameworks (GDPR, SOC2, HIPAA, etc.).

    Provides gap analysis: given a framework, which controls are covered?
    """

    # Known controls per framework (abbreviated)
    _FRAMEWORK_CONTROLS: ClassVar[Dict[ComplianceFramework, List[str]]] = {
        ComplianceFramework.GDPR: [
            "GDPR-Art.5", "GDPR-Art.6", "GDPR-Art.7", "GDPR-Art.12",
            "GDPR-Art.15", "GDPR-Art.16", "GDPR-Art.17", "GDPR-Art.25",
            "GDPR-Art.28", "GDPR-Art.30", "GDPR-Art.32", "GDPR-Art.33",
            "GDPR-Art.34", "GDPR-Art.35", "GDPR-Art.44",
        ],
        ComplianceFramework.SOC2: [
            "CC1", "CC2", "CC3", "CC4", "CC5",
            "CC6", "CC7", "CC8", "CC9", "CC10",
        ],
        ComplianceFramework.HIPAA: [
            "164.308", "164.310", "164.312", "164.314",
            "164.316", "164.502", "164.504", "164.506",
            "164.508", "164.510", "164.512", "164.514",
        ],
        ComplianceFramework.PCI_DSS: [
            "Req1", "Req2", "Req3", "Req4", "Req5", "Req6",
            "Req7", "Req8", "Req9", "Req10", "Req11", "Req12",
        ],
        ComplianceFramework.ISO_27001: [
            "A.5", "A.6", "A.7", "A.8", "A.9", "A.10",
            "A.11", "A.12", "A.13", "A.14", "A.15", "A.16",
            "A.17", "A.18",
        ],
        ComplianceFramework.CCPA: [
            "1798.100", "1798.105", "1798.110", "1798.115",
            "1798.120", "1798.125", "1798.130", "1798.135",
            "1798.140", "1798.145", "1798.150", "1798.155",
        ],
    }

    def __init__(self) -> None:
        self._mappings: Dict[str, List[ComplianceMapping]] = defaultdict(list)  # policy_id -> [...]

    def register(self, mapping: ComplianceMapping) -> None:
        self._mappings[mapping.policy_id].append(mapping)

    def get_covered_controls(self, framework: ComplianceFramework) -> Set[str]:
        """Return all control IDs covered by any registered policy for a framework."""
        covered: Set[str] = set()
        for maps in self._mappings.values():
            for m in maps:
                if m.framework == framework:
                    covered.update(m.control_ids)
        return covered

    def gap_analysis(self, framework: ComplianceFramework) -> Dict[str, Any]:
        """Return which controls are covered vs missing for a framework."""
        all_controls = set(self._FRAMEWORK_CONTROLS.get(framework, []))
        covered = self.get_covered_controls(framework)
        missing = all_controls - covered
        return {
            "framework": framework.value,
            "total_controls": len(all_controls),
            "covered": len(covered),
            "missing": len(missing),
            "coverage_pct": round(len(covered) / max(len(all_controls), 1) * 100, 1),
            "covered_controls": sorted(covered),
            "missing_controls": sorted(missing),
        }

    def export(self) -> Dict[str, Any]:
        return {
            fw.value: self.gap_analysis(fw) for fw in ComplianceFramework
        }


# ────────────────────────────────────────────────────────────────────────────────
# Policy Set
# ────────────────────────────────────────────────────────────────────────────────

@dataclass
class EnforcementResult:
    """Complete result of a policy enforcement run."""
    allowed: bool
    violations: List[Violation] = field(default_factory=list)
    warnings: List[Violation] = field(default_factory=list)
    blocked_by: List[Tuple[str, str]] = field(default_factory=list)  # (policy, rule)
    evaluation_time_ms: float = 0.0
    run_id: str = field(default_factory=_short_uid)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def has_critical(self) -> bool:
        return any(v.severity == Severity.CRITICAL for v in self.violations)

    @property
    def max_severity(self) -> Severity:
        if not self.violations:
            return Severity.INFO
        return max(v.severity for v in self.violations)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed, "run_id": self.run_id,
            "timestamp": self.timestamp, "evaluation_time_ms": self.evaluation_time_ms,
            "max_severity": self.max_severity.value,
            "violation_count": len(self.violations),
            "warning_count": len(self.warnings),
            "blocked_by": [{"policy": p, "rule": r} for p, r in self.blocked_by],
            "violations": [v.to_dict() for v in self.violations],
        }


class PolicySet:
    """A named, versioned collection of policies with conflict detection."""

    def __init__(self, name: str = "default", version: str = "1.0.0") -> None:
        self.name = name
        self.version = version
        self._policies: Dict[str, PolicyDefinition] = {}
        self.conflict_detector = ConflictDetector()

    def add(self, policy: PolicyDefinition) -> None:
        self._policies[policy.policy_id] = policy
        logger.info("PolicySet[%s]: added %s (%s)", self.name, policy.name, policy.policy_id)

    def remove(self, policy_id: str) -> bool:
        return self._policies.pop(policy_id, None) is not None

    def get(self, policy_id: str) -> Optional[PolicyDefinition]:
        return self._policies.get(policy_id)

    def list_all(self) -> List[PolicyDefinition]:
        return list(self._policies.values())

    def list_enabled(self) -> List[PolicyDefinition]:
        return [p for p in self._policies.values() if p.enabled]

    def list_by_domain(self, domain: str) -> List[PolicyDefinition]:
        return [p for p in self._policies.values() if p.domain == domain]

    def detect_conflicts(self) -> List[ConflictReport]:
        return self.conflict_detector.detect(list(self._policies.values()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name, "version": self.version,
            "policies": [p.to_dict() for p in self._policies.values()],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> PolicySet:
        ps = cls(name=d.get("name", "default"), version=d.get("version", "1.0.0"))
        for pd in d.get("policies", []):
            ps.add(PolicyDefinition.from_dict(pd))
        return ps

    @classmethod
    def from_json(cls, s: str) -> PolicySet:
        return cls.from_dict(json.loads(s))


# ────────────────────────────────────────────────────────────────────────────────
# Policy Enforcer  (runtime enforcement)
# ────────────────────────────────────────────────────────────────────────────────

class PolicyEnforcer:
    """Runtime enforcement engine.

    Evaluates a PolicySet against incoming data, produces violations,
    enforces actions (allow/deny/warn/flag/redact/mask), and logs everything
    through the AuditLogger.

    Integration hooks:
        - pre_evaluate / post_evaluate callbacks
        - Custom data redaction via redaction_map
    """

    def __init__(self, policy_set: Optional[PolicySet] = None,
                 audit_logger: Optional[AuditLogger] = None,
                 default_action: EnforcementAction = EnforcementAction.ALLOW) -> None:
        self.policy_set = policy_set or PolicySet()
        self.audit = audit_logger or AuditLogger()
        self.default_action = default_action
        self._pre_hooks: List[Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]] = []
        self._post_hooks: List[Callable[[EnforcementResult], None]] = []

    def add_hook(self, phase: Literal["pre", "post"],
                 callback: Callable[..., Optional[Any]]) -> None:
        if phase == "pre":
            self._pre_hooks.append(callback)
        else:
            self._post_hooks.append(callback)

    def enforce(self, data: Dict[str, Any],
                domains: Optional[List[str]] = None,
                policy_ids: Optional[List[str]] = None) -> EnforcementResult:
        """Evaluate all enabled policies against `data` and return a result.

        Args:
            data: Input data dict to check against policies.
            domains: If set, only evaluate policies in these domains.
            policy_ids: If set, only evaluate these specific policy IDs.

        Returns:
            EnforcementResult with violations and allow/deny status.
        """
        import time
        t0 = time.perf_counter()

        # Run pre-hooks — hooks may mutate `data`
        for hook in self._pre_hooks:
            try:
                result = hook(deepcopy(data))
                if result is not None:
                    data = result
            except Exception:
                logger.exception("Pre-hook failed; continuing")

        policies = self._select_policies(domains, policy_ids)
        violations: List[Violation] = []
        warnings: List[Violation] = []
        blocked_by: List[Tuple[str, str]] = []

        for policy in policies:
            if not policy.enabled:
                continue
            for rule in policy.enabled_rules:
                if rule.evaluate(data):
                    violation = Violation(
                        rule_id=rule.rule_id, rule_name=rule.name,
                        policy_id=policy.policy_id, policy_name=policy.name,
                        severity=rule.severity, action=rule.action,
                        message=f"[{policy.name}] {rule.name}: {rule.description}",
                        remediation=rule.remediation,
                        context={"domain": policy.domain},
                        compliance_refs=[f.value for f in rule.compliance_refs],
                    )

                    # Log to audit trail
                    self.audit.log(
                        event_type="violation",
                        policy_id=policy.policy_id, rule_id=rule.rule_id,
                        action=rule.action.value,
                        severity=rule.severity.name,
                        message=violation.message,
                        data=data,
                        context={"policy_name": policy.name, "rule_name": rule.name},
                    )

                    if rule.action == EnforcementAction.DENY:
                        violations.append(violation)
                        blocked_by.append((policy.name, rule.name))
                    elif rule.action in (EnforcementAction.WARN, EnforcementAction.FLAG):
                        warnings.append(violation)
                        violations.append(violation)
                    else:
                        violations.append(violation)

        elapsed = (time.perf_counter() - t0) * 1000.0
        allowed = len(blocked_by) == 0

        result = EnforcementResult(
            allowed=allowed, violations=violations, warnings=warnings,
            blocked_by=blocked_by, evaluation_time_ms=round(elapsed, 2),
        )

        # Audit the overall enforcement
        self.audit.log(
            event_type="enforce",
            action="ALLOW" if allowed else "DENY",
            message=f"Enforcement {'passed' if allowed else 'blocked'}; "
                    f"{len(violations)} violations, {len(warnings)} warnings",
            data=data,
            context={"run_id": result.run_id, "blocked_by": result.blocked_by},
        )

        # Run post-hooks
        for hook in self._post_hooks:
            try:
                hook(result)
            except Exception:
                logger.exception("Post-hook failed; continuing")

        return result

    def _select_policies(self, domains: Optional[List[str]],
                         policy_ids: Optional[List[str]]) -> List[PolicyDefinition]:
        if policy_ids:
            return [
                p for pid in policy_ids
                if (p := self.policy_set.get(pid)) and p.enabled
            ]
        enabled = self.policy_set.list_enabled()
        if domains:
            enabled = [p for p in enabled if p.domain in domains]
        return enabled

    def enforce_with_redaction(self, data: Dict[str, Any],
                               redact_fields: List[str],
                               domains: Optional[List[str]] = None) -> Tuple[EnforcementResult, Dict[str, Any]]:
        """Enforce policies AND redact specified fields from a copy of the data.

        Returns (result, redacted_copy).
        """
        redacted = deepcopy(data)
        for field in redact_fields:
            if field in redacted:
                redacted[field] = "[REDACTED]"
        result = self.enforce(redacted, domains=domains)
        return result, redacted


# ────────────────────────────────────────────────────────────────────────────────
# Preset Policy Factories
# ────────────────────────────────────────────────────────────────────────────────

class DataPrivacyPreset:
    """Factory for GDPR / CCPA -aligned data privacy policies."""

    @staticmethod
    def create() -> PolicyDefinition:
        return PolicyDefinition(
            name="Data Privacy Policy",
            description="Detects PII patterns: emails, SSNs, credit cards, phones, IPs, addresses, DOBs.",
            domain="privacy", version="1.0.0",
            tags=["pii", "gdpr", "ccpa", "compliance"],
            compliance_frameworks=[ComplianceFramework.GDPR, ComplianceFramework.CCPA],
            rules=[
                PolicyRule(
                    name="Email Detection", description="Detects email addresses",
                    conditions=[RuleCondition("content", "regex",
                                              r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")],
                    action=EnforcementAction.WARN, severity=Severity.HIGH,
                    remediation="Redact or mask email addresses.",
                    compliance_refs=[ComplianceFramework.GDPR],
                ),
                PolicyRule(
                    name="SSN Detection", description="Detects US SSN patterns",
                    conditions=[RuleCondition("content", "regex",
                                              r"\b\d{3}[-.]?\d{2}[-.]?\d{4}\b")],
                    action=EnforcementAction.DENY, severity=Severity.CRITICAL,
                    remediation="Never store raw SSNs. Use tokenization.",
                    compliance_refs=[ComplianceFramework.GDPR, ComplianceFramework.CCPA],
                ),
                PolicyRule(
                    name="Credit Card Detection", description="Detects credit card numbers",
                    conditions=[RuleCondition("content", "regex",
                                              r"\b(?:\d[ -]*?){13,19}\b")],
                    action=EnforcementAction.DENY, severity=Severity.CRITICAL,
                    remediation="Use PCI-compliant tokenization.",
                    compliance_refs=[ComplianceFramework.PCI_DSS],
                ),
                PolicyRule(
                    name="Phone Number Detection", description="Detects US phone numbers",
                    conditions=[RuleCondition("content", "regex",
                                              r"\b\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")],
                    action=EnforcementAction.WARN, severity=Severity.MEDIUM,
                    remediation="Mask phone numbers in non-essential contexts.",
                ),
                PolicyRule(
                    name="IP Address Detection", description="Detects IPv4 addresses",
                    conditions=[RuleCondition("content", "regex",
                                              r"\b(?:\d{1,3}\.){3}\d{1,3}\b")],
                    action=EnforcementAction.WARN, severity=Severity.LOW,
                    remediation="Anonymize IP addresses where not operationally required.",
                ),
                PolicyRule(
                    name="Street Address Detection", description="Detects physical addresses",
                    conditions=[RuleCondition("content", "regex",
                                              r"\b\d{1,5}\s\w+\s(?:St(?:reet)?|Ave(?:nue)?|Rd|Blvd|Ln)\b")],
                    action=EnforcementAction.WARN, severity=Severity.MEDIUM,
                ),
                PolicyRule(
                    name="DOB Detection", description="Detects date-of-birth fields",
                    conditions=[RuleCondition("content", "regex",
                                              r"\b(?:DOB|Date of Birth|Birthdate?)[:\s]*[\d/.-]+\b")],
                    action=EnforcementAction.WARN, severity=Severity.HIGH,
                    remediation="Encrypt dates of birth at rest.",
                    compliance_refs=[ComplianceFramework.GDPR],
                ),
            ],
        )


class SecurityPreset:
    """Factory for security vulnerability detection policies."""

    @staticmethod
    def create() -> PolicyDefinition:
        return PolicyDefinition(
            name="Security Policy",
            description="Detects SQL injection, XSS, hardcoded secrets, command injection, path traversal.",
            domain="security", version="1.0.0",
            tags=["security", "owasp", "vulnerability"],
            compliance_frameworks=[ComplianceFramework.SOC2, ComplianceFramework.ISO_27001],
            rules=[
                PolicyRule(
                    name="SQL Injection Detection",
                    description="Detects SQL injection patterns",
                    conditions=[
                        RuleCondition("content", "regex",
                                      r"(?i)(\bSELECT\b.*\bFROM\b|\bDROP\b\s+\bTABLE\b|\bINSERT\b\s+\bINTO\b)"),
                        RuleCondition("content", "regex", r"(?i)(--|\*/|@@)"),
                    ],
                    match_all=False,  # OR — any pattern triggers
                    action=EnforcementAction.DENY, severity=Severity.CRITICAL,
                    remediation="Use parameterized queries.",
                    compliance_refs=[ComplianceFramework.PCI_DSS],
                ),
                PolicyRule(
                    name="XSS Detection",
                    description="Detects cross-site scripting attempts",
                    conditions=[RuleCondition("content", "regex",
                                              r"(?i)(<script|javascript:|onerror=|onload=|eval\(|alert\()")],
                    action=EnforcementAction.DENY, severity=Severity.CRITICAL,
                    remediation="Sanitize all user inputs. Use CSP headers.",
                    compliance_refs=[ComplianceFramework.SOC2],
                ),
                PolicyRule(
                    name="Hardcoded Secret Detection",
                    description="Detects hardcoded API keys, passwords, tokens",
                    conditions=[RuleCondition("content", "regex",
                                              r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][^'\"]{8,}['\"]")],
                    action=EnforcementAction.DENY, severity=Severity.CRITICAL,
                    remediation="Use a secrets manager (Vault, AWS Secrets Manager).",
                    compliance_refs=[ComplianceFramework.SOC2, ComplianceFramework.ISO_27001],
                ),
                PolicyRule(
                    name="Command Injection Detection",
                    description="Detects command injection patterns",
                    conditions=[RuleCondition("content", "regex",
                                              r"(?i)(;\s*(rm|shutdown|curl|wget|nc)\b|\$\{|`[^`]+`)")],
                    action=EnforcementAction.DENY, severity=Severity.CRITICAL,
                    remediation="Never pass raw user input to shell commands.",
                ),
                PolicyRule(
                    name="Path Traversal Detection",
                    description="Detects path traversal attacks",
                    conditions=[RuleCondition("content", "regex",
                                              r"(\.\.\/|\.\.\\|%2e%2e%2f|%2e%2e/)")],
                    action=EnforcementAction.DENY, severity=Severity.CRITICAL,
                    remediation="Resolve and canonicalize paths before file access.",
                ),
            ],
        )


