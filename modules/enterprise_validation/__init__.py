"""
Enterprise Validation & Certification OS — Module Entry Point
==============================================================

@module(name='enterprise_validation', version='1.0.0')
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import pattern: use try/except for both import contexts
try:
    from enterprise.platform_kernel import Module, module, HealthStatus, EventBus
except ImportError:
    import sys
    _parent = str(Path(__file__).resolve().parents[3])
    if _parent not in sys.path:
        sys.path.insert(0, _parent)
    from enterprise.platform_kernel import Module, module, HealthStatus, EventBus

from .validation_engine import (
    ValidationEngine,
    CertificationLevel,
    ModuleScore,
    ValidationReport,
    EvidenceRecord,
    run_full_validation,
)

__all__ = [
    "EnterpriseValidationModule",
    "ValidationEngine",
    "CertificationLevel",
    "ModuleScore",
    "ValidationReport",
    "EvidenceRecord",
    "run_full_validation",
]

__version__ = "1.0.0"

logger = logging.getLogger("enterprise.validation")


@module(name="enterprise_validation", version="1.0.0")
class EnterpriseValidationModule(Module):
    """Enterprise Validation & Certification OS.

    Independent validation authority — not a developer. Evaluates the entire
    platform against measurable engineering standards using objective evidence.
    """

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self._engine: Optional[ValidationEngine] = None

    async def initialize(self) -> None:
        self._engine = ValidationEngine(config=self._config)
        self._status = HealthStatus.HEALTHY

    async def health_check(self) -> HealthStatus:
        return HealthStatus.HEALTHY if self._engine else HealthStatus.UNHEALTHY

    async def shutdown(self) -> None:
        self._engine = None
        self._status = HealthStatus.UNHEALTHY

    @property
    def engine(self) -> Optional[ValidationEngine]:
        return self._engine

    async def validate_all(self, evidence_dir: str = "") -> ValidationReport:
        """Run full platform validation and return report."""
        if not self._engine:
            raise RuntimeError("Module not initialized")
        return await self._engine.validate_all(evidence_dir=evidence_dir)

    async def validate_module(self, module_name: str) -> ModuleScore:
        """Validate a single module."""
        if not self._engine:
            raise RuntimeError("Module not initialized")
        return await self._engine.validate_module(module_name)