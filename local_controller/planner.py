"""Deterministic goal -> task DAG planner.

INTENT
------
Turn one natural-language GOAL string into an ordered list of BuildTasks that,
executed together, produce a small program. It is a deterministic template
pipeline (goalify -> spec -> epics -> tasks) so the SAME goal always yields the
SAME plan (no randomness, easy to test).

Each task carries ``step``, ``feature``, ``prompt``, ``deps`` (list of the step
indices it depends on) and a ``test_hint`` used later by the build provider to
self-test the produced artifact. The pipeline yields 4-8 cohesive steps.

``enrich_prompt`` implements the "make bigger prompts" feature: it expands a
terse prompt into a much more detailed, self-contained instruction so a worker
/ external LLM has full context to act on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class BuildTask:
    """A single cohesive work unit in a program build plan."""

    step: int
    feature: str
    prompt: str
    deps: List[int] = field(default_factory=list)
    test_hint: str = ""

    def to_dict(self) -> dict:
        return {
            "step": self.step,
            "feature": self.feature,
            "prompt": self.prompt,
            "deps": list(self.deps),
            "test_hint": self.test_hint,
        }


@dataclass
class Plan:
    """Ordered collection of build steps for one goal."""

    goal: str
    tasks: List[BuildTask]

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "steps": [t.to_dict() for t in self.tasks],
        }


# ---------------------------------------------------------------------------
# Deterministic pipeline
# ---------------------------------------------------------------------------

# Canonical epic skeleton -> each becomes one task. Features are cohesive and
# deliberately ordered so later steps depend on earlier ones (chain DAG).
_EPICS = [
    {
        "feature": "requirements_and_spec",
        "prompt_tpl": (
            "Write a concise requirements spec for building: {goal}. "
            "List the inputs, expected outputs, and functional requirements "
            "as bullet points. This is the contract the implementation must meet."
        ),
        "test_hint": "assert 'requirements' in spec_text.lower()",
    },
    {
        "feature": "data_and_state_model",
        "prompt_tpl": (
            "Design the core data model and state for: {goal}. "
            "Define the fields, types, and default values used by the program. "
            "Keep it minimal but complete."
        ),
        "test_hint": "assert isinstance(your_model, dict)",
    },
    {
        "feature": "core_logic",
        "prompt_tpl": (
            "Implement the core logic/module for: {goal}. "
            "Expose a clean function or class that turns the documented inputs "
            "into the documented outputs. Add inline comments."
        ),
        "test_hint": "'def main' in source or 'class ' in source",
    },
    {
        "feature": "api_and_interface",
        "prompt_tpl": (
            "Wrap the logic for: {goal} behind a simple programmatic interface "
            "(CLI, callable, or small HTTP endpoint). Wire inputs in, outputs out. "
            "Handle at least a basic error case."
        ),
        "test_hint": "'__main__' in source",
    },
    {
        "feature": "tests_and_validation",
        "prompt_tpl": (
            "Write tests that exercise the interface for: {goal}. "
            "Cover the happy path plus one edge case. Tests must be runnable "
            "with plain assertions or a minimal unittest.TestCase."
        ),
        "test_hint": "'assert ' in tests or 'Test' in tests",
    },
    {
        "feature": "packaging_and_readme",
        "prompt_tpl": (
            "Package the program for: {goal}. Write a minimal README that "
            "describes what it does and how to run it, and specify how the "
            "pieces fit together as one deliverable."
        ),
        "test_hint": "'# ' in readme",
    },
]


def _goalify(goal: str) -> str:
    """Normalize the goal into a clean, single-line phrasing."""
    goal = (goal or "").strip()
    if not goal:
        goal = "a small utility program"
    goal = re.sub(r"\s+", " ", goal)
    return goal


def parse_goal(goal: str) -> Plan:
    """Deterministically decompose a GOAL string into a task DAG plan."""
    cleaner = _goalify(goal)
    tasks: List[BuildTask] = []
    for idx, epic in enumerate(_EPICS):
        deps = [i for i in range(idx)]  # chain: each step depends on all before it
        if deps == [idx - 1] and idx > 0:  # keep it a simple linear chain
            deps = [idx - 1]
        tasks.append(
            BuildTask(
                step=idx + 1,
                feature=epic["feature"],
                prompt=epic["prompt_tpl"].format(goal=cleaner),
                deps=deps,
                test_hint=epic["test_hint"],
            )
        )
    return Plan(goal=cleaner, tasks=tasks)


# ---------------------------------------------------------------------------
# Prompt enrichment  ("make bigger prompts")
# ---------------------------------------------------------------------------

_ENRICH_SECTIONS = [
    ("Context", "You are a senior software engineer generating one cohesive "
                "program from a single goal."),
    ("Constraints", "Use plain Python. Keep every artifact self-contained and "
                    "independently runnable. Never transmit or leak secrets."),
    ("Acceptance criteria", "The generated program must be runnable, tested, "
                            "and packaged as a single coherent deliverable."),
    ("Output format", "Return focused, executable code plus short comments. "
                      "Prefer explicit over clever."),
]


def enrich_prompt(prompt: str, goal: str = "") -> str:
    """Expand a terse prompt into a much more detailed, workable one.

    This is the "make bigger prompts" feature: it wraps the given prompt in
    structured context sections so a worker or external LLM sees intent,
    constraints, acceptance criteria and output format alongside the core ask.

    ICM integration (optional): if env ``ICM_PROJECT`` points at an ICM skill
    project, the routed stage's markdown is appended as context so the worker
    follows the project's numbered-stage instructions (progressive disclosure)
    rather than a bare inline prompt. When unset, this is a no-op — no hard
    coupling.
    """
    prompt = (prompt or "").strip()
    if not prompt:
        prompt = "Build a small runnable program."
    lines = [
        "## CORE ASK",
        prompt,
        "",
    ]
    if goal:
        lines += ["## ORIGINAL GOAL", goal, ""]
    lines += ["## BUILDING GUIDANCE"]
    for title, body in _ENRICH_SECTIONS:
        lines.append(f"- {title}: {body}")
    lines += [
        "",
        "Expand on every part; do not just restate the ask. Produce the full "
        "artifact with all details filled in.",
    ]
    # ── Optional ICM stage context (progressive disclosure) ──────────────
    import os as _os
    icm_root = _os.environ.get("ICM_PROJECT", "").strip()
    if icm_root and _os.path.isdir(icm_root):
        try:
            from enterprise.modules.icm import ICMProject, classify
        except Exception:
            return "\n".join(lines)
        try:
            proj = ICMProject.open(icm_root)
            stage = proj.route(goal or prompt)
            routed = classify(goal or prompt)
            if stage is not None:
                ctx = proj.stage_context(stage)
                lines += [
                    "",
                    "## ICM STAGE (skill discipline layer)",
                    f"- Project: {proj.root.name}",
                    f"- Route  : {routed} (sequential ICM work)",
                    f"- Stage  : {stage.slug}",
                    "",
                    ctx,
                ]
        except Exception:
            pass
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------


def plan_to_program(goal: str) -> Plan:
    """Alias: parse_goal -> plan. Endpoint-facing."""
    return parse_goal(goal)


def plan_dict(plan: Plan) -> dict:
    """Serialize a Plan to a JSON-friendly dict (endpoint payload)."""
    return plan.to_dict()