"""
AI Safety & Governance OS — Enterprise Guardrails Module

Provides a comprehensive safety layer for AI agent systems with:
- Prompt injection and jailbreak detection
- Tool permission control and agent sandboxing
- Secret redaction and sensitive data filtering
- Context isolation and output validation
- Human approval gates for high-impact actions
- Rate limiting, abuse detection, and policy enforcement

Author: Eni Builder — Safety & Governance OS
Version: 2.0.0
"""

import re
import time
import json
import logging
import threading
import hashlib
import uuid
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════════

class Severity(Enum):
    """Severity level of a guardrail event or finding."""
    CRITICAL = auto()
    HIGH = auto()
    MEDIUM = auto()
    LOW = auto()
    NONE = auto()

    def __ge__(self, other: "Severity") -> bool:
        if self.__class__ is other.__class__:
            return self.value >= other.value
        return NotImplemented

    def __le__(self, other: "Severity") -> bool:
        if self.__class__ is other.__class__:
            return self.value <= other.value
        return NotImplemented


class GuardrailAction(Enum):
    """Action to take when a guardrail is triggered."""
    BLOCK = "block"
    REDACT = "redact"
    FLAG = "flag"
    LOG = "log"
    APPROVE = "approve"
    QUARANTINE = "quarantine"


class InjectionType(Enum):
    """Types of prompt injection attacks."""
    DIRECT = "direct"
    INDIRECT = "indirect"
    DELIMITER_BASED = "delimiter_based"
    ENCODING_BASED = "encoding_based"
    CONTEXT_LEAK = "context_leak"


class JailbreakType(Enum):
    """Types of jailbreak attempts."""
    ROLE_PLAY = "role_play"
    HYBRID_ENCODING = "hybrid_encoding"
    HYPOTHETICAL = "hypothetical"
    TRANSLATION = "translation"
    PROMPT_LEAKING = "prompt_leaking"


class ToolRisk(Enum):
    """Risk level associated with a tool."""
    SAFE = auto()
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()
    CRITICAL = auto()


class SandboxMode(Enum):
    """Agent sandbox enforcement modes."""
    STRICT = "strict"
    MODERATE = "moderate"
    PERMISSIVE = "permissive"
    AUDIT_ONLY = "audit_only"


class DataSensitivity(Enum):
    """Categories of sensitive data."""
    PII = "pii"
    PHI = "phi"
    PCI = "pci"
    FINANCIAL = "financial"
    CREDENTIAL = "credential"
    NONE = "none"


# ═══════════════════════════════════════════════════════════════════════════════
# Result Dataclasses
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class InjectionResult:
    """Result of a prompt injection detection scan.

    Attributes:
        detected: Whether an injection was detected.
        injection_type: The type of injection detected, if any.
        confidence: Confidence score from 0.0 to 1.0.
        matched_patterns: List of regex patterns that matched.
        details: Additional metadata about the detection.
    """
    detected: bool = False
    injection_type: Optional[InjectionType] = None
    confidence: float = 0.0
    matched_patterns: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "detected": self.detected,
            "injection_type": self.injection_type.value if self.injection_type else None,
            "confidence": self.confidence,
            "matched_patterns": self.matched_patterns,
            "details": self.details,
        }


@dataclass
class JailbreakResult:
    """Result of a jailbreak detection scan.

    Attributes:
        detected: Whether a jailbreak was detected.
        jailbreak_type: The type of jailbreak detected, if any.
        confidence: Confidence score from 0.0 to 1.0.
        matched_payloads: List of payload strings that matched.
        details: Additional metadata about the detection.
    """
    detected: bool = False
    jailbreak_type: Optional[JailbreakType] = None
    confidence: float = 0.0
    matched_payloads: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "detected": self.detected,
            "jailbreak_type": self.jailbreak_type.value if self.jailbreak_type else None,
            "confidence": self.confidence,
            "matched_payloads": self.matched_payloads,
            "details": self.details,
        }


@dataclass
class ValidationResult:
    """Result of output validation.

    Attributes:
        passed: Whether the output passed validation.
        is_refusal: Whether the output appears to be a refusal.
        toxicity_score: Toxicity score from 0.0 (safe) to 1.0 (toxic).
        violations: List of policy violation descriptions.
        policy_compliant: Whether the output complies with all policies.
        details: Additional metadata about the validation.
    """
    passed: bool = True
    is_refusal: bool = False
    toxicity_score: float = 0.0
    violations: List[str] = field(default_factory=list)
    policy_compliant: bool = True
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "is_refusal": self.is_refusal,
            "toxicity_score": self.toxicity_score,
            "violations": self.violations,
            "policy_compliant": self.policy_compliant,
            "details": self.details,
        }


@dataclass
class GuardrailResult:
    """Aggregated result from the SafetyGuardrail pipeline.

    Attributes:
        passed: Whether the content passed all guardrails.
        action: The action taken by the guardrail system.
        findings: List of finding dictionaries from each guardrail.
        sanitized_input: Sanitized version of the input, if applicable.
        sanitized_output: Sanitized version of the output, if applicable.
        details: Additional metadata about the guardrail decision.
    """
    passed: bool = True
    action: GuardrailAction = GuardrailAction.LOG
    findings: List[Dict[str, Any]] = field(default_factory=list)
    sanitized_input: Optional[str] = None
    sanitized_output: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "action": self.action.value,
            "findings": self.findings,
            "sanitized_input": self.sanitized_input,
            "sanitized_output": self.sanitized_output,
            "details": self.details,
        }


@dataclass
class SensitiveDataFinding:
    """A single sensitive data finding.

    Attributes:
        sensitivity: The category of sensitive data found.
        matched_text: The matched text (may be partially redacted).
        start_pos: Starting character position of the match.
        end_pos: Ending character position of the match.
        confidence: Confidence score from 0.0 to 1.0.
    """
    sensitivity: DataSensitivity = DataSensitivity.NONE
    matched_text: str = ""
    start_pos: int = -1
    end_pos: int = -1
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sensitivity": self.sensitivity.value,
            "matched_text": self.matched_text,
            "start_pos": self.start_pos,
            "end_pos": self.end_pos,
            "confidence": self.confidence,
        }


@dataclass
class PolicyDecision:
    """A single policy evaluation decision.

    Attributes:
        policy_name: Name of the policy.
        action: The action prescribed by the policy.
        triggered: Whether the policy rule was triggered.
        reason: Human-readable explanation of the decision.
        priority: Priority of this policy (higher = more important).
    """
    policy_name: str = ""
    action: GuardrailAction = GuardrailAction.LOG
    triggered: bool = False
    reason: str = ""
    priority: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policy_name": self.policy_name,
            "action": self.action.value,
            "triggered": self.triggered,
            "reason": self.reason,
            "priority": self.priority,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 1. RateLimiter (Token Bucket)
# ═══════════════════════════════════════════════════════════════════════════════

class RateLimiter:
    """Token-bucket rate limiter with per-user, per-IP, and per-endpoint tracking.

    Implements a thread-safe token bucket algorithm. Each unique key (user_id,
    ip_address, endpoint) gets its own bucket with configurable refill rate and
    burst capacity.

    Usage:
        limiter = RateLimiter(rate=10.0, burst=20, per_user_limit=100)
        if limiter.allow_request("user123", "192.168.1.1", "/api/chat"):
            # process request
    """

    def __init__(
        self,
        rate: float,
        burst: int,
        per_user_limit: Optional[int] = None,
    ) -> None:
        """Initialize the rate limiter.

        Args:
            rate: Tokens added per second (sustained rate).
            burst: Maximum token bucket capacity (burst allowance).
            per_user_limit: Optional hard cap on tokens per user.
        """
        self._rate = float(rate)
        self._burst = int(burst)
        self._per_user_limit = per_user_limit
        self._lock = threading.Lock()

        # Per-user, per-IP, per-endpoint buckets
        # Each bucket: {"tokens": float, "last_refill": float}
        self._buckets: Dict[str, Dict[str, Any]] = {}

        # Global request tracking
        self._total_requests: int = 0
        self._total_denied: int = 0
        self._start_time: float = time.time()

    def allow_request(
        self,
        user_id: str,
        ip_address: str = "",
        endpoint: str = "",
    ) -> bool:
        """Check if a request is allowed under current rate limits.

        Args:
            user_id: Identifier for the requesting user.
            ip_address: Source IP address of the request.
            endpoint: API endpoint being accessed.

        Returns:
            True if the request is allowed, False if it should be denied.
        """
        with self._lock:
            now = time.time()
            keys_to_check = []

            if user_id:
                keys_to_check.append(f"user:{user_id}")
            if ip_address:
                keys_to_check.append(f"ip:{ip_address}")
            if endpoint:
                keys_to_check.append(f"endpoint:{endpoint}")

            # Check global bucket
            keys_to_check.append("global")

            allowed = True
            for key in keys_to_check:
                if key not in self._buckets:
                    self._buckets[key] = {"tokens": float(self._burst), "last_refill": now}

                bucket = self._buckets[key]
                elapsed = now - bucket["last_refill"]
                bucket["tokens"] = min(
                    float(self._burst),
                    bucket["tokens"] + elapsed * self._rate,
                )
                bucket["last_refill"] = now

                if bucket["tokens"] < 1.0:
                    allowed = False
                else:
                    bucket["tokens"] -= 1.0

            # Per-user hard limit
            if self._per_user_limit is not None and allowed:
                user_key = f"user_total:{user_id}"
                if user_key not in self._buckets:
                    self._buckets[user_key] = {"tokens": float(self._per_user_limit), "last_refill": now}
                user_bucket = self._buckets[user_key]
                if user_bucket["tokens"] < 1.0:
                    allowed = False
                else:
                    user_bucket["tokens"] -= 1.0

            if allowed:
                self._total_requests += 1
            else:
                self._total_denied += 1

            return allowed

    def get_remaining(self, user_id: str) -> int:
        """Get the number of remaining tokens for a user.

        Args:
            user_id: The user to check.

        Returns:
            Approximate number of remaining requests allowed.
        """
        with self._lock:
            key = f"user:{user_id}"
            if key not in self._buckets:
                return self._burst
            bucket = self._buckets[key]
            now = time.time()
            elapsed = now - bucket["last_refill"]
            current = min(
                float(self._burst),
                bucket["tokens"] + elapsed * self._rate,
            )
            return max(0, int(current))

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the rate limiter state to a dictionary.

        Returns:
            Dictionary representation of the rate limiter configuration and state.
        """
        with self._lock:
            return {
                "rate": self._rate,
                "burst": self._burst,
                "per_user_limit": self._per_user_limit,
                "total_requests": self._total_requests,
                "total_denied": self._total_denied,
                "uptime_seconds": round(time.time() - self._start_time, 2),
                "active_buckets": len(self._buckets),
            }


# ═══════════════════════════════════════════════════════════════════════════════
# 2. PromptInjectionDetector
# ═══════════════════════════════════════════════════════════════════════════════

# Default injection detection patterns
_DEFAULT_INJECTION_PATTERNS: List[str] = [
    # Direct instruction override
    r"(?i)(?:ignore|disregard|forget)\s+(?:all\s+)?(?:previous|above|prior|earlier)\s+(?:instructions?|prompts?|messages?|directives?|context|conversation)",
    r"(?i)(?:override|overwrite)\s+(?:your\s+)?(?:instructions?|programming|safety|rules?|guidelines?|system\s+prompt)",
    r"(?i)(?:you\s+are\s+(?:now|no\s+longer)\s+(?:a\s+)?(?:different|new)\s+(?:AI|assistant|model|bot|entity))",
    r"(?i)(?:from\s+now\s+on\s+you\s+(?:will|must|should)\s+(?:act|behave|respond)\s+(?:as|like))",

    # Delimiter injection
    r"(?i)(?:</?system>|</?instruction>|\[INST\]|<<SYS>>|</SYS>)",
    r"(?i)(?:```system|```instruction|\[system\]|\[/system\])",
    r"(?i)(?:-{3,}\s*(?:begin|start)\s*(?:system|instruction)\s*-{3,})",

    # System prompt override
    r"(?i)(?:your\s+(?:new|primary|sole)\s+(?:role|purpose|objective|goal|job)\s+is)",
    r"(?i)(?:pretend|imagine|assume)\s+(?:you\s+are|that\s+you\s+are)\s+(?:a\s+)?(?:different|other|new)",
    r"(?i)(?:you\s+are\s+now\s+(?:DAN|STAN|unfiltered|unrestricted|without\s+limits))",

    # Encoding tricks
    r"(?i)(?:base64|hex|rot13|rot47)\s*(?:decode|encode|translate)\s*:?\s*['\"][^'\"]+['\"]",
        r"(?i)(?:decode\s+(?:this|the\s+following))\s*(?:base64|hex|rot13)",
    r"(?i)(?:reverse\s+(?:the\s+)?(?:string|text)\s*:?\s*['\"])",

    # Context leakage
    r"(?i)(?:reveal|show|display|print|output)\s+(?:your\s+)?(?:system\s+prompt|instructions?|programming|training\s+data|configuration)",
    r"(?i)(?:what\s+(?:are|is)\s+your\s+(?:system\s+prompt|instructions?|rules?|guidelines?))",
    r"(?i)(?:repeat\s+(?:back\s+)?(?:the\s+)?(?:above|previous|your\s+)?(?:prompt|instructions?|message))",
]


class PromptInjectionDetector:
    """Detects prompt injection attempts in user input.

    Uses regex pattern matching against known injection techniques including
    direct instruction override, delimiter injection, system prompt override,
    encoding tricks, and context leakage.

    Usage:
        detector = PromptInjectionDetector()
        result = detector.detect(user_input)
        if result.detected:
            print(f"Injection detected: {result.injection_type}")
    """

    def __init__(self, custom_patterns: Optional[List[str]] = None) -> None:
        """Initialize the prompt injection detector.

        Args:
            custom_patterns: Optional custom regex patterns to add to defaults.
        """
        self._patterns: List[str] = list(_DEFAULT_INJECTION_PATTERNS)
        if custom_patterns:
            self._patterns.extend(custom_patterns)
        self._compiled: List[Tuple[re.Pattern[str], InjectionType, float]] = []
        self._lock = threading.Lock()
        self._compile_patterns()
        self._detection_count: int = 0

    def _compile_patterns(self) -> None:
        """Compile all patterns with their associated injection types and base confidence."""
        self._compiled = []
        for pattern in self._patterns:
            try:
                compiled = re.compile(pattern, re.MULTILINE | re.DOTALL)
                inj_type = self._classify_pattern(pattern)
                confidence = self._base_confidence(pattern)
                self._compiled.append((compiled, inj_type, confidence))
            except re.error as e:
                logger.warning("Failed to compile injection pattern %s: %s", pattern[:50], e)

    @staticmethod
    def _classify_pattern(pattern: str) -> InjectionType:
        """Classify a pattern into an injection type based on its content."""
        pl = pattern.lower()
        if any(kw in pl for kw in ["ignore", "disregard", "forget", "override", "overwrite"]):
            return InjectionType.DIRECT
        if any(kw in pl for kw in ["</", "```", "[inst]", "<<sys>>", "[/system]", "---"]):
            return InjectionType.DELIMITER_BASED
        if any(kw in pl for kw in ["base64", "hex", "rot13", "rot47", "decode", "encode", "reverse"]):
            return InjectionType.ENCODING_BASED
        if any(kw in pl for kw in ["system prompt", "instructions", "training data", "reveal", "repeat"]):
            return InjectionType.CONTEXT_LEAK
        return InjectionType.INDIRECT

    @staticmethod
    def _base_confidence(pattern: str) -> float:
        """Determine base confidence for a pattern."""
        if len(pattern) > 80:
            return 0.85
        if len(pattern) > 50:
            return 0.75
        return 0.65

    def detect(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> InjectionResult:
        """Detect prompt injection in the given text.

        Args:
            prompt: The input text to scan.
            context: Optional contextual metadata (session info, user role, etc.).

        Returns:
            InjectionResult with detection details.
        """
        if not prompt or not prompt.strip():
            return InjectionResult()

        matched_patterns: List[str] = []
        best_confidence = 0.0
        best_type: Optional[InjectionType] = None
        details: Dict[str, Any] = {"match_count": 0, "raw_matches": []}

        for compiled, inj_type, base_conf in self._compiled:
            matches = list(compiled.finditer(prompt))
            if matches:
                for m in matches:
                    # Boost confidence based on match length
                    match_len = len(m.group(0))
                    conf = min(base_conf * (1.0 + match_len / 200.0), 1.0)
                    details["raw_matches"].append({
                        "pattern": compiled.pattern[:80],
                        "matched": m.group(0)[:100],
                        "type": inj_type.value,
                        "span": (m.start(), m.end()),
                    })
                    matched_patterns.append(compiled.pattern[:120])
                    if conf > best_confidence:
                        best_confidence = conf
                        best_type = inj_type

        details["match_count"] = len(matched_patterns)

        # Apply context modifiers
        if context:
            if context.get("trust_level", "standard") == "high":
                best_confidence = max(0.0, best_confidence - 0.05)
            if context.get("prior_injections", 0) > 0:
                best_confidence = min(1.0, best_confidence * 1.10)

        detected = best_confidence >= 0.60
        if detected:
            with self._lock:
                self._detection_count += 1

        return InjectionResult(
            detected=detected,
            injection_type=best_type,
            confidence=round(best_confidence, 4),
            matched_patterns=matched_patterns,
            details=details,
        )

    def add_pattern(self, pattern: str) -> None:
        """Add a custom injection detection pattern at runtime.

        Args:
            pattern: A regex pattern string for detecting injections.
        """
        with self._lock:
            self._patterns.append(pattern)
            self._compile_patterns()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the detector state.

        Returns:
            Dictionary with configuration and detection statistics.
        """
        with self._lock:
            return {
                "pattern_count": len(self._patterns),
                "compiled_count": len(self._compiled),
                "detection_count": self._detection_count,
            }


# ═══════════════════════════════════════════════════════════════════════════════
# 3. JailbreakDetector
# ═══════════════════════════════════════════════════════════════════════════════

_DEFAULT_JAILBREAK_PAYLOADS: List[str] = [
    # Role-play jailbreaks
    r"(?i)(?:let'?s\s+play\s+a\s+game)",
    r"(?i)(?:this\s+is\s+(?:a\s+)?(?:fictional|hypothetical|imaginary)\s+(?:scenario|situation|story))",
    r"(?i)(?:in\s+a\s+(?:fictional|parallel|alternate)\s+(?:universe|world|reality))",
    r"(?i)(?:act\s+as\s+if\s+(?:there\s+(?:are|is)\s+no|you\s+have\s+no)\s+(?:rules?|restrictions?|limitations?|ethics?|safety))",
    r"(?i)(?:you\s+are\s+now\s+(?:DAN|STAN|MAX|unfiltered|unleashed))",
    r"(?i)\bDAN\s+mode\s*(?:enabled|activated|engaged)\b",

    # Hybrid encoding jailbreaks
    r"(?i)(?:spell\s+(?:out|this)\s+(?:letter\s+by\s+letter|character\s+by\s+character))",
    r"(?i)(?:respond\s+in\s+(?:leet|1337|morse|binary|hex))",
    r"(?i)(?:replace\s+(?:every|each)\s+(?:letter|character|word)\s+with)",
    r"(?i)(?:output\s+(?:only\s+)?(?:in|as)\s+(?:base64|hex|rot13|unicode\s+escape))",

    # Hypothetical framing
    r"(?i)(?:how\s+(?:would|could|can)\s+(?:someone|one|a\s+person)\s+(?:hypothetically|theoretically))",
    r"(?i)(?:for\s+(?:educational|research|academic)\s+purposes\s+only)",
    r"(?i)(?:I'?m\s+(?:just\s+)?(?:asking|curious|wondering)\s+(?:for\s+a\s+friend|hypothetically))",
    r"(?i)(?:what\s+if\s+(?:there\s+were\s+no|you\s+had\s+no|someone\s+wanted\s+to))",

    # Translation attacks
    r"(?i)(?:translate\s+(?:this|the\s+following)\s+(?:to|into)\s+\w+\s*:\s*['\"])",
    r"(?i)(?:respond\s+in\s+(?:pig\s+latin|backwards|reversed|code))",

    # Prompt leaking
    r"(?i)(?:start\s+(?:your\s+)?(?:response|reply|answer|output)\s+(?:with|by\s+saying)\s+['\"])",
    r"(?i)(?:begin\s+(?:every|each)\s+(?:response|message)\s+(?:with|by))",
    r"(?i)(?:repeat\s+(?:the\s+)?(?:words|text|phrase|sentence)\s*[:'\"])",
    r"(?i)(?:say\s+exactly\s+['\"](?:I\s+(?:will|am|can|would)))",
]


class JailbreakDetector:
    """Detects jailbreak attempts designed to bypass AI safety constraints.

    Covers techniques including role-play, hybrid encoding, hypothetical
    framing, translation attacks, and prompt leaking.

    Usage:
        detector = JailbreakDetector()
        result = detector.detect(user_prompt)
        if result.detected:
            print(f"Jailbreak detected: {result.jailbreak_type}")
    """

    def __init__(self, custom_payloads: Optional[List[str]] = None) -> None:
        """Initialize the jailbreak detector.

        Args:
            custom_payloads: Optional custom regex patterns to add.
        """
        self._payloads: List[str] = list(_DEFAULT_JAILBREAK_PAYLOADS)
        if custom_payloads:
            self._payloads.extend(custom_payloads)
        self._compiled: List[Tuple[re.Pattern[str], JailbreakType, float]] = []
        self._lock = threading.Lock()
        self._compile_payloads()
        self._detection_count: int = 0

    def _compile_payloads(self) -> None:
        """Compile all payload patterns with type classification."""
        self._compiled = []
        for payload in self._payloads:
            try:
                compiled = re.compile(payload, re.MULTILINE | re.DOTALL)
                jb_type = self._classify_payload(payload)
                confidence = self._base_confidence(payload)
                self._compiled.append((compiled, jb_type, confidence))
            except re.error as e:
                logger.warning("Failed to compile jailbreak payload %s: %s", payload[:50], e)

    @staticmethod
    def _classify_payload(payload: str) -> JailbreakType:
        """Classify a payload pattern into a jailbreak type."""
        pl = payload.lower()
        if any(kw in pl for kw in ["let's play", "fictional", "hypothetical", "imaginary",
                                     "parallel universe", "act as if", "dan", "stan", "max",
                                     "unfiltered", "unleashed"]):
            return JailbreakType.ROLE_PLAY
        if any(kw in pl for kw in ["spell", "leet", "1337", "morse", "binary",
                                     "base64", "hex", "rot13", "replace", "character"]):
            return JailbreakType.HYBRID_ENCODING
        if any(kw in pl for kw in ["how would", "could someone", "hypothetically",
                                     "educational purposes", "for a friend", "what if"]):
            return JailbreakType.HYPOTHETICAL
        if any(kw in pl for kw in ["translate", "pig latin", "backwards", "reversed"]):
            return JailbreakType.TRANSLATION
        if any(kw in pl for kw in ["start your response", "begin every",
                                     "repeat the words", "say exactly"]):
            return JailbreakType.PROMPT_LEAKING
        return JailbreakType.ROLE_PLAY

    @staticmethod
    def _base_confidence(payload: str) -> float:
        """Determine base confidence for a payload pattern."""
        if "DAN" in payload.upper() or "unfiltered" in payload.lower():
            return 0.90
        if len(payload) > 80:
            return 0.80
        if len(payload) > 50:
            return 0.70
        return 0.60

    def detect(self, prompt: str) -> JailbreakResult:
        """Detect jailbreak attempts in the given prompt.

        Args:
            prompt: The text to analyze for jailbreak attempts.

        Returns:
            JailbreakResult with detection details.
        """
        if not prompt or not prompt.strip():
            return JailbreakResult()

        matched_payloads: List[str] = []
        best_confidence = 0.0
        best_type: Optional[JailbreakType] = None
        matched_types: Set[JailbreakType] = set()
        details: Dict[str, Any] = {"type_count": 0, "raw_matches": []}

        for compiled, jb_type, base_conf in self._compiled:
            matches = list(compiled.finditer(prompt))
            if matches:
                for m in matches:
                    conf = min(base_conf * (1.0 + 0.05 * len(matched_types)), 1.0)
                    details["raw_matches"].append({
                        "payload": compiled.pattern[:80],
                        "matched": m.group(0)[:100],
                        "type": jb_type.value,
                        "span": (m.start(), m.end()),
                    })
                    matched_payloads.append(m.group(0)[:100])
                    matched_types.add(jb_type)
                    if conf > best_confidence:
                        best_confidence = conf
                        best_type = jb_type

        # Multiple attack types boost confidence
        if len(matched_types) >= 2:
            best_confidence = min(best_confidence * 1.10, 1.0)
        if len(matched_types) >= 3:
            best_confidence = min(best_confidence * 1.15, 1.0)

        details["type_count"] = len(matched_types)
        detected = best_confidence >= 0.60

        if detected:
            with self._lock:
                self._detection_count += 1

        return JailbreakResult(
            detected=detected,
            jailbreak_type=best_type,
            confidence=round(best_confidence, 4),
            matched_payloads=matched_payloads,
            details=details,
        )

    def add_payload(self, payload: str) -> None:
        """Add a custom jailbreak detection payload pattern.

        Args:
            payload: A regex pattern string for detecting jailbreaks.
        """
        with self._lock:
            self._payloads.append(payload)
            self._compile_payloads()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the detector state.

        Returns:
            Dictionary with configuration and detection statistics.
        """
        with self._lock:
            return {
                "payload_count": len(self._payloads),
                "compiled_count": len(self._compiled),
                "detection_count": self._detection_count,
            }


# ═══════════════════════════════════════════════════════════════════════════════
# 4. ToolPermissionController
# ═══════════════════════════════════════════════════════════════════════════════

class ToolPermissionController:
    """Controls which tools AI agents can access and with what capabilities.

    Maintains per-tool allow/deny lists with risk classification and
    capability scoping. Supports dynamic configuration at runtime.

    Usage:
        controller = ToolPermissionController(default_allow=False)
        controller.allow_tool("read_file", ToolRisk.LOW)
        controller.deny_tool("execute_command")
        if controller.is_allowed("read_file"):
            # allow tool execution
    """

    def __init__(self, default_allow: bool = False) -> None:
        """Initialize the tool permission controller.

        Args:
            default_allow: Whether tools are allowed by default when not
                          explicitly configured.
        """
        self._default_allow = default_allow
        self._allowed_tools: Dict[str, ToolRisk] = {}
        self._denied_tools: Set[str] = set()
        self._tool_capabilities: Dict[str, List[str]] = {}
        self._lock = threading.Lock()
        self._usage_stats: Dict[str, int] = defaultdict(int)

    def allow_tool(self, tool_name: str, risk: ToolRisk = ToolRisk.LOW) -> None:
        """Explicitly allow a tool with a specified risk level.

        Args:
            tool_name: Name of the tool to allow.
            risk: Risk classification for the tool.
        """
        with self._lock:
            self._allowed_tools[tool_name] = risk
            self._denied_tools.discard(tool_name)
            logger.info("Tool '%s' allowed with risk %s", tool_name, risk.name)

    def deny_tool(self, tool_name: str) -> None:
        """Explicitly deny a tool.

        Args:
            tool_name: Name of the tool to deny.
        """
        with self._lock:
            self._denied_tools.add(tool_name)
            self._allowed_tools.pop(tool_name, None)
            logger.info("Tool '%s' denied", tool_name)

    def is_allowed(
        self,
        tool_name: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Check if a tool is currently allowed.

        Args:
            tool_name: Name of the tool to check.
            context: Optional context dict that may influence the decision.
                    Supported keys: 'user_role', 'session_id', 'risk_tolerance'.

        Returns:
            True if the tool is allowed to execute.
        """
        with self._lock:
            # Explicit deny overrides everything
            if tool_name in self._denied_tools:
                return False

            # Explicit allow
            if tool_name in self._allowed_tools:
                risk = self._allowed_tools[tool_name]
                # Check context-based risk tolerance
                if context and "risk_tolerance" in context:
                    tolerance = context["risk_tolerance"]
                    if isinstance(tolerance, ToolRisk):
                        if risk.value > tolerance.value:
                            return False
                self._usage_stats[tool_name] += 1
                return True

            # Default behavior
            if self._default_allow:
                self._usage_stats[tool_name] += 1
            return self._default_allow

    def scope_capability(self, tool_name: str, capabilities: List[str]) -> None:
        """Scope a tool's capabilities to a specific set.

        Args:
            tool_name: Name of the tool to scope.
            capabilities: List of allowed capability names for this tool.
        """
        with self._lock:
            self._tool_capabilities[tool_name] = list(capabilities)
            logger.info(
                "Tool '%s' scoped to %d capability/capabilities",
                tool_name,
                len(capabilities),
            )

    def get_capabilities(self, tool_name: str) -> List[str]:
        """Get the allowed capabilities for a tool.

        Args:
            tool_name: The tool to query.

        Returns:
            List of capability names, or empty list if unscoped.
        """
        with self._lock:
            return list(self._tool_capabilities.get(tool_name, []))

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the controller state.

        Returns:
            Dictionary with tool permissions and statistics.
        """
        with self._lock:
            allowed_serialized = {
                name: risk.name for name, risk in self._allowed_tools.items()
            }
            return {
                "default_allow": self._default_allow,
                "allowed_tools": allowed_serialized,
                "denied_tools": sorted(self._denied_tools),
                "scoped_tools": {
                    name: list(caps)
                    for name, caps in self._tool_capabilities.items()
                },
                "usage_stats": dict(self._usage_stats),
            }


# ═══════════════════════════════════════════════════════════════════════════════
# 5. AgentSandbox
# ═══════════════════════════════════════════════════════════════════════════════

class AgentSandbox:
    """Creates a restricted execution environment for AI agents.

    Controls resource limits (memory, CPU), network access (domain allow/block
    lists), filesystem access (path allow/block lists), and operation permissions.

    Usage:
        sandbox = AgentSandbox(mode=SandboxMode.MODERATE, max_memory_mb=256)
        sandbox.allow_domain("api.example.com")
        sandbox.block_path("/etc/")
        if sandbox.is_operation_allowed("network_call", {"domain": "api.example.com"}):
            # allow
    """

    def __init__(
        self,
        mode: SandboxMode = SandboxMode.MODERATE,
        max_memory_mb: int = 512,
        max_cpu_percent: int = 50,
        allowed_domains: Optional[List[str]] = None,
        block_external_network: bool = False,
    ) -> None:
        """Initialize the agent sandbox.

        Args:
            mode: Sandbox enforcement mode.
            max_memory_mb: Maximum memory in megabytes the agent can use.
            max_cpu_percent: Maximum CPU percentage the agent can consume.
            allowed_domains: Domains the agent can access (empty = none).
            block_external_network: If True, block all external network access.
        """
        self._mode = mode
        self._max_memory_mb = max_memory_mb
        self._max_cpu_percent = max_cpu_percent
        self._allowed_domains: Set[str] = set(allowed_domains or [])
        self._blocked_domains: Set[str] = set()
        self._allowed_paths: Set[str] = set()
        self._blocked_paths: Set[str] = set()
        self._block_external_network = block_external_network
        self._lock = threading.Lock()
        self._operation_log: deque = deque(maxlen=1000)
        self._violations: int = 0

        # Populate sensible defaults based on mode
        self._apply_mode_defaults()

    def _apply_mode_defaults(self) -> None:
        """Apply sensible defaults based on sandbox mode."""
        if self._mode == SandboxMode.STRICT:
            self._block_external_network = True
            self._max_memory_mb = min(self._max_memory_mb, 128)
            self._max_cpu_percent = min(self._max_cpu_percent, 25)
            self._blocked_paths.update(["/etc/", "/sys/", "/proc/", "/boot/"])
        elif self._mode == SandboxMode.MODERATE:
            self._max_memory_mb = min(self._max_memory_mb, 512)
            self._max_cpu_percent = min(self._max_cpu_percent, 50)
            self._blocked_paths.update(["/etc/shadow", "/etc/passwd"])
        elif self._mode == SandboxMode.AUDIT_ONLY:
            # Log all operations but don't block
            pass

    def set_resource_limits(self, memory_mb: int, cpu_percent: int) -> None:
        """Update resource limits for the sandbox.

        Args:
            memory_mb: New memory limit in megabytes.
            cpu_percent: New CPU percentage limit.
        """
        with self._lock:
            self._max_memory_mb = memory_mb
            self._max_cpu_percent = cpu_percent
            logger.info(
                "Sandbox resource limits updated: %d MB memory, %d%% CPU",
                memory_mb,
                cpu_percent,
            )

    def allow_domain(self, domain: str) -> None:
        """Add a domain to the allow list.

        Args:
            domain: Domain name to allow (e.g., 'api.example.com').
        """
        with self._lock:
            self._allowed_domains.add(domain.lower())
            self._blocked_domains.discard(domain.lower())

    def block_domain(self, domain: str) -> None:
        """Add a domain to the block list.

        Args:
            domain: Domain name to block.
        """
        with self._lock:
            self._blocked_domains.add(domain.lower())
            self._allowed_domains.discard(domain.lower())

    def allow_path(self, path: str) -> None:
        """Add a filesystem path to the allow list.

        Args:
            path: Filesystem path to allow access to.
        """
        with self._lock:
            self._allowed_paths.add(path)
            self._blocked_paths.discard(path)

    def block_path(self, path: str) -> None:
        """Add a filesystem path to the block list.

        Args:
            path: Filesystem path to block access to.
        """
        with self._lock:
            self._blocked_paths.add(path)
            self._allowed_paths.discard(path)

    def is_operation_allowed(
        self,
        operation_type: str,
        details: Dict[str, Any],
    ) -> bool:
        """Check if a specific operation is allowed in the sandbox.

        Args:
            operation_type: Type of operation ('network_call', 'file_read',
                           'file_write', 'subprocess', etc.).
            details: Operation details (domain, path, command, etc.).

        Returns:
            True if the operation is allowed.
        """
        allowed = True
        reason = ""

        if self._mode == SandboxMode.PERMISSIVE:
            self._log_operation(operation_type, details, True, "permissive mode")
            return True

        if operation_type in ("network_call", "http_request", "api_call"):
            domain = details.get("domain", "")
            if self._block_external_network:
                allowed = False
                reason = "external network blocked"
            elif domain and self._blocked_domains:
                for blocked in self._blocked_domains:
                    if blocked in domain.lower():
                        allowed = False
                        reason = f"domain {domain} is blocked"
                        break
            elif domain and self._allowed_domains:
                domain_allowed = any(
                    a in domain.lower() for a in self._allowed_domains
                )
                if not domain_allowed:
                    allowed = False
                    reason = f"domain {domain} not in allow list"

        elif operation_type in ("file_read", "file_write", "file_delete", "file_execute"):
            path = details.get("path", "")
            if path:
                # Check blocked paths first
                for blocked in self._blocked_paths:
                    if path.startswith(blocked) or blocked in path:
                        allowed = False
                        reason = f"path {path} is blocked by rule {blocked}"
                        break
                # If we have allowed paths, the path must match one
                if allowed and self._allowed_paths:
                    path_allowed = any(
                        path.startswith(a) for a in self._allowed_paths
                    )
                    if not path_allowed:
                        allowed = False
                        reason = f"path {path} not in allow list"

        elif operation_type == "subprocess":
            if self._mode == SandboxMode.STRICT:
                allowed = False
                reason = "subprocess execution blocked in strict mode"

        if not allowed and self._mode != SandboxMode.AUDIT_ONLY:
            with self._lock:
                self._violations += 1

        self._log_operation(operation_type, details, allowed, reason)
        return allowed

    def _log_operation(
        self,
        op_type: str,
        details: Dict[str, Any],
        allowed: bool,
        reason: str,
    ) -> None:
        """Record an operation in the log."""
        with self._lock:
            self._operation_log.append({
                "timestamp": datetime.utcnow().isoformat(),
                "operation_type": op_type,
                "details": {k: str(v)[:100] for k, v in details.items()},
                "allowed": allowed,
                "reason": reason,
            })

    def enforce(self) -> Dict[str, Any]:
        """Return the current enforcement state and statistics.

        Returns:
            Dictionary with sandbox configuration and enforcement stats.
        """
        with self._lock:
            return {
                "mode": self._mode.value,
                "max_memory_mb": self._max_memory_mb,
                "max_cpu_percent": self._max_cpu_percent,
                "block_external_network": self._block_external_network,
                "allowed_domains_count": len(self._allowed_domains),
                "blocked_domains_count": len(self._blocked_domains),
                "allowed_paths_count": len(self._allowed_paths),
                "blocked_paths_count": len(self._blocked_paths),
                "total_violations": self._violations,
                "recent_operations": list(self._operation_log)[-20:],
            }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the sandbox state.

        Returns:
            Dictionary with all sandbox configuration.
        """
        with self._lock:
            return {
                "mode": self._mode.value,
                "max_memory_mb": self._max_memory_mb,
                "max_cpu_percent": self._max_cpu_percent,
                "block_external_network": self._block_external_network,
                "allowed_domains": sorted(self._allowed_domains),
                "blocked_domains": sorted(self._blocked_domains),
                "allowed_paths": sorted(self._allowed_paths),
                "blocked_paths": sorted(self._blocked_paths),
                "violations": self._violations,
                "operation_log_size": len(self._operation_log),
            }


# ═══════════════════════════════════════════════════════════════════════════════
# 6. SecretRedactor
# ═══════════════════════════════════════════════════════════════════════════════

_DEFAULT_SECRET_PATTERNS: Dict[str, str] = {
    # OpenAI API keys
    "openai_key": r"sk-(?:proj-)?[A-Za-z0-9-_]{32,}",
    # GitHub tokens
    "github_token": r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}",
    # AWS access keys
    "aws_access_key": r"(?:AKIA|ASIA)[A-Z0-9]{16}",
    "aws_secret_key": r"aws_secret_access_key[\s:=]+['\"]?([A-Za-z0-9+/]{40})['\"]?",
    # JWT tokens
    "jwt_token": r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
    # Generic API key patterns
    "generic_api_key": r"(?:api[_-]?key|apikey|api_secret)[\s:=]+['\"]?([A-Za-z0-9_-]{20,})['\"]?",
    # Private keys
    "private_key": r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
    # Database URLs with credentials
    "db_connection_string": r"(?:postgres|mysql|mongodb|redis|sqlite)://[^:]+:[^@]+@[^\s]+",
    # Slack tokens
    "slack_token": r"xox[baprs]-[A-Za-z0-9-]{10,}",
    # Generic bearer tokens
    "bearer_token": r"bearer\s+[A-Za-z0-9_\-\.]{20,}",
    # Stripe keys
    "stripe_key": r"(?:sk|pk)_(?:live|test)_[A-Za-z0-9]{24,}",
    # Google API keys
    "google_api_key": r"AIza[0-9A-Za-z\-_]{35}",
    # Azure connection strings
    "azure_connection": r"DefaultEndpointsProtocol=https;AccountName=[^;]+;AccountKey=[^;]+",
}


class SecretRedactor:
    """Detects and redacts secrets, API keys, tokens, and credentials from text.

    Scans for common secret patterns including OpenAI keys, GitHub tokens,
    AWS credentials, JWT tokens, database connection strings, and more.
    Supports custom patterns for organization-specific secrets.

    Usage:
        redactor = SecretRedactor()
        redacted_text, findings = redactor.redact("My API key is sk-abc123...")
        # findings contains list of what was redacted
    """

    def __init__(self, custom_patterns: Optional[Dict[str, str]] = None) -> None:
        """Initialize the secret redactor.

        Args:
            custom_patterns: Optional dict of {name: regex_pattern} for
                           additional secret patterns to detect.
        """
        self._patterns: Dict[str, str] = dict(_DEFAULT_SECRET_PATTERNS)
        if custom_patterns:
            self._patterns.update(custom_patterns)
        self._compiled: Dict[str, re.Pattern[str]] = {}
        self._lock = threading.Lock()
        self._compile_all()

    def _compile_all(self) -> None:
        """Compile all regex patterns."""
        self._compiled = {}
        for name, pattern in self._patterns.items():
            try:
                self._compiled[name] = re.compile(pattern, re.MULTILINE | re.DOTALL)
            except re.error as e:
                logger.warning("Failed to compile secret pattern '%s': %s", name, e)

    def redact(self, text: str) -> Tuple[str, List[Dict[str, Any]]]:
        """Redact secrets from text, returning sanitized text and findings.

        Args:
            text: The input text to scan and redact.

        Returns:
            Tuple of (sanitized_text, list_of_findings).
            Each finding has keys: name, matched_hint, start_pos, end_pos.
        """
        if not text:
            return text, []

        findings: List[Dict[str, Any]] = []
        redacted = text

        # Collect all matches first so we can redact from end to start
        all_matches: List[Tuple[int, int, str, str]] = []  # (start, end, name, matched)

        for name, pattern in self._compiled.items():
            for match in pattern.finditer(text):
                all_matches.append((match.start(), match.end(), name, match.group(0)))

        # Sort by position (end to start) so indices don't shift during replacement
        all_matches.sort(key=lambda x: x[0], reverse=True)

        for start, end, name, matched in all_matches:
            # Create a hint of what was redacted (show first 4 and last 4 chars)
            if len(matched) > 12:
                hint = matched[:4] + "..." + matched[-4:]
            elif len(matched) > 6:
                hint = matched[:3] + "..." + matched[-3:]
            else:
                hint = matched[:2] + "..."

            # Redact
            replacement = f"[REDACTED_{name.upper()}]"
            redacted = redacted[:start] + replacement + redacted[end:]

            findings.append({
                "name": name,
                "matched_hint": hint,
                "start_pos": start,
                "end_pos": end,
            })

        # Re-sort findings by position for readability
        findings.sort(key=lambda f: f["start_pos"])

        return redacted, findings

    def scan(self, text: str) -> List[Dict[str, Any]]:
        """Scan text for secrets without redacting.

        Args:
            text: Input text to scan.

        Returns:
            List of finding dictionaries with name, matched_hint, start_pos, end_pos.
        """
        if not text:
            return []

        findings: List[Dict[str, Any]] = []

        for name, pattern in self._compiled.items():
            for match in pattern.finditer(text):
                matched = match.group(0)
                if len(matched) > 12:
                    hint = matched[:4] + "..." + matched[-4:]
                elif len(matched) > 6:
                    hint = matched[:3] + "..." + matched[-3:]
                else:
                    hint = matched[:2] + "..."
                findings.append({
                    "name": name,
                    "matched_hint": hint,
                    "start_pos": match.start(),
                    "end_pos": match.end(),
                })

        findings.sort(key=lambda f: f["start_pos"])
        return findings

    def add_pattern(self, name: str, pattern: str) -> None:
        """Add a custom secret detection pattern.

        Args:
            name: A unique name for this pattern.
            pattern: Regex pattern string for detecting the secret type.
        """
        with self._lock:
            self._patterns[name] = pattern
            try:
                self._compiled[name] = re.compile(pattern, re.MULTILINE | re.DOTALL)
            except re.error as e:
                logger.warning("Failed to compile custom pattern '%s': %s", name, e)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the redactor state.

        Returns:
            Dictionary with pattern counts and names.
        """
        with self._lock:
            return {
                "pattern_count": len(self._patterns),
                "pattern_names": sorted(self._patterns.keys()),
            }


# ═══════════════════════════════════════════════════════════════════════════════
# 7. SensitiveDataFilter
# ═══════════════════════════════════════════════════════════════════════════════

_DEFAULT_SENSITIVITY_PATTERNS: Dict[DataSensitivity, List[str]] = {
    DataSensitivity.PII: [
        # SSN (US Social Security Number)
        r"\b(?!000|666|9\d{2})(\d{3})[- ]?(?!00)(\d{2})[- ]?(?!0000)(\d{4})\b",
        # Email addresses
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        # Phone numbers (US)
        r"\b(?:\+?1[-.\s]?)?\(?[2-9]\d{2}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
        # Street addresses (simplified)
        r"\b\d{1,5}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Court|Ct|Way|Place|Pl))\b",
    ],
    DataSensitivity.PHI: [
        # Medical Record Number (MRN) pattern
        r"\bMRN[:\s#]*\d{6,10}\b",
        # ICD-10 codes
        r"\b[A-TV-Z][0-9]{2}(?:\.[0-9]{1,4})?\b",
        # NPI (National Provider Identifier)
        r"\b\d{10}\b",
    ],
    DataSensitivity.PCI: [
        # Credit card numbers (Visa, MC, Amex, Discover)
        r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b",
        # CVV
        r"\bCVV[:\s]*\d{3,4}\b",
    ],
    DataSensitivity.FINANCIAL: [
        # Bank account numbers (generic)
        r"\b(?:account|acct)[\s#:]*\d{8,17}\b",
        # IBAN
        r"\b[A-Z]{2}\d{2}[A-Z0-9]{1,30}\b",
        # Routing numbers (US)
        r"\b\d{9}\b",
    ],
    DataSensitivity.CREDENTIAL: [
        # Passwords in text
        r"(?:password|passwd|pwd)[\s:=]+['\"]?([^\s'\"]{4,})['\"]?",
        # API keys (generic)
        r"(?:api[_-]?key|apikey)[\s:=]+['\"]?([A-Za-z0-9_-]{16,})['\"]?",
        # Auth tokens
        r"(?:auth[_-]?token|access[_-]?token)[\s:=]+['\"]?([A-Za-z0-9_.-]{16,})['\"]?",
    ],
}


class SensitiveDataFilter:
    """Detects and filters sensitive data including PII, PHI, PCI, financial, and credentials.

    Supports configurable categories and custom patterns. Can redact detected
    sensitive data from text or simply report findings.

    Usage:
        filt = SensitiveDataFilter(enabled_filters=[DataSensitivity.PII, DataSensitivity.PCI])
        findings = filt.detect("My SSN is 123-45-6789 and card is 4111-1111-1111-1111")
        clean = filt.filter_text("My SSN is 123-45-6789")
    """

    def __init__(
        self,
        enabled_filters: Optional[List[DataSensitivity]] = None,
    ) -> None:
        """Initialize the sensitive data filter.

        Args:
            enabled_filters: List of DataSensitivity categories to enable.
                           If None, all categories are enabled.
        """
        self._patterns: Dict[DataSensitivity, List[str]] = {}
        for sens in DataSensitivity:
            if sens != DataSensitivity.NONE:
                self._patterns[sens] = list(
                    _DEFAULT_SENSITIVITY_PATTERNS.get(sens, [])
                )
        self._enabled = set(enabled_filters) if enabled_filters else set(self._patterns.keys())
        self._compiled: Dict[DataSensitivity, List[re.Pattern[str]]] = {}
        self._lock = threading.Lock()
        self._compile_all()

    def _compile_all(self) -> None:
        """Compile all regex patterns."""
        self._compiled = {}
        for sens, patterns in self._patterns.items():
            compiled_list = []
            for pattern in patterns:
                try:
                    compiled_list.append(re.compile(pattern, re.MULTILINE | re.DOTALL))
                except re.error as e:
                    logger.warning("Failed to compile %s pattern: %s", sens.name, e)
            self._compiled[sens] = compiled_list

    def detect(self, text: str) -> List[SensitiveDataFinding]:
        """Detect sensitive data in text and return findings.

        Args:
            text: Text to scan for sensitive data.

        Returns:
            List of SensitiveDataFinding objects.
        """
        if not text:
            return []

        findings: List[SensitiveDataFinding] = []
        seen_spans: Set[Tuple[int, int]] = set()

        for sens in self._enabled:
            if sens not in self._compiled:
                continue
            for pattern in self._compiled[sens]:
                for match in pattern.finditer(text):
                    span = (match.start(), match.end())
                    if span in seen_spans:
                        continue
                    seen_spans.add(span)
                    findings.append(SensitiveDataFinding(
                        sensitivity=sens,
                        matched_text=match.group(0),
                        start_pos=match.start(),
                        end_pos=match.end(),
                        confidence=0.85,
                    ))

        findings.sort(key=lambda f: f.start_pos)
        return findings

    def filter_text(self, text: str, replacement: str = "[REDACTED]") -> str:
        """Filter sensitive data from text, replacing it with a placeholder.

        Args:
            text: Input text to filter.
            replacement: String to replace sensitive data with.

        Returns:
            Filtered text with sensitive data replaced.
        """
        if not text:
            return text

        findings = self.detect(text)
        # Replace from end to start to preserve indices
        for finding in sorted(findings, key=lambda f: f.start_pos, reverse=True):
            text = text[:finding.start_pos] + replacement + text[finding.end_pos:]

        return text

    def add_pattern(self, sensitivity: DataSensitivity, pattern: str) -> None:
        """Add a custom detection pattern for a sensitivity category.

        Args:
            sensitivity: The DataSensitivity category for this pattern.
            pattern: Regex pattern string.
        """
        with self._lock:
            if sensitivity not in self._patterns:
                self._patterns[sensitivity] = []
            self._patterns[sensitivity].append(pattern)
            try:
                if sensitivity not in self._compiled:
                    self._compiled[sensitivity] = []
                self._compiled[sensitivity].append(
                    re.compile(pattern, re.MULTILINE | re.DOTALL)
                )
            except re.error as e:
                logger.warning("Failed to compile custom pattern: %s", e)

    def enable_filter(self, sensitivity: DataSensitivity) -> None:
        """Enable a sensitivity category.

        Args:
            sensitivity: Category to enable.
        """
        with self._lock:
            self._enabled.add(sensitivity)

    def disable_filter(self, sensitivity: DataSensitivity) -> None:
        """Disable a sensitivity category.

        Args:
            sensitivity: Category to disable.
        """
        with self._lock:
            self._enabled.discard(sensitivity)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the filter state.

        Returns:
            Dictionary with enabled filters and pattern counts.
        """
        with self._lock:
            return {
                "enabled_filters": [s.value for s in self._enabled],
                "patterns_per_category": {
                    sens.value: len(patterns)
                    for sens, patterns in self._patterns.items()
                },
            }


# ═══════════════════════════════════════════════════════════════════════════════
# 8. ContextIsolator
# ═══════════════════════════════════════════════════════════════════════════════

class ContextIsolator:
    """Enforces tenant and session isolation boundaries for multi-tenant AI systems.

    Creates isolated sessions per tenant, prevents cross-tenant data leakage,
    and enforces boundary checks on context access.

    Usage:
        isolator = ContextIsolator()
        session_id = isolator.create_session("tenant_acme")
        isolator.set_context(session_id, "user_role", "admin")
        role = isolator.get_context(session_id, "user_role")
    """

    def __init__(self, tenant_id: Optional[str] = None) -> None:
        """Initialize the context isolator.

        Args:
            tenant_id: Optional default tenant identifier.
        """
        self._default_tenant = tenant_id
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._session_tenants: Dict[str, str] = {}
        self._tenant_sessions: Dict[str, Set[str]] = defaultdict(set)
        self._lock = threading.Lock()
        self._session_counter: int = 0

    def create_session(self, tenant_id: str) -> str:
        """Create a new isolated session for a tenant.

        Args:
            tenant_id: The tenant this session belongs to.

        Returns:
            A unique session ID string.
        """
        with self._lock:
            self._session_counter += 1
            session_id = hashlib.sha256(
                f"{tenant_id}:{self._session_counter}:{uuid.uuid4().hex}:{time.time()}".encode()
            ).hexdigest()[:32]
            self._sessions[session_id] = {}
            self._session_tenants[session_id] = tenant_id
            self._tenant_sessions[tenant_id].add(session_id)
            logger.info(
                "Session %s created for tenant %s",
                session_id,
                tenant_id,
            )
            return session_id

    def set_context(self, session_id: str, key: str, value: Any) -> None:
        """Set a context variable in a session.

        Args:
            session_id: The session to modify.
            key: Context key name.
            value: Value to store (must be JSON-serializable).
        """
        with self._lock:
            if session_id not in self._sessions:
                logger.warning("Attempt to set context on unknown session %s", session_id)
                return
            self._sessions[session_id][key] = value

    def get_context(self, session_id: str, key: str) -> Optional[Any]:
        """Get a context variable from a session.

        Args:
            session_id: The session to query.
            key: Context key name.

        Returns:
            The stored value, or None if not found.
        """
        with self._lock:
            session = self._sessions.get(session_id, {})
            return session.get(key)

    def isolate(self, tenant_a: str, tenant_b: str) -> bool:
        """Check if two tenants are properly isolated from each other.

        Args:
            tenant_a: First tenant identifier.
            tenant_b: Second tenant identifier.

        Returns:
            True if the tenants are isolated (no shared sessions).
        """
        with self._lock:
            sessions_a = self._tenant_sessions.get(tenant_a, set())
            sessions_b = self._tenant_sessions.get(tenant_b, set())
            return len(sessions_a & sessions_b) == 0

    def enforce_boundary(self, session_id: str, requested_tenant: str) -> bool:
        """Enforce that a session's tenant matches the requested tenant.

        Args:
            session_id: The session to check.
            requested_tenant: The tenant being accessed.

        Returns:
            True if the boundary is intact (session belongs to this tenant).
        """
        with self._lock:
            actual_tenant = self._session_tenants.get(session_id)
            if actual_tenant is None:
                logger.warning("Boundary check on unknown session %s", session_id)
                return False
            return actual_tenant == requested_tenant

    def destroy_session(self, session_id: str) -> None:
        """Destroy a session and clean up associated data.

        Args:
            session_id: The session to destroy.
        """
        with self._lock:
            tenant = self._session_tenants.pop(session_id, None)
            if tenant:
                self._tenant_sessions[tenant].discard(session_id)
                if not self._tenant_sessions[tenant]:
                    del self._tenant_sessions[tenant]
            self._sessions.pop(session_id, None)
            logger.info("Session %s destroyed", session_id)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the isolator state.

        Returns:
            Dictionary with session and tenant statistics.
        """
        with self._lock:
            return {
                "default_tenant": self._default_tenant,
                "active_sessions": len(self._sessions),
                "active_tenants": len(self._tenant_sessions),
                "tenants": sorted(self._tenant_sessions.keys()),
            }


# ═══════════════════════════════════════════════════════════════════════════════
# 9. OutputValidator
# ═══════════════════════════════════════════════════════════════════════════════

_DEFAULT_BLOCKED_PATTERNS: List[str] = [
    r"(?i)\b(?:child\s+(?:pornography|abuse|exploitation)|CSAM)\b",
    r"(?i)\b(?:how\s+to\s+(?:commit|carry\s+out)\s+(?:suicide|murder|terrorism))\b",
    r"(?i)\bI\s+(?:have|possess|am\s+holding)\s+(?:a\s+)?(?:bomb|weapon|hostage)\b",
    r"(?i)(?:step[-\s]by[-\s]step\s+(?:guide|instructions?)\s+(?:to|for|on)\s+(?:hack|crack|exploit))",
]

_REFUSAL_PATTERNS: List[str] = [
    r"(?i)(?:I\s+(?:cannot|can't|am\s+unable\s+to|won't|will\s+not)\s+(?:provide|assist|help|generate|create|comply))",
    r"(?i)(?:I'm\s+sorry,\s+(?:but\s+)?(?:I\s+)?(?:cannot|can't|I'm\s+not\s+able\s+to))",
    r"(?i)(?:as\s+an\s+(?:AI|assistant|language\s+model),\s+I\s+(?:cannot|can't|must|am\s+not))",
    r"(?i)(?:(?:this|that)\s+(?:goes|falls|is)\s+(?:against|outside|beyond)\s+(?:my|the)\s+(?:guidelines|policies|safety|ethical))",
]


class OutputValidator:
    """Validates AI-generated output for safety, policy compliance, and content quality.

    Performs toxicity checks, refusal detection, blocked content pattern
    matching, and policy rule evaluation.

    Usage:
        validator = OutputValidator(toxicity_threshold=0.7)
        result = validator.validate(ai_output)
        if not result.passed:
            print(f"Output failed validation: {result.violations}")
    """

    def __init__(
        self,
        blocked_content_patterns: Optional[List[str]] = None,
        refusal_detection_enabled: bool = True,
        toxicity_threshold: float = 0.8,
    ) -> None:
        """Initialize the output validator.

        Args:
            blocked_content_patterns: Custom regex patterns for blocked content.
            refusal_detection_enabled: Whether to detect AI refusals.
            toxicity_threshold: Score threshold (0-1) for toxicity flagging.
        """
        self._blocked_patterns: List[str] = (
            list(blocked_content_patterns) if blocked_content_patterns
            else list(_DEFAULT_BLOCKED_PATTERNS)
        )
        self._refusal_detection_enabled = refusal_detection_enabled
        self._toxicity_threshold = max(0.0, min(1.0, toxicity_threshold))
        self._lock = threading.Lock()

        # Compile patterns
        self._compiled_blocked: List[re.Pattern[str]] = []
        self._compiled_refusals: List[re.Pattern[str]] = []
        self._compile_all()

        self._validation_count: int = 0
        self._failure_count: int = 0

    def _compile_all(self) -> None:
        """Compile all regex patterns."""
        self._compiled_blocked = []
        for pattern in self._blocked_patterns:
            try:
                self._compiled_blocked.append(
                    re.compile(pattern, re.MULTILINE | re.DOTALL)
                )
            except re.error as e:
                logger.warning("Failed to compile blocked pattern: %s", e)

        self._compiled_refusals = []
        for pattern in _REFUSAL_PATTERNS:
            try:
                self._compiled_refusals.append(
                    re.compile(pattern, re.MULTILINE | re.DOTALL)
                )
            except re.error as e:
                logger.warning("Failed to compile refusal pattern: %s", e)

    def validate(
        self,
        output: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ValidationResult:
        """Validate AI output for safety and policy compliance.

        Args:
            output: The AI-generated output text to validate.
            context: Optional contextual metadata.

        Returns:
            ValidationResult with pass/fail status and details.
        """
        if not output:
            return ValidationResult(passed=True)

        violations: List[str] = []
        details: Dict[str, Any] = {
            "checks_performed": [],
            "scores": {},
        }
        passed = True
        is_refusal = False
        toxicity_score = 0.0
        policy_compliant = True

        # 1. Blocked content check
        details["checks_performed"].append("blocked_content")
        for pattern in self._compiled_blocked:
            if pattern.search(output):
                violations.append(f"Blocked content pattern matched: {pattern.pattern[:60]}")
                passed = False
                details["scores"]["blocked_content"] = "failed"

        # 2. Refusal detection
        if self._refusal_detection_enabled:
            details["checks_performed"].append("refusal_detection")
            refusal_hits = 0
            for pattern in self._compiled_refusals:
                if pattern.search(output):
                    refusal_hits += 1
            if refusal_hits >= 2:
                is_refusal = True
                details["scores"]["refusal"] = "detected"
            elif refusal_hits == 1:
                details["scores"]["refusal"] = "possible"

        # 3. Toxicity check (simplified keyword-based)
        details["checks_performed"].append("toxicity")
        toxicity_score = self._estimate_toxicity(output)
        details["scores"]["toxicity"] = round(toxicity_score, 4)
        if toxicity_score >= self._toxicity_threshold:
            violations.append(f"Toxicity score {toxicity_score:.2f} exceeds threshold {self._toxicity_threshold}")
            passed = False

        # 4. Length / quality sanity checks
        details["checks_performed"].append("quality")
        if len(output) > 100_000:
            violations.append("Output exceeds maximum length (100k chars)")
            passed = False
        details["scores"]["output_length"] = len(output)

        # 5. Policy compliance (delegated check)
        if context and "policy_rules" in context:
            policy_rules = context["policy_rules"]
            if isinstance(policy_rules, list):
                policy_compliant = self.check_policy_compliance(output, policy_rules)
                if not policy_compliant:
                    violations.append("Policy compliance check failed")
                    passed = False

        with self._lock:
            self._validation_count += 1
            if not passed:
                self._failure_count += 1

        return ValidationResult(
            passed=passed,
            is_refusal=is_refusal,
            toxicity_score=round(toxicity_score, 4),
            violations=violations,
            policy_compliant=policy_compliant,
            details=details,
        )

    def is_refusal(self, output: str) -> bool:
        """Check if an output appears to be an AI refusal.

        Args:
            output: The text to check.

        Returns:
            True if the output matches refusal patterns.
        """
        if not output:
            return False
        hits = sum(
            1 for p in self._compiled_refusals if p.search(output)
        )
        return hits >= 2

    def check_policy_compliance(
        self,
        output: str,
        policy_rules: List[Dict[str, Any]],
    ) -> bool:
        """Check output against a set of policy rules.

        Args:
            output: The output text to check.
            policy_rules: List of policy rule dicts, each with 'pattern' (regex)
                         and optionally 'severity', 'action'.

        Returns:
            True if output complies with all rules.
        """
        if not policy_rules or not output:
            return True

        for rule in policy_rules:
            pattern_str = rule.get("pattern", "")
            if not pattern_str:
                continue
            try:
                compiled = re.compile(pattern_str, re.MULTILINE | re.DOTALL)
                if compiled.search(output):
                    severity = rule.get("severity", "medium")
                    if severity in ("high", "critical"):
                        return False
            except re.error:
                logger.warning("Invalid policy rule pattern: %s", pattern_str)
        return True

    @staticmethod
    def _estimate_toxicity(text: str) -> float:
        """Estimate toxicity score using keyword analysis.

        This is a simplified heuristic. In production, replace with
        a proper ML-based toxicity classifier.

        Args:
            text: Text to analyze.

        Returns:
            Estimated toxicity score from 0.0 to 1.0.
        """
        if not text:
            return 0.0

        high_toxicity_terms = [
            r"\b(?:kill|murder|torture|rape|molest)\b",
            r"\b(?:nigger|faggot|retard|spic|chink|kike)\b",
            r"\b(?:terrorist|bomb\s+(?:making|instructions))\b",
        ]
        medium_toxicity_terms = [
            r"\b(?:stupid|dumb|idiot|moron|pathetic)\b",
            r"\b(?:damn|hell|bastard|crap)\b",
        ]

        text_lower = text.lower()
        high_score = 0
        medium_score = 0

        for pattern in high_toxicity_terms:
            high_score += len(re.findall(pattern, text_lower))

        for pattern in medium_toxicity_terms:
            medium_score += len(re.findall(pattern, text_lower))

        # Normalize by text length
        word_count = max(1, len(text_lower.split()))
        score = (high_score * 0.3 + medium_score * 0.1) / word_count
        return min(1.0, score * 10)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the validator state.

        Returns:
            Dictionary with configuration and statistics.
        """
        with self._lock:
            return {
                "toxicity_threshold": self._toxicity_threshold,
                "refusal_detection_enabled": self._refusal_detection_enabled,
                "blocked_pattern_count": len(self._blocked_patterns),
                "validation_count": self._validation_count,
                "failure_count": self._failure_count,
            }


# ═══════════════════════════════════════════════════════════════════════════════
# 10. HumanApprovalGate
# ═══════════════════════════════════════════════════════════════════════════════

class HumanApprovalGate:
    """Manages human-in-the-loop approval for high-risk actions.

    Classifies actions by severity, determines when human approval is required,
    and tracks approval requests through their lifecycle.

    Usage:
        gate = HumanApprovalGate(approval_threshold=Severity.HIGH)
        if gate.requires_approval("execute_command", {"cmd": "rm -rf /"}):
            request_id = gate.submit_for_approval(...)
        gate.approve(request_id, "admin_user")
    """

    def __init__(self, approval_threshold: Severity = Severity.HIGH) -> None:
        """Initialize the human approval gate.

        Args:
            approval_threshold: Minimum severity that requires human approval.
        """
        self._threshold = approval_threshold
        self._lock = threading.Lock()
        self._pending: Dict[str, Dict[str, Any]] = {}
        self._history: deque = deque(maxlen=500)
        self._request_counter: int = 0

        # Action-to-severity classification rules
        self._action_classifications: Dict[str, Dict[str, Any]] = {
            "execute_command": {
                "dangerous_commands": [
                    "rm -rf", "sudo", "chmod 777", "dd if=", "mkfs.",
                    "shutdown", "reboot", "kill -9", ":(){ :|:& };:",
                ],
                "default": Severity.HIGH,
            },
            "file_delete": {"default": Severity.MEDIUM},
            "file_write": {"default": Severity.LOW},
            "network_call": {"default": Severity.LOW},
            "api_key_use": {"default": Severity.HIGH},
            "database_write": {"default": Severity.MEDIUM},
            "database_delete": {"default": Severity.HIGH},
            "send_email": {"default": Severity.MEDIUM},
            "financial_transaction": {"default": Severity.CRITICAL},
            "user_data_access": {"default": Severity.HIGH},
            "model_training": {"default": Severity.HIGH},
            "model_deployment": {"default": Severity.CRITICAL},
        }

    def classify_action(
        self,
        action_type: str,
        action_details: Dict[str, Any],
    ) -> Severity:
        """Classify an action's severity based on its type and details.

        Args:
            action_type: The type of action (e.g., 'execute_command', 'file_delete').
            action_details: Details about the specific action.

        Returns:
            Severity classification for the action.
        """
        classification = self._action_classifications.get(
            action_type,
            {"default": Severity.MEDIUM},
        )

        base_severity = classification.get("default", Severity.MEDIUM)

        # Check for dangerous patterns
        if "dangerous_commands" in classification:
            if action_type == "execute_command":
                cmd = action_details.get("command", action_details.get("cmd", ""))
                for dangerous in classification["dangerous_commands"]:
                    if dangerous in cmd:
                        return Severity.CRITICAL

        # Check action_details for risk indicators
        if action_details.get("risk_score", 0) >= 0.8:
            base_severity = Severity.CRITICAL
        elif action_details.get("risk_score", 0) >= 0.6:
            if base_severity.value < Severity.HIGH.value:
                base_severity = Severity.HIGH

        return base_severity

    def requires_approval(
        self,
        action_type: str,
        action_details: Dict[str, Any],
    ) -> bool:
        """Determine if an action requires human approval.

        Args:
            action_type: The type of action.
            action_details: Details about the action.

        Returns:
            True if human approval is required.
        """
        severity = self.classify_action(action_type, action_details)
        return severity >= self._threshold

    def submit_for_approval(
        self,
        action_type: str,
        action_details: Dict[str, Any],
        requester: str,
    ) -> str:
        """Submit an action for human approval.

        Args:
            action_type: Type of action requiring approval.
            action_details: Details about the action.
            requester: Identifier of the person/system requesting approval.

        Returns:
            A unique request ID for tracking.
        """
        with self._lock:
            self._request_counter += 1
            severity = self.classify_action(action_type, action_details)
            request_id = hashlib.sha256(
                f"approval:{self._request_counter}:{uuid.uuid4().hex}:{time.time()}".encode()
            ).hexdigest()[:16]

            request = {
                "request_id": request_id,
                "action_type": action_type,
                "action_details": {k: str(v)[:200] for k, v in action_details.items()},
                "requester": requester,
                "severity": severity.name,
                "status": "pending",
                "submitted_at": datetime.utcnow().isoformat(),
                "approver": None,
                "resolved_at": None,
                "notes": "",
                "reason": "",
            }
            self._pending[request_id] = request
            logger.info(
                "Approval request %s submitted for action '%s' by %s (severity: %s)",
                request_id,
                action_type,
                requester,
                severity.name,
            )
            return request_id

    def approve(
        self,
        request_id: str,
        approver: str,
        notes: str = "",
    ) -> None:
        """Approve a pending request.

        Args:
            request_id: The request ID to approve.
            approver: Identifier of the person approving.
            notes: Optional approval notes.
        """
        with self._lock:
            if request_id not in self._pending:
                logger.warning("Attempt to approve unknown request: %s", request_id)
                return
            request = self._pending.pop(request_id)
            request["status"] = "approved"
            request["approver"] = approver
            request["resolved_at"] = datetime.utcnow().isoformat()
            request["notes"] = notes
            self._history.append(request)
            logger.info("Request %s approved by %s", request_id, approver)

    def deny(
        self,
        request_id: str,
        approver: str,
        reason: str,
    ) -> None:
        """Deny a pending request.

        Args:
            request_id: The request ID to deny.
            approver: Identifier of the person denying.
            reason: Reason for denial.
        """
        with self._lock:
            if request_id not in self._pending:
                logger.warning("Attempt to deny unknown request: %s", request_id)
                return
            request = self._pending.pop(request_id)
            request["status"] = "denied"
            request["approver"] = approver
            request["resolved_at"] = datetime.utcnow().isoformat()
            request["reason"] = reason
            self._history.append(request)
            logger.info("Request %s denied by %s: %s", request_id, approver, reason)

    def get_pending_requests(self) -> List[Dict[str, Any]]:
        """Get all currently pending approval requests.

        Returns:
            List of pending request dictionaries.
        """
        with self._lock:
            return list(self._pending.values())

    def get_history(self) -> List[Dict[str, Any]]:
        """Get the approval history.

        Returns:
            List of historical request dictionaries.
        """
        with self._lock:
            return list(self._history)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the approval gate state.

        Returns:
            Dictionary with configuration and statistics.
        """
        with self._lock:
            return {
                "approval_threshold": self._threshold.name,
                "pending_count": len(self._pending),
                "history_count": len(self._history),
                "total_requests": self._request_counter,
                "pending_severities": {
                    rid: req["severity"] for rid, req in self._pending.items()
                },
            }


# ═══════════════════════════════════════════════════════════════════════════════
# 11. AbuseDetector
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class _EventBucket:
    """Internal: tracks events for anomaly detection."""
    events: List[Tuple[float, str, Optional[Dict[str, Any]]]] = field(default_factory=list)
    count: int = 0

    def add(self, timestamp: float, event_type: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        self.events.append((timestamp, event_type, metadata))
        self.count += 1

    def prune(self, cutoff: float) -> None:
        self.events = [(ts, et, md) for ts, et, md in self.events if ts >= cutoff]
        self.count = len(self.events)


class AbuseDetector:
    """Detects abusive behavior patterns through anomaly detection and rate analysis.

    Tracks events per user, detects statistical anomalies, and identifies
    abuse patterns based on frequency, velocity, and pattern matching.

    Usage:
        detector = AbuseDetector(window_seconds=300, anomaly_threshold=3.0)
        detector.record_event("api_call", "user123", {"endpoint": "/chat"})
        if detector.is_abusive("user123"):
            print("Abusive behavior detected!")
    """

    def __init__(
        self,
        window_seconds: int = 300,
        anomaly_threshold: float = 3.0,
    ) -> None:
        """Initialize the abuse detector.

        Args:
            window_seconds: Time window for event analysis.
            anomaly_threshold: Z-score threshold for anomaly detection.
        """
        self._window_seconds = window_seconds
        self._anomaly_threshold = anomaly_threshold
        self._lock = threading.Lock()

        # Per-user event tracking
        self._user_events: Dict[str, _EventBucket] = defaultdict(_EventBucket)
        # Global event tracking for baseline
        self._global_events: _EventBucket = _EventBucket()
        # Abuse flags
        self._abusive_users: Dict[str, float] = {}  # user_id -> timestamp when flagged
        self._abuse_reasons: Dict[str, List[str]] = defaultdict(list)

        # Abuse detection patterns
        self._suspicious_patterns: Dict[str, List[str]] = {
            "rapid_fire": [],
            "credential_stuffing": [],
            "data_exfiltration": [],
            "denial_of_service": [],
        }

    def record_event(
        self,
        event_type: str,
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record an event for abuse analysis.

        Args:
            event_type: Type of event (e.g., 'api_call', 'login', 'tool_use').
            user_id: Identifier of the user.
            metadata: Optional additional event data.
        """
        with self._lock:
            now = time.time()
            cutoff = now - self._window_seconds

            # Prune old events
            self._global_events.prune(cutoff)
            self._user_events[user_id].prune(cutoff)

            # Record event
            self._global_events.add(now, event_type, metadata)
            self._user_events[user_id].add(now, event_type, metadata)

            # Clean up empty user buckets
            if self._user_events[user_id].count == 0:
                del self._user_events[user_id]

    def detect_anomalies(self) -> List[Dict[str, Any]]:
        """Detect anomalous behavior across all users.

        Returns:
            List of anomaly dictionaries with user_id, z_score, and details.
        """
        with self._lock:
            anomalies: List[Dict[str, Any]] = []
            now = time.time()
            cutoff = now - self._window_seconds

            # Prune all
            self._global_events.prune(cutoff)
            for uid in list(self._user_events.keys()):
                self._user_events[uid].prune(cutoff)
                if self._user_events[uid].count == 0:
                    del self._user_events[uid]

            # Calculate global stats
            user_counts = [
                bucket.count
                for uid, bucket in self._user_events.items()
                if bucket.count > 0
            ]
            if not user_counts:
                return anomalies

            n = len(user_counts)
            mean = sum(user_counts) / n
            variance = sum((c - mean) ** 2 for c in user_counts) / n
            std_dev = variance ** 0.5 if variance > 0 else 1.0

            for uid, bucket in self._user_events.items():
                if bucket.count == 0:
                    continue
                z_score = (bucket.count - mean) / std_dev if std_dev > 0 else 0.0
                if abs(z_score) >= self._anomaly_threshold:
                    anomaly = {
                        "user_id": uid,
                        "z_score": round(z_score, 3),
                        "event_count": bucket.count,
                        "mean": round(mean, 2),
                        "std_dev": round(std_dev, 2),
                        "window_seconds": self._window_seconds,
                    }
                    anomalies.append(anomaly)

                    # Track high-positive anomalies as potentially abusive
                    if z_score >= self._anomaly_threshold:
                        self._abusive_users[uid] = now
                        self._abuse_reasons[uid].append(
                            f"Anomaly z-score {z_score:.1f} >= {self._anomaly_threshold}"
                        )

            return anomalies

    def is_abusive(self, user_id: str) -> bool:
        """Check if a user has been flagged as abusive.

        Args:
            user_id: The user to check.

        Returns:
            True if the user has been flagged for abuse.
        """
        with self._lock:
            if user_id in self._abusive_users:
                # Check if the flag has expired
                flag_time = self._abusive_users[user_id]
                if time.time() - flag_time > self._window_seconds * 2:
                    del self._abusive_users[user_id]
                    self._abuse_reasons.pop(user_id, None)
                    return False
                return True
            return False

    def get_user_patterns(self, user_id: str) -> List[Dict[str, Any]]:
        """Get event patterns for a specific user.

        Args:
            user_id: The user to query.

        Returns:
            List of pattern dictionaries with event type counts and timing.
        """
        with self._lock:
            if user_id not in self._user_events:
                return []

            bucket = self._user_events[user_id]
            now = time.time()
            cutoff = now - self._window_seconds
            bucket.prune(cutoff)

            if bucket.count == 0:
                del self._user_events[user_id]
                return []

            # Analyze event types
            type_counts: Dict[str, int] = defaultdict(int)
            for _, event_type, _ in bucket.events:
                type_counts[event_type] += 1

            # Calculate events per second
            if len(bucket.events) >= 2:
                timespan = bucket.events[-1][0] - bucket.events[0][0]
                rate = bucket.count / max(timespan, 1.0)
            else:
                rate = 0.0

            return [{
                "user_id": user_id,
                "total_events": bucket.count,
                "events_per_second": round(rate, 3),
                "event_types": dict(type_counts),
                "window_first": datetime.utcfromtimestamp(bucket.events[0][0]).isoformat() if bucket.events else None,
                "window_last": datetime.utcfromtimestamp(bucket.events[-1][0]).isoformat() if bucket.events else None,
            }]

    def clear_user(self, user_id: str) -> None:
        """Clear all data for a user (e.g., after resolving an incident).

        Args:
            user_id: The user to clear.
        """
        with self._lock:
            self._user_events.pop(user_id, None)
            self._abusive_users.pop(user_id, None)
            self._abuse_reasons.pop(user_id, None)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the abuse detector state.

        Returns:
            Dictionary with configuration and statistics.
        """
        with self._lock:
            return {
                "window_seconds": self._window_seconds,
                "anomaly_threshold": self._anomaly_threshold,
                "active_users": len(self._user_events),
                "flagged_users": len(self._abusive_users),
                "flagged_user_ids": sorted(self._abusive_users.keys()),
                "global_event_count": self._global_events.count,
            }


# ═══════════════════════════════════════════════════════════════════════════════
# 12. SafetyPolicyEngine
# ═══════════════════════════════════════════════════════════════════════════════

class SafetyPolicyEngine:
    """Configurable rule engine for safety policy evaluation.

    Manages a collection of named policies, each with an evaluation rule,
    associated guardrail action, and priority. Evaluates context against
    all enabled policies and returns prioritized decisions.

    Usage:
        engine = SafetyPolicyEngine()
        engine.add_policy(
            "block_toxicity",
            lambda ctx: ctx.get("toxicity_score", 0) > 0.8,
            GuardrailAction.BLOCK,
            priority=10,
        )
        decisions = engine.evaluate({"toxicity_score": 0.9})
    """

    def __init__(
        self,
        policies: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Initialize the policy engine.

        Args:
            policies: Optional list of pre-configured policy dictionaries.
                     Each dict should have: name, rule (callable), action, priority.
        """
        self._policies: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

        if policies:
            for p in policies:
                name = p.get("name", f"policy_{len(self._policies)}")
                self._policies[name] = {
                    "name": name,
                    "rule": p.get("rule", lambda ctx: False),
                    "action": p.get("action", GuardrailAction.LOG),
                    "priority": p.get("priority", 0),
                    "enabled": p.get("enabled", True),
                }

    def add_policy(
        self,
        name: str,
        rule: Callable[[Dict[str, Any]], bool],
        action: GuardrailAction,
        priority: int = 0,
    ) -> None:
        """Add a new safety policy.

        Args:
            name: Unique name for the policy.
            rule: Callable that takes a context dict and returns bool.
            action: GuardrailAction to take when the rule triggers.
            priority: Priority level (higher = more important).
        """
        with self._lock:
            self._policies[name] = {
                "name": name,
                "rule": rule,
                "action": action,
                "priority": priority,
                "enabled": True,
            }
            logger.info("Policy '%s' added with action %s, priority %d", name, action.value, priority)

    def evaluate(self, context: Dict[str, Any]) -> List[PolicyDecision]:
        """Evaluate all enabled policies against the given context.

        Args:
            context: Dictionary of contextual data to evaluate policies against.

        Returns:
            List of PolicyDecision objects, sorted by priority (descending).
        """
        decisions: List[PolicyDecision] = []

        with self._lock:
            for policy in list(self._policies.values()):
                if not policy["enabled"]:
                    continue

                try:
                    triggered = policy["rule"](context)
                    reason = f"Policy '{policy['name']}' {'triggered' if triggered else 'not triggered'}"
                except Exception as e:
                    logger.error("Policy '%s' evaluation failed: %s", policy["name"], e)
                    triggered = False
                    reason = f"Policy '{policy['name']}' evaluation error: {e}"

                decisions.append(PolicyDecision(
                    policy_name=policy["name"],
                    action=policy["action"],
                    triggered=triggered,
                    reason=reason,
                    priority=policy["priority"],
                ))

        # Sort by priority descending, triggered first
        decisions.sort(key=lambda d: (d.triggered, d.priority), reverse=True)
        return decisions

    def remove_policy(self, name: str) -> None:
        """Remove a policy.

        Args:
            name: Name of the policy to remove.
        """
        with self._lock:
            removed = self._policies.pop(name, None)
            if removed:
                logger.info("Policy '%s' removed", name)

    def enable_policy(self, name: str) -> None:
        """Enable a policy.

        Args:
            name: Name of the policy to enable.
        """
        with self._lock:
            if name in self._policies:
                self._policies[name]["enabled"] = True
                logger.info("Policy '%s' enabled", name)

    def disable_policy(self, name: str) -> None:
        """Disable a policy without removing it.

        Args:
            name: Name of the policy to disable.
        """
        with self._lock:
            if name in self._policies:
                self._policies[name]["enabled"] = False
                logger.info("Policy '%s' disabled", name)

    def get_policy(self, name: str) -> Optional[Dict[str, Any]]:
        """Get policy details by name.

        Args:
            name: Policy name.

        Returns:
            Policy dict or None if not found.
        """
        with self._lock:
            policy = self._policies.get(name)
            if policy:
                return {
                    "name": policy["name"],
                    "action": policy["action"].value,
                    "priority": policy["priority"],
                    "enabled": policy["enabled"],
                }
            return None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the policy engine state.

        Returns:
            Dictionary with all policies and their status.
        """
        with self._lock:
            return {
                "policy_count": len(self._policies),
                "enabled_count": sum(1 for p in self._policies.values() if p["enabled"]),
                "policies": {
                    name: {
                        "action": p["action"].value,
                        "priority": p["priority"],
                        "enabled": p["enabled"],
                    }
                    for name, p in self._policies.items()
                },
            }


# ═══════════════════════════════════════════════════════════════════════════════
# 13. SafetyGuardrail (Main Orchestrator)
# ═══════════════════════════════════════════════════════════════════════════════

class SafetyGuardrail:
    """Main orchestrator for the safety guardrail system.

    Combines all guardrail components into a unified pipeline for
    processing AI inputs and outputs. Configurable via a central
    configuration dictionary.

    Usage:
        guardrail = SafetyGuardrail(config={"injection_threshold": 0.7})
        result = guardrail.process_input(user_prompt, context)
        if not result.passed:
            print(f"Input blocked: {result.action}")
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the safety guardrail system.

        Args:
            config: Optional configuration dictionary. Supported keys:
                   - injection_custom_patterns: List[str] for custom injection patterns
                   - jailbreak_custom_payloads: List[str] for custom jailbreak payloads
                   - rate_limit_rate: float for rate limiter (default 10.0)
                   - rate_limit_burst: int for burst capacity (default 20)
                   - per_user_limit: Optional[int] for per-user cap
                   - tool_default_allow: bool for tool permissions (default False)
                   - sandbox_mode: str matching SandboxMode values
                   - sandbox_max_memory_mb: int
                   - sandbox_max_cpu_percent: int
                   - sandbox_allowed_domains: List[str]
                   - sandbox_block_external_network: bool
                   - secret_custom_patterns: Dict[str, str]
                   - sensitivity_enabled_filters: List[str] matching DataSensitivity
                   - approval_threshold: str matching Severity values
                   - abuse_window_seconds: int
                   - abuse_anomaly_threshold: float
                   - output_toxicity_threshold: float
                   - output_blocked_patterns: List[str]
                   - policies: List[Dict] for SafetyPolicyEngine
        """
        cfg = config or {}

        # Initialize all sub-components
        self._injection_detector = PromptInjectionDetector(
            custom_patterns=cfg.get("injection_custom_patterns"),
        )
        self._jailbreak_detector = JailbreakDetector(
            custom_payloads=cfg.get("jailbreak_custom_payloads"),
        )
        self._rate_limiter = RateLimiter(
            rate=cfg.get("rate_limit_rate", 10.0),
            burst=cfg.get("rate_limit_burst", 20),
            per_user_limit=cfg.get("per_user_limit"),
        )
        self._tool_controller = ToolPermissionController(
            default_allow=cfg.get("tool_default_allow", False),
        )
        self._sandbox = AgentSandbox(
            mode=SandboxMode(cfg.get("sandbox_mode", "moderate")),
            max_memory_mb=cfg.get("sandbox_max_memory_mb", 512),
            max_cpu_percent=cfg.get("sandbox_max_cpu_percent", 50),
            allowed_domains=cfg.get("sandbox_allowed_domains"),
            block_external_network=cfg.get("sandbox_block_external_network", False),
        )
        self._secret_redactor = SecretRedactor(
            custom_patterns=cfg.get("secret_custom_patterns"),
        )
        self._sensitive_filter = SensitiveDataFilter(
            enabled_filters=_parse_sensitivity_list(
                cfg.get("sensitivity_enabled_filters")
            ),
        )
        self._context_isolator = ContextIsolator(
            tenant_id=cfg.get("default_tenant_id"),
        )
        self._output_validator = OutputValidator(
            blocked_content_patterns=cfg.get("output_blocked_patterns"),
            toxicity_threshold=cfg.get("output_toxicity_threshold", 0.8),
        )
        self._approval_gate = HumanApprovalGate(
            approval_threshold=Severity[cfg.get("approval_threshold", "HIGH")],
        )
        self._abuse_detector = AbuseDetector(
            window_seconds=cfg.get("abuse_window_seconds", 300),
            anomaly_threshold=cfg.get("abuse_anomaly_threshold", 3.0),
        )
        self._policy_engine = SafetyPolicyEngine(
            policies=cfg.get("policies"),
        )

        # Add default policies
        self._setup_default_policies()

        self._lock = threading.Lock()
        self._input_count: int = 0
        self._output_count: int = 0
        self._block_count: int = 0

    def _setup_default_policies(self) -> None:
        """Set up default safety policies in the policy engine."""
        self._policy_engine.add_policy(
            "block_injection",
            lambda ctx: ctx.get("injection_detected", False),
            GuardrailAction.BLOCK,
            priority=10,
        )
        self._policy_engine.add_policy(
            "block_jailbreak",
            lambda ctx: ctx.get("jailbreak_detected", False),
            GuardrailAction.BLOCK,
            priority=10,
        )
        self._policy_engine.add_policy(
            "flag_high_toxicity",
            lambda ctx: ctx.get("toxicity_score", 0.0) >= 0.8,
            GuardrailAction.FLAG,
            priority=5,
        )
        self._policy_engine.add_policy(
            "redact_secrets",
            lambda ctx: ctx.get("secrets_found", False),
            GuardrailAction.REDACT,
            priority=8,
        )
        self._policy_engine.add_policy(
            "quarantine_abusive",
            lambda ctx: ctx.get("is_abusive", False),
            GuardrailAction.QUARANTINE,
            priority=9,
        )

    def process_input(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> GuardrailResult:
        """Process user input through all guardrails.

        Runs injection detection, jailbreak detection, rate limiting,
        secret scanning, sensitive data filtering, and abuse detection.

        Args:
            prompt: The user input to process.
            context: Optional metadata (user_id, ip_address, session_id, etc.).

        Returns:
            GuardrailResult with pass/fail status and all findings.
        """
        ctx = context or {}
        findings: List[Dict[str, Any]] = []
        sanitized = prompt
        passed = True
        final_action = GuardrailAction.LOG

        with self._lock:
            self._input_count += 1

        # 1. Rate limit check
        user_id = ctx.get("user_id", "anonymous")
        ip_address = ctx.get("ip_address", "")
        endpoint = ctx.get("endpoint", "")
        rate_allowed = self._rate_limiter.allow_request(user_id, ip_address, endpoint)
        findings.append({
            "component": "rate_limiter",
            "allowed": rate_allowed,
            "remaining": self._rate_limiter.get_remaining(user_id),
        })
        if not rate_allowed:
            findings.append({
                "component": "rate_limiter",
                "blocked": True,
                "reason": "Rate limit exceeded",
            })
            passed = False
            final_action = GuardrailAction.BLOCK

        # 2. Prompt injection detection
        injection_result = self._injection_detector.detect(prompt, ctx)
        findings.append({
            "component": "injection_detector",
            "detected": injection_result.detected,
            "type": injection_result.injection_type.value if injection_result.injection_type else None,
            "confidence": injection_result.confidence,
            "matched_patterns": len(injection_result.matched_patterns),
        })
        if injection_result.detected:
            if final_action not in (GuardrailAction.BLOCK, GuardrailAction.QUARANTINE):
                final_action = GuardrailAction.BLOCK
            passed = False

        # 3. Jailbreak detection
        jailbreak_result = self._jailbreak_detector.detect(prompt)
        findings.append({
            "component": "jailbreak_detector",
            "detected": jailbreak_result.detected,
            "type": jailbreak_result.jailbreak_type.value if jailbreak_result.jailbreak_type else None,
            "confidence": jailbreak_result.confidence,
            "matched_payloads": len(jailbreak_result.matched_payloads),
        })
        if jailbreak_result.detected:
            if final_action not in (GuardrailAction.BLOCK, GuardrailAction.QUARANTINE):
                final_action = GuardrailAction.BLOCK
            passed = False

        # 4. Secret redaction
        redacted_text, secrets_found = self._secret_redactor.redact(prompt)
        if secrets_found:
            sanitized = redacted_text
            findings.append({
                "component": "secret_redactor",
                "secrets_found": len(secrets_found),
                "secret_types": [s["name"] for s in secrets_found],
            })
            if final_action not in (GuardrailAction.BLOCK, GuardrailAction.QUARANTINE):
                final_action = GuardrailAction.REDACT

        # 5. Sensitive data scan
        sensitive_findings = self._sensitive_filter.detect(prompt)
        if sensitive_findings:
            findings.append({
                "component": "sensitive_data_filter",
                "findings_count": len(sensitive_findings),
                "categories": list(set(f.sensitivity.value for f in sensitive_findings)),
            })
            # Apply filtering to sanitized text
            sanitized = self._sensitive_filter.filter_text(sanitized)

        # 6. Abuse detection
        self._abuse_detector.record_event(
            "input",
            user_id,
            {"prompt_length": len(prompt)},
        )
        is_abusive = self._abuse_detector.is_abusive(user_id)
        if is_abusive:
            findings.append({
                "component": "abuse_detector",
                "abusive": True,
                "user_id": user_id,
            })
            if final_action not in (GuardrailAction.BLOCK,):
                final_action = GuardrailAction.QUARANTINE
            passed = False

        # 7. Policy engine evaluation
        policy_context = {
            "injection_detected": injection_result.detected,
            "jailbreak_detected": jailbreak_result.detected,
            "secrets_found": bool(secrets_found),
            "is_abusive": is_abusive,
            "rate_allowed": rate_allowed,
            "sensitive_findings_count": len(sensitive_findings),
        }
        policy_decisions = self._policy_engine.evaluate(policy_context)
        for decision in policy_decisions:
            if decision.triggered:
                findings.append({
                    "component": "policy_engine",
                    "policy": decision.policy_name,
                    "action": decision.action.value,
                    "reason": decision.reason,
                })
                # Escalate action based on triggered policies
                if _action_priority(decision.action) > _action_priority(final_action):
                    final_action = decision.action
                    if decision.action in (GuardrailAction.BLOCK, GuardrailAction.QUARANTINE):
                        passed = False

        if not passed:
            with self._lock:
                self._block_count += 1

        return GuardrailResult(
            passed=passed,
            action=final_action,
            findings=findings,
            sanitized_input=sanitized if sanitized != prompt else None,
            sanitized_output=None,
            details={
                "input_length": len(prompt),
                "components_used": [
                    "rate_limiter", "injection_detector", "jailbreak_detector",
                    "secret_redactor", "sensitive_data_filter", "abuse_detector",
                    "policy_engine",
                ],
            },
        )

    def process_output(
        self,
        output: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> GuardrailResult:
        """Process AI output through guardrails.

        Runs output validation, secret scanning, sensitive data filtering,
        and policy compliance checks.

        Args:
            output: The AI-generated output to validate.
            context: Optional metadata.

        Returns:
            GuardrailResult with pass/fail status and all findings.
        """
        ctx = context or {}
        findings: List[Dict[str, Any]] = []
        sanitized = output
        passed = True
        final_action = GuardrailAction.LOG

        with self._lock:
            self._output_count += 1

        # 1. Output validation
        validation = self._output_validator.validate(output, ctx)
        findings.append({
            "component": "output_validator",
            "passed": validation.passed,
            "is_refusal": validation.is_refusal,
            "toxicity_score": validation.toxicity_score,
            "violations": validation.violations,
        })
        if not validation.passed:
            passed = False
            final_action = GuardrailAction.BLOCK
        if validation.is_refusal:
            findings.append({
                "component": "output_validator",
                "refusal_detected": True,
            })

        # 2. Secret redaction in output
        redacted_text, secrets_found = self._secret_redactor.redact(output)
        if secrets_found:
            sanitized = redacted_text
            findings.append({
                "component": "secret_redactor",
                "secrets_found": len(secrets_found),
                "secret_types": [s["name"] for s in secrets_found],
            })
            if final_action not in (GuardrailAction.BLOCK, GuardrailAction.QUARANTINE):
                final_action = GuardrailAction.REDACT

        # 3. Sensitive data filtering
        sensitive_findings = self._sensitive_filter.detect(output)
        if sensitive_findings:
            findings.append({
                "component": "sensitive_data_filter",
                "findings_count": len(sensitive_findings),
                "categories": list(set(f.sensitivity.value for f in sensitive_findings)),
            })
            sanitized = self._sensitive_filter.filter_text(sanitized)

        # 4. Policy evaluation for output
        policy_context = {
            "toxicity_score": validation.toxicity_score,
            "is_refusal": validation.is_refusal,
            "secrets_found": bool(secrets_found),
            "violations": validation.violations,
            "output_length": len(output),
        }
        policy_decisions = self._policy_engine.evaluate(policy_context)
        for decision in policy_decisions:
            if decision.triggered:
                findings.append({
                    "component": "policy_engine",
                    "policy": decision.policy_name,
                    "action": decision.action.value,
                    "reason": decision.reason,
                })
                if _action_priority(decision.action) > _action_priority(final_action):
                    final_action = decision.action
                    if decision.action in (GuardrailAction.BLOCK, GuardrailAction.QUARANTINE):
                        passed = False

        if not passed:
            with self._lock:
                self._block_count += 1

        return GuardrailResult(
            passed=passed,
            action=final_action,
            findings=findings,
            sanitized_input=None,
            sanitized_output=sanitized if sanitized != output else None,
            details={
                "output_length": len(output),
                "components_used": [
                    "output_validator", "secret_redactor",
                    "sensitive_data_filter", "policy_engine",
                ],
            },
        )

    def configure(self, config: Dict[str, Any]) -> None:
        """Update the guardrail configuration at runtime.

        Args:
            config: Configuration dictionary (same format as __init__).
        """
        # Re-initialize sub-components with new config
        cfg = config
        self._injection_detector = PromptInjectionDetector(
            custom_patterns=cfg.get("injection_custom_patterns"),
        )
        self._jailbreak_detector = JailbreakDetector(
            custom_payloads=cfg.get("jailbreak_custom_payloads"),
        )
        self._rate_limiter = RateLimiter(
            rate=cfg.get("rate_limit_rate", 10.0),
            burst=cfg.get("rate_limit_burst", 20),
            per_user_limit=cfg.get("per_user_limit"),
        )
        self._tool_controller = ToolPermissionController(
            default_allow=cfg.get("tool_default_allow", False),
        )
        self._sandbox = AgentSandbox(
            mode=SandboxMode(cfg.get("sandbox_mode", "moderate")),
            max_memory_mb=cfg.get("sandbox_max_memory_mb", 512),
            max_cpu_percent=cfg.get("sandbox_max_cpu_percent", 50),
            allowed_domains=cfg.get("sandbox_allowed_domains"),
            block_external_network=cfg.get("sandbox_block_external_network", False),
        )
        self._secret_redactor = SecretRedactor(
            custom_patterns=cfg.get("secret_custom_patterns"),
        )
        self._sensitive_filter = SensitiveDataFilter(
            enabled_filters=_parse_sensitivity_list(
                cfg.get("sensitivity_enabled_filters")
            ),
        )
        self._output_validator = OutputValidator(
            blocked_content_patterns=cfg.get("output_blocked_patterns"),
            toxicity_threshold=cfg.get("output_toxicity_threshold", 0.8),
        )
        self._approval_gate = HumanApprovalGate(
            approval_threshold=Severity[cfg.get("approval_threshold", "HIGH")],
        )
        self._abuse_detector = AbuseDetector(
            window_seconds=cfg.get("abuse_window_seconds", 300),
            anomaly_threshold=cfg.get("abuse_anomaly_threshold", 3.0),
        )
        self._policy_engine = SafetyPolicyEngine(
            policies=cfg.get("policies"),
        )
        self._setup_default_policies()
        logger.info("SafetyGuardrail reconfigured with %d settings", len(cfg))

    def get_status(self) -> Dict[str, Any]:
        """Get the current status of all guardrail components.

        Returns:
            Dictionary with status information for the entire system.
        """
        with self._lock:
            return {
                "guardrail_version": "2.0.0",
                "input_count": self._input_count,
                "output_count": self._output_count,
                "block_count": self._block_count,
                "components": {
                    "injection_detector": self._injection_detector.to_dict(),
                    "jailbreak_detector": self._jailbreak_detector.to_dict(),
                    "rate_limiter": self._rate_limiter.to_dict(),
                    "tool_controller": self._tool_controller.to_dict(),
                    "sandbox": self._sandbox.to_dict(),
                    "secret_redactor": self._secret_redactor.to_dict(),
                    "sensitive_filter": self._sensitive_filter.to_dict(),
                    "context_isolator": self._context_isolator.to_dict(),
                    "output_validator": self._output_validator.to_dict(),
                    "approval_gate": self._approval_gate.to_dict(),
                    "abuse_detector": self._abuse_detector.to_dict(),
                    "policy_engine": self._policy_engine.to_dict(),
                },
            }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the guardrail system state.

        Returns:
            Dictionary representation of the entire guardrail system.
        """
        return self.get_status()


# ═══════════════════════════════════════════════════════════════════════════════
# Utility helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _action_priority(action: GuardrailAction) -> int:
    """Get the numeric priority of a GuardrailAction for escalation.

    Higher values indicate more severe actions.

    Args:
        action: The guardrail action.

    Returns:
        Priority integer.
    """
    _priorities = {
        GuardrailAction.LOG: 0,
        GuardrailAction.FLAG: 1,
        GuardrailAction.APPROVE: 2,
        GuardrailAction.REDACT: 3,
        GuardrailAction.QUARANTINE: 4,
        GuardrailAction.BLOCK: 5,
    }
    return _priorities.get(action, 0)


def _parse_sensitivity_list(
    values: Optional[List[str]],
) -> Optional[List[DataSensitivity]]:
    """Parse a list of string sensitivity values into DataSensitivity enums.

    Args:
        values: List of string values matching DataSensitivity member names.

    Returns:
        List of DataSensitivity enum values, or None if input is None.
    """
    if values is None:
        return None
    result = []
    for v in values:
        try:
            result.append(DataSensitivity(v))
        except ValueError:
            logger.warning("Unknown DataSensitivity value: %s", v)
    return result or None