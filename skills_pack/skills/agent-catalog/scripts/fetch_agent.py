#!/usr/bin/env python3
"""Fetch a specialist agent's full instructions from the ENI Agent Catalog.

Usage:
    python3 fetch_agent.py <slug-or-search>
    python3 fetch_agent.py --list            # list categories + counts
    python3 fetch_agent.py --search <query> [--source codex|agency] [--limit N]
    python3 fetch_agent.py --overview        # total / sources / categories

Reads the committed canonical catalog either via the enterprise module (when
PYTHONPATH points at the repo) or directly from the canonical JSON.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

CANON = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "agent_catalog.json"
)
CANON = os.path.normpath(CANON)

# Single source of truth: the enterprise repo's committed canonical JSON.
_ENTERPRISE_CANON = os.path.expanduser(
    "~/Desktop/Enterprise Builder/enterprise/modules/agent_catalog/data/agent_catalog.json"
)


def _load():
    for path in (CANON, _ENTERPRISE_CANON):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)["agents"]
    raise FileNotFoundError(
        f"canonical catalog not found at {CANON} nor {_ENTERPRISE_CANON}"
    )


def _find(agents, term):
    term = term.lower()
    exact = [a for a in agents if a["slug"].lower() == term]
    if exact:
        return exact[0]
    for a in agents:
        if term in a["slug"].lower() or term in a["name"].lower():
            return a
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description="ENI Agent Catalog CLI")
    ap.add_argument("slug", nargs="?", help="agent slug or name fragment")
    ap.add_argument("--list", action="store_true", help="list categories + counts")
    ap.add_argument("--search", help="faceted textual search")
    ap.add_argument("--source", help="filter by source: codex | agency")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--overview", action="store_true")
    args = ap.parse_args()

    agents = _load()

    if args.overview:
        srcs = {s for a in agents for s in (a.get("sources") or [])}
        print(f"total agents: {len(agents)}")
        print(f"sources: {', '.join(sorted(srcs))}")
        cats = []
        for a in agents:
            cats += a.get("categories") or []
        from collections import Counter

        print("\ncategories:")
        for c, n in Counter(cats).most_common():
            print(f"  {c}: {n}")
        return

    if args.list:
        from collections import Counter

        cats = Counter()
        for a in agents:
            cats.update(a.get("categories") or [])
        for c, n in sorted(cats.items()):
            print(f"{c}: {n}")
        return

    if args.search:
        q = args.search.lower()
        out = []
        for a in agents:
            srcs = a.get("sources") or []
            if args.source and args.source not in srcs:
                continue
            blob = (
                " ".join([a.get("slug", ""), a.get("name", ""), a.get("description", "")])
                .lower()
            ) + " " + " ".join(a.get("categories") or []).lower()
            if q in blob:
                out.append(a)
            if len(out) >= args.limit:
                break
        for a in out:
            srcs = ",".join(a.get("sources") or [])
            print(f"[{srcs}] {a['slug']} — {(a.get('description') or '')[:100]}")
        print(f"\n({len(out)} matches)")
        return

    if not args.slug:
        ap.print_help()
        return

    a = _find(agents, args.slug)
    if a is None:
        print(f"No agent matched '{args.slug}'. Try --search <query>.")
        sys.exit(1)

    print(f"# {a['name']}  (slug: {a['slug']})")
    print(f"sources    : {', '.join(a.get('sources') or [])}")
    print(f"categories : {', '.join(a.get('categories') or [])}")
    if a.get("model"):
        print(f"model      : {a['model']}")
    if a.get("sandbox_mode"):
        print(f"sandbox    : {a['sandbox_mode']}")
    if a.get("vibe"):
        print(f"vibe       : {a['vibe']}")
    if a.get("emoji"):
        print(f"emoji      : {a['emoji']}")
    print("\n" + "=" * 60)
    print(a.get("instructions", "(no instructions)"))
    print("=" * 60)


if __name__ == "__main__":
    main()
