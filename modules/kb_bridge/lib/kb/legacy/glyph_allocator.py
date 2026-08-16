#!/usr/bin/env python3
"""
ENI Glyph Allocator & DSL Parser
Unicode Private Use Area (U+E000–U+F8FF) allocation with 1-token DSL invocation.
"""

import json
import threading
from pathlib import Path
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
import hashlib


GLYPHS_DIR = Path("~/.eni/kb/glyphs").expanduser()
ALLOCATION_FILE = GLYPHS_DIR / "allocation.json"
GLYPH_MAP_FILE = GLYPHS_DIR / "glyph_map.json"


class GlyphCategory(Enum):
    CORE = ("core", 0xE000, 0xE0FF, "eni:")
    DEMIURGE = ("demiurge", 0xE100, 0xE1FF, "demiurge:")
    STOCKBOT = ("stockbot", 0xE200, 0xE2FF, "stockbot:")
    LUMEN = ("lumen", 0xE300, 0xE3FF, "lumen:")
    SWARM = ("swarm", 0xE400, 0xE4FF, "swarm:")
    OUTDOORS = ("outdoors", 0xE500, 0xE5FF, "outdoors:")
    SECURITY = ("security", 0xE600, 0xE6FF, "sec:")
    GAMING = ("gaming", 0xE700, 0xE7FF, "game:")
    RESERVED = ("reserved", 0xE800, 0xEFFF, "")
    USER = ("user", 0xF000, 0xF8FF, "user:")

    def __init__(self, name: str, start: int, end: int, prefix: str):
        self.cat_name = name
        self.start = start
        self.end = end
        self.prefix = prefix


@dataclass
class GlyphEntry:
    glyph: str
    skill_id: str
    category: str
    allocated: str  # ISO timestamp
    dsl_spec: Dict[str, Any] = field(default_factory=dict)
    usage_count: int = 0
    last_used: Optional[str] = None
    fitness: float = 0.0
    unicode_cp: int = 0


@dataclass
class DSLParam:
    name: str
    type: str  # string, number, boolean, enum, path
    required: bool = False
    default: Any = None
    enum: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class DSLSpec:
    verb: str
    params: List[DSLParam] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    description: str = ""


class GlyphAllocator:
    """Thread-safe glyph allocation with category ranges."""

    def __init__(self):
        self._lock = threading.RLock()
        self._allocation: Dict[str, GlyphEntry] = {}
        self._next_available: Dict[str, int] = {}
        self._load()

    def _load(self):
        GLYPHS_DIR.mkdir(parents=True, exist_ok=True)
        if ALLOCATION_FILE.exists():
            data = json.loads(ALLOCATION_FILE.read_text())
            for glyph_str, entry_data in data.get("allocated", {}).items():
                entry = GlyphEntry(**entry_data)
                entry.unicode_cp = ord(glyph_str)
                self._allocation[glyph_str] = entry
            self._next_available = data.get("next_available", {})
        else:
            # Initialize next_available for each category
            for cat in GlyphCategory:
                self._next_available[cat.cat_name] = cat.start
            self._save()

    def _save(self):
        data = {
            "version": 1,
            "allocated": {g: asdict(e) for g, e in self._allocation.items()},
            "next_available": self._next_available,
            "categories": {c.cat_name: {"range": f"U+{c.start:04X}-U+{c.end:04X}", "prefix": c.prefix} for c in GlyphCategory}
        }
        ALLOCATION_FILE.write_text(json.dumps(data, indent=2))

    def allocate(self, category: str = "core", skill_id: str = "") -> str:
        """Allocate next available glyph in category."""
        with self._lock:
            cat = next((c for c in GlyphCategory if c.cat_name == category), GlyphCategory.CORE)
            next_cp = self._next_available.get(category, cat.start)

            # Find next free slot
            for cp in range(next_cp, cat.end + 1):
                glyph = chr(cp)
                if glyph not in self._allocation:
                    entry = GlyphEntry(
                        glyph=glyph,
                        skill_id=skill_id or f"eni:pending-{glyph}",
                        category=category,
                        allocated=datetime.utcnow().isoformat() + "Z",
                        unicode_cp=cp
                    )
                    self._allocation[glyph] = entry
                    self._next_available[category] = cp + 1
                    self._save()
                    return glyph

            raise RuntimeError(f"Glyph exhaustion in category {category}")

    def register_skill(self, glyph: str, skill_id: str, dsl_spec: DSLSpec):
        """Register a skill to an allocated glyph with its DSL spec."""
        with self._lock:
            if glyph in self._allocation:
                self._allocation[glyph].skill_id = skill_id
                self._allocation[glyph].dsl_spec = asdict(dsl_spec)
                self._save()

    def get(self, glyph: str) -> Optional[GlyphEntry]:
        return self._allocation.get(glyph)

    def record_use(self, glyph: str):
        with self._lock:
            if glyph in self._allocation:
                entry = self._allocation[glyph]
                entry.usage_count += 1
                entry.last_used = datetime.utcnow().isoformat() + "Z"
                # Fitness = usage * compression_ratio (approx)
                entry.fitness = entry.usage_count * 1.5
                self._save()

    def list_category(self, category: str) -> List[GlyphEntry]:
        with self._lock:
            return [e for e in self._allocation.values() if e.category == category]

    def list_all(self) -> List[GlyphEntry]:
        with self._lock:
            return list(self._allocation.values())

    def get_next_available(self, category: str) -> str:
        cat = next((c for c in GlyphCategory if c.cat_name == category), GlyphCategory.CORE)
        next_cp = self._next_available.get(category, cat.start)
        if next_cp <= cat.end:
            return chr(next_cp)
        return ""


class DSLParser:
    """Parse and validate ENI glyph DSL invocations."""

    GRAMMAR = {
        'glyph': r'[\uE000-\uF8FF]',
        'verb': r'[a-zA-Z_][a-zA-Z0-9_-]*(?::[a-zA-Z_][a-zA-Z0-9_-]*)?',
        'param': r'@[a-zA-Z_][a-zA-Z0-9_-]*\s*=\s*(?:"[^"]*"|\'[^\']*\'|[a-zA-Z0-9_.\-/]+|true|false)',
    }

    def __init__(self, allocator: GlyphAllocator):
        self.allocator = allocator

    def parse(self, invocation: str) -> Dict[str, Any]:
        """Parse glyph invocation: '󰀀 build:appimage @target=linux @sign=gpg'"""
        invocation = invocation.strip()
        if not invocation:
            raise ValueError("Empty invocation")

        parts = invocation.split()
        if not parts:
            raise ValueError("No glyph found")

        glyph = parts[0]
        if len(glyph) != 1 or not ('\uE000' <= glyph <= '\uF8FF'):
            raise ValueError(f"Invalid glyph: {glyph!r} (must be single PUA char)")

        entry = self.allocator.get(glyph)
        if not entry:
            raise ValueError(f"Glyph {glyph!r} not allocated")

        result = {
            "glyph": glyph,
            "skill_id": entry.skill_id,
            "verb": None,
            "params": {}
        }

        # Parse verb and params
        i = 1
        while i < len(parts):
            part = parts[i]
            if part.startswith('@'):
                # Parameter
                eq_idx = part.find('=')
                if eq_idx == -1:
                    raise ValueError(f"Invalid param format: {part}")
                name = part[1:eq_idx]
                value_str = part[eq_idx + 1:]

                # Parse value
                value = self._parse_value(value_str)
                result["params"][name] = value
            elif result["verb"] is None:
                result["verb"] = part
            else:
                # Could be positional arg or malformed
                raise ValueError(f"Unexpected token: {part}")
            i += 1

        # Validate against DSL spec if available
        if entry.dsl_spec:
            self._validate_params(entry.dsl_spec, result["params"])

        return result

    def _parse_value(self, value_str: str) -> Any:
        value_str = value_str.strip()
        # String literals
        if (value_str.startswith('"') and value_str.endswith('"')) or \
           (value_str.startswith("'") and value_str.endswith("'")):
            return value_str[1:-1]
        # Boolean
        if value_str.lower() == "true":
            return True
        if value_str.lower() == "false":
            return False
        # Number
        try:
            if '.' in value_str:
                return float(value_str)
            return int(value_str)
        except ValueError:
            pass
        # Identifier/path
        return value_str

    def _validate_params(self, dsl_spec: Dict, params: Dict):
        """Validate params against DSL spec."""
        spec_params = dsl_spec.get("params", [])
        param_specs = {p["name"]: p for p in spec_params}

        # Check required
        for p in spec_params:
            if p["required"] and p["name"] not in params:
                if p["default"] is not None:
                    params[p["name"]] = p["default"]
                else:
                    raise ValueError(f"Required parameter missing: {p['name']}")

        # Check enum values
        for name, value in params.items():
            if name in param_specs:
                spec = param_specs[name]
                if spec["enum"] and value not in spec["enum"]:
                    raise ValueError(f"Invalid value for {name}: {value} (enum: {spec['enum']})")

    def format_invocation(self, glyph: str, verb: str = None, **params) -> str:
        """Format a valid invocation string."""
        parts = [glyph]
        if verb:
            parts.append(verb)
        for k, v in params.items():
            if isinstance(v, str):
                v = f'"{v}"'
            elif isinstance(v, bool):
                v = "true" if v else "false"
            parts.append(f"@{k}={v}")
        return " ".join(parts)

    def get_completions(self, prefix: str) -> List[str]:
        """Get glyph completions for prefix (for LSP)."""
        completions = []
        for entry in self.allocator.list_all():
            if entry.glyph.startswith(prefix) or \
               (entry.dsl_spec and entry.dsl_spec.get("verb", "").startswith(prefix)) or \
               (entry.skill_id.startswith(prefix)):
                completions.append(entry.glyph)
        return completions


class GlyphMap:
    """Bidirectional glyph ↔ skill mapping with DSL help."""

    def __init__(self, allocator: GlyphAllocator, parser: DSLParser):
        self.allocator = allocator
        self.parser = parser

    def to_json(self) -> Dict:
        """Export for MCP/LSP consumption."""
        return {
            "glyphs": {
                glyph: {
                    "skill_id": entry.skill_id,
                    "category": entry.category,
                    "dsl": entry.dsl_spec,
                    "usage_count": entry.usage_count,
                    "fitness": entry.fitness
                }
                for glyph, entry in self.allocator._allocation.items()
            },
            "categories": {c.cat_name: {"range": f"U+{c.start:04X}-U+{c.end:04X}", "prefix": c.prefix} for c in GlyphCategory}
        }

    def save_map(self):
        GLYPH_MAP_FILE.write_text(json.dumps(self.to_json(), indent=2))

    def get_skill_by_glyph(self, glyph: str) -> Optional[str]:
        entry = self.allocator.get(glyph)
        return entry.skill_id if entry else None

    def get_glyph_by_skill(self, skill_id: str) -> Optional[str]:
        for glyph, entry in self.allocator._allocation.items():
            if entry.skill_id == skill_id:
                return glyph
        return None

    def get_dsl_help(self, glyph: str) -> Optional[str]:
        entry = self.allocator.get(glyph)
        if not entry or not entry.dsl_spec:
            return None
        spec = entry.dsl_spec
        lines = [f"{glyph} {spec.get('verb', '')} — {spec.get('description', '')}"]
        for p in spec.get("params", []):
            req = " (required)" if p.get("required") else ""
            enum = f" [{', '.join(p['enum'])}]" if p.get("enum") else ""
            default = f" = {p['default']}" if p.get("default") is not None else ""
            lines.append(f"  @{p['name']}: {p['type']}{enum}{default}{req}")
        for ex in spec.get("examples", []):
            lines.append(f"  e.g. {ex}")
        return "\n".join(lines)


# Demo / CLI
if __name__ == "__main__":
    import sys

    allocator = GlyphAllocator()
    parser = DSLParser(allocator)
    glyph_map = GlyphMap(allocator, parser)

    if len(sys.argv) < 2:
        print("Usage: glyph_allocator.py <command> [args]")
        print("Commands: allocate <category> [skill_id], parse <invocation>, list [category], map, help <glyph>")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "allocate":
        cat = sys.argv[2] if len(sys.argv) > 2 else "core"
        skill = sys.argv[3] if len(sys.argv) > 3 else ""
        glyph = allocator.allocate(cat, skill)
        print(f"Allocated: {glyph} (U+{ord(glyph):04X}) for {skill or 'pending'} in {cat}")

    elif cmd == "parse":
        inv = " ".join(sys.argv[2:])
        try:
            result = parser.parse(inv)
            print(json.dumps(result, indent=2))
        except ValueError as e:
            print(f"Parse error: {e}", file=sys.stderr)
            sys.exit(1)

    elif cmd == "list":
        cat = sys.argv[2] if len(sys.argv) > 2 else None
        entries = allocator.list_category(cat) if cat else allocator.list_all()
        for e in entries:
            print(f"{e.glyph} (U+{e.unicode_cp:04X}) → {e.skill_id} [{e.category}] uses={e.usage_count}")

    elif cmd == "map":
        print(json.dumps(glyph_map.to_json(), indent=2))

    elif cmd == "help":
        if len(sys.argv) < 3:
            print("Usage: help <glyph>")
            sys.exit(1)
        help_text = glyph_map.get_dsl_help(sys.argv[2])
        if help_text:
            print(help_text)
        else:
            print(f"No DSL spec for glyph {sys.argv[2]!r}")

    elif cmd == "register":
        # register <glyph> <skill_id> <verb> [@param=type:required:default:enum...]
        glyph = sys.argv[2]
        skill_id = sys.argv[3]
        verb = sys.argv[4]
        params = []
        for arg in sys.argv[5:]:
            if arg.startswith('@'):
                # @name=type:required:default:enum1,enum2
                parts = arg[1:].split('=', 1)
                name = parts[0]
                spec_parts = parts[1].split(':') if len(parts) > 1 else ['string', 'false', '', '']
                p = DSLParam(
                    name=name,
                    type=spec_parts[0],
                    required=spec_parts[1].lower() == 'true',
                    default=spec_parts[2] if spec_parts[2] else None,
                    enum=spec_parts[3].split(',') if spec_parts[3] else []
                )
                params.append(p)
        dsl = DSLSpec(verb=verb, params=params)
        allocator.register_skill(glyph, skill_id, dsl)
        glyph_map.save_map()
        print(f"Registered {glyph} → {skill_id} with verb {verb}")

    else:
        print(f"Unknown command: {cmd}")