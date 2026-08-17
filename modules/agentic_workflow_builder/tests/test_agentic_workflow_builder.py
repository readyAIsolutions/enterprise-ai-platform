"""Tests for the agentic_workflow_builder module.

Grounded in the JEVanClief transcript *"Claude Code + Cursor: Making Agentic
workflows with an Agentic workflow!"* — composing parser/auditor/framework-loader
agents, ParsedStatement schema, to-do-list generation, monolithic-to-modules
refactoring, and cost estimation.
"""

from __future__ import annotations

import json

import pytest

from enterprise.modules.agentic_workflow_builder import (
    AgentSpec,
    AgenticWorkflowBuilderModule,
    ParsedStatement,
    Workflow,
    build_workflow,
    create_agentic_workflow_builder_module,
    create_todo_list,
    decompose_module,
    estimate_cost,
    statement_matches,
    workflow_stats,
)
from enterprise.modules.agentic_workflow_builder.agentic_workflow_builder import (
    AUDITOR_AGENT,
    FRAMEWORK_LOADER_AGENT,
    PARSER_AGENT,
    ENVIRONMENTS,
    TOOLS,
)


def test_constants_match_transcript_tools_and_environments():
    assert "claude_code" in TOOLS
    assert "cursor" in TOOLS
    assert "wsl" in ENVIRONMENTS
    assert "powershell" in ENVIRONMENTS


def test_agent_spec_roundtrip():
    agent = AgentSpec(
        name="framework_loader",
        role=FRAMEWORK_LOADER_AGENT,
        system_prompt="Break the source PDF into its specific parts.",
        tools=["claude_code", "cursor"],
    )
    assert agent.to_dict()["role"] == FRAMEWORK_LOADER_AGENT
    assert AgentSpec.from_dict(agent.to_dict()) == agent


def test_agent_spec_rejects_unknown_tool():
    with pytest.raises(ValueError):
        AgentSpec(name="bad", role=PARSER_AGENT, tools=["vim"])


def test_build_workflow_composes_sections():
    parser = AgentSpec(name="parser", role=PARSER_AGENT)
    auditor = AgentSpec(name="auditor", role=AUDITOR_AGENT)
    loader = AgentSpec(
        name="framework_loader",
        role=FRAMEWORK_LOADER_AGENT,
        tools=["cursor"],
    )
    wf = build_workflow("compliance_pipeline", parser, auditor, loader)
    assert len(wf.agents) == 3
    assert wf.roles == [PARSER_AGENT, AUDITOR_AGENT, FRAMEWORK_LOADER_AGENT]
    stats = workflow_stats(wf)
    assert stats["agent_count"] == 3
    assert stats["name"] == "compliance_pipeline"


def test_workflow_duplicate_agent_rejected():
    wf = Workflow(name="wf")
    wf.add_agent(AgentSpec(name="parser", role=PARSER_AGENT))
    with pytest.raises(ValueError):
        wf.add_agent(AgentSpec(name="parser", role=AUDITOR_AGENT))


def test_todo_list_created_before_editing():
    steps = [
        "Read through the source lines",
        "Update the parsed statement documents",
        "Generate a new README",
    ]
    todo = create_todo_list("Refactor the compliance codebase", steps)
    assert len(todo) == 3
    assert all(item["done"] is False for item in todo)
    assert todo[0]["index"] == 1
    assert todo[2]["goal"] == "Refactor the compliance codebase"


def test_todo_list_requires_goal():
    with pytest.raises(ValueError):
        create_todo_list("   ", ["a"])


def test_parsed_statement_fields_match_transcript():
    statement = ParsedStatement(
        individual="individual",
        description="description",
        category="compliance",
        field="list",
        compliance=["field_a", "field_b"],
    )
    data = statement.to_dict()
    assert set(data.keys()) == {
        "individual",
        "description",
        "category",
        "field",
        "compliance",
    }
    # "doing the list as a string" serialisation is supported.
    as_string = statement.to_json(list_as_string=True)
    parsed = json.loads(as_string)
    assert parsed["compliance"] == "field_a, field_b"
    # And it round-trips back to a real list.
    assert ParsedStatement.from_dict(parsed).compliance == ["field_a", "field_b"]


def test_parsed_statement_matches_field_by_field():
    reference = ParsedStatement(
        individual="i",
        description="d",
        category="compliance",
        field="list",
        compliance=["a", "b"],
    )
    good = ParsedStatement(
        individual="i", description="d", category="compliance", field="list",
        compliance=["a", "b"],
    )
    bad = ParsedStatement(
        individual="i", description="d", category="compliance", field="list",
        compliance=["a", "c"],
    )
    assert statement_matches(good, reference) is True
    assert statement_matches(bad, reference) is False


def test_decompose_monolith_splits_into_initiating_modules(tmp_path):
    source = "\n".join(
        [
            "import json",
            "",
            "def load_framework(path):",
            "    return []",
            "",
            "class ParsedStatement:",
            "    pass",
            "",
            "def main():",
            "    pass",
        ]
    )
    modules = decompose_module(source, filename="massive.py")
    names = [m["name"] for m in modules]
    # The monolithic file is broken into at least two named module sections.
    assert len(modules) >= 2
    assert "core" in names
    out = tmp_path / "modules"
    out.mkdir()
    for i, m in enumerate(modules):
        (out / f"module_{i}_{m['name']}.py").write_text(m["source"])
    written = list(out.glob("*.py"))
    assert len(written) == len(modules)


def test_decompose_monolith_requires_source():
    with pytest.raises(ValueError):
        decompose_module("   ")


def test_estimate_cost_api_vs_pro():
    api = estimate_cost(hours=1.0, plan="api")
    assert api["billing_model"] == "per_token"
    assert api["estimated_usd"] == 5.0
    pro = estimate_cost(hours=1.0, plan="pro")
    assert pro["billing_model"] == "monthly_subscription"
    # Pro account is capped by its monthly token limit / subscription.
    assert pro["estimated_usd"] <= pro["monthly_cap_usd"]


def test_estimate_cost_bad_plan():
    with pytest.raises(ValueError):
        estimate_cost(hours=1.0, plan="grok")


async def test_module_lifecycle():
    m = create_agentic_workflow_builder_module()
    await m.initialize()
    assert m.status.value == "healthy"
    assert (await m.health_check()).value == "healthy"
    await m.shutdown()
    assert (await m.health_check()).value == "stopping"


async def test_module_facade_and_event_bus():
    m = create_agentic_workflow_builder_module(
        {"environment": "powershell", "plan": "pro"}
    )
    await m.initialize()

    events = []

    class FakeBus:
        def publish(self, event):
            events.append(event)

    m.set_event_bus(FakeBus())
    agent = m.create_agent("parser", PARSER_AGENT)
    wf = m.compose_workflow("pipeline", [agent])
    todo = m.make_todo_list("goal", ["step one"])
    stmt = m.make_statement(
        "i", "d", "compliance", field="list", compliance=["a"]
    )
    split = m.split_monolith("import json\n\nclass ParsedStatement:\n    pass\n")
    cost = m.cost(hours=2.0)

    assert len(wf.agents) == 1
    assert len(todo) == 1
    assert stmt.category == "compliance"
    assert len(split) >= 1
    assert cost["plan"] == "pro"
    assert m.stats()["environment"] == "powershell"

    # Event publishing is guarded: bus present => events fired.
    topics = [e.topic for e in events]
    assert "agentic_workflow_builder.agent_created" in topics
    assert "agentic_workflow_builder.workflow_composed" in topics

    # With no event bus set, publish is a no-op (never raises).
    m2 = create_agentic_workflow_builder_module()
    await m2.initialize()
    m2.create_agent("loader", FRAMEWORK_LOADER_AGENT)
    assert m2.stats()["status"] == "healthy"
    await m2.shutdown()


async def test_module_bad_config_fails_initialize():
    m = create_agentic_workflow_builder_module({"environment": "sandbox"})
    with pytest.raises(ValueError):
        await m.initialize()
    assert m.status.value == "unhealthy"
