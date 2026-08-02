"""
Prompt Registry — Centralized Enterprise Prompt Management System.

Provides prompt versioning with semver, full-text catalog search, deprecation
lifecycle management, A/B testing with variant assignment, a Jinja2-style
template engine with block inheritance, and a structured approval workflow.

Architecture:
    PromptTemplate — Jinja2-like templates with {% block %} inheritance
    PromptVersion — semver-tracked version of a compiled prompt
    PromptRecord  — complete prompt with full version history
    ABTest        — A/B test config: control vs variants with traffic split
    PromptCatalog — searchable catalog (by name, tag, semantic metadata)
    PromptRegistry — central registry orchestration all of the above

Python 3.10+ | dataclasses | full type hints | production quality
"""

from __future__ import annotations

import hashlib
import itertools
import json
import re
from abc import ABC, abstractmethod
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from functools import lru_cache
from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    FrozenSet,
    Iterator,
    List,
    Optional,
    Pattern,
    Sequence,
    Set,
    Tuple,
    TypeVar,
    Union,
)

# ────────────────────────────────────────────────────────────────────────────────
# Version / Status Enums
# ────────────────────────────────────────────────────────────────────────────────

class PromptStatus(str, Enum):
    """Approval-workflow status for a prompt record."""
    DRAFT      = "draft"
    PENDING    = "pending"       # submitted for approval
    APPROVED   = "approved"
    REJECTED   = "rejected"      # sent back to draft
    DEPRECATED = "deprecated"
    RETIRED    = "retired"       # fully removed from rotation


class VariantAllocation(str, Enum):
    """How A/B test traffic is split across variants."""
    EVEN      = "even"           # equal weight
    WEIGHTED  = "weighted"       # explicit weights
    RAMP      = "ramp"           # gradually increasing split
    STICKY    = "sticky"         # user-key-based deterministic assignment


# ────────────────────────────────────────────────────────────────────────────────
# Errors
# ────────────────────────────────────────────────────────────────────────────────

class PromptRegistryError(Exception):
    """Base for all prompt-registry errors."""

class PromptNotFoundError(PromptRegistryError):
    """A requested prompt / version does not exist."""

class InvalidTransitionError(PromptRegistryError):
    """Illegal status transition."""

class TemplateError(PromptRegistryError):
    """Template compilation / rendering failure."""

class ABTestError(PromptRegistryError):
    """A/B testing configuration / assignment error."""


# ────────────────────────────────────────────────────────────────────────────────
# Semver helper
# ────────────────────────────────────────────────────────────────────────────────

_SEMVER_RE: Pattern[str] = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+(?P<build>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)

def parse_semver(v: str) -> Tuple[int, int, int, str, str]:
    """Parse a semver string into (major, minor, patch, prerelease, build)."""
    m = _SEMVER_RE.match(v.strip())
    if not m:
        raise ValueError(f"Invalid semver: {v!r}")
    return (
        int(m["major"]),
        int(m["minor"]),
        int(m["patch"]),
        m["prerelease"] or "",
        m["build"] or "",
    )

def semver_key(v: str) -> Tuple[int, int, int, str]:
    """Sortable key for semver strings (prerelease sorts before release)."""
    major, minor, patch, pre, _ = parse_semver(v)
    return (major, minor, patch, "" if pre else "\uffff", pre)

T = TypeVar("T")


# ────────────────────────────────────────────────────────────────────────────────
# Template System  (Jinja2-style with inheritance)
# ────────────────────────────────────────────────────────────────────────────────

@dataclass
class TemplateBlock:
    """A named block within a template, used for inheritance overrides."""
    name: str
    content: str
    line_start: int
    line_end: int


@dataclass
class PromptTemplate:
    """A Jinja2-style template with block-inheritance support.

    Supported syntax:
        {{ variable }}          — variable substitution
        {% if expr %}...{% endif %}  — conditional
        {% for x in y %}...{% endfor %}  — iteration
        {% block name %}...{% endblock %}  — overridable block
        {% extends "parent_id" %}  — inherit from parent template
        {{ variable | filter }}  — filters (upper, lower, default, etc.)
    """

    id: str
    source: str
    parent_id: Optional[str] = None
    blocks: Dict[str, TemplateBlock] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ── block extraction ---------------------------------------------------

    _BLOCK_RE: ClassVar[Pattern[str]] = re.compile(
        r"^\{%-?\s*block\s+(\w+)\s*-?%\}(.*?)\{%-?\s*endblock\s*(?:\1)?\s*-?%\}$",
        re.DOTALL | re.MULTILINE,
    )

    _EXTENDS_RE: ClassVar[Pattern[str]] = re.compile(
        r"\{%-?\s*extends\s+['\"]([^'\"]+)['\"]\s*-?%\}",
    )

    _VARIABLE_RE: ClassVar[Pattern[str]] = re.compile(
        r"\{\{[\t ]*([a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)*)(?:[\t ]*\|[\t ]*(\w+))?[\t ]*\}\}"
    )

    def __post_init__(self) -> None:
        if not self.blocks:
            self._extract_blocks()

    # noinspection PyAttributeOutsideInit
    def _extract_blocks(self) -> None:
        """Parse `{% block name %} ... {% endblock %}` anywhere in text."""
        block_open = re.compile(
            r"\{%-?\s*block\s+(\w+)\s*-?%\}", re.DOTALL
        )
        block_close = re.compile(
            r"\{%-?\s*endblock\s*(\w+)?\s*-?%\}", re.DOTALL
        )
        extends_match = self._EXTENDS_RE.search(self.source)
        extends = extends_match.group(1) if extends_match else None

        text = self.source
        if extends_match:
            text = text[:extends_match.start()] + text[extends_match.end():]

        result: List[str] = []
        pos = 0
        while pos < len(text):
            open_m = block_open.search(text, pos)
            if not open_m:
                result.append(text[pos:])
                break
            result.append(text[pos:open_m.start()])
            block_name = open_m.group(1)
            content_start = open_m.end()
            close_m = block_close.search(text, content_start)
            if not close_m:
                raise TemplateError(f"Unclosed block '{block_name}'")
            content = text[content_start:close_m.start()]
            # Find approximate line numbers
            line_start = text[:open_m.start()].count('\n') + 1
            line_end = text[:close_m.end()].count('\n') + 1
            self.blocks[block_name] = TemplateBlock(
                name=block_name, content=content,
                line_start=line_start, line_end=line_end,
            )
            result.append(f"{{{{ BLOCK:{block_name} }}}}")
            pos = close_m.end()

        self.parent_id = extends
        self.source = "".join(result)

    # ── rendering ----------------------------------------------------------

    def render(self, vars_: Dict[str, Any],
               registry: Optional[PromptCatalog] = None) -> str:
        """Render the template into a final string.

        Resolution order:
        1. Walk parent chain (extends). The bottom-most template (base/parent)
           provides the overall structure. Each child's blocks override the
           parent's matching blocks.
        2. Substitute variables, conditionals, and loops.
        """
        if not self.parent_id:
            # No inheritance — straightforward render
            text = self.source
            for name, block in self.blocks.items():
                text = text.replace(f"{{{{ BLOCK:{name} }}}}", block.content)
            return self._render_text(text, vars_)

        # Inheritance path: walk to root (base template), then render downward
        if registry is None:
            raise TemplateError(
                f"Template '{self.id}' extends '{self.parent_id}' "
                f"but no registry provided for lookup"
            )

        chain: List[PromptTemplate] = [self]
        visited: Set[str] = {self.id}
        current = self
        while current.parent_id:
            parent = registry.get_template(current.parent_id)
            if parent is None:
                raise TemplateError(f"Parent template '{current.parent_id}' not found")
            if parent.id in visited:
                raise TemplateError("Circular extends detected")
            visited.add(parent.id)
            chain.append(parent)
            current = parent

        # Collect blocks from all templates (child wins)
        merged_blocks: Dict[str, str] = {}
        for tpl in reversed(chain):  # ancestors first
            for name, block in tpl.blocks.items():
                merged_blocks[name] = block.content

        # Render from the root template (last in chain = base)
        root = chain[-1]
        text = root.source
        for name, content in merged_blocks.items():
            text = text.replace(f"{{{{ BLOCK:{name} }}}}", content)

        return self._render_text(text, vars_)

    def _render_text(self, text: str, vars_: Dict[str, Any]) -> str:
        """Core text renderer: variables, conditionals, loops."""
        # --- for loops ---
        text = self._expand_for_loops(text, vars_)

        # --- if/else ---
        text = self._expand_conditionals(text, vars_)

        # --- variables ---
        def _replace_var(m: re.Match) -> str:
            var_path = m.group(1)
            filt = m.group(2)
            val = self._resolve_path(var_path, vars_)
            if filt:
                val = self._apply_filter(val, filt)
            return str(val) if val is not None else ""

        text = self._VARIABLE_RE.sub(_replace_var, text)

        return text

    @staticmethod
    def _resolve_path(path: str, vars_: Dict[str, Any]) -> Any:
        parts = path.split(".")
        val: Any = vars_
        for p in parts:
            if isinstance(val, dict):
                val = val.get(p)
            elif hasattr(val, p):
                val = getattr(val, p)
            else:
                return None
        return val

    _FOR_RE: ClassVar[Pattern[str]] = re.compile(
        r"\{%-?\s*for\s+(\w+)(?:\s*,\s*(\w+))?\s+in\s+([\w.]+)\s*-?%\}(.*?)\{%-?\s*endfor\s*-?%\}$",
        re.DOTALL | re.MULTILINE,
    )

    def _expand_for_loops(self, text: str, vars_: Dict[str, Any]) -> str:
        """Expand `{% for item in list %}...{% endfor %}`."""
        changed = True
        while changed:
            changed = False
            for m in self._FOR_RE.finditer(text):
                var_name = m.group(1)
                idx_name = m.group(2)
                iter_path = m.group(3)
                body = m.group(4)
                seq = self._resolve_path(iter_path, vars_)
                if seq is None or not hasattr(seq, "__iter__") or isinstance(seq, (str, bytes)):
                    continue
                loop_lines: List[str] = []
                for i, item in enumerate(seq):
                    local = {**vars_, var_name: item}
                    if idx_name:
                        local[idx_name] = i
                    loop_lines.append(self._render_text(body, local))
                text = text[: m.start()] + "".join(loop_lines) + text[m.end():]
                changed = True
                break  # restart after mutation
        return text

    _IF_RE: ClassVar[Pattern[str]] = re.compile(
        r"\{%-?\s*if\s+(not\s+)?([\w.]+)(?:\s*(==|!=|>=|<=|>|<)\s*(['\"]?)([\w.]+)\4)?\s*-?%\}"
        r"(.*?)"
        r"\{%-?\s*endif\s*-?%\}$",
        re.DOTALL | re.MULTILINE,
    )

    _IF_ELSE_RE: ClassVar[Pattern[str]] = re.compile(
        r"\{%-?\s*if\s+(not\s+)?([\w.]+)(?:\s*(==|!=|>=|<=|>|<)\s*(['\"]?)([\w.]+)\4)?\s*-?%\}"
        r"(.*?)"
        r"\{%-?\s*else\s*-?%\}"
        r"(.*?)"
        r"\{%-?\s*endif\s*-?%\}$",
        re.DOTALL | re.MULTILINE,
    )

    def _expand_conditionals(self, text: str, vars_: Dict[str, Any]) -> str:
        def _eval(neg: Optional[str], path: str, op: Optional[str],
                  val: Optional[str]) -> bool:
            lhs = self._resolve_path(path, vars_)
            truthy = bool(lhs)
            if neg:
                truthy = not truthy
                return truthy
            if op is None or val is None:
                return truthy
            rhs = self._resolve_path(val, vars_) if val else None
            if rhs is None:
                try:
                    rhs = float(val)
                except ValueError:
                    rhs = val
            try:
                lhs_num = float(lhs) if not isinstance(lhs, bool) else float("nan")
                rhs_num = float(rhs) if not isinstance(rhs, bool) else float("nan")
            except (ValueError, TypeError):
                lhs_num = rhs_num = float("nan")
            if op == "==":
                return str(lhs) == str(rhs)
            elif op == "!=":
                return str(lhs) != str(rhs)
            elif op in (">", "<", ">=", "<="):
                import operator as _op
                _ops = {">": _op.gt, "<": _op.lt, ">=": _op.ge, "<=": _op.le}
                # noinspection PyTypeChecker
                return _ops[op](lhs_num, rhs_num)
            return False

        # else-variant first (longer match)
        for m in self._IF_ELSE_RE.finditer(text):
            truthy = _eval(m.group(1), m.group(2), m.group(3), m.group(5))
            body = m.group(6) if truthy else m.group(7)
            text = text[: m.start()] + body + text[m.end():]
            return self._expand_conditionals(text, vars_)  # recurse

        for m in self._IF_RE.finditer(text):
            truthy = _eval(m.group(1), m.group(2), m.group(3), m.group(5))
            body = m.group(6) if truthy else ""
            text = text[: m.start()] + body + text[m.end():]
            return self._expand_conditionals(text, vars_)

        return text

    @staticmethod
    def _apply_filter(val: Any, filt_name: str) -> Any:
        filters: Dict[str, Callable[[Any], Any]] = {
            "upper": lambda x: str(x).upper(),
            "lower": lambda x: str(x).lower(),
            "title": lambda x: str(x).title(),
            "trim": lambda x: str(x).strip(),
            "length": lambda x: len(str(x)),
            "default": lambda x, d="": x if x else d,
            "json": lambda x: json.dumps(x) if not isinstance(x, str) else x,
            "first": lambda x: x[0] if hasattr(x, "__getitem__") and len(x) > 0 else x,
            "last": lambda x: x[-1] if hasattr(x, "__getitem__") and len(x) > 0 else x,
        }
        fn = filters.get(filt_name)
        return fn(val) if fn else val


# ────────────────────────────────────────────────────────────────────────────────
# Prompt Version  (semver-tracked)
# ────────────────────────────────────────────────────────────────────────────────

@dataclass
class PromptVersion:
    """A single semver-tagged version of a prompt."""
    id: str                                    # prompt_id
    semver: str                                # "1.2.3" or "1.2.3-beta.1"
    content: str                               # compiled (rendered) prompt text
    template_id: Optional[str] = None           # source template id
    variables: Dict[str, Any] = field(default_factory=dict)
    changelog: str = ""
    author: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    checksum: str = ""                         # SHA256 of content

    def __post_init__(self) -> None:
        if not self.checksum:
            self.checksum = hashlib.sha256(self.content.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "semver": self.semver, "content": self.content,
            "template_id": self.template_id, "variables": self.variables,
            "changelog": self.changelog, "author": self.author,
            "created_at": self.created_at, "checksum": self.checksum,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> PromptVersion:
        return cls(**{k: d[k] for k in [
            "id", "semver", "content", "template_id", "variables",
            "changelog", "author", "created_at", "checksum",
        ] if k in d})


# ────────────────────────────────────────────────────────────────────────────────
# Prompt Record
# ────────────────────────────────────────────────────────────────────────────────

@dataclass
class PromptRecord:
    """Full lifecycle record of a named prompt."""
    id: str
    name: str
    description: str = ""
    tags: List[str] = field(default_factory=list)
    status: PromptStatus = PromptStatus.DRAFT
    owner: str = ""
    approved_by: Optional[str] = None
    current_semver: str = "0.1.0"
    versions: List[PromptVersion] = field(default_factory=list)  # sorted newest first
    template_id: Optional[str] = None
    template_vars: Dict[str, Any] = field(default_factory=dict)
    deprecation_reason: str = ""
    successor_id: Optional[str] = None       # recommended replacement
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    ab_tests: List[str] = field(default_factory=list)  # ABTest ids this prompt participates in

    @property
    def latest(self) -> Optional[PromptVersion]:
        return self.versions[0] if self.versions else None

    def find_version(self, semver: str) -> Optional[PromptVersion]:
        for v in self.versions:
            if v.semver == semver:
                return v
        return None

    def add_version(self, v: PromptVersion) -> None:
        self.versions.insert(0, v)
        self.current_semver = v.semver
        self.updated_at = v.created_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "tags": self.tags, "status": self.status.value, "owner": self.owner,
            "approved_by": self.approved_by, "current_semver": self.current_semver,
            "versions": [v.to_dict() for v in self.versions],
            "template_id": self.template_id, "template_vars": self.template_vars,
            "deprecation_reason": self.deprecation_reason,
            "successor_id": self.successor_id,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "metadata": self.metadata, "ab_tests": self.ab_tests,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> PromptRecord:
        versions = [PromptVersion.from_dict(v) for v in d.get("versions", [])]
        return cls(
            id=d["id"], name=d["name"], description=d.get("description", ""),
            tags=d.get("tags", []), status=PromptStatus(d.get("status", "draft")),
            owner=d.get("owner", ""), approved_by=d.get("approved_by"),
            current_semver=d.get("current_semver", "0.1.0"),
            versions=versions, template_id=d.get("template_id"),
            template_vars=d.get("template_vars", {}),
            deprecation_reason=d.get("deprecation_reason", ""),
            successor_id=d.get("successor_id"),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            metadata=d.get("metadata", {}), ab_tests=d.get("ab_tests", []),
        )


# ────────────────────────────────────────────────────────────────────────────────
# A/B Testing
# ────────────────────────────────────────────────────────────────────────────────

@dataclass
class ABTestVariant:
    """A single variant arm in an A/B test."""
    name: str                 # "control", "variant_a", etc.
    prompt_id: str            # which PromptRecord
    version_semver: str       # which specific version
    weight: float = 0.0       # allocation weight (0–1)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ABTest:
    """An A/B test comparing multiple prompt variants."""
    id: str
    name: str
    description: str = ""
    variants: List[ABTestVariant] = field(default_factory=list)
    allocation: VariantAllocation = VariantAllocation.EVEN
    traffic_pct: float = 100.0          # % of traffic to include
    user_key_field: str = "user_id"     # for sticky allocation
    start_at: Optional[str] = None
    end_at: Optional[str] = None
    status: str = "draft"               # draft | running | paused | concluded
    metrics: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def assign(self, context: Dict[str, Any]) -> ABTestVariant:
        """Deterministically assign a user/request to a variant.

        In STICKY mode the assignment is keyed off `user_key_field` so the same
        user always gets the same variant throughout the test.
        """
        if not self.variants:
            raise ABTestError("No variants defined")
        if self.status != "running":
            # If not running, always return first (control) variant
            return self.variants[0]

        if self.allocation == VariantAllocation.STICKY:
            key_val = str(context.get(self.user_key_field, "unknown"))
            bucket = int(hashlib.md5(f"{self.id}:{key_val}".encode()).hexdigest(), 16) % 100
            cumulative = 0.0
            for v in self._normalized_variants():
                cumulative += v.weight * 100.0
                if bucket < cumulative:
                    return v
            return self.variants[0]

        if self.allocation == VariantAllocation.EVEN:
            n = len(self.variants)
            weights = [1.0 / n] * n
        elif self.allocation == VariantAllocation.RAMP:
            weights = self._ramp_weights()
        else:
            # WEIGHTED
            weights = [v.weight for v in self.variants]

        cumulative = 0.0
        r = hash(str(context)) % 100000 / 100000.0
        for v, w in zip(self.variants, weights):
            cumulative += w
            if r <= cumulative:
                return v
        return self.variants[-1]

    def _normalized_variants(self) -> List[ABTestVariant]:
        total = sum(v.weight for v in self.variants) or 1.0
        return [
            ABTestVariant(
                name=v.name, prompt_id=v.prompt_id,
                version_semver=v.version_semver,
                weight=v.weight / total, metadata=v.metadata,
            )
            for v in self.variants
        ]

    def _ramp_weights(self) -> List[float]:
        """Gradually shifting weights from control toward variants.

        The `traffic_pct` is used as the proportion going to non-control variants.
        """
        if len(self.variants) == 1:
            return [1.0]
        control_weight = max(0.0, 1.0 - self.traffic_pct / 100.0)
        variant_count = len(self.variants) - 1
        variant_weight = (1.0 - control_weight) / max(variant_count, 1)
        return [control_weight] + [variant_weight] * variant_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "variants": [
                {"name": v.name, "prompt_id": v.prompt_id,
                 "version_semver": v.version_semver, "weight": v.weight,
                 "metadata": v.metadata}
                for v in self.variants
            ],
            "allocation": self.allocation.value, "traffic_pct": self.traffic_pct,
            "user_key_field": self.user_key_field,
            "start_at": self.start_at, "end_at": self.end_at,
            "status": self.status, "metrics": self.metrics,
            "created_at": self.created_at,
        }


# ────────────────────────────────────────────────────────────────────────────────
# Prompt Catalog  (searchable index)
# ────────────────────────────────────────────────────────────────────────────────

@dataclass
class SearchFilter:
    """Filter criteria for catalog queries."""
    name_pattern: Optional[str] = None       # regex
    tags: Optional[FrozenSet[str]] = None    # all must match
    status: Optional[PromptStatus] = None
    owner: Optional[str] = None
    deprecated_only: bool = False
    min_semver: Optional[str] = None
    max_results: int = 100


class PromptCatalog:
    """Searchable, in-memory catalog of PromptRecords and PromptTemplates."""

    def __init__(self) -> None:
        self._records: Dict[str, PromptRecord] = {}
        self._templates: Dict[str, PromptTemplate] = {}
        self._ab_tests: Dict[str, ABTest] = {}
        # inverted indexes
        self._tag_index: Dict[str, Set[str]] = defaultdict(set)
        self._name_index: Dict[str, str] = {}  # lowercase name -> id

    # ── records ------------------------------------------------------------

    def add(self, record: PromptRecord) -> None:
        self._records[record.id] = record
        self._name_index[record.name.lower()] = record.id
        for tag in record.tags:
            self._tag_index[tag.lower()].add(record.id)

    def remove(self, record_id: str) -> bool:
        rec = self._records.pop(record_id, None)
        if rec is None:
            return False
        self._name_index.pop(rec.name.lower(), None)
        for tag in rec.tags:
            s = self._tag_index.get(tag.lower())
            if s:
                s.discard(record_id)
        return True

    def get(self, record_id: str) -> Optional[PromptRecord]:
        return self._records.get(record_id)

    def get_by_name(self, name: str) -> Optional[PromptRecord]:
        rid = self._name_index.get(name.lower())
        return self._records.get(rid) if rid else None

    def search(self, filt: SearchFilter) -> List[PromptRecord]:
        results = list(self._records.values())

        if filt.name_pattern:
            pat = re.compile(filt.name_pattern, re.IGNORECASE)
            results = [r for r in results if pat.search(r.name)]
        if filt.tags:
            tag_set = {t.lower() for t in filt.tags}
            results = [r for r in results
                       if tag_set.issubset({t.lower() for t in r.tags})]
        if filt.status:
            results = [r for r in results if r.status == filt.status]
        if filt.owner:
            results = [r for r in results if r.owner == filt.owner]
        if filt.deprecated_only:
            results = [r for r in results if r.status in (PromptStatus.DEPRECATED, PromptStatus.RETIRED)]
        if filt.min_semver:
            min_key = semver_key(filt.min_semver)
            results = [r for r in results if r.latest and semver_key(r.latest.semver) >= min_key]

        # sort by newest first
        results.sort(key=lambda r: r.updated_at or "", reverse=True)
        return results[: filt.max_results]

    def list_all(self) -> List[PromptRecord]:
        return list(self._records.values())

    def count_by_status(self) -> Dict[str, int]:
        counts: Dict[str, int] = defaultdict(int)
        for r in self._records.values():
            counts[r.status.value] += 1
        return dict(counts)

    # ── templates ----------------------------------------------------------

    def add_template(self, tpl: PromptTemplate) -> None:
        self._templates[tpl.id] = tpl

    def get_template(self, tpl_id: str) -> Optional[PromptTemplate]:
        return self._templates.get(tpl_id)

    def list_templates(self) -> List[PromptTemplate]:
        return list(self._templates.values())

    # ── A/B tests ----------------------------------------------------------

    def add_ab_test(self, test: ABTest) -> None:
        self._ab_tests[test.id] = test

    def get_ab_test(self, test_id: str) -> Optional[ABTest]:
        return self._ab_tests.get(test_id)

    def list_ab_tests(self, status: Optional[str] = None) -> List[ABTest]:
        if status:
            return [t for t in self._ab_tests.values() if t.status == status]
        return list(self._ab_tests.values())

    def assign_ab_variant(self, test_id: str, context: Dict[str, Any]) -> ABTestVariant:
        test = self._ab_tests.get(test_id)
        if test is None:
            raise ABTestError(f"A/B test '{test_id}' not found")
        return test.assign(context)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "records": [r.to_dict() for r in self._records.values()],
            "templates": [{"id": t.id, "source": t.source, "parent_id": t.parent_id,
                           "metadata": t.metadata} for t in self._templates.values()],
            "ab_tests": [t.to_dict() for t in self._ab_tests.values()],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> PromptCatalog:
        cat = cls()
        for rd in d.get("records", []):
            cat.add(PromptRecord.from_dict(rd))
        for td in d.get("templates", []):
            cat.add_template(PromptTemplate(
                id=td["id"], source=td["source"],
                parent_id=td.get("parent_id"),
                metadata=td.get("metadata", {}),
            ))
        for ad in d.get("ab_tests", []):
            variants = [
                ABTestVariant(name=v["name"], prompt_id=v["prompt_id"],
                              version_semver=v["version_semver"],
                              weight=v.get("weight", 0.0),
                              metadata=v.get("metadata", {}))
                for v in ad.get("variants", [])
            ]
            cat.add_ab_test(ABTest(
                id=ad["id"], name=ad["name"],
                description=ad.get("description", ""),
                variants=variants,
                allocation=VariantAllocation(ad.get("allocation", "even")),
                traffic_pct=ad.get("traffic_pct", 100.0),
                user_key_field=ad.get("user_key_field", "user_id"),
                start_at=ad.get("start_at"), end_at=ad.get("end_at"),
                status=ad.get("status", "draft"),
                metrics=ad.get("metrics", {}),
                created_at=ad.get("created_at", ""),
            ))
        return cat


# ────────────────────────────────────────────────────────────────────────────────
# Prompt Registry  (central orchestrator)
# ────────────────────────────────────────────────────────────────────────────────

class PromptRegistry:
    """Central registry — ties together catalog, versions, A/B tests, and templates.

    Workflow state machine (valid transitions):
        DRAFT → PENDING → APPROVED → DEPRECATED → RETIRED
        DRAFT → PENDING → REJECTED  → DRAFT
        APPROVED → DRAFT  (when new version created)

    Usage:
        >>> reg = PromptRegistry()
        >>> rec = reg.create("greet", "Greeting Prompt", "Hello {{ name }}!",
        ...                  tags=["onboarding"], owner="alice")
        >>> reg.submit(rec.id)
        >>> reg.approve(rec.id, approver="bob")
        >>> rendered = reg.render("greet", {"name": "World"})
    """

    _TRANSITIONS: ClassVar[Dict[PromptStatus, FrozenSet[PromptStatus]]] = {
        PromptStatus.DRAFT:      frozenset({PromptStatus.PENDING, PromptStatus.DEPRECATED}),
        PromptStatus.PENDING:    frozenset({PromptStatus.APPROVED, PromptStatus.REJECTED}),
        PromptStatus.APPROVED:   frozenset({PromptStatus.DEPRECATED, PromptStatus.DRAFT}),
        PromptStatus.REJECTED:   frozenset({PromptStatus.DRAFT}),
        PromptStatus.DEPRECATED: frozenset({PromptStatus.RETIRED}),
        PromptStatus.RETIRED:    frozenset(),
    }

    def __init__(self, catalog: Optional[PromptCatalog] = None) -> None:
        self.catalog = catalog or PromptCatalog()
        self._observers: Dict[str, List[Callable[..., None]]] = defaultdict(list)
        self._initial_semver = "0.1.0"

    # ── lifecycle: create / version ----------------------------------------

    def create(self, name: str, description: str, template_source: str = "",
               tags: Optional[List[str]] = None, owner: str = "",
               template_id: Optional[str] = None,
               template_vars: Optional[Dict[str, Any]] = None) -> PromptRecord:
        """Create a new prompt record (DRAFT) from a template source."""
        prompt_id = self._generate_id(name)
        tpl = PromptTemplate(id=prompt_id + "_tpl", source=template_source)
        self.catalog.add_template(tpl)

        compiled = tpl.render(template_vars or {})
        version = PromptVersion(
            id=prompt_id, semver=self._initial_semver, content=compiled,
            template_id=tpl.id, variables=deepcopy(template_vars) if template_vars else {},
            author=owner, changelog="Initial creation",
        )
        record = PromptRecord(
            id=prompt_id, name=name, description=description,
            tags=tags or [], owner=owner, template_id=tpl.id,
            template_vars=template_vars or {},
            versions=[],   # will be set by add_version
        )
        record.add_version(version)
        self.catalog.add(record)
        self._emit("created", record)
        return record

    def update(self, prompt_id: str, template_source: str,
               template_vars: Optional[Dict[str, Any]] = None,
               changelog: str = "", author: str = "") -> PromptRecord:
        """Bump version — edit the template source and/or variables.

        Automatically bumps semver: if the previous was 1.2.3 this becomes 1.2.4.
        """
        rec = self._require(prompt_id)
        tpl = self.catalog.get_template(rec.template_id or "")
        if tpl is None:
            raise PromptNotFoundError(f"Template for '{prompt_id}' not found")

        tpl.source = template_source
        tpl._extract_blocks()  # reparse
        merged_vars = {**rec.template_vars, **(template_vars or {})}

        compiled = tpl.render(merged_vars)
        new_semver = self._bump_patch(rec.current_semver)
        version = PromptVersion(
            id=prompt_id, semver=new_semver, content=compiled,
            template_id=tpl.id, variables=deepcopy(merged_vars),
            author=author, changelog=changelog,
        )
        rec.add_version(version)
        rec.template_vars = merged_vars
        rec.status = PromptStatus.DRAFT
        self.catalog.add(rec)
        self._emit("version_created", rec, version)
        return rec

    def get(self, prompt_id: str) -> Optional[PromptRecord]:
        return self.catalog.get(prompt_id)

    def get_by_name(self, name: str) -> Optional[PromptRecord]:
        return self.catalog.get_by_name(name)

    def delete(self, prompt_id: str) -> bool:
        rec = self.catalog.get(prompt_id)
        if rec is None:
            return False
        ok = self.catalog.remove(prompt_id)
        if ok:
            self._emit("deleted", rec)
        return ok

    # ── rendering ----------------------------------------------------------

    def render(self, prompt_id: str, vars_: Optional[Dict[str, Any]] = None,
               version_semver: Optional[str] = None) -> str:
        """Render the named prompt's template with the given variables.

        If `version_semver` is specified, that historical version's stored
        content is returned (with optional variable overrides applied);
        otherwise the latest version is served.
        """
        rec = self._require(prompt_id)

        if version_semver:
            v = rec.find_version(version_semver)
            if v is None:
                raise PromptNotFoundError(f"Version {version_semver} not found for '{prompt_id}'")
            # Re-render the stored version content with overrides
            tpl = self._require_template(rec)
            vars_used = v.variables if v.variables else rec.template_vars
            merged = {**vars_used, **(vars_ or {})}
            # If the version has its own content and no new vars, return content directly
            if not vars_ and v.content:
                return v.content
            # Otherwise re-render with historical variables on current template
            return tpl.render(merged, registry=self.catalog)

        tpl = self._require_template(rec)
        merged = {**rec.template_vars, **(vars_ or {})}
        result = tpl.render(merged, registry=self.catalog)
        return result

    def render_ab(self, test_id: str, context: Dict[str, Any],
                  extra_vars: Optional[Dict[str, Any]] = None) -> Tuple[str, ABTestVariant]:
        """A/B-aware render: assign variant, then render that variant's prompt."""
        variant = self.catalog.assign_ab_variant(test_id, context)
        prompt_vars = {**context, **(extra_vars or {})}
        rendered = self.render(variant.prompt_id, prompt_vars, variant.version_semver)
        return rendered, variant

    # ── approval workflow --------------------------------------------------

    def submit(self, prompt_id: str, approvers: Optional[List[str]] = None) -> PromptRecord:
        """Submit DRAFT → PENDING."""
        rec = self._transition(prompt_id, PromptStatus.PENDING)
        self._emit("submitted", rec, approvers)
        return rec

    def approve(self, prompt_id: str, approver: str) -> PromptRecord:
        """PENDING → APPROVED."""
        rec = self._transition(prompt_id, PromptStatus.APPROVED)
        rec.approved_by = approver
        self.catalog.add(rec)
        self._emit("approved", rec, approver)
        return rec

    def reject(self, prompt_id: str, reason: str = "") -> PromptRecord:
        """PENDING → REJECTED."""
        rec = self._transition(prompt_id, PromptStatus.REJECTED)
        self._emit("rejected", rec, reason)
        return rec

    def deprecate(self, prompt_id: str, reason: str = "",
                  successor_id: Optional[str] = None) -> PromptRecord:
        """APPROVED → DEPRECATED."""
        rec = self._transition(prompt_id, PromptStatus.DEPRECATED)
        rec.deprecation_reason = reason
        rec.successor_id = successor_id
        self.catalog.add(rec)
        self._emit("deprecated", rec, reason)
        return rec

    def retire(self, prompt_id: str) -> PromptRecord:
        """DEPRECATED → RETIRED."""
        rec = self._transition(prompt_id, PromptStatus.RETIRED)
        self._emit("retired", rec)
        return rec

    # ── search -------------------------------------------------------------

    def search(self, filt: SearchFilter) -> List[PromptRecord]:
        return self.catalog.search(filt)

    def list_all(self) -> List[PromptRecord]:
        return self.catalog.list_all()

    # ── A/B test management ------------------------------------------------

    def create_ab_test(self, name: str, variants: List[ABTestVariant],
                       allocation: VariantAllocation = VariantAllocation.EVEN,
                       traffic_pct: float = 100.0,
                       user_key_field: str = "user_id",
                       description: str = "") -> ABTest:
        test = ABTest(
            id=self._generate_id("ab_" + name),
            name=name, description=description, variants=variants,
            allocation=allocation, traffic_pct=traffic_pct,
            user_key_field=user_key_field,
        )
        self.catalog.add_ab_test(test)
        return test

    def start_ab_test(self, test_id: str) -> ABTest:
        test = self._require_ab(test_id)
        if test.status != "draft":
            raise ABTestError(f"Can only start 'draft' tests, got '{test.status}'")
        test.status = "running"
        test.start_at = datetime.now(timezone.utc).isoformat()
        self._emit("ab_started", test)
        return test

    def pause_ab_test(self, test_id: str) -> ABTest:
        test = self._require_ab(test_id)
        test.status = "paused"
        return test

    def conclude_ab_test(self, test_id: str, winner_variant: Optional[str] = None,
                         metrics: Optional[Dict[str, Any]] = None) -> ABTest:
        test = self._require_ab(test_id)
        test.status = "concluded"
        test.end_at = datetime.now(timezone.utc).isoformat()
        if metrics:
            test.metrics.update(metrics)
        if winner_variant:
            test.metrics["winner"] = winner_variant
        self._emit("ab_concluded", test, winner_variant)
        return test

    # ── observers / hooks --------------------------------------------------

    def on(self, event: str, callback: Callable[..., None]) -> None:
        """Register an observer callback for a lifecycle event.

        Events: created, version_created, submitted, approved, rejected,
                deprecated, retired, deleted, ab_started, ab_concluded.
        """
        self._observers[event].append(callback)

    def remove_observer(self, event: str, callback: Callable[..., None]) -> None:
        try:
            self._observers[event].remove(callback)
        except ValueError:
            pass

    # ── import / export ----------------------------------------------------

    def export_catalog(self) -> Dict[str, Any]:
        return self.catalog.to_dict()

    def import_catalog(self, data: Dict[str, Any]) -> None:
        self.catalog = PromptCatalog.from_dict(data)

    # ── helpers ------------------------------------------------------------

    def _require(self, prompt_id: str) -> PromptRecord:
        rec = self.catalog.get(prompt_id)
        if rec is None:
            raise PromptNotFoundError(f"Prompt '{prompt_id}' not found")
        return rec

    def _require_template(self, rec: PromptRecord) -> PromptTemplate:
        tpl_id = rec.template_id or rec.id + "_tpl"
        tpl = self.catalog.get_template(tpl_id)
        if tpl is None:
            raise PromptNotFoundError(f"Template '{tpl_id}' not found")
        return tpl

    def _require_ab(self, test_id: str) -> ABTest:
        t = self.catalog.get_ab_test(test_id)
        if t is None:
            raise ABTestError(f"A/B test '{test_id}' not found")
        return t

    def _transition(self, prompt_id: str, target: PromptStatus) -> PromptRecord:
        rec = self._require(prompt_id)
        allowed = self._TRANSITIONS.get(rec.status, frozenset())
        if target not in allowed:
            raise InvalidTransitionError(
                f"Cannot transition {rec.id} from {rec.status.value} "
                f"to {target.value}. Allowed: {[s.value for s in allowed]}"
            )
        rec.status = target
        rec.updated_at = datetime.now(timezone.utc).isoformat()
        self.catalog.add(rec)
        return rec

    def _emit(self, event: str, *args: Any) -> None:
        for cb in self._observers.get(event, []):
            try:
                cb(*args)
            except Exception:
                pass  # observers must not disrupt core workflow

    @staticmethod
    def _generate_id(prefix: str) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")[:17]
        slug = re.sub(r"[^a-z0-9_]", "_", prefix.lower())[:40]
        return f"{slug}_{ts}"

    @staticmethod
    def _bump_patch(semver: str) -> str:
        major, minor, patch, pre, build = parse_semver(semver)
        return f"{major}.{minor}.{patch + 1}"