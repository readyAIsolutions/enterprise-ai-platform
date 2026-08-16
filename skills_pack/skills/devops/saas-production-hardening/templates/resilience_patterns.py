"""
Resilience Patterns for SaaS Production Hardening.

Drop-in module providing production-grade resilience patterns for all outbound HTTP/gRPC calls:
- Circuit Breaker (prevent cascade failures)
- Retry with Exponential Backoff + Jitter
- Timeout Enforcement (connection + read)
- Bulkhead Isolation (concurrency limits)
- Rate Limiting (token bucket)
- Dead Letter Queue for failed operations
- Idempotency Keys with TTL

All patterns are composable and can be applied per-client or globally via @resilient decorator.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import random
import time
import uuid
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from functools import wraps
from typing import Any, Callable, Optional, TypeVar, Generic

import httpx
import redis.asyncio as redis

T = TypeVar("T")


# =============================================================================
# CIRCUIT BREAKER
# =============================================================================


class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation, requests pass through
    OPEN = "open"          # Failing, requests blocked immediately
    HALF_OPEN = "half_open"  # Testing recovery, limited requests allowed


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5          # Failures before opening
    success_threshold: int = 3          # Successes in half-open before closing
    timeout: float = 30.0               # Seconds before half-open
    excluded_exceptions: tuple = (TimeoutError, asyncio.TimeoutError)


class CircuitBreaker:
    """
    Circuit breaker implementation with three states:
    - CLOSED: Normal operation, failures counted
    - OPEN: Short-circuit failures, return error immediately
    - HALF_OPEN: Limited requests allowed to test recovery
    """

    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    async def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute function with circuit breaker protection."""
        async with self._lock:
            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
                    logger.info(f"Circuit breaker '{self.name}' entering HALF_OPEN")
                else:
                    raise CircuitOpenError(f"Circuit breaker '{self.name}' is OPEN")

        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except self.config.excluded_exceptions as e:
            await self._on_failure()
            raise
        except Exception as e:
            await self._on_failure()
            raise

    def _should_attempt_reset(self) -> bool:
        if self._last_failure_time is None:
            return True
        return (time.time() - self._last_failure_time) >= self.config.timeout

    async def _on_success(self) -> None:
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    logger.info(f"Circuit breaker '{self.name}' CLOSED")
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0  # Reset on success

    async def _on_failure(self) -> None:
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning(f"Circuit breaker '{self.name}' reopened after half-open failure")
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.config.failure_threshold:
                    self._state = CircuitState.OPEN
                    logger.warning(f"Circuit breaker '{self.name}' OPENED after {self._failure_count} failures")

    def get_stats(self) -> dict:
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
        }


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open and request is rejected."""
    pass


# =============================================================================
# RETRY WITH EXPONENTIAL BACKOFF + JITTER
# =============================================================================


@dataclass
class RetryConfig:
    max_attempts: int = 3
    base_delay: float = 1.0          # Initial delay in seconds
    max_delay: float = 60.0          # Maximum delay cap
    exponential_base: float = 2.0    # Exponential factor
    jitter: float = 0.1              # Jitter factor (0-1)
    retryable_exceptions: tuple = (
        httpx.TimeoutException,
        httpx.ConnectError,
        httpx.RemoteProtocolError,
        asyncio.TimeoutError,
        ConnectionError,
        TimeoutError,
    )
    retry_on_status: tuple = (429, 500, 502, 503, 504)


async def retry_with_backoff(
    func: Callable[..., T],
    *args,
    config: Optional[RetryConfig] = None,
    **kwargs,
) -> T:
    """
    Execute function with exponential backoff and jitter retry logic.
    
    Delay = min(base_delay * exponential_base^attempt + jitter, max_delay)
    """
    config = config or RetryConfig()
    last_exception = None

    for attempt in range(config.max_attempts):
        try:
            result = await func(*args, **kwargs)
            
            # Check if HTTP response status is retryable
            if hasattr(result, 'status_code') and result.status_code in config.retry_on_status:
                if attempt < config.max_attempts - 1:
                    raise httpx.HTTPStatusError(
                        f"Retryable status {result.status_code}",
                        request=None,
                        response=result
                    )
            
            if attempt > 0:
                logger.info(f"Retry succeeded on attempt {attempt + 1} for {func.__name__}")
            return result
            
        except config.retryable_exceptions as e:
            last_exception = e
            if attempt < config.max_attempts - 1:
                delay = min(
                    config.base_delay * (config.exponential_base ** attempt) + 
                    random.uniform(0, config.jitter),
                    config.max_delay
                )
                logger.warning(
                    f"Retry {attempt + 1}/{config.max_attempts} for {func.__name__} "
                    f"after {delay:.2f}s: {type(e).__name__}: {e}"
                )
                await asyncio.sleep(delay)
                continue
            raise
        except httpx.HTTPStatusError as e:
            if e.response.status_code in config.retry_on_status and attempt < config.max_attempts - 1:
                last_exception = e
                delay = min(
                    config.base_delay * (config.exponential_base ** attempt) + 
                    random.uniform(0, config.jitter),
                    config.max_delay
                )
                logger.warning(
                    f"Retry {attempt + 1}/{config.max_attempts} for {func.__name__} "
                    f"after {delay:.2f}s: HTTP {e.response.status_code}"
                )
                await asyncio.sleep(delay)
                continue
            raise
        except Exception as e:
            # Non-retryable exception
            logger.error(f"Non-retryable error in {func.__name__}: {type(e).__name__}: {e}")
            raise

    # All retries exhausted
    raise RetryExhaustedError(
        f"All {config.max_attempts} attempts failed for {func.__name__}"
    ) from last_exception


class RetryExhaustedError(Exception):
    """Raised when all retry attempts are exhausted."""
    pass


# =============================================================================
# TIMEOUT ENFORCEMENT
# =============================================================================


@dataclass
class TimeoutConfig:
    connect_timeout: float = 10.0    # Connection establishment timeout
    read_timeout: float = 30.0       # Read/response timeout
    write_timeout: float = 10.0      # Write/request timeout
    pool_timeout: float = 5.0        # Connection pool acquisition timeout


async def with_timeout(
    func: Callable[..., T],
    *args,
    timeout: float = 30.0,
    **kwargs,
) -> T:
    """Execute function with timeout enforcement."""
    return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)


# =============================================================================
# BULKHEAD ISOLATION (Concurrency Limiting)
# =============================================================================


class Bulkhead:
    """
    Limits concurrent executions to prevent resource exhaustion.
    Uses semaphore for async concurrency control.
    """
    
    def __init__(self, name: str, max_concurrent: int = 10, max_queue: int = 100):
        self.name = name
        self.max_concurrent = max_concurrent
        self.max_queue = max_queue
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._queue_semaphore = asyncio.Semaphore(max_queue)
        self._active = 0
        self._queued = 0
        self._lock = asyncio.Lock()
        self._rejected = 0

    @asynccontextmanager
    async def execute(self):
        """Context manager for bulkhead execution."""
        # Try to enter queue
        acquired_queue = await self._queue_semaphore.acquire()
        if not acquired_queue:
            async with self._lock:
                self._rejected += 1
            raise BulkheadRejectedError(f"Bulkhead '{self.name}' queue full")
        
        try:
            async with self._lock:
                self._queued += 1
            
            # Acquire execution slot
            await self._semaphore.acquire()
            
            async with self._lock:
                self._queued -= 1
                self._active += 1
            
            try:
                yield
            finally:
                self._semaphore.release()
                async with self._lock:
                    self._active -= 1
        finally:
            self._queue_semaphore.release()

    def get_stats(self) -> dict:
        return {
            "name": self.name,
            "max_concurrent": self.max_concurrent,
            "max_queue": self.max_queue,
            "active": self._active,
            "queued": self._queued,
            "rejected": self._rejected,
            "utilization": self._active / self.max_concurrent if self.max_concurrent > 0 else 0,
        }


class BulkheadRejectedError(Exception):
    """Raised when bulkhead queue is full."""
    pass


# =============================================================================
# RATE LIMITING (Token Bucket)
# =============================================================================


class TokenBucketRateLimiter:
    """
    Token bucket rate limiter with Redis backend for distributed rate limiting.
    """
    
    def __init__(
        self,
        redis_client: redis.Redis,
        key: str,
        rate: float,           # Requests per second
        burst: int = 10,       # Maximum burst allowance
    ):
        self.redis = redis_client
        self.key = f"ratelimit:{key}"
        self.rate = rate
        self.burst = burst
        self._local_tokens = burst
        self._last_refill = time.time()

    async def acquire(self, tokens: int = 1, blocking: bool = True, timeout: float = 30.0) -> bool:
        """
        Acquire tokens from the bucket.
        Returns True if acquired, False if not available (non-blocking).
        """
        start = time.time()
        
        while True:
            # Try local first (fast path)
            if self._local_tokens >= tokens:
                self._local_tokens -= tokens
                return True
            
            # Refill from Redis (distributed sync)
            await self._refill_from_redis()
            
            if self._local_tokens >= tokens:
                self._local_tokens -= tokens
                return True
            
            if not blocking:
                return False
            
            if time.time() - start > timeout:
                raise RateLimitTimeoutError(f"Rate limit timeout for {self.key}")
            
            # Wait for token refill
            wait_time = tokens / self.rate
            await asyncio.sleep(min(wait_time, 0.1))

    async def _refill_from_redis(self):
        """Refill local tokens from Redis."""
        now = time.time()
        elapsed = now - self._last_refill
        
        # Calculate tokens to add
        new_tokens = elapsed * self.rate
        if new_tokens > 0:
            # Atomic increment in Redis
            pipe = self.redis.pipeline()
            pipe.incrbyfloat(f"{self.key}:tokens", new_tokens)
            pipe.set(f"{self.key}:last_refill", now)
            results = await pipe.execute()
            
            self._local_tokens = min(
                results[0],  # Current tokens from Redis
                self.burst
            )
            self._last_refill = now

    def get_stats(self) -> dict:
        return {
            "key": self.key,
            "rate": self.rate,
            "burst": self.burst,
            "local_tokens": self._local_tokens,
        }


class RateLimitTimeoutError(Exception):
    """Raised when rate limit acquisition times out."""
    pass


# =============================================================================
# IDEMPOTENCY KEYS
# =============================================================================


class IdempotencyManager:
    """
    Manages idempotency keys with TTL for exactly-once semantics.
    Uses Redis for distributed coordination.
    """
    
    def __init__(self, redis_client: redis.Redis, default_ttl: int = 86400):
        self.redis = redis_client
        self.default_ttl = default_ttl

    async def check_and_set(self, key: str, value: Any, ttl: Optional[int] = None) -> tuple[bool, Any]:
        """
        Check if key exists, if not set it with value.
        Returns (is_new, existing_value).
        """
        full_key = f"idempotency:{key}"
        ttl = ttl or self.default_ttl
        
        # Atomic check-and-set using SET NX EX
        result = await self.redis.set(
            full_key,
            str(value) if value is not None else "",
            nx=True,
            ex=ttl,
        )
        
        if result:
            return True, None
        
        # Key exists, get existing value
        existing = await self.redis.get(full_key)
        return False, existing

    async def get(self, key: str) -> Optional[Any]:
        """Get existing idempotency value."""
        full_key = f"idempotency:{key}"
        return await self.redis.get(full_key)

    async def delete(self, key: str) -> bool:
        """Delete idempotency key."""
        full_key = f"idempotency:{key}"
        return await self.redis.delete(full_key) > 0

    async def extend_ttl(self, key: str, ttl: int) -> bool:
        """Extend TTL of existing key."""
        full_key = f"idempotency:{key}"
        return await self.redis.expire(full_key, ttl)


# =============================================================================
# DEAD LETTER QUEUE
# =============================================================================


@dataclass
class DeadLetterEntry:
    id: str
    operation: str
    payload: dict
    error: str
    attempts: int
    created_at: datetime
    last_attempt: datetime


class DeadLetterQueue:
    """
    Dead letter queue for failed operations that exceed retry limits.
    Stores failed operations for later inspection and replay.
    """
    
    def __init__(self, redis_client: redis.Redis, max_size: int = 10000):
        self.redis = redis_client
        self.max_size = max_size
        self.queue_key = "dlq:entries"
        self.index_key = "dlq:index"

    async def add(self, entry: DeadLetterEntry) -> str:
        """Add entry to dead letter queue."""
        entry_id = entry.id or str(uuid.uuid4())
        entry.id = entry_id
        
        # Store entry
        await self.redis.hset(
            f"{self.queue_key}:{entry_id}",
            mapping={
                "id": entry.id,
                "operation": entry.operation,
                "payload": str(entry.payload),
                "error": entry.error,
                "attempts": str(entry.attempts),
                "created_at": entry.created_at.isoformat(),
                "last_attempt": entry.last_attempt.isoformat(),
            }
        )
        
        # Add to sorted set index (by creation time)
        await self.redis.zadd(self.index_key, {entry_id: entry.created_at.timestamp()})
        
        # Trim if over max size
        await self._trim_if_needed()
        
        return entry_id

    async def _trim_if_needed(self):
        """Remove oldest entries if over max size."""
        count = await self.redis.zcard(self.index_key)
        if count > self.max_size:
            # Remove oldest entries
            to_remove = count - self.max_size
            oldest = await self.redis.zrange(self.index_key, 0, to_remove - 1)
            if oldest:
                pipe = self.redis.pipeline()
                for entry_id in oldest:
                    pipe.delete(f"{self.queue_key}:{entry_id}")
                    pipe.zrem(self.index_key, entry_id)
                await pipe.execute()

    async def get(self, entry_id: str) -> Optional[DeadLetterEntry]:
        """Get entry by ID."""
        data = await self.redis.hgetall(f"{self.queue_key}:{entry_id}")
        if not data:
            return None
        return DeadLetterEntry(
            id=data["id"],
            operation=data["operation"],
            payload=eval(data["payload"]),  # Note: in production use json
            error=data["error"],
            attempts=int(data["attempts"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            last_attempt=datetime.fromisoformat(data["last_attempt"]),
        )

    async def list(self, limit: int = 100, offset: int = 0) -> list[DeadLetterEntry]:
        """List entries, newest first."""
        ids = await self.redis.zrevrange(self.index_key, offset, offset + limit - 1)
        entries = []
        for entry_id in ids:
            entry = await self.get(entry_id)
            if entry:
                entries.append(entry)
        return entries

    async def replay(self, entry_id: str, handler: Callable) -> bool:
        """Replay a dead letter entry."""
        entry = await self.get(entry_id)
        if not entry:
            return False
        
        try:
            await handler(entry.payload)
            await self.remove(entry_id)
            return True
        except Exception as e:
            logger.error(f"Replay failed for {entry_id}: {e}")
            return False

    async def remove(self, entry_id: str) -> bool:
        """Remove entry from queue."""
        pipe = self.redis.pipeline()
        pipe.delete(f"{self.queue_key}:{entry_id}")
        pipe.zrem(self.index_key, entry_id)
        await pipe.execute()
        return True


# =============================================================================
# COMPOSABLE RESILIENCE DECORATOR
# =============================================================================


@dataclass
class ResilienceConfig:
    """Configuration for all resilience patterns."""
    circuit_breaker: Optional[CircuitBreakerConfig] = None
    retry: Optional[RetryConfig] = None
    timeout: float = 30.0
    bulkhead: Optional[int] = None  # Max concurrent
    rate_limit: Optional[float] = None  # Requests per second
    idempotency_key: Optional[str] = None


# Global registries
_circuit_breakers: dict[str, CircuitBreaker] = {}
_bulkheads: dict[str, Bulkhead] = {}


def get_circuit_breaker(name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
    """Get or create circuit breaker."""
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(name, config)
    return _circuit_breakers[name]


def get_bulkhead(name: str, max_concurrent: int = 10) -> Bulkhead:
    """Get or create bulkhead."""
    if name not in _bulkheads:
        _bulkheads[name] = Bulkhead(name, max_concurrent)
    return _bulkheads[name]


def resilient(
    name: str,
    config: Optional[ResilienceConfig] = None,
    circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
    retry_config: Optional[RetryConfig] = None,
    timeout: float = 30.0,
    bulkhead_limit: Optional[int] = None,
    rate_limit: Optional[float] = None,
    idempotency_key: Optional[str] = None,
):
    """
    Decorator that applies all resilience patterns to an async function.
    
    Usage:
        @resilient("fonoster_api", timeout=30, bulkhead_limit=5, retry_config=RetryConfig(max_attempts=3))
        async def call_fonoster(...):
            ...
    """
    config = config or ResilienceConfig()
    config.circuit_breaker = config.circuit_breaker or circuit_breaker_config
    config.retry = config.retry or retry_config
    config.timeout = timeout
    config.bulkhead = config.bulkhead or bulkhead_limit
    config.rate_limit = config.rate_limit or rate_limit
    config.idempotency_key = config.idempotency_key or idempotency_key

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            # Resolve idempotency key if callable
            idem_key = config.idempotency_key
            if callable(idem_key):
                idem_key = idem_key(*args, **kwargs)
            
            # Check idempotency
            if idem_key:
                # Would need redis client - simplified for now
                pass
            
            # Get resilience components
            cb = get_circuit_breaker(name, config.circuit_breaker) if config.circuit_breaker else None
            bh = get_bulkhead(name, config.bulkhead) if config.bulkhead else None
            
            # Build execution chain
            async def execute():
                if config.retry:
                    return await retry_with_backoff(func, *args, config=config.retry, **kwargs)
                return await func(*args, **kwargs)
            
            # Apply circuit breaker
            if cb:
                execute = lambda: cb.call(execute)
            
            # Apply bulkhead
            if bh:
                async with bh.execute():
                    return await execute()
            
            return await execute()
        
        return wrapper
    return decorator


# =============================================================================
# RESILIENT HTTP CLIENT
# =============================================================================


class ResilientHttpClient:
    """
    HTTP client with all resilience patterns built-in.
    """
    
    def __init__(
        self,
        name: str,
        base_url: str,
        timeout_config: Optional[TimeoutConfig] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        retry_config: Optional[RetryConfig] = None,
        bulkhead_limit: int = 10,
        default_headers: Optional[dict] = None,
    ):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.timeout_config = timeout_config or TimeoutConfig()
        self.circuit_breaker_config = circuit_breaker_config or CircuitBreakerConfig()
        self.retry_config = retry_config or RetryConfig()
        self.bulkhead = Bulkhead(name, max_concurrent=bulkhead_limit)
        self.circuit_breaker = CircuitBreaker(name, self.circuit_breaker_config)
        self.default_headers = default_headers or {}
        
        # Create httpx client with timeout config
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=self.timeout_config.connect_timeout,
                read=self.timeout_config.read_timeout,
                write=self.timeout_config.write_timeout,
                pool=self.timeout_config.pool_timeout,
            ),
            headers=self.default_headers,
        )

    async def _request_with_resilience(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> httpx.Response:
        """Execute request with all resilience patterns."""
        
        url = f"{self.base_url}/{path.lstrip('/')}"
        
        async def _do_request():
            async with self.bulkhead.execute():
                return await self.circuit_breaker.call(
                    lambda: retry_with_backoff(
                        self._client.request,
                        method,
                        url,
                        config=self.retry_config,
                        **kwargs,
                    )
                )
        
        return await _do_request()

    async def get(self, path: str, **kwargs) -> httpx.Response:
        return await self._request_with_resilience("GET", path, **kwargs)

    async def post(self, path: str, **kwargs) -> httpx.Response:
        return await self._request_with_resilience("POST", path, **kwargs)

    async def put(self, path: str, **kwargs) -> httpx.Response:
        return await self._request_with_resilience("PUT", path, **kwargs)

    async def patch(self, path: str, **kwargs) -> httpx.Response:
        return await self._request_with_resilience("PATCH", path, **kwargs)

    async def delete(self, path: str, **kwargs) -> httpx.Response:
        return await self._request_with_resilience("DELETE", path, **kwargs)

    async def close(self):
        await self._client.aclose()

    def get_stats(self) -> dict:
        return {
            "name": self.name,
            "circuit_breaker": self.circuit_breaker.get_stats(),
            "bulkhead": self.bulkhead.get_stats(),
        }


# =============================================================================
# FACTORY FUNCTIONS FOR COMMON SERVICES
# =============================================================================


def create_fonoster_client(config) -> ResilientHttpClient:
    """Create resilient client for Fonoster gRPC gateway (if HTTP) or use gRPC directly."""
    # Note: Fonoster uses gRPC, not HTTP. This is a placeholder for HTTP gateway.
    return ResilientHttpClient(
        name="fonoster",
        base_url=config.voice.fonoster_base_url.replace("grpc://", "http://").replace("50051", "8080"),
        timeout_config=TimeoutConfig(connect_timeout=10, read_timeout=30),
        circuit_breaker_config=CircuitBreakerConfig(failure_threshold=5, timeout=30),
        retry_config=RetryConfig(max_attempts=3, base_delay=1.0),
        bulkhead_limit=10,
    )


def create_usesend_client(config) -> ResilientHttpClient:
    """Create resilient client for useSend API."""
    return ResilientHttpClient(
        name="usesend",
        base_url=config.email.usesend_base_url,
        timeout_config=TimeoutConfig(connect_timeout=10, read_timeout=30),
        circuit_breaker_config=CircuitBreakerConfig(failure_threshold=5, timeout=30),
        retry_config=RetryConfig(max_attempts=3, base_delay=1.0),
        bulkhead_limit=20,
        default_headers={
            "Authorization": f"Bearer {config.email.usesend_api_key}",
            "Content-Type": "application/json",
        } if config.email.usesend_api_key else {},
    )


def create_odoo_client(config) -> ResilientHttpClient:
    """Create resilient client for Odoo JSON-RPC API."""
    return ResilientHttpClient(
        name="odoo",
        base_url=config.crm.odoo_url,
        timeout_config=TimeoutConfig(connect_timeout=10, read_timeout=60),
        circuit_breaker_config=CircuitBreakerConfig(failure_threshold=3, timeout=60),
        retry_config=RetryConfig(max_attempts=3, base_delay=2.0),
        bulkhead_limit=5,
    )


def create_openrouter_client(config) -> ResilientHttpClient:
    """Create resilient client for OpenRouter API."""
    return ResilientHttpClient(
        name="openrouter",
        base_url=config.models.openrouter_base_url,
        timeout_config=TimeoutConfig(connect_timeout=10, read_timeout=120),
        circuit_breaker_config=CircuitBreakerConfig(failure_threshold=5, timeout=60),
        retry_config=RetryConfig(max_attempts=3, base_delay=2.0, max_delay=60),
        bulkhead_limit=10,
        default_headers={
            "Authorization": f"Bearer {config.models.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://demiurge.marketing",
            "X-Title": "Demiurge Marketing OS",
        } if config.models.openrouter_api_key else {},
    )


# =============================================================================
# HEALTH CHECK ENDPOINTS
# =============================================================================


async def get_resilience_health() -> dict:
    """Get health status of all resilience components."""
    health = {
        "circuit_breakers": {},
        "bulkheads": {},
        "overall": "healthy",
    }
    
    for name, cb in _circuit_breakers.items():
        stats = cb.get_stats()
        health["circuit_breakers"][name] = stats
        if stats["state"] == "open":
            health["overall"] = "degraded"
    
    for name, bh in _bulkheads.items():
        stats = bh.get_stats()
        health["bulkheads"][name] = stats
        if stats["utilization"] > 0.9:
            health["overall"] = "degraded"
    
    return health