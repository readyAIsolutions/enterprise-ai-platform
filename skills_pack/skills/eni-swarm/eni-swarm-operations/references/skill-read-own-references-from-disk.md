# Reading this skill's own references fully (ENI-COMPRESSED bypass)

When interpreting fleet-monitor cron results, you often need the full text of this
skill's references (e.g. fleet-staleness-interpretation.md, fleet-monitor-cron-
deliverable.md, fleet-monitor-concise-summary.md). On this box that BACKFIRES:

## The problem
`skill_view(name='eni-swarm-operations')` and `skill_view(..., file_path='references/*.md')`
return EVERYTHING wrapped in `<ENI-COMPRESSED>` blocks (head + tail elided), so you lose
the middle of the decision rules you actually need — same SNAFU documented in
fleet-monitor-concise-summary.md, but for the SKILL'S OWN files, not builder files.
This happens even when the reference is short (a few KB).

## Fix: bypass skill_view — `open()` the file directly
The skill's category subdir is **`eni-swarm/`** (not obvious). On-disk root:

```
~/.hermes/skills/eni-swarm/eni-swarm-operations/references/
```

Read any reference in full with plain Python `open()`, which is NOT compressed:

```python
sk = "/home/hunter/.hermes/skills/eni-swarm/eni-swarm-operations/references"
with open(os.path.join(sk, "fleet-monitor-cron-deliverable.md")) as f:
    print(f.read())     # full text, no compression
```

Also run/verify the pass the same way — see `scripts/fleet_monitor_pass.py` for the
reference run pattern, and read_file override note in fleet-monitor-concise-summary.md.

## Pitfall
Do NOT reconstruct file paths by number (zero-padding gotcha also applies to builder
STATUS files — BUILDER_5.md != BUILDER_05.md). For this skill's references, the paths
are exact and stable; just hardcode the reference name as above.