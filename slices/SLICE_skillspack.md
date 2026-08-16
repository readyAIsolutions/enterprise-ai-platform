# SLICE C — Portable Skills/LSP/MCP/Plugin Pack + Installer + Packaging
Build into: /home/hunter/Desktop/Enterprise Builder/enterprise/skills_pack/ and scripts/

Goal: companies can self-host the platform AND get a working Hermes layer in one command.
Port every skill/LSP/MCP/plugin from the live ~/.hermes into the product repo so it's
versioned + shipable, plus a one-command installer.

TASKS:
1. Create a portable mirror under /home/hunter/Desktop/Enterprise Builder/enterprise/
   skills_pack/ with subdirs: skills/, lsp/, mcp/, plugins/.
2. COPY (not relocate) from the live home:
   - skills_pack/skills/   <- ~/.hermes/skills/ (all categories)
   - skills_pack/mcp/      <- ~/.hermes/mcp_servers/  (compression, knowledge_base)
   - skills_pack/plugins/  <- ~/.hermes/plugins/ (eni-omega-compress-paid)
   - skills_pack/lsp/      <- any language-server dirs found (~/.hermes/docs or 'lsp' names)
   Use `cp -r` and then `find ... -name __pycache__ -prune -exec rm -rf {}` and remove
   *.pyc. Keep total size sane; skip giant carrier/build dumps if present.
3. Write scripts/install_skillspack.sh: copies skills_pack/ into a target home (default
   ~/.hermes), preserving category layout, idempotent (backup existing first to
   ~/.hermes/.skillspack_backup_TIMESTAMP), chomp pycache again, then prints a summary.
   Must be safe to re-run.
4. Write scripts/eni_cli (or .py) a small "eni" CLI with subcommands:
     eni doctor        -> reports platform health by importing platform_kernel + bootstrap
     eni install       -> runs install_skillspack.sh
     eni status        -> prints module count / healthy / tests count from config
     eni up            -> prints docker compose up -d instructions
   Give it a docstring + help text. Put it in scripts/ and make it executable.
5. Makefile + docker: vendor a working docker-compose.yml (reuse enterprise/docker if
   present; if docker not installed, still write compose). Add Makefile targets:
   `install` (skillspack + pip -e), `test`, `up`, `doctor`, `status`. Do NOT break the
   existing Makefile — merge, don't overwrite blindly (read it first).
6. Verify: `bash scripts/install_skillspack.sh --dry-run` actually works (stat counts of
   files before/after), CLI `python scripts/eni_cli status` runs, and parrot config parses.

CONSTRAINTS:
- english comments. Do NOT modify the enterprise/running services.
- This is largely mechanical copy + light scripts. CORRECTNESS = installer works and the
  CLI executes. Prove with real command output in your STATUS.
DELIVERABLE: files + installer dry-run real output + STATUS_SKILLSPACK.md with PASS/FAIL,
  "what adds R / what to drop" + UNVALIDATED (e.g. we can't assert a foreign install).
  English-only.