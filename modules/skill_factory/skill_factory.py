"""
SkillFactory — Meta-Skill Generator / Registry / Self-Evolution.

Enterprise-grade module for discovering, generating, storing, versioning,
benchmarking, and self-evolving markdown skill recipes (superpowers /
hermes-skill-factory / SkillClaw concepts).

Components
----------
SkillRegistry
    Filesystem-backed registry of markdown skill recipes stored under
    ``<data_dir>/skills/<name>/``.  Each skill is a ``SKILL.md`` document with
    YAML frontmatter (metadata) plus a markdown body.  Versioning is enforced
    with semver bumping and full history is preserved on every update.

SkillGenerator
    Meta-skill auto-generation: compiles a task description or an observed
    command sequence into a markdown ``SKILL.md`` recipe with frontmatter and
    numbered execution steps.  Exposes pure, IO-free helper functions.

SkillEvolutionLoop
    Benchmarking and self-evolution: tracks a moving-average score and a
    feedback trail per skill, then proposes a refined version of a skill
    (an ``Outcome & refinement`` section) with a semver patch bump.

SkillFactory
    Convenience facade bundling the registry, generator and evolution loop
    together with optional event publishing.

All public functions are pure / unit-testable without external dependencies.

Python: 3.10+
"""

from __future__ import annotations

import builtins
import json
import logging
import os
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Module logger
# ---------------------------------------------------------------------------
_log: logging.Logger = logging.getLogger("enterprise.skill_factory")

# Default ceiling for the number of steps extracted from a command sequence.
MAX_STEPS: int = 40

# Default moving-average alpha used for scoring.
SCORE_ALPHA: float = 0.3

# Default starting version for a brand-new skill.
INITIAL_VERSION: str = "1.0.0"


# ===========================================================================
# Pure helpers (frontmatter + command parsing)
# ===========================================================================


def _yaml_quote(value: str) -> str:
    """Quote a scalar string for safe single-line YAML output."""
    value = value.replace("\n", " ").replace("\r", " ").strip()
    # Double-quote whenever the string contains characters that would be
    # ambiguous in plain YAML.
    if value == "" or re.search(r'[:#\[\]{},&\*!|>\'"%@`]|^\s|^[-?]|\s$', value):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _yaml_emit(data: dict[str, Any]) -> str:
    """Emit a simple, deterministic YAML document for a flat metadata dict.

    Supports string / number / bool scalars and lists of scalars, which is
    all that skill frontmatter requires.
    """
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                if isinstance(item, dict):
                    lines.append(f"  - {json.dumps(item, sort_keys=True)}")
                else:
                    lines.append(f"  - {_yaml_quote(str(item))}")
        elif isinstance(value, str):
            lines.append(f"{key}: {_yaml_quote(value)}")
        elif value is None:
            lines.append(f"{key}:")
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines)


def _yaml_parse(block: str) -> dict[str, Any]:
    """Parse the subset of YAML emitted by :func:`_yaml_emit`.

    Handles ``key: scalar``, ``key:`` with ``  - item`` lists, and blank
    value keys.  Unknown nesting is best-effort.
    """
    result: dict[str, Any] = {}
    current_list_key: str | None = None
    for raw_line in block.splitlines():
        line = raw_line.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("  - "):
            item = line[4:].strip()
            if current_list_key is not None:
                entries = result.get(current_list_key)
                if not isinstance(entries, list):
                    entries = []
                    result[current_list_key] = entries
                entries.append(_unquote(item))
            continue
        current_list_key = None
        if ":" not in line:
            continue
        key, _, raw_value = line.partition(":")
        key = key.strip()
        raw_value = raw_value.strip()
        if not raw_value:
            # Empty value: may be an empty scalar or the head of a list.
            result[key] = ""
            current_list_key = key
            continue
        result[key] = _coerce(_unquote(raw_value))
        current_list_key = None
    return result


def _unquote(value: str) -> str:
    """Strip matching double quotes from a scalar, unescaping if needed."""
    if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
        inner = value[1:-1]
        inner = inner.replace('\\"', '"').replace("\\\\", "\\")
        return inner
    return value


def _coerce(value: str) -> Any:
    """Best-effort coercion of a scalar string to bool/int/float/str."""
    if value == "null":
        return None
    lowered = value.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


# ===========================================================================
# Data model
# ===========================================================================


@dataclass
class SkillRecord:
    """A versioned skill recipe with metadata and history."""

    name: str
    version: str
    body: str
    category: str = "general"
    description: str = ""
    tags: list[str] = field(default_factory=list)
    score: float = 0.0
    feedback: list[str] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None

    def metadata(self) -> dict[str, Any]:
        """Return metadata only (no body), suitable for listings."""
        return {
            "name": self.name,
            "version": self.version,
            "category": self.category,
            "description": self.description,
            "tags": list(self.tags),
            "score": self.score,
            "updated_at": self.updated_at,
        }

    def to_dict(self) -> dict[str, Any]:
        """Return the full record as a dict (including body)."""
        data = self.metadata()
        data["body"] = self.body
        data["feedback"] = list(self.feedback)
        data["history"] = list(self.history)
        data["created_at"] = self.created_at
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillRecord:
        return cls(
            name=str(data.get("name", "")),
            version=str(data.get("version", INITIAL_VERSION)),
            body=str(data.get("body", "")),
            category=str(data.get("category", "general")),
            description=str(data.get("description", "")),
            tags=list(data.get("tags", []) or []),
            score=float(data.get("score", 0.0)),
            feedback=list(data.get("feedback", []) or []),
            history=list(data.get("history", []) or []),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


def _now_iso() -> str:
    """Return an ISO-8601 UTC timestamp string."""
    return datetime.now(UTC).isoformat()


def bump_version(version: str, part: str = "patch") -> str:
    """Bump a semver ``X.Y.Z`` string.

    Args:
        version: Semver string like ``"1.2.3"``.
        part: Which segment to bump: ``"patch"``, ``"minor"`` or ``"major"``.

    Returns:
        The bumped semver string.
    """
    parts = re.split(r"[.]", version.strip())
    try:
        nums = [int(p) for p in parts[:3]]
    except ValueError:
        nums = [1, 0, 0]
    while len(nums) < 3:
        nums.append(0)
    if part == "major":
        nums[0] += 1
        nums[1] = 0
        nums[2] = 0
    elif part == "minor":
        nums[1] += 1
        nums[2] = 0
    else:  # patch
        nums[2] += 1
    return ".".join(str(n) for n in nums)


# ===========================================================================
# SkillRegistry
# ===========================================================================


class SkillRegistry:
    """Filesystem-backed registry of versioned markdown skill recipes.

    Layout::

        <data_dir>/skills/<name>/SKILL.md     current frontmatter + body
        <data_dir>/skills/<name>/_meta.json   score, feedback, history, timestamps

    :func:`create` upserts: a brand-new skill starts at ``1.0.0``; an existing
    skill is version-bumped (patch) and its prior body is archived to history.
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir: Path = Path(data_dir)

    # ── Path helpers ────────────────────────────────────────────────────────

    def root(self) -> Path:
        """The directory that stores all skills (created on demand)."""
        return self._data_dir / "skills"

    def skill_dir(self, name: str) -> Path:
        return self.root() / name

    def skill_file(self, name: str) -> Path:
        return self.skill_dir(name) / "SKILL.md"

    def meta_file(self, name: str) -> Path:
        return self.skill_dir(name) / "_meta.json"

    def ensure(self) -> Path:
        """Create the skills root directory if missing and return it."""
        root = self.root()
        root.mkdir(parents=True, exist_ok=True)
        return root

    def exists(self, name: str) -> bool:
        """Return True if a skill with this name exists on disk."""
        return self.skill_file(name).exists()

    # ── Create ──────────────────────────────────────────────────────────────

    def create(
        self,
        name: str,
        body: str,
        category: str = "general",
        description: str = "",
        tags: builtins.list[str] | None = None,
    ) -> SkillRecord:
        """Create a new skill, or version-bump an existing one (upsert).

        If the skill already exists the patch version is bumped and the
        previous body is archived to the skill's history.
        """
        name = name.strip()
        if not name:
            raise ValueError("skill name must not be empty")

        self.ensure()
        now = _now_iso()

        if self.exists(name):
            current = self.get(name)
            assert current is not None, "skill exists but could not be read"
            new_version = bump_version(current.version)
            # Archive the current body into history.
            history = list(current.history)
            history.append(
                {
                    "version": current.version,
                    "body": current.body,
                    "updated_at": current.updated_at,
                }
            )
            record = SkillRecord(
                name=name,
                version=new_version,
                body=body,
                category=category or current.category,
                description=description or current.description,
                tags=tags if tags is not None else list(current.tags),
                score=current.score,
                feedback=list(current.feedback),
                history=history,
                created_at=current.created_at,
                updated_at=now,
            )
        else:
            record = SkillRecord(
                name=name,
                version=INITIAL_VERSION,
                body=body,
                category=category or "general",
                description=description,
                tags=list(tags or []),
                score=0.0,
                feedback=[],
                history=[],
                created_at=now,
                updated_at=now,
            )

        self._write(record)
        _log.debug("Skill created/updated: %s v%s", name, record.version)
        return record

    # ── Read ────────────────────────────────────────────────────────────────

    def get(self, name: str) -> SkillRecord | None:
        """Return the full skill record, or None if it does not exist."""
        skill_file = self.skill_file(name)
        if not skill_file.exists():
            return None
        text = skill_file.read_text(encoding="utf-8")
        frontmatter, body = parse_frontmatter(text)

        meta: dict[str, Any] = {}
        meta_file = self.meta_file(name)
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                meta = {}

        record = SkillRecord.from_dict(
            {
                "name": frontmatter.get("name", name),
                "version": str(frontmatter.get("version", meta.get("version", INITIAL_VERSION))),
                "body": body,
                "category": str(frontmatter.get("category", meta.get("category", "general"))),
                "description": str(frontmatter.get("description", meta.get("description", ""))),
                "tags": list(frontmatter.get("tags") or meta.get("tags") or []),
                "score": float(meta.get("score", 0.0)),
                "feedback": list(meta.get("feedback", []) or []),
                "history": list(meta.get("history", []) or []),
                "created_at": meta.get("created_at"),
                "updated_at": frontmatter.get("updated_at", meta.get("updated_at")),
            }
        )
        return record

    def list(self) -> builtins.list[dict[str, Any]]:
        """Return metadata-only dicts for all skills (no bodies)."""
        self.ensure()
        result: list[dict[str, Any]] = []
        for child in sorted(self.root().iterdir()):
            if not child.is_dir():
                continue
            record = self.get(child.name)
            if record is not None:
                result.append(record.metadata())
        return result

    # ── Update ──────────────────────────────────────────────────────────────

    def update(
        self,
        name: str,
        body: str | None = None,
        category: str | None = None,
        description: str | None = None,
        tags: builtins.list[str] | None = None,
    ) -> SkillRecord | None:
        """Update an existing skill, bumping the patch version keeping history.

        Returns the updated record, or None if the skill does not exist.
        """
        current = self.get(name)
        if current is None:
            return None

        new_body = body if body is not None else current.body
        new_version = bump_version(current.version)
        history = list(current.history)
        history.append(
            {
                "version": current.version,
                "body": current.body,
                "updated_at": current.updated_at,
            }
        )
        record = SkillRecord(
            name=name,
            version=new_version,
            body=new_body,
            category=category if category is not None else current.category,
            description=description if description is not None else current.description,
            tags=tags if tags is not None else list(current.tags),
            score=current.score,
            feedback=list(current.feedback),
            history=history,
            created_at=current.created_at,
            updated_at=_now_iso(),
        )
        self._write(record)
        _log.debug("Skill updated: %s v%s", name, record.version)
        return record

    # ── Delete ──────────────────────────────────────────────────────────────

    def delete(self, name: str) -> bool:
        """Delete a skill (and its history).  Returns True if removed."""
        target = self.skill_dir(name)
        if not target.exists():
            return False
        shutil.rmtree(target)
        return True

    # ── Persistence ─────────────────────────────────────────────────────────

    def _write(self, record: SkillRecord) -> None:
        """Persist a record: SKILL.md (frontmatter + body) and _meta.json."""
        if not record.name:
            raise ValueError("skill name must not be empty")
        directory = self.skill_dir(record.name)
        directory.mkdir(parents=True, exist_ok=True)

        frontmatter = build_frontmatter(
            {
                "name": record.name,
                "version": record.version,
                "category": record.category,
                "description": record.description,
                "tags": list(record.tags),
                "updated_at": record.updated_at,
            }
        )
        (self.skill_file(record.name)).write_text(
            frontmatter + (record.body or ""), encoding="utf-8"
        )

        meta: dict[str, Any] = {
            "name": record.name,
            "version": record.version,
            "category": record.category,
            "description": record.description,
            "tags": list(record.tags),
            "score": record.score,
            "feedback": list(record.feedback),
            "history": list(record.history),
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }
        self.meta_file(record.name).write_text(
            json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8"
        )

    def is_writable(self) -> bool:
        """Return True if the skills root exists and is writable."""
        try:
            root = self.ensure()
            return os.access(str(root), os.W_OK)
        except OSError:
            return False


# ===========================================================================
# Frontmatter parse/build (shared by registry and generator)
# ===========================================================================


def build_frontmatter(meta: dict[str, Any]) -> str:
    """Build a YAML frontmatter block (including ``---`` delimiters).

    Args:
        meta: Flat metadata dict.  Keys order is deterministic (insertion).

    Returns:
        A string starting with ``---\\n`` and ending with ``---\\n``.
    """
    body = _yaml_emit(meta)
    return f"---\n{body}\n---\n"


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split a document into (frontmatter dict, body).

    Expects the document to begin with a ``---`` delimiter line, a YAML block,
    and a closing ``---`` line.  Returns ``({}, text)`` when no frontmatter is
    present.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    end_index: int | None = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_index = i
            break
    if end_index is None:
        return {}, text
    block = "\n".join(lines[1:end_index])
    body = "\n".join(lines[end_index + 1 :])
    return _yaml_parse(block), body


# ===========================================================================
# SkillGenerator
# ===========================================================================


class SkillGenerator:
    """Meta-skill auto-generation from a prompt or an observed command sequence."""

    #: Regex used to normalise free-text into a URL/name safe slug.
    _SLUG_RE: re.Pattern = re.compile(r"[^a-z0-9]+")
    _SLUG_MAX: int = 48

    def generate_skill(
        self,
        commands: list[str],
        category: str = "general",
        description: str = "",
        prompt: str | None = None,
        triggers: list[str] | None = None,
    ) -> dict[str, Any]:
        """Compile an observed command sequence into a full SKILL.md document.

        Returns a dict containing ``name``, ``version``, ``frontmatter``,
        ``markdown`` (frontmatter + numbered steps), ``steps``,
        ``category``, ``description``.
        """
        steps = extract_steps(commands)
        name = name_from_prompt(prompt or description or "auto-generated-skill")
        meta = {
            "name": name,
            "version": INITIAL_VERSION,
            "category": category,
            "description": description,
            "triggers": list(triggers or []),
        }
        frontmatter = build_frontmatter(meta)
        body = self._render_steps(steps)
        markdown = frontmatter + body
        return {
            "name": name,
            "version": INITIAL_VERSION,
            "category": category,
            "description": description,
            "frontmatter": frontmatter,
            "markdown": markdown,
            "steps": list(steps),
        }

    @staticmethod
    def _render_steps(steps: list[str]) -> str:
        """Render extracted steps as a numbered markdown section."""
        if not steps:
            return "No steps extracted.\n"
        lines = ["# Usage", ""]
        lines.extend([f"{i}. {step}" for i, step in enumerate(steps, start=1)])
        return "\n".join(lines) + "\n"


def extract_steps(commands: list[str]) -> list[str]:
    """Clean, trim and cap a list of raw command lines into actionable steps.

    - Strips surrounding whitespace.
    - Drops empty / blank entries.
    - Caps the result at :data:`MAX_STEPS` entries.

    Args:
        commands: Raw command strings, e.g. shell commands.

    Returns:
        A cleaned list of non-empty step strings.
    """
    cleaned: list[str] = []
    for raw in commands:
        if raw is None:
            continue
        stripped = str(raw).strip()
        if not stripped:
            continue
        cleaned.append(stripped)
    return cleaned[:MAX_STEPS]


def name_from_prompt(prompt: str) -> str:
    """Convert a free-text prompt into a lowercase URL/name-safe slug.

    Examples::

        "Deploy the PostgreSQL backup" -> "deploy-the-postgresql-backup"

    Args:
        prompt: Free-text prompt or description.

    Returns:
        A slug suitable for use as a skill name.
    """
    text = (prompt or "").strip().lower()
    slug = SkillGenerator._SLUG_RE.sub("-", text).strip("-")
    if not slug:
        slug = "auto-generated-skill"
    return slug[: SkillGenerator._SLUG_MAX].strip("-") or "auto-generated-skill"


# ===========================================================================
# SkillEvolutionLoop
# ===========================================================================


class SkillEvolutionLoop:
    """Benchmark / refine / self-evolve skill recipes.

    Tracks a moving-average success score and a feedback trail per skill, and
    proposes refined (version-bumped) versions of a skill that summarise recent
    feedback in an ``Outcome & refinement`` section.
    """

    def __init__(self, registry: SkillRegistry) -> None:
        self._registry: SkillRegistry = registry
        #: Keep a small in-memory mirror of scores/records for pure scoring.
        self._runs: dict[str, list[bool]] = {}

    def record_run(self, skill_name: str, success: bool, feedback: str = "") -> SkillRecord:
        """Record a benchmark run for a skill, updating its moving-average score.

        Args:
            skill_name: Name of the skill to benchmark.
            success: Whether the run succeeded.
            feedback: Optional human/agent feedback to append to the trail.

        Returns:
            The updated SkillRecord.
        """
        record = self._registry.get(skill_name)
        if record is None:
            raise KeyError(f"skill '{skill_name}' not found in registry")
        assert record is not None

        runs = self._runs.setdefault(skill_name, [])
        runs.append(bool(success))
        record.score = moving_average(runs, alpha=SCORE_ALPHA)
        if feedback:
            record.feedback.append(feedback.strip())

        self._registry._write(record)  # noqa: SLF001  (persist updated score/feedback)
        return record

    def evolve(
        self,
        skill_name: str,
        max_recent_feedback: int = 5,
    ) -> SkillRecord:
        """Propose a refined version of a skill.

        The refined body appends an ``Outcome & refinement`` section summarising
        the most recent feedback, and the patch version is bumped.  History is
        preserved via the registry.

        Returns:
            The newly evolved SkillRecord.
        """
        record = self._registry.get(skill_name)
        if record is None:
            raise KeyError(f"skill '{skill_name}' not found in registry")
        assert record is not None

        refined = self._propose_refinement(record, max_recent_feedback=max_recent_feedback)
        return self._registry.update(
            skill_name,
            body=refined,
            category=record.category,
            description=record.description,
            tags=list(record.tags),
        )

    @staticmethod
    def _propose_refinement(
        record: SkillRecord, max_recent_feedback: int = 5
    ) -> str:
        """Pure: build a refined body string for a skill record."""
        recent = record.feedback[-max_recent_feedback:]
        section = ["", "## Outcome & refinement", ""]
        if recent:
            section.append("Observed outcomes from recent runs have informed this refinement:")
            for item in recent:
                section.append(f"- {item}")
        else:
            section.append(
                "No explicit feedback recorded yet; this version consolidates "
                "current guidance and structure."
            )
        section.append(f"- Benchmark score: {record.score:.3f}")
        return record.body.rstrip() + "\n" + "\n".join(section) + "\n"


def moving_average(runs: list[bool], alpha: float = SCORE_ALPHA) -> float:
    """Compute the exponential moving-average score from a sequence of runs.

    The first measurement seeds the score directly (1.0 / 0.0); subsequent
    measurements blend in with weight ``alpha``.

    Args:
        runs: Ordered list of boolean run outcomes (True == success).
        alpha: Smoothing factor in ``(0, 1]``.

    Returns:
        A float score in ``[0.0, 1.0]``.
    """
    if not runs:
        return 0.0
    alpha = max(0.0, min(1.0, alpha))
    score = 1.0 if runs[0] else 0.0
    for outcome in runs[1:]:
        score = score * (1.0 - alpha) + (1.0 if outcome else 0.0) * alpha
    return round(score, 4)


# ===========================================================================
# SkillFactory facade
# ===========================================================================

#: Callback type for event publishing: (topic, payload) -> None
EventPublisher = Callable[[str, dict[str, Any]], None]


class SkillFactory:
    """Facade bundling the registry, generator and evolution loop."""

    def __init__(
        self,
        data_dir: Path,
        generator: SkillGenerator | None = None,
        evolution: SkillEvolutionLoop | None = None,
    ) -> None:
        self.registry: SkillRegistry = SkillRegistry(data_dir)
        self.generator: SkillGenerator = generator or SkillGenerator()
        self.evolution: SkillEvolutionLoop = evolution or SkillEvolutionLoop(self.registry)
        #: Optional event publisher wired by the owning module.
        self._event_publisher: EventPublisher | None = None

    def set_event_publisher(self, publisher: EventPublisher | None) -> None:
        """Wire an optional event publisher callback."""
        self._event_publisher = publisher

    def _emit(self, topic: str, payload: dict[str, Any]) -> None:
        if self._event_publisher is not None:
            try:
                self._event_publisher(topic, payload)
            except Exception as exc:  # pragma: no cover - defensive
                _log.warning("Event publisher failed for %s: %s", topic, exc)

    # ── Registry passthroughs ───────────────────────────────────────────────

    def create(
        self,
        name: str,
        body: str,
        category: str = "general",
        description: str = "",
        tags: builtins.list[str] | None = None,
    ) -> SkillRecord:
        existed = self.registry.exists(name)
        record = self.registry.create(name, body, category, description, tags)
        payload = {"name": record.name, "version": record.version}
        self._emit("skill.updated" if existed else "skill.created", payload)
        return record

    def get(self, name: str) -> SkillRecord | None:
        return self.registry.get(name)

    def list(self) -> builtins.list[dict[str, Any]]:
        return self.registry.list()

    def update(
        self,
        name: str,
        body: str | None = None,
        category: str | None = None,
        description: str | None = None,
        tags: builtins.list[str] | None = None,
    ) -> SkillRecord | None:
        record = self.registry.update(name, body, category, description, tags)
        if record is not None:
            self._emit(
                "skill.updated",
                {"name": record.name, "version": record.version},
            )
        return record

    def delete(self, name: str) -> bool:
        return self.registry.delete(name)

    # ── Generation passthrough ──────────────────────────────────────────────

    def generate(
        self,
        commands: builtins.list[str],
        category: str = "general",
        description: str = "",
        prompt: str | None = None,
        triggers: builtins.list[str] | None = None,
    ) -> dict[str, Any]:
        """Generate a skill document; does not persist unless persisted."""
        return self.generator.generate_skill(commands, category, description, prompt, triggers)

    # ── Evolution passthrough ───────────────────────────────────────────────

    def record_run(self, skill_name: str, success: bool, feedback: str = "") -> SkillRecord:
        return self.evolution.record_run(skill_name, success, feedback)

    def evolve(self, skill_name: str, max_recent_feedback: int = 5) -> SkillRecord:
        record = self.evolution.evolve(skill_name, max_recent_feedback=max_recent_feedback)
        self._emit(
            "skill.evolved",
            {"name": record.name, "version": record.version},
        )
        return record
