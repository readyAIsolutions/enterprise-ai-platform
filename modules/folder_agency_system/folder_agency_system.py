"""Pure-logic core for the ``folder_agency_system`` module.

Grounding: JEVanClief, "Your Start Up is going to be Replaced by a Folder."
(https://www.youtube.com/watch?v=XIk-Ru85xmA).  The transcript argues that an
AI startup's work -- its capabilities, projects, and agents -- should be
organized not by a swarm of hundreds of hand-tuned agents but by a well
maintained **folder hierarchy** that one good *librarian* agent can walk
through.  Key ideas realised here:

* *Second brains / Jarvis databases* are "just a bunch of folders carrying
  sequences, hierarchies, markdown processes and states" -- the catalog the
  AI (the librarian) wanders through to decide *how, when and where* to act.
* *Folders carry capabilities, projects and agents*: the folder structure is
  the organization of the AI startup, and good file management means the
  whole thing "organizes itself" so a simple question can bring the right
  folders and files to the agent.
* *Templates as deployed software*: an ICM/second-brain template is "a
  deployed software, a small one, a package solving a certain problem".  A
  template is imported once and its initial state is version one -- it "isn't
  going anywhere" -- and a user can start a *workbench* which is "copying and
  building out that layer" as a deployable mini-copy anyone in the org can
  activate and collaborate inside of.
* *The Atlas*: a company's logic, "guaranteed facts that aren't going to be
  edited a lot", the condensed second brain other workbenches may access
  (with anonymization / read-only access) instead of the full editable brain.
* *The librarian, not hundreds of agents*: "you don't need hundreds of
  agents. You need the organization of the library and one good librarian."
  The card catalog is "how to talk about data" -- high-signal summaries that
  point to where the real detail lives.
* *Multi-user scale + governance*: bigger companies need "a little bit more
  governance, compliance and monitoring" on top of the folder freedom.

This module is **stdlib-only and network-free**; it materialises an on-disk
folder agency rooted at a local directory (typically ``tmp_path`` in tests).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class FolderKind(Enum):
    """The kinds of folder in the agency hierarchy."""

    ROOT = "root"
    CAPABILITY = "capability"
    PROJECT = "project"
    AGENT = "agent"
    ATLAS = "atlas"
    WORKBENCH = "workbench"
    TEMPLATE = "template"


# Name of the markdown card that carries the high-signal summary of a folder.
CARD_FILE = "README.md"
# Sub-folder that holds the immutable template source (version one).
_TEMPLATES_DIR = "templates"
_WORKBENCHES_DIR = "workbenches"
_ATLAS_DIR = "atlas"
_CAPABILITIES_DIR = "capabilities"
_PROJECTS_DIR = "projects"
_AGENTS_DIR = "agents"


@dataclass
class FolderNode:
    """A single node in the agency folder hierarchy.

    Attributes:
        name: Leaf name of the folder.
        kind: The FolderKind of this node.
        description: High-signal summary stored in the node's markdown card.
        children: Nested child nodes, keyed by their folder name.
        path: Absolute filesystem path backing this node.
    """

    name: str
    kind: FolderKind
    description: str = ""
    children: Dict[str, "FolderNode"] = field(default_factory=dict)
    path: Optional[Path] = None

    def is_container(self) -> bool:
        """Return True if this node is one of the top-level container kinds."""
        return self.kind in (FolderKind.ROOT, FolderKind.WORKBENCH)

    def to_dict(self) -> Dict[str, Any]:
        """JSON-serialisable snapshot of this node."""
        return {
            "name": self.name,
            "kind": self.kind.value,
            "description": self.description,
            "path": str(self.path) if self.path else None,
            "children": {k: v.to_dict() for k, v in sorted(self.children.items())},
        }


class FolderAgencyError(Exception):
    """Raised on invalid folder-agency operations."""


class FolderAgency:
    """An on-disk folder hierarchy organising an AI startup's work.

    The agency materialises a root folder containing ``capabilities/``,
    ``projects/``, ``agents/``, ``templates/``, ``workbenches/`` and
    ``atlas/``.  Each node is backed by a real directory plus a ``README.md``
    card carrying the high-signal description so a librarian agent can answer
    "what's going on in here?" purely from markdown.

    Args:
        root: Local directory that will hold the agency.  Created on first use.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._tree: Optional[FolderNode] = None

    # ── scaffold / structure ────────────────────────────────────────────────
    def scaffold(self) -> FolderNode:
        """Create the top-level container folders and their markdown cards.

        Returns:
            The newly built root FolderNode.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        root_node = FolderNode(
            name=self.root.name or "agency",
            kind=FolderKind.ROOT,
            description="AI startup organization: capabilities, projects, agents.",
            path=self.root,
        )
        self._ensure_container(self.root / _CAPABILITIES_DIR, FolderKind.CAPABILITY)
        self._ensure_container(self.root / _PROJECTS_DIR, FolderKind.PROJECT)
        self._ensure_container(self.root / _AGENTS_DIR, FolderKind.AGENT)
        self._ensure_container(self.root / _TEMPLATES_DIR, FolderKind.TEMPLATE)
        self._ensure_container(self.root / _WORKBENCHES_DIR, FolderKind.WORKBENCH)
        self._ensure_container(self.root / _ATLAS_DIR, FolderKind.ATLAS)

        for child in _CONTAINERS:
            root_node.children[child] = self._build_node(self.root / child)

        self._tree = root_node
        return root_node

    def _ensure_container(self, path: Path, kind: FolderKind) -> FolderNode:
        """Create a container folder plus its README card and return its node."""
        path.mkdir(parents=True, exist_ok=True)
        node = FolderNode(name=path.name, kind=kind, description=_DEFAULT_DESC[kind], path=path)
        _write_card(path, node.description)
        return node

    # ── node creation ───────────────────────────────────────────────────────
    def create_capability(self, name: str, description: str = "") -> FolderNode:
        """Create a capability folder (what the startup can do) under capabilities/."""
        self._create_node(_CAPABILITIES_DIR, name, FolderKind.CAPABILITY, description)
        self._rebuild_container_children(FolderKind.CAPABILITY)
        return self._children_of(FolderKind.CAPABILITY)[-1]

    def create_project(self, name: str, description: str = "") -> FolderNode:
        """Create a project folder (a concrete piece of work) under projects/."""
        node = self._create_node(_PROJECTS_DIR, name, FolderKind.PROJECT, description)
        self._rebuild_container_children(FolderKind.PROJECT)
        return node

    def create_agent(self, name: str, role: str = "") -> FolderNode:
        """Create an agent folder under agents/ describing one agent's role."""
        node = self._create_node(_AGENTS_DIR, name, FolderKind.AGENT, role)
        self._rebuild_container_children(FolderKind.AGENT)
        return node

    def _create_node(
        self,
        parent_dir: str,
        name: str,
        kind: FolderKind,
        description: str,
    ) -> FolderNode:
        self._ensure_scaffolded()
        clean = _safe_name(name)
        folder = self.root / parent_dir / clean
        if folder.exists():
            raise FolderAgencyError(f"Folder already exists: {folder}")
        folder.mkdir(parents=True, exist_ok=False)
        node = FolderNode(name=clean, kind=kind, description=description, path=folder)
        _write_card(folder, description)
        return node

    # ── templates & workbenches (deployed software) ─────────────────────────
    def import_template(self, name: str, description: str = "") -> FolderNode:
        """Import a template: its initial state is version one, kept immutable.

        Templates are "a deployed software, a small package solving a certain
        problem".  The imported source directory is never mutated afterwards;
        workbenches are built as copies of it.
        """
        node = self._create_node(_TEMPLATES_DIR, name, FolderKind.TEMPLATE, description)
        self._rebuild_container_children(FolderKind.TEMPLATE)
        return node

    def create_workbench(self, template: str, name: str) -> FolderNode:
        """Start a workbench by copying a template ("building out that layer").

        Anyone in the organization can activate a workbench; it is a
        deployable mini-copy of the template so the immutable version one
        template is never touched.
        """
        self._ensure_scaffolded()
        src = self.root / _TEMPLATES_DIR / _safe_name(template)
        if not src.is_dir():
            raise FolderAgencyError(f"Unknown template: {template}")
        dst = self.root / _WORKBENCHES_DIR / _safe_name(name)
        if dst.exists():
            raise FolderAgencyError(f"Workbench already exists: {dst}")
        dst.mkdir(parents=True, exist_ok=False)
        _copy_tree(src, dst)
        node = FolderNode(
            name=dst.name,
            kind=FolderKind.WORKBENCH,
            description=f"Deployed workbench from template '{template}'.",
            path=dst,
        )
        _write_card(dst, node.description)
        self._rebuild_container_children(FolderKind.WORKBENCH)
        return node

    def list_workbenches(self) -> List[FolderNode]:
        """Return the deployed workbenches in this agency."""
        self._ensure_scaffolded()
        return self._children_of(FolderKind.WORKBENCH)

    # ── atlas (guaranteed facts, read-mostly) ───────────────────────────────
    def create_atlas(self, name: str, facts: Optional[Dict[str, Any]] = None) -> FolderNode:
        """Create an Atlas: the company's guaranteed facts, rarely edited.

        Unlike an editable workbench, an Atlas holds stable facts other
        workbenches can consult (optionally anonymized / read-only).  Facts are
        persisted as JSON alongside the markdown card.
        """
        node = self._create_node(_ATLAS_DIR, name, FolderKind.ATLAS, "Guaranteed facts (stable).")
        facts_path = node.path / "facts.json"
        facts_path.write_text(
            json.dumps(facts or {}, indent=2, sort_keys=True), encoding="utf-8"
        )
        self._rebuild_container_children(FolderKind.ATLAS)
        return node

    def read_atlas(self, name: str) -> Dict[str, Any]:
        """Read the facts of a named Atlas (read-only access to stable data)."""
        self._ensure_scaffolded()
        facts_path = self.root / _ATLAS_DIR / _safe_name(name) / "facts.json"
        if not facts_path.is_file():
            raise FolderAgencyError(f"No Atlas named: {name}")
        return json.loads(facts_path.read_text(encoding="utf-8"))

    # ── librarian / query ───────────────────────────────────────────────────
    def librarian_query(self, needle: str) -> List[FolderNode]:
        """The one good librarian: walk the library and return matching nodes.

        Matches are found against node names and their README cards
        (case-insensitive substring), so a simple question can bring the right
        folders and files to the agent.
        """
        self._ensure_scaffolded()
        needle_l = needle.lower()
        hits: List[FolderNode] = []

        def _walk(node: FolderNode) -> None:
            if needle_l in node.name.lower() or needle_l in node.description.lower():
                hits.append(node)
            for child in node.children.values():
                _walk(child)

        _walk(self.tree)
        return hits

    def render_tree(self) -> str:
        """Render the folder hierarchy as a human-readable indented tree."""
        lines: List[str] = []

        def _render(node: FolderNode, indent: int = 0) -> None:
            marker = "[d]" if node.path and node.path.is_dir() else "[ ]"
            lines.append(f"{'  ' * indent}{marker} {node.name}  ({node.kind.value})")
            for child in node.children.values():
                _render(child, indent + 1)

        _render(self.tree)
        return "\n".join(lines)

    def manifest(self) -> Dict[str, Any]:
        """Return a JSON-serialisable manifest of the whole agency."""
        return self.tree.to_dict()

    # ── internal helpers ────────────────────────────────────────────────────
    @property
    def tree(self) -> FolderNode:
        if self._tree is None:
            self.scaffold()
        return self._tree  # type: ignore[return-value]

    def _ensure_scaffolded(self) -> None:
        if self._tree is None:
            self.scaffold()

    def _build_node(self, path: Path) -> FolderNode:
        card = path / CARD_FILE
        desc = card.read_text(encoding="utf-8") if card.is_file() else ""
        node = FolderNode(name=path.name, kind=_kind_of_dir(path), description=desc, path=path)
        for child in sorted(path.iterdir()):
            if child.is_dir() and not child.name.startswith("."):
                node.children[child.name] = self._build_node(child)
        return node

    def _rebuild_container_children(self, kind: FolderKind) -> None:
        """Re-scan a top-level container so new nodes show up in the tree."""
        dirname = _CONTAINER_DIR[kind]
        container = self.root / dirname
        self.tree.children[dirname] = self._build_node(container)

    def _children_of(self, kind: FolderKind) -> List[FolderNode]:
        dirname = _CONTAINER_DIR[kind]
        container_node = self.tree.children.get(dirname)
        if container_node is None:
            return []
        return [n for n in container_node.children.values() if n.kind is kind]


# Container dir -> the top-level directory name it maps to.
_CONTAINER_DIR: Dict[FolderKind, str] = {
    FolderKind.CAPABILITY: _CAPABILITIES_DIR,
    FolderKind.PROJECT: _PROJECTS_DIR,
    FolderKind.AGENT: _AGENTS_DIR,
    FolderKind.TEMPLATE: _TEMPLATES_DIR,
    FolderKind.WORKBENCH: _WORKBENCHES_DIR,
    FolderKind.ATLAS: _ATLAS_DIR,
}
_CONTAINERS: List[str] = list(_CONTAINER_DIR.values())

_DEFAULT_DESC: Dict[FolderKind, str] = {
    FolderKind.CAPABILITY: "What the startup can do.",
    FolderKind.PROJECT: "Concrete pieces of work being done.",
    FolderKind.AGENT: "Agents arrayed across the folder hierarchy.",
    FolderKind.TEMPLATE: "Immutable version-one templates (deployed software).",
    FolderKind.WORKBENCH: "Deployable workbench copies of a template.",
    FolderKind.ATLAS: "Guaranteed facts; stable, read-mostly.",
}


def _safe_name(name: str) -> str:
    """Make a name safe to use as a single folder component."""
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name.strip())
    if not cleaned:
        raise FolderAgencyError("Folder name must contain at least one alphanumeric char.")
    return cleaned


def _write_card(folder: Path, description: str) -> None:
    """Write the high-signal markdown card for a folder."""
    (folder / CARD_FILE).write_text(description, encoding="utf-8")


def _copy_tree(src: Path, dst: Path) -> None:
    """Copy a template directory tree into a workbench."""
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=False)
            _copy_tree(item, target)
        else:
            target.write_bytes(item.read_bytes())


def _kind_of_dir(path: Path) -> FolderKind:
    """Infer a FolderKind from a directory's location in the hierarchy."""
    parent = path.parent.name if path.parent else ""
    if parent == _CAPABILITIES_DIR:
        return FolderKind.CAPABILITY
    if parent == _PROJECTS_DIR:
        return FolderKind.PROJECT
    if parent == _AGENTS_DIR:
        return FolderKind.AGENT
    if parent == _TEMPLATES_DIR:
        return FolderKind.TEMPLATE
    if parent == _WORKBENCHES_DIR:
        return FolderKind.WORKBENCH
    if parent == _ATLAS_DIR:
        return FolderKind.ATLAS
    return FolderKind.ROOT
