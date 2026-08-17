"""Unit tests for the claude_code_ui_harness module (network-free, stdlib)."""
from __future__ import annotations

import asyncio
from pathlib import Path

from enterprise.modules.claude_code_ui_harness import (
    ClaudeCodeUiHarness, ClaudeSession, PlanPhase, PlanPhaseKind, PrdDocument,
    SessionStatus, UsageRecord, ViewMode, WorkspaceNode,
    create_claude_code_ui_harness_module,
)


def _make_workspace(tmp_path: Path) -> Path:
    """A tiny script->animation-style workspace like the transcript's own
    build (structure, folders, scripts)."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scenes").mkdir()
    (tmp_path / "scripts" / "intro.py").write_text("print('intro')\n")
    (tmp_path / "scripts" / "outro.py").write_text("print('outro')\n")
    (tmp_path / "readme.md").write_text("# workflow\n")
    return tmp_path


def test_harness_sessions_control_and_observe():
    """Grounds 'control Claude' + 'monitor/observe how the agents are working'."""
    h = ClaudeCodeUiHarness()
    session = h.start_session("s1", "frontend build", tool="cli")
    assert session.status == SessionStatus.RUNNING
    assert h.observe("s1") is session
    assert h.list_sessions()[0].label == "frontend build"
    h.sessions.mark("s1", SessionStatus.COMPLETED)
    assert h.observe("s1").status == SessionStatus.COMPLETED


def test_usage_tracking_favors_subscription_savings():
    """Grounds 'use your Anthropic subscription, so it doesn't cost as much'.
    API-flagged usage carries a cost; subscription work does not."""
    h = ClaudeCodeUiHarness()
    h.start_session("s1", "sub work")
    h.start_session("s2", "api work")
    h.track_usage(UsageRecord("s1", messages=10, input_tokens=5000,
                              output_tokens=2000, via_api=False))
    h.track_usage(UsageRecord("s2", messages=5, input_tokens=2000,
                              output_tokens=1000, via_api=True))
    summary = h.usage_summary()
    assert summary["messages"] == 15
    assert summary["subscription_tokens"] == 7000
    assert summary["api_tokens"] == 3000
    assert summary["estimated_api_cost"] > 0
    assert summary["subscription_savings"] == summary["estimated_api_cost"]


def test_workspace_navigation_folders_and_mind_map(tmp_path):
    """Grounds navigating 'not just simple folders ... but maybe something
    like a mind map or a web map'."""
    ws = _make_workspace(tmp_path)
    h = ClaudeCodeUiHarness(workspace_root=ws)

    folders = h.view(ViewMode.FOLDERS)
    assert isinstance(folders, list) and folders
    # workspace has 2 folders + a file at depth 0
    top_names = {n.name for n in folders}
    assert {"scripts", "scenes", "readme.md"} <= top_names

    paths = h.workspace_paths()
    assert any(p.endswith("intro.py") for p in paths)

    mind = h.view(ViewMode.MIND_MAP)
    assert isinstance(mind, WorkspaceNode)
    assert mind.links  # connected map view built from the same tree


def test_workspace_navigation_missing_dir():
    h = ClaudeCodeUiHarness(workspace_root="/does/not/exist")
    assert h.view(ViewMode.FOLDERS) == []
    assert h.workspace_paths() == []


def test_prd_build_and_render_phased_early_to_late():
    """Grounds 'make a PRD markdown ... breaks down steps and structure for
    early phase to late phase' rather than 'build the whole thing at once'."""
    h = ClaudeCodeUiHarness()
    doc = h.build_prd(
        title="Claude Code Front End",
        goal="Control and observe Claude Code agents through a custom UI.",
        stacks=["next.js", "claude cli"],
        integrations=["anthropic subscription", "github"],
        targeting="early adopters building AI animation workflows",
        phases=[
            PlanPhase("scaffold", PlanPhaseKind.EARLY, ["init repo"], ["app/"]),
            PlanPhase("wire", PlanPhaseKind.MID, ["connect cli"], ["runtime/"]),
            PlanPhase("polish", PlanPhaseKind.LATE, ["ship ui"], ["dist/"]),
        ],
    )
    md = h.render_prd(doc)
    assert "# Claude Code Front End — Product Requirements Document" in md
    assert "## Stacks" in md and "- next.js" in md
    assert "## Integrations" in md
    assert "## Phases (early -> late)" in md
    # ordering is early, mid, late
    assert md.index("early phase") < md.index("mid phase") < md.index("late phase")


def test_prd_auditor_flags_ungrounded_prd():
    """Grounds 'feed this into another version of Claude ... act as that
    auditor and it can kind of redo it there'."""
    h = ClaudeCodeUiHarness()
    doc = PrdDocument(title="vague", goal="build it",
                      stacks=[], integrations=[])
    findings = h.audit_prd(doc)
    assert any("No stacks" in f.message for f in findings)
    assert any("early" in f.message for f in findings)  # not staged early->late


def test_module_lifecycle_and_event_bus_publish():
    """Module wraps the harness with HEALTHY lifecycle and optional events."""
    m = create_claude_code_ui_harness_module(
        {"workspace_root": ".", "max_depth": 3}
    )
    asyncio.run(m.initialize())
    assert m.status.value == "healthy"
    assert "HEALTHY" in str(asyncio.run(m.health_check()))

    # no event bus wired => publish is a safe no-op
    m.start_session("s1", "test")
    summary = m.usage_summary()
    assert summary["messages"] == 0

    # wiring an event bus lets the harness publish Event(...)
    class _FakeBus:
        def __init__(self):
            self.events = []

        def publish(self, event):
            self.events.append(event)

    bus = _FakeBus()
    m.set_event_bus(bus)
    m.track_usage(UsageRecord("s1", messages=3, input_tokens=100,
                              output_tokens=50, via_api=False))
    assert any(e.topic == "claude_code_ui_harness.usage.recorded"
               for e in bus.events)

    asyncio.run(m.shutdown())
    assert m.harness is None
    assert m.status.value == "unknown"