"""
ENI Enterprise — Tool Permission Gate + Execution Audit (Master-class sandbox).

A declarative, policy/schema-based virtual sandbox for the tool surface.  Instead
of shelling out to a subprocess jail (too risky / not offline-testable), this
module provides:

  * ``ToolPolicy``  — declarative per-tool permission rules: allow / deny / ask,
    plus argument constraints (regex allow / deny lists) so e.g. a BashTool that
    attempts ``rm -rf /`` can be *blocked* even though the tool itself is allowed.
  * ``ToolGate``    — the decision engine.  Before any tool executes it checks the
    policy:  ALLOW -> run, DENY -> blocked result, ASK -> pending-approval result.
    Every decision is written into the audit log (append-only) with outcome +
    duration, forming an immutable-ish hash chain.
  * ``ToolAudit``   — append-only audit log of every tool call (tool, args,
    allowed, outcome, duration_ms, caller) with ``recent()`` / ``search()`` and a
    SHA-256 hash-chain integrity check so tampering is detectable.

The gate is wired into ``ToolRegistry.invoke`` so every real tool call passes
through it and is recorded.  Pure stdlib, fully offline / unit-testable.

License: Proprietary — ENI AI OS
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

# ============================================================================
# Decisions
# ============================================================================


class Decision(StrEnum):
    """Permission decision for a tool invocation."""

    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"

    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.value


@dataclass
class GateResult:
    """Result of a gate evaluation / execution.

    Attributes:
        tool: Tool name that was evaluated.
        decision: ALLOW / DENY / ASK.
        allowed: True iff the call may proceed (decision == ALLOW).
        reason: Human-readable explanation for the decision.
        result: Payload returned by the underlying callable (when run & allowed).
        error: Exception message when the underlying callable failed.
        duration_ms: Wall-clock runtime of the underlying callable, if run.
        pending: True when the call requires human approval (ASK).
    """

    tool: str
    decision: Decision = Decision.ALLOW
    reason: str = ""
    allowed: bool = field(default=True, init=False)
    result: Any = None
    error: str = ""
    duration_ms: float = 0.0
    pending: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self.allowed = self.decision == Decision.ALLOW
        self.pending = self.decision == Decision.ASK


# ============================================================================
# Tool Policy
# ============================================================================


@dataclass
class ToolRule:
    """A single declarative permission rule.

    Attributes:
        tool: Tool name pattern ("BashTool", "*", "File*").  fnmatch semantics.
        level: ALLOW / DENY / ASK for matching tools.
        arg_allow: Optional list of regexes.  When present, the call is only
            permitted if the serialized arguments match *at least one* of them.
        arg_deny: Optional list of regexes.  When present, the call is blocked if
            *any* of them matches the serialized arguments (e.g. "rm -rf /").
        description: Free-text rationale / owner of the rule.
    """

    tool: str = "*"
    level: Decision = Decision.ALLOW
    arg_allow: list[str] | None = None
    arg_deny: list[str] | None = None
    description: str = ""

    def matches(self, tool_name: str) -> bool:
        return fnmatch.fnmatch(tool_name, self.tool)

    def specificity(self) -> int:
        """Higer = more specific rule (exact names beat '*')."""
        if self.tool == "*":
            return 0
        # count non-wildcard characters; longer literal matches are more specific
        literal = re.sub(r"[*?\[\]]", "", self.tool)
        return 100 + len(literal)

    def violates(self, args: dict[str, Any]) -> str | None:
        """Return a reason string if ``args`` violate this rule's constraints,
        else None.

        Patterns are tested against the JSON-serialized argument object AND
        against each individual string argument value (so anchored patterns like
        ``^cat\\s`` match the actual command text, not the surrounding braces).
        """
        if not (self.arg_deny or self.arg_allow):
            return None
        arg_text = _serialize_args(args)
        # union of serialized text + each string arg value
        haystacks = [arg_text]
        if isinstance(args, dict):
            for val in args.values():
                if isinstance(val, str):
                    haystacks.append(val)
                elif val is not None:
                    try:
                        haystacks.append(_serialize_args(val))
                    except Exception:  # noqa: BLE001
                        pass
        if self.arg_deny:
            for pattern in self.arg_deny:
                try:
                    rx = re.compile(pattern)
                except re.error:
                    continue
                for h in haystacks:
                    if rx.search(h):
                        return f"args match denied pattern: {pattern!r}"
        if self.arg_allow:
            for h in haystacks:
                for pattern in self.arg_allow:
                    try:
                        if re.search(pattern, h):
                            return None
                    except re.error:
                        continue
            return "args do not match any allow pattern"
        return None


def _serialize_args(args: dict[str, Any] | None) -> str:
    """Serialize args to a stable string used for regex constraint matching."""
    if not args:
        return ""
    try:
        return json.dumps(args, sort_keys=True, default=str, ensure_ascii=False)
    except Exception:
        return str(args)


class ToolPolicy:
    """Declarative per-tool permission policy with argument constraints.

    Resolution semantics:
      1. The most-specific matching rule for a tool governs (exact names beat
         wildcards; deny beats allow at equal specificity for safety).
      2. If the governing rule declares arg constraints, they are enforced first:
         any arg_deny hit -> DENY; missing arg_allow -> DENY.
      3. Otherwise the rule's level is the decision.
      4. If no rule matches, the default level applies.
    """

    def __init__(
        self,
        default: Decision = Decision.ALLOW,
        rules: Iterable[ToolRule] | None = None,
        name: str = "default",
    ) -> None:
        self.default = default
        self.name = name
        self._rules: list[ToolRule] = list(rules or [])
        self._lock = threading.RLock()

    # -- builders ----------------------------------------------------------
    def rule(
        self,
        tool: str,
        level: Decision | str = Decision.ALLOW,
        arg_allow: list[str] | None = None,
        arg_deny: list[str] | None = None,
        description: str = "",
    ) -> ToolPolicy:
        lvl = _coerce_decision(level)
        with self._lock:
            self._rules.append(
                ToolRule(
                    tool=tool,
                    level=lvl,
                    arg_allow=arg_allow,
                    arg_deny=arg_deny,
                    description=description,
                )
            )
        return self

    def allow(
        self,
        tool: str = "*",
        arg_allow: list[str] | None = None,
        arg_deny: list[str] | None = None,
        description: str = "",
    ) -> ToolPolicy:
        return self.rule(tool, Decision.ALLOW, arg_allow, arg_deny, description)

    def deny(
        self,
        tool: str = "*",
        arg_allow: list[str] | None = None,
        arg_deny: list[str] | None = None,
        description: str = "",
    ) -> ToolPolicy:
        return self.rule(tool, Decision.DENY, arg_allow, arg_deny, description)

    def ask(
        self,
        tool: str = "*",
        arg_allow: list[str] | None = None,
        arg_deny: list[str] | None = None,
        description: str = "",
    ) -> ToolPolicy:
        return self.rule(tool, Decision.ASK, arg_allow, arg_deny, description)

    # -- matching ----------------------------------------------------------
    def governing_rule(self, tool_name: str) -> ToolRule | None:
        """Most-specific rule that matches ``tool_name`` (deny-biased tie-break)."""
        with self._lock:
            matched = [r for r in self._rules if r.matches(tool_name)]
            if not matched:
                return None
            best = max(matched, key=lambda r: r.specificity())
            # safety: at equal specificity deny wins — recompute with that bias
            best_spec = best.specificity()
            candidates = [r for r in matched if r.specificity() == best_spec]
            candidates.sort(key=lambda r: _deny_rank(r.level), reverse=True)
            return candidates[0]

    def decide(self, tool_name: str, args: dict[str, Any] | None = None) -> GateResult:
        """Evaluate the policy for a tool invocation -> a GateResult decision."""
        rule = self.governing_rule(tool_name)
        args = args or {}
        if rule is None:
            return GateResult(
                tool=tool_name,
                decision=self.default,
                reason=f"no rule -> default {self.default.value}",
            )
        # argument constraints take precedence
        violation = rule.violates(args)
        if violation is not None:
            detail = rule.description and f" ({rule.description})" or ""
            return GateResult(
                tool=tool_name,
                decision=Decision.DENY,
                reason=f"arg constraint blocked: {violation}{detail}",
            )
        return GateResult(
            tool=tool_name, decision=rule.level, reason=f"rule '{rule.tool}' -> {rule.level.value}"
        )

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "name": self.name,
                "default": self.default.value,
                "rules": [
                    {
                        "tool": r.tool,
                        "level": r.level.value,
                        "arg_allow": r.arg_allow,
                        "arg_deny": r.arg_deny,
                        "description": r.description,
                    }
                    for r in self._rules
                ],
            }

    # -- config ------------------------------------------------------------
    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> ToolPolicy:
        """Build a policy from a declarative config dict.

        Example::
            {
                "name": "sandbox",
                "default": "allow",
                "rules": [
                    {"tool": "BashTool", "level": "deny", "arg_deny": ["rm\\s+-rf\\s*/\\b"]},
                    {"tool": "FileWriteTool", "level": "ask"},
                ],
            }
        """
        cfg = cfg or {}
        default = _coerce_decision(cfg.get("default", "allow"))
        policy = cls(default=default, name=cfg.get("name", "configured"))
        for r in cfg.get("rules", []):
            tool = r.get("tool", "*")
            level = _coerce_decision(r.get("level", "allow"))
            policy.rule(
                tool,
                level,
                arg_allow=r.get("arg_allow"),
                arg_deny=r.get("arg_deny"),
                description=r.get("description", ""),
            )
        return policy


def _coerce_decision(value: Decision | str) -> Decision:
    if isinstance(value, Decision):
        return value
    return Decision(value)


def _deny_rank(level: Decision) -> int:
    """Higher = more restrictive (used for deny-biased tie-breaking)."""
    if level == Decision.DENY:
        return 3
    if level == Decision.ASK:
        return 2
    return 1


# ============================================================================
# Tool Audit
# ============================================================================


@dataclass
class AuditRecord:
    """A single audit-log entry in the hash chain.

    Attributes:
        seq: Monotonic sequence number.
        ts: ISO-8601 UTC timestamp of the call.
        tool: Tool name invoked.
        args: Arguments passed (serialized copy).
        allowed: Whether the gate permitted execution.
        decision: allow / deny / ask.
        outcome: 'success' | 'error' | 'blocked' | 'pending'.
        duration_ms: Wall-clock runtime (0 for non-executed calls).
        caller: Identity of the caller (user_id / session).
        reason: Gate reason string.
        error: Error message on failure.
        prev_hash: Hash of the previous record in the chain.
        digest: SHA-256 digest of this record (prev_hash + payload).
    """

    seq: int
    tool: str
    args: dict[str, Any]
    allowed: bool
    decision: str
    outcome: str
    duration_ms: float = 0.0
    caller: str = "anonymous"
    reason: str = ""
    error: str = ""
    prev_hash: str = ""
    digest: str = ""
    ts: str = field(default_factory=lambda: _now_iso())

    def payload(self) -> str:
        compact = {
            "seq": self.seq,
            "ts": self.ts,
            "tool": self.tool,
            "args": self.args,
            "allowed": self.allowed,
            "decision": self.decision,
            "outcome": self.outcome,
            "duration_ms": self.duration_ms,
            "caller": self.caller,
            "reason": self.reason,
            "error": self.error,
        }
        return json.dumps(compact, sort_keys=True, default=str)

    def compute_digest(self) -> str:
        return hashlib.sha256(f"{self.prev_hash}|{self.payload()}".encode()).hexdigest()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ToolAudit:
    """Append-only audit log with hash-chain integrity protection.

    Every record is chained to the previous via ``prev_hash``/``digest`` (SHA-256),
    so any post-hoc tampering with a prior record breaks the chain and is detected
    by ``verify_integrity()``.  Thread-safe; offline; stdlib only.
    """

    def __init__(self) -> None:
        self._records: list[AuditRecord] = []
        self._lock = threading.RLock()
        self._seq = 0

    # -- writing -----------------------------------------------------------
    def record(
        self,
        tool: str,
        args: dict[str, Any] | None = None,
        allowed: bool = True,
        decision: Decision | str = Decision.ALLOW,
        outcome: str = "success",
        duration_ms: float = 0.0,
        caller: str = "anonymous",
        reason: str = "",
        error: str = "",
    ) -> AuditRecord:
        with self._lock:
            prev_hash = self._records[-1].digest if self._records else ""
            self._seq += 1
            rec = AuditRecord(
                seq=self._seq,
                tool=tool,
                args=dict(args or {}),
                allowed=bool(allowed),
                decision=_coerce_decision(decision).value,
                outcome=outcome,
                duration_ms=float(duration_ms),
                caller=caller,
                reason=reason,
                error=error,
                prev_hash=prev_hash,
            )
            rec.digest = rec.compute_digest()
            self._records.append(rec)
            return rec

    # -- reading -----------------------------------------------------------
    def recent(self, n: int = 10) -> list[AuditRecord]:
        """Return the most recent ``n`` records (chronological order)."""
        with self._lock:
            return list(self._records[-n:])

    def search(self, **kwargs: Any) -> list[AuditRecord]:
        """Filter records by exact field equality; empty kwargs -> all.

        Supported fields: tool, allowed, decision, outcome, caller, seq.
        """
        with self._lock:
            result = self._records
            for key, val in kwargs.items():
                if key in ("tool", "decision", "outcome", "caller"):
                    result = [r for r in result if getattr(r, key) == val]
                elif key in ("allowed",):
                    result = [r for r in result if r.allowed == bool(val)]
                elif key == "seq":
                    result = [r for r in result if r.seq == int(val)]
                else:
                    msg = f"unsupported audit search field: {key}"
                    raise KeyError(msg)
            return list(result)

    def all(self) -> list[AuditRecord]:
        with self._lock:
            return list(self._records)

    def count(self) -> int:
        with self._lock:
            return len(self._records)

    # -- integrity ---------------------------------------------------------
    def verify_integrity(self) -> bool:
        """Recompute the hash chain end-to-end.  False if any record was tampered."""
        with self._lock:
            prev_hash = ""
            for rec in self._records:
                if rec.prev_hash != prev_hash:
                    return False
                if rec.compute_digest() != rec.digest:
                    return False
                prev_hash = rec.digest
            return True

    def to_dict(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "seq": r.seq,
                    "ts": r.ts,
                    "tool": r.tool,
                    "args": r.args,
                    "allowed": r.allowed,
                    "decision": r.decision,
                    "outcome": r.outcome,
                    "duration_ms": r.duration_ms,
                    "caller": r.caller,
                    "reason": r.reason,
                    "error": r.error,
                    "prev_hash": r.prev_hash,
                    "digest": r.digest,
                }
                for r in self._records
            ]


# ============================================================================
# Tool Gate
# ============================================================================


class ToolGate:
    """Policy enforcement + audit for the tool execution path.

    Usage (async wired into ToolRegistry.invoke)::

        policy = ToolPolicy().deny("BashTool", arg_deny=[r"rm\\s+-rf\\s*/\\b"])
        gate = ToolGate(policy)
        decision = gate.evaluate("BashTool", {"command": "rm -rf /"})  # DENY
        result = await gate.run("BashTool", {"command": "ls"}, lambda: _run(), caller="agent-7")
    """

    def __init__(
        self,
        policy: ToolPolicy | None = None,
        audit: ToolAudit | None = None,
    ) -> None:
        self.policy = policy or ToolPolicy()  # defaults to allow
        self.audit = audit or ToolAudit()

    # -- decision only (no execution) --------------------------------------
    def evaluate(
        self,
        tool: str,
        args: dict[str, Any] | None = None,
        caller: str = "anonymous",
    ) -> GateResult:
        """Return the gate decision for a tool call, without executing it."""
        res = self.policy.decide(tool, args)
        res.caller = caller  # type: ignore[attr-defined]  # not stored on result
        return res

    # -- execute through the gate (sync callable) --------------------------
    def run(
        self,
        tool: str,
        args: dict[str, Any] | None,
        fn: Callable[[], Any],
        caller: str = "anonymous",
    ) -> GateResult:
        """Evaluate policy, then run ``fn`` iff ALLOW; record every call in audit.

        DENY  -> blocked result (fn not called, audit outcome='blocked').
        ASK   -> pending result (fn not called, audit outcome='pending').
        ALLOW -> run fn, time it, audit outcome='success' / 'error'.
        """
        args = args or {}
        decision = self.policy.decide(tool, args)

        if decision.decision == Decision.DENY:
            self.audit.record(
                tool,
                args,
                allowed=False,
                decision=Decision.DENY,
                outcome="blocked",
                caller=caller,
                reason=decision.reason,
            )
            return decision

        if decision.decision == Decision.ASK:
            self.audit.record(
                tool,
                args,
                allowed=False,
                decision=Decision.ASK,
                outcome="pending",
                caller=caller,
                reason=decision.reason,
            )
            return decision

        start = time.perf_counter()
        try:
            result = fn()
            elapsed = (time.perf_counter() - start) * 1000.0
        except Exception as exc:  # noqa: BLE001 - record then re-raise
            elapsed = (time.perf_counter() - start) * 1000.0
            self.audit.record(
                tool,
                args,
                allowed=True,
                decision=Decision.ALLOW,
                outcome="error",
                duration_ms=elapsed,
                caller=caller,
                reason=decision.reason,
                error=str(exc),
            )
            raise
        self.audit.record(
            tool,
            args,
            allowed=True,
            decision=Decision.ALLOW,
            outcome="success",
            duration_ms=elapsed,
            caller=caller,
            reason=decision.reason,
        )
        decision.result = result
        decision.duration_ms = elapsed
        return decision

    # -- async execution through the gate ----------------------------------
    async def arun(
        self,
        tool: str,
        args: dict[str, Any] | None,
        afn: Callable[[], Any],
        caller: str = "anonymous",
    ):
        """Async variant of :meth:`run` (used by the synchronous promise below)."""
        return self.run(tool, args, afn, caller)

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> ToolGate:
        """Build a gate+audit from a {policy: {...}} config dict."""
        cfg = cfg or {}
        policy = ToolPolicy.from_config(cfg.get("policy", {}))
        return cls(policy=policy)
