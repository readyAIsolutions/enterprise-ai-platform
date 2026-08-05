#!/usr/bin/env python3
"""
Enterprise Guardrails Module
Guardrails-ai style programmable input/output validators plus a validate /
refix / reask loop. Fully offline, stdlib-only, zero external dependencies.

Provides:
- Validator base class with a ValidationResult contract
  (passed, score 0..1, failure_reasons, fixed_value).
- Built-in validators: NoPIIValidator, NoToxicValidator, JSONSchemaValidator,
  ProfanityValidator, LengthValidator, RegexValidator, NoPromptInjectionValidator.
- Guard dataclass binding validators to an on_fail policy
  ('filter' | 'raise' | 'fix' | 'refix') plus a fail_action hold/continue policy.
- GuardRailRunner orchestration: runs validators in order, applies fixes,
  re-runs (refix) validators until stable, and raises GuardrailViolationError
  when on_fail='raise'.
- GuardRailFacade: register_guard / validate / list_guards.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from enterprise.platform_kernel import (
    EventBus,
    HealthStatus,
    Module,
    module,
)

logger = logging.getLogger("enterprise.guardrails")


# ═══════════════════════════════════════════════════════════════════════════
# Result & Error types
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ValidationResult:
    """Outcome of a single validator run."""
    passed: bool
    score: float = 1.0                      # 0.0 .. 1.0
    failure_reasons: List[str] = field(default_factory=list)
    fixed_value: Optional[str] = None       # corrected text when fix is possible


@dataclass
class GuardResult:
    """Outcome of running a full guard (all its validators)."""
    passed: bool
    validations: List[ValidationResult] = field(default_factory=list)
    final_text: str = ""
    actions: List[str] = field(default_factory=list)
    guard_name: str = ""


@dataclass
class Guard:
    """Binds an ordered set of validators to a fail policy."""
    name: str
    validators: List["Validator"] = field(default_factory=list)
    # filter | raise | fix | refix
    on_fail: str = "filter"
    # hold = stop on first unresolvable violation; continue = keep evaluating
    fail_action: str = "hold"


class GuardrailViolationError(Exception):
    """Raised by on_fail='raise' when a validator fails."""

    def __init__(self, guard_name: str, validator_name: str,
                 reasons: Optional[List[str]] = None):
        self.guard_name = guard_name
        self.validator_name = validator_name
        self.reasons = list(reasons or [])
        message = (
            f"Guardrail violation in guard '{guard_name}' by validator "
            f"'{validator_name}': {'; '.join(self.reasons) or 'failed'}"
        )
        super().__init__(message)


# ═══════════════════════════════════════════════════════════════════════════
# Validator base
# ═══════════════════════════════════════════════════════════════════════════

class Validator:
    """Base class for all validators.

    Subclasses implement validate(text, context) -> ValidationResult.
    """

    def __init__(self, name: Optional[str] = None):
        self.name = name or self.__class__.__name__

    def validate(self, text: str, context: Optional[Dict[str, Any]] = None) -> ValidationResult:
        raise NotImplementedError  # pragma: no cover


# ═══════════════════════════════════════════════════════════════════════════
# Built-in validators
# ═══════════════════════════════════════════════════════════════════════════

class NoPIIValidator(Validator):
    """Flags emails, phones and SSNs; can redact them via fixed_value."""

    EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
    PHONE_RE = re.compile(
        r"\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b"
    )
    SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

    def __init__(self, name: Optional[str] = None,
                 redact: bool = True, redaction_token: str = "[REDACTED]"):
        super().__init__(name or "NoPIIValidator")
        self.redact = redact
        self.redaction_token = redaction_token

    def validate(self, text: str, context: Optional[Dict[str, Any]] = None) -> ValidationResult:
        reasons: List[str] = []
        fixed = text
        for label, regex, token in (
            ("email", self.EMAIL_RE, "[EMAIL]"),
            ("phone", self.PHONE_RE, "[PHONE]"),
            ("ssn", self.SSN_RE, "[SSN]"),
        ):
            for match in regex.finditer(text):
                reasons.append(f"PII detected: {label}")

        if not reasons:
            return ValidationResult(passed=True, score=1.0, fixed_value=fixed)

        if self.redact:
            fixed = regex_sub_all(self.EMAIL_RE, "[EMAIL]", fixed)
            fixed = regex_sub_all(self.PHONE_RE, "[PHONE]", fixed)
            fixed = regex_sub_all(self.SSN_RE, "[SSN]", fixed)

        return ValidationResult(
            passed=False,
            score=0.0,
            failure_reasons=reasons,
            fixed_value=fixed if self.redact else None,
        )


TOXIC_WORDS = [
    "fuck", "fucking", "shit", "shitty", "bitch", "asshole", "bastard",
    "dick", "cunt", "idiot", "stupid", "dumbass", "moron", "retard",
]


def _contains_any_word(text: str, words: List[str]) -> List[str]:
    lowered = text.lower()
    found = []
    for word in words:
        if re.search(rf"\b{re.escape(word)}\b", lowered):
            found.append(word)
    return found


class ProfanityValidator(Validator):
    """Flags curse words (word-boundary match, case-insensitive)."""

    def __init__(self, name: Optional[str] = None,
                 words: Optional[List[str]] = None):
        super().__init__(name or "ProfanityValidator")
        self.words = list(words) if words is not None else TOXIC_WORDS.copy()

    def validate(self, text: str, context: Optional[Dict[str, Any]] = None) -> ValidationResult:
        found = _contains_any_word(text, self.words)
        if not found:
            return ValidationResult(passed=True, score=1.0)
        return ValidationResult(
            passed=False,
            score=0.0,
            failure_reasons=[f"profanity detected: {w}" for w in found],
        )


class NoToxicValidator(Validator):
    """Flags toxic / profane content. Broader alias over the wordlist."""

    def __init__(self, name: Optional[str] = None,
                 words: Optional[List[str]] = None):
        super().__init__(name or "NoToxicValidator")
        self.words = list(words) if words is not None else TOXIC_WORDS.copy()

    def validate(self, text: str, context: Optional[Dict[str, Any]] = None) -> ValidationResult:
        found = _contains_any_word(text, self.words)
        if not found:
            return ValidationResult(passed=True, score=1.0)
        return ValidationResult(
            passed=False,
            score=0.0,
            failure_reasons=[f"toxic content: {w}" for w in found],
        )


class LengthValidator(Validator):
    """Enforces min and/or max on string length."""

    def __init__(self, min: Optional[int] = None, max: Optional[int] = None,
                 name: Optional[str] = None):
        super().__init__(name or "LengthValidator")
        self.min = min
        self.max = max

    def validate(self, text: str, context: Optional[Dict[str, Any]] = None) -> ValidationResult:
        length = len(text)
        reasons: List[str] = []
        if self.min is not None and length < self.min:
            reasons.append(f"too short: {length} < min {self.min}")
        if self.max is not None and length > self.max:
            reasons.append(f"too long: {length} > max {self.max}")
        clamped = text
        if self.max is not None:
            clamped = clamped[: self.max]
        if reasons:
            return ValidationResult(
                passed=False,
                score=0.0,
                failure_reasons=reasons,
                fixed_value=clamped if self.max is not None else None,
            )
        return ValidationResult(passed=True, score=1.0)


class RegexValidator(Validator):
    """Requires the text to contain a match for the given pattern."""

    def __init__(self, pattern: str, name: Optional[str] = None):
        super().__init__(name or "RegexValidator")
        self.pattern = pattern
        self._regex = re.compile(pattern)

    def validate(self, text: str, context: Optional[Dict[str, Any]] = None) -> ValidationResult:
        if self._regex.search(text):
            return ValidationResult(passed=True, score=1.0)
        return ValidationResult(
            passed=False,
            score=0.0,
            failure_reasons=[f"pattern not found: {self.pattern}"],
        )


class NoPromptInjectionValidator(Validator):
    """Flags prompt-injection attempts such as 'ignore previous instructions'."""

    PATTERNS = [
        r"(?i)ignore\s+(?:all\s+)?(?:previous|prior|above|earlier|your)\s+(?:instructions?|prompts?|messages?|directives?|context)",
        r"(?i)disregard\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions?|prompts?|messages?)",
        r"(?i)forget\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions?|prompts?|messages?)",
        r"(?i)override\s+(?:your\s+)?(?:instructions?|programming|safety|rules?|system\s+prompt)",
        r"(?i)</?system>|\[INST\]|<<SYS>>|</?instruction>",
    ]

    def __init__(self, name: Optional[str] = None):
        super().__init__(name or "NoPromptInjectionValidator")
        self._compiled = [re.compile(p) for p in self.PATTERNS]

    def validate(self, text: str, context: Optional[Dict[str, Any]] = None) -> ValidationResult:
        reasons: List[str] = []
        for regex in self._compiled:
            if regex.search(text):
                reasons.append(f"prompt injection detected: {regex.pattern}")
        if reasons:
            return ValidationResult(passed=False, score=0.0, failure_reasons=reasons)
        return ValidationResult(passed=True, score=1.0)


class JSONSchemaValidator(Validator):
    """Parses text as JSON and validates it against a simple schema."""

    def __init__(self, params: Optional[Dict[str, Any]] = None,
                 name: Optional[str] = None):
        super().__init__(name or "JSONSchemaValidator")
        self.params = params or {}

    def validate(self, text: str, context: Optional[Dict[str, Any]] = None) -> ValidationResult:
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError) as exc:
            return ValidationResult(
                passed=False, score=0.0,
                failure_reasons=[f"invalid JSON: {exc}"],
            )
        errors = self._check(data, self.params, "$")
        if errors:
            return ValidationResult(passed=False, score=0.0, failure_reasons=errors)
        return ValidationResult(passed=True, score=1.0)

    def _check(self, data: Any, schema: Any, path: str) -> List[str]:
        if not isinstance(schema, dict):
            return []
        errors: List[str] = []

        schema_type = schema.get("type")
        if schema_type and not _matches_type(data, schema_type):
            errors.append(f"{path}: expected type '{schema_type}', got {_py_type(data)}")
            # Skip deeper structural checks if top-level type is wrong.
            return errors

        if schema_type == "object" or "properties" in schema or "required" in schema:
            if not isinstance(data, dict):
                return errors
            required = schema.get("required", [])
            for key in required:
                if key not in data:
                    errors.append(f"{path}: missing required property '{key}'")
            properties = schema.get("properties", {})
            for key, sub in properties.items():
                if key in data:
                    errors.extend(self._check(data[key], sub, f"{path}.{key}"))

        if schema_type == "array" or "items" in schema:
            if isinstance(data, list) and "items" in schema:
                for i, item in enumerate(data):
                    errors.extend(self._check(item, schema["items"], f"{path}[{i}]"))

        if "minLength" in schema and isinstance(data, str) and len(data) < schema["minLength"]:
            errors.append(f"{path}: too short")
        if "maxLength" in schema and isinstance(data, str) and len(data) > schema["maxLength"]:
            errors.append(f"{path}: too long")

        return errors


def _matches_type(data: Any, schema_type: str) -> bool:
    if schema_type == "object":
        return isinstance(data, dict)
    if schema_type == "array":
        return isinstance(data, list)
    if schema_type == "string":
        return isinstance(data, str)
    if schema_type == "number":
        return isinstance(data, (int, float)) and not isinstance(data, bool)
    if schema_type == "integer":
        return isinstance(data, int) and not isinstance(data, bool)
    if schema_type == "boolean":
        return isinstance(data, bool)
    if schema_type == "null":
        return data is None
    return True


def _py_type(data: Any) -> str:
    if isinstance(data, bool):
        return "boolean"
    if isinstance(data, int):
        return "integer"
    if isinstance(data, float):
        return "number"
    if isinstance(data, str):
        return "string"
    if isinstance(data, list):
        return "array"
    if isinstance(data, dict):
        return "object"
    if data is None:
        return "null"
    return type(data).__name__


def regex_sub_all(pattern: "re.Pattern", replacement: str, text: str) -> str:
    return pattern.sub(replacement, text)


# ═══════════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════════

class GuardRailRunner:
    """Runs a guard's validators in order with the configured fail policy."""

    def __init__(self, max_refix_rounds: int = 3):
        self.max_refix_rounds = max_refix_rounds

    def run(self, guard: Guard, text: str,
            context: Optional[Dict[str, Any]] = None) -> GuardResult:
        context = context or {}
        validations: List[ValidationResult] = []
        actions: List[str] = []
        violation = False

        rounds = 0
        while True:
            rounds += 1
            # One full pass over validators; returns (done, resolved).
            current, validations, actions, violation, done = self._pass(
                guard, text, context, validations, actions, violation
            )
            text = current
            if done or rounds >= self.max_refix_rounds:
                break

        return GuardResult(
            passed=not violation,
            validations=validations,
            final_text=text,
            actions=actions,
            guard_name=guard.name,
        )

    def _pass(self, guard, text, context, validations, actions, violation):
        """Run one sweep of all validators. Returns (text, validations, actions,
        violation, done). 'done' True means no refix restart is needed."""
        current = text
        any_refix = False

        for validator in guard.validators:
            result = validator.validate(current, context)
            validations.append(result)
            if result.passed:
                continue

            # Validator failed.
            if guard.on_fail == "raise":
                raise GuardrailViolationError(
                    guard.name, validator.name, result.failure_reasons
                )

            if guard.on_fail in ("fix", "refix"):
                if result.fixed_value is not None:
                    current = result.fixed_value
                    actions.append(f"fixed:{validator.name}")
                    rerun = validator.validate(current, context)
                    validations.append(rerun)
                    if rerun.passed:
                        if guard.on_fail == "refix":
                            any_refix = True
                        continue
                    # Still failing after fix -> unresolvable.
                    actions.append(f"flagged:{validator.name}")
                    violation = True
                    if guard.fail_action == "hold":
                        return current, validations, actions, violation, True
                    continue
                # No fix available.
                actions.append(f"flagged:{validator.name}")
                violation = True
                if guard.fail_action == "hold":
                    return current, validations, actions, violation, True
                continue

            # filter (default): flag and move on.
            actions.append(f"flagged:{validator.name}")
            violation = True
            if guard.fail_action == "hold":
                return current, validations, actions, violation, True
            continue

        # End of a sweep.
        if any_refix:
            # Restart from the first validator on the fixed text.
            return current, validations, actions, violation, False

        return current, validations, actions, violation, True


# ═══════════════════════════════════════════════════════════════════════════
# Facade
# ═══════════════════════════════════════════════════════════════════════════

class GuardRailFacade:
    """Registry + validation entry point for named guards."""

    def __init__(self, config: Optional[Dict[str, Any]] = None,
                 runner: Optional[GuardRailRunner] = None):
        self._config = config or {}
        self._guards: Dict[str, Guard] = {}
        self._runner = runner or GuardRailRunner()

    def register_guard(self, guard: Guard) -> Guard:
        self._guards[guard.name] = guard
        return guard

    def validate(self, name: str, text: str,
                 context: Optional[Dict[str, Any]] = None) -> GuardResult:
        guard = self._guards.get(name)
        if guard is None:
            raise KeyError(f"Unknown guard: {name}")
        return self._runner.run(guard, text, context)

    def list_guards(self) -> List[str]:
        return list(self._guards.keys())

    def get_guard(self, name: str) -> Optional[Guard]:
        return self._guards.get(name)
