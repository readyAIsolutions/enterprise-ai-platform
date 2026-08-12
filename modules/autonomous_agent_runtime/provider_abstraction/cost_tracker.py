"""
Cost Tracker — Token/Cost Accounting
=====================================

Tracks token usage and costs per provider, model, and session.
Provides budgeting, alerts, and detailed reporting.

Follows ENI patterns: stdlib-first, async-native, comprehensive type hints.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .config_schema import BUILTIN_PRICING, CostTrackingConfig, ProviderConfig
from .provider_interface import CompletionResponse, EmbeddingResponse, ProviderMetrics


@dataclass
class UsageRecord:
    """Single usage record."""

    timestamp: float
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    request_id: str | None = None
    session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionUsage:
    """Aggregated usage for a session."""

    session_id: str
    started_at: float
    ended_at: float | None = None
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cost_usd: float = 0.0
    request_count: int = 0
    providers: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    models: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    @property
    def total_tokens(self) -> int:
        return self.total_prompt_tokens + self.total_completion_tokens

    @property
    def duration_seconds(self) -> float:
        end = self.ended_at or time.time()
        return end - self.started_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_seconds": self.duration_seconds,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "request_count": self.request_count,
            "providers": dict(self.providers),
            "models": dict(self.models),
        }


class CostTracker:
    """
    Tracks token usage and costs across providers and sessions.

    Features:
    - Per-provider, per-model, per-session accounting
    - Budget limits with alerts
    - Persistent storage (JSONL)
    - Real-time metrics emission
    - Cost estimation before requests
    """

    def __init__(
        self,
        config: CostTrackingConfig | None = None,
        metrics_callback: Callable[[str, dict[str, Any]], None] | None = None,
        storage_path: str | Path | None = None,
    ) -> None:
        self.config = config or CostTrackingConfig()
        self._metrics_callback = metrics_callback
        self._storage_path = Path(storage_path) if storage_path else None
        self._lock = asyncio.Lock()

        # In-memory tracking
        self._usage_records: list[UsageRecord] = []
        self._sessions: dict[str, SessionUsage] = {}
        self._current_session: str | None = None

        # Aggregated counters
        self._provider_totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._model_totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._daily_totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

        # Budget tracking
        self._session_budget_alerted = False
        self._daily_budget_alerted = False

        # Load existing data if storage exists
        if self._storage_path and self._storage_path.exists():
            self._load_from_storage()

    def _emit_metric(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        if self._metrics_callback:
            try:
                self._metrics_callback(name, {"value": value, "labels": labels or {}})
            except Exception:
                pass

    def _get_pricing(self, model: str) -> dict[str, float] | None:
        """Get pricing for a model."""
        # Check custom pricing first
        pricing = self.config.custom_pricing.get(model)
        if pricing:
            return pricing
        return BUILTIN_PRICING.get(model)

    def calculate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Calculate cost for token usage."""
        pricing = self._get_pricing(model)
        if not pricing:
            return 0.0

        input_cost = (prompt_tokens / 1000) * pricing.get("input_per_1k", 0)
        output_cost = (completion_tokens / 1000) * pricing.get("output_per_1k", 0)
        return input_cost + output_cost

    def estimate_cost(self, model: str, estimated_prompt_tokens: int, estimated_completion_tokens: int) -> float:
        """Estimate cost before making a request."""
        return self.calculate_cost(model, estimated_prompt_tokens, estimated_completion_tokens)

    async def record_usage(
        self,
        response: CompletionResponse | EmbeddingResponse,
        provider: str,
        request_id: str | None = None,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> UsageRecord:
        """Record usage from a completion or embedding response."""
        session_id = session_id or self._current_session or "default"

        if isinstance(response, CompletionResponse):
            prompt_tokens = response.prompt_tokens
            completion_tokens = response.completion_tokens
        else:
            prompt_tokens = response.usage.get("prompt_tokens", 0)
            completion_tokens = response.usage.get("completion_tokens", 0)

        total_tokens = prompt_tokens + completion_tokens
        model = response.model
        cost = response.cost_usd if response.cost_usd > 0 else self.calculate_cost(model, prompt_tokens, completion_tokens)

        record = UsageRecord(
            timestamp=time.time(),
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost,
            request_id=request_id,
            session_id=session_id,
            metadata=metadata or {},
        )

        async with self._lock:
            self._usage_records.append(record)
            self._update_aggregates(record, session_id)
            self._check_budgets(session_id)

            # Persist to storage
            if self._storage_path:
                await self._persist_record(record)

        self._emit_metric("usage_recorded", 1, {"provider": provider, "model": model})
        self._emit_metric("tokens_used", total_tokens, {"provider": provider, "model": model})
        self._emit_metric("cost_usd", cost, {"provider": provider, "model": model})

        return record

    def _update_aggregates(self, record: UsageRecord, session_id: str) -> None:
        """Update aggregated counters."""
        # Provider totals
        pt = self._provider_totals[record.provider]
        pt["prompt_tokens"] += record.prompt_tokens
        pt["completion_tokens"] += record.completion_tokens
        pt["total_tokens"] += record.total_tokens
        pt["cost_usd"] += record.cost_usd
        pt["requests"] += 1

        # Model totals
        mt = self._model_totals[record.model]
        mt["prompt_tokens"] += record.prompt_tokens
        mt["completion_tokens"] += record.completion_tokens
        mt["total_tokens"] += record.total_tokens
        mt["cost_usd"] += record.cost_usd
        mt["requests"] += 1

        # Daily totals
        day = time.strftime("%Y-%m-%d", time.localtime(record.timestamp))
        dt = self._daily_totals[day]
        dt["prompt_tokens"] += record.prompt_tokens
        dt["completion_tokens"] += record.completion_tokens
        dt["total_tokens"] += record.total_tokens
        dt["cost_usd"] += record.cost_usd
        dt["requests"] += 1

        # Session tracking
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionUsage(session_id=session_id, started_at=record.timestamp)

        session = self._sessions[session_id]
        session.total_prompt_tokens += record.prompt_tokens
        session.total_completion_tokens += record.completion_tokens
        session.total_cost_usd += record.cost_usd
        session.request_count += 1
        session.providers[record.provider] += 1
        session.models[record.model] += 1

    def _check_budgets(self, session_id: str) -> None:
        """Check and alert on budget thresholds."""
        session = self._sessions.get(session_id)
        if not session:
            return

        # Session budget
        if self.config.budget_per_session and not self._session_budget_alerted:
            pct = session.total_cost_usd / self.config.budget_per_session
            if pct >= self.config.alert_threshold_pct:
                self._session_budget_alerted = True
                self._emit_metric("budget_alert", 1, {"type": "session", "pct": str(pct)})

        # Daily budget
        day = time.strftime("%Y-%m-%d")
        daily = self._daily_totals.get(day, {})
        daily_cost = daily.get("cost_usd", 0)
        if self.config.budget_per_day and not self._daily_budget_alerted:
            pct = daily_cost / self.config.budget_per_day
            if pct >= self.config.alert_threshold_pct:
                self._daily_budget_alerted = True
                self._emit_metric("budget_alert", 1, {"type": "daily", "pct": str(pct)})

    async def _persist_record(self, record: UsageRecord) -> None:
        """Persist usage record to JSONL file."""
        if not self._storage_path:
            return

        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps({
                "timestamp": record.timestamp,
                "provider": record.provider,
                "model": record.model,
                "prompt_tokens": record.prompt_tokens,
                "completion_tokens": record.completion_tokens,
                "total_tokens": record.total_tokens,
                "cost_usd": record.cost_usd,
                "request_id": record.request_id,
                "session_id": record.session_id,
                "metadata": record.metadata,
            })
            with open(self._storage_path, "a") as f:
                f.write(line + "\n")
        except Exception:
            pass  # Never let persistence break the request

    def _load_from_storage(self) -> None:
        """Load usage records from storage."""
        if not self._storage_path or not self._storage_path.exists():
            return

        try:
            with open(self._storage_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    record = UsageRecord(**data)
                    self._usage_records.append(record)
                    self._update_aggregates(record, record.session_id or "default")
        except Exception:
            pass  # Corrupted storage, start fresh

    def start_session(self, session_id: str | None = None) -> str:
        """Start a new tracking session."""
        import uuid

        session_id = session_id or f"session_{uuid.uuid4().hex[:8]}"
        self._current_session = session_id
        self._session_budget_alerted = False
        return session_id

    def end_session(self, session_id: str | None = None) -> SessionUsage | None:
        """End a tracking session."""
        session_id = session_id or self._current_session
        if not session_id or session_id not in self._sessions:
            return None

        session = self._sessions[session_id]
        session.ended_at = time.time()

        if self._current_session == session_id:
            self._current_session = None
            self._session_budget_alerted = False

        return session

    def get_session_usage(self, session_id: str | None = None) -> SessionUsage | None:
        """Get usage for a session."""
        session_id = session_id or self._current_session
        if not session_id:
            return None
        return self._sessions.get(session_id)

    def get_provider_usage(self, provider: str | None = None) -> dict[str, dict[str, float]]:
        """Get aggregated usage by provider."""
        if provider:
            return {provider: dict(self._provider_totals.get(provider, {}))}
        return {k: dict(v) for k, v in self._provider_totals.items()}

    def get_model_usage(self, model: str | None = None) -> dict[str, dict[str, float]]:
        """Get aggregated usage by model."""
        if model:
            return {model: dict(self._model_totals.get(model, {}))}
        return {k: dict(v) for k, v in self._model_totals.items()}

    def get_daily_usage(self, days: int = 30) -> dict[str, dict[str, float]]:
        """Get daily usage for last N days."""
        cutoff = time.time() - (days * 86400)
        result = {}
        for day, totals in sorted(self._daily_totals.items()):
            day_ts = time.mktime(time.strptime(day, "%Y-%m-%d"))
            if day_ts >= cutoff:
                result[day] = dict(totals)
        return result

    def get_total_usage(self) -> dict[str, Any]:
        """Get overall usage summary."""
        total_prompt = sum(v["prompt_tokens"] for v in self._provider_totals.values())
        total_completion = sum(v["completion_tokens"] for v in self._provider_totals.values())
        total_cost = sum(v["cost_usd"] for v in self._provider_totals.values())
        total_requests = sum(v["requests"] for v in self._provider_totals.values())

        return {
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_tokens": total_prompt + total_completion,
            "total_cost_usd": round(total_cost, 6),
            "total_requests": total_requests,
            "providers": len(self._provider_totals),
            "models_used": len(self._model_totals),
            "active_sessions": len([s for s in self._sessions.values() if s.ended_at is None]),
        }

    def get_budget_status(self) -> dict[str, Any]:
        """Get current budget status."""
        session = self._sessions.get(self._current_session) if self._current_session else None
        day = time.strftime("%Y-%m-%d")
        daily = self._daily_totals.get(day, {})

        return {
            "session": {
                "budget": self.config.budget_per_session,
                "spent": session.total_cost_usd if session else 0,
                "remaining": max(0, (self.config.budget_per_session or 0) - (session.total_cost_usd if session else 0)),
                "pct_used": (session.total_cost_usd / self.config.budget_per_session * 100) if session and self.config.budget_per_session else 0,
                "alerted": self._session_budget_alerted,
            } if self.config.budget_per_session else None,
            "daily": {
                "budget": self.config.budget_per_day,
                "spent": daily.get("cost_usd", 0),
                "remaining": max(0, (self.config.budget_per_day or 0) - daily.get("cost_usd", 0)),
                "pct_used": (daily.get("cost_usd", 0) / self.config.budget_per_day * 100) if self.config.budget_per_day else 0,
                "alerted": self._daily_budget_alerted,
            } if self.config.budget_per_day else None,
        }

    async def export_usage(self, path: str | Path, format: str = "json") -> None:
        """Export usage data to file."""
        path = Path(path)
        data = {
            "summary": self.get_total_usage(),
            "budget": self.get_budget_status(),
            "by_provider": self.get_provider_usage(),
            "by_model": self.get_model_usage(),
            "by_day": self.get_daily_usage(),
            "sessions": {sid: s.to_dict() for sid, s in self._sessions.items()},
            "records": [
                {
                    "timestamp": r.timestamp,
                    "provider": r.provider,
                    "model": r.model,
                    "prompt_tokens": r.prompt_tokens,
                    "completion_tokens": r.completion_tokens,
                    "total_tokens": r.total_tokens,
                    "cost_usd": r.cost_usd,
                    "request_id": r.request_id,
                    "session_id": r.session_id,
                    "metadata": r.metadata,
                }
                for r in self._usage_records
            ],
        }

        if format == "json":
            path.write_text(json.dumps(data, indent=2))
        elif format == "jsonl":
            with open(path, "w") as f:
                for r in self._usage_records:
                    f.write(json.dumps({
                        "timestamp": r.timestamp,
                        "provider": r.provider,
                        "model": r.model,
                        "prompt_tokens": r.prompt_tokens,
                        "completion_tokens": r.completion_tokens,
                        "total_tokens": r.total_tokens,
                        "cost_usd": r.cost_usd,
                        "request_id": r.request_id,
                        "session_id": r.session_id,
                        "metadata": r.metadata,
                    }) + "\n")
        else:
            raise ValueError(f"Unsupported format: {format}")

    async def reset(self) -> None:
        """Reset all tracking data."""
        async with self._lock:
            self._usage_records.clear()
            self._sessions.clear()
            self._provider_totals.clear()
            self._model_totals.clear()
            self._daily_totals.clear()
            self._current_session = None
            self._session_budget_alerted = False
            self._daily_budget_alerted = False


__all__ = [
    "UsageRecord",
    "SessionUsage",
    "CostTracker",
]