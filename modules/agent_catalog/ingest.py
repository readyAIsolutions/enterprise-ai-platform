"""Generate the canonical unified agent catalog from both source repos.

Fuses:
  - Source "codex"  : ~/Desktop/awesome-codex-subagents-main  (Codex .toml subagents)
  - Source "agency" : ~/Desktop/agency-agents-main           (Markdown division agents)

Output: canonical merged JSON (modules/agent_catalog/data/agent_catalog.json)
plus a per-agent detail directory (modules/agent_catalog/data/agents/<slug>.json).

The canonical JSON is committed to the repo so the module works even when the
source repos are absent; `refresh` re-ingests from the live sources.
"""
from __future__ import annotations

import glob
import json
import os
import re
import tomllib
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None


# --------------------------------------------------------------------------- #
# Parsers
# --------------------------------------------------------------------------- #
def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "agent"


def parse_codex_toml(path: str, category: str) -> dict[str, Any]:
    text = open(path, encoding="utf-8").read()
    try:
        data = tomllib.loads(text)
    except Exception:
        data = {}
    slug = os.path.splitext(os.path.basename(path))[0]
    name = data.get("name") or slug
    instructions = (
        data.get("developer_instructions")
        or (data.get("instructions") or {}).get("text", "")
        or ""
    ).strip()
    return {
        "slug": _slugify(name),
        "name": str(name),
        "description": (data.get("description") or "").strip(),
        "model": data.get("model"),
        "model_reasoning_effort": data.get("model_reasoning_effort"),
        "sandbox_mode": data.get("sandbox_mode"),
        "source": "codex",
        "categories": [category],
        "instructions": instructions,
        "emoji": None,
        "color": None,
        "vibe": None,
        "origin_path": path,
    }


def parse_agency_md(path: str, category: str) -> dict[str, Any]:
    text = open(path, encoding="utf-8").read()
    fm: dict[str, Any] = {}
    body = text
    if text.startswith("---"):
        m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
        if m and yaml is not None:
            try:
                fm = yaml.safe_load(m.group(1)) or {}
            except Exception:
                fm = {}
            body = m.group(2)
    slug = os.path.splitext(os.path.basename(path))[0]
    name = fm.get("name") or slug
    return {
        "slug": _slugify(slug),
        "name": str(name),
        "description": (fm.get("description") or "").strip(),
        "model": None,
        "model_reasoning_effort": None,
        "sandbox_mode": None,
        "source": "agency",
        "categories": [category],
        "instructions": body.strip(),
        "emoji": fm.get("emoji"),
        "color": fm.get("color"),
        "vibe": fm.get("vibe"),
        "origin_path": path,
    }


# --------------------------------------------------------------------------- #
# Canopy builder
# --------------------------------------------------------------------------- #
def discover_codex(root: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not os.path.isdir(root):
        return out
    for cat in sorted(os.listdir(root)):
        cdir = os.path.join(root, cat)
        if not os.path.isdir(cdir):
            continue
        for f in sorted(glob.glob(os.path.join(cdir, "*.toml"))):
            out.append(parse_codex_toml(f, cat))
    return out


def discover_agency(root: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not os.path.isdir(root):
        return out
    for cat in sorted(os.listdir(root)):
        adir = os.path.join(root, cat)
        if not os.path.isdir(adir) or cat.startswith(".") or cat in ("scripts", ".github"):
            continue
        for f in sorted(glob.glob(os.path.join(adir, "*.md"))):
            base = os.path.basename(f)
            if base.lower() in ("readme.md", "readme_zh-cn.md"):
                continue
            out.append(parse_agency_md(f, cat))
    return out


def build_canonical(codex_root: str, agency_root: str) -> dict[str, Any]:
    codex = discover_codex(codex_root)
    agency = discover_agency(agency_root)
    all_agents = codex + agency

    # Merge by slug: later sources win for scalar fields, categories & sources union.
    merged: dict[str, dict[str, Any]] = {}
    for a in all_agents:
        slug = a["slug"]
        cur = merged.get(slug)
        if cur is None:
            merged[slug] = dict(a)
            merged[slug]["categories"] = list(a["categories"])
            merged[slug]["sources"] = [a["source"]]
            continue
        # union sources + categories
        for s in a["sources"] if "sources" in a else [a["source"]]:
            if s not in cur["sources"]:
                cur["sources"].append(s)
        for c in a["categories"]:
            if c not in cur["categories"]:
                cur["categories"].append(c)
        # prefer richer instructions
        if len(a["instructions"]) > len(cur["instructions"]):
            cur["instructions"] = a["instructions"]
        if not cur["description"] and a["description"]:
            cur["description"] = a["description"]
        if cur["name"].startswith(cur["slug"]) is not False:
            pass

    return {
        "schema_version": "1.0.0",
        "generated_from": {
            "codex": codex_root,
            "agency": agency_root,
        },
        "stats": {
            "codex_raw": len(codex),
            "agency_raw": len(agency),
            "unique_agents": len(merged),
            "merged_shared_slugs": len(codex) + len(agency) - len(merged),
        },
        "agents": list(merged.values()),
    }


def main() -> None:  # pragma: no cover
    here = os.path.dirname(os.path.abspath(__file__))
    # data dir lives at <repo>/modules/agent_catalog/data
    data_dir = os.path.join(here, "data")
    os.makedirs(data_dir, exist_ok=True)
    agents_dir = os.path.join(data_dir, "agents")
    os.makedirs(agents_dir, exist_ok=True)

    codex_root = os.path.expanduser("~/Desktop/awesome-codex-subagents-main/categories")
    agency_root = os.path.expanduser("~/Desktop/agency-agents-main")

    canon = build_canonical(codex_root, agency_root)
    json_path = os.path.join(data_dir, "agent_catalog.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(canon, fh, indent=2, ensure_ascii=False)

    # per-agent detail
    for a in canon["agents"]:
        with open(os.path.join(agents_dir, f"{a['slug']}.json"), "w", encoding="utf-8") as fh:
            json.dump(a, fh, indent=2, ensure_ascii=False)

    print(f"Wrote {json_path}")
    print(f"  unique agents : {canon['stats']['unique_agents']}")
    print(f"  codex raw     : {canon['stats']['codex_raw']}")
    print(f"  agency raw    : {canon['stats']['agency_raw']}")
    print(f"  merged        : {canon['stats']['merged_shared_slugs']} (shared slugs collapsed)")


if __name__ == "__main__":
    main()
