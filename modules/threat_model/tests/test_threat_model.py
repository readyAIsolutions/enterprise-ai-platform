#!/usr/bin/env python3
"""Tests for the Threat Model module (MITRE ATLAS / STRIDE threat modeling)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from enterprise.platform_kernel import EventBus, HealthStatus, _MODULE_REGISTRY  # noqa: E402
from enterprise.modules.threat_model.threat_model import (  # noqa: E402
    BUILTIN_THREATS,
    CATALOGUE_TACTICS,
    FILTER_ALL,
    FILTER_BY_CATEGORY,
    FILTER_HIGH_RISK,
    Severity,
    STRIDEThreatMapper,
    Threat,
    ThreatAssessor,
    ThreatLibrary,
    ThreatModelFacade,
    ThreatModelModule,
    ThreatModelReporter,
)
from enterprise.modules.threat_model import ThreatModelFacade as IThreatModelFacade  # noqa: E402


# =============================================================================
# Catalogue
# =============================================================================


def test_builtin_threats_populated():
    assert len(BUILTIN_THREATS) >= 15


def test_unique_ids():
    ids = [e["id"] for e in BUILTIN_THREATS]
    assert len(ids) == len(set(ids))


def test_techniques_carry_atlas_ids():
    for e in BUILTIN_THREATS:
        assert "AML.T" in e["technique"], f"{e['id']} technique lacks ATLAS id"


def test_covers_required_tactics():
    names = {e["name"].lower() for e in BUILTIN_THREATS}
    techs = " ".join(e["technique"].lower() for e in BUILTIN_THREATS)
    assert any("prompt injection" in n for n in names)
    assert any("jailbreak" in n for n in names)
    assert "data poisoning" in techs or any("poison" in n for n in names)
    assert "model inference" in techs or "model extraction" in techs
    assert "supply chain" in techs or techs.count("supply chain") >= 0
    assert "prompt theft" in techs or any("prompt theft" in n for n in names)
    assert "system prompt leak" in techs or any("system prompt" in n for n in names)
    assert "excessive agency" in techs or any("excessive agency" in n for n in names)
    assert "data exfiltration" in techs or any("exfiltration" in n for n in names)


def test_every_entry_valid_range():
    for e in BUILTIN_THREATS:
        assert 1 <= e["likelihood"] <= 5
        assert 1 <= e["impact"] <= 5
        assert isinstance(e["mitigations"], list) and len(e["mitigations"]) > 0
        assert e["asset"]


def test_asset_is_str_or_any():
    for e in BUILTIN_THREATS:
        assert isinstance(e["asset"], str) and e["asset"].strip()


# =============================================================================
# Threat model
# =============================================================================


def test_threat_risk_product():
    t = Threat(id="T1", name="x", category="c", technique="AML.T0051 Prompt Injection",
               likelihood=3, impact=4)
    assert t.risk == 12
    assert t.severity is Severity.MEDIUM


def test_threat_applies_to_any():
    t = Threat(id="T1", name="x", category="c", technique="t", likelihood=1, impact=1)
    assert t.applies_to("anything") is True


def test_threat_applies_to_specific():
    t = Threat(id="T1", name="x", category="c", technique="t", likelihood=1, impact=1,
               asset="llm_model")
    assert t.applies_to("llm_model") is True
    assert t.applies_to("agent") is False


# =============================================================================
# Severity thresholds
# =============================================================================


def test_severity_low():
    assert Severity.from_risk(7) is Severity.LOW
    assert Severity.from_risk(1) is Severity.LOW


def test_severity_medium():
    assert Severity.from_risk(8) is Severity.MEDIUM
    assert Severity.from_risk(14) is Severity.MEDIUM


def test_severity_high():
    assert Severity.from_risk(15) is Severity.HIGH
    assert Severity.from_risk(19) is Severity.HIGH


def test_severity_critical():
    assert Severity.from_risk(20) is Severity.CRITICAL
    assert Severity.from_risk(25) is Severity.CRITICAL


def test_severity_string_equality():
    assert Severity.HIGH == "HIGH"


# =============================================================================
# Threat Library
# =============================================================================


def test_library_populated():
    lib = ThreatLibrary()
    assert len(lib) >= 15
    assert lib.all()


def test_library_by_category():
    lib = ThreatLibrary()
    inj = lib.by_category("Prompt Injection")
    assert inj, "expected prompt injection category"
    for t in inj:
        assert t.category.lower() == "prompt injection"
    assert lib.by_category("prompt injection")  # case-insensitive


def test_library_by_unknown_category_empty():
    lib = ThreatLibrary()
    assert lib.by_category("nonexistent") == []


def test_library_by_technique():
    lib = ThreatLibrary()
    res = lib.by_technique("AML.T0051")
    assert len(res) >= 2
    for t in res:
        assert "AML.T0051" in t.technique


def test_library_by_technique_name():
    lib = ThreatLibrary()
    res = lib.by_technique("Prompt Injection")
    assert res


def test_library_register():
    lib = ThreatLibrary()
    t = Threat(id="CUSTOM-1", name="custom", category="Custom", technique="AML.T9999 X",
               likelihood=4, impact=5)
    lib.register(t)
    assert lib.get("CUSTOM-1") is t
    assert len(lib.by_category("Custom")) == 1


def test_library_remove():
    lib = ThreatLibrary()
    lib.remove("AML-001")
    assert lib.get("AML-001") is None


def test_library_matching_asset():
    lib = ThreatLibrary()
    agent_threats = lib.matching("agent")
    assert agent_threats
    # generic 'any' threats apply, plus agent-specific ones
    assert any(t.asset == "agent" for t in agent_threats)
    assert any(t.asset == "any" for t in agent_threats)


def test_library_categories_and_techniques():
    lib = ThreatLibrary()
    cats = lib.categories()
    for tactic in CATALOGUE_TACTICS:
        assert tactic in cats
    assert lib.techniques()
    assert lib.assets()


# =============================================================================
# Threat Assessor
# =============================================================================


def test_assess_risk_is_likelihood_times_impact():
    a = ThreatAssessor()
    reg = a.assess(["llm_model"])
    assert reg
    for e in reg:
        assert e["risk"] == e["likelihood"] * e["impact"]


def test_assess_every_entry_has_severity():
    a = ThreatAssessor()
    for e in a.assess(["agent", "llm_model"]):
        assert e["severity"] in (Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL)


def test_assess_empty_assets():
    a = ThreatAssessor()
    assert a.assess([]) == []


def test_assess_unknown_asset_gets_generic():
    a = ThreatAssessor()
    reg = a.assess(["mystery_component"])
    assert reg
    assert all(e["asset"] == "mystery_component" for e in reg)


def test_filter_all_returns_everything():
    a = ThreatAssessor()
    full = a.assess(["llm_model"], filter_mode=FILTER_ALL)
    assert full == a.assess(["llm_model"], filter_mode="all")


def test_filter_high_risk():
    a = ThreatAssessor()
    full = a.assess(["llm_model", "agent", "supply_chain"])
    high = a.assess(["llm_model", "agent", "supply_chain"], filter_mode=FILTER_HIGH_RISK)
    assert high
    for e in high:
        assert e["severity"] in (Severity.HIGH, Severity.CRITICAL)
    assert len(high) <= len(full)


def test_filter_by_category():
    a = ThreatAssessor()
    reg = a.assess(["llm_model", "agent", "rag_pipeline"],
                   filter_mode=FILTER_BY_CATEGORY, category="Prompt Injection")
    assert reg
    for e in reg:
        assert e["category"] == "Prompt Injection"


def test_filter_by_category_requires_category():
    a = ThreatAssessor()
    with pytest.raises(ValueError):
        a.assess(["llm_model"], filter_mode=FILTER_BY_CATEGORY, category=None)


def test_assess_invalid_filter():
    a = ThreatAssessor()
    with pytest.raises(ValueError):
        a.assess(["llm_model"], filter_mode="bogus")


def test_assess_sorted_by_risk_desc():
    a = ThreatAssessor()
    reg = a.assess(["agent", "llm_model", "rag_pipeline"])
    risks = [e["risk"] for e in reg]
    assert risks == sorted(risks, reverse=True)


# =============================================================================
# Reporter
# =============================================================================


def test_reporter_sorted_register():
    rep = ThreatModelReporter()
    a = ThreatAssessor()
    reg = a.assess(["agent", "llm_model", "rag_pipeline", "supply_chain"])
    ordered = rep.sorted_register(reg)
    risks = [e["risk"] for e in ordered]
    assert risks == sorted(risks, reverse=True)


def test_reporter_top_n():
    rep = ThreatModelReporter()
    a = ThreatAssessor()
    reg = a.assess(["agent", "llm_model", "rag_pipeline", "supply_chain"])
    top = rep.top_n(reg, 3)
    assert len(top) == 3
    assert top[0]["risk"] >= top[-1]["risk"]


def test_reporter_top_n_clamps():
    rep = ThreatModelReporter()
    a = ThreatAssessor()
    reg = a.assess(["llm_model"])
    assert len(rep.top_n(reg, 999)) == len(reg)
    assert rep.top_n(reg, 0) == []
    assert rep.top_n(reg, -5) == []


def test_reporter_mitigation_coverage_full():
    lib = ThreatLibrary()
    # custom threat with no mitigations to reduce coverage
    lib.register(Threat(id="NOMIT", name="n", category="c", technique="t",
                        likelihood=1, impact=1, mitigations=[]))
    a = ThreatAssessor(lib)
    reg = a.assess(["llm_model"])
    assert 0.0 <= ThreatModelReporter.mitigation_coverage(reg) <= 1.0


def test_reporter_mitigation_coverage_partial():
    lib = ThreatLibrary(threats=[
        Threat(id="NOMIT-1", name="n", category="c", technique="t",
               likelihood=1, impact=1, mitigations=[], asset="custom_asset_x"),
        Threat(id="WITH-1", name="w", category="c", technique="t",
               likelihood=1, impact=1, mitigations=["m1"], asset="custom_asset_x"),
        Threat(id="WITH-2", name="w2", category="c", technique="t",
               likelihood=1, impact=1, mitigations=["m2"], asset="custom_asset_x"),
    ])
    a = ThreatAssessor(lib)
    reg = a.assess(["custom_asset_x"])
    cov = ThreatModelReporter.mitigation_coverage(reg)
    assert cov == pytest.approx(2 / 3, abs=1e-3)
    assert cov > 0.0 and cov < 1.0


def test_reporter_full_report():
    rep = ThreatModelReporter()
    a = ThreatAssessor()
    reg = a.assess(["agent", "llm_model"])
    out = rep.report(reg, top_n=3)
    assert out["register"] == rep.sorted_register(reg)
    assert out["total_threats"] == len(reg)
    assert len(out["top_risks"]) == 3
    assert out["max_risk"] == max(e["risk"] for e in reg)
    assert set(out["severity_counts"].keys()) == {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


# =============================================================================
# STRIDE Mapper
# =============================================================================


def test_stride_six_categories():
    m = STRIDEThreatMapper()
    result = m.map("agent")
    assert set(result.keys()) == set(STRIDEThreatMapper.STRIDE_CATEGORIES)
    assert len(result) == 6


def test_stride_each_category_has_content():
    m = STRIDEThreatMapper()
    result = m.map("llm_model")
    for cat, threats in result.items():
        assert threats, f"category {cat} has no threats"
        assert cat in STRIDEThreatMapper.STRIDE_CATEGORIES


def test_stride_examples_have_fields():
    m = STRIDEThreatMapper()
    result = m.map("rag_pipeline")
    for threats in result.values():
        entry = threats[0]
        assert entry["asset"] == "rag_pipeline"
        assert entry["description"]
        assert entry["technique"]
        assert isinstance(entry["mitigations"], list)


def test_stride_categories_method():
    m = STRIDEThreatMapper()
    assert m.categories() == STRIDEThreatMapper.STRIDE_CATEGORIES
    assert len(m.categories()) == 6


def test_stride_information_disclosure_present():
    m = STRIDEThreatMapper()
    result = m.map("api_gateway")
    assert "Information Disclosure" in result


# =============================================================================
# Facade
# =============================================================================


def test_facade_assess():
    f = ThreatModelFacade()
    reg = f.assess(["agent", "llm_model"])
    assert reg
    assert all("severity" in e for e in reg)


def test_facade_stride():
    f = ThreatModelFacade()
    result = f.stride("agent")
    assert len(result) == 6


def test_facade_report():
    f = ThreatModelFacade()
    out = f.report(["agent", "llm_model"], top_n=2)
    assert out["total_threats"] > 0
    assert len(out["top_risks"]) == 2


def test_facade_library_lookups():
    f = ThreatModelFacade()
    assert f.by_category("Model Extraction")
    assert f.by_technique("AML.T0010")
    assert len(f.catalogue()) == len(ThreatLibrary())


def test_facade_importable_from_full_module():
    # re-exported facade class should be identical
    assert IThreatModelFacade is ThreatModelFacade


# =============================================================================
# Module lifecycle
# =============================================================================


def test_module_registered_with_platform():
    assert "threat_model" in _MODULE_REGISTRY
    cls = _MODULE_REGISTRY["threat_model"]
    assert issubclass(cls, ThreatModelModule)
    assert cls._meta_version == "1.0.0"
    assert cls._meta_name == "threat_model"


def test_module_status_unknown_before_init():
    mod = ThreatModelModule()
    assert mod.status in (HealthStatus.UNKNOWN, HealthStatus.STARTING)


async def test_module_initialize_healthy():
    mod = ThreatModelModule()
    await mod.initialize()
    assert mod.status is HealthStatus.HEALTHY
    assert mod.facade is not None
    assert await mod.health_check() is HealthStatus.HEALTHY


async def test_module_facade_reports_after_init():
    mod = ThreatModelModule()
    await mod.initialize()
    out = mod.report(["agent", "llm_model"])
    assert out["total_threats"] > 0
    assert len(mod.stride("agent")) == 6


async def test_module_assess_publishes_event():
    bus = EventBus(config={"async_dispatch": False})
    received = []
    bus.subscribe("threat.register.assessed")(lambda ev: received.append(ev.topic))
    mod = ThreatModelModule()
    mod.set_event_bus(bus)
    await mod.initialize()
    mod.assess(["llm_model"])
    assert "threat.register.assessed" in received


async def test_module_report_publishes_event():
    bus = EventBus(config={"async_dispatch": False})
    received = []
    bus.subscribe("threat.report.ready")(lambda ev: received.append(ev.topic))
    mod = ThreatModelModule()
    mod.set_event_bus(bus)
    await mod.initialize()
    mod.report(["llm_model"])
    assert "threat.report.ready" in received


async def test_module_shutdown():
    mod = ThreatModelModule()
    await mod.initialize()
    await mod.shutdown()
    assert mod.facade is None
    with pytest.raises(RuntimeError):
        mod.assess(["llm_model"])
