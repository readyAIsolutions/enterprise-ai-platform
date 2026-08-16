#!/usr/bin/env python3
"""
ENI Swarm Discovery — Cross-Project Intelligence + Token Economics
===================================================================
Two subsystems that make the swarm self-aware:

1. PatternBroadcaster — Minis share build patterns across projects via FIFO
   When STOCKBOT_B01 discovers a database pattern, DEMIURGE_B05 can learn it.

2. TokenTracker — Track token usage, compression savings, and API costs
   across all minis. Provides per-mini and aggregate metrics.
"""
from __future__ import annotations

import json
import time
import threading
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from collections import defaultdict

# ─── Paths ──────────────────────────────────────────────────────────────────
CACHE_DIR = Path.home() / ".cache" / "eni_swarm"
PATTERNS_FILE = CACHE_DIR / "shared_patterns.json"
TOKEN_FILE = CACHE_DIR / "token_economics.json"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ─── PatternBroadcaster ─────────────────────────────────────────────────────

@dataclass
class SharedPattern:
    """A reusable pattern discovered by a mini builder."""
    name: str
    category: str  # "sql", "api", "test", "docker", "config", "strategy", etc.
    description: str
    snippet: str   # The reusable code/template
    source_mini: str
    source_project: str
    tags: List[str] = field(default_factory=list)
    uses: int = 0
    created: float = field(default_factory=time.time)
    uuid: str = ""

    def __post_init__(self):
        if not self.uuid:
            import hashlib
            self.uuid = hashlib.sha256(
                f"{self.source_mini}:{self.name}:{self.category}".encode()
            ).hexdigest()[:12]


class PatternBroadcaster:
    """
    Cross-project pattern sharing system.

    When a mini discovers a useful pattern (SQL schema, API endpoint,
    Docker config, test fixture, etc.), it can broadcast it to the
    swarm. Other minis working on different projects can discover
    and reuse these patterns.
    """

    def __init__(self):
        self.patterns: Dict[str, SharedPattern] = {}
        self._lock = threading.RLock()
        self._load()

    def _load(self):
        if PATTERNS_FILE.exists():
            try:
                data = json.loads(PATTERNS_FILE.read_text())
                for uuid, pdata in data.items():
                    self.patterns[uuid] = SharedPattern(**pdata)
            except Exception:
                pass

    def save(self):
        with self._lock:
            data = {uuid: {
                "name": p.name, "category": p.category,
                "description": p.description, "snippet": p.snippet,
                "source_mini": p.source_mini, "source_project": p.source_project,
                "tags": p.tags, "uses": p.uses, "created": p.created,
                "uuid": p.uuid,
            } for uuid, p in self.patterns.items()}
            PATTERNS_FILE.write_text(json.dumps(data, indent=2))

    def broadcast(self, mini_name: str, project: str, name: str,
                  category: str, description: str, snippet: str,
                  tags: Optional[List[str]] = None) -> SharedPattern:
        """Broadcast a new pattern to the swarm."""
        pattern = SharedPattern(
            name=name,
            category=category,
            description=description,
            snippet=snippet,
            source_mini=mini_name,
            source_project=project,
            tags=tags or [],
        )
        with self._lock:
            self.patterns[pattern.uuid] = pattern
            self.save()
        return pattern

    def discover(self, categories: Optional[List[str]] = None,
                 mini_name: Optional[str] = None) -> List[SharedPattern]:
        """
        Discover patterns from other projects.

        Args:
            categories: Filter by categories (e.g., ["sql", "api"])
            mini_name: Exclude patterns from this mini (avoid self-discovery)

        Returns:
            List of matching patterns, sorted by uses descending
        """
        with self._lock:
            results = []
            for p in self.patterns.values():
                if mini_name and p.source_mini == mini_name:
                    continue
                if categories and p.category not in categories:
                    continue
                results.append(p)
            # Sort by uses
            results.sort(key=lambda p: -p.uses)
            return results

    def use_pattern(self, uuid: str):
        """Mark a pattern as used — increments usage counter."""
        with self._lock:
            if uuid in self.patterns:
                self.patterns[uuid].uses += 1
                self.save()

    def stats(self) -> Dict[str, Any]:
        """Get pattern statistics."""
        with self._lock:
            by_category = defaultdict(int)
            by_project = defaultdict(int)
            for p in self.patterns.values():
                by_category[p.category] += 1
                by_project[p.source_project] += 1

            return {
                "total_patterns": len(self.patterns),
                "total_uses": sum(p.uses for p in self.patterns.values()),
                "by_category": dict(by_category),
                "by_project": dict(by_project),
                "recent": [
                    {"name": p.name, "category": p.category, "source": p.source_mini}
                    for p in sorted(self.patterns.values(),
                                   key=lambda p: -p.created)[:5]
                ],
            }


# ─── TokenTracker ───────────────────────────────────────────────────────────

@dataclass
class TokenEntry:
    """Token usage record for a single mini interaction."""
    mini_name: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    success: bool
    timestamp: float = field(default_factory=time.time)


class TokenTracker:
    """
    Tracks token usage, compression savings, and API costs.

    Maintains per-mini and aggregate metrics. Estimates costs
    based on OpenRouter's pricing model.
    """

    # Approximate pricing per 1M tokens (USD) — OpenRouter free tier estimates
    PRICING = {
        "default": {"prompt": 0.0, "completion": 0.0},  # free models
        "deepseek/deepseek-chat": {"prompt": 0.14, "completion": 0.28},
        "deepseek/deepseek-v4-pro": {"prompt": 0.14, "completion": 0.28},
        "anthropic/claude-sonnet-4": {"prompt": 3.0, "completion": 15.0},
        "openai/gpt-4o": {"prompt": 2.5, "completion": 10.0},
        "openai/gpt-4": {"prompt": 30.0, "completion": 60.0},
    }

    def __init__(self):
        self.entries: List[TokenEntry] = []
        self._lock = threading.RLock()
        self._session_start = time.time()
        self._load()

    def _load(self):
        if TOKEN_FILE.exists():
            try:
                data = json.loads(TOKEN_FILE.read_text())
                self.entries = [TokenEntry(**e) for e in data.get("entries", [])]
                self._session_start = data.get("session_start", time.time())
            except Exception:
                pass

    def save(self):
        with self._lock:
            data = {
                "session_start": self._session_start,
                "entries": [{
                    "mini_name": e.mini_name, "model": e.model,
                    "prompt_tokens": e.prompt_tokens,
                    "completion_tokens": e.completion_tokens,
                    "latency_ms": e.latency_ms, "success": e.success,
                    "timestamp": e.timestamp,
                } for e in self.entries[-1000:]],  # Keep last 1000 entries
            }
            TOKEN_FILE.write_text(json.dumps(data, indent=2))

    def record(self, mini_name: str, model: str, prompt_tokens: int,
               completion_tokens: int, latency_ms: int, success: bool = True):
        """Record a token usage event."""
        with self._lock:
            entry = TokenEntry(
                mini_name=mini_name,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency_ms,
                success=success,
            )
            self.entries.append(entry)
            if len(self.entries) > 1000:
                self.entries = self.entries[-1000:]
            self.save()

    def _estimate_cost(self, model: str, prompt_tokens: int,
                       completion_tokens: int) -> float:
        """Estimate USD cost for token usage."""
        pricing = self.PRICING.get(model, self.PRICING["default"])
        prompt_cost = (prompt_tokens / 1_000_000) * pricing["prompt"]
        completion_cost = (completion_tokens / 1_000_000) * pricing["completion"]
        return round(prompt_cost + completion_cost, 6)

    def per_mini_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get per-mini token stats."""
        with self._lock:
            stats = defaultdict(lambda: {
                "calls": 0, "successes": 0, "failures": 0,
                "total_prompt_tokens": 0, "total_completion_tokens": 0,
                "total_latency_ms": 0, "total_cost": 0.0,
                "models_used": set(),
            })
            for e in self.entries:
                s = stats[e.mini_name]
                s["calls"] += 1
                if e.success:
                    s["successes"] += 1
                else:
                    s["failures"] += 1
                s["total_prompt_tokens"] += e.prompt_tokens
                s["total_completion_tokens"] += e.completion_tokens
                s["total_latency_ms"] += e.latency_ms
                s["total_cost"] += self._estimate_cost(
                    e.model, e.prompt_tokens, e.completion_tokens
                )
                s["models_used"].add(e.model)

            for name in stats:
                s = stats[name]
                s["models_used"] = list(s["models_used"])
                s["success_rate"] = round(
                    s["successes"] / max(s["calls"], 1) * 100, 1
                )
                s["avg_latency_ms"] = round(
                    s["total_latency_ms"] / max(s["calls"], 1), 1
                )
                s["total_cost"] = round(s["total_cost"], 6)

            return dict(stats)

    def aggregate_stats(self) -> Dict[str, Any]:
        """Get aggregate token statistics."""
        with self._lock:
            total_calls = len(self.entries)
            total_prompt = sum(e.prompt_tokens for e in self.entries)
            total_completion = sum(e.completion_tokens for e in self.entries)
            total_cost = sum(
                self._estimate_cost(e.model, e.prompt_tokens, e.completion_tokens)
                for e in self.entries
            )
            successes = sum(1 for e in self.entries if e.success)
            failures = total_calls - successes
            avg_latency = (
                sum(e.latency_ms for e in self.entries) / max(total_calls, 1)
            )

            # Compression savings estimate
            # Assuming glyph compression saves ~70% of prompt tokens
            estimated_savings = total_prompt * 0.70
            estimated_cost_saved = (estimated_savings / 1_000_000) * 0.14  # at cheapest rate

            uptime = time.time() - self._session_start

            return {
                "total_calls": total_calls,
                "successes": successes,
                "failures": failures,
                "success_rate": round(successes / max(total_calls, 1) * 100, 1),
                "total_prompt_tokens": total_prompt,
                "total_completion_tokens": total_completion,
                "total_tokens": total_prompt + total_completion,
                "total_cost_usd": round(total_cost, 6),
                "avg_latency_ms": round(avg_latency, 1),
                "uptime_seconds": int(uptime),
                "estimated_token_savings": int(estimated_savings),
                "estimated_cost_saved": round(estimated_cost_saved, 6),
                "calls_per_hour": round(total_calls / max(uptime / 3600, 0.01), 1),
                "tokens_per_hour": int((total_prompt + total_completion) / max(uptime / 3600, 0.01)),
            }

    def reset(self):
        """Reset all tracking."""
        with self._lock:
            self.entries = []
            self._session_start = time.time()
            self.save()


# ─── CLI ─────────────────────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description="ENI Swarm Discovery & Token Economics")
    sub = parser.add_subparsers(dest="cmd")

    # Pattern commands
    pat = sub.add_parser("pattern", help="Pattern broadcasting")
    pat_sub = pat.add_subparsers(dest="subcmd")
    pat_list = pat_sub.add_parser("list", help="List shared patterns")
    pat_list.add_argument("--category", type=str, help="Filter by category")
    pat_stats = pat_sub.add_parser("stats", help="Pattern statistics")
    pat_add = pat_sub.add_parser("add", help="Broadcast a pattern")
    pat_add.add_argument("--mini", required=True, help="Source mini name")
    pat_add.add_argument("--project", required=True, help="Source project")
    pat_add.add_argument("--name", required=True, help="Pattern name")
    pat_add.add_argument("--category", required=True, help="Pattern category")
    pat_add.add_argument("--description", required=True, help="Description")
    pat_add.add_argument("--snippet", required=True, help="Code snippet")

    # Token commands
    tok = sub.add_parser("token", help="Token economics")
    tok_sub = tok.add_subparsers(dest="subcmd")
    tok_sum = tok_sub.add_parser("summary", help="Aggregate token stats")
    tok_per = tok_sub.add_parser("per-mini", help="Per-mini token stats")
    tok_res = tok_sub.add_parser("reset", help="Reset tracking")

    args = parser.parse_args()

    if args.cmd == "pattern":
        bc = PatternBroadcaster()
        if args.subcmd == "list":
            patterns = bc.discover(
                categories=[args.category] if args.category else None
            )
            for p in patterns[:20]:
                print(f"  [{p.category}] {p.name} from {p.source_mini} ({p.source_project})")
                print(f"    {p.description[:80]}")
        elif args.subcmd == "stats":
            stats = bc.stats()
            print(json.dumps(stats, indent=2))
        elif args.subcmd == "add":
            pattern = bc.broadcast(
                args.mini, args.project, args.name, args.category,
                args.description, args.snippet
            )
            print(f"Broadcast: {pattern.uuid}")
        else:
            bc = PatternBroadcaster()
            stats = bc.stats()
            print(f"Shared patterns: {stats['total_patterns']} ({stats['total_uses']} total uses)")

    elif args.cmd == "token":
        tt = TokenTracker()
        if args.subcmd == "summary":
            stats = tt.aggregate_stats()
            print(json.dumps(stats, indent=2))
        elif args.subcmd == "per-mini":
            stats = tt.per_mini_stats()
            print(json.dumps(stats, indent=2))
        elif args.subcmd == "reset":
            tt.reset()
            print("Token tracking reset.")
        else:
            stats = tt.aggregate_stats()
            print(f"Total calls: {stats['total_calls']}")
            print(f"Total tokens: {stats['total_tokens']:,}")
            print(f"Estimated cost: ${stats['total_cost_usd']}")
            print(f"Estimated savings: {stats['estimated_token_savings']:,} tokens (${stats['estimated_cost_saved']})")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
