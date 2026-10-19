"""composable_workflow_engine.core — compose-your-own context-engineering
workflow engine.

Grounded ENTIRELY in ColeMedin's "The True Power of AI Coding - Build Your
OWN Workflows (Full Guide)" (https://www.youtube.com/watch?v=mHBk8Z7Exag).

Core thesis of the transcript: AI coding is not about one-off prompts — it is
about building SYSTEMS / WORKFLOWS that evolve to fit your needs. Rather than
adopting an existing framework wholesale (PRP = Product Requirement Prompt,
BMAD, the GitHub spec-kit), the author argues you should understand the
PHILOSOPHY and fundamental PHASES behind them so you can COMPOSE YOUR OWN.

The primary mental model the author teaches is a three-step process:
    PLANNING -> IMPLEMENTATION -> VALIDATION

He expands PLANNING into sub-steps:
    * vibe planning  — free-form exploration of ideas/architecture/tech-stack
                       with the assistant as a research companion.
    * initial requirements (the "initial MD" / PRD) — a high-level feature
                       request you could hand another human.
    * create plan    — turn the requirements into a full context-engineered
                       plan: read/understand requirements, research (RAG + web
                       + a codebase-analyst sub-agent), then produce granular
                       tasks, desired codebase structure, documentation/example
                       references, and success criteria. (This is exactly what
                       the PRP framework produces.)

IMPLEMENTATION executes the plan task-by-task via a task-management cycle
(TODO -> DOING -> REVIEW -> DONE) one task at a time to avoid hallucination;
crucially the author does NOT use sub-agents here (shared primary context).

VALIDATION has the assistant validate its own work (generate/run tests via a
validator sub-agent in an isolated context) plus a human code review, and can
reopen tasks.

Context-engineering components named in the diagram: RAG (external docs),
MEMORY (conversation history), TASK MANAGEMENT, PROMPT ENGINEERING. Reusable
building blocks named: slash commands, sub-agents, global rules.

This module turns those PHASES into composable, pure, deterministic data
structures. No LLM calls, no network — each phase is simulated as a structured
record/transform so the workflow is reproducible and testable.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class WorkflowError(Exception):
    """Raised for invalid templates / composition / execution errors."""


# ─────────────────────────────────────────────────────────────────────────────
# Vocabulary grounded in the transcript
# ─────────────────────────────────────────────────────────────────────────────

# The frameworks the author explicitly names.
KNOWN_FRAMEWORKS: List[str] = ["prp", "bmad", "spec-kit", "custom"]

# Context-engineering components from the Excalidraw diagram.
CONTEXT_COMPONENTS: List[str] = [
    "rag",
    "memory",
    "task_management",
    "prompt_engineering",
]

# Reusable building blocks the author uses to automate phases.
BUILDING_BLOCKS: List[str] = ["slash_command", "sub_agent", "global_rules"]


@dataclass
class WorkflowPhase:
    """A single phase in a workflow template.

    Mirrors the author's notion that a workflow is an ordered set of phases,
    each with a role (who/what runs it), the inputs it consumes, the outputs
    (artifacts) it produces, and the instructions that drive it.
    """

    name: str
    role: str
    instructions: str
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    # Whether this phase uses an isolated-context sub-agent. Per the transcript
    # planning & validation use sub-agents; implementation purposely does NOT.
    uses_sub_agent: bool = False
    # Context-engineering components leaned on by this phase.
    context_components: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise WorkflowError("WorkflowPhase.name must be a non-empty string")
        if not self.role or not self.role.strip():
            raise WorkflowError(
                f"WorkflowPhase {self.name!r}: role must be non-empty"
            )
        for comp in self.context_components:
            if comp not in CONTEXT_COMPONENTS:
                raise WorkflowError(
                    f"Unknown context component {comp!r} in phase "
                    f"{self.name!r}; known: {CONTEXT_COMPONENTS}"
                )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "instructions": self.instructions,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "uses_sub_agent": self.uses_sub_agent,
            "context_components": list(self.context_components),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowPhase":
        if not isinstance(data, dict):
            raise WorkflowError("phase data must be a dict")
        try:
            return cls(
                name=data["name"],
                role=data["role"],
                instructions=data.get("instructions", ""),
                inputs=list(data.get("inputs", [])),
                outputs=list(data.get("outputs", [])),
                uses_sub_agent=bool(data.get("uses_sub_agent", False)),
                context_components=list(data.get("context_components", [])),
            )
        except KeyError as exc:
            raise WorkflowError(f"phase dict missing key: {exc}") from exc


@dataclass
class WorkflowTemplate:
    """An ordered list of phases composing a workflow.

    A template may mirror a named framework (prp / bmad / spec-kit) or be a
    fully custom composition the user builds from fundamental phases.
    """

    name: str
    phases: List[WorkflowPhase] = field(default_factory=list)
    framework: str = "custom"
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise WorkflowError("WorkflowTemplate.name must be non-empty")
        if self.framework not in KNOWN_FRAMEWORKS:
            raise WorkflowError(
                f"Unknown framework {self.framework!r}; known: {KNOWN_FRAMEWORKS}"
            )

    def phase_names(self) -> List[str]:
        return [p.name for p in self.phases]

    def get_phase(self, name: str) -> Optional[WorkflowPhase]:
        for p in self.phases:
            if p.name == name:
                return p
        return None

    def add_phase(self, phase: WorkflowPhase) -> "WorkflowTemplate":
        """Append a phase (fluent). Used when composing a custom template."""
        if not isinstance(phase, WorkflowPhase):
            raise WorkflowError("add_phase expects a WorkflowPhase")
        self.phases.append(phase)
        return self

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "framework": self.framework,
            "description": self.description,
            "phases": [p.to_dict() for p in self.phases],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowTemplate":
        if not isinstance(data, dict):
            raise WorkflowError("template data must be a dict")
        try:
            phases = [
                WorkflowPhase.from_dict(p) for p in data.get("phases", [])
            ]
            return cls(
                name=data["name"],
                phases=phases,
                framework=data.get("framework", "custom"),
                description=data.get("description", ""),
            )
        except KeyError as exc:
            raise WorkflowError(f"template dict missing key: {exc}") from exc


@dataclass
class ValidationResult:
    """Result of validating a template."""

    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Built-in templates — mirror the frameworks named in the transcript
# ─────────────────────────────────────────────────────────────────────────────


def _build_prp_template() -> WorkflowTemplate:
    """PRP = Product Requirement Prompt.

    The author: "When you generate a PRP, you're taking your initial
    requirements and turning it into a much more structured document ... that
    has things like the task list ..., your desired codebase structure, your
    success criteria, all the documentation examples that you wanted to
    reference." Planning & validation use sub-agents; implementation does not.
    """
    return WorkflowTemplate(
        name="prp",
        framework="prp",
        description=(
            "Product Requirement Prompt: vibe plan -> initial requirements "
            "(PRD) -> context-engineered plan -> implement task-by-task -> "
            "validate."
        ),
        phases=[
            WorkflowPhase(
                name="vibe_planning",
                role="research_companion",
                instructions=(
                    "Free-form exploration of ideas, architecture, concepts, "
                    "and tech stack with the AI as a research companion. "
                    "Unstructured on purpose."
                ),
                inputs=["idea"],
                outputs=["exploration_notes"],
                uses_sub_agent=False,
                context_components=["memory"],
            ),
            WorkflowPhase(
                name="initial_requirements",
                role="planner",
                instructions=(
                    "Produce the 'initial MD' / PRD: a high-level feature "
                    "request you could hand another human, with references to "
                    "supporting docs and examples."
                ),
                inputs=["exploration_notes"],
                outputs=["initial_md"],
                uses_sub_agent=False,
                context_components=["prompt_engineering"],
            ),
            WorkflowPhase(
                name="create_plan",
                role="codebase_analyst",
                instructions=(
                    "Read/understand requirements, research via RAG + web + a "
                    "codebase-analyst sub-agent, then produce granular tasks, "
                    "desired codebase structure, documentation/example "
                    "references, and success criteria."
                ),
                inputs=["initial_md"],
                outputs=["plan", "tasks", "success_criteria"],
                uses_sub_agent=True,
                context_components=["rag", "task_management"],
            ),
            WorkflowPhase(
                name="implementation",
                role="implementer",
                instructions=(
                    "Execute the plan task-by-task, cycling each task "
                    "TODO->DOING->REVIEW->DONE one at a time to avoid "
                    "hallucination. No sub-agents: keep shared primary "
                    "context."
                ),
                inputs=["plan", "tasks"],
                outputs=["code"],
                uses_sub_agent=False,
                context_components=["task_management", "memory"],
            ),
            WorkflowPhase(
                name="validation",
                role="validator",
                instructions=(
                    "Validator sub-agent generates and runs tests in an "
                    "isolated context; a human performs a code review and can "
                    "reopen tasks."
                ),
                inputs=["code", "success_criteria"],
                outputs=["test_report", "review_findings"],
                uses_sub_agent=True,
                context_components=["task_management"],
            ),
        ],
    )


def _build_spec_kit_template() -> WorkflowTemplate:
    """GitHub spec-kit style.

    The author: spec-kit "provides a lot of commands to help us do a very
    similar thing that we're doing here with the vibe planning and then ...
    creating our initial requirements and creating the plan." Modelled here as
    a command-driven spec -> plan -> implement -> validate flow.
    """
    return WorkflowTemplate(
        name="spec-kit",
        framework="spec-kit",
        description=(
            "GitHub spec-kit style: command-driven specify -> plan -> "
            "implement -> validate."
        ),
        phases=[
            WorkflowPhase(
                name="specify",
                role="slash_command",
                instructions=(
                    "Use spec-kit commands to capture a specification from the "
                    "high-level request (analogous to vibe planning + initial "
                    "requirements)."
                ),
                inputs=["idea"],
                outputs=["spec"],
                uses_sub_agent=False,
                context_components=["prompt_engineering"],
            ),
            WorkflowPhase(
                name="plan",
                role="slash_command",
                instructions=(
                    "Turn the spec into a structured plan with tasks and "
                    "success criteria, researching context as needed."
                ),
                inputs=["spec"],
                outputs=["plan", "tasks", "success_criteria"],
                uses_sub_agent=True,
                context_components=["rag", "task_management"],
            ),
            WorkflowPhase(
                name="implement",
                role="implementer",
                instructions=(
                    "Execute the plan task-by-task in the primary context."
                ),
                inputs=["plan", "tasks"],
                outputs=["code"],
                uses_sub_agent=False,
                context_components=["task_management"],
            ),
            WorkflowPhase(
                name="validate",
                role="validator",
                instructions=(
                    "Validate the output with tests and a human review."
                ),
                inputs=["code", "success_criteria"],
                outputs=["test_report", "review_findings"],
                uses_sub_agent=True,
                context_components=["task_management"],
            ),
        ],
    )


def _build_three_step_template() -> WorkflowTemplate:
    """The author's fundamental mental model: PLAN -> IMPLEMENT -> VALIDATE."""
    return WorkflowTemplate(
        name="three-step",
        framework="custom",
        description=(
            "The author's primary mental model: planning -> implementing -> "
            "validating. The fundamental base to compose your own workflow."
        ),
        phases=[
            WorkflowPhase(
                name="planning",
                role="planner",
                instructions=(
                    "Plan: vibe-plan, capture requirements, and build a "
                    "context-engineered plan. The most important phase."
                ),
                inputs=["idea"],
                outputs=["plan"],
                uses_sub_agent=True,
                context_components=["rag", "task_management", "memory"],
            ),
            WorkflowPhase(
                name="implementing",
                role="implementer",
                instructions=(
                    "Implement the plan task-by-task in the primary context."
                ),
                inputs=["plan"],
                outputs=["code"],
                uses_sub_agent=False,
                context_components=["task_management"],
            ),
            WorkflowPhase(
                name="validating",
                role="validator",
                instructions=(
                    "Validate with tests and a human code review; reopen "
                    "tasks if needed."
                ),
                inputs=["code"],
                outputs=["test_report"],
                uses_sub_agent=True,
                context_components=["task_management"],
            ),
        ],
    )


_BUILTIN_BUILDERS = {
    "prp": _build_prp_template,
    "spec-kit": _build_spec_kit_template,
    "three-step": _build_three_step_template,
}


# ─────────────────────────────────────────────────────────────────────────────
# The engine
# ─────────────────────────────────────────────────────────────────────────────


class WorkflowEngine:
    """Registers templates and runs them over a context dict.

    Deterministic & pure: running a template produces a per-phase execution
    log; each phase is simulated as a structured transform that records which
    inputs it consumed from the context and merges its declared outputs back
    into the context (as placeholder artifact records, never fabricated LLM
    output).
    """

    def __init__(self) -> None:
        self._templates: Dict[str, WorkflowTemplate] = {}
        self.register_builtins()

    # ── registration ────────────────────────────────────────────────────────
    def register_builtins(self) -> None:
        for builder in _BUILTIN_BUILDERS.values():
            tmpl = builder()
            self._templates[tmpl.name] = tmpl

    def register_template(
        self, template: WorkflowTemplate, overwrite: bool = False
    ) -> None:
        if not isinstance(template, WorkflowTemplate):
            raise WorkflowError("register_template expects a WorkflowTemplate")
        if template.name in self._templates and not overwrite:
            raise WorkflowError(
                f"Template {template.name!r} already registered"
            )
        self._templates[template.name] = template

    def all_templates(self) -> List[str]:
        """Return the names of all registered templates."""
        return sorted(self._templates)

    def get_template(self, name: str) -> WorkflowTemplate:
        tmpl = self._templates.get(name)
        if tmpl is None:
            raise WorkflowError(f"No template named {name!r}")
        return tmpl

    def has_template(self, name: str) -> bool:
        return name in self._templates

    # ── composition ──────────────────────────────────────────────────────────
    def compose(
        self,
        name: str,
        phases: List[WorkflowPhase],
        framework: str = "custom",
        description: str = "",
        register: bool = True,
        overwrite: bool = False,
    ) -> WorkflowTemplate:
        """Compose a custom template from fundamental phases."""
        template = WorkflowTemplate(
            name=name,
            phases=list(phases),
            framework=framework,
            description=description,
        )
        if register:
            self.register_template(template, overwrite=overwrite)
        return template

    # ── validation ────────────────────────────────────────────────────────────
    def validate_template(
        self, template: WorkflowTemplate
    ) -> ValidationResult:
        """Validate: phases non-empty, unique names, required inputs satisfied.

        Required-inputs check: a phase input is satisfied if it was produced as
        an output by an earlier phase, or if it is a declared seed input of the
        first phase (treated as externally supplied).
        """
        errors: List[str] = []
        warnings: List[str] = []

        if not template.phases:
            errors.append("template has no phases")
            return ValidationResult(valid=False, errors=errors)

        names = template.phase_names()
        seen: Dict[str, int] = {}
        for n in names:
            seen[n] = seen.get(n, 0) + 1
        dupes = sorted(n for n, c in seen.items() if c > 1)
        for d in dupes:
            errors.append(f"duplicate phase name: {d!r}")

        # Required inputs: seed inputs come from the first phase's inputs.
        available: set[str] = set(template.phases[0].inputs)
        for idx, phase in enumerate(template.phases):
            if idx == 0:
                # first phase consumes seed inputs, which are externally given
                available.update(phase.inputs)
            else:
                for inp in phase.inputs:
                    if inp not in available:
                        errors.append(
                            f"phase {phase.name!r} requires input {inp!r} "
                            f"which is not produced by any earlier phase"
                        )
            available.update(phase.outputs)
            if not phase.outputs:
                warnings.append(f"phase {phase.name!r} produces no outputs")

        return ValidationResult(
            valid=not errors, errors=errors, warnings=warnings
        )

    # ── execution ────────────────────────────────────────────────────────────
    def run(
        self,
        template_name: str,
        context: Optional[Dict[str, Any]] = None,
        strict: bool = True,
    ) -> Dict[str, Any]:
        """Run a template over a context dict, producing a per-phase log.

        Pure & deterministic — simulates each phase as a structured transform.
        Returns a dict with keys: template, framework, context (final),
        phase_log (list of per-phase records), artifacts.
        """
        template = self.get_template(template_name)

        if strict:
            result = self.validate_template(template)
            if not result.valid:
                raise WorkflowError(
                    f"Cannot run invalid template {template_name!r}: "
                    f"{result.errors}"
                )

        ctx: Dict[str, Any] = copy.deepcopy(context or {})
        phase_log: List[Dict[str, Any]] = []
        artifacts: Dict[str, Any] = {}

        for order, phase in enumerate(template.phases):
            consumed: Dict[str, Any] = {}
            missing: List[str] = []
            for inp in phase.inputs:
                if inp in ctx:
                    consumed[inp] = ctx[inp]
                else:
                    missing.append(inp)

            produced: Dict[str, Any] = {}
            for out in phase.outputs:
                # Structured, deterministic artifact record (NOT fabricated
                # model output) — records provenance of the phase.
                artifact = {
                    "produced_by": phase.name,
                    "role": phase.role,
                    "order": order,
                    "from_inputs": list(phase.inputs),
                }
                produced[out] = artifact
                ctx[out] = artifact
                artifacts[out] = artifact

            phase_log.append(
                {
                    "order": order,
                    "phase": phase.name,
                    "role": phase.role,
                    "uses_sub_agent": phase.uses_sub_agent,
                    "context_components": list(phase.context_components),
                    "consumed": list(consumed),
                    "missing_inputs": missing,
                    "produced": list(produced),
                    "status": "completed" if not missing else "degraded",
                }
            )

        return {
            "template": template.name,
            "framework": template.framework,
            "phase_count": len(template.phases),
            "phase_log": phase_log,
            "artifacts": artifacts,
            "context": ctx,
        }

    def describe(self, template_name: str) -> Dict[str, Any]:
        """Return a JSON-safe description of a template."""
        return self.get_template(template_name).to_dict()
