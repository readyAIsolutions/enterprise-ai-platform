# resume_cleanup_checklist.md — edit rules for rough resume pastes

Apply these when a user pastes resume/CV text and asks to "fix it up / clean it / make a doc".

## MUST DO
- Preserve every real fact verbatim: job titles, companies, locations, certifications,
  reference names + phone numbers. Never invent employers, dates, or credentials.
- Reorder to reverse-chronological (most recent first).
- Normalize all date ranges to `Mon YYYY – Mon YYYY` or `Mon YYYY – Present`.
- Tighten the professional summary into ONE strong paragraph; delete run-on sentences.
- Group scattered skills into labeled bullet clusters.
- Expand one-line job blurbs into 2–4 concrete, quantified bullets using specifics the
  user already provided (duct sizes, hour counts, "zero-incident record", systems used).

## WATCH FOR (common paste defects)
- **Backwards chronology**: a job with an earlier end date listed AFTER a later-dated job.
  Reorder.
- **Future / typo end dates**: "July 20th" with no year, or an end date that's actually
  "Present". If ambiguous, set to `Present` and TELL the user the assumption so they can
  correct it.
- **Overlapping dates**: flag overlaps; usually one is a typo.
- **Inconsistent casing**: "hvac" / "HVAC", "Epoxy Empire YEG" vs "EPOXY EMPIRE YEG".
  Normalize to Title Case for company/section headers.
- **Missing location on a job**: fill from the user's city if obvious, else leave and note.

## STRUCTURE (output order — two-column DESIGNED layout)
For the PDF, use the navy-sidebar two-column layout (see reportlab_resume_template.py):
- LEFT navy sidebar: Name (large bold) → role/tagline → PROFILE summary → contact
  (LOCATION/PHONE/EMAIL/LICENSE labels) → TECHNICAL SKILLS (bulleted) → SELF-TAUGHT TECH
  (bulleted) → REFERENCES (name + phone) → EDUCATION. White text on navy.
- RIGHT white column: EXPERIENCE only — each job as title + right-aligned dates (2-col
  Table), blue employer|location line, 2–4 bullets. Newest first.
For the DOCX (editable source), a clean single-column version is fine: Name (22pt accent) →
centered contact line → License subline → PROFESSIONAL SUMMARY → TECHNICAL SKILLS →
EXPERIENCE → EDUCATION → PERSONAL/SELF-TAUGHT → REFERENCES. Both files deliver the same content.

## DELIVER
- Both `.docx` and `.pdf` to `/home/hunter/Desktop/`.
- Filename: `<FirstName>_<LastName>_Resume.docx` / `.pdf`.
- After building, verify with `file *.pdf` and report both absolute paths.
