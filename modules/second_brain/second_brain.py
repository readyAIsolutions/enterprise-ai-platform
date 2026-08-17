"""Second Brain — a knowledge capture & resurfacing engine, NOT a notes app.

Built directly from three real pulled JE Van Clief transcripts:

* “Your Second Brain Is Not a Notes App” (-CUsfao6m7E): the core thesis. A
  second brain must *connect* ideas, not just store them:

      “It's not just notes. It's not just a bunch of information ... if you
       can put it into a bucket and that's it, I find that that ends up
       becoming a graveyard ... a massive amount of information that's getting
       stored.”  →  plain storage rots; linking is what keeps a vault alive.
      “You're helping it create the connections because the AI ... I am
       stopping it from needing to make those connections. Understanding it
       will fill the gaps as long as the connections are good enough.”
      “It's metadata in a certain way ... it captures and isolates my
       thinking.”  →  capture carries metadata, not just blobs of text.

  So the module treats a note as a node with tags/source metadata, and
  ideas as edges (link_ideas), and retrieval as concept lookup, not folder
  traversal (query_concept).

* “Van Squared: A Free Local AI Model Labeled a 26-Year Archive”
  (mme027WZhgo): the long-archive idea. Label/tag decades of material so it
  stays forever searchable. The “labeled archive that compounds” — metadata
  added once keeps paying off as the archive grows:
      “you had 20 years of video and you wanted to be able to search through
       it all ... navigate 20 years of video.” / “I'll just change the tags.”

* “AI Since 2011: The Ideas That Outlive Every Model” (lDXCkx3Nla8): ideas /
  first principles are what outlive any single model or tool. The value of a
  second brain is not the tool but the *compounding archive of ideas* that
  keeps working as the underlying tools change. → build_compounding_report
  measures that compounding (growth, linkage, resurfacing health) over time.

Everything here is pure Python and network-free so it is unit-testable in
isolation. No fake enterprise features: just the capture / link / resurface /
concept-query / compounding-review honestly derived from the source material.

Version: 1.0.0
"""
from __future__ import annotations

import re
import string
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Set


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_tags(tags: Optional[Iterable[str]] = None) -> List[str]:
    """Lowercase, strip, drop empties; keeps tags comparable & searchable."""
    seen: Set[str] = set()
    out: List[str] = []
    for t in tags or ():
        tt = str(t).strip().lower()
        if tt and tt not in seen:
            seen.add(tt)
            out.append(tt)
    return out


def _tokenize(text: str) -> Set[str]:
    """Crude but dependency-free tokenizer for concept matching."""
    words = re.findall(r"[A-Za-z0-9']+", text.lower())
    stops = {"the", "and", "for", "are", "but", "not", "you", "that",
             "this", "with", "your", "from", "have", "was", "had", "its",
             "a", "an", "of", "to", "in", "on", "is", "it", "so", "as",
             "how", "what", "when", "why", "will", "can", "all", "any"}
    return {w for w in words if w not in stops and len(w) > 2}


# --------------------------------------------------------------------------
# Spaced-repetition schedule (simple, deterministic, no external deps)
# --------------------------------------------------------------------------

def _next_review_bump(current_num: int, forgotten: bool = False) -> timedelta:
    """Return the delay until the next review for a memorized entry.

    Doubling intervals (1d → 2d → 4d → 8d …) up to a 32-day cap. If the
    entry was marked 'forgotten' the interval resets back to 1 day. This is
    the "resurface / bring-back" mechanics: review prompts increase how often
    an idea actually re-enters working memory.
    """
    if forgotten or current_num < 1:
        days = 1
    else:
        days = min(2 ** current_num, 32)
    return timedelta(days=days)


@dataclass
class Entry:
    """A single captured idea (a node in the second-brain graph)."""
    id: str
    text: str
    tags: List[str] = field(default_factory=list)
    source: str = ""
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    # -- spaced-repetition state -----------------------------------------
    reviews: int = 0                 # how many times it has been resurfaced
    next_review: datetime = field(default_factory=_utcnow)  # due immediately
    interval_num: int = 0            # current repetition interval exponent
    # -- linkage ----------------------------------------------------------
    links: Set[str] = field(default_factory=set)  # ids of connected entries

    def add_link(self, other_id: str) -> None:
        self.links.add(other_id)

    def remove_link(self, other_id: str) -> None:
        self.links.discard(other_id)

    def is_due(self, now: Optional[datetime] = None) -> bool:
        return self.next_review <= (now or _utcnow())

    def review(self, now: Optional[datetime] = None) -> None:
        """Mark reviewed; schedules the next resurface prompt."""
        now = now or _utcnow()
        self.reviews += 1
        self.interval_num += 1
        self.next_review = now + _next_review_bump(self.interval_num)

    def forget(self, now: Optional[datetime] = None) -> None:
        """Mark as not-yet-retained; pulls it back for review sooner."""
        now = now or _utcnow()
        self.interval_num = 0
        self.next_review = now + _next_review_bump(0)


class SecondBrain:
    """Knowledge capture & resurfacing engine.

    Pure in-memory store (network-free) implementing the four behaviours the
    transcripts teach, plus a compounding report:
      * capture(note, tags, source)     — capture with metadata (not just blobs)
      * link_ideas(a, b)                — connect related ideas (edges)
      * resurface(due)                  — spaced-repetition retrieval prompts
      * query_concept(term)             — retrieval by concept, not folder
      * build_compounding_report(...)   — the "labeled archive that compounds"
    """

    def __init__(self) -> None:
        self._entries: Dict[str, Entry] = {}
        self._link_events: List[tuple] = []  # history of (a, b, when)
        self._capture_events: List[str] = []  # id order of captures
        self._concepts: Dict[str, Set[str]] = {}  # concept token -> entry ids

    # ------------------------------------------------------------- capture
    def capture(self, note: str,
                tags: Optional[Iterable[str]] = None,
                source: str = "",
                entry_id: Optional[str] = None) -> Entry:
        """Store a note as a metadata-carrying node and index its concepts.

        Mirrors the transcript's "it's metadata in a certain way ... it
        captures and isolates my thinking": the raw text is kept, but the
        tags/source metadata is what makes it retrievable later.
        """
        eid = entry_id or self._next_id()
        entry = Entry(id=eid, text=note, tags=_normalize_tags(tags),
                      source=source)
        self._entries[eid] = entry
        self._capture_events.append(eid)
        for tok in _tokenize(note) | set(entry.tags):
            self._concepts.setdefault(tok, set()).add(eid)
        return entry

    def _next_id(self) -> str:
        n = len(self._entries)
        letters = string.ascii_lowercase
        base = letters[n % 26] if n < 26 ** 2 else "z"
        return f"{base}{n+1}"

    # --------------------------------------------------------------- link
    def link_ideas(self, a: str, b: str, when: Optional[datetime] = None) -> bool:
        """Connect two ideas with a bidirectional edge.

        From the transcript: "A node is going to be some sort of description,
        some sort of thing. An edge is how that connects to other things ...
        This is useful when you start looking at a company or your process."
        Returns False if either id is unknown; True on success/dup.
        """
        if a not in self._entries or b not in self._entries or a == b:
            return False
        self._entries[a].add_link(b)
        self._entries[b].add_link(a)
        self._link_events.append((a, b, when or _utcnow()))
        return True

    def neighbors(self, entry_id: str) -> List[str]:
        """The set of ideas directly connected to an entry."""
        if entry_id not in self._entries:
            return []
        return sorted(self._entries[entry_id].links)

    def connected_component(self, entry_id: str) -> List[str]:
        """BFS over the idea graph — the full cluster reachable from an entry."""
        if entry_id not in self._entries:
            return []
        seen: Set[str] = {entry_id}
        stack = [entry_id]
        while stack:
            cur = stack.pop()
            for nxt in self._entries[cur].links:
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return sorted(seen)

    # ----------------------------------------------------------- resurface
    def resurface(self, due: Optional[datetime] = None) -> List[Entry]:
        """Return entries whose spaced-repetition review is now due.

        These are the retrieval prompts — the "bring the idea back into
        working memory" step that keeps a second brain from becoming a static
        graveyard of stored-but-forgotten notes.
        """
        now = due or _utcnow()
        return [e for e in self._entries.values() if e.is_due(now)]

    def review(self, entry_id: str, forgotten: bool = False) -> bool:
        """Record a resurfacing outcome for an entry."""
        e = self._entries.get(entry_id)
        if e is None:
            return False
        if forgotten:
            e.forget()
        else:
            e.review()
        return True

    # ------------------------------------------------- concept query
    def query_concept(self, term: str) -> List[Entry]:
        """Retrieve entries by concept/tag, not folder traversal.

        Matches any tag exactly and any entry whose tokenized text overlaps
        the query tokens. Returns newest-first.
        """
        q = term.strip().lower()
        if not q:
            return []
        tok = _tokenize(q)
        ids: Set[str] = set()
        # exact tag hit
        for eid, e in self._entries.items():
            if q in e.tags:
                ids.add(eid)
        # token overlap on text + tags
        for tokw in tok:
            ids |= self._concepts.get(tokw, set())
        hits = [self._entries[i] for i in ids]
        hits.sort(key=lambda e: e.created_at, reverse=True)
        return hits

    def by_tag(self, tag: str) -> List[Entry]:
        q = tag.strip().lower()
        return [e for e in self._entries.values() if q in e.tags]

    def get(self, entry_id: str) -> Optional[Entry]:
        return self._entries.get(entry_id)

    def count(self) -> int:
        return len(self._entries)

    # ------------------------------------------------------ compounding
    def build_compounding_report(
            self,
            window: Optional[timedelta] = None,
            now: Optional[datetime] = None) -> Dict:
        """Report on how the second brain compounds over a time window.

        The "Van Squared (labeled 26-year archive)" + "ideas that outlive
        every model" idea: an archive is valuable not because of its size but
        because captured ideas keep connecting and keep resurfacing. This
        report surfaces growth, linkage density, resurfacing health, and the
        distinction between stored-but-lonely vs actively-linked knowledge.
        """
        now = now or _utcnow()
        start = now - window if window else None
        entries = list(self._entries.values())
        if start:
            entries = [e for e in entries if e.created_at >= start]

        total = len(entries)
        linked = [e for e in entries if e.links]
        total_links = sum(len(e.links) for e in entries) // 2  # undirected
        isolated = [e for e in entries if not e.links and e.reviews == 0]
        due_now = [e for e in entries if e.is_due(now)]
        reviewable = sum(e.reviews for e in entries)

        density = 0.0
        if total > 1:
            possible = total * (total - 1) / 2
            density = total_links / possible if possible else 0.0

        # compound score: growth + linkage + resurfacing activity
        growth = total
        score = (growth
                 + (total_links * 2)
                 + reviewable
                 - len(isolated))

        return {
            "total_entries": total,
            "linked_entries": len(linked),
            "total_links": total_links,
            "isolated_entries": len(isolated),
            "due_for_resurface": len(due_now),
            "total_revsurfacings": reviewable,
            "link_density": round(density, 4),
            "active_concepts": len(self._concepts),
            "compound_score": score,
            "verdict": (
                "compounding" if density >= 0.15 and total >= 3
                else "compounding" if total >= 5 and reviewable >= 2
                else "storage only"  # the "graveyard" case from the transcript
            ),
        }


def make_second_brain() -> SecondBrain:
    """Factory for a fresh SecondBrain engine."""
    return SecondBrain()
