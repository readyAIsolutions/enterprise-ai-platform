---
name: office-doc-generation
description: "Generate polished Word (.docx) and PDF documents — resumes, cover letters, reports, forms — programmatically on a Linux desktop host. Covers the reliable python-docx + LibreOffice headless pipeline for the DOCX, the PEP 668 venv workaround, and content-cleanup conventions for resume/CL tasks. CRITICAL: when the user wants the PDF to look DIFFERENT from a Word doc (says 'make it look professional not like a doc' / 'look different'), do NOT export the DOCX — build it directly with ReportLab as a TWO-COLUMN navy-sidebar resume (the accepted layout; the single-column accent-bar+callout look was rejected as 'ugly'). Also covers the mandatory visual PDF defect-check (vision models summarize and skip defects — crop the bottom strip). Use when the user pastes resume/CV/letter text and says 'fix it up / turn it into a doc and pdf', or asks for any formatted .docx/.pdf."
---

# office-doc-generation

Generate formatted Office docs (DOCX) and their PDF twins on a Linux desktop. Primary
use case seen so far: a user pastes a rough resume/CV and wants it cleaned, re-structured,
and shipped as both `.docx` and `.pdf` onto their Desktop.

## When to use
- User pastes resume / CV / cover letter / bio text and says "fix this up", "make it clean",
  "turn it into a document", "also make a pdf".
- Any task to produce a structured `.docx` or `.pdf` from text on this host.
- Do NOT use for shipping Python apps (that's python-app-packaging / linux-appimage-packaging)
  or web dashboards.

## Pipeline (the reliable path on this box)
1. **python-docx is NOT preinstalled and pip is PEP 668 locked.** Do NOT `pip install`
   bare — it fails with "externally-managed-environment". Instead create a throwaway venv:
   ```
   python3 -m venv /tmp/venv_docx
   /tmp/venv_docx/bin/pip install python-docx
   /tmp/venv_docx/bin/python build.py
   ```
   The venv is ephemeral; that's fine. (If you ever need it to persist, the venv lives in
   /tmp and dies on reboot — recreated per session is acceptable.)
2. **Build the .docx with python-docx** (see references/layout_primitives.md for the
   reusable helper functions: name header, centered contact line, section title with
   bottom border, summary paragraph, bullet list with bold-lead split, job block with
   right-aligned date tab). Use `Calibri` 10.5pt base, an accent RGBColor for headers.
3. **Convert to PDF with LibreOffice headless** (soffice is preinstalled; no sudo needed):
   ```bash
   cd /home/hunter/Desktop && soffice --headless --convert-to pdf \
       --outdir /home/hunter/Desktop Hunter_Name_Resume.docx
   ```
   This produces a valid 1.7 PDF. Verify with `file *.pdf` (expect "PDF document, version 1.7").
   NOTE: do NOT try `pandoc`/`wkhtmltopdf` unless soffice is missing — soffice is the
   lowest-friction path here and preserves fonts/layout best.

## Designed PDF path (when the user wants it to NOT look like a Word doc)
If the user says "make it look more professional than a doc", "look different", or otherwise
signals they want a DESIGNED resume (not a printed Word file), do NOT just export the DOCX.
LibreOffice export preserves the document semantics and STILL READS AS A WORD LAYOUT — the
user explicitly rejected that ("pdf still looks ugly as hell" on a soffice-exported doc).
Build the PDF directly with **ReportLab** for real layout control.

### DEFAULT designed layout: TWO-COLUMN with a LIGHT-BLUE sidebar (dark text)
This is the layout the user ACCEPTED after several rejected iterations. Use it as the default
for resumes:
- `pip install reportlab` into the same `/tmp/venv_docx` (reportlab 5.x works, no sudo).
- Two `Frame`s on one `PageTemplate`: a LEFT sidebar `Frame` (full height) and a RIGHT main
  `Frame`. Paint the sidebar background via the `onPage` hook `canv.rect(0,0,LM+SIDE_W,PH)`.
- **Sidebar background = LIGHT blue (`#cfe0f2`), sidebar text = DARK (`#0d2236` body,
  `#0b3d6b` accent).** This is what the user can actually read. (The dark-navy sidebar with
  white/dim text was rejected repeatedly as "can't read it / see-through".)
- **CRITICAL layout rule — keep the sidebar SHORT so it fits its frame.** Put ONLY name + role
  + contact + Technical Skills + Self-Taught Tech in the sidebar. Put PROFESSIONAL SUMMARY +
  EXPERIENCE + EDUCATION + REFERENCES in the RIGHT main column. If you instead cram
  summary/references/education into the sidebar it OVERFLOWS and leaks into the main frame (see
  the "Sidebar frame overflow" pitfall — this is the exact bug that produced "missing words").
- Main column: job title + right-aligned dates as a 2-col `Table`, blue employer line, bullets;
  then Education bullets; then References as a 2-col name/number `Table`.
- **LEGIBILITY IS THE #1 REJECTED-DESIGN TRIGGER.** The user said "pdf still looks ugly as hell"
  then "can barely read some shit on the pdf". Two concrete causes to AVOID:
  (a) **Sidebar bullet lead text must be BRIGHT WHITE (`#ffffff`), NOT dim light-blue (`#9fc0e0`).**
      A dim lead color on navy is the exact thing that read as "barely readable" — use white for
      both the bold lead AND the bullet body in the sidebar.
  (b) **Body fonts must stay >=9pt.** The earlier 8.4-8.6pt sidebar / 8.9pt main was called
      unreadable. Use ~9.1-9.6pt sidebar body and ~9.1-9.6pt main bullets; name 20pt, section
      heads 11pt. Do NOT go below 9pt anywhere on the page.
  (c) **Sidebar TEXT COLOR on navy was STILL called "can't read it / see-through" even at white.**
      The reliable fix the user accepted: make the sidebar BACKGROUND a LIGHT blue
      (`#cfe0f2`) with DARK navy text (`#0d2236`) for the body and a DEEP blue (`#0b3d6b`)
      for accent blocks (self-taught/references/education). Dark-on-light is the only thing
      this user finds reliably readable — do NOT go back to white/dim-blue text on a dark
      navy sidebar for him. (If a future user wants the dark-navy sidebar, keep text pure
      white `#ffffff`, never the dim `#9fc0e0`.)
- **Force-1-page by trimming SPACING, not fonts.** When content spills to a near-empty page 2
  (only the last job's tail), do NOT shrink fonts below the >=9pt floor. Instead: reduce margins
  (0.55->0.45in), reduce `spaceBefore` on sidebar heads (10->7), reduce job-block `Spacer` (4->3),
  and reduce bullet `sb` trailing space (0.8->0.5). This recovers the overflow while staying
  readable. (User accepted "shrink fonts slightly" once, but spacing-first is the safer default —
  if you must shrink, only ~0.3-0.5pt and re-verify legibility.)
- This split fills BOTH columns and avoids the failure modes seen: (a) sidebar text getting
  CUT OFF / leaking into the main column, and (b) a near-empty trailing page / big bottom gap.
  If the sidebar overflows, the fix is to move content OUT of the sidebar into the main column
  (summary/education/references belong in the main column) — NOT to cram more into the sidebar.
- Keep the DOCX too (editable source) — deliver BOTH, regenerated, for any content edit.
- ReportLab emits PDF 1.4 (not 1.7) — that's fine; `file` still reports "PDF document".
- See references/reportlab_resume_template.py for the complete working two-column builder
  (navy sidebar + experience column, 1 page, >=9pt, white sidebar leads). Copy and edit the
  CONTENT block per user.

### Why NOT the accent-bar + callout-box single-column look
The earlier design (top accent `HRFlowable` bar, centered name, a shaded `Table` callout box
for "Personal Skills", everything single-column) looked "like a Word doc" to the user and was
rejected. Do not default to it. The two-column sidebar is the accepted standard.

## Iterative edit loop (common — user sends several small fixes)
Resumes get revised in rounds: "fix the date", "add a section", "remove expired certs",
"add Pi/Arduino". Don't rebuild from scratch each time — keep the Python builder script
(e.g. /tmp/build_resume.py) and just patch + re-run:
```bash
# 1. edit the builder (patch the string/date/bullet)
# 2. regenerate docx
/tmp/venv_docx/bin/python /tmp/build_resume.py
# 3. regenerate pdf in place
cd /home/hunter/Desktop && soffice --headless --convert-to pdf --outdir /home/hunter/Desktop Hunter_Name_Resume.docx
# 4. VERIFY the change actually landed in the PDF (see Pitfalls — text-layer grep)
```
The DOCX and PDF overwrite in place; the user expects the SAME two files updated, not new
numbered versions.

## Resume / CV cleanup conventions (embed these — they are the value-add)
When given rough resume text, the user expects transformation, not transcription:
- **Fix date order & typos.** Original pastes often have backwards chronology or a
  future/"Present" end date that's actually a typo (e.g. "July 20th" with no year, or a
  job listed AFTER a later-dated job). Reorder to reverse-chronological and normalize to
  `Mon YYYY – Mon YYYY` / `Mon YYYY – Present`. Flag any assumption you made to the user
  (e.g. "treated Epoxy Empire as current job — tell me if wrong").
- **Tighten the summary** into one strong paragraph; drop run-on sentences.
- **Group skills** into scannable bullet clusters (Design, Mechanical, Safety, Equipment…).
- **Expand thin job blurbs** into 2–4 real, quantified bullets. Pull concrete specifics
  already present (duct sizes, hour counts, zero-incident record) and surface them.
- **Remove EXPIRED credentials, don't just list them.** If the user says a cert lapsed
  (e.g. "First Aid and H2S Alive expired"), DELETE it from the list — do NOT keep it with
  a "(expired)" tag. Keep only currently-valid certs. This applies to any credential the
  user says is no longer active.
- **Add a "Personal / Self-Taught" section when the user has non-formal technical skills.**
  Many users (esp. hands-on tradespeople who tinker) have real skills with no classroom
  behind them: custom PC building, 3D printing, Raspberry Pi / Arduino, Linux OS install &
  maintenance, local AI (llama.cpp), self-hosting, scripting/automation. Surface these as a
  distinct section (after Education, before References) with a one-line intro that frames
  them as self-directed competency, not bragging. Draw items from what the user has actually
  done — do not invent. If unsure what to include, propose a few from the user's known
  activity and let them trim.
- **Keep all real facts verbatim**: every job title, company, location, cert, and reference
  number must be preserved exactly. Never invent employers, dates, or credentials.
- **Structure / layout**: for the DESIGNED PDF use the two-column navy-sidebar layout
  (see references/reportlab_resume_template.py and the STRUCTURE block in
  references/resume_cleanup_checklist.md). For the DOCX editable source, a clean
  single-column version is acceptable. See the "Designed PDF path" section above.

## Output location & naming
- Save to `/home/hunter/Desktop/` by default (user explicitly wants Desktop delivery).
- Filename: `Hunter_Laidlaw_Resume.docx` / `.pdf` (or `<FirstName>_<LastName>_<Doc>.docx`).
- Deliver BOTH docx and pdf in the same run; the user wants "a doc and also a pdf".

## Pitfalls
- **`/mnt` can be read-only** on this host (an exfat volume got mounted `ro` there and
  locked the mountpoint). Always create a fresh mountpoint like `/media/Backup` for drives;
  do NOT assume `/mnt` is writable. (This is a host-state quirk, not a rule — just don't
  be surprised if `mkdir /mnt/X` fails with "Read-only file system".)
- **soffice needs the file by name in the cwd** — run the convert command from the dir
  containing the .docx, or pass the full path.
- **python-docx tab stops**: use `paragraph_format.tab_stops.add_tab_stop(Inches(6.9),
  WD_ALIGN_PARAGRAPH.RIGHT)` for right-aligned dates; a plain `\t` alone won't align.
- **Don't over-format**: user prefers clean/legible, not flashy. Deep-blue accent + black
  body is the safe default; ask before changing palette. LEGIBILITY BEATS PRETTINESS — if a
  designed element (dim sidebar text, tiny font, low-contrast callout) hurts readability,
  drop it. The user will say "looks ugly / can't read it" faster than "needs more flair".
- **Email typo trap**: users paste emails with a comma instead of a period (e.g. "gmail,com").
  Always normalize to the correct "." domain and confirm the fix to the user — don't silently
  ship a broken address.
- **Sidebar contrast trap (ReportLab)**: building bullet leads with a dim color like
  `#9fc0e0` on a navy sidebar reads as "barely readable". Use `#ffffff` for sidebar text/leads.
- **Sidebar frame overflow (TWO-FRAME BUG — this is the #1 resume-killer here).** When you use
  TWO `Frame`s (sidebar + main) on one `PageTemplate` and the sidebar flowables are TALLER than
  `frame_side`, ReportLab does NOT just clip — it silently PUSHES the overflow into `frame_main`
  (the next frame). Symptom the user reports: "words are missing / empty space above references
  and below education / text is see-through". What's actually happening: the late sidebar items
  (self-taught tech, references, education) leak into the main column and render scrambled or
  in a mid-page gap, while the sidebar shows a blank hole. This is NOT a contrast problem.
  **THE FIX (proven this session):** keep the sidebar content SHORTER than the frame. Move
  PROFESSIONAL SUMMARY, EDUCATION, and REFERENCES into the MAIN (white) column, and leave ONLY
  name + contact + the two skill lists (Technical / Self-Taught) in the sidebar. That sidebar
  always fits; the main column fills with summary+experience+education+references. Do NOT pack
  the sidebar full and hope — it will overflow-cross. (A single-frame + 2-col `Table` also
  avoids it but triggers ReportLab's "cell too large" LayoutError with big nested content, so
  the two-frame-with-short-sidebar approach is the reliable one.) After any sidebar edit,
  VERIFY with a per-band pixel scan (see visual_pdf_verification.md) that sidebar text is
  continuous top-to-bottom with NO zero-text gap bands — scanning only the far-left x (margin)
  gives false "GAP" readings, so scan at x≈20% of page width where the real text sits.

## Verification
- `ls -la /home/hunter/Desktop/<name>.*` — both files present.
- `file <name>.pdf` → "PDF document" (1.4 for ReportLab, 1.7 for soffice).
- **VISUAL verification for designed PDFs is MANDATORY.** Render to PNG and LOOK — text-layer
  greps and page counts miss the real bugs (cutoff, empty trailing page, misalignment).
  CRITICAL: a generic "critique this resume" prompt makes the vision model return a content
  SUMMARY and skip the defect checklist. Instead crop the bottom strip and ask a narrow
  yes/no defect question (see references/visual_pdf_verification.md for the exact recipe).
  The viewer's own chrome (page tabs, "Page 2 of 2") is NOT part of your document.

## References
- `references/layout_primitives.md` — the reusable python-docx helper snippets (header,
  section rule, bullet-lead, job block with date tab) copied from the working resume builder.
- `references/resume_cleanup_checklist.md` — the edit rules applied to rough resume pastes.
- `references/reportlab_resume_template.py` — COMPLETE working two-column ReportLab builder
  with the ACCEPTED layout baked in: LIGHT-BLUE sidebar (#cfe0f2) + DARK text, sidebar holds
  ONLY name+contact+skills (short so it never overflows), main column holds
  summary+experience+education+references. This is the DEFAULT "make it look different from a
  doc" layout — copy and edit the CONTENT block per user. Do NOT revert it to the dark-navy /
  white-text / references-in-sidebar shape (that reproduced the "missing words" overflow bug).
- `references/visual_pdf_verification.md` — how to render + defect-check a designed PDF,
  including the vision-model-summarization trap and the bottom-strip crop fix.
