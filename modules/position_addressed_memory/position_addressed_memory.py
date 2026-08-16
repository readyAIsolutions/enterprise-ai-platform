"""Position-addressed memory — *folder-as-memory* for AI context.

Grounded in the JEVanClief transcript *"How I Run Creative, Software, and
Business Work as One System"* (https://www.youtube.com/watch?v=hALln9wrrQo).

The transcript identifies **three bets** on what "memory" means for an LLM:

* **OpenBrain / vector embeddings  -> CONTENT addressed** — "take everything
  you've ever written, turn it into numbers, ask the model to find what's
  similar. It works. It's also slow to set up, expensive to maintain, and
  sometimes it can be very brittle" (returns "nine vaguely related notes").
* **Karpathy's LLM wiki            -> LINK addressed** — maintainable markdown
  entity pages, "contradictions are flagged, orphan pages are found"; the
  trade is that "you need a maintenance LLM running constantly."
* **the folder system             -> POSITION addressed** — "the folder system
  you already have and your own brain."

The key mechanic implemented here is the folder-as-memory cascade: a root
``CLAUDE.md`` whose rules **cascade down**, per-project ``Context.md`` that
**layers on top**, and per-file scene/convention docs. "By the time Claude
reads the scene, it has already inherited the brand voice, the production
rules, the specific shot list. Nothing got embedded, nothing's getting
retrieved. The location of the information and the actual routing of it did
the work." This mirrors "Unix environment variables scope down" and "CSS
specificity scopes down" — "the folder name is a namespace, the namespace
carries meaning."

:class:`ContextStack` walks a filesystem path root->leaf collecting the
inherited rules; :class:`PathResolver` turns a path into its meaningful
namespace; and :class:`MemoryAddressing` models all three addressing modes
(position / content-hash / link) behind a deterministic resolver.

Stdlib-only, network-free, deterministic. No numpy / pandas / requests.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# Constants grounded in the transcript
# ---------------------------------------------------------------------------

#: Root context file whose rules *cascade down* to every descendant.
ROOT_CONTEXT_FILE = "CLAUDE.md"
#: Per-project context file that *layers on top* of inherited rules.
PROJECT_CONTEXT_FILE = "Context.md"
#: Convention/per-file context documents checked alongside any file.
CONVENTION_CONTEXT_FILES = ("CLAUDE.md", "Context.md")

#: The three bets on what memory means for an LLM (transcript).
POSITION_ADDRESSED = "position"  # the folder system
CONTENT_ADDRESSED = "content"    # vector embeddings / content hash
LINK_ADDRESSED = "link"          # wiki-style entity pages

DEFAULT_RULE_FILES = (ROOT_CONTEXT_FILE, PROJECT_CONTEXT_FILE)


class AddressingMode(Enum):
    """Which memory addressing bet a resolution came from."""

    POSITION = POSITION_ADDRESSED
    CONTENT = CONTENT_ADDRESSED
    LINK = LINK_ADDRESSED


class Precedence(Enum):
    """How conflicting keys across stacked context layers are resolved.

    ``DEEPEST`` (default) mirrors the transcript — "Context.md inside the
    project layers on top", i.e. the most specific (deepest) rule wins, just
    like CSS specificity scopes down. ``SHALLOWEST`` makes the root rule win.
    """

    DEEPEST = "deepest"
    SHALLOWEST = "shallowest"


# ---------------------------------------------------------------------------
# ContextRule
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")
_KV_RE = re.compile(r"^([A-Za-z_][\w .-]*?)\s*:\s*(.*?)\s*$")


def _normalize_key(raw: str) -> str:
    """Normalise a heading/title into a lookup key (``Brand Voice`` -> ``brand_voice``)."""
    return "_".join(raw.strip().lower().split())


@dataclass(frozen=True)
class ContextRule:
    """A single inherited context rule discovered along a filesystem path.

    Attributes:
        key: Normalised lookup key (e.g. ``"brand_voice"``).
        title: Original human-readable heading (e.g. ``"Brand Voice"``).
        value: The rule body.
        source: Filename the rule came from (``CLAUDE.md`` / ``Context.md``).
        path: Absolute path of the context file that declared this rule.
        order: Stack position (0 == root, increasing toward the leaf).
    """

    key: str
    value: str
    source: str = PROJECT_CONTEXT_FILE
    path: str = ""
    title: str = ""
    order: int = 0

    def __post_init__(self) -> None:
        if not self.title:
            object.__setattr__(self, "title", self.key)

    @property
    def is_root(self) -> bool:
        """True when this rule came from a root (cascading) context file."""
        return self.source == ROOT_CONTEXT_FILE

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "title": self.title,
            "value": self.value,
            "source": self.source,
            "path": self.path,
            "order": self.order,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "ContextRule":
        return cls(
            key=str(data["key"]),
            title=str(data.get("title", "")),
            value=str(data.get("value", "")),
            source=str(data.get("source", PROJECT_CONTEXT_FILE)),
            path=str(data.get("path", "")),
            order=int(str(data.get("order", 0))),
        )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"<ContextRule {self.key!r} source={self.source!r} "
            f"order={self.order} path={self.path!r}>"
        )


def parse_markdown_context(
    content: str,
    path: str = "",
    source: str = PROJECT_CONTEXT_FILE,
    order: int = 0,
) -> list[ContextRule]:
    """Parse a markdown context document into :class:`ContextRule` objects.

    Supports both ``## Heading`` blocks (the heading is the key, the indented
    body lines become the value) and ``key: value`` lines. Returns rules in
    document order, all tagged with ``path`` / ``source`` / ``order``.
    """
    rules: list[ContextRule] = []
    heading: Optional[str] = None
    heading_lines: list[str] = []

    def flush_heading() -> None:
        nonlocal heading, heading_lines
        if heading is not None:
            rules.append(
                ContextRule(
                    key=_normalize_key(heading),
                    title=heading.strip(),
                    value="\n".join(heading_lines).strip(),
                    source=source,
                    path=path,
                    order=order,
                )
            )
        heading = None
        heading_lines = []

    for raw in content.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        head_match = _HEADING_RE.match(stripped)
        if head_match:
            flush_heading()
            heading = head_match.group(1)
            continue
        if heading is not None:
            heading_lines.append(stripped)
            continue
        kv_match = _KV_RE.match(stripped)
        if kv_match:
            key_raw, value = kv_match.group(1), kv_match.group(2)
            rules.append(
                ContextRule(
                    key=_normalize_key(key_raw),
                    title=key_raw.strip(),
                    value=value,
                    source=source,
                    path=path,
                    order=order,
                )
            )
    flush_heading()
    return rules


# ---------------------------------------------------------------------------
# ContextStack — the cascade (root -> leaf)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ContextLayer:
    """One directory's worth of context rules, with its owning directory."""

    directory: str
    rules: tuple[ContextRule, ...]

    def keys(self) -> set[str]:
        return {r.key for r in self.rules}


class ContextStack:
    """Walks a filesystem path from root to leaf collecting inherited rules.

    Every directory from the configured ``root`` down to the target file is
    inspected for context rule files (``CLAUDE.md`` and ``Context.md`` by
    default). Rules collected this way are *inherited*: the root's
    ``CLAUDE.md`` cascades down to every descendant, while a project's
    ``Context.md`` layers on top of it — exactly the transcript's mechanic.

    Conflicting keys are resolved with a fixed :class:`Precedence`:
    ``DEEPEST`` (default, most specific rule wins) or ``SHALLOWEST`` (the root
    rule wins). No network; purely local filesystem reads.
    """

    def __init__(
        self,
        root: str,
        rule_files: tuple[str, ...] = DEFAULT_RULE_FILES,
        precedence: Precedence | str = Precedence.DEEPEST,
        loader: Optional[Callable[[str], Optional[str]]] = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.rule_files = tuple(rule_files)
        self.precedence = Precedence(precedence)
        #: loader(path) -> text; defaults to reading local files.
        self._loader = loader or self._default_loader

    @staticmethod
    def _default_loader(path: str) -> Optional[str]:
        p = Path(path)
        try:
            return p.read_text(encoding="utf-8") if p.is_file() else None
        except OSError:
            return None

    # ------------------------------------------------------------------ walk
    def ancestors(self, path: str) -> list[Path]:
        """Directories from root (inclusive) down to the file's parent (inclusive)."""
        target = Path(path).resolve()
        if target != self.root and self.root not in target.parents:
            raise ValueError(f"path {target} is not under root {self.root}")
        chain: list[Path] = [self.root]
        if target == self.root:
            return chain
        rel = target.relative_to(self.root)
        parent_parts = rel.parts[:-1]
        cur = self.root
        for part in parent_parts:
            cur = cur / part
            chain.append(cur)
        return chain

    # -------------------------------------------------------------- collect
    def collect(self, path: str) -> list[ContextLayer]:
        """Collect inherited context layers for ``path``, ordered root -> leaf.

        Every directory from root down to the file's parent is inspected for
        rule files; the target file itself (a per-file scene/convention doc)
        is parsed as the deepest layer, so opening a file inherits brand
        voice, production rules *and* the specific shot list.
        """
        layers: list[ContextLayer] = []
        for order, directory in enumerate(self.ancestors(path)):
            rules: list[ContextRule] = []
            for filename in self.rule_files:
                file_path = directory / filename
                text = self._loader(str(file_path))
                if text is None:
                    continue
                rules.extend(
                    parse_markdown_context(
                        text,
                        path=str(file_path),
                        source=filename,
                        order=order,
                    )
                )
            if rules:
                layers.append(ContextLayer(str(directory), tuple(rules)))
        # the file itself is the deepest context layer (per-file convention doc)
        target = Path(path).resolve()
        if target.is_file() and target.name not in self.rule_files:
            text = self._loader(str(target))
            if text is not None:
                file_rules = parse_markdown_context(
                    text,
                    path=str(target),
                    source=target.name,
                    order=len(layers),
                )
                if file_rules:
                    layers.append(ContextLayer(str(target), tuple(file_rules)))
        return layers

    def rules_for(self, path: str) -> list[ContextRule]:
        """Flatten all inherited rules for ``path`` in root->leaf document order."""
        flat: list[ContextRule] = []
        for layer in self.collect(path):
            flat.extend(layer.rules)
        return flat

    # -------------------------------------------------------------- resolve
    def resolve(self, path: str) -> dict[str, str]:
        """Merge inherited rules into a key->value map for ``path``.

        With :class:`Precedence.DEEPEST` (default) the deepest, most specific
        rule for a key wins — matching the transcript's "Context.md layers on
        top" and CSS-specificity scoping. With :class:`Precedence.SHALLOWEST`
        the root rule wins.
        """
        rules = self.rules_for(path)
        merged: dict[str, str] = {}
        if self.precedence is Precedence.SHALLOWEST:
            # first (root-most) occurrence wins
            seen: set[str] = set()
            for rule in rules:
                if rule.key in seen:
                    continue
                seen.add(rule.key)
                merged[rule.key] = rule.value
        else:
            # DEEPEST: last (leaf-most) occurrence wins
            for rule in rules:
                merged[rule.key] = rule.value
        return merged

    def resolve_rule(self, path: str, key: str) -> Optional[ContextRule]:
        """Return the winning :class:`ContextRule` for ``key`` at ``path``."""
        rules = self.rules_for(path)
        if not rules:
            return None
        if self.precedence is Precedence.SHALLOWEST:
            for rule in rules:
                if rule.key == key:
                    return rule
            return None
        winner: Optional[ContextRule] = None
        for rule in rules:
            if rule.key == key:
                winner = rule
        return winner


# ---------------------------------------------------------------------------
# PathResolver — the path as a namespace
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PathResolution:
    """The meaning a filesystem path carries on its own (no retrieval)."""

    path: str
    root: str
    namespaces: tuple[str, ...]  # meaningful folder-name namespace, root->leaf
    filename: str
    depth: int  # number of namespaces between root and the file


class PathResolver:
    """Turns a filesystem path into its meaningful namespace.

    The transcript: "The folder name is a namespace. The namespace carries
    meaning. We just didn't have a model that could read it before." Resolving
    a path by *position* is exactly this: the path itself — video work, the
    client, the pipeline, the scene — does the routing.
    """

    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()

    def is_within(self, path: str) -> bool:
        p = Path(path).resolve()
        return p == self.root or self.root in p.parents

    def relative(self, path: str) -> Path:
        p = Path(path).resolve()
        if not self.is_within(path):
            raise ValueError(f"path {p} is not under root {self.root}")
        return p.relative_to(self.root)

    def resolve(self, path: str) -> PathResolution:
        rel = self.relative(path)
        parts = rel.parts
        filename = parts[-1] if parts else rel.name
        namespaces = parts[:-1]
        return PathResolution(
            path=str(Path(path).resolve()),
            root=str(self.root),
            namespaces=namespaces,
            filename=filename,
            depth=len(namespaces),
        )

    def namespace_path(self, path: str) -> str:
        """Return the position address as a slash-joined namespace string."""
        res = self.resolve(path)
        return "/".join(res.namespaces) if res.namespaces else "."


# ---------------------------------------------------------------------------
# The three addressing modes
# ---------------------------------------------------------------------------

@dataclass
class PositionHit:
    """A position-addressed resolution: content + inherited context."""

    path: str
    content: Optional[str]
    context: dict[str, str]
    namespaces: tuple[str, ...]
    mode: AddressingMode = AddressingMode.POSITION

    def has_context(self, key: str) -> bool:
        return key in self.context

    def context_of(self, key: str) -> Optional[str]:
        return self.context.get(key)


@dataclass
class ContentHit:
    """A content-addressed resolution by SHA-256 digest."""

    digest: str
    content: Optional[str]
    mode: AddressingMode = AddressingMode.CONTENT


@dataclass
class LinkHit:
    """A link-addressed resolution from a wiki-style entity name."""

    name: str
    content: Optional[str]
    target: Optional[str] = None
    mode: AddressingMode = AddressingMode.LINK


class ContentStore:
    """Content-addressed memory: address content by its SHA-256 digest.

    Mirrors the OpenBrain / vector-embedding bet (content is the address) but
    implemented deterministically with a real content hash — "you take
    everything you've ever written, you turn it into numbers, you ask the
    model to find what's similar."
    """

    def __init__(self) -> None:
        self._by_digest: dict[str, str] = {}

    @staticmethod
    def digest(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def address(self, content: str) -> str:
        """Store and return the content's SHA-256 address (deduplicated)."""
        digest = self.digest(content)
        self._by_digest.setdefault(digest, content)
        return digest

    def resolve(self, digest: str) -> Optional[str]:
        return self._by_digest.get(digest)

    def contains(self, content: str) -> bool:
        return self.digest(content) in self._by_digest

    def lookup(self, query: str) -> ContentHit:
        """Resolve a query by content hash (also accept a bare hash)."""
        if re.fullmatch(r"[0-9a-f]{64}", query) and query in self._by_digest:
            return ContentHit(digest=query, content=self._by_digest[query])
        digest = self.digest(query)
        return ContentHit(digest=digest, content=self._by_digest.get(digest))

    def __len__(self) -> int:
        return len(self._by_digest)


class LinkStore:
    """Link-addressed memory: wiki-style entity pages with edges.

    Mirrors the Karpathy-LLM-wiki bet: markdown entity pages maintained by an
    agent, where "contradictions are flagged" and "orphan pages are found".
    A page is *defined* (name -> content) and can *reference* other names;
    referencing the same name with conflicting targets is flagged as a
    contradiction, and referenced-but-never-defined names are orphans.
    """

    def __init__(self) -> None:
        self._defs: dict[str, str] = {}
        self._refs: dict[str, set[str]] = {}

    def define(self, name: str, content: str) -> None:
        self._defs[name.strip()] = content

    def reference(self, name: str, target: str) -> None:
        """Record a directed link ``name -> target``; flag contradictions."""
        self._refs.setdefault(name.strip(), set()).add(target.strip())

    def resolve(self, name: str) -> Optional[str]:
        return self._defs.get(name.strip())

    def target(self, name: str) -> Optional[str]:
        """Resolve a name through one hop to a defined page's content."""
        refs = self._refs.get(name.strip())
        if not refs:
            return self._defs.get(name.strip())
        for ref in refs:
            if ref in self._defs:
                return self._defs[ref]
        return None

    def lookup(self, name: str) -> LinkHit:
        n = name.strip()
        content = self._defs.get(n) or self.target(n)
        return LinkHit(name=n, content=content, target=content and n if n in self._defs else None)

    def orphans(self) -> list[str]:
        """Names referenced but never defined (mirrors wiki orphan pages)."""
        return sorted(n for n in self._refs if n not in self._defs)

    def contradictions(self) -> list[tuple[str, set[str]]]:
        """Names referenced with more than one distinct target."""
        return [(n, targets) for n, targets in self._refs.items() if len(targets) > 1]

    def __len__(self) -> int:
        return len(self._defs)


# ---------------------------------------------------------------------------
# MemoryAddressing — the deterministic resolver across all three modes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Resolution:
    """Result of a deterministic resolution across the three addressing modes."""

    query: str
    mode: AddressingMode
    hit: object  # PositionHit | ContentHit | LinkHit
    alternatives: dict[str, object] = field(default_factory=dict)


class MemoryAddressing:
    """A memory-addressing model over all three bets from the transcript.

    Holds three backing stores — position (filesystem path + inherited
    context), content (SHA-256 hash) and link (wiki entity names) — and a
    *deterministic* resolver. Given an opaque query, resolution follows a fixed
    rule so the answer never depends on randomness:

    1. a 64-hex string is treated as a **content** digest;
    2. otherwise a value that looks like a filesystem path under ``root`` is
       resolved by **position** (loading inherited context along the way);
    3. otherwise the query is treated as a **link** (wiki entity name).
    """

    def __init__(
        self,
        root: str,
        rule_files: tuple[str, ...] = DEFAULT_RULE_FILES,
        precedence: Precedence | str = Precedence.DEEPEST,
    ) -> None:
        self.root = str(Path(root).resolve())
        self.context_stack = ContextStack(
            self.root, rule_files=rule_files, precedence=precedence
        )
        self.path_resolver = PathResolver(self.root)
        self.position_store: dict[str, str] = {}
        self.content = ContentStore()
        self.links = LinkStore()

    # ------------------------------------------------------------ the stores
    def store_position(self, path: str, content: str) -> str:
        """Store a file's content by its filesystem position."""
        resolved = str(Path(path).resolve())
        self.position_store[resolved] = content
        return resolved

    def store_content(self, content: str) -> str:
        return self.content.address(content)

    def store_link(self, name: str, content: str) -> None:
        self.links.define(name, content)

    def link(self, name: str, target: str) -> None:
        self.links.reference(name, target)

    # ------------------------------------------------------- position resolve
    def resolve_position(self, path: str) -> PositionHit:
        resolved = str(Path(path).resolve())
        res = self.path_resolver.resolve(path)
        content = self.position_store.get(resolved)
        if content is None:
            # fall back to reading the local file, if present (no network)
            p = Path(resolved)
            if p.is_file():
                try:
                    content = p.read_text(encoding="utf-8")
                except OSError:
                    content = None
        context = self.context_stack.resolve(resolved)
        return PositionHit(
            path=resolved,
            content=content,
            context=context,
            namespaces=res.namespaces,
        )

    def resolve_content(self, query: str) -> ContentHit:
        return self.content.lookup(query)

    def resolve_link(self, name: str) -> LinkHit:
        return self.links.lookup(name)

    # ------------------------------------------------------ deterministic API
    def _classify(self, query: str) -> AddressingMode:
        if re.fullmatch(r"[0-9a-f]{64}", query):
            return AddressingMode.CONTENT
        if "/" in query or "\\" in query:
            try:
                if self.path_resolver.is_within(query):
                    return AddressingMode.POSITION
            except ValueError:
                pass
        return AddressingMode.LINK

    def resolve(self, query: str) -> Resolution:
        """Deterministically resolve ``query`` through the addressing modes."""
        mode = self._classify(query)
        alternatives: dict[str, object] = {}
        if mode is AddressingMode.CONTENT:
            hit = self.resolve_content(query)
            if self.path_resolver.is_within(query):
                alternatives["position"] = self.resolve_position(query)
        elif mode is AddressingMode.POSITION:
            hit = self.resolve_position(query)
            alternatives["content"] = self.resolve_content(query)
        else:
            hit = self.resolve_link(query)
            alternatives["content"] = self.resolve_content(query)
        return Resolution(query=query, mode=mode, hit=hit, alternatives=alternatives)

    def inherited_context(self, path: str) -> dict[str, str]:
        """Return the full cascading context a file inherits from its path."""
        return self.context_stack.resolve(path)
