"""ENI Model Router OS Module — an enterprise model-routing / fallback gateway.

A production-grade, stdlib-only model-routing gateway inspired by the LiteLLM
retry / cooldown pattern. It manages a fleet of *deployments* (upstream model
endpoints), selects healthy ones for each request via weighted (hash-bucket)
selection, retries transient failures per a per-exception-type policy, and
falls back across the model group when a deployment exhausts its allowed
failures — placing the failing deployment into a time-based cooldown so it is
excluded from dispatch until it recovers.

Concepts
--------
DeploymentModel : one upstream model endpoint (provider, base_url, api_key env,
    weight, allowed_fails, cooldown_time, max_fallbacks, retry_policy).

CooldownCache   : the LiteLLM-style state machine. Tracks consecutive failed
    calls per deployment; when ``fails >= allowed_fails`` the deployment is put
    in a cooldown (excluded from dispatch) until ``cooldown_time`` elapses.

BaseProviderAdapter : pluggable transport. ``HTTPAdapter`` calls an
    OpenAI-compatible ``/chat/completions`` endpoint via ``urllib.request``;
    ``EchoAdapter`` / ``NoopAdapter`` are deterministic, offline stubs used for
    tests and simulated fault injection.

Router / ModelRouter : dispatch + fallback machine + ergonomic facade.

All components are stdlib-only (zero external dependencies).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import socket
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from enterprise.platform_kernel import EventBus, HealthStatus, Module, module

logger = logging.getLogger("enterprise.model_router")


# =============================================================================
# Domain exceptions (retry-policy keyed by their __name__)
# =============================================================================


class ProviderError(Exception):
    """Base class for all provider/transport failures surfaced by adapters."""


class RateLimitError(ProviderError):
    """Upstream returned 429 / rate-limited; safe to retry."""


class ProviderTimeoutError(TimeoutError, ProviderError):
    """Upstream timed out; safe to retry."""


class AuthenticationError(ProviderError):
    """Upstream rejected credentials (401/403); NOT retryable by default."""


class ServiceUnavailableError(ProviderError):
    """Upstream 5xx / unavailable; retryable by default."""


class NoDeploymentAvailableError(ProviderError):
    """No healthy (non-cooldowned, non-blacklisted) deployment is left."""


# =============================================================================
# Data models
# =============================================================================


@dataclass
class DeploymentModel:
    """A single upstream model deployment (endpoint + routing policy).

    Attributes:
        id: unique deployment identifier within this router.
        model: upstream model name sent in the request body.
        provider: provider label (e.g. ``"openrouter"``, ``"local"``, ``"echo"``).
        base_url: endpoint base URL (``/chat/completions`` is appended).
        api_key_env: name of the env var holding the API key (optional).
        weight: relative dispatch weight for weighted selection.
        allowed_fails: consecutive failures before the deployment is cooled down.
        cooldown_time: seconds the deployment stays in cooldown once triggered.
        max_fallbacks: group-level fallback cap this deployment contributes to.
        retry_policy: map of exception-type-name -> max retries on that deployment.
        group: model-group id this deployment belongs to (default "default").
        blacklisted: if True the deployment is never selected.
    """

    id: str
    model: str = ""
    provider: str = ""
    base_url: str = ""
    api_key_env: Optional[str] = None
    weight: int = 1
    allowed_fails: int = 3
    cooldown_time: float = 60.0
    max_fallbacks: int = 2
    retry_policy: Dict[str, int] = field(default_factory=dict)
    group: str = "default"
    blacklisted: bool = False

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DeploymentModel":
        known = {
            "id", "model", "provider", "base_url", "api_key_env", "weight",
            "allowed_fails", "cooldown_time", "max_fallbacks", "retry_policy",
            "group", "blacklisted",
        }
        kw = {k: v for k, v in d.items() if k in known}
        return cls(**kw)


@dataclass
class ProviderResponse:
    """Normalized result returned by a provider adapter."""

    content: Any = None
    status: str = "success"
    tokens: Dict[str, int] = field(default_factory=dict)


@dataclass
class RouteResult:
    """Result of routing one request through the model group."""

    messages: Any = None
    status: str = "error"  # "success" | "error"
    latency_ms: float = 0.0
    deployment_id: Optional[str] = None
    attempts: int = 0
    fallbacks_used: int = 0
    final_error: Optional[str] = None
    tokens: Optional[Dict[str, int]] = None


# =============================================================================
# CooldownCache — the LiteLLM retry/cooldown state machine
# =============================================================================


class CooldownCache:
    """Tracks consecutive failures and time-based cooldowns per deployment.

    LiteLLM-rip state machine:

    - Every failed call calls :meth:`record_failure` which increments the
      deployment's consecutive-failure counter.
    - When ``fails >= allowed_fails`` the deployment is placed in cooldown via
      :meth:`add_cooldown` and its failure counter is reset (fresh slate so it
      gets a fair chance after recovery).
    - While in cooldown, :meth:`is_deployment_cooldowned` returns True and the
      deployment is excluded from dispatch.
    - After ``cooldown_time`` elapses the deployment is eligible again.
    """

    def __init__(self, clock: Optional[Callable[[], float]] = None) -> None:
        self._now = clock or time.monotonic
        self._cooldowns: Dict[str, float] = {}   # deployment_id -> cooldown_until
        self._failed_calls: Dict[str, int] = {}  # deployment_id -> consecutive fails
        self._lock = threading.RLock()

    # -- failure accounting --------------------------------------------------

    def record_failure(
        self,
        deployment_id: str,
        allowed_fails: int = 3,
        cooldown_time: float = 60.0,
    ) -> bool:
        """Increment the fail counter; return True if it just entered cooldown."""
        with self._lock:
            self._failed_calls[deployment_id] = self._failed_calls.get(deployment_id, 0) + 1
            if self._failed_calls[deployment_id] >= allowed_fails:
                self.add_cooldown(deployment_id, cooldown_time)
                return True
            return False

    def reset_failures(self, deployment_id: str) -> None:
        """Clear the consecutive-failure counter (after a success)."""
        with self._lock:
            self._failed_calls.pop(deployment_id, None)

    def failure_count(self, deployment_id: str) -> int:
        with self._lock:
            return self._failed_calls.get(deployment_id, 0)

    # -- cooldown -------------------------------------------------------------

    def add_cooldown(self, deployment_id: str, cooldown_time: float) -> None:
        """Place a deployment in cooldown for ``cooldown_time`` seconds."""
        with self._lock:
            self._cooldowns[deployment_id] = self._now() + max(cooldown_time, 0.0)
            # Fresh slate: the deployment gets a fair chance once it recovers.
            self._failed_calls.pop(deployment_id, None)

    def is_deployment_cooldowned(self, deployment_id: str) -> bool:
        with self._lock:
            until = self._cooldowns.get(deployment_id)
            if until is None:
                return False
            if self._now() >= until:
                # Expired; lazily remove and treat as healthy.
                self._cooldowns.pop(deployment_id, None)
                return False
            return True

    def remove_cooldown(self, deployment_id: str) -> None:
        with self._lock:
            self._cooldowns.pop(deployment_id, None)

    def cooldown_remaining(self, deployment_id: str) -> float:
        with self._lock:
            until = self._cooldowns.get(deployment_id)
            if until is None:
                return 0.0
            rem = until - self._now()
            return rem if rem > 0 else 0.0

    def active_cooldowns(self) -> Dict[str, float]:
        """Return deployment_id -> remaining seconds for currently-active cooldowns."""
        return {
            rid: self.cooldown_remaining(rid)
            for rid in list(self._cooldowns)
            if self.is_deployment_cooldowned(rid)
        }


# =============================================================================
# Provider adapters
# =============================================================================


class BaseProviderAdapter:
    """Interface every transport must implement.

    ``call`` returns a :class:`ProviderResponse` or raises a :class:`ProviderError`
    subclass so the router can apply its retry/cooldown policy.
    """

    async def call(self, deployment: DeploymentModel, request: Any) -> ProviderResponse:
        raise NotImplementedError


class HTTPAdapter(BaseProviderAdapter):
    """Stdlib ``urllib.request`` transport for an OpenAI-compatible endpoint.

    POSTs ``{model, messages, **extra}`` to ``<base_url>/chat/completions``
    with an optional ``Authorization: Bearer`` header read from ``api_key_env``.
    """

    def __init__(
        self,
        timeout: float = 60.0,
        env: Optional[Dict[str, str]] = None,
    ) -> None:
        self.timeout = timeout
        self._env = env if env is not None else os.environ

    async def call(self, deployment: DeploymentModel, request: Any) -> ProviderResponse:
        url = deployment.base_url.rstrip("/") + "/chat/completions"
        payload = {"model": deployment.model, "messages": request}
        api_key = self._env.get(deployment.api_key_env) if deployment.api_key_env else None
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        if api_key:
            req.add_header("Authorization", f"Bearer {api_key}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            code = e.code
            if code == 429:
                raise RateLimitError(f"HTTP 429 rate-limited for {deployment.id}")
            if code in (401, 403):
                raise AuthenticationError(f"HTTP {code} auth for {deployment.id}")
            if 500 <= code <= 599:
                raise ServiceUnavailableError(f"HTTP {code} unavailable for {deployment.id}")
            raise ProviderError(f"HTTP {code} for {deployment.id}")
        except (urllib.error.URLError, TimeoutError, socket.timeout) as e:
            raise ProviderTimeoutError(f"timeout/runtime error for {deployment.id}: {e}")

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise ProviderError(f"malformed response from {deployment.id}")
        tokens = data.get("usage") or {}
        return ProviderResponse(content=content, status="success", tokens=tokens)


class EchoAdapter(BaseProviderAdapter):
    """Deterministic offline adapter for tests.

    Optionally takes a ``fail_map`` mapping ``deployment_id`` -> list of
    exception instances to raise in sequence (popped FIFO). Once the list is
    empty the deployment succeeds, letting tests drive retry / cooldown /
    fallback deterministically with zero network.
    """

    def __init__(self, fail_map: Optional[Dict[str, List[BaseException]]] = None) -> None:
        self.fail_map: Dict[str, List[BaseException]] = fail_map or {}
        self.calls = 0

    async def call(self, deployment: DeploymentModel, request: Any) -> ProviderResponse:
        self.calls += 1
        fails = self.fail_map.get(deployment.id)
        if fails:
            exc = fails.pop(0)
            raise exc
        last = request[-1]["content"] if request else ""
        content = f"echo[{deployment.model}]:{last}"
        return ProviderResponse(
            content=content,
            status="success",
            tokens={"prompt_tokens": len(str(request)), "completion_tokens": len(content)},
        )


class NoopAdapter(BaseProviderAdapter):
    """Pure no-op adapter: never fails, returns an empty canned response."""

    async def call(self, deployment: DeploymentModel, request: Any) -> ProviderResponse:
        return ProviderResponse(content="", status="success", tokens={})


# =============================================================================
# Router — dispatch + retry/fallback/cooldown machine
# =============================================================================


_DEFAULT_RETRY_POLICY: Dict[str, int] = {
    "RateLimitError": 1,
    "ProviderTimeoutError": 2,
    "TimeoutError": 2,
    "ServiceUnavailableError": 1,
}


class Router:
    """Core routing engine.

    Holds a fleet of deployments plus a cooldown cache, selects healthy
    deployments via weighted (hash-bucket) selection, runs each request through
    a provider adapter with per-exception-type retries, and falls back across
    the model group (capped by ``max_fallbacks``), cooling down deployments that
    exhaust their allowed failures.
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        adapter: Optional[BaseProviderAdapter] = None,
        adapter_map: Optional[Dict[str, BaseProviderAdapter]] = None,
        clock: Optional[Callable[[], float]] = None,
        rng: Optional[random.Random] = None,
    ) -> None:
        self._config = config or {}
        self._now = clock or time.monotonic
        self._rng = rng or random.Random()
        self.adapter: Optional[BaseProviderAdapter] = adapter
        self.adapter_map: Dict[str, BaseProviderAdapter] = dict(adapter_map or {})

        self.cooldown = CooldownCache(clock=self._now)
        self.deployments: Dict[str, DeploymentModel] = {}
        self._blacklist: set = set(self._config.get("blacklist", []))

        # Metrics
        self._success_counts: Dict[str, int] = {}
        self._fail_counts: Dict[str, int] = {}
        self._latency_sum: Dict[str, float] = {}
        self._latency_count: Dict[str, int] = {}
        self._request_count: int = 0
        self._fallbacks_used: int = 0
        self._lock = threading.RLock()

        route_metrics = self._config.get("route_metrics", True)
        self._metrics_enabled = bool(route_metrics)

        # Seed deployments from config
        for d in (self._config.get("deployments") or []):
            self.add_deployment(DeploymentModel.from_dict(d))

    # -- deployment management ------------------------------------------------

    def add_deployment(self, deployment: DeploymentModel) -> None:
        with self._lock:
            deployment.blacklisted = deployment.blacklisted or deployment.id in self._blacklist
            self.deployments[deployment.id] = deployment
            self.cooldown.remove_cooldown(deployment.id)
            self.cooldown.reset_failures(deployment.id)

    def remove_deployment(self, deployment_id: str) -> Optional[DeploymentModel]:
        with self._lock:
            dep = self.deployments.pop(deployment_id, None)
            if dep:
                self.cooldown.remove_cooldown(deployment_id)
                self.cooldown.reset_failures(deployment_id)
            return dep

    def get_deployment(self, deployment_id: str) -> Optional[DeploymentModel]:
        return self.deployments.get(deployment_id)

    def deployments_for_group(self, group_id: str) -> List[DeploymentModel]:
        return [d for d in self.deployments.values() if d.group == group_id]

    # -- health / selection ----------------------------------------------------

    def _is_healthy(self, deployment: DeploymentModel) -> bool:
        if deployment.blacklisted:
            return False
        if self.cooldown.is_deployment_cooldowned(deployment.id):
            return False
        return True

    def _select_weighted(
        self,
        group_id: str,
        exclude: Optional[set] = None,
    ) -> Optional[DeploymentModel]:
        """Hash-bucket weighted selection among healthy deployments.

        Each deployment contributes ``weight`` buckets to the range
        ``[0, total_weight)``; a uniform sample lands in a deployment's buckets
        with probability proportional to its weight.
        """
        exclude = exclude or set()
        candidates = [
            d for d in self.deployments_for_group(group_id)
            if self._is_healthy(d) and d.id not in exclude
        ]
        if not candidates:
            return None
        total = max(sum(max(d.weight, 0) for d in candidates), 1)
        r = self._rng.uniform(0, total)
        for d in candidates:
            r -= max(d.weight, 0)
            if r <= 0:
                return d
        return candidates[-1]

    # -- dispatch -------------------------------------------------------------

    def _adapter_for(self, deployment: DeploymentModel) -> BaseProviderAdapter:
        if not deployment:
            raise ProviderError("no deployment")
        a = self.adapter_map.get(deployment.id)
        if a is not None:
            return a
        if self.adapter is not None:
            return self.adapter
        return HTTPAdapter()

    async def _invoke_with_retries(
        self,
        deployment: DeploymentModel,
        request: Any,
    ) -> ProviderResponse:
        """Call adapter for this deployment applying per-exception-type retries."""
        retry_policy: Dict[str, int] = {
            **_DEFAULT_RETRY_POLICY,
            **(deployment.retry_policy or {}),
        }
        adapter = self._adapter_for(deployment)
        attempt = 0
        while True:
            attempt += 1
            try:
                return await adapter.call(deployment, request)
            except ProviderError as e:
                key = type(e).__name__
                if isinstance(e, AuthenticationError):
                    raise  # never retry auth failures
                max_retries = retry_policy.get(key, 0)
                if attempt <= max_retries:
                    logger.debug(
                        "retrying %s on %s (attempt %d/%d): %s",
                        request, deployment.id, attempt, max_retries, key,
                    )
                    await asyncio.sleep(0)  # yield; deterministic offline
                    continue
                raise

    def _record_failure(self, deployment_id: str, allowed_fails: int, cooldown_time: float) -> bool:
        entered = self.cooldown.record_failure(deployment_id, allowed_fails, cooldown_time)
        if self._metrics_enabled:
            with self._lock:
                self._fail_counts[deployment_id] = self._fail_counts.get(deployment_id, 0) + 1
        return entered

    def _record_success(self, deployment_id: str, tokens: Optional[Dict], latency_ms: float) -> None:
        self.cooldown.reset_failures(deployment_id)
        if self._metrics_enabled:
            with self._lock:
                self._success_counts[deployment_id] = self._success_counts.get(deployment_id, 0) + 1
                self._latency_sum[deployment_id] = self._latency_sum.get(deployment_id, 0.0) + latency_ms
                self._latency_count[deployment_id] = self._latency_count.get(deployment_id, 0) + 1

    async def route(self, group_id: str, request: Any, **kw: Any) -> RouteResult:
        """Route ``request`` through the model group named ``group_id``.

        Returns:
            A :class:`RouteResult` describing success/failure, latency,
            the winning deployment, attempts, fallbacks used and final error.
        """
        start = self._now()
        if self._metrics_enabled:
            with self._lock:
                self._request_count += 1

        group = self.deployments_for_group(group_id)
        if not group:
            return RouteResult(
                status="error",
                latency_ms=0.0,
                final_error=f"unknown model group: {group_id}",
            )

        max_fallbacks = max((d.max_fallbacks for d in group), default=1)
        tried: set = set()
        fallbacks_used = 0
        attempts = 0
        last_error: Optional[BaseException] = None
        last_deployment: Optional[str] = None

        deployment = self._select_weighted(group_id, exclude=tried)
        while deployment is not None:
            tried.add(deployment.id)
            last_deployment = deployment.id
            attempts += 1
            try:
                resp = await self._invoke_with_retries(deployment, request)
                latency_ms = (self._now() - start) * 1000.0
                self._record_success(deployment.id, resp.tokens, latency_ms)
                return RouteResult(
                    messages=resp.content,
                    status="success",
                    latency_ms=latency_ms,
                    deployment_id=deployment.id,
                    attempts=attempts,
                    fallbacks_used=fallbacks_used,
                    tokens=resp.tokens,
                )
            except ProviderError as e:
                last_error = e
                self._record_failure(
                    deployment.id,
                    deployment.allowed_fails,
                    deployment.cooldown_time,
                )
                remaining = len(group) - len(tried)
                if fallbacks_used < max_fallbacks and remaining > 0:
                    fallbacks_used += 1
                    with self._lock:
                        self._fallbacks_used += 1
                    deployment = self._select_weighted(group_id, exclude=tried)
                else:
                    deployment = None

        latency_ms = (self._now() - start) * 1000.0
        return RouteResult(
            status="error",
            latency_ms=latency_ms,
            deployment_id=last_deployment,
            attempts=attempts,
            fallbacks_used=fallbacks_used,
            final_error=str(last_error) if last_error else f"no_healthy_deployment:{group_id}",
        )

    # -- metrics ---------------------------------------------------------------

    def avg_latency_ms(self, deployment_id: str) -> float:
        with self._lock:
            n = self._latency_count.get(deployment_id, 0)
            if n == 0:
                return 0.0
            return self._latency_sum.get(deployment_id, 0.0) / n

    def snapshot(self) -> Dict[str, Any]:
        """Return a full metrics snapshot (success/fail, cooldowns, latency...)."""
        with self._lock:
            deps = {}
            for rid, dep in self.deployments.items():
                deps[rid] = {
                    "model": dep.model,
                    "provider": dep.provider,
                    "weight": dep.weight,
                    "allowed_fails": dep.allowed_fails,
                    "cooldown_time": dep.cooldown_time,
                    "group": dep.group,
                    "blacklisted": dep.blacklisted,
                    "successes": self._success_counts.get(rid, 0),
                    "failures": self._fail_counts.get(rid, 0),
                    "avg_latency_ms": self.avg_latency_ms(rid),
                }
            return {
                "request_count": self._request_count,
                "fallbacks_used": self._fallbacks_used,
                "cooldowns": self.cooldown.active_cooldowns(),
                "deployments": deps,
                "route_metrics_enabled": self._metrics_enabled,
            }

    def get_status(self) -> Dict[str, Any]:
        healthy = [rid for rid, dep in self.deployments.items() if self._is_healthy(dep)]
        return {
            "deployments": list(self.deployments),
            "healthy": healthy,
            "in_cooldown": list(self.cooldown.active_cooldowns()),
            "blacklisted": list(self._blacklist),
            "request_count": self._request_count,
            "fallbacks_used": self._fallbacks_used,
        }

    def health(self) -> bool:
        """True if at least one deployment is selectable."""
        if not self.deployments:
            return False
        return any(self._is_healthy(d) for d in self.deployments.values())


class ModelRouter(Router):
    """Ergonomic facade over :class:`Router`.

    Accepts deployments as dicts or :class:`DeploymentModel` instances and
    exposes the friendly ``route(group_id, messages, **kw)`` API plus
    ``add_deployment`` / ``remove_deployment`` / ``get_status`` / ``health`` /
    ``snapshot``.
    """

    async def route(self, group_id: str, messages: Any, **kw: Any) -> RouteResult:
        return await super().route(group_id, messages, **kw)

    def add_deployment(self, deployment: Any) -> None:
        if isinstance(deployment, dict):
            deployment = DeploymentModel.from_dict(deployment)
        super().add_deployment(deployment)


# =============================================================================
# Platform kernel module
# =============================================================================


@module(name="model_router", version="1.0.0")
class ModelRouterModule(Module):
    """Kernel module wrapping a :class:`ModelRouter`.

    Configuration (under ``modules.model_router.config`` in config.yaml):
        deployments (list[dict]): per-deployment configuration.
        route_metrics (bool): enable per-route metrics (default True).
        blacklist (list[str]): deployment ids never selected.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._event_bus: Optional[EventBus] = None
        self._router: Optional[ModelRouter] = None
        self._lock = threading.RLock()

    @property
    def router(self) -> Optional[ModelRouter]:
        with self._lock:
            return self._router

    @property
    def event_bus(self) -> Optional[EventBus]:
        with self._lock:
            return self._event_bus

    async def initialize(self) -> None:
        with self._lock:
            self._status = HealthStatus.STARTING
        cfg = dict(self._config or {})
        # Default to the real HTTP transport; tests may construct a ModelRouter
        # directly (or set an adapter afterward) for offline operation.
        router = ModelRouter(cfg, adapter=HTTPAdapter())
        with self._lock:
            self._router = router
            self._status = HealthStatus.HEALTHY
        logger.info(
            "model_router initialized with %d deployment(s)",
            len(router.deployments),
        )

    async def health_check(self) -> HealthStatus:
        with self._lock:
            if self._router is not None and self._status == HealthStatus.HEALTHY:
                return HealthStatus.HEALTHY
            return HealthStatus.UNHEALTHY

    async def shutdown(self) -> None:
        with self._lock:
            if self._status == HealthStatus.STOPPING:
                return  # idempotent
            self._status = HealthStatus.STOPPING
            self._router = None
            logger.info("model_router shut down")

    def set_event_bus(self, event_bus: EventBus) -> None:
        with self._lock:
            self._event_bus = event_bus


__all__ = [
    "Router",
    "ModelRouter",
    "ModelRouterModule",
    "DeploymentModel",
    "CooldownCache",
    "RouteResult",
    "ProviderResponse",
    "BaseProviderAdapter",
    "HTTPAdapter",
    "EchoAdapter",
    "NoopAdapter",
    "ProviderError",
    "RateLimitError",
    "ProviderTimeoutError",
    "AuthenticationError",
    "ServiceUnavailableError",
    "NoDeploymentAvailableError",
]
