"""
Data Quality Engine
Measures and monitors data quality across 8 dimensions:
  Accuracy, Completeness, Freshness, Consistency, Uniqueness,
  Timeliness, Reliability, AI Readiness.

Detects: missing values, duplicates, corruption, schema drift,
         data drift, invalid relationships.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

import math


# ─── Quality Dimension Enums ──────────────────────────────────────────────────

class QualityDimension(str, Enum):
    """The 8 dimensions of data quality."""
    ACCURACY = "accuracy"
    COMPLETENESS = "completeness"
    FRESHNESS = "freshness"
    CONSISTENCY = "consistency"
    UNIQUENESS = "uniqueness"
    TIMELINESS = "timeliness"
    RELIABILITY = "reliability"
    AI_READINESS = "ai_readiness"


class QualityStatus(str, Enum):
    """Overall quality status."""
    EXCELLENT = "excellent"  # >= 95%
    GOOD = "good"            # >= 85%
    FAIR = "fair"            # >= 70%
    POOR = "poor"            # >= 50%
    CRITICAL = "critical"     # < 50%


# ─── Quality Metric ───────────────────────────────────────────────────────────

@dataclass
class QualityMetric:
    """A single quality measurement."""
    dimension: QualityDimension
    score: float  # 0.0 to 1.0
    threshold: float = 0.85
    details: Dict[str, Any] = field(default_factory=dict)
    measured_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def passed(self) -> bool:
        return self.score >= self.threshold

    @property
    def status(self) -> QualityStatus:
        return QualityEngine.score_to_status(self.score)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dimension": self.dimension.value,
            "score": round(self.score, 4),
            "threshold": self.threshold,
            "passed": self.passed,
            "status": self.status.value,
            "details": self.details,
            "measured_at": self.measured_at.isoformat(),
        }


# ─── Quality Rule ─────────────────────────────────────────────────────────────

@dataclass
class QualityRule:
    """A rule for checking a specific quality dimension."""
    rule_id: str
    name: str
    dimension: QualityDimension
    check_fn: Callable[[Any], Tuple[bool, float, Dict[str, Any]]]
    threshold: float = 0.85
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


# ─── Anomaly Types ────────────────────────────────────────────────────────────

@dataclass
class DataAnomaly:
    """Detected data anomaly."""
    anomaly_type: str  # missing, duplicate, corruption, drift, schema, relationship
    field_name: str
    description: str
    severity: str  # low, medium, high, critical
    detected_at: datetime = field(default_factory=datetime.utcnow)
    sample_values: List[Any] = field(default_factory=list)
    affected_count: int = 0
    total_count: int = 0
    suggestion: Optional[str] = None

    @property
    def affected_percentage(self) -> float:
        if self.total_count == 0:
            return 0.0
        return self.affected_count / self.total_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            "anomaly_type": self.anomaly_type,
            "field_name": self.field_name,
            "description": self.description,
            "severity": self.severity,
            "detected_at": self.detected_at.isoformat(),
            "sample_values": self.sample_values[:10],
            "affected_count": self.affected_count,
            "total_count": self.total_count,
            "affected_percentage": round(self.affected_percentage, 4),
            "suggestion": self.suggestion,
        }


# ─── Main Quality Engine ──────────────────────────────────────────────────────

class QualityEngine:
    """
    Enterprise data quality engine.

    Measures quality across 8 dimensions and detects common data issues.
    Supports custom quality rules and thresholds.

    Usage:
        engine = QualityEngine()
        report = engine.assess_dataset(records, schema)
        anomalies = engine.detect_anomalies(records, schema)
    """

    def __init__(self, rules: Optional[List[QualityRule]] = None):
        self._rules: Dict[str, QualityRule] = {}
        self._custom_checks: List[Callable] = []
        if rules:
            for rule in rules:
                self.add_rule(rule)
        self._setup_default_rules()

    def _setup_default_rules(self) -> None:
        """Set up built-in quality rules."""
        # Completeness check
        self.add_rule(QualityRule(
            rule_id="Q001",
            name="Missing Values Check",
            dimension=QualityDimension.COMPLETENESS,
            check_fn=self._check_completeness,
            threshold=0.95,
        ))
        # Uniqueness check
        self.add_rule(QualityRule(
            rule_id="Q002",
            name="Duplicate Detection",
            dimension=QualityDimension.UNIQUENESS,
            check_fn=self._check_uniqueness,
            threshold=0.95,
        ))
        # Freshness check
        self.add_rule(QualityRule(
            rule_id="Q003",
            name="Data Freshness",
            dimension=QualityDimension.FRESHNESS,
            check_fn=self._check_freshness,
            threshold=0.90,
        ))
        # Consistency check
        self.add_rule(QualityRule(
            rule_id="Q004",
            name="Format Consistency",
            dimension=QualityDimension.CONSISTENCY,
            check_fn=self._check_consistency,
            threshold=0.90,
        ))
        # Accuracy check
        self.add_rule(QualityRule(
            rule_id="Q005",
            name="Value Range Accuracy",
            dimension=QualityDimension.ACCURACY,
            check_fn=self._check_accuracy,
            threshold=0.95,
        ))
        # AI Readiness check
        self.add_rule(QualityRule(
            rule_id="Q006",
            name="AI/ML Readiness",
            dimension=QualityDimension.AI_READINESS,
            check_fn=self._check_ai_readiness,
            threshold=0.85,
        ))

    # ── Rule Management ──────────────────────────────────────────────────

    def add_rule(self, rule: QualityRule) -> None:
        self._rules[rule.rule_id] = rule

    def remove_rule(self, rule_id: str) -> bool:
        if rule_id in self._rules:
            del self._rules[rule_id]
            return True
        return False

    def get_rules(self) -> List[QualityRule]:
        return list(self._rules.values())

    # ── Quality Checks ───────────────────────────────────────────────────

    def _check_completeness(
        self, data: Any
    ) -> Tuple[bool, float, Dict[str, Any]]:
        """Check for missing/null values."""
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            records = [data]
        else:
            return True, 1.0, {"error": "Unsupported data format"}

        if not records:
            return True, 1.0, {"total_records": 0}

        total_fields = 0
        missing_fields = 0
        field_missing: Dict[str, int] = defaultdict(int)
        total = len(records)

        for record in records:
            if isinstance(record, dict):
                for key, val in record.items():
                    total_fields += 1
                    if val is None or (isinstance(val, str) and not val.strip()):
                        missing_fields += 1
                        field_missing[key] += 1

        if total_fields == 0:
            return True, 1.0, {"total_records": total}

        completeness = 1.0 - (missing_fields / total_fields)
        passed = completeness >= 0.95

        return passed, completeness, {
            "total_records": total,
            "total_fields": total_fields,
            "missing_fields": missing_fields,
            "field_missing_counts": dict(field_missing),
        }

    def _check_uniqueness(
        self, data: Any
    ) -> Tuple[bool, float, Dict[str, Any]]:
        """Check for duplicate records."""
        if not isinstance(data, list):
            return True, 1.0, {"error": "List expected for uniqueness check"}

        if not data:
            return True, 1.0, {"total_records": 0}

        total = len(data)
        seen = set()
        duplicates = 0

        for record in data:
            if isinstance(record, dict):
                # Hash the record for comparison
                record_hash = hashlib.md5(
                    json.dumps(record, sort_keys=True, default=str).encode()
                ).hexdigest()
            else:
                record_hash = str(record)
            if record_hash in seen:
                duplicates += 1
            seen.add(record_hash)

        uniqueness = 1.0 - (duplicates / max(total, 1))
        passed = uniqueness >= 0.95

        return passed, uniqueness, {
            "total_records": total,
            "unique_records": len(seen),
            "duplicate_records": duplicates,
        }

    def _check_freshness(
        self, data: Any
    ) -> Tuple[bool, float, Dict[str, Any]]:
        """Check if data is recent/fresh."""
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            records = [data]
        else:
            return True, 1.0, {"error": "Unsupported data format"}

        if not records:
            return True, 1.0, {"total_records": 0}

        time_fields = [
            "updated_at", "created_at", "timestamp", "date", "last_modified",
            "modified_at", "dt", "time", "event_time", "ingestion_time",
        ]

        now = datetime.utcnow()
        stale_count = 0
        checked = 0
        max_age_days = 30  # Default max age

        for record in records:
            if not isinstance(record, dict):
                continue
            for tf in time_fields:
                if tf in record or any(
                    k.lower().replace('_', '') == tf for k in record
                ):
                    val = record.get(tf) or record.get(
                        next((k for k in record if k.lower().replace('_', '') == tf), None)
                    )
                    if val:
                        try:
                            if isinstance(val, str):
                                val = datetime.fromisoformat(val.replace('Z', '+00:00'))
                            if isinstance(val, datetime):
                                checked += 1
                                age = (now - val.replace(tzinfo=None)).days
                                if age > max_age_days:
                                    stale_count += 1
                        except (ValueError, TypeError):
                            pass
                    break

        if checked == 0:
            return True, 1.0, {"message": "No timestamp fields found to check freshness"}

        freshness = 1.0 - (stale_count / max(checked, 1))
        passed = freshness >= 0.90

        return passed, freshness, {
            "checked_records": checked,
            "stale_records": stale_count,
            "max_age_days": max_age_days,
        }

    def _check_consistency(
        self, data: Any
    ) -> Tuple[bool, float, Dict[str, Any]]:
        """Check format and type consistency across records."""
        if not isinstance(data, list):
            return True, 1.0, {"error": "List expected"}

        if len(data) < 2:
            return True, 1.0, {"total_records": len(data)}

        total = len(data)
        inconsistent = 0
        format_violations: List[Dict[str, Any]] = []

        # Collect field types across records
        field_types: Dict[str, Set[type]] = defaultdict(set)
        field_formats: Dict[str, Counter] = defaultdict(Counter)

        for record in data:
            if not isinstance(record, dict):
                continue
            for key, val in record.items():
                if val is not None:
                    field_types[key].add(type(val))
                    if isinstance(val, str):
                        # Detect format pattern
                        fmt = self._detect_string_format(val)
                        if fmt:
                            field_formats[key][fmt] += 1

        # Check type consistency
        for field, types in field_types.items():
            if len(types) > 1:
                inconsistent += 1
                format_violations.append({
                    "field": field,
                    "types": [t.__name__ for t in types],
                })

        # Check format consistency
        for field, formats in field_formats.items():
            total_vals = sum(formats.values())
            dominant = formats.most_common(1)
            if dominant:
                dominant_pct = dominant[0][1] / total_vals
                if dominant_pct < 0.90 and total_vals > 5:
                    inconsistent += 1
                    format_violations.append({
                        "field": field,
                        "formats": dict(formats.most_common(3)),
                        "dominant_percentage": round(dominant_pct, 3),
                    })

        consistency = 1.0 - (inconsistent / max(len(field_types) + len(field_formats), 1))
        passed = consistency >= 0.90

        return passed, consistency, {
            "total_records": total,
            "fields_with_type_inconsistency": sum(
                1 for types in field_types.values() if len(types) > 1
            ),
            "format_violations": format_violations[:10],
        }

    def _check_accuracy(
        self, data: Any
    ) -> Tuple[bool, float, Dict[str, Any]]:
        """Check value accuracy: ranges, constraints, expected patterns."""
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            records = [data]
        else:
            return True, 1.0, {"error": "Unsupported format"}

        if not records:
            return True, 1.0, {"total_records": 0}

        # Known field constraints
        constraints: Dict[str, Dict[str, Any]] = {
            "age": {"min": 0, "max": 150, "type": int},
            "score": {"min": 0, "max": 100, "type": (int, float)},
            "rating": {"min": 0, "max": 5, "type": (int, float)},
            "percentage": {"min": 0, "max": 100, "type": (int, float)},
            "probability": {"min": 0, "max": 1, "type": float},
            "count": {"min": 0, "type": int},
        }

        total_values = 0
        invalid_values = 0
        violations: List[Dict] = []

        for record in records:
            if not isinstance(record, dict):
                continue
            for key, val in record.items():
                if val is None:
                    continue
                total_values += 1
                key_lower = key.lower()

                # Check against known constraints
                for constraint_key, constraint in constraints.items():
                    if constraint_key in key_lower:
                        try:
                            if "type" in constraint:
                                expected_type = constraint["type"]
                                if not isinstance(val, expected_type):
                                    try:
                                        if expected_type == int:
                                            int(val)
                                        elif expected_type == float:
                                            float(val)
                                        elif isinstance(expected_type, tuple):
                                            if not isinstance(val, expected_type):
                                                continue
                                    except (ValueError, TypeError):
                                        invalid_values += 1
                                        violations.append({
                                            "field": key,
                                            "value": str(val),
                                            "reason": f"Expected {constraint_key} type",
                                        })
                                        continue

                            num_val = float(val)
                            if "min" in constraint and num_val < constraint["min"]:
                                invalid_values += 1
                                violations.append({
                                    "field": key,
                                    "value": num_val,
                                    "reason": f"Below minimum {constraint['min']}",
                                })
                            if "max" in constraint and num_val > constraint["max"]:
                                invalid_values += 1
                                violations.append({
                                    "field": key,
                                    "value": num_val,
                                    "reason": f"Above maximum {constraint['max']}",
                                })
                        except (ValueError, TypeError):
                            pass

        if total_values == 0:
            return True, 1.0, {"message": "No values to check"}

        accuracy = 1.0 - (invalid_values / total_values)
        passed = accuracy >= 0.95

        return passed, accuracy, {
            "total_values": total_values,
            "invalid_values": invalid_values,
            "violations": violations[:20],
        }

    def _check_ai_readiness(
        self, data: Any
    ) -> Tuple[bool, float, Dict[str, Any]]:
        """Check if data is ready for AI/ML consumption."""
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            records = [data]
        else:
            return True, 1.0, {"error": "Unsupported format"}

        if not records:
            return True, 0.0, {"message": "No data to assess"}

        score_components: Dict[str, float] = {}
        total_records = len(records)

        # 1. Label/annotation quality (if applicable)
        has_labels = False
        label_quality = 1.0
        label_fields = ["label", "target", "class", "category", "tag", "annotation"]
        labeled_count = 0
        for record in records:
            if isinstance(record, dict):
                for lf in label_fields:
                    if lf in record:
                        has_labels = True
                        if record[lf] is not None:
                            labeled_count += 1
                        break
        if has_labels:
            label_quality = labeled_count / total_records
        score_components["label_coverage"] = label_quality

        # 2. Data volume adequacy
        volume_score = min(1.0, total_records / 1000)  # 1000 records = good
        score_components["volume_adequacy"] = volume_score

        # 3. Feature diversity
        if records and isinstance(records[0], dict):
            fields = len(records[0])
            feature_score = min(1.0, fields / 10)  # 10+ features = good
        else:
            feature_score = 0.5
        score_components["feature_diversity"] = feature_score

        # 4. Numeric data ratio
        numeric_count = 0
        total_values = 0
        for record in records:
            if isinstance(record, dict):
                for val in record.values():
                    total_values += 1
                    if isinstance(val, (int, float)):
                        numeric_count += 1
        numeric_ratio = numeric_count / max(total_values, 1)
        score_components["numeric_ratio"] = numeric_ratio

        # 5. No free-text blobs dominating
        text_field_count = 0
        long_text_count = 0
        for record in records[:100]:
            if isinstance(record, dict):
                for val in record.values():
                    if isinstance(val, str):
                        text_field_count += 1
                        if len(val) > 1000:
                            long_text_count += 1
        blob_score = 1.0 - (long_text_count / max(text_field_count, 1)) if text_field_count else 1.0
        score_components["text_blob_ratio"] = blob_score

        # Aggregate score
        ai_readiness = sum(score_components.values()) / len(score_components)
        passed = ai_readiness >= 0.85

        return passed, ai_readiness, {
            "components": score_components,
            "total_records": total_records,
        }

    # ── Anomaly Detection ─────────────────────────────────────────────────

    def detect_anomalies(
        self,
        data: Union[List[Dict], Dict],
        schema: Optional[Dict[str, Any]] = None,
        known_relationships: Optional[List[Dict[str, str]]] = None,
    ) -> List[DataAnomaly]:
        """Detect all types of data anomalies."""
        records: List[Dict] = [data] if isinstance(data, dict) else data
        anomalies: List[DataAnomaly] = []

        # Missing values
        anomalies.extend(self._detect_missing_values(records))

        # Duplicates
        anomalies.extend(self._detect_duplicates(records))

        # Data corruption
        anomalies.extend(self._detect_corruption(records, schema))

        # Schema drift
        if schema:
            anomalies.extend(self._detect_schema_drift(records, schema))

        # Data drift
        anomalies.extend(self._detect_data_drift(records))

        # Invalid relationships
        if known_relationships:
            anomalies.extend(self._detect_invalid_relationships(records, known_relationships))

        return anomalies

    def _detect_missing_values(self, records: List[Dict]) -> List[DataAnomaly]:
        anomalies: List[DataAnomaly] = []
        total = len(records)
        if total == 0:
            return anomalies

        field_missing: Dict[str, int] = defaultdict(int)
        for record in records:
            if isinstance(record, dict):
                for key, val in record.items():
                    if val is None or (isinstance(val, str) and not val.strip()):
                        field_missing[key] += 1

        for field, count in field_missing.items():
            pct = count / total
            severity = (
                "critical" if pct > 0.50
                else "high" if pct > 0.25
                else "medium" if pct > 0.10
                else "low"
            )
            anomalies.append(DataAnomaly(
                anomaly_type="missing",
                field_name=field,
                description=f"Field '{field}' has {count}/{total} ({pct:.1%}) missing values",
                severity=severity,
                affected_count=count,
                total_count=total,
                suggestion="Consider imputation, default values, or making field optional",
            ))

        return anomalies

    def _detect_duplicates(self, records: List[Dict]) -> List[DataAnomaly]:
        anomalies: List[DataAnomaly] = []
        total = len(records)
        if total < 2:
            return anomalies

        seen: Dict[str, List[int]] = defaultdict(list)
        for idx, record in enumerate(records):
            rec_hash = hashlib.md5(
                json.dumps(record, sort_keys=True, default=str).encode()
            ).hexdigest()
            seen[rec_hash].append(idx)

        dup_count = sum(len(indices) - 1 for indices in seen.values() if len(indices) > 1)
        if dup_count > 0:
            anomalies.append(DataAnomaly(
                anomaly_type="duplicate",
                field_name="__record__",
                description=f"Found {dup_count} duplicate records out of {total}",
                severity="high" if dup_count / total > 0.10 else "medium",
                affected_count=dup_count,
                total_count=total,
                suggestion="Deduplicate records, identify root cause of duplication",
            ))

        return anomalies

    def _detect_corruption(
        self, records: List[Dict], schema: Optional[Dict[str, Any]]
    ) -> List[DataAnomaly]:
        anomalies: List[DataAnomaly] = []
        total = len(records)
        if total == 0:
            return anomalies

        for record in records:
            if not isinstance(record, dict):
                continue
            for key, val in record.items():
                if isinstance(val, str):
                    # Check for encoding corruption
                    if '\ufffd' in val or '\x00' in val:
                        anomalies.append(DataAnomaly(
                            anomaly_type="corruption",
                            field_name=key,
                            description=f"Encoding corruption detected in field '{key}'",
                            severity="high",
                            sample_values=[val[:100]],
                            affected_count=1,
                            total_count=total,
                            suggestion="Re-encode with proper charset, verify data source encoding",
                        ))

                # Check for truncation
                if isinstance(val, str) and len(val) > 50000:
                    anomalies.append(DataAnomaly(
                        anomaly_type="corruption",
                        field_name=key,
                        description=f"Potential truncation: field '{key}' has abnormally large string ({len(val)} chars)",
                        severity="medium",
                        affected_count=1,
                        total_count=total,
                    ))

                # Check for type mismatches
                if schema and key in schema:
                    expected_type = schema[key]
                    if not isinstance(val, expected_type) and val is not None:
                        anomalies.append(DataAnomaly(
                            anomaly_type="corruption",
                            field_name=key,
                            description=f"Type mismatch: expected {expected_type.__name__}, got {type(val).__name__}",
                            severity="medium",
                            sample_values=[str(val)[:100]],
                            affected_count=1,
                            total_count=total,
                        ))

        return anomalies

    def _detect_schema_drift(
        self, records: List[Dict], schema: Dict[str, Any]
    ) -> List[DataAnomaly]:
        """Detect schema drift: new or missing fields vs expected schema."""
        anomalies: List[DataAnomaly] = []
        total = len(records)
        if total == 0 or not schema:
            return anomalies

        expected_fields = set(schema.keys())
        actual_fields: Set[str] = set()
        field_occurrence: Dict[str, int] = defaultdict(int)

        for record in records:
            if isinstance(record, dict):
                for key in record:
                    actual_fields.add(key)
                    field_occurrence[key] += 1

        # New fields not in schema
        new_fields = actual_fields - expected_fields
        for field in new_fields:
            pct = field_occurrence[field] / total
            anomalies.append(DataAnomaly(
                anomaly_type="schema_drift",
                field_name=field,
                description=f"New field '{field}' not in schema (present in {pct:.1%} of records)",
                severity="medium" if pct > 0.5 else "low",
                affected_count=field_occurrence[field],
                total_count=total,
                suggestion="Update schema definition or investigate source",
            ))

        # Missing fields from schema
        missing_fields = expected_fields - actual_fields
        for field in missing_fields:
            anomalies.append(DataAnomaly(
                anomaly_type="schema_drift",
                field_name=field,
                description=f"Expected field '{field}' missing from all records",
                severity="high",
                affected_count=total,
                total_count=total,
                suggestion="Check data pipeline, may indicate upstream change",
            ))

        # Fields not consistently present
        for field in actual_fields & expected_fields:
            pct = field_occurrence[field] / total
            if pct < 0.90:
                anomalies.append(DataAnomaly(
                    anomaly_type="schema_drift",
                    field_name=field,
                    description=f"Field '{field}' only present in {pct:.1%} of records",
                    severity="low",
                    affected_count=total - field_occurrence[field],
                    total_count=total,
                    suggestion="Ensure consistent field population",
                ))

        return anomalies

    def _detect_data_drift(self, records: List[Dict]) -> List[DataAnomaly]:
        """Detect data drift using statistical distribution analysis."""
        anomalies: List[DataAnomaly] = []
        total = len(records)
        if total < 10:
            return anomalies

        # For each numeric field, check distribution
        numeric_fields: Dict[str, List[float]] = defaultdict(list)
        for record in records:
            if isinstance(record, dict):
                for key, val in record.items():
                    if isinstance(val, (int, float)) and val is not None:
                        numeric_fields[key].append(float(val))

        for field, values in numeric_fields.items():
            if len(values) < 10:
                continue

            # Check for outliers using IQR
            sorted_vals = sorted(values)
            q1_idx = len(sorted_vals) // 4
            q3_idx = 3 * len(sorted_vals) // 4
            q1 = sorted_vals[q1_idx]
            q3 = sorted_vals[q3_idx]
            iqr = q3 - q1
            if iqr == 0:
                continue

            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr
            outliers = [v for v in values if v < lower_bound or v > upper_bound]

            if len(outliers) > len(values) * 0.05:  # More than 5% outliers
                anomalies.append(DataAnomaly(
                    anomaly_type="data_drift",
                    field_name=field,
                    description=(
                        f"Statistical outliers detected in '{field}': "
                        f"{len(outliers)}/{len(values)} ({len(outliers)/len(values):.1%}) "
                        f"outside IQR [{lower_bound:.2f}, {upper_bound:.2f}]"
                    ),
                    severity="medium",
                    sample_values=sorted(outliers)[:5],
                    affected_count=len(outliers),
                    total_count=len(values),
                    suggestion="Investigate data source for unexpected distribution shift",
                ))

        return anomalies

    def _detect_invalid_relationships(
        self, records: List[Dict], relationships: List[Dict[str, str]]
    ) -> List[DataAnomaly]:
        """Detect invalid relationships between fields."""
        anomalies: List[DataAnomaly] = []
        total = len(records)

        for rel in relationships:
            parent = rel.get("parent_field", "")
            child = rel.get("child_field", "")
            rel_type = rel.get("type", "1:1")

            parent_values = set()
            child_counts: Dict[str, int] = defaultdict(int)

            for record in records:
                if isinstance(record, dict):
                    p_val = record.get(parent)
                    c_val = record.get(child)
                    if p_val is not None:
                        parent_values.add(p_val)
                    if c_val is not None and rel_type == "1:1":
                        child_counts[str(c_val)] += 1

            # Check for 1:1 violations
            if rel_type == "1:1":
                violations = [k for k, v in child_counts.items() if v > 1]
                if violations:
                    anomalies.append(DataAnomaly(
                        anomaly_type="invalid_relationship",
                        field_name=f"{parent} -> {child}",
                        description=(
                            f"1:1 relationship violation: {len(violations)} child values "
                            f"appear multiple times"
                        ),
                        severity="medium",
                        sample_values=violations[:5],
                        affected_count=len(violations),
                        total_count=total,
                        suggestion="Check for unintended duplicates in child field",
                    ))

            # Check orphaned children
            if rel.get("check_orphans", False):
                present_parents = parent_values
                orphan_count = 0
                for record in records:
                    if isinstance(record, dict):
                        c_val = record.get(child)
                        p_val = record.get(parent)
                        if c_val is not None and p_val not in present_parents:
                            orphan_count += 1
                if orphan_count > 0:
                    anomalies.append(DataAnomaly(
                        anomaly_type="invalid_relationship",
                        field_name=f"{parent} -> {child}",
                        description=f"Orphaned child records: {orphan_count}",
                        severity="high",
                        affected_count=orphan_count,
                        total_count=total,
                        suggestion="Restore missing parent records or clean up orphans",
                    ))

        return anomalies

    # ── Main Assessment ───────────────────────────────────────────────────

    def assess_dataset(
        self,
        data: Union[List[Dict], Dict],
        schema: Optional[Dict[str, Any]] = None,
        relationships: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Run a comprehensive quality assessment."""
        records: List[Dict] = [data] if isinstance(data, dict) else data

        # Run all quality checks
        metrics: List[QualityMetric] = []
        for rule in self._rules.values():
            if not rule.enabled:
                continue
            try:
                passed, score, details = rule.check_fn(records)
                metrics.append(QualityMetric(
                    dimension=rule.dimension,
                    score=score,
                    threshold=rule.threshold,
                    details=details,
                ))
            except Exception as e:
                metrics.append(QualityMetric(
                    dimension=rule.dimension,
                    score=0.0,
                    threshold=rule.threshold,
                    details={"error": str(e)},
                ))

        # Run anomaly detection
        anomalies = self.detect_anomalies(records, schema, relationships)

        # Compute overall score
        overall_score = self._compute_overall_score(metrics) if metrics else 0.0
        overall_status = self.score_to_status(overall_score)

        # Compute dimension scores
        dimension_scores: Dict[str, float] = {}
        for metric in metrics:
            dimension_scores[metric.dimension.value] = metric.score

        return {
            "overall_score": round(overall_score, 4),
            "overall_status": overall_status.value,
            "dimension_scores": dimension_scores,
            "metrics": [m.to_dict() for m in metrics],
            "anomalies": [a.to_dict() for a in anomalies],
            "anomaly_count": len(anomalies),
            "anomaly_severity": {
                "critical": sum(1 for a in anomalies if a.severity == "critical"),
                "high": sum(1 for a in anomalies if a.severity == "high"),
                "medium": sum(1 for a in anomalies if a.severity == "medium"),
                "low": sum(1 for a in anomalies if a.severity == "low"),
            },
            "total_records": len(records),
            "assessed_at": datetime.utcnow().isoformat(),
            "pass": overall_status in (QualityStatus.EXCELLENT, QualityStatus.GOOD),
        }

    @staticmethod
    def _compute_overall_score(metrics: List[QualityMetric]) -> float:
        """Compute weighted overall quality score."""
        if not metrics:
            return 1.0
        weights = {
            QualityDimension.ACCURACY: 0.20,
            QualityDimension.COMPLETENESS: 0.20,
            QualityDimension.FRESHNESS: 0.15,
            QualityDimension.CONSISTENCY: 0.15,
            QualityDimension.UNIQUENESS: 0.10,
            QualityDimension.TIMELINESS: 0.05,
            QualityDimension.RELIABILITY: 0.05,
            QualityDimension.AI_READINESS: 0.10,
        }
        total_weight = 0.0
        weighted_sum = 0.0
        for metric in metrics:
            w = weights.get(metric.dimension, 0.10)
            weighted_sum += metric.score * w
            total_weight += w
        return weighted_sum / total_weight if total_weight > 0 else 1.0

    @staticmethod
    def score_to_status(score: float) -> QualityStatus:
        if score >= 0.95:
            return QualityStatus.EXCELLENT
        elif score >= 0.85:
            return QualityStatus.GOOD
        elif score >= 0.70:
            return QualityStatus.FAIR
        elif score >= 0.50:
            return QualityStatus.POOR
        return QualityStatus.CRITICAL

    @staticmethod
    def _detect_string_format(value: str) -> Optional[str]:
        """Detect string format pattern."""
        import re
        if re.match(r'^\d{4}-\d{2}-\d{2}$', value):
            return "date_iso"
        if re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}', value):
            return "datetime_iso"
        if re.match(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$', value):
            return "email"
        if re.match(r'^https?://', value):
            return "url"
        if re.match(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$', value):
            return "uuid"
        if re.match(r'^\d+$', value):
            return "numeric_string"
        if re.match(r'^[\d.]+$', value):
            return "decimal_string"
        return None