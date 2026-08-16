#!/usr/bin/env python3
"""Clear all exhausted credential pool entries in auth.json."""

import json
from pathlib import Path

AUTH_PATH = Path.home() / ".hermes" / "auth.json"

with open(AUTH_PATH) as f:
    data = json.load(f)

cp = data.get("credential_pool", {})
cleared = 0

for pool_key, entries in list(cp.items()):
    for entry in entries:
        if entry.get("last_status") == "exhausted":
            print(f"Clearing {pool_key}:{entry['id']} (error {entry.get('last_error_code')})")
            entry["last_status"] = None
            entry["last_status_at"] = None
            entry["last_error_code"] = None
            entry["last_error_reason"] = None
            entry["last_error_message"] = None
            entry["last_error_reset_at"] = None
            cleared += 1

if cleared == 0:
    print("No exhausted pool entries found.")
else:
    with open(AUTH_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\nCleared {cleared} exhausted pool entries. Saved.")