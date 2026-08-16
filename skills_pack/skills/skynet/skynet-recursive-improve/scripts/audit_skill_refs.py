#!/usr/bin/env python3
r"""Reference-integrity scanner for a Hermes skill dir (sibling to audit_skill_commands.py).

audit_skill_commands.py answers "are the hermes subcommands real?" and "are hardcoded
Windows paths / missing skill-local files present?". This script answers a DIFFERENT
question: "are the LINKED paths inside the skill well-formed and present on disk?" — at
the granularity of FILE:LINE, with the false positives a naive grep produces stripped out.

It catches three defect classes a naive `grep references/|scripts/` misses:
  1. TRAILING-PUNCTUATION TYPOS: a linked path with a trailing period/comma that would
     404 if copy-pasted, e.g. `references/debug-white-screen.md.` — and it REPORTS
     whether the clean (punct-stripped) target EXISTS, so you can tell a cosmetic typo
     from a typo-on-a-missing file.
  2. MISSING_LOCAL_FILES: skill-local scripts/references/templates/ paths that do not
     exist on disk (genuinely missing, NOT project-relative like DEMIURGE/USB paths).
  3. WINDOWS_PATHS: hardcoded C:\... paths non-portable to this Linux host.

False-positive guards (learned the hard way on a live audit):
  * Regex fragments inside `re.compile(r"...")` look like paths (`[^'"]+`,
    `references/.`). Skip any match containing regex metacharacters.
  * Project-relative DEMIURGE/USB references (e.g. `templates/index.html` next to
    "USB dashboard/app.py") are NOT skill-local files — exclude by line context.

Usage:
    python3 audit_skill_refs.py [SKILL_DIR]   # default: resolves real shared skills dir

Prints a per-skill PASS/FAIL board with file:line evidence. READ-ONLY — edits nothing.
"""
import os
import re
import sys

PROJECT_ROOT_HINTS = ("DEMIURGE", "lumen", "demiurge", "Desktop", "Commander",
                      "home/hunter", "run/media")

TRAIL_PUNCT = ".,;:!?"          # trailing punctuation that should not be in a path
LINK_RE = re.compile(r"\]\(([^)]+)\)")                 # markdown link target
BARE_RE = re.compile(r"(?<![`\w/])(?:references|scripts|templates|assets)/[A-Za-z0-9_./-]+")
WIN_RE = re.compile(r"(?<![A-Za-z])[A-Z]:[\\/][\\/A-Za-z0-9_ .-]+")
# Matches containing these are regex/code fragments, not path references.
REGEX_META = set("[]^$*+{}()")


def _default_skills():
    """Resolve the real shared skills dir even under an ENI profile HOME override.

    Under an isolated profile, HOME is redirected to ~/.hermes/profiles/<name>/home,
    so a naive expanduser('~/.hermes/skills') points nowhere. Walk back up.
    """
    home = os.path.expanduser("~")
    if ".hermes/profiles" in home:
        real = os.path.abspath(os.path.join(home, "..", "..", "..", "skills"))
        if os.path.isdir(real):
            return real
    d = os.path.join(home, ".hermes", "skills")
    return os.path.abspath(d) if os.path.isdir(d) else os.path.expanduser("~/.hermes/skills")


def find_skill_dirs(base):
    dirs = []
    for root, _, files in os.walk(base):
        if "SKILL.md" in files:
            dirs.append((os.path.relpath(root, base), root))
    return sorted(dirs)


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else _default_skills()
    print(f"Scanning skill tree for reference integrity: {base}\n")

    issue_skills = 0
    for name, d in find_skill_dirs(base):
        winpaths = set()
        missing = []     # (rel, ln, raw, clean, why)
        typos = []       # (rel, ln, raw, clean, note)
        for root, _, files in os.walk(d):
            for f in files:
                p = os.path.join(root, f)
                try:
                    lines = open(p, errors="ignore").read().splitlines()
                except Exception:
                    continue
                rel = os.path.relpath(p, d)
                for ln, line in enumerate(lines, 1):
                    for w in WIN_RE.findall(line):
                        winpaths.add(w)
                    # markdown link targets
                    for m in LINK_RE.finditer(line):
                        tgt = m.group(1).strip()
                        if any(c in tgt for c in REGEX_META):
                            continue
                        selflag = False
                        clean = tgt
                        while clean and clean[-1] in TRAIL_PUNCT:
                            selflag = True
                            clean = clean[:-1]
                        if selflag:
                            typos.append((rel, ln, tgt, clean, "trailing-punct in link"))
                        if clean and not clean.startswith(("http://", "https://", "/")):
                            cand = os.path.join(d, clean)
                            if not os.path.exists(cand) and not any(h in clean for h in PROJECT_ROOT_HINTS):
                                missing.append((rel, ln, tgt, clean, "link-target missing"))
                    # bare inline references
                    for m in BARE_RE.finditer(line):
                        tgt = m.group(0)
                        if any(c in tgt for c in REGEX_META):
                            continue
                        clean = tgt
                        pflag = False
                        while clean and clean[-1] in TRAIL_PUNCT:
                            clean = clean[:-1]
                            pflag = True
                        if pflag:
                            typos.append((rel, ln, tgt, clean, "trailing-punct inline"))
                        if clean and not os.path.exists(os.path.join(d, clean)) and not any(h in clean for h in PROJECT_ROOT_HINTS):
                            # project-relative DEMIURGE/USB dashboard path (not skill-local)
                            if clean.endswith("templates/index.html") and ("USB" in line or "DEMIURGE" in line or "dashboard/app.py" in line):
                                continue
                            missing.append((rel, ln, tgt, clean, "bare-ref missing"))

        flagged = bool(winpaths or missing or typos)
        if flagged:
            issue_skills += 1
        print(f"== {name}")
        if winpaths:
            print(f"   WINDOWS_PATHS (non-portable): {sorted(winpaths)}")
        if missing:
            for rel, ln, tgt, clean, why in missing:
                print(f"   MISSING_LOCAL_FILE: {rel}:{ln}  raw='{tgt}'  clean='{clean}'  ({why})")
        if typos:
            for rel, ln, tgt, clean, note in typos:
                exists = os.path.exists(os.path.join(d, clean))
                e = "target EXISTS" if exists else "target MISSING"
                print(f"   TYPO: {rel}:{ln}  raw='{tgt}'  ->clean='{clean}'  ({note}; {e})")
        if not flagged:
            print("   OK (no issues)")
        print()

    print(f"SUMMARY: {issue_skills} skill(s) with potential issues out of "
          f"{len(find_skill_dirs(base))} scanned.")


if __name__ == "__main__":
    main()
