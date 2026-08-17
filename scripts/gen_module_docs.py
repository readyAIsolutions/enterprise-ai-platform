#!/usr/bin/env python3
"""Generate one doc page per module + a grouped reference index, and emit a
master-README Modules insert that covers EVERY module (so docs stay current as
the build loop adds modules).

Outputs (all grounded from real module metadata):
  enterprise/docs/modules/<name>.md          one page per module
  enterprise/docs/MODULES_REFERENCE.md       grouped full index (with links)
  enterprise/README_MODULES_INSERT.md        ready-to-splice full module table
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

REPO = Path("/home/hunter/Desktop/Enterprise Builder/enterprise")
PARENT = Path("/home/hunter/Desktop/Enterprise Builder")
DOCS = REPO / "docs" / "modules"


def _import(module: str):
    sys.path.insert(0, str(PARENT))
    return importlib.import_module(f"enterprise.modules.{module}.__init__")


def _meta(module: str) -> dict:
    try:
        mod = _import(module)
    except Exception:
        return {"version": "?", "doc": "", "facades": []}
    doc = (mod.__doc__ or "").strip()
    fac = []
    try:
        cls = next((c for c in dir(mod)
                    if isinstance(getattr(mod, c), type)
                    and getattr(mod, c).__module__.endswith("__init__")
                    and c.endswith("Module")), None)
        if cls:
            fac = sorted(m for m in dir(getattr(mod, cls))
                         if not m.startswith("_") and m not in
                         ("config", "name", "status", "module_id", "version"))
    except Exception:
        pass
    return {"version": getattr(mod, "__version__", "?"), "doc": doc, "facades": fac[:30]}


def _page(name: str, cat: str, prio: int, purpose: str, version: str, meta: dict) -> str:
    fac = ", ".join(meta["facades"]) if meta["facades"] else "(module-level API)"
    doc = meta["doc"] or purpose
    return (
        f"# Module: `{name}`\n\n"
        f"- Category: {cat} · priority {prio}\n"
        f"- Version: {version}\n"
        f"- Purpose: {purpose}\n"
        f"- Skill: `eni-module-{name}` (ICM stages) in skills_pack/skills/eni-modules/{name}/\n\n"
        f"## What it does\n{doc}\n\n"
        f"## Key API (facade methods)\n{fac}\n\n"
        f"## Tests\n```bash\npython3 -m pytest modules/{name}/tests -q\n```\n\n"
        f"## Import\n```python\nfrom enterprise.modules.{name} import create_{name}_module\nm = create_{name}_module()\n```\n"
    )


def main() -> None:
    cat = json.loads((REPO / "data/build/module_catalog.json").read_text())
    entries = cat["order"]
    DOCS.mkdir(parents=True, exist_ok=True)

    grouped: dict[str, list] = {}
    for e in entries:
        name, prio, catname, purpose = e["module"], e["priority"], e["category"], e["purpose"]
        ver = e.get("version", "?")
        meta = _meta(name)
        (DOCS / f"{name}.md").write_text(
            _page(name, catname, prio, purpose, ver, meta), encoding="utf-8")
        grouped.setdefault(catname, []).append((prio, name, purpose))

    # grouped reference index
    lines = ["# ENI Module Reference (all modules)", "",
             "_Auto-generated: python3 scripts/gen_module_docs.py — one page per module in docs/modules/._", ""]
    for catname in sorted(grouped, key=lambda c: min(p for p, _, _ in grouped[c])):
        lines.append(f"## {catname}")
        lines.append("| Module | Purpose | Doc |")
        lines.append("|--------|---------|-----|")
        for _, name, purpose in sorted(grouped[catname]):
            lines.append(f"| `{name}` | {purpose} | [docs/modules/{name}.md](modules/{name}.md) |")
        lines.append("")
    (REPO / "docs" / "MODULES_REFERENCE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # master-README insert (a single table covering every module, grouped)
    ins = ["## Modules — complete reference (all modules)", "",
           "Every platform module (auto-discovered by the Platform Kernel):",
           "one page per module in [`docs/modules/`](docs/modules/) and the full grouped"
           " index in [`docs/MODULES_REFERENCE.md`](docs/MODULES_REFERENCE.md).", ""]
    for catname in sorted(grouped, key=lambda c: min(p for p, _, _ in grouped[c])):
        ins.append(f"### {catname}")
        ins.append("| Module | Purpose |")
        ins.append("|--------|---------|")
        for _, name, purpose in sorted(grouped[catname]):
            ins.append(f"| `{name}` | {purpose} |")
        ins.append("")
    (REPO / "README_MODULES_INSERT.md").write_text("\n".join(ins) + "\n", encoding="utf-8")

    # splice the full reference into the master README (after "## Modules")
    insert_text = "\n".join(ins).replace(
        "## Modules — complete reference (all modules)",
        "### Complete module reference (all modules)", 1).replace("\n### ", "\n#### ")
    readme = (REPO / "README.md").read_text()
    marker = "## Modules\n\n"
    if "### Complete module reference (all modules)" not in readme:
        (REPO / "README.md").write_text(readme.replace(marker, marker + insert_text + "\n", 1),
                                        encoding="utf-8")

    print(f"Wrote {len(entries)} module doc pages + MODULES_REFERENCE.md + README_MODULES_INSERT.md"
          f" + spliced master README")


if __name__ == "__main__":
    main()