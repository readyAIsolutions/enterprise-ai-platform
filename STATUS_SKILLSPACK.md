# STATUS — SLICE C: Portable Skills/LSP/MCP/Plugin Pack + Installer + Packaging

Date: 2026-08-16
Builder: SLICE C (parallel swarm)
Repo root: /home/hunter/Desktop/Enterprise Builder/enterprise
Spec: slices/SLICE_skillspack.md

## Summary

The live Hermes layer (~/.hermes) has been mirrored into the product repo as a
versioned, ship-able "skills_pack" (SLICE C), plus a one-command installer, a
small `eni` CLI, a root `docker-compose.yml` for the Hermes layer, and merged
Makefile targets. All deliverables verified with real output. The platform
kernel (`platform_kernel.py`, repo root, v1.0.0) is NOT modified — only read.

## DELIVERABLES (all present)

| Artifact | Status | Notes |
|---|---|---|
| skills_pack/skills/ (20 categories) | PASS | 957 files after pycache strip |
| skills_pack/lsp/ (eni_compression) | PASS | from ~/.hermes/lsp_servers |
| skills_pack/mcp/ (compression, knowledge_base) | PASS | 2 servers |
| skills_pack/plugins/ (eni-omega-compress-paid) | PASS | networkx/whatsapp contacts |
| skills_pack/__init__.py | PASS | versioned docstring |
| scripts/install_skillspack.sh | PASS | executable, idempotent, dry-run |
| scripts/eni_cli | PASS | executable, doctor/install/status/up |
| docker-compose.yml (root, Hermes layer) | PASS | `docker compose config` valid |
| Makefile targets (merged, none overwritten) | PASS | `make skillspack-dryrun`, `make eni-status` |
| STATUS_SKILLSPACK.md | PASS | this file |

## PROOF — installer dry-run (real output, bash scripts/install_skillspack.sh --dry-run)

```
[ENI skillspack install] pack: /home/hunter/Desktop/Enterprise Builder/enterprise/skills_pack
  target Hermes home : /tmp/skillspack_test
  skills categories  : 20
  skill files        : 957
  lsp server files   : 1
  mcp server files   : 2
  plugin files       : 3
  total files        : 963

[DRY-RUN] no files were copied. Planned mapping:
  .../skills_pack/skills/ -> /tmp/skillspack_test/skills/
  .../skills_pack/lsp/    -> /tmp/skillspack_test/lsp_servers/
  .../skills_pack/mcp/    -> /tmp/skillspack_test/mcp_servers/
  .../skills_pack/plugins/ -> /tmp/skillspack_test/plugins/

Would BACK UP existing destination to: /tmp/skillspack_test/.skillspack_backup_<TIMESTAMP>
[DRY-RUN] complete.
```

## PROOF — installer idempotency (3 re-runs on fresh target, real output)

```
run1 exit=0 skills=957 nested=0 total_to_disk=963
run2 exit=0 skills=957 nested=0 total_to_disk=963
run3 exit=0 skills=957 nested=0 total_to_disk=963
  install complete summary (run3): skills 957 / lsp 1 / mcp 2 / plugin 3 / total 963
  backups created: /tmp/verify/.skillspack_backup_20260816_141000
  __pycache__ dirs in target: 0     *.pyc files in target: 0
```

Note: an early version nested `skills/skills` on re-runs because `cp -rn "src/" "dst/"`
copies `src` *into* `dst` when `dst` already exists instead of merging contents.
Fixed by using a `/.` source (content-merge). Root cause documented in the script.

## PROOF — eni CLI (real output, python3 scripts/eni_cli <cmd>)

`python3 scripts/eni_cli status`
```
ENI platform status
----------------------------------------------
  [OK]   platform kernel:             platform_kernel v1.0.0
  modules present:       51
  modules healthy:       51
  test files:            147
  [OK] skills_pack present:         yes
```

`python3 scripts/eni_cli doctor`
```
ENI platform doctor
----------------------------------------------
  [PASS] platform kernel import:      platform_kernel (v1.0.0)
  bootstrap source:           no module-level bootstrap (kernel drives orchestration)
  [PASS] skills_pack/ mirror:         present (870 skill objs)
  lsp/mcp/plugins objs:      1/2/2
  config dir:                 .../enterprise/config
```

`python3 scripts/eni_cli up` -> prints `docker compose`/`make run|status|logs|down` instructions. OK.

`make skillspack-dryrun` and `make eni-status` both exit 0 (verified above).
`docker compose -f docker-compose.yml config` -> OK.

## VERDICT — what adds R / what to drop

Adds R (self-host revenue / upsell value):
- One-command deploy of a working Hermes layer is the core self-host pitch: a
  company gets the platform AND agents working from a single `make`/`eni install`.
- `eni doctor` / `eni status` doubles as a health/upsell screen (kernel healthy,
  pack present) that support/sales can run on customer machines.
- Versioned mirror means customers self-host WITHOUT handing them your live
  `~/.hermes` secrets — the pack is scrubbed of auth/cache/config (see below).
- Nesting bug caught + fixed = installer is actually safe on re-run (trust signal).

Drop / exclude from ship (DON'T copy into pack):
- DO NOT mirror ~/.hermes auth.json, *.key, config.yaml, secrets.enc, *.db,
  channel_directory.json, pairing/, profile secrets. None were copied — the pack
  is clean by construction (only skills/lsp/mcp/plugins copied).
- DO NOT vendor the giant 115MB ~/.hermes/lsp node_modules dump. The pack vendors
  only ~/.hermes/lsp_servers (eni_compression). Reinstall language servers via npm.
- The Dockerfile in the shipped root compose uses python:3.12-slim; swap to the
  repo's existing docker/Dockerfile if you want the full heavy base image instead.

## UNVALIDATED (can NOT be asserted from this box)

- A real target machine install into a fresh ~/.hermes (foreign environment) has
  not been performed here; only dry-run + temp-target re-runs were proven.
- Whether ~/.hermes/lsp (language-server binaries) rebuild cleanly on another OS.
- Live behavior of the MCP/plugin servers (compression, knowledge_base,
  eni-omega-compress-paid) after install on a customer host.
- Root docker-compose `--profile hermes up` was config-validated, not actually
  run (docker present, build/smoke not executed).
- `eni install` against ~/.hermes for real was NOT run (avoid mutating the live
  home in this swarm); temp-target runs prove the same code path.

## FILES CREATED / MODIFIED (this slice)

- skills_pack/ (new): __init__.py, skills/(20 cats), lsp/, mcp/, plugins/
- scripts/install_skillspack.sh (new, executable)
- scripts/eni_cli (new, executable)
- docker-compose.yml (new — root Hermes-layer compose; existing docker/docker-compose.yml untouched)
- Makefile (modified — appended SLICE C section; no existing target changed)
- STATUS_SKILLSPACK.md (new — this file)

No enterprise kernel/bootstrap/module source was modified.