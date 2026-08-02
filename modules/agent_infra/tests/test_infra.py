#!/usr/bin/env python3
"""
Test Suite — Claude Code Infra Enterprise Module
=================================================
Comprehensive tests for all infrastructure components:
  - BuddyManager, BuddyAgent, SharedContext, BuddyRole
  - VoicePipeline, TTSProvider, STTProvider, VoiceSession
  - ClaudeCodeInfraModule lifecycle

Run: python3 -m pytest enterprise/modules/agent_infra/tests/ -v -p no:anyio
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

_ENTERPRISE_ROOT = Path(__file__).resolve().parents[3]
if str(_ENTERPRISE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ENTERPRISE_ROOT))

# ── Platform imports ────────────────────────────────────────────────────────
from enterprise.platform_kernel import HealthStatus

# ── Infra module imports ────────────────────────────────────────────────────
from enterprise.modules.agent_infra.buddy_system import (
    BuddyManager, BuddyAgent, SharedContext, BuddyRole, BuddyState,
)
from enterprise.modules.agent_infra.voice import (
    VoicePipeline, TTSProvider, STTProvider, VoiceSession,
    VoiceProvider, VoiceStatus,
)
from enterprise.modules.agent_infra import ClaudeCodeInfraModule


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def event_loop():
    """Create a fresh event loop for each test."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# BuddySystem Tests (13 tests)
# =============================================================================


class TestSharedContext:
    """Tests for SharedContext."""

    def test_create_context(self):
        ctx = SharedContext(task="Build API")
        assert ctx.task == "Build API"
        assert len(ctx.conversation) == 0

    def test_add_message(self):
        ctx = SharedContext(task="Test")
        ctx.add_message("Alice", "Hello team!")
        assert len(ctx.conversation) == 1
        assert ctx.conversation[0]["sender"] == "Alice"

    def test_add_artifact(self):
        ctx = SharedContext(task="Test")
        ctx.add_artifact("design.md", "# Design Doc")
        assert "design.md" in ctx.artifacts

    def test_get_summary(self):
        ctx = SharedContext(task="Review code")
        ctx.add_message("Bob", "LGTM")
        ctx.add_artifact("review.json", {"approved": True})
        summary = ctx.get_summary()
        assert summary["message_count"] == 1
        assert summary["artifact_count"] == 1


class TestBuddyAgent:
    """Tests for BuddyAgent."""

    @pytest.mark.asyncio
    async def test_execute(self):
        buddy = BuddyAgent(name="Alice", role=BuddyRole.DEVELOPER)
        response = await buddy.execute("Write tests")
        assert "Alice" in response
        assert "Write tests" in response

    @pytest.mark.asyncio
    async def test_execute_with_context(self):
        ctx = SharedContext(task="Debug issue")
        buddy = BuddyAgent(name="Bob", role=BuddyRole.ANALYST, context=ctx)
        await buddy.execute("Check logs")
        assert len(ctx.conversation) == 1
        assert ctx.conversation[0]["sender"] == "Bob"

    @pytest.mark.asyncio
    async def test_review(self):
        buddy = BuddyAgent(name="Carol", role=BuddyRole.REVIEWER)
        review = await buddy.review("Some code content")
        assert review["approved"]
        assert review["reviewer"] == "Carol"


class TestBuddyManager:
    """Tests for BuddyManager."""

    @pytest.mark.asyncio
    async def test_initialize(self):
        mgr = BuddyManager()
        await mgr.initialize()
        assert await mgr.health_check()
        assert mgr.buddy_count == 0

    @pytest.mark.asyncio
    async def test_create_context(self):
        mgr = BuddyManager()
        await mgr.initialize()
        ctx = mgr.create_context("Design system")
        assert mgr.context_count == 1
        assert mgr.get_context(ctx.context_id) is ctx

    @pytest.mark.asyncio
    async def test_spawn_buddy(self):
        mgr = BuddyManager()
        await mgr.initialize()
        ctx = mgr.create_context("Task A")
        buddy = mgr.spawn_buddy("Alice", BuddyRole.ARCHITECT, ctx)
        assert mgr.buddy_count == 1
        assert buddy.name == "Alice"
        assert buddy.role == BuddyRole.ARCHITECT

    @pytest.mark.asyncio
    async def test_list_buddies_by_context(self):
        mgr = BuddyManager()
        await mgr.initialize()
        ctx1 = mgr.create_context("Project X")
        ctx2 = mgr.create_context("Project Y")
        mgr.spawn_buddy("A", BuddyRole.DEVELOPER, ctx1)
        mgr.spawn_buddy("B", BuddyRole.TESTER, ctx1)
        mgr.spawn_buddy("C", BuddyRole.DEVELOPER, ctx2)

        team1 = mgr.list_buddies(ctx1.context_id)
        assert len(team1) == 2
        team2 = mgr.list_buddies(ctx2.context_id)
        assert len(team2) == 1

    @pytest.mark.asyncio
    async def test_delegate(self):
        mgr = BuddyManager()
        await mgr.initialize()
        ctx = mgr.create_context("Fix bug")
        mgr.spawn_buddy("Dev1", BuddyRole.DEVELOPER, ctx)
        mgr.spawn_buddy("Dev2", BuddyRole.DEVELOPER, ctx)

        results = await mgr.delegate(ctx.context_id, "Add unit tests")
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_delegate_filtered_by_role(self):
        mgr = BuddyManager()
        await mgr.initialize()
        ctx = mgr.create_context("Review")
        mgr.spawn_buddy("Dev", BuddyRole.DEVELOPER, ctx)
        mgr.spawn_buddy("Rev", BuddyRole.REVIEWER, ctx)

        results = await mgr.delegate(ctx.context_id, "Check code",
                                     roles=[BuddyRole.REVIEWER])
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_team_review(self):
        mgr = BuddyManager()
        await mgr.initialize()
        ctx = mgr.create_context("Code Review")
        mgr.spawn_buddy("R1", BuddyRole.REVIEWER, ctx)
        mgr.spawn_buddy("R2", BuddyRole.REVIEWER, ctx)

        review_result = await mgr.team_review(ctx.context_id, "function foo() {}")
        assert review_result["approved"]
        assert review_result["reviewer_count"] == 2

    @pytest.mark.asyncio
    async def test_get_team_stats(self):
        mgr = BuddyManager()
        await mgr.initialize()
        ctx = mgr.create_context("Stats test")
        mgr.spawn_buddy("A", BuddyRole.DEVELOPER, ctx)
        mgr.spawn_buddy("B", BuddyRole.TESTER, ctx)

        stats = mgr.get_team_stats(ctx.context_id)
        assert stats["member_count"] == 2
        assert "developer" in stats["roles"]
        assert "tester" in stats["roles"]

    @pytest.mark.asyncio
    async def test_remove_buddy(self):
        mgr = BuddyManager()
        await mgr.initialize()
        ctx = mgr.create_context("Temp")
        buddy = mgr.spawn_buddy("Temp", BuddyRole.CUSTOM, ctx)
        assert mgr.buddy_count == 1
        assert mgr.remove_buddy(buddy.buddy_id)
        assert mgr.buddy_count == 0


# =============================================================================
# Voice Tests (12 tests)
# =============================================================================


class TestTTSProvider:
    """Tests for TTSProvider."""

    @pytest.mark.asyncio
    async def test_initialize(self):
        tts = TTSProvider(provider=VoiceProvider.MOCK)
        await tts.initialize()
        assert await tts.health_check()

    @pytest.mark.asyncio
    async def test_synthesize(self):
        tts = TTSProvider(provider=VoiceProvider.MOCK)
        await tts.initialize()
        audio = await tts.synthesize("Hello, world!")
        assert isinstance(audio, bytes)
        assert len(audio) > 44  # Larger than WAV header
        # Should start with RIFF header
        assert audio[:4] == b'RIFF'

    @pytest.mark.asyncio
    async def test_synthesize_empty_text(self):
        tts = TTSProvider(provider=VoiceProvider.MOCK)
        await tts.initialize()
        audio = await tts.synthesize("")
        assert isinstance(audio, bytes)

    @pytest.mark.asyncio
    async def test_voice_property(self):
        tts = TTSProvider(provider=VoiceProvider.MOCK, config={"voice": "en_US-amy"})
        assert tts.voice == "en_US-amy"
        tts.voice = "en_US-john"
        assert tts.voice == "en_US-john"


class TestSTTProvider:
    """Tests for STTProvider."""

    @pytest.mark.asyncio
    async def test_initialize(self):
        stt = STTProvider(provider=VoiceProvider.MOCK)
        await stt.initialize()
        assert await stt.health_check()

    @pytest.mark.asyncio
    async def test_transcribe(self):
        stt = STTProvider(provider=VoiceProvider.MOCK)
        await stt.initialize()
        # Create a minimal valid WAV
        tts = TTSProvider()
        await tts.initialize()
        audio = await tts.synthesize("test speech input")
        text = await stt.transcribe(audio)
        assert isinstance(text, str)
        assert len(text) > 0

    @pytest.mark.asyncio
    async def test_transcribe_empty_audio(self):
        stt = STTProvider(provider=VoiceProvider.MOCK)
        await stt.initialize()
        text = await stt.transcribe(b"")
        assert text == ""


class TestVoicePipeline:
    """Tests for VoicePipeline."""

    @pytest.mark.asyncio
    async def test_initialize(self):
        pipeline = VoicePipeline()
        await pipeline.initialize()
        assert await pipeline.health_check()
        assert pipeline.tts is not None
        assert pipeline.stt is not None

    @pytest.mark.asyncio
    async def test_transcribe_session(self):
        pipeline = VoicePipeline()
        await pipeline.initialize()
        tts = TTSProvider()
        await tts.initialize()
        audio = await tts.synthesize("hello world")
        session = await pipeline.transcribe(audio)
        assert isinstance(session, VoiceSession)
        assert len(session.transcript) > 0

    @pytest.mark.asyncio
    async def test_synthesize(self):
        pipeline = VoicePipeline()
        await pipeline.initialize()
        audio = await pipeline.synthesize("Hello from pipeline")
        assert isinstance(audio, bytes)
        assert audio[:4] == b'RIFF'

    @pytest.mark.asyncio
    async def test_listen_and_respond(self):
        pipeline = VoicePipeline()
        await pipeline.initialize()

        def handler(text):
            return f"Response to: {text}"

        pipeline.set_response_handler(handler)

        tts = TTSProvider()
        await tts.initialize()
        audio = await tts.synthesize("hello")

        session = await pipeline.listen_and_respond(audio)
        assert session.status == VoiceStatus.IDLE
        assert len(session.transcript) > 0
        assert "Response to:" in session.response
        assert session.audio_data is not None

    @pytest.mark.asyncio
    async def test_active_providers(self):
        pipeline = VoicePipeline(config={
            "tts_provider": "piper",
            "stt_provider": "whisper",
        })
        await pipeline.initialize()
        assert pipeline.active_providers["tts"] == "piper"
        assert pipeline.active_providers["stt"] == "whisper"

    @pytest.mark.asyncio
    async def test_shutdown(self):
        pipeline = VoicePipeline()
        await pipeline.initialize()
        await pipeline.shutdown()
        assert pipeline.session_count == 0


# =============================================================================
# ClaudeCodeInfraModule Tests (3 tests)
# =============================================================================


class TestClaudeCodeInfraModule:
    """Tests for the ClaudeCodeInfraModule class."""

    @pytest.mark.asyncio
    async def test_initialize(self):
        mod = ClaudeCodeInfraModule()
        await mod.initialize()
        assert mod.status == HealthStatus.HEALTHY
        assert mod.tui is not None
        assert mod.server is not None
        assert mod.plugin_manager is not None
        assert mod.buddy_manager is not None
        assert mod.voice is not None

    @pytest.mark.asyncio
    async def test_health_check(self):
        mod = ClaudeCodeInfraModule()
        await mod.initialize()
        status = await mod.health_check()
        assert status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)

    @pytest.mark.asyncio
    async def test_shutdown(self):
        mod = ClaudeCodeInfraModule()
        await mod.initialize()
        await mod.shutdown()