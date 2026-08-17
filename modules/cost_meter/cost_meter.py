"""Per-tenant cost metering + fractional-reasoning policy (B3 + C4).

Standalone, stdlib-only implementation of the two building blocks behind the
"cheaper, better automated building" selling point:

  * :class:`TenantMeter` — persists per-tenant token/cost accumulators and
    enforces a monthly budget. When a tenant's spend would exceed its budget
    the ``spend`` call is rejected (``allowed == False``) and the remaining
    quota is reported. State lives in a single JSON file written atomically.
  * :class:`Policy` — maps a *task class* (sequential/icm vs swarm/judgment)
    to a *model tier* (cheap vs frontier) so deterministic ICM work is pinned
    to the cheapest model while judgment work may escalate to a frontier
    model.

Both objects are plain Python and depend only on the standard library so they
can be unit-tested and embedded anywhere in the platform (router, broker,
dashboard) without pulling in the whole kernel.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Model tiers & task classes (the fractional-reasoning ladder, C4)
# ---------------------------------------------------------------------------

# The escalation ladder as an explicit, configurable surface.
MODEL_TIERS = ("cheap", "frontier")
TASK_CLASSES = ("sequential", "icm", "swarm", "judgment")

# Default fractional-reasoning policy: deterministic/ICM work -> cheapest tier,
# judgment/swarm work may escalate to the frontier tier.
DEFAULT_TIER_BY_CLASS: dict[str, str] = {
    "sequential": "cheap",
    "icm": "cheap",
    "swarm": "frontier",
    "judgment": "frontier",
}
DEFAULT_TIER = "cheap"


class Policy:
    """Fractional-reasoning policy: maps a task class to a model tier.

    Deterministic ICM/sequential work pins to the *cheap* tier (cost exactly
    where the work is cheap); judgment/swarm work may escalate to the
    *frontier* tier. The mapping is fully configurable via ``config`` and every
    unknown class falls back to ``default_tier``.
    """

    __slots__ = ("_by_class", "_default_tier")

    def __init__(
        self,
        by_class: Optional[dict[str, str]] = None,
        default_tier: Optional[str] = None,
    ) -> None:
        mapping = dict(DEFAULT_TIER_BY_CLASS)
        if by_class:
            for cls, tier in by_class.items():
                if tier not in MODEL_TIERS:
                    raise ValueError(
                        f"unknown model tier {tier!r}; expected one of {MODEL_TIERS}"
                    )
                mapping[cls] = tier
        self._by_class = mapping
        self._default_tier = default_tier or DEFAULT_TIER
        if self._default_tier not in MODEL_TIERS:
            raise ValueError(
                f"unknown default tier {self._default_tier!r}; "
                f"expected one of {MODEL_TIERS}"
            )

    # -- construction -------------------------------------------------------
    @classmethod
    def from_config(cls, config: Optional[dict[str, Any] | None] = None):
        """Build a :class:`Policy` from a config dict.

        Recognised keys:

          * ``by_class``      -> ``{task_class: tier}`` overrides
          * ``default_tier``  -> fallback for unknown/empty task classes

        Missing keys fall back to the built-in default mapping.
        """
        config = config or {}
        return cls(
            by_class=config.get("by_class"),
            default_tier=config.get("default_tier"),
        )

    # -- behaviour ----------------------------------------------------------
    def tier_for(self, task_class: Optional[str]) -> str:
        """Return the model tier a task class is pinned to."""
        if not task_class:
            return self._default_tier
        return self._by_class.get(task_class, self._default_tier)

    def resolve(self, task_class: Optional[str]) -> dict[str, str]:
        """Return a resolved ``{task_class, tier}`` decision for a task class."""
        cls = task_class or "unknown"
        return {"task_class": cls, "tier": self.tier_for(cls)}

    def resolve_task(self, task: str) -> dict[str, str]:
        """Resolve a raw task description by classifying it first.

        Uses the platform ICM classifier when available; otherwise a tiny
        local keyword classifier (kept in sync with ICM's division of labor).
        """
        task_class = _classify_task(task)
        return self.resolve(task_class)

    @property
    def default_tier(self) -> str:
        return self._default_tier

    @property
    def mapping(self) -> dict[str, str]:
        return dict(self._by_class)


_JUDGMENT_HINTS = (
    "legal", "judgment", "reason", "debate", "arbitrat", "adjudicat",
    "classif", "creativity", "generat", "assess", "cross-valid",
)
_SEQUENTIAL_HINTS = (
    "compliance", "verify", "certify", "check", "validate", "convert",
    "export", "render", "deploy", "ingest", "format", "proofread",
)


def _classify_task(task: str) -> str:
    """Classify a task as 'swarm'/'judgment' or 'sequential'/'icm'."""
    t = task.lower()
    try:  # prefer the authoritative platform classifier when importable
        from enterprise.modules.icm import classify as _icm_classify  # noqa: F401

        icm_result = _icm_classify(task)
        if icm_result in ("sequential", "swarm"):
            return icm_result
    except Exception:  # pragma: no cover - icm not importable here
        pass
    for kw in _JUDGMENT_HINTS:
        if kw in t:
            return "swarm"
    if any(kw in t for kw in _SEQUENTIAL_HINTS):
        return "sequential"
    return "sequential"


# ---------------------------------------------------------------------------
# Per-tenant metering + budget enforcement (B3)
# ---------------------------------------------------------------------------

def _current_month() -> str:
    """Return the current budget period as ``YYYY-MM``."""
    return date.today().strftime("%Y-%m")


class TenantMeter:
    """Tracks per-tenant token/cost accumulators and enforces monthly budgets.

    State is a ``{tenant: record}`` map where each record holds the totals for
    the current budget period plus the tenant's configured monthly budget. On
    every mutation the state is written to disk **atomically** (write to a
    temp file in the same directory, then ``os.replace``), so a crash mid-write
    never leaves a truncated/corrupt JSON file behind.

    Example::

        meter = TenantMeter(path)
        meter.set_budget("acme", budget=100.0)
        meter.add("acme", tokens=100, cost=1.5)      # accumulate, not budgeted
        result = meter.spend("acme", tokens=250, cost=99.0)  # enforced
        result["allowed"]   # False if it would bust the budget
        result["remaining"] # left in the monthly budget
    """

    def __init__(
        self,
        path: os.PathLike | str | None = None,
        budgets: Optional[dict[str, float]] = None,
        persist: bool = True,
        load: bool = True,
    ) -> None:
        self.path = Path(path) if path else Path("data") / "cost_meter.json"
        self.persist = persist
        # {tenant: {"tokens": int, "cost": float, "budget": float, "month": str}}
        self._records: dict[str, dict[str, Any]] = {}
        if budgets:
            for tenant, budget in budgets.items():
                self._records.setdefault(tenant, {})["budget"] = float(budget)
        if load and self.path.exists():
            self._load()
        for rec in self._records.values():
            rec.setdefault("month", _current_month())
            rec.setdefault("budget", float("inf"))
            rec.setdefault("tokens", 0)
            rec.setdefault("cost", 0.0)

    # -- persistence --------------------------------------------------------
    def _load(self) -> None:
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                for tenant, rec in data.items():
                    if isinstance(rec, dict):
                        self._records[tenant] = {
                            "tokens": int(rec.get("tokens", 0)),
                            "cost": float(rec.get("cost", 0.0)),
                            "budget": float(rec.get("budget", float("inf"))),
                            "month": str(rec.get("month", _current_month())),
                        }
        except (OSError, ValueError):
            # never let a corrupt file take the meter down; start fresh
            self._records = {}

    def _persist(self) -> None:
        if not self.persist:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._records, indent=2, sort_keys=True)
        fd, tmp = tempfile.mkstemp(
            dir=str(self.path.parent), prefix=".cost_meter.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)  # atomic
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # -- tenant records -----------------------------------------------------
    def _ensure(self, tenant: str) -> dict[str, Any]:
        rec = self._records.get(tenant)
        if rec is None:
            rec = {
                "tokens": 0,
                "cost": 0.0,
                "budget": float("inf"),
                "month": _current_month(),
            }
            self._records[tenant] = rec
        # roll over on new budget period
        if rec.get("month") != _current_month():
            rec["month"] = _current_month()
            rec["tokens"] = 0
            rec["cost"] = 0.0
        return rec

    def set_budget(self, tenant: str, budget: float) -> None:
        """Set (or update) a tenant's monthly budget in cost units."""
        rec = self._ensure(tenant)
        rec["budget"] = float(budget)
        self._persist()

    def add(self, tenant: str, tokens: int = 0, cost: float = 0.0) -> float:
        """Accumulate usage for a tenant *without* budget enforcement.

        Useful for recording raw metering (C2 live BI) while ``spend`` remains
        the guarded path. Returns the tenant's current accumulated cost.
        """
        rec = self._ensure(tenant)
        rec["tokens"] += int(tokens or 0)
        rec["cost"] += float(cost or 0.0)
        self._persist()
        return float(rec["cost"])

    def spend(self, tenant: str, tokens: int = 0, cost: float = 0.0) -> dict[str, Any]:
        """Record usage *against* the monthly budget.

        If the additional ``cost`` would push the tenant over its configured
        monthly budget the spend is rejected: no state changes and
        ``allowed == False`` is returned. Otherwise the usage is applied and
        ``allowed == True``. ``remaining`` is always the budget left after the
        (accepted or hypothetical) spend.

        A tenant with an unlimited budget (no ``budget`` configured) always
        spends successfully.
        """
        rec = self._ensure(tenant)
        tokens = int(tokens or 0)
        cost = float(cost or 0.0)
        budget = float(rec["budget"])
        projected = float(rec["cost"]) + cost
        allowed = projected <= budget + 1e-9
        if allowed:
            rec["tokens"] += tokens
            rec["cost"] = projected
            self._persist()
        return {
            "tenant": tenant,
            "allowed": allowed,
            "tokens": int(rec["tokens"]),
            "cost": float(rec["cost"]),
            "budget": budget if budget != float("inf") else None,
            "remaining": self.remaining(tenant),
        }

    def remaining(self, tenant: str) -> Optional[float]:
        """Budget units left for the tenant this period (None = unlimited)."""
        rec = self._ensure(tenant)
        budget = float(rec["budget"])
        if budget == float("inf"):
            return None
        return max(0.0, budget - float(rec["cost"]))

    def summary(self, tenant: str) -> dict[str, Any]:
        """A compact, human-readable snapshot for one tenant."""
        rec = self._ensure(tenant)
        budget = float(rec["budget"])
        return {
            "tenant": tenant,
            "month": rec["month"],
            "tokens": int(rec["tokens"]),
            "cost": float(rec["cost"]),
            "budget": budget if budget != float("inf") else None,
            "remaining": self.remaining(tenant),
        }

    def tenants(self) -> list[str]:
        return sorted(self._records)

    def total(self) -> dict[str, Any]:
        """Platform-wide totals (across tenants) for live BI."""
        return {
            "tenants": len(self._records),
            "tokens": sum(int(r["tokens"]) for r in self._records.values()),
            "cost": sum(float(r["cost"]) for r in self._records.values()),
        }


__all__ = [
    "TenantMeter",
    "Policy",
    "MODEL_TIERS",
    "TASK_CLASSES",
    "DEFAULT_TIER",
    "DEFAULT_TIER_BY_CLASS",
    "classify_task",
]
# re-export for convenience
classify_task = _classify_task
