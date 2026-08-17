"""Tests for group_chat_orchestration (multi-participant AI + human group chat).

Grounded in four pulled JE Van Clief transcripts (rWHHnIR30DE group-chat,
0fCQ-4J_jzk cowork, pdoSAWWCDO8 design-handoff, RZ0AcCLVPFA AI-as-compiler).
All tests are pure / network-free.
"""
from __future__ import annotations

import asyncio

from enterprise.modules.group_chat_orchestration import (
    AI, HUMAN, GroupChat, create_group_chat_orchestration_module, start_group,
)
from enterprise.platform_kernel import _MODULE_REGISTRY


def _room():
    return start_group(
        "design_room",
        [
            {"name": "moderator", "role": "driver", "kind": "human"},
            {"name": "curriculum_ai", "role": "curriculum", "kind": "ai"},
            {"name": "critic_ai", "role": "critic", "kind": "ai"},
            {"name": "synthesis_ai", "role": "synthesis", "kind": "ai"},
            {"name": "domain_expert", "role": "domain", "kind": "human"},
        ],
        topic="design a new course curriculum",
    )


def test_start_group_counts_and_moderator():
    chat = _room()
    s = chat.stats()
    assert s["participants"] == 5
    assert s["ai_participants"] == 3      # three of the five are AI (transcript)
    assert s["human_participants"] == 2
    assert chat.moderator == "moderator"  # first human is the driver/moderator


def test_submit_message_returns_handoff_and_advances():
    chat = _room()
    h = chat.submit_message("curriculum_ai", "We should focus on fundamentals.")
    assert h.kind == "turn"
    assert h.from_name == "curriculum_ai"
    assert chat.turns["curriculum_ai"] == 1
    assert len(chat.messages) == 1
    assert h.to_name in chat.order  # mic passed to someone else in the room


def test_next_speaker_round_robin_and_kind_filter():
    chat = _room()
    first = chat.next_speaker(after="moderator")
    # after moderator, round-robin must NOT return moderator first
    assert first != "moderator"
    nxt = chat.next_speaker(after=first)
    assert nxt != first
    # restrict to humans only
    human = chat.next_speaker(after="critic_ai", kind=HUMAN)
    assert chat._participant(human)["kind"] == HUMAN
    ai = chat.next_speaker(after="moderator", kind=AI)
    assert chat._participant(ai)["kind"] == AI


def test_all_ai_read_shared_context():
    # transcript: every AI reads everything the others wrote and reacts
    chat = _room()
    chat.submit_message("domain_expert", "Students already know linear algebra.")
    chat.submit_message("curriculum_ai", "Given that, start with differential eq.")
    chat.submit_message("critic_ai", "Budget says 12 weeks, not 16.")
    # everyone downstream saw all three prior messages (append-only transcript)
    t = chat.transcript()
    assert len(t) == 3
    assert t[2]["text"].startswith("Budget")
    assert chat.turns["critic_ai"] == 1


def test_escalate_to_human_pauses_room_and_resume_gating():
    chat = _room()
    h = chat.escalate_to_human("needs product owner decision", by_participant="curriculum_ai")
    assert h.kind == "escalation"
    assert chat.paused_for == "moderator"
    # non-moderator posting while paused is refused
    try:
        chat.submit_message("curriculum_ai", "keep going?")
        raised = False
    except RuntimeError:
        raised = True
    assert raised
    # moderator may still post, and wrong-actor resume is rejected
    assert chat.resume(by_human="critic_ai") is False
    assert chat.resume(by_human="moderator") is True
    assert chat.paused_for is None
    assert chat.submit_message("curriculum_ai", "ok resuming").kind == "turn"


def test_handoff_to_agent_records_delegation():
    # cowork + design-handoff: human keeps control while work goes to a model
    chat = _room()
    h = chat.handoff_to_agent(
        "moderator", "synthesis_ai",
        payload={"draft": "week 1-3 outline"},
        note="local model handoff",
    )
    assert h.kind == "agent"
    assert h.from_name == "moderator"
    assert h.to_name == "synthesis_ai"
    assert h.note == "local model handoff"


def test_check_focus_moderator_on_task():
    chat = _room()
    assert chat.check_focus("design the new course curriculum for spring") == "on_topic"
    assert chat.check_focus("what is the weather in paris today") == "off_topic"


def test_summarize_round_condenses_context():
    chat = _room()
    chat.submit_message("curriculum_ai", "Module one: intro.")
    chat.submit_message("critic_ai", "Trim it to three weeks.")
    chat.submit_message("domain_expert", "Keep the lab sessions.")
    summ = chat.summarize_round()
    assert summ["message_count"] == 3
    assert summ["human_messages"] == 1
    assert summ["ai_messages"] == 2
    assert "critic_ai:" in summ["summary"]
    assert summ["round"] == 1
    # summarization emitted a summary handoff
    assert any(h.kind == "summary" for h in chat.handoffs)


def test_module_initializes_and_registers():
    import enterprise.modules.group_chat_orchestration  # noqa: F401
    assert "group_chat_orchestration" in _MODULE_REGISTRY

    m = create_group_chat_orchestration_module({})
    asyncio.run(m.initialize())
    assert asyncio.run(m.health_check()).value in ("healthy", "HEALTHY") \
        or "HEALTHY" in str(asyncio.run(m.health_check()))

    m.start_group(
        "r2",
        [
            {"name": "alice", "role": "lead", "kind": "human"},
            {"name": "bot_alpha", "role": "alpha", "kind": "ai"},
        ],
        topic="ship the release plan",
    )
    assert m.submit_message("r2", "bot_alpha", "draft the release notes")["kind"] == "turn"
    assert m.stats("r2")["messages"] == 1
    summ = m.summarize_round("r2")
    assert summ["message_count"] == 1

    asyncio.run(m.shutdown())
    assert m._chats == {}
