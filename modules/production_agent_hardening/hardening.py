"""Production Agent Hardening — turn a demo AI agent into something that survives production.

Grounded in two real JE Van Clief transcripts pulled into the ENI Enterprise Platform:

  * "Two Engineers on Why Your Agent Demo Will Not Survive Production" (ezRtp6K6zwE)
    NLP Logix engineers on the gap between a working demo and a production agent:
    the demo runs once, on your machine, with your data; production must run
    continuously, on someone else's infrastructure, with unpredictable input.
    Their recurring theme is observability — "it helps you understand how things
    are running" — plus recognizing that "best" is company-specific and nothing
    can be shipped without guardrails around errors, retries, secrets and cost.

  * "Systems Thinking for People Who Build With AI" (NWyTsKTKka8)
    A systems lens on agentic AI: feedback loops, coupling, and emergent
    behavior. It cites an MIT Project Nanda finding that ~95% of agentic AI
    initiatives had zero real impact — the classic "demo did not survive into
    production" failure mode. The fix is to reason about the whole system
    (loops, coupling, and what happens when a component degrades) instead of
    only polishing the happy-path ability of a single agent.

This module makes those lessons concrete as a *hardening linter*: it scores an
agent specification across the production-readiness dimensions the transcripts
care about, returns findings + criticals, and adds a systems-thinking analysis
of feedback loops and coupling. Pure, deterministic, dependency-free logic so
it is fully unit-testable with no network.

Hardening dimensions (score 0..100 across weighted checks):
  * error_handling   — code tolerates exceptions, has explicit fallbacks
  * retries          — transient failures retried with backoff, not one-shot
  * observability    — logging/tracing/metrics so you can see how it's running
  * secrets          — no secrets in code/prompts; injected, redacted
  * cost_bounds      — explicit max tokens/calls/latency budget
  * graceful_failure — demo fails loudly into a safe degradable state
  * deterministic    — reproducible output (schema, temperature/seed control)
  * demo_trap        — no demo shortcuts (canned outputs, hardcoded answers,
                       prompt-only "instructions", single happy-path)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

__version__ = "1.0.0"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Severity levels for findings.
CRITICAL = "critical"
WARNING = "warning"
PASS = "pass"

# Default weights across the eight hardening dimensions (sum to 100).
DEFAULT_WEIGHTS: Dict[str, int] = {
    "error_handling": 15,
    "retries": 10,
    "observability": 20,
    "secrets": 15,
    "cost_bounds": 10,
    "graceful_failure": 10,
    "deterministic": 10,
    "demo_trap": 10,
}

# A demo-trap is any of these landmark signatures that appear in a demo-only spec.
DEMO_TRAP_SIGNATURES: Tuple[str, ...] = (
    "canned_response",
    "hardcoded_output",
    "hardcoded_answer",
    "mock_reply",
    "pretend",
    "just_print",
    "demo_only",
    "sample_data_only",
)


@dataclass
class Finding:
    """A single hardening finding for one dimension."""

    dimension: str
    severity: str  # critical | warning | pass
    message: str
    detail: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dimension": self.dimension,
            "severity": self.severity,
            "message": self.message,
            "detail": self.detail,
        }


@dataclass
class HardeningReport:
    """Result of hardening an agent spec."""

    score: float  # 0..100
    findings: List[Finding] = field(default_factory=list)
    criticals: List[Finding] = field(default_factory=list)
    passed: int = 0
    warnings: int = 0
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": round(self.score, 1),
            "passed": self.passed,
            "warnings": self.warnings,
            "criticals": len(self.criticals),
            "findings": [f.to_dict() for f in self.findings],
            "criticals_list": [f.to_dict() for f in self.criticals],
            "summary": self.summary,
        }


# ---------------------------------------------------------------------------
# Dimension check helpers (each inspects a slice of the spec dict)
# ---------------------------------------------------------------------------


def _truthy(value: Any) -> bool:
    """Coerce a spec field to a boolean without raising on odd types."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() not in ("", "false", "no", "0", "none")
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return bool(value)


def _check_error_handling(spec: Dict[str, Any], findings: List[Finding]) -> None:
    node = spec.get("error_handling", {})
    if isinstance(node, bool):
        node = {"enabled": node}
    enabled = _truthy(node.get("enabled", node.get("strategy")))
    fallback = _truthy(node.get("fallback", node.get("fallback_behavior")))
    if enabled and fallback:
        findings.append(Finding("error_handling", PASS,
                                "errors are caught and have an explicit fallback path."))
    elif enabled:
        findings.append(Finding("error_handling", WARNING,
                                "errors are caught but there is no explicit fallback behavior "
                                "when the model/tool fails."))
    else:
        findings.append(Finding("error_handling", CRITICAL,
                                "no error handling in spec — an exception will crash the whole run "
                                "in production (transcript: demos run once on your machine; "
                                "production must absorb unpredictable failures)."))


def _check_retries(spec: Dict[str, Any], findings: List[Finding]) -> None:
    ret = spec.get("retries", {})
    if isinstance(ret, bool):
        ret = {"enabled": ret}
    max_retries = ret.get("max_retries", ret.get("retries"))
    policy = str(ret.get("policy", ret.get("backoff", ""))).lower()
    if max_retries is not None and int(max_retries) > 0:
        if "exponential" in policy or "backoff" in policy or "jitter" in policy:
            findings.append(Finding("retries", PASS,
                                    f"transient failures retried ({max_retries}x) with "
                                    f"backoff policy '{policy}'."))
        else:
            findings.append(Finding("retries", WARNING,
                                    f"retries configured ({max_retries}x) but no backoff policy — "
                                    "retrying immediately can hammer a rate-limited API."))
    else:
        findings.append(Finding("retries", CRITICAL,
                                "no retry policy — a single transient network/API error fails the "
                                "whole agent. Production needs retries with backoff."))


def _check_observability(spec: Dict[str, Any], findings: List[Finding]) -> None:
    obs = spec.get("observability", {})
    if isinstance(obs, bool):
        obs = {"logging": obs, "tracing": False, "metrics": False}
    logging_ = _truthy(obs.get("logging", obs.get("log")))
    tracing = _truthy(obs.get("tracing"))
    metrics = _truthy(obs.get("metrics", obs.get("monitoring")))
    covered = [k for k, v in (("logging", logging_), ("tracing", tracing),
                              ("metrics", metrics)) if v]
    if len(covered) >= 2:
        findings.append(Finding("observability", PASS,
                                "production observability present: " + ", ".join(covered) + "."))
    elif len(covered) == 1:
        findings.append(Finding("observability", WARNING,
                                f"only {covered[0]} is enabled — you cannot fully 'understand how "
                                "things are running' (transcript theme) without traces/metrics."))
    else:
        findings.append(Finding("observability", CRITICAL,
                                "no logging/tracing/metrics — producers cannot see why an agent "
                                "misbehaves. The transcript's core rule: production requires "
                                "knowing 'how things are running'."))


def _check_secrets(spec: Dict[str, Any], findings: List[Finding]) -> None:
    sec = spec.get("secrets", spec.get("security", {}))
    if isinstance(sec, bool):
        sec = {"hardcoded": not sec}
    hardcoded = _truthy(sec.get("hardcoded", sec.get("in_code")))
    injection = str(sec.get("injection", sec.get("source", ""))).lower()
    if hardcoded:
        findings.append(Finding("secrets", CRITICAL,
                                "secrets are hardcoded in the spec/code — a demo leak becomes a "
                                "production breach the moment it's shared."))
    elif injection and injection not in ("none", ""):
        findings.append(Finding("secrets", PASS,
                                f"no hardcoded secrets; injected via '{injection}'."))
    else:
        findings.append(Finding("secrets", WARNING,
                                "no hardcoded secrets visible, but no injection source is declared — "
                                "state explicitly where keys/lookups live."))


def _check_cost_bounds(spec: Dict[str, Any], findings: List[Finding]) -> None:
    cost = spec.get("cost_bounds", spec.get("cost", {}))
    if isinstance(cost, bool):
        cost = {"enabled": cost}
    max_tokens = cost.get("max_tokens")
    max_calls = cost.get("max_calls")
    budget = cost.get("budget")
    bounded = any(v is not None for v in (max_tokens, max_calls, budget))
    if bounded:
        tokens = f"{max_tokens} tokens" if max_tokens is not None else "unbounded tokens"
        calls = f"{max_calls} calls" if max_calls is not None else "unbounded calls"
        findings.append(Finding("cost_bounds", PASS,
                                f"explicit cost floor/ceiling present: {tokens}, {calls}."))
    else:
        findings.append(Finding("cost_bounds", WARNING,
                                "no cost bounds — an uncontrolled agent loop can burn unbounded "
                                "tokens/calls against production APIs and models."))


def _check_graceful_failure(spec: Dict[str, Any], findings: List[Finding]) -> None:
    gf = spec.get("graceful_failure", spec.get("degradation", {}))
    if isinstance(gf, bool):
        gf = {"enabled": gf}
    enabled = _truthy(gf.get("enabled", gf.get("degrade")))
    mode = str(gf.get("mode", gf.get("behavior", ""))).lower()
    if enabled:
        findings.append(Finding("graceful_failure", PASS,
                                "agent degrades safely on failure" +
                                (f" (mode: {mode})" if mode else "") + "."))
    else:
        findings.append(Finding("graceful_failure", CRITICAL,
                                "no graceful failure/degradation — when a dependency is down the "
                                "agent must degrade predictably instead of returning garbage or erroring hard."))


def _check_deterministic(spec: Dict[str, Any], findings: List[Finding]) -> None:
    det = spec.get("deterministic", spec.get("output_control", {}))
    if isinstance(det, bool):
        det = {"enabled": det}
    schema = _truthy(det.get("schema", det.get("structured")))
    temp = det.get("temperature")
    temp_controlled = isinstance(temp, (int, float)) and 0.0 <= temp < 1.0
    enabled = _truthy(det.get("enabled"))
    if schema and (temp_controlled or enabled):
        findings.append(Finding("deterministic", PASS,
                                "outputs are schema-constrained and reproducibility is controlled "
                                f"(temperature={temp})."))
    elif schema:
        findings.append(Finding("deterministic", WARNING,
                                "structured output schema present but no temperature/seed control — "
                                "outputs may still vary run to run."))
    else:
        findings.append(Finding("deterministic", WARNING,
                                "no structured-output schema or determinism control — consumers can't "
                                "rely on a stable shape from the agent."))


def _check_demo_trap(spec: Dict[str, Any], findings: List[Finding]) -> None:
    """Look for demo-only shortcuts that get 'fixed' by hardcoding in a demo."""
    trap_node = spec.get("demo_trap", spec.get("demo", {}))
    if isinstance(trap_node, bool):
        trap_node = {"canned_responses": not trap_node, "hardcoded_outputs": not trap_node}
    canned = _truthy(trap_node.get("canned_responses", trap_node.get("canned")))
    hardcoded_out = _truthy(trap_node.get("hardcoded_outputs", trap_node.get("hardcoded_output")))
    # Also scan the whole spec text for landmark demo-only signatures.
    blob = str(spec).lower()
    signatures = [s for s in DEMO_TRAP_SIGNATURES if s in blob]
    if canned or hardcoded_out:
        findings.append(Finding("demo_trap", CRITICAL,
                                "spec still uses canned/hardcoded responses — the exact 'demo trap' "
                                "the transcript warns about; it won't generalize to real input."))
    elif signatures:
        findings.append(Finding("demo_trap", WARNING,
                                "possible demo-trap signatures found: "
                                + ", ".join(signatures) + "."))
    else:
        findings.append(Finding("demo_trap", PASS,
                                "no canned responses or hardcoded outputs; generalizes beyond the demo happy-path."))


# dispatch table: dimension -> checker
_CHECKERS = {
    "error_handling": _check_error_handling,
    "retries": _check_retries,
    "observability": _check_observability,
    "secrets": _check_secrets,
    "cost_bounds": _check_cost_bounds,
    "graceful_failure": _check_graceful_failure,
    "deterministic": _check_deterministic,
    "demo_trap": _check_demo_trap,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def harden_spec(spec: Dict[str, Any],
                weights: Optional[Dict[str, int]] = None,
                fail_on: Optional[List[str]] = None) -> HardeningReport:
    """Lint an agent spec across production-hardening dimensions.

    Args:
        spec: dict describing an agent's production posture. Any subset of the
              eight dimension keys may be present; missing/empty dims score 0.
        weights: optional per-dimension weights (defaults sum to 100).
        fail_on: optional list of dimensions that must not be critical.

    Returns:
        A HardeningReport with a 0..100 score, per-dimension findings, and the
        list of critical blockers.
    """
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update(weights)
    findings: List[Finding] = []
    for dim, checker in _CHECKERS.items():
        checker(spec, findings)

    criticals = [f for f in findings if f.severity == CRITICAL]
    crit_dims = {f.dimension for f in criticals}
    pass_findings = [f for f in findings if f.severity == PASS]

    # Score: each dimension contributes its weight if it passed; half if it's a
    # warning (>= 2 of its sub-criteria solid); zero on critical/missing.
    passed_weight = 0
    warn_weight = 0
    for f in findings:
        if f.severity == PASS:
            passed_weight += w.get(f.dimension, 0)
        elif f.severity == WARNING:
            warn_weight += w.get(f.dimension, 0) * 0.5
    score = (passed_weight + warn_weight)

    passed = len(pass_findings)
    warnings = sum(1 for f in findings if f.severity == WARNING)

    if fail_on and crit_dims & set(fail_on):
        summary = ("NOT production-ready: critical blockers in "
                   + ", ".join(sorted(crit_dims & set(fail_on))) + ".")
    elif not criticals:
        summary = ("Production-ready posture: all hardening dimensions satisfied "
                   f"(score {score:.0f}/100).")
    elif score >= 50:
        summary = ("Progressing, but not shippable: "
                   + ", ".join(sorted(crit_dims)) + " are critical blockers.")
    else:
        summary = "Demo-grade: multiple dimensions missing. Fix the blockers before production."

    report = HardeningReport(
        score=score, findings=findings, criticals=criticals,
        passed=passed, warnings=warnings, summary=summary,
    )
    return report


def run_readiness_check(spec: Dict[str, Any],
                        min_score: float = 70.0,
                        required: Optional[List[str]] = None) -> Dict[str, Any]:
    """Gate an agent for production against a minimum score and required dims.

    Returns a dict suitable for a CI/board gate:
        {ready, score, critical_blocks, required_missing, report}
    """
    if required is None:
        required = ["secrets", "error_handling", "observability"]
    report = harden_spec(spec)
    critical_blocks = [f.dimension for f in report.criticals]
    required_missing = [d for d in required if d in critical_blocks]
    ready = (report.score >= min_score) and not required_missing
    return {
        "ready": ready,
        "score": report.score,
        "critical_blocks": critical_blocks,
        "required_missing": required_missing,
        "report": report.to_dict(),
    }


def systems_feedback_loop(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Systems-thinking lens (NWyTsKTKka8): feedback loops + coupling analysis.

    Accepts an optional 'components' adjacency map in the spec:
        spec["components"] = {"A": ["B", "C"], "B": ["A"], ...}
    and detects:
      * feedback loops   — closed cycles (A→B→A) that can amplify drift or
                           runaway cost unless bounded.
      * coupling         — how interconnected the graph is; high coupling means
                           one failing node drags everything down.
    If no explicit graph is given, it synthesizes one from the presence of the
    hardening dimensions and reports single-node (no-loop) findings.
    """
    graph = spec.get("components")
    noop_finding = "no component graph provided; add spec['components'] to analyze loops/coupling."

    if not isinstance(graph, dict) or not graph:
        return {
            "feedback_loops": [],
            "loop_count": 0,
            "coupling": 0.0,
            "max_depth": 0,
            "note": noop_finding,
            "systems_verdict": "System not modeled — cannot reason about emergent behavior.",
        }

    def _cycle(path: List[str], node: str) -> List[str]:
        """Return the closed cycle path[node:] + [node] (node is already in path)."""
        i = path.index(node)
        return path[i:] + [node]

    edges = 0
    node_set = set(graph.keys())
    for neighbors in graph.values():
        for n in neighbors:
            if isinstance(n, str):
                edges += 1
                node_set.add(n)

    # Detect cycles with DFS.
    loops: List[List[str]] = []
    visited: set = set()
    path: List[str] = []

    def dfs(node: str) -> None:
        if node in path:
            cyc = _cycle(path, node)
            if cyc not in loops:
                loops.append(cyc)
            return
        if node in visited:
            return
        visited.add(node)
        path.append(node)
        for nxt in graph.get(node, []):
            if isinstance(nxt, str):
                dfs(nxt)
        path.pop()

    for start in graph:
        dfs(start)

    nodes = len(node_set)
    # Coupling = mean degree (in+out) normalized; ~1.0 means tightly coupled.
    degree = edges / max(1, nodes)
    coupling = min(degree / max(1, nodes - 1), 1.0) if nodes > 1 else 0.0

    if loops:
        verdict = ("Detected {} feedback loop(s). Loops can amplify drift/runaway cost "
                   "unless bounded — add rate/cost/budget limits on each closed cycle."
                   ).format(len(loops))
    elif coupling > 0.5:
        verdict = ("No closed feedback loops, but coupling is high ({:.2f}) — a single "
                   "degrading component can cascade across the system."
                   ).format(coupling)
    else:
        verdict = "Graph is acyclic and loosely coupled — lower emergent-behavior risk."

    return {
        "feedback_loops": loops,
        "loop_count": len(loops),
        "coupling": round(coupling, 2),
        "edge_count": edges,
        "node_count": nodes,
        "systems_verdict": verdict,
    }


# Final __all__ (clean, no placeholders)
__all__ = [
    "CRITICAL", "WARNING", "PASS",
    "DEFAULT_WEIGHTS", "DEMO_TRAP_SIGNATURES",
    "Finding", "HardeningReport",
    "harden_spec", "run_readiness_check", "systems_feedback_loop",
    "__version__",
]
