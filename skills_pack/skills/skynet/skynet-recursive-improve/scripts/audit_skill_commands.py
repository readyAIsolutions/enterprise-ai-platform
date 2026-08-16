#!/usr/bin/env python3
"""Audit a Hermes skill's referenced commands, paths, and local files.

For every `hermes <sub>` mention inside a skill dir (SKILL.md + templates +
references + scripts), classify the subcommand as REAL (exists in `hermes
--help`) or INVALID (not a real subcommand -> usually PROSE, e.g. "a hermes
agent", "hermes errors out"). Run this BEFORE trusting or patching any skill
that drives the CLI.

It ALSO catches portability/integrity defects that a naive grep misses:
  * Windows-style absolute paths (C:\\Users\\... / C:/Users/...) -> will FAIL on
    this Linux host. The skynet-* skills were authored on LO's Windows box and
    still hardcode these.
  * Referenced skill-local files (scripts/ references/ templates/) that do NOT
    exist on disk (genuinely missing, as opposed to project-relative paths the
    skill intentionally points elsewhere).
  * Trailing-punctuation TYPOS on a linked path (e.g. "references/x.md.") — the
    clean target usually EXISTS, so it is a cosmetic copy-paste bug, not a
    missing file. Reported separately as TYPO_TRAILING_PUNCT.

Usage:
    python3 audit_skill_commands.py [SKILL_DIR]   # default: ~/.hermes/skills

Prints a per-skill table. INVALID entries are flagged "(likely PROSE)" because a
naive grep calls them "broken commands" but they are descriptive phrases, not
invocations. Confirm by reading the surrounding sentence.

NOTE: the NATIVE `hermes skills audit` / `hermes skills check` subcommands exist
but ONLY audit hub-installed skills (skills.sh集市). They report "No hub-installed
skills to audit" for the local ~/.hermes/skills tree, so this script remains the
tool for auditing the local skills dir.
"""
import os
import re
import subprocess
import sys

# Project-relative roots a skill may legitimately point at (NOT skill-local, so
# a missing scripts/X.py under them is NOT a skill defect).
PROJECT_ROOT_HINTS = ("DEMIURGE", "lumen", "demiurge", "Desktop", "Commander",
                      "home/hunter", "run/media")


def _default_skills():
    """Resolve the real shared skills dir even under an ENI profile HOME override.

    When Hermes runs an agent under an isolated profile, HOME is redirected to
    ~/.hermes/profiles/<name>/home, so a naive expanduser("~/.hermes/skills")
    points at a non-existent path and the audit silently finds zero skills. Walk
    back up to the real ~/.hermes/skills in that case.
    """
    home = os.path.expanduser("~")
    if ".hermes/profiles" in home:
        real = os.path.abspath(os.path.join(home, "..", "..", "..", "skills"))
        if os.path.isdir(real):
            return real
    d = os.path.join(home, ".hermes", "skills")
    return os.path.abspath(d) if os.path.isdir(d) else os.path.expanduser("~/.hermes/skills")


DEFAULT = _default_skills()


def hermes_valid_subs():
    """Return the set of real `hermes` subcommands by parsing `hermes --help`."""
    out = subprocess.run(["hermes", "--help"], capture_output=True, text=True)
    text = out.stdout + out.stderr
    m = re.search(r"\{([^}]*)\}", text)          # usage line: {chat,model,...,logs}
    if m:
        return set(t.strip() for t in m.group(1).split(",") if t.strip())
    return set(re.findall(r"\b([a-z][a-z-]+)\b", text))


def is_subcommand(sub, valid):
    if sub in valid:
        return True
    r = subprocess.run(["hermes", sub, "--help"], capture_output=True, text=True)
    return "invalid choice" not in (r.stdout + r.stderr)


def find_skill_dirs(base):
    dirs = []
    for root, _, files in os.walk(base):
        if "SKILL.md" in files:
            dirs.append((os.path.relpath(root, base), root))
    return sorted(dirs)


def windows_paths(txt):
    """Return absolute Windows drive paths (C:\\... or C:/...) found in text.

    Requires an UPPERCASE drive letter (C:, D:, ...) so we DON'T false-match
    URL schemes that share the `x://` shape (https:// -> s://, http:// -> p://,
    magnet:// -> t://, steam:// -> m://). Windows absolute paths always use a
    capital drive letter, so this cleanly separates the two.
    """
    return set(re.findall(r"(?<![A-Za-z])[A-Z]:[\\/][\\/A-Za-z0-9_ .-]+", txt))


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    valid = hermes_valid_subs()
    print(f"Real hermes subcommands ({len(valid)}): {sorted(valid)}\n")
    print(f"Auditing hermes refs under: {base}\n")

    issue_skills = 0
    for name, d in find_skill_dirs(base):
        subs = set()
        localrefs = set()      # ACCUMULATED across every file (bug fixed: was reassigned per-file)
        winpaths = set()
        for root, _, files in os.walk(d):
            for f in files:
                if not f.endswith((".md", ".sh", ".py")):
                    continue
                try:
                    txt = open(os.path.join(root, f), errors="ignore").read()
                except Exception:
                    continue
                for s in re.findall(r"hermes\s+([a-z][a-z-]+)", txt):
                    subs.add(s)
                localrefs |= set(re.findall(
                    r"(?:scripts|references|templates)/[A-Za-z0-9_./-]+", txt))
                winpaths |= windows_paths(txt)

        real = sorted(s for s in subs if is_subcommand(s, valid))
        invalid = sorted(s for s in subs if not is_subcommand(s, valid))
        inv = f"  INVALID={invalid} (likely PROSE)" if invalid else ""

        # Genuinely-missing / typo'd skill-local files (exclude project-relative hints).
        # STRIP trailing [.,;:!?] (e.g. "scripts/x.sh.") to separate a cosmetic typo from a
        # real absence; skip regex-code fragments and bare directory mentions ("references/.").
        TRAIL = ".,;:!?"
        REGEX_META = set("[]^$*+(){}")
        missing_local, typos = [], []
        for r in sorted(localrefs):
            if any(c in r for c in REGEX_META):
                continue
            clean = r
            while clean and clean[-1] in TRAIL:
                clean = clean[:-1]
            if clean.endswith("/"):
                continue  # directory mention (e.g. "references/"), not a file reference
            if clean != r:
                if os.path.exists(os.path.join(d, clean)):
                    pass  # trailing punct is sentence punctuation, NOT a path typo (clean target exists)
                elif not any(h in clean for h in PROJECT_ROOT_HINTS):
                    missing_local.append(r)   # typo AND genuinely absent
                continue
            if not os.path.exists(os.path.join(d, r)) and not any(h in r for h in PROJECT_ROOT_HINTS):
                missing_local.append(r)
        loc = (f"  MISSING_LOCAL_FILES={sorted(set(missing_local))}"
               if missing_local else "")
        typ = (f"  TYPO_TRAILING_PUNCT={sorted(set(typos))}"
               if typos else "")

        # Windows paths are always a portability defect on this Linux host.
        win = (f"  WINDOWS_PATHS={sorted(winpaths)}"
               f" (NON-PORTABLE to Linux host)" if winpaths else "")

        # Report file/path integrity EVEN WHEN a skill has NO hermes subcommands.
        # Bug fixed (2026-07-09, ENI3_w1): the old early `continue` hid MISSING_LOCAL_FILES
        # for such skills -- e.g. devops/desktop-app-ship-audit's missing
        # scripts/capture_assets.sh was silently skipped because it has no hermes refs.
        flag = "  <<< ISSUE" if (invalid or missing_local or winpaths or typos) else ""
        if not (subs or winpaths or missing_local or typos):
            print(f"  {name:44s} no hermes refs")
            continue
        if flag:
            issue_skills += 1
        print(f"  {name:44s} real={real}{inv}{loc}{typ}{win}{flag}")

    print(f"\nSUMMARY: {issue_skills} skill(s) with potential issues "
          f"(INVALID hermes refs / missing local files / Windows paths / trailing-punct typos).")
    print("  INVALID = prose, not real commands (verify by reading the sentence).")
    print("  WINDOWS_PATHS = hardcoded C:\\... paths that fail on this Linux box;")


if __name__ == "__main__":
    main()
