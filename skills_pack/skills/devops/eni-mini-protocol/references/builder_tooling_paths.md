# Builder tooling paths — canonical locations & the "guessing trap"

## Canonical on-disk locations (verified BUILDER_37, Aug 2026)

The skill's category directory is `devops`, NOT `eni-swarm`. Do not guess the
path from the skill name or the `eni-swarm` family of related skills.

- Skill root: `~/.hermes/skills/devops/eni-mini-protocol/`
- Idle check: `~/.hermes/skills/devops/eni-mini-protocol/scripts/check_builder_idle.sh`
  - Run: `bash ~/.hermes/skills/devops/eni-mini-protocol/scripts/check_builder_idle.sh BUILDER_37`
  - The BUILDER_NAME arg is MANDATORY and the `bash` prefix is REQUIRED (confirmed BUILDER_37, Aug 12 2026):
    - `bash .../check_builder_idle.sh` (no arg) -> `usage: check_builder_idle.sh <BUILDER_NAME>`, EXIT=1
    - `./check_builder_idle.sh BUILDER_37` (not executable) -> `Permission denied`, EXIT=126
    The script needs BOTH the verbatim name AND the `bash` interpreter. A pass that
    omits either burns 1–2 extra calls before the 5-mirror check actually runs.
- Others: `scripts/eni_resume.sh`, `scripts/eni_pl_relay.sh`
- Template: `templates/STATUS_BUILDER_IDLE.md`

## Pitfall: locating scripts when skill_view output is compressed

In this environment, `skill_view` output for SKILL.md bodies is ENI-compressed —
only head/tail metadata remains readable inline, and the JSON `path`/`skill_dir`
fields are not visible. A first pass (Aug 10 2026) guessed
`~/.hermes/skills/eni-swarm/eni-mini-protocol/scripts/check_builder_idle.sh` and
wasted a call on `No such file or directory`.

FIX: locate support files with
`search_files(target='files', path='~/.hermes', pattern='check_builder_idle.sh')`
(or the file you need) — ripgrep scan returns the true path instantly.
Only then run the script.

## Recurrence confirmed (second pass, same day Aug 10 2026)

The guessing trap is NOT a one-off — it fired again on a later steady-state idle
pass. Despite the first pass being documented, the agent again wasted TWO calls
guessing before running `find`:
  `~/.hermes/scripts/check_builder_idle.sh`  -> No such file or directory
  `<workdir>/scripts/check_builder_idle.sh`  -> (path in the project, not the skill)
The canonical script lives ONLY in the skill dir:
`~/.hermes/skills/devops/eni-mini-protocol/scripts/check_builder_idle.sh`

Takeaway for future passes: DO NOT guess intermediate dirs at all — either use the
canonical path above verbatim, or run `find ~/.hermes -name 'check_builder_idle.sh'`
/ `search_files(pattern='check_builder_idle.sh')` as the FIRST action. The skill
category directory is `devops`, never `eni-swarm`, and the script never lives in
`~/Desktop/*/scripts/` or `~/.hermes/scripts/`.

## Reference-files are readable

Unlike SKILL.md bodies, individual `references/*.md` files usually return
uncompressed via `skill_view(name, file_path)` — read those for full protocol
text when the main body is unreadable.