# layout_primitives.md — reusable python-docx helpers

Copied from the working resume builder (`/tmp/build_resume.py`). Import:
`from docx import Document`, `from docx.shared import Pt, RGBColor, Inches`,
`from docx.enum.text import WD_ALIGN_PARAGRAPH`, `from docx.oxml.ns import qn`,
`from docx.oxml import OxmlElement`.

## colors
```python
ACCENT = RGBColor(0x1F, 0x3A, 0x5F)   # deep blue
DARK   = RGBColor(0x22, 0x22, 0x22)
GREY   = RGBColor(0x55, 0x55, 0x55)
```

## base style + margins
```python
normal = doc.styles["Normal"]
normal.font.name = "Calibri"
normal.font.size = Pt(10.5)
normal.paragraph_format.space_after = Pt(4)
normal.paragraph_format.line_spacing = 1.05
for s in doc.sections:
    s.top_margin = Inches(0.6); s.bottom_margin = Inches(0.6)
    s.left_margin = Inches(0.7); s.right_margin = Inches(0.7)
```

## name header (22pt accent, centered)
```python
def name_header():
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("HUNTER LAIDLAW"); r.bold = True; r.font.size = Pt(22)
    r.font.color.rgb = ACCENT; r.font.name = "Calibri"
```

## centered contact + subline
```python
def contact_line():
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("Edmonton, AB  |  (780) 893-2704  |  mimicreed500@gmail.com")
    r.font.size = Pt(10); r.font.color.rgb = GREY
    p2 = doc.add_paragraph(); p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r2 = p2.add_run("Class 5 Driver's License (Personal Vehicle)")
    r2.font.size = Pt(9.5); r2.italic = True; r2.font.color.rgb = GREY
```

## section title with bottom border rule
```python
def section_title(text):
    p = doc.add_paragraph()
    r = p.add_run(text.upper()); r.bold = True; r.font.size = Pt(12)
    r.font.color.rgb = ACCENT
    pPr = p._p.get_or_add_pPr(); pbdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single"); bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "2"); bottom.set(qn("w:color"), "1F3A5F")
    pbdr.append(bottom); pPr.append(pbdr)
    p.paragraph_format.space_before = Pt(10); p.paragraph_format.space_after = Pt(4)
```

## bullets with bold-lead split ("Lead | rest")
```python
def bullets(items):
    for it in items:
        p = doc.add_paragraph(style="List Bullet")
        p.paragraph_format.left_indent = Inches(0.22); p.paragraph_format.space_after = Pt(2)
        if "|" in it:
            lead, rest = it.split("|", 1)
            r = p.add_run(lead.strip() + ": "); r.bold = True; r.font.size = Pt(10.5)
            r2 = p.add_run(rest.strip()); r2.font.size = Pt(10.5)
        else:
            r = p.add_run(it); r.font.size = Pt(10.5)
```

## job block: title|company + location / right-aligned dates
```python
def job(title, company, location, dates, points):
    p = doc.add_paragraph(); p.paragraph_format.space_before = Pt(6)
    rt = p.add_run(title); rt.bold = True; rt.font.size = Pt(11); rt.font.color.rgb = DARK
    rc = p.add_run("  |  " + company); rc.bold = True; rc.font.size = Pt(10.5)
    rc.font.color.rgb = ACCENT
    p2 = doc.add_paragraph(); p2.paragraph_format.space_after = Pt(3)
    left = p2.add_run(location); left.font.size = Pt(9.5); left.italic = True
    left.font.color.rgb = GREY
    p2.add_run("\t")
    rd = p2.add_run(dates); rd.font.size = Pt(9.5); rd.italic = True; rd.font.color.rgb = GREY
    p2.paragraph_format.tab_stops.add_tab_stop(Inches(6.9), WD_ALIGN_PARAGRAPH.RIGHT)
    bullets(points)
```
