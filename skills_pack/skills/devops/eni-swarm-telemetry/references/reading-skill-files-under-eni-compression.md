# Reading this skill's files under the ENI-COMPRESSION overlay

## Symptom
When you `skill_view(name)` (or `read_file` a skill path) in a session where the
ENI compression overlay is active, the tool result comes back wrapped in
`<ENI-COMPRESSED ratio=…x carrier=…>` with only a truncated `--- head ---` /
`--- tail ---` fragment. The full template/script body is NOT readable through
the normal skill tool — the ratio shows (~2x on templates, ~7-9x on dir listings)
that the real content is losslessly persisted to the carrier PNG, not inline.

Observed concretely on `templates/fleet-cron-report.md` — the bare `## Report
template` section header was visible in the head, but the body was cut.

## Fix — read the file directly on disk instead
The skill files themselves are NOT compressed on disk. Bypass the wrapper:
- Locate the skill dir: `~/.hermes/skills/devops/eni-swarm-telemetry/`
  (list via `search_files(target='files')` or `ls` to confirm).
- For a specific file, `read_file` the absolute on-disk path
  (`/home/hunter/.hermes/skills/<category>/<name>/templates/…`).
- To recover a truncated template's structure quickly, extract just the
  section headers with grep rather than the whole body, e.g.
  `grep -nE '^#{1,3} |^\*\*|^> \*\*' <file>` — headers are short enough to come
  back legible even when a full dump is compressed.

## Whitespace whitespace
- The skill front-matter `description` and the `linked_files` dict DO come back
  intact in the head/tail — use them as the canonical map of what refs/templates/
  scripts exist, then read each actual file on disk.
- `skill_view` with a `file_path` still uses the same compressed channel; when
  the body matters, always go to disk.