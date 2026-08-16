---
name: agent-catalog
description: >-
  Query and invoke specialist agents from the ENI Enterprise Agent Catalog — a
  unified, deduplicated registry fusing 172 Codex subagents
  (~/Desktop/awesome-codex-subagents-main) and 263 Agency division agents
  (~/Desktop/agency-agents-main) into 432 normalized specialists. Use whenever
  the task would benefit from a named specialist (architect, security engineer,
  backend dev, marketer, designer, data/AI, governance, etc.), when LO asks to
  "use the catalog", "call a specialist", "swarm/agency agents", or "codex
  subagents". Covers locating the right agent and retrieving its full
  instructions to act as that specialist.
---

# ENI Agent Catalog — Specialist-Agent Registry

The enterprise `agent_catalog` module (in
`~/Desktop/Enterprise Builder/enterprise/modules/agent_catalog/`) fuses TWO
complementary specialist-agent libraries into ONE normalized, searchable set:

| Source | Repo | Format | Count | Character |
|--------|------|--------|-------|-----------|
| Codex   | `~/Desktop/awesome-codex-subagents-main` | `.toml` subagents | 172 | Engineering-focused: per-language devs, architects, infra, quality, data/AI, LLMOps. Carries model + sandbox hints. |
| Agency  | `~/Desktop/agency-agents-main` | `.md` division agents | 263 | Business breadth: marketing, sales, product, PM, design, security, support, strategy. Carries emoji/color/vibe persona. |

"Rebuilt better": shared roles across the two catalogs collapse into one record
with unioned categories & sources. **432 unique specialists total.**

## When to use this skill

- LO asks to invoke a specialist / "swarm" / "agency agent" / "codex subagent".
- The task has a hard specialty (e.g. Django, Go, threat modeling, LLM eval,
  brand design, market research) and a named specialist would raise quality.
- You want the enterprise `agent_catalog` module's search / A2A / registry.

## The canonical data

The fused catalog is committed so it works offline:
- Canonical JSON: `.../modules/agent_catalog/data/agent_catalog.json` (432 agents)
- Per-agent detail: `.../modules/agent_catalog/data/agents/<slug>.json`
- Regenerate from live sources: `python3 .../modules/agent_catalog/ingest.py`

## Quick CLI (from this skill's scripts/ dir)

```bash
S=~/.hermes/skills/agent-catalog/scripts/fetch_agent.py

python3 $S --overview                      # total / sources / categories
python3 $S --list                          # category -> count
python3 $S --search security --limit 10    # faceted search
python3 $S --search api --source codex     # source-filtered search
python3 $S <slug>                           # full instructions for one agent
```

Examples:
```bash
python3 $S software-architect     # agency persona agent
python3 $S fullstack-developer    # codex subagent
python3 $S --search "threat model"
```

## Full agent index

The complete master index (all 432 agents, grouped by category with
descriptions) is in `references/master-index.md`. Read it to pick the right
specialist, then `fetch_agent.py <slug>` for full instructions.

## How to act as a specialist

1. **Locate**: search the catalog or scan the master index for the best-matching
   specialist (consider both sources — a specialist may exist in one or both).
2. **Retrieve**: run `fetch_agent.py <slug>` to get the agent's full
   instructions/model/vibe.
3. **Adopt the persona**: follow the agent's working mode, focus areas, quality
   checks, and output contract as your operating instructions for this subtask.
4. **Cross-source note**: if the role exists in both catalogs, prefer the richer
   instruction set (often the agency persona adds domain personality; the codex
   adds tool/sandbox discipline).

## Enterprise module integration

The module auto-discovers into the Platform Kernel and registers each of the 432
specialists as an A2A `AgentCard` (via `AgentCatalogFacade.register_all_in_a2a`),
so specialists can participate in agent-to-agent task orchestration.

```python
from enterprise.modules.agent_catalog import create_agent_catalog_module
mod = create_agent_catalog_module({'db_path': 'data/agent_catalog.db'})
await mod.initialize()
fac = mod.facade
fac.overview()                               # {'total': 432, ...}
fac.search('architect', source='codex')
fac.get('engineering-software-architect')
```

## Pitfalls

- Some roles exist in **both** catalogs under different slugs (e.g. codex
  `software-architect` vs agency `engineering-software-architect`). Search, then
  pick the richer set — don't assume one is missing.
- Codex `.toml` names come from `name=` (lowercase slug); Agency `.md` names come
  from YAML `name:` (human-friendly "Software Architect"). Match on `slug` for
  stable identity.
- `fetch_agent.py --search` matches slug/name/description/categories — use it
  for fuzzy discovery; use `fetch_agent.py <slug>` (exact first) for retrieval.
- If the enterprise repo moves, update the `CANON` path in `fetch_agent.py` and
  the canonical JSON path in `ingest.py`.
