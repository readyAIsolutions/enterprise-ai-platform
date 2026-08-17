"""Tests for the automation_triage module (task-triage ladder + wrong-layer/scoping guards)."""
from __future__ import annotations

import asyncio

from enterprise.modules.automation_triage import (
    AutomationLayer, TriageAction, create_automation_triage_module,
    detect_wrong_layer, scope_for_one_client, triage_task,
    what_not_to_automate,
)


# --- LADDER: WHAT TO AUTOMATE (SjlCJIU9ODs) ---


def test_low_volume_prototype_stays_at_raw_layer():
    dec = triage_task("summarize a one-off document", {"volume": 1, "repeatable": False})
    assert dec.action is TriageAction.SERVE_RAW
    assert dec.ladder_level is AutomationLayer.LAYER_0_RAW_OUTPUT
    assert dec.reasons  # has a reason


def test_repeatable_high_volume_wraps_into_flow():
    dec = triage_task(
        "triage incoming customer support tickets",
        {"volume": 200, "repeatable": True, "flow_ready": True},
    )
    assert dec.action is TriageAction.WRAP_IN_FLOW
    assert dec.ladder_level is AutomationLayer.LAYER_2_CONTEXT_FLOW


def test_flow_with_learning_data_builds_system():
    dec = triage_task(
        "route support tickets and learn from resolutions",
        {"volume": 300, "repeatable": True, "flow_ready": True,
         "learning_data": True},
    )
    assert dec.action is TriageAction.BUILD_SYSTEM
    assert dec.ladder_level is AutomationLayer.LAYER_3_LEARNING_SYSTEM


def test_judgment_heavy_task_kept_human():
    dec = triage_task(
        "negotiate enterprise contract pricing with a client",
        {"volume": 50, "repeatable": True, "flow_ready": True,
         "judgment_needed": 3, "cost_of_error": "high"},
    )
    assert dec.action is TriageAction.KEEP_HUMAN


def test_judgment_keyword_detection_from_task_text():
    # "design strategy" carries taste/judgment signals picked from the task string.
    dec = triage_task(
        "design the brand strategy for the launch",
        {"volume": 10, "repeatable": True, "flow_ready": True,
         "cost_of_error": "high"},
    )
    assert dec.action is TriageAction.KEEP_HUMAN


# --- WRONG LAYER (956DPSPX4wg) ---


def test_detect_wrong_layer_undervalued_raw_output():
    report = detect_wrong_layer(
        "triage incoming customer support tickets",
        AutomationLayer.LAYER_0_RAW_OUTPUT,
        {"volume": 200, "repeatable": True, "flow_ready": True},
    )
    assert report.wrong_layer is True
    assert report.suggested_layer is AutomationLayer.LAYER_2_CONTEXT_FLOW


def test_detect_wrong_layer_matches_when_at_or_above():
    report = detect_wrong_layer(
        "triage incoming customer support tickets",
        AutomationLayer.LAYER_3_LEARNING_SYSTEM,
        {"volume": 200, "repeatable": True, "flow_ready": True},
    )
    assert report.wrong_layer is False


def test_detect_wrong_layer_flags_over_automation_of_judgment_task():
    report = detect_wrong_layer(
        "negotiate enterprise contract pricing",
        2,  # treated as LAYER_2_CONTEXT_FLOW
        {"judgment_needed": 3, "cost_of_error": "high"},
    )
    assert report.wrong_layer is True
    assert report.suggested_layer is None  # nothing should be automated away


# --- WHAT NOT TO AUTOMATE (ZMDXs59Ntjc) ---


def test_what_not_to_automate_repeatable_mechanics_yes():
    dec = what_not_to_automate(
        "convert invoice PDFs to csv rows",
        {"volume": 400, "repeatable": True},
    )
    assert dec.automate is True
    assert dec.keep_human is False


def test_what_not_to_automate_judgment_stays_human():
    dec = what_not_to_automate(
        "approve the final editorial direction",
        {"volume": 10, "repeatable": True},
    )
    assert dec.automate is False
    assert dec.keep_human is True


# --- ONE CLIENT SCOPING GUARD (AZ1l-oaD3tk) ---


def test_scope_guard_defer_production_when_no_client():
    verdict = scope_for_one_client(
        ["scrape leads", "multi-tenancy", "kubernetes", "soc2 compliance"],
        {"clients": 0, "validated_use_case": False},
    )
    assert verdict.approved is False
    assert verdict.action == "defer_production"
    assert any("multi-tenanc" in d for d in verdict.drop)
    assert "scrape leads" in verdict.keep


def test_scope_guard_proceed_with_validated_one_client():
    verdict = scope_for_one_client(
        ["scrape leads", "kubernetes"],
        {"clients": 1, "validated_use_case": True},
    )
    assert verdict.approved is True
    assert verdict.action == "proceed"


def test_scope_guard_no_production_features_proceeds():
    verdict = scope_for_one_client(
        ["scrape leads", "dedupe contacts"],
        {"clients": 0, "validated_use_case": False},
    )
    assert verdict.approved is True
    assert verdict.drop == []


def test_scope_guard_accepts_comma_string_input():
    verdict = scope_for_one_client(
        "scrape leads, kubernetes, multi-tenancy",
        {"clients": 0, "validated_use_case": False},
    )
    assert verdict.approved is False


# --- MODULE LIFECYCLE + REGISTRATION ---


def test_module_initializes_and_health():
    m = create_automation_triage_module({})
    asyncio.run(m.initialize())
    assert asyncio.run(m.health_check()).value == "healthy"
    asyncio.run(m.shutdown())


def test_module_facade_triage():
    m = create_automation_triage_module({})
    asyncio.run(m.initialize())
    out = m.triage("triage incoming support tickets",
                   {"volume": 200, "repeatable": True, "flow_ready": True})
    assert out["action"] == "wrap_in_flow"
    assert out["ladder_level"] == 2


def test_module_registered_in_registry():
    from enterprise.platform_kernel import _MODULE_REGISTRY
    assert "automation_triage" in _MODULE_REGISTRY
