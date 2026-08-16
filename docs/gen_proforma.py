#!/usr/bin/env python3
"""Build ENI ENTERPRISE 2-Year Proforma (xlsx) with live formulas + an Assumptions
sheet. All assumptions are editable yellow cells; every revenue/cost line is a
formula that updates the monthly and yearly views automatically.

Edit the yellow cells with real numbers, then reopen to see live totals.
"""
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

wb = Workbook()
HDR = PatternFill("solid", fgColor="1F2937")
HDR_FONT = Font(bold=True, color="FFFFFF")
LBL = Font(bold=True)
ASMP = PatternFill("solid", fgColor="FFF2CC")   # editable
THIN = Side(style="thin", color="CCCCCC")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
MONEY = '"$"#,##0'

# ---------------- ASSUMPTIONS ----------------
ws = wb.active
ws.title = "Assumptions"
ws["A1"] = "ENI ENTERPRISE — PROFORMA ASSUMPTIONS  (edit the YELLOW cells; every other cell is a live formula)"
ws["A1"].font = Font(bold=True, size=12)
ws["A1"].alignment.__class__  # noqa
hdr = ("Item", "key", "value")
for c, t in enumerate(hdr, 1):
    cell = ws.cell(2, c, t); cell.font = HDR_FONT; cell.fill = HDR; cell.border = BORDER

# (label, key, value, is_pct)
A = [
    ("Team license ARR, low",   "team_annual_low",    12000, False),
    ("Team license ARR, high",  "team_annual_high",   25000, False),
    ("Hosted SaaS per builder/mo", "saas_builder_mo", 10,    False),
    ("White-label margin %",    "white_margin",        0.40, True),
    ("Y1 avg co-build clients", "y1_clients",          2,    False),
    ("Y1 avg $/client/yr",      "y1_arpu",            15000, False),
    ("Y1 hosted builders (avg)", "y1_builders",         8,    False),
    ("Y2 avg co-build clients", "y2_clients",          5,    False),
    ("Y2 avg $/client/yr",      "y2_arpu",            16000, False),
    ("Y2 hosted builders (avg)", "y2_builders",        20,   False),
    ("White-label $/session",   "white_per_session",   1500, False),
    ("Model/API + GPU /month",  "cost_model",           800, False),
    ("Founder draw /month",     "salary",              4000, False),
    ("Infra /month",            "infra",                300, False),
    ("Mktg & sales /month",     "mktg",                1000, False),
    ("Legal/acctg /month (amort)", "legal",             400, False),
    ("Tax rate",                "tax_rate",             0.20, True),
]
ncells = {}
r = 4
for item, key, val, pct in A:
    ws.cell(r, 1, item).border = BORDER
    ws.cell(r, 2, key).border = BORDER
    v = ws.cell(r, 3, val); v.fill = ASMP; v.border = BORDER
    v.number_format = '0.0%' if pct else (MONEY if key not in ("y1_builders", "y2_builders") else "#,##0")
    ncells[key] = f"Assumptions!$C${r}"
    r += 1
ws.column_dimensions["A"].width = 38
ws.column_dimensions["B"].width = 14
ws.column_dimensions["C"].width = 12

# ---------------- PROFORMA 24 MO ----------------
wf = wb.create_sheet("Proforma 24mo")
months = list(range(1, 25))
for m in months:
    col = get_column_letter(m + 1)
    c = wf[f"{col}1"]; c.value = f"M{m}"; c.font = HDR_FONT; c.fill = HDR; c.border = BORDER
wf["A1"] = "LINE \\ MONTH"; wf["A1"].font = HDR_FONT; wf["A1"].fill = HDR

rows = {
    "co": 3, "hosted": 4, "white": 5, "totrev": 6,
    "c_m": 8, "c_s": 9, "c_i": 10, "c_k": 11, "c_l": 12,
    "totcost": 13, "net": 14, "netpost": 15,
}
lbls = {
    3: "Co-build client revenue", 4: "Hosted SaaS revenue", 5: "White-label revenue",
    6: "TOTAL REVENUE", 7: "Costs", 8: "Model/API + GPU", 9: "Founder draw",
    10: "Infra", 11: "Mktg & sales", 12: "Legal/acctg",
    13: "TOTAL COSTS", 14: "NET (pre-tax)", 15: "NET (post-tax)",
}
for rr, t in lbls.items():
    wf[f"A{rr}"] = t
for m in months:
    col = get_column_letter(m + 1)
    # co-build revenue: Y1 ramp (20% → 50% → 100% in Y2)
    if m <= 6:
        wf[f"{col}3"] = f"=ROUND(({ncells['y1_arpu']}*{ncells['y1_clients']}/12)*0.2,0)"
    elif m <= 12:
        wf[f"{col}3"] = f"=ROUND(({ncells['y1_arpu']}*{ncells['y1_clients']}/12)*0.5,0)"
    else:
        wf[f"{col}3"] = f"=ROUND({ncells['y2_arpu']}*{ncells['y2_clients']}/12,0)"
    b = ncells['y1_builders'] if m <= 12 else ncells['y2_builders']
    wf[f"{col}4"] = f"={b}*{ncells['saas_builder_mo']}"
    wf[f"{col}5"] = f"={ncells['white_per_session']}*{ncells['white_margin']}"
    wf[f"{col}6"] = f"=SUM({col}3:{col}5)"
    wf[f"{col}8"] = f"={ncells['cost_model']}"
    wf[f"{col}9"] = f"={ncells['salary']}"
    wf[f"{col}10"] = f"={ncells['infra']}"
    wf[f"{col}11"] = f"={ncells['mktg']}"
    wf[f"{col}12"] = f"={ncells['legal']}"
    wf[f"{col}13"] = f"=SUM({col}8:{col}12)"
    wf[f"{col}14"] = f"={col}6-{col}13"
    wf[f"{col}15"] = f"=ROUND({col}14*(1-{ncells['tax_rate']}),0)"
    for rr in (6, 13, 14, 15):
        wf[f"{col}{rr}"].font = LBL
wf.column_dimensions["A"].width = 22

# ---------------- YEARLY SUMMARY ----------------
wy = wb.create_sheet("Yearly Summary")
wy["A1"] = "YEARLY SUMMARY"; wy["A1"].font = LBL
for c, t in enumerate(["Year", "Revenue", "Costs", "Net (pre)", "Net (post)"], 1):
    cell = wy.cell(2, c, t); cell.font = HDR_FONT; cell.fill = HDR; cell.border = BORDER
for yr, mn in ((1, list(range(2, 14))), (2, list(range(14, 26)))):
    rr = yr + 2
    wy[f"A{rr}"] = f"Year {yr}"
    wy[f"B{rr}"] = "=" + "+".join(f"{get_column_letter(m+1)}6" for m in mn); wy[f"B{rr}"].number_format = MONEY
    wy[f"C{rr}"] = "=" + "+".join(f"{get_column_letter(m+1)}13" for m in mn); wy[f"C{rr}"].number_format = MONEY
    wy[f"D{rr}"] = "=" + "+".join(f"{get_column_letter(m+1)}14" for m in mn); wy[f"D{rr}"].number_format = MONEY
    wy[f"E{rr}"] = "=" + "+".join(f"{get_column_letter(m+1)}15" for m in mn); wy[f"E{rr}"].number_format = MONEY
for c in "BCDE":
    wy.column_dimensions[c].width = 16

path = "/home/hunter/Desktop/Enterprise Builder/enterprise/docs/ENI_PROFORMA_2YR.xlsx"
# make the 24-month view first (LibreOffice csv export uses the first sheet)
wb.move_sheet("Proforma 24mo", offset=-1)
wb.active = 0
wb.save(path)
print("saved", path)  # noqa: T201