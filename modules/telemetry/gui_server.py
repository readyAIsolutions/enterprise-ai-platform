"""ENI Enterprise Build-Module GUI.

A small stdlib-only web server (no deps) that shows, per project/build session,
WHICH enterprise modules are being used, HOW (on which hook/tool), WHAT functions
were created, and WHY (each module's purpose). Serves a single dark UI page.

Endpoints:
  /            -> HTML UI
  /api/sessions -> [{session, goal, created_at, steps, status, modules:[...], functions:[...]}]
  /api/modules  -> module_purpose catalog (role/hook/why for all 87)
  /api/telemetry-> raw module usage rows (live as builds happen)

Real data only: build sessions from data/build_sessions/*/manifest.json, module
purpose from module_purpose.json, live usage from module_usage.jsonl.
"""
# ruff: noqa: E501 T201 ANN201 ANN002 ANN003 PTH110 PTH123 SIM105 SIM115 W292  # template CSS/JS + stdlib http server style
from __future__ import annotations

import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

_REPO = Path(os.environ.get(
    "ENI_ENTERPRISE_HOME",
    str(Path(__file__).resolve().parent.parent / "enterprise"),
))
if not (_REPO / "modules").exists():
    _REPO = Path("/home/hunter/Desktop/Enterprise Builder/enterprise")

_DATA = _REPO / "data" / "build_sessions"
_TELE = _DATA / "module_usage.jsonl"
_PURPOSE = _REPO / "modules" / "telemetry" / "module_purpose.json"


def _load_purpose() -> dict:
    try:
        return json.loads(_PURPOSE.read_text())
    except Exception:
        return {}


def _scan_functions(path: str) -> list[dict]:
    """Parse function/class definitions out of a written artifact .py file."""
    fs = []
    if not path or not os.path.exists(path):
        return fs
    try:
        src = open(path, encoding="utf-8", errors="replace").read()
    except Exception:
        return fs
    for m in re.finditer(r'^\s*(?:async\s+def|def)\s+([A-Za-z_]\w*)\s*\(', src, re.M):
        fs.append({"kind": "function", "name": m.group(1)})
    for m in re.finditer(r'^\s*class\s+([A-Za-z_]\w*)\s*[:(]', src, re.M):
        fs.append({"kind": "class", "name": m.group(1)})
    return fs


def _load_sessions(purpose: dict) -> list[dict]:
    """Aggregate real build sessions + infer module usage per session."""
    sessions = []
    if not _DATA.exists():
        return sessions

    # live telemetry rows grouped by session
    tele = {}
    if _TELE.exists():
        for line in _TELE.read_text().splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            tele.setdefault(r.get("session") or "?", []).append(r)

    for d in sorted(_DATA.iterdir()):
        if not d.is_dir() or not d.name.startswith("session"):
            continue
        man = d / "manifest.json"
        if not man.exists():
            continue
        try:
            m = json.loads(man.read_text())
        except Exception:
            continue
        sid = m.get("session_id") or d.name
        goal = m.get("goal") or "Untitled build"
        steps = []
        for st in m.get("steps", []):
            attempts = st.get("attempts", [])
            steps.append({
                "step": st.get("step"),
                "feature": st.get("feature"),
                "status": st.get("status"),
                "attempts": len(attempts),
                "passed": sum(1 for a in attempts if a.get("status") == "test-passed"),
                "file": st.get("file"),
                "functions": _scan_functions(st.get("file") or ""),
            })
        # module usage: telemetry for this session, else infer a plausible base set
        mods_used = {}
        for r in tele.get(sid, []):
            nm = r.get("module")
            if not nm or nm in mods_used:
                continue
            p = purpose.get(nm, {})
            mods_used[nm] = {
                "name": nm,
                "role": p.get("role", "Build capability"),
                "hook": r.get("hook") or p.get("hook", "pre_llm_call"),
                "tool": r.get("tool", ""),
                "why": r.get("why") or p.get("why", ""),
                "used_at": r.get("ts"),
            }
        sessions.append({
            "session": sid,
            "goal": goal,
            "created_at": m.get("created_at", ""),
            "status": m.get("status"),
            "steps": steps,
            "modules": sorted(mods_used.values(), key=lambda x: x["name"]),
            "functions": [f for st in steps for f in st["functions"]],
        })
    # newest first
    sessions.sort(key=lambda s: s.get("created_at") or "", reverse=True)
    return sessions


def _all_functions(sessions: list[dict]) -> int:
    return sum(len(s["functions"]) for s in sessions)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args):  # noqa: A002
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path == "/" or path == "/index.html":
                self._send(200, PAGE.encode(), "text/html; charset=utf-8")
            elif path == "/api/sessions":
                purpose = _load_purpose()
                ss = _load_sessions(purpose)
                body = json.dumps({
                    "sessions": ss, "count": len(ss),
                    "total_functions": _all_functions(ss),
                }).encode()
                self._send(200, body, "application/json")
            elif path == "/api/modules":
                body = json.dumps(_load_purpose()).encode()
                self._send(200, body, "application/json")
            elif path == "/api/telemetry":
                rows = _load_sessions({})  # reuses read; light enough
                body = json.dumps([r for s in rows for r in s["modules"]]).encode()
                self._send(200, body, "application/json")
            elif path == "/health":
                self._send(200, b"ok", "application/json")
            else:
                self._send(404, b"not found", "text/plain")
        except Exception as e:  # noqa: BLE001
            self._send(500, str(e).encode(), "text/plain")


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>ENI Enterprise — Build Module GUI</title>
<style>
:root{--bg:#0d1117;--panel:#161b22;--panel2:#1c2230;--txt:#e6edf3;--mut:#8b949e;
--acc:#58a6ff;--grn:#3fb950;--red:#f85149;--ylw:#d29922;--purp:#bc8cff}
*{box-sizing:border-box;margin:0}
body{background:var(--bg);color:var(--txt);font:14px/1.5 'JetBrains Mono',monospace;padding:20px}
header{display:flex;align-items:center;gap:14px;margin-bottom:18px;flex-wrap:wrap}
header h1{font-size:20px;color:var(--acc)}
.badge{background:var(--panel2);border:1px solid #30363d;border-radius:20px;padding:3px 12px;font-size:13px}
.badge b{color:var(--grn)}
.badge .r{color:var(--red)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
.card{background:var(--panel);border:1px solid #30363d;border-radius:10px;padding:14px;cursor:pointer;transition:.15s}
.card:hover{border-color:var(--acc);transform:translateY(-2px)}
.card h2{font-size:15px;color:var(--txt);margin-bottom:4px}
.card .goal{color:var(--mut);font-size:12px;margin-bottom:10px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}
.chip{background:var(--panel2);border:1px solid #30363d;border-radius:6px;padding:2px 8px;font-size:11px}
.chip.m{color:var(--acc)} .chip.f{color:var(--grn)} .chip.n{color:var(--mut)}
.status{display:inline-block;font-size:11px;padding:2px 8px;border-radius:6px}
.status.ok{background:#1f3d2b;color:var(--grn)}
.status.test-failed{background:#3d2226;color:var(--red)}
.steps{background:var(--panel2);border-radius:8px;margin-top:10px;padding:8px}
.steps div{font-size:11px;color:var(--mut);padding:3px 0;border-bottom:1px solid #21262d}
.detail{background:var(--bg);border:1px solid #30363d;border-radius:12px;padding:20px;margin-top:20px}
.detail h2{color:var(--acc);margin-bottom:6px}
.modtable{width:100%;border-collapse:collapse;margin-top:10px}
.modtable th{text-align:left;color:var(--mut);font-size:11px;padding:6px 8px;border-bottom:1px solid #30363d}
.modtable td{padding:8px;border-bottom:1px solid #21262d;font-size:12px;vertical-align:top}
.modtable .name{color:var(--acc);font-weight:600}
.modtable .role{color:var(--purp)}
.modtable .hook{color:var(--ylw)}
.section{font-size:13px;color:var(--mut);margin:18px 0 8px;text-transform:uppercase;letter-spacing:.5px}
a{color:var(--acc);text-decoration:none}
.back{cursor:pointer;color:var(--acc)}
@media(max-width:700px){.grid{grid-template-columns:1fr}}
</style></head>
<body>
<header>
  <h1>◈ ENI Enterprise — Build Module GUI</h1>
  <span class="badge" id="cnt"></span>
  <span class="badge">live module usage + functions created per build</span>
  <input id="q" placeholder=" filter by goal / session…" value=""
    oninput="render(this.value.toLowerCase())"
    style="margin-left:auto;background:var(--panel);border:1px solid #30363d;color:var(--txt);
           border-radius:8px;padding:6px 10px;font:inherit;min-width:220px">
</header>
<div class="grid" id="grid" style="margin-top:14px"></div>
<div class="detail" id="detail" style="display:none"></div>

<script>
let SESSIONS=[], MODS={};
async function load(){
  const s=await (await fetch('/api/sessions')).json();
  const m=await (await fetch('/api/modules')).json();
  MODS=m; SESSIONS=s.sessions;
  document.getElementById('cnt').innerHTML =
    '<b>'+s.count+'</b> projects &nbsp;·&nbsp; <b>'+s.total_functions+'</b> functions &nbsp;·&nbsp; 87 modules';
  render();
}
function chips(ss){
  let html='';
  const ms=[...new Set(ss.modules.map(x=>x.name))].slice(0,8);
  ms.forEach(n=>html+='<span class="chip m">'+n+'</span>');
  const totalF=ss.functions.length;
  if(totalF) html+='<span class="chip f">'+totalF+' defs</span>';
  const totalSteps=ss.steps.length;
  html+='<span class="chip n">'+totalSteps+' steps</span>';
  return html;
}
function render(filter=''){
  const g=document.getElementById('grid');
  const q=document.getElementById('q');
  if(filter==='' && q){ filter=(q.value||'').toLowerCase(); }
  g.innerHTML='';
  const list=SESSIONS.filter(s=>!filter || s.goal.toLowerCase().includes(filter) || s.session.includes(filter));
  list.forEach(s=>{
    const st = s.steps.filter(x=>x.status==='test-passed').length + '/'+s.steps.length;
    const done = s.status? s.status : (s.steps.every(x=>x.status==='test-passed')?'ok':'building');
    const d=new Date(s.created_at||0).toLocaleString();
    const card=document.createElement('div');
    card.className='card';
    card.innerHTML =
      '<h2>'+escapeHtml(s.goal)+'</h2>'+
      '<div class="goal">'+s.session+' · '+d+' · steps '+st+
        ' <span class="status '+(done==='ok'?'ok':'test-failed')+'">'+done+'</span></div>'+
      chips(s)+
      '<div class="steps">'+(s.steps.slice(0,6).map(x=>'<div>'+x.feature+' — '+(x.passed)+'/'+x.attempts+' passed</div>').join('')||'<div>no steps yet</div>')+'</div>';
    card.onclick=()=>detail(s);
    g.appendChild(card);
  });
  if(!list.length) g.innerHTML='<div style="color:var(--mut)">no matching builds</div>';
}
function detail(s){
  const dt=document.getElementById('detail');
  dt.style.display='block';
  _detailOpen=true;
  let mh='<table class="modtable"><tr><th>Module</th><th>Role (how)</th><th>Hook</th><th>Why / detail</th></tr>';
  if(s.modules.length===0){
    mh+='<tr><td colspan=4 style="color:var(--mut)">No module telemetry recorded yet for this session — start using the enterprise drop-in and modules will log here live.</td></tr>';
  }
  s.modules.forEach(m=>{
    mh+='<tr><td class="name">'+m.name+'</td><td class="role">'+escapeHtml(m.role)+'</td>'+
        '<td class="hook">'+escapeHtml(m.hook||'')+'</td><td>'+escapeHtml(m.why||'')+(m.tool?' <span class="chip n">tool:'+m.tool+'</span>':'')+'</td></tr>';
  });
  mh+='</table>';
  let fn='<div class="section">functions created</div><div class="chips">';
  const seen=new Set();
  s.functions.forEach(f=>{ const k=f.name; if(!seen.has(k)){seen.add(k); fn+='<span class="chip f">'+f.kind+' '+f.name+'()</span>';}});
  fn+='</div>'+(seen.size===0?'<div style="color:var(--mut);font-size:12px">none parsed from artifacts</div>':'');
  let steps='<div class="section">build steps</div>';
  s.steps.forEach(x=>{ steps+='<div style="padding:4px 0;border-bottom:1px solid #21262d">'+
    '<b>'+x.feature+'</b> <span class="status '+(x.status==='test-passed'?'ok':'test-failed')+'">'+(x.status||'?')+'</span> — '+x.passed+'/'+x.attempts+' passed'+
    (x.functions.length?' <span style="color:var(--mut)">·</span> <span class="chip f">'+x.functions.map(f=>f.name).join(', ')+'</span>':'')
    +'</div>'; });
  dt.innerHTML='<div class="back" id="backBtn" style="cursor:pointer">&larr; back to all builds</div>'+
      '<h2>'+escapeHtml(s.goal)+'</h2>'+
      '<div style="color:var(--mut)">'+s.session+'</div>'+
      steps+fn+'<div class="section">modules used ('+s.modules.length+')</div>'+mh;
    document.getElementById('backBtn').onclick = function(){ _detailOpen=false; dt.style.display='none'; window.scrollTo(0,0); };
    window.scrollTo(0,0);
}
function escapeHtml(x){return String(x||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
load();
let _detailOpen=false;
setInterval(function(){ if(_detailOpen) return; load(); },4000);
</script>
</body></html>
"""


def main(port: int = 8930) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"[eni-gui] enterprise build-module GUI on http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    import sys
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8930)
