# Reading full content of ENI-compressed skills / references

## Problem
`skill_view(name=...)` on an ENI-compressed skill returns ONLY a truncated
head/tail window (wrapped in `<ENI-COMPRESSED ...>` metadata) — the middle
sections of SKILL.md and its `references/*.md` files are elided. This hides
the exact reconcile steps, mirror path lists, and pitfalls you need to execute
the protocol correctly. The full content is losslessly persisted to a carrier
PNG but is not convenient to unpack mid-task.

## Fix (no decompression needed)
The raw, uncompressed markdown still lives on disk under the skill's directory.
Read it directly from the filesystem at offsets to recover the middle sections:

```bash
# locate the skill dir (example):
find /home/hunter/.hermes/skills -iname 'eni-mini-protocol' -type d
# or locate a specific reference file:
find /home/hunter/.hermes/skills -iname 'builder_control_fifo_idle.md'
```

Then `read_file` the raw file with `offset`/`limit` to page through the middle
that `skill_view` elided. Repeat with successive offsets until you have the
full body (e.g. offset=25 then offset=37 for a ~100-line reference). This is
faster and more reliable than decoding the carrier.

## Pitfall — the file content is already plain markdown, not the compressed JSON
The on-disk `SKILL.md` / `references/*.md` are the real readable text. Nothing
about the file itself is altered by the compression layer; only the `skill_view`
tool output is truncated. So direct `read_file` gives you clean, complete content.

## When you'll need this
Any time you load an ENI-compressed skill (species under `eni-*`, `skynet-*`,
`demiurge-*`, etc.) and the head/tail window is not enough to act — especially
protocol skills where the executable steps and path lists live in the middle of
the references. Do not guess at the omitted middle; read the files.