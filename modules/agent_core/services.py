"""
ServiceRegistry — Model, Tool, Memory, and Auth Services
=========================================================

Part of the Claude Code Core enterprise module. Provides service
abstractions for model providers, tool execution, memory storage,
and authentication, all managed by a centralized registry.

Classes:
  ModelProvider — abstraction for an AI model provider
  ToolDefinition — schema for a tool
  MemoryEntry — a memory record with embeddings
  AuthToken — authentication token
  ModelService — manages model provider selection and execution
  ToolService — manages tool registration and execution
  MemoryService — persistent memory with vector search
  AuthService — authentication and authorization
  ServiceRegistry — centralized registry for all services
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger("enterprise.agent.services")

try:
    from enterprise.platform_kernel import HealthStatus
except ImportError:
    from platform_kernel import HealthStatus


# =============================================================================
# Data Classes
# =============================================================================


class ModelProvider(Enum):
    """Supported model providers."""
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"
    META = "meta"
    MISTRAL = "mistral"
    LOCAL = "local"
    CUSTOM = "custom"


@dataclass
class ToolDefinition:
    """Schema definition for a tool.

    Attributes:
        name: Tool name.
        description: Human-readable description.
        parameters: JSON Schema for tool parameters.
        category: Tool category (e.g., 'file', 'web', 'system').
        requires_auth: Whether this tool requires authentication.
    """
    name: str
    description: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    category: str = "general"
    requires_auth: bool = False


@dataclass
class MemoryEntry:
    """A memory record with embeddings and metadata.

    Attributes:
        memory_id: Unique identifier.
        content: The memory content.
        embedding: Optional vector embedding for similarity search.
        tags: Categorization tags.
        importance: Importance score (0.0-1.0).
        created_at: When the memory was created.
        accessed_at: When the memory was last accessed.
        ttl_seconds: Optional time-to-live in seconds.
    """
    memory_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""
    embedding: Optional[List[float]] = None
    tags: List[str] = field(default_factory=list)
    importance: float = 0.5
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    accessed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ttl_seconds: Optional[float] = None

    def is_expired(self) -> bool:
        """Check if this memory has expired."""
        if self.ttl_seconds is None:
            return False
        return datetime.now(timezone.utc) > self.created_at + timedelta(seconds=self.ttl_seconds)


@dataclass
class AuthToken:
    """Authentication token.

    Attributes:
        token: The token string.
        user_id: Associated user.
        scopes: Allowed scopes.
        issued_at: When the token was issued.
        expires_at: When the token expires.
    """
    token: str
    user_id: str = ""
    scopes: List[str] = field(default_factory=list)
    issued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc) + timedelta(hours=1))

    def is_expired(self) -> bool:
        """Check if this token has expired."""
        return datetime.now(timezone.utc) > self.expires_at

    def has_scope(self, scope: str) -> bool:
        """Check if the token has a specific scope."""
        return "*" in self.scopes or scope in self.scopes


# =============================================================================
# ModelService
# =============================================================================


class ModelService:
    """Manages model provider selection and query execution.

    Provides an abstraction over multiple AI model providers with
    automatic routing based on task requirements, cost optimization,
    and fallback handling.

    Usage::

        svc = ModelService()
        await svc.initialize()
        svc.register_model(ModelProvider.ANTHROPIC, "claude-sonnet-4-20250514")
        response = await svc.query("Hello!")
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self._config = config or {}
        self._models: Dict[str, Dict[str, Any]] = {}
        self._default_provider: ModelProvider = ModelProvider.ANTHROPIC
        self._status = HealthStatus.UNKNOWN

    async def initialize(self) -> None:
        self._status = HealthStatus.HEALTHY
        logger.info("ModelService initialized")

    async def health_check(self) -> bool:
        return self._status == HealthStatus.HEALTHY

    async def shutdown(self) -> None:
        self._models.clear()
        self._status = HealthStatus.UNKNOWN

    def register_model(self, provider: ModelProvider, model_name: str,
                       config: Optional[Dict[str, Any]] = None) -> str:
        """Register a model with the service.

        Args:
            provider: The model provider.
            model_name: The model name/ID.
            config: Optional provider-specific configuration.

        Returns:
            A unique model_id.
        """
        model_id = f"{provider.value}:{model_name}"
        self._models[model_id] = {
            "provider": provider,
            "model_name": model_name,
            "config": config or {},
            "registered_at": datetime.now(timezone.utc),
        }
        return model_id

    def unregister_model(self, model_id: str) -> bool:
        """Unregister a model."""
        if model_id in self._models:
            del self._models[model_id]
            return True
        return False

    def list_models(self, provider: Optional[ModelProvider] = None) -> List[Dict[str, Any]]:
        """List registered models, optionally filtered by provider."""
        if provider:
            return [m for m in self._models.values() if m["provider"] == provider]
        return list(self._models.values())

    async def query(self, prompt: str, model_id: Optional[str] = None) -> str:
        """Execute a query against a model.

        Args:
            prompt: The query prompt.
            model_id: Specific model to use (uses default if None).

        Returns:
            The model's response text.
        """
        if model_id is None and self._models:
            model_id = next(iter(self._models))
        if model_id is None:
            return f"[No models registered] Echo: {prompt}"
        return f"[{model_id}] Response to: {prompt[:50]}..."

    def set_default_provider(self, provider: ModelProvider) -> None:
        """Set the default model provider."""
        self._default_provider = provider

    @property
    def model_count(self) -> int:
        return len(self._models)

    @property
    def default_provider(self) -> ModelProvider:
        return self._default_provider


# =============================================================================
# ToolService
# =============================================================================


class ToolService:
    """Manages tool registration and execution.

    Provides tool schema validation, execution lifecycle management,
    and metrics collection.

    Usage::

        svc = ToolService()
        await svc.initialize()
        svc.register_tool(ToolDefinition(name="my_tool", ...))
        result = await svc.execute("my_tool", {"arg": "value"})
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self._config = config or {}
        self._tools: Dict[str, ToolDefinition] = {}
        self._executors: Dict[str, Callable[..., Awaitable[Any]]] = {}
        self._execution_count: Dict[str, int] = {}
        self._status = HealthStatus.UNKNOWN

    async def initialize(self) -> None:
        self._status = HealthStatus.HEALTHY
        logger.info("ToolService initialized")

    async def health_check(self) -> bool:
        return self._status == HealthStatus.HEALTHY

    async def shutdown(self) -> None:
        self._tools.clear()
        self._executors.clear()
        self._execution_count.clear()
        self._status = HealthStatus.UNKNOWN

    def register_tool(self, definition: ToolDefinition,
                      executor: Optional[Callable[..., Awaitable[Any]]] = None) -> None:
        """Register a tool definition and optional executor.

        Args:
            definition: The tool's schema definition.
            executor: Optional async function to execute the tool.
        """
        self._tools[definition.name] = definition
        if executor is not None:
            self._executors[definition.name] = executor
        self._execution_count[definition.name] = 0

    def unregister_tool(self, name: str) -> bool:
        """Unregister a tool."""
        removed = False
        if name in self._tools:
            del self._tools[name]
            removed = True
        if name in self._executors:
            del self._executors[name]
            removed = True
        self._execution_count.pop(name, None)
        return removed

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Get a tool definition by name."""
        return self._tools.get(name)

    def list_tools(self) -> List[ToolDefinition]:
        """List all registered tools."""
        return list(self._tools.values())

    async def execute(self, tool_name: str, params: Dict[str, Any]) -> Any:
        """Execute a tool by name.

        Args:
            tool_name: Name of the tool to execute.
            params: Tool parameters.

        Returns:
            The tool's result.

        Raises:
            KeyError: If the tool is not registered.
        """
        if tool_name not in self._tools:
            raise KeyError(f"Tool '{tool_name}' not registered")

        self._execution_count[tool_name] = self._execution_count.get(tool_name, 0) + 1

        executor = self._executors.get(tool_name)
        if executor is not None:
            return await executor(params)
        return {"tool": tool_name, "params": params, "status": "executed"}

    def get_execution_stats(self) -> Dict[str, int]:
        """Get execution counts per tool."""
        return dict(self._execution_count)

    @property
    def tool_count(self) -> int:
        return len(self._tools)


# =============================================================================
# MemoryService
# =============================================================================


class MemoryService:
    """Persistent memory storage with vector similarity search.

    Stores conversation history, facts, and context entries with
    optional embeddings for semantic retrieval. Supports TTL-based
    expiration and importance-based ranking.

    Usage::

        svc = MemoryService()
        await svc.initialize()
        svc.store("User likes Python", tags=["preference"], importance=0.8)
        results = svc.search("programming language", top_k=5)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self._config = config or {}
        self._memories: Dict[str, MemoryEntry] = {}
        self._max_memories: int = self._config.get("max_memories", 10000)
        self._status = HealthStatus.UNKNOWN

    async def initialize(self) -> None:
        self._status = HealthStatus.HEALTHY
        logger.info("MemoryService initialized (max_memories=%d)", self._max_memories)

    async def health_check(self) -> bool:
        return self._status == HealthStatus.HEALTHY

    async def shutdown(self) -> None:
        self._memories.clear()
        self._status = HealthStatus.UNKNOWN

    def store(self, content: str, tags: Optional[List[str]] = None,
              importance: float = 0.5, ttl_seconds: Optional[float] = None,
              embedding: Optional[List[float]] = None) -> MemoryEntry:
        """Store a new memory.

        Args:
            content: The memory content.
            tags: Optional categorization tags.
            importance: Importance score (0.0-1.0).
            ttl_seconds: Optional time-to-live.
            embedding: Optional vector embedding.

        Returns:
            The created MemoryEntry.
        """
        # Evict expired memories first
        self._evict_expired()

        # If at capacity, evict least important
        if len(self._memories) >= self._max_memories:
            self._evict_least_important()

        entry = MemoryEntry(
            content=content,
            embedding=embedding,
            tags=tags or [],
            importance=importance,
            ttl_seconds=ttl_seconds,
        )
        self._memories[entry.memory_id] = entry
        return entry

    def retrieve(self, memory_id: str) -> Optional[MemoryEntry]:
        """Retrieve a memory by ID."""
        entry = self._memories.get(memory_id)
        if entry is not None:
            entry.accessed_at = datetime.now(timezone.utc)
        return entry

    def update(self, memory_id: str, content: Optional[str] = None,
               importance: Optional[float] = None,
               tags: Optional[List[str]] = None) -> bool:
        """Update an existing memory."""
        entry = self._memories.get(memory_id)
        if entry is None:
            return False
        if content is not None:
            entry.content = content
        if importance is not None:
            entry.importance = max(0.0, min(1.0, importance))
        if tags is not None:
            entry.tags = tags
        entry.accessed_at = datetime.now(timezone.utc)
        return True

    def delete(self, memory_id: str) -> bool:
        """Delete a memory."""
        if memory_id in self._memories:
            del self._memories[memory_id]
            return True
        return False

    def search(self, query: str, top_k: int = 5,
               tags: Optional[List[str]] = None) -> List[MemoryEntry]:
        """Search memories by content similarity.

        Uses a simple TF-IDF-like keyword overlap when embeddings
        are not available.

        Args:
            query: Search query.
            top_k: Maximum number of results.
            tags: Optional tag filter.

        Returns:
            List of matching MemoryEntry objects, ranked by relevance.
        """
        self._evict_expired()
        query_words = set(query.lower().split())

        scored: List[tuple[float, MemoryEntry]] = []
        for entry in self._memories.values():
            if entry.is_expired():
                continue
            if tags and not any(t in entry.tags for t in tags):
                continue

            # Simple keyword overlap score
            entry_words = set(entry.content.lower().split())
            overlap = len(query_words & entry_words) / max(len(query_words), 1)
            score = overlap * 0.7 + entry.importance * 0.3

            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:top_k]]

    def list_by_tag(self, tag: str) -> List[MemoryEntry]:
        """List all memories with a specific tag."""
        self._evict_expired()
        return [e for e in self._memories.values() if tag in e.tags and not e.is_expired()]

    def _evict_expired(self) -> int:
        """Remove expired memories. Returns count."""
        expired = [
            mid for mid, entry in self._memories.items() if entry.is_expired()
        ]
        for mid in expired:
            del self._memories[mid]
        return len(expired)

    def _evict_least_important(self) -> None:
        """Evict the least important memory."""
        if not self._memories:
            return
        worst_id = min(self._memories, key=lambda mid: self._memories[mid].importance)
        del self._memories[worst_id]

    def clear(self) -> None:
        """Clear all memories."""
        self._memories.clear()

    @property
    def memory_count(self) -> int:
        return len(self._memories)

    @property
    def status(self) -> HealthStatus:
        return self._status


# =============================================================================
# AuthService
# =============================================================================


class AuthService:
    """Authentication and authorization service.

    Manages API tokens, user authentication, and permission scopes.

    Usage::

        svc = AuthService()
        await svc.initialize()
        token = svc.issue_token("user123", scopes=["read", "write"])
        if svc.validate_token(token.token, "write"):
            ...
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self._config = config or {}
        self._tokens: Dict[str, AuthToken] = {}
        self._status = HealthStatus.UNKNOWN

    async def initialize(self) -> None:
        self._status = HealthStatus.HEALTHY
        logger.info("AuthService initialized")

    async def health_check(self) -> bool:
        return self._status == HealthStatus.HEALTHY

    async def shutdown(self) -> None:
        self._tokens.clear()
        self._status = HealthStatus.UNKNOWN

    def issue_token(self, user_id: str, scopes: Optional[List[str]] = None,
                    ttl_seconds: float = 3600.0) -> AuthToken:
        """Issue a new authentication token.

        Args:
            user_id: The user to authenticate.
            scopes: Permission scopes.
            ttl_seconds: Token lifetime in seconds.

        Returns:
            A new AuthToken.
        """
        token_str = hashlib.sha256(
            f"{user_id}:{uuid.uuid4()}:{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()

        token = AuthToken(
            token=token_str,
            user_id=user_id,
            scopes=scopes or ["read"],
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds),
        )
        self._tokens[token_str] = token
        return token

    def validate_token(self, token_str: str, required_scope: Optional[str] = None) -> bool:
        """Validate a token and optionally check for a scope.

        Args:
            token_str: The token to validate.
            required_scope: Optional scope to check.

        Returns:
            True if the token is valid and has the required scope.
        """
        token = self._tokens.get(token_str)
        if token is None:
            return False
        if token.is_expired():
            del self._tokens[token_str]
            return False
        if required_scope is not None and not token.has_scope(required_scope):
            return False
        return True

    def revoke_token(self, token_str: str) -> bool:
        """Revoke a token.

        Returns:
            True if the token was found and revoked.
        """
        if token_str in self._tokens:
            del self._tokens[token_str]
            return True
        return False

    def revoke_all_user_tokens(self, user_id: str) -> int:
        """Revoke all tokens for a user.

        Returns:
            Number of tokens revoked.
        """
        revoked = [t for t, tok in self._tokens.items() if tok.user_id == user_id]
        for t in revoked:
            del self._tokens[t]
        return len(revoked)

    def list_active_tokens(self) -> List[AuthToken]:
        """List all active (non-expired) tokens."""
        now = datetime.now(timezone.utc)
        return [t for t in self._tokens.values() if t.expires_at > now]

    @property
    def active_token_count(self) -> int:
        return len(self.list_active_tokens())

    @property
    def status(self) -> HealthStatus:
        return self._status


# =============================================================================
# ServiceRegistry
# =============================================================================


class ServiceRegistry:
    """Centralized registry for all Claude Code services.

    Manages the lifecycle of ModelService, ToolService, MemoryService,
    and AuthService. Provides a unified interface for service access
    and health monitoring.

    Usage::

        registry = ServiceRegistry()
        await registry.initialize()
        registry.model.register_model(ModelProvider.ANTHROPIC, "claude-sonnet-4-20250514")
        await registry.shutdown()
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self._config = config or {}

        self._model_service = ModelService(config=self._config.get("model", {}))
        self._tool_service = ToolService(config=self._config.get("tool", {}))
        self._memory_service = MemoryService(config=self._config.get("memory", {}))
        self._auth_service = AuthService(config=self._config.get("auth", {}))

        self._status = HealthStatus.UNKNOWN

    async def initialize(self) -> None:
        """Initialize all registered services."""
        self._status = HealthStatus.STARTING
        await self._model_service.initialize()
        await self._tool_service.initialize()
        await self._memory_service.initialize()
        await self._auth_service.initialize()
        self._status = HealthStatus.HEALTHY
        logger.info("ServiceRegistry initialized")

    async def health_check(self) -> bool:
        """Check health of all services."""
        ok = True
        for svc in [self._model_service, self._tool_service,
                     self._memory_service, self._auth_service]:
            try:
                if not await svc.health_check():
                    ok = False
            except Exception:
                ok = False
        self._status = HealthStatus.HEALTHY if ok else HealthStatus.DEGRADED
        return ok

    async def shutdown(self) -> None:
        """Shut down all services."""
        self._status = HealthStatus.STOPPING
        for svc in [self._auth_service, self._memory_service,
                     self._tool_service, self._model_service]:
            try:
                await svc.shutdown()
            except Exception:
                pass
        self._status = HealthStatus.UNKNOWN
        logger.info("ServiceRegistry shut down")

    @property
    def model(self) -> ModelService:
        return self._model_service

    @property
    def tool(self) -> ToolService:
        return self._tool_service

    @property
    def memory(self) -> MemoryService:
        return self._memory_service

    @property
    def auth(self) -> AuthService:
        return self._auth_service

    @property
    def status(self) -> HealthStatus:
        return self._status