#!/usr/bin/env python3
"""B5 - CI/CD bridge.

A deterministic goal -> step planner that decomposes a single high-level goal
into an ordered list of N ICM-stage tasks (intake, research, drafting,
verification, output) that a CI system could submit to a builder fleet via
submit_plan. The plan is fully deterministic: the same goal always yields the
same steps, so CI can cache, diff and re-run incrementally.

Exposes:
    build_plan(goal) -> list of Step          # core, importable
    Step dataclass

CLI:
    python3 scripts/ci_bridge.py --goal 'build a budget tracker'
    python3 scripts/ci_bridge.py --json --goal '...'   # machine readable
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from typing import List, Optional

# Ordered ICM pipeline stages. Order here is the canonical execution order.
ICM_STAGES = ["intake", "research", "drafting", "verification", "output"]

# Deterministic per-stage task templates. {goal} is the only substitution.
_STAGE_PLAN = {
    "intake": {
        "title": "Clarify and scope the goal",
        "task": "Restate the goal {goal!r} as a precise, single-sentence "
                "specification with explicit in/out boundaries and one success "
                "criterion. Produce an intake brief.",
        "feature": "intake_brief",
        "test_hint": "specification present",
    },
    "research": {
        "title": "Research requirements and constraints",
        "task": "Identify dependencies, interfaces, inputs/outputs and edge "
                "cases for {goal!r}. Record assumptions in a research note.",
        "feature": "research_note",
        "test_hint": "assumptions recorded",
    },
    "drafting": {
        "title": "Draft the implementation",
        "task": "Implement the core deliverable for {goal!r} that satisfies "
                "the intake spec and research assumptions. Produce runnable "
                "artifacts with a minimal CLI or callable interface.",
        "feature": "implementation",
        "test_hint": "'__main__' in source or 'def main' in source",
    },
    "verification": {
        "title": "Verify with tests",
        "task": "Write and run tests that exercise {goal!r}. Cover the happy "
                "path plus one edge case, using plain assertions or a minimal "
                "unittest.TestCase.",
        "feature": "tests_and_validation",
        "test_hint": "'assert ' in tests or 'Test' in tests",
    },
    "output": {
        "title": "Package and document",
        "task": "Package the deliverable for {goal!r}: a short README "
                "describing what it does and how to run it, plus a manifest of "
                "produced artifacts.",
        "feature": "packaging_and_readme",
        "test_hint": "'# ' in readme",
    },
}


@dataclass
class Step:
    """A single ICM-stage task in a decomposed plan."""
    step: int
    stage: str
    title: str
    task: str
    prompt: str
    feature: str
    test_hint: str
    deps: List[int] = field(default_factory=list)


def _normalize_goal(goal: str) -> str:
    goal = (goal or "").strip()
    if not goal:
        goal = "a small utility program"
    return re.sub(r"\s+", " ", goal)


def build_plan(goal: str) -> List[Step]:
    """Deterministically decompose ``goal`` into N ICM-stage Steps.

    The plan is a linear dependency chain over the fixed ICM stage order, so
    it is reproducible across runs, hosts and CI pipelines.
    """
    cleaner = _normalize_goal(goal)
    steps: List[Step] = []
    for idx, stage in enumerate(ICM_STAGES):
        tpl = _STAGE_PLAN[stage]
        task = tpl["task"].format(goal=cleaner)
        steps.append(
            Step(
                step=idx + 1,
                stage=stage,
                title=tpl["title"],
                task=task,
                prompt=task,
                feature=tpl["feature"],
                test_hint=tpl["test_hint"],
                deps=[idx] if idx > 0 else [],
            )
        )
    return steps


def build_plan_id(goal: str, steps: Optional[List[Step]] = None) -> str:
    """Stable plan fingerprint so CI can cache/reuse identical plans."""
    steps = steps if steps is not None else build_plan(goal)
    payload = json.dumps([asdict(s) for s in steps]).encode()
    return hashlib.sha256(payload).hexdigest()[:12]


def _plan_to_json(steps: List[Step], goal: str = "") -> dict:
    return {
        "goal": _normalize_goal(goal),
        "stages": ICM_STAGES,
        "steps": [asdict(s) for s in steps],
        "count": len(steps),
        "plan_id": build_plan_id(goal, steps),
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="ci_bridge.py",
        description="Decompose a goal into ICM-stage tasks for a CI system.")
    ap.add_argument("--goal", required=True,
                    help="The high-level goal to decompose.")
    ap.add_argument("--json", action="store_true",
                    help="Emit JSON instead of a human-readable table.")
    args = ap.parse_args(argv)

    steps = build_plan(args.goal)
    if args.json:
        print(json.dumps(_plan_to_json(steps, args.goal), indent=2))
        return 0

    print(f"CI plan for goal: {_normalize_goal(args.goal)!r}")
    print(f"Stages (ICM): {' -> '.join(ICM_STAGES)}")
    print(f"Plan id: {build_plan_id(args.goal, steps)}  steps: {len(steps)}")
    print("-" * 72)
    for s in steps:
        deps = f"  after step {s.deps[0]}" if s.deps else "  (root)"
        print(f"[{s.step}] {s.stage.upper():<12} {s.title}{deps}")
        print(f"      feature: {s.feature}")
        print(f"      task:    {s.task}")
    print("-" * 72)
    print("Submit each step as its own task to a builder fleet via "
          "POST /api/submit_plan.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
