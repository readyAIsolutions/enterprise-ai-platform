#!/usr/bin/env python3
"""
SKYNET Linux Model Router — discover models and test routing on THIS box.

Usage:
    python3 model_router.py discover          # Scan all configured providers
    python3 model_router.py route "fix a bug" # Route a task to best model
    python3 model_router.py health            # Check all providers
    python3 model_router.py test              # End-to-end test
    python3 model_router.py status            # One-line status

Designed for Hermes Agent profiles with these providers:
  airllm     — local Mistral-7B @ 127.0.0.1:8913
  claude-sub — local Claude @ 127.0.0.1:8912
  groq       — llama-3.3-70b-versatile
  cerebras   — gemma-4-31b
  sambanova  — DeepSeek-V3.2
  deepinfra  — Qwen3.5-397B-A17B
  openrouter — fallback gateway
  gemini     — fallback

Requires: `hermes` CLI on PATH (for provider discovery + config).
Optional: `requests` for live HTTP health checks.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Provider configuration (mirrors ~/.hermes/config.yaml) ────────────────
PROVIDERS: Dict[str, Dict[str, Any]] = {
    "airllm": {
        "name": "airllm",
        "base_url": "http://127.0.0.1:8913/v1",
        "model": "mistralai/Mistral-7B-Instruct-v0.2",
        "context": 8192,
        "speed": "fastest",
        "best_for": ["simple", "classification", "formatting", "quick-qa"],
    },
    "claude-sub": {
        "name": "claude-sub",
        "base_url": "http://127.0.0.1:8912/v1",
        "model": "claude-sonnet-5",
        "context": 200000,
        "speed": "medium",
        "best_for": ["reasoning", "architecture", "review", "security-audit",
                     "debugging", "research"],
    },
    "groq": {
        "name": "groq",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "context": 131072,
        "speed": "fast",
        "best_for": ["creative", "writing", "brainstorming", "general"],
    },
    "cerebras": {
        "name": "cerebras",
        "base_url": "https://api.cerebras.ai/v1",
        "model": "gemma-4-31b",
        "context": 131072,
        "speed": "fast",
        "best_for": ["general", "qa", "extraction", "writing"],
    },
    "sambanova": {
        "name": "sambanova",
        "base_url": "https://api.sambanova.ai/v1",
        "model": "DeepSeek-V3.2",
        "context": 131072,
        "speed": "medium",
        "best_for": ["code", "implementation", "refactoring", "debugging",
                     "deep-reasoning", "architecture", "orchestration"],
    },
    "deepinfra": {
        "name": "deepinfra",
        "base_url": "https://api.deepinfra.com/v1/openai",
        "model": "Qwen/Qwen3.5-397B-A17B",
        "context": 131072,
        "speed": "slow",
        "best_for": ["research", "analysis", "heavy-reasoning", "review"],
    },
    "openrouter": {
        "name": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "auto",
        "context": 131072,
        "speed": "variable",
        "best_for": ["fallback", "experimental", "diverse"],
    },
    "gemini": {
        "name": "gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "model": "gemini-pro",
        "context": 131072,
        "speed": "medium",
        "best_for": ["fallback", "multimodal", "creative"],
    },
}

# ── Task-to-provider routing matrix ───────────────────────────────────────
# (task_type, complexity) → (primary_provider, fallback_chain)
ROUTING_TABLE: Dict[str, List[Tuple[str, List[str]]]] = {
    "code": [
        ("sambanova", ["deepinfra", "claude-sub", "groq"]),
    ],
    "implementation": [
        ("sambanova", ["deepinfra", "claude-sub", "groq"]),
    ],
    "refactoring": [
        ("sambanova", ["claude-sub", "deepinfra", "groq"]),
    ],
    "debugging": [
        ("sambanova", ["claude-sub", "deepinfra", "groq"]),
    ],
    "deep-reasoning": [
        ("sambanova", ["claude-sub", "deepinfra", "groq"]),
    ],
    "architecture": [
        ("claude-sub", ["sambanova", "deepinfra", "groq"]),
    ],
    "orchestration": [
        ("sambanova", ["claude-sub", "deepinfra", "groq"]),
    ],
    "review": [
        ("claude-sub", ["sambanova", "deepinfra", "groq"]),
    ],
    "security-audit": [
        ("claude-sub", ["deepinfra", "sambanova", "groq"]),
    ],
    "research": [
        ("deepinfra", ["claude-sub", "sambanova", "cerebras"]),
    ],
    "analysis": [
        ("deepinfra", ["claude-sub", "sambanova", "cerebras"]),
    ],
    "heavy-reasoning": [
        ("claude-sub", ["deepinfra", "sambanova", "openrouter"]),
    ],
    "creative": [
        ("groq", ["sambanova", "cerebras", "openrouter"]),
    ],
    "writing": [
        ("groq", ["cerebras", "sambanova", "openrouter"]),
    ],
    "brainstorming": [
        ("groq", ["cerebras", "sambanova", "openrouter"]),
    ],
    "general": [
        ("groq", ["cerebras", "sambanova", "airllm"]),
    ],
    "quick-qa": [
        ("airllm", ["cerebras", "groq"]),
    ],
    "classification": [
        ("airllm", ["cerebras", "groq"]),
    ],
    "formatting": [
        ("airllm", ["cerebras", "groq"]),
    ],
    "extraction": [
        ("cerebras", ["groq", "sambanova", "airllm"]),
    ],
    "qa": [
        ("cerebras", ["groq", "sambanova", "airllm"]),
    ],
    "fallback": [
        ("openrouter", ["gemini", "groq"]),
    ],
}


# ── Task classifier ────────────────────────────────────────────────────────
def classify_task(prompt: str) -> Tuple[str, int]:
    """
    Classify a task from prompt text. Returns (task_type, complexity 1-3).
    """
    p = prompt.lower()

    # HIGH complexity (3) — architecture, heavy reasoning, multi-step
    if any(k in p for k in ["architecture", "design system", "infrastructure",
                             "orchestrat", "swarm", "multi-agent", "pipeline",
                             "vulnerability", "harden", "penetration",
                             "full review", "comprehensive"]):
        complexity = 3
    # MEDIUM complexity (2) — code, debugging, research
    elif any(k in p for k in ["code", "function", "implement", "debug", "refactor",
                               "research", "analyze", "deep dive",
                               "theorem", "prove"]):
        complexity = 2
    else:
        complexity = 1

    # Task type detection — ordered: MOST specific first
    # Security before review (both match "audit")
    if any(k in p for k in ["security", "vulnerability", "exploit", "harden",
                              "penetration", "audit trail"]):
        return ("security-audit", complexity)
    if any(k in p for k in ["architecture", "design system", "infrastructure",
                              "component diagram", "system design"]):
        return ("architecture", complexity)
    if any(k in p for k in ["orchestrat", "swarm", "multi-agent", "parallel",
                              "fan-out", "coordinator"]):
        return ("orchestration", complexity)
    if any(k in p for k in ["debug", "traceback", "error: ", "seg fault",
                              "breakpoint", "stack trace"]):
        return ("debugging", complexity)
    if any(k in p for k in ["code", "function", "implement", "refactor",
                              "class ", "api ", "module", "library",
                              "patch", "fix bug"]):
        return ("code", complexity)
    # Analysis before research (both match "analyze", "investigate")
    if any(k in p for k in ["analyze", "examine", "probe", "methodology",
                              "deep dive", "dissect"]):
        return ("analysis", complexity)
    if any(k in p for k in ["research", "investigate", "compare approaches",
                              "survey", "literature"]):
        return ("research", complexity)
    # Review last among the heavy tasks
    if any(k in p for k in ["review code", "audit code", "check code", "verify",
                              "validate", "lint"]):
        return ("review", complexity)
    if any(k in p for k in ["creative", "brainstorm", "ideate", "generate ideas",
                              "innovative", "novel"]):
        return ("creative", complexity)
    if any(k in p for k in ["write", "draft", "compose", "article", "blog",
                              "report", "essay", "story"]):
        return ("writing", complexity)
    if any(k in p for k in ["extract", "parse", "scrape", "pull data"]):
        return ("extraction", complexity)
    if any(k in p for k in ["classify", "category", "label", "sort",
                              "categorize"]):
        return ("classification", complexity)
    if any(k in p for k in ["format", "convert", "transform", "restyle"]):
        return ("formatting", complexity)
    # Quick math/trivia → qa
    if any(k in p for k in ["what is", "how many", "when did", "where is",
                              "who is", "what are", "define ", "meaning of"]):
        return ("qa", complexity)

    return ("general", complexity)


# ── Router ─────────────────────────────────────────────────────────────────
class ModelRouter:
    """Route tasks to optimal model/provider combos with fallback chains."""

    def __init__(self):
        self.providers = PROVIDERS
        self.routing = ROUTING_TABLE
        self._unhealthy: Dict[str, float] = {}  # provider → cooldown_until
        self._stats: Dict[str, int] = {"routes": 0, "fallbacks": 0}

    def route(self, task: str) -> Dict[str, Any]:
        """
        Route a task. Returns:
          {primary: {provider, model, base_url}, fallbacks: [...], task_type, complexity}
        """
        task_type, complexity = classify_task(task)

        # Look up routing
        route_candidates = self.routing.get(task_type)
        if route_candidates is None:
            route_candidates = self.routing.get("general", [("groq", ["cerebras", "sambanova"])])

        primary_provider, fallback_providers = route_candidates[0]
        fallback_chain = fallback_providers[:]

        # If primary is unhealthy, shift to first healthy fallback
        now = time.time()
        if primary_provider in self._unhealthy and now < self._unhealthy[primary_provider]:
            if fallback_chain:
                primary_provider = fallback_chain.pop(0)
                self._stats["fallbacks"] += 1

        primary_info = self.providers.get(primary_provider, self.providers["openrouter"])

        result = {
            "task": task[:120],
            "task_type": task_type,
            "complexity": complexity,
            "primary": {
                "provider": primary_provider,
                "model": primary_info["model"],
                "base_url": primary_info["base_url"],
                "speed": primary_info["speed"],
            },
            "fallbacks": [
                {
                    "provider": p,
                    "model": self.providers[p]["model"],
                    "speed": self.providers[p]["speed"],
                }
                for p in fallback_chain[:3]
                if p in self.providers
            ],
        }
        self._stats["routes"] += 1
        return result

    def mark_unhealthy(self, provider: str, cooldown_seconds: int = 300) -> None:
        """Mark a provider as unhealthy for cooldown_seconds."""
        self._unhealthy[provider] = time.time() + cooldown_seconds

    def mark_healthy(self, provider: str) -> None:
        """Clear unhealthy status."""
        self._unhealthy.pop(provider, None)

    def stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "unhealthy": {
                p: int(until - time.time())
                for p, until in self._unhealthy.items()
                if time.time() < until
            },
        }


# ── Health checks ──────────────────────────────────────────────────────────
def check_provider_health(provider_name: str) -> Dict[str, Any]:
    """Check if a provider's endpoint is reachable."""
    info = PROVIDERS.get(provider_name, {})
    base_url = info.get("base_url", "")
    result = {
        "provider": provider_name,
        "model": info.get("model", "unknown"),
        "reachable": False,
        "latency_ms": None,
        "error": None,
    }

    if not base_url:
        result["error"] = "no base_url configured"
        return result

    try:
        import urllib.request
        import urllib.error

        t0 = time.time()
        # Try the models endpoint (OpenAI-compatible)
        check_url = base_url.rstrip("/") + "/models"
        req = urllib.request.Request(check_url)
        # Add auth header if we can read it from config
        try:
            output = subprocess.check_output(
                ["hermes", "config", "get", f"providers.{provider_name}.api_key"],
                stderr=subprocess.DEVNULL, text=True, timeout=5
            ).strip()
            if output:
                req.add_header("Authorization", f"Bearer {output}")
        except Exception:
            pass  # No API key accessible, try without

        resp = urllib.request.urlopen(req, timeout=5)
        result["reachable"] = resp.status == 200
        result["latency_ms"] = int((time.time() - t0) * 1000)
        if result["reachable"]:
            try:
                data = json.loads(resp.read().decode())
                result["model_count"] = len(data.get("data", []))
            except Exception:
                result["model_count"] = "unknown"
    except urllib.error.HTTPError as e:
        result["error"] = f"HTTP {e.code}"
    except urllib.error.URLError as e:
        result["error"] = str(e.reason)
    except Exception as e:
        result["error"] = str(e)[:200]

    return result


def check_all_providers() -> List[Dict[str, Any]]:
    """Check health of all configured providers."""
    results = []
    for name in PROVIDERS:
        print(f"  Checking {name:12s} ... ", end="", flush=True)
        r = check_provider_health(name)
        status = "✓" if r["reachable"] else "✗"
        latency = f" ({r['latency_ms']}ms)" if r["latency_ms"] else ""
        error = f" — {r['error']}" if r.get("error") else ""
        print(f"{status}{latency}{error}")
        results.append(r)
    return results


# ── Discover models ────────────────────────────────────────────────────────
def discover_hermes_models() -> Dict[str, Any]:
    """Discover available models via hermes CLI."""
    result = {
        "configured_providers": list(PROVIDERS.keys()),
        "hermes_available": False,
        "providers_from_hermes": [],
        "model_aliases": {},
        "default_model": None,
    }
    try:
        output = subprocess.check_output(
            ["hermes", "config", "get", "providers"],
            stderr=subprocess.DEVNULL, text=True, timeout=5
        )
        result["providers_from_hermes"] = [
            p.strip() for p in output.split()
            if p.strip() and not p.startswith("{") and not p.startswith("[")
        ]
        result["hermes_available"] = True
    except Exception:
        pass

    try:
        output = subprocess.check_output(
            ["hermes", "config", "get", "model.default"],
            stderr=subprocess.DEVNULL, text=True, timeout=5
        ).strip()
        if output:
            result["default_model"] = output
    except Exception:
        pass

    return result


# ── Main CLI ───────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "status":
        h = discover_hermes_models()
        router = ModelRouter()
        stats = router.stats()
        print(f"SKYNET Router: {len(PROVIDERS)} providers | "
              f"{stats['routes']} routes | {stats['fallbacks']} fallbacks")
        print(f"  Hermes available: {h['hermes_available']}")
        print(f"  Default model: {h['default_model'] or 'N/A'}")
        unhealthy = stats.get("unhealthy", {})
        if unhealthy:
            for p, ttl in unhealthy.items():
                print(f"  Unhealthy: {p} (cooldown: {ttl}s)")

    elif cmd == "discover":
        print("=== SKYNET Model Discovery ===\n")
        print("Configured providers:")
        for name, info in PROVIDERS.items():
            print(f"  {name:12s} → {info['model']} @ {info['base_url']}")

        print("\nHermes integration:")
        h = discover_hermes_models()
        print(f"  Hermes CLI: {'available' if h['hermes_available'] else 'NOT FOUND'}")
        print(f"  Providers from Hermes: {h['providers_from_hermes'] or 'N/A'}")
        print(f"  Default model: {h['default_model'] or 'N/A'}")

        print("\nSKYNET package check:")
        try:
            from skynet.activate import status as sky_status
            s = sky_status()
            print(f"  SKYNET root: {s.get('skynet_root', 'N/A')}")
            print(f"  Modules: {s.get('modules_ok', 0)}/{s.get('modules_total', 0)}")
            print(f"  Tor available: {s.get('tor_available', False)}")
        except ImportError:
            print("  SKYNET package: NOT IMPORTABLE (install or set PYTHONPATH)")
        except Exception as e:
            print(f"  SKYNET package: ERROR ({e})")

    elif cmd == "route":
        if len(sys.argv) < 3:
            print("Usage: model_router.py route <task description>")
            sys.exit(1)
        task = " ".join(sys.argv[2:])
        router = ModelRouter()
        result = router.route(task)
        print(f"\nTask: {result['task']}...")
        print(f"Classified as: {result['task_type']} (complexity {result['complexity']})")
        print(f"\n→ PRIMARY: {result['primary']['provider']} / {result['primary']['model']}")
        print(f"  Speed: {result['primary']['speed']}")
        print(f"  URL: {result['primary']['base_url']}")
        print(f"\nFallback chain:")
        for i, fb in enumerate(result['fallbacks'], 1):
            print(f"  {i}. {fb['provider']} / {fb['model']} ({fb['speed']})")

    elif cmd == "health":
        print("=== Provider Health Check ===\n")
        results = check_all_providers()
        ok = sum(1 for r in results if r["reachable"])
        total = len(results)
        print(f"\n{ok}/{total} providers reachable")

    elif cmd == "test":
        # Auto-add SKYNET to path if found
        _sky_root = os.environ.get("SKYNET_ROOT", "")
        if not _sky_root or not os.path.isdir(_sky_root):
            _sky_root = os.path.expanduser("~/Desktop/SKYNET")
        # Also try standard locations
        if not os.path.isdir(_sky_root):
            for alt in [
                os.path.expanduser("~/Desktop/SKYNET"),
                "/home/hunter/Desktop/SKYNET",
            ]:
                if os.path.isdir(alt):
                    _sky_root = alt
                    break
        if os.path.isdir(_sky_root) and _sky_root not in sys.path:
            sys.path.insert(0, _sky_root)

        print("=== SKYNET Router Full Test ===\n")

        # 1. Import check
        print("1. SKYNET package import:")
        try:
            import skynet
            print(f"   ✓ skynet v{skynet.__version__} at {skynet.__file__}")
        except Exception as e:
            print(f"   ✗ {e}")

        # 2. Module activation
        print("\n2. Module activation:")
        try:
            from skynet.activate import activate
            report = activate(verbose=False)
            print(f"   ✓ {report['ok']}/{report['total']} modules ({report['health']})")
        except Exception as e:
            print(f"   ✗ {e}")

        # 3. Router test
        print("\n3. Task routing test:")
        router = ModelRouter()
        test_tasks = [
            ("write a function to sort a list", "code"),
            ("design a microservice architecture", "architecture"),
            ("write a creative story about dragons", "creative"),
            ("debug this segmentation fault", "debugging"),
            ("what is 2+2?", "qa"),
            ("analyze this research paper's methodology", "analysis"),
            ("review this security audit report", "security-audit"),
        ]
        for task, expected_type in test_tasks:
            result = router.route(task)
            match = "✓" if result["task_type"] == expected_type else f"✗ (got {result['task_type']})"
            print(f"   {match} '{task[:50]}...' → {result['primary']['provider']}")

        # 4. Provider check (quick)
        print("\n4. Provider network check (local only):")
        for name in ["airllm", "claude-sub"]:
            r = check_provider_health(name)
            status = "✓" if r["reachable"] else f"✗ ({r.get('error', 'unknown')})"
            print(f"   {status} {name}")

        print("\n=== Test complete ===")


if __name__ == "__main__":
    main()