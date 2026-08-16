"""Video as Code — spec-driven AI animation pipeline (pure core).

Grounded entirely in the JEVanClief talk *"Video as Code: My AI Animation
Stack"* (https://www.youtube.com/watch?v=yEa6dgh7wuc). The central thesis of
that talk is that AI video/animation generation should be treated as **software
engineering applied to a creative problem**, and that the *hard work is not the
AI and not the code — it is the spec*::

    "The hard work isn't the AI. It's not the code, it's the spec."

The speaker's workflow is a document-driven pipeline::

    markdown spec (the "brief")
      -> coding agent (Claude Code)
      -> Remotion component library
      -> video editing software (Cap Cut)

Each scene is a React component; "a video is just a function of images over
time."  The critical quality lever is how *tight* the spec is::

    "A loose spec or a poor spec means that Claude or your AI agent makes more
     interpretive choices or hallucinates more. A tight spec means you're
     directing it at every beat."

And the motivating quote (attributed to David Ugarte)::

    "Give me the freedom of a tight brief."

This module is **network-free and stdlib-only**. It implements the
spec-driven generation pipeline as data:

* ``VideoSpec`` / ``Scene`` — the structured form of the markdown brief.
* ``parse_spec_markdown`` / ``spec_from_dict`` / ``spec_to_dict`` — describe a
  brief as a document and move it between representations.
* ``validate_spec`` — warns on missing / loose fields.
* ``tightness_score`` — a spec-quality score in ``[0, 1]`` derived from
  structuredness (metadata, per-scene detail, timing, script).
* ``hallucination_risk_estimate`` — a documented heuristic mapping tightness to
  hallucination risk, inverse to tightness, faithful to the talk's claim.
* ``PipelineRunner`` — spec -> (optional generation) -> assembly manifest ->
  final artifact.  Generation is an injectable, deterministic ``StubGenerator``;
  the ``RealGenerator`` interface degrades gracefully (``ok: False``) when no
  external tooling is available (network-free).

Version: 1.0.0
Python: 3.10+
"""

from __future__ import annotations

import abc
import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Sequence

# ---------------------------------------------------------------------------
# Documented constants grounded in the transcript
# ---------------------------------------------------------------------------

# The transcript's four-stage stack, in order.
VIDEO_AS_CODE_STACK: tuple[str, ...] = (
    "spec (markdown brief)",
    "coding agent (Claude Code)",
    "Remotion component library",
    "video editing software (Cap Cut)",
)

# The motivating quote from the talk.
TIGHT_BRIEF_QUOTE = "Give me the freedom of a tight brief."

# Heuristic referenced in the talk: loose spec -> more interpretive choices /
# more hallucination; tight spec -> directing the agent at every beat.
LOOSE_SPEC_CLAIM = (
    "A loose spec means the AI agent makes more interpretive choices or "
    "hallucinates more; a tight spec means you are directing it at every beat."
)

# Required metadata keys at the top of a brief.
_SPEC_METADATA_KEYS: tuple[str, ...] = ("title", "thesis", "arc")

# Per-scene fields that contribute to spec detail (per the talk: descriptions
# of what happens, notes on timing and emphasis, visual elements, background).
_SCENE_DETAIL_FIELDS: tuple[str, ...] = (
    "description",
    "visual_elements",
    "emphasis",
    "background_notes",
    "script_lines",
)

# Weights for the tightness score. Sum = 1.00.
_TIGHTNESS_WEIGHTS: dict[str, float] = {
    "metadata": 0.20,  # title + thesis + arc present
    "structure": 0.20,  # at least one scene (per-scene breakdown present)
    "scene_detail": 0.35,  # per-scene required fields filled
    "timing": 0.15,  # timing_seconds given and positive
    "script": 0.10,  # script_lines present per scene
}

# Thresholds used to bucket a hallucination risk *estimate* into a label.
# Derived so that a tight spec (which yields low risk) maps to LOW:
#   risk <= 0.25 (tightness >= 0.75) -> LOW
#   risk <= 0.50 (tightness >= 0.50) -> MEDIUM
#   else (tightness < 0.50)          -> HIGH
_RISK_LABEL_BOUNDS = (0.25, 0.5)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Scene:
    """A single shot/beat of a video-as-code brief.

    Mirrors the transcript's description of a spec: "headings for each scene,
    descriptions of what happens, notes on timing and emphasis."

    Attributes:
        scene_id: Stable identifier (e.g. "scene_1").
        description: Prose description of what happens in the scene.
        timing_seconds: Target duration in seconds (> 0 when specified).
        visual_elements: List of concrete visual/on-screen elements.
        emphasis: What must "land" in this scene (a beat to direct the agent).
        background_notes: What stays in the background / low-key.
        script_lines: Spoken/scripted lines, if any, for this scene.
    """

    scene_id: str
    description: str = ""
    timing_seconds: float | None = None
    visual_elements: list[str] = field(default_factory=list)
    emphasis: str = ""
    background_notes: str = ""
    script_lines: list[str] = field(default_factory=list)


@dataclass
class VideoSpec:
    """The structured form of a video-as-code markdown brief.

    Attributes:
        title: Title of the video.
        thesis: The central idea / thesis ("What's the thesis of this video?").
        arc: The narrative arc ("What's the arc?").
        scenes: Ordered per-scene breakdown.
        style_guide: Optional free-form dict describing the visual language
            (color palette, animation timing, minimal text), per the talk.
        component_registry: Optional list of reusable building blocks
            (text animations, backgrounds, transitions, data visualizations).
    """

    title: str = ""
    thesis: str = ""
    arc: str = ""
    scenes: list[Scene] = field(default_factory=list)
    style_guide: dict[str, str] = field(default_factory=dict)
    component_registry: list[str] = field(default_factory=list)


@dataclass
class SpecValidationReport:
    """Result of validating a :class:`VideoSpec`.

    ``errors`` are correctness problems (invalid structure).  ``warnings`` and
    ``missing_fields`` / ``loose_fields`` capture the *loose* spec signals that,
    per the transcript, increase hallucination risk.
    """

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    loose_fields: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Serialization / parsing
# ---------------------------------------------------------------------------


def _markdown_field_value(text: str, aliases: Sequence[str]) -> str | None:
    """Return the first `<Alias>: <rest>` value that appears in *text*."""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        for alias in aliases:
            lowered = stripped.lower()
            if lowered.startswith(alias.lower()) and ":" in stripped:
                _, _, value = stripped.partition(":")
                value = value.strip()
                if value:
                    return value
    return None


def parse_spec_markdown(text: str) -> VideoSpec:
    """Parse a markdown video brief into a structured :class:`VideoSpec`.

    This is the markdown -> structure step of the "spec as code" pipeline.  The
    expected shape mirrors the speaker's description of a spec — headings for
    each scene, descriptions of what happens, notes on timing and emphasis::

        # Title of the video

        Thesis: the central idea
        Arc: the narrative arc

        ## Scene 1
        Description: what happens in this scene.
        Emphasis: the beat that must land.
        Background: what stays in the background.
        Timing: 12 seconds
        Visuals:
        - an orbiting hexagon
        Script:
        - hello, and welcome.

    Unknown keys are tolerated; the caller sees missing fields in
    :func:`validate_spec`.
    """
    spec = VideoSpec()
    lines = text.splitlines()

    prelude: list[str] = []  # lines before the first scene heading
    current_scene: Scene | None = None
    pending_key: str | None = None
    pending_lines: list[str] = []

    def flush_pending() -> None:
        nonlocal pending_key, pending_lines
        if current_scene is not None and pending_key is not None:
            value = " ".join(pending_lines).strip()
            if pending_key == "visuals":
                current_scene.visual_elements = _split_items(pending_lines)
            elif pending_key == "script":
                current_scene.script_lines = _split_items(pending_lines)
            elif value:
                if pending_key == "description":
                    current_scene.description = value
                elif pending_key == "emphasis":
                    current_scene.emphasis = value
                elif pending_key == "background":
                    current_scene.background_notes = value
                elif pending_key == "timing":
                    current_scene.timing_seconds = _parse_seconds(value)
        pending_key, pending_lines = None, []

    scene_index = 0
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("##"):
            flush_pending()
            heading = re.sub(r"^#+\s*", "", stripped)
            scene_index += 1
            current_scene = Scene(scene_id=f"scene_{scene_index}")
            spec.scenes.append(current_scene)
            continue

        if current_scene is None:
            prelude.append(stripped)
            continue

        # Scene body: field key or continuation line.
        lower = stripped.lower()
        if lower.startswith("description:"):
            flush_pending(); pending_key = "description"; pending_lines = [stripped.split(":", 1)[1]]
        elif lower.startswith("emphasis:"):
            flush_pending(); pending_key = "emphasis"; pending_lines = [stripped.split(":", 1)[1]]
        elif lower.startswith("background:"):
            flush_pending(); pending_key = "background"; pending_lines = [stripped.split(":", 1)[1]]
        elif lower.startswith("timing:"):
            flush_pending(); pending_key = "timing"; pending_lines = [stripped.split(":", 1)[1]]
        elif lower.startswith("visuals:") or lower.startswith("visual elements:"):
            flush_pending(); pending_key = "visuals"; pending_lines = [stripped.split(":", 1)[1]]
        elif lower.startswith("script:") or lower.startswith("script lines:"):
            flush_pending(); pending_key = "script"; pending_lines = [stripped.split(":", 1)[1]]
        elif pending_key is not None and stripped.startswith(("-", "*")):
            pending_lines.append(stripped.lstrip("-* ").strip())
        elif pending_key is not None and not stripped.endswith(":") and not stripped.startswith("#"):
            pending_lines.append(stripped)
        else:
            # Trailing free-text without an active field: ignore for structure.
            continue
    flush_pending()

    # Metadata comes from the prelude (title heading + `Key: value` lines).
    spec.title = _markdown_field_value("\n".join(prelude), ("title",)) or _heading_title(prelude)
    spec.thesis = _markdown_field_value("\n".join(prelude), ("thesis",)) or ""
    spec.arc = _markdown_field_value("\n".join(prelude), ("arc",)) or ""
    return spec


def _heading_title(prelude: Sequence[str]) -> str:
    for line in prelude:
        if line.startswith("#") and not line.startswith("##"):
            return re.sub(r"^#+\s*", "", line).strip()
    return ""


def _parse_seconds(value: str) -> float | None:
    """Parse a timing like ``12``, ``12s``, ``12 sec`` or ``0:42`` into seconds."""
    value = value.strip().lower()
    for suffix in ("seconds", "sec", "s"):
        if value.endswith(suffix):
            value = value[: -len(suffix)].strip()
            break
    if ":" in value:
        parts = value.split(":")
        try:
            minutes = float(parts[0])
            seconds = float(parts[1])
            return minutes * 60.0 + seconds
        except ValueError:
            return None
    try:
        return float(value)
    except ValueError:
        return None


def _split_items(lines: Sequence[str]) -> list[str]:
    """Turn list-lines into trimmed strings, dropping empty/header residue."""
    out: list[str] = []
    for line in lines:
        item = line.strip().lstrip("-* ").strip()
        if item and item not in out:
            out.append(item)
    return out


def spec_to_dict(spec: VideoSpec) -> dict[str, Any]:
    """Serialize a :class:`VideoSpec` to a plain JSON-compatible dict."""
    return asdict(spec)


def spec_from_dict(data: dict[str, Any]) -> VideoSpec:
    """Deserialize a plain dict into a :class:`VideoSpec`.

    Raises:
        ValueError: if the dict is not a valid spec mapping.
    """
    if not isinstance(data, dict):
        raise ValueError("spec data must be a mapping")
    scenes: list[Scene] = []
    for raw_scene in data.get("scenes", []) or []:
        if not isinstance(raw_scene, dict):
            raise ValueError("each scene must be a mapping")
        raw_elems = raw_scene.get("visual_elements", []) or []
        raw_script = raw_scene.get("script_lines", []) or []
        scenes.append(
            Scene(
                scene_id=str(raw_scene.get("scene_id", "")),
                description=str(raw_scene.get("description", "") or ""),
                timing_seconds=raw_scene.get("timing_seconds"),
                visual_elements=[str(e) for e in raw_elems],
                emphasis=str(raw_scene.get("emphasis", "") or ""),
                background_notes=str(raw_scene.get("background_notes", "") or ""),
                script_lines=[str(s) for s in raw_script],
            )
        )
    return VideoSpec(
        title=str(data.get("title", "") or ""),
        thesis=str(data.get("thesis", "") or ""),
        arc=str(data.get("arc", "") or ""),
        scenes=scenes,
        style_guide=dict(data.get("style_guide", {}) or {}),
        component_registry=[str(c) for c in (data.get("component_registry", []) or [])],
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_spec(spec: VideoSpec) -> SpecValidationReport:
    """Validate a spec and surface *loose* / missing fields as warnings.

    Purely structural: it cannot judge prose quality, but it faithfully flags
    the absence of the fields the transcript emphasises (description, timing,
    emphasis) — the absence of which is the definition of a loose spec.
    """
    errors: list[str] = []
    warnings: list[str] = []
    missing_fields: list[str] = []
    loose_fields: list[str] = []

    for key in _SPEC_METADATA_KEYS:
        if not getattr(spec, key, "").strip():
            errors.append(f"missing metadata field: {key!r}")

    if not spec.scenes:
        errors.append("spec has no scenes (no per-scene breakdown)")
    else:
        for scene in spec.scenes:
            if not scene.scene_id.strip():
                errors.append("scene with empty scene_id")
            if not scene.description.strip():
                missing_fields.append(f"{scene.scene_id}.description")
                warnings.append(f"{scene.scene_id}: no description of what happens")
            if not scene.visual_elements:
                loose_fields.append(f"{scene.scene_id}.visual_elements")
                warnings.append(f"{scene.scene_id}: no explicit visual elements")
            if not scene.emphasis.strip():
                missing_fields.append(f"{scene.scene_id}.emphasis")
                warnings.append(f"{scene.scene_id}: no emphasis/beat specified")
            if not scene.background_notes.strip():
                loose_fields.append(f"{scene.scene_id}.background_notes")
                warnings.append(f"{scene.scene_id}: no background notes")
            if not scene.timing_seconds or scene.timing_seconds <= 0:
                missing_fields.append(f"{scene.scene_id}.timing_seconds")
                warnings.append(f"{scene.scene_id}: timing not specified")
            if not scene.script_lines:
                loose_fields.append(f"{scene.scene_id}.script_lines")
                warnings.append(f"{scene.scene_id}: no script lines")

    return SpecValidationReport(
        valid=not errors,
        errors=errors,
        warnings=warnings,
        missing_fields=missing_fields,
        loose_fields=loose_fields,
    )


# ---------------------------------------------------------------------------
# Tightness scoring
# ---------------------------------------------------------------------------


def _detail_fraction(scene: Scene) -> float:
    """Fraction of per-scene detail fields that are filled, in ``[0, 1]``."""
    filled = 0.0
    for field_name in _SCENE_DETAIL_FIELDS:
        if field_name == "timing_seconds":
            filled += 1.0 if (scene.timing_seconds or 0) > 0 else 0.0
        else:
            value = getattr(scene, field_name, "")
            filled += 1.0 if (isinstance(value, list) and value) or (value not in (None, "")) else 0.0
    return filled / len(_SCENE_DETAIL_FIELDS)


def tightness_score(spec: VideoSpec) -> float:
    """Compute a spec-quality / tightness score in ``[0, 1]``.

    Follows from the transcript directly: a tight spec is one that directs the
    agent "at every beat" — metadata (thesis, arc), a per-scene breakdown,
    timing, and emphasis.  The score is a weighted sum of five components:

    * ``metadata`` (20%)   — title, thesis and arc are present.
    * ``structure`` (20%)  — the spec has at least one scene.
    * ``scene_detail`` (35%) — per-scene required fields are filled.
    * ``timing`` (15%)     — timing_seconds given and > 0 for each scene.
    * ``script`` (10%)     — script lines present per scene.

    A higher tightness implies the agent makes fewer interpretive choices.
    """
    if not isinstance(spec, VideoSpec):
        raise TypeError("tightness_score expects a VideoSpec")
    total = 0.0

    meta = sum(1 for key in _SPEC_METADATA_KEYS if getattr(spec, key, "").strip())
    total += _TIGHTNESS_WEIGHTS["metadata"] * (meta / len(_SPEC_METADATA_KEYS))

    total += _TIGHTNESS_WEIGHTS["structure"] * (1.0 if spec.scenes else 0.0)

    if spec.scenes:
        total += _TIGHTNESS_WEIGHTS["scene_detail"] * (
            sum(_detail_fraction(s) for s in spec.scenes) / len(spec.scenes)
        )

    if spec.scenes:
        timing_ok = sum(1 for s in spec.scenes if (s.timing_seconds or 0) > 0)
        total += _TIGHTNESS_WEIGHTS["timing"] * (timing_ok / len(spec.scenes))

    if spec.scenes:
        script_ok = sum(1 for s in spec.scenes if s.script_lines)
        total += _TIGHTNESS_WEIGHTS["script"] * (script_ok / len(spec.scenes))

    return round(_clamp01(total), 4)


def hallucination_risk_label(risk: float) -> str:
    """Map a risk estimate to LOW / MEDIUM / HIGH."""
    low_bound, medium_bound = _RISK_LABEL_BOUNDS
    if risk <= low_bound:
        return "LOW"
    if risk <= medium_bound:
        return "MEDIUM"
    return "HIGH"


def hallucination_risk_estimate(tightness: float) -> float:
    """Estimate hallucination risk ``in [0, 1]`` given a tightness score.

    Documented heuristic, faithful to the transcript's claim that a loose spec
    makes the agent "make more interpretive choices or hallucinate more" while a
    tight spec "directs it at every beat".  Risk is therefore **inverse** to
    tightness:

        risk(tightness) = clamp(1 - tightness, 0, 1)

    * ``tightness = 1.0`` (fully directed)  -> risk ``0.0`` (LOW)
    * ``tightness = 0.75``                 -> risk ``0.25`` (LOW)
    * ``tightness = 0.5`` (half loose)      -> risk ``0.5`` (MEDIUM)
    * ``tightness = 0.25``                 -> risk ``0.75`` (HIGH)
    * ``tightness = 0.0`` (no spec)         -> risk ``1.0`` (HIGH)

    This is a deliberately simple monotone-decreasing mapping documented for
    auditability; it is an estimate, not a measurement.
    """
    return round(_clamp01(1.0 - _clamp01(tightness)), 4)


# ---------------------------------------------------------------------------
# Generation stage (network-free, injectable)
# ---------------------------------------------------------------------------


@dataclass
class SceneRender:
    """The output of generating one scene.

    Attributes:
        scene_id: The generating scene's id.
        component_name: The Remotion-style React component name assembled.
        ok: Whether generation succeeded.
        note: Human-readable note (errors, or deterministic detail).
        payload: Deterministic/descriptive payload for the scene.
    """

    scene_id: str
    component_name: str
    ok: bool = True
    note: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


class GenerationError(Exception):
    """Raised when a generator cannot honour an :class:`VideoSpec`."""


class Generator(abc.ABC):
    """Abstract generation stage of the pipeline.

    Implementations map a spec (or a single scene) to a :class:`SceneRender`.
    """

    def generate_scene(self, scene: Scene) -> SceneRender:
        """Generate a single scene. Must be deterministic for stable tests."""
        raise NotImplementedError

    def generate(self, spec: VideoSpec) -> list[SceneRender]:
        """Generate every scene of a spec, in order."""
        return [self.generate_scene(scene) for scene in spec.scenes]


class RealGenerator(Generator):
    """Interface for real external tooling (e.g. Claude Code + Remotion).

    Because this module is **network-free**, no real tooling is attached by
    default.  When ``tooling`` is ``None`` this generator degrades gracefully:
    every call returns a ``SceneRender(ok=False)`` signalling that generation
    cannot proceed offline — exactly the graceful-degradation contract requested.
    A caller may inject a ``tooling`` callable to model a live backend.
    """

    def __init__(self, tooling: Any = None) -> None:
        self._tooling = tooling

    def generate_scene(self, scene: Scene) -> SceneRender:
        if self._tooling is None:
            return SceneRender(
                scene_id=scene.scene_id,
                component_name=f"{_component_name(scene)}Unavailable",
                ok=False,
                note="no generation tooling available (network-free); degraded gracefully",
            )
        try:
            result = self._tooling(scene)
            if isinstance(result, SceneRender):
                return result
            return SceneRender(
                scene_id=scene.scene_id,
                component_name=_component_name(scene),
                ok=True,
                note="delegated to injected tooling",
                payload=dict(result or {}),
            )
        except Exception as exc:  # noqa: BLE001 - degrade, don't crash the pipeline
            return SceneRender(
                scene_id=scene.scene_id,
                component_name=f"{_component_name(scene)}Error",
                ok=False,
                note=f"tooling raised: {exc}",
            )


class StubGenerator(Generator):
    """Deterministic, network-free generation for testing the pipeline.

    Produces stable output: the same spec always yields byte-identical renders
    (render ids are content hashes), so pipeline tests are reproducible.
    """

    def generate_scene(self, scene: Scene) -> SceneRender:
        digest = hashlib.sha256(
            f"{scene.scene_id}|{scene.description}|{scene.timing_seconds}".encode()
        ).hexdigest()[:12]
        return SceneRender(
            scene_id=scene.scene_id,
            component_name=_component_name(scene),
            ok=True,
            note="deterministic stub render (hash=%s)" % digest,
            payload={
                "scene_id": scene.scene_id,
                "timing_seconds": scene.timing_seconds,
                "component": _component_name(scene),
                "digest": digest,
            },
        )


def _component_name(scene: Scene) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "", scene.scene_id.title().replace("_", " ")) or "Scene"
    return f"{base}Component"


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------


@dataclass
class AssemblyManifest:
    """The assembly artifact produced from a spec.

    Attributes:
        spec_title: Title of the source brief.
        source: Path or description of the source document, if any.
        total_scenes: Number of scenes assembled.
        total_duration_seconds: Sum of per-scene timings.
        tightness: Computed tightness score.
        hallucination_risk: Estimated hallucination risk.
        risk_label: LOW / MEDIUM / HIGH label for the estimate.
        stages: Ordered list of pipeline stage descriptions run.
        renders: Per-scene generation outputs.
        component_registry: Reusable building blocks referenced, if any.
    """

    spec_title: str
    source: str
    total_scenes: int
    total_duration_seconds: float
    tightness: float
    hallucination_risk: float
    risk_label: str
    stages: list[str] = field(default_factory=list)
    renders: list[SceneRender] = field(default_factory=list)
    component_registry: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the manifest to a plain JSON-compatible dict."""
        return {
            "spec_title": self.spec_title,
            "source": self.source,
            "total_scenes": self.total_scenes,
            "total_duration_seconds": self.total_duration_seconds,
            "tightness": self.tightness,
            "hallucination_risk": self.hallucination_risk,
            "risk_label": self.risk_label,
            "stages": list(self.stages),
            "renders": [asdict(r) for r in self.renders],
            "component_registry": list(self.component_registry),
        }


@dataclass
class PipelineResult:
    """Result of a full pipeline run."""

    manifest: AssemblyManifest
    artifact_path: str | None
    ok: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "artifact_path": self.artifact_path,
            "manifest": self.manifest.to_dict(),
        }


class PipelineRunner:
    """Run the spec -> assembly -> artifact pipeline.

    Stages (mirroring the discussed stack): parse/validate the brief, score its
    tightness, estimate hallucination risk, generate each scene (injectable
    generator), then assemble a manifest and write an artifact file.

    Network-free by default: with no generator supplied a deterministic
    :class:`StubGenerator` is used so runs are reproducible.
    """

    def __init__(self, generator: Generator | None = None) -> None:
        self._generator = generator if generator is not None else StubGenerator()

    @property
    def generator(self) -> Generator:
        return self._generator

    def run(
        self,
        spec: VideoSpec,
        output_dir: str | Path | None = None,
        source: str = "brief.markdown",
        validate: bool = True,
    ) -> PipelineResult:
        """Execute the pipeline and return the assembly result.

        Args:
            spec: The structured brief to build.
            output_dir: Optional directory to write ``manifest.json``; when
                given, the artifact path is returned in the result.
            source: Description path of the source document (for the manifest).
            validate: When True, run :func:`validate_spec` first.

        Raises:
            GenerationError: if validation fails and ``validate`` is True.
        """
        stages: list[str] = []
        if validate:
            report = validate_spec(spec)
            if not report.valid:
                raise GenerationError("; ".join(report.errors))

        tightness = tightness_score(spec)
        risk = hallucination_risk_estimate(tightness)
        label = hallucination_risk_label(risk)

        stages.append(f"spec parsed & validated ({len(spec.scenes)} scenes)")
        stages.append(f"tightness scored = {tightness}")
        stages.append(f"hallucination risk estimated = {risk} ({label})")

        renders = self._generator.generate(spec)
        stages.append(f"generated {len(renders)} scene renders "
                      f"({"all ok" if all(r.ok for r in renders) else "with degraded renders"})")

        total_duration = sum(float(s.timing_seconds or 0.0) for s in spec.scenes)
        manifest = AssemblyManifest(
            spec_title=spec.title or "(untitled)",
            source=source,
            total_scenes=len(spec.scenes),
            total_duration_seconds=round(total_duration, 2),
            tightness=tightness,
            hallucination_risk=risk,
            risk_label=label,
            stages=stages,
            renders=renders,
            component_registry=list(spec.component_registry),
        )

        artifact_path: str | None = None
        if output_dir is not None:
            out = Path(output_dir)
            out.mkdir(parents=True, exist_ok=True)
            artifact = out / "manifest.json"
            artifact.write_text(
                json.dumps(manifest.to_dict(), indent=2, sort_keys=True), encoding="utf-8"
            )
            artifact_path = str(artifact)

        return PipelineResult(manifest=manifest, artifact_path=artifact_path, ok=True)


def run_pipeline(
    spec: VideoSpec,
    output_dir: str | Path | None = None,
    generator: Generator | None = None,
    source: str = "brief.markdown",
) -> PipelineResult:
    """Convenience wrapper around :class:`PipelineRunner`."""
    return PipelineRunner(generator=generator).run(spec, output_dir=output_dir, source=source)


# ---------------------------------------------------------------------------
# Pipeline runner for spec dicts (convenience)
# ---------------------------------------------------------------------------


def run_pipeline_from_dict(
    spec: dict[str, Any],
    output_dir: str | Path | None = None,
    generator: Generator | None = None,
    source: str = "brief.markdown",
) -> PipelineResult:
    """Run the pipeline from a plain dict spec (JSON round-trip friendly)."""
    return run_pipeline(
        spec_from_dict(spec), output_dir=output_dir, generator=generator, source=source
    )


# ---------------------------------------------------------------------------
# Convenience totals
# ---------------------------------------------------------------------------


def total_duration(spec: VideoSpec) -> float:
    """Return the summed duration of all scenes, in seconds."""
    return round(sum(float(s.timing_seconds or 0.0) for s in spec.scenes), 2)


def scene_count(spec: VideoSpec) -> int:
    """Return the number of scenes in a spec."""
    return len(spec.scenes)


__all__ = [
    # model
    "Scene",
    "VideoSpec",
    "SpecValidationReport",
    # serialization
    "parse_spec_markdown",
    "spec_to_dict",
    "spec_from_dict",
    # validation / scoring
    "validate_spec",
    "tightness_score",
    "hallucination_risk_estimate",
    "hallucination_risk_label",
    # generation
    "Generator",
    "RealGenerator",
    "StubGenerator",
    "SceneRender",
    "GenerationError",
    # pipeline
    "PipelineRunner",
    "PipelineResult",
    "AssemblyManifest",
    "run_pipeline",
    "run_pipeline_from_dict",
    # helpers
    "total_duration",
    "scene_count",
    # transcript constants
    "VIDEO_AS_CODE_STACK",
    "TIGHT_BRIEF_QUOTE",
    "LOOSE_SPEC_CLAIM",
]