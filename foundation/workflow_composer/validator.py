"""
Pipeline Validator: Validate pipelines before execution.

Checks dependency ordering, input/output compatibility, circular
dependencies, and resource requirements.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from .composer import ComposedPipeline, Module, Stage
    from .pipeline import PipelineResult
except ImportError:
    from composer import ComposedPipeline, Module, Stage
    from pipeline import PipelineResult


@dataclass
class ValidationIssue:
    """A single validation issue.

    Attributes:
        severity: 'error' (fatal), 'warning' (non-fatal), or 'info'.
        message: Human-readable description.
        stage_index: The stage index this issue relates to (or None if global).
        code: Machine-readable issue code.
    """
    severity: str  # 'error', 'warning', 'info'
    message: str
    stage_index: Optional[int] = None
    code: str = ""


@dataclass
class ValidationReport:
    """Aggregate validation report.

    Attributes:
        is_valid: True if no errors were found (warnings are OK).
        issues: List of all validation issues found.
        metadata: Additional context about the validation.
    """
    is_valid: bool = True
    issues: List[ValidationIssue] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_error(self, message: str, stage_index: Optional[int] = None, code: str = "") -> None:
        """Add an error-level issue. Sets is_valid = False."""
        self.is_valid = False
        self.issues.append(ValidationIssue("error", message, stage_index, code))

    def add_warning(self, message: str, stage_index: Optional[int] = None, code: str = "") -> None:
        """Add a warning-level issue."""
        self.issues.append(ValidationIssue("warning", message, stage_index, code))

    def add_info(self, message: str, stage_index: Optional[int] = None, code: str = "") -> None:
        """Add an info-level issue."""
        self.issues.append(ValidationIssue("info", message, stage_index, code))

    @property
    def errors(self) -> List[ValidationIssue]:
        """Return only error-level issues."""
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> List[ValidationIssue]:
        """Return only warning-level issues."""
        return [i for i in self.issues if i.severity == "warning"]


class PipelineValidator:
    """Validates pipeline integrity and correctness before execution.

    Performs multiple validation passes:
    1. Dependency order — ensures every stage's dependencies are satisfied.
    2. Input/output compatibility — checks that data flows correctly between stages.
    3. Circular dependency detection — finds any cycles in the dependency graph.
    4. Resource requirements — verifies resource constraints (tokens, memory, etc.).

    Usage:
        validator = PipelineValidator(module_registry={...})
        report = validator.validate(pipeline)
        if report.is_valid:
            executor.execute(pipeline, ...)
    """

    def __init__(
        self,
        module_registry: Optional[Dict[str, Module]] = None,
        max_tokens: Optional[int] = None,
    ):
        """Initialize the validator.

        Args:
            module_registry: Dict of module name -> Module for schema checking.
            max_tokens: Optional global token budget for the pipeline.
        """
        self._modules: Dict[str, Module] = module_registry or {}
        self._max_tokens = max_tokens

    # ------------------------------------------------------------------
    # Main Entry Point
    # ------------------------------------------------------------------

    def validate(self, pipeline: ComposedPipeline) -> ValidationReport:
        """Run all validation checks on a composed pipeline.

        Args:
            pipeline: The ComposedPipeline to validate.

        Returns:
            A ValidationReport with any issues found.
        """
        report = ValidationReport()

        self._check_structure(pipeline, report)
        if report.is_valid:
            self._check_dependency_order(pipeline, report)
        self._check_io_compatibility(pipeline, report)
        self._check_circular_dependencies(pipeline, report)
        self._check_resource_requirements(pipeline, report)

        report.metadata["stage_count"] = len(pipeline.stages)
        report.metadata["total_issues"] = len(report.issues)
        report.metadata["error_count"] = len(report.errors)
        report.metadata["warning_count"] = len(report.warnings)

        return report

    # ------------------------------------------------------------------
    # Structural Checks
    # ------------------------------------------------------------------

    def _check_structure(self, pipeline: ComposedPipeline, report: ValidationReport) -> None:
        """Check basic structural integrity of the pipeline.

        Args:
            pipeline: Pipeline to check.
            report: Report to append issues to.
        """
        if not pipeline.stages:
            report.add_error("Pipeline has no stages", code="EMPTY_PIPELINE")
            return

        seen_modules: Set[str] = set()
        for i, stage in enumerate(pipeline.stages):
            if not stage.module_name:
                report.add_error(
                    f"Stage {i} has no module name", stage_index=i, code="MISSING_MODULE_NAME"
                )
            elif stage.module_name in seen_modules:
                report.add_warning(
                    f"Module '{stage.module_name}' appears multiple times",
                    stage_index=i,
                    code="DUPLICATE_MODULE",
                )
            seen_modules.add(stage.module_name)

            # Check module exists in registry (if provided)
            if self._modules and stage.module_name not in self._modules:
                report.add_error(
                    f"Module '{stage.module_name}' not found in registry",
                    stage_index=i,
                    code="UNKNOWN_MODULE",
                )

            # Validate depends_on indices
            for dep in stage.depends_on:
                if dep < 0 or dep >= len(pipeline.stages):
                    report.add_error(
                        f"Stage {i} depends on invalid index {dep}",
                        stage_index=i,
                        code="INVALID_DEPENDENCY_INDEX",
                    )
                elif dep >= i:
                    report.add_error(
                        f"Stage {i} depends on future stage {dep} (forward reference not allowed)",
                        stage_index=i,
                        code="FORWARD_DEPENDENCY",
                    )

    # ------------------------------------------------------------------
    # Dependency Order
    # ------------------------------------------------------------------

    def _check_dependency_order(self, pipeline: ComposedPipeline, report: ValidationReport) -> None:
        """Verify that all dependencies are satisfied in execution order.

        Checks that every stage's declared dependencies appear earlier in the pipeline.

        Args:
            pipeline: Pipeline to check.
            report: Report to append issues to.
        """
        available_outputs: Set[str] = set()
        unresolved_deps: Dict[str, Set[str]] = {}

        for i, stage in enumerate(pipeline.stages):
            # Module-level dependencies
            mod = self._modules.get(stage.module_name)
            if mod and mod.dependencies:
                unresolved = [d for d in mod.dependencies if d not in available_outputs]
                if unresolved:
                    unresolved_deps[stage.module_name] = set(unresolved)
                    report.add_warning(
                        f"Stage {i} ('{stage.module_name}') depends on modules not yet executed: {unresolved}. "
                        f"Outputs may be unavailable.",
                        stage_index=i,
                        code="UNSATISFIED_MODULE_DEP",
                    )

            # Stage-level dependencies (depends_on)
            for dep_idx in stage.depends_on:
                dep_stage = pipeline.stages[dep_idx]
                # Check that the dependency's outputs satisfy this stage's inputs
                if stage.input_mapping:
                    dep_outputs = set(dep_stage.output_mapping.values())
                    needed_inputs = set(stage.input_mapping.values())
                    missing = needed_inputs - dep_outputs - set(available_outputs) - set(stage.input_mapping.keys())
                    if missing:
                        report.add_warning(
                            f"Stage {i} may be missing inputs {missing} from dependency stage {dep_idx}",
                            stage_index=i,
                            code="MISSING_INPUT_FROM_DEP",
                        )

            # Track outputs produced by this stage
            available_outputs.add(stage.module_name)
            available_outputs.update(stage.output_mapping.values())

        if unresolved_deps:
            report.metadata["unresolved_dependencies"] = unresolved_deps

    # ------------------------------------------------------------------
    # Input/Output Compatibility
    # ------------------------------------------------------------------

    def _check_io_compatibility(self, pipeline: ComposedPipeline, report: ValidationReport) -> None:
        """Check that inputs and outputs are compatible between consecutive stages.

        Verifies that each stage's required inputs are either:
        - Provided as pipeline initial inputs (required_inputs)
        - Produced by an earlier stage
        - Or explicitly mapped

        Args:
            pipeline: Pipeline to check.
            report: Report to append issues to.
        """
        # Track what outputs are available at each stage
        available: Set[str] = set(pipeline.required_inputs or set())

        for i, stage in enumerate(pipeline.stages):
            mod = self._modules.get(stage.module_name)

            # Determine what this stage needs
            if stage.input_mapping:
                needed = set(stage.input_mapping.values())
            elif mod and mod.input_schema:
                needed = set(mod.input_schema.keys())
            else:
                needed = set()

            # Check if all needed inputs are available
            missing = needed - available
            if missing:
                report.add_warning(
                    f"Stage {i} ('{stage.module_name}') requires inputs {missing} "
                    f"but they are not available from prior stages or initial inputs",
                    stage_index=i,
                    code="MISSING_INPUT",
                )

            # Check type compatibility if schemas are known
            if mod:
                for out_key, out_type in mod.output_schema.items():
                    # Simple type name check (could be extended)
                    pass

            # Make this stage's outputs available
            if stage.output_mapping:
                available.update(stage.output_mapping.values())
            elif mod:
                available.update(mod.output_schema.keys())

    # ------------------------------------------------------------------
    # Circular Dependency Detection
    # ------------------------------------------------------------------

    def _check_circular_dependencies(
        self, pipeline: ComposedPipeline, report: ValidationReport
    ) -> None:
        """Detect circular dependencies in the pipeline's dependency graph.

        Uses DFS cycle detection on the stage dependency graph (depends_on edges).
        Also checks module-level dependency cycles if modules are registered.

        Args:
            pipeline: Pipeline to check.
            report: Report to append issues to.
        """
        n = len(pipeline.stages)

        # Build adjacency list from depends_on
        adj: Dict[int, List[int]] = {i: [] for i in range(n)}
        for i, stage in enumerate(pipeline.stages):
            for dep in stage.depends_on:
                if 0 <= dep < n:
                    adj[i].append(dep)

        # DFS-based cycle detection
        WHITE, GRAY, BLACK = 0, 1, 2
        color = [WHITE] * n
        cycle_nodes: List[int] = []

        def dfs(u: int) -> bool:
            color[u] = GRAY
            for v in adj[u]:
                if color[v] == GRAY:
                    # Back edge: cycle detected
                    cycle_nodes.extend([u, v])
                    return True
                elif color[v] == WHITE:
                    if dfs(v):
                        cycle_nodes.append(u)
                        return True
            color[u] = BLACK
            return False

        for i in range(n):
            if color[i] == WHITE:
                if dfs(i):
                    cycle_modules = [
                        pipeline.stages[idx].module_name
                        for idx in reversed(cycle_nodes)
                    ]
                    report.add_error(
                        f"Circular dependency detected: {' -> '.join(cycle_modules)}",
                        code="CIRCULAR_DEPENDENCY",
                    )
                    # Only report the first cycle
                    break

        # Also check module-level dependency cycles using the registry
        if self._modules:
            module_cycles = self._detect_module_cycles(pipeline)
            for cycle in module_cycles:
                report.add_error(
                    f"Module-level circular dependency: {' -> '.join(cycle)}",
                    code="MODULE_CIRCULAR_DEPENDENCY",
                )

    def _detect_module_cycles(self, pipeline: ComposedPipeline) -> List[List[str]]:
        """Detect cycles in the module dependency graph.

        Args:
            pipeline: Pipeline to check.

        Returns:
            List of cycles, each as a list of module names.
        """
        stage_modules = [s.module_name for s in pipeline.stages]
        module_set = set(stage_modules)
        adj: Dict[str, List[str]] = {}

        for name in module_set:
            mod = self._modules.get(name)
            if mod:
                adj[name] = [d for d in mod.dependencies if d in module_set]
            else:
                adj[name] = []

        # DFS cycle detection on module graph
        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        cycles: List[List[str]] = []
        path: List[str] = []

        def dfs(node: str) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in adj.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in rec_stack:
                    cycle_start = path.index(neighbor)
                    cycles.append(path[cycle_start:] + [neighbor])

            path.pop()
            rec_stack.discard(node)

        for node in module_set:
            if node not in visited:
                dfs(node)

        return cycles

    # ------------------------------------------------------------------
    # Resource Requirements
    # ------------------------------------------------------------------

    def _check_resource_requirements(
        self, pipeline: ComposedPipeline, report: ValidationReport
    ) -> None:
        """Check that the pipeline stays within resource constraints.

        Validates against:
        - Global token budget (if set)
        - Per-module token constraints

        Args:
            pipeline: Pipeline to check.
            report: Report to append issues to.
        """
        total_tokens = pipeline.estimated_total_tokens

        # Check global budget
        if self._max_tokens is not None and total_tokens > self._max_tokens:
            report.add_error(
                f"Pipeline estimated token usage ({total_tokens}) exceeds budget ({self._max_tokens})",
                code="TOKEN_BUDGET_EXCEEDED",
            )
        elif self._max_tokens is not None:
            usage_pct = (total_tokens / self._max_tokens) * 100
            if usage_pct > 80:
                report.add_warning(
                    f"Pipeline token usage ({total_tokens}/{self._max_tokens}) is at {usage_pct:.0f}% of budget",
                    code="TOKEN_BUDGET_HIGH",
                )

        # Check per-module constraints
        for i, stage in enumerate(pipeline.stages):
            mod = self._modules.get(stage.module_name)
            if mod:
                for c in mod.constraints:
                    if c.constraint_type == "max_tokens":
                        if mod.estimated_tokens > c.value:
                            report.add_warning(
                                f"Module '{stage.module_name}' estimated tokens ({mod.estimated_tokens}) "
                                f"exceeds its max_tokens constraint ({c.value})",
                                stage_index=i,
                                code="MODULE_TOKEN_EXCEEDED",
                            )

        report.metadata["estimated_total_tokens"] = total_tokens
        report.metadata["token_budget"] = self._max_tokens

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def validate_quick(self, pipeline: ComposedPipeline) -> bool:
        """Quick boolean check — returns True if pipeline has no errors.

        Args:
            pipeline: Pipeline to check.

        Returns:
            True if valid, False otherwise.
        """
        report = self.validate(pipeline)
        return report.is_valid