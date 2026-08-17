"""Tests for the custom_agent_workflows module.

Grounded in the Cole Medin transcript *"The True Power of AI Coding — Build
Your OWN Workflows (Full Guide)"* (https://www.youtube.com/watch?v=mHBk8Z7Exag).
"""

from __future__ import annotations

import pytest

from enterprise.modules.custom_agent_workflows import (
    AGENT_CODEBASE_ANALYST,
    AGENT_VALIDATOR,
    CODEBASE_ANALYST,
    PHASE_IMPLEMENTATION,
    PHASE_PLANNING,
    PHASE_VALIDATION,
    SLASH_CREATE_PLAN,
    SLASH_EXECUTE_PLAN,
    SLASH_PRIMER,
    TASK_DONE,
    TASK_DOING,
    TASK_REVIEW,
    TASK_TODO,
    VALIDATOR,
    CustomAgentWorkflowsModule,
    CodingWorkflow,
    Task,
    TaskManager,
    WorkflowPlan,
    build_initial_md,
    build_plan,
    create_custom_agent_workflows_module,
    create_plan_slash_command,
    execute_plan_slash_command,
    primer_slash_command,
    research_codebase,
    validate_code,
    validate_plan,
)


# -- planning phase --------------------------------------------------------

def test_initial_md_new_project_is_prd():
    md = build_initial_md("Obsidian agent integration", references=["example obsidian plugin"])
    assert md.startswith("# Obsidian agent integration")
    assert "PRD" in md
    assert "MVP" in md
    assert "obsidian plugin" in md
    assert "Integration Points" not in md


def test_initial_md_existing_project_lists_integration_points():
    md = build_initial_md(
        "OpenAI API compatibility",
        references=["openai docs"],
        integration_points=["src/api/routes.py", "src/client.py"],
        is_new_project=False,
    )
    assert "## Integration Points" in md
    assert "src/api/routes.py" in md
    assert "src/client.py" in md


def test_build_plan_creates_granular_tasks():
    initial_md = build_initial_md("OpenAI API compatibility", references=["openai docs"])
    plan = build_plan(initial_md)
    assert plan.title == "OpenAI API compatibility"
    assert plan.tasks, "plan must contain granular tasks"
    for i, task in enumerate(plan.tasks, 1):
        assert task.id == f"task-{i}"
        assert task.description
        assert task.status == TASK_TODO
    assert plan.success_criteria
    assert plan.references == ["openai docs"]
    assert plan.desired_structure


def test_build_plan_custom_tasks():
    initial_md = build_initial_md("Feature X")
    plan = build_plan(initial_md, default_tasks=["task A", "task B"])
    assert [t.description for t in plan.tasks] == ["task A", "task B"]


# -- task management -------------------------------------------------------

def test_task_manager_state_machine():
    tm = TaskManager([Task(id="task-1", description="do the thing")])
    tm.mark("task-1", TASK_DOING)
    assert tm.tasks[0].status == TASK_DOING
    tm.mark("task-1", TASK_REVIEW)
    tm.mark("task-1", TASK_DONE)
    assert tm.tasks[0].status == TASK_DONE


def test_task_manager_invalid_transition():
    tm = TaskManager([Task(id="task-1", description="x")])
    with pytest.raises(ValueError):
        tm.mark("task-1", TASK_DONE)  # cannot jump straight to done


def test_task_manager_unknown_id():
    tm = TaskManager([Task(id="task-1", description="x")])
    with pytest.raises(KeyError):
        tm.mark("nope", TASK_DOING)


def test_task_manager_next_and_completed():
    tm = TaskManager([Task(id="a", description="a"), Task(id="b", description="b")])
    assert tm.next().id == "a"
    assert tm.remaining() == 2
    assert not tm.completed
    tm.mark("a", TASK_DOING)
    tm.mark("a", TASK_REVIEW)
    tm.mark("a", TASK_DONE)
    assert tm.next().id == "b"
    tm.mark("b", TASK_DOING)
    tm.mark("b", TASK_REVIEW)
    tm.mark("b", TASK_DONE)
    assert tm.next() is None
    assert tm.completed


# -- validation ------------------------------------------------------------

def test_validate_plan_ok():
    plan = WorkflowPlan(title="T", summary="s",
                        tasks=[Task(id="t1", description="d")],
                        success_criteria=["c"])
    result = validate_plan(plan)
    assert result["valid"] is True
    assert result["issues"] == []


def test_validate_plan_empty_tasks_fails():
    plan = WorkflowPlan(title="T", summary="s", tasks=[], success_criteria=["c"])
    result = validate_plan(plan)
    assert result["valid"] is False
    assert any("no granular tasks" in i for i in result["issues"])


def test_validate_code_passes_with_content(tmp_path):
    (tmp_path / "app.py").write_text("print('hi')\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "helper.py").write_text("x = 1\n")
    result = validate_code(str(tmp_path))
    assert result["agent"] == AGENT_VALIDATOR
    assert result["context"] == "isolated"
    assert result["passed"] is True
    assert result["checked"] == 2


def test_validate_code_flags_empty_file(tmp_path):
    (tmp_path / "app.py").write_text("")
    result = validate_code(str(tmp_path))
    assert result["passed"] is False
    assert result["issues"] == ["app.py: empty file"]


def test_validate_code_missing_dir_raises(tmp_path):
    with pytest.raises(ValueError):
        validate_code(str(tmp_path / "does-not-exist"))


# -- subagents -------------------------------------------------------------

def test_research_codebase_isolated_summary(tmp_path):
    (tmp_path / "routes.py").write_text("x = 1")
    (tmp_path / "client.py").write_text("y = 2")
    result = research_codebase(str(tmp_path))
    assert result["agent"] == AGENT_CODEBASE_ANALYST
    assert result["context"] == "isolated"
    assert result["file_count"] == 2
    assert result["files"] == ["client.py", "routes.py"]
    assert "Codebase analyst" in result["summary"]


def test_codebase_analyst_identity():
    assert CODEBASE_ANALYST.name == AGENT_CODEBASE_ANALYST
    assert VALIDATOR.name == AGENT_VALIDATOR
    assert CODEBASE_ANALYST.role == "Research"
    assert VALIDATOR.role == "Validation"


# -- slash commands --------------------------------------------------------

def test_primer_command_lists_files_to_read():
    result = primer_slash_command(key_files=["README.md", "AGENTS.md"])
    assert result["command"] == SLASH_PRIMER
    assert result["files_to_read"] == ["AGENTS.md", "README.md"]


def test_primer_scans_project_root(tmp_path):
    (tmp_path / "README.md").write_text("# readme")
    (tmp_path / "code.py").write_text("x = 1")
    result = primer_slash_command(project_root=str(tmp_path), key_files=["ARCHITECTURE.md"])
    assert "README.md" in result["files_to_read"]
    assert "ARCHITECTURE.md" in result["files_to_read"]
    assert "code.py" not in result["files_to_read"]


def test_create_plan_command_phases():
    result = create_plan_slash_command("my requirements")
    assert result["command"] == SLASH_CREATE_PLAN
    assert result["requirements_doc"] == "my requirements"
    assert "read and understand the requirements" in result["phases"]
    assert "codebase analysis subagent research" in result["phases"]


def test_execute_plan_command_counts_tasks():
    plan = WorkflowPlan(title="T", summary="s",
                        tasks=[Task(id="t1", description="a"),
                               Task(id="t2", description="b")])
    result = execute_plan_slash_command(plan)
    assert result["command"] == SLASH_EXECUTE_PLAN
    assert result["task_count"] == 2
    assert "task loop" in result["phases"]


# -- orchestrator ----------------------------------------------------------

def test_workflow_full_run_plan_implement_validate():
    wf = CodingWorkflow(name="obsidian-integration")
    report = wf.run(
        "Connect Obsidian vault to the custom agent",
        references=["example obsidian plugin"],
        integration_points=["src/agent.py", "src/api.py"],
        is_new_project=False,
    )
    assert report["phases"] == [PHASE_PLANNING, PHASE_IMPLEMENTATION, PHASE_VALIDATION]
    assert report["tasks_completed"] is True
    assert report["plan_valid"] is True
    assert report["plan"].title == "Connect Obsidian vault to the custom agent"


def test_workflow_execute_before_plan_raises():
    wf = CodingWorkflow()
    with pytest.raises(RuntimeError):
        wf.execute()


# -- module lifecycle ------------------------------------------------------

async def test_module_initialize_healthy():
    m = create_custom_agent_workflows_module()
    await m.initialize()
    assert (await m.health_check()).value == "healthy"
    assert m.stats()["workflow_initialized"] is True
    assert m.stats()["max_tasks"] == 12


async def test_module_facade_plan_and_validate():
    m = create_custom_agent_workflows_module()
    await m.initialize()
    plan = m.plan("Feature X", references=["ref"], integration_points=["a.py"],
                  is_new_project=False)
    assert plan["title"] == "Feature X"
    assert len(plan["tasks"]) >= 1
    assert m.validate_plan(plan)["valid"] is True
    assert m.build_initial_md("Feature X").startswith("# Feature X")


async def test_module_execute_tasks():
    m = create_custom_agent_workflows_module()
    await m.initialize()
    plan = m.plan("Feature X")
    assert m.execute(plan) is True


async def test_module_subagent_and_validate(tmp_path):
    m = create_custom_agent_workflows_module()
    await m.initialize()
    (tmp_path / "main.py").write_text("x = 1")
    research = m.research_codebase(str(tmp_path))
    assert research["file_count"] == 1
    check = m.validate_code(str(tmp_path))
    assert check["passed"] is True


async def test_module_health_check_and_shutdown():
    m = create_custom_agent_workflows_module()
    await m.initialize()
    assert (await m.health_check()).value == "healthy"
    await m.shutdown()
    assert (await m.health_check()).value == "stopping"


async def test_module_publishes_only_with_event_bus():
    m = create_custom_agent_workflows_module()
    await m.initialize()
    # No event bus set -> publishing must be a no-op (no exception).
    m.plan("Feature X")

    class FakeBus:
        def __init__(self):
            self.published = []

        def publish(self, event):
            self.published.append(event)

    bus = FakeBus()
    m.set_event_bus(bus)
    m.plan("Feature Y")
    assert len(bus.published) == 1
    assert bus.published[0].topic == "custom_agent_workflows.plan_created"
    assert bus.published[0].source == "custom_agent_workflows"
    assert bus.published[0].payload["title"] == "Feature Y"
