"""
Innovation R&D OS Module

Enterprise-grade innovation and research & development management system.
Provides tools for research tracking, experiment management, integrity checks,
sandboxed environments, technology scouting, and IP management.

Version: 1.0.0
"""

__version__ = "1.0.0"
__module__ = "innovation_rd"

from .research import ResearchDomain, ResearchEntry, ResearchLibrary
from .experiment import Experiment, ExperimentStatus, ExperimentTracker
from .integrity import IntegrityCheck, IntegrityReport
from .isolation import IsolationConfig, IsolationManager
from .scouting import ScoutTarget, ScoutEntry, ScoutEngine
from .ip import IPCategory, IPEntry, IPManager
from .pipeline import InnovationPipeline, Opportunity, Hypothesis, ResearchResult
from .pipeline import Assessment, ExperimentDesign, Prototype, MetricsSnapshot
from .pipeline import Comparison, Decision, Documentation, TransferPackage

__all__ = [
    "__version__",
    # Pipeline
    "InnovationPipeline",
    "Opportunity",
    "Hypothesis",
    "ResearchResult",
    "Assessment",
    "ExperimentDesign",
    "Prototype",
    "MetricsSnapshot",
    "Comparison",
    "Decision",
    "Documentation",
    "TransferPackage",
    # Research
    "ResearchDomain",
    "ResearchEntry",
    "ResearchLibrary",
    # Experiment
    "Experiment",
    "ExperimentStatus",
    "ExperimentTracker",
    # Integrity
    "IntegrityCheck",
    "IntegrityReport",
    # Isolation
    "IsolationConfig",
    "IsolationManager",
    # Scouting
    "ScoutTarget",
    "ScoutEntry",
    "ScoutEngine",
    # IP
    "IPCategory",
    "IPEntry",
    "IPManager",
]