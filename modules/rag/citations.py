"""
Citation Handling for the RAG System.

Provides research-integrity citation management: citations are collected from
retrieved chunks, de-duplicated, and rendered in a variety of common styles
(APA, MLA, Chicago, IEEE, and a raw/NONE style). Purely stdlib-based, so it
works offline with no scientific-packages dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence


# --------------------------------------------------------------------------- #
# Citation style enum + Citation dataclass
# --------------------------------------------------------------------------- #
class CitationStyle(str, Enum):
    """Supported citation formatting styles."""

    APA = "apa"
    MLA = "mla"
    CHICAGO = "chicago"
    IEEE = "ieee"
    NONE = "none"
    RAW = "raw"


@dataclass
class Citation:
    """A single citation referencing a source document or chunk.

    Attributes:
        source_id: Unique identifier of the source (e.g. doc id or url).
        title: Title of the source document.
        author: Author or organization string.
        year: Publication year.
        publisher: Publisher / venue.
        url: Optional URL.
        page: Optional page / chunk reference.
        metadata: Extra fields (e.g. ``chunk_id``, ``accessed``).
    """

    source_id: str
    title: str = ""
    author: str = ""
    year: str = ""
    publisher: str = ""
    url: str = ""
    page: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __hash__(self) -> int:  # make citations usable in sets for de-dup
        return hash(
            (self.source_id, self.title, self.author, self.year, self.page or "")
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Citation):
            return NotImplemented
        return hash(self) == hash(other)


# --------------------------------------------------------------------------- #
# CitationManager
# --------------------------------------------------------------------------- #
class CitationManager:
    """Collect, de-duplicate and format citations.

    A manager holds a mutable set of :class:`Citation` objects. Adding a
    citation that is already present (by its hash) is a no-op, which prevents
    duplicate references from repeated retrieval.
    """

    def __init__(
        self,
        default_style: CitationStyle | str = CitationStyle.APA,
        citations: Optional[Sequence[Citation]] = None,
    ) -> None:
        self.default_style = (
            default_style
            if isinstance(default_style, CitationStyle)
            else CitationStyle(str(default_style).lower())
        )
        self._citations: Dict[str, Citation] = {}
        if citations:
            for c in citations:
                self.add_citation(c)

    # -- collection ------------------------------------------------------ #
    def add_citation(self, citation: Citation) -> bool:
        """Add a citation (no-op if an identical one already exists).

        Returns True if the citation was newly added, False if it was a
        duplicate.
        """
        key = self._key(citation)
        if key in self._citations:
            return False
        self._citations[key] = citation
        return True

    def add_many(self, citations: Sequence[Citation]) -> int:
        """Add several citations, returning the count newly inserted."""
        added = 0
        for c in citations:
            if self.add_citation(c):
                added += 1
        return added

    @staticmethod
    def _key(citation: Citation) -> str:
        return "|".join(
            [
                str(citation.source_id or ""),
                str(citation.page or ""),
                str(citation.author or ""),
                str(citation.year or ""),
            ]
        )

    def remove(self, source_id: str) -> bool:
        """Remove all citations matching a given source id."""
        to_remove = [k for k, v in self._citations.items() if v.source_id == source_id]
        for k in to_remove:
            del self._citations[k]
        return bool(to_remove)

    def clear(self) -> None:
        """Remove all citations."""
        self._citations.clear()

    # -- accessors ------------------------------------------------------- #
    @property
    def citations(self) -> List[Citation]:
        """The unique citations, in insertion order."""
        return list(self._citations.values())

    def __len__(self) -> int:
        return len(self._citations)

    def __iter__(self):
        return iter(self.citations)

    # -- formatting ------------------------------------------------------ #
    @staticmethod
    def format_citation(citation: Citation, style: CitationStyle | str) -> str:
        """Format a single citation into a string.

        Args:
            citation: The citation to format.
            style: The target :class:`CitationStyle`.

        Raises:
            ValueError: If the style is unknown.
        """
        if not isinstance(style, CitationStyle):
            style = CitationStyle(str(style).lower())

        if style == CitationStyle.NONE or style == CitationStyle.RAW:
            return (
                f"{citation.author} ({citation.year}). {citation.title}. "
                f"{citation.publisher}."
            ).strip() or str(citation.source_id)

        if style == CitationStyle.APA:
            return (
                f"{citation.author or 'Anon'} ({citation.year or 'n.d.'}). "
                f"{citation.title}. {citation.publisher}."
                f"{(' ' + citation.url) if citation.url else ''}"
            ).strip()

        if style == CitationStyle.MLA:
            pieces = [
                citation.author or "Anon",
                f'"{citation.title}".',
            ]
            if citation.publisher:
                pieces.append(citation.publisher)
            if citation.year:
                pieces.append(citation.year)
            return " ".join(pieces).rstrip() + "."

        if style == CitationStyle.CHICAGO:
            return (
                f"{citation.author or 'Anon'}, "
                f"{citation.title if citation.title else citation.source_id}, "
                f"{citation.publisher or ''}, {citation.year or 'n.d.'}."
            ).replace("  ", " ").strip()

        if style == CitationStyle.IEEE:
            ref = f"[{citation.source_id}] {citation.author or ''}"
            if citation.title:
                ref += f", \"{citation.title}\""
            if citation.publisher:
                ref += f", {citation.publisher}"
            if citation.year:
                ref += f", {citation.year}"
            return ref.strip()

        raise ValueError(f"Unknown citation style: {style}")

    def format(
        self,
        style: Optional[CitationStyle | str] = None,
        prefix: str = "",
    ) -> str:
        """Format all citations into a single newline-separated reference list.

        Args:
            style: The style to use (defaults to ``default_style``).
            prefix: Optional header line (e.g. "References:").
        """
        style = style or self.default_style
        if isinstance(style, str):
            style = CitationStyle(style.lower())
        lines = [self.format_citation(c, style) for c in self.citations]
        body = "\n".join(lines)
        if prefix:
            return f"{prefix}\n{body}".strip()
        return body

    def inline_marks(self, style: CitationStyle | str = CitationStyle.IEEE) -> str:
        """Render bracketed inline citation markers, one per source id."""
        if isinstance(style, str):
            style = CitationStyle(style.lower())
        if style == CitationStyle.IEEE:
            return " ".join(f"[{c.source_id}]" for c in self.citations)
        return self.format(style)

    def to_dict(self) -> List[Dict[str, Any]]:
        """Serialize citations to plain dicts (JSON-friendly)."""
        return [
            {
                "source_id": c.source_id,
                "title": c.title,
                "author": c.author,
                "year": c.year,
                "publisher": c.publisher,
                "url": c.url,
                "page": c.page,
                "metadata": dict(c.metadata),
            }
            for c in self.citations
        ]


def create_citation_manager(
    style: CitationStyle | str = CitationStyle.APA,
    citations: Optional[Sequence[Citation]] = None,
    **kwargs: Any,
) -> CitationManager:
    """Create a :class:`CitationManager`.

    Args:
        style: The default citation style.
        citations: Optional initial citations.
        **kwargs: Ignored (provided for API symmetry with other factories).
    """
    del kwargs  # accepted for symmetry
    return CitationManager(default_style=style, citations=citations)


__all__ = [
    "CitationStyle",
    "Citation",
    "CitationManager",
    "create_citation_manager",
]
