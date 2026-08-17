# Interpretable Context Methodology (ICM) — Integration Spec

Source: `ICM_Enterprise_Integration_Spec.docx` (Hunter / Demiurge, draft v1).
**LO directive: this is the DEFAULT structure for every skill added to Demiurge / Enterprise.**

ICM is the internal *discipline layer* for how each individual agent task is
structured AFTER Hermes routes it. It is NOT a replacement for the
orchestration/swarm layer.

## Where it fits (3 integration points, priority order)
1. **Prompt Engineering / Skill Layer (primary)** — every task is backed by a
   markdown instruction file in a NUMBERED STAGE FOLDER, not an inline prompt.
   Mechanical work (formatting, API calls, file conversion, validation) is
   offloaded to a script beside the markdown, not left to the model.
2. **Context Compression** — progressive disclosure: load only the stage's
   markdown, not full context. Cuts tokens per call and stops swarm agents from
   re-reading unneeded context.
3. **Standardized Skill Format Across Projects** — one folder/markdown/script
   convention across Aurora, Marlin, Detective, Demiurge → faster to build,
   audit, portable.

## Division of labor: ICM vs Swarm
- **ICM** governs sequential, single-agent, human-reviewed, deterministic work
  where predictability > concurrency.
- **Swarm/Hermes** governs concurrent multi-agent reasoning (cross-check/debate).
- Do NOT use ICM as a substitute for swarm, and do NOT use swarm where a
  deterministic script would do. Enterprise needs both.

Reference table from spec:
- Aurora: 01_intake / 02_compliance_check / 03_citation_verify (deterministic,
  auditable, client-facing) + scripts; reasoning goes to swarm layer.
- Marlin: 01_image_intake / 02_trellis / 03_blender / 04_cad_export (sequential
  reviewed pipeline) + build.js/pandoc; compliance to swarm.
- Detective: parallel generation to swarm; ops 01_deploy/02_bugfix/03_verify.

## Standard folder template (apply to EVERY new skill)
```
project/
├── 00_master.md            ← table of contents; tells Hermes which folder to activate
├── 01_intake/instructions.md + scripts/
├── 02_research/instructions.md + scripts/
├── 03_drafting/instructions.md + scripts/
├── 04_verification/instructions.md + scripts/
└── 05_output/instructions.md + scripts/
```
`00_master.md` is the ONLY file Hermes needs to read to know which numbered
folder to activate for a task — it holds the MAP, not the details. Each stage
folder is self-contained: one markdown (role, inputs, definition of good
output) + a `scripts/` dir for deterministic work.

## Adopted conventions in this repo
- Module skills live at `skills_pack/skills/eni-modules/<module>/` (and mirror
  to `~/.hermes/skills/eni-modules/<module>/`) in ICM form: `00_master.md` +
  numbered `0N_<stage>/instructions.md` (+ `scripts/` where mechanical work
  exists).
- Root task map: `docs/ICM_00_master.md` maps task -> module -> stage.
- Module *capability* ordering: `data/build/module_catalog.json` +
  `MODULE_CATALOG.md` (P1 Knowledge / P2 Agent Workflow / P3 Build Quality /
  P4 Domain). ICM stages are the *task-flow* axis layered on top.
