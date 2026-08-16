#!/usr/bin/env python3
"""
ENI Model Resolver — Auto-Fallback Model Selection
===================================================
Probes OpenRouter's free models, maintains a prioritized fallback list,
and provides auto-switching when a model returns 429/401/403.

Used by eni_agent_term bridge to keep minis running regardless of
rate limits or expired keys.

Usage:
  resolver = ModelResolver()
  model = resolver.resolve("tencent/hy3:free")  # get best available model
  resolver.mark_failed("tencent/hy3:free", 429)  # mark as rate-limited
  next_model = resolver.resolve("tencent/hy3:free")  # will skip failed model
"""
from __future__ import annotations

import json
import time
import threading
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field

# ─── Paths ──────────────────────────────────────────────────────────────────
CACHE_DIR = Path.home() / ".cache" / "eni_swarm"
MODEL_CACHE = CACHE_DIR / "live_models.json"
MODEL_STATE = CACHE_DIR / "model_state.json"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ─── Known Free Models (OpenRouter free tier) ────────────────────────────────
# These are the models confirmed working via probe_models.py
DEFAULT_FREE_MODELS = [
    "tencent/hy3:free",           # Hunyuan 3 — most reliable free model
    "openai/gpt-3.5-turbo:free",  # GPT-3.5 Turbo
    "google/gemma-2-9b-it:free",  # Gemma 2 9B
    "mistralai/mistral-7b-instruct:free",  # Mistral 7B
    "nvidia/llama-3.1-nemotron-70b-instruct:free",  # NVIDIA Nemotron
    "microsoft/phi-3-mini-128k-instruct:free",  # Phi-3 Mini
    "qwen/qwen-2-7b-instruct:free",  # Qwen 2 7B
    "undi95/toppy-m-7b:free",     # Toppy M 7B
    "huggingfaceh4/zephyr-7b-beta:free",  # Zephyr 7B
]

# Models LO has confirmed working (from memory: 6/28 providers working)
LO_CONFIRMED_MODELS = [
    "openrouter/nemotron-ultra",  # 2 keys
    "zhipu/glm-5.2",
    "sambanova/DeepSeek-V3.1",
    "cerebras/gemma-4-31b",
    "nvidia/nemotron-nano",
    "upstage/solar-pro",
    "deepseek/deepseek-v4-pro",   # current model
]


@dataclass
class ModelEntry:
    """A tracked model with its health state."""
    name: str
    provider: str = "openrouter"
    alive: bool = True
    fail_count: int = 0
    consecutive_fails: int = 0
    last_fail_time: float = 0.0
    last_fail_code: int = 0
    cooldown_until: float = 0.0
    priority: int = 0
    total_uses: int = 0
    first_seen: float = field(default_factory=time.time)

    @property
    def in_cooldown(self) -> bool:
        return time.time() < self.cooldown_until

    @property
    def cooldown_remaining(self) -> float:
        return max(0, self.cooldown_until - time.time())


class ModelResolver:
    """
    Manages model availability and provides auto-fallback resolution.

    Maintains a prioritized list of models, tracking which are healthy,
    rate-limited, or dead. When resolving, returns the best available
    model, skipping those in cooldown or marked dead.
    """

    def __init__(self):
        self.models: Dict[str, ModelEntry] = {}
        self._lock = threading.RLock()
        self._load_state()
        self._ensure_defaults()

    def _ensure_defaults(self):
        """Add default free models if registry is empty."""
        with self._lock:
            if not self.models:
                for model in DEFAULT_FREE_MODELS:
                    self.models[model] = ModelEntry(name=model)

    def _load_state(self):
        """Load model state from disk."""
        if MODEL_STATE.exists():
            try:
                data = json.loads(MODEL_STATE.read_text())
                for name, entry_data in data.items():
                    self.models[name] = ModelEntry(**entry_data)
            except Exception:
                pass

    def save_state(self):
        """Persist model state to disk."""
        with self._lock:
            data = {name: {
                "name": m.name, "provider": m.provider, "alive": m.alive,
                "fail_count": m.fail_count, "consecutive_fails": m.consecutive_fails,
                "last_fail_time": m.last_fail_time, "last_fail_code": m.last_fail_code,
                "cooldown_until": m.cooldown_until, "priority": m.priority,
                "total_uses": m.total_uses, "first_seen": m.first_seen,
            } for name, m in self.models.items()}
            MODEL_STATE.write_text(json.dumps(data, indent=2))

    def resolve(self, preferred: Optional[str] = None) -> Optional[str]:
        """
        Resolve the best available model.

        Args:
            preferred: Preferred model to try first

        Returns:
            Model name string, or None if no models available
        """
        with self._lock:
            # Ensure preferred model exists in registry
            if preferred and preferred not in self.models:
                self.models[preferred] = ModelEntry(name=preferred)

            # Build candidate list: preferred first, then by priority
            candidates = []
            for name, entry in self.models.items():
                if entry.in_cooldown:
                    continue
                if not entry.alive and entry.consecutive_fails > 3:
                    continue
                priority = 0
                if name == preferred:
                    priority = 1000
                elif entry.alive:
                    priority = entry.priority + 500 - entry.consecutive_fails * 10
                else:
                    priority = entry.priority - entry.consecutive_fails * 50
                candidates.append((priority, name))

            candidates.sort(key=lambda x: -x[0])

            # Return best candidate
            if candidates:
                model = candidates[0][1]
                self.models[model].total_uses += 1
                return model

            # All models are dead/cooldown — return least-dead one
            if preferred and preferred in self.models:
                return preferred
            if self.models:
                return min(self.models.values(),
                          key=lambda m: m.cooldown_remaining).name
            return None

    def mark_failed(self, model: str, status_code: int):
        """
        Mark a model as failed with the given HTTP status code.

        Cooldown strategy:
        - 401/403 (auth): 30-minute cooldown, mark dead
        - 402 (no credits): 5-minute cooldown
        - 429 (rate limited): exponential backoff based on consecutive fails
        - 5xx (server error): 1-minute cooldown
        """
        with self._lock:
            if model not in self.models:
                self.models[model] = ModelEntry(name=model)

            entry = self.models[model]
            entry.fail_count += 1
            entry.consecutive_fails += 1
            entry.last_fail_time = time.time()
            entry.last_fail_code = status_code

            if status_code in (401, 403):
                # Auth failure — long cooldown
                entry.cooldown_until = time.time() + 1800  # 30 min
                entry.alive = False
            elif status_code == 402:
                entry.cooldown_until = time.time() + 300  # 5 min
            elif status_code == 429:
                # Exponential backoff: 10s * 2^fails, max 15 min
                backoff = min(10 * (2 ** min(entry.consecutive_fails, 6)), 900)
                entry.cooldown_until = time.time() + backoff
            else:
                entry.cooldown_until = time.time() + 60

            self.save_state()

    def mark_success(self, model: str):
        """Mark a model as working — resets consecutive fail count."""
        with self._lock:
            if model in self.models:
                entry = self.models[model]
                entry.consecutive_fails = 0
                entry.alive = True
                entry.cooldown_until = 0
                self.save_state()

    def add_model(self, model: str, provider: str = "openrouter", priority: int = 0):
        """Add a new model to the registry."""
        with self._lock:
            if model not in self.models:
                self.models[model] = ModelEntry(
                    name=model, provider=provider, priority=priority
                )
                self.save_state()

    def get_all(self) -> List[Dict]:
        """Get all models with their status."""
        with self._lock:
            return [
                {
                    "name": name,
                    "alive": m.alive,
                    "in_cooldown": m.in_cooldown,
                    "cooldown_remaining": round(m.cooldown_remaining, 1),
                    "consecutive_fails": m.consecutive_fails,
                    "total_uses": m.total_uses,
                    "last_fail_code": m.last_fail_code,
                }
                for name, m in sorted(
                    self.models.items(),
                    key=lambda x: (-x[1].alive, x[1].cooldown_remaining)
                )
            ]

    def healthy_count(self) -> int:
        """Count of healthy (alive, not in cooldown) models."""
        with self._lock:
            return sum(1 for m in self.models.values()
                      if m.alive and not m.in_cooldown)

    def reset_all(self):
        """Reset all models to healthy state."""
        with self._lock:
            for m in self.models.values():
                m.alive = True
                m.consecutive_fails = 0
                m.cooldown_until = 0
            self.save_state()


# ─── CLI ─────────────────────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description="ENI Model Resolver")
    parser.add_argument("--list", action="store_true", help="List all models with status")
    parser.add_argument("--resolve", type=str, help="Resolve best model, optionally with preferred")
    parser.add_argument("--fail", type=str, help="Mark model as failed: MODEL:CODE (e.g. deepseek/deepseek-chat:429)")
    parser.add_argument("--success", type=str, help="Mark model as successful")
    parser.add_argument("--add", type=str, help="Add a model to registry")
    parser.add_argument("--reset", action="store_true", help="Reset all models to healthy")
    args = parser.parse_args()

    resolver = ModelResolver()

    if args.reset:
        resolver.reset_all()
        print("All models reset to healthy.")

    if args.add:
        resolver.add_model(args.add)
        print(f"Added: {args.add}")

    if args.fail:
        parts = args.fail.split(":")
        model = parts[0]
        code = int(parts[1]) if len(parts) > 1 else 500
        resolver.mark_failed(model, code)
        print(f"Marked {model} as failed (HTTP {code})")

    if args.success:
        resolver.mark_success(args.success)
        print(f"Marked {args.success} as successful")

    if args.resolve:
        result = resolver.resolve(args.resolve)
        print(f"Preferred: {args.resolve}")
        print(f"Resolved: {result or 'NO MODELS AVAILABLE'}")

    if args.list or not any([args.resolve, args.fail, args.success, args.add, args.reset]):
        models = resolver.get_all()
        print(f"\n{'Model':<45} {'Alive':<8} {'Cooldown':<12} {'Fails':<8} {'Uses':<8} {'Last'}")
        print("-" * 100)
        for m in models:
            alive = "🟢" if m["alive"] else "🔴"
            cd = f"{m['cooldown_remaining']}s" if m["in_cooldown"] else "—"
            print(f"{m['name']:<45} {alive:<8} {cd:<12} {m['consecutive_fails']:<8} {m['total_uses']:<8} {m['last_fail_code']}")
        print(f"\nHealthy models: {resolver.healthy_count()}/{len(models)}")


if __name__ == "__main__":
    main()
