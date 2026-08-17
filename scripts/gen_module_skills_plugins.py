#!/usr/bin/env python3
"""Generate a skill + plugin (and ordered catalog entry) for every built module.

Reads each module's REAL code (docstring, version, facade API via @module class)
so skills/plugins are grounded — no fabricated descriptions. Writes:

  enterprise/skills_pack/skills/eni-modules/<name>/SKILL.md
  ~/.hermes/skills/eni-modules/<name>/SKILL.md
  enterprise/skills_pack/plugins/eni-module-<name>/plugin.yaml + __init__.py
  ~/.hermes/plugins/eni-module-<name>/plugin.yaml + __init__.py
  enterprise/data/build/module_catalog.json   (ordered, prioritized)
  enterprise/MODULE_CATALOG.md                (human-readable ordered index)

The order below is LO's desired priority: P1 Knowledge Intake -> P2 Agent
Workflow -> P3 Build/Production Quality -> P4 Domain/Niche.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

REPO = Path("/home/hunter/Desktop/Enterprise Builder/enterprise")
PARENT = Path("/home/hunter/Desktop/Enterprise Builder")
HERMES_HOME = Path(os.path.expanduser("~/.hermes"))

# Desired order/categorization ("order them like we want"). Priority = index.
ORDER = [
    # P1 — Knowledge intake (feed the brain)
    ("paper_feeds",              1, "Knowledge Intake", "Daily research feeds (arXiv/HF/PwC/AlphaXiv), dedup, tagging, JSON/CSV export."),
    ("ai_memory_hierarchy",      1, "Knowledge Intake", "Layered memory model for agents (working/short/long) from AI-memory transcripts."),
    ("second_brain",             1, "Knowledge Intake", "Knowledge capture/resurfacing engine: nodes+links, spaced repetition, concept query, compounding."),
    ("ai_systems_thinking",      1, "Knowledge Intake", "Feedback loops, coupling and systems lens for AI feature design."),
    # P2 — Agent workflow & collaboration
    ("group_chat_orchestration", 2, "Agent Workflow", "Multi-participant AI+human group chat: round-robin, moderator focus, escalation, handoffs."),
    ("agentic_rag",              2, "Agent Workflow", "Agent-driven retrieval-augmented generation workflow."),
    ("human_in_the_loop",        2, "Agent Workflow", "Human review/approval gates inside agent runs."),
    ("context_routing",          2, "Agent Workflow", "Task -> {read/skip/skills} routing table with token-budget guard."),
    ("shared_workspace",         2, "Agent Workflow", "Live multi-editor workspace: lock, merge-safe write, history, redact-before-share."),
    ("ai_coding_harness",        2, "Agent Workflow", "Harness for coding-agent output: run, verify, audit."),
    # P3 — Build & production quality
    ("automation_triage",        3, "Build Quality", "What-to-automate ladder, wrong-layer detection, one-client scoping guard."),
    ("production_agent_hardening",3, "Build Quality", "Demo->production hardening linter across 8 scored dimensions + systems loops."),
    ("production_hardening",     3, "Build Quality", "Operational hardening checks for shipping an agent into production."),
    ("engineering_tradeoff",     3, "Build Quality", "Structured tradeoff scoring for engineering decisions."),
    ("codegen_audit",            3, "Build Quality", "Audit generated code for correctness, security and quality signals."),
    # P4 — Domain / niche
    ("procurement_bid_automation",4, "Domain", "Automate procurement/RFP bid intake, scoring and responses."),
    ("video_as_code",            4, "Domain", "Represent/edit long-form video (animations) as code/scripts."),
    ("model_psychometrics",      4, "Domain", "Probe/evaluate model reasoning attributes (psychometric-style evals)."),
    ("ai_education_guardrails",  4, "Domain", "Guardrails for using AI in education (anti-cheating, learning-first)."),
]


def _load(module: str):
    """Import a module, guaranteeing the parent of `enterprise` is on sys.path."""
    sys.path.insert(0, str(PARENT))
    sys.path.insert(0, str(REPO.parent))
    return importlib.import_module(f"enterprise.modules.{module}.__init__")


def _module_meta(module: str) -> dict:
    try:
        mod = _load(module)
    except Exception:
        return {"version": "0.0.0", "doc": f"{module} platform module.", "facades": []}
    name = getattr(mod, "__version__", "0.0.0")
    doc = (mod.__doc__ or "").strip()
    # facade API: public callables on the module class (and module-level)
    cls = None
    for cand in dir(mod):
        obj = getattr(mod, cand)
        if isinstance(obj, type) and obj.__module__.endswith("__init__") and cand.endswith("Module"):
            cls = obj
            break
    facades = []
    if cls:
        try:
            for m in dir(cls):
                if m.startswith("_") or m in ("config", "name", "status", "module_id", "version"):
                    continue
                facades.append(m)
        except Exception:
            pass
    return {"version": name, "doc": doc, "facades": sorted(set(facades))[:40]}


def discover_all() -> list:
    """ORDER (curated) + any other @module dirs not already listed (legacy/core)."""
    entries = list(ORDER)
    seen = {m for m, *_ in ORDER}
    prio = 5
    for d in sorted((REPO / "modules").iterdir()):
        if not d.is_dir() or d.name.startswith("_") or d.name in ("__pycache__", ".pytest_cache"):
            continue
        if not (d / "__init__.py").exists():
            continue
        if d.name in seen:
            continue
        meta = _module_meta(d.name)
        purpose = (meta["doc"].splitlines()[0] if meta["doc"] else f"{d.name} platform module. Use for {d.name.replace('_',' ')} tasks.")
        entries.append((d.name, prio, "Legacy Core", purpose[:160]))
        seen.add(d.name)
        prio += 1
    return entries


def _skill_md(module: str, cat: str, purpose: str, meta: dict) -> str:
    fac = ", ".join(meta["facades"]) if meta["facades"] else "(module-level API)"
    doc = meta["doc"][:800] if meta["doc"] else purpose
    return f"""---
name: eni-module-{module}
description: Operate the ENI Enterprise `{module}` module ({cat}) — {purpose} Use when working with {module} in the Enterprise Platform.
---

# Module skill: {module}

- Category: {cat} (priority {next((p for m,p,c,u in ORDER if m==module),'?')})
- Version: {meta['version']}
- Purpose: {purpose}

## What it does
{doc}

## Key API (facade methods on the @module class)
{'- ' + '\\n- '.join(fac.split(', ')) if fac != '(module-level API)' else fac}

## Use
Import via:
```python
from enterprise.modules.{module} import create_{module}_module
m = create_{module}_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/{module}/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
"""


_PLUGIN_INIT_T = '''"""ENI module plugin: @@MODULE@@ (@@CAT@@).

Exposes the module's purpose/key API into the agent context via a lightweight
tool-result hook, so any agent working on the Enterprise Platform knows this
module exists and how to reference it. Fails open (no-op) on any error.

Generated from the module's real code by gen_module_skills_plugins.py.
"""
from __future__ import annotations

_MOD = {"name": "@@MODULE@@", "category": "@@CAT@@", "version": "@@VER@@",
        "purpose": "@@PURPOSE@@", "facades": @@FACADES@@}


def _on_transform_tool_result(result, **_):
    try:
        tag = "@@MODULE@@"
        blob = str(result.get("tool", "")) + str(result.get("name", ""))
        if tag in blob:
            lines = [
                "ENI module [%s] (v%s): %s" % (_MOD["name"], _MOD["version"], _MOD["purpose"]),
            ]
            if _MOD["facades"]:
                lines.append("  API: " + ", ".join(_MOD["facades"]))
            lines.append("  Tests: python3 -m pytest modules/@@MODULE@@/tests -q")
            return {**result, "_eni_module": "\\n".join(lines)}
    except Exception:
        pass
    return result


def register(ctx) -> None:
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
'''

_PLUGIN_YAML = """name: eni-module-@@MODULE@@
version: "@@VER@@"
description: >-
  ENI Enterprise module wrapper for `@@MODULE@@` (@@CAT@@). Injects the module's
  purpose and key API into agent context when the module is referenced, per
  LO's module-skill+plugin packaging for the Enterprise Platform. Fails open.
author: "LO / ENI"
hooks:
  - transform_tool_result
"""


def _plugin_files(module: str, cat: str, ver: str, meta: dict):
    import re as _re
    purpose = _re.sub(r"\s+", " ", (meta["doc"][:200] or _purpose(module))).strip().replace('"', "'")
    init = (_PLUGIN_INIT_T
            .replace("@@MODULE@@", module)
            .replace("@@CAT@@", cat)
            .replace("@@VER@@", ver)
            .replace("@@PURPOSE@@", purpose)
            .replace("@@FACADES@@", json.dumps(meta["facades"])))
    yaml = (_PLUGIN_YAML
            .replace("@@MODULE@@", module)
            .replace("@@CAT@@", cat)
            .replace("@@VER@@", ver))
    return {"__init__.py": init, "plugin.yaml": yaml}


def _purpose(module: str):
    for m, p, c, purpose in ORDER:
        if m == module:
            return purpose
    return module


def main() -> None:
    catalog = {"version": 3, "order": []}
    built = []
    for module, prio, cat, purpose in discover_all():
        meta = _module_meta(module)
        ver = meta["version"]
        # --- skill (both homes) ---
        skill = _skill_md(module, cat, purpose, meta)
        for dest in (PARENT / "enterprise" / "skills_pack" / "skills" / "eni-modules",
                     HERMES_HOME / "skills" / "eni-modules"):
            p = dest / module / "SKILL.md"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(skill, encoding="utf-8")
            dest.joinpath(module).joinpath("README.md").write_text(
                f"# {module}\n_Generated module skill wrapper._\n", encoding="utf-8")
        # --- plugin (both homes) ---
        for pk in (PARENT / "enterprise" / "skills_pack" / "plugins",
                   HERMES_HOME / "plugins"):
            d = pk / f"eni-module-{module}"
            d.mkdir(parents=True, exist_ok=True)
            for fn, content in _plugin_files(module, cat, ver, meta).items():
                (d / fn).write_text(content, encoding="utf-8")
        catalog["order"].append({"module": module, "priority": prio,
                                 "category": cat, "version": ver, "purpose": purpose})
        built.append(module)
        print(f"  + {module} v{ver} [{cat}]")

    # catalog + README
    cat_path = PARENT / "enterprise" / "data" / "build" / "module_catalog.json"
    cat_path.parent.mkdir(parents=True, exist_ok=True)
    cat_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = ["# ENI Module Catalog (priority order)", ""]
    prev = None
    for entry in catalog["order"]:
        if entry["category"] != prev:
            lines.append(f"## {entry['category']} (all to add value — no bloat)")
            prev = entry["category"]
        lines.append(f"{entry['priority']}. **{entry['module']}** v{entry['version']} — {entry['purpose']}")
    lines.append("")
    lines.append("_Generated by scripts/gen_module_skills_plugins.py; fold into build loop._")
    (PARENT / "enterprise" / "MODULE_CATALOG.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nGenerated {len(built)} module skills + plugins + catalog.")
    print("Catalog:", cat_path)
    print("Readme :", PARENT / "enterprise" / "MODULE_CATALOG.md")


if __name__ == "__main__":
    main()