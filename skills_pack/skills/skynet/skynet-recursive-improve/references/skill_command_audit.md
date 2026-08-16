# Skill Command Audit — procedure & pitfalls

Reusable method for verifying a Hermes skill's referenced commands actually exist,
and for catching portability/integrity defects. Owned by `skynet-recursive-improve`
via `scripts/audit_skill_commands.py`.

## Procedure
1. Get the REAL subcommand list: `hermes --help` (the `{...}` usage brace).
2. For every `hermes <sub>` mention in a skill (SKILL.md + scripts/templates/references),
   run `hermes <sub> --help`. Exit 0 -> REAL; "invalid choice" -> does NOT exist.
3. Classify: REAL = usable; INVALID that sits mid-sentence ("hermes errors out") = PROSE,
   leave it (do NOT "fix" it into a command).
4. Confirm the proven ENI runner is `~/.local/bin/eni_agent_term.py` (also `eni` =
   `hermes -p eni`) — there is NO `hermes agent run` / `hermes run` / `hermes container`
   / `hermes terminal` / `hermes errors` subcommand.
5. Re-run the local scanner for the whole tree:
   `python3 ~/.hermes/skills/skynet/skynet-recursive-improve/scripts/audit_skill_commands.py ~/.hermes/skills`

## Pitfall — Windows-path scan vs URLs
To flag hardcoded `C:\Users\...` (Linux-portability defects), do NOT use
`[A-Za-z]:[\\/]` — it false-matches URL schemes (`https://`->`s://`, `http://`->`p://`,
`magnet://`->`t://`). Require an uppercase drive letter + negative lookbehind:
    re.findall(r"(?<![A-Za-z])[A-Z]:[\\/][\\/A-Za-z0-9_ .-]+", text)
Windows absolute paths always use a capital drive letter, so this separates
`C:\Users` from `https://` cleanly. The 4 `skynet-*` skills (authored on LO's Windows
box) hardcode `C:\Users\Hunter\Desktop\...` and fail if copy-pasted on Linux; they are
gated by a `caveman-stack`/`skynet` package pre-flight (package not installed here),
but the raw `cd C:\...` blocks are NOT gated.

## Pitfall — accumulate sets across os.walk with `|=`, not `=`
When collecting matches over every file in a skill dir, use `localrefs |= set(...)`;
reassigning `localrefs = set(...)` inside the loop keeps only the LAST file's matches
(silent missing-file false negative).

## Pitfall — native audit is hub-only
`hermes skills audit`/`check` only cover hub-installed skills (skills.sh集市) and return
"No hub-installed skills to audit" for the local `~/.hermes/skills` tree. Use the local
script for local skills.

## Pitfall — profile HOME override
Under an isolated profile (`eni`), `HOME`->`~/.hermes/profiles/<name>/home`, so a literal
`~/.hermes/skills/...` path does not exist. Use the absolute `/home/hunter/.hermes/skills/...`
or pass no arg (script auto-resolves via `_default_skills()`).
