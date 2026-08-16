#!/usr/bin/env python3
"""
DEFAULT "make it look different from a Word doc" resume builder (WORKING / ACCEPTED layout).
Two-column: LIGHT-BLUE sidebar (dark text) on the left + white main column on the right.

WHY THIS SHAPE (learned the hard way — do not regress):
  - Sidebar bg is LIGHT blue (#cfe0f2) with DARK text. White/dim text on a DARK navy
    sidebar was rejected repeatedly as "can't read it / see-through" by this user.
  - The sidebar holds ONLY name + role + contact + Technical Skills + Self-Taught Tech.
    PROFESSIONAL SUMMARY + EXPERIENCE + EDUCATION + REFERENCES go in the MAIN column.
    Reason: with TWO frames on one PageTemplate, if the sidebar is TALLER than its frame,
    ReportLab pushes the overflow into the MAIN frame — the late sidebar sections leak in
    and render scrambled / with a mid-page blank gap ("words are missing"). Keeping the
    sidebar short guarantees it fits and never overflow-crosses.
  - body fonts >= ~8.8pt everywhere; force 1 page by trimming SPACING, not fonts.
Run: /tmp/venv_docx/bin/python reportlab_resume_template.py
Deps: reportlab (pip install reportlab into /tmp/venv_docx; no sudo)
"""
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph,
    Spacer, ListFlowable, ListItem, Table, TableStyle, HRFlowable, KeepTogether)

INK, MUTED = colors.HexColor("#161616"), colors.HexColor("#5e5e5e")
ACCENT, ACCENT2 = colors.HexColor("#14304d"), colors.HexColor("#2f5d8a")
SIDE_BG = colors.HexColor("#cfe0f2")   # LIGHT blue sidebar (readable)
SIDE_TX = colors.HexColor("#0d2236")   # DARK text on light blue
SIDE_MU = colors.HexColor("#344e66")
BLUE_SIDE = colors.HexColor("#0b3d6b") # deep-blue accent block (self-taught)
LINE = colors.HexColor("#c2cedb")

PW, PH = letter
LM = RM = TM = BM = 0.4*inch
SIDE_W = 2.55*inch
GAP = 0.22*inch
MAIN_W = PW - LM - RM - SIDE_W - GAP

def S(n, **kw): return ParagraphStyle(n, **kw)
st_side_name = S("sn", fontName="Helvetica-Bold", fontSize=18, textColor=SIDE_TX, leading=20)
st_side_role = S("sr", fontName="Helvetica", fontSize=9.6, textColor=SIDE_MU, leading=12.2)
st_side_head = S("sh", fontName="Helvetica-Bold", fontSize=10.5, textColor=ACCENT, leading=12.5, spaceBefore=6, spaceAfter=2)
st_side_body = S("sb", fontName="Helvetica", fontSize=8.8, textColor=SIDE_TX, leading=11.6)
st_side_sub = S("ss", fontName="Helvetica-Oblique", fontSize=8.3, textColor=SIDE_MU, leading=10.6)
st_side_sm = S("sm", fontName="Helvetica", fontSize=8.9, textColor=SIDE_TX, leading=11.6)
st_side_blue = S("sblue", fontName="Helvetica", fontSize=8.8, textColor=BLUE_SIDE, leading=11.6)
st_sec = S("sec", fontName="Helvetica-Bold", fontSize=11.5, textColor=ACCENT, leading=13, spaceBefore=8, spaceAfter=2)
st_job = S("job", fontName="Helvetica-Bold", fontSize=10.2, textColor=INK, leading=12.4)
st_co = S("co", fontName="Helvetica-Bold", fontSize=9.3, textColor=ACCENT2, leading=11.4)
st_meta = S("meta", fontName="Helvetica-Oblique", fontSize=8.4, textColor=MUTED, leading=10.6)
st_body = S("body", fontName="Helvetica", fontSize=9.3, textColor=INK, leading=12.2, spaceAfter=4)
st_bull = S("bull", fontName="Helvetica", fontSize=9.0, textColor=INK, leading=11.6)
st_ref = S("ref", fontName="Helvetica", fontSize=9.2, textColor=INK, leading=11.8)

def bullets(items, style=st_bull, lead_color=ACCENT2, sb=1.0):
    flow = []
    for it in items:
        if "|" in it:
            lead, rest = it.split("|", 1)
            para = Paragraph(f'<font color="#{lead_color.hexval()[2:]}"><b>{lead.strip()}</b></font>: {rest.strip()}', style)
        else:
            para = Paragraph(it, style)
        flow.append(ListItem(para, leftIndent=9, value="•"))
    return ListFlowable(flow, bulletType="bullet", bulletColor=lead_color,
                        bulletFontSize=6.5, leftIndent=11, spaceBefore=0, spaceAfter=sb)

# ---- CONTENT (edit per user; keep every real fact verbatim) ----
name = "HUNTER<br/>LAIDLAW"
role = "HVAC &amp; Mechanical Professional<br/>Self-Taught Technician"
contact = [("LOCATION","Edmonton, AB"),("PHONE","(780) 893-2704"),
           ("EMAIL","hunter.laidlaw.work@gmail.com"),("LICENSE","Class 5 (Personal Vehicle)")]
tech = ["Design &amp; Prototyping | AutoCAD, Fusion 360, 3D design",
        "Mechanical | Blueprint reading, sheet-metal, duct install",
        "Operational Safety | SiteDocs, FLHAs, risk assessment",
        "Equipment | EWP, Skid Steer, construction machinery",
        "Credentials | CSTS 2020, WHMIS 2020, Fall Protection, EWP"]
personal = ["PC Building &amp; Hardware | Custom AMD workstation",
        "3D Printing | Creality fleet; prototype-to-part",
        "Linux &amp; OS | Ubuntu install, drivers, recovery",
        "Local AI | llama.cpp (Vulkan) offline deployment",
        "AI Dev | Desktop apps, GUIs via AI pair-programming",
        "Electronics | Raspberry Pi &amp; Arduino projects",
        "Networking | Secure remote access, AppImage packaging",
        "Scripting | Backup/recovery automation"]
experience = [
    ("Floor Coating Technician","Epoxy Empire YEG","Edmonton, AB","Apr 2026 – Jul 2026",
     ["Applied MVB, polyaspartic, epoxy flake systems to spec","Mixed epoxy to manufacturer spec","Operated grinders for scratch-profile prep","Worked 12+ hr prep days"]),
    # ... add remaining jobs here (reverse-chronological) ...
]
education = ["Sheet Metal Level 1 | Registered apprentice, Blue Book",
             "High School Diploma | Completed",
             "CAD &amp; Design | 3D-printing &amp; durability analysis"]
references = [("Dave Melnychuk","780-886-3207"),("Marcus Kuefler (Kueflers Yard)","587-590-3257"),("Tyrell","250-540-5187")]
summary = ("Dependable HVAC and mechanical professional with hands-on experience across "
    "commercial and residential installation, industrial construction, and mechanical design. "
    "Proven ability to co-lead sheet-metal crews while upholding strict quality and safety "
    "standards with a zero-incident record. Self-taught in 3D printing, electronics, and Linux.")

def draw_bg(c, doc):
    c.saveState()
    c.setFillColor(SIDE_BG); c.rect(0,0,LM+SIDE_W,PH,fill=1,stroke=0)
    c.setFillColor(ACCENT); c.rect(LM+SIDE_W+GAP, PH-0.1*inch, MAIN_W, 0.05*inch, fill=1, stroke=0)
    c.restoreState()

doc = BaseDocTemplate("/home/hunter/Desktop/Hunter_Laidlaw_Resume.pdf", pagesize=letter,
    leftMargin=LM, rightMargin=RM, topMargin=TM, bottomMargin=BM, title="Hunter Laidlaw — Resume")
fs = Frame(0, BM, LM+SIDE_W, PH-BM, id="side", leftPadding=LM, rightPadding=0.18*inch, topPadding=TM, bottomPadding=4)
fm = Frame(LM+SIDE_W+GAP, BM, MAIN_W, PH-TM-BM, id="main", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
doc.addPageTemplates([PageTemplate(id="all", frames=[fs, fm], onPage=draw_bg)])

# ---- SIDEBAR: keep SHORT (name + contact + 2 skill lists ONLY) ----
side = [Spacer(1,2), Paragraph(name, st_side_name), Spacer(1,1), Paragraph(role, st_side_role),
        Spacer(1,6), HRFlowable(width="100%", thickness=0.6, color=SIDE_MU, spaceAfter=4)]
for l,v in contact:
    side += [Paragraph(l, st_side_sub), Paragraph(v, st_side_sm), Spacer(1,3)]
side += [Paragraph("TECHNICAL SKILLS", st_side_head),
         HRFlowable(width="100%", thickness=0.5, color=SIDE_MU, spaceAfter=3),
         bullets(tech, style=st_side_body, lead_color=SIDE_TX, sb=0.5)]
side += [Paragraph("SELF-TAUGHT TECH", st_side_head),
         HRFlowable(width="100%", thickness=0.5, color=SIDE_MU, spaceAfter=3),
         bullets(personal, style=st_side_blue, lead_color=BLUE_SIDE, sb=0.2)]

# ---- MAIN: summary + experience + education + references ----
main = [Spacer(1,2), Paragraph("PROFESSIONAL SUMMARY", st_sec),
        HRFlowable(width="100%", thickness=0.5, color=LINE, spaceBefore=0, spaceAfter=3),
        Paragraph(summary, st_body),
        Paragraph("EXPERIENCE", st_sec),
        HRFlowable(width="100%", thickness=0.5, color=LINE, spaceBefore=0, spaceAfter=3)]
for jt, co, loc, dates, pts in experience:
    head = Table([[Paragraph(jt, st_job), Paragraph(dates, st_meta)]], colWidths=[MAIN_W*0.70, MAIN_W*0.30])
    head.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("ALIGN",(1,0),(1,0),"RIGHT"),
        ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
        ("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0)]))
    main.append(KeepTogether([head, Paragraph(f"{co}  &nbsp;|&nbsp;  {loc}", st_co), bullets(pts), Spacer(1, 3)]))
main += [Paragraph("EDUCATION &amp; CREDENTIALS", st_sec),
         HRFlowable(width="100%", thickness=0.5, color=LINE, spaceBefore=0, spaceAfter=3),
         bullets(education),
         Paragraph("REFERENCES", st_sec),
         HRFlowable(width="100%", thickness=0.5, color=LINE, spaceBefore=0, spaceAfter=3)]
ref_rows = [[Paragraph(f"<b>{n}</b>", st_ref), Paragraph(num, st_ref)] for n, num in references]
rt = Table(ref_rows, colWidths=[MAIN_W*0.68, MAIN_W*0.32])
rt.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("ALIGN",(1,0),(1,-1),"RIGHT"),
    ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
    ("TOPPADDING",(0,0),(-1,-1),0.5),("BOTTOMPADDING",(0,0),(-1,-1),0.5)]))
main.append(rt)

doc.build(side + main)   # side flows into frame 'side', main into frame 'main'
print("PDF built: /home/hunter/Desktop/Hunter_Laidlaw_Resume.pdf")
