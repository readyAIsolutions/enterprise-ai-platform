#!/usr/bin/env python3
"""
Diagnose why a model isn't showing in the Hermes `/model` picker.

Run this to verify:
1. Model is in the curated OPENROUTER_MODELS fallback list
2. Model appears in live OpenRouter /v1/models
3. Model advertises `tools` in supported_parameters (REQUIRED for picker)
4. Model is included after catalog filtering

Usage:
    python3 verify_model_in_picker.py [model-id]
    python3 verify_model_in_picker.py deepseek/deepseek-v4-flash-0731
"""

import sys
import json
import urllib.request

# Add hermes_cli to path
import hermes_cli.models as m

def check_model(model_id: str):
    print(f"\n{'='*60}")
    print(f"Diagnosing: {model_id}")
    print(f"{'='*60}\n")

    # 1. Check curated fallback list
    print("1. Checking OPENROUTER_MODELS fallback list...")
    in_fallback = False
    for mid, desc in m.OPENROUTER_MODELS:
        if mid == model_id:
            print(f"   ✓ Found in fallback: {mid} -> {desc}")
            in_fallback = True
            break
    if not in_fallback:
        print(f"   ✗ NOT in OPENROUTER_MODELS fallback list")
        print(f"   → Add to hermes_cli/models.py OPENROUTER_MODELS list")

    # 2. Clear cache and fetch live
    print("\n2. Fetching live OpenRouter catalog (clearing cache)...")
    m._openrouter_catalog_cache = None
    from hermes_cli.models import fetch_openrouter_models
    models = fetch_openrouter_models(force_refresh=True)

    in_catalog = False
    for mid, desc in models:
        if mid == model_id:
            print(f"   ✓ In filtered catalog: {mid} -> {desc}")
            in_catalog = True
            break

    if not in_catalog:
        print(f"   ✗ NOT in filtered catalog ({len(models)} models)")
        print(f"   → Model either missing from live API or lacks 'tools' support")

    # 3. Check live API directly for tool support
    print("\n3. Checking live OpenRouter API for tool support...")
    try:
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/models",
            headers={"Accept": "application/json", "User-Agent": "hermes-cli/verify"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.load(resp)
        live_by_id = {item.get("id"): item for item in payload.get("data", []) if isinstance(item, dict)}
        live_item = live_by_id.get(model_id)

        if not live_item:
            print(f"   ✗ Model NOT in live OpenRouter /v1/models")
        else:
            print(f"   ✓ Model exists in live API")
            params = live_item.get("supported_parameters", [])
            if isinstance(params, list) and "tools" in params:
                print(f"   ✓ Advertises 'tools' support: {params}")
            elif isinstance(params, list):
                print(f"   ✗ MISSING 'tools' in supported_parameters: {params}")
                print(f"   → This model CANNOT work with Hermes agent loop")
            else:
                print(f"   ? supported_parameters missing/malformed: {params}")
                print(f"   → Treated as 'unknown → allow' by picker (permissive)")
    except Exception as e:
        print(f"   ! API check failed: {e}")

    # 4. Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    if in_fallback and in_catalog:
        print("✓ Model SHOULD appear in `/model` picker")
        print("  → Run `hermes model` → select 'OpenRouter' provider → find model")
    elif in_fallback and not in_catalog:
        print("⚠ Model in fallback but NOT in filtered catalog")
        print("  → Likely missing 'tools' support on OpenRouter")
    else:
        print("✗ Model NOT in fallback list")
        print("  → Add to OPENROUTER_MODELS in hermes_cli/models.py")


if __name__ == "__main__":
    model_id = sys.argv[1] if len(sys.argv) > 1 else "deepseek/deepseek-v4-flash-0731"
    check_model(model_id)