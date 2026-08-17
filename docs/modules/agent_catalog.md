# Module: `agent_catalog`

- Category: Legacy Core · priority 6
- Version: 1.0.0
- Purpose: ENI Agent Catalog Module -- unified specialist-agent registry.
- Skill: `eni-module-agent_catalog` (ICM stages) in skills_pack/skills/eni-modules/agent_catalog/

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
and sources), SQLite persistence with faceted search, and every agent
registered as an A2A ``AgentCard`` so it can participate in the platform's
agent-to-agent network.

The module is a registered Platform Kernel module implementing the standard
lifecycle (``initialize`` / ``health_check`` / ``shutdown``) and the event-bus
wiring contract (``set_event_bus``). A public ``AgentCatalogFacade`` exposes
``search`` / ``get`` / ``overview`` / ``register_all_in_a2a``.

The canonical catalog JSON is committed to ``data/agent_catalog.json`` so the
module works offline; ``python -m modules.agent_catalog.ingest`` regenerates it
from the live source repos, and ``create_agent_catalog_module`` may pass a
``refresh_ingest=True`` config to re-ingest on boot.

## Key API (facade methods)
facade, health_check, initialize, set_event_bus, shutdown

## Tests
```bash
python3 -m pytest modules/agent_catalog/tests -q
```

## Import
```python
from enterprise.modules.agent_catalog import create_agent_catalog_module
m = create_agent_catalog_module()
```
