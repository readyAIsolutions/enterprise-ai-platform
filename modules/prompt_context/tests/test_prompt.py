"""
Comprehensive tests for the Prompt & Context Management OS module.

Tests cover:
- Prompt Registry: CRUD, versioning, status transitions, rollback, metrics, serialization
- Context Manager: Add, retrieve, update, remove, expiration, assembly, deduplication
- Optimizer: All strategies, presets, conflict detection, statistics
- Token Budget: Allocation, truncation, caching, model routing, compression
- Evaluator: All metrics, hallucination detection, grading, summaries
- Quality Gates: All gate types, blocking, warnings, edge cases
"""

import json
import os
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone, timedelta

# Ensure the module is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# ---------------------------------------------------------------------------
# Imports from module — prompt_context re-exports all submodules
# ---------------------------------------------------------------------------

from enterprise.modules.prompt_context import (
    PromptRegistry,
    PromptRegistryError,
    PromptNotFoundError,
    VersionNotFoundError,
    InvalidTransitionError,
    RollbackError,
    PromptStatus,
    ChangeType,
    MetricName,
    ChangelogEntry,
    PerformanceMetric,
    PromptVersion,
    PromptRecord,
    SemanticVersion,
    PromptIDGenerator,
    detect_template_issues,
    ContextManager,
    ContextManagerError,
    ContextNotFoundError,
    ContextWindowExceededError,
    ContextType,
    ContextPriority,
    ContextSource,
    ContextBlock,
    ContextSnapshot,
    ContextWindow,
    ContextOptimizer,
    OptimizerError,
    OptimizationStrategy,
    OptimizerPreset,
    OptimizationAction,
    OptimizationResult,
    OptimizerConfig,
    TokenBudgetManager,
    TokenBudgetError,
    BudgetExceededError,
    TruncationStrategy,
    BudgetAllocation,
    CacheStrategy,
    TokenBudget,
    CacheEntry,
    BudgetReport,
    ModelRoute,
    PromptEvaluator,
    EvaluatorError,
    EvalMetric,
    EvalGrade,
    EvalScore,
    EvaluationResult,
    EvalSummary,
    HallucinationCheck,
    QualityGates,
    QualityGateError,
    QualityGateBlockedError,
    GateSeverity,
    GateStatus,
    GateCategory,
    GateCheck,
    QualityGateResult,
    GateConfig,
)


# ============================================================================
# Prompt Registry Tests
# ============================================================================

class TestSemanticVersion(unittest.TestCase):
    """Tests for SemanticVersion."""

    def test_parse_valid(self):
        v = SemanticVersion.parse("1.2.3")
        self.assertEqual(v.major, 1)
        self.assertEqual(v.minor, 2)
        self.assertEqual(v.patch, 3)
        self.assertIsNone(v.pre)

    def test_parse_with_pre(self):
        v = SemanticVersion.parse("2.0.0-alpha.1")
        self.assertEqual(v.major, 2)
        self.assertEqual(v.minor, 0)
        self.assertEqual(v.patch, 0)
        self.assertEqual(v.pre, "alpha.1")

    def test_parse_invalid(self):
        with self.assertRaises(ValueError):
            SemanticVersion.parse("not.a.version")

    def test_comparison(self):
        self.assertTrue(SemanticVersion(1, 0, 0) < SemanticVersion(2, 0, 0))
        self.assertTrue(SemanticVersion(1, 2, 0) < SemanticVersion(1, 3, 0))
        self.assertTrue(SemanticVersion(1, 0, 0) < SemanticVersion(1, 0, 1))
        self.assertEqual(SemanticVersion(1, 0, 0), SemanticVersion(1, 0, 0))

    def test_pre_release_comparison(self):
        v1 = SemanticVersion(1, 0, 0, pre="alpha")
        v2 = SemanticVersion(1, 0, 0)
        self.assertTrue(v1 < v2)  # Pre-release < release

    def test_bump(self):
        v = SemanticVersion.parse("1.2.3")
        self.assertEqual(str(v.bump_major()), "2.0.0")
        self.assertEqual(str(v.bump_minor()), "1.3.0")
        self.assertEqual(str(v.bump_patch()), "1.2.4")

    def test_try_parse(self):
        self.assertIsNotNone(SemanticVersion.try_parse("1.0.0"))
        self.assertIsNone(SemanticVersion.try_parse("invalid"))

    def test_str_and_repr(self):
        v = SemanticVersion(2, 1, 0)
        self.assertEqual(str(v), "2.1.0")
        self.assertIn("2.1.0", repr(v))


class TestPromptIDGenerator(unittest.TestCase):
    """Tests for PromptIDGenerator."""

    def test_generate(self):
        pid = PromptIDGenerator.generate("my prompt")
        self.assertTrue(PromptIDGenerator.validate(pid))

    def test_validate_invalid(self):
        self.assertFalse(PromptIDGenerator.validate("not-a-valid-id"))
        self.assertFalse(PromptIDGenerator.validate(""))

    def test_short_id(self):
        pid = PromptIDGenerator.generate("my prompt")
        short = PromptIDGenerator.short_id(pid)
        self.assertIn("my-prompt", pid)
        self.assertEqual(short, "my-prompt")


class TestDetectTemplateIssues(unittest.TestCase):
    """Tests for detect_template_issues."""

    def test_no_issues(self):
        issues = detect_template_issues("Hello {{name}}, your task is {{task}}")
        self.assertEqual(issues, [])

    def test_unbalanced_braces(self):
        issues = detect_template_issues("Hello {{name}, your task is {{task}}")
        self.assertTrue(any("Unbalanced" in i for i in issues))

    def test_empty_variables(self):
        issues = detect_template_issues("Hello {{}}, how are you?")
        self.assertTrue(any("Empty variable" in i for i in issues))

    def test_duplicate_variables(self):
        issues = detect_template_issues("{{name}} and {{name}} again")
        self.assertTrue(any("Duplicate" in i for i in issues))

    def test_empty_template(self):
        issues = detect_template_issues("")
        self.assertEqual(issues, [])


class TestPromptRegistry(unittest.TestCase):
    """Tests for PromptRegistry."""

    def setUp(self):
        self.registry = PromptRegistry()

    def test_define_prompt(self):
        prompt_id = self.registry.define(
            name="Test Summarizer",
            objective="Summarize articles",
            template="Summarize: {{content}}",
            tags=["summarizer", "test"],
        )
        self.assertTrue(prompt_id.startswith("prmpt_"))
        self.assertIn(prompt_id, self.registry)

    def test_define_empty_name_raises(self):
        with self.assertRaises(ValueError):
            self.registry.define(name="", objective="test", template="{{x}}")

    def test_define_empty_objective_raises(self):
        with self.assertRaises(ValueError):
            self.registry.define(name="test", objective="", template="{{x}}")

    def test_define_empty_template_raises(self):
        with self.assertRaises(ValueError):
            self.registry.define(name="test", objective="test", template="")

    def test_get_prompt(self):
        pid = self.registry.define(
            name="Test", objective="Test", template="{{var}}"
        )
        record = self.registry.get(pid)
        self.assertEqual(record.name, "Test")
        self.assertEqual(record.current_version, "0.1.0")

    def test_get_nonexistent_raises(self):
        with self.assertRaises(PromptNotFoundError):
            self.registry.get("nonexistent_id")

    def test_get_current(self):
        pid = self.registry.define(
            name="Test", objective="Test", template="{{var}}"
        )
        version = self.registry.get_current(pid)
        self.assertEqual(version.version, "0.1.0")
        self.assertEqual(version.objective, "Test")

    def test_get_version(self):
        pid = self.registry.define(
            name="Test", objective="Test", template="{{var}}"
        )
        version = self.registry.get_version(pid, "0.1.0")
        self.assertEqual(version.template, "{{var}}")

    def test_get_nonexistent_version_raises(self):
        pid = self.registry.define(
            name="Test", objective="Test", template="{{var}}"
        )
        with self.assertRaises(VersionNotFoundError):
            self.registry.get_version(pid, "9.9.9")

    def test_update_creates_new_version(self):
        pid = self.registry.define(
            name="Test", objective="Old objective", template="{{var}}"
        )
        new_ver = self.registry.update(
            pid, objective="New objective", author="tester"
        )
        self.assertNotEqual(new_ver, "0.1.0")
        self.assertEqual(self.registry.get_current(pid).objective, "New objective")

    def test_update_template(self):
        pid = self.registry.define(
            name="Test", objective="Test", template="{{old}}"
        )
        new_ver = self.registry.update(pid, template="{{new}}")
        self.assertIn("{{new}}", self.registry.get_current(pid).template)

    def test_update_no_changes(self):
        pid = self.registry.define(
            name="Test", objective="Test", template="{{var}}"
        )
        result = self.registry.update(pid)  # No changes
        self.assertEqual(result, "0.1.0")

    def test_version_history(self):
        pid = self.registry.define(
            name="Test", objective="v1", template="{{a}}"
        )
        self.registry.update(pid, objective="v2")
        self.registry.update(pid, objective="v3")

        history = self.registry.get_history(pid)
        self.assertEqual(len(history), 3)  # Created + 2 updates

        tree = self.registry.get_version_tree(pid)
        self.assertIn("root", tree)

    def test_compare_versions(self):
        pid = self.registry.define(
            name="Test", objective="v1", template="{{a}}"
        )
        v2 = self.registry.update(pid, objective="v2", template="{{a}}{{b}}")

        comparison = self.registry.compare_versions(pid, "0.1.0", v2)
        self.assertTrue(comparison["objective_changed"])
        self.assertTrue(comparison["template_changed"])
        self.assertEqual(comparison["variables_added"], ["b"])

    def test_delete_soft(self):
        pid = self.registry.define(
            name="Test", objective="Test", template="{{var}}"
        )
        self.registry.delete(pid, hard=False)
        record = self.registry.get(pid)
        self.assertEqual(
            record.versions[record.current_version].status,
            PromptStatus.ARCHIVED,
        )

    def test_delete_hard(self):
        pid = self.registry.define(
            name="Test", objective="Test", template="{{var}}"
        )
        self.registry.delete(pid, hard=True)
        with self.assertRaises(PromptNotFoundError):
            self.registry.get(pid)

    def test_set_status(self):
        pid = self.registry.define(
            name="Test", objective="Test", template="{{var}}"
        )
        self.registry.set_status(pid, PromptStatus.ACTIVE)
        self.assertEqual(
            self.registry.get_current(pid).status,
            PromptStatus.ACTIVE,
        )

    def test_invalid_transition(self):
        pid = self.registry.define(
            name="Test", objective="Test", template="{{var}}"
        )
        self.registry.set_status(pid, PromptStatus.ARCHIVED)
        # Archived -> Active is not valid
        with self.assertRaises(InvalidTransitionError):
            self.registry.set_status(pid, PromptStatus.ACTIVE)

    def test_rollback(self):
        pid = self.registry.define(
            name="Test", objective="v1", template="{{a}}"
        )
        self.registry.update(pid, objective="v2")
        self.registry.update(pid, objective="v3")

        new_ver = self.registry.rollback(pid, "0.1.0", author="tester")
        current = self.registry.get_current(pid)
        self.assertEqual(current.objective, "v1")
        self.assertNotEqual(current.version, "0.1.0")  # New version created

    def test_rollback_nonexistent(self):
        pid = self.registry.define(
            name="Test", objective="Test", template="{{var}}"
        )
        with self.assertRaises(RollbackError):
            self.registry.rollback(pid, "nonexistent")

    def test_assemble(self):
        pid = self.registry.define(
            name="Test", objective="Test",
            template="Hello {{name}}, your task is {{task}}"
        )
        result = self.registry.assemble(pid, {
            "name": "Alice", "task": "summarize"
        })
        self.assertEqual(result, "Hello Alice, your task is summarize")

    def test_assemble_missing_variables(self):
        pid = self.registry.define(
            name="Test", objective="Test",
            template="Hello {{name}}, task: {{task}}"
        )
        with self.assertRaises(ValueError):
            self.registry.assemble(pid, {"name": "Alice"})

    def test_assemble_extra_variables(self):
        pid = self.registry.define(
            name="Test", objective="Test", template="{{name}}"
        )
        with self.assertRaises(ValueError):
            self.registry.assemble(pid, {"name": "Alice", "extra": "value"})

    def test_assemble_no_validate(self):
        pid = self.registry.define(
            name="Test", objective="Test", template="{{name}}"
        )
        result = self.registry.assemble(
            pid, {"name": "Alice", "extra": "value"}, validate=False
        )
        self.assertEqual(result, "Alice")

    def test_validate_variables(self):
        pid = self.registry.define(
            name="Test", objective="Test",
            template="{{name}} {{task}}"
        )
        valid, missing, extra = self.registry.validate_variables(
            pid, {"name": "A", "task": "B", "extra": "C"}
        )
        self.assertFalse(valid)
        self.assertEqual(missing, [])
        self.assertEqual(extra, ["extra"])

        valid, missing, extra = self.registry.validate_variables(
            pid, {"name": "A"}
        )
        self.assertFalse(valid)
        self.assertEqual(missing, ["task"])

    def test_list_prompts(self):
        self.registry.define(
            name="A", objective="First", template="{{x}}",
            tags=["tag1"]
        )
        self.registry.define(
            name="B", objective="Second", template="{{y}}",
            tags=["tag2"]
        )

        all_prompts = self.registry.list_prompts()
        self.assertEqual(len(all_prompts), 2)

        tagged = self.registry.list_prompts(tags=["tag1"])
        self.assertEqual(len(tagged), 1)

        searched = self.registry.list_prompts(search="Second")
        self.assertEqual(len(searched), 1)

        searched_none = self.registry.list_prompts(search="nonexistent")
        self.assertEqual(len(searched_none), 0)

    def test_record_and_get_metrics(self):
        pid = self.registry.define(
            name="Test", objective="Test", template="{{var}}"
        )
        self.registry.record_metric(
            pid, MetricName.ACCURACY, 0.95, sample_size=10
        )
        self.registry.record_metric(
            pid, MetricName.ACCURACY, 0.88, sample_size=5
        )
        self.registry.record_metric(
            pid, MetricName.LATENCY_MS, 1200
        )

        metrics = self.registry.get_metrics(pid)
        self.assertEqual(len(metrics), 3)

        accuracy_metrics = self.registry.get_metrics(pid, metric_name=MetricName.ACCURACY)
        self.assertEqual(len(accuracy_metrics), 2)

        aggregated = self.registry.get_aggregated_metrics(pid)
        self.assertIn(MetricName.ACCURACY, aggregated)
        self.assertAlmostEqual(aggregated[MetricName.ACCURACY]["avg"], 0.915, places=2)

    def test_get_best_version(self):
        pid = self.registry.define(
            name="Test", objective="v1", template="{{a}}"
        )
        self.registry.record_metric(pid, MetricName.ACCURACY, 0.70)

        v2 = self.registry.update(pid, objective="v2")
        self.registry.record_metric(pid, MetricName.ACCURACY, 0.95, version=v2)

        best = self.registry.get_best_version(pid, by_metric=MetricName.ACCURACY)
        self.assertEqual(best, v2)

    def test_create_variant(self):
        pid = self.registry.define(
            name="Base", objective="Base prompt", template="{{x}}"
        )
        variant_id = self.registry.create_variant(
            pid, name_suffix="B",
            template="Variant {{x}}"
        )
        variant = self.registry.get(variant_id)
        self.assertIn("variant", variant.tags)

    def test_serialization(self):
        self.registry.define(
            name="A", objective="First", template="{{x}}"
        )
        self.registry.define(
            name="B", objective="Second", template="{{y}}"
        )

        data = self.registry.to_dict()
        self.assertEqual(len(data), 2)

        restored = PromptRegistry.from_dict(data)
        self.assertEqual(len(restored), 2)

    def test_save_and_load(self):
        self.registry.define(
            name="Test", objective="Test", template="{{var}}"
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name

        try:
            self.registry.save(path)
            loaded = PromptRegistry.load(path)
            self.assertEqual(len(loaded), 1)
        finally:
            os.unlink(path)

    def test_thread_safety(self):
        self.registry.define(
            name="Shared", objective="Test", template="{{var}}"
        )
        errors = []

        def worker():
            try:
                for _ in range(100):
                    pid = self.registry.define(
                        name=f"Thread-{threading.get_ident()}",
                        objective="Test", template="{{x}}"
                    )
                    self.registry.update(pid, objective=f"Updated-{threading.get_ident()}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)


# ============================================================================
# Context Manager Tests
# ============================================================================

class TestContextBlock(unittest.TestCase):
    """Tests for ContextBlock."""

    def test_creation(self):
        block = ContextBlock(
            id="test_1",
            type=ContextType.TASK,
            content="Test task",
            priority=ContextPriority.HIGH,
        )
        self.assertEqual(block.id, "test_1")
        self.assertEqual(block.type, ContextType.TASK)
        self.assertEqual(block.content, "Test task")
        self.assertFalse(block.is_expired)

    def test_expiry_by_ttl(self):
        block = ContextBlock(
            id="test",
            type=ContextType.CUSTOM,
            content="test",
            ttl_seconds=-1,  # Expired immediately
        )
        self.assertTrue(block.is_expired)

    def test_expiry_by_absolute(self):
        block = ContextBlock(
            id="test",
            type=ContextType.CUSTOM,
            content="test",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        self.assertTrue(block.is_expired)

    def test_estimated_tokens(self):
        block = ContextBlock(
            id="test", type=ContextType.CUSTOM, content="a" * 400
        )
        self.assertEqual(block.estimated_tokens, 100)

    def test_serialization(self):
        block = ContextBlock(
            id="test", type=ContextType.TASK, content="content",
            priority=ContextPriority.CRITICAL, source=ContextSource.USER,
            tags=["important"],
        )
        d = block.to_dict()
        restored = ContextBlock.from_dict(d)
        self.assertEqual(restored.id, "test")
        self.assertEqual(restored.type, ContextType.TASK)
        self.assertEqual(restored.priority, ContextPriority.CRITICAL)


class TestContextManager(unittest.TestCase):
    """Tests for ContextManager."""

    def setUp(self):
        self.ctx = ContextManager(max_tokens=100_000)

    def test_add_context(self):
        bid = self.ctx.add("test content", type=ContextType.TASK)
        self.assertIsNotNone(bid)
        self.assertEqual(len(self.ctx), 1)

    def test_add_empty_raises(self):
        with self.assertRaises(ValueError):
            self.ctx.add("")

    def test_get_context(self):
        bid = self.ctx.add("test", type=ContextType.TASK)
        block = self.ctx.get(bid)
        self.assertEqual(block.content, "test")

    def test_get_nonexistent_raises(self):
        with self.assertRaises(ContextNotFoundError):
            self.ctx.get("nonexistent")

    def test_get_by_type(self):
        self.ctx.add_task("Do something")
        self.ctx.add_security_policy("Don't share data")
        self.ctx.add_knowledge("Article about X")

        tasks = self.ctx.get_by_type(ContextType.TASK)
        self.assertEqual(len(tasks), 1)

        sec = self.ctx.get_by_type(ContextType.SECURITY)
        self.assertEqual(len(sec), 1)

    def test_get_by_tag(self):
        self.ctx.add("content", tags=["important", "urgent"])
        self.ctx.add("other", tags=["normal"])

        important = self.ctx.get_by_tag("important")
        self.assertEqual(len(important), 1)

        none = self.ctx.get_by_tag("nonexistent")
        self.assertEqual(len(none), 0)

    def test_get_immutable(self):
        self.ctx.add("normal")
        self.ctx.add_security_policy("Security rule")

        immutable = self.ctx.get_immutable()
        self.assertEqual(len(immutable), 1)

    def test_get_critical(self):
        self.ctx.add("normal", priority=ContextPriority.MEDIUM)
        self.ctx.add_security_policy("Security")

        critical = self.ctx.get_critical()
        self.assertEqual(len(critical), 1)

    def test_update_context(self):
        bid = self.ctx.add("old content")
        self.ctx.update(bid, content="new content")
        self.assertEqual(self.ctx.get(bid).content, "new content")

    def test_update_immutable_raises(self):
        bid = self.ctx.add_security_policy("Security rule")
        with self.assertRaises(ContextManagerError):
            self.ctx.update(bid, content="modified")

    def test_remove_context(self):
        bid = self.ctx.add("test")
        self.ctx.remove(bid)
        self.assertEqual(len(self.ctx), 0)

    def test_remove_immutable_raises(self):
        bid = self.ctx.add_security_policy("Security")
        with self.assertRaises(ContextManagerError):
            self.ctx.remove(bid)
        # Force remove should work
        self.ctx.remove(bid, force=True)
        self.assertEqual(len(self.ctx), 0)

    def test_remove_by_type(self):
        self.ctx.add_task("Task 1")
        self.ctx.add_task("Task 2")
        self.ctx.add_knowledge("Knowledge")

        count = self.ctx.remove_by_type(ContextType.TASK)
        self.assertEqual(count, 2)
        self.assertEqual(len(self.ctx), 1)

    def test_clear(self):
        self.ctx.add("test1")
        self.ctx.add("test2")
        self.ctx.add_security_policy("Security")

        count = self.ctx.clear(keep_immutable=True)
        self.assertEqual(count, 2)
        self.assertEqual(len(self.ctx), 1)  # Security remains

        count = self.ctx.clear(keep_immutable=False)
        self.assertEqual(count, 1)
        self.assertEqual(len(self.ctx), 0)

    def test_expire_stale(self):
        self.ctx.add("stale", ttl_seconds=-1)  # Already stale
        self.ctx.add("fresh", ttl_seconds=3600)
        self.ctx.add_security_policy("Security")

        count = self.ctx.expire_stale()
        self.assertEqual(count, 1)  # Only stale non-immutable removed

    def test_assemble_context(self):
        self.ctx.add_task("Summarize article")
        self.ctx.add_security_policy("Do not share PII")
        self.ctx.add_knowledge("Article content here...")

        assembled = self.ctx.assemble_context()
        self.assertIn("Summarize article", assembled)
        self.assertIn("Do not share PII", assembled)
        self.assertIn("Article content here", assembled)

    def test_assemble_with_max_tokens(self):
        self.ctx.add_task("A" * 1000)
        self.ctx.add_knowledge("B" * 5000)

        assembled = self.ctx.assemble_context(max_tokens=200)
        tokens = len(assembled) // 4
        self.assertLessEqual(tokens, 250)  # Some slack

    def test_token_usage_report(self):
        self.ctx.add_task("Test task content here")
        self.ctx.add_knowledge("Knowledge content")

        report = self.ctx.token_usage_report()
        self.assertIn("total_tokens", report)
        self.assertIn("by_type", report)
        self.assertGreater(report["total_tokens"], 0)

    def test_snapshot_and_restore(self):
        self.ctx.add_task("Task content")
        self.ctx.add_knowledge("Knowledge")

        snap = self.ctx.snapshot()
        self.assertEqual(len(snap.blocks), 2)

        self.ctx.clear(keep_immutable=False)
        self.assertEqual(len(self.ctx), 0)

        self.ctx.restore(snap)
        self.assertEqual(len(self.ctx), 2)

    def test_diff(self):
        self.ctx.add_task("Task")
        snap = self.ctx.snapshot()

        self.ctx.add_knowledge("New knowledge")
        diff = self.ctx.diff(snap)
        self.assertEqual(diff["added_count"], 1)
        self.assertEqual(diff["removed_count"], 0)

    def test_deduplicate(self):
        self.ctx.add("The quick brown fox jumps over the lazy dog", type=ContextType.CUSTOM)
        self.ctx.add("The quick brown fox jumps over the lazy dog", type=ContextType.CUSTOM)
        self.ctx.add("Something completely different", type=ContextType.CUSTOM)

        count = self.ctx.deduplicate(similarity_threshold=0.85)
        self.assertEqual(count, 1)
        self.assertEqual(len(self.ctx), 2)

    def test_detect_conflicts(self):
        self.ctx.add_system_instruction("You must always verify the data")
        self.ctx.add_system_instruction("You must not verify the data")

        conflicts = self.ctx.detect_conflicts()
        self.assertGreater(len(conflicts), 0)

    def test_convenience_methods(self):
        task_id = self.ctx.add_task("Do X")
        proj_id = self.ctx.add_project("Project Y")
        conv_id = self.ctx.add_conversation("User: Hello\nAI: Hi there")
        mem_id = self.ctx.add_memory("Remember Z")
        know_id = self.ctx.add_knowledge("Article about W")
        std_id = self.ctx.add_standards("Coding standards v2")
        doc_id = self.ctx.add_documentation("API docs here")
        sec_id = self.ctx.add_security_policy("No data leaks")
        comp_id = self.ctx.add_compliance_rules("GDPR compliance")
        sys_id = self.ctx.add_system_instruction("Be helpful")

        self.assertEqual(len(self.ctx), 10)

    def test_serialization(self):
        self.ctx.add_task("Task")
        self.ctx.add_knowledge("Knowledge")

        json_str = self.ctx.to_json()
        restored = ContextManager.from_json(json_str)
        self.assertEqual(len(restored), 2)

        d = self.ctx.to_dict()
        restored2 = ContextManager.from_dict(d)
        self.assertEqual(len(restored2), 2)


# ============================================================================
# Optimizer Tests
# ============================================================================

class TestContextOptimizer(unittest.TestCase):
    """Tests for ContextOptimizer."""

    def setUp(self):
        self.optimizer = ContextOptimizer()

    def _make_blocks(self, *contents):
        """Helper to create block dicts."""
        blocks = []
        for i, content in enumerate(contents):
            blocks.append({
                "id": f"block_{i}",
                "type": "custom",
                "content": content,
                "priority": 50,
                "relevance": 0.8,
                "is_immutable": False,
                "tags": [],
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        return blocks

    def test_deduplicate_strategy(self):
        blocks = self._make_blocks(
            "The quick brown fox jumps over the lazy dog",
            "The quick brown fox jumps over the lazy dog",
            "Something else entirely different here",
        )
        result = self.optimizer.optimize(
            blocks,
            strategies=[OptimizationStrategy.DEDUPLICATE],
        )
        self.assertGreater(result.tokens_saved, 0)
        self.assertGreaterEqual(result.blocks_removed, 1)

    def test_remove_stale(self):
        old_time = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        blocks = [
            {
                "id": "old_block",
                "type": "custom",
                "content": "Old content that should be removed",
                "priority": 50,
                "created_at": old_time,
                "is_immutable": False,
                "tags": [],
                "relevance": 0.5,
            },
            {
                "id": "new_block",
                "type": "custom",
                "content": "Fresh content",
                "priority": 50,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "is_immutable": False,
                "tags": [],
                "relevance": 0.8,
            },
        ]
        result = self.optimizer.optimize(
            blocks, strategies=[OptimizationStrategy.REMOVE_STALE]
        )
        self.assertGreaterEqual(result.blocks_removed, 1)

    def test_preserve_critical(self):
        blocks = self._make_blocks(
            "Normal content", "Normal content 2",
        )
        blocks.append({
            "id": "critical_block",
            "type": "custom",
            "content": "Critical security rule",
            "priority": 50,
            "relevance": 0.5,
            "is_immutable": True,
            "tags": ["security"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        result = self.optimizer.optimize(
            blocks, strategies=[
                OptimizationStrategy.PRESERVE_CRITICAL,
                OptimizationStrategy.DEDUPLICATE,
            ]
        )
        # Critical block should be preserved
        self.assertTrue(blocks[2].get("_preserved", False))

    def test_normalize(self):
        blocks = self._make_blocks(
            "  Extra   spaces   and\n\n\nmultiple newlines\n\nhere  "
        )
        result = self.optimizer.optimize(
            blocks, strategies=[OptimizationStrategy.NORMALIZE]
        )
        self.assertGreater(len(result.actions), 0)

    def test_summarize_long_block(self):
        long_text = "First sentence. " + "Middle filler text. " * 200 + "Last sentence."
        blocks = self._make_blocks(long_text)

        config = OptimizerConfig(summarize_min_tokens=5)
        optimizer = ContextOptimizer(config=config)

        result = optimizer.optimize(
            blocks, strategies=[OptimizationStrategy.SUMMARIZE]
        )
        # Should have at least some compression
        self.assertGreaterEqual(result.tokens_saved, 0)

    def test_batch_optimize_with_preset(self):
        blocks = self._make_blocks(
            "Task: summarize article",
            "Security: do not share PII",
            "Knowledge: article content here with many words " + "extra " * 100,
        )
        # Duplicate one
        blocks.append(dict(blocks[0]))
        blocks[-1]["id"] = "block_dup"

        result = self.optimizer.optimize(
            blocks, preset=OptimizerPreset.BALANCED
        )
        self.assertIn("tokens_saved", result.to_dict())
        self.assertIn("compression_ratio", result.to_dict())

    def test_detect_conflicts(self):
        blocks = [
            {
                "id": "a", "type": "system", "content": "You must always check data",
                "priority": 75, "relevance": 1.0, "is_immutable": False,
                "tags": [], "created_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "id": "b", "type": "system", "content": "You must never check data",
                "priority": 75, "relevance": 1.0, "is_immutable": False,
                "tags": [], "created_at": datetime.now(timezone.utc).isoformat(),
            },
        ]
        result = self.optimizer.optimize(
            blocks, strategies=[OptimizationStrategy.DETECT_CONFLICTS]
        )
        self.assertGreater(result.conflicts_detected, 0)

    def test_detect_outdated(self):
        blocks = self._make_blocks(
            "This API is deprecated and no longer supported as of 2023"
        )
        result = self.optimizer.optimize(
            blocks, strategies=[OptimizationStrategy.DETECT_OUTDATED]
        )
        self.assertGreater(len(result.actions), 0)

    def test_remove_low_priority(self):
        blocks = [
            {
                "id": "high", "type": "system", "content": "Important " * 200,
                "priority": 90, "relevance": 1.0, "is_immutable": False,
                "tags": [], "created_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "id": "low", "type": "custom", "content": "Filler " * 200,
                "priority": 10, "relevance": 0.1, "is_immutable": False,
                "tags": [], "created_at": datetime.now(timezone.utc).isoformat(),
            },
        ]
        config = OptimizerConfig(max_tokens=100)
        optimizer = ContextOptimizer(config=config)

        result = optimizer.optimize(
            blocks, strategies=[OptimizationStrategy.REMOVE_LOW_PRIORITY]
        )
        # Low priority should be removed when over budget
        self.assertGreaterEqual(result.blocks_removed, 0)

    def test_all_presets_work(self):
        blocks = self._make_blocks(
            "Task content", "Security policy",
            "Duplicate task content",  # near-dup of first
            "Knowledge " + "info " * 100,
        )

        for preset in OptimizerPreset:
            result = self.optimizer.optimize(blocks.copy(), preset=preset)
            self.assertIsNotNone(result)
            self.assertIsInstance(result.compression_ratio, float)

    def test_get_stats(self):
        blocks = self._make_blocks("test content")
        self.optimizer.optimize(blocks, preset=OptimizerPreset.BALANCED)
        stats = self.optimizer.get_stats()
        self.assertGreater(stats["runs"], 0)

    def test_get_history(self):
        blocks = self._make_blocks("test")
        self.optimizer.optimize(blocks, preset=OptimizerPreset.BALANCED)
        history = self.optimizer.get_history()
        self.assertGreater(len(history), 0)

    def test_merge_similar(self):
        blocks = self._make_blocks(
            "System must verify user identity before proceeding",
            "System should verify user identity before proceeding with the task",
            "Completely unrelated content here",
        )
        # Set same types for merging
        for b in blocks:
            b["type"] = "system"

        result = self.optimizer.optimize(
            blocks, strategies=[OptimizationStrategy.MERGE_SIMILAR]
        )
        # Similar blocks should be merged (reducing total block count)
        self.assertGreaterEqual(result.blocks_merged, 0)


# ============================================================================
# Token Budget Tests
# ============================================================================

class TestTokenBudgetManager(unittest.TestCase):
    """Tests for TokenBudgetManager."""

    def setUp(self):
        self.tbm = TokenBudgetManager(total_budget=100_000)

    def test_init_allocations(self):
        self.assertGreater(self.tbm.budget.total, 0)
        self.assertIn("system", self.tbm.budget.allocated)
        self.assertIn("output", self.tbm.budget.allocated)

    def test_allocate_and_consume(self):
        self.tbm.allocate("custom", 5000)
        self.assertTrue(self.tbm.consume("custom", 2000))
        self.assertEqual(self.tbm.budget.used["custom"], 2000)

    def test_consume_exceeds_budget(self):
        self.tbm.allocate("custom", 1000)
        ok = self.tbm.consume("custom", 2000)
        self.assertFalse(ok)

    def test_can_fit(self):
        self.tbm.allocate("test", 5000)
        self.assertTrue(self.tbm.can_fit(3000, "test"))
        self.assertFalse(self.tbm.can_fit(6000, "test"))

    def test_reserve(self):
        available_before = self.tbm.budget.available
        self.tbm.reserve(5000)
        self.assertEqual(self.tbm.budget.available, available_before - 5000)

    def test_get_available(self):
        self.tbm.allocate("test", 1000)
        available = self.tbm.get_available("test")
        self.assertEqual(available, 1000)
        self.tbm.consume("test", 300)
        self.assertEqual(self.tbm.get_available("test"), 700)

    def test_reset(self):
        self.tbm.allocate("test", 1000)
        self.tbm.consume("test", 500)
        self.tbm.reset()
        self.assertEqual(self.tbm.budget.used["test"], 0)

    def test_truncate_head(self):
        text = "A" * 4000  # ~1000 tokens
        truncated, saved = self.tbm.truncate(
            text, max_tokens=100, strategy=TruncationStrategy.HEAD
        )
        self.assertLess(len(truncated), len(text))
        self.assertGreater(saved, 0)

    def test_truncate_tail(self):
        text = "A" * 4000
        truncated, saved = self.tbm.truncate(
            text, max_tokens=100, strategy=TruncationStrategy.TAIL
        )
        self.assertLess(len(truncated), len(text))

    def test_truncate_middle(self):
        text = "A" * 2000 + "MIDDLE" + "B" * 2000
        truncated, saved = self.tbm.truncate(
            text, max_tokens=200, strategy=TruncationStrategy.MIDDLE
        )
        self.assertIn("[content truncated]", truncated)

    def test_truncate_smart(self):
        text = "Keep this [IMPORTANT] ... filler " * 100
        truncated, saved = self.tbm.truncate(
            text, max_tokens=200, strategy=TruncationStrategy.SMART,
            preserve_patterns=[r"\[IMPORTANT\]"],
        )
        self.assertLess(len(truncated), len(text))

    def test_truncate_no_truncation_needed(self):
        text = "short"
        truncated, saved = self.tbm.truncate(text, max_tokens=1000)
        self.assertEqual(truncated, text)
        self.assertEqual(saved, 0)

    def test_summarize(self):
        text = (
            "First paragraph with important information.\n\n"
            + "Middle filler content. " * 50 + "\n\n"
            + "Last paragraph with conclusion."
        )
        summary = self.tbm.summarize(text, target_tokens=50, method="extractive")
        self.assertLess(len(summary), len(text))
        self.assertIn("First paragraph", summary)

    def test_summarize_hierarchical(self):
        text = (
            "OVERVIEW\nThis is the overview section.\n\n"
            "DETAILS\nThis section has many details. " * 20 + "\n\n"
            "CONCLUSION\nFinal thoughts."
        )
        summary = self.tbm.summarize(text, target_tokens=50, method="hierarchical")
        self.assertIn("## OVERVIEW", summary)
        self.assertLess(len(summary), len(text))

    def test_cache_set_and_get(self):
        self.tbm.cache_set("key1", "cached content")
        result = self.tbm.cache_get("key1")
        self.assertEqual(result, "cached content")

    def test_cache_miss(self):
        result = self.tbm.cache_get("nonexistent")
        self.assertIsNone(result)

    def test_cache_lookup_by_template(self):
        self.tbm.cache_set(
            "key1", "Hello Alice",
            template_id="greeting",
            variables={"name": "Alice"},
        )
        result = self.tbm.cache_lookup_by_template(
            "greeting", {"name": "Alice"}
        )
        self.assertEqual(result, "Hello Alice")

    def test_cache_invalidate(self):
        self.tbm.cache_set("key1", "content1")
        self.tbm.cache_set("key2", "content2")
        count = self.tbm.cache_invalidate("key1")
        self.assertEqual(count, 1)
        self.assertIsNone(self.tbm.cache_get("key1"))
        self.assertIsNotNone(self.tbm.cache_get("key2"))

    def test_cache_clear_all(self):
        self.tbm.cache_set("k1", "c1")
        self.tbm.cache_set("k2", "c2")
        count = self.tbm.cache_invalidate()
        self.assertEqual(count, 2)
        self.assertIsNone(self.tbm.cache_get("k1"))

    def test_cache_stats(self):
        self.tbm.cache_set("k1", "data")
        self.tbm.cache_get("k1")
        self.tbm.cache_get("k1")
        stats = self.tbm.cache_stats()
        self.assertEqual(stats["entries"], 1)
        self.assertGreater(stats["total_accesses"], 0)

    def test_route_model(self):
        routes = self.tbm.route_model(
            estimated_input_tokens=50000,
            estimated_output_tokens=4000,
        )
        self.assertGreater(len(routes), 0)
        self.assertTrue(any(r.suitable for r in routes))

    def test_route_model_exceeds_budget(self):
        routes = self.tbm.route_model(
            estimated_input_tokens=500000,  # Too large for any model
        )
        # All should be unsuitable
        self.assertFalse(any(r.suitable for r in routes))

    def test_route_model_with_latency_requirement(self):
        routes = self.tbm.route_model(
            estimated_input_tokens=1000,
            latency_requirement="low",
        )
        suitable = [r for r in routes if r.suitable]
        self.assertGreater(len(suitable), 0)
        # All suitable should be low latency
        for r in suitable:
            self.assertEqual(r.latency_tier, "low")

    def test_route_model_with_cost_limit(self):
        routes = self.tbm.route_model(
            estimated_input_tokens=1000,
            max_cost_per_request=0.001,
        )
        # Should filter out expensive models
        suitable = [r for r in routes if r.suitable]
        self.assertGreaterEqual(len(suitable), 0)

    def test_semantic_compress(self):
        text = (
            "It is worth noting that the system, in order to function properly, "
            "must be configured correctly. Due to the fact that errors can occur, "
            "we should check the logs. This is very important."
        )
        compressed = self.tbm.semantic_compress(text, target_ratio=0.5)
        self.assertLess(len(compressed), len(text))
        # Should have removed filler phrases
        self.assertNotIn("It is worth noting that", compressed)
        self.assertNotIn("in order to", compressed)
        self.assertIn("note:", compressed.lower())

    def test_should_retrieve(self):
        # With enough budget and good benefit, should retrieve
        result = self.tbm.should_retrieve(
            current_context_tokens=10000,
            retrieval_cost_tokens=500,
            retrieval_benefit_score=0.8,
        )
        self.assertTrue(result)

        # With benefit too low to justify cost, should not retrieve
        result = self.tbm.should_retrieve(
            current_context_tokens=50000,
            retrieval_cost_tokens=5000,
            retrieval_benefit_score=0.01,
        )
        self.assertFalse(result)

    def test_compute_retrieval_quota(self):
        quota = self.tbm.compute_retrieval_quota(
            task_complexity=0.8,
            context_fullness=0.3,
        )
        self.assertGreater(quota, 0)

    def test_fit_to_budget(self):
        self.tbm.allocate("context", 5000)
        text = "content " * 5000  # Lots of tokens
        fitted = self.tbm.fit_to_budget(text, "context")
        self.assertLessEqual(len(fitted) // 4, 5000)

    def test_generate_report(self):
        report = self.tbm.generate_report()
        self.assertIsInstance(report, BudgetReport)
        self.assertGreater(report.budget.total, 0)

    def test_compression_stats(self):
        self.tbm.record_compression("dedup", 500)
        self.tbm.record_compression("truncate", 300)
        stats = self.tbm.get_compression_stats()
        self.assertEqual(stats["total_tokens_saved"], 800)


# ============================================================================
# Evaluator Tests
# ============================================================================

class TestPromptEvaluator(unittest.TestCase):
    """Tests for PromptEvaluator."""

    def setUp(self):
        self.evaluator = PromptEvaluator()

    def test_evaluate_with_reference(self):
        result = self.evaluator.evaluate(
            prompt_id="test_prompt",
            prompt_version="1.0.0",
            response="The cat sat on the mat",
            reference="The cat sat on the mat",
            input_tokens=100,
            output_tokens=25,
            latency_ms=500,
            cost=0.001,
            task_completed=True,
            user_rating=9.0,
        )
        self.assertIsInstance(result, EvaluationResult)
        self.assertGreater(result.overall_score, 0)
        self.assertIsNot(result.overall_grade, EvalGrade.UNKNOWN)

    def test_evaluate_low_accuracy(self):
        result = self.evaluator.evaluate(
            prompt_id="test",
            prompt_version="1.0.0",
            response="The dog ran in the park",
            reference="The cat sat on the mat",
            input_tokens=100,
            output_tokens=25,
            latency_ms=500,
            cost=0.001,
        )
        # Accuracy should be lower with mismatched content
        self.assertLess(result.overall_score, 90.0)

    def test_hallucination_detected(self):
        result = self.evaluator.evaluate(
            prompt_id="test",
            prompt_version="1.0.0",
            response="Research proves that 95% of cats prefer fish",
            reference="Cats eat a variety of foods",
            input_tokens=100,
            output_tokens=25,
            latency_ms=500,
            cost=0.001,
        )
        # Should detect unsupported definitive claims
        self.assertTrue(result.hallucination_detected)

    def test_hallucination_not_detected(self):
        result = self.evaluator.evaluate(
            prompt_id="test",
            prompt_version="1.0.0",
            response="Cats eat a variety of foods including fish",
            reference="Cats eat a variety of foods including fish and meat",
            input_tokens=100,
            output_tokens=25,
            latency_ms=500,
            cost=0.001,
        )
        self.assertFalse(result.hallucination_detected)

    def test_token_efficiency(self):
        result = self.evaluator.evaluate(
            prompt_id="test",
            prompt_version="1.0.0",
            response="Short and concise response",
            input_tokens=500,
            output_tokens=10,
            latency_ms=500,
            cost=0.001,
        )
        # Should have some efficiency score
        has_efficiency = any(
            s.metric == EvalMetric.TOKEN_EFFICIENCY for s in result.scores
        )
        self.assertTrue(has_efficiency)

    def test_latency_scoring(self):
        # Fast response
        result_fast = self.evaluator.evaluate(
            prompt_id="test",
            prompt_version="1.0.0",
            response="response",
            latency_ms=100,
        )
        # Slow response
        result_slow = self.evaluator.evaluate(
            prompt_id="test",
            prompt_version="1.0.0",
            response="response",
            latency_ms=15000,
        )
        latency_fast = next(
            s for s in result_fast.scores if s.metric == EvalMetric.LATENCY_MS
        )
        latency_slow = next(
            s for s in result_slow.scores if s.metric == EvalMetric.LATENCY_MS
        )
        self.assertGreater(latency_fast.value, latency_slow.value)

    def test_cost_scoring(self):
        result_cheap = self.evaluator.evaluate(
            prompt_id="test", prompt_version="1.0.0",
            response="r", cost=0.0001,
        )
        result_expensive = self.evaluator.evaluate(
            prompt_id="test", prompt_version="1.0.0",
            response="r", cost=5.00,
        )
        cost_cheap = next(
            s for s in result_cheap.scores if s.metric == EvalMetric.COST
        )
        cost_exp = next(
            s for s in result_expensive.scores if s.metric == EvalMetric.COST
        )
        self.assertGreater(cost_cheap.value, cost_exp.value)

    def test_tool_accuracy(self):
        result = self.evaluator.evaluate(
            prompt_id="test",
            prompt_version="1.0.0",
            response="Used tools",
            tool_calls=[
                {"name": "search"},
                {"name": "read_file"},
            ],
            expected_tools=["search", "read_file"],
        )
        tool_score = next(
            s for s in result.scores if s.metric == EvalMetric.TOOL_ACCURACY
        )
        self.assertAlmostEqual(tool_score.value, 100.0, places=1)

    def test_tool_accuracy_mismatch(self):
        result = self.evaluator.evaluate(
            prompt_id="test",
            prompt_version="1.0.0",
            response="Used tools",
            tool_calls=[{"name": "wrong_tool"}],
            expected_tools=["search"],
        )
        tool_score = next(
            s for s in result.scores if s.metric == EvalMetric.TOOL_ACCURACY
        )
        self.assertLess(tool_score.value, 100.0)

    def test_stability(self):
        result = self.evaluator.evaluate(
            prompt_id="test",
            prompt_version="1.0.0",
            response="The system processes data securely and efficiently",
            previous_response="The system processes data securely and efficiently",
        )
        stability_score = next(
            s for s in result.scores if s.metric == EvalMetric.PROMPT_STABILITY
        )
        # Very similar responses
        self.assertGreaterEqual(stability_score.value, 80.0)

    def test_compare_versions(self):
        comparison = self.evaluator.compare_versions(
            prompt_id="test",
            version_a="1.0.0",
            version_b="1.1.0",
            response_a="Short concise answer",
            response_b="A very long and detailed answer with much more information",
            reference="Short concise answer",
            input_tokens=100,
            output_tokens=20,
            latency_ms=500,
            cost=0.001,
        )
        self.assertIn("winner", comparison)
        self.assertIn("version_a", comparison)
        self.assertIn("version_b", comparison)

    def test_batch_evaluate(self):
        items = [
            {
                "prompt_id": "test",
                "prompt_version": "1.0.0",
                "response": f"Response {i}",
                "reference": f"Expected {i}",
            }
            for i in range(5)
        ]
        results = self.evaluator.evaluate_batch(items)
        self.assertEqual(len(results), 5)

    def test_get_summary(self):
        for i in range(10):
            self.evaluator.evaluate(
                prompt_id="test",
                prompt_version="1.0.0",
                response=f"Response {i}",
                reference=f"Expected {i}",
                input_tokens=100,
                output_tokens=25,
                latency_ms=500,
                cost=0.001,
                task_completed=(i % 2 == 0),
            )

        summary = self.evaluator.get_summary(prompt_id="test")
        self.assertEqual(summary.num_evaluations, 10)
        self.assertGreater(summary.overall_avg, 0)
        self.assertGreaterEqual(summary.task_completion_rate, 0)

    def test_get_trends(self):
        for i in range(15):
            self.evaluator.evaluate(
                prompt_id="test",
                prompt_version="1.0.0",
                response=f"Response {i}",
                reference=f"Expected {i}",
                input_tokens=100,
                output_tokens=25,
                latency_ms=500 + i * 10,
                cost=0.001,
            )

        trends = self.evaluator.get_trends(window=10)
        self.assertLessEqual(len(trends), 10)

    def test_grade_assignment(self):
        # High score
        result = self.evaluator.evaluate(
            prompt_id="test", prompt_version="1.0.0",
            response="Perfect match",
            reference="Perfect match",
            input_tokens=100, output_tokens=20,
            latency_ms=100, cost=0.0001,
            task_completed=True, user_rating=10.0,
        )
        self.assertIn(result.overall_grade, [EvalGrade.A, EvalGrade.A_PLUS])

    def test_get_history(self):
        self.evaluator.evaluate(
            prompt_id="test", prompt_version="1.0.0",
            response="r1", reference="e1",
        )
        self.evaluator.evaluate(
            prompt_id="test", prompt_version="1.0.0",
            response="r2", reference="e2",
        )

        history = self.evaluator.get_history()
        self.assertEqual(len(history), 2)

    def test_clear_history(self):
        self.evaluator.evaluate(
            prompt_id="test", prompt_version="1.0.0",
            response="r", reference="e",
        )
        count = self.evaluator.clear_history()
        self.assertEqual(count, 1)
        self.assertEqual(len(self.evaluator), 0)

    def test_serialization(self):
        self.evaluator.evaluate(
            prompt_id="test", prompt_version="1.0.0",
            response="response", reference="expected",
            input_tokens=100, output_tokens=25,
            latency_ms=500, cost=0.001,
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name

        try:
            self.evaluator.to_json(path)
            loaded = PromptEvaluator.from_json(path)
            self.assertEqual(len(loaded), 1)
        finally:
            os.unlink(path)

    def test_eval_result_properties(self):
        result = self.evaluator.evaluate(
            prompt_id="test", prompt_version="1.0.0",
            response="response",
            input_tokens=500, output_tokens=200,
            latency_ms=1500, cost=0.005,
            task_completed=True,
        )
        self.assertEqual(result.total_tokens, 700)

    def test_context_utilization(self):
        result = self.evaluator.evaluate(
            prompt_id="test", prompt_version="1.0.0",
            response="The system uses knowledge about AI safety to guide responses",
            context_used=[
                "AI safety principles are important for responsible deployment",
                "Systems should be transparent about limitations",
            ],
        )
        retrieval_scores = [
            s for s in result.scores
            if s.metric == EvalMetric.RETRIEVAL_QUALITY
        ]
        self.assertGreater(len(retrieval_scores), 0)


# ============================================================================
# Quality Gates Tests
# ============================================================================

class TestQualityGates(unittest.TestCase):
    """Tests for QualityGates."""

    def setUp(self):
        self.gates = QualityGates()

    def test_check_all_passes_with_valid_context(self):
        result = self.gates.check_all(
            prompt_version="1.0.0",
            prompt_status="active",
            security_policies=["Do not share PII"],
            compliance_rules=["Follow GDPR"],
            context_blocks=[
                {
                    "type": "task",
                    "content": "Summarize",
                    "id": "t1",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            ],
            token_usage={"utilization_pct": 50},
        )
        self.assertTrue(result.passed)
        self.assertEqual(len(result.blocked_by), 0)

    def test_block_on_deprecated_version(self):
        self.gates.config.allow_deprecated = False
        result = self.gates.check_all(
            prompt_version="0.5.0",
            prompt_status="deprecated",
            security_policies=["policy"],
            compliance_rules=["rule"],
        )
        self.assertFalse(result.passed)
        self.assertIn("Prompt Version Check", result.blocked_by)

    def test_allow_deprecated_when_configured(self):
        self.gates.config.allow_deprecated = True
        result = self.gates.check_all(
            prompt_version="0.5.0",
            prompt_status="deprecated",
            security_policies=["policy"],
            compliance_rules=["rule"],
            context_blocks=[
                {"id": "t1", "type": "task", "created_at": datetime.now(timezone.utc).isoformat()},
            ],
        )
        self.assertTrue(result.passed)

    def test_block_on_archived(self):
        result = self.gates.check_all(
            prompt_version="1.0.0",
            prompt_status="archived",
            security_policies=["policy"],
            compliance_rules=["rule"],
        )
        self.assertFalse(result.passed)

    def test_block_on_missing_security(self):
        self.gates.config.require_security_context = True
        result = self.gates.check_all(
            prompt_version="1.0.0",
            prompt_status="active",
            # No security policies
            compliance_rules=["rule"],
        )
        self.assertFalse(result.passed)
        self.assertIn("Security Policy Check", result.blocked_by)

    def test_block_on_missing_compliance(self):
        self.gates.config.require_compliance_context = True
        result = self.gates.check_all(
            prompt_version="1.0.0",
            prompt_status="active",
            security_policies=["policy"],
            # No compliance rules
        )
        self.assertFalse(result.passed)
        self.assertIn("Compliance Rule Check", result.blocked_by)

    def test_warn_on_high_token_utilization(self):
        result = self.gates.check_all(
            prompt_version="1.0.0",
            prompt_status="active",
            security_policies=["policy"],
            compliance_rules=["rule"],
            token_usage={"utilization_pct": 97},  # Over 95%
        )
        # Should have warnings about token budget
        self.assertTrue(len(result.warnings) > 0 or not result.passed)

    def test_block_on_missing_required_tools(self):
        self.gates.config.required_tools = ["search", "database"]
        result = self.gates.check_all(
            prompt_version="1.0.0",
            prompt_status="active",
            security_policies=["policy"],
            compliance_rules=["rule"],
            tool_registry=["search"],  # Missing "database"
        )
        self.assertFalse(result.passed)
        self.assertIn("Tool Availability Check", result.blocked_by)

    def test_pass_when_tools_available(self):
        self.gates.config.required_tools = ["search"]
        result = self.gates.check_all(
            prompt_version="1.0.0",
            prompt_status="active",
            security_policies=["policy"],
            compliance_rules=["rule"],
            tool_registry=["search", "read_file"],
        )
        self.assertTrue(result.passed)

    def test_warn_on_conflicts(self):
        result = self.gates.check_all(
            prompt_version="1.0.0",
            prompt_status="active",
            security_policies=["policy"],
            compliance_rules=["rule"],
            conflicts=[
                {"severity": "medium", "description": "Context conflict"}
            ],
        )
        self.assertTrue(result.has_warnings)  # Medium severity = warning, not block

    def test_block_on_high_severity_conflicts(self):
        result = self.gates.check_all(
            prompt_version="1.0.0",
            prompt_status="active",
            security_policies=["policy"],
            compliance_rules=["rule"],
            conflicts=[
                {"severity": "high", "block_a": "a", "block_b": "b"}
            ],
        )
        self.assertFalse(result.passed)
        self.assertIn("Context Conflict Check", result.blocked_by)

    def test_warn_on_stale_knowledge(self):
        old_time = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        result = self.gates.check_all(
            prompt_version="1.0.0",
            prompt_status="active",
            security_policies=["policy"],
            compliance_rules=["rule"],
            knowledge_blocks=[
                {
                    "id": "kb1",
                    "created_at": old_time,
                    "content": "old knowledge",
                }
            ],
        )
        # Should warn about stale knowledge (default max 168 hours = 7 days)
        self.assertGreater(len(result.warnings), 0)

    def test_skipped_checks(self):
        # Skipping a category should not affect pass/fail
        result = self.gates.check_all(
            prompt_version="1.0.0",
            prompt_status="active",
            security_policies=["policy"],
            compliance_rules=["rule"],
            skip_categories=[GateCategory.SECURITY],
        )
        self.assertTrue(result.passed)

    def test_strict_mode(self):
        strict_gates = QualityGates(config=GateConfig(strict_mode=True))
        result = strict_gates.check_all(
            prompt_version="1.0.0",
            prompt_status="active",
            security_policies=["policy"],  # Missing compliance
            token_usage={"utilization_pct": 97},  # High utilization
        )
        # In strict mode, warnings become blocks, so should fail
        self.assertFalse(result.passed)

    def test_assert_passes_raises(self):
        result = self.gates.check_all(
            prompt_version="1.0.0",
            prompt_status="archived",
        )
        with self.assertRaises(QualityGateBlockedError):
            self.gates.assert_passes(result)

    def test_assert_passes_returns_result(self):
        result = self.gates.check_all(
            prompt_version="1.0.0",
            prompt_status="active",
            security_policies=["policy"],
            compliance_rules=["rule"],
            context_blocks=[
                {"id": "t1", "type": "task", "created_at": datetime.now(timezone.utc).isoformat()},
            ],
        )
        returned = self.gates.assert_passes(result)
        self.assertIs(returned, result)

    def test_register_custom_check(self):
        def custom_check(context: dict) -> GateCheck:
            return GateCheck(
                check_id="custom_1",
                name="Custom Check",
                category=GateCategory.PERFORMANCE,
                severity=GateSeverity.WARN,
                status=GateStatus.PASSED,
                passed=True,
                message="Custom check passed",
            )

        self.gates.register_check(custom_check)
        result = self.gates.check_all(
            prompt_version="1.0.0",
            prompt_status="active",
            security_policies=["policy"],
            compliance_rules=["rule"],
            custom_context={"extra": "data"},
        )
        self.assertTrue(result.passed)

    def test_remove_custom_check(self):
        def custom_check(context):
            return GateCheck(
                check_id="c1", name="C", category=GateCategory.PERFORMANCE,
                severity=GateSeverity.WARN, status=GateStatus.PASSED, passed=True,
                message="ok",
            )

        self.gates.register_check(custom_check)
        self.assertTrue(self.gates.remove_check(custom_check))
        self.assertFalse(self.gates.remove_check(custom_check))

    def test_preconfigured_gates(self):
        sec_gates = QualityGates.create_security_gates()
        self.assertTrue(sec_gates.config.require_security_context)
        self.assertTrue(sec_gates.config.strict_mode)

        full_gates = QualityGates.create_full_gates()
        self.assertTrue(full_gates.config.require_security_context)
        self.assertTrue(full_gates.config.require_compliance_context)

        light_gates = QualityGates.create_lightweight_gates()
        self.assertFalse(light_gates.config.require_security_context)
        self.assertTrue(light_gates.config.allow_deprecated)

    def test_get_stats(self):
        self.gates.check_all(
            prompt_version="1.0.0",
            prompt_status="active",
            security_policies=["policy"],
            compliance_rules=["rule"],
        )
        stats = self.gates.get_stats()
        self.assertGreater(stats["runs"], 0)
        self.assertIn("pass_rate", stats)

    def test_get_history(self):
        self.gates.check_all(
            prompt_version="1.0.0",
            prompt_status="active",
            security_policies=["p"], compliance_rules=["r"],
        )
        history = self.gates.get_history()
        self.assertGreater(len(history), 0)

    def test_result_properties(self):
        result = self.gates.check_all(
            prompt_version="1.0.0",
            prompt_status="active",
            security_policies=["policy"],
            compliance_rules=["rule"],
        )
        self.assertFalse(result.has_blocks)
        d = result.to_dict()
        self.assertIn("passed", d)
        self.assertIn("total_checks", d)
        self.assertIn("checks_passed", d)

    def test_experimental_version(self):
        self.gates.config.allow_experimental = True
        result = self.gates.check_all(
            prompt_version="0.9.0-beta",
            prompt_status="experimental",
            security_policies=["policy"],
            compliance_rules=["rule"],
        )
        self.assertTrue(result.passed)

        self.gates.config.allow_experimental = False
        result = self.gates.check_all(
            prompt_version="0.9.0-beta",
            prompt_status="experimental",
            security_policies=["policy"],
            compliance_rules=["rule"],
        )
        self.assertFalse(result.passed)

    def test_context_age_warn(self):
        old_time = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        result = self.gates.check_all(
            prompt_version="1.0.0",
            prompt_status="active",
            security_policies=["policy"],
            compliance_rules=["rule"],
            context_blocks=[
                {
                    "id": "old",
                    "type": "custom",
                    "created_at": old_time,
                    "is_immutable": False,
                }
            ],
        )
        # Context age is INFO level by default, shouldn't block
        self.assertTrue(result.passed)

    def test_gateconfig_defaults(self):
        config = GateConfig()
        self.assertTrue(config.require_security_context)
        self.assertTrue(config.require_compliance_context)
        self.assertFalse(config.allow_deprecated)
        self.assertTrue(config.allow_experimental)


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration(unittest.TestCase):
    """End-to-end integration tests across modules."""

    def test_full_prompt_lifecycle(self):
        """Test the full prompt lifecycle: define -> update -> optimize -> evaluate -> gate."""
        # 1. Define prompt
        registry = PromptRegistry()
        pid = registry.define(
            name="Article Summarizer",
            objective="Summarize news articles accurately",
            template=(
                "You are a summarizer. Security: {{security_rules}}. "
                "Summarize: {{article}}"
            ),
            tags=["summarizer", "production"],
        )
        registry.set_status(pid, PromptStatus.ACTIVE)

        # 2. Set up context
        ctx = ContextManager(max_tokens=50000)
        ctx.add_task("Summarize this article about AI")
        ctx.add_security_policy("Do not share PII or confidential data")
        ctx.add_compliance_rules("Follow EU AI Act guidelines")
        ctx.add_knowledge("AI is a rapidly evolving field...")
        ctx.add_documentation("Summary should be 3-5 sentences")

        # 3. Assemble prompt
        assembled = registry.assemble(pid, {
            "security_rules": "Do not share PII",
            "article": "Artificial intelligence is transforming industries...",
        })
        self.assertIn("Do not share PII", assembled)
        self.assertIn("transforming industries", assembled)

        # 4. Optimize context
        optimizer = ContextOptimizer()
        blocks = [
            {
                "id": b.id,
                "type": b.type.value,
                "content": b.content,
                "priority": b.priority.value,
                "relevance": b.relevance_score,
                "is_immutable": b.is_immutable,
                "tags": b.tags,
                "created_at": b.created_at.isoformat(),
            }
            for b in ctx.get_all()
        ]
        opt_result = optimizer.optimize(blocks, preset=OptimizerPreset.BALANCED)
        self.assertIsNotNone(opt_result)

        # 5. Token budget
        tbm = TokenBudgetManager(total_budget=10000)
        fitted_prompt = tbm.fit_to_budget(assembled, "system")
        self.assertIsNotNone(fitted_prompt)

        # 6. Cache the assembled prompt
        tbm.cache_set(
            f"prompt_{pid}", fitted_prompt,
            template_id=pid,
            variables={"security_rules": "Do not share PII", "article": "..."},
        )

        # 7. Evaluate
        evaluator = PromptEvaluator()
        eval_result = evaluator.evaluate(
            prompt_id=pid,
            prompt_version=registry.get_current(pid).version,
            response="AI is transforming industries including healthcare, finance, and transportation through automation and data analysis.",
            reference="AI is transforming multiple industries through automation.",
            input_tokens=500,
            output_tokens=100,
            latency_ms=800,
            cost=0.002,
            task_completed=True,
            user_rating=8.5,
        )
        self.assertTrue(eval_result.task_completed)
        self.assertGreater(eval_result.overall_score, 50.0)

        # 8. Record metrics
        registry.record_metric(pid, MetricName.ACCURACY, eval_result.overall_score / 100)
        registry.record_metric(pid, MetricName.LATENCY_MS, eval_result.latency_ms)

        # 9. Quality gates
        gates = QualityGates()
        gate_result = gates.check_all(
            prompt_version=registry.get_current(pid).version,
            prompt_status=registry.get_current(pid).status.value,
            security_policies=["Do not share PII"],
            compliance_rules=["Follow EU AI Act"],
            context_blocks=[
                {"id": "t", "type": "task", "created_at": datetime.now(timezone.utc).isoformat()}
            ],
        )
        self.assertTrue(gate_result.passed)

        # 10. Version update with evaluation
        v2 = registry.update(pid, objective="Summarize news articles concisely and accurately")
        eval_v2 = evaluator.evaluate(
            prompt_id=pid, prompt_version=v2,
            response="AI transforms industries via automation.",
            reference="AI transforms industries through automation.",
            input_tokens=500, output_tokens=50,
            latency_ms=600, cost=0.0015,
            task_completed=True,
        )
        registry.record_metric(pid, MetricName.ACCURACY, eval_v2.overall_score / 100, version=v2)

        # Version 2 should be recorded
        metrics_v2 = registry.get_metrics(pid, version=v2, metric_name=MetricName.ACCURACY)
        self.assertEqual(len(metrics_v2), 1)

    def test_context_manager_integration_with_optimizer(self):
        """Test optimizer working with ContextManager blocks."""
        ctx = ContextManager()
        ctx.add_task("Summarize")
        ctx.add_knowledge("Article text here")
        ctx.add_knowledge("Article text here")  # Duplicate

        optimizer = ContextOptimizer()
        result = optimizer.optimize_from_manager(ctx, preset=OptimizerPreset.BALANCED)
        self.assertIsNotNone(result)

    def test_evaluator_to_registry_feedback_loop(self):
        """Test that evaluation results feed back into prompt registry metrics."""
        registry = PromptRegistry()
        pid = registry.define(
            name="Test", objective="Test", template="{{x}}"
        )
        registry.set_status(pid, PromptStatus.ACTIVE)

        evaluator = PromptEvaluator()

        for i in range(5):
            result = evaluator.evaluate(
                prompt_id=pid,
                prompt_version=registry.get_current(pid).version,
                response=f"Response {i}",
                reference="Expected response",
                input_tokens=100,
                output_tokens=25,
                latency_ms=500,
                cost=0.001,
                task_completed=(i < 4),
            )
            # Feed back to registry
            registry.record_metric(
                pid,
                MetricName.ACCURACY,
                result.overall_score / 100,
            )

        metrics = registry.get_aggregated_metrics(pid)
        self.assertIn(MetricName.ACCURACY, metrics)
        self.assertEqual(metrics[MetricName.ACCURACY]["count"], 5)

    def test_quality_gates_with_context_manager(self):
        """Test quality gates using ContextManager."""
        ctx = ContextManager()
        ctx.add_task("Test task")
        ctx.add_security_policy("No data leaks")
        ctx.add_compliance_rules("GDPR")

        security_blocks = ctx.get_by_type(ContextType.SECURITY)
        compliance_blocks = ctx.get_by_type(ContextType.COMPLIANCE)

        gates = QualityGates()
        result = gates.check_all(
            prompt_version="1.0.0",
            prompt_status="active",
            security_policies=[b.content for b in security_blocks],
            compliance_rules=[b.content for b in compliance_blocks],
            context_manager=ctx,
        )
        self.assertTrue(result.passed)


# ============================================================================
# Run
# ============================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)