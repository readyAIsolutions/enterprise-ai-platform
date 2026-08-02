"""
Context Manager - Enterprise-grade context management system.

Manages hierarchical context blocks for AI interactions, including:
- Current task and active project context
- Recent conversation history
- Long-term memory retrieval
- Retrieved knowledge (RAG)
- Organizational standards and documentation
- Security requirements and compliance rules
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union
from collections import OrderedDict
import json


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ContextType(str, Enum):
    """Standard context block types."""
    TASK = "task"                       # Current task description
    PROJECT = "project"                 # Active project info
    CONVERSATION = "conversation"       # Recent conversation history
    MEMORY = "memory"                   # Long-term memory
    KNOWLEDGE = "knowledge"             # Retrieved knowledge (RAG)
    STANDARDS = "standards"            # Organizational standards
    DOCUMENTATION = "documentation"     # Relevant documentation
    SECURITY = "security"              # Security requirements
    COMPLIANCE = "compliance"          # Compliance rules
    SYSTEM = "system"                  # System-level instructions
    USER_PREFERENCES = "user_prefs"    # User preferences/settings
    TOOL_DEFINITIONS = "tools"         # Available tool definitions
    CUSTOM = "custom"                  # User-defined context


class ContextPriority(int, Enum):
    """Priority levels for context blocks (higher = more important)."""
    CRITICAL = 100      # Must never be truncated (security, compliance)
    HIGH = 75           # Very important (task, project)
    MEDIUM = 50         # Standard importance
    LOW = 25            # Nice to have
    BACKGROUND = 0      # Optional context


class ContextSource(str, Enum):
    """Source of a context block."""
    SYSTEM = "system"
    USER = "user"
    RETRIEVAL = "retrieval"      # From RAG/knowledge base
    MEMORY = "memory"            # From long-term memory
    INFERENCE = "inference"      # Inferred from conversation
    EXTERNAL = "external"        # From external API/tool
    CACHED = "cached"            # From context cache


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class ContextBlock:
    """A single block of context with metadata."""
    id: str
    type: ContextType
    content: str
    priority: ContextPriority = ContextPriority.MEDIUM
    source: ContextSource = ContextSource.SYSTEM
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    ttl_seconds: Optional[int] = None
    relevance_score: float = 1.0
    is_immutable: bool = False
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    _token_estimate: Optional[int] = None

    @property
    def is_expired(self) -> bool:
        """Check if this context block has expired."""
        if self.expires_at:
            return datetime.now(timezone.utc) > self.expires_at
        if self.ttl_seconds is not None:
            return (datetime.now(timezone.utc) - self.created_at).total_seconds() > self.ttl_seconds
        return False

    @property
    def age_seconds(self) -> float:
        """Age of this context block in seconds."""
        return (datetime.now(timezone.utc) - self.created_at).total_seconds()

    @property
    def estimated_tokens(self) -> int:
        """Rough token estimate (4 chars ~= 1 token)."""
        if self._token_estimate is None:
            self._token_estimate = max(1, len(self.content) // 4)
        return self._token_estimate

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "content": self.content,
            "priority": self.priority.value,
            "source": self.source.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "ttl_seconds": self.ttl_seconds,
            "relevance_score": self.relevance_score,
            "is_immutable": self.is_immutable,
            "tags": self.tags,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextBlock":
        return cls(
            id=data["id"],
            type=ContextType(data["type"]),
            content=data["content"],
            priority=ContextPriority(data["priority"]),
            source=ContextSource(data["source"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
            ttl_seconds=data.get("ttl_seconds"),
            relevance_score=data.get("relevance_score", 1.0),
            is_immutable=data.get("is_immutable", False),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ContextBlock):
            return NotImplemented
        return self.id == other.id


@dataclass
class ContextSnapshot:
    """A point-in-time snapshot of the entire context."""
    blocks: List[ContextBlock]
    total_tokens: int
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextWindow:
    """Defines constraints for the context window."""
    max_tokens: int
    reserved_tokens: int = 0          # Reserved for response
    min_free_tokens: int = 500        # Minimum free tokens to maintain
    current_usage: int = 0


# ---------------------------------------------------------------------------
# Context Manager
# ---------------------------------------------------------------------------

class ContextManagerError(Exception):
    """Base exception for context manager errors."""


class ContextNotFoundError(ContextManagerError):
    """Raised when a context block is not found."""


class ContextWindowExceededError(ContextManagerError):
    """Raised when the context window is exceeded."""


class ContextManager:
    """
    Enterprise-grade context manager for AI interactions.

    Features:
    - Hierarchical context blocks with typed categories
    - Priority-based organization
    - TTL-based expiration
    - Relevance scoring
    - Token-aware window management
    - Immutable critical context (security, compliance)
    - Context deduplication
    - Snapshot and restore
    - Thread-safe operations

    Usage::

        ctx = ContextManager(max_tokens=100000)
        ctx.add_task("Summarize this article")
        ctx.add_security_policy("Data must not leave the system")
        ctx.add_knowledge("The article discusses AI safety...", relevance=0.95)
        assembled = ctx.assemble_context()
    """

    def __init__(
        self,
        max_tokens: int = 100_000,
        reserved_tokens: int = 4_000,
        enable_auto_eviction: bool = True,
    ):
        self._blocks: OrderedDict[str, ContextBlock] = OrderedDict()
        self._lock = threading.RLock()
        self._id_counter = 0
        self.window = ContextWindow(
            max_tokens=max_tokens,
            reserved_tokens=reserved_tokens,
        )
        self.enable_auto_eviction = enable_auto_eviction
        self._on_evict_callbacks: List[Callable[[ContextBlock], None]] = []

    # ------------------------------------------------------------------
    # Adding Context
    # ------------------------------------------------------------------

    def add(
        self,
        content: str,
        type: ContextType = ContextType.CUSTOM,
        priority: ContextPriority = ContextPriority.MEDIUM,
        source: ContextSource = ContextSource.SYSTEM,
        ttl_seconds: Optional[int] = None,
        relevance_score: float = 1.0,
        is_immutable: bool = False,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        block_id: Optional[str] = None,
    ) -> str:
        """
        Add a context block.

        Returns:
            The block ID.
        """
        if not content or not content.strip():
            raise ValueError("Context content cannot be empty")

        bid = block_id or self._generate_id(type)

        block = ContextBlock(
            id=bid,
            type=type,
            content=content,
            priority=priority,
            source=source,
            ttl_seconds=ttl_seconds,
            relevance_score=relevance_score,
            is_immutable=is_immutable,
            tags=tags or [],
            metadata=metadata or {},
        )

        with self._lock:
            self._blocks[bid] = block
            self.window.current_usage = self._compute_total_tokens()

            if self.enable_auto_eviction and self.is_over_limit():
                self._evict_to_fit()

        return bid

    def add_task(self, description: str, priority: ContextPriority = ContextPriority.HIGH) -> str:
        """Add a task context block."""
        return self.add(
            content=description,
            type=ContextType.TASK,
            priority=priority,
            source=ContextSource.USER,
        )

    def add_project(self, info: str, priority: ContextPriority = ContextPriority.HIGH) -> str:
        """Add a project context block."""
        return self.add(
            content=info,
            type=ContextType.PROJECT,
            priority=priority,
        )

    def add_conversation(self, messages: Union[str, List[Dict[str, str]]]) -> str:
        """Add conversation history."""
        if isinstance(messages, list):
            content = "\n".join(
                f"{m.get('role', 'unknown')}: {m.get('content', '')}"
                for m in messages
            )
        else:
            content = messages
        return self.add(
            content=content,
            type=ContextType.CONVERSATION,
            priority=ContextPriority.MEDIUM,
            ttl_seconds=3600,  # Conversations expire after 1 hour
        )

    def add_memory(self, content: str, relevance: float = 0.8) -> str:
        """Add a long-term memory block."""
        return self.add(
            content=content,
            type=ContextType.MEMORY,
            source=ContextSource.MEMORY,
            relevance_score=relevance,
            priority=ContextPriority.MEDIUM,
        )

    def add_knowledge(self, content: str, relevance: float = 0.9) -> str:
        """Add retrieved knowledge."""
        return self.add(
            content=content,
            type=ContextType.KNOWLEDGE,
            source=ContextSource.RETRIEVAL,
            relevance_score=relevance,
            priority=ContextPriority.HIGH,
        )

    def add_standards(self, content: str) -> str:
        """Add organizational standards."""
        return self.add(
            content=content,
            type=ContextType.STANDARDS,
            priority=ContextPriority.HIGH,
            is_immutable=True,
        )

    def add_documentation(self, content: str) -> str:
        """Add documentation context."""
        return self.add(
            content=content,
            type=ContextType.DOCUMENTATION,
            source=ContextSource.RETRIEVAL,
            priority=ContextPriority.MEDIUM,
        )

    def add_security_policy(self, content: str) -> str:
        """Add a security policy (immutable, critical)."""
        return self.add(
            content=content,
            type=ContextType.SECURITY,
            priority=ContextPriority.CRITICAL,
            is_immutable=True,
            tags=["security", "immutable"],
        )

    def add_compliance_rules(self, content: str) -> str:
        """Add compliance rules (immutable, critical)."""
        return self.add(
            content=content,
            type=ContextType.COMPLIANCE,
            priority=ContextPriority.CRITICAL,
            is_immutable=True,
            tags=["compliance", "immutable"],
        )

    def add_system_instruction(self, content: str) -> str:
        """Add a system-level instruction."""
        return self.add(
            content=content,
            type=ContextType.SYSTEM,
            priority=ContextPriority.HIGH,
            is_immutable=True,
        )

    # ------------------------------------------------------------------
    # Retrieving Context
    # ------------------------------------------------------------------

    def get(self, block_id: str) -> ContextBlock:
        """Retrieve a specific context block."""
        with self._lock:
            if block_id not in self._blocks:
                raise ContextNotFoundError(f"Context block not found: {block_id}")
            return self._blocks[block_id]

    def get_by_type(self, type: ContextType) -> List[ContextBlock]:
        """Get all context blocks of a specific type."""
        with self._lock:
            return [b for b in self._blocks.values() if b.type == type and not b.is_expired]

    def get_by_tag(self, tag: str) -> List[ContextBlock]:
        """Get all context blocks with a specific tag."""
        with self._lock:
            return [b for b in self._blocks.values() if tag in b.tags and not b.is_expired]

    def get_immutable(self) -> List[ContextBlock]:
        """Get all immutable context blocks."""
        with self._lock:
            return [b for b in self._blocks.values() if b.is_immutable and not b.is_expired]

    def get_critical(self) -> List[ContextBlock]:
        """Get all critical-priority context blocks."""
        with self._lock:
            return [
                b for b in self._blocks.values()
                if b.priority == ContextPriority.CRITICAL and not b.is_expired
            ]

    def get_all(self, include_expired: bool = False) -> List[ContextBlock]:
        """Get all context blocks."""
        with self._lock:
            blocks = list(self._blocks.values())
            if not include_expired:
                blocks = [b for b in blocks if not b.is_expired]
            return blocks

    # ------------------------------------------------------------------
    # Mutating Context
    # ------------------------------------------------------------------

    def update(
        self,
        block_id: str,
        content: Optional[str] = None,
        relevance_score: Optional[float] = None,
        priority: Optional[ContextPriority] = None,
        ttl_seconds: Optional[int] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update an existing context block."""
        block = self.get(block_id)

        if block.is_immutable:
            raise ContextManagerError(f"Cannot update immutable block: {block_id}")

        with self._lock:
            if content is not None:
                block.content = content
            if relevance_score is not None:
                block.relevance_score = max(0.0, min(1.0, relevance_score))
            if priority is not None:
                block.priority = priority
            if ttl_seconds is not None:
                block.ttl_seconds = ttl_seconds
                block.expires_at = None
            if tags is not None:
                block.tags = tags
            if metadata is not None:
                block.metadata = {**block.metadata, **metadata}

    def remove(self, block_id: str, force: bool = False) -> None:
        """Remove a context block."""
        block = self.get(block_id)
        if block.is_immutable and not force:
            raise ContextManagerError(
                f"Cannot remove immutable block {block_id}. Use force=True to override."
            )

        with self._lock:
            del self._blocks[block_id]
            self.window.current_usage = self._compute_total_tokens()

    def remove_by_type(self, type: ContextType) -> int:
        """Remove all blocks of a specific type. Returns count removed."""
        with self._lock:
            to_remove = [
                bid for bid, b in self._blocks.items()
                if b.type == type and not b.is_immutable
            ]
            for bid in to_remove:
                del self._blocks[bid]
            self.window.current_usage = self._compute_total_tokens()
            return len(to_remove)

    def clear(self, keep_immutable: bool = True) -> int:
        """Clear all context, optionally keeping immutable blocks."""
        with self._lock:
            if keep_immutable:
                to_remove = [
                    bid for bid, b in self._blocks.items()
                    if not b.is_immutable
                ]
            else:
                to_remove = list(self._blocks.keys())

            for bid in to_remove:
                del self._blocks[bid]

            self.window.current_usage = self._compute_total_tokens()
            return len(to_remove)

    # ------------------------------------------------------------------
    # Expiration Management
    # ------------------------------------------------------------------

    def expire_stale(self) -> int:
        """Remove all expired context blocks. Returns count removed."""
        with self._lock:
            expired = [
                bid for bid, b in self._blocks.items()
                if b.is_expired and not b.is_immutable
            ]
            for bid in expired:
                del self._blocks[bid]
            self.window.current_usage = self._compute_total_tokens()
            return len(expired)

    def set_expiry(self, block_id: str, ttl_seconds: int) -> None:
        """Set a TTL on a context block."""
        block = self.get(block_id)
        with self._lock:
            block.ttl_seconds = ttl_seconds
            block.expires_at = None  # Clear explicit expiry in favor of TTL

    def set_absolute_expiry(self, block_id: str, expires_at: datetime) -> None:
        """Set an absolute expiry time."""
        block = self.get(block_id)
        with self._lock:
            block.expires_at = expires_at
            block.ttl_seconds = None

    # ------------------------------------------------------------------
    # Context Assembly
    # ------------------------------------------------------------------

    def assemble_context(
        self,
        max_tokens: Optional[int] = None,
        sort_by: str = "priority",
        include_types: Optional[List[ContextType]] = None,
        exclude_types: Optional[List[ContextType]] = None,
    ) -> str:
        """
        Assemble all active context into a single string for the prompt.

        Args:
            max_tokens: Maximum tokens for assembled context.
            sort_by: Sorting strategy ('priority', 'relevance', 'age').
            include_types: Only include these context types.
            exclude_types: Exclude these context types.

        Returns:
            Assembled context string.
        """
        # Expire stale blocks first
        self.expire_stale()

        with self._lock:
            blocks = list(self._blocks.values())

        # Filter
        if include_types:
            blocks = [b for b in blocks if b.type in include_types]
        if exclude_types:
            blocks = [b for b in blocks if b.type not in exclude_types]

        # Sort
        blocks = self._sort_blocks(blocks, sort_by)

        # Assemble with token budget
        limit = max_tokens or (self.window.max_tokens - self.window.reserved_tokens)
        return self._assemble_with_budget(blocks, limit)

    def assemble_by_type(self) -> Dict[ContextType, str]:
        """Assemble context grouped by type."""
        result = {}
        for ctx_type in ContextType:
            blocks = self.get_by_type(ctx_type)
            if blocks:
                result[ctx_type] = "\n".join(b.content for b in blocks)
        return result

    # ------------------------------------------------------------------
    # Token Management
    # ------------------------------------------------------------------

    @property
    def total_tokens(self) -> int:
        """Total estimated tokens in current context."""
        with self._lock:
            return self._compute_total_tokens()

    def is_over_limit(self) -> bool:
        """Check if context exceeds the token window."""
        available = self.window.max_tokens - self.window.reserved_tokens
        return self.total_tokens > available

    def token_usage_report(self) -> Dict[str, Any]:
        """Generate a token usage report by context type."""
        with self._lock:
            report: Dict[str, Dict[str, Any]] = {}
            for block in self._blocks.values():
                if block.is_expired:
                    continue
                ct = block.type.value
                if ct not in report:
                    report[ct] = {"blocks": 0, "tokens": 0, "priority": block.priority.value}
                report[ct]["blocks"] += 1
                report[ct]["tokens"] += block.estimated_tokens
                report[ct]["priority"] = max(report[ct]["priority"], block.priority.value)

            return {
                "total_tokens": self.total_tokens,
                "max_tokens": self.window.max_tokens,
                "reserved_tokens": self.window.reserved_tokens,
                "available": self.window.max_tokens - self.window.reserved_tokens - self.total_tokens,
                "usage_pct": round(self.total_tokens / max(1, self.window.max_tokens) * 100, 1),
                "by_type": report,
            }

    # ------------------------------------------------------------------
    # Snapshot & Restore
    # ------------------------------------------------------------------

    def snapshot(self) -> ContextSnapshot:
        """Create a point-in-time snapshot of current context."""
        with self._lock:
            blocks = [
                ContextBlock(
                    id=b.id,
                    type=b.type,
                    content=b.content,
                    priority=b.priority,
                    source=b.source,
                    created_at=b.created_at,
                    expires_at=b.expires_at,
                    ttl_seconds=b.ttl_seconds,
                    relevance_score=b.relevance_score,
                    is_immutable=b.is_immutable,
                    tags=list(b.tags),
                    metadata=dict(b.metadata),
                )
                for b in self._blocks.values()
                if not b.is_expired
            ]
            return ContextSnapshot(
                blocks=blocks,
                total_tokens=sum(b.estimated_tokens for b in blocks),
            )

    def restore(self, snapshot: ContextSnapshot) -> None:
        """Restore context from a snapshot."""
        with self._lock:
            self._blocks.clear()
            for block in snapshot.blocks:
                self._blocks[block.id] = block
            self.window.current_usage = self._compute_total_tokens()

    def diff(self, other_snapshot: ContextSnapshot) -> Dict[str, Any]:
        """Compute differences between current context and a snapshot."""
        current_ids = set(self._blocks.keys())
        snapshot_ids = {b.id for b in other_snapshot.blocks}

        return {
            "added": sorted(current_ids - snapshot_ids),
            "removed": sorted(snapshot_ids - current_ids),
            "unchanged": sorted(current_ids & snapshot_ids),
            "added_count": len(current_ids - snapshot_ids),
            "removed_count": len(snapshot_ids - current_ids),
        }

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    def deduplicate(self, similarity_threshold: float = 0.85) -> int:
        """
        Remove near-duplicate context blocks.

        Returns count of blocks removed.
        """
        with self._lock:
            blocks = list(self._blocks.items())
            to_remove = set()

            for i, (id_a, block_a) in enumerate(blocks):
                if id_a in to_remove or block_a.is_immutable:
                    continue
                for j, (id_b, block_b) in enumerate(blocks):
                    if j <= i or id_b in to_remove or block_b.is_immutable:
                        continue
                    if block_a.type == block_b.type:
                        similarity = self._text_similarity(block_a.content, block_b.content)
                        if similarity >= similarity_threshold:
                            # Remove the one with lower priority or later creation
                            if block_a.priority.value >= block_b.priority.value:
                                to_remove.add(id_b)
                            else:
                                to_remove.add(id_a)
                                break

            for bid in to_remove:
                del self._blocks[bid]

            self.window.current_usage = self._compute_total_tokens()
            return len(to_remove)

    # ------------------------------------------------------------------
    # Conflict Detection
    # ------------------------------------------------------------------

    def detect_conflicts(self) -> List[Dict[str, Any]]:
        """Detect conflicting context blocks."""
        conflicts = []
        with self._lock:
            blocks = list(self._blocks.values())
            for i, block_a in enumerate(blocks):
                for j, block_b in enumerate(blocks):
                    if j <= i:
                        continue
                    # Check for contradictory instructions
                    if block_a.type == ContextType.SYSTEM and block_b.type == ContextType.SYSTEM:
                        if self._detect_contradiction(block_a.content, block_b.content):
                            conflicts.append({
                                "block_a": block_a.id,
                                "block_b": block_b.id,
                                "type": "system_instruction_conflict",
                                "severity": "high",
                            })
        return conflicts

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Serialize context manager to dictionary."""
        with self._lock:
            return {
                "blocks": [b.to_dict() for b in self._blocks.values()],
                "window": {
                    "max_tokens": self.window.max_tokens,
                    "reserved_tokens": self.window.reserved_tokens,
                },
                "auto_eviction": self.enable_auto_eviction,
            }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextManager":
        """Deserialize from dictionary."""
        window_data = data.get("window", {})
        ctx = cls(
            max_tokens=window_data.get("max_tokens", 100_000),
            reserved_tokens=window_data.get("reserved_tokens", 4_000),
            enable_auto_eviction=data.get("auto_eviction", True),
        )
        with ctx._lock:
            for block_data in data.get("blocks", []):
                block = ContextBlock.from_dict(block_data)
                ctx._blocks[block.id] = block
            ctx.window.current_usage = ctx._compute_total_tokens()
        return ctx

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)

    @classmethod
    def from_json(cls, json_str: str) -> "ContextManager":
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_evict(self, callback: Callable[[ContextBlock], None]) -> None:
        """Register a callback for when blocks are evicted."""
        self._on_evict_callbacks.append(callback)

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _generate_id(self, type: ContextType) -> str:
        """Generate a unique block ID."""
        self._id_counter += 1
        ts = int(time.time() * 1000)
        return f"ctx_{type.value}_{ts}_{self._id_counter}"

    def _compute_total_tokens(self) -> int:
        """Compute total token usage."""
        return sum(
            b.estimated_tokens
            for b in self._blocks.values()
            if not b.is_expired
        )

    def _sort_blocks(
        self, blocks: List[ContextBlock], strategy: str
    ) -> List[ContextBlock]:
        """Sort context blocks by the given strategy."""
        if strategy == "priority":
            # Critical first, then by type importance
            type_order = {
                ContextType.SECURITY: 0,
                ContextType.COMPLIANCE: 1,
                ContextType.SYSTEM: 2,
                ContextType.TASK: 3,
                ContextType.PROJECT: 4,
                ContextType.STANDARDS: 5,
                ContextType.KNOWLEDGE: 6,
                ContextType.DOCUMENTATION: 7,
                ContextType.MEMORY: 8,
                ContextType.CONVERSATION: 9,
                ContextType.USER_PREFERENCES: 10,
                ContextType.TOOL_DEFINITIONS: 11,
                ContextType.CUSTOM: 12,
            }
            return sorted(
                blocks,
                key=lambda b: (
                    -b.priority.value,
                    type_order.get(b.type, 99),
                    -b.relevance_score,
                ),
            )
        elif strategy == "relevance":
            return sorted(blocks, key=lambda b: -b.relevance_score)
        elif strategy == "age":
            return sorted(blocks, key=lambda b: b.age_seconds)
        else:
            return blocks

    def _assemble_with_budget(
        self, blocks: List[ContextBlock], max_tokens: int
    ) -> str:
        """Assemble blocks up to the token budget."""
        sections: List[str] = []
        token_count = 0

        for block in blocks:
            block_tokens = block.estimated_tokens
            if token_count + block_tokens > max_tokens:
                if block.is_immutable:
                    # Immutable blocks must be included; truncate with warning
                    truncated = self._truncate_text(
                        block.content,
                        max_tokens - token_count,
                    )
                    sections.append(
                        f"[{block.type.value.upper()}] (TRUNCATED)\n{truncated}"
                    )
                    token_count = max_tokens
                else:
                    # Skip non-immutable blocks that don't fit
                    continue
            else:
                sections.append(
                    f"[{block.type.value.upper()}]\n{block.content}"
                )
                token_count += block_tokens

            if token_count >= max_tokens:
                break

        return "\n\n".join(sections)

    def _evict_to_fit(self) -> None:
        """Evict low-priority blocks to fit within token budget."""
        available = self.window.max_tokens - self.window.reserved_tokens
        if self.total_tokens <= available:
            return

        # Sort by priority (ascending), then relevance (ascending), then age (descending)
        evictable = sorted(
            [
                b for b in self._blocks.values()
                if not b.is_immutable and not b.is_expired
            ],
            key=lambda b: (b.priority.value, b.relevance_score, -b.age_seconds),
        )

        for block in evictable:
            if self.total_tokens <= available:
                break
            self._blocks.pop(block.id, None)
            for cb in self._on_evict_callbacks:
                try:
                    cb(block)
                except Exception:
                    pass

    @staticmethod
    def _truncate_text(text: str, max_tokens: int) -> str:
        """Truncate text to fit within a token budget."""
        if max_tokens <= 0:
            return ""
        max_chars = max_tokens * 4
        if len(text) <= max_chars:
            return text
        return text[:max_chars - 20] + "... [TRUNCATED]"

    @staticmethod
    def _text_similarity(a: str, b: str) -> float:
        """Compute Jaccard similarity between two texts."""
        words_a = set(a.lower().split())
        words_b = set(b.lower().split())
        if not words_a or not words_b:
            return 0.0
        intersection = words_a & words_b
        union = words_a | words_b
        return len(intersection) / len(union)

    @staticmethod
    def _detect_contradiction(text_a: str, text_b: str) -> bool:
        """Simple contradiction detection based on negation keywords."""
        negation_patterns = [
            ("must", "must not"),
            ("always", "never"),
            ("required", "prohibited"),
            ("allow", "deny"),
            ("include", "exclude"),
        ]
        a_lower = text_a.lower()
        b_lower = text_b.lower()
        for pos, neg in negation_patterns:
            if pos in a_lower and neg in b_lower:
                return True
            if neg in a_lower and pos in b_lower:
                return True
        return False

    def __len__(self) -> int:
        with self._lock:
            return len(self._blocks)

    def __contains__(self, block_id: str) -> bool:
        with self._lock:
            return block_id in self._blocks

    def __repr__(self) -> str:
        return (
            f"ContextManager(blocks={len(self)}, "
            f"tokens={self.total_tokens}/{self.window.max_tokens})"
        )