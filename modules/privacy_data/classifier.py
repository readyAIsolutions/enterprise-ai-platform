"""
Data Classification Engine
Classifies data by sensitivity, type, and regulatory requirements.
Supports classification levels:
  Public, Internal, Confidential, Restricted
Data types: PII, Financial, Medical, Legal, IP, AI Training, AI Memory, Customer, Operational
"""
from __future__ import annotations

import re
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union


# ─── Classification Enums ────────────────────────────────────────────────────

class SensitivityLevel(str, Enum):
    """Data sensitivity classification tiers."""
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"

    @classmethod
    def from_score(cls, score: float) -> "SensitivityLevel":
        if score >= 0.9:
            return cls.RESTRICTED
        elif score >= 0.7:
            return cls.CONFIDENTIAL
        elif score >= 0.4:
            return cls.INTERNAL
        return cls.PUBLIC

    @property
    def numeric_level(self) -> int:
        mapping = {
            SensitivityLevel.PUBLIC: 0,
            SensitivityLevel.INTERNAL: 1,
            SensitivityLevel.CONFIDENTIAL: 2,
            SensitivityLevel.RESTRICTED: 3,
        }
        return mapping[self]


class DataType(str, Enum):
    """Specific data type categories."""
    PII = "pii"                      # Personally Identifiable Information
    FINANCIAL = "financial"           # Payment, banking, financial records
    MEDICAL = "medical"              # PHI, health records
    LEGAL = "legal"                  # Legal documents, contracts
    IP = "ip"                        # Intellectual Property
    AI_TRAINING = "ai_training"      # Training data for AI/ML
    AI_MEMORY = "ai_memory"          # AI agent memory/persona data
    CUSTOMER = "customer"            # Customer relationship data
    OPERATIONAL = "operational"      # System operational data
    OTHER = "other"                  # Unclassified

    @property
    def default_sensitivity(self) -> SensitivityLevel:
        mapping = {
            DataType.PII: SensitivityLevel.CONFIDENTIAL,
            DataType.FINANCIAL: SensitivityLevel.RESTRICTED,
            DataType.MEDICAL: SensitivityLevel.CONFIDENTIAL,
            DataType.LEGAL: SensitivityLevel.CONFIDENTIAL,
            DataType.IP: SensitivityLevel.RESTRICTED,
            DataType.AI_TRAINING: SensitivityLevel.INTERNAL,
            DataType.AI_MEMORY: SensitivityLevel.CONFIDENTIAL,
            DataType.CUSTOMER: SensitivityLevel.CONFIDENTIAL,
            DataType.OPERATIONAL: SensitivityLevel.INTERNAL,
            DataType.OTHER: SensitivityLevel.PUBLIC,
        }
        return mapping[self]


class ClassificationConfidence(str, Enum):
    """Confidence level of a classification result."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ─── PII Detection Patterns ──────────────────────────────────────────────────

PII_PATTERNS: Dict[str, re.Pattern] = {
    "email": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'),
    "ssn_us": re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
    "credit_card": re.compile(
        r'\b(?:\d{4}[-\s]?){3}\d{4}\b|\b\d{13,19}\b'
    ),
    "phone_us": re.compile(
        r'\b\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'
    ),
    "ip_address": re.compile(
        r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
    ),
    "dob": re.compile(
        r'\b(?:0[1-9]|1[0-2])[/-](?:0[1-9]|[12]\d|3[01])[/-](?:19|20)\d{2}\b'
    ),
    "passport": re.compile(r'\b[A-Z][0-9]{7,8}\b'),
    "bank_account": re.compile(r'\b\d{8,17}\b'),
    "national_id": re.compile(r'\b[A-Z]{2}\d{6,12}[A-Z]?\b'),
    "api_key": re.compile(
        r'\b(?:api[_-]?key|apikey|secret[_-]?key|token)[:=]\s*[\'"]?[A-Za-z0-9_\-\.]{20,}\b',
        re.IGNORECASE,
    ),
    "aws_key": re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
    "private_key_header": re.compile(
        r'-----BEGIN\s(?:RSA|EC|DSA|OPENSSH|PGP)?\s?PRIVATE\sKEY-----'
    ),
}

PII_TYPE_NAMES: Dict[str, str] = {
    "email": "Email Address",
    "ssn_us": "US Social Security Number",
    "credit_card": "Credit Card Number",
    "phone_us": "US Phone Number",
    "ip_address": "IP Address",
    "dob": "Date of Birth",
    "passport": "Passport Number",
    "bank_account": "Bank Account Number",
    "national_id": "National ID",
    "api_key": "API Key / Secret",
    "aws_key": "AWS Access Key",
    "private_key_header": "Private Key",
}


# ─── Classification Rules ─────────────────────────────────────────────────────

@dataclass
class ClassificationRule:
    """A rule for classifying data based on pattern or condition."""
    rule_id: str
    name: str
    data_type: DataType
    sensitivity: SensitivityLevel
    patterns: List[Union[str, re.Pattern]] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    field_names: List[str] = field(default_factory=list)
    custom_matcher: Optional[Callable[[Any], Tuple[bool, float]]] = None
    weight: float = 1.0
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def matches_field_name(self, name: str) -> bool:
        """Check if field name matches any known patterns."""
        name_lower = name.lower().replace('_', ' ').replace('-', ' ')
        for fn in self.field_names:
            if fn.lower() in name_lower:
                return True
        return False

    def matches_value(self, value: Any) -> Tuple[bool, float]:
        """Check if value matches patterns. Returns (matched, confidence)."""
        if value is None:
            return False, 0.0
        if self.custom_matcher:
            return self.custom_matcher(value)
        strval = str(value)
        if not strval.strip():
            return False, 0.0
        matches = 0
        total = len(self.patterns) + len(self.keywords)
        if total == 0:
            return False, 0.0
        for pat in self.patterns:
            if isinstance(pat, re.Pattern):
                if pat.search(strval):
                    matches += 1
            elif isinstance(pat, str):
                if pat.lower() in strval.lower():
                    matches += 1
        for kw in self.keywords:
            if kw.lower() in strval.lower():
                matches += 1
        if matches == 0:
            return False, 0.0
        return True, min(1.0, matches / total)


# ─── Default Classification Rules ─────────────────────────────────────────────

DEFAULT_RULES: List[ClassificationRule] = [
    ClassificationRule(
        rule_id="R001",
        name="PII - Email",
        data_type=DataType.PII,
        sensitivity=SensitivityLevel.CONFIDENTIAL,
        patterns=[PII_PATTERNS["email"]],
        field_names=["email", "e_mail", "mail", "email_addr", "from", "to"],
        weight=1.0,
    ),
    ClassificationRule(
        rule_id="R002",
        name="PII - SSN",
        data_type=DataType.PII,
        sensitivity=SensitivityLevel.RESTRICTED,
        patterns=[PII_PATTERNS["ssn_us"]],
        field_names=["ssn", "social_security", "social security", "tax_id"],
        weight=2.0,
    ),
    ClassificationRule(
        rule_id="R003",
        name="Financial - Credit Card",
        data_type=DataType.FINANCIAL,
        sensitivity=SensitivityLevel.RESTRICTED,
        patterns=[PII_PATTERNS["credit_card"]],
        field_names=["card", "cc", "credit_card", "card_number", "pan", "payment"],
        weight=2.0,
        metadata={"pci_dss": True},
    ),
    ClassificationRule(
        rule_id="R004",
        name="PII - Phone",
        data_type=DataType.PII,
        sensitivity=SensitivityLevel.CONFIDENTIAL,
        patterns=[PII_PATTERNS["phone_us"]],
        field_names=["phone", "mobile", "cell", "contact", "telephone", "tel"],
        weight=1.0,
    ),
    ClassificationRule(
        rule_id="R005",
        name="PII - IP Address",
        data_type=DataType.PII,
        sensitivity=SensitivityLevel.INTERNAL,
        patterns=[PII_PATTERNS["ip_address"]],
        field_names=["ip", "ip_addr", "ip_address", "remote_addr", "client_ip"],
        weight=0.5,
    ),
    ClassificationRule(
        rule_id="R006",
        name="PII - Date of Birth",
        data_type=DataType.PII,
        sensitivity=SensitivityLevel.CONFIDENTIAL,
        patterns=[PII_PATTERNS["dob"]],
        field_names=["dob", "birth", "birth_date", "date_of_birth", "birthday"],
        weight=1.0,
    ),
    ClassificationRule(
        rule_id="R007",
        name="Financial - Bank Account",
        data_type=DataType.FINANCIAL,
        sensitivity=SensitivityLevel.RESTRICTED,
        patterns=[PII_PATTERNS["bank_account"]],
        field_names=["account", "acct", "bank", "iban", "routing", "sort_code"],
        weight=2.0,
    ),
    ClassificationRule(
        rule_id="R008",
        name="Medical - Generic",
        data_type=DataType.MEDICAL,
        sensitivity=SensitivityLevel.CONFIDENTIAL,
        keywords=[
            "diagnosis", "patient", "treatment", "prescription",
            "medical", "health", "clinical", "doctor", "hospital",
            "symptom", "condition", "therapy", "medication", "pharmacy",
        ],
        field_names=[
            "diagnosis", "patient", "treatment", "medical", "health",
            "clinical", "prescription", "medication", "symptom",
        ],
        weight=1.5,
    ),
    ClassificationRule(
        rule_id="R009",
        name="Legal",
        data_type=DataType.LEGAL,
        sensitivity=SensitivityLevel.CONFIDENTIAL,
        keywords=[
            "contract", "agreement", "nda", "lawsuit", "litigation",
            "attorney", "lawyer", "legal", "court", "jurisdiction",
            "terms of service", "tos", "privacy policy",
        ],
        field_names=[
            "contract", "legal", "agreement", "nda", "tos",
            "terms", "policy", "clause", "provision",
        ],
        weight=1.0,
    ),
    ClassificationRule(
        rule_id="R010",
        name="IP - Intellectual Property",
        data_type=DataType.IP,
        sensitivity=SensitivityLevel.RESTRICTED,
        keywords=[
            "proprietary", "trade secret", "patent", "copyright",
            "intellectual property", "source code", "algorithm",
            "blueprint", "formula", "design document",
        ],
        field_names=[
            "algorithm", "patent", "trade_secret", "proprietary",
            "source_code", "blueprint",
        ],
        weight=2.0,
    ),
    ClassificationRule(
        rule_id="R011",
        name="AI Training Data",
        data_type=DataType.AI_TRAINING,
        sensitivity=SensitivityLevel.INTERNAL,
        keywords=[
            "training", "dataset", "corpus", "labeled", "annotation",
            "fine-tune", "embedding", "vector", "token",
        ],
        field_names=[
            "embedding", "vector", "training_data", "corpus",
            "annotation", "labels",
        ],
        weight=0.8,
    ),
    ClassificationRule(
        rule_id="R012",
        name="AI Memory",
        data_type=DataType.AI_MEMORY,
        sensitivity=SensitivityLevel.CONFIDENTIAL,
        keywords=[
            "memory", "context", "persona", "conversation_history",
            "agent_state", "preference", "user_profile",
        ],
        field_names=[
            "memory", "persona", "agent_state", "context",
            "user_profile", "conversation",
        ],
        weight=1.2,
    ),
    ClassificationRule(
        rule_id="R013",
        name="Customer Data",
        data_type=DataType.CUSTOMER,
        sensitivity=SensitivityLevel.CONFIDENTIAL,
        keywords=[
            "customer", "client", "account", "subscription",
            "order", "purchase", "invoice",
        ],
        field_names=[
            "customer", "client", "account", "subscription",
            "order", "purchase", "billing",
        ],
        weight=1.0,
    ),
    ClassificationRule(
        rule_id="R014",
        name="Secrets / Keys",
        data_type=DataType.FINANCIAL,
        sensitivity=SensitivityLevel.RESTRICTED,
        patterns=[
            PII_PATTERNS["api_key"],
            PII_PATTERNS["aws_key"],
            PII_PATTERNS["private_key_header"],
        ],
        field_names=[
            "api_key", "secret", "password", "token", "credential",
            "private_key", "access_key", "auth",
        ],
        weight=3.0,
    ),
    ClassificationRule(
        rule_id="R015",
        name="Operational Data",
        data_type=DataType.OPERATIONAL,
        sensitivity=SensitivityLevel.INTERNAL,
        keywords=[
            "log", "metric", "event", "trace", "debug",
            "performance", "throughput", "latency", "uptime",
        ],
        field_names=[
            "log", "metric", "event", "trace", "debug",
            "timestamp", "created_at", "updated_at",
        ],
        weight=0.5,
    ),
]


# ─── Classification Result ────────────────────────────────────────────────────

@dataclass
class ClassificationResult:
    """Result of classifying a single field or dataset."""
    data_type: DataType
    sensitivity: SensitivityLevel
    confidence: ClassificationConfidence
    score: float
    matched_rules: List[str]
    pii_detected: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    classified_at: datetime = field(default_factory=datetime.utcnow)
    classifier_version: str = "1.0.0"

    @property
    def requires_encryption(self) -> bool:
        return self.sensitivity in (
            SensitivityLevel.CONFIDENTIAL,
            SensitivityLevel.RESTRICTED,
        )

    @property
    def requires_consent(self) -> bool:
        return self.data_type in (
            DataType.PII, DataType.MEDICAL, DataType.AI_MEMORY,
        )

    @property
    def export_restricted(self) -> bool:
        return self.sensitivity in (
            SensitivityLevel.CONFIDENTIAL,
            SensitivityLevel.RESTRICTED,
        ) or self.data_type in (DataType.FINANCIAL, DataType.MEDICAL)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "data_type": self.data_type.value,
            "sensitivity": self.sensitivity.value,
            "confidence": self.confidence.value,
            "score": self.score,
            "matched_rules": self.matched_rules,
            "pii_detected": self.pii_detected,
            "warnings": self.warnings,
            "metadata": self.metadata,
            "classified_at": self.classified_at.isoformat(),
            "classifier_version": self.classifier_version,
            "requires_encryption": self.requires_encryption,
            "requires_consent": self.requires_consent,
            "export_restricted": self.export_restricted,
        }


# ─── Main Classifier ──────────────────────────────────────────────────────────

class DataClassifier:
    """
    Enterprise data classification engine.

    Classifies data fields and records by sensitivity, data type,
    and detects PII patterns. Supports custom rule registration.

    Usage:
        classifier = DataClassifier()
        result = classifier.classify_field("email", "user@example.com")
        dataset_results = classifier.classify_dataset({"email": "..."})
    """

    def __init__(
        self,
        rules: Optional[List[ClassificationRule]] = None,
        pii_patterns: Optional[Dict[str, re.Pattern]] = None,
    ):
        self._rules: Dict[str, ClassificationRule] = {}
        self._pii_patterns = pii_patterns or dict(PII_PATTERNS)
        self._classification_count = 0
        self._last_classification: Optional[datetime] = None

        # Register default rules
        for rule in (rules or DEFAULT_RULES):
            self.register_rule(rule)

    # ── Rule Management ──────────────────────────────────────────────────

    def register_rule(self, rule: ClassificationRule) -> None:
        """Register a classification rule."""
        self._rules[rule.rule_id] = rule

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a classification rule by ID."""
        if rule_id in self._rules:
            del self._rules[rule_id]
            return True
        return False

    def get_rules(self) -> List[ClassificationRule]:
        """Get all registered rules."""
        return list(self._rules.values())

    def get_rules_by_type(self, data_type: DataType) -> List[ClassificationRule]:
        """Get rules matching a specific data type."""
        return [r for r in self._rules.values() if r.data_type == data_type]

    # ── PII Detection ────────────────────────────────────────────────────

    def detect_pii(self, value: Any) -> List[Dict[str, Any]]:
        """Detect PII patterns in a value."""
        if value is None:
            return []
        strval = str(value)
        if not strval.strip():
            return []
        detected: List[Dict[str, Any]] = []
        for pii_type, pattern in self._pii_patterns.items():
            matches = pattern.findall(strval)
            for match in matches:
                # Mask the matched value for security
                masked = self._mask_pii_value(str(match))
                detected.append({
                    "type": pii_type,
                    "name": PII_TYPE_NAMES.get(pii_type, pii_type),
                    "masked_value": masked,
                    "length": len(str(match)),
                })
        return detected

    @staticmethod
    def _mask_pii_value(value: str) -> str:
        """Mask a PII value, preserving length."""
        if len(value) <= 4:
            return "*" * len(value)
        return value[:2] + "*" * (len(value) - 4) + value[-2:]

    # ── Classification ───────────────────────────────────────────────────

    def classify_field(
        self,
        field_name: str,
        value: Any,
        context: Optional[Dict[str, Any]] = None,
    ) -> ClassificationResult:
        """Classify a single field by name and value."""
        matched_rules: List[str] = []
        type_scores: Dict[DataType, float] = {}
        sensitivity_scores: List[float] = []
        pii_detected: List[Dict[str, Any]] = []
        warnings: List[str] = []

        # Detect PII
        pii_detected = self.detect_pii(value)
        if pii_detected:
            warnings.append(
                f"PII detected: {[p['name'] for p in pii_detected]}"
            )

        # Evaluate all rules
        for rule in self._rules.values():
            if not rule.enabled:
                continue
            name_match = rule.matches_field_name(field_name)
            value_match, value_conf = rule.matches_value(value)

            if name_match or value_match:
                score = rule.weight
                if name_match and value_match:
                    score *= 1.5  # Boost when both name and value match
                if value_match:
                    score *= (0.5 + 0.5 * value_conf)

                type_scores.setdefault(rule.data_type, 0.0)
                type_scores[rule.data_type] += score
                sensitivity_scores.append(
                    (rule.sensitivity.numeric_level * score)
                )
                matched_rules.append(rule.rule_id)

                if name_match and rule.data_type == DataType.IP:
                    warnings.append(
                        f"Field '{field_name}' matches IP patterns"
                    )

        # Determine best data type
        if type_scores:
            best_type = max(type_scores, key=lambda k: type_scores[k])
            best_score = type_scores[best_type]
        else:
            best_type = DataType.OTHER
            best_score = 0.0

        # Determine sensitivity
        if sensitivity_scores:
            avg_sensitivity_score = (
                sum(sensitivity_scores) / sum(
                    s for s in type_scores.values()
                )
            ) / SensitivityLevel.RESTRICTED.numeric_level
        else:
            avg_sensitivity_score = 0.0

        sensitivity = SensitivityLevel.from_score(
            max(avg_sensitivity_score, best_type.default_sensitivity.numeric_level / 3)
        )

        # Compute confidence
        if len(matched_rules) >= 3:
            confidence = ClassificationConfidence.HIGH
        elif len(matched_rules) >= 1:
            confidence = ClassificationConfidence.MEDIUM
        else:
            confidence = ClassificationConfidence.LOW
            if not pii_detected:
                warnings.append("No classification rules matched; defaulting to OTHER/PUBLIC")

        self._classification_count += 1
        self._last_classification = datetime.utcnow()

        return ClassificationResult(
            data_type=best_type,
            sensitivity=sensitivity,
            confidence=confidence,
            score=round(best_score, 3),
            matched_rules=matched_rules,
            pii_detected=pii_detected,
            warnings=warnings,
            metadata={"field_name": field_name, **(context or {})},
        )

    def classify_dataset(
        self,
        data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, ClassificationResult]:
        """Classify all fields in a dataset/record."""
        results: Dict[str, ClassificationResult] = {}
        for field_name, value in data.items():
            results[field_name] = self.classify_field(
                field_name, value, context
            )
        return results

    def classify_dataframe(
        self,
        df: Any,
        sample_size: Optional[int] = 100,
    ) -> Dict[str, ClassificationResult]:
        """
        Classify columns in a pandas DataFrame.
        Requires pandas to be installed.
        """
        import pandas as pd

        if not isinstance(df, pd.DataFrame):
            raise TypeError("Expected pandas DataFrame")

        results: Dict[str, ClassificationResult] = {}
        sample = df.head(sample_size) if sample_size else df

        for col in df.columns:
            # Sample values for classification
            values = sample[col].dropna().astype(str).tolist()
            combined_value = " | ".join(values[:min(10, len(values))])
            results[col] = self.classify_field(
                col, combined_value,
                context={"column_dtype": str(df[col].dtype), "null_count": int(df[col].isna().sum())},
            )
        return results

    def get_dataset_summary(
        self,
        dataset_results: Dict[str, ClassificationResult],
    ) -> Dict[str, Any]:
        """Generate a summary of dataset classification results."""
        sensitivity_counts: Dict[str, int] = {}
        type_counts: Dict[str, int] = {}
        pii_fields: List[str] = []
        warnings_list: List[str] = []

        for field, result in dataset_results.items():
            sensitivity_counts.setdefault(result.sensitivity.value, 0)
            sensitivity_counts[result.sensitivity.value] += 1
            type_counts.setdefault(result.data_type.value, 0)
            type_counts[result.data_type.value] += 1
            if result.pii_detected:
                pii_fields.append(field)
            warnings_list.extend(result.warnings)

        return {
            "total_fields": len(dataset_results),
            "sensitivity_distribution": sensitivity_counts,
            "type_distribution": type_counts,
            "pii_fields": pii_fields,
            "pii_field_count": len(pii_fields),
            "restricted_fields": [
                f for f, r in dataset_results.items()
                if r.sensitivity == SensitivityLevel.RESTRICTED
            ],
            "confidential_fields": [
                f for f, r in dataset_results.items()
                if r.sensitivity == SensitivityLevel.CONFIDENTIAL
            ],
            "warnings": warnings_list,
            "requires_encryption": [
                f for f, r in dataset_results.items() if r.requires_encryption
            ],
            "requires_consent": [
                f for f, r in dataset_results.items() if r.requires_consent
            ],
        }

    # ── Utility ──────────────────────────────────────────────────────────

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "total_rules": len(self._rules),
            "rules_by_type": {
                dt.value: len(self.get_rules_by_type(dt))
                for dt in DataType
            },
            "classifications_performed": self._classification_count,
            "last_classification": (
                self._last_classification.isoformat()
                if self._last_classification else None
            ),
        }

    def suggest_classification(
        self,
        field_name: str,
        sample_values: List[Any],
    ) -> ClassificationResult:
        """Suggest classification based on field name and sample values."""
        combined = " | ".join(str(v) for v in sample_values[:20])
        return self.classify_field(field_name, combined)

    def validate_classification(
        self,
        current: ClassificationResult,
        field_name: str,
        sample_values: List[Any],
    ) -> Dict[str, Any]:
        """Validate an existing classification against current analysis."""
        suggested = self.suggest_classification(field_name, sample_values)
        changed = (
            suggested.data_type != current.data_type
            or suggested.sensitivity.numeric_level != current.sensitivity.numeric_level
        )
        return {
            "changed": changed,
            "current_type": current.data_type.value,
            "suggested_type": suggested.data_type.value,
            "current_sensitivity": current.sensitivity.value,
            "suggested_sensitivity": suggested.sensitivity.value,
            "current_score": current.score,
            "suggested_score": suggested.score,
            "new_matches": [
                r for r in suggested.matched_rules
                if r not in current.matched_rules
            ],
        }