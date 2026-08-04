"""
Skills Import — standard markdown-skills format importer.

Adds the ability to parse and ingest the *standard* markdown-skills format used
by the community (superpowers by obra, anthropics/skills) into the existing
:class:`~enterprise.modules.skill_factory.skill_factory.SkillRegistry`.

Standard format
---------------
A single markdown file that may start with YAML frontmatter::

    ---
    name: some-skill
    description: What this skill does
    ---

    Instructions / markdown body.

    --TRIGGERS--
    - a trigger phrase
    - another trigger phrase
    --END TRIGGERS--

When frontmatter is absent, the skill name is derived from the first markdown
``# Heading``.  The ``--TRIGGERS--`` block (bullet list of trigger phrases) is
optional and is exposed separately as ``triggers``.

This module is deliberately **stdlib-only** and never imports ``yaml``: the
frontmatter parser splits on ``---`` delimiter lines and parses ``key: value``
lines manually.  Only the subset of YAML used by skill frontmatter is needed.

Exports
-------
SkillImport
    Dataclass: ``name``, ``description``, ``body``, ``triggers``, ``raw``.
parse_skill_markdown(text)
    Parse raw markdown text into a :class:`SkillImport`.
import_skill_from_markdown(text, registry)
    Parse then store via the existing registry, returning a ``SkillRecord``.
SkillsImportFacade
    File-oriented facade: ``parse_file``, ``import_file``, ``import_dir``,
    ``list_all``.

Python: 3.10+
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .skill_factory import SkillRecord, SkillRegistry

_log: logging.Logger = logging.getLogger("enterprise.skill_factory.skills_import")

#: Marker that opens an optional triggers block inside the markdown body.
_TRIGGERS_OPEN: str = "--TRIGGERS--"
#: Marker that (optionally) closes a triggers block.
_TRIGGERS_CLOSE: str = "--END TRIGGERS--"


# ===========================================================================
# Data model
# ===========================================================================


@dataclass
class SkillImport:
    """Parsed representation of a standard markdown skill document."""

    name: str
    description: str
    body: str
    triggers: list[str] = field(default_factory=list)
    raw: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dict view (useful for logging / inspection)."""
        return {
            "name": self.name,
            "description": self.description,
            "body": self.body,
            "triggers": list(self.triggers),
        }


# ===========================================================================
# Minimal frontmatter parser (stdlib only — never imports yaml)
# ===========================================================================


def _parse_frontmatter_block(block: str) -> dict[str, str]:
    """Parse ``key: value`` lines from a frontmatter block.

    Handles ``key: value``, ``key:`` (empty value), quoted values and
    ``key: [a, b]`` inline lists (coerced to a comma-space string).  Nested
    YAML structures are intentionally ignored — skill frontmatter is flat.
    """
    result: dict[str, str] = {}
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, raw_value = line.partition(":")
        key = key.strip()
        value = raw_value.strip()
        if not key:
            continue
        # Inline list: "key: [a, b]" or "key: [a, b], trailing-ignored".
        if value.startswith("[") and "]" in value:
            inner = value[1 : value.index("]")].strip()
            value = ", ".join(p.strip() for p in inner.split(",") if p.strip())
        result[key] = _strip_quotes(value)
    return result


def _strip_quotes(value: str) -> str:
    """Strip a single matching pair of surrounding quotes."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split text into (frontmatter dict, body).  Returns ({}, text) when the
    document does not begin with a ``---`` delimiter."""
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
    return _parse_frontmatter_block(block), body


# ===========================================================================
# Triggers block extraction
# ===========================================================================


def _extract_triggers(body: str) -> tuple[str, list[str]]:
    """Extract an optional ``--TRIGGERS--`` bullet block from the body.

    Returns ``(cleaned_body, triggers)`` where ``cleaned_body`` has the
    triggers block removed and ``triggers`` is the list of bullet items.
    """
    lines = body.splitlines()
    open_index: int | None = None
    for i, line in enumerate(lines):
        if line.strip().upper() == _TRIGGERS_OPEN:
            open_index = i
            break
    if open_index is None:
        return body, []

    triggers: list[str] = []
    close_index: int | None = None
    j = open_index + 1
    # Skip blank lines immediately after the marker.
    while j < len(lines) and not lines[j].strip():
        j += 1
    while j < len(lines):
        line = lines[j].strip()
        if line.upper() == _TRIGGERS_CLOSE:
            close_index = j
            break
        if not line:
            # A blank line ends the bullet list (common in superpowers format).
            break
        if line.startswith("- ") or line.startswith("* "):
            triggers.append(line[2:].strip())
            j += 1
            continue
        if line.startswith("-") or line.startswith("*"):
            triggers.append(line[1:].strip())
            j += 1
            continue
        # A non-bullet, non-blank line ends the triggers block.
        break

    end = close_index if close_index is not None else j
    kept = lines[:open_index] + lines[end + 1 :]
    return "\n".join(kept).strip() + "\n", triggers


def _name_from_first_heading(body: str) -> str:
    """Derive a skill name from the first markdown ``# Heading``."""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            heading = stripped[2:].strip()
            return heading
    return ""


# ===========================================================================
# Public parse / import API
# ===========================================================================


def parse_skill_markdown(text: str) -> SkillImport:
    """Parse raw markdown text into a :class:`SkillImport`.

    - YAML frontmatter (``name`` / ``description``) is parsed when present.
    - Without frontmatter, the name is derived from the first ``# heading``.
    - An optional ``--TRIGGERS--`` bullet block is parsed into ``triggers``
      and stripped from the returned ``body``.
    - Missing ``description`` / ``triggers`` degrade gracefully to empty.
    - Missing ``name`` yields an empty string (callers decide how to handle).

    Args:
        text: Raw markdown source of a skill document.

    Returns:
        A populated :class:`SkillImport`.
    """
    if text is None:
        text = ""

    frontmatter, body = _split_frontmatter(text)

    name = str(frontmatter.get("name", "")).strip()
    description = str(frontmatter.get("description", "")).strip()

    body, triggers = _extract_triggers(body)

    if not name:
        name = _name_from_first_heading(body)

    return SkillImport(
        name=name,
        description=description,
        body=body,
        triggers=triggers,
        raw=text,
    )


def import_skill_from_markdown(text: str, registry: SkillRegistry) -> SkillRecord:
    """Parse standard markdown and store it via the existing registry.

    The parsed description is preserved and the parsed triggers are stored as
    the skill's tags so they survive round-trips through the registry.  Raises
    :class:`ValueError` when the document has no usable name.

    Args:
        text: Raw markdown source of a skill document.
        registry: An existing :class:`SkillRegistry` (its ``create`` method is
            the real store path — versioning / history preserved).

    Returns:
        The stored :class:`SkillRecord`.
    """
    parsed = parse_skill_markdown(text)
    if not parsed.name:
        raise ValueError(
            "skill markdown has no name (no frontmatter 'name:' and no '# heading')"
        )
    return registry.create(
        name=parsed.name,
        body=parsed.body,
        category="general",
        description=parsed.description,
        tags=list(parsed.triggers),
    )


# ===========================================================================
# Facade
# ===========================================================================


class SkillsImportFacade:
    """File-oriented facade for importing standard markdown skills.

    Wraps an existing :class:`SkillRegistry` (or builds one from a
    ``data_dir``) and exposes parse / import helpers plus a listing view.

    Args:
        registry: An existing registry.  Mutually exclusive with ``data_dir``.
        data_dir: Root data directory used to build a fresh registry when
            ``registry`` is not supplied.
    """

    def __init__(
        self,
        registry: SkillRegistry | None = None,
        data_dir: Path | str | None = None,
    ) -> None:
        if registry is not None:
            if data_dir is not None:
                raise ValueError("pass either registry or data_dir, not both")
            self.registry: SkillRegistry = registry
        elif data_dir is not None:
            self.registry = SkillRegistry(Path(data_dir))
        else:
            raise ValueError("SkillsImportFacade requires a registry or data_dir")
        self.registry.ensure()

    # ── Parsing ────────────────────────────────────────────────────────────

    def parse_file(self, path: Path | str) -> SkillImport:
        """Read and parse a single markdown skill file.

        Args:
            path: Path to a ``.md`` skill file.

        Returns:
            The parsed :class:`SkillImport`.
        """
        file = Path(path)
        text = file.read_text(encoding="utf-8")
        parsed = parse_skill_markdown(text)
        _log.debug("Parsed skill file %s -> %r", file, parsed.name)
        return parsed

    # ── Import ─────────────────────────────────────────────────────────────

    def import_file(self, path: Path | str) -> SkillRecord:
        """Parse a single markdown file and store it in the registry.

        Args:
            path: Path to a ``.md`` skill file.

        Returns:
            The stored :class:`SkillRecord`.
        """
        file = Path(path)
        text = file.read_text(encoding="utf-8")
        return import_skill_from_markdown(text, self.registry)

    def import_dir(self, dirpath: Path | str) -> list[SkillRecord]:
        """Walk a directory of ``*.md`` files and import each.

        Files that fail to parse (e.g. no usable name) are skipped gracefully
        and logged, so one bad file does not abort the whole import.

        Args:
            dirpath: Directory to walk (recursively).

        Returns:
            The list of successfully stored :class:`SkillRecord` instances.
        """
        directory = Path(dirpath)
        records: list[SkillRecord] = []
        for file in sorted(directory.rglob("*.md")):
            if not file.is_file():
                continue
            try:
                records.append(self.import_file(file))
            except ValueError as exc:
                _log.warning("Skipping %s: %s", file, exc)
        return records

    # ── Listing ────────────────────────────────────────────────────────────

    def list_all(self) -> list[dict[str, Any]]:
        """Return metadata-only dicts for all skills in the registry."""
        return self.registry.list()
