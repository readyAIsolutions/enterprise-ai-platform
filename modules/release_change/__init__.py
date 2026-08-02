"""
Release & Change Management OS Module

Enterprise-grade release and change management for the ENI platform.
Manages the full lifecycle of changes: classification, workflow,
deployment strategies, quality gates, and deliverables.

Supports:
  - Structured change workflows with 14 stages
  - Risk-based classification (13 change types, 4 risk levels)
  - 8 deployment strategies (canary, blue-green, staged rollout, etc.)
  - 10 quality gate checks
  - 10 deliverable types for compliance and audit readiness

Version: 1.0.0
"""

__version__ = "1.0.0"

from .workflow import ChangeStage, ChangeRecord, ChangeWorkflow
from .changes import ChangeType, RiskLevel, ChangeTemplate, ChangeClassifier
from .strategies import StrategyType, DeploymentStrategy, StrategyEngine
from .quality_gates import GateType, GateStatus, QualityGate, QualityGateEngine
from .deliverables import DeliverableType, Deliverable, DeliverableManager

__all__ = [
    # Workflow
    "ChangeStage",
    "ChangeRecord",
    "ChangeWorkflow",
    # Changes
    "ChangeType",
    "RiskLevel",
    "ChangeTemplate",
    "ChangeClassifier",
    # Strategies
    "StrategyType",
    "DeploymentStrategy",
    "StrategyEngine",
    # Quality Gates
    "GateType",
    "GateStatus",
    "QualityGate",
    "QualityGateEngine",
    # Deliverables
    "DeliverableType",
    "Deliverable",
    "DeliverableManager",
]