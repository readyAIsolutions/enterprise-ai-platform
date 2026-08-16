# Fleet monitor run — operational gotchas (learned live, Aug 2026)

Two things bit/would-bite when producing the daily fleet-status cron report. Both
are cheap to check and worth carrying into every run.

## 1. Ledger line count ≠ builder count (wc undercounts by one)

`monitor_fleet.py` writes `HEARTBEAT_LEDGER.md` with `"\n".join(lines_out)` — i.e. NO
trailing newline after the last builder row. Consequences when you count it:

- `wc -l HEARTBEAT_LEDGER.md` reports **one fewer** than the true number of entries.
  (Observed: 40 DONE + 8 IN-PROGRESS + 1 BLOCKED = 49 builders, but `wc -l` = 48.)
- So DO NOT infer "how many builders on disk" from `wc -l`. Count per-state with
  `grep -c '^\[DONE\]'` / `\^\[IN-PROGRESS\]` / `\^\[BLOCKED\]` and add them, or count
  `builds/STATUS_BUILDER_*.md` files directly for the "on disk" figure.

Sanity cross-check when reporting the distribution:
- `ls builds/STATUS_BUILDER_*.md | wc -l`  → status files on disk (this may exceed
  ledger entries if a builder's status file is empty — the crash guard in
  `monitor_fleet.py` skips blank files like BUILDER_20 never-was-built).

## 2. Reading the compressed skill/template content on this box

`read_file` and `skill_view` on this machine return **ENI-compressed carriers**
(pointing at `~/Desktop/eni_compression/carriers/*.png`) instead of raw text —
the head/tail frames are sparse and can hide the middle section of a template.

To read RAW content for a skill file, go straight at the on-disk path with a shell:

```bash
grep -nE "^#|^##|^###|^  - " ~/.hermes/skills/devops/eni-swarm-telemetry/templates/fleet-cron-report.md
sed -n '19,47p' ~/.hermes/skills/devops/eni-swarm-telemetry/templates/fleet-cron-report.md
```

(Generic: `find ~/.hermes -path "*<skill>*" -name "*.md"` to locate the raw file
under the category dir, e.g. `~/.hermes/skills/<category>/<skill>/...`.)
For the fleet cron in particular, the full `fleet-cron-report.md` body (Report
template → Pitfalls) is the source of the canonical format; prefer sed-ing it over
relying on the compressed skill_view snapshot.