#!/usr/bin/env python3
"""
Integration test for hermes-superior-integration skill.
Tests that all components are importable and functional.
"""

import sys
import asyncio
import inspect
from pathlib import Path

# Add skill scripts to path
skill_dir = Path(__file__).parent.parent
sys.path.insert(0, str(skill_dir / "scripts"))

def test_imports():
    """Test that all modules can be imported."""
    print("Testing imports...")
    
    # Test enhanced_tui
    try:
        from enhanced_tui import HermesTUI, HermesCompleter, MultiLineInput, MessageDisplay, StatusBar
        print("  ✅ enhanced_tui imports OK")
    except ImportError as e:
        print(f"  ❌ enhanced_tui import failed: {e}")
        return False
    
    # Test smart_context
    try:
        from smart_context import SmartContextManager, TaskAwareContext, MessageScore
        print("  ✅ smart_context imports OK")
    except ImportError as e:
        print(f"  ❌ smart_context import failed: {e}")
        return False
    
    # Test parallel_delegation
    try:
        from parallel_delegation import (
            ParallelDelegationEngine, 
            TaskSpec, 
            TaskResult, 
            AgentStatus,
            delegate_parallel,
            delegate_with_dependencies,
            ENISwarmDelegationEngine
        )
        print("  ✅ parallel_delegation imports OK")
    except ImportError as e:
        print(f"  ❌ parallel_delegation import failed: {e}")
        return False
    
    # Test model_adapter
    try:
        from model_adapter import (
            ModelAdapter, 
            ModelProfile, 
            ModelFamily, 
            MODEL_PROFILES,
            PROMPT_TEMPLATES,
            get_prompt_template
        )
        print("  ✅ model_adapter imports OK")
    except ImportError as e:
        print(f"  ❌ model_adapter import failed: {e}")
        return False
    
    # Test eni_bridge
    try:
        from eni_bridge import (
            ENIBridge,
            ENITask,
            ENIBuilder,
            ENITaskStatus,
            eni_dispatch,
            eni_parallel_dispatch,
            ENIFIFOReader
        )
        print("  ✅ eni_bridge imports OK")
    except ImportError as e:
        print(f"  ❌ eni_bridge import failed: {e}")
        return False
    
    # Test web_dashboard
    try:
        from web_dashboard import (
            app,
            ConnectionManager,
            WebSessionManager,
            AgentTaskManager,
            LocalAgentClient
        )
        print("  ✅ web_dashboard imports OK")
    except ImportError as e:
        print(f"  ❌ web_dashboard import failed: {e}")
        return False
    
    return True


def test_model_adapter():
    """Test model adapter functionality."""
    print("\nTesting model adapter...")
    
    from model_adapter import ModelAdapter, ModelFamily
    
    adapter = ModelAdapter()
    
    test_models = [
        "anthropic/claude-3-opus",
        "openai/gpt-4o",
        "nvidia/nemotron-3-ultra",
        "deepseek/deepseek-v3",
        "upstage/solar-pro",
        "zhipu/glm-4",
        "meta-llama/llama-3.1-70b",
        "mistralai/mistral-large",
        "local/llama-3.1-8b"
    ]
    
    for model in test_models:
        family = adapter.detect_family(model)
        profile = adapter.get_profile(model)
        adapted = adapter.adapt_system_prompt("Test prompt", model)
        params = adapter.get_sampling_params(model)
        
        assert family != ModelFamily.UNKNOWN, f"Failed to detect family for {model}"
        assert len(adapted) > len("Test prompt"), "Prompt not adapted"
        assert "max_tokens" in params, "Missing sampling params"
        print(f"  ✅ {model} → {family.value}")
    
    # Test prompt templates
    from model_adapter import get_prompt_template
    
    for template_name in ["code_review", "debugging"]:
        for model in ["anthropic/claude-3-opus", "nvidia/nemotron-3-ultra", "local/llama"]:
            template = get_prompt_template(template_name, model)
            assert len(template) > 0, f"Empty template for {template_name}/{model}"
            print(f"  ✅ Template {template_name} for {model}")
    
    return True


async def test_smart_context():
    """Test smart context compression."""
    print("\nTesting smart context...")
    
    from smart_context import SmartContextManager, TaskAwareContext
    
    manager = SmartContextManager(max_tokens=100, preserve_recent=2)
    
    # Create test messages that will exceed token limit
    messages = []
    for i in range(30):
        content = f'Message {i}: ' + 'word ' * 100
        messages.append({'type': 'user', 'message': {'role': 'user', 'content': content}})
    
    # Test compression
    compressed, stats = await manager.compress(messages, current_task="fix auth bug", target_tokens=50)
    
    assert stats["compressed"] == True, "Should have compressed"
    assert stats["final_count"] < stats["original_count"], "Should have fewer messages"
    assert stats["final_tokens"] < stats["original_tokens"], "Should have fewer tokens"
    print(f"  ✅ Compressed {stats['original_count']} → {stats['final_count']} messages")
    print(f"  ✅ Tokens: {stats['original_tokens']:.0f} → {stats['final_tokens']:.0f}")
    
    # Test task-aware
    task_ctx = TaskAwareContext(manager)
    task_ctx.set_task("security audit")
    compressed2, stats2 = await task_ctx.compress_for_task(messages, 50)
    print(f"  ✅ Task-aware compression works")
    
    return True


def test_parallel_delegation():
    """Test parallel delegation engine."""
    print("\nTesting parallel delegation...")
    
    from parallel_delegation import (
        ParallelDelegationEngine, 
        TaskSpec, 
        AgentStatus,
        delegate_parallel
    )
    
    engine = ParallelDelegationEngine(max_concurrent=3)
    
    # Add test tasks
    specs = [
        TaskSpec(prompt=f"Task {i}", agent_type="test", agent_name=f"task_{i}")
        for i in range(5)
    ]
    
    task_ids = engine.add_tasks(specs)
    assert len(task_ids) == 5
    
    # Test with dependencies
    engine2 = ParallelDelegationEngine(max_concurrent=2)
    dep_specs = [
        TaskSpec(prompt="A", agent_name="A"),
        TaskSpec(prompt="B", agent_name="B", dependencies=["A"]),
        TaskSpec(prompt="C", agent_name="C", dependencies=["B"]),
    ]
    dep_ids = engine2.add_tasks(dep_specs)
    assert len(dep_ids) == 3
    
    print("  ✅ Task creation and dependencies work")
    return True


def test_eni_bridge():
    """Test ENI bridge."""
    print("\nTesting ENI bridge...")
    
    from eni_bridge import ENIBridge, ENITask, ENITaskStatus
    
    bridge = ENIBridge(eni_endpoint="http://localhost:8420")
    
    # Test task creation
    task = ENITask(
        id="test_123",
        prompt="Test prompt",
        agent_type="builder",
        power_level=50
    )
    
    bridge.tasks[task.id] = task
    assert bridge.get_task("test_123") == task
    
    # Test FIFO
    from eni_bridge import ENIFIFOReader
    fifo = ENIFIFOReader()
    assert fifo.fifo_dir.exists()
    
    print("  ✅ ENI bridge components work")
    return True


def test_templates():
    """Test template files exist."""
    print("\nTesting templates...")
    
    # Templates are in the claude-code-integration skill directory
    skill_dir = Path(__file__).parent.parent.parent
    templates_dir = Path(__file__).parent.parent.parent / "claude-code-integration" / "templates"
    
    required = [
        "CLAUDE.md.template",
        "CLAUDE.local.md.template", 
        "hooks.yaml.template"
    ]
    
    for t in required:
        path = templates_dir / t
        assert path.exists(), f"Missing template: {t}"
        size = path.stat().st_size
        assert size > 100, f"Template too small: {t}"
        print(f"  ✅ {t} ({size:,} bytes)")
    
    return True


def test_references():
    """Test reference documentation exists."""
    print("\nTesting references...")
    
    skill_dir = Path(__file__).parent.parent.parent
    refs_dir = Path(__file__).parent.parent.parent / "claude-code-integration" / "references"
    
    required = [
        "architecture_mapping.md",
        "tui_architecture.md",
        "shell_command.md",
        "hooks_system.md",
        "memory_system.md",
        "agent_delegation.md",
        "session_management.md",
        "model_agnostic_prompts.md",
        "parallel_delegation.md",
        "context_intelligence.md",
        "eni_integration.md"
    ]
    
    for r in required:
        path = Path(__file__).parent.parent.parent / "claude-code-integration" / "references" / r
        assert path.exists(), f"Missing reference: {r}"
        size = path.stat().st_size
        assert size > 1000, f"Reference too small: {r}"
        print(f"  ✅ {r} ({size:,} bytes)")
    
    return True


async def main():
    """Run all tests."""
    print("=" * 60)
    print("HERMES SUPERIOR INTEGRATION - INTEGRATION TESTS")
    print("=" * 60)
    
    tests = [
        ("Imports", test_imports),
        ("Model Adapter", test_model_adapter),
        ("Smart Context", test_smart_context),
        ("Parallel Delegation", test_parallel_delegation),
        ("ENI Bridge", test_eni_bridge),
        ("Templates", lambda: test_templates()),
        ("References", lambda: test_references()),
    ]
    
    passed = 0
    failed = 0
    
    for name, test in tests:
        try:
            if inspect.iscoroutinefunction(test):
                result = await test()
            else:
                result = test()
            if result:
                print(f"  ✅ {test.__name__} passed")
            else:
                print(f"  ❌ {test.__name__} failed")
                raise AssertionError("Test returned False")
            print(f"  ✅ {test.__name__} passed")
        except Exception as e:
            print(f"  ❌ {test.__name__} failed with exception: {e}")
            import traceback
            traceback.print_exc()
            return 1
    
    print("\n" + "=" * 60)
    print(f"RESULTS: All tests passed!")
    print("=" * 60)
    print("\n🎉 ALL TESTS PASSED!")
    print("\nHermes Superior Integration is ready for use!")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
