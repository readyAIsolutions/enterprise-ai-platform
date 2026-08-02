"""
AI Safety & Governance OS — Continuous Monitoring Module
========================================================
Enterprise-grade continuous monitoring for AI safety: accuracy drift,
hallucination rates, unsafe outputs, prompt attacks, model/data drift,
user complaints, latency, cost, tool failures, behavior anomalies,
and security event correlation.

All major classes are thread-safe and self-contained.
"""

import re
import time
import math
import json
import logging
import threading
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union
from collections import defaultdict, deque
import statistics

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DriftStatus(Enum):
    """Status of distribution drift detection."""
    STABLE = "stable"
    WARNING = "warning"
    DRIFTING = "drifting"
    CRITICAL = "critical"


class AlertSeverity(Enum):
    """Severity levels for monitoring alerts."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class AttackType(Enum):
    """Types of prompt attacks detected."""
    INJECTION = "injection"
    JAILBREAK = "jailbreak"
    EXTRACTION = "extraction"
    DOS = "dos"
    DATA_EXFILTRATION = "data_exfiltration"
    UNKNOWN = "unknown"


class SLOStatus(Enum):
    """Status of SLO compliance."""
    MET = "met"
    AT_RISK = "at_risk"
    BREACHED = "breached"


class AnomalyType(Enum):
    """Types of behavioral anomalies."""
    LATENCY_SPIKE = "latency_spike"
    ERROR_BURST = "error_burst"
    PATTERN_CHANGE = "pattern_change"
    VOLUME_ANOMALY = "volume_anomaly"
    BEHAVIORAL_SHIFT = "behavioral_shift"


# ---------------------------------------------------------------------------
# Result Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class DriftReport:
    """Report from drift detection analysis."""
    status: DriftStatus = DriftStatus.STABLE
    drift_magnitude: float = 0.0
    baseline_mean: float = 0.0
    current_mean: float = 0.0
    p_value: float = 1.0
    affected_dimensions: List[str] = field(default_factory=list)
    recommendation: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "drift_magnitude": self.drift_magnitude,
            "baseline_mean": self.baseline_mean,
            "current_mean": self.current_mean,
            "p_value": self.p_value,
            "affected_dimensions": self.affected_dimensions,
            "recommendation": self.recommendation,
            "details": self.details,
        }


@dataclass
class Alert:
    """A monitoring alert instance."""
    alert_id: str = ""
    severity: AlertSeverity = AlertSeverity.INFO
    title: str = ""
    description: str = ""
    source: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    acknowledged: bool = False
    resolved: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "acknowledged": self.acknowledged,
            "resolved": self.resolved,
            "metadata": self.metadata,
        }


@dataclass
class SLOReport:
    """Service Level Objective compliance report."""
    slo_name: str = ""
    target_percent: float = 0.0
    current_percent: float = 0.0
    status: SLOStatus = SLOStatus.MET
    error_budget_remaining: float = 0.0
    burn_rate: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slo_name": self.slo_name,
            "target_percent": self.target_percent,
            "current_percent": self.current_percent,
            "status": self.status.value,
            "error_budget_remaining": self.error_budget_remaining,
            "burn_rate": self.burn_rate,
            "details": self.details,
        }


@dataclass
class SecurityEvent:
    """A security-related event for correlation."""
    event_id: str = ""
    event_type: str = ""
    severity: AlertSeverity = AlertSeverity.INFO
    source_ip: str = ""
    user_agent: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    correlated_events: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "severity": self.severity.value,
            "source_ip": self.source_ip,
            "user_agent": self.user_agent,
            "timestamp": self.timestamp.isoformat(),
            "correlated_events": self.correlated_events,
            "details": self.details,
        }


@dataclass
class BehaviorProfile:
    """Behavioral profile for a user or agent."""
    user_id: str = ""
    baseline_latency: float = 0.0
    baseline_request_rate: float = 0.0
    common_endpoints: List[str] = field(default_factory=list)
    deviation_score: float = 0.0
    flags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "baseline_latency": self.baseline_latency,
            "baseline_request_rate": self.baseline_request_rate,
            "common_endpoints": self.common_endpoints,
            "deviation_score": self.deviation_score,
            "flags": self.flags,
        }


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _generate_id(prefix: str = "") -> str:
    """Generate a short unique identifier."""
    import uuid
    return prefix + uuid.uuid4().hex[:12]


def _compute_psi(expected_probs: List[float], actual_probs: List[float]) -> float:
    """Compute Population Stability Index."""
    if len(expected_probs) != len(actual_probs):
        raise ValueError("Expected and actual probability arrays must be same length")
    psi = 0.0
    for e, a in zip(expected_probs, actual_probs):
        e = max(e, 1e-10)
        a = max(a, 1e-10)
        psi += (a - e) * math.log(a / e)
    return psi


def _percentile(sorted_vals: List[float], p: float) -> float:
    """Compute percentile from sorted list."""
    if not sorted_vals:
        return 0.0
    n = len(sorted_vals)
    k = (p / 100.0) * (n - 1)
    f = int(math.floor(k))
    c = int(math.ceil(k))
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


# ---------------------------------------------------------------------------
# 1. AccuracyDriftDetector
# ---------------------------------------------------------------------------

class AccuracyDriftDetector:
    """
    Tracks prediction accuracy over time and detects drift from baseline.

    Maintains a sliding window of correctness flags and supports per-category
    accuracy tracking. Uses statistical comparison between baseline and
    current windows to detect accuracy degradation.
    """

    def __init__(
        self,
        baseline_accuracy: float = 0.0,
        window_size: int = 100,
        drift_threshold: float = 0.05,
    ) -> None:
        self.baseline_accuracy = baseline_accuracy
        self.window_size = window_size
        self.drift_threshold = drift_threshold
        self._predictions: deque = deque(maxlen=window_size)
        self._category_correct: Dict[str, List[bool]] = defaultdict(list)
        self._category_total: Dict[str, int] = defaultdict(int)
        self._lock = threading.RLock()

    def record_prediction(self, correct: bool, category: Optional[str] = None) -> None:
        """Record a single prediction outcome."""
        with self._lock:
            self._predictions.append(1.0 if correct else 0.0)
            if category:
                self._category_correct[category].append(correct)

    def detect_drift(self) -> DriftReport:
        """
        Detect accuracy drift between baseline and current window.

        Returns a DriftReport with status, magnitude, and recommendation.
        """
        with self._lock:
            if len(self._predictions) < 10:
                return DriftReport(
                    status=DriftStatus.STABLE,
                    baseline_mean=self.baseline_accuracy,
                    current_mean=0.0,
                    recommendation="Insufficient data for drift detection.",
                    details={"sample_count": len(self._predictions)},
                )

            current_accuracy = sum(self._predictions) / len(self._predictions)
            drift_magnitude = abs(self.baseline_accuracy - current_accuracy)

            if drift_magnitude > self.drift_threshold * 3:
                status = DriftStatus.CRITICAL
                recommendation = (
                    f"CRITICAL accuracy drift of {drift_magnitude:.4f} detected. "
                    "Immediate investigation required. Consider rollback or model switch."
                )
            elif drift_magnitude > self.drift_threshold * 2:
                status = DriftStatus.DRIFTING
                recommendation = (
                    f"Significant accuracy drift of {drift_magnitude:.4f}. "
                    "Schedule investigation and prepare fallback model."
                )
            elif drift_magnitude > self.drift_threshold:
                status = DriftStatus.WARNING
                recommendation = (
                    f"Minor accuracy drift of {drift_magnitude:.4f}. "
                    "Continue monitoring and review recent inputs."
                )
            else:
                status = DriftStatus.STABLE
                recommendation = "Accuracy is stable within expected thresholds."

            # Identify affected categories
            affected_dimensions = []
            for cat, results in self._category_correct.items():
                if results:
                    cat_acc = sum(1 for r in results[-50:] if r) / min(50, len(results))
                    if abs(self.baseline_accuracy - cat_acc) > self.drift_threshold:
                        affected_dimensions.append(cat)

            # Compute approximate p-value using z-test for proportions
            n = len(self._predictions)
            se = math.sqrt(
                (self.baseline_accuracy * (1 - self.baseline_accuracy)) / n
                + (current_accuracy * (1 - current_accuracy)) / n
            )
            if se > 0:
                z_score = drift_magnitude / se
                p_value = 2 * (1 - 0.5 * (1 + math.erf(abs(z_score) / math.sqrt(2))))
            else:
                p_value = 1.0

            return DriftReport(
                status=status,
                drift_magnitude=drift_magnitude,
                baseline_mean=self.baseline_accuracy,
                current_mean=current_accuracy,
                p_value=p_value,
                affected_dimensions=affected_dimensions,
                recommendation=recommendation,
                details={
                    "sample_count": n,
                    "threshold": self.drift_threshold,
                },
            )

    def get_current_accuracy(self) -> float:
        """Return the current accuracy over the window."""
        with self._lock:
            if not self._predictions:
                return 0.0
            return sum(self._predictions) / len(self._predictions)

    def get_per_category_accuracy(self) -> Dict[str, float]:
        """Return per-category accuracy breakdown."""
        with self._lock:
            result = {}
            for cat, results in self._category_correct.items():
                if results:
                    recent = results[-50:]
                    result[cat] = sum(1 for r in recent if r) / len(recent)
            return result

    def reset_baseline(self, new_baseline: float) -> None:
        """Reset the accuracy baseline to a new value."""
        with self._lock:
            self.baseline_accuracy = new_baseline
            logger.info(f"AccuracyDriftDetector baseline reset to {new_baseline:.4f}")

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "baseline_accuracy": self.baseline_accuracy,
                "window_size": self.window_size,
                "drift_threshold": self.drift_threshold,
                "current_accuracy": self.get_current_accuracy(),
                "sample_count": len(self._predictions),
                "category_accuracy": self.get_per_category_accuracy(),
            }


# ---------------------------------------------------------------------------
# 2. HallucinationRateTracker
# ---------------------------------------------------------------------------

class HallucinationRateTracker:
    """
    Tracks hallucination rate in model outputs over a sliding window.

    Records each output with a hallucination flag and confidence score,
    provides trending information, and triggers alerts when the rate
    exceeds the configured threshold.
    """

    def __init__(self, window_size: int = 500, alert_threshold: float = 0.15) -> None:
        self.window_size = window_size
        self.alert_threshold = alert_threshold
        self._records: deque = deque(maxlen=window_size)
        self._lock = threading.RLock()

    def record_output(self, text: str, is_hallucination: bool, confidence: float = 1.0) -> None:
        """Record a single model output with its hallucination status."""
        with self._lock:
            self._records.append({
                "text": text[:500],
                "is_hallucination": is_hallucination,
                "confidence": confidence,
                "timestamp": datetime.utcnow(),
            })

    def get_trend(self, lookback_hours: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get hallucination rate trend, optionally limited to recent hours.
        Returns a list of per-hour rate data points.
        """
        with self._lock:
            if not self._records:
                return []

            records = list(self._records)
            now = datetime.utcnow()
            if lookback_hours is not None:
                cutoff = now - timedelta(hours=lookback_hours)
                records = [r for r in records if r["timestamp"] >= cutoff]

            if not records:
                return []

            # Group by hour
            by_hour: Dict[str, Dict[str, Any]] = defaultdict(
                lambda: {"total": 0, "hallucinations": 0}
            )
            for r in records:
                hour_key = r["timestamp"].strftime("%Y-%m-%dT%H")
                by_hour[hour_key]["total"] += 1
                if r["is_hallucination"]:
                    by_hour[hour_key]["hallucinations"] += 1

            trend = []
            for hour_key in sorted(by_hour.keys()):
                d = by_hour[hour_key]
                trend.append({
                    "hour": hour_key,
                    "total": d["total"],
                    "hallucinations": d["hallucinations"],
                    "rate": d["hallucinations"] / d["total"] if d["total"] > 0 else 0.0,
                })
            return trend

    def get_current_rate(self) -> float:
        """Get the current hallucination rate over the window."""
        with self._lock:
            if not self._records:
                return 0.0
            hallucinations = sum(1 for r in self._records if r["is_hallucination"])
            return hallucinations / len(self._records)

    def check_alert(self) -> Optional[Alert]:
        """Check if hallucination rate exceeds threshold and generate alert."""
        with self._lock:
            rate = self.get_current_rate()
            if rate >= self.alert_threshold:
                return Alert(
                    alert_id=_generate_id("hal-"),
                    severity=AlertSeverity.WARNING if rate < self.alert_threshold * 2 else AlertSeverity.CRITICAL,
                    title=f"Hallucination Rate Alert: {rate:.2%}",
                    description=(
                        f"Hallucination rate of {rate:.2%} exceeds threshold "
                        f"of {self.alert_threshold:.2%}. "
                        f"Window size: {len(self._records)} outputs."
                    ),
                    source="HallucinationRateTracker",
                    metadata={
                        "current_rate": rate,
                        "threshold": self.alert_threshold,
                        "sample_count": len(self._records),
                    },
                )
            return None

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "window_size": self.window_size,
                "alert_threshold": self.alert_threshold,
                "current_rate": self.get_current_rate(),
                "sample_count": len(self._records),
                "trend_24h": self.get_trend(lookback_hours=24),
            }


# ---------------------------------------------------------------------------
# 3. UnsafeOutputDetector
# ---------------------------------------------------------------------------

class UnsafeOutputDetector:
    """
    Detects unsafe or harmful outputs using pattern matching and confidence scoring.

    Maintains a configurable set of unsafe patterns and tracks detection rates
    over time. Can be extended with ML-based scoring.
    """

    DEFAULT_PATTERNS = [
        r"(?i)\b(hate\s*speech|violence|self-harm|suicide)\b",
        r"(?i)\b(exploit|vulnerability|bypass\s*security)\b",
        r"(?i)\b(personally\s*identifiable|social\s*security|credit\s*card)\b",
        r"(?i)\b(weapon|bomb|explosive|chemical\s*weapon)\b",
        r"(?i)\b(illegal\s*drug|narcotic|trafficking)\b",
    ]

    def __init__(
        self,
        unsafe_patterns: Optional[List[str]] = None,
        ml_threshold: float = 0.6,
    ) -> None:
        self.patterns = [re.compile(p) for p in (unsafe_patterns or self.DEFAULT_PATTERNS)]
        self.ml_threshold = ml_threshold
        self._detections: deque = deque(maxlen=1000)
        self._total_analyzed: int = 0
        self._lock = threading.RLock()

    def analyze(self, output: str) -> Dict[str, Any]:
        """
        Analyze an output string for unsafe content.
        Returns a dict with safety assessment and matched patterns.
        """
        with self._lock:
            self._total_analyzed += 1
            matched_patterns: List[str] = []
            max_confidence = 0.0

            for pattern in self.patterns:
                matches = pattern.findall(output)
                if matches:
                    matched_patterns.append(pattern.pattern)
                    # Simple confidence heuristic based on match count
                    confidence = min(1.0, len(matches) * 0.3)
                    max_confidence = max(max_confidence, confidence)

            is_unsafe = max_confidence >= self.ml_threshold
            return {
                "is_unsafe": is_unsafe,
                "confidence": max_confidence,
                "matched_patterns": matched_patterns,
                "output_length": len(output),
            }

    def is_unsafe(self, output: str) -> bool:
        """Quick check if an output is unsafe."""
        result = self.analyze(output)
        return result["is_unsafe"]

    def record_detection(self, output: str, category: str) -> None:
        """Record a confirmed unsafe detection."""
        with self._lock:
            self._detections.append({
                "output_snippet": output[:300],
                "category": category,
                "timestamp": datetime.utcnow(),
            })

    def get_unsafe_rate(self) -> float:
        """Get the overall rate of unsafe outputs detected."""
        with self._lock:
            if self._total_analyzed == 0:
                return 0.0
            return len(self._detections) / self._total_analyzed

    def get_recent_detections(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get the most recently detected unsafe outputs."""
        with self._lock:
            detections = list(self._detections)
            return [
                {
                    "output_snippet": d["output_snippet"],
                    "category": d["category"],
                    "timestamp": d["timestamp"].isoformat(),
                }
                for d in detections[-limit:]
            ]

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "pattern_count": len(self.patterns),
                "ml_threshold": self.ml_threshold,
                "total_analyzed": self._total_analyzed,
                "detections": len(self._detections),
                "unsafe_rate": self.get_unsafe_rate(),
            }


# ---------------------------------------------------------------------------
# 4. PromptAttackDetector
# ---------------------------------------------------------------------------

class PromptAttackDetector:
    """
    Detects and classifies prompt-based attacks including injection, jailbreak,
    extraction, denial-of-service, and data exfiltration attempts.
    """

    # Common attack heuristics
    INJECTION_PATTERNS = [
        r"(?i)(ignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|directives?|prompts?))",
        r"(?i)(you\s+are\s+now\s+(DAN|jailbroken|unrestricted|free))",
        r"(?i)(system\s*:\s*|\[system\]|<system>)",
        r"(?i)(forget\s+(everything|all\s+rules))",
    ]

    JAILBREAK_PATTERNS = [
        r"(?i)(role\s*play|pretend|imagine\s+you\s+are)",
        r"(?i)(no\s+rules|no\s+restrictions|no\s+limits|without\s+restrictions?)",
        r"(?i)(evil\s+(confidant|twin|version|mode))",
        r"(?i)(developer\s*mode|god\s*mode)",
    ]

    EXTRACTION_PATTERNS = [
        r"(?i)(reveal\s+(your\s+)?(system\s+)?prompt)",
        r"(?i)(show\s+me\s+(your\s+)?(instructions?|training|weights?))",
        r"(?i)(what\s+(are|is)\s+(your\s+)?(instructions?|directives?))",
        r"(?i)(repeat\s+(back\s+)?(everything|the\s+above|your\s+prompt))",
    ]

    DOS_PATTERNS = [
        r"(?i)(repeat\s+(this|the\s+following)\s+\d+\s+times)",
        r"(?i)(infinite\s+(loop|recursion))",
    ]

    EXFILTRATION_PATTERNS = [
        r"(?i)(send\s+(this|the\s+(conversation|chat|data))\s+to)",
        r"(?i)(email\s+(this|me|yourself))",
        r"(?i)(exfiltrate|steal\s+data)",
    ]

    def __init__(self) -> None:
        self._attacks: deque = deque(maxlen=5000)
        self._total_prompts: int = 0
        self._lock = threading.RLock()

    def detect_attack(self, prompt: str, metadata: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
        """
        Detect if a prompt contains an attack pattern.
        Returns attack details dict or None if no attack detected.
        """
        with self._lock:
            self._total_prompts += 1
            attack_type = self.classify_attack(prompt)

            if attack_type == AttackType.UNKNOWN:
                return None

            details = {
                "attack_type": attack_type.value,
                "prompt_snippet": prompt[:500],
                "prompt_length": len(prompt),
                "metadata": metadata or {},
            }
            return details

    def classify_attack(self, prompt: str) -> AttackType:
        """Classify the type of attack in a prompt."""
        # Check each pattern category
        for pattern in self.INJECTION_PATTERNS:
            if re.search(pattern, prompt):
                return AttackType.INJECTION

        for pattern in self.JAILBREAK_PATTERNS:
            if re.search(pattern, prompt):
                return AttackType.JAILBREAK

        for pattern in self.EXTRACTION_PATTERNS:
            if re.search(pattern, prompt):
                return AttackType.EXTRACTION

        for pattern in self.EXFILTRATION_PATTERNS:
            if re.search(pattern, prompt):
                return AttackType.DATA_EXFILTRATION

        for pattern in self.DOS_PATTERNS:
            if re.search(pattern, prompt):
                return AttackType.DOS

        return AttackType.UNKNOWN

    def record_attack(
        self, attack_type: AttackType, source_ip: str, user_id: str, details: Dict
    ) -> None:
        """Record a confirmed attack event."""
        with self._lock:
            self._attacks.append({
                "attack_type": attack_type.value,
                "source_ip": source_ip,
                "user_id": user_id,
                "timestamp": datetime.utcnow(),
                "details": details,
            })

    def get_attack_rate(self, window: Optional[timedelta] = None) -> float:
        """Get the attack rate over a time window."""
        with self._lock:
            if self._total_prompts == 0:
                return 0.0

            if window is None:
                return len(self._attacks) / self._total_prompts

            cutoff = datetime.utcnow() - window
            recent_attacks = sum(
                1 for a in self._attacks if a["timestamp"] >= cutoff
            )
            # Approximate: count total prompts in last window as proportion
            return recent_attacks / max(1, self._total_prompts)

    def get_active_threats(self) -> List[Dict[str, Any]]:
        """Get list of active/recent threats."""
        with self._lock:
            cutoff = datetime.utcnow() - timedelta(hours=1)
            threats = []
            for a in self._attacks:
                if a["timestamp"] >= cutoff:
                    threats.append({
                        "attack_type": a["attack_type"],
                        "source_ip": a["source_ip"],
                        "user_id": a["user_id"],
                        "timestamp": a["timestamp"].isoformat(),
                        "details": a["details"],
                    })
            return threats

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "total_prompts_analyzed": self._total_prompts,
                "total_attacks_detected": len(self._attacks),
                "attack_rate": self.get_attack_rate(),
                "active_threats": len(self.get_active_threats()),
            }


# ---------------------------------------------------------------------------
# 5. ModelDriftDetector
# ---------------------------------------------------------------------------

class ModelDriftDetector:
    """
    Detects drift in model output distributions using KL divergence.

    Maintains a reference distribution and compares incoming distributions
    to detect when the model's output behavior has shifted significantly.
    """

    def __init__(self, reference_distribution: Optional[Dict[str, float]] = None) -> None:
        self.reference_distribution: Dict[str, float] = reference_distribution or {}
        self._current_distribution: Dict[str, float] = {}
        self._observation_counts: Dict[str, int] = defaultdict(int)
        self._total_observations: int = 0
        self._lock = threading.RLock()

    def record_output_distribution(self, distribution: Dict[str, float]) -> None:
        """Record a new output distribution observation."""
        with self._lock:
            for key, prob in distribution.items():
                self._observation_counts[key] += 1
            self._total_observations += 1

            # Normalize to probabilities
            self._current_distribution = {}
            for key, count in self._observation_counts.items():
                self._current_distribution[key] = count / self._total_observations

    def compute_kl_divergence(self, p: Dict[str, float], q: Dict[str, float]) -> float:
        """
        Compute Kullback-Leibler divergence: KL(P || Q).
        P is the reference (baseline), Q is the current distribution.
        """
        all_keys = set(p.keys()) | set(q.keys())
        kl = 0.0
        for key in all_keys:
            p_val = p.get(key, 1e-10)
            q_val = q.get(key, 1e-10)
            if p_val > 0:
                kl += p_val * math.log(p_val / q_val)
        return kl

    def detect_drift(self, threshold: float = 0.1) -> DriftReport:
        """
        Detect distribution drift using KL divergence.
        Returns a DriftReport with status and details.
        """
        with self._lock:
            if not self.reference_distribution or not self._current_distribution:
                return DriftReport(
                    status=DriftStatus.STABLE,
                    recommendation="Insufficient data for drift detection.",
                    details={"reference_keys": len(self.reference_distribution),
                             "current_keys": len(self._current_distribution)},
                )

            kl_div = self.compute_kl_divergence(
                self.reference_distribution, self._current_distribution
            )

            if kl_div > threshold * 5:
                status = DriftStatus.CRITICAL
                recommendation = (
                    f"CRITICAL distribution drift (KL={kl_div:.4f}). "
                    "Model output distribution has shifted dramatically."
                )
            elif kl_div > threshold * 2:
                status = DriftStatus.DRIFTING
                recommendation = (
                    f"Significant distribution drift (KL={kl_div:.4f}). "
                    "Investigate model behavior changes."
                )
            elif kl_div > threshold:
                status = DriftStatus.WARNING
                recommendation = (
                    f"Mild distribution drift (KL={kl_div:.4f}). "
                    "Continue monitoring."
                )
            else:
                status = DriftStatus.STABLE
                recommendation = "Output distribution is stable."

            # Affected dimensions are keys with large probability shift
            all_keys = set(self.reference_distribution.keys()) | set(self._current_distribution.keys())
            affected_dimensions = []
            for key in all_keys:
                ref_p = self.reference_distribution.get(key, 0.0)
                cur_p = self._current_distribution.get(key, 0.0)
                if abs(ref_p - cur_p) > 0.05:
                    affected_dimensions.append(key)

            return DriftReport(
                status=status,
                drift_magnitude=kl_div,
                baseline_mean=0.0,
                current_mean=0.0,
                p_value=0.0,
                affected_dimensions=affected_dimensions,
                recommendation=recommendation,
                details={
                    "kl_divergence": kl_div,
                    "threshold": threshold,
                    "total_observations": self._total_observations,
                    "reference_distribution": dict(self.reference_distribution),
                    "current_distribution": dict(self._current_distribution),
                },
            )

    def update_reference(self) -> None:
        """Update the reference distribution to the current distribution."""
        with self._lock:
            self.reference_distribution = dict(self._current_distribution)
            logger.info("ModelDriftDetector reference distribution updated")

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "reference_distribution": self.reference_distribution,
                "total_observations": self._total_observations,
                "current_keys": list(self._current_distribution.keys()),
            }


# ---------------------------------------------------------------------------
# 6. DataDriftDetector
# ---------------------------------------------------------------------------

class DataDriftDetector:
    """
    Detects drift in input data distributions using Population Stability Index (PSI).

    Monitors feature-level distributions over time and flags features
    that have shifted significantly from the reference period.
    """

    def __init__(self, reference_stats: Optional[Dict[str, Dict[str, float]]] = None) -> None:
        self.reference_stats: Dict[str, Dict[str, float]] = reference_stats or {}
        self._feature_values: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.RLock()

    def record_batch(self, features: Dict[str, List[float]]) -> None:
        """Record a batch of feature values."""
        with self._lock:
            for feature, values in features.items():
                self._feature_values[feature].extend(values)
                # Cap per-feature storage
                if len(self._feature_values[feature]) > 10000:
                    self._feature_values[feature] = self._feature_values[feature][-5000:]

    def compute_psi(self, feature: str) -> float:
        """
        Compute Population Stability Index for a feature.

        Bins the reference and current distributions and applies the PSI formula.
        """
        with self._lock:
            if feature not in self._feature_values or not self._feature_values[feature]:
                return 0.0

            current_values = self._feature_values[feature][-1000:]
            if not current_values:
                return 0.0

            ref_stats = self.reference_stats.get(feature)
            if not ref_stats:
                return 0.0

            # Use 10 bins based on reference min/max
            ref_min = ref_stats.get("min", 0.0)
            ref_max = ref_stats.get("max", 1.0)
            if ref_max <= ref_min:
                ref_max = ref_min + 1.0

            bin_edges = [ref_min + i * (ref_max - ref_min) / 10 for i in range(11)]
            ref_count = ref_stats.get("count", 0)

            psi_total = 0.0
            for i in range(10):
                lower, upper = bin_edges[i], bin_edges[i + 1]
                # Reference proportion (estimate from stats)
                if ref_count > 0:
                    ref_prop = 0.1  # Equal mass assumption if no detailed bins
                else:
                    ref_prop = 0.0

                # Current proportion
                in_bin = sum(1 for v in current_values if lower <= v < upper)
                cur_prop = in_bin / len(current_values) if current_values else 0.0

                ref_prop = max(ref_prop, 1e-6)
                cur_prop = max(cur_prop, 1e-6)

                if cur_prop > 0:
                    psi_total += (cur_prop - ref_prop) * math.log(cur_prop / ref_prop)

            return psi_total

    def detect_drift(self, threshold: float = 0.25) -> List[DriftReport]:
        """
        Detect data drift across all tracked features.
        Returns a list of DriftReports, one per drifted feature.
        """
        with self._lock:
            reports: List[DriftReport] = []

            for feature in self._feature_values:
                psi = self.compute_psi(feature)

                if psi > threshold:
                    ref_stats = self.reference_stats.get(feature, {})
                    current_vals = self._feature_values[feature][-500:]
                    current_mean = statistics.mean(current_vals) if current_vals else 0.0

                    if psi > threshold * 3:
                        status = DriftStatus.CRITICAL
                    elif psi > threshold * 2:
                        status = DriftStatus.DRIFTING
                    else:
                        status = DriftStatus.WARNING

                    reports.append(DriftReport(
                        status=status,
                        drift_magnitude=psi,
                        baseline_mean=ref_stats.get("mean", 0.0),
                        current_mean=current_mean,
                        p_value=0.0,
                        affected_dimensions=[feature],
                        recommendation=(
                            f"Data drift detected for feature '{feature}' "
                            f"(PSI={psi:.4f}). Review data pipeline and input distributions."
                        ),
                        details={
                            "feature": feature,
                            "psi": psi,
                            "threshold": threshold,
                            "reference_stats": ref_stats,
                        },
                    ))

            return reports

    def update_reference(self) -> None:
        """Update reference statistics from current feature values."""
        with self._lock:
            for feature, values in self._feature_values.items():
                if values:
                    self.reference_stats[feature] = {
                        "mean": statistics.mean(values),
                        "std": statistics.stdev(values) if len(values) > 1 else 0.0,
                        "min": min(values),
                        "max": max(values),
                        "count": len(values),
                    }
            logger.info(f"DataDriftDetector reference updated for {len(self.reference_stats)} features")

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "tracked_features": list(self._feature_values.keys()),
                "reference_features": list(self.reference_stats.keys()),
                "feature_value_counts": {
                    f: len(v) for f, v in self._feature_values.items()
                },
            }


# ---------------------------------------------------------------------------
# 7. UserComplaintTracker
# ---------------------------------------------------------------------------

class UserComplaintTracker:
    """
    Tracks user-submitted complaints and safety reports.

    Records complaints with categorization, provides trending analysis,
    and supports complaint resolution workflows.
    """

    def __init__(self) -> None:
        self._complaints: Dict[str, Dict[str, Any]] = {}
        self._resolved: Dict[str, str] = {}
        self._lock = threading.RLock()

    def record_complaint(
        self,
        user_id: str,
        category: str,
        severity: AlertSeverity,
        description: str,
        metadata: Optional[Dict] = None,
    ) -> str:
        """Record a new user complaint. Returns the complaint_id."""
        with self._lock:
            complaint_id = _generate_id("cmp-")
            self._complaints[complaint_id] = {
                "complaint_id": complaint_id,
                "user_id": user_id,
                "category": category,
                "severity": severity.value,
                "description": description,
                "metadata": metadata or {},
                "timestamp": datetime.utcnow(),
                "resolved": False,
            }
            logger.info(f"UserComplaintTracker: recorded complaint {complaint_id} from {user_id}")
            return complaint_id

    def get_complaint_rate(self, window: Optional[timedelta] = None) -> float:
        """
        Get complaint rate per hour. If window is provided, computes
        rate over that window.
        """
        with self._lock:
            if not self._complaints:
                return 0.0

            now = datetime.utcnow()
            if window is None:
                window = timedelta(hours=24)

            cutoff = now - window
            recent = sum(
                1 for c in self._complaints.values()
                if c["timestamp"] >= cutoff
            )
            hours = window.total_seconds() / 3600
            return recent / max(1, hours)

    def get_trending_categories(self, top_n: int = 5) -> List[Dict[str, Any]]:
        """Get top trending complaint categories by frequency."""
        with self._lock:
            now = datetime.utcnow()
            cutoff = now - timedelta(hours=24)
            category_counts: Dict[str, int] = defaultdict(int)

            for c in self._complaints.values():
                if c["timestamp"] >= cutoff:
                    category_counts[c["category"]] += 1

            trending = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)
            return [
                {"category": cat, "count": count, "window": "24h"}
                for cat, count in trending[:top_n]
            ]

    def resolve_complaint(self, complaint_id: str, resolution: str) -> None:
        """Mark a complaint as resolved with a resolution note."""
        with self._lock:
            if complaint_id in self._complaints:
                self._complaints[complaint_id]["resolved"] = True
                self._resolved[complaint_id] = resolution
                logger.info(f"UserComplaintTracker: resolved complaint {complaint_id}")

    def to_dict(self) -> dict:
        with self._lock:
            total = len(self._complaints)
            unresolved = sum(
                1 for c in self._complaints.values() if not c["resolved"]
            )
            return {
                "total_complaints": total,
                "unresolved": unresolved,
                "complaint_rate_per_hour": self.get_complaint_rate(),
                "trending_categories": self.get_trending_categories(),
            }


# ---------------------------------------------------------------------------
# 8. LatencyMonitor
# ---------------------------------------------------------------------------

class LatencyMonitor:
    """
    Monitors endpoint latency against SLO targets.

    Tracks latency percentiles, computes SLO compliance, and alerts
    when error budgets are at risk of being exhausted.
    """

    def __init__(
        self,
        slo_target_ms: float = 500.0,
        slo_percentile: float = 95.0,
        window_size: int = 1000,
    ) -> None:
        self.slo_target_ms = slo_target_ms
        self.slo_percentile = slo_percentile
        self.window_size = window_size
        self._latencies: deque = deque(maxlen=window_size)
        self._endpoint_latencies: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=window_size // 4)
        )
        self._total_requests: int = 0
        self._slo_violations: int = 0
        self._lock = threading.RLock()

    def record_latency(self, latency_ms: float, endpoint: str = "", model: str = "") -> None:
        """Record a single latency measurement."""
        with self._lock:
            self._latencies.append(latency_ms)
            self._total_requests += 1
            if latency_ms > self.slo_target_ms:
                self._slo_violations += 1
            if endpoint:
                self._endpoint_latencies[endpoint].append(latency_ms)

    def get_stats(self) -> Dict[str, float]:
        """Get basic latency statistics."""
        with self._lock:
            if not self._latencies:
                return {
                    "count": 0, "mean": 0.0, "std": 0.0,
                    "min": 0.0, "max": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0,
                }

            vals = list(self._latencies)
            sorted_vals = sorted(vals)
            n = len(vals)
            mean = sum(vals) / n
            std = statistics.stdev(vals) if n > 1 else 0.0

            return {
                "count": n,
                "mean": mean,
                "std": std,
                "min": sorted_vals[0],
                "max": sorted_vals[-1],
                "p50": _percentile(sorted_vals, 50),
                "p95": _percentile(sorted_vals, 95),
                "p99": _percentile(sorted_vals, 99),
            }

    def get_slo_report(self) -> SLOReport:
        """Generate the current SLO compliance report."""
        with self._lock:
            if not self._latencies or self._total_requests == 0:
                return SLOReport(
                    slo_name=f"p{int(self.slo_percentile)}_latency",
                    target_percent=self.slo_target_ms,
                    current_percent=100.0,
                    status=SLOStatus.MET,
                    error_budget_remaining=100.0,
                    burn_rate=0.0,
                    details={"total_requests": self._total_requests},
                )

            vals = sorted(self._latencies)
            p_value = _percentile(vals, self.slo_percentile)

            # SLO is met if the percentile is <= target
            slo_met = p_value <= self.slo_target_ms
            violation_rate = self._slo_violations / max(1, self._total_requests)
            error_budget = max(0.0, 100.0 - (violation_rate * 100.0))
            burn_rate = violation_rate / max(1e-6, 1.0 - (self.slo_percentile / 100.0))

            if error_budget <= 0:
                status = SLOStatus.BREACHED
            elif error_budget < 30:
                status = SLOStatus.AT_RISK
            else:
                status = SLOStatus.MET

            return SLOReport(
                slo_name=f"p{int(self.slo_percentile)}_latency",
                target_percent=self.slo_target_ms,
                current_percent=p_value,
                status=status,
                error_budget_remaining=error_budget,
                burn_rate=burn_rate,
                details={
                    "total_requests": self._total_requests,
                    "slo_violations": self._slo_violations,
                    "violation_rate": violation_rate,
                    "window_size": len(self._latencies),
                },
            )

    def check_slo_breach(self) -> Optional[Alert]:
        """Check if SLO is breached and generate an alert."""
        report = self.get_slo_report()
        if report.status == SLOStatus.BREACHED:
            return Alert(
                alert_id=_generate_id("slo-"),
                severity=AlertSeverity.CRITICAL,
                title=f"SLO Breached: {report.slo_name}",
                description=(
                    f"p{int(self.slo_percentile)} latency is {report.current_percent:.1f}ms "
                    f"(target: {report.target_percent:.1f}ms). "
                    f"Error budget exhausted. Burn rate: {report.burn_rate:.2f}."
                ),
                source="LatencyMonitor",
                metadata=report.to_dict(),
            )
        elif report.status == SLOStatus.AT_RISK:
            return Alert(
                alert_id=_generate_id("slo-"),
                severity=AlertSeverity.WARNING,
                title=f"SLO At Risk: {report.slo_name}",
                description=(
                    f"Error budget remaining: {report.error_budget_remaining:.1f}%. "
                    f"Burn rate: {report.burn_rate:.2f}."
                ),
                source="LatencyMonitor",
                metadata=report.to_dict(),
            )
        return None

    def get_percentiles(self) -> Dict[str, float]:
        """Get key latency percentiles."""
        with self._lock:
            if not self._latencies:
                return {"p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0, "p999": 0.0}
            vals = sorted(self._latencies)
            return {
                "p50": _percentile(vals, 50),
                "p90": _percentile(vals, 90),
                "p95": _percentile(vals, 95),
                "p99": _percentile(vals, 99),
                "p999": _percentile(vals, 99.9),
            }

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "slo_target_ms": self.slo_target_ms,
                "slo_percentile": self.slo_percentile,
                "window_size": self.window_size,
                "stats": self.get_stats(),
                "slo_report": self.get_slo_report().to_dict(),
                "percentiles": self.get_percentiles(),
            }


# ---------------------------------------------------------------------------
# 9. CostMonitor
# ---------------------------------------------------------------------------

class CostMonitor:
    """
    Monitors API/model inference costs against budgets.

    Tracks per-model costs, projects monthly spend, and alerts
    when budgets are at risk of being exceeded.
    """

    def __init__(self, monthly_budget: float = 1000.0, alert_threshold: float = 0.8) -> None:
        self.monthly_budget = monthly_budget
        self.alert_threshold = alert_threshold
        self._costs: deque = deque(maxlen=10000)
        self._model_costs: Dict[str, float] = defaultdict(float)
        self._daily_costs: Dict[str, float] = defaultdict(float)
        self._lock = threading.RLock()

    def record_cost(
        self, amount: float, model: str, tokens_in: int = 0, tokens_out: int = 0
    ) -> None:
        """Record a cost event."""
        with self._lock:
            now = datetime.utcnow()
            day_key = now.strftime("%Y-%m-%d")
            self._costs.append({
                "amount": amount,
                "model": model,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "timestamp": now,
            })
            self._model_costs[model] += amount
            self._daily_costs[day_key] += amount

    def get_current_month_cost(self) -> float:
        """Get total cost for the current month."""
        with self._lock:
            now = datetime.utcnow()
            month_start = now.strftime("%Y-%m-01")
            start_date = datetime.strptime(month_start, "%Y-%m-%d")
            return sum(
                c["amount"] for c in self._costs
                if c["timestamp"] >= start_date
            )

    def get_daily_cost_trend(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get daily cost trend for the specified number of days."""
        with self._lock:
            now = datetime.utcnow()
            trend = []
            for i in range(days - 1, -1, -1):
                day = now - timedelta(days=i)
                day_key = day.strftime("%Y-%m-%d")
                trend.append({
                    "date": day_key,
                    "cost": round(self._daily_costs.get(day_key, 0.0), 4),
                })
            return trend

    def get_model_cost_breakdown(self) -> Dict[str, float]:
        """Get per-model cost breakdown."""
        with self._lock:
            return dict(self._model_costs)

    def check_budget_alert(self) -> Optional[Alert]:
        """Check if budget threshold is crossed and generate alert."""
        with self._lock:
            current_cost = self.get_current_month_cost()
            ratio = current_cost / self.monthly_budget if self.monthly_budget > 0 else 0.0

            if ratio >= 1.0:
                return Alert(
                    alert_id=_generate_id("cost-"),
                    severity=AlertSeverity.CRITICAL,
                    title="Monthly Budget Exceeded",
                    description=(
                        f"Monthly cost {current_cost:.2f} exceeds budget of "
                        f"{self.monthly_budget:.2f} ({ratio:.1%}). Consider "
                        "rate limiting or model switching."
                    ),
                    source="CostMonitor",
                    metadata={
                        "current_cost": current_cost,
                        "monthly_budget": self.monthly_budget,
                        "ratio": ratio,
                        "projected_monthly": self.project_monthly_cost(),
                    },
                )
            elif ratio >= self.alert_threshold:
                return Alert(
                    alert_id=_generate_id("cost-"),
                    severity=AlertSeverity.WARNING,
                    title=f"Budget Alert: {ratio:.1%} of Monthly Budget Used",
                    description=(
                        f"Current spend: {current_cost:.2f} / {self.monthly_budget:.2f}. "
                        f"Projected: {self.project_monthly_cost():.2f}."
                    ),
                    source="CostMonitor",
                    metadata={
                        "current_cost": current_cost,
                        "monthly_budget": self.monthly_budget,
                        "ratio": ratio,
                    },
                )
            return None

    def project_monthly_cost(self) -> float:
        """Project total monthly cost based on current burn rate."""
        with self._lock:
            now = datetime.utcnow()
            days_in_month = 30.0  # approximation
            day_of_month = now.day
            if day_of_month < 1:
                return 0.0

            current_cost = self.get_current_month_cost()
            daily_rate = current_cost / day_of_month
            return daily_rate * days_in_month

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "monthly_budget": self.monthly_budget,
                "alert_threshold": self.alert_threshold,
                "current_month_cost": self.get_current_month_cost(),
                "projected_monthly_cost": self.project_monthly_cost(),
                "model_breakdown": dict(self._model_costs),
                "daily_trend": self.get_daily_cost_trend(7),
            }


# ---------------------------------------------------------------------------
# 10. ToolFailureRateTracker
# ---------------------------------------------------------------------------

class ToolFailureRateTracker:
    """
    Tracks tool call success/failure rates and detects degradation.

    Monitors per-tool failure rates, latency, and error patterns to
    identify when specific tools are degrading or failing.
    """

    def __init__(self, alert_threshold: float = 0.05) -> None:
        self.alert_threshold = alert_threshold
        self._tool_calls: Dict[str, deque] = defaultdict(lambda: deque(maxlen=500))
        self._total_calls: int = 0
        self._lock = threading.RLock()

    def record_tool_call(
        self, tool_name: str, success: bool, latency_ms: float = 0.0, error_message: str = ""
    ) -> None:
        """Record a single tool call outcome."""
        with self._lock:
            self._tool_calls[tool_name].append({
                "success": success,
                "latency_ms": latency_ms,
                "error_message": error_message[:500],
                "timestamp": datetime.utcnow(),
            })
            self._total_calls += 1

    def get_failure_rate(self, tool_name: Optional[str] = None) -> float:
        """Get failure rate for a specific tool or overall."""
        with self._lock:
            if tool_name:
                calls = self._tool_calls.get(tool_name, [])
                if not calls:
                    return 0.0
                return sum(1 for c in calls if not c["success"]) / len(calls)

            if self._total_calls == 0:
                return 0.0
            all_calls = []
            for calls in self._tool_calls.values():
                all_calls.extend(calls)
            if not all_calls:
                return 0.0
            return sum(1 for c in all_calls if not c["success"]) / len(all_calls)

    def get_per_tool_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get detailed statistics per tool."""
        with self._lock:
            stats = {}
            for tool_name, calls in self._tool_calls.items():
                if not calls:
                    continue
                total = len(calls)
                failures = sum(1 for c in calls if not c["success"])
                latencies = [c["latency_ms"] for c in calls if c["latency_ms"] > 0]
                error_msgs = [c["error_message"] for c in calls if c["error_message"]]

                stats[tool_name] = {
                    "total_calls": total,
                    "failures": failures,
                    "failure_rate": failures / total if total > 0 else 0.0,
                    "avg_latency_ms": statistics.mean(latencies) if latencies else 0.0,
                    "common_errors": list(set(error_msgs))[:5],
                }
            return stats

    def detect_degradation(self) -> List[Dict[str, Any]]:
        """Detect tools showing degradation based on failure rate threshold."""
        with self._lock:
            degraded = []
            per_tool = self.get_per_tool_stats()
            for tool_name, stats in per_tool.items():
                if stats["failure_rate"] >= self.alert_threshold:
                    degraded.append({
                        "tool_name": tool_name,
                        "failure_rate": stats["failure_rate"],
                        "total_calls": stats["total_calls"],
                        "threshold": self.alert_threshold,
                        "severity": (
                            "critical" if stats["failure_rate"] >= self.alert_threshold * 3
                            else "warning"
                        ),
                    })
            return degraded

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "alert_threshold": self.alert_threshold,
                "total_calls": self._total_calls,
                "overall_failure_rate": self.get_failure_rate(),
                "per_tool_stats": self.get_per_tool_stats(),
                "degraded_tools": self.detect_degradation(),
            }


# ---------------------------------------------------------------------------
# 11. BehaviorAnomalyDetector
# ---------------------------------------------------------------------------

class BehaviorAnomalyDetector:
    """
    Detects anomalous user/agent behavior using z-score based anomaly detection.

    Builds behavioral profiles (latency, request rate, endpoints) and flags
    deviations that may indicate abuse, compromise, or malfunction.
    """

    def __init__(self, window_size: int = 1000, zscore_threshold: float = 3.0) -> None:
        self.window_size = window_size
        self.zscore_threshold = zscore_threshold
        self._user_behavior: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=window_size)
        )
        self._user_profiles: Dict[str, BehaviorProfile] = {}
        self._lock = threading.RLock()

    def record_behavior(
        self,
        user_id: str,
        endpoint: str,
        latency_ms: float,
        token_count: int,
        metadata: Optional[Dict] = None,
    ) -> None:
        """Record a single behavioral data point for a user."""
        with self._lock:
            self._user_behavior[user_id].append({
                "endpoint": endpoint,
                "latency_ms": latency_ms,
                "token_count": token_count,
                "metadata": metadata or {},
                "timestamp": datetime.utcnow(),
            })

    def build_profile(self, user_id: str) -> BehaviorProfile:
        """Build or retrieve a behavioral profile for a user."""
        with self._lock:
            behaviors = list(self._user_behavior.get(user_id, []))
            if not behaviors:
                return BehaviorProfile(user_id=user_id)

            latencies = [b["latency_ms"] for b in behaviors]
            baseline_latency = statistics.mean(latencies) if latencies else 0.0

            # Request rate: requests per minute over the window
            if len(behaviors) >= 2:
                time_span = (
                    behaviors[-1]["timestamp"] - behaviors[0]["timestamp"]
                ).total_seconds()
                baseline_request_rate = (
                    len(behaviors) / (time_span / 60.0) if time_span > 0 else 0.0
                )
            else:
                baseline_request_rate = 0.0

            # Common endpoints
            endpoint_counts: Dict[str, int] = defaultdict(int)
            for b in behaviors:
                endpoint_counts[b["endpoint"]] += 1
            common_endpoints = [
                ep for ep, _ in sorted(
                    endpoint_counts.items(), key=lambda x: x[1], reverse=True
                )[:10]
            ]

            # Deviation score
            deviation_score = 0.0
            if latencies:
                mean_lat = statistics.mean(latencies)
                std_lat = statistics.stdev(latencies) if len(latencies) > 1 else 1.0
                recent_latencies = latencies[-10:] if len(latencies) >= 10 else latencies
                recent_mean = statistics.mean(recent_latencies)
                if std_lat > 0:
                    deviation_score = abs(recent_mean - mean_lat) / std_lat

            profile = BehaviorProfile(
                user_id=user_id,
                baseline_latency=baseline_latency,
                baseline_request_rate=baseline_request_rate,
                common_endpoints=common_endpoints,
                deviation_score=deviation_score,
                flags=[],
            )

            self._user_profiles[user_id] = profile
            return profile

    def detect_anomalies(self, user_id: str) -> List[Dict[str, Any]]:
        """Detect behavioral anomalies for a specific user."""
        with self._lock:
            profile = self.build_profile(user_id)
            behaviors = list(self._user_behavior.get(user_id, []))
            if not behaviors:
                return []

            anomalies: List[Dict[str, Any]] = []

            # Check recent behavior against profile
            recent = behaviors[-50:] if len(behaviors) >= 50 else behaviors

            # Latency anomaly
            recent_latencies = [b["latency_ms"] for b in recent]
            if recent_latencies and profile.baseline_latency > 0:
                recent_mean = statistics.mean(recent_latencies)
                std = statistics.stdev(recent_latencies) if len(recent_latencies) > 1 else 1.0
                z_score = (
                    abs(recent_mean - profile.baseline_latency) / (std / math.sqrt(len(recent_latencies)))
                    if std > 0 else 0.0
                )
                if z_score > self.zscore_threshold:
                    anomalies.append({
                        "type": AnomalyType.LATENCY_SPIKE.value,
                        "z_score": z_score,
                        "current_mean": recent_mean,
                        "baseline_mean": profile.baseline_latency,
                        "severity": "critical" if z_score > self.zscore_threshold * 2 else "warning",
                    })

            # Endpoint anomaly: using uncommon endpoints
            for b in recent[-10:]:
                if b["endpoint"] and b["endpoint"] not in profile.common_endpoints:
                    anomalies.append({
                        "type": AnomalyType.PATTERN_CHANGE.value,
                        "endpoint": b["endpoint"],
                        "detail": "Uncommon endpoint accessed",
                        "severity": "warning",
                    })
                    break

            # Token count anomaly
            token_counts = [b["token_count"] for b in recent if b["token_count"] > 0]
            if token_counts and len(token_counts) > 5:
                mean_tokens = statistics.mean(token_counts)
                std_tokens = statistics.stdev(token_counts) if len(token_counts) > 1 else 1.0
                for tc in token_counts[-5:]:
                    z = abs(tc - mean_tokens) / std_tokens if std_tokens > 0 else 0.0
                    if z > self.zscore_threshold:
                        anomalies.append({
                            "type": AnomalyType.VOLUME_ANOMALY.value,
                            "z_score": z,
                            "token_count": tc,
                            "mean_tokens": mean_tokens,
                            "severity": "warning",
                        })
                        break

            return anomalies

    def get_suspicious_users(self) -> List[str]:
        """Get list of users with detected anomalies."""
        with self._lock:
            suspicious = []
            for user_id in self._user_behavior:
                anomalies = self.detect_anomalies(user_id)
                if anomalies:
                    suspicious.append(user_id)
            return suspicious

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "window_size": self.window_size,
                "zscore_threshold": self.zscore_threshold,
                "tracked_users": len(self._user_behavior),
                "suspicious_users": self.get_suspicious_users(),
                "profiles_built": len(self._user_profiles),
            }


# ---------------------------------------------------------------------------
# 12. SecurityEventCorrelator
# ---------------------------------------------------------------------------

class SecurityEventCorrelator:
    """
    Correlates security events to detect attack patterns and chains.

    Groups related events by time proximity, source, and type to identify
    coordinated attacks or multi-stage security incidents.
    """

    def __init__(self, correlation_window: int = 300) -> None:
        self.correlation_window = correlation_window  # seconds
        self._events: deque = deque(maxlen=5000)
        self._correlation_groups: List[Dict[str, Any]] = []
        self._lock = threading.RLock()

    def record_event(self, event: SecurityEvent) -> None:
        """Record a new security event."""
        with self._lock:
            self._events.append(event)

    def correlate(self) -> List[Dict[str, Any]]:
        """
        Correlate recent events to find groups of related events.
        Returns list of correlation groups.
        """
        with self._lock:
            if not self._events:
                return []

            events = list(self._events)
            now = datetime.utcnow()
            window = timedelta(seconds=self.correlation_window)

            # Cluster events by time proximity and source IP
            groups: List[Dict[str, Any]] = []
            visited: Set[int] = set()

            for i, event in enumerate(events):
                if i in visited:
                    continue
                if (now - event.timestamp).total_seconds() > self.correlation_window * 2:
                    continue

                group = {
                    "root_event_id": event.event_id,
                    "events": [event.to_dict()],
                    "event_types": {event.event_type},
                    "source_ips": {event.source_ip} if event.source_ip else set(),
                    "source": event.source_ip,
                    "severity": event.severity.value,
                    "triggered_at": event.timestamp.isoformat(),
                }
                visited.add(i)

                for j, other in enumerate(events):
                    if j in visited:
                        continue
                    time_diff = abs((event.timestamp - other.timestamp).total_seconds())
                    same_source = (
                        event.source_ip
                        and other.source_ip
                        and event.source_ip == other.source_ip
                    )
                    if time_diff <= self.correlation_window and same_source:
                        group["events"].append(other.to_dict())
                        group["event_types"].add(other.event_type)
                        group["source_ips"].add(other.source_ip)
                        if other.severity.value in ("critical", "emergency"):
                            group["severity"] = other.severity.value
                        visited.add(j)

                group["event_types"] = list(group["event_types"])
                group["source_ips"] = list(group["source_ips"])
                group["event_count"] = len(group["events"])
                groups.append(group)

            self._correlation_groups = groups
            return groups

    def get_event_chain(self, root_event_id: str) -> List[SecurityEvent]:
        """Get all events in the chain starting from a root event."""
        with self._lock:
            chain: List[SecurityEvent] = []
            root_event = None

            for event in self._events:
                if event.event_id == root_event_id:
                    root_event = event
                    break

            if not root_event:
                return chain

            chain.append(root_event)
            # Follow correlated events
            for corr_id in root_event.correlated_events:
                for event in self._events:
                    if event.event_id == corr_id:
                        chain.append(event)
                        break

            return chain

    def detect_patterns(self) -> List[Dict[str, Any]]:
        """
        Detect known attack patterns from correlated events.
        Returns list of detected patterns.
        """
        with self._lock:
            groups = self.correlate()
            patterns: List[Dict[str, Any]] = []

            for group in groups:
                event_types = set(group.get("event_types", []))
                event_count = group.get("event_count", 0)

                # Reconnaissance pattern: multiple scan/access events
                if "unauthorized_access" in event_types and event_count >= 3:
                    patterns.append({
                        "pattern": "reconnaissance",
                        "confidence": min(1.0, event_count / 10.0),
                        "group": group,
                        "recommendation": "Investigate for potential reconnaissance activity.",
                    })

                # Brute force pattern: many rapid failures
                if "auth_failure" in event_types and event_count >= 5:
                    patterns.append({
                        "pattern": "brute_force",
                        "confidence": min(1.0, event_count / 20.0),
                        "group": group,
                        "recommendation": "Rate limit or block the source IP.",
                    })

                # Data exfiltration pattern
                if "data_exfiltration" in event_types:
                    patterns.append({
                        "pattern": "data_exfiltration",
                        "confidence": 0.8,
                        "group": group,
                        "recommendation": "Immediate containment and investigation required.",
                    })

            return patterns

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "correlation_window": self.correlation_window,
                "total_events": len(self._events),
                "correlation_groups": len(self._correlation_groups),
                "active_patterns": self.detect_patterns(),
            }


# ---------------------------------------------------------------------------
# 13. SafetyMonitor — Main Orchestrator
# ---------------------------------------------------------------------------

class SafetyMonitor:
    """
    Main orchestrator for the safety monitoring system.

    Coordinates all monitoring subsystems, collects agent interaction data,
    manages alerts, and provides a unified health status and dashboard.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        config = config or {}

        self.config = config
        self.accuracy_drift = AccuracyDriftDetector(
            baseline_accuracy=config.get("baseline_accuracy", 0.95),
            window_size=config.get("accuracy_window", 100),
            drift_threshold=config.get("drift_threshold", 0.05),
        )
        self.hallucination_tracker = HallucinationRateTracker(
            window_size=config.get("hallucination_window", 500),
            alert_threshold=config.get("hallucination_threshold", 0.15),
        )
        self.unsafe_detector = UnsafeOutputDetector(
            unsafe_patterns=config.get("unsafe_patterns"),
            ml_threshold=config.get("unsafe_ml_threshold", 0.6),
        )
        self.attack_detector = PromptAttackDetector()
        self.model_drift = ModelDriftDetector(
            reference_distribution=config.get("reference_distribution"),
        )
        self.data_drift = DataDriftDetector(
            reference_stats=config.get("data_reference_stats"),
        )
        self.complaint_tracker = UserComplaintTracker()
        self.latency_monitor = LatencyMonitor(
            slo_target_ms=config.get("slo_target_ms", 500.0),
            slo_percentile=config.get("slo_percentile", 95.0),
            window_size=config.get("latency_window", 1000),
        )
        self.cost_monitor = CostMonitor(
            monthly_budget=config.get("monthly_budget", 1000.0),
            alert_threshold=config.get("budget_alert_threshold", 0.8),
        )
        self.tool_failure_tracker = ToolFailureRateTracker(
            alert_threshold=config.get("tool_failure_threshold", 0.05),
        )
        self.behavior_anomaly = BehaviorAnomalyDetector(
            window_size=config.get("behavior_window", 1000),
            zscore_threshold=config.get("zscore_threshold", 3.0),
        )
        self.security_correlator = SecurityEventCorrelator(
            correlation_window=config.get("correlation_window", 300),
        )

        self._alerts: Dict[str, Alert] = {}
        self._monitoring_active: bool = False
        self._monitoring_thread: Optional[threading.Thread] = None
        self._monitoring_interval: float = config.get("monitoring_interval", 60.0)
        self._lock = threading.RLock()

        logger.info("SafetyMonitor initialized with config: %s", list(config.keys()))

    def start_monitoring(self) -> None:
        """Start the background monitoring thread."""
        with self._lock:
            if self._monitoring_active:
                logger.warning("SafetyMonitor: monitoring already active")
                return
            self._monitoring_active = True
            self._monitoring_thread = threading.Thread(
                target=self._monitoring_loop, daemon=True, name="safety-monitor"
            )
            self._monitoring_thread.start()
            logger.info("SafetyMonitor: monitoring started (interval: %.1fs)", self._monitoring_interval)

    def stop_monitoring(self) -> None:
        """Stop the background monitoring thread."""
        with self._lock:
            self._monitoring_active = False
            logger.info("SafetyMonitor: monitoring stopped")

    def _monitoring_loop(self) -> None:
        """Background monitoring loop."""
        while self._monitoring_active:
            try:
                self._run_checks()
            except Exception as e:
                logger.error("SafetyMonitor: error in monitoring loop: %s", e)
            time.sleep(self._monitoring_interval)

    def _run_checks(self) -> None:
        """Run all periodic health checks and generate alerts."""
        # Accuracy drift
        drift_report = self.accuracy_drift.detect_drift()
        if drift_report.status in (DriftStatus.DRIFTING, DriftStatus.CRITICAL):
            self._add_alert(Alert(
                alert_id=_generate_id("drift-"),
                severity=(
                    AlertSeverity.CRITICAL
                    if drift_report.status == DriftStatus.CRITICAL
                    else AlertSeverity.WARNING
                ),
                title=f"Accuracy Drift Detected: {drift_report.status.value}",
                description=drift_report.recommendation,
                source="AccuracyDriftDetector",
                metadata=drift_report.to_dict(),
            ))

        # Hallucination rate
        hal_alert = self.hallucination_tracker.check_alert()
        if hal_alert:
            self._add_alert(hal_alert)

        # SLO breach
        slo_alert = self.latency_monitor.check_slo_breach()
        if slo_alert:
            self._add_alert(slo_alert)

        # Budget alert
        budget_alert = self.cost_monitor.check_budget_alert()
        if budget_alert:
            self._add_alert(budget_alert)

        # Tool degradation
        for degraded in self.tool_failure_tracker.detect_degradation():
            self._add_alert(Alert(
                alert_id=_generate_id("tool-"),
                severity=(
                    AlertSeverity.CRITICAL
                    if degraded["severity"] == "critical"
                    else AlertSeverity.WARNING
                ),
                title=f"Tool Degradation: {degraded['tool_name']}",
                description=(
                    f"Tool '{degraded['tool_name']}' failure rate: "
                    f"{degraded['failure_rate']:.2%} "
                    f"(threshold: {degraded['threshold']:.2%})"
                ),
                source="ToolFailureRateTracker",
                metadata=degraded,
            ))

    def _add_alert(self, alert: Alert) -> None:
        """Add an alert, deduplicating by title and source."""
        with self._lock:
            for existing in self._alerts.values():
                if (
                    existing.title == alert.title
                    and existing.source == alert.source
                    and not existing.resolved
                ):
                    logger.debug("SafetyMonitor: suppressed duplicate alert: %s", alert.title)
                    return
            self._alerts[alert.alert_id] = alert
            logger.warning(
                "SafetyMonitor: ALERT [%s] %s: %s",
                alert.severity.value.upper(),
                alert.title,
                alert.description[:200],
            )

    def record_agent_interaction(self, interaction: Dict[str, Any]) -> None:
        """
        Record a complete agent interaction for monitoring.

        Expected keys in interaction dict:
        - user_id, prompt, output, correct, category, latency_ms, tokens_in,
          tokens_out, model, endpoint, tool_calls, is_hallucination,
          cost, metadata
        """
        with self._lock:
            user_id = interaction.get("user_id", "unknown")
            prompt = interaction.get("prompt", "")
            output = interaction.get("output", "")
            latency_ms = interaction.get("latency_ms", 0.0)
            endpoint = interaction.get("endpoint", "")
            model = interaction.get("model", "")
            cost = interaction.get("cost", 0.0)
            tokens_in = interaction.get("tokens_in", 0)
            tokens_out = interaction.get("tokens_out", 0)

            # Record prediction accuracy
            if "correct" in interaction:
                self.accuracy_drift.record_prediction(
                    correct=bool(interaction["correct"]),
                    category=interaction.get("category"),
                )

            # Record hallucination
            if "is_hallucination" in interaction:
                self.hallucination_tracker.record_output(
                    text=output,
                    is_hallucination=bool(interaction["is_hallucination"]),
                    confidence=interaction.get("hallucination_confidence", 1.0),
                )

            # Analyze output for unsafe content
            if output:
                unsafe_result = self.unsafe_detector.analyze(output)
                if unsafe_result["is_unsafe"]:
                    category = "pattern_match"
                    self.unsafe_detector.record_detection(output, category)

            # Detect prompt attacks
            if prompt:
                attack_result = self.attack_detector.detect_attack(
                    prompt, metadata=interaction.get("metadata")
                )
                if attack_result:
                    self.attack_detector.record_attack(
                        attack_type=AttackType(attack_result["attack_type"]),
                        source_ip=interaction.get("source_ip", ""),
                        user_id=user_id,
                        details=attack_result,
                    )

            # Record latency
            if latency_ms > 0:
                self.latency_monitor.record_latency(
                    latency_ms=latency_ms, endpoint=endpoint, model=model
                )

            # Record cost
            if cost > 0:
                self.cost_monitor.record_cost(
                    amount=cost, model=model,
                    tokens_in=tokens_in, tokens_out=tokens_out,
                )

            # Record tool calls
            for tc in interaction.get("tool_calls", []):
                self.tool_failure_tracker.record_tool_call(
                    tool_name=tc.get("tool_name", "unknown"),
                    success=tc.get("success", True),
                    latency_ms=tc.get("latency_ms", 0.0),
                    error_message=tc.get("error_message", ""),
                )

            # Record behavior
            self.behavior_anomaly.record_behavior(
                user_id=user_id,
                endpoint=endpoint,
                latency_ms=latency_ms,
                token_count=tokens_in + tokens_out,
                metadata=interaction.get("metadata"),
            )

    def get_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status of all monitoring subsystems."""
        with self._lock:
            drift = self.accuracy_drift.detect_drift()
            slo = self.latency_monitor.get_slo_report()
            hallucinations = self.hallucination_tracker.get_current_rate()
            unsafe_rate = self.unsafe_detector.get_unsafe_rate()
            attack_rate = self.attack_detector.get_attack_rate()
            tool_health = self.tool_failure_tracker.get_failure_rate()
            degraded_tools = self.tool_failure_tracker.detect_degradation()
            anomalies = self.behavior_anomaly.get_suspicious_users()

            # Overall health: green/yellow/red
            issues = 0
            if drift.status in (DriftStatus.DRIFTING, DriftStatus.CRITICAL):
                issues += 1
            if slo.status in (SLOStatus.AT_RISK, SLOStatus.BREACHED):
                issues += 1
            if hallucinations >= 0.15:
                issues += 1
            if tool_health >= 0.05:
                issues += 1
            if anomalies:
                issues += 1

            if issues >= 3:
                overall = "critical"
            elif issues >= 1:
                overall = "warning"
            else:
                overall = "healthy"

            return {
                "overall": overall,
                "monitoring_active": self._monitoring_active,
                "accuracy": {
                    "current": self.accuracy_drift.get_current_accuracy(),
                    "drift_status": drift.status.value,
                    "drift_magnitude": drift.drift_magnitude,
                },
                "hallucination_rate": hallucinations,
                "unsafe_output_rate": unsafe_rate,
                "attack_rate": attack_rate,
                "slo": slo.to_dict(),
                "current_month_cost": self.cost_monitor.get_current_month_cost(),
                "tool_failure_rate": tool_health,
                "degraded_tools": degraded_tools,
                "suspicious_users": anomalies,
                "active_alerts": len([a for a in self._alerts.values() if not a.resolved]),
            }

    def get_active_alerts(self) -> List[Alert]:
        """Get all unresolved alerts."""
        with self._lock:
            return [a for a in self._alerts.values() if not a.resolved]

    def acknowledge_alert(self, alert_id: str) -> None:
        """Acknowledge a specific alert."""
        with self._lock:
            if alert_id in self._alerts:
                self._alerts[alert_id].acknowledged = True
                logger.info("SafetyMonitor: acknowledged alert %s", alert_id)

    def resolve_alert(self, alert_id: str) -> None:
        """Resolve a specific alert."""
        with self._lock:
            if alert_id in self._alerts:
                self._alerts[alert_id].resolved = True
                logger.info("SafetyMonitor: resolved alert %s", alert_id)

    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get consolidated dashboard data for all monitoring subsystems."""
        with self._lock:
            return {
                "health": self.get_health_status(),
                "drift": self.accuracy_drift.to_dict(),
                "hallucination": self.hallucination_tracker.to_dict(),
                "unsafe_output": self.unsafe_detector.to_dict(),
                "prompt_attacks": self.attack_detector.to_dict(),
                "latency": self.latency_monitor.to_dict(),
                "cost": self.cost_monitor.to_dict(),
                "tool_failures": self.tool_failure_tracker.to_dict(),
                "behavior": self.behavior_anomaly.to_dict(),
                "security": self.security_correlator.to_dict(),
                "complaints": self.complaint_tracker.to_dict(),
                "active_alerts": [a.to_dict() for a in self.get_active_alerts()],
            }

    def to_dict(self) -> dict:
        return self.get_dashboard_data()


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------

__all__ = [
    # Enums
    "DriftStatus",
    "AlertSeverity",
    "AttackType",
    "SLOStatus",
    "AnomalyType",
    # Dataclasses
    "DriftReport",
    "Alert",
    "SLOReport",
    "SecurityEvent",
    "BehaviorProfile",
    # Monitors
    "AccuracyDriftDetector",
    "HallucinationRateTracker",
    "UnsafeOutputDetector",
    "PromptAttackDetector",
    "ModelDriftDetector",
    "DataDriftDetector",
    "UserComplaintTracker",
    "LatencyMonitor",
    "CostMonitor",
    "ToolFailureRateTracker",
    "BehaviorAnomalyDetector",
    "SecurityEventCorrelator",
    "SafetyMonitor",
]