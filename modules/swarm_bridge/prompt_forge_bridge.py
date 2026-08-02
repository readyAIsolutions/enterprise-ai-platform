#!/usr/bin/env python3
"""
ENI PromptForge Bridge — Enterprise Wrapper
=============================================
Wraps the ENI PromptForge v1.0 engine as an enterprise module component.

PromptForge enhances builder prompts with live context:
  - Web search (DuckDuckGo) for current knowledge
  - Knowledge Base (MCP) skills & memories
  - LSP code intelligence from project filesystems
  - Swarm context (live builder states, blockers, reasoning)
  - YouTube transcript knowledge (harvested via PIA VPN rotation)
  - Model capability awareness
  - Live context injections (from LO / master_driver)

This bridge provides:
  - enhance_task()         — enhance a raw prompt with all context sources
  - enhance_for_builder()  — builder-specific enhancement with swarm awareness
  - batch_enhance()        — enhance multiple tasks in parallel
  - get_forge_status()     — health/metrics of the PromptForge engine

Gracefully degrades if PromptForge is not installed — returns the
original prompt unchanged with metadata noting the fallback.
"""
from __future__ import annotations

import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("enterprise.swarm.promptforge")


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class EnhancedTask:
    """Result of prompt enhancement for a builder task.

    Attributes:
        original:        The raw task prompt before enhancement.
        enhanced:        The fully enhanced prompt text.
        metadata:        Enhancement metadata (sources, lengths, ratios).
        builder:         Builder name (if builder-specific).
        model:           Target model.
        timestamp:       ISO timestamp of enhancement.
        sections:        Dict of section name → content for each source.
    """

    original: str
    enhanced: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    builder: str = ""
    model: str = "free-router"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    sections: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_length": len(self.original),
            "enhanced_length": len(self.enhanced),
            "compression_ratio": (
                round(len(self.enhanced) / max(len(self.original), 1), 2)
            ),
            "builder": self.builder,
            "model": self.model,
            "timestamp": self.timestamp,
            "sections_included": list(self.sections.keys()),
            "original": self.original[:300],
            "enhanced_preview": self.enhanced[:500],
            **{k: v for k, v in self.metadata.items() if k not in ("original_length", "enhanced_length")},
        }


# =============================================================================
# PromptForgeBridge
# =============================================================================


class PromptForgeBridge:
    """Enterprise bridge wrapping the ENI PromptForge engine.

    Usage::

        pf = PromptForgeBridge(enable_web=True, enable_swarm=True)
        result = pf.enhance_task("Build a trading dashboard")
        # Or for a specific builder:
        result = pf.enhance_for_builder("BUILDER_01", "Add OANDA integration")
    """

    def __init__(
        self,
        enable_web: bool = True,
        enable_youtube: bool = False,
        enable_swarm: bool = True,
        enable_kb: bool = True,
        enable_lsp: bool = True,
        enable_live_context: bool = True,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize the PromptForgeBridge.

        Args:
            enable_web:         Enable DuckDuckGo web search enhancement.
            enable_youtube:     Enable YouTube transcript harvesting (requires VPN).
            enable_swarm:       Include live swarm context in prompts.
            enable_kb:          Include knowledge base skills & memories.
            enable_lsp:         Include LSP code intelligence.
            enable_live_context: Include live LO context injections.
            config:             Additional PromptForge configuration.
        """
        self._config = config or {}
        self._enable_web = enable_web
        self._enable_youtube = enable_youtube
        self._enable_swarm = enable_swarm
        self._enable_kb = enable_kb
        self._enable_lsp = enable_lsp
        self._enable_live_context = enable_live_context

        self._forge = None
        self._available = False
        self._init_error: Optional[str] = None
        self._stats: Dict[str, Any] = {
            "total_enhancements": 0,
            "total_original_chars": 0,
            "total_enhanced_chars": 0,
            "avg_compression_ratio": 0.0,
            "last_enhancement": None,
            "errors": 0,
        }

        self._init_forge()

    # ── Initialization ─────────────────────────────────────────────────────

    def _init_forge(self) -> None:
        """Try to import and initialize PromptForge."""
        try:
            # Try both import paths
            try:
                from eni.prompt_forge import (
                    PromptForge,
                    get_forge,
                    PROMPTFORGE_AVAILABLE,
                )
                self._available = PROMPTFORGE_AVAILABLE
            except ImportError:
                # Maybe the swarm root is on sys.path
                from eni.prompt_forge import (
                    PromptForge,
                    get_forge,
                    PROMPTFORGE_AVAILABLE,
                )
                self._available = PROMPTFORGE_AVAILABLE

            if self._available:
                self._forge = get_forge(
                    enable_youtube=self._enable_youtube,
                    enable_web=self._enable_web,
                )
                logger.info(
                    "PromptForgeBridge initialized (web=%s, yt=%s, swarm=%s)",
                    self._enable_web,
                    self._enable_youtube,
                    self._enable_swarm,
                )
            else:
                self._init_error = "PromptForge reports PROMPTFORGE_AVAILABLE=False"
                logger.warning("PromptForgeBridge: %s", self._init_error)

        except ImportError as exc:
            self._init_error = f"PromptForge not importable: {exc}"
            logger.warning("PromptForgeBridge: %s", self._init_error)
        except Exception as exc:
            self._init_error = f"PromptForge init failed: {exc}"
            logger.error("PromptForgeBridge: %s", self._init_error)

    # ── Properties ─────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        """Is PromptForge available for enhancements?"""
        return self._available and self._forge is not None

    @property
    def init_error(self) -> Optional[str]:
        """Error message if initialization failed."""
        return self._init_error

    # ── Enhancement ────────────────────────────────────────────────────────

    def enhance_task(
        self,
        prompt: str,
        model: str = "free-router",
        *,
        include_web: Optional[bool] = None,
        include_youtube: Optional[bool] = None,
        include_swarm: Optional[bool] = None,
        include_kb: Optional[bool] = None,
        include_lsp: Optional[bool] = None,
        include_live: Optional[bool] = None,
    ) -> EnhancedTask:
        """Enhance a raw task prompt with all available context.

        Args:
            prompt:           The raw task description / prompt.
            model:            Target model name.
            include_web:      Override web search (default: instance setting).
            include_youtube:  Override YouTube knowledge (default: instance setting).
            include_swarm:    Override swarm context (default: instance setting).
            include_kb:       Override knowledge base (default: instance setting).
            include_lsp:      Override LSP code intelligence (default: instance setting).
            include_live:     Override live context (default: instance setting).

        Returns:
            EnhancedTask with the fully enhanced prompt and metadata.
        """
        start = time.time()

        if not self.available:
            return self._fallback_enhance(prompt, model)

        # Merge overrides with instance defaults
        web = include_web if include_web is not None else self._enable_web
        yt = include_youtube if include_youtube is not None else self._enable_youtube
        swarm = include_swarm if include_swarm is not None else self._enable_swarm
        kb = include_kb if include_kb is not None else self._enable_kb
        lsp = include_lsp if include_lsp is not None else self._enable_lsp
        live = include_live if include_live is not None else self._enable_live_context

        try:
            result = self._forge.enhance(
                prompt,
                model=model,
                include_web=web,
                include_yt=yt,
                include_swarm=swarm,
                include_kb=kb,
                include_lsp=lsp,
                include_live=live,
            )

            elapsed = time.time() - start
            task = EnhancedTask(
                original=prompt,
                enhanced=result.enhanced,
                metadata={
                    **result.metadata,
                    "enhancement_time_ms": round(elapsed * 1000, 1),
                },
                model=model,
                sections=result.sections,
            )

            self._update_stats(task, elapsed)
            logger.debug(
                "Enhanced prompt: %d → %d chars (%.1fx, %.0fms)",
                len(prompt), len(result.enhanced),
                result.metadata.get("compression_ratio", 0),
                elapsed * 1000,
            )
            return task

        except Exception as exc:
            self._stats["errors"] += 1
            logger.error("Enhancement failed: %s", exc)
            return self._fallback_enhance(prompt, model, error=str(exc))

    def enhance_for_builder(
        self,
        builder_name: str,
        task: str,
        model: str = "free-router",
    ) -> EnhancedTask:
        """Enhance a prompt specifically for a named builder.

        Adds swarm awareness, builder identity, and protocol instructions.

        Args:
            builder_name:  Builder name (e.g., 'BUILDER_03').
            task:          The task description.
            model:         Target model.

        Returns:
            EnhancedTask with builder-specific enhancement.
        """
        start = time.time()

        if not self.available:
            return self._fallback_enhance(task, model, builder=builder_name)

        try:
            result = self._forge.enhance_for_builder(builder_name, task, model=model)

            elapsed = time.time() - start
            enhanced_task = EnhancedTask(
                original=task,
                enhanced=result.enhanced,
                metadata={
                    **result.metadata,
                    "enhancement_time_ms": round(elapsed * 1000, 1),
                    "builder": builder_name,
                },
                builder=builder_name,
                model=model,
                sections=result.sections,
            )

            self._update_stats(enhanced_task, elapsed)
            logger.debug(
                "Enhanced for builder %s: %d → %d chars (%.1fx)",
                builder_name,
                len(task), len(result.enhanced),
                result.metadata.get("compression_ratio", 0),
            )
            return enhanced_task

        except Exception as exc:
            self._stats["errors"] += 1
            logger.error("Builder enhancement failed for %s: %s", builder_name, exc)
            return self._fallback_enhance(task, model, builder=builder_name, error=str(exc))

    def batch_enhance(
        self,
        tasks: List[Dict[str, str]],
        model: str = "free-router",
    ) -> List[EnhancedTask]:
        """Enhance multiple tasks (potentially for different builders).

        Args:
            tasks: List of dicts with 'builder' (optional) and 'task' keys.
            model: Target model for all tasks.

        Returns:
            List of EnhancedTask results (same order as input).
        """
        results: List[EnhancedTask] = []
        for entry in tasks:
            builder = entry.get("builder", "")
            task_text = entry.get("task", "")
            if not task_text:
                results.append(EnhancedTask(
                    original="",
                    enhanced="",
                    metadata={"error": "empty task"},
                ))
                continue

            if builder:
                result = self.enhance_for_builder(builder, task_text, model=model)
            else:
                result = self.enhance_task(task_text, model=model)
            results.append(result)

        return results

    # ── Fallback ───────────────────────────────────────────────────────────

    def _fallback_enhance(
        self,
        prompt: str,
        model: str = "free-router",
        builder: str = "",
        error: str = "",
    ) -> EnhancedTask:
        """Return the original prompt as-is with metadata noting the fallback."""
        return EnhancedTask(
            original=prompt,
            enhanced=prompt,  # No enhancement
            metadata={
                "fallback": True,
                "error": error or self._init_error or "PromptForge unavailable",
                "compression_ratio": 1.0,
                "enhancement_time_ms": 0,
                "sources_used": [],
            },
            builder=builder,
            model=model,
        )

    # ── Stats ──────────────────────────────────────────────────────────────

    def _update_stats(self, task: EnhancedTask, elapsed_sec: float) -> None:
        """Update internal enhancement statistics."""
        self._stats["total_enhancements"] += 1
        self._stats["total_original_chars"] += len(task.original)
        self._stats["total_enhanced_chars"] += len(task.enhanced)
        total = self._stats["total_enhancements"]
        if total > 0 and self._stats["total_original_chars"] > 0:
            self._stats["avg_compression_ratio"] = round(
                self._stats["total_enhanced_chars"] / self._stats["total_original_chars"], 2
            )
        self._stats["last_enhancement"] = datetime.now(timezone.utc).isoformat()

    def get_forge_status(self) -> Dict[str, Any]:
        """Get PromptForge health and usage statistics.

        Returns:
            Dict with 'available', 'stats', 'config', 'init_error'.
        """
        return {
            "available": self.available,
            "init_error": self._init_error,
            "config": {
                "enable_web": self._enable_web,
                "enable_youtube": self._enable_youtube,
                "enable_swarm": self._enable_swarm,
                "enable_kb": self._enable_kb,
                "enable_lsp": self._enable_lsp,
                "enable_live_context": self._enable_live_context,
            },
            "stats": self._stats,
        }

    # ── Cleanup ────────────────────────────────────────────────────────────

    def shutdown(self) -> None:
        """Shut down PromptForge (stops background YouTube harvester)."""
        if self._forge:
            try:
                self._forge.shutdown()
                logger.info("PromptForge shut down")
            except Exception as exc:
                logger.warning("Error shutting down PromptForge: %s", exc)
        self._forge = None
        self._available = False

    def __repr__(self) -> str:
        return (
            f"<PromptForgeBridge available={self.available} "
            f"enhancements={self._stats['total_enhancements']}>"
        )
