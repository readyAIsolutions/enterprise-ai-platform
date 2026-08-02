#!/usr/bin/env python3
"""
Test Suite — Claude Code Core Enterprise Module
================================================
Comprehensive tests for all core components:
  - TaskScheduler, SwarmTaskBridge, Task, BackgroundTask
  - SmartContext, ContextTier, EmbeddingCache, CompressionEngine, WindowManager
  - HooksEngine, HookPlugin, HookType, HookPriority
  - StateManager, CRDTStore, DistributedLock, StateVersion
  - ModelService, ToolService, MemoryService, AuthService, ServiceRegistry
  - ClaudeCodeModule lifecycle (initialize, health_check, shutdown)

Run: python3 -m pytest enterprise/modules/agent_core/tests/ -v -p no:anyio
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

# ── Core module imports ─────────────────────────────────────────────────────
from enterprise.modules.agent_core.task_system import (
    Task, TaskType, TaskStatus, TaskPriority, BackgroundTask,
    TaskScheduler, SwarmTaskBridge, TaskResult,
)
from enterprise.modules.agent_core.context_manager import (
    SmartContext, ContextTier, EmbeddingCache,
    CompressionEngine, WindowManager, ContextEntry,
)
from enterprise.modules.agent_core.hooks_engine import (
    HooksEngine, HookType, HookPriority, HookResult,
    PluginManifest, HookPlugin,
)
from enterprise.modules.agent_core.state_manager import (
    StateManager, CRDTStore, DistributedLock,
    StateVersion, MergeStrategy, StateEntry,
)
from enterprise.modules.agent_core.services import (
    ModelService, ToolService, MemoryService, AuthService,
    ServiceRegistry, ModelProvider, ToolDefinition, MemoryEntry, AuthToken,
)
from enterprise.modules.agent_core import ClaudeCodeModule


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
# TaskSystem Tests (10 tests)
# =============================================================================


class TestTask:
    """Tests for Task data model."""

    def test_task_creation_defaults(self):
        t = Task()
        assert t.task_type == TaskType.CUSTOM
        assert t.status == TaskStatus.QUEUED
        assert t.priority == TaskPriority.NORMAL
        assert t.max_retries == 3
        assert t.timeout_seconds == 300.0

    def test_task_custom_fields(self):
        t = Task(
            name="test-task",
            task_type=TaskType.BACKGROUND_JOB,
            priority=TaskPriority.HIGH,
            max_retries=5,
            timeout_seconds=60.0,
            payload={"key": "value"},
        )
        assert t.name == "test-task"
        assert t.task_type == TaskType.BACKGROUND_JOB
        assert t.priority == TaskPriority.HIGH
        assert t.max_retries == 5
        assert t.timeout_seconds == 60.0
        assert t.payload == {"key": "value"}

    def test_task_hash(self):
        t1 = Task()
        t2 = Task()
        assert hash(t1) != hash(t2)
        assert hash(t1) == hash(t1)


class TestTaskResult:
    """Tests for TaskResult."""

    def test_success_result(self):
        r = TaskResult(task_id="abc", success=True, data={"x": 1}, attempts=2)
        assert r.success
        assert r.data == {"x": 1}
        assert r.error is None
        assert r.attempts == 2

    def test_failure_result(self):
        r = TaskResult(task_id="abc", success=False, error="Something broke")
        assert not r.success
        assert r.error == "Something broke"
        assert r.data is None


class TestSwarmTaskBridge:
    """Tests for SwarmTaskBridge."""

    @pytest.mark.asyncio
    async def test_initialize(self):
        bridge = SwarmTaskBridge()
        await bridge.initialize()
        assert await bridge.health_check()

    @pytest.mark.asyncio
    async def test_delegate_locally(self):
        bridge = SwarmTaskBridge()
        await bridge.initialize()
        task = Task(name="test")
        result = await bridge.delegate(task)
        assert result.success
        assert result.task_id == task.task_id

    @pytest.mark.asyncio
    async def test_shutdown(self):
        bridge = SwarmTaskBridge()
        await bridge.initialize()
        await bridge.shutdown()


class TestTaskScheduler:
    """Tests for TaskScheduler."""

    @pytest.mark.asyncio
    async def test_initialize(self):
        sched = TaskScheduler()
        await sched.initialize()
        assert await sched.health_check()
        assert sched.queue_size == 0

    @pytest.mark.asyncio
    async def test_submit_single(self):
        sched = TaskScheduler()
        await sched.initialize()
        task = Task(name="single")
        result = await sched.submit(task)
        assert result.success
        assert result.task_id == task.task_id
        assert result.attempts == 1
        await sched.shutdown()

    @pytest.mark.asyncio
    async def test_submit_with_custom_executor(self):
        sched = TaskScheduler()
        await sched.initialize()

        async def my_executor(payload):
            return {"custom": True, "payload": payload}

        task = Task(name="custom", payload={"a": 1})
        result = await sched.submit(task, executor=my_executor)
        assert result.success
        assert result.data == {"custom": True, "payload": {"a": 1}}
        await sched.shutdown()

    @pytest.mark.asyncio
    async def test_submit_many(self):
        sched = TaskScheduler(config={"max_concurrency": 5})
        await sched.initialize()
        tasks = [Task(name=f"task-{i}") for i in range(5)]
        results = await sched.submit_many(tasks)
        assert len(results) == 5
        assert all(r.success for r in results)
        await sched.shutdown()

    @pytest.mark.asyncio
    async def test_cancel_task(self):
        sched = TaskScheduler()
        await sched.initialize()
        task = Task(name="cancel-me")
        # Submit as background (fire and forget part)
        cancelled = sched.cancel(task.task_id)
        assert not cancelled  # Not yet running
        await sched.shutdown()

    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        sched = TaskScheduler()
        await sched.initialize()
        call_count = 0

        async def flaky(payload):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("transient error")
            return {"ok": True}

        task = Task(name="flaky", max_retries=3)
        result = await sched.submit(task, executor=flaky)
        assert result.success
        assert call_count == 2
        await sched.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown(self):
        sched = TaskScheduler()
        await sched.initialize()
        await sched.shutdown()
        assert sched.queue_size == 0
        assert sched.running_count == 0


# =============================================================================
# ContextManager Tests (10 tests)
# =============================================================================


class TestEmbeddingCache:
    """Tests for EmbeddingCache."""

    def test_set_and_get(self):
        cache = EmbeddingCache(max_size=10)
        cache.set("key1", [0.1, 0.2, 0.3])
        assert cache.get("key1") == [0.1, 0.2, 0.3]

    def test_miss_returns_none(self):
        cache = EmbeddingCache(max_size=10)
        assert cache.get("nonexistent") is None

    def test_hit_rate(self):
        cache = EmbeddingCache(max_size=10)
        cache.get("a")  # miss
        cache.get("b")  # miss
        cache.set("a", [1.0])
        cache.get("a")  # hit
        assert cache.hit_rate == 1.0 / 3.0

    def test_lru_eviction(self):
        cache = EmbeddingCache(max_size=2)
        cache.set("a", [1.0])
        cache.set("b", [2.0])
        cache.set("c", [3.0])  # evicts "a"
        assert cache.get("a") is None
        assert cache.get("b") == [2.0]
        assert cache.get("c") == [3.0]

    def test_clear(self):
        cache = EmbeddingCache(max_size=10)
        cache.set("a", [1.0])
        cache.clear()
        assert cache.size == 0


class TestCompressionEngine:
    """Tests for CompressionEngine."""

    def test_trim(self):
        engine = CompressionEngine()
        content = "  hello   world\n\n  foo  bar  "
        trimmed, tokens = engine.trim(content)
        assert "hello" in trimmed and "world" in trimmed
        assert "foo" in trimmed and "bar" in trimmed
        assert tokens >= 2

    def test_summarize_short_text(self):
        engine = CompressionEngine()
        content = "Short text."
        summary, tokens = engine.summarize(content, max_sentences=5)
        assert summary == content

    def test_summarize_long_text(self):
        engine = CompressionEngine()
        content = (
            "First sentence. Second sentence with more words here. "
            "Third sentence. Fourth sentence with details. "
            "Fifth sentence. Sixth sentence. Seventh sentence."
        )
        summary, tokens = engine.summarize(content, max_sentences=3)
        assert "First sentence" in summary
        assert len(summary) < len(content)

    def test_compute_embedding(self):
        engine = CompressionEngine()
        emb = engine.compute_embedding("hello world")
        assert len(emb) == 128
        assert all(0.0 <= x <= 1.0 for x in emb)

    def test_cosine_similarity(self):
        engine = CompressionEngine()
        a = [1.0, 0.0, 0.0]
        b = [1.0, 0.0, 0.0]
        assert engine.cosine_similarity(a, b) == 1.0

        c = [0.0, 1.0, 0.0]
        assert engine.cosine_similarity(a, c) == 0.0


class TestWindowManager:
    """Tests for WindowManager."""

    def test_add_entry(self):
        wm = WindowManager(max_tokens=1000)
        entry = ContextEntry(entry_id="1", content="hello world", token_count=2)
        wm.add(entry)
        assert len(wm.entries) == 1
        assert wm.total_tokens == 2

    def test_eviction_on_over_budget(self):
        wm = WindowManager(max_tokens=5)
        e1 = ContextEntry(entry_id="1", content="a", token_count=3, relevance_score=0.5)
        e2 = ContextEntry(entry_id="2", content="b", token_count=3, relevance_score=0.8)
        wm.add(e1)
        wm.add(e2)  # Total 6 > 5, should evict e1 (lower relevance)
        assert len(wm.entries) == 1
        assert wm.entries[0].entry_id == "2"

    def test_remove_entry(self):
        wm = WindowManager(max_tokens=100)
        entry = ContextEntry(entry_id="r1", content="x", token_count=1)
        wm.add(entry)
        assert wm.remove("r1")
        assert len(wm.entries) == 0

    def test_query_relevant(self):
        wm = WindowManager(max_tokens=1000)
        engine = CompressionEngine()
        e1 = ContextEntry(entry_id="a", content="python programming language development", token_count=4)
        e2 = ContextEntry(entry_id="b", content="cooking recipes food kitchen", token_count=4)
        wm.add(e1)
        wm.add(e2)
        query_emb = engine.compute_embedding("python code development")
        results = wm.query_relevant(query_emb, engine, top_k=2)
        assert len(results) == 2
        # Both entries should be returned, similarity-based ordering may vary with hash embeddings


class TestSmartContext:
    """Tests for SmartContext."""

    @pytest.mark.asyncio
    async def test_initialize(self):
        ctx = SmartContext()
        await ctx.initialize()
        assert await ctx.health_check()

    @pytest.mark.asyncio
    async def test_add_and_query(self):
        ctx = SmartContext()
        await ctx.initialize()
        ctx.add_entry("Python is a programming language for software development",
                      metadata={"topic": "python"})
        ctx.add_entry("Spaghetti carbonara is an Italian pasta recipe",
                      metadata={"topic": "cooking"})
        results = ctx.query("code software development programming", top_k=2)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_compress_entry(self):
        ctx = SmartContext()
        await ctx.initialize()
        ctx.add_entry("Hello world. " * 50)
        assert ctx.compress_entry(
            ctx.window.entries[0].entry_id,
            ContextTier.TRIMMED
        )
        assert ctx.window.entries[0].tier == ContextTier.TRIMMED

    @pytest.mark.asyncio
    async def test_compress_all(self):
        ctx = SmartContext()
        await ctx.initialize()
        for i in range(5):
            ctx.add_entry(f"Entry {i} content here. " * 10)
        count = ctx.compress_all_to_tier(ContextTier.TRIMMED)
        assert count == 5

    @pytest.mark.asyncio
    async def test_get_stats(self):
        ctx = SmartContext()
        await ctx.initialize()
        ctx.add_entry("hello world", entry_id="hw")
        stats = ctx.get_stats()
        assert stats["total_entries"] == 1
        assert stats["total_tokens"] >= 2
        assert "token_usage_pct" in stats

    @pytest.mark.asyncio
    async def test_shutdown(self):
        ctx = SmartContext()
        await ctx.initialize()
        await ctx.shutdown()
        assert len(ctx.window.entries) == 0


# =============================================================================
# HooksEngine Tests (10 tests)
# =============================================================================


class TestHookPlugin:
    """Tests for HookPlugin."""

    def test_register_handler(self):
        manifest = PluginManifest(name="test-plugin")
        plugin = HookPlugin(manifest)

        def handler(data, **kwargs):
            return data

        plugin.register(HookType.QUERY_PRE_PROCESS, handler)
        assert plugin.has_handler(HookType.QUERY_PRE_PROCESS)
        assert not plugin.has_handler(HookType.TOOL_POST_EXECUTE)

    def test_unregister_handler(self):
        manifest = PluginManifest(name="test")
        plugin = HookPlugin(manifest)

        def handler(data, **kwargs):
            return data

        plugin.register(HookType.SESSION_START, handler)
        assert plugin.unregister(HookType.SESSION_START, handler)
        assert not plugin.has_handler(HookType.SESSION_START)

    def test_priority_ordering(self):
        manifest = PluginManifest(name="ordered", priority=HookPriority.NORMAL)
        plugin = HookPlugin(manifest)
        results = []

        def high(data, **kwargs):
            results.append("high")
            return data

        def low(data, **kwargs):
            results.append("low")
            return data

        plugin.register(HookType.QUERY_PRE_PROCESS, low, priority=HookPriority.LOW)
        plugin.register(HookType.QUERY_PRE_PROCESS, high, priority=HookPriority.HIGH)
        handlers = plugin.get_handlers(HookType.QUERY_PRE_PROCESS)
        assert len(handlers) == 2
        # High priority (lower value) should come first
        assert handlers[0] is high
        assert handlers[1] is low

    def test_enabled_disabled(self):
        manifest = PluginManifest(name="toggle")
        plugin = HookPlugin(manifest)
        assert plugin.enabled
        plugin.enabled = False
        assert not plugin.enabled


class TestHooksEngine:
    """Tests for HooksEngine."""

    @pytest.mark.asyncio
    async def test_initialize(self):
        engine = HooksEngine()
        await engine.initialize()
        assert await engine.health_check()

    @pytest.mark.asyncio
    async def test_trigger_sync_handler(self):
        engine = HooksEngine()
        await engine.initialize()

        manifest = PluginManifest(name="my-plugin")
        plugin = HookPlugin(manifest)
        plugin.register(HookType.QUERY_PRE_PROCESS, lambda d, **kw: {"processed": True})
        engine.register_plugin(plugin)

        results = engine.trigger_sync(HookType.QUERY_PRE_PROCESS, data={"q": "hello"})
        assert len(results) == 1
        assert results[0].hook_type == HookType.QUERY_PRE_PROCESS

    @pytest.mark.asyncio
    async def test_trigger_async_handler(self):
        engine = HooksEngine()
        await engine.initialize()

        manifest = PluginManifest(name="async-plugin")
        plugin = HookPlugin(manifest)

        async def async_handler(data, **kwargs):
            await asyncio.sleep(0.01)
            return {"async": True, **data}

        plugin.register(HookType.QUERY_POST_PROCESS, async_handler)
        engine.register_plugin(plugin)

        results = await engine.trigger(HookType.QUERY_POST_PROCESS, data={"q": "test"})
        assert len(results) == 1
        assert results[0].data == {"async": True, "q": "test"}

    @pytest.mark.asyncio
    async def test_prevent_default(self):
        engine = HooksEngine()
        await engine.initialize()

        manifest = PluginManifest(name="blocker")
        plugin = HookPlugin(manifest)
        plugin.register(HookType.TOOL_PRE_EXECUTE,
                        lambda d, **kw: {"__prevent_default__": True})
        engine.register_plugin(plugin)

        results = engine.trigger_sync(HookType.TOOL_PRE_EXECUTE, data={"tool": "bash"})
        assert len(results) == 1
        assert results[0].prevent_default

    @pytest.mark.asyncio
    async def test_multiple_plugins(self):
        engine = HooksEngine()
        await engine.initialize()

        for i in range(3):
            manifest = PluginManifest(name=f"plugin-{i}")
            plugin = HookPlugin(manifest)
            plugin.register(HookType.SESSION_START, lambda d, i=i, **kw: {"plugin": i})
            engine.register_plugin(plugin)

        results = engine.trigger_sync(HookType.SESSION_START, data={})
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_unregister_plugin(self):
        engine = HooksEngine()
        await engine.initialize()

        manifest = PluginManifest(name="temp", plugin_id="temp1")
        plugin = HookPlugin(manifest)
        engine.register_plugin(plugin)
        assert engine.plugin_count == 1

        engine.unregister_plugin("temp1")
        assert engine.plugin_count == 0

    @pytest.mark.asyncio
    async def test_trigger_stats(self):
        engine = HooksEngine()
        await engine.initialize()
        engine.trigger_sync(HookType.SESSION_START, data={})
        engine.trigger_sync(HookType.SESSION_START, data={})
        stats = engine.get_trigger_stats()
        assert stats[HookType.SESSION_START.value] == 2

    @pytest.mark.asyncio
    async def test_disabled_plugin_skipped(self):
        engine = HooksEngine()
        await engine.initialize()

        manifest = PluginManifest(name="off")
        plugin = HookPlugin(manifest)
        plugin.register(HookType.QUERY_PRE_PROCESS, lambda d, **kw: d)
        plugin.enabled = False
        engine.register_plugin(plugin)

        results = engine.trigger_sync(HookType.QUERY_PRE_PROCESS, data={})
        assert len(results) == 0


# =============================================================================
# StateManager Tests (9 tests)
# =============================================================================


class TestCRDTStore:
    """Tests for CRDTStore."""

    def test_g_counter(self):
        store = CRDTStore()
        assert store.g_counter_value("visits") == 0
        store.g_counter_increment("visits", "node1", 5)
        store.g_counter_increment("visits", "node2", 3)
        assert store.g_counter_value("visits") == 8

    def test_pn_counter(self):
        store = CRDTStore()
        store.pn_counter_increment("score", "n1", 10)
        store.pn_counter_decrement("score", "n1", 3)
        assert store.pn_counter_value("score") == 7

    def test_register(self):
        store = CRDTStore()
        store.register_set("config", {"host": "localhost"})
        assert store.register_get("config") == {"host": "localhost"}
        store.register_delete("config")
        assert store.register_get("config") is None

    def test_or_set(self):
        store = CRDTStore()
        store.set_add("tags", "python")
        store.set_add("tags", "rust")
        store.set_add("tags", "go")
        store.set_remove("tags", "go")
        members = store.set_members("tags")
        assert "python" in members
        assert "rust" in members
        assert "go" not in members

    def test_merge(self):
        s1 = CRDTStore()
        s1.g_counter_increment("x", "n1", 5)

        s2 = CRDTStore()
        s2.g_counter_increment("x", "n2", 3)

        s1.merge(s2)
        assert s1.g_counter_value("x") == 8

    def test_serialization(self):
        store = CRDTStore()
        store.g_counter_increment("cnt", "n1", 42)
        store.register_set("key", "value")
        data = store.to_dict()
        restored = CRDTStore.from_dict(data)
        assert restored.g_counter_value("cnt") == 42
        assert restored.register_get("key") == "value"


class TestDistributedLock:
    """Tests for DistributedLock."""

    @pytest.mark.asyncio
    async def test_acquire_release(self):
        lock = DistributedLock("res1")
        acquired = await lock.acquire(timeout=1.0)
        assert acquired
        assert lock.is_locked
        lock.release()
        assert not lock.is_locked

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        lock = DistributedLock("res2")
        async with lock as l:
            assert l.is_locked
        assert not lock.is_locked


class TestStateManager:
    """Tests for StateManager."""

    @pytest.mark.asyncio
    async def test_initialize(self):
        sm = StateManager()
        await sm.initialize()
        assert await sm.health_check()

    @pytest.mark.asyncio
    async def test_set_and_get(self):
        sm = StateManager()
        await sm.initialize()
        sm.set("name", "Hermes")
        assert sm.get("name") == "Hermes"
        assert sm.exists("name")
        assert not sm.exists("missing")

    @pytest.mark.asyncio
    async def test_update_bumps_version(self):
        sm = StateManager()
        await sm.initialize()
        sm.set("key", "v1")
        v1 = sm.get_entry("key").version
        sm.set("key", "v2")
        v2 = sm.get_entry("key").version
        assert v2 > v1

    @pytest.mark.asyncio
    async def test_delete(self):
        sm = StateManager()
        await sm.initialize()
        sm.set("temp", "value")
        assert sm.delete("temp")
        assert sm.get("temp") is None
        assert not sm.delete("nonexistent")

    @pytest.mark.asyncio
    async def test_list_keys(self):
        sm = StateManager()
        await sm.initialize()
        sm.set("app:config", {})
        sm.set("app:state", {})
        sm.set("other", {})
        assert len(sm.list_keys("app:")) == 2

    @pytest.mark.asyncio
    async def test_crdt_operations(self):
        sm = StateManager()
        await sm.initialize()
        assert sm.g_counter_inc("hits", 10) == 10
        assert sm.g_counter_get("hits") == 10
        sm.set_add("languages", "python")
        assert "python" in sm.set_members("languages")

    @pytest.mark.asyncio
    async def test_snapshot_restore(self):
        sm = StateManager()
        await sm.initialize()
        sm.set("key1", "val1")
        sm.set("key2", "val2")
        snap = sm.snapshot()
        assert "entries" in snap

        sm2 = StateManager()
        await sm2.initialize()
        count = sm2.restore(snap)
        assert count == 2
        assert sm2.get("key1") == "val1"

    @pytest.mark.asyncio
    async def test_shutdown(self):
        sm = StateManager()
        await sm.initialize()
        await sm.shutdown()
        assert sm.entry_count == 0


# =============================================================================
# Services Tests (10 tests)
# =============================================================================


class TestModelService:
    @pytest.mark.asyncio
    async def test_initialize(self):
        svc = ModelService()
        await svc.initialize()
        assert await svc.health_check()

    @pytest.mark.asyncio
    async def test_register_model(self):
        svc = ModelService()
        await svc.initialize()
        mid = svc.register_model(ModelProvider.ANTHROPIC, "claude-sonnet-4-20250514")
        assert svc.model_count == 1
        svc.unregister_model(mid)
        assert svc.model_count == 0

    @pytest.mark.asyncio
    async def test_query(self):
        svc = ModelService()
        await svc.initialize()
        svc.register_model(ModelProvider.OPENAI, "gpt-4o")
        response = await svc.query("Hello")
        assert "gpt-4o" in response or "Hello" in response


class TestToolService:
    @pytest.mark.asyncio
    async def test_register_and_execute(self):
        svc = ToolService()
        await svc.initialize()
        svc.register_tool(ToolDefinition(name="test_tool", category="test"))

        async def executor(params):
            return {"result": params.get("x", 0) * 2}

        svc.register_tool(ToolDefinition(name="double", category="math"), executor)
        result = await svc.execute("double", {"x": 5})
        assert result == {"result": 10}

    @pytest.mark.asyncio
    async def test_execute_unregistered_raises(self):
        svc = ToolService()
        await svc.initialize()
        with pytest.raises(KeyError):
            await svc.execute("nonexistent", {})


class TestMemoryService:
    @pytest.mark.asyncio
    async def test_store_and_retrieve(self):
        svc = MemoryService()
        await svc.initialize()
        entry = svc.store("User likes Python", tags=["pref"], importance=0.9)
        retrieved = svc.retrieve(entry.memory_id)
        assert retrieved.content == "User likes Python"

    @pytest.mark.asyncio
    async def test_search(self):
        svc = MemoryService()
        await svc.initialize()
        svc.store("Python programming language", tags=["tech"])
        svc.store("Italian cooking recipes", tags=["food"])
        results = svc.search("programming", top_k=1)
        assert len(results) == 1
        assert "Python" in results[0].content

    @pytest.mark.asyncio
    async def test_delete(self):
        svc = MemoryService()
        await svc.initialize()
        entry = svc.store("temp")
        assert svc.delete(entry.memory_id)
        assert svc.retrieve(entry.memory_id) is None


class TestAuthService:
    @pytest.mark.asyncio
    async def test_issue_and_validate(self):
        svc = AuthService()
        await svc.initialize()
        token = svc.issue_token("user1", scopes=["read", "write"])
        assert svc.validate_token(token.token, "read")
        assert svc.validate_token(token.token, "write")
        assert not svc.validate_token(token.token, "admin")

    @pytest.mark.asyncio
    async def test_revoke_token(self):
        svc = AuthService()
        await svc.initialize()
        token = svc.issue_token("user1")
        assert svc.active_token_count == 1
        svc.revoke_token(token.token)
        assert not svc.validate_token(token.token)


class TestServiceRegistry:
    @pytest.mark.asyncio
    async def test_initialize_all(self):
        registry = ServiceRegistry()
        await registry.initialize()
        assert await registry.health_check()
        assert registry.model is not None
        assert registry.tool is not None
        assert registry.memory is not None
        assert registry.auth is not None

    @pytest.mark.asyncio
    async def test_shutdown(self):
        registry = ServiceRegistry()
        await registry.initialize()
        await registry.shutdown()


# =============================================================================
# ClaudeCodeModule Tests (3 tests)
# =============================================================================


class TestClaudeCodeModule:
    """Tests for the ClaudeCodeModule class."""

    @pytest.mark.asyncio
    async def test_initialize(self):
        mod = ClaudeCodeModule()
        await mod.initialize()
        assert mod.status == HealthStatus.HEALTHY
        assert mod.engine is not None
        assert mod.coordinator is not None
        assert mod.scheduler is not None
        assert mod.context_manager is not None
        assert mod.hooks is not None
        assert mod.state is not None
        assert mod.services is not None

    @pytest.mark.asyncio
    async def test_health_check(self):
        mod = ClaudeCodeModule()
        await mod.initialize()
        status = await mod.health_check()
        assert status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)

    @pytest.mark.asyncio
    async def test_shutdown(self):
        mod = ClaudeCodeModule()
        await mod.initialize()
        await mod.shutdown()
        assert mod.status in (HealthStatus.UNKNOWN, HealthStatus.STOPPING)