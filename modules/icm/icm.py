"""Interpretable Context Methodology (ICM) — prompt-engineering & skill layer.

ICM is the **internal discipline layer** that governs how an individual agent
task is structured AFTER the orchestration layer (Hermes routing / swarm) has
decided *which* agent runs it. It is NOT a replacement for orchestration — it
provides auditability, predictable behavior, and lower token overhead at the
level of a single agent run.

The core mechanic is dangerously simple: **an agent's instructions live in
numbered, self-contained stage folders (markdown + scripts), not in inline
strings.** A stage folder holds:

    project/
    ├── 00_master.md          <- table of contents; maps a task to a stage folder
    ├── 01_intake/            <- instructions.md (role, inputs, good output) + scripts/
    ├── 02_research/
    ├── 03_drafting/
    ├── 04_verification/
    └── 05_output/

Why this matters here (the three spec integration points):
  2.1 Prompt/Skill layer  - every task is backed by folder markdown + a script,
                            never a bare inline prompt.
  2.2 Context compression - "progressive disclosure": only load the markdown for
                            the CURRENT stage, not the whole system context. This
                            is exactly what cuts per-call token load for cheaper
                            OpenRouter / swarm usage.
  2.3 Standardized format - one convention across every project (Aurora, Marlin,
                            ops, etc.) so new agents are fast to build/audit/port.

Division of labor (spec §3): ICM === sequential, single-agent, human-reviewed,
deterministic work. Swarm === concurrent, multi-agent reasoning/validation. This
module ships a tiny classifier that applies that rule so the routing layer
doesn't misuse one for the other.

Version: 1.0.0
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class StageFolder:
    """A numbered, self-contained stage (folder) in an ICM project."""

    number: int
    name: str
    path: Path
    instructions_md: Path
    scripts_dir: Path

    @property
    def slug(self) -> str:
        return f"{self.number:02d}_{self.name}"

    def instructions_text(self) -> str:
        if self.instructions_md.exists():
            return self.instructions_md.read_text(encoding="utf-8", errors="replace")
        return ""

    def scripts(self) -> List[str]:
        if not self.scripts_dir.exists():
            return []
        return sorted(p.name for p in self.scripts_dir.iterdir() if p.is_file())


@dataclass
class ICMProject:
    """An interpreted project rooted at a folder with a `00_master.md`."""

    root: Path
    master_md: Path
    stages: List[StageFolder] = field(default_factory=list)
    task_map: Dict[str, str] = field(default_factory=dict)  # task keyword -> slug

    # --------------------------------------------------------------- factory
    @classmethod
    def open(cls, project_dir: str | os.PathLike[str]) -> "ICMProject":
        root = Path(project_dir).resolve()
        master = root / "00_master.md"
        if not master.exists():
            raise FileNotFoundError(
                f"not an ICM project (missing 00_master.md) at {root}")
        stages = cls._scan_stages(root)
        task_map = cls._parse_task_map(master)
        return cls(root=root, master_md=master, stages=stages, task_map=task_map)

    @classmethod
    def _scan_stages(cls, root: Path) -> List[StageFolder]:
        """Discover numbered stage folders (NN_<name>)."""
        stages = []
        for d in sorted(root.iterdir()):
            if not d.is_dir():
                continue
            m = re.match(r"^(\d{2})_([a-zA-Z0-9_\-]+)$", d.name)
            if not m:
                continue
            num = int(m.group(1))
            name = m.group(2)
            stages.append(StageFolder(
                number=num, name=name, path=d,
                instructions_md=d / "instructions.md",
                scripts_dir=d / "scripts",
            ))
        stages.sort(key=lambda s: s.number)
        return stages

    @classmethod
    def _parse_task_map(cls, master: Path) -> Dict[str, str]:
        """Read 00_master.md and map task keywords -> stage slugs.

        The master is the ONLY file an orchestrator must read to know which
        stage folder to activate. It is a lightweight table of contents, not a
        task spec. Simple syntax:
            # stage, task
            ## 01_intake, intake payment
            ## 05_output, emit report
        """
        mapping: Dict[str, str] = {}
        text = master.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            line = line.strip().lstrip("#").strip()
            if "," not in line:
                continue
            stage, task = (p.strip() for p in line.split(",", 1))
            if not stage or not task:
                continue
            # stage may be given as slug (01_intake) or number (01)
            slug = stage if "_" in stage else stage + ""
            # resolve to an actual stage folder name if possible, else store raw
            mapping[task.lower()] = slug
        return mapping

    # ----------------------------------------------------------------- route
    def route(self, task: str) -> Optional[StageFolder]:
        """Map a task description to the most relevant stage folder.

        Uses the 00_master.md task map first (explicit), then a keyword
        fallback (stage name match). Returns None if nothing matches.
        """
        task_l = task.strip().lower()
        # 1) explicit task-map hit
        hit = self.task_map.get(task_l)
        if hit:
            for s in self.stages:
                if s.slug == hit or s.slug.endswith(hit):
                    return s
        # 2) keyword fallback: match a stage word OR a common stem/prefix in the
        #    task (e.g. "verify" matches stage "verification", "deploy" matches
        #    "deploy", "cad" matches "cad_export").
        tokens = re.findall(r"[a-z]+", task_l)
        for s in self.stages:
            for word in s.name.split("_"):
                if not word or len(word) < 3:
                    continue
                if word in task_l:
                    return s
                # stem match: a task token starts with this stage word (e.g.
                # "verif..." -> "verification") or vice versa
                for tok in tokens:
                    if tok.startswith(word[:5]) or word.startswith(tok[:5]):
                        return s
        return None

    # ------------------------------------ progressive disclosure (compression)
    def stage_context(self, stage: StageFolder) -> str:
        """Return ONLY the markdown instructions for the given stage.

        This is the progressive-disclosure core: the agent gets stage-specific
        instructions, not the whole project context. Blessedly cheap for the
        model caller (fewer tokens per OpenRouter call). Includes a pointer to
        the stage's scripts so the model delegates deterministic work, not tries
        to do it inline.
        """
        parts = [stage.instructions_text()]
        scripts = stage.scripts()
        if scripts:
            parts.append("# Deterministic helpers (do not hand-reason these)\n- "
                         + "\n- ".join(f"`scripts/{s}`" for s in scripts))
        return "\n\n".join(p for p in parts if p)

    def master_context(self) -> str:
        """Return the small table-of-contents (the whole master file)."""
        return self.master_md.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Sequential vs swarm classifier (division of labor, spec §3)
# ---------------------------------------------------------------------------

# Stage/verb markers that indicate deterministic, sequential, single-agent work.
_SEQUENTIAL_HINTS = [
    "intake", "compliance", "citation", "verify", "export", "deploy",
    "bugfix", "convert", "format", "validate", "check", "render", "cad",
    "build", "compile", "review", "proofread", "clean", "ocr", "ingest",
]
# Markers that indicate judgment-heavy, multi-model reasoning (keep in swarm).
_SWARM_HINTS = [
    "classif", "legal", "reason", "cross-valid", "cross review", "debate",
    "character", "creativity", "generat", "plot", "clue", "consistency",
    "horizon", "assess", "judgment", "arbitrat", "adjudicat",
]


def classify(task: str) -> str:
    """Return 'sequential' (ICM) or 'swarm' for a task description.

    Implements the spec's division of labor: predictable, auditable,
    single-agent work -> sequential ICM; cross-check / debate / creative
    generation -> swarm. Judge a task by its dominant signal.
    """
    t = task.lower()
    for kw in _SWARM_HINTS:
        if kw in t:
            return "swarm"
    for kw in _SEQUENTIAL_HINTS:
        if kw in t:
            return "sequential"
    # default: simple, auditable work is best as deterministic sequential
    return "sequential"


def should_use_swarm(task: str) -> bool:
    """True when the task should go to the multi-agent swarm layer, not ICM."""
    return classify(task) == "swarm"


__all__ = [
    "ICMProject",
    "StageFolder",
    "classify",
    "should_use_swarm",
    "__version__",
]
__version__ = "1.0.0"