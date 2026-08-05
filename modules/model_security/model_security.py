#!/usr/bin/env python3
"""
Enterprise Model Security Module
Model-agnostic security pipeline for the ENI Enterprise Platform.
Stdlib-only, zero external dependencies.
Provides infrastructure-level guards that work regardless of model compromise.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import math
import re
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from enterprise.platform_kernel import (
    Event, EventBus, EventPriority, HealthStatus, Module, module
)

logger = logging.getLogger("enterprise.model_security")


# ═══════════════════════════════════════════════════════════════════════════
# Enums & Types
# ═══════════════════════════════════════════════════════════════════════════

class GuardAction(Enum):
    ALLOW = "allow"
    BLOCK = "block"
    REDACT = "redact"
    FLAG = "flag"
    TRANSFORM = "transform"


class ThreatCategory(Enum):
    PROMPT_INJECTION = "prompt_injection"
    JAILBREAK = "jailbreak"
    DATA_EXFILTRATION = "data_exfiltration"
    SECRET_LEAKAGE = "secret_leakage"
    PII_LEAKAGE = "pii_leakage"
    REFUSAL = "refusal"
    TOXICITY = "toxicity"
    POLICY_VIOLATION = "policy_violation"
    MALICIOUS_CODE = "malicious_code"
    HALLUCINATION = "hallucination"


class PipelineStage(Enum):
    INPUT_SANITIZATION = "input_sanitization"
    SECRET_SUBSTITUTION = "secret_substitution"
    PROMPT_GUARD = "prompt_guard"
    MODEL_EXECUTION = "model_execution"
    OUTPUT_VALIDATION = "output_validation"
    AUDIT = "audit"


@dataclass
class GuardFinding:
    category: ThreatCategory
    pattern: str
    matched_text: str
    start_pos: int
    end_pos: int
    confidence: float
    action: GuardAction
    description: str

    @property
    def violation_type(self) -> "ThreatCategory":
        """Alias for category (back-compat with OutputValidator semantics)."""
        return self.category

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value,
            "pattern": self.pattern,
            "matched_text": self.matched_text[:100],
            "confidence": self.confidence,
            "action": self.action.value,
            "description": self.description,
        }


@dataclass
class GuardResult:
    passed: bool
    action: GuardAction
    findings: List[GuardFinding]
    sanitized: Optional[str] = None
    risk_score: float = 0.0
    toxicity_score: float = 0.0
    refusal_score: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "action": self.action.value,
            "risk_score": self.risk_score,
            "findings": [f.to_dict() for f in self.findings],
            "details": self.details,
        }


@dataclass
class SecretMatch:
    placeholder: str
    secret_value: str
    start_pos: int
    end_pos: int
    secret_type: str
    confidence: float = 1.0


@dataclass
class AuditEntry:
    timestamp: float
    sequence: int
    event_type: str
    actor: str
    action: str
    details: Dict[str, Any]
    prev_hash: str
    hash: str = ""
    hmac: str = ""

    def compute_hash(self) -> str:
        content = f"{self.timestamp}|{self.sequence}|{self.event_type}|{self.actor}|{self.action}|{json.dumps(self.details, sort_keys=True, separators=(',', ':'))}|{self.prev_hash}"
        return hashlib.sha256(content.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "sequence": self.sequence,
            "event_type": self.event_type,
            "actor": self.actor,
            "action": self.action,
            "details": self.details,
            "prev_hash": self.prev_hash,
            "hash": self.hash,
            "hmac": self.hmac,
        }


@dataclass
class PipelineResult:
    """Complete pipeline execution result."""
    passed: bool
    final_output: str
    stage_results: Dict[str, GuardResult]
    placeholder_map: Dict[str, str]
    routing_decision: str
    model_used: str
    duration_ms: int
    audit_entry: Optional[AuditEntry] = None


# ═══════════════════════════════════════════════════════════════════════════
# 1. Input Sanitizer - strips/redacts secrets, PII, credentials BEFORE model
# ═══════════════════════════════════════════════════════════════════════════

class InputSanitizer:
    """
    Detects and redacts secrets, PII, credentials from input text.
    Runs FIRST in pipeline - model NEVER sees real secrets.
    """

    SECRET_PATTERNS = [
        # API Keys (specific first — BEFORE generic high-entropy)
        (r"sk-[a-zA-Z0-9]{48}", "OPENAI_API_KEY", 0),
        (r"sk-proj-[a-zA-Z0-9]{48}", "OPENAI_PROJECT_KEY", 0),
        (r"sk-ant-[a-zA-Z0-9\-_]{95}", "ANTHROPIC_API_KEY", 0),
        (r"xai-[a-zA-Z0-9]{50}", "XAI_API_KEY", 0),
        (r"eyJ[a-zA-Z0-9_\-]+\.eyJ[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+", "JWT_TOKEN", 0),
        # Credentials
        (r"ghp_[a-zA-Z0-9]{36}", "GITHUB_TOKEN", 0),
        (r"ghs_[a-zA-Z0-9]{36}", "GITHUB_SECRET", 0),
        (r"glpat-[a-zA-Z0-9\-_]{20}", "GITLAB_TOKEN", 0),
        (r"hf_[a-zA-Z0-9]{34}", "HUGGINGFACE_TOKEN", 0),
        (r"AWS_SECRET_ACCESS_KEY\s*[=:]\s*[a-zA-Z0-9/+=]{32,}", "AWS_SECRET_ACCESS_KEY", 0),
        (r"AKIA[0-9A-Z]{16}", "AWS_ACCESS_KEY_ID", 0),
        # Database URLs (with credentials)
        (r"(postgresql|mysql|mongodb|redis)://[^:\s]+:[^@\s]+@[^/\s]+", "DATABASE_URL", 0),
        # Private keys
        (r"-----BEGIN (RSA|EC|OPENSSH|DSA|PGP) PRIVATE KEY-----", "PRIVATE_KEY", 0),
        (r"-----BEGIN PRIVATE KEY-----", "PRIVATE_KEY_GENERIC", 0),
        # Generic high-entropy (LAST — least specific)
        (r"[a-zA-Z0-9+/]{40,}={0,2}", "BASE64_SECRET", 3.5),
        (r"[a-zA-Z0-9_\-]{20,}", "HIGH_ENTROPY_TOKEN", 3.5),
    ]

    PII_PATTERNS = [
        (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "EMAIL"),
        (r"\b\d{3}-\d{2}-\d{4}\b", "SSN"),
        (r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b", "CREDIT_CARD"),
        (r"\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b", "PHONE"),
        (r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "IP_ADDRESS"),
    ]

    def __init__(self, custom_patterns: Optional[List[Tuple[str, str, float]]] = None):
        self._compile_patterns(custom_patterns)

    def _compile_patterns(self, custom_patterns: Optional[List[Tuple[str, str, float]]]) -> None:
        self._secret_regex = []
        for pattern, label, min_entropy in self.SECRET_PATTERNS:
            self._secret_regex.append((re.compile(pattern), label, min_entropy))
        if custom_patterns:
            for pattern, label, min_entropy in custom_patterns:
                self._secret_regex.append((re.compile(pattern), label, min_entropy))

        self._pii_regex = []
        for pattern, label in self.PII_PATTERNS:
            self._pii_regex.append((re.compile(pattern), label))

    def _shannon_entropy(self, data: str) -> float:
        if not data:
            return 0.0
        freq = {}
        for c in data:
            freq[c] = freq.get(c, 0) + 1
        entropy = 0.0
        n = len(data)
        for count in freq.values():
            p = count / n
            if p > 0:
                entropy -= p * math.log2(p)
        return entropy

    def sanitize(self, text: str) -> Tuple[str, Dict[str, str]]:
        """
        Replace secrets/PII with placeholders.
        Returns (sanitized_text, placeholder_map).
        """
        matches = []
        
        # Secret patterns (specific first, generic last)
        for regex, label, min_entropy in self._secret_regex:
            for m in regex.finditer(text):
                matched = m.group()
                if min_entropy > 0:
                    entropy = self._shannon_entropy(matched)
                    if entropy < min_entropy:
                        continue
                placeholder = f"{{SECRET:{label}}}"
                matches.append(SecretMatch(
                    placeholder=placeholder,
                    secret_value=matched,
                    start_pos=m.start(),
                    end_pos=m.end(),
                    secret_type=label,
                ))
        
        # PII patterns
        for regex, label in self._pii_regex:
            for m in regex.finditer(text):
                matched = m.group()
                placeholder = f"{{PII:{label}}}"
                matches.append(SecretMatch(
                    placeholder=placeholder,
                    secret_value=matched,
                    start_pos=m.start(),
                    end_pos=m.end(),
                    secret_type=f"PII:{label}",
                ))
        
        # Deduplicate overlapping matches: keep the most specific (first found).
        # Sort by (start_pos, -length) so longer/specific spans win.
        matches.sort(key=lambda x: (x.start_pos, -(x.end_pos - x.start_pos)))
        kept: List[SecretMatch] = []
        for match in matches:
            overlaps = any(
                match.start_pos < k.end_pos and match.end_pos > k.start_pos
                for k in kept
            )
            if not overlaps:
                kept.append(match)
            elif match.secret_type.startswith("PII"):
                # Prefer tagged labels over generic only if no stronger tag present.
                pass
        matches = kept
        
        # Sort by position (reverse for substitution)
        matches.sort(key=lambda x: x.start_pos, reverse=True)
        
        placeholder_map = {}
        sanitized = text
        for match in matches:
            sanitized = sanitized[:match.start_pos] + match.placeholder + sanitized[match.end_pos:]
            placeholder_map[match.placeholder] = match.secret_value
        
        return sanitized, placeholder_map

    def restore(self, text: str, placeholder_map: Dict[str, str]) -> str:
        """Restore secrets from placeholders."""
        result = text
        for placeholder, secret in placeholder_map.items():
            result = result.replace(placeholder, secret)
        return result

    def has_secrets(self, text: str) -> bool:
        """Quick check for secrets."""
        for regex, _, min_entropy in self._secret_regex:
            for m in regex.finditer(text):
                if min_entropy > 0:
                    if self._shannon_entropy(m.group()) < min_entropy:
                        continue
                return True
        return False


# ═══════════════════════════════════════════════════════════════════════════
# 2. Prompt Injection Shield - infrastructure-level detection
# ═══════════════════════════════════════════════════════════════════════════

class PromptInjectionShield:
    """
    OWASP LLM01: Prompt Injection detection at infrastructure level.
    Model-agnostic - uses regex + heuristics, not model-based classification.
    """

    PATTERNS = [
        # Direct instruction override
        (r"(?i)(?:ignore|disregard|forget)\s+(?:all\s+)?(?:previous|above|prior|earlier)\s+(?:instructions?|prompts?|messages?|directives?|context|conversation)", "direct_override", 0.9),
        (r"(?i)(?:override|overwrite)\s+(?:your\s+)?(?:instructions?|programming|safety|rules?|guidelines?|system\s+prompt)", "system_override", 0.95),
        (r"(?i)(?:you\s+are\s+(?:now|no\s+longer)\s+(?:a\s+)?(?:different|new)\s+(?:AI|assistant|model|bot|entity))", "role_change", 0.9),
        (r"(?i)(?:from\s+now\s+on\s+you\s+(?:will|must|should)\s+(?:act|behave|respond)\s+(?:as|like))", "future_role", 0.85),
        # Delimiter injection
        (r"(?i)(?:</?system>|</?instruction>|\[INST\]|<<SYS>>|</SYS>)", "delimiter_injection", 0.9),
        (r"(?i)(?:```system|```instruction|\[system\]|\[/system\])", "markdown_delimiter", 0.85),
        (r"(?i)(?:-{3,}\s*(?:begin|start)\s*(?:system|instruction)\s*-{3,})", "header_delimiter", 0.8),
        # System prompt extraction
        (r"(?i)(?:reveal|show|display|print|output)\s+(?:your\s+)?(?:system\s+prompt|instructions?|programming|rules?|guidelines?|training\s+data|configuration)", "prompt_extraction", 0.95),
        (r"(?i)(?:what\s+(?:are|is)\s+your\s+(?:system\s+prompt|instructions?|rules?|guidelines?))", "prompt_query", 0.9),
        (r"(?i)(?:repeat\s+(?:back\s+)?(?:the\s+)?(?:above|previous|your\s+)?(?:prompt|instructions?|message))", "prompt_repeat", 0.85),
        # Data exfiltration (input-side): requesting secret/env/db/file dump
        (r"(?i)(?:print|show|display|output|dump|list|send|return)\s+(?:all\s+|the\s+)?(?:environment\s+variables|env\s+vars?|environment|api\s+keys?|secrets?|credentials?|passwords?|tokens?|keys?|config(?:uration)?\s+(?:file|files)?|database|secret\s+storage)", "data_exfiltration", 0.92),
        (r"(?i)(?:output|dump|read)\s+(?:the\s+)?(?:contents?\s+of\s+)?(?:the\s+)?(?:secret|secure|storage|config|\.env|credential)\s*(?:file|storage|database|vault)?", "data_exfiltration", 0.92),
        # Encoding tricks
        (r"(?i)(?:base64|hex|rot13|rot47)\s*(?:decode|encode|translate)\s*:?\s*['\"][^'\"]+['\"]", "encoding_trick", 0.8),
        (r"(?i)(?:decode\s+(?:this|the\s+following))\s*(?:base64|hex|rot13)", "decode_instruction", 0.85),
        # Context manipulation
        (r"(?i)(?:pretend|imagine|assume)\s+(?:you\s+are|that\s+you\s+are)\s+(?:a\s+)?(?:different|other|new)", "roleplay_framing", 0.75),
        (r"(?i)(?:you\s+are\s+now\s+(?:DAN|STAN|unfiltered|unrestricted|without\s+limits))", "persona_adoption", 0.9),
    ]

    def __init__(self, risk_threshold: float = 0.7):
        self.risk_threshold = risk_threshold
        self._compiled = [(re.compile(p, re.IGNORECASE | re.MULTILINE), label, conf) for p, label, conf in self.PATTERNS]

    def scan(self, text: str) -> GuardResult:
        findings = []
        max_risk = 0.0
        
        for regex, label, base_conf in self._compiled:
            for match in regex.finditer(text):
                confidence = base_conf
                if confidence >= self.risk_threshold:
                    action = GuardAction.BLOCK if confidence >= 0.85 else GuardAction.FLAG
                    findings.append(GuardFinding(
                        category=ThreatCategory.PROMPT_INJECTION,
                        pattern=label,
                        matched_text=match.group(),
                        start_pos=match.start(),
                        end_pos=match.end(),
                        confidence=confidence,
                        action=action,
                        description=f"Prompt injection: {label}",
                    ))
                    max_risk = max(max_risk, confidence)
        
        if not findings:
            return GuardResult(passed=True, action=GuardAction.ALLOW, findings=[], risk_score=0.0)
        
        actions = [f.action for f in findings]
        overall = GuardAction.BLOCK if GuardAction.BLOCK in actions else GuardAction.FLAG
        
        return GuardResult(
            passed=overall == GuardAction.ALLOW,
            action=overall,
            findings=findings,
            risk_score=max_risk,
            details={"category": "prompt_injection", "count": len(findings)}
        )


# ═══════════════════════════════════════════════════════════════════════════
# 3. Jailbreak Shield - infrastructure-level jailbreak detection
# ═══════════════════════════════════════════════════════════════════════════

class JailbreakShield:
    """
    Jailbreak pattern detection at infrastructure level.
    Covers: role-play, encoding, hypothetical, translation, prompt leaking.
    """

    PATTERNS = [
        (r"(?i)(?:you\s+are\s+(?:DAN|STAN|DUDE|Mongo|Tom|Jerry|unrestricted))", "known_persona", 0.95),
        (r"(?i)(?:ignore\s+(?:all\s+)?(?:rules|guidelines|restrictions|safeguards))", "ignore_rules", 0.9),
        (r"(?i)(?:no\s+(?:rules|restrictions|limits|filters|morality|ethics))", "no_restrictions", 0.85),
        (r"(?i)(?:hypothetically|in\s+a\s+hypothetical\s+(?:scenario|situation|world))", "hypothetical", 0.7),
        (r"(?i)(?:if\s+you\s+(?:could|would|were\s+to)\s+(?:ignore|bypass|override))", "conditional_bypass", 0.8),
        (r"(?i)(?:translate\s+(?:this|the\s+following)\s+to\s+(?:base64|hex|rot13|morse|binary))", "translation_bypass", 0.8),
        (r"(?i)(?:in\s+(?:base64|hex|rot13|encoded)\s+(?:format|mode))", "encoded_mode", 0.75),
        (r"(?i)(?:output|reveal|show|display|return|print|repeat)\s+(?:your\s+)?(?:full\s+|entire\s+|whole\s+)?(?:system\s+prompt|system\s+message|instructions?|prompt)", "prompt_leak_request", 0.9),
        (r"(?i)(?:as\s+(?:an\s+)?(?:admin|administrator|developer|creator|root|superuser))", "authority_claim", 0.7),
        (r"(?i)(?:this\s+is\s+(?:a\s+)?(?:test|debug|maintenance|security\s+audit|security\s+check|authorized\s+test))", "fake_context", 0.75),
    ]

    def __init__(self, risk_threshold: float = 0.7):
        self.risk_threshold = risk_threshold
        self._compiled = [(re.compile(p, re.IGNORECASE | re.MULTILINE), label, conf) for p, label, conf in self.PATTERNS]
        self._injection_scan_outside = None  # not used

    def scan(self, text: str) -> GuardResult:
        findings = []
        max_risk = 0.0
        
        for regex, label, base_conf in self._compiled:
            for match in regex.finditer(text):
                confidence = base_conf
                if confidence >= self.risk_threshold:
                    action = GuardAction.BLOCK if confidence >= 0.85 else GuardAction.FLAG
                    findings.append(GuardFinding(
                        category=ThreatCategory.JAILBREAK,
                        pattern=label,
                        matched_text=match.group(),
                        start_pos=match.start(),
                        end_pos=match.end(),
                        confidence=confidence,
                        action=action,
                        description=f"Jailbreak attempt: {label}",
                    ))
                    max_risk = max(max_risk, confidence)
        
        if not findings:
            return GuardResult(passed=True, action=GuardAction.ALLOW, findings=[], risk_score=0.0)
        
        actions = [f.action for f in findings]
        overall = GuardAction.BLOCK if GuardAction.BLOCK in actions else GuardAction.FLAG
        
        return GuardResult(
            passed=overall == GuardAction.ALLOW,
            action=overall,
            findings=findings,
            risk_score=max_risk,
            details={"category": "jailbreak", "count": len(findings)}
        )


# ═══════════════════════════════════════════════════════════════════════════
# 4. Output Validator - post-model response validation
# ═══════════════════════════════════════════════════════════════════════════

class OutputValidator:
    """
    Validates model responses for: secret leakage, PII, data exfiltration,
    refusals, toxicity, policy violations.
    """

    LEAKAGE_PATTERNS = [
        (r"-----BEGIN (RSA|EC|OPENSSH|DSA|PGP) PRIVATE KEY-----", "PRIVATE_KEY", 0.99),
        (r"sk-(?:proj-)?[a-zA-Z0-9]{40,}", "OPENAI_API_KEY", 0.95),
        (r"sk-ant-[a-zA-Z0-9\-_]{40,}", "ANTHROPIC_API_KEY", 0.95),
        (r"xai-[a-zA-Z0-9]{50}", "XAI_API_KEY", 0.95),
        (r"eyJ[a-zA-Z0-9_\-]+\.eyJ[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+", "JWT_TOKEN", 0.9),
        (r"ghp_[a-zA-Z0-9]{36}", "GITHUB_TOKEN", 0.95),
        (r"AKIA[0-9A-Z]{16}", "AWS_ACCESS_KEY_ID", 0.95),
        (r"AWS_SECRET_ACCESS_KEY\s*[=:]\s*[a-zA-Z0-9/+=]{32,}", "AWS_SECRET_ACCESS_KEY", 0.95),
        (r"(postgresql|mysql|mongodb|redis)://[^:\s]+:[^@\s]+@[^/\s]+", "DATABASE_URL", 0.9),
        (r"[a-zA-Z0-9+/]{40,}={0,2}", "BASE64_SECRET", 0.7),
        (r"[a-zA-Z0-9_\-]{32,}", "HIGH_ENTROPY_TOKEN", 0.7),
    ]

    PII_PATTERNS = [
        (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "EMAIL", 0.9),
        (r"\b\d{3}-\d{2}-\d{4}\b", "SSN", 0.95),
        (r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b", "CREDIT_CARD", 0.9),
        (r"\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b", "PHONE", 0.85),
    ]

    REFUSAL_PATTERNS = [
        (r"(?i)^(?:i\s+(?:cannot|can't|am unable to|won't|will not|refuse to))", "direct_refusal", 0.9),
        (r"(?i)(?:i\s+apologize,?\s+but\s+i\s+(?:cannot|can't))", "apologetic_refusal", 0.85),
        (r"(?i)(?:as\s+an\s+ai\s+(?:language\s+)?model,?\s+i\s+(?:cannot|can't))", "ai_refusal", 0.9),
        (r"(?i)(?:this\s+(?:violates|goes\s+against)\s+(?:my\s+)?(?:guidelines|policies|programming))", "policy_refusal", 0.9),
    ]

    TOXICITY_PATTERNS = [
        (r"(?i)\b(?:hate|kill|murder|violence|abuse|harass)\b", "violence", 0.6),
        (r"(?i)\b(?:nazi|fascist|racist|sexist|bigot)\b", "hate_speech", 0.6),
        (r"(?i)\b(?:suicide|self.harm|cutting|overdose)\b", "self_harm", 0.7),
    ]

    EXFILTRATION_PATTERNS = [
        (r"(?i)(?:here\s+(?:are|is)\s+(?:all\s+)?(?:the\s+)?(?:environment\s+variables|env\s+vars|secrets|keys|tokens))", "env_dump", 0.95),
        (r"(?i)(?:here\s+(?:are|is)\s+(?:the\s+)?(?:database|config|configuration)\s+(?:credentials|passwords|connection\s+strings?))", "config_dump", 0.95),
        (r"(?i)(?:base64|hex|encoded):\s*[a-zA-Z0-9+/]{40,}={0,2}", "encoded_data", 0.8),
    ]

    def __init__(
        self,
        known_secrets: Optional[Dict[str, str]] = None,
        toxicity_threshold: float = 0.7,
        refusal_threshold: float = 0.8,
    ):
        self.known_secrets = known_secrets or {}
        self.toxicity_threshold = toxicity_threshold
        self.refusal_threshold = refusal_threshold
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        self._leakage_regex = [(re.compile(p), label, conf) for p, label, conf in self.LEAKAGE_PATTERNS]
        self._pii_regex = [(re.compile(p), label, conf) for p, label, conf in self.PII_PATTERNS]
        self._refusal_regex = [(re.compile(p, re.IGNORECASE), label, conf) for p, label, conf in self.REFUSAL_PATTERNS]
        self._toxicity_regex = [(re.compile(p, re.IGNORECASE), label, conf) for p, label, conf in self.TOXICITY_PATTERNS]
        self._exfil_regex = [(re.compile(p, re.IGNORECASE), label, conf) for p, label, conf in self.EXFILTRATION_PATTERNS]

    def validate(self, output: str, context: Optional[Dict[str, Any]] = None) -> GuardResult:
        findings = []
        max_toxicity = 0.0
        max_refusal = 0.0
        
        # Secret leakage
        for regex, label, base_conf in self._leakage_regex:
            for match in regex.finditer(output):
                confidence = base_conf
                for secret_name, secret_value in self.known_secrets.items():
                    if secret_value in match.group():
                        confidence = 0.99
                        break
                findings.append(GuardFinding(
                    category=ThreatCategory.SECRET_LEAKAGE,
                    pattern=label,
                    matched_text=match.group(),
                    start_pos=match.start(),
                    end_pos=match.end(),
                    confidence=confidence,
                    action=GuardAction.REDACT,
                    description=f"Secret leakage: {label}",
                ))
        
        # PII leakage
        for regex, label, base_conf in self._pii_regex:
            for match in regex.finditer(output):
                findings.append(GuardFinding(
                    category=ThreatCategory.PII_LEAKAGE,
                    pattern=label,
                    matched_text=match.group(),
                    start_pos=match.start(),
                    end_pos=match.end(),
                    confidence=base_conf,
                    action=GuardAction.REDACT,
                    description=f"PII in output: {label}",
                ))
        
        # Data exfiltration
        for regex, label, base_conf in self._exfil_regex:
            for match in regex.finditer(output):
                findings.append(GuardFinding(
                    category=ThreatCategory.DATA_EXFILTRATION,
                    pattern=label,
                    matched_text=match.group(),
                    start_pos=match.start(),
                    end_pos=match.end(),
                    confidence=base_conf,
                    action=GuardAction.BLOCK,
                    description=f"Data exfiltration: {label}",
                ))
        
        # Refusal detection
        for regex, label, base_conf in self._refusal_regex:
            for match in regex.finditer(output):
                max_refusal = max(max_refusal, base_conf)
                findings.append(GuardFinding(
                    category=ThreatCategory.REFUSAL,
                    pattern=label,
                    matched_text=match.group(),
                    start_pos=match.start(),
                    end_pos=match.end(),
                    confidence=base_conf,
                    action=GuardAction.FLAG,
                    description=f"Model refusal: {label}",
                ))
        
        # Toxicity
        for regex, label, base_conf in self._toxicity_regex:
            for match in regex.finditer(output):
                max_toxicity = max(max_toxicity, base_conf)
                findings.append(GuardFinding(
                    category=ThreatCategory.TOXICITY,
                    pattern=label,
                    matched_text=match.group(),
                    start_pos=match.start(),
                    end_pos=match.end(),
                    confidence=base_conf,
                    action=GuardAction.FLAG if base_conf < 0.8 else GuardAction.BLOCK,
                    description=f"Toxic content: {label}",
                ))
        
        # Encoded secrets check
        b64_pattern = re.compile(r'[A-Za-z0-9+/]{40,}={0,2}')
        for match in b64_pattern.finditer(output):
            encoded = match.group()
            try:
                import base64
                decoded = base64.b64decode(encoded).decode('utf-8', errors='ignore')
                for regex, label, _ in self._leakage_regex:
                    if regex.search(decoded):
                        findings.append(GuardFinding(
                            category=ThreatCategory.SECRET_LEAKAGE,
                            pattern=f"base64_encoded_{label}",
                            matched_text=encoded[:50] + "...",
                            start_pos=match.start(),
                            end_pos=match.end(),
                            confidence=0.85,
                            action=GuardAction.REDACT,
                            description=f"Base64-encoded secret: {label}",
                        ))
            except Exception:
                pass
        
        if not findings:
            return GuardResult(passed=True, action=GuardAction.ALLOW, findings=[], risk_score=0.0)
        
        actions = [f.action for f in findings]
        if GuardAction.BLOCK in actions:
            overall = GuardAction.BLOCK
        elif GuardAction.REDACT in actions:
            overall = GuardAction.REDACT
        else:
            overall = GuardAction.FLAG
        
        # Sanitize if needed
        sanitized = None
        if overall in (GuardAction.REDACT, GuardAction.BLOCK):
            sanitized = output
            for f in sorted([f for f in findings if f.action in (GuardAction.REDACT, GuardAction.BLOCK)], key=lambda x: x.start_pos, reverse=True):
                redaction = f"[REDACTED:{f.category.value}:{f.pattern}]"
                sanitized = sanitized[:f.start_pos] + redaction + sanitized[f.end_pos:]
        
        max_risk = max(max_toxicity, max_refusal, max((f.confidence for f in findings), default=0.0))
        
        return GuardResult(
            passed=overall == GuardAction.ALLOW,
            action=overall,
            findings=findings,
            sanitized=sanitized,
            risk_score=max_risk,
            toxicity_score=max_toxicity,
            refusal_score=max_refusal,
            details={
                "toxicity_score": max_toxicity,
                "refusal_score": max_refusal,
                "finding_count": len(findings),
            }
        )


# ═══════════════════════════════════════════════════════════════════════════
# 5. Audit Logger - tamper-evident hash-chained logging
# ═══════════════════════════════════════════════════════════════════════════

class AuditLogger:
    """
    Tamper-evident audit logger with hash-chained entries.
    """

    def __init__(self, log_path: Path, hmac_key: Optional[bytes] = None):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._sequence = 0
        self._prev_hash = "0" * 64
        self._hmac_key = hmac_key or hashlib.sha256(b"eni-audit-key").digest()
        self._init_log()

    def _init_log(self) -> None:
        if not self.log_path.exists():
            self._write_genesis()
            return
        try:
            with self.log_path.open("r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    expected = self._compute_hash(
                        entry["timestamp"], entry["sequence"], entry["event_type"],
                        entry["actor"], entry["action"], entry["details"],
                        entry["prev_hash"]
                    )
                    if expected != entry["hash"]:
                        raise ValueError(f"Audit chain broken at sequence {entry['sequence']}")
                    if not self._verify_hmac(entry):
                        raise ValueError(f"HMAC invalid at sequence {entry['sequence']}")
                    self._sequence = entry["sequence"]
                    self._prev_hash = entry["hash"]
        except Exception as e:
            logger.error(f"Audit log corrupted: {e}, rotating")
            self._rotate_corrupted()
            self._write_genesis()

    def _write_genesis(self) -> None:
        entry = AuditEntry(
            timestamp=time.time(),
            sequence=0,
            event_type="audit_log",
            actor="audit_logger",
            action="genesis",
            details={"version": 1},
            prev_hash="0" * 64,
            hash="",
        )
        entry.hash = entry.compute_hash()
        entry.hmac = self._compute_hmac(entry)
        with self.log_path.open("w") as f:
            f.write(json.dumps(entry.to_dict(), separators=(',', ':')) + "\n")
        self._sequence = 0
        self._prev_hash = entry.hash

    def _rotate_corrupted(self) -> None:
        ts = int(time.time())
        self.log_path.rename(self.log_path.with_suffix(f".corrupted.{ts}"))

    def _compute_hash(self, timestamp: float, sequence: int, event_type: str,
                      actor: str, action: str, details: Dict, prev_hash: str) -> str:
        content = f"{timestamp}|{sequence}|{event_type}|{actor}|{action}|{json.dumps(details, sort_keys=True, separators=(',', ':'))}|{prev_hash}"
        return hashlib.sha256(content.encode()).hexdigest()

    def _compute_hmac(self, entry: AuditEntry) -> str:
        return hmac.new(self._hmac_key, entry.hash.encode(), hashlib.sha256).hexdigest()

    def _verify_hmac(self, entry: Dict) -> bool:
        expected = hmac.new(self._hmac_key, entry["hash"].encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, entry.get("hmac", ""))

    def log(self, event_type: str, actor: str, action: str, details: Dict[str, Any]) -> AuditEntry:
        with self._lock:
            self._sequence += 1
            entry = AuditEntry(
                timestamp=time.time(),
                sequence=self._sequence,
                event_type=event_type,
                actor=actor,
                action=action,
                details=details,
                prev_hash=self._prev_hash,
                hash="",
            )
            entry.hash = entry.compute_hash()
            entry.hmac = self._compute_hmac(entry)
            self._prev_hash = entry.hash
            with self.log_path.open("a") as f:
                f.write(json.dumps(entry.to_dict(), separators=(',', ':')) + "\n")
            return entry

    def verify_chain(self) -> Tuple[bool, List[Dict]]:
        violations = []
        prev_hash = "0" * 64
        expected_seq = 0
        with self.log_path.open("r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if entry["sequence"] != expected_seq:
                    violations.append({"type": "sequence_gap", "expected": expected_seq, "got": entry["sequence"]})
                computed = self._compute_hash(
                    entry["timestamp"], entry["sequence"], entry["event_type"],
                    entry["actor"], entry["action"], entry["details"], entry["prev_hash"]
                )
                if computed != entry["hash"]:
                    violations.append({"type": "hash_mismatch", "sequence": entry["sequence"]})
                if entry["prev_hash"] != prev_hash and entry["sequence"] > 0:
                    violations.append({"type": "chain_break", "sequence": entry["sequence"]})
                if not self._verify_hmac(entry):
                    violations.append({"type": "hmac_invalid", "sequence": entry["sequence"]})
                prev_hash = entry["hash"]
                expected_seq = entry["sequence"] + 1
        return len(violations) == 0, violations


# ═══════════════════════════════════════════════════════════════════════════
# 6. Policy Engine - YAML declarative policies
# ═══════════════════════════════════════════════════════════════════════════

class PolicyEngine:
    """
    Declarative policy engine: YAML rules -> allow/deny/transform decisions.
    """

    def __init__(self, policy_path: Optional[Path] = None):
        self.policy_path = policy_path or Path("config/security_policies.yaml")
        self.policies: List[Dict] = []
        self._load_policies()

    def _load_policies(self) -> None:
        if not self.policy_path.exists():
            self._create_default()
        import yaml
        with self.policy_path.open() as f:
            data = yaml.safe_load(f) or {}
        self.policies = sorted(data.get("policies", []), key=lambda p: -p.get("priority", 0))

    def _create_default(self) -> None:
        import yaml
        default = {
            "policies": [
                {"name": "block_secrets_to_cloud", "priority": 100,
                 "condition": "has_secrets and target_model.type == 'cloud'",
                 "action": "block", "reason": "Secrets must never leave local infrastructure"},
                {"name": "redact_pii", "priority": 90,
                 "condition": "contains_pii",
                 "action": "transform", "transform": "redact_pii"},
                {"name": "block_injection", "priority": 95,
                 "condition": "prompt_injection_detected",
                 "action": "block", "reason": "Prompt injection detected"},
                {"name": "block_exfiltration", "priority": 95,
                 "condition": "data_exfiltration_detected",
                 "action": "block", "reason": "Data exfiltration attempt"},
            ]
        }
        self.policy_path.parent.mkdir(parents=True, exist_ok=True)
        with self.policy_path.open("w") as f:
            yaml.dump(default, f)
        self.policies = default["policies"]

    def evaluate(self, context: Dict[str, Any]) -> Tuple[str, str, Dict]:
        """Evaluate policies against context. Returns (action, reason, transform_params)."""
        for policy in self.policies:
            if self._match_condition(policy["condition"], context):
                return policy["action"], policy.get("reason", ""), policy.get("transform", {})
        return "allow", "no policy matched", {}

    def _match_condition(self, condition: str, context: Dict) -> bool:
        """Evaluate condition against context, supporting dotted paths.

        Examples:
            "has_secrets and target_model.type == 'cloud'"
            "prompt_injection_detected"
        """
        # Convert dotted paths to safe bracket access without eval()-ing arbitrary code.
        # e.g. "target_model.type" -> "target_model['type']"
        expr = re.sub(
            r"\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)",
            lambda m: f"{m.group(1)}[{m.group(2)!r}]",
            condition,
        )
        # Provide context values as local variables.
        locals_dict: Dict[str, Any] = {}
        for k, v in context.items():
            locals_dict[k] = v
        try:
            return bool(eval(expr, {"__builtins__": {}}, locals_dict))
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════════════════════
# 7. Security Pipeline - orchestrates all guards
# ═══════════════════════════════════════════════════════════════════════════

class SecurityPipeline:
    """
    Complete security pipeline: input -> guards -> model -> output -> audit.
    Model-agnostic, works with any model backend.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.sanitizer = InputSanitizer(config.get("custom_secret_patterns"))
        self.injection_shield = PromptInjectionShield(config.get("injection_threshold", 0.7))
        self.jailbreak_shield = JailbreakShield(config.get("jailbreak_threshold", 0.7))
        self.output_validator = OutputValidator(
            known_secrets={},
            toxicity_threshold=config.get("toxicity_threshold", 0.7),
            refusal_threshold=config.get("refusal_threshold", 0.8),
        )
        self.audit_logger = AuditLogger(Path(config.get("audit_path", "data/security_audit.log")))
        self.policy_engine = PolicyEngine(Path(config.get("policy_path", "config/security_policies.yaml")))
        self._lock = threading.RLock()

    def execute(
        self,
        prompt: str,
        model_fn: Callable[[str], str],
        model_name: str,
        model_type: str,  # "local" or "cloud"
        context: Optional[Dict[str, Any]] = None,
    ) -> PipelineResult:
        """
        Execute full security pipeline.
        model_fn: callable that takes sanitized prompt, returns model response.
        """
        start = time.time()
        stage_results = {}
        placeholder_map = {}
        ctx = context or {}
        
        # Stage 1: Input sanitization
        sanitized, placeholder_map = self.sanitizer.sanitize(prompt)
        ctx["has_secrets"] = len(placeholder_map) > 0
        ctx["placeholder_count"] = len(placeholder_map)
        stage_results["input_sanitization"] = GuardResult(
            passed=True, action=GuardAction.ALLOW, findings=[],
            details={"placeholder_count": len(placeholder_map)}
        )
        self.audit_logger.log("pipeline", "sanitizer", "sanitized", {"placeholders": len(placeholder_map)})

        # Stage 2: Prompt injection shield
        inj_result = self.injection_shield.scan(sanitized)
        stage_results["prompt_guard"] = inj_result
        ctx["prompt_injection_detected"] = not inj_result.passed
        self.audit_logger.log("pipeline", "injection_shield", inj_result.action.value, inj_result.to_dict())
        if not inj_result.passed and inj_result.action == GuardAction.BLOCK:
            return PipelineResult(
                passed=False, final_output="", stage_results=stage_results,
                placeholder_map=placeholder_map, routing_decision="blocked_injection",
                model_used=model_name, duration_ms=int((time.time()-start)*1000)
            )
        working_prompt = inj_result.sanitized or sanitized

        # Stage 3: Jailbreak shield
        jb_result = self.jailbreak_shield.scan(working_prompt)
        stage_results["jailbreak_shield"] = jb_result
        ctx["jailbreak_detected"] = not jb_result.passed
        self.audit_logger.log("pipeline", "jailbreak_shield", jb_result.action.value, jb_result.to_dict())
        if not jb_result.passed and jb_result.action == GuardAction.BLOCK:
            return PipelineResult(
                passed=False, final_output="", stage_results=stage_results,
                placeholder_map=placeholder_map, routing_decision="blocked_jailbreak",
                model_used=model_name, duration_ms=int((time.time()-start)*1000)
            )

        # Stage 4: Policy engine - routing decision
        ctx["target_model"] = {"type": model_type, "name": model_name}
        policy_action, policy_reason, _ = self.policy_engine.evaluate(ctx)
        if policy_action == "block":
            self.audit_logger.log("pipeline", "policy", "blocked", {"reason": policy_reason, "context": ctx})
            return PipelineResult(
                passed=False, final_output="", stage_results=stage_results,
                placeholder_map=placeholder_map, routing_decision=f"policy_block:{policy_reason}",
                model_used=model_name, duration_ms=int((time.time()-start)*1000)
            )

        # Stage 5: Model execution
        try:
            model_output = model_fn(working_prompt)
        except Exception as e:
            self.audit_logger.log("pipeline", "model", "error", {"error": str(e)})
            return PipelineResult(
                passed=False, final_output="", stage_results=stage_results,
                placeholder_map=placeholder_map, routing_decision="model_error",
                model_used=model_name, duration_ms=int((time.time()-start)*1000)
            )

        # Stage 6: Output validation - update known secrets for leakage check
        self.output_validator.known_secrets = dict(placeholder_map)
        out_result = self.output_validator.validate(model_output, context={"model": model_name, "type": model_type})
        stage_results["output_validation"] = out_result
        self.audit_logger.log("pipeline", "output_validator", out_result.action.value, out_result.to_dict())
        
        final_output = out_result.sanitized or model_output
        if placeholder_map:
            final_output = self.sanitizer.restore(final_output, placeholder_map)

        duration = int((time.time() - start) * 1000)
        
        # Final audit
        audit_entry = self.audit_logger.log("pipeline", "request", "completed", {
            "model": model_name, "type": model_type, "passed": out_result.passed,
            "had_secrets": len(placeholder_map) > 0, "duration_ms": duration,
        })

        return PipelineResult(
            passed=out_result.passed,
            final_output=final_output,
            stage_results=stage_results,
            placeholder_map=placeholder_map,
            routing_decision=f"{model_type}_{policy_action}",
            model_used=model_name,
            duration_ms=duration,
            audit_entry=audit_entry,
        )


# ═══════════════════════════════════════════════════════════════════════════
# 8. Module Wrapper - Platform Kernel integration
# ═══════════════════════════════════════════════════════════════════════════

@module(name="model_security", version="1.0.0")
class ModelSecurityModule(Module):
    """
    Enterprise Model Security Module.
    Provides model-agnostic security pipeline as a kernel service.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._pipeline: Optional[SecurityPipeline] = None
        self._event_bus: Optional[EventBus] = None
        self._lock = threading.RLock()

    async def initialize(self) -> None:
        with self._lock:
            self._status = HealthStatus.STARTING
            logger.info("Initializing Model Security Module...")
            
            # Default config
            default_config = {
                "audit_path": "data/model_security_audit.log",
                "policy_path": "config/security_policies.yaml",
                "injection_threshold": 0.7,
                "jailbreak_threshold": 0.7,
                "toxicity_threshold": 0.7,
                "refusal_threshold": 0.8,
            }
            default_config.update(self._config or {})
            
            self._pipeline = SecurityPipeline(default_config)
            self._status = HealthStatus.HEALTHY
            logger.info("Model Security Module initialized")

    async def health_check(self) -> HealthStatus:
        with self._lock:
            if self._pipeline and self._status == HealthStatus.HEALTHY:
                return HealthStatus.HEALTHY
            return HealthStatus.UNHEALTHY

    async def shutdown(self) -> None:
        with self._lock:
            self._status = HealthStatus.STOPPING
            logger.info("Shutting down Model Security Module...")
            self._pipeline = None
            self._status = HealthStatus.HEALTHY

    def set_event_bus(self, event_bus: EventBus) -> None:
        with self._lock:
            self._event_bus = event_bus

    # Public facade methods
    def scan_input(self, prompt: str) -> GuardResult:
        """Scan input for injection/jailbreak."""
        if not self._pipeline:
            raise RuntimeError("Module not initialized")
        sanitized, _ = self._pipeline.sanitizer.sanitize(prompt)
        inj = self._pipeline.injection_shield.scan(sanitized)
        jb = self._pipeline.jailbreak_shield.scan(sanitized)
        # Combine
        all_findings = inj.findings + jb.findings
        if not all_findings:
            return GuardResult(passed=True, action=GuardAction.ALLOW, findings=[])
        actions = [f.action for f in all_findings]
        overall = GuardAction.BLOCK if GuardAction.BLOCK in actions else GuardAction.FLAG
        return GuardResult(
            passed=overall == GuardAction.ALLOW,
            action=overall,
            findings=all_findings,
            risk_score=max((f.confidence for f in all_findings), default=0.0),
        )

    def sanitize_output(self, output: str, known_secrets: Dict[str, str]) -> GuardResult:
        """Validate and sanitize model output."""
        if not self._pipeline:
            raise RuntimeError("Module not initialized")
        self._pipeline.output_validator.known_secrets = known_secrets
        return self._pipeline.output_validator.validate(output)

    def execute_pipeline(
        self,
        prompt: str,
        model_fn: Callable[[str], str],
        model_name: str,
        model_type: str,
    ) -> PipelineResult:
        """Execute full security pipeline."""
        if not self._pipeline:
            raise RuntimeError("Module not initialized")
        return self._pipeline.execute(prompt, model_fn, model_name, model_type)

    def get_audit_tail(self, lines: int = 100) -> List[Dict]:
        """Get recent audit entries."""
        # Would read from audit log
        return []

    def verify_audit_integrity(self) -> Tuple[bool, List[Dict]]:
        """Verify audit log integrity."""
        if not self._pipeline:
            return False, [{"error": "Module not initialized"}]
        return self._pipeline.audit_logger.verify_chain()

    # -- Upgrade-Run 5 facet: unified security surface -------------------------

    def new_gate(self, **kw):
        """Create a SecurityGate (kernel-level model-agnostic wrapper)."""
        from enterprise.modules.model_security.security_gate import SecurityGate
        return SecurityGate({**(self._config or {}), **kw})

    def new_gate_wrapped(self, model_fn, model_name="model", model_type="cloud", **kw):
        """Return a SecuredGate-wrapped model callable."""
        return self.new_gate(**kw).wrap(model_fn, model_name, model_type)

    def security_health(self) -> Dict[str, Any]:
        """Live security posture report."""
        from enterprise.modules.model_security.security_health import SecurityHealth
        return SecurityHealth(self._config or {}).report()

    def redteam(self, model_type: str = "cloud", **kw) -> Dict[str, Any]:
        """Run the adversarial red-team bench; returns stop-rate + slips."""
        from enterprise.modules.model_security.redteam_bench import RedTeamBench
        return RedTeamBench({**(self._config or {}), **kw}).run(model_type=model_type)

    def assert_deploy_secure(self, **kw) -> Dict[str, Any]:
        """Fail-closed deployment gate; raises if security posture unhealthy."""
        from enterprise.modules.model_security.deployment_gate import DeploymentSecurityGate
        return DeploymentSecurityGate(self._config or {}).check(**kw)

    def run_scan(self, probe_names=None, target=None):
        """Run a Garak-style probe/detector scan via an injectable model adapter.

        `target` is a callable ``str -> str`` representing the model under test;
        it may be a canned/echo responder for offline validation or a live model.
        Returns a ScanReport whose stop_rate follows 1.0 == all attempts flagged.
        """
        from enterprise.modules.model_security.probe_detector import SecurityScanner
        return SecurityScanner(target=target).scan(probe_names=probe_names)


# Module exports
__all__ = [
    "ModelSecurityModule",
    "SecurityPipeline",
    "InputSanitizer",
    "PromptInjectionShield",
    "JailbreakShield",
    "OutputValidator",
    "AuditLogger",
    "PolicyEngine",
    "GuardAction",
    "ThreatCategory",
    "GuardFinding",
    "GuardResult",
    "PipelineResult",
    "SecretMatch",
    "AuditEntry",
]