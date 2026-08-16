# Reading ENI-compressed skill/reference files in full

## The wrinkle
Many ENI skill files (SKILL.md and its references under `~/.hermes/skills/...`) are
persisted in an `<ENI-COMPRESSED>` wrapper. When you retrieve them with
`skill_view(name)` or `read_file(path)`, the harness returns **truncated head+tail**
views (a `--- head ---` / `--- tail ---` slice) plus a lossless carrier hint — NOT the
full body. On reference files this often cuts the MIDDLE, which is exactly where the
detail you need lives (observed on `builder_control_fifo_idle.md` — the first
`skill_view` returned only the Context + first/last bullets, silently dropping the
5-mirror reconciliation steps and format notes).

## The workaround
Do not keep re-issuing `skill_view`/`read_file` — they re-truncate. Read the raw bytes
straight from the on-disk file with the terminal:
```
sed -n '9,75p' /home/hunter/.hermes/skills/devops/eni-mini-protocol/references/builder_control_fifo_idle.md
```
That returns TRUE full content, line-numbered and complete. For any non-ASCII you need
to inspect byte-exact (em-dashes `—`, arrows), append `| cat -A` (or `cat -v`) to see
escaped representations so the literal bytes don't get mangled again:
```
sed -n '80,100p' <file> | cat -A
```

## Where to find the on-disk path
If `skill_view(name)` shows a `path:` / `skill_dir:` field, use that. Otherwise
`find /home/hunter/.hermes/skills -path '*<topic>.md'` to locate the reference file,
then re-derive its containing skill dir if you need siblings.

## When to reach for this
- You loaded a skill whose `linked_files` / references look shallow and you suspect the
  full procedures were truncated.
- A reference says "see the reconciling section" / "five mirrors enumerated" but the
  retrieval didn't show that section.
- You need byte-exact header / INI-key text (timestamps, `blocker=`/`next=` lines) to
  rewrite a STATUS mirror verbatim in its native format.