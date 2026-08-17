#!/usr/bin/env python3
"""C2 — Live Business Intelligence CLI.

Reads real telemetry from the build pipeline and prints a one-page business
snapshot (number of builds, number of artifacts, estimated tokens / cost)
across all ``data/build_sessions/<session>`` folders.

Sources of truth (no fabrication):
  * Builds   — subdirectories of ``data/build_sessions/`` whose name starts
                with ``session_``.
  * Artifacts— files inside each session folder (the ``stepNN_*.py`` outputs).
  * Tokens/cost — read from ``data/cost_meter.json`` when present
                (``{"tokens": N, "cost": M}``).  When absent and there are no
                files, we print zeros and a note.  When absent but there are
                artifacts, we report an *estimate* based on a configurable
                per-artifact token rate and clearly label it as an estimate.

If any data source is missing we print zeros for the affected metric and a
``note`` line explaining what was missing — we never invent numbers.

Usage:
    python3 scripts/live_bi.py
    python3 scripts/live_bi.py --builds-dir data/build_sessions \
        --cost-meter data/cost_meter.json --rate 800 --cost-per-1k 0.01

Exit status: 0 on success (even when data is empty/missing).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_BUILDS_DIR = REPO_ROOT / "data" / "build_sessions"
DEFAULT_COST_METER = REPO_ROOT / "data" / "cost_meter.json"
DEFAULT_RATE = 800          # estimated tokens per artifact file (estimate only)
DEFAULT_COST_PER_1K = 0.01  # USD per 1,000 estimated tokens (estimate only)


def count_sessions_and_artifacts(builds_dir: Path) -> dict[str, Any]:
    """Count build sessions and artifacts under *builds_dir*.

    Returns ``{"sessions": int, "artifacts": int, "ok": bool}``.  A session is a
    directory whose name starts with ``session_``; an artifact is any regular
    file inside a session directory (e.g. ``step01_*.py``).  The ``manifest.json``
    is metadata and is NOT counted as an artifact.
    """
    result = {"sessions": 0, "artifacts": 0, "ok": False}
    if builds_dir is None or not builds_dir.exists() or not builds_dir.is_dir():
        return result
    if not os.access(builds_dir, os.R_OK):
        return result

    result["ok"] = True
    for entry in sorted(builds_dir.iterdir()):
        if not entry.is_dir() or not entry.name.startswith("session_"):
            continue
        result["sessions"] += 1
        try:
            for f in entry.iterdir():
                if f.is_file() and f.name != "manifest.json":
                    result["artifacts"] += 1
        except OSError:
            continue
    return result


def load_cost_meter(cost_meter: Path) -> dict[str, Any]:
    """Load ``cost_meter.json`` if present.

    Returns ``{"present": bool, "tokens": int|None, "cost": float|None}``.
    ``tokens`` / ``cost`` are only set from real values when the file exists
    and parses; otherwise they are ``None`` (never fabricated).
    """
    out = {"present": False, "tokens": None, "cost": None}
    if cost_meter is None or not cost_meter.exists():
        return out
    try:
        data = json.loads(cost_meter.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return out
    if not isinstance(data, dict):
        return out
    out["present"] = True
    out["tokens"] = data.get("tokens")
    out["cost"] = data.get("cost")
    return out


def estimate_tokens(artifacts: int, rate: int) -> int:
    """Estimated tokens from the artifact count (clearly an estimate)."""
    return artifacts * rate


def render_snapshot(
    builds: dict[str, Any],
    meter: dict[str, Any],
    rate: int,
    cost_per_1k: float,
) -> str:
    """Render the one-page business snapshot as a plain-text string."""
    sessions = builds["sessions"]
    artifacts = builds["artifacts"]
    notes: list[str] = []

    if not builds["ok"]:
        notes.append("build_sessions data missing; counts reported as 0.")

    # Tokens / cost: prefer the real cost_meter when present.
    if meter["present"] and meter["tokens"] is not None:
        tokens = int(meter["tokens"])
        cost = float(meter["cost"]) if meter["cost"] is not None else tokens / 1000.0 * cost_per_1k
        est = False
    elif artifacts == 0:
        tokens = 0
        cost = 0.0
        est = False
        notes.append("no artifacts and no cost_meter.json; tokens/cost = 0.")
    else:
        tokens = estimate_tokens(artifacts, rate)
        cost = (tokens / 1000.0) * cost_per_1k
        est = True
        notes.append(
            f"no cost_meter.json; tokens/cost estimated at {rate} tokens/artifact "
            f"* ${cost_per_1k}/1k tokens."
        )

    lines = [
        "ENI Business Snapshot",
        "---------------------",
        f"Build sessions : {sessions}",
        f"Artifacts      : {artifacts}",
        f"Est tokens     : {tokens}{'  (estimated)' if est else ''}",
        f"Est cost       : ${cost:.4f}{'  (estimated)' if est else ''}",
    ]
    if notes:
        lines.append("Notes:")
        lines.extend(f"  - {n}" for n in notes)
    else:
        lines.append("Notes: all sources present; values are real telemetry.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="live_bi",
        description="C2 live business intelligence snapshot.",
    )
    parser.add_argument("--builds-dir", type=str, default=str(DEFAULT_BUILDS_DIR),
                        help="path to data/build_sessions (default: repo default)")
    parser.add_argument("--cost-meter", type=str, default=str(DEFAULT_COST_METER),
                        help="path to cost_meter.json (default: repo default)")
    parser.add_argument("--rate", type=int, default=DEFAULT_RATE,
                        help="estimated tokens per artifact when no meter present")
    parser.add_argument("--cost-per-1k", type=float, default=DEFAULT_COST_PER_1K,
                        help="USD per 1,000 estimated tokens")
    args = parser.parse_args(argv)

    builds = count_sessions_and_artifacts(Path(args.builds_dir))
    meter = load_cost_meter(Path(args.cost_meter))
    print(render_snapshot(builds, meter, args.rate, args.cost_per_1k))
    return 0


if __name__ == "__main__":
    sys.exit(main())
