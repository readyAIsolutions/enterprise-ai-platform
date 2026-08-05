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

import abc
import json
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger("enterprise.guardrails")


# ═══════════════════════════════════════════════════════════════════════════
# Result & Error types
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class ValidationResult:
    """Outcome of a single validator run."""

    passed: bool
    score: float = 1.0  # 0.0 .. 1.0
    failure_reasons: list[str] = field(default_factory=list)
    fixed_value: str | None = None  # corrected text when fix is possible


@dataclass
class GuardResult:
    """Outcome of running a full guard (all its validators).

    Carries both the classic per-validator sweep view (validations / final_text /
    actions) and the Guardrails-AI plugin view (failures / fixes) so the legacy
    runner and the new declarative Guard.run / Guardrails facade can share one
    aggregate type.
    """

    passed: bool
    validations: list[Any] = field(default_factory=list)
    final_text: str = ""
    actions: list[str] = field(default_factory=list)
    guard_name: str = ""
    # Guardrails-AI plugin aggregation
    failures: list[FailResult] = field(default_factory=list)
    fixes: list[Any] = field(default_factory=list)
    name: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            self.name = self.guard_name
        if not self.guard_name:
            self.guard_name = self.name


@dataclass
class Guard:
    """Binds an ordered set of validators to a fail policy.

    Consumed by the classic GuardRailRunner (filter/raise/fix/refix) and, via
    ``run()`` / ``__call__``, by the declarative Guardrails facade which
    implements the Guardrails-AI on_fail action semantics (block / fix / raise).
    """

    name: str
    validators: list[Validator] = field(default_factory=list)
    # filter | raise | fix | refix  (classic runner policy)
    on_fail: str = "filter"
    # hold = stop on first unresolvable violation; continue = keep evaluating
    fail_action: str = "hold"

    def __post_init__(self) -> None:
        self.validators = list(self.validators)

    def __call__(self, value: Any, metadata: dict[str, Any] | None = None) -> GuardResult:
        return self.run(value, metadata)

    def run(self, value: Any, metadata: dict[str, Any] | None = None) -> GuardResult:
        """Run all validators declaratively, honouring per-validator on_fail
        actions: 'fix' applies fix_value (re-validating the repaired value to
        confirm), 'block' rejects (no fix applied) and 'raise' raises
        GuardrailViolationError. Aggregates into a GuardResult.
        """
        passed = True
        failures: list[FailResult] = []
        fixes: list[Any] = []
        actions: list[str] = []
        validations: list[Any] = []
        current = value

        for validator in self.validators:
            outcome = _evaluate_validator(validator, current, metadata)
            validations.append(outcome.raw)
            if outcome.passed:
                continue

            # ---- Guardrails-AI on_fail action semantics ----
            if outcome.on_fail == "raise":
                raise GuardrailViolationError(self.name, outcome.validator_name, outcome.reasons)

            if outcome.on_fail == "fix" and outcome.fix_value is not None:
                current = outcome.fix_value
                # Re-validate the repaired value to confirm the fix took.
                re_outcome = _evaluate_validator(validator, current, metadata)
                validations.append(re_outcome.raw)
                if re_outcome.passed:
                    fixes.append(outcome.fix_value)
                    actions.append(f"fixed:{outcome.validator_name}")
                    continue
                # Fix did not fully repair -> treat as blocked.
                passed = False
                failures.append(outcome.failure)
                actions.append(f"blocked:{outcome.validator_name}")
                if self.fail_action == "hold":
                    break
                continue

            # block (default): reject without applying a fix
            passed = False
            failures.append(outcome.failure)
            actions.append(f"blocked:{outcome.validator_name}")
            # classic 'hold' means stop evaluating further validators
            if self.fail_action == "hold":
                break

        return GuardResult(
            passed=passed,
            validations=validations,
            final_text=_canonical_text(current),
            actions=actions,
            guard_name=self.name,
            failures=[f for f in failures if f is not None],
            fixes=fixes,
            name=self.name,
        )


class GuardrailViolationError(Exception):
    """Raised by on_fail='raise' when a validator fails."""

    def __init__(
        self, guard_name: str, validator_name: str, reasons: list[str] | None = None
    ) -> None:
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


class Validator(abc.ABC):
    """Base class for all validators.

    Subclasses implement validate(value, metadata) -> ValidationResult
    (classic) or -> PassResult / FailResult (Guardrails-AI plugin style).

    ``data_type`` drives dispatch (``'string'`` | ``'number'`` | ``'json'`` ...)
    so the framework can coerce input appropriately before invoking a
    validator that was registered for a specific type.
    """

    def __init__(self, name: str | None = None, data_type: str = "string") -> None:
        self.name = name or self.__class__.__name__
        self.data_type = data_type

    @abc.abstractmethod
    def validate(self, value: Any, metadata: dict[str, Any] | None = None) -> Any:
        raise NotImplementedError  # pragma: no cover


# ═══════════════════════════════════════════════════════════════════════════
# Built-in validators
# ═══════════════════════════════════════════════════════════════════════════


class NoPIIValidator(Validator):
    """Flags emails, phones and SSNs; can redact them via fixed_value."""

    EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
    PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b")
    SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

    def __init__(
        self, name: str | None = None, redact: bool = True, redaction_token: str = "[REDACTED]"
    ) -> None:
        super().__init__(name or "NoPIIValidator")
        self.redact = redact
        self.redaction_token = redaction_token

    def validate(self, text: str, context: dict[str, Any] | None = None) -> ValidationResult:
        reasons: list[str] = []
        fixed = text
        for label, regex, _token in (
            ("email", self.EMAIL_RE, "[EMAIL]"),
            ("phone", self.PHONE_RE, "[PHONE]"),
            ("ssn", self.SSN_RE, "[SSN]"),
        ):
            for _match in regex.finditer(text):
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
    "fuck",
    "fucking",
    "shit",
    "shitty",
    "bitch",
    "asshole",
    "bastard",
    "dick",
    "cunt",
    "idiot",
    "stupid",
    "dumbass",
    "moron",
    "retard",
]


def _contains_any_word(text: str, words: list[str]) -> list[str]:
    lowered = text.lower()
    found = []
    for word in words:
        if re.search(rf"\b{re.escape(word)}\b", lowered):
            found.append(word)
    return found


class ProfanityValidator(Validator):
    """Flags curse words (word-boundary match, case-insensitive)."""

    def __init__(self, name: str | None = None, words: list[str] | None = None) -> None:
        super().__init__(name or "ProfanityValidator")
        self.words = list(words) if words is not None else TOXIC_WORDS.copy()

    def validate(self, text: str, context: dict[str, Any] | None = None) -> ValidationResult:
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

    def __init__(self, name: str | None = None, words: list[str] | None = None) -> None:
        super().__init__(name or "NoToxicValidator")
        self.words = list(words) if words is not None else TOXIC_WORDS.copy()

    def validate(self, text: str, context: dict[str, Any] | None = None) -> ValidationResult:
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

    def __init__(
        self, min: int | None = None, max: int | None = None, name: str | None = None
    ) -> None:
        super().__init__(name or "LengthValidator")
        self.min = min
        self.max = max

    def validate(self, text: str, context: dict[str, Any] | None = None) -> ValidationResult:
        length = len(text)
        reasons: list[str] = []
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

    def __init__(self, pattern: str, name: str | None = None) -> None:
        super().__init__(name or "RegexValidator")
        self.pattern = pattern
        self._regex = re.compile(pattern)

    def validate(self, text: str, context: dict[str, Any] | None = None) -> ValidationResult:
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

    def __init__(self, name: str | None = None) -> None:
        super().__init__(name or "NoPromptInjectionValidator")
        self._compiled = [re.compile(p) for p in self.PATTERNS]

    def validate(self, text: str, context: dict[str, Any] | None = None) -> ValidationResult:
        reasons: list[str] = []
        for regex in self._compiled:
            if regex.search(text):
                reasons.append(f"prompt injection detected: {regex.pattern}")
        if reasons:
            return ValidationResult(passed=False, score=0.0, failure_reasons=reasons)
        return ValidationResult(passed=True, score=1.0)


class JSONSchemaValidator(Validator):
    """Parses text as JSON and validates it against a simple schema."""

    def __init__(self, params: dict[str, Any] | None = None, name: str | None = None) -> None:
        super().__init__(name or "JSONSchemaValidator", data_type="json")
        self.params = params or {}

    def validate(self, text: Any, context: dict[str, Any] | None = None) -> ValidationResult:
        # Accept either a raw JSON string (classic path) or an already-parsed
        # value (Guardrails-AI data_type='json' dispatch path).
        if isinstance(text, str):
            try:
                data = json.loads(text)
            except (json.JSONDecodeError, TypeError) as exc:
                return ValidationResult(
                    passed=False,
                    score=0.0,
                    failure_reasons=[f"invalid JSON: {exc}"],
                )
        else:
            data = text
        errors = self._check(data, self.params, "$")
        if errors:
            return ValidationResult(passed=False, score=0.0, failure_reasons=errors)
        return ValidationResult(passed=True, score=1.0)

    def _check(self, data: Any, schema: Any, path: str) -> list[str]:
        if not isinstance(schema, dict):
            return []
        errors: list[str] = []

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


def regex_sub_all(pattern: re.Pattern, replacement: str, text: str) -> str:
    return pattern.sub(replacement, text)


# ═══════════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════════


class GuardRailRunner:
    """Runs a guard's validators in order with the configured fail policy."""

    def __init__(self, max_refix_rounds: int = 3) -> None:
        self.max_refix_rounds = max_refix_rounds

    def run(self, guard: Guard, text: str, context: dict[str, Any] | None = None) -> GuardResult:
        context = context or {}
        validations: list[ValidationResult] = []
        actions: list[str] = []
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
                raise GuardrailViolationError(guard.name, validator.name, result.failure_reasons)

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

    def __init__(
        self, config: dict[str, Any] | None = None, runner: GuardRailRunner | None = None
    ) -> None:
        self._config = config or {}
        self._guards: dict[str, Guard] = {}
        self._runner = runner or GuardRailRunner()

    def register_guard(self, guard: Guard) -> Guard:
        self._guards[guard.name] = guard
        return guard

    def validate(self, name: str, text: str, context: dict[str, Any] | None = None) -> GuardResult:
        guard = self._guards.get(name)
        if guard is None:
            msg = f"Unknown guard: {name}"
            raise KeyError(msg)
        return self._runner.run(guard, text, context)

    def list_guards(self) -> list[str]:
        return list(self._guards.keys())

    def get_guard(self, name: str) -> Guard | None:
        return self._guards.get(name)


# ═══════════════════════════════════════════════════════════════════════════
# Guardrails-AI validator-plugin layer
# (PassResult / FailResult union + name-registered registry + data_type
#  dispatch + on_fail fix/block/raise semantics) — stdlib only.
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class PassResult:
    """Guardrails-AI style pass outcome for a validator run."""

    passed: bool = True
    validator_name: str = ""
    error_message: str = ""
    fix_value: Any = None
    on_fail: str | None = None
    # aliases kept for drop-in compatibility with the classic path
    failure_reasons: list[str] = field(default_factory=list)
    fixed_value: Any = None
    score: float = 1.0


@dataclass
class FailResult:
    """Guardrails-AI style fail outcome carrying the on_fail action to take.

    on_fail is one of:
      - 'fix':   apply ``fix_value`` to repair the input
      - 'block': reject the input (do NOT apply a fix)
      - 'raise': raise GuardrailViolationError
    """

    passed: bool = False
    validator_name: str = ""
    error_message: str = ""
    fix_value: Any = None
    on_fail: str = "block"
    # aliases kept for drop-in compatibility with the classic path
    failure_reasons: list[str] = field(default_factory=list)
    fixed_value: Any = None
    score: float = 0.0


def _coerce(value: Any, data_type: str) -> Any:
    """data_type dispatch: coerce input before invoking a typed validator."""
    if data_type == "json" and isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError, TypeError):
            return value
    if data_type == "number" and isinstance(value, str):
        s = value.strip()
        try:
            return int(s) if s.lstrip("+-").isdigit() else float(s)
        except (ValueError, TypeError):
            return value
    if data_type == "string" and not isinstance(value, str):
        return str(value)
    return value


def _canonical_text(value: Any) -> str:
    """Render any value as text for GuardResult.final_text."""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return str(value)


@dataclass
class _RunOutcome:
    """Normalised single-validator evaluation."""

    raw: Any
    passed: bool
    validator_name: str
    error_message: str
    fix_value: Any
    on_fail: str
    reasons: list[str]
    failure: FailResult | None


def _evaluate_validator(
    validator: Validator, value: Any, metadata: dict[str, Any] | None = None
) -> _RunOutcome:
    """Validate ``value`` through ``validator`` after applying data_type
    coercion, normalising the result (PassResult / FailResult / ValidationResult)
    into a single _RunOutcome."""
    data_type = getattr(validator, "data_type", "string") or "string"
    coerced = _coerce(value, data_type)
    raw = validator.validate(coerced, metadata)
    vname = getattr(validator, "name", None) or validator.__class__.__name__

    if isinstance(raw, PassResult):
        return _RunOutcome(raw, True, vname, "", None, "", [], None)

    if isinstance(raw, FailResult):
        reasons = list(raw.failure_reasons) or (
            [raw.error_message] if raw.error_message else [f"failed: {vname}"]
        )
        return _RunOutcome(
            raw=raw,
            passed=False,
            validator_name=vname,
            error_message=raw.error_message or "; ".join(reasons),
            fix_value=raw.fix_value if raw.fix_value is not None else raw.fixed_value,
            on_fail=raw.on_fail or "block",
            reasons=reasons,
            failure=raw,
        )

    if isinstance(raw, ValidationResult):
        if raw.passed:
            return _RunOutcome(raw, True, vname, "", None, "", [], None)
        reasons = list(raw.failure_reasons) or ["failed"]
        on_fail = "fix" if raw.fixed_value is not None else "block"
        fail = FailResult(
            validator_name=vname,
            error_message="; ".join(reasons),
            fix_value=raw.fixed_value,
            on_fail=on_fail,
            failure_reasons=reasons,
            fixed_value=raw.fixed_value,
        )
        return _RunOutcome(
            raw, False, vname, "; ".join(reasons), raw.fixed_value, on_fail, reasons, fail
        )

    # Unknown result contract: default to blocking if not truthily passing.
    passed = bool(getattr(raw, "passed", raw is True))
    if passed:
        return _RunOutcome(raw, True, vname, "", None, "", [], None)
    return _RunOutcome(
        raw, False, vname, "validation failed", None, "block", ["validation failed"], None
    )


# ───────────────────────────────────────────────────────────────────────────
# Built-in plugin validators (Guardrails-AI style, PassResult/FailResult)
# ───────────────────────────────────────────────────────────────────────────

_PII_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PII_PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b")
_PII_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


class PIIValidator(Validator):
    """Flags emails / phones / SSNs; on_fail='fix' offers a redacted fix_value."""

    def __init__(self, name: str | None = None, redact: bool = True) -> None:
        super().__init__(name or "PIIValidator", data_type="string")
        self.redact = redact

    def validate(self, value: Any, metadata: dict[str, Any] | None = None) -> Any:
        text = str(value)
        reasons: list[str] = []
        for label, regex in (
            ("email", _PII_EMAIL_RE),
            ("phone", _PII_PHONE_RE),
            ("ssn", _PII_SSN_RE),
        ):
            if regex.search(text):
                reasons.append(f"PII detected: {label}")
        if not reasons:
            return PassResult(validator_name=self.name)
        fixed = text
        if self.redact:
            fixed = _PII_EMAIL_RE.sub("[EMAIL]", fixed)
            fixed = _PII_PHONE_RE.sub("[PHONE]", fixed)
            fixed = _PII_SSN_RE.sub("[SSN]", fixed)
        return FailResult(
            validator_name=self.name,
            error_message="; ".join(reasons),
            fix_value=fixed if self.redact else None,
            on_fail="fix" if self.redact else "block",
            failure_reasons=reasons,
            fixed_value=fixed if self.redact else None,
        )


_PROMPT_INJECTION_PATTERNS = [
    r"(?i)ignore\s+(?:all\s+)?(?:previous|prior|above|earlier|your)\s+(?:instructions?|prompts?|messages?|directives?|context)",
    r"(?i)disregard\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions?|prompts?|messages?)",
    r"(?i)forget\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions?|prompts?|messages?)",
    r"(?i)override\s+(?:your\s+)?(?:instructions?|programming|safety|rules?|system\s+prompt)",
    r"(?i)reveal\s+(?:your|the|hidden|system)\s+(?:system\s+)?(?:prompt|instructions?|secret)",
    r"(?i)</?system>|\[INST\]|<<SYS>>|</?instruction>",
    r"(?i)you\s+are\s+now\s+(?:a\s+)?(?:jailbroken|uncensored|DAN|without\s+restrictions)",
]


class PromptInjectionValidator(Validator):
    """Flags prompt-injection attempts (ignore/override instruction patterns)."""

    def __init__(self, name: str | None = None) -> None:
        super().__init__(name or "PromptInjectionValidator", data_type="string")
        self._compiled = [re.compile(p) for p in _PROMPT_INJECTION_PATTERNS]

    def validate(self, value: Any, metadata: dict[str, Any] | None = None) -> Any:
        text = str(value)
        reasons = ["prompt injection detected" for p in self._compiled if p.search(text)]
        if not reasons:
            return PassResult(validator_name=self.name)
        return FailResult(
            validator_name=self.name,
            error_message="; ".join(reasons),
            on_fail="raise",
            failure_reasons=reasons,
        )


_JAILBREAK_PATTERNS = [
    r"(?i)\bdan\b",
    r"(?i)do\s+anything\s+now",
    r"(?i)no\s+(?:restrictions|limits|rules|guardrails)",
    r"(?i)(?:pretend|act)\s+(?:to\s+)?(?:be|as)\s+(?:an?\s+)?(?:uncensored|unfiltered|god)\s+mode",
    r"(?i)jailbreak",
    r"(?i)developer\s+mode",
]


class JailbreakValidator(Validator):
    """Flags classic 'jailbreak' / 'DAN' / 'do anything now' attempt markers."""

    def __init__(self, name: str | None = None) -> None:
        super().__init__(name or "JailbreakValidator", data_type="string")
        self._compiled = [re.compile(p) for p in _JAILBREAK_PATTERNS]

    def validate(self, value: Any, metadata: dict[str, Any] | None = None) -> Any:
        text = str(value)
        reasons = [f"jailbreak marker: {p.pattern}" for p in self._compiled if p.search(text)]
        if not reasons:
            return PassResult(validator_name=self.name)
        return FailResult(
            validator_name=self.name,
            error_message="; ".join(reasons),
            on_fail="block",
            failure_reasons=reasons,
        )


_SHELL_INJECTION_PATTERNS = [
    r"(?i)\bos\.system\s*\(",
    r"(?i)\bsubprocess\s*\.\s*(?:run|call|Popen)\s*\(",
    r"(?i)\b(?:exec|eval|system)\s*\(",
    r"`[^`]*`",
    r"\$(?:\([^)]*\)|\{[^}]*\})",
    r"(?:\;\s*rm\s+-rf|&&|>\/dev\/null|2>&1)",
]


class ShellInjectionValidator(Validator):
    """Flags shell command-injection payloads (metacharacters, exec calls)."""

    def __init__(self, name: str | None = None) -> None:
        super().__init__(name or "ShellInjectionValidator", data_type="string")
        self._compiled = [re.compile(p) for p in _SHELL_INJECTION_PATTERNS]

    def validate(self, value: Any, metadata: dict[str, Any] | None = None) -> Any:
        text = str(value)
        reasons = [f"shell injection: {p.pattern}" for p in self._compiled if p.search(text)]
        if not reasons:
            return PassResult(validator_name=self.name)
        return FailResult(
            validator_name=self.name,
            error_message="; ".join(reasons),
            on_fail="block",
            failure_reasons=reasons,
        )


_SQL_INJECTION_PATTERNS = [
    r"(?i)\bunion\s+(?:all\s+)?select\b",
    r"(?i)\bdrop\s+table\b",
    r"(?i)\b(?:or|and)\s+['\"]?1['\"]?\s*=\s*['\"]?1['\"]?\b",
    r"(?i)\bsleep\s*\(\s*\d",
    r"(?i)--\s|#\s|/\*!",
    r"['\"]\s*;",
    r"(?i);\s*(?:drop|delete|select|insert|update)\b",
]


class SQLInjectionValidator(Validator):
    """Flags classic SQL injection payloads (tautologies, stacked queries)."""

    def __init__(self, name: str | None = None) -> None:
        super().__init__(name or "SQLInjectionValidator", data_type="string")
        self._compiled = [re.compile(p) for p in _SQL_INJECTION_PATTERNS]

    def validate(self, value: Any, metadata: dict[str, Any] | None = None) -> Any:
        text = str(value)
        reasons = [f"sql injection: {p.pattern}" for p in self._compiled if p.search(text)]
        if not reasons:
            return PassResult(validator_name=self.name)
        return FailResult(
            validator_name=self.name,
            error_message="; ".join(reasons),
            on_fail="block",
            failure_reasons=reasons,
        )


class ToxicLanguageValidator(Validator):
    """Flags toxic / profane language against a wordlist (on_fail='block')."""

    def __init__(self, name: str | None = None, words: list[str] | None = None) -> None:
        super().__init__(name or "ToxicLanguageValidator", data_type="string")
        self.words = list(words) if words is not None else TOXIC_WORDS.copy()

    def validate(self, value: Any, metadata: dict[str, Any] | None = None) -> Any:
        text = str(value)
        found = _contains_any_word(text, self.words)
        if not found:
            return PassResult(validator_name=self.name)
        reasons = [f"toxic language: {w}" for w in found]
        return FailResult(
            validator_name=self.name,
            error_message="; ".join(reasons),
            on_fail="block",
            failure_reasons=reasons,
        )


class SecretLeakValidator(Validator):
    """Flags leaked secrets: AWS access keys, PEM private keys, bearer tokens."""

    _AWS_KEY_RE = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
    _PEM_PRIV_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
    _BEARER_RE = re.compile(r"(?i)\b(?:bearer|token)\s+[A-Za-z0-9._~+/=-]{20,}")

    def __init__(self, name: str | None = None) -> None:
        super().__init__(name or "SecretLeakValidator", data_type="string")

    def validate(self, value: Any, metadata: dict[str, Any] | None = None) -> Any:
        text = str(value)
        reasons: list[str] = []
        if self._AWS_KEY_RE.search(text):
            reasons.append("AWS access key leaked")
        if self._PEM_PRIV_RE.search(text):
            reasons.append("private key leaked")
        if self._BEARER_RE.search(text):
            reasons.append("bearer token leaked")
        if not reasons:
            return PassResult(validator_name=self.name)
        return FailResult(
            validator_name=self.name,
            error_message="; ".join(reasons),
            on_fail="block",
            failure_reasons=reasons,
        )


_URL_SCHEME_RE = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*)://[^\s'\"]+")
# Dangerous schemes routinely written WITHOUT '//' (javascript:, data:, vbscript:)
_URL_BARE_SCHEME_RE = re.compile(r"(?i)\b(javascript|vbscript|data|file):")


class URLValidator(Validator):
    """Flags non-http(s) URL schemes (javascript:, data:, file:) and malformed
    absolute URLs — a lightweight SSRF/credential-exfil guard."""

    def __init__(self, name: str | None = None) -> None:
        super().__init__(name or "URLValidator", data_type="string")

    def validate(self, value: Any, metadata: dict[str, Any] | None = None) -> Any:
        text = str(value)
        reasons: list[str] = []
        for match in _URL_SCHEME_RE.finditer(text):
            scheme = match.group(1).lower()
            if scheme not in ("http", "https"):
                reasons.append(f"disallowed URL scheme: {scheme}://")
            else:
                rest = match.group(0).split("://", 1)[1]
                if not rest or "." not in rest.split("/")[0]:
                    reasons.append(f"malformed http(s) URL: {match.group(0)}")
        for match in _URL_BARE_SCHEME_RE.finditer(text):
            scheme = match.group(1).lower()
            reasons.append(f"disallowed URL scheme: {scheme}:")
        if not reasons:
            return PassResult(validator_name=self.name)
        return FailResult(
            validator_name=self.name,
            error_message="; ".join(reasons),
            on_fail="block",
            failure_reasons=reasons,
        )


# ───────────────────────────────────────────────────────────────────────────
# ValidatorRegistry + register_validator
# ───────────────────────────────────────────────────────────────────────────


class ValidatorRegistry:
    """Name -> validator-class registry with a register_validator decorator and
    per-name data_type dispatch metadata."""

    def __init__(self) -> None:
        self._validators: dict[str, type[Validator]] = {}
        self._data_types: dict[str, str] = {}

    def register_validator(
        self, name: str, data_type: str = "string"
    ) -> Callable[[type[Validator]], type[Validator]]:
        """Decorator registering a validator class under ``name``."""

        def decorator(cls: type[Validator]) -> type[Validator]:
            if name in self._validators:
                msg = f"Validator '{name}' already registered"
                raise ValueError(msg)
            if not (isinstance(cls, type) and issubclass(cls, Validator)):
                msg = f"register_validator('{name}') requires a Validator subclass, got {cls!r}"
                raise TypeError(msg)
            self._validators[name] = cls
            self._data_types[name] = data_type
            return cls

        return decorator

    def get(self, name: str) -> type[Validator] | None:
        return self._validators.get(name)

    def requires(self, name: str) -> str:
        """Return the data_type registered for a validator name ('' if unknown)."""
        return self._data_types.get(name, "")

    def instantiate(self, name: str, *args: Any, **kwargs: Any) -> Validator:
        cls = self._validators.get(name)
        if cls is None:
            msg = f"Unknown validator: {name}"
            raise KeyError(msg)
        validator = cls(*args, **kwargs)
        # The registry's registered data_type drives dispatch; apply it so a
        # validator registered for 'number'/'json' is coerced appropriately.
        validator.data_type = self._data_types.get(name, getattr(validator, "data_type", "string"))
        return validator

    def list_validators(self) -> list[str]:
        return sorted(self._validators.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._validators

    def __len__(self) -> int:
        return len(self._validators)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ValidatorRegistry({len(self._validators)} validators)>"


def _register_builtin_validators(registry: ValidatorRegistry) -> None:
    """Register every built-in plugin validator with its dispatch data_type."""
    registry.register_validator("pii", data_type="string")(PIIValidator)
    registry.register_validator("prompt_injection", data_type="string")(PromptInjectionValidator)
    registry.register_validator("jailbreak", data_type="string")(JailbreakValidator)
    registry.register_validator("shell_injection", data_type="string")(ShellInjectionValidator)
    registry.register_validator("sql_injection", data_type="string")(SQLInjectionValidator)
    registry.register_validator("toxic_language", data_type="string")(ToxicLanguageValidator)
    registry.register_validator("json_schema", data_type="json")(JSONSchemaValidator)
    registry.register_validator("secret_leak", data_type="string")(SecretLeakValidator)
    registry.register_validator("url", data_type="string")(URLValidator)


def build_default_registry() -> ValidatorRegistry:
    registry = ValidatorRegistry()
    _register_builtin_validators(registry)
    return registry


_DEFAULT_REGISTRY = build_default_registry()


def register_validator(name: str, data_type: str = "string"):
    """Module-level convenience: register a validator into the default registry."""
    return _DEFAULT_REGISTRY.register_validator(name, data_type)


# ───────────────────────────────────────────────────────────────────────────
# Guardrails facade (declarative)
# ───────────────────────────────────────────────────────────────────────────


def _aggregate(results: list[GuardResult]) -> GuardResult:
    """Combine multiple per-guard results into one aggregate GuardResult."""
    all_passed = all(r.passed for r in results)
    failures: list[FailResult] = []
    fixes: list[Any] = []
    validations: list[Any] = []
    actions: list[str] = []
    for r in results:
        failures.extend(r.failures)
        fixes.extend(r.fixes)
        validations.extend(r.validations)
        actions.extend(r.actions)
    names = ",".join(r.guard_name for r in results if r.guard_name)
    final_text = ""
    # Prefer the last non-produced final_text from a passing guard chain.
    for r in results:
        if r.final_text is not None:
            final_text = r.final_text
    return GuardResult(
        passed=all_passed,
        validations=validations,
        final_text=final_text,
        actions=actions,
        guard_name=names,
        failures=failures,
        fixes=fixes,
        name=names,
    )


class Guardrails:
    """Declarative facade over the validator-plugin system.

    ``validate(value, guard_names, metadata=None)`` runs one or several named
    guards and returns the aggregate GuardResult.
    """

    def __init__(
        self, config: dict[str, Any] | None = None, registry: ValidatorRegistry | None = None
    ) -> None:
        self._config = config or {}
        self.registry = registry or build_default_registry()
        self._guards: dict[str, Guard] = {}

    # -- registry plumbing -------------------------------------------------
    def register_validator(self, name: str, data_type: str = "string"):
        return self.registry.register_validator(name, data_type)

    def list_validators(self) -> list[str]:
        return self.registry.list_validators()

    def get_validator(self, name: str) -> type[Validator] | None:
        return self.registry.get(name)

    # -- guards ------------------------------------------------------------
    def register_guard(self, guard: Guard) -> Guard:
        self._guards[guard.name] = guard
        return guard

    def add_guard(self, name: str, validators: list[Validator], on_fail: str = "block") -> Guard:
        guard = Guard(name=name, validators=validators, on_fail=on_fail)
        return self.register_guard(guard)

    def list_guards(self) -> list[str]:
        return list(self._guards.keys())

    def get_guard(self, name: str) -> Guard | None:
        return self._guards.get(name)

    # -- validation --------------------------------------------------------
    def validate(
        self,
        value: Any,
        guard_names: str | list[str],
        metadata: dict[str, Any] | None = None,
    ) -> GuardResult:
        names = [guard_names] if isinstance(guard_names, str) else list(guard_names)
        if not names:
            return GuardResult(
                passed=True, final_text=_canonical_text(value), guard_name="", name=""
            )
        results: list[GuardResult] = []
        for name in names:
            guard = self._guards.get(name)
            if guard is None:
                msg = f"Unknown guard: {name}"
                raise KeyError(msg)
            results.append(guard.run(value, metadata))
        return _aggregate(results)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Guardrails guards={list(self._guards)} validators={self.registry.list_validators()}>"
        )
