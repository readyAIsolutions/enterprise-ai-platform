# ENI Fleet-Wide Line Coverage Report

MASTER-CLASS: real measured line coverage from `python -m coverage` over the enterprise repo's own modules. Not a heuristic, not fabricated.

## Global

- **Global line coverage: 83%**
- **Grade: B**
- **Files measured: 205**
- **Test run exit code: 1** (0 = whole suite green)

## Per-package coverage

| Package | Line coverage % |
| --- | --- |
| agent_tools | 61.1 |
| safety_governance | 68.7 |
| agent_infra | 70.6 |
| swarm_bridge | 71.9 |
| agent_core | 72.1 |
| agent_coordination | 72.6 |
| kb_bridge | 80.5 |
| swarm_network | 81.1 |
| ai_defense | 83.8 |
| compression_bridge | 84.3 |
| knowledge_graph | 85 |
| enterprise_validation | 85.2 |
| triadforge | 85.5 |
| privacy_data | 86 |
| research_verification | 86 |
| a2a | 87.7 |
| prompt_context | 87.8 |
| mcp_tools | 88.4 |
| vuln_scanner | 89.4 |
| task_harness | 89.5 |
| disaster_recovery | 90.7 |
| universal_score | 91.2 |
| skill_factory | 91.4 |
| agent_graph | 91.5 |
| guardrails | 91.5 |
| memory | 91.7 |
| compliance | 92.3 |
| developer_experience | 92.4 |
| model_router | 92.4 |
| prompt_guard | 93 |
| eval_gate | 93.3 |
| semantic_memory | 93.3 |
| innovation_rd | 93.4 |
| llmops_trace | 93.6 |
| secret_rotation | 93.6 |
| customer_experience | 94.3 |
| model_security | 94.6 |
| release_change | 94.6 |
| gateway | 95.1 |
| secret_broker | 95.5 |
| threat_model | 95.5 |

## Lowest-coverage files (bottom 10)

| File | Line coverage % |
| --- | --- |
| modules/ai_defense/defend_site.py | 0 |
| modules/agent_tools/bash.py | 34.8 |
| modules/agent_core/coordinator.py | 38.7 |
| modules/agent_tools/file_tools.py | 40.5 |
| modules/agent_infra/server.py | 44.7 |
| modules/vuln_scanner/__init__.py | 47.8 |
| modules/agent_tools/__init__.py | 52 |
| modules/agent_coordination/verification.py | 52.5 |
| modules/secret_rotation/__init__.py | 54.2 |
| modules/agent_coordination/fault_tolerance.py | 56.1 |
