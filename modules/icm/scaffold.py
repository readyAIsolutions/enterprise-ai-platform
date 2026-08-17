"""ICM project scaffolder — generate the standard numbered stage template.

Creates the spec's canonical folder structure (spec §4):

    <project>/
    ├── 00_master.md            <- table of contents; routes tasks to stages
    ├── 01_intake/      instructions.md + scripts/
    ├── 02_research/
    ├── 03_drafting/
    ├── 04_verification/
    └── 05_output/

Also ships a ready-made example project for the common pipelines referenced in
the spec (document compliance / ops), so a real reference implementation exists
out of the box rather than an empty skeleton.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

DEFAULT_STAGES = [
    "01_intake",
    "02_research",
    "03_drafting",
    "04_verification",
    "05_output",
]

_DEFAULT_MASTER = """# {project} — ICM master map

This file is the ONLY thing an orchestrator reads to route a task to a stage
folder. It holds the map, not the details. Each stage folder is self-contained
(instructions.md + scripts/).

## task routing
# stage, task
## 01_intake, intake
## 02_research, research
## 03_drafting, draft
## 04_verification, verify
## 05_output, output
"""

_DEFAULT_INSTRUCTIONS = """# Stage: {stage}

## Role
You are the {stage} stage of the ICM pipeline for {project}.

## Inputs
- What this stage receives, and where it comes from.

## Definition of good output
- What this stage must produce for the next stage to succeed.
- Keep it verifiable and auditable.

## Rules
- Offload mechanical work (formatting, conversion, validation, API calls) to a
  script under `scripts/` — do NOT hand-reason what a deterministic tool should do.
- Keep this stage self-contained. Read only what this stage needs.
"""


def _stage_title(num: int, name: str) -> str:
    return f"{num:02d}_{name}"


def scaffold(project_dir: str | os.PathLike[str],
             stages: Optional[list[str]] = None,
             with_examples: bool = True) -> Path:
    """Create the ICM project folder tree at project_dir. Returns project root."""
    root = Path(project_dir)
    root.mkdir(parents=True, exist_ok=True)
    project_name = root.name or "project"

    stages = stages or list(DEFAULT_STAGES)

    # 00_master.md
    master = root / "00_master.md"
    if not master.exists():
        master.write_text(_DEFAULT_MASTER.format(project=project_name),
                          encoding="utf-8")

    for slug in stages:
        m = __import__("re").match(r"^(\d{2})_([a-zA-Z0-9_\-]+)$", slug)
        if not m:
            continue
        num, name = int(m.group(1)), m.group(2)
        folder = root / slug
        (folder / "scripts").mkdir(parents=True, exist_ok=True)
        inst = folder / "instructions.md"
        if not inst.exists():
            inst.write_text(
                _DEFAULT_INSTRUCTIONS.format(project=project_name, stage=name),
                encoding="utf-8")

    if with_examples:
        _scaffold_example(root)

    return root


def _scaffold_example(root: Path) -> None:
    """Drop two reference implementations the spec names (spec §5 next-steps):
    a deterministic document-compliance pipeline and a repeatable ops pipeline.
    """
    # 1) doc compliance (Aurora-style)
    doc = root / "11_example_doc_compliance"
    doc.mkdir(parents=True, exist_ok=True)
    (doc / "scripts").mkdir(exist_ok=True)
    (doc / "instructions.md").write_text(
        "# Example: Document compliance audit\n\n"
        "Role: run a deterministic compliance checklist (e.g. PIPEDA fields).\n"
        "Offload the checklist to a script. Report pass/fail per item.\n",
        encoding="utf-8")
    (doc / "scripts" / "checklist.py").write_text(
        "#!/usr/bin/env python3\n"
        "\"\"\"Deterministic compliance checklist — seats NOT for the model.\"\"\"\n"
        "ITEMS = ['consent', 'purpose', 'retention', 'access', 'disclosure']\n"
        "def run(record):\n"
        "    return {k: bool(record.get(k)) for k in ITEMS}\n"
        "if __name__ == '__main__':\n"
        "    print(run({'consent': True, 'purpose': True}))\n",
        encoding="utf-8")

    # 2) repeatable ops (Detective ops style)
    ops = root / "12_example_ops_deploy"
    ops.mkdir(parents=True, exist_ok=True)
    (ops / "scripts").mkdir(exist_ok=True)
    (ops / "instructions.md").write_text(
        "# Example: Repeatable ops (Oracle Cloud-style)\n\n"
        "Role: deploy + health-check a service. Deterministic steps only.\n"
        "Run the deploy script, then the health check, and report the result.\n",
        encoding="utf-8")
    (ops / "scripts" / "healthcheck.sh").write_text(
        "#!/usr/bin/env bash\n# Example deterministic health check\n"
        "curl -sf http://127.0.0.1:8421/api/health && echo OK || exit 1\n",
        encoding="utf-8")


__all__ = ["scaffold", "DEFAULT_STAGES"]