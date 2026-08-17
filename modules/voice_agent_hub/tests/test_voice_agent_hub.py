"""Unit tests for the voice_agent_hub module (no network, real assertions)."""
from __future__ import annotations

import asyncio

import pytest

from enterprise.platform_kernel import HealthStatus

from enterprise.modules.voice_agent_hub import (
    CodingAgent,
    GroupCallSession,
    Intent,
    KeywordEngine,
    KeywordRule,
    Participant,
    PsychometricWorkload,
    Scale,
    VoiceAgentHub,
    VoiceAgentHubModule,
    VoiceCommand,
    VoiceCommandStatus,
    create_voice_agent_hub_module,
)


# --- keyword engine ---------------------------------------------------------
def test_keyword_engine_matches_intent_by_phrase():
    engine = KeywordEngine()
    matched = engine.match("what scales are we missing from the engine?")
    assert any(r.intent == Intent.REVIEW_SCALES for r in matched)


def test_keyword_engine_returns_empty_for_unrelated_text():
    engine = KeywordEngine()
    assert engine.match("hello, how is everyone doing today?") == []


def test_keyword_engine_case_insensitive():
    engine = KeywordEngine()
    matched = engine.match("What Scales Are We Missing?")
    assert any(r.intent == Intent.REVIEW_SCALES for r in matched)


def test_keyword_engine_custom_rule_registration():
    engine = KeywordEngine()
    rule = KeywordRule(keywords=("ship it",), intent=Intent.UNKNOWN, description="x")
    engine.register(rule)
    matched = engine.match("please ship it now")
    assert rule in matched


# --- psychometric workload --------------------------------------------------
def test_workload_starts_with_10_built_in_scales():
    workload = PsychometricWorkload.with_defaults()
    assert workload.built_in_count == 10
    assert workload.has_scale("ECE-1")
    assert workload.has_scale("RWA")


def test_workload_suggests_missing_dark_triad_scales():
    workload = PsychometricWorkload.with_defaults()
    missing = workload.suggest_missing_scales()
    abbrs = [s.abbreviation for s in missing]
    assert "Dark Triad" in abbrs
    assert "Machiavellianism" in abbrs
    assert workload.built_in_count == 10  # suggestion does not mutate


def test_workload_expands_from_10_to_12():
    workload = PsychometricWorkload.with_defaults()
    missing = workload.suggest_missing_scales()
    added = workload.expand_catalog(missing)
    assert added >= 2
    assert workload.built_in_count == 10 + added


def test_workload_add_scale_is_idempotent():
    workload = PsychometricWorkload.with_defaults()
    scale = Scale("Dark Triad", "Dark Triad", "composite")
    assert workload.add_scale(scale) is True
    assert workload.add_scale(scale) is False  # duplicate ignored


def test_workload_frontend_review_flags_new_scales():
    workload = PsychometricWorkload.with_defaults()
    workload.add_scale(Scale("Dark Triad", "Dark Triad", "composite"))
    components = workload.review_front_end()
    assert any("Dark Triad" in c for c in components)


# --- voice command parsing & orchestration ----------------------------------
def test_parse_utterance_creates_command_and_records_transcript():
    hub = VoiceAgentHub()
    commands = hub.parse_utterance("what scales are we missing?", speaker="K")
    assert len(commands) >= 1
    assert commands[0].speaker == "K"
    assert commands[0].intent == Intent.REVIEW_SCALES
    assert hub.session.utterance_count == 1
    assert hub.command_count == len(commands)


def test_parse_utterance_no_match_returns_empty():
    hub = VoiceAgentHub()
    assert hub.parse_utterance("nice weather today", speaker="K") == []
    assert hub.utterance_count == 1  # still recorded


def test_dispatch_targets_speakers_own_agent():
    agent = CodingAgent(name="claude-k", local_data_allowed=True)
    k = Participant(name="K", agent=agent)
    hub = VoiceAgentHub()
    hub.add_participant(k)

    commands = hub.parse_utterance("what scales are we missing?", speaker="K")
    cmd = commands[0]
    assert cmd.target_agent == "claude-k"

    dispatched = hub.dispatch(cmd)
    assert dispatched.status == VoiceCommandStatus.COMPLETED


def test_control_agent_targets_another_participants_agent():
    my_agent = CodingAgent(name="claude-me")
    other_agent = CodingAgent(name="claude-david")
    me = Participant(name="JEVanClief", agent=my_agent)
    david = Participant(name="David McDermott", agent=other_agent)
    hub = VoiceAgentHub()
    hub.add_participant(me)
    hub.add_participant(david)

    commands = hub.parse_utterance(
        "control someone else's Claude Code by voice", speaker="JEVanClief"
    )
    assert any(c.intent == Intent.CONTROL_AGENT for c in commands)
    control = [c for c in commands if c.intent == Intent.CONTROL_AGENT][0]
    assert control.target_agent == "claude-david"


def test_dispatch_unknown_target_fails():
    hub = VoiceAgentHub()
    cmd = VoiceCommand(
        id="cmd-1",
        text="do something",
        speaker="K",
        intent=Intent.UNKNOWN,
        target_agent="nonexistent",
    )
    dispatched = hub.dispatch(cmd)
    assert dispatched.status == VoiceCommandStatus.FAILED


def test_interrupt_running_agent():
    agent = CodingAgent(name="claude-k")
    k = Participant(name="K", agent=agent)
    hub = VoiceAgentHub()
    hub.add_participant(k)

    commands = hub.parse_utterance("what scales are we missing?", speaker="K")
    cmd = commands[0]
    hub.dispatch_async(cmd)  # leave it running

    assert agent.is_busy
    assert hub.interrupt("claude-k") is True
    assert cmd.status == VoiceCommandStatus.INTERRUPTED
    assert not agent.is_busy


def test_interrupt_idle_agent_returns_false():
    agent = CodingAgent(name="claude-k")
    hub = VoiceAgentHub()
    hub.add_agent(agent)
    assert hub.interrupt("claude-k") is False


# --- local data access ------------------------------------------------------
def test_local_data_access_defaults_to_false():
    agent = CodingAgent(name="claude-k")
    hub = VoiceAgentHub()
    hub.add_agent(agent)
    assert hub.can_access_local_data("claude-k") is False


def test_grant_and_revoke_local_data_access():
    agent = CodingAgent(name="claude-k")
    hub = VoiceAgentHub()
    hub.add_agent(agent)
    hub.grant_local_data_access("claude-k")
    assert hub.can_access_local_data("claude-k") is True
    hub.revoke_local_data_access("claude-k")
    assert hub.can_access_local_data("claude-k") is False


# --- keyword-triggered workflow shortcut ------------------------------------
def test_trigger_workflow_parses_and_dispatches():
    agent = CodingAgent(name="claude-k")
    k = Participant(name="K", agent=agent)
    hub = VoiceAgentHub()
    hub.add_participant(k)

    commands = hub.trigger_workflow("what scales are we missing?", speaker="K")
    assert commands
    # all dispatched commands should have completed (no busy agents left)
    assert all(c.status == VoiceCommandStatus.COMPLETED for c in commands)


# --- module lifecycle -------------------------------------------------------
@pytest.mark.asyncio
async def test_module_initialize_sets_healthy():
    module = create_voice_agent_hub_module()
    await module.initialize()
    assert module.status is HealthStatus.HEALTHY
    assert module.hub is not None


@pytest.mark.asyncio
async def test_module_health_check():
    module = create_voice_agent_hub_module()
    await module.initialize()
    assert await module.health_check() is HealthStatus.HEALTHY


@pytest.mark.asyncio
async def test_module_shutdown_sets_stopping():
    module = create_voice_agent_hub_module()
    await module.initialize()
    await module.shutdown()
    assert module.status is HealthStatus.STOPPING


@pytest.mark.asyncio
async def test_module_publishes_only_with_event_bus():
    module = create_voice_agent_hub_module()
    await module.initialize()
    # Without an event bus, facade methods should still work (no crash).
    module.parse_utterance("what scales are we missing?", speaker="K")
    assert module.hub.command_count >= 1


@pytest.mark.asyncio
async def test_module_metadata_from_decorator():
    from enterprise.platform_kernel import _MODULE_REGISTRY

    assert "voice_agent_hub" in _MODULE_REGISTRY
    module = create_voice_agent_hub_module()
    assert module.name == "voice_agent_hub"
    assert module.version == "1.0.0"
    assert module.status is HealthStatus.UNKNOWN  # before initialize


@pytest.mark.asyncio
async def test_module_facade_methods(tmp_path):
    module = create_voice_agent_hub_module({"max_interrupts": 3})
    await module.initialize()

    result = module.run_scale_review(speaker="K")
    assert result["built_in_count"] == 10
    assert result["missing_count"] >= 2

    expansion = module.run_catalog_expansion(speaker="K")
    assert expansion["after_count"] == 10 + expansion["added_count"]

    frontend = module.run_frontend_review(speaker="K")
    assert frontend["missing_count"] >= 0

    # Use tmp_path to confirm tmp IO is available if needed
    marker = tmp_path / "hub_marker.txt"
    marker.write_text("voice_agent_hub")
    assert marker.read_text() == "voice_agent_hub"
