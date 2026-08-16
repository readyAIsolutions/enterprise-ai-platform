# Single-File Hermes Dashboard — ENI Swarm Monitoring Pattern

## Endpoint: /eni_status

Reads ENI builder logs from `/tmp/eni_opt_logs/`, determines per-builder state, and returns JSON suitable for a live dashboard grid.

### Backend (Python, stdlib only)

```python
ENI_LOG_DIR = "/tmp/eni_opt_logs"

def scan_eni_builders():
    builders = []
    if not os.path.isdir(ENI_LOG_DIR):
        return builders
    for fn in sorted(os.listdir(ENI_LOG_DIR)):
        if not fn.endswith('.log'): continue
        name = fn.replace('.log','')
        path = os.path.join(ENI_LOG_DIR, fn)
        try:
            stat = os.stat(path)
            with open(path,'rb') as f:
                f.seek(max(0, stat.st_size - 2000))
                tail = f.read().decode(errors='ignore')
            lines = [l.strip() for l in tail.split('\n') if l.strip()]
            state = "idle"
            if any('❯' in l for l in lines[-3:]): state = "idle"
            elif any('thinking' in l.lower() for l in lines[-5:]): state = "thinking"
            elif any('ERROR' in l or 'Traceback' in l for l in lines[-3:]): state = "error"
            last_activity = ""
            for l in reversed(lines):
                if l and '─' not in l and '❯' not in l and len(l) > 5:
                    last_activity = l[:120]; break
            builders.append({
                "name": name, "state": state,
                "size_kb": stat.st_size // 1024,
                "mtime": int(stat.st_mtime),
                "last_activity": last_activity
            })
        except: pass
    return builders
```

### Frontend (JS, zero-dependency)

```javascript
async function refreshEni(){
    try{var r=await fetch('/eni_status');eniData=await r.json();renderEni()}catch(e){}
}
function renderEni(){
    var data=eniData.builders||[];
    var filtered=eniFilter==='all'?data:data.filter(b=>b.name.indexOf(eniFilter)===0);
    document.getElementById('eni-count').textContent=filtered.length+' / '+data.length+' builders';
    var states={idle:'🟢 idle',thinking:'🟡 thinking',error:'🔴 error'};
    document.getElementById('eni-grid').innerHTML=filtered.map(b=>{
        var age=Math.floor(Date.now()/1000-b.mtime);
        var ageStr=age<60?age+'s':age<3600?Math.floor(age/60)+'m':Math.floor(age/3600)+'h';
        return`<div class="health-card" title="${escHtml(b.last_activity||'')}">
          <div><span style="font-size:10px">${states[b.state]||'⚪ '+b.state}</span>
          <span style="font-size:10px">${escHtml(b.name)}</span></div>
          <div><span style="color:var(--muted);font-size:10px">${ageStr} · ${b.size_kb}KB</span></div>
        </div>`;
    }).join('')||'<div>No builders</div>';
}
```

### Filters by product prefix

Add filter buttons (SB, D3D, NAS, LUM) that set `eniFilter` and re-render. The ENI swarm uses these prefixes: SB=StockBot, D3D=Demiurge3D, NAS=NAS projects, LUM=Lumen. Active filter gets `var(--green)` border.

### Auto-refresh

Refresh every 30s when the tab is active:
```javascript
setInterval(function(){if(activeTab==='eni')refreshEni()},30000);
```

### Key decisions
- Read last 2000 bytes only (cheap, fast even with 54 concurrent builders)
- State detection: idle if `❯` (hermes REPL prompt), thinking if "thinking/reasoning" in last 5 lines, error if "ERROR/Traceback"
- Last activity: first non-decorative line going backward through tail
- Filter by product prefix (startsWith match) not substring

### Pitfalls
- Do NOT read entire log files — some are 100KB+. Use seek-to-end + tail read.
- State detection by `❯` character: this is the hermes YOLO REPL prompt. If the prompt character changes, update the detection.
- The `/eni_log/<name>` endpoint for viewing individual logs should also use tail-read (last 10KB).
