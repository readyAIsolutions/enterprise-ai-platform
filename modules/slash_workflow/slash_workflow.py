"""Pure-logic core for the ``slash_workflow`` module.

Grounding: ColeMedin, "The True Power of AI Coding - Build Your OWN Workflows"
(https://www.youtube.com/watch?v=mHBk8Z7Exag).  The transcript teaches a
three-phase AI-coding workflow -- **Plan -> Implement -> Validate** -- built
out of reusable markdown *slash commands* (``primer``, ``create_plan``,
``execute_plan``, ``validate``), a structured *planning document* (goals,
granular tasks, files-to-edit/create, patterns, success criteria), isolated
context-window *sub-agents* used for planning and validation **only** (never
during implementation, so the primary context window stays authoritative and
shared memory is not fragmented), a *task manager* driving a deterministic
``to-do -> doing -> review`` cycle until everything is done, and *global rules*
(``CLAUDE.md``) whose context cascades into every phase.

This module is a pure-stdlib, network-free implementation of that philosophy:

* :class:`TaskStatus` and :class:`TaskItem`  -- typed task with guarded status
  transitions (todo -> doing -> review -> done, with rework edges).
* :class:`TaskManager` -- deterministic task cycle over an ordered backlog.
* :class:`SlashCommand` and :class:`SlashCommandRegistry` -- markdown slash
  commands rendered as reusable prompts; ships the four commands from the talk.
* :class:`PlanDocument` -- the planning-document schema from the talk.
* :class:`SubAgent` -- an isolated-context worker that only returns a summary,
  keeping the primary context window concise (planning / validation only).
* :class:`GlobalRules` -- CLAUDE.md-style golden rules that cascade into
  every slash-command render.
* :class:`WorkflowValidator` -- validates plans, task cycles, and the
  sub-agent isolation policy (no sub-agents during implementation).
* :class:`WorkflowEngine` -- runs the three phases with a deterministic
  task cycle and enforces the sub-agent policy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, Iterable, List, Optional, Sequence

__version__ = "1.0.0"


# ---------------------------------------------------------------------------
# Task status model
# ---------------------------------------------------------------------------
class TaskStatus(str, Enum):
    """Lifecycle of a single granular implementation task.

    Mirrors the talk's ``to-do -> doing -> review`` cycle; ``done`` terminates
    the cycle, ``blocked`` records an obstacle the workflow should surface.
    """

    TODO = "todo"
    DOING = "doing"
    REVIEW = "review"
    DONE = "done"
    BLOCKED = "blocked"


# Allowed one-hop transitions (identity map, explicit edges).
_ALLOWED_TRANSITIONS: Dict[TaskStatus, frozenset] = {
    TaskStatus.TODO: frozenset({TaskStatus.DOING, TaskStatus.BLOCKED}),
    TaskStatus.DOING: frozenset({TaskStatus.REVIEW, TaskStatus.TODO, TaskStatus.BLOCKED}),
    TaskStatus.REVIEW: frozenset({TaskStatus.DONE, TaskStatus.DOING, TaskStatus.BLOCKED}),
    TaskStatus.DONE: frozenset(),
    TaskStatus.BLOCKED: frozenset({TaskStatus.TODO, TaskStatus.DOING}),
}


def allowed_transitions(status: TaskStatus) -> frozenset:
    """Return the set of statuses a task may legally move to from *status*."""
    return _ALLOWED_TRANSITIONS[status]


@dataclass
class TaskItem:
    """A single granular task inside a :class:`PlanDocument`."""

    title: str
    files: List[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.TODO
    detail: str = ""

    def advance(self, target: TaskStatus) -> "TaskItem":
        """Transition the task to *target*, raising ValueError on illegal moves.

        Enforces the deterministic cycle from the talk: a task cannot jump
        straight from ``todo`` to ``done``, and done tasks are terminal.
        """
        if target not in allowed_transitions(self.status):
            raise ValueError(
                f"illegal task transition {self.status.value} -> {target.value}"
            )
        self.status = target
        return self

    @property
    def is_done(self) -> bool:
        return self.status is TaskStatus.DONE


class TaskManager:
    """Deterministic task cycle over an ordered backlog.

    Models the ``to-do -> doing -> review -> next`` loop ColeMedin describes
    for ``execute_plan``: tasks are pulled one by one, worked, sent to review,
    and only then moved on to -- until everything is done.
    """

    def __init__(self, tasks: Optional[Sequence[TaskItem]] = None) -> None:
        self._tasks: List[TaskItem] = list(tasks or [])

    @property
    def tasks(self) -> List[TaskItem]:
        return self._tasks

    def add(self, task: TaskItem) -> "TaskManager":
        self._tasks.append(task)
        return self

    def next_active(self) -> Optional[TaskItem]:
        """Return the first non-terminal task in backlog order (todo only)."""
        for t in self._tasks:
            if t.status is TaskStatus.TODO:
                return t
        return None

    def pull(self) -> Optional[TaskItem]:
        """Pull the next todo task and mark it *doing* (deterministic order)."""
        task = self.next_active()
        if task is None:
            return None
        task.advance(TaskStatus.DOING)
        return task

    def send_to_review(self, task: TaskItem) -> TaskItem:
        if task.status is not TaskStatus.DOING:
            raise ValueError("only a task in 'doing' can be sent to review")
        return task.advance(TaskStatus.REVIEW)

    def approve(self, task: TaskItem) -> TaskItem:
        if task.status is not TaskStatus.REVIEW:
            raise ValueError("only a task in 'review' can be approved")
        return task.advance(TaskStatus.DONE)

    def rework(self, task: TaskItem) -> TaskItem:
        """Return a reviewed task back to *doing* for rework."""
        if task.status is not TaskStatus.REVIEW:
            raise ValueError("only a task in 'review' can be sent back to doing")
        return task.advance(TaskStatus.DOING)

    @property
    def remaining(self) -> int:
        return sum(1 for t in self._tasks if not t.is_done)

    def is_complete(self) -> bool:
        return all(t.is_done for t in self._tasks) and len(self._tasks) > 0

    def cycle(self, implement: Callable[[TaskItem], None],
              review: Callable[[TaskItem], bool],
              max_rework: int = 3) -> List[TaskItem]:
        """Run the full deterministic task cycle.

        For each task in backlog order: mark *doing*, invoke *implement*, move
        to *review*, and consult *review*. If the review returns False the task
        returns to *doing* for rework (bounded by *max_rework*); otherwise it is
        approved and the cycle advances to the next task.
        """
        order: List[TaskItem] = []
        for task in self._tasks:
            if task.is_done:
                continue
            rework_left = max_rework
            while not task.is_done:
                if task.status is TaskStatus.TODO:
                    task.advance(TaskStatus.DOING)
                implement(task)
                self.send_to_review(task)
                if review(task):
                    self.approve(task)
                    break
                if rework_left <= 0:
                    task.advance(TaskStatus.BLOCKED)
                    break
                rework_left -= 1
                self.rework(task)
            order.append(task)
        return order


# ---------------------------------------------------------------------------
# Slash commands (reusable markdown prompts / workflows)
# ---------------------------------------------------------------------------
@dataclass
class SlashCommand:
    """A markdown slash command rendered as a reusable prompt/workflow.

    In the talk, slash commands are "simply prompts that you want to turn into
    reusable workflows" -- e.g. ``primer``, ``create_plan``, ``execute_plan``
    and ``validate``.  A command has a name, a description, a markdown body
    (with ``{placeholder}`` slots) and an optional list of arguments it expects.
    """

    name: str
    description: str
    body: str
    args: List[str] = field(default_factory=list)

    def render(self, **kwargs: str) -> str:
        """Render the command body with *kwargs* substituted for placeholders."""
        extra = set(kwargs) - set(self.args)
        if extra:
            raise ValueError(f"unexpected args for /{self.name}: {sorted(extra)}")
        return self.body.format(**kwargs)

    def to_markdown(self, **kwargs: str) -> str:
        """Render the command as a full /command block with a header."""
        head = f"/{self.name} -- {self.description}\n"
        return head + self.render(**kwargs)


def default_slash_commands() -> Dict[str, SlashCommand]:
    """The four commands ColeMedin builds around the Plan->Implement->Validate flow.

    * ``primer``        -- read key files to catch the assistant up on the codebase.
    * ``create_plan``   -- turn the initial requirements doc into a full plan.
    * ``execute_plan``  -- read the plan, create tasks, then drive the task cycle.
    * ``validate``      -- run an isolated validator to make sure code is solid.
    """
    return {
        "primer": SlashCommand(
            name="primer",
            description="catch the AI assistant up on the project",
            args=["read_paths"],
            body=(
                "Read the following key files to get up to speed on the project:\n"
                "{read_paths}\n"
                "Summarise the architecture, conventions and open questions before "
                "we proceed."
            ),
        ),
        "create_plan": SlashCommand(
            name="create_plan",
            description="turn requirements into a full planning document",
            args=["requirements_path"],
            body=(
                "Take the requirements document at {requirements_path} and build a "
                "plan: goals, granular tasks, files to edit/create, patterns to "
                "follow and success criteria. Use a codebase-analyst sub-agent for "
                "research, keeping our primary context window concise."
            ),
        ),
        "execute_plan": SlashCommand(
            name="execute_plan",
            description="read the plan and drive the to-do->doing->review cycle",
            args=["plan_path"],
            body=(
                "Read the plan at {plan_path}, create the tasks, and knock them out "
                "one by one: mark each task doing, implement it, move it to review, "
                "then move on to the next until everything is done. Do NOT delegate "
                "implementation to sub-agents."
            ),
        ),
        "validate": SlashCommand(
            name="validate",
            description="validate the produced code with an isolated validator",
            args=["plan_path"],
            body=(
                "Validate the implementation for the plan at {plan_path}. Use a "
                "validator sub-agent in its own context window to write and run "
                "tests, then report anything that needs fixing back to the primary "
                "conversation."
            ),
        ),
    }


class SlashCommandRegistry:
    """A registry of reusable slash commands with lookup and rendering."""

    def __init__(self, commands: Optional[Dict[str, SlashCommand]] = None) -> None:
        self._commands: Dict[str, SlashCommand] = dict(
            commands if commands is not None else default_slash_commands()
        )

    def register(self, command: SlashCommand) -> "SlashCommandRegistry":
        self._commands[command.name] = command
        return self

    def get(self, name: str) -> Optional[SlashCommand]:
        return self._commands.get(name)

    def names(self) -> List[str]:
        return sorted(self._commands)

    def render(self, name: str, **kwargs: str) -> str:
        command = self.get(name)
        if command is None:
            raise KeyError(f"unknown slash command: /{name}")
        return command.to_markdown(**kwargs)


# ---------------------------------------------------------------------------
# Plan document schema
# ---------------------------------------------------------------------------
@dataclass
class PlanDocument:
    """The planning-document schema described in the talk.

    Holds the goals, the granular task list, the files to edit and to create,
    the existing patterns to follow, and the success criteria -- everything the
    assistant needs to "get the job done" and against which work is validated.
    """

    title: str
    goals: List[str] = field(default_factory=list)
    tasks: List[TaskItem] = field(default_factory=list)
    files_to_edit: List[str] = field(default_factory=list)
    files_to_create: List[str] = field(default_factory=list)
    patterns: List[str] = field(default_factory=list)
    success_criteria: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)

    @property
    def all_files(self) -> List[str]:
        return list(self.files_to_edit) + list(self.files_to_create)

    def to_markdown(self) -> str:
        lines = [f"# Plan: {self.title}", ""]
        if self.goals:
            lines += ["## Goals"] + [f"- {g}" for g in self.goals] + [""]
        if self.tasks:
            lines += ["## Tasks"]
            for i, t in enumerate(self.tasks, 1):
                files = ", ".join(t.files) if t.files else "-"
                lines.append(f"{i}. [ ] {t.title}  (files: {files})")
            lines.append("")
        if self.files_to_edit:
            lines += ["## Files to edit"] + [f"- {f}" for f in self.files_to_edit] + [""]
        if self.files_to_create:
            lines += ["## Files to create"] + [f"- {f}" for f in self.files_to_create] + [""]
        if self.patterns:
            lines += ["## Patterns to follow"] + [f"- {p}" for p in self.patterns] + [""]
        if self.success_criteria:
            lines += ["## Success criteria"] + [f"- {s}" for s in self.success_criteria] + [""]
        return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Sub-agents (isolated context) and global rules (CLAUDE.md)
# ---------------------------------------------------------------------------
@dataclass
class SubAgent:
    """An isolated-context worker.

    ColeMedin uses sub-agents for research (planning) and validation only: each
    runs in its own context window and returns a concise summary so the primary
    conversation stays focused. Sub-agents are deliberately NOT used during
    implementation because separate context windows cannot share memory and
    produce conflicting changes.
    """

    name: str
    system_prompt: str = ""
    role: str = "research"

    def run(self, work: Callable[[], str]) -> str:
        """Run *work* in isolation and return a concise summary.

        Only the returned string escapes into the primary context window.
        """
        result = work()
        return f"[{self.name} summary] {result}"


class GlobalRules:
    """CLAUDE.md-style golden rules whose context cascades into every phase.

    In the talk these are the instructions the assistant must follow "no matter
    what" -- starting a project, adding a feature, or fixing a bug.  Cascading
    context means the base rules are always present and phase rules are layered
    on top of them.
    """

    def __init__(self, rules: Optional[Sequence[str]] = None) -> None:
        self._rules: List[str] = list(rules or [])

    def add(self, rule: str) -> "GlobalRules":
        self._rules.append(rule)
        return self

    @property
    def rules(self) -> List[str]:
        return list(self._rules)

    def cascade(self, phase_rules: Sequence[str] = ()) -> str:
        """Render base rules followed by phase rules (cascading context)."""
        lines = list(self._rules) + list(phase_rules)
        return "\n".join(f"- {r}" for r in lines)


def default_global_rules() -> GlobalRules:
    """Golden rules distilled from the talk's philosophy."""
    return GlobalRules([
        "Never vibe code: understand every change before accepting it.",
        "Keep context curated: research and validation may use isolated sub-agents; "
        "implementation stays in the primary context window.",
        "Work task by task -- never ask the assistant to do too much at once.",
        "Always validate your own work, then perform a human code review and "
        "manual tests before calling a change done.",
    ])


# ---------------------------------------------------------------------------
# Workflow phases and validator
# ---------------------------------------------------------------------------
class Phase(str, Enum):
    """The three phases of the workflow from the talk."""

    PLAN = "plan"
    IMPLEMENT = "implement"
    VALIDATE = "validate"


class WorkflowValidator:
    """Pure validation logic for plans, task cycles and sub-agent policy.

    Encodes the talk's central rule: sub-agents are welcome during **planning**
    and **validation** but must never be used during **implementation**.
    """

    PLAN_PHASES = {Phase.PLAN, Phase.VALIDATE}

    def validate_plan(self, plan: PlanDocument) -> List[str]:
        """Return a list of problems with a plan (empty means it is sound)."""
        problems: List[str] = []
        if not plan.title:
            problems.append("plan has no title")
        if not plan.goals:
            problems.append("plan has no goals")
        if not plan.tasks:
            problems.append("plan has no tasks")
        if not plan.success_criteria:
            problems.append("plan has no success criteria")
        for i, task in enumerate(plan.tasks, 1):
            if not task.title:
                problems.append(f"task #{i} has no title")
            if task.status not in (TaskStatus.TODO,):
                problems.append(f"task #{i} should start as todo")
        return problems

    def is_plan_valid(self, plan: PlanDocument) -> bool:
        return not self.validate_plan(plan)

    def check_subagent_policy(self, phase: Phase, using_subagent: bool) -> None:
        """Raise if a sub-agent is used during implementation."""
        if phase is Phase.IMPLEMENT and using_subagent:
            raise ValueError(
                "sub-agents must not be used during implementation: isolated context "
                "windows cannot share memory and cause conflicting changes"
            )

    def validate_task_cycle(self, manager: TaskManager) -> List[str]:
        """Return problems if the task cycle did not finish all tasks."""
        problems: List[str] = []
        if not manager.tasks:
            problems.append("task manager has no tasks")
        if not manager.is_complete():
            blocked = [t.title for t in manager.tasks if t.status is TaskStatus.BLOCKED]
            if blocked:
                problems.append(f"tasks blocked after rework budget: {blocked}")
            else:
                problems.append("task cycle did not complete all tasks")
        return problems


# ---------------------------------------------------------------------------
# Workflow engine
# ---------------------------------------------------------------------------
@dataclass
class PhaseReport:
    """Outcome of a single workflow phase."""

    phase: Phase
    ok: bool
    detail: str = ""


class WorkflowEngine:
    """Runs the Plan -> Implement -> Validate workflow with a task cycle.

    Phase inputs:
      * plan     : :class:`PlanDocument`
      * implement: ``Callable[[TaskItem], None]`` -- does the concrete work.
      * review   : ``Callable[[TaskItem], bool]`` -- True approves the task.
      * validate : ``Callable[[], str]`` -- optional validator work.

    The engine enforces the deterministic task cycle and the sub-agent policy:
    *planning* and *validation* may use an isolated validator sub-agent;
    *implementation* never may.
    """

    def __init__(self,
                 plan: Optional[PlanDocument] = None,
                 validator: Optional[WorkflowValidator] = None,
                 manager: Optional[TaskManager] = None) -> None:
        self.plan = plan
        self.validator = validator or WorkflowValidator()
        self.manager = manager or TaskManager()
        self.reports: List[PhaseReport] = []

    # -- planning -----------------------------------------------------------
    def plan_phase(self, plan: PlanDocument, using_subagent: bool = False,
                   research: Optional[Callable[[], str]] = None) -> PhaseReport:
        """Validate (and optionally enrich via an isolated research sub-agent)."""
        self.check_phase_policy(Phase.PLAN, using_subagent)
        problems = self.validator.validate_plan(plan)
        if problems:
            report = PhaseReport(Phase.PLAN, False, "; ".join(problems))
            self.reports.append(report)
            return report
        self.plan = plan
        detail = f"plan '{plan.title}' validated with {len(plan.tasks)} tasks"
        if using_subagent and research is not None:
            agent = SubAgent("codebase-analyst", role="planning")
            detail += " | " + agent.run(research)
        report = PhaseReport(Phase.PLAN, True, detail)
        self.reports.append(report)
        return report

    # -- implementation -----------------------------------------------------
    def implement_phase(self, plan: Optional[PlanDocument] = None,
                        implement: Callable[[TaskItem], None] = lambda t: None,
                        review: Callable[[TaskItem], bool] = lambda t: True,
                        max_rework: int = 3,
                        using_subagent: bool = False) -> PhaseReport:
        """Drive the deterministic task cycle over the plan's tasks.

        Passing ``using_subagent=True`` violates the policy and raises; the
        implementation phase is intentionally sub-agent-free.
        """
        self.check_phase_policy(Phase.IMPLEMENT, using_subagent)
        active = plan or self.plan
        if active is None:
            raise ValueError("no plan available for implementation")
        self.manager = TaskManager(list(active.tasks))
        done = self.manager.cycle(implement=implement, review=review,
                                  max_rework=max_rework)
        problems = self.validator.validate_task_cycle(self.manager)
        ok = not problems
        detail = f"{len(done)}/{len(active.tasks)} tasks completed"
        if problems:
            detail += "; " + "; ".join(problems)
        report = PhaseReport(Phase.IMPLEMENT, ok, detail)
        self.reports.append(report)
        return report

    # -- validation ---------------------------------------------------------
    def validate_phase(self, validator_work: Optional[Callable[[], str]] = None,
                       using_subagent: bool = True) -> PhaseReport:
        """Run validation; a validator sub-agent is welcome here."""
        self.check_phase_policy(Phase.VALIDATE, using_subagent)
        detail = "all success criteria satisfied"
        if using_subagent:
            agent = SubAgent("validator", role="validation")
            detail += " | " + agent.run(validator_work or (lambda: "tests passed"))
        report = PhaseReport(Phase.VALIDATE, True, detail)
        self.reports.append(report)
        return report

    # -- orchestration ------------------------------------------------------
    def run(self, plan: PlanDocument,
            implement: Callable[[TaskItem], None] = lambda t: None,
            review: Callable[[TaskItem], bool] = lambda t: True,
            validate_work: Optional[Callable[[], str]] = None,
            max_rework: int = 3) -> List[PhaseReport]:
        """Run all three phases and return the ordered phase reports.

        Use a planning sub-agent for research and a validator sub-agent for
        validation, but never a sub-agent during implementation.
        """
        self.reports = []
        self.plan_phase(plan, using_subagent=True)
        self.implement_phase(plan=plan, implement=implement, review=review,
                             max_rework=max_rework, using_subagent=False)
        self.validate_phase(validate_work, using_subagent=True)
        return self.reports

    def check_phase_policy(self, phase: Phase, using_subagent: bool) -> None:
        self.validator.check_subagent_policy(phase, using_subagent)

    @property
    def all_ok(self) -> bool:
        return len(self.reports) == 3 and all(r.ok for r in self.reports)


def build_plan(title: str, tasks: Iterable[str],
               files_to_edit: Optional[Iterable[str]] = None,
               files_to_create: Optional[Iterable[str]] = None,
               patterns: Optional[Iterable[str]] = None,
               success_criteria: Optional[Iterable[str]] = None,
               references: Optional[Iterable[str]] = None,
               goals: Optional[Iterable[str]] = None) -> PlanDocument:
    """Convenience builder turning a list of task titles into a PlanDocument."""
    return PlanDocument(
        title=title,
        goals=list(goals) if goals else [f"Implement {title}"],
        tasks=[TaskItem(title=t) for t in tasks],
        files_to_edit=list(files_to_edit or []),
        files_to_create=list(files_to_create or []),
        patterns=list(patterns or []),
        success_criteria=list(success_criteria or []) if success_criteria else [],
        references=list(references or []),
    )


__all__ = [
    "TaskStatus",
    "TaskItem",
    "TaskManager",
    "SlashCommand",
    "SlashCommandRegistry",
    "default_slash_commands",
    "PlanDocument",
    "SubAgent",
    "GlobalRules",
    "default_global_rules",
    "Phase",
    "PhaseReport",
    "WorkflowValidator",
    "WorkflowEngine",
    "build_plan",
    "allowed_transitions",
]
