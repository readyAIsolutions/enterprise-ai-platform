#!/usr/bin/env python3
"""
Diagnose stale provider_models_cache.json — the per-provider discovery cache
that feeds the Hermes `/model` TUI picker.

This is DIFFERENT from the model catalog cache (model_catalog.json).
provider_models_cache.json stores LIVE /v1/models from each provider
and is ONLY refreshed by `hermes model --refresh` (interactive terminal).

Run this to check:
1. Does the cache file exist?
2. How many models per provider?
3. Is your target model in the OpenRouter section?
4. Compare against live OpenRouter API

Usage:
    python3 diagnose_provider_cache.py [model-id]
"""

import json
import os
import sys
import urllib.request

CACHE_PATH = os.path.expanduser("~/.hermes/provider_models_cache.json")

def main():
    model_id = sys.argv[1] if len(sys.argv) > 1 else "deepseek/deepseek-v4-flash-0731"

    print(f"{'='*60}")
    print(f"Diagnosing provider_models_cache.json for: {model_id}")
    print(f"{'='*60}\n")

    # 1. Check cache file
    print("1. Checking provider_models_cache.json...")
    if not os.path.exists(CACHE_PATH):
        print(f"   ✗ Cache file NOT FOUND at {CACHE_PATH}")
        print(f"   → Run: hermes model --refresh  (in interactive terminal)")
        return

    with open(CACHE_PATH) as f:
        cache = json.load(f)

    print(f"   ✓ Cache exists: {CACHE_PATH}")
    print(f"   Providers cached: {list(cache.keys())}")

    # 2. Check OpenRouter section
    if "openrouter" not in cache:
        print("   ✗ NO 'openrouter' key in cache!")
        print("   → Run: hermes model --refresh")
        return

    or_data = cache["openrouter"]
    models = or_data.get("models", [])
    print(f"   OpenRouter models cached: {len(models)}")

    # 3. Check for target model
    found = model_id in models
    if found:
        print(f"   ✓ Target model FOUND in cache: {model_id}")
    else:
        print(f"   ✗ Target model MISSING from cache: {model_id}")
        # Show DeepSeek models present
        ds_models = [m for m in models if "deepseek" in m.lower()]
        print(f"   DeepSeek models in cache ({len(ds_models)}):")
        for m in ds_models:
            print(f"     - {m}")

    # 4. Compare with live API
    print("\n2. Checking live OpenRouter API...")
    try:
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/models",
            headers={"Accept": "application/json", "User-Agent": "hermes-cli/diagnose"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.load(resp)
        live_models = {item.get("id") for item in payload.get("data", []) if isinstance(item, dict)}
        live_ds = sorted([m for m in live_models if "deepseek" in m.lower()])
        print(f"   Live OpenRouter models: {len(live_models)}")
        print(f"   Live DeepSeek models ({len(live_ds)}):")
        for m in live_ds:
            in_cache = " ✓" if m in models else " ✗ MISSING FROM CACHE"
            print(f"     - {m}{in_cache}")

        if model_id in live_models and model_id not in models:
            print(f"\n   → MODEL EXISTS IN LIVE API BUT NOT IN CACHE")
            print(f"   → FIX: Run 'hermes model --refresh' in INTERACTIVE terminal")

    except Exception as e:
        print(f"   ! Live API check failed: {e}")

    # 5. Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    if found:
        print("✓ Model present in provider_models_cache.json")
        print("  → Should appear in `/model` picker after selecting OpenRouter provider")
    else:
        print("✗ Model MISSING from provider_models_cache.json")
        print("  → CACHE IS STALE")
        print("  → FIX: Run this in your ACTUAL terminal (interactive):")
        print("       hermes model --refresh")
        print("  → This wipes the cache and re-fetches ALL providers")


if __name__ == "__main__":
    main()