"""
ENI ENTERPRISE PLATFORM KERNEL v1.0
Orchestrates all 10 OS modules + foundational systems.
Dynamic module loading, quality gates, audit trails, continuous improvement.
"""
__version__ = "3.0.0"
__author__ = "ENI Enterprise"

from .kernel import PlatformKernel
from .registry import ModuleRegistry
from .orchestrator import Orchestrator
from .quality_gate import QualityGateEngine
from .audit import AuditTrail

__all__ = [
    "PlatformKernel", "ModuleRegistry", "Orchestrator",
    "QualityGateEngine", "AuditTrail"
]