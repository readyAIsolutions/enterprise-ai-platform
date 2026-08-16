# Hardware-profiling add-only modules (GPU / WebGL capability sensor)

Pattern for a LUMEN add-only module that profiles REAL hardware (e.g. a GPU
capability profiler) WITHOUT opening a display or a GPU context — proven this
cycle by `lumen/capability.py` (builder LM10, 2026-07-11). It feeds the GPU
fragment budget + surface cap into `recommend` / `auto_tune` (previously only
GUESSED from config knobs).

## Hard leash rules for this class
- Module top level imports ONLY stdlib. NEVER import `lumen`, PyQt, QWebEngine,
  Xlib, or GL. (`import lumen.capability` is fine ONLY if the module itself
  imports zero of those — capability.py imports only argparse/json/re/shutil/
  subprocess/sys/dataclasses/enum/pathlib/typing.)
- No `QApplication`, no display, no GPU context. Prove it with the subprocess
  probe: `QT_QPA_PLATFORM=offscreen DISPLAY= .venv/bin/python -c "import sys,
  lumen.<mod>; bad=any(m.split('.')[0] in ('PyQt6','PySide6','Xlib') for m in
  sys.modules); print('PULLED_QT:'+repr([m for m in sys.modules if
  m.split('.')[0] in ('PyQt6','PySide6','Xlib')]))"` -> assert `PULLED_QT:[]`.
- Degrade, never crash: on a Qt-less / container box return a conservative
  fallback profile.

## The `_detect_raw()` funnel (single point of hardware I/O)
Funnel ALL probing into ONE function so tests can monkeypatch it and the
module stays deterministic + headless:

```python
def _detect_raw() -> Dict[str, object]:
    raw: Dict[str, object] = {}
    raw.update(_read_sys_drm())          # /sys (displayless)
    lspci = _run_lspci()                 # subprocess (displayless)
    if lspci:
        parsed = _parse_lspci(lspci)
        raw.setdefault("vendor_id", parsed.get("vendor_id"))
        raw.setdefault("device_id", parsed.get("device_id"))
        raw.setdefault("model", parsed.get("model"))
    return raw
```

### /sys/class/drm reads (displayless, no GPU context)
- Vendor / device id: `/sys/class/drm/card<N>/device/{vendor,device}` (e.g.
  `0x1002` AMD, `0x10de` NVIDIA, `0x8086` Intel; device `0x731f` = Navi 10).
- Driver name: resolve the `driver` symlink under `device/` -> `.name`.
- VRAM (AMD): `/sys/class/drm/card<N>/device/mem_info_vram_total` (bytes).
- Multi-head pixel load: for each `card<N>/card<N>-<conn>/` with `status`
  == `connected`, read the first line of `modes` (`WxH`), sum `W*H`.
- Guard EVERY read in try/except (OSError/PermissionError); missing `/sys`
  (container) -> return `{}`.

### `lspci -nn` -- STRIP DISPLAY, and parse the RIGHT bracket
```python
def _run_lspci() -> str:
    try:
        proc = subprocess.run(
            [shutil.which("lspci") or "lspci", "-nn"],
            capture_output=True, text=True, timeout=5,
            env={k: v for k, v in os.environ.items() if k != "DISPLAY"},
        )
        return proc.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""
```
THE GOTCHA: a VGA line is
`00:02.0 VGA compatible controller [0300]: Advanced Micro Devices, Inc. [AMD/ATI] Navi 10 [Radeon RX 5700 XT] [1002:731f] (rev c1)`.
The LEADING `[0300]` is the PCI **class code** (VGA = 0300) -- it has NO colon.
The real PCI id is `[1002:731f]` (has a colon). A naive "first `[`" parse grabs
`[0300]` -> bogus vendor/device. Fix:

```python
import re
_PAT = re.compile(r"\[([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\]")
def _parse_lspci(text):
    out = {}
    for line in text.splitlines():
        low = line.lower()
        if "vga" not in low and "3d" not in low and "display" not in low:
            continue
        m = _PAT.search(line)                 # the [vid:did] token, NOT [0300]
        if m:
            out["vendor_id"] = "0x" + m.group(1).lower()
            out["device_id"] = "0x" + m.group(2).lower()
        tmp = re.sub(r"^[\w\.\:]+ ", "", line)   # drop bus id
        tmp = _PAT.sub("", tmp)                   # drop [vid:did]
        tmp = re.sub(r"\[[0-9a-fA-F]{4}\]", "", tmp)  # drop [0300] class
        if ":" in tmp:
            tmp = tmp.split(":", 1)[1]
        tmp = re.sub(r"\(rev[^)]*\)", "", tmp)    # drop "(rev c1)"
        tmp = tmp.strip()
        if tmp:
            out["model"] = tmp                    # KEEP [..] (has "RX 5700 XT")
        if out:
            break
    return out
```

## Capability TABLE + fallback chain
```python
_CAP_TABLE = {
    (VENDOR_AMD, "0x731f"): _CapEntry(Tier.HIGH, 900_000_000, 4, 1.5, 16384, 2, 8192),
    # ... known GPUs ...
}
_VENDOR_FALLBACK = {VENDOR_AMD: _CapEntry(Tier.MID, 420_000_000, 2, 1.25, 8192, 2, 4096), ...}
_FALLBACK = _CapEntry(Tier.LOW, 120_000_000, 1, 1.0, 4096, 1, 0)

def _entry_for(vendor_id, device_id):
    if (vendor_id, device_id) in _CAP_TABLE: return _CAP_TABLE[(vendor_id, device_id)]
    if vendor_id in _VENDOR_FALLBACK:       return _VENDOR_FALLBACK[vendor_id]
    return _FALLBACK
```
`fragment_budget` is the headline number: total sustainable frag/s across ALL
live surfaces -- same unit as `lumen.perf.gpu_fragment_load`, so it drops
straight into `perf.gpu_budget_report`, `recommend.auto_assign`,
`auto_tune`. `source` = `"detected"` only when the exact `(vendor,device)` is in
the table OR the vendor is known; else `"fallback"`.

## Additive seam into a module YOU own (low-risk, ADD-ONLY)
To make the profiler actually drive the engine without editing a sibling, add a
NEW function to a module you already own that lazily imports the new module and
falls back:

```python
# inside lumen/recommend.py (owned by LM10)
def profile_from_capability(cfg=None, surfaces=None):
    try:
        from lumen.capability import profile as _cap_profile
        cap = _cap_profile()
    except Exception:
        return profile_from_config(cfg, surfaces)   # graceful fallback
    ...
    return HardwareProfile(..., budget=cap.fragment_budget,
                           max_surfaces=cap.surface_cap,
                           dpr_cap=cap.recommended_dpr)
```
Adding a function to your OWN module is within ADD-ONLY; editing a SIBLING's
module is not. Existing API + its tests stay green.

## Verified on LO's real box (evidence to cite)
`python -m lumen.capability --self-test` ->
`self-test PASS: gpu=AMD ... Navi 10 [Radeon RX 5700 XT] tier=high
budget=900,000,000 surfaces=4 source=detected`
Correctly fingerprinted AMD RX 5700 XT (Navi 10, device 0x731f) with NO display
opened. Test suite: 24 passed; flake8/mypy/importlint clean; PULLED_QT:[].
