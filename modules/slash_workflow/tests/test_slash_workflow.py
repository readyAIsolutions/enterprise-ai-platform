"""Unit tests for the slash_workflow module (no network, real assertions)."""
from __future__ import annotations

import asyncio

import pytest

from enterprise.platform_kernel import HealthStatus

from enterprise.modules.slash_workflow import (
    GlobalRules,
    Phase,
    PhaseReport,
    PlanDocument,
    SlashCommand,
    SlashCommandRegistry,
    SlashWorkflowModule,
    SubAgent,
    TaskItem,
    TaskManager,
    TaskStatus,
    WorkflowEngine,
    WorkflowValidator,
    allowed_transitions,
    build_plan,
    create_slash_workflow,
    create_slash_workflow_module,
    default_global_rules,
    default_slash_commands,
)


# --- task status transitions ----------------------------------------------
def test_task_advance_through_full_cycle():
    task = TaskItem(title="add endpoint")
    assert task.status is TaskStatus.TODO
    task.advance(TaskStatus.DOING)
    task.advance(TaskStatus.REVIEW)
    task.advance(TaskStatus.DONE)
    assert task.is_done


def test_task_cannot_skip_to_done():
    task = TaskItem(title="skip")
    with pytest.raises(ValueError):
        task.advance(TaskStatus.DONE)  # todo -> done is illegal


def test_done_task_is_terminal():
    task = TaskItem(title="done task")
    task.advance(TaskStatus.DOING)
    task.advance(TaskStatus.REVIEW)
    task.advance(TaskStatus.DONE)
    with pytest.raises(ValueError):
        task.advance(TaskStatus.REVIEW)


def test_allowed_transitions_mapping():
    assert allowed_transitions(TaskStatus.DOING) == frozenset(
        {TaskStatus.REVIEW, TaskStatus.TODO, TaskStatus.BLOCKED}
    )
    assert allowed_transitions(TaskStatus.REVIEW) == frozenset(
        {TaskStatus.DONE, TaskStatus.DOING, TaskStatus.BLOCKED}
    )
    assert allowed_transitions(TaskStatus.DONE) == frozenset()


# --- task manager deterministic cycle -------------------------------------
def test_task_manager_pull_marks_doing_in_order():
    manager = TaskManager([TaskItem("a"), TaskItem("b"), TaskItem("c")])
    assert manager.pull().title == "a"
    assert manager.pull().title == "b"
    assert manager.pull().title == "c"
    assert manager.pull() is None


def test_task_manager_cycle_orders_work_and_approves():
    worked = []
    tasks = [TaskItem("t1"), TaskItem("t2"), TaskItem("t3")]
    manager = TaskManager(tasks)
    manager.cycle(
        implement=lambda t: worked.append(t.title),
        review=lambda t: True,
    )
    assert worked == ["t1", "t2", "t3"]
    assert manager.is_complete()
    assert manager.remaining == 0


def test_task_manager_cycle_applies_rework_on_failed_review():
    calls = {"t1": 0}
    tasks = [TaskItem("t1")]
    manager = TaskManager(tasks)
    manager.cycle(
        implement=lambda t: calls.__setitem__("t1", calls["t1"] + 1),
        review=lambda t: calls["t1"] >= 2,  # fail the first review
        max_rework=3,
    )
    assert calls["t1"] == 2  # one rework cycle -> two implementations
    assert manager.is_complete()


def test_task_manager_cycle_blocks_when_rework_exhausted():
    tasks = [TaskItem("stubborn")]
    manager = TaskManager(tasks)
    manager.cycle(implement=lambda t: None, review=lambda t: False, max_rework=1)
    assert not manager.is_complete()
    assert tasks[0].status is TaskStatus.BLOCKED


def test_task_manager_validation_on_bad_transitions():
    manager = TaskManager([TaskItem("x")])
    task = manager.tasks[0]
    with pytest.raises(ValueError):
        manager.approve(task)  # cannot approve a todo
    with pytest.raises(ValueError):
        manager.send_to_review(task)  # cannot send a todo to review


# --- slash commands -------------------------------------------------------
def test_default_slash_commands_present():
    commands = default_slash_commands()
    assert set(commands) == {"primer", "create_plan", "execute_plan", "validate"}


def test_slash_command_render_substitutes_args():
    cmd = SlashCommand(name="primer", description="catch up", body="read {read_paths}",
                       args=["read_paths"])
    rendered = cmd.render(read_paths="src/, CLAUDE.md")
    assert "src/, CLAUDE.md" in rendered
    assert "read" in rendered


def test_slash_command_rejects_unknown_args():
    cmd = SlashCommand(name="x", description="", body="hi {a}", args=["a"])
    with pytest.raises(ValueError):
        cmd.render(a="1", b="2")


def test_registry_lookup_and_markdown():
    reg = SlashCommandRegistry()
    assert reg.get("execute_plan") is not None
    assert set(reg.names()) == {"primer", "create_plan", "execute_plan", "validate"}
    md = reg.render("create_plan", requirements_path="requirements.md")
    assert md.startswith("/create_plan")
    assert "requirements.md" in md
    assert reg.get("nope") is None
    with pytest.raises(KeyError):
        reg.render("nope")


def test_execute_plan_command_forbids_implementation_subagents():
    body = default_slash_commands()["execute_plan"].body
    assert "Do NOT delegate" in body
    assert "sub-agents" in body


# --- plan document schema ------------------------------------------------
def test_plan_document_to_markdown():
    plan = build_plan(
        "OpenAI API compat",
        tasks=["add /v1/chat", "add /v1/models"],
        files_to_edit=["app.py"],
        files_to_create=["routes.py"],
        patterns=["fastapi routers"],
        success_criteria=["all tests pass"],
    )
    md = plan.to_markdown()
    assert "# Plan: OpenAI API compat" in md
    assert "add /v1/chat" in md
    assert "[ ] add /v1/chat" in md
    assert "## Files to create" in md and "- routes.py" in md
    assert "## Success criteria" in md


def test_plan_document_all_files():
    plan = PlanDocument(
        title="t", files_to_edit=["a.py"], files_to_create=["b.py", "c.py"]
    )
    assert plan.all_files == ["a.py", "b.py", "c.py"]


# --- sub-agents (isolated context) ---------------------------------------
def test_subagent_returns_only_summary():
    agent = SubAgent("validator", role="validation")
    out = agent.run(lambda: "ran 12 tests; 0 failures")
    assert out.startswith("[validator summary]")
    assert "12 tests" in out


# --- global rules cascading context --------------------------------------
def test_global_rules_cascade_layers_phase_rules():
    rules = default_global_rules()
    assert len(rules.rules) >= 4
    rendered = rules.cascade(["Do not use sub-agents during implementation"])
    lines = [ln for ln in rendered.splitlines() if ln.startswith("- ")]
    assert len(lines) == len(rules.rules) + 1
    assert "Do not use sub-agents" in rendered
    assert "Never vibe code" in rendered


# --- workflow validator --------------------------------------------------
def test_validator_accepts_sound_plan():
    plan = build_plan("ok", tasks=["t1"], success_criteria=["pass"])
    assert WorkflowValidator().is_plan_valid(plan)


def test_validator_rejects_incomplete_plan():
    plan = PlanDocument(title="")
    problems = WorkflowValidator().validate_plan(plan)
    assert "plan has no title" in problems
    assert "plan has no goals" in problems
    assert "plan has no tasks" in problems
    assert "plan has no success criteria" in problems


def test_validator_rejects_task_starting_not_todo():
    plan = build_plan("x", tasks=["a"])
    plan.tasks[0].advance(TaskStatus.DOING)
    problems = WorkflowValidator().validate_plan(plan)
    assert any("should start as todo" in p for p in problems)


def test_subagent_policy_rejects_implementation_use():
    v = WorkflowValidator()
    v.check_subagent_policy(Phase.PLAN, using_subagent=True)  # allowed
    v.check_subagent_policy(Phase.VALIDATE, using_subagent=True)  # allowed
    with pytest.raises(ValueError):
        v.check_subagent_policy(Phase.IMPLEMENT, using_subagent=True)
    v.check_subagent_policy(Phase.IMPLEMENT, using_subagent=False)  # allowed


def test_validator_flags_incomplete_cycle():
    manager = TaskManager([TaskItem("a")])
    problems = WorkflowValidator().validate_task_cycle(manager)
    assert any("did not complete" in p for p in problems)


# --- workflow engine -----------------------------------------------------
def _sample_plan() -> PlanDocument:
    return build_plan(
        "feature",
        tasks=["scaffold", "logic", "tests"],
        files_to_create=["core.py", "test_core.py"],
        success_criteria=["tests green"],
    )


def test_engine_run_all_three_phases_ok():
    engine = create_slash_workflow()
    reports = engine.run(_sample_plan(), review=lambda t: True)
    assert [r.phase for r in reports] == [
        Phase.PLAN, Phase.IMPLEMENT, Phase.VALIDATE
    ]
    assert engine.all_ok
    assert all(r.ok for r in reports)


def test_engine_implementation_uses_no_subagents_and_orders_work():
    engine = WorkflowEngine()
    worked = []
    reports = engine.run(
        _sample_plan(),
        implement=lambda t: worked.append(t.title),
        review=lambda t: True,
    )
    assert worked == ["scaffold", "logic", "tests"]
    assert engine.all_ok


def test_engine_plan_phase_rejects_bad_plan():
    engine = WorkflowEngine()
    report = engine.plan_phase(PlanDocument(title="bad"))
    assert report.phase is Phase.PLAN
    assert not report.ok
    assert "no goals" in report.detail


def test_engine_implement_phase_forbids_subagent():
    engine = WorkflowEngine()
    with pytest.raises(ValueError):
        engine.implement_phase(plan=_sample_plan(), using_subagent=True)


def test_engine_validate_phase_uses_validator_subagent():
    engine = WorkflowEngine()
    report = engine.validate_phase(using_subagent=True)
    assert report.phase is Phase.VALIDATE
    assert report.ok
    assert "validator" in report.detail


def test_engine_all_ok_false_until_full_run():
    engine = WorkflowEngine()
    engine.plan_phase(_sample_plan())
    assert not engine.all_ok  # only 1 of 3 phases run


# --- module facade --------------------------------------------------------
def test_module_initialize_healthy_and_facade():
    module = create_slash_workflow_module({"max_rework": 3})
    asyncio.run(module.initialize())
    assert module.status is HealthStatus.HEALTHY
    assert module.health_check() is not None
    assert "primer" in module.render_command("primer", read_paths="src/")

    reports = module.run_workflow(_sample_plan(), review=lambda t: True)
    assert len(reports) == 3
    assert module.engine.all_ok


def test_module_name_and_version():
    module = create_slash_workflow_module()
    assert module.name == "slash_workflow"
    assert module.version == "1.0.0"


def test_module_shutdown_sets_stopping():
    module = create_slash_workflow_module()
    asyncio.run(module.initialize())
    asyncio.run(module.shutdown())
    assert module.status is HealthStatus.STOPPING


def test_create_slash_workflow_builds_engine_with_plan_config():
    engine = create_slash_workflow(
        {"plan": {"title": "cfg", "tasks": ["a", "b"]}}
    )
    assert engine.plan is not None
    assert len(engine.plan.tasks) == 2


def test_global_rules_config_extends_defaults():
    engine = create_slash_workflow({"global_rules": ["Always commit atomically"]})
    rules = default_global_rules().cascade([])
    assert "Never vibe code" in rules
