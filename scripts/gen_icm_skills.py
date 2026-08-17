#!/usr/bin/env python3
"""Wrap every built module skill into the ICM numbered-stage folder layout.

ICM (Interpretable Context Methodology) — LO directive: every skill uses
numbered stage folders + a 00_master.md map + scripts/ for deterministic work,
with progressive disclosure.

For each module, emits (in BOTH enterprise/skills_pack/skills/eni-modules/<m>/
and ~/.hermes/skills/eni-modules/<m>/):
  00_master.md               entry/map: purpose, stages that apply, how to use
  01_intake/instructions.md  inputs + normalization, scripts
  02_research/instructions.md (research-style modules only)
  03_drafting/instructions.md produce the deliverable
  04_verification/instructions.md run the module's real tests
  05_output/instructions.md  output / handoff
Plus a root map: docs/ICM_00_master.md (task -> module -> stage).
Grounded from real module metadata (data/build/module_catalog.json + import).
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

REPO = Path("/home/hunter/Desktop/Enterprise Builder/enterprise")
PARENT = Path("/home/hunter/Desktop/Enterprise Builder")
HERMES = Path(os.path.expanduser("~/.hermes"))

RESEARCH_CATEGORIES = {"Knowledge Intake", "Agent Workflow"}


def load_catalog() -> list:
    c = json.loads((REPO / "data/build/module_catalog.json").read_text(encoding="utf-8"))
    return c["order"]


def _import(module: str):
    sys.path.insert(0, str(PARENT))
    return importlib.import_module(f"enterprise.modules.{module}.__init__")


def facades(module: str) -> list:
    try:
        mod = _import(module)
        cls = next((c for c in dir(mod)
                    if isinstance(getattr(mod, c), type)
                    and getattr(mod, c).__module__.endswith("__init__")
                    and c.endswith("Module")), None)
        if cls:
            return sorted(m for m in dir(getattr(mod, cls))
                          if not m.startswith("_") and m not in
                          ("config", "name", "status", "module_id", "version"))
    except Exception:
        pass
    return []


def _ini(module: str, purpose: str, role: str, inputs: str, good: str, scripts: str) -> str:
    return (f"# {role}\n\n"
            f"Purpose: {purpose}\n\n"
            f"## Role\n{role} for the `{module}` module.\n\n"
            f"## Inputs\n{inputs}\n\n"
            f"## Definition of good output\n{good}\n\n"
            f"## Scripts\n{scripts}\n")


def stage_plan(module: str, purpose: str, cat: str, fac: list):
    t = fac[:6]
    api = ", ".join(t) if t else purpose
    return {
        "01_intake": _ini(module, purpose, "Gather and normalize inputs",
                          f"Raw inputs/context for {module}: {scope(module)}. "
                          "Validate and stage them before any processing.",
                          f"Normalised, staged inputs ready for {module}. No unvalidated data passes.",
                          f"python3 -m pytest modules/{module}/tests -q (validates core logic)"),
        "02_research": _ini(module, purpose, "Pull relevant context (progressive disclosure)",
                            "Only the stage-relevant reference context needed to run this module.",
                            f"The minimum context to run {module} — no full-system dump.",
                            ""),
        "03_drafting": _ini(module, purpose, "Produce the deliverable",
                            f"Normalised inputs + the {module} API ({api}).",
                            f"A {module} output produced via its facade methods; deterministic where possible.",
                            ""),
        "04_verification": _ini(module, purpose, "Verify",
                                f"The {module} deliverable + its expectations.",
                                f"All checks pass: the module's own test suite is green and the result "
                                "meets the definition of good output.",
                                f"python3 -m pytest modules/{module}/tests -q  (REAL suite; must pass)"),
        "05_output": _ini(module, purpose, "Hand off the finished result",
                          f"Verified {module} output.",
                          "A clean, auditable deliverable/commit referencing which input produced it.",
                          "Commit on upgrade/demiurge-enterprise-boost (main is protected)."),
    }


def scope(m):
    return {"paper_feeds": "research feeds", "second_brain": "knowledge notes",
            "ai_memory_hierarchy": "agent memory", "group_chat_orchestration": "chat turns",
            "shared_workspace": "shared files/history", "context_routing": "tasks",
            "automation_triage": "task specs", "production_agent_hardening": "agent specs",
            "codegen_audit": "generated code", "video_as_code": "video scripts",
            "procurement_bid_automation": "RFPs/bids", "ai_education_guardrails": "education prompts",
            "model_psychometrics": "model responses", "agentic_rag": "queries+corpus",
            "human_in_the_loop": "approval items", "ai_coding_harness": "agent code runs",
            "production_hardening": "deploy specs", "engineering_tradeoff": "options",
            "ai_systems_thinking": "system designs"}.get(m, "inputs")


def main():
    entries = load_catalog()
    root_map = ["# ICM 00_master — Enterprise Task -> Module -> Stage map", "",
                "Read this file to know which module + stage to activate for a task.",
                "Catch-all: if a task just needs a capability, use the module directly.",
                "", "| Task / need | Module | Primary stage(s) |", "|---|---|---|"]
    for e in entries:
        m, prio, cat, purpose = e["module"], e["priority"], e["category"], e["purpose"]
        fac = facades(m)
        plan = stage_plan(m, purpose, cat, fac)
        stages = stages_for(cat)
        # stage folders to create
        folders = ["01_intake"] + (["02_research"] if cat in RESEARCH_CATEGORIES else []) + \
                  ["03_drafting", "04_verification", "05_output"]
        for dest in (REPO / "skills_pack/skills/eni-modules", HERMES / "skills/eni-modules"):
            d = dest / m
            d.mkdir(parents=True, exist_ok=True)
            master = (f"# ICM module map: {m}\n\n"
                      f"- Category: {cat} (priority {prio})\n- Version: {e['version']}\n"
                      f"- Purpose: {purpose}\n- API: {', '.join(fac[:8]) or purpose}\n\n"
                      f"## Stages\n{stages}\n\n"
                      f"**To use:** read the stage folder below matching your task. "
                      f"Start at 01_intake; run 04_verification before 05_output.\n")
            (d / "00_master.md").write_text(master, encoding="utf-8")
            for s in folders:
                (d / s).mkdir(parents=True, exist_ok=True)
                (d / s / "instructions.md").write_text(plan.get(s, ""), encoding="utf-8")
            scripts = d / "scripts"
            scripts.mkdir(exist_ok=True)
        root_map.append(f"| {purpose[:60]} | {m} | {stages} |")
    root_map += ["", "_Generated: python3 scripts/gen_icm_skills.py_"]
    (REPO / "docs/ICM_00_master.md").write_text("\n".join(root_map), encoding="utf-8")
    print(f"ICM skills generated for {len(entries)} modules. Root map: docs/ICM_00_master.md")


def stages_for(cat):
    base = "01_intake, 03_drafting, 04_verification, 05_output"
    if cat in RESEARCH_CATEGORIES:
        base = base.replace("03_drafting", "02_research, 03_drafting")
    return base


if __name__ == "__main__":
    main()