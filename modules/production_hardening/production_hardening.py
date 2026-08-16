"""Production Hardening — production-readiness assessment for ML / agent systems.

Pure, stdlib-only, network-free logic engine, grounded in the real pulled
transcript `data/transcripts/JEVanClief/ezRtp6K6zwE.md` — "Two Engineers on
Why Your Agent Demo Will Not Survive Production" (a 57-min NLP Logix interview
with Anton Corner and Ryan Nent).  Thesis: a demo and a sustained production
system live under different constraints — the invisible 80% (governance,
monitoring, runtime, databases, monitoring tooling) is what makes a system
operate reliably:

    "you have 80% of the work ... it's governance, it's monitoring, it's
     your runtime, it's your databases behind the scene."

Every category and rule carries a real `transcript_ref`.  Public surface:
ReadinessRule/RuleResult/CategoryResult/ReadinessReport, CATEGORIES,
default_rules(), assess()/assess_answers(), and deterministic run-assurance
helpers: check_deterministic_output, detect_drift, circuit_breaker_state,
retry_plan, human_escalation_required.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Sequence


# =============================================================================
# Outcome enums
# =============================================================================

class CheckOutcome(Enum):
    """A single check's verdict.  PASS/WARN/FAIL map to 1.0/0.5/0.0."""
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"

    @property
    def score(self) -> float:
        return {"PASS": 1.0, "WARN": 0.5, "FAIL": 0.0}[self.value]


class RiskLevel(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @property
    def weight(self) -> float:
        return {"LOW": 1.0, "MEDIUM": 2.0, "HIGH": 4.0, "CRITICAL": 8.0}[self.value]


# =============================================================================
# Data model
# =============================================================================

@dataclass(frozen=True)
class ReadinessRule:
    """A single grounded production-readiness rule.

    `key` is the name used in the questionnaire answers (a `SystemProfile`
    or plain dict).  `evaluate(answer)` maps the answer to PASS/WARN/FAIL.
    """
    id: str
    category: str
    title: str
    description: str
    transcript_ref: str          # grounded quote / paraphrase from the episode
    risk: RiskLevel
    weight: float = 1.0
    # Optional explicit map; if given, the answer is looked up directly.
    verdict_map: Optional[Mapping[Any, CheckOutcome]] = None
    # Otherwise: `threshold` = PASS threshold for numeric/bool (bool True => 1.0).
    threshold: float = 0.5
    warn_threshold: float = 0.25  # [warn_threshold, threshold) is a WARN band
    lower_is_better: bool = False

    def evaluate(self, answer: Any) -> CheckOutcome:
        """Turn a single questionnaire answer into a verdict (deterministic)."""
        if self.verdict_map is not None:
            return self.verdict_map.get(answer, CheckOutcome.WARN)
        # Normalise bool / numeric answers to a 0..1 scale.
        if isinstance(answer, bool):
            numeric = 1.0 if answer else 0.0
        elif isinstance(answer, (int, float)):
            numeric = float(answer)
        else:
            numeric = 1.0 if answer is not None else 0.0
        if self.lower_is_better:
            numeric = 1.0 - numeric
        if numeric >= self.threshold:
            return CheckOutcome.PASS
        if numeric >= self.warn_threshold:
            return CheckOutcome.WARN
        return CheckOutcome.FAIL


@dataclass(frozen=True)
class RuleResult:
    rule: ReadinessRule
    answer: Any
    outcome: CheckOutcome
    raw_score: float

    @property
    def weighted_score(self) -> float:
        return self.raw_score * self.rule.weight * self.rule.risk.weight


@dataclass
class CategoryResult:
    """Aggregated result for one readiness category."""
    name: str
    title: str
    summary: str
    transcript_ref: str
    rules: List[RuleResult] = field(default_factory=list)

    @property
    def outcome(self) -> CheckOutcome:
        if not self.rules:
            return CheckOutcome.WARN
        raw = sum(r.raw_score for r in self.rules) / len(self.rules)
        if raw >= 0.75:
            return CheckOutcome.PASS
        if raw >= 0.5:
            return CheckOutcome.WARN
        return CheckOutcome.FAIL

    @property
    def score(self) -> float:
        if not self.rules:
            return 0.0
        return sum(r.raw_score for r in self.rules) / len(self.rules)

    @property
    def weighted_score(self) -> float:
        if not self.rules:
            return 0.0
        num = sum(r.weighted_score for r in self.rules)
        den = sum(r.rule.weight * r.rule.risk.weight for r in self.rules)
        return num / den if den else 0.0


@dataclass
class ReadinessReport:
    """Structured production-readiness report for one system."""
    system_name: str
    overall_score: float          # weighted 0..1
    gate_verdict: str             # "APPROVED" | "REVIEW" | "BLOCKED"
    production_ready: bool
    categories: List[CategoryResult] = field(default_factory=list)
    summary: str = ""
    top_risks: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "system_name": self.system_name,
            "overall_score": round(self.overall_score, 3),
            "gate_verdict": self.gate_verdict,
            "production_ready": self.production_ready,
            "summary": self.summary,
            "categories": [
                {
                    "name": c.name,
                    "title": c.title,
                    "outcome": c.outcome.value,
                    "score": round(c.score, 3),
                    "weighted_score": round(c.weighted_score, 3),
                    "rules": [
                        {
                            "id": r.rule.id,
                            "title": r.rule.title,
                            "outcome": r.outcome.value,
                            "score": r.raw_score,
                        }
                        for r in c.rules
                    ],
                }
                for c in self.categories
            ],
            "top_risks": self.top_risks,
            "recommendations": self.recommendations,
        }

    def markdown(self) -> str:
        """Human-readable report (useful for dashboards / status boards)."""
        lines = [
            f"# Production Readiness Report — {self.system_name}",
            f"Overall score: {self.overall_score:.2f}  "
            f"Verdict: {self.gate_verdict}  Ready: {self.production_ready}",
            self.summary,
            "",
            "## Category results",
        ]
        for c in self.categories:
            lines.append(f"- [{c.outcome.value:4}] {c.name} ({c.score:.2f}) "
                         f"— {c.title}")
            for r in c.rules:
                lines.append(f"    - [{r.outcome.value:4}] {r.rule.title} "
                             f"({r.raw_score:.2f})")
        if self.top_risks:
            lines.append("")
            lines.append("## Top risks")
            for risk in self.top_risks:
                lines.append(f"- {risk}")
        if self.recommendations:
            lines.append("")
            lines.append("## Recommendations")
            for rec in self.recommendations:
                lines.append(f"- {rec}")
        return "\n".join(lines)


# =============================================================================
# System profile (questionnaire answers)
# =============================================================================

@dataclass
class SystemProfile:
    """The answers to the readiness questionnaire.

    `answers` maps each rule key to a bool, numeric 0..1, or discrete value
    (see `verdict_map` on the corresponding rule).
    """
    name: str
    answers: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.answers.get(key, default)


# =============================================================================
# The grounded readiness checklist
# =============================================================================
# Every rule is mapped to a specific point the NLP Logix engineers made.

CATEGORIES: Dict[str, dict] = {
    "determinism": {
        "title": "Determinism & Confidence",
        "summary": "LLMs have no confidence score and are not deterministic.",
        "transcript_ref": "lines ~342-354 — \"the biggest constraint ... they "
                          "have no confidence score and they're not "
                          "deterministic ... would they do million times the "
                          "same thing the same way?\"",
    },
    "observability": {
        "title": "Observability, Monitoring & Runtime",
        "summary": "The invisible 80% — governance, monitoring, runtime, "
                   "databases, monitoring tooling.",
        "transcript_ref": "lines ~795-805 — \"80% of the work ... it's "
                          "governance, it's monitoring, it's your runtime, "
                          "it's your databases behind the scene, it's your "
                          "monitoring tools.\"",
    },
    "human_oversight": {
        "title": "Security, Governance & Human Oversight",
        "summary": "Who has access to the agent, what it can touch, guard "
                   "rails and escalation.",
        "transcript_ref": "lines ~920-938 — \"nobody cares what agent has "
                          "access to, who has access to the agent, which "
                          "tools available ... validation loops, guard "
                          "rails ... risk management.\"",
    },
    "resilience": {
        "title": "Brittle Chains & Failure Handling",
        "summary": "Build deterministic fallback code where the model fails.",
        "transcript_ref": "lines ~550-553 — \"wherever the model falls short "
                          "or is failing, that's when you build that "
                          "deterministic code.\"",
    },
    "evaluation": {
        "title": "Evaluation & Right-Sizing",
        "summary": "Is an agent even the answer? Validate small deterministic "
                   "processes instead of over-engineering.",
        "transcript_ref": "lines ~660-674 — \"when you have small processes "
                          "that are more deterministic it's very easy ... is "
                          "an agent going to be the answer or is it just "
                          "going to be a little bit overkill?\"",
    },
    "scaling": {
        "title": "Scaling & Resource Limits",
        "summary": "Scalability to actual production tends to get fuzzy; a "
                   "monolith demo won't handle real load.",
        "transcript_ref": "lines ~493-495 & ~385-388 — \"when you talk about "
                          "scalability to actual production it tends to get "
                          "a little bit fuzzy ... not scalable.\"",
    },
    "sustainability": {
        "title": "Sustained Run vs One-Off Demo",
        "summary": "Don't be over-enthusiastic about shipping demos to "
                   "production; find the conservative middle ground.",
        "transcript_ref": "lines ~1301-1308 — \"you should not be so over "
                          "enthusiastic to go in production ... find this "
                          "middle ground be conservative on your "
                          "principles.\"",
    },
}


def _rule(rid, cat, title, desc, ref, risk, **kw):
    return ReadinessRule(
        id=rid, category=cat, title=title, description=desc,
        transcript_ref=ref, risk=risk, **kw,
    )


def default_rules() -> List[ReadinessRule]:
    """The grounded readiness checklist (deterministic, ordered by category)."""
    rules = [
        # ---- determinism ----
        _rule("determinism.no_confidence", "determinism",
              "Confidence score available", "System exposes a calibrated "
              "confidence/uncertainty estimate per decision instead of "
              "treating every LLM answer as equally trustworthy.",
              "LLMs have no confidence score and are not deterministic",
              RiskLevel.CRITICAL, threshold=0.5),
        _rule("determinism.repeatable", "determinism",
              "Repeatable under fixed inputs",
              "Same input converges to the same decision in a sustained run "
              "(temperature/seed policy, golden path re-checks).",
              "would they do million times the same thing the same way? "
              "Probably not.", RiskLevel.HIGH, threshold=0.5),
        _rule("determinism.unknown_unknowns", "determinism",
              "Unknown-unknowns acknowledged",
              "Team accepts that agent behaviour has no universal definition "
              "and treats unanticipated states as expected risk.",
              "everybody has their own angle on what agent should do ... it "
              "has no standard definition (NIST).", RiskLevel.MEDIUM,
              threshold=0.5),

        # ---- observability ----
        _rule("observability.logging", "observability",
              "Structured logging & runtime visibility",
              "The invisible 80% — runtime, databases, logs — is instrumented "
              "so failures become visible.",
              "it's governance, it's monitoring, it's your runtime, it's "
              "your databases behind the scene.", RiskLevel.CRITICAL,
              threshold=0.5),
        _rule("observability.metrics", "observability",
              "Monitoring tooling & alerting",
              "Monitoring tools exist, are monitored the same way across "
              "solutions, and can react proactively.",
              "that's how you will monitor the solution that's how you will "
              "proactively react on something if happens.",
              RiskLevel.HIGH, threshold=0.5),
        _rule("observability.traceability", "observability",
              "Auditable decision trace",
              "Every agent decision can be traced back to the model, tools "
              "and data that produced it.",
              "nobody cares what agent has access to ... all this validation "
              "loops, guard rails.", RiskLevel.MEDIUM, threshold=0.5),

        # ---- human oversight ----
        _rule("human_oversight.access_control", "human_oversight",
              "Access control & least privilege",
              "Who has access to the agent and which tools it may touch are "
              "explicitly controlled.",
              "nobody cares what agent has access to, who has access to the "
              "agent, which tools available.", RiskLevel.CRITICAL,
              threshold=0.5),
        _rule("human_oversight.guardrails", "human_oversight",
              "Guard rails & validation loops",
              "Validation loops and guard rails are configured for the "
              "business's risk profile.",
              "all this validation loops, guard rails, it's a ton of stuff "
              "which needs to be configured.", RiskLevel.HIGH, threshold=0.5),
        _rule("human_oversight.escalation", "human_oversight",
              "Human escalation path",
              "There is a defined route to escalate low-confidence / "
              "high-impact actions to a human before acting.",
              "human would not either [do the same thing a million times].",
              RiskLevel.CRITICAL, threshold=0.5),

        # ---- resilience ----
        _rule("resilience.deterministic_fallback", "resilience",
              "Deterministic fallback path",
              "Where the model falls short or is failing, deterministic code "
              "carries the task.",
              "wherever the model falls short or is failing, that's when you "
              "build that deterministic code.", RiskLevel.HIGH, threshold=0.5),
        _rule("resilience.circuit_breaker", "resilience",
              "Circuit breaker on failure",
              "Repeated failures trip a breaker instead of letting a brittle "
              "chain cascade.",
              "this app ... now it breaks every 20 minutes.", RiskLevel.HIGH,
              threshold=0.5),
        _rule("resilience.retry_policy", "resilience",
              "Retry with backoff",
              "Transient failures are retried with backoff, not re-run "
              "blindly at full rate.",
              "it breaks every 20 minutes ... skip all this hub-up.",
              RiskLevel.MEDIUM, threshold=0.5),

        # ---- evaluation ----
        _rule("evaluation.right_sizing", "evaluation",
              "Agent right-sized (not overkill)",
              "Small deterministic processes are used where an agent is "
              "overkill.",
              "is an agent going to be the answer or is it just going to be "
              "a little bit overkill?", RiskLevel.MEDIUM, threshold=0.5),
        _rule("evaluation.test_suite", "evaluation",
              "Validation / test loop",
              "There is an evaluation loop that re-checks the agent before "
              "and after changes.",
              "validation loops, guard rails, it's a ton of stuff which "
              "needs to be configured.", RiskLevel.HIGH, threshold=0.5),
        _rule("evaluation.risk_register", "evaluation",
              "Risk management register",
              "The business's specific risk-management position is recorded "
              "and applied.",
              "best practice in your specific domain business ... what's "
              "your risk management.", RiskLevel.MEDIUM, threshold=0.5),

        # ---- scaling ----
        _rule("scaling.load_model", "scaling",
              "Load model for sustained traffic",
              "A sustained-run load model exists instead of a single-demo "
              "path.",
              "when you talk about scalability to actual production it tends "
              "to get a little bit fuzzy.", RiskLevel.HIGH, threshold=0.5),
        _rule("scaling.burst_capacity", "scaling",
              "Burst / concurrency capacity",
              "System handles concurrent users at scale.",
              "million the same sequence requests ... your monolith "
              "generated solution would never support this because it's not "
              "scalable.", RiskLevel.HIGH, threshold=0.5),
        _rule("scaling.local_resources", "scaling",
              "Local resource limits surfaced",
              "Local dev resource constraints are tracked and do not hide "
              "production cost/latency surprises.",
              "it may not be completely perfect because the [build] ... "
              "running on a local machine.", RiskLevel.MEDIUM, threshold=0.5),

        # ---- sustainability ----
        _rule("sustainability.no_demo_credit", "sustainability",
              "No demo-credit at the gate",
              "Production approval does not assume the demo 'worked'; it "
              "checks sustained constraints.",
              "Why Your Agent Demo Will Not Survive Production.",
              RiskLevel.HIGH, threshold=0.5),
        _rule("sustainability.conservative_gate", "sustainability",
              "Conservative adoption plan",
              "A staged adoption plan with a conservative middle ground "
              "between 'never' and 'ship everything now'.",
              "you should not be so over enthusiastic to go in production "
              "and just take everything ... find this middle ground.",
              RiskLevel.HIGH, threshold=0.5),
        _rule("sustainability.change_control", "sustainability",
              "Model/stack change control",
              "Model updates are a swap that doesn't silently break the "
              "workflow; the workflow is the stable contract.",
              "I don't really care when the models update because I figured "
              "out what workflow works with the models.",
              RiskLevel.MEDIUM, threshold=0.5),
    ]
    return rules


# =============================================================================
# Scoring
# =============================================================================

def _gate_verdict(score: float) -> str:
    if score >= 0.75:
        return "APPROVED"
    if score >= 0.5:
        return "REVIEW"
    return "BLOCKED"


def _top_risks(report_rules: Sequence[RuleResult], limit: int = 5) -> List[str]:
    failed = [r for r in report_rules if r.outcome is CheckOutcome.FAIL]
    failed.sort(key=lambda r: r.rule.risk.weight, reverse=True)
    return [
        f"[{r.rule.risk.value}] {r.rule.category}.{r.rule.id}: {r.rule.title}"
        for r in failed[:limit]
    ]


def _recommendations(report_rules: Sequence[RuleResult]) -> List[str]:
    recs = []
    for r in report_rules:
        if r.outcome is CheckOutcome.FAIL:
            recs.append(f"{r.rule.title} ({r.rule.category}): "
                        f"{r.rule.description}")
        elif r.outcome is CheckOutcome.WARN:
            recs.append(f"Review: {r.rule.title} ({r.rule.category})")
    return recs


def assess(system: SystemProfile, rules: Optional[Sequence[ReadinessRule]] = None,
           ) -> ReadinessReport:
    """Score a `SystemProfile` against the grounded checklist."""
    rules = list(rules) if rules is not None else default_rules()

    category_order = list(CATEGORIES)
    by_category: Dict[str, List[RuleResult]] = {c: [] for c in category_order}
    all_results: List[RuleResult] = []

    for rule in rules:
        answer = system.get(rule.id, None)
        outcome = rule.evaluate(answer)
        result = RuleResult(rule=rule, answer=answer, outcome=outcome,
                            raw_score=outcome.score)
        by_category.setdefault(rule.category, []).append(result)
        all_results.append(result)

    categories: List[CategoryResult] = []
    for name in category_order:
        meta = CATEGORIES[name]
        categories.append(CategoryResult(
            name=name,
            title=meta["title"],
            summary=meta["summary"],
            transcript_ref=meta["transcript_ref"],
            rules=by_category.get(name, []),
        ))

    # Weighted overall score over every answered rule (unanswered count as 0).
    weighted_sum = 0.0
    denom = 0.0
    for r in all_results:
        denom += r.rule.weight * r.rule.risk.weight
        weighted_sum += r.weighted_score
    overall = weighted_sum / denom if denom else 0.0

    verdict = _gate_verdict(overall)
    ready = verdict == "APPROVED"

    summary = (
        f"{system.name}: readiness {overall:.2f}/1.00 — {verdict}. "
        + ("Cleared for sustained production run."
           if ready else
           "Gaps remain in the invisible 80%: governance, monitoring, "
           "runtime and guard rails.")
    )

    return ReadinessReport(
        system_name=system.name,
        overall_score=round(overall, 4),
        gate_verdict=verdict,
        production_ready=ready,
        categories=categories,
        summary=summary,
        top_risks=_top_risks(all_results),
        recommendations=_recommendations(all_results),
    )


def assess_answers(name: str, answers: Mapping[str, Any],
                   rules: Optional[Sequence[ReadinessRule]] = None,
                   ) -> ReadinessReport:
    """Convenience wrapper — score a plain answers dict."""
    return assess(SystemProfile(name=name, answers=dict(answers)), rules=rules)


# =============================================================================
# Run-assurance checks (deterministic)
# =============================================================================

@dataclass(frozen=True)
class DeterminismResult:
    """Outcome of a deterministic-output probe over N runs of same input."""
    runs: int
    distinct_outputs: int
    stable_ratio: float          # 1.0 - distinct/runs
    outcome: CheckOutcome

    @property
    def consistent(self) -> bool:
        return self.outcome is CheckOutcome.PASS


def check_deterministic_output(observed: Sequence[Any]) -> DeterminismResult:
    """Probe determinism by feeding the same input K times and comparing
    outputs (a demo looks fine once; a sustained run needs a repeatable
    golden path — "would they do million times the same thing?")."""
    observed = list(observed)
    if not observed:
        return DeterminismResult(0, 0, 0.0, CheckOutcome.WARN)
    distinct = len(set(observed))
    stable = 1.0 - (distinct - 1) / max(1, len(observed) - 1)
    if distinct == 1:
        outcome = CheckOutcome.PASS
    elif distinct < len(observed):
        # Some repeats but not a fully stable golden path.
        outcome = CheckOutcome.WARN
    else:
        outcome = CheckOutcome.FAIL
    return DeterminismResult(len(observed), distinct, round(stable, 4), outcome)


@dataclass(frozen=True)
class DriftResult:
    """Data/model drift detection stub comparing a reference to live stats."""
    z_score: float               # |current - reference| / reference_std
    threshold: float             # z-score that trips a WARN (default 2.0)
    outcome: CheckOutcome
    note: str

    @property
    def drifted(self) -> bool:
        return self.outcome is not CheckOutcome.PASS


def detect_drift(reference_mean: float, current_mean: float,
                 reference_std: float, threshold_std: float = 2.0,
                 ) -> DriftResult:
    """Detect drift as a z-score of the live stream vs a reference
    distribution.  Deterministic, network-free.  Drift is the silent failure
    that only becomes visible once monitoring is in place."""
    if reference_std <= 0:
        z = 0.0 if current_mean == reference_mean else float("inf")
    else:
        z = abs(current_mean - reference_mean) / reference_std
    # Hard cap to keep the stub finite & testable.
    z = z if math.isfinite(z) else threshold_std * 10.0
    if z <= threshold_std:
        outcome = CheckOutcome.PASS
        note = "within drift threshold"
    elif z <= threshold_std * 1.5:
        outcome = CheckOutcome.WARN
        note = "drift approaching threshold — schedule review"
    else:
        outcome = CheckOutcome.FAIL
        note = "significant drift detected — retrain / revalidate required"
    return DriftResult(round(z, 4), threshold_std, outcome, note)


class CircuitState(Enum):
    CLOSED = "CLOSED"          # normal traffic
    OPEN = "OPEN"              # breaker tripped — fast-fail
    HALF_OPEN = "HALF_OPEN"    # probe attempt allowed


@dataclass(frozen=True)
class CircuitDecision:
    state: CircuitState
    failures_in_window: int
    max_failures: int
    cooldown_remaining: int    # attempts left before a HALF_OPEN probe
    reason: str

    @property
    def allows_traffic(self) -> bool:
        return self.state is not CircuitState.OPEN


def circuit_breaker_state(failures_in_window: int, max_failures: int,
                          cooldown_remaining: int = 0, allow_probe: bool = False,
                          ) -> CircuitDecision:
    """Circuit-breaker semantics for a brittle chain (the demo app that
    "breaks every 20 minutes"): CLOSED within budget, OPEN when tripped,
    HALF_OPEN only after cooldown elapses and a probe is allowed."""
    if failures_in_window > max_failures:
        if cooldown_remaining <= 0 and allow_probe:
            return CircuitDecision(CircuitState.HALF_OPEN, failures_in_window,
                                   max_failures, 0,
                                   "cooldown elapsed; single probe allowed")
        return CircuitDecision(CircuitState.OPEN, failures_in_window,
                               max_failures, cooldown_remaining,
                               "breaker tripped — fast-fail")
    return CircuitDecision(CircuitState.CLOSED, failures_in_window,
                           max_failures, cooldown_remaining,
                           "within failure budget")


@dataclass(frozen=True)
class RetryDecision:
    attempt: int
    max_retries: int
    allowed: bool
    backoff_seconds: float
    reason: str


def retry_plan(attempt: int, max_retries: int,
               base_backoff: float = 1.0, multiplier: float = 2.0,
               jitter: float = 0.0) -> RetryDecision:
    """Exponential-backoff retry semantics; `jitter` defaults to 0 for
    determinism."""
    allowed = attempt <= max_retries
    backoff = base_backoff * (multiplier ** max(0, attempt - 1)) + jitter
    reason = ("retry allowed" if allowed else "retry budget exhausted")
    return RetryDecision(attempt, max_retries, allowed,
                         round(backoff, 4), reason)


@dataclass(frozen=True)
class EscalationDecision:
    severity: RiskLevel
    threshold: RiskLevel           # at/above this risk a human is required
    human_required: bool
    reason: str


def human_escalation_required(severity: RiskLevel,
                              threshold: RiskLevel = RiskLevel.HIGH,
                              ) -> EscalationDecision:
    """Human-oversight gate: high-risk actions must route to a human."""
    required = severity.weight >= threshold.weight
    reason = ("human approval required — high risk" if required
              else "automated path acceptable")
    return EscalationDecision(severity, threshold, required, reason)


__all__ = [
    "CATEGORIES", "CheckOutcome", "CircuitState", "RiskLevel",
    "ReadinessRule", "RuleResult", "CategoryResult", "ReadinessReport",
    "SystemProfile", "default_rules", "assess", "assess_answers",
    "DeterminismResult", "check_deterministic_output",
    "DriftResult", "detect_drift",
    "CircuitDecision", "circuit_breaker_state",
    "RetryDecision", "retry_plan",
    "EscalationDecision", "human_escalation_required",
]
