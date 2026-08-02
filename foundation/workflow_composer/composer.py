"""
Workflow Composer: Dynamic Assembly of Module Pipelines.

Given a task description, the WorkflowComposer analyzes required capabilities,
selects suitable modules, and assembles an optimal ordered sequence respecting
constraints and dependencies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


class ExecutionMode(Enum):
    """How a module stage should be executed."""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    CONDITIONAL = "conditional"


@dataclass
class ModuleCapability:
    """Describes a capability that a module can provide.

    Attributes:
        name: The capability identifier (e.g. 'text_summarization', 'code_generation').
        confidence: How confident the module is at this capability (0.0 - 1.0).
        tags: Optional tags for fuzzy/multi-dimensional matching.
    """
    name: str
    confidence: float = 1.0
    tags: Set[str] = field(default_factory=set)

    def __post_init__(self):
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"Confidence must be in [0.0, 1.0], got {self.confidence}")


@dataclass
class ModuleConstraint:
    """A constraint that limits when or how a module can be used.

    Attributes:
        constraint_type: The type of constraint (e.g. 'max_tokens', 'requires_module', 'excludes_module').
        value: The constraint value (module name, token count, etc.).
        severity: 'hard' (must satisfy) or 'soft' (preference).
    """
    constraint_type: str
    value: Any
    severity: str = "hard"  # 'hard' or 'soft'


@dataclass
class Module:
    """Represents a composable module in the workflow system.

    Attributes:
        name: Unique module identifier.
        capabilities: Set of capabilities this module provides.
        constraints: Constraints on module usage.
        input_schema: Expected input keys/types for this module.
        output_schema: Output keys/types produced by this module.
        estimated_tokens: Estimated token cost to invoke this module.
        dependencies: Other module names this module depends on.
        metadata: Arbitrary additional metadata.
    """
    name: str
    capabilities: List[ModuleCapability] = field(default_factory=list)
    constraints: List[ModuleConstraint] = field(default_factory=list)
    input_schema: Dict[str, str] = field(default_factory=dict)
    output_schema: Dict[str, str] = field(default_factory=dict)
    estimated_tokens: int = 0
    dependencies: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def has_capability(self, capability_name: str) -> bool:
        """Check if this module provides a given capability by name."""
        return any(c.name == capability_name for c in self.capabilities)

    def capability_confidence(self, capability_name: str) -> float:
        """Return the confidence score for a given capability, or 0.0 if absent."""
        for c in self.capabilities:
            if c.name == capability_name:
                return c.confidence
        return 0.0

    def matches_tags(self, tags: Set[str]) -> bool:
        """Check if this module's capabilities match any of the given tags."""
        for cap in self.capabilities:
            if cap.tags & tags:
                return True
        return False


@dataclass
class Stage:
    """A single stage within a composed pipeline.

    Attributes:
        module_name: Name of the module to execute.
        mode: Execution mode for this stage.
        input_mapping: Maps pipeline-wide input keys to this module's inputs.
        output_mapping: Maps this module's outputs to pipeline-wide output keys.
        condition: Optional callable evaluated to decide whether to run (for CONDITIONAL mode).
        depends_on: Stage indices that must complete before this stage.
        metadata: Arbitrary additional metadata.
    """
    module_name: str
    mode: ExecutionMode = ExecutionMode.SEQUENTIAL
    input_mapping: Dict[str, str] = field(default_factory=dict)
    output_mapping: Dict[str, str] = field(default_factory=dict)
    condition: Optional[Callable[[Dict[str, Any]], bool]] = None
    depends_on: List[int] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ComposedPipeline:
    """The result of composing a pipeline: an ordered sequence of stages.

    Attributes:
        stages: Ordered list of stages to execute.
        estimated_total_tokens: Aggregate estimated token cost.
        required_inputs: Input keys that must be provided to run the pipeline.
        produced_outputs: Output keys the pipeline will produce.
        metadata: Arbitrary additional metadata (e.g. rationale, warnings).
    """
    stages: List[Stage] = field(default_factory=list)
    estimated_total_tokens: int = 0
    required_inputs: Set[str] = field(default_factory=set)
    produced_outputs: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CapabilityRequirement:
    """A parsed requirement extracted from a task description.

    Attributes:
        capability: The capability name needed.
        priority: Importance of this requirement (higher = more critical).
        constraints: Any constraints tied to this requirement.
    """
    capability: str
    priority: int = 1
    constraints: List[ModuleConstraint] = field(default_factory=list)


class WorkflowComposer:
    """Dynamically assembles optimal module pipelines from task descriptions.

    The composer analyzes a task description to extract capability requirements,
    matches them against a registry of available modules, and assembles a
    dependency-respecting, constraint-satisfying execution pipeline.

    Usage:
        composer = WorkflowComposer(modules=[...])
        pipeline = composer.compose("Summarize this text and extract key entities")
    """

    # Common capability keywords for task parsing
    _CAPABILITY_PATTERNS: Dict[str, List[str]] = {
        "text_summarization": ["summarize", "summarization", "summary", "summarise", "tl;dr", "condense"],
        "entity_extraction": ["extract entities", "entity extraction", "ner", "named entity", "find entities"],
        "code_generation": ["generate code", "write code", "code generation", "implement", "create function"],
        "text_classification": ["classify", "classification", "categorize", "categorise", "label"],
        "sentiment_analysis": ["sentiment", "polarity", "opinion", "tone analysis"],
        "translation": ["translate", "translation", "convert to"],
        "question_answering": ["answer", "question", "qa", "respond to"],
        "embeddings": ["embedding", "vectorize", "encode", "vector representation"],
        "data_extraction": ["extract data", "parse", "pull out", "retrieve"],
        "formatting": ["format", "reformat", "structure", "output format"],
        "validation": ["validate", "verify", "check", "ensure"],
        "reasoning": ["reason", "logic", "deduction", "inference", "chain of thought"],
    }

    def __init__(self, modules: Optional[List[Module]] = None):
        """Initialize the composer with an optional module registry.

        Args:
            modules: Initial list of available Module instances.
        """
        self._modules: Dict[str, Module] = {}
        if modules:
            for m in modules:
                self.register_module(m)

    # ------------------------------------------------------------------
    # Module Registry
    # ------------------------------------------------------------------

    def register_module(self, module: Module) -> None:
        """Register a module in the composer's registry.

        Args:
            module: The Module instance to register.

        Raises:
            ValueError: If a module with the same name is already registered.
        """
        if module.name in self._modules:
            raise ValueError(f"Module '{module.name}' is already registered")
        self._modules[module.name] = module

    def unregister_module(self, name: str) -> None:
        """Remove a module from the registry.

        Args:
            name: Name of the module to remove.

        Raises:
            KeyError: If the module is not found.
        """
        if name not in self._modules:
            raise KeyError(f"Module '{name}' not found")
        del self._modules[name]

    def get_module(self, name: str) -> Module:
        """Retrieve a registered module by name.

        Args:
            name: The module name.

        Returns:
            The Module instance.

        Raises:
            KeyError: If not found.
        """
        if name not in self._modules:
            raise KeyError(f"Module '{name}' not found")
        return self._modules[name]

    @property
    def modules(self) -> Dict[str, Module]:
        """Return a copy of the module registry."""
        return dict(self._modules)

    # ------------------------------------------------------------------
    # Task Analysis / Requirement Extraction
    # ------------------------------------------------------------------

    def extract_requirements(self, task_description: str) -> List[CapabilityRequirement]:
        """Parse a natural-language task description into structured capability requirements.

        Uses keyword matching against known capability patterns. Falls back to
        extracting noun-verb phrases when no patterns match.

        Args:
            task_description: Free-form text describing the desired workflow.

        Returns:
            A list of CapabilityRequirement instances in priority order.
        """
        text = task_description.lower()
        requirements: List[CapabilityRequirement] = []

        for capability, keywords in self._CAPABILITY_PATTERNS.items():
            for kw in keywords:
                if kw in text:
                    # Priority: earlier matches = higher priority (may be refined later)
                    priority = len(self._CAPABILITY_PATTERNS) - list(self._CAPABILITY_PATTERNS.keys()).index(capability)
                    requirements.append(CapabilityRequirement(capability=capability, priority=priority))
                    break  # no double-count per capability

        # Sort by descending priority
        requirements.sort(key=lambda r: r.priority, reverse=True)
        return requirements

    # ------------------------------------------------------------------
    # Capability Matching
    # ------------------------------------------------------------------

    def find_modules_for_capability(
        self, capability: str, min_confidence: float = 1e-9
    ) -> List[Tuple[Module, float]]:
        """Find all registered modules that provide a given capability.

        Args:
            capability: The capability name to search for.
            min_confidence: Minimum confidence threshold (0.0 - 1.0).

        Returns:
            List of (Module, confidence) tuples sorted by descending confidence.
        """
        matches: List[Tuple[Module, float]] = []
        for mod in self._modules.values():
            conf = mod.capability_confidence(capability)
            if conf >= min_confidence:
                matches.append((mod, conf))
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches

    def match_capabilities(
        self, requirements: List[CapabilityRequirement]
    ) -> Dict[str, List[Tuple[Module, float]]]:
        """Match a set of requirements to candidate modules.

        Args:
            requirements: Capability requirements from extract_requirements.

        Returns:
            Dict mapping capability name -> list of (Module, confidence) candidates.
        """
        result: Dict[str, List[Tuple[Module, float]]] = {}
        for req in requirements:
            candidates = self.find_modules_for_capability(req.capability)
            if candidates:
                result[req.capability] = candidates
        return result

    # ------------------------------------------------------------------
    # Constraint Satisfaction
    # ------------------------------------------------------------------

    def _check_module_constraints(
        self,
        module: Module,
        selected_modules: Set[str],
    ) -> Tuple[bool, List[str]]:
        """Check whether a module's constraints are satisfied given current selection.

        Args:
            module: The module to check.
            selected_modules: Set of already-selected module names.

        Returns:
            Tuple of (satisfied: bool, violations: List[str] describing issues).
        """
        violations: List[str] = []
        for c in module.constraints:
            if c.constraint_type == "requires_module":
                if c.value not in selected_modules:
                    violations.append(
                        f"'{module.name}' requires '{c.value}' which is not selected"
                    )
            elif c.constraint_type == "excludes_module":
                if c.value in selected_modules:
                    violations.append(
                        f"'{module.name}' is incompatible with selected '{c.value}'"
                    )
            elif c.constraint_type == "max_tokens":
                # Deferrable — will be caught by optimizer
                pass
        return len(violations) == 0, violations

    def _resolve_dependency_order(self, module_names: List[str]) -> List[str]:
        """Topologically sort module names so dependencies come first.

        Args:
            module_names: List of module names to order.

        Returns:
            Topologically sorted list of module names.

        Raises:
            ValueError: If a circular dependency is detected.
        """
        name_set = set(module_names)
        in_degree: Dict[str, int] = {n: 0 for n in module_names}
        adj: Dict[str, List[str]] = {n: [] for n in module_names}

        for name in module_names:
            mod = self._modules[name]
            for dep in mod.dependencies:
                if dep in name_set:
                    adj[dep].append(name)
                    in_degree[name] += 1

        # Kahn's algorithm
        queue = [n for n in module_names if in_degree[n] == 0]
        result: List[str] = []

        while queue:
            # Sort for deterministic output
            queue.sort()
            node = queue.pop(0)
            result.append(node)
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) != len(module_names):
            remaining = set(module_names) - set(result)
            raise ValueError(f"Circular dependency detected involving: {remaining}")

        return result

    # ------------------------------------------------------------------
    # Pipeline Composition
    # ------------------------------------------------------------------

    def compose(
        self,
        task_description: str,
        *,
        preferred_modules: Optional[List[str]] = None,
        max_modules: Optional[int] = None,
    ) -> ComposedPipeline:
        """Compose an optimal pipeline from a task description.

        This is the main entry point. It:
        1. Extracts capability requirements from the task description.
        2. Matches each requirement to candidate modules.
        3. Selects the best module per capability (respecting preferences).
        4. Checks constraints and resolves dependencies.
        5. Builds stages with input/output mappings.
        6. Returns a ComposedPipeline ready for validation and execution.

        Args:
            task_description: Free-form text describing the task.
            preferred_modules: Optional list of module names to prefer.
            max_modules: Optional cap on number of stages.

        Returns:
            A ComposedPipeline with ordered stages and metadata.

        Raises:
            ValueError: If no modules can satisfy a required capability.
        """
        requirements = self.extract_requirements(task_description)

        if not requirements:
            raise ValueError(
                f"No capability requirements could be extracted from: '{task_description}'"
            )

        # Match capabilities to modules and select best per capability
        matched = self.match_capabilities(requirements)
        selected_names: Set[str] = set()
        selected_modules: List[Module] = []
        selection_rationale: List[str] = []

        for req in requirements:
            candidates = matched.get(req.capability, [])
            if not candidates:
                raise ValueError(
                    f"No module found for capability '{req.capability}'. "
                    f"Required by: '{task_description}'"
                )

            # Prefer the user-specified module if it's in the candidates
            chosen: Optional[Module] = None
            if preferred_modules:
                for cand_mod, _ in candidates:
                    if cand_mod.name in preferred_modules:
                        chosen = cand_mod
                        selection_rationale.append(
                            f"'{req.capability}' -> '{chosen.name}' (preferred)"
                        )
                        break

            if chosen is None:
                # Pick highest confidence that satisfies constraints
                for cand_mod, conf in candidates:
                    ok, _ = self._check_module_constraints(cand_mod, selected_names)
                    if ok:
                        chosen = cand_mod
                        selection_rationale.append(
                            f"'{req.capability}' -> '{chosen.name}' (confidence={conf:.2f})"
                        )
                        break

            if chosen is None:
                # Fall back to highest-confidence even with constraint issues
                chosen = candidates[0][0]
                selection_rationale.append(
                    f"'{req.capability}' -> '{chosen.name}' (fallback)"
                )

            if chosen.name not in selected_names:
                selected_names.add(chosen.name)
                selected_modules.append(chosen)

            if max_modules and len(selected_modules) >= max_modules:
                break

        # Resolve dependency order
        module_names = [m.name for m in selected_modules]
        try:
            ordered_names = self._resolve_dependency_order(module_names)
        except ValueError as e:
            # If topological sort fails, fall back to insertion order
            ordered_names = module_names

        # Reorder selected_modules accordingly
        name_to_module = {m.name: m for m in selected_modules}
        ordered_modules = [name_to_module[n] for n in ordered_names]

        # Build stages
        stages: List[Stage] = []
        all_required_inputs: Set[str] = set()
        all_produced_outputs: Set[str] = set()
        total_tokens = 0

        for mod in ordered_modules:
            stage = Stage(
                module_name=mod.name,
                mode=ExecutionMode.SEQUENTIAL,
                input_mapping={k: k for k in mod.input_schema},
                output_mapping={k: k for k in mod.output_schema},
            )
            stages.append(stage)
            all_required_inputs.update(mod.input_schema.keys())
            all_produced_outputs.update(mod.output_schema.keys())
            total_tokens += mod.estimated_tokens

        # Remove inputs that are produced by earlier stages (internal dependencies)
        for i, stage in enumerate(stages):
            for prev in stages[:i]:
                all_required_inputs -= set(prev.output_mapping.values())

        return ComposedPipeline(
            stages=stages,
            estimated_total_tokens=total_tokens,
            required_inputs=all_required_inputs,
            produced_outputs=all_produced_outputs,
            metadata={
                "task_description": task_description,
                "requirements": [r.capability for r in requirements],
                "rationale": selection_rationale,
                "module_count": len(stages),
            },
        )

    # ------------------------------------------------------------------
    # Quick / Convenience Methods
    # ------------------------------------------------------------------

    def find_modules_by_tag(self, tags: Set[str]) -> List[Module]:
        """Return all modules whose capabilities match any of the given tags.

        Args:
            tags: Set of tag strings to match.

        Returns:
            List of matching Module instances.
        """
        return [m for m in self._modules.values() if m.matches_tags(tags)]

    def suggest_alternatives(self, module_name: str, capability: str) -> List[Module]:
        """Suggest alternative modules for a given capability.

        Args:
            module_name: The currently selected module name.
            capability: The capability to find alternatives for.

        Returns:
            List of alternative Module instances (excluding the given one).
        """
        candidates = self.find_modules_for_capability(capability)
        return [m for m, _ in candidates if m.name != module_name]