#!/usr/bin/env python3
"""Validate learned_routing.json for invalid provider names.

Run this when the engine hangs to check for corrupted provider data.
"""
import json
from pathlib import Path

PROVIDER_DEFS = {
    "openrouter", "groq", "anthropic", "cerebras", "google", "mistral",
    "cohere", "together", "fireworks", "deepseek", "xai", "nvidia",
    "huggingface", "sambanova", "novita", "pollinations", "ollama", "gemini"
}

def validate_learned_routing(path: Path = None):
    if path is None:
        path = Path(__file__).resolve().parent.parent / "data" / "learned_routing.json"
    
    if not path.exists():
        print(f"No learned_routing.json at {path}")
        return True
    
    data = json.loads(path.read_text())
    invalid = [p for p in data.get("providers_ranked", []) if p not in PROVIDER_DEFS]
    
    if invalid:
        print(f"INVALID PROVIDERS FOUND: {invalid}")
        # Fix by filtering
        valid = [p for p in data.get("providers_ranked", []) if p in PROVIDER_DEFS]
        data["providers_ranked"] = valid
        path.write_text(json.dumps(data, indent=2))
        print(f"Fixed! Now has {len(valid)} valid providers")
        return False
    else:
        print("All providers valid")
        return True

if __name__ == "__main__":
    validate_learned_routing()