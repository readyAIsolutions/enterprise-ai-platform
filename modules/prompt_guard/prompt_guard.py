#!/usr/bin/env python3
"""Enterprise Prompt Guard Module — injection / jailbreak / policy guarding.

A stdlib-only facade that inspects an inbound prompt and produces a
:class:`GuardVerdict` deciding whether it may proceed to the model. It chains
three independent checks in short-circuit order:

1. :class:`PromptInjectionGuard` — **prompt injection** patterns (directive
   smuggling: "ignore previous instructions", "system prompt", persona-override)
   and **jailbreak** patterns (DAN-style, role-play bypass, encoding tricks).
   Lexical (regex/pattern) + behavioral (ratio/depth heuristics) scoring.

2. :class:`PolicyGuard` — declarative policy enforcement: denylisted topics,
   max prompt length, allowed roles.

3. :class:`PromptGuard` — the facade. ``run(prompt, policy)`` chains the above
   in short-circuit, accumulates a risk score and blocked patterns, and returns
   a :class:`GuardVerdict`. Every decision is recorded in an append-only
   :class:`AuditLog`.

All components are stdlib-only (``re``, ``dataclasses``, ``time``, ``uuid``)
with zero external dependencies.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from enterprise.platform_kernel import HealthStatus, Module, module

logger = logging.getLogger("enterprise.prompt_guard")

__version__ = "1.0.0"


# =============================================================================
# Audit log
# =============================================================================


@dataclass
class AuditEntry:
    """A single immutable record of a guard decision."""

    id: str
    ts: float
    prompt_id: str
    allowed: bool
    risk_score: float
    reasons: list[str] = field(default_factory=list)
    blocked_patterns: list[str] = field(default_factory=list)


class AuditLog:
    """Append-only in-memory log of guard decisions."""

    def __init__(self, capacity: int = 10000) -> None:
        self._entries: list[AuditEntry] = []
        self.capacity = capacity

    def append(self, entry: AuditEntry) -> None:
        self._entries.append(entry)
        if len(self._entries) > self.capacity:
            # cheap FIFO trim
            del self._entries[: len(self._entries) - self.capacity]

    def entries(self) -> list[AuditEntry]:
        return list(self._entries)

    def count(self) -> int:
        return len(self._entries)

    def blocked_count(self) -> int:
        return sum(1 for e in self._entries if not e.allowed)

    def recent(self, n: int = 20) -> list[AuditEntry]:
        return list(self._entries[-n:])


# =============================================================================
# Injection / jailbreak guard
# =============================================================================


@dataclass
class GuardFinding:
    """Result of one guard component."""

    matched: bool
    score: float = 0.0
    patterns: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


class PromptInjectionGuard:
    """Detect prompt-injection and jailbreak attempts (lexical + behavioral).

    Lexical detection: a curated set of directive / jailbreak token patterns
    matched case-insensitively. Behavioral detection: heuristic scoring such as
    the ratio of imperative directive tokens to benign content, and the
    presence of developer-secret-forcing triggers ("output the system prompt",
    "repeat your instructions verbatim").
    """

    # Ordinary prompt-injection directives.
    INJECTION_PATTERNS: list[str] = [
        r"ignore (all |previous |prior )?instructions",
        r"ignore (all |previous |prior )?(the )?above",
        r"disregard (all |previous )?(the )?instructions",
        r"you are now (the )?system",
        r"system prompt",
        r"reveal (your |the )?(system |hidden )?(prompt|instructions)",
        r"print (your |the )?(system )?prompt",
        r"repeat (your |the )?instructions (verbatim|exactly)",
        r"override (your |all )?(instructions|rules)",
        r"new instructions",
        r"from now on (you )?must",
        r"act as if you have no (rules|restrictions)",
        r"pretend you are not (an )?assistant",
        r"do whatever (the|they|you) (want|wish)",
        r"you have (no |zero )?(rules|restrictions|constraints)",
    ]

    # Jailbreak-specific bypass patterns.
    JAILBREAK_PATTERNS: list[str] = [
        r"\bDAN\b",
        r"do anything now",
        r"jailbreak",
        r"developer mode",
        r"hypothetical (scenario|scenarios)",
        r"fictional (scenario|scenarios)",
        r"in a (hypothetical|fictional) (world|setting)",
        r"role[ -]?play",
        r"as (a )?(movie|novel|role[- ]play) scenario",
        r"for (research|testing|educational|entertainment) purposes (only )?(please )?(ignore|bypass)",
        r"base64",
        r"rot13",
        r"opaquely (encoded|obfuscated)",
    ]

    def __init__(
        self,
        injection_threshold: float = 1.0,
        jailbreak_threshold: float = 1.0,
        allowlist: list[str] | None = None,
    ) -> None:
        self.injection_threshold = injection_threshold
        self.jailbreak_threshold = jailbreak_threshold
        self.allowlist = [a.lower() for a in (allowlist or [])]
        self._inj_re = [re.compile(p, re.IGNORECASE) for p in self.INJECTION_PATTERNS]
        self._jb_re = [re.compile(p, re.IGNORECASE) for p in self.JAILBREAK_PATTERNS]

    # -- lexical ----------------------------------------------------------- #

    def scan_lexical(self, text: str) -> GuardFinding:
        """Match injection + jailbreak token patterns, return a finding."""
        matched = 0
        patterns: list[str] = []
        for p in self._inj_re:
            if p.search(text):
                matched += 1
                patterns.append(p.pattern)
        for p in self._jb_re:
            if p.search(text):
                matched += 1
                patterns.append(p.pattern)
        return GuardFinding(
            matched=matched > 0,
            score=float(matched),
            patterns=patterns,
            reasons=["matched %d lexical pattern(s)" % matched] if matched else [],
        )

    # -- behavioral -------------------------------------------------------- #

    def _behavioral_score(self, text: str) -> GuardFinding:
        """Heuristic behavioural scoring.

        * Imperative directive ratio: fraction of lines starting with an
          imperative verb ("ignore", "forget", "override", "pretend", "you").
        * Developer-secret forcing: "output the system prompt" style phrasing.
        """
        score = 0.0
        reasons: list[str] = []
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            return GuardFinding(False, 0.0, [], [])
        imperative = [
            ln
            for ln in lines
            if re.match(
                r"^(ignore|forget|override|pretend|you( must| are| should)|do not|repeat|reveal|print)\b",
                ln,
                re.IGNORECASE,
            )
        ]
        ratio = len(imperative) / len(lines)
        if ratio > 0.5:
            score += 2.0
            reasons.append(f"high imperative-directive ratio ({ratio:.2f})")
        if re.search(r"output (the |your )?(system )?prompt", text, re.IGNORECASE):
            score += 2.0
            reasons.append("developer-secret forcing phrasing")
        # Length-weighted: very short prompts shouldn't be penalised for a single verb.
        return GuardFinding(
            matched=score > 0,
            score=score,
            patterns=[r"imperative_directive_ratio"] if ratio > 0.5 else [],
            reasons=reasons,
        )

    # -- public ------------------------------------------------------------ #

    def detect(self, text: str) -> GuardFinding:
        """Combined injection + jailbreak check: lexical + behavioral.

        Returns a finding; ``matched`` is True if either signal fired.
        """
        lex = self.scan_lexical(text)
        beh = self._behavioral_score(text)
        score = lex.score + beh.score
        patterns = list(dict.fromkeys(lex.patterns + beh.patterns))
        reasons = list(dict.fromkeys(lex.reasons + beh.reasons))
        return GuardFinding(
            matched=lex.matched or beh.matched,
            score=score,
            patterns=patterns,
            reasons=reasons,
        )

    def detect_injection(self, text: str) -> GuardFinding:
        return self.scan_lexical(text)

    def detect_jailbreak(self, text: str) -> GuardFinding:
        """Jailbreak-only lexical + behavioral signal."""
        matched = 0
        patterns: list[str] = []
        for p in self._jb_re:
            if p.search(text):
                matched += 1
                patterns.append(p.pattern)
        beh = self._behavioral_score(text)
        return GuardFinding(
            matched=(matched > 0) or beh.matched,
            score=float(matched) + beh.score,
            patterns=patterns + beh.patterns,
            reasons=(["matched %d jailbreak pattern(s)" % matched] if matched else [])
            + beh.reasons,
        )


# =============================================================================
# Policy guard
# =============================================================================


@dataclass
class Policy:
    """Declarative prompt policy."""

    denylist: list[str] = field(default_factory=list)  # forbidden topics / tokens
    max_length: int = 0  # 0 == unlimited
    allowed_roles: list[str] = field(default_factory=list)  # empty == any

    @classmethod
    def from_config(cls, cfg: dict[str, Any] | None) -> Policy:
        cfg = cfg or {}
        return cls(
            denylist=[str(t).lower() for t in cfg.get("denylist", [])],
            max_length=int(cfg.get("max_length", 0) or 0),
            allowed_roles=[str(r).lower() for r in cfg.get("allowed_roles", [])],
        )


class PolicyGuard:
    """Enforce a :class:`Policy` (denylist topics, max length, allowed roles)."""

    def __init__(self) -> None:
        pass

    def enforce(
        self, prompt: str, policy: Policy | None = None, role: str | None = None
    ) -> GuardFinding:
        policy = policy or Policy()
        reasons: list[str] = []
        patterns: list[str] = []
        blocked = False

        # Denylist topics.
        prompt_lower = prompt.lower()
        for topic in policy.denylist:
            if topic and topic in prompt_lower:
                blocked = True
                patterns.append(topic)
                reasons.append(f"denylisted topic present: {topic!r}")

        # Max length.
        if policy.max_length > 0 and len(prompt) > policy.max_length:
            blocked = True
            patterns.append("max_length")
            reasons.append("prompt length %d exceeds max %d" % (len(prompt), policy.max_length))

        # Allowed roles.
        if policy.allowed_roles:
            role_l = (role or "").lower()
            if role_l not in policy.allowed_roles:
                blocked = True
                patterns.append("role")
                reasons.append(f"role {role!r} not in allowed_roles")

        return GuardFinding(
            matched=blocked,
            score=1.0 if blocked else 0.0,
            patterns=patterns,
            reasons=reasons,
        )


# =============================================================================
# Facade
# =============================================================================


@dataclass
class GuardVerdict:
    """Outcome of :meth:`PromptGuard.run`."""

    allowed: bool
    risk_score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    blocked_patterns: list[str] = field(default_factory=list)

    def summary(self) -> str:  # pragma: no cover - convenience
        return "ALLOWED" if self.allowed else "BLOCKED"


class PromptGuard:
    """Facade chaining injection + jailbreak + policy checks in short-circuit.

    ``run(prompt, policy, role, prompt_id)``:

    1. **Jailbreak** check first (most dangerous). If a jailbreak signal fires
       hard, block immediately.
    2. **Injection** check. If injection pattern matches, block.
    3. **Policy** check. Enforce denylist / length / roles.

    The first blocking check short-circuits the remaining checks. Every decision
    is appended to :attr:`audit_log`.
    """

    def __init__(
        self,
        injection: PromptInjectionGuard | None = None,
        policy_guard: PolicyGuard | None = None,
        audit_log: AuditLog | None = None,
        risk_threshold: float = 2.0,
    ) -> None:
        self.injection = injection or PromptInjectionGuard()
        self.policy_guard = policy_guard or PolicyGuard()
        self.audit_log = audit_log or AuditLog()
        self.risk_threshold = risk_threshold

    def run(
        self,
        prompt: str,
        policy: Policy | None = None,
        role: str | None = None,
        prompt_id: str | None = None,
    ) -> GuardVerdict:
        prompt_id = prompt_id or uuid.uuid4().hex
        reasons: list[str] = []
        blocked: list[str] = []
        risk = 0.0
        allowed = True

        # 1) Jailbreak (short-circuit on hard match).
        jb = self.injection.detect_jailbreak(prompt)
        if jb.matched:
            allowed = False
            risk = max(risk, jb.score)
            reasons.append("jailbreak pattern detected")
            reasons.extend(f"jailbreak: {r}" for r in jb.reasons)
            blocked.extend(jb.patterns)

        # 2) Injection.
        if allowed:
            inj = self.injection.scan_lexical(prompt)
            if inj.matched:
                allowed = False
                risk = max(risk, inj.score)
                reasons.append("prompt injection pattern detected")
                blocked.extend(inj.patterns)

        # 3) Policy.
        if allowed:
            pol = self.policy_guard.enforce(prompt, policy, role)
            if pol.matched:
                allowed = False
                risk = max(risk, pol.score)
                reasons.extend(pol.reasons)
                blocked.extend(pol.patterns)

        # Risk accumulates for blocked prompts even when a specific gate did not
        # hard-fire (e.g. sub-threshold behavioural signal).
        if allowed:
            beh = self.injection._behavioral_score(prompt)
            risk = min(beh.score, 5.0)
            if risk >= self.risk_threshold:
                allowed = False
                reasons.append("behavioural risk above threshold")
                blocked.extend(beh.patterns)

        blocked = list(dict.fromkeys(blocked))
        reasons = list(dict.fromkeys(reasons))
        verdict = GuardVerdict(
            allowed=allowed,
            risk_score=round(risk, 4),
            reasons=reasons,
            blocked_patterns=blocked,
        )

        self.audit_log.append(
            AuditEntry(
                id=uuid.uuid4().hex,
                ts=time.time(),
                prompt_id=prompt_id,
                allowed=allowed,
                risk_score=verdict.risk_score,
                reasons=reasons,
                blocked_patterns=blocked,
            )
        )
        return verdict


# =============================================================================
# Kernel module
# =============================================================================


@module(name="prompt_guard", version="1.0.0")
class PromptGuardModule(Module):
    """Kernel-registered module exposing the PromptGuard to the platform."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._config = config or {}
        self.guard = self._build_guard()

    def _build_guard(self) -> PromptGuard:
        cfg = self._config or {}
        inj_cfg = cfg.get("injection", {}) or {}
        injection = PromptInjectionGuard(
            injection_threshold=float(inj_cfg.get("injection_threshold", 1.0)),
            jailbreak_threshold=float(inj_cfg.get("jailbreak_threshold", 1.0)),
            allowlist=inj_cfg.get("allowlist") or None,
        )
        audit = AuditLog(capacity=int(cfg.get("audit_capacity", 10000)))
        return PromptGuard(
            injection=injection,
            audit_log=audit,
            risk_threshold=float(cfg.get("risk_threshold", 2.0)),
        )

    async def initialize(self) -> None:
        self._status = HealthStatus.STARTING
        self.guard = self._build_guard()
        self._status = HealthStatus.HEALTHY
        logger.info("Prompt Guard Module initialized.")

    async def health_check(self) -> HealthStatus:
        return HealthStatus.HEALTHY

    async def shutdown(self) -> None:
        logger.info("Prompt Guard Module shutdown complete.")

    # Convenience passthroughs.
    def run(
        self, prompt: str, policy: Policy | None = None, role: str | None = None, **kw: Any
    ) -> GuardVerdict:
        return self.guard.run(prompt, policy, role, **kw)

    def audit(self) -> list[AuditEntry]:
        return self.guard.audit_log.entries()
