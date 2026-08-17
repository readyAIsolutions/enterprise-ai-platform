---
name: eni-module-agent_catalog
description: Operate the ENI Enterprise `agent_catalog` module (Legacy Core) — ENI Agent Catalog Module -- unified specialist-agent registry. Use when working with agent_catalog in the Enterprise Platform.
---

# Module skill: agent_catalog

- Category: Legacy Core (priority ?)
- Version: 1.0.0
- Purpose: ENI Agent Catalog Module -- unified specialist-agent registry.

## What it does
ENI Agent Catalog Module -- unified specialist-agent registry.

Fuses two complementary specialist-agent catalogs into one normalized,
searchable platform module:

  * **Codex** subagents  (~/Desktop/awesome-codex-subagents-main) — 172
    engineering-focused agents in native Codex ``.toml`` format, each carrying
    a model hint, reasoning effort and sandbox mode.
  * **Agency** division agents (~/Desktop/agency-agents-main) — 263 business /
    product / sales / marketing / design / engineering agents in Markdown with
    YAML frontmatter (someone "persona" agents with emoji + color + vibe).

"Rebuilt better" means: a single normalized schema, cross-source slug
deduplication (shared roles collapse into one record with unioned categories
and sources), SQLite persistence with faceted searc

## Key API (facade methods on the @module class)
- facade\n- health_check\n- initialize\n- set_event_bus\n- shutdown

## Use
Import via:
```python
from enterprise.modules.agent_catalog import create_agent_catalog_module
m = create_agent_catalog_module()
import asyncio; asyncio.run(m.initialize())
```
(Pass a config dict as the first arg when the module needs one.)

## Verify / test
From the repo root:
```bash
python3 -m pytest modules/agent_catalog/tests -q
```
(self-contained unit tests, no network; must pass).

## Troubleshooting
- `ModuleNotFoundError: enterprise` -> run from repo root (conftest aliases it) or
  set PYTHONPATH="/home/hunter/Desktop/Enterprise Builder".
- Repo path has a space -> always quote it in shell / use the absolute path.
