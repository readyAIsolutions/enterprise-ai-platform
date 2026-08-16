"""Unified Work System — creative, technical/software, and business as ONE system.

Grounded in the JEVanClief one-system thesis: creative work, software work,
and business work are the same problem wearing different clothes.  The
*artifact* is the center, and every lens looks at that same artifact and should
tell the same story.  AI is what makes it possible to run the three lenses as a
single unified system instead of three separate consultancies.

This module is *engineering*, not philosophy:

  IMPLEMENTED (real logic)
    * Artifact-centered WorkSystem rendering one artifact through N lenses.
    * Lens derivation — each lens extracts structured facts from the shared
      artifact (creative: audience/impact/mood; technical: stack/architecture/
      tasks; business: value/cost/market/revenue).
    * Lens-consistency check — detects when lenses disagree, i.e. whether they
      are actually telling the same story.
    * Memory model — a MemoryStore with a three-way addressing hierarchy
      (position / link / content) mirroring the transcript's three bets on
      memory, an explicit HumanMemory (the in-the-loop context machine) split
      from external AI memory, contradiction flagging and namespace cascade.

  NOT IMPLEMENTED (philosophy, not a feature)
    - "Consciousness", "taste", "the model replacing taste": a taste guardian is
      a *role* recorded by the creative lens, not a computable property.
    - Real vector embeddings (stdlib-only): content addressing uses a
      deterministic content signature + keyword overlap instead of an embedding
      model.

Pure stdlib, network-free, unit-testable.
"""

from __future__ import annotations

import hashlib
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, ClassVar

__all__ = [
    "COMMON_STORY_DIMENSIONS",
    "Artifact",
    "Lens",
    "CreativeLens",
    "TechnicalLens",
    "BusinessLens",
    "LensView",
    "ConsistencyReport",
    "WorkSystem",
    "MemoryItem",
    "MemoryStore",
    "HumanMemory",
    "ContextResolver",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: The story dimensions every lens is expected to be able to express.  If two
#: lenses give *different* answers for the same dimension, the three lenses are
#: NOT telling the same story — that is a consistency violation.
COMMON_STORY_DIMENSIONS: tuple[str, ...] = (
    "subject",            # what is this artifact about
    "audience",           # who is it for
    "success_definition", # what "done / good" looks like
    "key_constraint",     # what limits it (time, budget, taste)
    "primary_metric",     # the one number that says it worked
)

#: Addressing modes for the memory model, mirroring the transcript's three
#: "bets" on what AI memory means.
POSITION_ADDRESSED = "position"   # the folder system / namespace cascade
LINK_ADDRESSED = "link"           # the wiki / entity pages
CONTENT_ADDRESSED = "content"     # the vector store / content signature


# ---------------------------------------------------------------------------
# Artifact — the center of the unified work system
# ---------------------------------------------------------------------------

@dataclass
class Artifact:
    """The one thing every lens looks at.

    The artifact holds raw ground-truth *facts* (attribute -> value).  Each
    lens reads the facts it cares about through its own field map.  When the
    artifact's facts encode contradictory stories for the same dimension across
    lenses (e.g. a creative audience that differs from the business audience),
    the consistency check surfaces it.
    """

    name: str
    kind: str = "project"                       # video_project | brand_deck | software_system | ...
    client: str = ""
    description: str = ""
    facts: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Lenses — each derives structured facts from the same artifact
# ---------------------------------------------------------------------------

class Lens:
    """Base class for a work lens.

    A lens reads a shared :class:`Artifact` and produces a :class:`LensView`
    containing (a) its *story* — its answer for each common story dimension —
    and (b) its *specifics* — the lens-specific facts it is best placed to
    surface.
    """

    kind: str = "generic"

    #: Maps each common story dimension to the artifact.facts key it reads.
    dimension_fields: ClassVar[dict[str, str]] = {}
    #: Artifact.facts keys surfaced as lens-specific structured facts.
    specific_fields: ClassVar[tuple[str, ...]] = ()

    def derive(self, artifact: Artifact) -> LensView:
        """Extract a LensView from the artifact through this lens."""
        story: dict[str, Any] = {}
        for dim, key in self.dimension_fields.items():
            if key in artifact.facts:
                story[dim] = artifact.facts[key]
        specifics = {key: artifact.facts[key] for key in self.specific_fields if key in artifact.facts}
        return LensView(lens=self.kind, story=story, specifics=specifics)


class CreativeLens(Lens):
    """Creative lens — audience, impact, mood, taste guardianship.

    Tracks the transcript's point that AI handles "everything around the
    taste" (the logistics) while a human stays the taste guardian — so the
    lens records *who* guards taste (a role), not the taste itself.
    """

    kind = "creative"

    dimension_fields = {
        "subject": "creative_subject",
        "audience": "creative_audience",
        "success_definition": "creative_success",
        "key_constraint": "creative_constraint",
        "primary_metric": "creative_metric",
    }
    specific_fields = (
        "impact",       # intended emotional / audience impact
        "mood",         # mood / tone of the artifact
        "brand_voice",  # brand voice the artifact must inherit
        "taste_guardian",  # who keeps taste in the loop (a role)
        "deliverable",  # the artifact-as-deliverable
    )


class TechnicalLens(Lens):
    """The software/technical lens — stack, architecture, tasks, pipeline.

    Mirrors the transcript's observation that most "creative" work is actually
    *logistics*: resizing exports, renaming files, re-recording, color matching.
    The technical lens owns the pipeline/stack and the mechanical task list.
    """

    kind = "technical"

    dimension_fields = {
        "subject": "technical_subject",
        "audience": "technical_audience",
        "success_definition": "technical_success",
        "key_constraint": "technical_constraint",
        "primary_metric": "technical_metric",
    }
    specific_fields = (
        "stack",         # technologies / toolchain
        "architecture",  # how the pipeline is structured
        "tasks",         # concrete mechanical task list (the logistics)
        "pipeline",      # the production pipeline
        "namespace",     # where the artifact lives (position addressing)
    )


class BusinessLens(Lens):
    """The business lens — value, cost, market, revenue.

    Captures the transcript's story that the *same artifact* supports a whole
    range of business models: sell videos, sell the system, license the IP,
    become an advisor.  The business lens owns monetization and client value.
    """

    kind = "business"

    dimension_fields = {
        "subject": "business_subject",
        "audience": "business_audience",
        "success_definition": "business_success",
        "key_constraint": "business_constraint",
        "primary_metric": "business_metric",
    }
    specific_fields = (
        "value",          # client / deliverable value
        "cost",           # cost to produce / maintain
        "market",         # the market the artifact serves
        "revenue",        # revenue model(s) the artifact enables
        "business_model", # e.g. "vendor", "system license", "advisor"
    )


@dataclass
class LensView:
    """The output of running one lens over an artifact."""

    lens: str
    story: dict[str, Any] = field(default_factory=dict)
    specifics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"lens": self.lens, "story": self.story, "specifics": self.specifics}


@dataclass
class ConsistencyReport:
    """Result of checking whether all lenses tell the same story."""

    views: dict[str, LensView] = field(default_factory=dict)
    agreements: dict[str, Any] = field(default_factory=dict)
    disagreements: dict[str, dict[str, Any]] = field(default_factory=dict)
    unstated: dict[str, list[str]] = field(default_factory=dict)

    @property
    def consistent(self) -> bool:
        return not self.disagreements

    def summary(self) -> str:
        parts = [f"consistent={self.consistent}"]
        if self.agreements:
            parts.append("agreements=" + ",".join(sorted(self.agreements)))
        if self.disagreements:
            parts.append("DISAGREEMENTS=" + ",".join(sorted(self.disagreements)))
        if self.unstated:
            parts.append("unstated=" + ",".join(sorted(self.unstated)))
        return " | ".join(parts)


# ---------------------------------------------------------------------------
# WorkSystem — the artifact at the center, viewed through many lenses
# ---------------------------------------------------------------------------

class WorkSystem:
    """One artifact, many lenses, run as a single system.

    This is the engineering embodiment of the transcript's thesis: instead of
    three separate consultancies each owning a lens, a single system owns the
    artifact and every lens looks at it.  The system also carries the external
    AI memory (the folder/wiki/content store) and the human context that is
    always in the loop.
    """

    def __init__(
        self,
        artifact: Artifact | None = None,
        lenses: list[Lens] | None = None,
    ) -> None:
        self.artifact = artifact or Artifact(name="untitled")
        self.lenses: list[Lens] = list(lenses) if lenses is not None else [
            CreativeLens(),
            TechnicalLens(),
            BusinessLens(),
        ]
        self.memory = MemoryStore()
        self.human = HumanMemory()

    # -- lens registry ------------------------------------------------------

    def add_lens(self, lens: Lens) -> None:
        """Register an additional lens on this work system."""
        self.lenses.append(lens)

    def render(self) -> dict[str, LensView]:
        """Render the shared artifact through every lens at once."""
        views: dict[str, LensView] = {}
        for lens in self.lenses:
            views[lens.kind] = lens.derive(self.artifact)
        return views

    def check_consistency(self) -> ConsistencyReport:
        """Detect when the lenses disagree — i.e. are not telling one story.

        For each common story dimension, collect the answer every lens gave.
        If two or more lenses answered and their answers differ, that dimension
        is a disagreement.  Dimensions answered by fewer than two lenses are
        marked *unstated* (we simply don't have enough of the story to judge).
        """
        views = self.render()
        report = ConsistencyReport(views=views)

        dim_to_values: dict[str, dict[str, Any]] = {d: {} for d in COMMON_STORY_DIMENSIONS}
        for lens_name, view in views.items():
            for dim, value in view.story.items():
                dim_to_values.setdefault(dim, {})[lens_name] = value

        for dim, values in dim_to_values.items():
            if len(values) < 2:
                if values:
                    report.unstated[dim] = sorted(values)
                continue
            distinct = {_canon(value) for value in values.values()}
            if len(distinct) == 1:
                report.agreements[dim] = next(iter(values.values()))
            else:
                report.disagreements[dim] = dict(values)
        return report


# ---------------------------------------------------------------------------
# Memory — external AI memory vs human memory, three addressing modes
# ---------------------------------------------------------------------------

def _canon(value: Any) -> Any:
    """Canonicalize a value for cross-lens comparison.

    Lists are sorted so that order differences don't break consistency, and
    simple nested containers compare consistently; strings are stripped.
    """
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return tuple(sorted(_canon(v) for v in value))
    if isinstance(value, tuple):
        return tuple(sorted(_canon(v) for v in value))
    if isinstance(value, dict):
        return tuple(sorted((k, _canon(v)) for k, v in value.items()))
    return value


def _signature(content: str) -> str:
    """Deterministic content signature (stdlib stand-in for an embedding)."""
    norm = _normalize(content)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _normalize(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9']+", text.lower()))


def _overlap(query: str, content: str) -> float:
    """Jaccard-style keyword overlap in [0, 1] — deterministic content scoring."""
    q = set(_normalize(query).split())
    c = set(_normalize(content).split())
    if not q:
        return 0.0
    return len(q & c) / len(q | c) if (q | c) else 0.0


@dataclass
class MemoryItem:
    """A single unit of external AI memory.

    A memory item is addressable all three ways at once, mirroring the
    transcript's three bets on memory:
      * ``namespace`` -> position (the folder system)
      * ``links``     -> link (the wiki / entity pages)
      * ``content``   -> content (signature + keyword overlap)
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""
    kind: str = "note"              # note | entity | rule | brand-rule | ...
    namespace: str = "root"         # position addressing (path / namespace)
    subject: str = ""               # used for contradiction detection
    links: list[str] = field(default_factory=list)
    priority: int = 0               # higher = surfaced first
    created_at: float = field(default_factory=time.time)

    @property
    def signature(self) -> str:
        return _signature(self.content)


@dataclass
class HumanMemory:
    """The human context machine that stays in the loop.

    The transcript: "My brain is a powerful context machine.  We are creating
    systems that allow me to offload context to the AI while simultaneously
    using my context to amplify that process."  HumanMemory is deliberately
    separate from the external MemoryStore — the human directs, the store
    serves.
    """

    notes: dict[str, str] = field(default_factory=dict)          # key -> human note
    decisions: list[str] = field(default_factory=list)           # "the taste" / judgment calls
    focus: list[str] = field(default_factory=list)               # current attention terms

    def remember(self, key: str, note: str) -> None:
        self.notes[key] = note

    def decide(self, decision: str) -> None:
        """Record a human judgment call (the human, not the model, has taste)."""
        self.decisions.append(decision)

    def direct(self, term: str) -> None:
        if term not in self.focus:
            self.focus.append(term)


class MemoryStore:
    """External AI memory: memory items with a three-way addressing hierarchy.

    Provides position-addressed retrieval + namespace cascade (root rules flow
    down, like ``Claude.md`` at the root reaching every nested scene), link-
    addressed retrieval (BFS over ``links``), content-addressed retrieval
    (signature match + keyword overlap), and contradiction flagging (two items
    in the same namespace+subject with different content).
    """

    def __init__(self) -> None:
        self._items: dict[str, MemoryItem] = {}
        self._by_namespace: dict[str, list[str]] = {}
        self._by_signature: dict[str, str] = {}
        self._by_subject: dict[tuple[str, str], list[str]] = {}

    # -- mutation -----------------------------------------------------------

    def add(self, item: MemoryItem) -> str:
        """Store a memory item; returns the item's id."""
        if item.id in self._items:
            raise ValueError(f"memory item already exists: {item.id}")
        self._items[item.id] = item
        self._by_namespace.setdefault(item.namespace, []).append(item.id)
        self._by_signature.setdefault(item.signature, item.id)
        if item.subject:
            self._by_subject.setdefault((item.namespace, item.subject), []).append(item.id)
        return item.id

    def get(self, item_id: str) -> MemoryItem | None:
        return self._items.get(item_id)

    def contradictions(self) -> list[tuple[MemoryItem, MemoryItem]]:
        """Flag memory items that conflict (same namespace + subject, diff content)."""
        out: list[tuple[MemoryItem, MemoryItem]] = []
        for ids in self._by_subject.values():
            for i, lhs_id in enumerate(ids):
                lhs = self._items[lhs_id]
                for rhs_id in ids[i + 1 :]:
                    rhs = self._items[rhs_id]
                    if lhs.signature != rhs.signature:
                        out.append((lhs, rhs))
        return out

    # -- retrieval ----------------------------------------------------------

    def namespace_items(self, namespace: str) -> list[MemoryItem]:
        """All items stored directly at ``namespace`` (no cascade)."""
        ids = self._by_namespace.get(namespace, [])
        return [self._items[i] for i in ids]

    def cascade(self, namespace: str) -> list[MemoryItem]:
        """Position-addressed retrieval: items at ``namespace`` plus every
        ancestor namespace (the root context cascades down)."""
        parts = [p for p in namespace.split("/") if p]
        namespaces = []
        for i in range(1, len(parts) + 1):
            namespaces.append("/".join(parts[:i]))
        if namespace != "root":
            namespaces.append("root")
        seen: dict[str, MemoryItem] = {}
        for ns in namespaces:
            for item in self.namespace_items(ns):
                seen[item.id] = item
        return sorted(seen.values(), key=lambda i: -i.priority)

    def retrieve(self, query: str, mode: str = POSITION_ADDRESSED, seed: str | None = None) -> list[MemoryItem]:
        """Retrieve memory items by one of the three addressing modes.

        ``position`` -> cascade from ``query`` as a namespace; ``link`` -> BFS
        from ``seed``; ``content`` -> signature match + keyword overlap on
        ``query``.
        """
        if mode == POSITION_ADDRESSED:
            return self.cascade(query)

        if mode == LINK_ADDRESSED:
            if seed is None or seed not in self._items:
                return []
            visited: set[str] = set()
            order: list[MemoryItem] = []
            stack = [seed]
            while stack:
                cur = self._items[stack.pop()]
                if cur.id in visited:
                    continue
                visited.add(cur.id)
                order.append(cur)
                for link_id in cur.links:
                    if link_id in self._items and link_id not in visited:
                        stack.append(link_id)
            return sorted(order, key=lambda i: -i.priority)

        # content-addressed
        exact = self._by_signature.get(_signature(query))
        scored = [(item, _overlap(query, item.content)) for item in self._items.values()]
        scored.sort(key=lambda pair: (pair[0].priority, pair[1]), reverse=True)
        results = [item for item, score in scored if score > 0.0]
        if exact is not None and all(r.id != exact for r in results):
            results.insert(0, self._items[exact])
        return results


class ContextResolver:
    """Combine external AI memory and human memory into one ranked context.

    The human's focus terms weight the external results so the person who is
    *in the loop* steers what the AI surfaces — external memory amplifies the
    human context machine rather than replacing it.
    """

    @staticmethod
    def combine(human: HumanMemory, external: MemoryStore, query: str) -> list[MemoryItem]:
        results = external.retrieve(query, mode=CONTENT_ADDRESSED)
        focus = set(_normalize(t) for t in human.focus)
        if focus:
            def _rank(item: MemoryItem) -> float:
                item_terms = set(_normalize(item.content).split())
                return len(item_terms & focus)
            results.sort(key=_rank, reverse=True)
        return results


# ---------------------------------------------------------------------------
# Convenience constructors
# ---------------------------------------------------------------------------

def build_artifact(
    name: str,
    *,
    client: str = "",
    kind: str = "project",
    description: str = "",
    **facts: Any,
) -> Artifact:
    """Build an Artifact with the given facts.

    Facts follow the lens field conventions, e.g. ``creative_audience``,
    ``business_revenue``, ``stack``.  See :meth:`WorkSystem.check_consistency`
    for how mismatched lens fields surface as disagreements.
    """
    return Artifact(
        name=name,
        kind=kind,
        client=client,
        description=description,
        facts=dict(facts),
    )
