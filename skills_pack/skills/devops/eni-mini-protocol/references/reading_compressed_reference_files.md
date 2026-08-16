# Reading ENI-COMPRESSED skill files in full

## Context
The ENI skills (e.g. `eni-mini-protocol`, `eni-build`) and their `references/*.md`
files are stored as **ENI-COMPRESSED carriers**. When you read one via
`skill_view(name)` or `read_file(path)`, you get back a JSON envelope showing only
the **head** (first ~dozen lines) and the **tail** (last few lines) of the file,
with the entire middle elided behind `--- head ---` / `--- tail ---` markers and a
`carrier=...png` pointer.

## Pitfall: the critical steps live in the elided middle
The compressed envelope is NOT the full document. The most important procedural
content is often ONLY in the middle that gets elided. In the BUILDER_37 idle pass
(Aug 2026), `references/builder_control_fifo_idle.md` showed the intro ("don't cat
a FIFO") and the tail (sibling-concurrency advice) — but the actual
**mirror-reconciliation procedure** (the 5 known STATUS paths, native-format rules,
the broad-glob `find` advice) was entirely in the elided middle. Had I trusted the
compressed envelope alone, I would have run an incomplete idle pass.
Do NOT assume the head+tail is sufficient.

## How to get the full text
Re-read the raw file with `read_file(path, offset=..., limit=...)` to page through
the middle, e.g.:
- `read_file(<skilldir>/references/builder_control_fifo_idle.md, offset=13, limit=55)`
- continue with `offset=68` (etc.) until you reach total_lines.

The skill directory lives under ~/.hermes/skills/<category>/<name>/ (e.g.
`/home/hunter/.hermes/skills/devops/eni-mini-protocol/references/...`).
Find the raw path with `search_files` if needed.

## Pitfall (verified Aug 09 2026): the compression threshold is an OUTPUT-SIZE cutoff, not a file-length cutoff
Do NOT assume slice length alone saves you. This session, the ENI output-compression
layer re-compressed even MODERATE terminal slices:
- `terminal("sed -n '1,60p' <path>")`  (60 lines)  -> returned PLAIN text fine.
- `terminal("sed -n '40,113p' <path>")` (74 lines) -> came back compressed (head+tail only).
- `terminal("sed -n '61,149p' <path>")`(89 lines) -> came back compressed (head+tail only).
The cutoff sits around ~60 lines of output; anything punching out much more gets
wrapped in a carrier again regardless of the requested byte range. Also, `read_file`
with NO offset (whole file) returns the compressed envelope, so paging with
`read_file(offset=..., limit=...)` (small pages, e.g. limit=55) is the RELIABLE way
to read the middle, and `sed` slices must stay small (~<=50-60 lines). When a `sed`
slice comes back as a carrier, it did NOT necessarily return plain text — narrow the
range and retry rather than trusting head+tail of the slice.

## Belt-and-suspenders
Before acting on any compressed skill/reference, page through the raw file until
you have seen every line (head + middle + tail). Re-verify the final HEAD of anything
you write afterwards, exactly as the mirror-reconciliation protocol demands.
