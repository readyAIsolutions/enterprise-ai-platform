"""Pure-stdlib core for the context_workflow_framework module.

Grounded in ColeMedin's "The True Power of AI Coding - Build Your OWN
Workflows" (https://www.youtube.com/watch?v=mHBk8Z7Exag). The talk argues
that AI coding is about building REUSABLE WORKFLOWS/SYSTEMS rather than
one-off prompts, and that existing frameworks (PRP = Product Requirement
Prompt, BMAD, GitHub spec-kit) all share the same PHILOSOPHY: scope the
task, gather and assemble context (docs, examples, rules), plan, implement,
and validate. Instead of adopting one framework wholesale, you should
understand that shared structure and COMPOSE YOUR OWN workflow.

This module is NETWORK-FREE and uses only the standard library.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


class WorkflowError(Exception):
    """Raised for invalid workflow composition or lookups."""


@dataclass
class WorkflowPhase:
    """A single phase of a context-engineering workflow.

    Mirrors the shared structure of PRP/BMAD/spec-kit: every phase has a
    purpose and concrete instructions, and declares the context keys it
    requires (docs, examples, rules, requirements, ...).
    """

    name: str
    purpose: str
    instructions: str = ""
    required_context: List[str] = field(default_factory=list)

    def missing_context(self, provided: Dict[str, object]) -> List[str]:
        """Return required_context keys absent (or empty) in ``provided``."""
        missing: List[str] = []
        for key in self.required_context:
            value = provided.get(key)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(key)
        return missing

    def render(self) -> str:
        lines = [f"## Phase: {self.name}", "", f"**Purpose:** {self.purpose}"]
        if self.instructions:
            lines += ["", self.instructions]
        if self.required_context:
            lines += ["", "**Required context:**"]
            lines += [f"- {key}" for key in self.required_context]
        return "\n".join(lines)


def _default_phases() -> List[WorkflowPhase]:
    """The default five-phase workflow mirroring the shared philosophy.

    scope -> gather_context -> plan -> implement -> validate
    """
    return [
        WorkflowPhase(
            name="scope",
            purpose="Define and scope the task and its success criteria.",
            instructions=(
                "Turn the initial idea into clear requirements: what to build, "
                "the success criteria, and the boundaries of the task."
            ),
            required_context=["requirements"],
        ),
        WorkflowPhase(
            name="gather_context",
            purpose="Gather and assemble the context the assistant needs.",
            instructions=(
                "Collect documentation, examples, and project rules via RAG, "
                "memory, and task management so the assistant is caught up."
            ),
            required_context=["docs", "examples", "rules"],
        ),
        WorkflowPhase(
            name="plan",
            purpose="Produce a structured planning document.",
            instructions=(
                "Turn requirements into a structured plan: task list, desired "
                "codebase structure, success criteria, and referenced docs."
            ),
            required_context=["requirements"],
        ),
        WorkflowPhase(
            name="implement",
            purpose="Implement the plan task by task.",
            instructions=(
                "Work through the task list, marking tasks to-do/doing/review "
                "and cycling until everything is done."
            ),
            required_context=["plan"],
        ),
        WorkflowPhase(
            name="validate",
            purpose="Validate the implementation against success criteria.",
            instructions=(
                "Create and run tests, perform a code review, and confirm the "
                "work meets the success criteria before finishing."
            ),
            required_context=["plan"],
        ),
    ]


def _prp_phases() -> List[WorkflowPhase]:
    """PRP (Product Requirement Prompt) oriented template."""
    return [
        WorkflowPhase(
            name="initial_requirements",
            purpose="Capture the initial feature requirements.",
            required_context=["requirements"],
        ),
        WorkflowPhase(
            name="generate_prp",
            purpose=(
                "Generate the Product Requirement Prompt: task list, desired "
                "codebase structure, success criteria, documentation examples."
            ),
            required_context=["requirements", "docs", "examples"],
        ),
        WorkflowPhase(
            name="execute_prp",
            purpose="Execute the PRP to implement the feature.",
            required_context=["prp"],
        ),
        WorkflowPhase(
            name="validate",
            purpose="Validate against the PRP success criteria.",
            required_context=["prp"],
        ),
    ]


def _bmad_phases() -> List[WorkflowPhase]:
    """BMAD oriented template emphasizing agent roles across the lifecycle."""
    return [
        WorkflowPhase(
            name="analyst",
            purpose="Analyze and brief the problem and requirements.",
            required_context=["requirements"],
        ),
        WorkflowPhase(
            name="architect",
            purpose="Design the architecture and desired structure.",
            required_context=["requirements", "docs"],
        ),
        WorkflowPhase(
            name="scrum_master",
            purpose="Break the architecture into a sequenced story/task list.",
            required_context=["architecture"],
        ),
        WorkflowPhase(
            name="developer",
            purpose="Implement the stories one at a time.",
            required_context=["stories"],
        ),
        WorkflowPhase(
            name="qa",
            purpose="Validate the implementation with tests and review.",
            required_context=["stories"],
        ),
    ]


def _spec_kit_phases() -> List[WorkflowPhase]:
    """GitHub spec-kit oriented template."""
    return [
        WorkflowPhase(
            name="specify",
            purpose="Write the specification of what to build.",
            required_context=["requirements"],
        ),
        WorkflowPhase(
            name="plan",
            purpose="Create the technical plan from the specification.",
            required_context=["spec"],
        ),
        WorkflowPhase(
            name="tasks",
            purpose="Break the plan into concrete, ordered tasks.",
            required_context=["plan"],
        ),
        WorkflowPhase(
            name="implement",
            purpose="Implement the tasks and validate the result.",
            required_context=["tasks"],
        ),
    ]


# Registry of named built-in templates. The point of the talk: these share a
# philosophy — understand it, then build your own by composing phases.
_TEMPLATES = {
    "prp": _prp_phases,
    "bmad": _bmad_phases,
    "spec_kit": _spec_kit_phases,
}


class WorkflowFramework:
    """An ordered, composable list of workflow phases.

    Defaults to the five-phase shared structure. Phases can be added,
    removed, and reordered; the framework can render a workflow document,
    validate provided context against each phase, walk to the next phase,
    and load named built-in templates.
    """

    def __init__(
        self,
        name: str = "custom",
        phases: Optional[List[WorkflowPhase]] = None,
    ) -> None:
        self.name = name
        self.phases: List[WorkflowPhase] = (
            list(phases) if phases is not None else _default_phases()
        )

    # ── composition ────────────────────────────────────────────────────────
    def phase_names(self) -> List[str]:
        return [p.name for p in self.phases]

    def get_phase(self, name: str) -> WorkflowPhase:
        for phase in self.phases:
            if phase.name == name:
                return phase
        raise WorkflowError(f"unknown phase: {name!r}")

    def add_phase(
        self, phase: WorkflowPhase, index: Optional[int] = None
    ) -> None:
        if phase.name in self.phase_names():
            raise WorkflowError(f"duplicate phase: {phase.name!r}")
        if index is None:
            self.phases.append(phase)
        else:
            self.phases.insert(index, phase)

    def remove_phase(self, name: str) -> None:
        if name not in self.phase_names():
            raise WorkflowError(f"unknown phase: {name!r}")
        self.phases = [p for p in self.phases if p.name != name]

    def reorder(self, order: List[str]) -> None:
        current = set(self.phase_names())
        if set(order) != current:
            raise WorkflowError(
                "reorder must list exactly the existing phase names"
            )
        lookup = {p.name: p for p in self.phases}
        self.phases = [lookup[name] for name in order]

    def next_phase(self, current: str) -> Optional[WorkflowPhase]:
        names = self.phase_names()
        if current not in names:
            raise WorkflowError(f"unknown phase: {current!r}")
        idx = names.index(current)
        if idx + 1 < len(self.phases):
            return self.phases[idx + 1]
        return None

    # ── rendering & validation ───────────────────────────────────────────────
    def render(self) -> str:
        lines = [f"# Workflow: {self.name}", ""]
        for phase in self.phases:
            lines.append(phase.render())
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def validate_context(
        self, provided: Dict[str, object]
    ) -> Dict[str, List[str]]:
        """Return a mapping of phase name -> missing required_context keys.

        Only phases with missing keys appear in the result.
        """
        result: Dict[str, List[str]] = {}
        for phase in self.phases:
            missing = phase.missing_context(provided)
            if missing:
                result[phase.name] = missing
        return result

    # ── templates ────────────────────────────────────────────────────────────
    @staticmethod
    def available_templates() -> List[str]:
        return sorted(_TEMPLATES)

    @classmethod
    def load_template(cls, name: str) -> "WorkflowFramework":
        if name not in _TEMPLATES:
            raise WorkflowError(
                f"unknown template: {name!r}; "
                f"available: {sorted(_TEMPLATES)}"
            )
        return cls(name=name, phases=_TEMPLATES[name]())


class ContextAssembler:
    """Assemble gathered context items into one ordered context block.

    Mirrors the "gather and assemble context" phase of the talk: docs,
    examples, and rules are gathered and composed into a single block with
    clear section headers, preserving insertion order.
    """

    def __init__(self) -> None:
        self._sections: List[tuple[str, str]] = []

    def add(self, section: str, content: str) -> "ContextAssembler":
        self._sections.append((section, content))
        return self

    def add_docs(self, content: str) -> "ContextAssembler":
        return self.add("docs", content)

    def add_examples(self, content: str) -> "ContextAssembler":
        return self.add("examples", content)

    def add_rules(self, content: str) -> "ContextAssembler":
        return self.add("rules", content)

    def sections(self) -> List[str]:
        return [name for name, _ in self._sections]

    def assemble(self) -> str:
        blocks: List[str] = []
        for section, content in self._sections:
            header = f"## {section}"
            blocks.append(f"{header}\n\n{content}".rstrip())
        return "\n\n".join(blocks).rstrip() + ("\n" if blocks else "")
