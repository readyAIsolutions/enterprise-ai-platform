"""Cost Meter — per-tenant cost metering + fractional-reasoning policy (B3 + C4).

Registers itself as a first-class Platform Kernel module so the rest of the
stack can:

  * meter tokens/cost per tenant (via :class:`TenantMeter`) and enforce a
    monthly budget — rejecting spends that would bust the quota,
  * map a task class (sequential/icm vs swarm/judgment) to a model tier
    (cheap vs frontier) via :class:`Policy`, so deterministic ICM work is
    pinned to the cheapest model and judgment work may escalate.

Both capabilities are plain, stdlib-only objects living in
:mod:`enterprise.modules.cost_meter.cost_meter`; this package exposes them as a
kernel module with an initialize / health_check / shutdown lifecycle and a
thin always-available facade.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from enterprise.platform_kernel import HealthStatus, Module, module

from .cost_meter import (
    DEFAULT_TIER,
    DEFAULT_TIER_BY_CLASS,
    MODEL_TIERS,
    TASK_CLASSES,
    Policy,
    TenantMeter,
    classify_task,
)

logger = logging.getLogger("eni.cost_meter_module")

__version__ = "1.0.0"
__module__ = "cost_meter"


@module(
    name="cost_meter",
    version=__version__,
    config_defaults={
        # where the per-tenant JSON ledger is persisted (relative to repo root
        # unless absolute)
        "data_file": "data/cost_meter.json",
        # default fractional-reasoning policy mapping
        "policy": {
            "by_class": DEFAULT_TIER_BY_CLASS,
            "default_tier": DEFAULT_TIER,
        },
    },
)
class CostMeterModule(Module):
    """Kernel module exposing per-tenant cost metering + budget enforcement."""

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._meter: Optional[TenantMeter] = None
        self._policy: Optional[Policy] = None
        self._data_file: Optional[Path] = None
        self._init_error: Optional[str] = None

    async def initialize(self) -> None:
        try:
            df = self.config.get("data_file", "data/cost_meter.json")
            path = Path(df)
            if not path.is_absolute():
                path = (self._repo_root or Path(".")) / df
            path.parent.mkdir(parents=True, exist_ok=True)
            self._data_file = path
            self._meter = TenantMeter(path=path, persist=True, load=True)
            policy_cfg = self.config.get("policy") or {}
            self._policy = Policy.from_config(policy_cfg)
            self.status = HealthStatus.HEALTHY
        except Exception as exc:  # defensively mark unhealthy, never crash kernel
            self._init_error = str(exc)
            self.status = HealthStatus.UNHEALTHY
            logger.warning("cost_meter init failed: %s", exc)

    async def health_check(self) -> HealthStatus:
        if self._init_error:
            return HealthStatus.UNHEALTHY
        return HealthStatus.HEALTHY

    async def shutdown(self) -> None:
        if self._meter is not None:
            try:
                self._meter._persist()  # flush latest ledger
            except Exception:  # pragma: no cover
                pass
        self.status = HealthStatus.UNKNOWN
        logger.info("cost_meter module shutdown")

    @property
    def _repo_root(self) -> Optional[Path]:
        # enterprise/ is the package; repo root is three levels up from modules/cost_meter
        return Path(__file__).resolve().parent.parent.parent

    # ------------------------------------------------------------- facade
    def meter(self) -> TenantMeter:
        """The live :class:`TenantMeter` (created lazily if not initialised)."""
        if self._meter is None:
            self._meter = TenantMeter(
                path=self._data_file or "data/cost_meter.json", persist=True, load=True
            )
        return self._meter

    def set_budget(self, tenant: str, budget: float) -> None:
        self.meter().set_budget(tenant, budget)

    def add_usage(self, tenant: str, tokens: int = 0, cost: float = 0.0) -> float:
        """Accumulate raw usage (not budget-enforced)."""
        return self.meter().add(tenant, tokens=tokens, cost=cost)

    def spend(self, tenant: str, tokens: int = 0, cost: float = 0.0) -> dict[str, Any]:
        """Budget-enforced spend; see :meth:`TenantMeter.spend`."""
        return self.meter().spend(tenant, tokens=tokens, cost=cost)

    def remaining(self, tenant: str) -> Optional[float]:
        return self.meter().remaining(tenant)

    def tier_for(self, task_class: Optional[str]) -> str:
        """Model tier a task class is pinned to (fractional reasoning)."""
        return self.policy().tier_for(task_class)

    def resolve(self, task: str) -> dict[str, Any]:
        """Classify a task and return the resolved ``{task_class, tier}`` plan."""
        return self.policy().resolve_task(task)

    def policy(self) -> Policy:
        if self._policy is None:
            self._policy = Policy.from_config(self.config.get("policy") or {})
        return self._policy


def create_cost_meter_module(
    config: Optional[dict[str, Any]] = None,
) -> CostMeterModule:
    """Create (but do not initialize) a :class:`CostMeterModule`."""
    return CostMeterModule(config=config or {})


__all__ = [
    "__version__",
    "CostMeterModule",
    "create_cost_meter_module",
    "TenantMeter",
    "Policy",
    "classify_task",
    "MODEL_TIERS",
    "TASK_CLASSES",
    "DEFAULT_TIER",
    "DEFAULT_TIER_BY_CLASS",
]
