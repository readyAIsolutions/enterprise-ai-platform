"""error_correction — Hamming error-correcting code as an enterprise module.

Grounded in the 3blue1brown transcript *"Hamming codes part 2: The one-line
implementation"* (https://www.youtube.com/watch?v=b3NxrZOu_CE): the parity-check
results read as bits spell the position of a flipped bit, so a Hamming code
collapses to a tiny XOR/reduce computation. This module exposes that technique as
a pure-stdlib, network-free capability with a Platform Kernel lifecycle.

The deterministic core lives in
:mod:`enterprise.modules.error_correction.error_correction` (``HammingCode``,
``reduce_xor``, ``parity_positions``); this package registers it as a module with
an initialize / health_check / shutdown lifecycle and a thin facade.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from enterprise.platform_kernel import Event, HealthStatus, Module, module

from .error_correction import (
    HammingCode,
    decode_correct,
    encode,
    hamming_7_4,
    parity_positions,
    reduce_xor,
)

logger = logging.getLogger("eni.error_correction_module")

__version__ = "1.0.0"
__all__ = [
    "ErrorCorrectionModule",
    "create_error_correction_module",
    "HammingCode",
    "decode_correct",
    "encode",
    "hamming_7_4",
    "parity_positions",
    "reduce_xor",
]


@module(
    name="error_correction",
    version=__version__,
    config_defaults={
        "n": 7,  # codeword length (2**r - 1); 7 => (7,4) Hamming
    },
)
class ErrorCorrectionModule(Module):
    """Kernel module exposing a Hamming error-correcting code."""

    def __init__(self, config: Optional[dict] = None) -> None:
        super().__init__(config)
        self._code: Optional[HammingCode] = None
        self._event_bus = None

    async def initialize(self) -> None:
        self._status = HealthStatus.STARTING
        try:
            cfg = self._config or {}
            n = int(cfg.get("n", 7))
            self._code = HammingCode(n)
            self._status = HealthStatus.HEALTHY
        except Exception as exc:  # pragma: no cover - defensive
            self._status = HealthStatus.UNHEALTHY
            raise exc

    async def health_check(self) -> HealthStatus:
        return self._status

    async def shutdown(self) -> None:
        self._status = HealthStatus.STOPPING
        self._code = None

    # -- facade -------------------------------------------------------------
    def encode(self, data) -> list:
        code = self._require_code().encode(data)
        self._publish("error_correction.encoded", {"length": len(code)})
        return code
    def decode(self, code) -> list:
        return self._require_code().decode(code, fix=True)

    def correct(self, code) -> list:
        return self._require_code().correct(code)

    def syndrome(self, code) -> int:
        return self._require_code().syndrome(code)

    @property
    def dimensions(self) -> dict:
        code = self._require_code()
        return {"n": code.n, "k": code.k, "r": code.r}

    def stats(self) -> dict:
        code = self._require_code()
        return {
            "n": code.n,
            "k": code.k,
            "r": code.r,
            "min_distance": code.min_distance,
            "status": self._status.value,
        }

    # -- helpers ------------------------------------------------------------
    def _require_code(self) -> HammingCode:
        if self._code is None:
            raise RuntimeError("error_correction module not initialized")
        return self._code

    def _publish(self, topic: str, payload: dict) -> None:
        if self._event_bus is not None:
            self._event_bus.publish(
                Event.create(topic=topic, source=self.name, payload=payload)
            )

    def set_event_bus(self, event_bus) -> None:
        """Store the kernel EventBus for cross-module publishing."""
        self._event_bus = event_bus


def create_error_correction_module(config: Optional[dict] = None) -> ErrorCorrectionModule:
    """Factory used for kernel discovery / direct instantiation."""
    return ErrorCorrectionModule(config=config)
