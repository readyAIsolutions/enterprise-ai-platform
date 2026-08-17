"""Tests for the multiplayer_agent_triage module."""

from __future__ import annotations

import json

import pytest

from enterprise.modules.multiplayer_agent_triage import (
    MultiplayerAgentTriageModule,
    MultiplayerTriageEngine,
    create_multiplayer_agent_triage_module,
    summarize_incidents,
)
from enterprise.modules.multiplayer_agent_triage.multiplayer_agent_triage import (
    PROBLEM_TYPES,
    WIN_TYPES,
    analyze_token_spend,
    classify_problem,
    classify_win,
)


# ---------------------------------------------------------------------------
# Problem classification (grounded in transcript failures)
# ---------------------------------------------------------------------------


def test_classify_deployment_blob_naming():
    # Transcript: "we think it's an Azure blob storage issue ... certain file
    # names are just not deploying well ... it gets stuck in thinking mode."
    result = classify_problem(
        {
            "symptom": "agent stuck in thinking mode because the deployment of "
            "the file names via azure blob storage is not deploying well"
        }
    )
    assert result.problem_type == "deployment"
    assert result.is_critical
    assert "blob" in result.matched_signals


def test_classify_sandbox_failure():
    # Transcript: "we get these issues here where it can't return the turn ...
    # it reading a file, failing the sandbox. We did create a nice fallback, so
    # it doesn't crash the whole system."
    result = classify_problem(
        {"symptom": "it can't return the turn because reading a file is failing the sandbox"}
    )
    assert result.problem_type == "sandbox"
    assert result.is_critical
    assert "fallback" in result.recommended_action


def test_classify_read_size():
    # Transcript: "we realized that there's an issue with how large of a read
    # each request would be cuz we're containerizing all of these to keep them
    # separate."
    result = classify_problem(
        {"symptom": "how large of a read each request would be in the container"}
    )
    assert result.problem_type == "read_size"


def test_classify_workspace_file_not_showing():
    # Transcript: "in this case, it didn't show the workspace files even though
    # it had access to it. ... just a simple kind of glitch in the system."
    result = classify_problem(
        {"symptom": "workspace files didn't show even though it had access"}
    )
    assert result.problem_type == "file_visibility"


def test_classify_unknown_and_confidence():
    result = classify_problem({"symptom": "no obvious keywords here at all"})
    assert result.problem_type == "unknown"
    assert result.confidence == 0.0
    assert not result.is_critical


def test_classify_problem_severity_hint_overrides():
    result = classify_problem(
        {"symptom": "stuck in thinking mode", "severity": "low"}
    )
    assert result.problem_type == "stuck_thinking"
    assert result.severity == "low"


# ---------------------------------------------------------------------------
# Win classification (grounded in transcript wins)
# ---------------------------------------------------------------------------


def test_classify_win_token_efficiency():
    # Transcript: users "have barely spent $30 in API fees" through hundreds of
    # files, "with tool calls, that's with reading the workspaces."
    record = classify_win(
        {
            "description": "all the alpha users together barely spent any api fee; "
            "very token efficient through hundreds of files and tool calls",
            "metrics": {"cost_usd": 30},
        }
    )
    assert record is not None
    assert record.win_type == "token_efficiency"
    assert record.metrics["cost_usd"] == 30


def test_classify_win_knowledge_corpus():
    record = classify_win(
        {"description": "uploaded a markdown knowledge corpus the agent can research and recommend from"}
    )
    assert record is not None
    assert record.win_type == "knowledge_corpus"


def test_classify_win_community_template():
    record = classify_win(
        {"description": "a choose your own adventure template with memories and states"}
    )
    assert record is not None
    assert record.win_type == "community_template"


def test_classify_win_returns_none_when_no_match():
    assert classify_win({"description": "zzz unmatched qqq"}) is None


# ---------------------------------------------------------------------------
# Token spend analysis
# ---------------------------------------------------------------------------


def test_analyze_token_spend_totals_and_per_agent():
    summary = analyze_token_spend(
        [
            {"agent": "claude", "tokens": 1000, "cost_usd": 1.0},
            {"agent": "claude", "tokens": 2000, "cost_usd": 2.0},
            {"agent": "gemini", "tokens": 500, "cost_usd": 0.5},
        ]
    )
    assert summary["total_tokens"] == 3500
    assert summary["total_cost_usd"] == 3.5
    assert summary["num_calls"] == 3
    assert summary["per_agent"]["claude"]["tokens"] == 3000
    assert summary["per_agent"]["gemini"]["cost_usd"] == 0.5


def test_analyze_token_spend_shared_default():
    summary = analyze_token_spend([{"tokens": 10}, {"tokens": 5}])
    assert summary["per_agent"]["shared"]["tokens"] == 15


# ---------------------------------------------------------------------------
# Engine aggregation + summary
# ---------------------------------------------------------------------------


def test_engine_triage_and_summary():
    engine = MultiplayerTriageEngine()
    engine.triage({"symptom": "azure blob deployment failing"})
    engine.triage({"symptom": "workspace files not showing"})
    engine.record_win(
        {"description": "shared workspace lets my team collaborate on files"}
    )

    s = engine.summary()
    assert s["problems"]["total"] == 2
    assert s["problems"]["by_type"]["deployment"] == 1
    assert s["problems"]["by_type"]["file_visibility"] == 1
    assert s["wins"]["total"] == 1
    assert s["wins"]["by_type"]["collaboration"] == 1
    # Both deployment (high) and file_visibility (escalated) are critical.
    assert len(s["critical_items"]) == 2
    assert set(s["problems"]["critical_types"]) == {
        "deployment",
        "file_visibility",
    }


def test_engine_critical_items():
    engine = MultiplayerTriageEngine()
    engine.triage({"symptom": "sandbox failure can't return the turn"})
    engine.triage({"symptom": "minor token cost check"})
    critical = engine.critical_items()
    assert len(critical) == 1
    assert critical[0].problem_type == "sandbox"


def test_summarize_incidents():
    p1 = classify_problem({"symptom": "deployment failing azure blob"})
    w1 = classify_win({"description": "explainer video workflow process automation"})
    s = summarize_incidents([p1], [w1])
    assert s["problems"]["total"] == 1
    assert s["wins"]["by_type"]["workflow_automation"] == 1


# ---------------------------------------------------------------------------
# Module lifecycle + facade + IO
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_module_initialize_healthy():
    mod = create_multiplayer_agent_triage_module()
    await mod.initialize()
    assert mod.status.value == "healthy"
    assert mod.name == "multiplayer_agent_triage"
    assert mod.version == "1.0.0"
    assert await mod.health_check() == mod.status
    await mod.shutdown()
    assert mod.status.value == "stopping"


@pytest.mark.asyncio
async def test_module_triage_requires_init():
    mod = MultiplayerAgentTriageModule()
    with pytest.raises(RuntimeError):
        mod.triage({"symptom": "x"})
    await mod.shutdown()


@pytest.mark.asyncio
async def test_module_facade_and_event_bus(tmp_path):
    mod = create_multiplayer_agent_triage_module({"publish_events": True})
    published = []

    class FakeBus:
        def publish(self, event):
            published.append(event)

    mod.set_event_bus(FakeBus())
    await mod.initialize()

    r = mod.triage({"symptom": "stuck in thinking mode after deployment"})
    assert r.problem_type in ("deployment", "stuck_thinking")
    w = mod.record_win({"description": "team collaboration shared workspace"})
    assert w is not None
    s = mod.summary()
    assert s["problems"]["total"] == 1
    assert s["wins"]["total"] == 1

    # Events should be published on the bus.
    assert len(published) == 2
    topics = {e.topic for e in published}
    assert "multiplayer_agent_triage.problem" in topics
    assert "multiplayer_agent_triage.win" in topics

    # Persist the summary to a tmp file to exercise IO.
    out = tmp_path / "summary.json"
    out.write_text(json.dumps(s), encoding="utf-8")
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["problems"]["total"] == 1

    await mod.shutdown()


@pytest.mark.asyncio
async def test_module_health_check():
    mod = create_multiplayer_agent_triage_module()
    await mod.initialize()
    health = await mod.health_check()
    assert health.is_operational()
    await mod.shutdown()


@pytest.mark.asyncio
async def test_module_config_defaults():
    # The @module decorator records config_defaults on the class metadata.
    assert MultiplayerAgentTriageModule._meta_config["max_problems_to_keep"] == 1000
    assert MultiplayerAgentTriageModule._meta_config["publish_events"] is True
    # Passed-in config is stored on the instance.
    mod = create_multiplayer_agent_triage_module({"publish_events": False})
    assert mod.config["publish_events"] is False


def test_problem_and_win_category_tables_populated():
    # Ensure the grounded category tables contain the expected entries.
    for expected in (
        "deployment",
        "sandbox",
        "read_size",
        "file_visibility",
        "stuck_thinking",
        "token_usage",
    ):
        assert expected in PROBLEM_TYPES
    for expected in (
        "token_efficiency",
        "knowledge_corpus",
        "community_template",
        "collaboration",
        "workflow_automation",
    ):
        assert expected in WIN_TYPES
