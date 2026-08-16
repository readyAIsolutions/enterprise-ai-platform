# Reference-integrity scan for skills (trailing-punct typos + missing + windows)

Companion to `scripts/audit_skill_commands.py` (which checks hermes subcommands + Windows
paths + missing skill-local files at skill granularity). This scanner adds LINKED-PATH
integrity at FILE:LINE granularity, and — critically — strips the false positives a naive
`grep references/|scripts/` produces.

## Run it

    python3 scripts/audit_skill_refs.py /home/hunter/.hermes/profiles/eni/skills
    # no arg -> auto-resolves the real shared skills dir (HOME-override safe)

READ-ONLY. Emits a per-skill board: WINDOWS_PATHS / MISSING_LOCAL_FILE / TYPO (with
`target EXISTS`/`target MISSING` annotation).

## What it catches that the hermes-command audit does not

1. TRAILING-PUNCTUATION TYPOS on a linked path — `references/debug-white-screen.md.`
   (trailing period). Naive grep lumps this into "missing file" but the REAL fix is to
   delete the period; the clean target usually EXISTS. The scanner reports both the raw
   string and the clean path, plus whether the clean target is on disk, so you can tell a
   cosmetic typo from a typo-on-a-missing file in one pass.
2. MISSING_LOCAL_FILES — skill-local scripts/references/templates/ paths absent on disk,
   excluding project-relative hints (DEMIURGE/lumen/Desktop/Commander/...).
3. WINDOWS_PATHS — hardcoded `C:\...` (uppercase-drive regex, URL-safe).

## PITFALLS (learned on a live ENI-profile audit, 2026-07-09)

PITFALL A — regex fragments in code look like path refs.
`re.compile(r"['\"](/api/[^'\"]+)['\"]")` yields a bare match `references/.` or
`[^'"]+` that a path regex happily consumes. SYMPTOM: phantom "MISSING_LOCAL_FILE:
scripts/endpoint_consistency_probe.py:23 raw='[^'"]+'". FIX: skip any match containing
regex metacharacters `[]^$*+{}()`:

    REGEX_META = set("[]^$*+{}()")
    if any(c in tgt for c in REGEX_META): continue

PITFALL B — project-relative DEMIURGE paths are NOT skill-local files.
A DEMIURGE-scaffold skill referencing `templates/index.html` next to "USB dashboard/app.py"
points at the USB dashboard repo, not a file shipped in the skill dir. SYMPTOM: phantom
"MISSING_LOCAL_FILE: templates/index.html". FIX: contextual exclusion — if the clean path
ends with `templates/index.html` AND the line contains `USB`/`DEMIURGE`/`dashboard/app.py`,
skip it (it is project-relative by design).

PITFALL C — trailing punctuation must be stripped BEFORE the existence check, and BOTH
forms reported. Stripping gives the clean path; reporting the raw form preserves the exact
typo (so a future patch can locate and fix the literal bad string). Never drop the raw.

PITFALL D — bare `references/.` at end of a prose sentence ("extract from SKILL.md +
references/.") is benign prose, not a broken link. The scanner still emits it as a
`trailing-punct inline` TYPO with `target EXISTS`; treat as low-severity / ignore.

## Companion pairing

Use BOTH for a full skill lint:
- `audit_skill_commands.py <dir>`  -> hermes subcommand REAL/FAKE + Windows + missing (skill-level)
- `audit_skill_refs.py <dir>`      -> linked-path typos + missing + windows (FILE:LINE-level)
Together they cover: fake-command instruction, missing run-step files, copy-paste 404 typos,
and non-portable Windows paths.
