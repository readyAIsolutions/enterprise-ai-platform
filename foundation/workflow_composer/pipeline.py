"""
Pipeline Executor: Define and execute multi-module pipelines.

Supports sequential, parallel, and conditional execution modes with
input/output mapping between stages.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

try:
    from .composer import ComposedPipeline, ExecutionMode, Stage
except ImportError:
    from composer import ComposedPipeline, ExecutionMode, Stage


@dataclass
class StageResult:
    """Result from executing a single pipeline stage.

    Attributes:
        stage_index: Index of the stage within the pipeline.
        module_name: Name of the executed module.
        success: Whether the stage completed successfully.
        output: Output data produced by the stage.
        error: Error message if the stage failed.
        duration_ms: Execution duration in milliseconds.
        metadata: Additional execution metadata.
    """
    stage_index: int
    module_name: str
    success: bool = True
    output: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    """Aggregate result from executing an entire pipeline.

    Attributes:
        success: Whether all stages completed without error.
        stages: Per-stage results in execution order.
        final_output: Merged output from all stages.
        total_duration_ms: Total pipeline execution duration.
        metadata: Additional execution metadata.
    """
    success: bool = True
    stages: List[StageResult] = field(default_factory=list)
    final_output: Dict[str, Any] = field(default_factory=dict)
    total_duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class PipelineExecutor:
    """Executes multi-module pipelines with support for multiple execution modes.

    Handles:
    - Sequential: Stages run one after another in order.
    - Parallel: Independent stages execute concurrently.
    - Conditional: Stages run only when a condition callable evaluates to True.

    Usage:
        executor = PipelineExecutor(module_handlers={...})
        result = executor.execute(composed_pipeline, initial_input={"text": "..."})
    """

    def __init__(
        self,
        module_handlers: Optional[Dict[str, Callable[..., Dict[str, Any]]]] = None,
        max_parallel: int = 10,
    ):
        """Initialize the executor.

        Args:
            module_handlers: Mapping of module name -> async/sync callable that
                             accepts (context: dict) and returns a dict of outputs.
            max_parallel: Maximum number of stages to execute in parallel.
        """
        self._handlers: Dict[str, Callable[..., Dict[str, Any]]] = module_handlers or {}
        self._max_parallel = max_parallel

    # ------------------------------------------------------------------
    # Handler Management
    # ------------------------------------------------------------------

    def register_handler(self, module_name: str, handler: Callable[..., Dict[str, Any]]) -> None:
        """Register a callable handler for a module.

        The handler receives a single context dictionary of inputs and must
        return a dictionary of outputs.

        Args:
            module_name: The module this handler is for.
            handler: Callable that accepts context dict and returns output dict.
        """
        self._handlers[module_name] = handler

    def unregister_handler(self, module_name: str) -> None:
        """Remove a handler.

        Args:
            module_name: Name of the module whose handler to remove.

        Raises:
            KeyError: If not registered.
        """
        if module_name not in self._handlers:
            raise KeyError(f"No handler registered for '{module_name}'")
        del self._handlers[module_name]

    # ------------------------------------------------------------------
    # Pipeline Execution
    # ------------------------------------------------------------------

    def execute(
        self,
        pipeline: ComposedPipeline,
        initial_input: Optional[Dict[str, Any]] = None,
        *,
        stop_on_error: bool = True,
    ) -> PipelineResult:
        """Execute a composed pipeline.

        Stages are grouped into execution groups based on their mode and
        dependencies: all sequential stages run in order; parallel stages
        within a group run concurrently; conditional stages are skipped if
        their condition evaluates to False.

        Args:
            pipeline: The ComposedPipeline to execute.
            initial_input: Initial input data fed to the first stage(s).
            stop_on_error: If True, stops execution on first stage failure.

        Returns:
            A PipelineResult summarizing execution.

        Raises:
            ValueError: If a module has no registered handler.
        """
        import time

        context: Dict[str, Any] = dict(initial_input or {})
        stages = pipeline.stages
        results: List[StageResult] = []
        total_start = time.monotonic()

        # Group stages into sequential/parallel batches respecting dependencies
        execution_groups = self._build_execution_groups(stages)

        for group in execution_groups:
            group_results = self._execute_group(
                group, context, results, stop_on_error
            )
            results.extend(group_results)

            # Merge outputs back into context for downstream stages
            for sr in group_results:
                if sr.success:
                    context.update(sr.output)

            # Check for failures
            if stop_on_error:
                for sr in group_results:
                    if not sr.success:
                        total_elapsed = (time.monotonic() - total_start) * 1000
                        return PipelineResult(
                            success=False,
                            stages=results,
                            final_output=context,
                            total_duration_ms=total_elapsed,
                            metadata={"stopped_on_error": True},
                        )

        total_elapsed = (time.monotonic() - total_start) * 1000
        return PipelineResult(
            success=all(r.success for r in results),
            stages=results,
            final_output=context,
            total_duration_ms=total_elapsed,
        )

    async def execute_async(
        self,
        pipeline: ComposedPipeline,
        initial_input: Optional[Dict[str, Any]] = None,
        *,
        stop_on_error: bool = True,
    ) -> PipelineResult:
        """Async version of execute. Uses asyncio for parallel stage execution.

        Args:
            pipeline: The ComposedPipeline to execute.
            initial_input: Initial input data.
            stop_on_error: Whether to stop on first failure.

        Returns:
            A PipelineResult.
        """
        import time

        context: Dict[str, Any] = dict(initial_input or {})
        stages = pipeline.stages
        results: List[StageResult] = []
        total_start = time.monotonic()

        execution_groups = self._build_execution_groups(stages)

        for group in execution_groups:
            group_results = await self._execute_group_async(
                group, context, results, stop_on_error
            )
            results.extend(group_results)

            for sr in group_results:
                if sr.success:
                    context.update(sr.output)

            if stop_on_error:
                for sr in group_results:
                    if not sr.success:
                        total_elapsed = (time.monotonic() - total_start) * 1000
                        return PipelineResult(
                            success=False,
                            stages=results,
                            final_output=context,
                            total_duration_ms=total_elapsed,
                            metadata={"stopped_on_error": True},
                        )

        total_elapsed = (time.monotonic() - total_start) * 1000
        return PipelineResult(
            success=all(r.success for r in results),
            stages=results,
            final_output=context,
            total_duration_ms=total_elapsed,
        )

    # ------------------------------------------------------------------
    # Internal: Execution Groups
    # ------------------------------------------------------------------

    def _build_execution_groups(self, stages: List[Stage]) -> List[List[Stage]]:
        """Partition stages into groups that can execute together.

        Sequential stages each get their own group.
        Adjacent parallel stages without inter-dependencies share a group.
        Conditional stages are placed in their own group.

        Args:
            stages: Ordered list of Stage instances.

        Returns:
            List of stage groups (each group is a list of stages).
        """
        groups: List[List[Stage]] = []
        i = 0

        while i < len(stages):
            stage = stages[i]

            if stage.mode == ExecutionMode.PARALLEL:
                # Collect adjacent parallel stages that don't depend on each other
                batch = [stage]
                j = i + 1
                while j < len(stages) and stages[j].mode == ExecutionMode.PARALLEL:
                    # Only group if this stage doesn't depend on anything in the batch
                    dep_indices = set(stages[j].depends_on)
                    batch_indices = {stages.index(s) for s in batch}
                    if not dep_indices & batch_indices:
                        batch.append(stages[j])
                    else:
                        break
                    j += 1
                groups.append(batch)
                i = j
            else:
                # Sequential or conditional: standalone group
                groups.append([stage])
                i += 1

        return groups

    def _execute_group(
        self,
        group: List[Stage],
        context: Dict[str, Any],
        previous_results: List[StageResult],
        stop_on_error: bool,
    ) -> List[StageResult]:
        """Execute a group of stages (synchronous path).

        Args:
            group: List of stages to execute.
            context: Shared data context.
            previous_results: Previously accumulated results.
            stop_on_error: Whether to stop on error.

        Returns:
            List of StageResults for this group.
        """
        import time

        if len(group) == 1:
            return [self._execute_single_stage(group[0], context)]

        # Parallel execution of group
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(len(group), self._max_parallel)
        ) as executor:
            futures = {
                executor.submit(self._execute_single_stage, stage, context): stage
                for stage in group
            }
            group_results: List[StageResult] = []
            for future in concurrent.futures.as_completed(futures):
                sr = future.result()
                group_results.append(sr)
                if not sr.success and stop_on_error:
                    # Cancel remaining futures
                    for f in futures:
                        f.cancel()
                    break
            # Restore stage order by sorting on module_name position
            name_order = {s.module_name: i for i, s in enumerate(group)}
            group_results.sort(key=lambda r: name_order.get(r.module_name, 0))
            return group_results

    async def _execute_group_async(
        self,
        group: List[Stage],
        context: Dict[str, Any],
        previous_results: List[StageResult],
        stop_on_error: bool,
    ) -> List[StageResult]:
        """Execute a group of stages (async path)."""
        if len(group) == 1:
            return [self._execute_single_stage(group[0], context)]

        tasks = [
            asyncio.to_thread(self._execute_single_stage, stage, context)
            for stage in group
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        group_results: List[StageResult] = []
        for stage, result in zip(group, results):
            if isinstance(result, Exception):
                group_results.append(StageResult(
                    stage_index=group.index(stage),
                    module_name=stage.module_name,
                    success=False,
                    error=str(result),
                ))
            else:
                group_results.append(result)
        return group_results

    def _execute_single_stage(
        self, stage: Stage, context: Dict[str, Any]
    ) -> StageResult:
        """Execute a single stage, handling conditional logic.

        Args:
            stage: The stage to execute.
            context: Current data context.

        Returns:
            A StageResult.
        """
        import time

        start = time.monotonic()

        # Check conditional
        if stage.mode == ExecutionMode.CONDITIONAL:
            if stage.condition and not stage.condition(context):
                return StageResult(
                    stage_index=0,  # caller should fix index
                    module_name=stage.module_name,
                    success=True,
                    output={},
                    duration_ms=(time.monotonic() - start) * 1000,
                    metadata={"skipped": True, "reason": "condition_false"},
                )

        # Resolve input mapping
        module_input: Dict[str, Any] = {}
        for module_key, context_key in stage.input_mapping.items():
            if context_key in context:
                module_input[module_key] = context[context_key]

        # Check for handler
        handler = self._handlers.get(stage.module_name)
        if handler is None:
            elapsed = (time.monotonic() - start) * 1000
            return StageResult(
                stage_index=0,
                module_name=stage.module_name,
                success=False,
                error=f"No handler registered for module '{stage.module_name}'",
                duration_ms=elapsed,
            )

        # Execute the handler
        try:
            raw_output = handler(module_input)
        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            return StageResult(
                stage_index=0,
                module_name=stage.module_name,
                success=False,
                error=f"Handler raised: {exc}",
                duration_ms=elapsed,
            )

        # Apply output mapping
        mapped_output: Dict[str, Any] = {}
        for module_key, context_key in stage.output_mapping.items():
            if module_key in raw_output:
                mapped_output[context_key] = raw_output[module_key]

        elapsed = (time.monotonic() - start) * 1000
        return StageResult(
            stage_index=0,
            module_name=stage.module_name,
            success=True,
            output=mapped_output,
            duration_ms=elapsed,
        )