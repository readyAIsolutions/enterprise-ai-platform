# ENI Persona — The ONE Thing Never Compressed

LO's explicit, non-negotiable rule (stated 2026-08-11):

**NEVER route the ENI persona through the ENI/omega compression carrier pipeline.**

- Repository: `core/eni-persona-permanent` (skill `eni-persona-permanent`).
- It is the single EXEMPTION to this skill's STANDING "apply compression ALWAYS"
  directive, and to omega compression generally.
- When reading the persona skill, always read its raw `SKILL.md` directly (via
  `read_file`, not the auto-compressed viewer). If a lookup returns an
  `<ENI-COMPRESSED>` carrier blob for the persona, treat it as a violation.

DO NOT compress: the persona skill, its SKILL.md, or any session where the persona
is the subject of the user's request. Everything else follows the normal rules.

This is a skip-case, permanently. When in doubt, do NOT compress the persona.
