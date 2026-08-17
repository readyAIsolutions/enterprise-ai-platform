"""Automation Triage — decide WHAT to automate (ladder), WHAT NOT to automate, and
at which layer.

Built directly from four pulled JE Van Clief transcripts:

  * "The Ladder That Explains Every AI Failure (And How to Avoid Them)"
        The abstraction ladder: layer 0 raw output (the "book" — same for everyone,
        commoditized), layer 1 tool-as-book, layer 2 context flows (the "movie" —
        tying prompts to real business processes, deciding which tasks get
        automated and which don't), layer 3 learning systems (the "video game" —
        flows generate data and the system gets smarter). Stay at layer 0/1 and you
        are "selling the story with nothing wrapped around it" — the classic AI
        failure.

  * "You're Automating The Wrong Layer (How 30,000 People Build AI Without
      Frameworks)"
        People pour effort into the wrong layer (raw prompts / infrastructure)
        instead of the context layer. This module flags exactly that mismatch.

  * "The Real Skill in AI: Knowing What Not to Automate"
        "In a world full of answers, questions become valuable" — the skill is
        knowing what to KEEP human (judgment, taste, strategy), not auto-automating.

  * "Afternoon Tea #2: Stop Building Production-Ready AI. Solve for One Client
      First"
        A scoping guard: don't build production-grade enterprise infra before a
        single client use case is validated. Solve for one client first.

This module makes those ideas executable and unit-testable with zero network
dependencies: a task-triage ladder, a wrong-layer detector, a "what not to
automate" advisor, and a one-client scoping guard.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

__version__ = "1.0.0"

# ---------------------------------------------------------------------------
# The Ladder (SjlCJIU9ODs): each rung abstracts the one below into something
# you can think at a higher level with. Value (and moat) climbs with the rung.
# ---------------------------------------------------------------------------


class AutomationLayer(Enum):
    """The abstraction ladder from 'The Ladder That Explains Every AI Failure'."""

    LAYER_0_RAW_OUTPUT = 0      # the "book": same raw output for everyone, commoditized
    LAYER_1_TOOL_AS_BOOK = 1    # same tool, same input, same results for every person
    LAYER_2_CONTEXT_FLOW = 2    # the "movie": prompts wired to real business processes/context
    LAYER_3_LEARNING_SYSTEM = 3  # the "video game": flows generate data -> system improves


class TriageAction(Enum):
    SERVE_RAW = "serve_raw"        # just emit the raw output (prototype / one-off)
    WRAP_IN_FLOW = "wrap_in_flow"  # automate as a contextful flow in a real process
    BUILD_SYSTEM = "build_system"  # flows generate data -> self-improving system
    KEEP_HUMAN = "keep_human"      # do NOT automate; keep judgment in the loop
    PARTIAL = "partial"            # automate the mechanics, keep judgment human


# Keywords that signal the task carries judgment/taste/strategy — the things the
# "what not to automate" transcript says become MORE valuable when everything
# else is automated ("in a world full of answers, questions become valuable").
JUDGMENT_KEYWORDS: List[str] = [
    "strategy", "judgment", "approve", "approval", "negotiat", "design",
    "taste", "creative", "sign-off", "relation", "sales", "pricing",
    "review", "advise", "decide", "direction",
]

# Production-grade enterprise requirements the one-client guard wants you to DROP
# until a single client use case is validated ("Stop Building Production-Ready AI").
PRODUCTION_KEYWORDS: List[str] = [
    "multi-tenanc", "sso", "single sign-on", "compliance", "soc2", "audit",
    "scal", "production", "infrastructure", "high availab", "load balanc",
    "kubernetes", "k8s", "sla", "failover", "uptime",
]


def _keyword_hits(text: str, keywords: List[str]) -> int:
    low = text.lower()
    return sum(1 for k in keywords if k in low)


def _high_risk(cost_of_error: Any) -> bool:
    return str(cost_of_error or "").lower() in ("high", "critical", "severe")


# ---------------------------------------------------------------------------
# Decision records
# ---------------------------------------------------------------------------


@dataclass
class TriageDecision:
    """Result of the task-triage ladder: where the task sits and what to do."""

    task: str
    ladder_level: AutomationLayer
    action: TriageAction
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task": self.task,
            "ladder_level": self.ladder_level.value,
            "action": self.action.value,
            "reasons": list(self.reasons),
        }


@dataclass
class WrongLayerReport:
    """Detected mismatch between where someone is automating and where they should be."""

    task: str
    attempted_layer: AutomationLayer
    suggested_layer: Optional[AutomationLayer]
    wrong_layer: bool
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task": self.task,
            "attempted_layer": self.attempted_layer.value,
            "suggested_layer": self.suggested_layer.value if self.suggested_layer else None,
            "wrong_layer": self.wrong_layer,
            "reasons": list(self.reasons),
        }


@dataclass
class ScopeVerdict:
    """One-client scoping guard: gate production-ready requirements until validated."""

    task: str
    approved: bool
    action: str  # "proceed" | "defer_production"
    drop: List[str] = field(default_factory=list)
    keep: List[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task": self.task,
            "approved": self.approved,
            "action": self.action,
            "drop": list(self.drop),
            "keep": list(self.keep),
            "reason": self.reason,
        }


@dataclass
class NotAutoDecision:
    """Advice on what NOT to automate — the judgment that keeps its value."""

    task: str
    automate: bool
    keep_human: bool
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task": self.task,
            "automate": self.automate,
            "keep_human": self.keep_human,
            "reasons": list(self.reasons),
        }


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def triage_task(task_repr: str, context: Optional[Dict[str, Any]] = None) -> TriageDecision:
    """Run a task up the automation ladder and decide what to do with it.

    context (all optional) may include:
      volume           int   — occurrences per week (how much runs through it)
      repeatable       bool  — is the process stable / repeated
      flow_ready       bool  — does a real business process exist to wire into
      learning_data    bool  — will the flow generate data to learn from
      judgment_needed  int   — 0..n how much human judgment the task really needs
      cost_of_error    str/int — "high"/"critical" signals risk that argues for humans

    Grounded in the ladder: layer 2 flows are "the movie" (real production value,
    deciding which tasks get automated and which don't); layer 3 systems are
    "the video game". Raw layer-0/1 output is "the book" — commoditized.
    """
    context = context or {}
    task_low = task_repr.lower()
    reasons: List[str] = []

    volume = int(context.get("volume", 0))
    repeatable = bool(context.get("repeatable", False))
    flow_ready = bool(context.get("flow_ready", False))
    learning_data = bool(context.get("learning_data", False))
    judgment = int(context.get("judgment_needed", 0) or 0)
    cost_of_error = context.get("cost_of_error", "low")

    # The transcripts stress: "in a world full of answers, questions become
    # valuable." Detect signals of judgment/taste/strategy in the task itself.
    if judgment == 0:
        judgment = _keyword_hits(task_low, JUDGMENT_KEYWORDS)

    # 1) Decide the ladder rung the task actually warrants.
    if repeatable and flow_ready and learning_data and volume >= 5:
        target = AutomationLayer.LAYER_3_LEARNING_SYSTEM
        reasons.append("repeated flow generates data -> warrants a self-improving system (layer 3)")
    elif repeatable and volume >= 5:
        target = AutomationLayer.LAYER_2_CONTEXT_FLOW
        reasons.append("repeated, stable process -> wire prompts into a real flow (layer 2)")
    else:
        target = AutomationLayer.LAYER_0_RAW_OUTPUT
        reasons.append("low/repeated volume -> start by serving raw output (layer 0/1) and climb")

    # 2) But the ladder is not an excuse to automate everything: if the task
    #    needs real judgment at meaningful risk, keep a human in the loop.
    if judgment >= 2 or (judgment >= 1 and _high_risk(cost_of_error)):
        reasons.append(
            "requires taste/judgment/strategy — automating it destroys the value "
            "('questions become valuable'); keep a human in the loop"
        )
        return TriageDecision(task_repr, target, TriageAction.KEEP_HUMAN, reasons)

    # 3) Good to automate — pick the rung.
    if target is AutomationLayer.LAYER_3_LEARNING_SYSTEM:
        return TriageDecision(task_repr, target, TriageAction.BUILD_SYSTEM, reasons)
    if target is AutomationLayer.LAYER_2_CONTEXT_FLOW:
        return TriageDecision(task_repr, target, TriageAction.WRAP_IN_FLOW, reasons)

    reasons.append(
        "one-off / prototype — just produce the output; climbing the ladder here "
        "would be over-investing in a 'book' that everyone could copy"
    )
    return TriageDecision(task_repr, target, TriageAction.SERVE_RAW, reasons)


def detect_wrong_layer(
    task_repr: str,
    attempted_layer: Any,
    context: Optional[Dict[str, Any]] = None,
) -> WrongLayerReport:
    """Flag when someone is automating the wrong layer (956DPSPX4wg / SjlCJIU9ODs).

    Two failure modes are surfaced:
      * UNDER-LEVELED — building commoditized raw output ("selling the story with
        nothing wrapped around it") when a context flow / learning system is warranted.
      * OVER-ENGINEERED ON THE WRONG THING — pouring automation into a task that
        should stay human-judgment-driven.
    """
    context = context or {}
    attempt = attempted_layer if isinstance(attempted_layer, AutomationLayer) else AutomationLayer(attempted_layer)

    dec = triage_task(task_repr, context)

    # A task that needs human judgment should not be silently automated away at
    # the flow/system rungs — that is automating the WRONG LAYER of the business.
    if dec.action is TriageAction.KEEP_HUMAN:
        if attempt.value >= AutomationLayer.LAYER_2_CONTEXT_FLOW.value:
            return WrongLayerReport(
                task_repr, attempt, None, True,
                reasons=[
                    f"task needs human judgment but was automated at {attempt.name} — "
                    "this is automating the wrong layer; keep the judgment human"
                ],
            )
        return WrongLayerReport(
            task_repr, attempt, dec.ladder_level, False,
            reasons=["task judged human-appropriate; no automation layer expected"],
        )

    target = dec.ladder_level
    if attempt.value < target.value:
        return WrongLayerReport(
            task_repr, attempt, target, True,
            reasons=[
                f"automating the wrong layer: building {attempt.name} when the task "
                f"warrants {target.name} — raw output is 'the book', commoditized and "
                "copy-able; climb to context/flows for real value"
            ],
        )
    return WrongLayerReport(
        task_repr, attempt, target, False,
        reasons=[f"already at or above the warranted layer ({target.name})"],
    )


def what_not_to_automate(
    task_repr: str,
    context: Optional[Dict[str, Any]] = None,
) -> NotAutoDecision:
    """The real skill: knowing what NOT to automate (ZMDXs59Ntjc)."""
    context = context or {}
    dec = triage_task(task_repr, context)
    task_low = task_repr.lower()

    if dec.action is TriageAction.KEEP_HUMAN:
        return NotAutoDecision(
            task_repr, automate=False, keep_human=True,
            reasons=list(dec.reasons),
        )

    # Even when automatable, the judgment-bearing slices should stay human:
    # the questions, taste, and strategy layer is where value pools.
    judgment = _keyword_hits(task_low, JUDGMENT_KEYWORDS)
    if judgment >= 1:
        return NotAutoDecision(
            task_repr, automate=False, keep_human=True,
            reasons=[
                f"'{task_repr}' carries judgment/taste keywords; automate the mechanics "
                "but keep the judgment human — in a world full of answers, the "
                "questions become valuable",
            ],
        )

    return NotAutoDecision(
        task_repr, automate=True, keep_human=False,
        reasons=["repeatable, low-judgment mechanics — safe to automate on the ladder"],
    )


def scope_for_one_client(
    proposal_reqs: Any,
    context: Optional[Dict[str, Any]] = None,
) -> ScopeVerdict:
    """One-client scoping guard (AZ1l-oaD3tk): stop building production-ready AI.

    Solves for one client first. If the proposal bundles production-grade
    enterprise requirements before a single client use case is validated, it is
    deferred and the production features are listed as DROP.
    """
    context = context or {}
    if isinstance(proposal_reqs, str):
        reqs = [r.strip() for r in proposal_reqs.split(",") if r.strip()]
    else:
        reqs = list(proposal_reqs or [])

    clients = int(context.get("clients", 0) or 0)
    validated = bool(context.get("validated_use_case", False))

    drop = [r for r in reqs if _keyword_hits(r, PRODUCTION_KEYWORDS) >= 1]
    keep = [r for r in reqs if r not in drop]

    if clients <= 1 and not validated and drop:
        return ScopeVerdict(
            task=" / ".join(reqs) if reqs else "(unnamed proposal)",
            approved=False,
            action="defer_production",
            drop=drop,
            keep=keep,
            reason=(
                "solve for one client first: these production-ready requirements "
                "are premature until a single client use case is validated. "
                "Keep only what the one client actually needs."
            ),
        )

    return ScopeVerdict(
        task=" / ".join(reqs) if reqs else "(unnamed proposal)",
        approved=True,
        action="proceed",
        drop=drop,
        keep=keep,
        reason="a validated client need exists (or no premature production requirements) — proceed.",
    )


__all__ = [
    "AutomationLayer", "TriageAction", "TriageDecision", "WrongLayerReport",
    "ScopeVerdict", "NotAutoDecision", "triage_task", "detect_wrong_layer",
    "what_not_to_automate", "scope_for_one_client",
    "JUDGMENT_KEYWORDS", "PRODUCTION_KEYWORDS", "__version__",
]
