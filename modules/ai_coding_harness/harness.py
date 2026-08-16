"""AI Coding Harness core — pure, network-free agentic Claude-Code workflow engine.

Grounded in four pulled JE Van Clief transcripts about using Claude Code to go
from a prompt to a working, hosted artifact (site / HTML / SVG / React / video):

  * ozkx_eUfjY0  "No Wix. No Squarespace. Just Claude Code and GitHub." — the
    prompt-to-site workflow: build context first, then prompt the agent to
    scaffold and generate the site, and host it (here: the scaffold step
    produces the free-hosting-friendly project layout).
  * rHDA0WMXzy4  "Stop Copy-Pasting Into Claude. Install Claude Code and
    Actually Use It." — installing Claude Code, working from the terminal, and
    letting the agent scaffold folders/projects instead of hand-writing files.
  * izMBiWG3L24  "SVG to React: Turning Illustrator Designs into Web
    Animations with Claude Code." — context setup (CLAUDE.md / project.md so
    the agent knows *where to go*), generating SVG/React animation artifacts
    from source SVGs, and the long natural-language iterate-and-verify loop.
  * vyN7ITKcGXU  "Claude Code + Remotion: Build Long-Form AI Animations from a
    Script." — the multi-stage pipeline (script -> specification/storyboard ->
    scenes -> render), each stage an editable, promptable artifact, plus the
    install/scaffold of Remotion templates and skills.

None of it needs a network, numpy, pandas or requests: this is the *planning,
scaffolding, prompting, iteration and verification* layer that makes that
workflow repeatable and testable. It operates only on strings and local files.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

__all__ = [
    "ArtifactKind",
    "PipelineStage",
    "ContextSpec",
    "ScaffoldSpec",
    "Artifact",
    "VerificationResult",
    "GenerationPlan",
    "AiCodingHarness",
    "default_context",
    "framework_for_kind",
    "__version__",
]
__version__ = "1.0.0"

# ---------------------------------------------------------------------------
# Enums grounded in the transcripts
# ---------------------------------------------------------------------------


class ArtifactKind(str, Enum):
    """The kinds of artfacts Van Clief generates from a prompt."""

    SITE = "site"            # full static site (ozkx_eUfjY0)
    HTML = "html"            # single-page artifact
    SVG = "svg"              # source illustrations/characters (izMBiWG3L24)
    REACT = "react"          # programmatic React animation (izMBiWG3L24)
    ANIMATION = "animation"  # script->video pipeline (vyN7ITKcGXU)


class PipelineStage(str, Enum):
    """Editable pipeline stages from the Remotion workflow (vyN7ITKcGXU).

    Van Clief: \"write a script ... then ... write a specification ... I can
    have the AI automate all four of these steps, or it can touch none of the
    steps except for one.\"
    """

    SCRIPT = "script"                # long-form / short-form source text
    SPECIFICATION = "specification"  # storyboard/spec: beats, visuals, colors
    SCENES = "scenes"                # per-scene React/SVG components
    RENDER = "render"                # composed/animated output
    VERIFY = "verify"                # the final check before shipping


# ---------------------------------------------------------------------------
# Context setup  (grounding: CLAUDE.md / project.md in izMBiWG3L24)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContextSpec:
    """A piece of agent context, roughly one CLAUDE.md / project.md.

    From izMBiWG3L24: the agent has \"a project MD ... that shows where to go
    for certain folders, where to get the original SVG, so instead of it
    having to sit here and read through the whole code base ... it already has
    built-in context of where it needs to go.\"
    """

    role: str
    read_paths: List[str] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)
    notes: str = ""

    def build(self) -> str:
        """Render this spec as a CLAUDE.md-style context block."""
        lines = [f"# {self.role}", ""]
        if self.read_paths:
            lines.append("## Read first")
            lines.extend(f"- {p}" for p in self.read_paths)
            lines.append("")
        if self.skills:
            lines.append("## Skills to use")
            lines.extend(f"- {s}" for s in self.skills)
            lines.append("")
        if self.notes:
            lines.append(f"## Notes\n{self.notes}\n")
        return "\n".join(lines).strip() + "\n"


def default_context() -> ContextSpec:
    """The baseline agent-context template used across the four transcripts."""
    return ContextSpec(
        role="JE Van Clief agentic coding harness",
        read_paths=["CLAUDE.md", "projects/*/context.md", "src/svg/"],
        skills=["remotion", "ui-ux-pro", "terminal"],
        notes=(
            "Work in folders, not single files. Read context first so you know "
            "where to go. Generate editable artifacts and iterate on them."
        ),
    )


# ---------------------------------------------------------------------------
# Scaffolding  (grounding: ozkx_eUfjY0, vyN7ITKcGXU folder workspaces)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScaffoldSpec:
    """A project folder to scaffold, mirroring Van Clief's folder workspaces.

    vyN7ITKcGXU: \"this is all just folders. No crazy apps. I have a folder for
    my script lab ... and a folder that has my animation studio.\"
    """

    name: str
    kind: ArtifactKind
    context: Optional[ContextSpec] = None
    subfolders: List[str] = field(default_factory=list)

    def resolved_subfolders(self) -> List[str]:
        """Subfolders with sensible defaults per artifact kind."""
        if self.subfolders:
            return list(self.subfolders)
        if self.kind == ArtifactKind.ANIMATION:
            return ["scripts", "specs", "scenes", "renders"]
        if self.kind == ArtifactKind.SITE:
            return ["pages", "assets", "components", "public"]
        if self.kind == ArtifactKind.REACT:
            return ["src/components", "src/svg", "public"]
        if self.kind == ArtifactKind.SVG:
            return ["svg", "src"]
        return ["public"]


# ---------------------------------------------------------------------------
# Artifacts and verification
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Artifact:
    """An editable generated artifact (site page, SVG, React component...)."""

    kind: ArtifactKind
    name: str
    body: str
    revision: int = 0

    def clone(self, **overrides: Any) -> "Artifact":
        return Artifact(
            kind=overrides.get("kind", self.kind),
            name=overrides.get("name", self.name),
            body=overrides.get("body", self.body),
            revision=overrides.get("revision", self.revision + 1),
        )


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of the verify loop for one artifact."""

    passed: bool
    checks: Dict[str, bool] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Generation plan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GenerationPlan:
    """A prompt -> artifact plan, the unit the agent is asked to execute."""

    prompt: str
    kind: ArtifactKind
    name: str
    context: Optional[ContextSpec] = None

    def prompt_with_context(self) -> str:
        if self.context is None:
            return self.prompt
        return f"{self.context.build()}\n\nTASK: {self.prompt}"


def framework_for_kind(kind: ArtifactKind) -> str:
    """What the underlying generator would use, per the transcripts."""
    return {
        ArtifactKind.SITE: "plain HTML/CSS (free GitHub Pages deploy)",
        ArtifactKind.HTML: "single HTML file",
        ArtifactKind.SVG: "labeled SVG (left iris, left eye, eyebrows...)",
        ArtifactKind.REACT: "React + Remotion components",
        ArtifactKind.ANIMATION: "Remotion + Node.js render pipeline (script->spec->scenes)",
    }[kind]


# ---------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------


class AiCodingHarness:
    """Repeatable agentic-coding workflow engine.

    Encapsulates the loop Van Clief uses every time: set up context, scaffold
    a project in folders, generate an artifact from a prompt, then iterate and
    verify until it passes. Everything is pure/offline so it is unit-testable.
    """

    def __init__(
        self,
        context: Optional[ContextSpec] = None,
        max_iterations: int = 5,
    ) -> None:
        self.context = context or default_context()
        self.max_iterations = max_iterations
        # Anniversary counter so 'iteration' is observable deterministically.
        self._revisions: Dict[str, int] = {}

    # -- context ------------------------------------------------------------
    def build_context(self, spec: Optional[ContextSpec] = None) -> str:
        return (spec or self.context).build()

    # -- scaffolding --------------------------------------------------------
    def scaffold(self, spec: ScaffoldSpec, root_dir: Path) -> List[Path]:
        """Create the project folder tree plus a CLAUDE.md context file."""
        root = root_dir / spec.name
        root.mkdir(parents=True, exist_ok=True)
        written: List[Path] = []
        for sub in spec.resolved_subfolders():
            d = root / sub
            d.mkdir(parents=True, exist_ok=True)
            written.append(d)
        ctx = spec.context or self.context
        claude = root / "CLAUDE.md"
        claude.write_text(ctx.build(), encoding="utf-8")
        written.append(claude)
        return written

    # -- prompt -> artifact -------------------------------------------------
    def plan(
        self,
        prompt: str,
        kind: ArtifactKind,
        name: Optional[str] = None,
        context: Optional[ContextSpec] = None,
    ) -> GenerationPlan:
        return GenerationPlan(
            prompt=prompt,
            kind=kind,
            name=name or f"{kind.value}-{len(self._revisions) + 1}",
            context=context or self.context,
        )

    def generate(self, plan: GenerationPlan) -> Artifact:
        """Produce a deterministic, editable artifact body from a prompt.

        This is the offline stand-in for the model call: it keeps the *shape*
        of the workflow (prompt -> editable code/text) without needing a model.
        """
        rev = self._revisions.get(plan.name, 0) + 1
        self._revisions[plan.name] = rev
        kind = plan.kind
        if kind == ArtifactKind.SVG:
            body = (
                f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" '
                f'aria-label="generated: {plan.prompt}">\n'
                f'  <circle cx="50" cy="40" r="18" fill="#7c5cff"/>\n'
                f'  <path d="M32 90 Q50 55 68 90Z" fill="#2b2b2b"/>\n'
                f"</svg>\n"
            )
        elif kind == ArtifactKind.REACT or kind == ArtifactKind.ANIMATION:
            body = (
                f"// generated-from: {plan.prompt}\n"
                f"export const {plan.name} = () => (\n"
                f'  <div className="scene" data-render="remotion">\n'
                f"    <svg width=\"80\" height=\"80\">"
                f"<circle cx=\"40\" cy=\"40\" r=\"20\" /></svg>\n"
                f"  </div>\n);\n"
            )
        elif kind == ArtifactKind.SITE:
            body = (
                f"<!doctype html>\n<html lang=\"en\">\n<head>\n"
                f'  <meta charset="utf-8"/>\n  <title>{plan.name}</title>\n'
                f"  <style>body{{font-family:system-ui;margin:3rem}}</style>\n"
                f"</head>\n<body>\n  <h1>{plan.name}</h1>\n"
                f"  <p>{plan.prompt}</p>\n</body>\n</html>\n"
            )
        else:  # HTML and everything else fall back to a plain HTML file
            body = (
                f"<!doctype html>\n<html><body>\n"
                f"  <h1>{plan.name}</h1>\n  <p>{plan.prompt}</p>\n"
                f"</body></html>\n"
            )
        return Artifact(kind=kind, name=plan.name, body=body, revision=rev)

    # -- verification -------------------------------------------------------
    def verify(self, artifact: Artifact) -> VerificationResult:
        """The check loop: non-empty, well-formed for its kind, editable."""
        checks: Dict[str, bool] = {
            "nonempty": bool(artifact.body and artifact.body.strip()),
            "has_revision": artifact.revision >= 1,
        }
        notes: List[str] = []
        if artifact.kind in (ArtifactKind.SITE, ArtifactKind.HTML):
            checks["has_html_root"] = "<html" in artifact.body
            checks["has_body"] = "<body" in artifact.body
        elif artifact.kind == ArtifactKind.SVG:
            checks["has_svg_root"] = (
                "<svg" in artifact.body and "</svg>" in artifact.body
            )
            checks["is_labeled"] = "aria-label" in artifact.body
        elif artifact.kind in (ArtifactKind.REACT, ArtifactKind.ANIMATION):
            checks["has_component"] = "export const" in artifact.body
            checks["is_remotion"] = "remotion" in artifact.body
        if not checks.get("has_html_root", True):
            notes.append("missing <html> root")
        if not checks.get("has_svg_root", True):
            notes.append("missing svg root tag")
        if not checks.get("has_body", True):
            notes.append("missing <body>")
        if not checks.get("has_component", True):
            notes.append("missing exported component")
        passed = all(checks.values())
        return VerificationResult(passed=passed, checks=checks, notes=notes)

    # -- iteration loop -----------------------------------------------------
    def iterate(self, artifact: Artifact, max_iterations: Optional[int] = None) -> Artifact:
        """Re-generate (bump revision) until the artifact verifies.

        Mirrors izMBiWG3L24's long natural-language edit loop and the
        verify-before-ship stage of the pipeline.
        """
        limit = max_iterations if max_iterations is not None else self.max_iterations
        current = artifact
        for _ in range(limit):
            if self.verify(current).passed:
                return current
            current = current.clone()
        return current

    # -- pipeline -----------------------------------------------------------
    def run_stages(self, script: str) -> Dict[PipelineStage, Artifact]:
        """Advance a script through the Remotion pipeline stages.

        vyN7ITKcGXU: script -> specification -> scenes -> render, each one an
        editable promptable artifact; VERIFY reports the final gate.
        """
        result: Dict[PipelineStage, Artifact] = {}
        plan = self.plan(script, ArtifactKind.ANIMATION, name="longform")
        stages = [
            (PipelineStage.SCRIPT, "script text prepared"),
            (PipelineStage.SPECIFICATION, "storyboard/spec written"),
            (PipelineStage.SCENES, "per-scene scenes generated"),
            (PipelineStage.RENDER, "composed output rendered"),
        ]
        for stage, delta in stages:
            art = plan
            if stage is PipelineStage.RENDER:
                # compose the scenes into a real renderable Remotion component
                body = self.generate(self.plan(
                    f"compose {delta}: {script}", ArtifactKind.ANIMATION,
                    name=plan.name,
                )).body
            else:
                body = f"// stage: {stage.value}\n// {delta}\n" + art.prompt_with_context()
            result[stage] = Artifact(
                kind=ArtifactKind.ANIMATION,
                name=plan.name,
                body=body,
                revision=self._bump(plan.name),
            )
        result[PipelineStage.VERIFY] = self.iterate(result[PipelineStage.RENDER])
        return result

    def _bump(self, key: str) -> int:
        self._revisions[key] = self._revisions.get(key, 0) + 1
        return self._revisions[key]


def default_harness() -> AiCodingHarness:
    """Facade: build the core engine with its default context."""
    return AiCodingHarness()
