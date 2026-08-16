# Module Rename & Rebrand Procedure

Complete procedure for stripping old branding (ENI, Claude Code, etc.) from enterprise modules.

## Phase 1: Directory Renames (swarm)

Dispatch 3 parallel subagents:
1. **Module renamer**: Rename directories, update all Python imports, `@module` decorators, run tests
2. **Docs renamer**: Rebrand all .md files in docs/, Enterprise_Validation/, READMEs
3. **Skills + dashboard**: Update Hermes skills, dashboard display names

## Phase 2: Deep Clean (sed pass)

After Phase 1, run a comprehensive sed sweep across ALL enterprise Python files:

```bash
# Logger names
find enterprise/modules/ -name "*.py" -exec sed -i \
  -e 's/enterprise\.claude_code_core\./enterprise.agent_core./g' \
  -e 's/enterprise\.claude_code_tools\./enterprise.agent_tools./g' \
  -e 's/enterprise\.claude_code_infra\./enterprise.agent_infra./g' {} +

# Internal variables
find enterprise/modules/ -name "*.py" -exec sed -i \
  -e 's/_eni_available/_swarm_available/g' \
  -e 's/eni_plugins/agent_plugins/g' {} +

# File/fifo names
find enterprise/modules/ -name "*.py" -exec sed -i \
  -e 's/eni_build_tasks\.json/build_tasks.json/g' \
  -e 's/eni_herself_tasks\.json/herself_tasks.json/g' \
  -e 's|/tmp/eni_deliverables|/tmp/enterprise_deliverables|g' \
  -e 's|eni_ctl_|swarm_ctl_|g' {} +

# Comment-only run instructions in test files
find enterprise/modules/ -name "*.py" -exec sed -i \
  -e 's|enterprise/modules/claude_code_core/tests/|enterprise/modules/agent_core/tests/|g' \
  -e 's|enterprise/modules/eni_swarm/tests/|enterprise/modules/swarm_bridge/tests/|g' {} +
```

## Phase 3: Doc Rebranding

Replace across ALL .md files in docs/ and Enterprise_Validation/:
- `ENI Enterprise` → `Enterprise AI Platform`
- `ENI` standalone → `Enterprise`
- `Claude Code` / `Claude Code Superior` → `Agent Engine`
- `eni_` prefix → appropriate new prefix

Also rename `STATUS_ENI_ENTERPRISE.md` → `STATUS_ENTERPRISE.md`.

## Phase 4: Skill Rebranding

Update skill YAML frontmatter names:
- `eni-enterprise-platform` → `enterprise-platform`
- `claude-code-superior` → `agent-superior`
- `claude-code-integration` → `agent-integration`

## Phase 5: Remaining Ref Check

```bash
grep -r "eni_\|claude_code" enterprise/modules/ --include="*.py" | grep -v __pycache__
grep -rl "ENI\|Claude Code" enterprise/Enterprise_Validation/ enterprise/docs/
```

Should return zero results in code. Comment-only references in test docstrings are acceptable.

## Rebrand Mapping

| Old | New |
|-----|-----|
| eni_kb | kb_bridge |
| eni_swarm | swarm_bridge |
| eni_compression | compression_bridge |
| claude_code_core | agent_core |
| claude_code_tools | agent_tools |
| claude_code_infra | agent_infra |
| ENICompressionModule | CompressionBridgeModule |
| STATUS_ENI_ENTERPRISE.md | STATUS_ENTERPRISE.md |

## Do NOT Rename

- `eni_compression/` standalone engine directory at `/home/hunter/Desktop/Eni Builder/eni_compression/` — the enterprise module `compression_bridge` depends on `core.engine` from this directory. The `__init__.py` adds `eni_compression/` to sys.path so `from core.engine import CompressionEngine` works.
- Hermes skill directories under `~/.hermes/skills/eni-swarm/` — the SKILL.md YAML frontmatter `name` field was updated, but the directory structure is cosmetic. Renaming directories requires skill_manage which may break cross-skill references.

## Verification

```bash
cd "/home/hunter/Desktop/Eni Builder"
python3 -m pytest enterprise/ -q -p no:anyio --ignore=enterprise/modules/compression_bridge/
# Should show all passing, zero rename-related failures
```
