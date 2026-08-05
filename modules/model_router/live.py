"""Live smoke/sanity helpers for the ENI Model Router.

This module makes the model_router *real-provider ready*: it gives operators a
non-destructive way to prove a deployment is reachable and a little failover
smoke test that exercises the cooldown + fallback chain against real endpoints
(or, crucially for CI, against an *injected* request function so the whole thing
runs hermetically offline with zero network).

Everything here is hermetic by default: pass ``request_fn`` to simulate
HTTP outcomes (429 / 5xx / timeout / success) and no socket is ever opened. The
real-network path (no ``request_fn``) is opt-in and used only by an operator
running a genuine sanity check against a live provider.

Public API
----------
LiveProbe.run(...)      -> one-shot non-destructive probe of a base_url.
LiveFailoverSmoke       -> sequential multi-deployment probe + cooldown/fallback.
ping_local_free_router() -> convenience ping of 127.0.0.1:8920 -> (bool, detail).
"""

from __future__ import annotations

import asyncio
import os
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .model_router import (
    CooldownCache,
    DeploymentModel,
    HTTPAdapter,
    ProviderError,
)

# A request function may either return a ``(status_code, body)`` tuple or raise.
RequestFn = Callable[..., Any]

DEFAULT_LOCAL_FREE_ROUTER = ("127.0.0.1", 8920)


# ---------------------------------------------------------------------------
# Probe result
# ---------------------------------------------------------------------------


@dataclass
class ProbeResult:
    """Result of a single non-destructive deployment probe."""

    reachable: bool = False
    status_code: int | None = None
    error: str | None = None
    latency_ms: float = 0.0
    cooldowned: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "reachable": self.reachable,
            "status_code": self.status_code,
            "error": self.error,
            "latency_ms": round(self.latency_ms, 3),
            "cooldowned": self.cooldowned,
        }


# ---------------------------------------------------------------------------
# LiveProbe
# ---------------------------------------------------------------------------


class LiveProbe:
    """Non-destructive one-shot liveness check against an OpenAI-compatible endpoint.

    Performs a single minimal ``/chat/completions`` request via the existing
    :class:`HTTPAdapter`. When ``request_fn`` is supplied (tests, offline CI) the
    real transport is bypassed entirely and the injected callable produces the
    HTTP outcome — no socket is opened.
    """

    def __init__(self, timeout: float = 15.0, env: Any = None) -> None:
        self.timeout = timeout
        self._env = env if env is not None else os.environ

    def run(
        self,
        base_url: str,
        api_key_env: str | None = None,
        model: str = "probe-model",
        request_fn: RequestFn | None = None,
    ) -> ProbeResult:
        start = time.monotonic()
        api_key = self._env.get(api_key_env) if api_key_env else None

        try:
            if request_fn is not None:
                status_code, body = self._invoke_injected(request_fn, base_url, model, api_key)
            else:
                status_code, body = self._invoke_live(base_url, api_key_env, model)
        except ProviderError as e:
            return ProbeResult(
                reachable=False,
                status_code=None,
                error=str(e),
                latency_ms=(time.monotonic() - start) * 1000.0,
            )
        latency_ms = (time.monotonic() - start) * 1000.0

        if status_code is not None and 200 <= status_code < 300:
            return ProbeResult(
                reachable=True,
                status_code=status_code,
                error=None,
                latency_ms=latency_ms,
            )
        error = f"HTTP {status_code}" if status_code is not None else "no response"
        return ProbeResult(
            reachable=False,
            status_code=status_code,
            error=error,
            latency_ms=latency_ms,
        )

    def _invoke_injected(
        self, request_fn: RequestFn, base_url: str, model: str, api_key: str | None
    ) -> tuple:
        outcome = request_fn(base_url=base_url, model=model, api_key=api_key, timeout=self.timeout)
        if isinstance(outcome, tuple) and len(outcome) == 2:
            return int(outcome[0]), outcome[1]
        return 200, outcome

    def _invoke_live(self, base_url: str, api_key_env: str | None, model: str) -> tuple:
        dep = DeploymentModel(
            id="live-probe",
            model=model,
            base_url=base_url,
            api_key_env=api_key_env,
        )
        adapter = HTTPAdapter(timeout=self.timeout, env=self._env)
        payload = [{"role": "user", "content": "ping"}]

        async def _go() -> None:
            await adapter.call(dep, payload)

        asyncio.run(_go())
        return adapter.last_status_code or 200, {}


# ---------------------------------------------------------------------------
# LiveFailoverSmoke
# ---------------------------------------------------------------------------


class LiveFailoverSmoke:
    """Sequential probe across a list of deployments + cooldown/fallback smoke.

    Iterates the deployments in order, probing each. A deployment that responds
    transiently (429 / 5xx / timeout) is fed to the :class:`CooldownCache`, and
    once its failures reach ``allowed_fails`` it is cooled down and skipped by
    the rest of the chain. The first *healthy* (2xx, non-cooldowned) deployment
    is selected — exactly the fallback behaviour of the full router, but here it
    is driven by live probes (or injected simulations) instead of a dispatch loop.

    Fully offline when ``request_fn`` is provided: the chain can be made to
    simulate 429 / 5xx / timeout against specific deployments and assert that
    the cooldown + fallback picks the healthy one.
    """

    def __init__(
        self,
        deployments: list[Any],
        request_fn: RequestFn | None = None,
        timeout: float = 15.0,
        cooldown_time: float = 5.0,
        allowed_fails: int = 3,
        clock: Callable[[], float] | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self.deployments = deployments
        self.request_fn = request_fn
        self.timeout = timeout
        self.cooldown_time = cooldown_time
        self.allowed_fails = allowed_fails
        self.probe = LiveProbe(timeout=timeout, env=env)
        self.cooldown = CooldownCache(clock=clock)

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _dep_id(dep: Any) -> str:
        if isinstance(dep, DeploymentModel):
            return dep.id
        if isinstance(dep, dict):
            return str(dep.get("id", "?"))
        return str(dep)

    @staticmethod
    def _dep_base_url(dep: Any) -> str:
        if isinstance(dep, DeploymentModel):
            return dep.base_url
        if isinstance(dep, dict):
            return dep.get("base_url") or dep.get("endpoint") or ""
        return str(dep)

    @staticmethod
    def _dep_model(dep: Any) -> str:
        if isinstance(dep, DeploymentModel):
            return dep.model or "probe-model"
        if isinstance(dep, dict):
            return dep.get("model") or "probe-model"
        return "probe-model"

    @staticmethod
    def _dep_key_env(dep: Any) -> str | None:
        if isinstance(dep, DeploymentModel):
            return dep.api_key_env
        if isinstance(dep, dict):
            return dep.get("api_key_env")
        return None

    def _classify_result(self, res: ProbeResult, dep: Any) -> bool:
        """Record a transient failure into the cooldown cache if applicable.

        Returns True when the deployment is transient-failing (429 / 5xx /
        timeout) so the caller knows to cooldown-track it.
        """
        if res.reachable:
            return False
        code = res.status_code
        err_lower = (res.error or "").lower()
        transient = (
            code == 429
            or (code is not None and 500 <= code <= 599)
            or "timeout" in err_lower
            or "timed out" in err_lower
        )
        if transient:
            self.cooldown.record_failure(
                self._dep_id(dep),
                self.allowed_fails,
                self.cooldown_time,
            )
        return transient

    # -- runner --------------------------------------------------------------

    def run(self) -> dict[str, Any]:
        """Probe each deployment sequentially, apply cooldowns, pick the healthy one.

        Returns a dict with keys:
            ok         -> True if a healthy deployment was selected.
            selected   -> id of the winning deployment (or None).
            reachable  -> list of deployment ids that were 2xx-reachable.
            results    -> per-deployment ProbeResult dicts in probe order.
        """
        results: dict[str, dict[str, Any]] = {}
        reachable: list[str] = []
        selected: str | None = None

        for dep in self.deployments:
            did = self._dep_id(dep)
            if self.cooldown.is_deployment_cooldowned(did):
                results[did] = ProbeResult(
                    reachable=False, error="cooldowned", cooldowned=True
                ).as_dict()
                continue

            res = self.probe.run(
                self._dep_base_url(dep),
                api_key_env=self._dep_key_env(dep),
                model=self._dep_model(dep),
                request_fn=self.request_fn,
            )
            d = res.as_dict()
            d["id"] = did
            d["cooldowned"] = self.cooldown.is_deployment_cooldowned(did)

            if res.reachable and not d["cooldowned"]:
                reachable.append(did)
                if selected is None:
                    selected = did
            else:
                self._classify_result(res, dep)
                d["cooldowned"] = self.cooldown.is_deployment_cooldowned(did)
            results[did] = d

        return {
            "ok": selected is not None,
            "selected": selected,
            "reachable": reachable,
            "results": results,
        }


# ---------------------------------------------------------------------------
# Local free-router ping
# ---------------------------------------------------------------------------


def ping_local_free_router(
    host: str = DEFAULT_LOCAL_FREE_ROUTER[0],
    port: int = DEFAULT_LOCAL_FREE_ROUTER[1],
    timeout: float = 1.0,
) -> tuple:
    """Confirm the local free-router proxy at ``127.0.0.1:8920`` is up.

    Non-destructive: attempts a TCP connect only. Returns ``(ok: bool, detail: str)``
    so an operator can print a human-readable one-liner.

        ok, detail = ping_local_free_router()
        print(detail)   # "127.0.0.1:8920 reachable" or "unreachable: ..."

    Args:
        host: host to ping (default 127.0.0.1).
        port: port to ping (default 8920, the free-router).
        timeout: connection timeout in seconds.

    Returns:
        A ``(bool, str)`` tuple — reachable status plus a detail string.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except OSError as e:
        return False, f"{host}:{port} unreachable: {e.__class__.__name__}: {e}"
    return True, f"{host}:{port} reachable"
