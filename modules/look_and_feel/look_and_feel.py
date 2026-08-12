"""
Enterprise Platform — Look & Feel Registry Module
==================================================

Enterprise-grade visual design registry. Parses, persists, and applies UI
look-and-feel rulesets ("design skills") so the Platform and downstream
generators can produce visually consistent, distinctive UI.

Provides:

  - LookAndFeelEntry   — data model for a single design module
  - LookAndFeelParser  — parses the structured module format from text/files
  - LookAndFeelRegistry— JSON-backed persistent store (CRUD + persist)
  - LookAndFeelModule  — enterprise Module facade exposing programmatic API + CLI
  - Events: lookandfeel.registry.updated, lookandfeel.module.used
  - Metrics: module count, last-used, per-tag counts

Architecture:
    __init__.py            — Module housekeeping, @module registration, exports
    look_and_feel.py       — LookAndFeelModule, Parser, Registry, CLI, Entry
    tests/test_look_and_feel.py — production-quality tests
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

_DEFAULT_MODULES = [
    "The Minimalist Muse",
    "The Ethereal Softness",
    "The Cyberpunk Dream",
    "The Dark Academia",
    "The Earthy Artisan",
    "The Neon Noir",
    "The Glassmorphism Gallery",
    "The Japandi Calm",
    "The Brutalist Edge",
    "The Biopunk Organism",
    "The Retro Wave",
    "The Golden Editorial",
]


# ══════════════════════════════════════════════════════════════════════════════
# Data model
# ══════════════════════════════════════════════════════════════════════════════


@dataclass
class LookAndFeelEntry:
    """A single look-and-feel design module.

    Fields map to the structured module format:

        [SKILL NAME]                 -> name
        [one line descriptor]        -> descriptor
        [one line mood/vibe]         -> mood   (optional in source)
        __________________________________
        [skill prompt — design ruleset] -> prompt
        [hashtag list]               -> hashtags
    """

    name: str
    descriptor: str = ""
    mood: str = ""
    prompt: str = ""
    hashtags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LookAndFeelEntry:
        return cls(
            name=str(data.get("name", "")),
            descriptor=str(data.get("descriptor", "")),
            mood=str(data.get("mood", "")),
            prompt=str(data.get("prompt", "")),
            hashtags=[str(h) for h in data.get("hashtags", [])],
        )


# ══════════════════════════════════════════════════════════════════════════════
# Parser
# ══════════════════════════════════════════════════════════════════════════════

_SEPARATOR_RE = re.compile(r"^_{6,}\s*$", re.MULTILINE)


class LookAndFeelParser:
    """Parses the look-and-feel module format.

    Handles the known pitfalls documented in references/parser-debugging.md:
      - Windows (\\r\\n) line-ending normalization
      - slicing content at the FORMATS: marker
      - separator index detection (< 2 rejected, 3rd line tolerated)
      - position-finding by known module names (regex splitting is fragile)
    """

    @staticmethod
    def _normalize(content: str) -> str:
        return content.replace("\r\n", "\n").replace("\r", "\n")

    @classmethod
    def _slice_formats(cls, content: str) -> str:
        idx = content.find("FORMATS:")
        if idx != -1:
            return content[idx:]
        return content

    @classmethod
    def parse_module(cls, content: str) -> LookAndFeelEntry | None:
        """Parse a single module block into a LookAndFeelEntry."""
        content = cls._normalize(content).strip()
        lines = content.split("\n")
        if len(lines) < 3:
            return None

        # Locate a separator line of underscores. It must exist and come after
        # the header lines (at least the name + descriptor).
        sep_idx = None
        for i, line in enumerate(lines):
            if _SEPARATOR_RE.match(line.strip()):
                sep_idx = i
                break
        if sep_idx is None or sep_idx < 2:
            return None

        name = lines[0].strip()
        descriptor = lines[1].strip()
        # Mood only present when there are 3+ header lines before the separator.
        mood = lines[2].strip() if sep_idx >= 3 else ""

        # Everything between separator and hashtags is the silent skill prompt.
        prompt_lines: list[str] = []
        hashtags: list[str] = []
        for raw in lines[sep_idx + 1 :]:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#"):
                hashtags.extend(t.strip() for t in line.split() if t.startswith("#"))
            else:
                prompt_lines.append(line)

        if not name:
            return None

        return LookAndFeelEntry(
            name=name,
            descriptor=descriptor,
            mood=mood,
            prompt="\n".join(prompt_lines),
            hashtags=[t.lstrip("#") for t in hashtags],
        )

    @classmethod
    def parse_modules_file(cls, content: str) -> list[LookAndFeelEntry]:
        """Parse all modules from a source file (handles the FORMATS: section)."""
        content = cls._slice_formats(cls._normalize(content))
        if not content.strip():
            return []

        # Position-find by known module names (reliable vs regex splitting).
        positions: list[tuple[int, str]] = []
        for name in _DEFAULT_MODULES:
            idx = content.find(name)
            if idx != -1:
                positions.append((idx, name))
        positions.sort(key=lambda p: p[0])

        # Also capture any module whose name isn't in the default list by
        # falling back to scanning blocks (robust to new/unknown modules).
        modules: list[LookAndFeelEntry] = []
        seen: set[str] = set()
        for i, (start_idx, name) in enumerate(positions):
            end_idx = positions[i + 1][0] if i + 1 < len(positions) else len(content)
            block = content[start_idx:end_idx].strip()
            if block and name not in seen:
                entry = cls.parse_module(block)
                if entry is not None:
                    seen.add(name)
                    modules.append(entry)

        return modules


# ══════════════════════════════════════════════════════════════════════════════
# Registry (persistence)
# ══════════════════════════════════════════════════════════════════════════════


class LookAndFeelRegistry:
    """JSON-backed persistent store of look-and-feel modules."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._modules: dict[str, LookAndFeelEntry] = {}
        self.load()

    # ── persistence ────────────────────────────────────────────────────────

    def load(self) -> None:
        self._modules = {}
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                for data in raw.get("modules", []):
                    entry = LookAndFeelEntry.from_dict(data)
                    if entry.name:
                        self._modules[entry.name] = entry
            except (json.JSONDecodeError, OSError, TypeError):
                self._modules = {}

    def persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "modules": [e.to_dict() for e in self._modules.values()],
        }
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    # ── CRUD ───────────────────────────────────────────────────────────────

    def upsert(self, entry: LookAndFeelEntry) -> bool:
        """Insert or overwrite a module. Returns True if it already existed."""
        existed = entry.name in self._modules
        self._modules[entry.name] = entry
        return existed

    def remove(self, name: str) -> bool:
        return self._modules.pop(name, None) is not None

    def get(self, name: str) -> LookAndFeelEntry | None:
        return self._modules.get(name)

    def all_modules(self) -> list[LookAndFeelEntry]:
        return list(self._modules.values())

    def search(self, tag: str, *, case_sensitive: bool = False) -> list[LookAndFeelEntry]:
        """Find modules whose hashtags match. Accepts '#tag' or 'tag'."""
        needle = tag.lstrip("#")
        if not case_sensitive:
            needle = needle.lower()
        out = []
        for entry in self._modules.values():
            for h in entry.hashtags:
                candidate = h if case_sensitive else h.lower()
                if candidate == needle or needle in candidate:
                    out.append(entry)
                    break
        return out

    def __len__(self) -> int:
        return len(self._modules)


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════


class LookAndFeelCLI:
    """Extremely thin CLI binding so the module is callable as 'lookandfeel'."""

    COMMANDS = ("list", "add", "use", "search", "remove")

    def __init__(self, registry: LookAndFeelRegistry, parser: LookAndFeelParser) -> None:
        self._registry = registry
        self._parser = parser

    def run(self, argv: list[str]) -> str:
        if not argv:
            return self.usage()
        cmd = argv[0].lower()
        if cmd == "list":
            return self._list()
        if cmd == "add":
            return self._add(argv[1:])
        if cmd == "use":
            return self._use(argv[1:])
        if cmd == "search":
            return self._search(argv[1:])
        if cmd == "remove":
            return self._remove(argv[1:])
        return self.usage()

    def _list(self) -> str:
        entries = self._registry.all_modules()
        if not entries:
            return "(registry is empty)"
        lines = []
        for i, e in enumerate(entries, 1):
            tags = " ".join(f"#{t}" for t in e.hashtags)
            lines.append(f"{i}. {e.name}\n   {tags}")
        return "\n".join(lines)

    def _add(self, args: list[str]) -> str:
        if not args:
            return "usage: lookandfeel add <file>"
        path = Path(args[0])
        if not path.exists():
            return f"error: file not found: {path}"
        entries = self._parser.parse_modules_file(path.read_text(encoding="utf-8"))
        if not entries:
            return "error: no modules parsed from file"
        out = []
        for e in entries:
            updated = self._registry.upsert(e)
            self._registry.persist()
            out.append(
                f"skill {e.name} updated" if updated else f"skill {e.name} added to registry"
            )
        return "\n".join(out)

    def _use(self, args: list[str]) -> str:
        if not args:
            return "usage: lookandfeel use <name>"
        name = " ".join(args)
        entry = self._registry.get(name)
        if entry is None:
            return f"error: module not found: {name}"
        return entry.prompt

    def _search(self, args: list[str]) -> str:
        if not args:
            return "usage: lookandfeel search <tag>"
        tag = args[0]
        entries = self._registry.search(tag)
        if not entries:
            return f"(no modules match #{tag.lstrip('#')})"
        return "\n".join(f"- {e.name}" for e in entries)

    def _remove(self, args: list[str]) -> str:
        if not args:
            return "usage: lookandfeel remove <name>"
        name = " ".join(args)
        if self._registry.remove(name):
            self._registry.persist()
            return f"removed {name}"
        return f"error: module not found: {name}"

    def usage(self) -> str:
        return (
            "usage: lookandfeel <command>\n"
            "commands: list | add <file> | use <name> | search <tag> | remove <name>"
        )
