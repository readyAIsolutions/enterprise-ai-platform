"""Tests for the Cost Meter module: per-tenant metering/budget + policy (B3 + C4)."""
from __future__ import annotations

import json

import pytest

from enterprise.modules.cost_meter import (
    Policy,
    TenantMeter,
    create_cost_meter_module,
)


# ---------------------------------------------------------------------------
# TenantMeter — accumulation
# ---------------------------------------------------------------------------

def test_meter_accumulates_tokens_and_cost(tmp_path):
    meter = TenantMeter(path=tmp_path / "cost.json", persist=False)
    meter.add("acme", tokens=100, cost=1.5)
    meter.add("acme", tokens=200, cost=2.5)

    summary = meter.summary("acme")
    assert summary["tokens"] == 300
    assert summary["cost"] == pytest.approx(4.0)
    assert meter.total()["tokens"] == 300
    assert meter.total()["cost"] == pytest.approx(4.0)


def test_meter_isolates_tenants(tmp_path):
    meter = TenantMeter(path=tmp_path / "cost.json", persist=False)
    meter.add("acme", tokens=100, cost=1.0)
    meter.add("globex", tokens=50, cost=0.5)
    assert meter.summary("globex")["tokens"] == 50
    assert meter.summary("acme")["tokens"] == 100
    assert meter.tenants() == ["acme", "globex"]


def test_meter_persists_and_reloads_atomically(tmp_path):
    path = tmp_path / "nested" / "cost_meter.json"
    meter = TenantMeter(path=path, persist=True)
    meter.set_budget("acme", 50.0)
    meter.add("acme", tokens=10, cost=3.0)
    assert path.exists()

    # no stray temp files left behind
    assert not list(path.parent.glob(".cost_meter.*.tmp"))

    reloaded = TenantMeter(path=path, load=True)
    assert reloaded.summary("acme")["tokens"] == 10
    assert reloaded.summary("acme")["cost"] == pytest.approx(3.0)
    assert reloaded.summary("acme")["budget"] == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# TenantMeter — budget enforcement via spend()
# ---------------------------------------------------------------------------

def test_spend_within_budget_is_allowed(tmp_path):
    meter = TenantMeter(path=tmp_path / "cost.json", persist=False)
    meter.set_budget("acme", 100.0)
    result = meter.spend("acme", tokens=250, cost=40.0)

    assert result["allowed"] is True
    assert result["cost"] == pytest.approx(40.0)
    assert result["remaining"] == pytest.approx(60.0)
    # exact-boundary spend is still allowed
    result2 = meter.spend("acme", tokens=10, cost=60.0)
    assert result2["allowed"] is True
    assert result2["remaining"] == pytest.approx(0.0)


def test_over_budget_spend_is_rejected(tmp_path):
    meter = TenantMeter(path=tmp_path / "cost.json", persist=False)
    meter.set_budget("acme", 100.0)
    meter.add("acme", tokens=100, cost=90.0)

    result = meter.spend("acme", tokens=999, cost=50.0)
    assert result["allowed"] is False
    # rejected spend must NOT mutate the ledger
    assert meter.summary("acme")["cost"] == pytest.approx(90.0)
    assert meter.summary("acme")["tokens"] == 100
    assert result["remaining"] == pytest.approx(10.0)


def test_unlimited_budget_always_allows(tmp_path):
    meter = TenantMeter(path=tmp_path / "cost.json", persist=False)
    result = meter.spend("acme", tokens=1_000_000, cost=1_000_000.0)
    assert result["allowed"] is True
    assert result["remaining"] is None


# ---------------------------------------------------------------------------
# Policy — fractional reasoning config (C4)
# ---------------------------------------------------------------------------

def test_policy_default_mapping_pins_icm_cheap_and_judgment_frontier():
    policy = Policy()

    # deterministic ICM / sequential work -> cheapest model
    assert policy.tier_for("sequential") == "cheap"
    assert policy.tier_for("icm") == "cheap"
    # judgment / swarm work may escalate to frontier
    assert policy.tier_for("judgment") == "frontier"
    assert policy.tier_for("swarm") == "frontier"
    # unknown classes fall back to the default tier
    assert policy.tier_for("mystery") == "cheap"
    assert policy.default_tier == "cheap"


def test_policy_from_config_overrides_and_default():
    policy = Policy.from_config(
        {"by_class": {"judgment": "cheap"}, "default_tier": "frontier"}
    )
    assert policy.tier_for("judgment") == "cheap"
    assert policy.tier_for("swarm") == "frontier"  # unchanged default mapping
    assert policy.tier_for("unknown") == "frontier"
    assert policy.tier_for(None) == "frontier"


def test_policy_rejects_unknown_tier():
    with pytest.raises(ValueError):
        Policy.from_config({"by_class": {"sequential": "quantum"}})


def test_policy_resolves_compliance_task_to_cheap_and_legal_to_frontier():
    policy = Policy()

    # a compliance task is deterministic ICM-class work -> cheapest model
    compliance = policy.resolve_task("run the compliance checklist on this record")
    assert compliance["tier"] == "cheap"

    # a legal-reasoning task is judgment-class work -> may escalate to frontier
    legal = policy.resolve_task("cross-validate the legal reasoning with a second model")
    assert legal["tier"] == "frontier"


# ---------------------------------------------------------------------------
# Module lifecycle + facade
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cost_meter_module_registers_and_initializes(tmp_path):
    mod = create_cost_meter_module(
        {"data_file": str(tmp_path / "cost_meter.json")}
    )
    assert mod is not None
    await mod.initialize()
    assert mod.status.value in ("healthy", "HEALTHY")
    assert (await mod.health_check()).value in ("healthy", "HEALTHY")

    mod.set_budget("acme", 100.0)
    mod.add_usage("acme", tokens=100, cost=10.0)
    result = mod.spend("acme", tokens=50, cost=95.0)
    assert result["allowed"] is False
    assert result["remaining"] == pytest.approx(90.0)
    assert mod.remaining("acme") == pytest.approx(90.0)

    # fractional-reasoning ready through the facade too
    assert mod.tier_for("sequential") == "cheap"
    assert mod.resolve("cross-validate the legal reasoning")["tier"] == "frontier"

    await mod.shutdown()


@pytest.mark.asyncio
async def test_cost_meter_ledger_reloads_via_module(tmp_path):
    path = tmp_path / "cost_meter.json"
    mod = create_cost_meter_module({"data_file": str(path)})
    await mod.initialize()
    mod.set_budget("acme", 50.0)
    mod.add_usage("acme", tokens=20, cost=7.0)
    await mod.shutdown()

    # a fresh instance loads the same persisted ledger
    mod2 = create_cost_meter_module({"data_file": str(path)})
    await mod2.initialize()
    assert mod2.meter().summary("acme")["cost"] == pytest.approx(7.0)
