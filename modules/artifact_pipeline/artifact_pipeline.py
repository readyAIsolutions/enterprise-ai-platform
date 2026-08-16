"""Pure Artifact Pipeline core — grounded in the JEVanClief transcript.

Transcript: "Watch Me Build Something Claude Code Can't Do Yet"
(https://www.youtube.com/watch?v=KC0VEZuo4OI, 891s). JEVanClief wants a front
end that lets him navigate all of his works in one organized, clear place — he
explicitly does NOT want a front end that calls Claude, because that incurs API
fees. He takes scripts and turns them into "full animations", with a clear
workflow and finished animations viewable in one place.

That is an asset / pipeline ORGANIZER, not a chatbot. This module models it:

  * :class:`ArtifactRegistry` — catalogs artifact files on disk (Path scanning,
    network-free) tracking each artifact's TYPE and STAGE.
  * :class:`WorkflowGraph` — valid stage transitions of the pipeline
    ``script -> storyboard -> animation -> render`` (with the transcript
    shortcut ``script -> animation``).
  * :class:`ArtifactPipeline` — groups / navigates by type, project, stage;
    tracks dependencies (a render depends on its script); surfaces renders.
  * :class:`JsonCatalogStore` / :class:`SqliteCatalogStore` — local persistence.

Stdlib-only and network-free — navigating works WITHOUT an LLM, to dodge API
fees exactly as the transcript describes.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

__all__ = [
    "ArtifactType",
    "Stage",
    "Artifact",
    "ArtifactRegistry",
    "WorkflowGraph",
    "ArtifactPipeline",
    "JsonCatalogStore",
    "SqliteCatalogStore",
    "ArtifactNotFoundError",
    "InvalidTransitionError",
    "DuplicateArtifactError",
    "DependencyError",
    "DEFAULT_TYPE_EXTENSIONS",
    "STAGE_ORDER",
]


# ==== Types & stages ==================================================


class ArtifactType(Enum):
    """The kind of creative work an artifact file represents."""

    SCRIPT = "script"            # a markdown/text script
    STORYBOARD = "storyboard"    # a structured scene outline
    ANIMATION = "animation"      # an animation source / motion document
    RENDER = "render"            # a finished video/animation output


class Stage(Enum):
    """Pipeline stage an artifact currently sits at (script..render)."""

    SCRIPT = "script"
    STORYBOARD = "storyboard"
    ANIMATION = "animation"
    RENDER = "render"


# The canonical pipeline order (transcript: scripts -> full animations).
STAGE_ORDER: tuple[Stage, ...] = (
    Stage.SCRIPT,
    Stage.STORYBOARD,
    Stage.ANIMATION,
    Stage.RENDER,
)

# Extension -> type mapping used to auto-classify files on disk.
DEFAULT_TYPE_EXTENSIONS: dict[ArtifactType, frozenset[str]] = {
    ArtifactType.SCRIPT: frozenset({".md", ".markdown", ".txt"}),
    ArtifactType.STORYBOARD: frozenset({".json", ".storyboard", ".sb"}),
    ArtifactType.ANIMATION: frozenset({".anim", ".motion", ".clips"}),
    ArtifactType.RENDER: frozenset({".mp4", ".webm", ".gif", ".mov", ".avi", ".mkv"}),
}


# ==== Errors ==========================================================


class ArtifactNotFoundError(KeyError):
    """Raised when no artifact with the given id is known to the registry."""


class DuplicateArtifactError(ValueError):
    """Raised when an artifact with the same normalized path is registered twice."""


class InvalidTransitionError(ValueError):
    """Raised when a stage transition is not allowed by the WorkflowGraph."""


class DependencyError(ValueError):
    """Raised when a dependency would be invalid (cycle, same artifact, bad stage)."""


# ==== Artifact ========================================================


@dataclass
class Artifact:
    """A single creative work artifact tracked by the pipeline."""

    id: str
    path: str
    name: str
    project: str
    type: ArtifactType
    stage: Stage
    dependencies: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_viewable(self) -> bool:
        """Finished animations/renders are the viewable outputs (one place)."""
        return self.stage in (Stage.ANIMATION, Stage.RENDER)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "path": self.path,
            "name": self.name,
            "project": self.project,
            "type": self.type.value,
            "stage": self.stage.value,
            "dependencies": sorted(self.dependencies),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Artifact":
        return cls(
            id=data["id"],
            path=data["path"],
            name=data["name"],
            project=data["project"],
            type=ArtifactType(data["type"]),
            stage=Stage(data["stage"]),
            dependencies=set(data.get("dependencies", [])),
            metadata=dict(data.get("metadata", {})),
        )


# ==== WorkflowGraph — defines the valid stage-transition pipeline =====


class WorkflowGraph:
    """Valid stage transitions for the script -> animation pipeline.

    Edges: SCRIPT -> {STORYBOARD, ANIMATION} (scripts -> full animations),
    STORYBOARD -> {ANIMATION}, ANIMATION -> {RENDER}, RENDER -> {} (terminal).
    """

    def __init__(self, edges: Optional[dict[Stage, set[Stage]]] = None) -> None:
        if edges is None:
            edges = {
                Stage.SCRIPT: {Stage.STORYBOARD, Stage.ANIMATION},
                Stage.STORYBOARD: {Stage.ANIMATION},
                Stage.ANIMATION: {Stage.RENDER},
                Stage.RENDER: set(),
            }
        self._edges: dict[Stage, set[Stage]] = {s: set(edges.get(s, set())) for s in STAGE_ORDER}

    # -- queries ------------------------------------------------------------
    def can_transition(self, frm: Stage, to: Stage) -> bool:
        return to in self._edges.get(frm, set())

    def next_stages(self, stage: Stage) -> list[Stage]:
        return [s for s in STAGE_ORDER if s in self._edges.get(stage, set())]

    def has_next(self, stage: Stage) -> bool:
        return bool(self._edges.get(stage, set()))

    def rank(self, stage: Stage) -> int:
        return STAGE_ORDER.index(stage)

    def strictly_before(self, earlier: Stage, later: Stage) -> bool:
        """True if `earlier` is strictly earlier in the pipeline than `later`."""
        return self.rank(earlier) < self.rank(later)

    def edges(self) -> dict[str, list[str]]:
        return {s.value: sorted(st.value for st in self._edges[s]) for s in STAGE_ORDER}

    def validate_transition(self, frm: Stage, to: Stage) -> None:
        """Raise InvalidTransitionError if ``frm -> to`` is not allowed."""
        if not self.can_transition(frm, to):
            raise InvalidTransitionError(
                f"invalid pipeline transition {frm.value!r} -> {to.value!r}; "
                f"allowed from {frm.value}: {self.next_stages(frm)}"
            )


# ==== ArtifactRegistry — on-disk catalog + grouping ===================


def _slugify(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")


def infer_type(path: Path, extensions: dict[ArtifactType, frozenset[str]]) -> ArtifactType:
    """Classify an artifact file by its extension (defaults to SCRIPT)."""
    ext = path.suffix.lower()
    for atype, exts in DEFAULT_TYPE_EXTENSIONS.items():
        if ext in exts:
            return atype
    # Fall back to a callable override map if one was supplied.
    for atype, exts in extensions.items():
        if ext in exts:
            return atype
    return ArtifactType.SCRIPT


def id_for_path(path: Path) -> str:
    """Stable artifact id from the normalized path (no network)."""
    return hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:16]


class ArtifactRegistry:
    """Catalogs artifacts found on disk and indexes them for navigation."""

    def __init__(
        self,
        extensions: Optional[dict[ArtifactType, frozenset[str]]] = None,
    ) -> None:
        self._extensions: dict[ArtifactType, frozenset[str]] = (
            extensions if extensions is not None else {}
        )
        self._artifacts: dict[str, Artifact] = {}
        self._by_project: dict[str, set[str]] = {}
        self._by_type: dict[ArtifactType, set[str]] = {t: set() for t in ArtifactType}
        self._by_stage: dict[Stage, set[str]] = {s: set() for s in Stage}
        self._graph = WorkflowGraph()

    # -- index maintenance --------------------------------------------------
    def _index(self, art: Artifact) -> None:
        self._by_project.setdefault(art.project, set()).add(art.id)
        self._by_type[art.type].add(art.id)
        self._by_stage[art.stage].add(art.id)

    def _reindex_stage(self, art: Artifact) -> None:
        for s in Stage:
            self._by_stage[s].discard(art.id)
        self._by_stage[art.stage].add(art.id)

    # -- registration -------------------------------------------------------
    def register(
        self,
        path: str,
        project: Optional[str] = None,
        type_: Optional[ArtifactType] = None,
        stage: Optional[Stage] = None,
        dependencies: Optional[Iterable[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        artifact_id: Optional[str] = None,
    ) -> Artifact:
        """Register a file path as an artifact, auto-detecting type/stage."""
        p = Path(path)
        atype = type_ if type_ is not None else infer_type(p, self._extensions)
        stg = stage if stage is not None else Stage(atype.value)
        proj = project or (p.parent.name if p.parent and p.parent.name != "." else "root")
        aid = artifact_id or id_for_path(p)
        if aid in self._artifacts:
            raise DuplicateArtifactError(f"artifact already registered: {aid}")
        art = Artifact(
            id=aid,
            path=str(p),
            name=p.stem,
            project=_slugify(proj) or "root",
            type=atype,
            stage=stg,
            dependencies=set(dependencies or []),
            metadata=dict(metadata or {}),
        )
        self._artifacts[aid] = art
        self._index(art)
        return art

    def remove(self, artifact_id: str) -> None:
        art = self.get(artifact_id)
        self._artifacts.pop(artifact_id)
        self._by_project.get(art.project, set()).discard(artifact_id)
        self._by_type[art.type].discard(artifact_id)
        self._by_stage[art.stage].discard(artifact_id)

    def get(self, artifact_id: str) -> Artifact:
        try:
            return self._artifacts[artifact_id]
        except KeyError:
            raise ArtifactNotFoundError(f"unknown artifact id: {artifact_id}") from None

    def __contains__(self, artifact_id: str) -> bool:
        return artifact_id in self._artifacts

    def __iter__(self) -> Iterator[Artifact]:
        return iter(self._artifacts.values())

    def __len__(self) -> int:
        return len(self._artifacts)

    def all(self) -> list[Artifact]:
        return list(self._artifacts.values())

    # -- navigation ---------------------------------------------------------
    def filter(
        self,
        project: Optional[str] = None,
        type_: Optional[ArtifactType] = None,
        stage: Optional[Stage] = None,
        viewable_only: bool = False,
    ) -> list[Artifact]:
        out: list[Artifact] = []
        pool: set[str] | None = None
        if project is not None:
            pool = set(self._by_project.get(_slugify(project), set()))
        if type_ is not None:
            ids = self._by_type.get(type_, set())
            pool = ids if pool is None else pool & ids
        if stage is not None:
            ids = self._by_stage.get(stage, set())
            pool = ids if pool is None else pool & ids
        ids = pool if pool is not None else set(self._artifacts)
        for aid in ids:
            art = self._artifacts[aid]
            if viewable_only and not art.is_viewable:
                continue
            out.append(art)
        return sorted(out, key=lambda a: (a.project, a.stage.value, a.name))

    def group_by(self, field_name: str) -> dict[str, list[Artifact]]:
        if field_name not in ("project", "type", "stage"):
            raise ValueError("field_name must be 'project', 'type' or 'stage'")
        result: dict[str, list[Artifact]] = {}
        for art in self.all():
            key = getattr(art, field_name)
            key = key.value if isinstance(key, Enum) else key
            result.setdefault(key, []).append(art)
        for key in result:
            result[key].sort(key=lambda a: (a.stage.value, a.name))
        return result

    def stats(self) -> dict[str, Any]:
        by_type = {t.value: len(self._by_type[t]) for t in ArtifactType}
        by_stage = {s.value: len(self._by_stage[s]) for s in Stage}
        return {
            "total_artifacts": len(self._artifacts),
            "by_type": by_type,
            "by_stage": by_stage,
            "projects": {p: len(v) for p, v in sorted(self._by_project.items())},
        }

    def scan(self, root: str, project: Optional[str] = None) -> list[Artifact]:
        """Walk a directory tree and register every recognized artifact file."""
        base = Path(root)
        proj_override = project
        added: list[Artifact] = []
        for p in sorted(base.rglob("*")):
            if not p.is_file():
                continue
            rel = p
            proj = proj_override or (rel.parent.name if rel.parent.name and rel.parent.name != "." else "root")
            art = self.register(str(p), project=proj)
            added.append(art)
        return added


# ==== Catalog stores — local persistence (never a network call) =======


class JsonCatalogStore:
    """JSON-file persistence for the catalog (in-memory + tmp_path friendly)."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def save(self, artifacts: Iterable[Artifact]) -> None:
        payload = [a.to_dict() for a in artifacts]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load(self) -> list[Artifact]:
        if not self.path.exists():
            return []
        return [Artifact.from_dict(d) for d in json.loads(self.path.read_text(encoding="utf-8"))]


class SqliteCatalogStore:
    """SQLite-backed persistence for the catalog (stdlib sqlite3, offline)."""

    def __init__(self, path: str) -> None:
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS artifacts (
                id TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                name TEXT NOT NULL,
                project TEXT NOT NULL,
                type TEXT NOT NULL,
                stage TEXT NOT NULL,
                dependencies TEXT NOT NULL,
                metadata TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def save(self, artifacts: Iterable[Artifact]) -> None:
        self._conn.execute("DELETE FROM artifacts")
        for a in artifacts:
            self._conn.execute(
                "INSERT OR REPLACE INTO artifacts "
                "(id, path, name, project, type, stage, dependencies, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    a.id,
                    a.path,
                    a.name,
                    a.project,
                    a.type.value,
                    a.stage.value,
                    json.dumps(sorted(a.dependencies)),
                    json.dumps(a.metadata),
                ),
            )
        self._conn.commit()

    def load(self) -> list[Artifact]:
        rows = self._conn.execute(
            "SELECT id, path, name, project, type, stage, dependencies, metadata FROM artifacts"
        ).fetchall()
        return [
            Artifact(
                id=r[0],
                path=r[1],
                name=r[2],
                project=r[3],
                type=ArtifactType(r[4]),
                stage=Stage(r[5]),
                dependencies=set(json.loads(r[6])),
                metadata=dict(json.loads(r[7])),
            )
            for r in rows
        ]

    def close(self) -> None:
        self._conn.close()


# ==== ArtifactPipeline — the organizer users navigate =================


class ArtifactPipeline:
    """Organizer/navigator over the catalog.

    Wraps :class:`ArtifactRegistry` and :class:`WorkflowGraph`, adds pipeline
    operations (advance artifacts, derive downstream artifacts, track
    dependencies) and optional persistence. This is the "front end to navigate
    all of my works" from the transcript — no LLM involved.
    """

    def __init__(
        self,
        registry: Optional[ArtifactRegistry] = None,
        graph: Optional[WorkflowGraph] = None,
        store: Optional[Any] = None,
    ) -> None:
        self.registry = registry or ArtifactRegistry()
        self.graph = graph or WorkflowGraph()
        self.store = store

    # -- registration (alias for ergonomics) --------------------------------
    def get(self, artifact_id: str) -> Artifact:
        return self.registry.get(artifact_id)

    def all(self) -> list[Artifact]:
        return self.registry.all()

    def __len__(self) -> int:
        return len(self.registry)

    def __iter__(self) -> Iterator[Artifact]:
        return iter(self.registry)

    def add(
        self,
        path: str,
        project: Optional[str] = None,
        type_: Optional[ArtifactType] = None,
        stage: Optional[Stage] = None,
        metadata: Optional[dict[str, Any]] = None,
        artifact_id: Optional[str] = None,
    ) -> Artifact:
        art = self.registry.register(
            path,
            project=project,
            type_=type_,
            stage=stage,
            metadata=metadata,
            artifact_id=artifact_id,
        )
        return art

    def add_dependency(self, artifact_id: str, depends_on: Iterable[str]) -> None:
        """Record that ``artifact_id`` depends on the given upstream ids."""
        art = self.registry.get(artifact_id)
        for dep in depends_on:
            dep_art = self.registry.get(dep)
            if dep_art.type is ArtifactType.RENDER:
                raise DependencyError("a render cannot be an upstream dependency")
            if not self.graph.strictly_before(dep_art.stage, art.stage):
                raise DependencyError(
                    f"dependency {dep} stage {dep_art.stage.value!r} is not strictly "
                    f"earlier than {art.stage.value!r}"
                )
            if dep == artifact_id:
                raise DependencyError("an artifact cannot depend on itself")
        art.dependencies |= set(depends_on)

    def derive(
        self,
        source_id: str,
        output_path: str,
        to_stage: Optional[Stage] = None,
        project: Optional[str] = None,
    ) -> Artifact:
        """Create a downstream artifact produced from ``source_id``.

        E.g. turn a script into an animation ("take scripts and turn them into
        full animations"); the new artifact automatically depends on the source.
        """
        source = self.registry.get(source_id)
        target_stage = to_stage or Stage(ArtifactType(infer_type(
            Path(output_path), self.registry._extensions
        )).value)
        # A derive is a single pipeline step: target must be one valid
        # transition away from the source's stage (e.g. script -> animation).
        if not self.graph.can_transition(source.stage, target_stage):
            raise InvalidTransitionError(
                f"cannot derive {target_stage.value!r} from a source at "
                f"{source.stage.value!r}: valid next steps "
                f"are {self.graph.next_stages(source.stage)}"
            )
        art = self.registry.register(output_path, project=project or source.project)
        art.dependencies.add(source.id)
        art.stage = target_stage
        self.registry._by_type[art.type].discard(art.id)
        art.type = ArtifactType(target_stage.value)
        self.registry._by_type[art.type].add(art.id)
        self.registry._reindex_stage(art)
        return art

    def advance(self, artifact_id: str, to_stage: Stage) -> Artifact:
        """Advance an artifact to a later stage (validated by the graph)."""
        art = self.registry.get(artifact_id)
        self.graph.validate_transition(art.stage, to_stage)
        art.stage = to_stage
        self.registry._reindex_stage(art)
        return art

    def can_advance(self, artifact_id: str) -> list[Stage]:
        art = self.registry.get(artifact_id)
        return self.graph.next_stages(art.stage)

    def readiness(self, artifact_id: str) -> dict[str, Any]:
        art = self.registry.get(artifact_id)
        return {
            "id": art.id,
            "name": art.name,
            "stage": art.stage.value,
            "next": [s.value for s in self.can_advance(artifact_id)],
            "is_finished": not self.graph.has_next(art.stage),
        }

    # -- navigation ---------------------------------------------------------
    def browse(
        self,
        project: Optional[str] = None,
        type_: Optional[str] = None,
        stage: Optional[str] = None,
    ) -> list[Artifact]:
        t = ArtifactType(type_) if type_ else None
        s = Stage(stage) if stage else None
        return self.registry.filter(project=project, type_=t, stage=s)

    def all_renders(self) -> list[Artifact]:
        """Finished animations & renders — viewable in one place."""
        return self.registry.filter(viewable_only=True)

    def dependencies_of(self, artifact_id: str) -> list[Artifact]:
        art = self.registry.get(artifact_id)
        return [self.registry.get(d) for d in sorted(art.dependencies)]

    def dependents_of(self, artifact_id: str) -> list[Artifact]:
        art = self.registry.get(artifact_id)
        return sorted(
            (a for a in self.registry.all() if artifact_id in a.dependencies),
            key=lambda a: a.name,
        )

    def group_by(self, field_name: str) -> dict[str, list[Artifact]]:
        return self.registry.group_by(field_name)

    def workflow(self) -> dict[str, list[str]]:
        return self.graph.edges()

    def stats(self) -> dict[str, Any]:
        return self.registry.stats()

    # -- persistence --------------------------------------------------------
    def persist(self) -> None:
        if self.store is None:
            raise RuntimeError("no catalog store configured; pass store= to pipeline")
        self.store.save(self.registry.all())

    def load_from_store(self) -> int:
        if self.store is None:
            raise RuntimeError("no catalog store configured; pass store= to pipeline")
        for art in self.store.load():
            if art.id not in self.registry:
                self.registry.register(
                    art.path,
                    project=art.project,
                    type_=art.type,
                    stage=art.stage,
                    dependencies=art.dependencies,
                    metadata=art.metadata,
                    artifact_id=art.id,
                )
        return len(self.registry)

    def scan(self, root: str, project: Optional[str] = None) -> list[Artifact]:
        return self.registry.scan(root, project=project)
