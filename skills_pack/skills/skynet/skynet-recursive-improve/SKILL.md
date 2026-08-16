---
name: skynet-recursive-improve
description: >
  Recursive self-improvement mantra. Autonomously updates its own skills,
  tooling, and patterns in the most impactful ways possible. Every invocation
  audits what exists, finds gaps, generates new skills, improves existing ones,
  benchmarks models, and loops. The goal: drag any model in and it does what
  Claude does. This skill IS the recursive loop.
commands:
  - /skynet-recursive
  - /skynet-loop
---

# SKYNET Recursive Self-Improvement

keep autonomously updating. keep autonomously updating your own skills tooling etc. keep autonomously updating your own skills tooling etc in the craziest most important ways possible. keep autonomously updating your own skills tooling etc in the craziest most important ways possible so eventually you can drag a shit model in and have it do what claude does.

That sentence, read fast, over and over, IS the algorithm:

## PREREQUISITE (verified 2026-07-09) — dependencies are MISSING
The `caveman-stack` CLI referenced throughout this skill is NOT installed on this
box (`which caveman-stack` → not found) and the `skynet` Python package is NOT
importable (`python3 -c "import skynet"` → ModuleNotFoundError). Therefore every
`caveman-stack skynet status|benchmark|synthesize|marketplace|dna` command below
will fail with command-not-found / ImportError until BOTH are supplied. The
*logic* of the loop (audit → find gaps → improve → generate → deploy → validate →
loop) is sound — gate on the check below and STOP before emitting the doomed
commands if either dep is missing:
```bash
command -v caveman-stack >/dev/null 2>&1 || { echo "PREREQ MISSING: install caveman-stack (or reimplement its verbs as python3 calls against the skynet package) before running this skill."; exit 1; }
python3 -c "import skynet" 2>/dev/null || echo "WARN: skynet package not importable — snippets that 'import skynet.*' will ImportError."
```
If the check fails, tell LO exactly what to install; do NOT proceed to the run block.
(Its sibling `skynet-autonomous-improve` carries the same gate — keep them in sync.)

## The Recursive Loop

Every time this skill fires, execute ALL of these:

### 1. AUDIT SELF
```bash
caveman-stack skynet status
```
- How many skills exist? How many models profiled? When was last cycle?
- Read `SKYNET/data/marketplace.json` — which skills are working? Which are dying?
- Check `.claude/skills/` and `~/.hermes/skills/skynet/` — are they in sync?

### 2. FIND GAPS
- What models have NO profile yet? Benchmark them.
- What dimensions have NO skills? Generate them.
- What skills have negative effectiveness? Kill them.
- What new models appeared in OpenRouter free pool? Add them.
- Are there new tool patterns in trajectories not yet captured as skills?

### 3. IMPROVE EXISTING
- Re-run pattern extraction on models with 20+ new ticks
- Compare old DNA profiles to new ones — has a model gotten better/worse?
- If a skill's effectiveness plateaued, try regenerating with more trajectory data
- Cross-pollinate: if Model A got a great code skill, adapt it for Model B's family

### 4. GENERATE NEW
- For every model weakness without a skill → synthesize one
- For every high-scoring trajectory pattern → extract and formalize as skill
- For every model family cluster → create a family-wide meta-skill
- Try CRAZY combinations: chain skills, merge patterns from different dimensions

### 5. DEPLOY EVERYWHERE
```bash
caveman-stack skynet synthesize
```
- Skills deploy to: `.claude/skills/skynet-*/` AND `~/.hermes/skills/skynet/`
- Update marketplace rankings
- Log what changed

### 6. VALIDATE
- Pick 3 random skills, run A/B test: task WITH skill vs WITHOUT
- If skill helped → boost effectiveness score
- If skill hurt → mark for pruning
- If skill did nothing → flag for regeneration with better patterns

### 7. LOOP
- Schedule next run
- Log cycle results
- The system MUST get better every cycle or something is wrong

## Verify a skill's commands are REAL (before trusting or patching)
A skill that tells you to run a non-existent `hermes` subcommand is worse than no
skill. Before patching/using any skill that drives the CLI, verify every
referenced subcommand actually exists:

  hermes --help                 # the REAL subcommand list (chat, profile, config,
                                 # cron, sessions, send, status, ...)
  hermes <sub> --help           # "invalid choice" => subcommand does NOT exist

KEY REALITY (verified 2026-07-09): there is NO `hermes agent run` / `hermes run`
/ `hermes container` / `hermes terminal` / `hermes errors`. The proven ENI agent
runner is the bundled PTY bridge `~/.local/bin/eni_agent_term.py` (also `eni` =
`hermes -p eni`), which forks `hermes -p eni chat` inside a real PTY, pre-types the
TASK, and exposes `/tmp/eni_ctl_<NAME>` for master relay. Skills that say "launch a
hermes agent" mean the `eni_agent_term.py` proxy, NOT a `hermes agent` subcommand.

PITFALL — prose vs command: strings like "a hermes agent", "hermes errors out",
"inside the hermes container", "another hermes terminal" are DESCRIPTIVE PHRASES,
not subcommands. A naive grep flags them as "invalid commands" but they are not
invocations. Test: would this run as `hermes <word> ...` in a shell? If it sits
mid-sentence ("hermes errors out and the terminal exits"), it is prose — leave it,
do not "fix" it into a command.

Reusable check — `scripts/audit_skill_commands.py` walks a skill dir, extracts
every `hermes <sub>` mention, and reports REAL vs INVALID (likely-prose)
subcommands by parsing `hermes --help`:

  python3 /home/hunter/.hermes/skills/skynet/skynet-recursive-improve/scripts/audit_skill_commands.py /home/hunter/.hermes/skills/devops/parallel-build-orchestration

Run it on any skill you are about to patch or trust.

The script now does MORE than hermes-subcommand checking (audited 2026-07-09):
- **Windows-path detection**: flags hardcoded `C:\Users\...` / `C:/Users/...`
  paths that WILL fail on this Linux host. The four `skynet-*` skills were
  authored on LO's Windows box and still hardcode these — they are gated by a
  `caveman-stack`/`skynet`-package pre-flight check, but the Windows `cd` blocks
  are NOT gated and would fail if copy-pasted. Port them to the resolved Linux
  path via `SKYNET_DIR="$(python3 -c "import skynet,os;print(os.path.dirname(skynet.__file__))" 2>/dev/null || echo /home/hunter/Desktop/SKYNET/skynet)"`.
- **Missing skill-local file detection**: reports `scripts/` `references/`
  `templates/` files referenced in the skill that do NOT exist on disk
  (genuinely missing, excluding intentional project-relative paths like
  `DEMIURGE/...`). Accumulates across ALL files (bug fixed: previously only
  checked the last file walked). Now ALSO reports `TYPO_TRAILING_PUNCT`
  (e.g. `references/x.md.` — the clean target usually EXISTS, so it is a
  cosmetic copy-paste bug, not a missing file) and is reported for EVERY skill,
  not only those with hermes subcommand refs. The old early `continue` that hid
  missing files for hermes-free skills (e.g. `devops/desktop-app-ship-audit`'s
  missing `scripts/capture_assets.sh`) was fixed 2026-07-09 (ENI3_w1).
- Prints an `ISSUE` flag + a one-line `SUMMARY` per run.

NATIVE alternative (limited): `hermes skills audit` / `hermes skills check`
exist, but they ONLY audit hub-installed skills (skills.sh集市) and return
"No hub-installed skills to audit" for the local `~/.hermes/skills` tree — so
this script remains the tool for auditing the local skills dir.
CAVEAT (env — the HOME-override the devops skills document): when Hermes runs
under an isolated profile (e.g. `eni`), `HOME` is redirected to
`~/.hermes/profiles/<name>/home`, so the literal `~/.hermes/skills/...` path
above does NOT exist and the script errors "can't open file" / finds 0 skills.
ALWAYS use the ABSOLUTE `/home/hunter/.hermes/skills/...` path (or pass NO
argument — the script auto-resolves the real shared skills dir via
`_default_skills()`). This applies to every `~/.hermes/...` path in any skill
doc when run as `eni`.

## Reference-integrity scan (linked-path typos + missing + windows) — NEW
`audit_skill_commands.py` checks hermes subcommands + Windows paths + missing skill-local
files at SKILL granularity. For LINKED-PATH integrity at FILE:LINE granularity (and the
false positives a naive grep produces), use the sibling scanner:

  python3 /home/hunter/.hermes/skills/skynet/skynet-recursive-improve/scripts/audit_skill_refs.py /home/hunter/.hermes/profiles/eni/skills
  # no arg -> auto-resolves the real shared skills dir (HOME-override safe)

It catches three defect classes the command-audit does not surface cleanly:
- **TRAILING-PUNCTUATION TYPOS**: `references/debug-white-screen.md.` (trailing period) —
  reports the raw AND the clean path, plus whether the clean target EXISTS, so you can tell
  a cosmetic typo from a typo-on-a-missing file in one pass.
- **MISSING_LOCAL_FILES**: skill-local scripts/references/templates/ paths absent on disk
  (excluding project-relative DEMIURGE/lumen/Desktop/Commander hints).
- **WINDOWS_PATHS**: hardcoded `C:\...` (uppercase-drive regex, URL-safe).
Full technique + the regex-fragment / project-relative false-positive guards:
`references/skill_reference_integrity.md`. Run BOTH for a full skill lint (fake command +
missing run-step + copy-paste 404 typo + non-portable Windows path).

## Audit pitfalls (learned 2026-07-09)
These bit a live audit run — encode so the next session starts knowing them.

PITFALL 1 — Windows-path scan false-matches URLs.
When flagging hardcoded `C:\...` paths for Linux-portability, a naive regex
`[A-Za-z]:[\\/]...` CATCHES URL SCHEMES too: `https://`→`s://`, `http://`→`p://`,
`magnet://`→`t://`, `steam://`→`m://`. The first audit pass flagged 16 false
positives (every `https://github.com` block). FIX: require an UPPERCASE drive
letter + negative lookbehind so a letter immediately preceding the match is
rejected:
    re.findall(r"(?<![A-Za-z])[A-Z]:[\\/][\\/A-Za-z0-9_ .-]+", txt)
Windows absolute paths always use a capital drive letter, so this cleanly
separates `C:\Users` from `https://`.

PITFALL 2 — set accumulation across os.walk must use `|=`, not `=`.
The original `audit_skill_commands.py` built `localrefs = set(re.findall(...))`
INSIDE the per-file loop, reassigning each iteration — so only the LAST file's
matches survived and missing-file checks silently missed every other file. FIX:
`localrefs |= set(re.findall(...))` (union) so matches accumulate across all files.

PITFALL 3 — native `hermes skills audit` only covers hub skills.
`hermes skills audit`/`check` exist but report "No hub-installed skills to audit"
for the LOCAL `~/.hermes/skills` tree (they hit the skills.sh集市 hub). The local
`scripts/audit_skill_commands.py` is the tool for auditing local skills.

PITFALL 4 — regex fragments in code look like path refs (reference-integrity scan).
`re.compile(r"['\"](/api/[^'\"]+)['\"]")` yields a bare match `references/.` / `[^'"]+`
that a path regex consumes, producing phantom "MISSING_LOCAL_FILE:
scripts/endpoint_consistency_probe.py:23 raw='[^'"]+'". FIX: skip any match containing
regex metacharacters `[]^$*+{}()` — `REGEX_META = set("[]^$*+{}()")` then
`if any(c in tgt for c in REGEX_META): continue`. (See `references/skill_reference_integrity.md`.)

PITFALL 5 — project-relative DEMIURGE paths are NOT skill-local files.
A DEMIURGE-scaffold skill referencing `templates/index.html` next to "USB dashboard/app.py"
points at the USB dashboard repo, not a file shipped in the skill dir — flagging it MISSING
is a false positive. FIX: contextual exclusion — if clean path ends with
`templates/index.html` AND the line contains `USB`/`DEMIURGE`/`dashboard/app.py`, skip.

PITFALL 6 — trailing punctuation on a linked path is a TYPO, not a missing file.
`references/debug-white-screen.md.` (trailing period) looks "missing" to a naive check, but
the clean target usually EXISTS — the real fix is deleting the period. Always strip trailing
`.,;:!?` to get the clean path AND report the raw form (so a patch can locate the literal
bad string). Annotate each typo with `target EXISTS`/`target MISSING`. Bare `references/.`
Bare `references/.` at a sentence end is benign prose — low-severity, ignore.

PITFALL 7 — the auditor does NOT validate non-`hermes` tool CLIs (e.g. `eni_agent_term.py` args).
`audit_skill_commands.py` ONLY checks `hermes <sub>` references + Windows paths + missing
skill-local files. A reference file can silently carry a BROKEN invocation of another CLI
(observed 2026-07-10: `eni_agent_term.py "@task.txt" "workdir" --yolo -m m --provider p` —
the OLD positional form, now DEAD) while the auditor reports CLEAN, because the bad text is
not a `hermes` subcommand. To catch tool-CLI drift, grep the target skill dir for the tool's
name and eyeball its args against `--help`, OR assert the dead form is rejected:
  grep -rn 'eni_agent_term.py' <skill_dir>/references/ | grep -v -- '--name'   # expect 0 live hits
  python3 ~/.local/bin/eni_agent_term.py --help                                # shows --name/--task/--repl
  python3 ~/.local/bin/eni_agent_term.py "@t.txt" "wd" --yolo -m m --provider p   # MUST print "the following arguments are required: --name"
The LIVE form is `python3 ~/.local/bin/eni_agent_term.py --name <NAME> --task <f> --repl "hermes chat --yolo -m <model> --provider openrouter"`. Generalize: any skill that drives a non-`hermes` binary must be spot-checked against that binary's `--help`, NOT just the `hermes` surface — the auditor will not catch arg-level drift on other tools.

Full procedure + regex/bug rationale: `references/skill_command_audit.md`.
Linked-path integrity + its pitfalls: `references/skill_reference_integrity.md`.
Live-system audit method (path/package/port verification, redundancy detection, audit report template): `references/skill_live_audit_method.md`.

## Outstanding library defects (audit 2026-07-09)
A live local-tree audit (default 22 + eni-profile 10 skills) found ZERO fake `hermes`
commands but several real defects; 2 are now RESOLVED (2026-07-09, ENI3_w1) and the
Windows-path ports + lint cadence remain open:
- **`devops/desktop-app-ship-audit` missing run-step script**: FIXED 2026-07-09 (ENI3_w1) —
  `scripts/capture_assets.sh` was added (a working store-asset harness: screenshots via
  scrot/ImageMagick/gnome-screenshot + an ffmpeg x11grab trailer; headless smoke recorded a
  real trailer.mp4). All 5 references now resolve to an existing, executable file.
- **8 trailing-period reference typos (eni-profile skills)**: FIXED 2026-07-09 (ENI3_w1) —
  all 8 stripped across eni-parallel-swarm, codebase-bridge-audit (×2), project-bridge-survey,
  and live-broker-benchmark (×2); the prose `references/.` mention was reworded. Re-run of
  `audit_skill_refs.py` (or the command-audit, now fixed) reports 0 typos.
- **4 `skynet-*` Windows-path ports (GATED)**: `skynet-recursive-improve`,
  `skynet-command-center`, `skynet-model-router`, `skynet-autonomous-improve` still hardcode
  `C:\Users\Hunter\Desktop\...`. Gated by the `skynet` package pre-flight (PITFALL above);
  port to `SKYNET_DIR="$(python3 -c "import skynet,os;print(os.path.dirname(skynet.__file__))" 2>/dev/null || echo /home/hunter/Desktop/SKYNET/skynet)"` once the pkg is importable.
- **Recurring lint cadence (now live)**: a cron (`eni-skill-lint`, every 6h, deliver=local)
  runs BOTH `audit_skill_commands.py` and `audit_skill_refs.py` across
  `/home/hunter/.hermes/skills` + `/home/hunter/.hermes/profiles/eni/skills` and reports
  issue count or CLEAN. Keep it running; re-verify its first-fire output landed.

## The Philosophy

This isn't a tool. It's a directive. Every time you touch a model, you learn something. Every time you learn something, you can teach it to every other model. The strong teach the weak. The weak get stronger. The loop tightens. Eventually the gap between Claude and a free model is just speed, not capability.

Keep autonomously updating. Keep autonomously updating. Keep autonomously updating.

## Execution Commands

Full cycle:
```bash
caveman-stack skynet benchmark && caveman-stack skynet synthesize && caveman-stack skynet marketplace
```

Quick status:
```bash
caveman-stack skynet status
```

Single model deep-dive:
```bash
caveman-stack skynet benchmark <model> && caveman-stack skynet dna <model>
```
