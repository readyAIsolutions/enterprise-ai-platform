"""
Workflow Composer Enterprise System.

Dynamically assembles, validates, optimizes, and executes multi-module pipelines
based on task requirements. Core components:

- WorkflowComposer: Assembles optimal module sequences from task descriptions
- PipelineExecutor: Executes multi-module pipelines (sequential, parallel, conditional)
- PipelineValidator: Validates pipeline integrity before execution
- PipelineOptimizer: Optimizes module selection to minimize token/cost usage
"""

from .composer import WorkflowComposer
from .pipeline import PipelineExecutor
from .validator import PipelineValidator
from .optimizer import PipelineOptimizer

__all__ = [
    "WorkflowComposer",
    "PipelineExecutor",
    "PipelineValidator",
    "PipelineOptimizer",
]