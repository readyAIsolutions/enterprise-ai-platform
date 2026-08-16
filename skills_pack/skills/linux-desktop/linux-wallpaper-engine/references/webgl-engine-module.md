# WebGL render engine module (additive) — technique + pitfalls

Condensed knowledge bank for building a *dedicated* WebGL wallpaper render engine
inside LUMEN (`lumen/wallpaper/webgl_engine.py`) without touching the proven
`shader.py` / `engine.py` core. Captured from ENI mini B01 (2026-07-11).

## Why a separate module (not editing shader.py)
`shader.py` wraps GLSL in a minimal Chromium WebGL page and renders via
`WebWallpaper`. That path is PROVEN. A dedicated engine adds wallpaper-engine
features on the same stable substrate: Shadertoy-complete uniform set, DPR clamp
(AMD multi-monitor safety), context-loss recovery, no-WebGL dark fallback,
audio-reactive `iAudio`, an offline GLSL validator, and a GPU-load estimator.
Keep it as a NEW module; import `WallpaperWindow`/`Wallpaper`/`WebWallpaper` only.

## Page template (self-contained, slot-substituted — never f-string braces)
Use a `textwrap.dedent` template with `__SLOT__` placeholders replaced by
`.replace(...)` (mirrors `shader.py` — avoids f-string brace hell with JS `{}`).
Required slots:
- `__FRAG__` — the GLSL fragment source (backtick-wrapped template literal in JS).
- `__FRAMELOOP__` — the throttled render loop (FPS-specific).
- `__DPR_CAP__` — numeric DPR clamp (default 1.5).
- `__AUDIO_EL__` / `__AUDIO_JS__` / `__AUDIO_FEED__` — empty when audio off.
Dark fallback in CSS so NO WebGL context still paints dark, NOT Chromium white:
```html
<style>html,body{margin:0;height:100%;overflow:hidden;
background:radial-gradient(circle at 50% 35%, #0a0a16 0%, #000 70%);}
#fb{position:fixed;inset:0;display:none;...}</style>
<body><canvas id="c"></canvas>
<div id="fb">WebGL unavailable — Lumen painted a dark fallback</div>
```
Context-loss recovery (kills the white-screen-on-GPU-reset regression):
```js
cv.addEventListener('webglcontextlost', function(e){ e.preventDefault();
  window.__lumenContextLost=true; }, {once:false});
cv.addEventListener('webglcontextrestored', function(){ location.reload(); });
```
If `gl` is null after `getContext('webgl')||getContext('experimental-webgl')`:
`document.getElementById('fb').style.display='flex'; return;` (no further WebGL calls).

## PITFALL: first-frame throttle must match the pure mirror
The render loop and any pure-Python mirror (e.g. `fps_should_draw(last, now, fps)`)
MUST agree on first-frame semantics or the unit test lies. Bug hit this session:
the JS seeded `last=now` on the first call and then SKIPPED the draw, while the
pure function returned `True` for `last==0`. Fix — extract a `drawFrame()` helper
and DRAW on the first frame in BOTH:
```js
var last=0;
function drawFrame(){ /* set uniforms + gl.drawArrays(...) */ }
function loop(now){
  requestAnimationFrame(loop);
  if(last===0){ last=now; drawFrame(); return; }   // first frame paints immediately
  if(now-last < MIN_MS) return;
  last=now; drawFrame();
}
requestAnimationFrame(loop);
```
Pure mirror: `if last_ms == 0: return True` (first frame draws), else
`(now - last) >= 1000/fps`. Test with a NON-zero `last_ms` for the skip case
(`fps_should_draw(100.0, 100.0 + min_ms*0.5, 30) is False`) — using `0.0` as a
"previous draw" timestamp re-triggers the first-frame branch and masks the bug.

## DPR clamp (AMD safety)
```python
def clamp_dpr(dpr, cap=1.5):
    try: dpr = float(dpr)
    except (TypeError, ValueError): dpr = 1.0
    if dpr < 1.0 or dpr != dpr:  # NaN guard (NaN != NaN)
        dpr = 1.0
    return min(dpr, max(1.0, float(cap)))
# canvas size = round(css_w * clamp_dpr(devicePixelRatio, cap))
```
A 4K canvas at 2x DPR is what OOMs the RX 5700 XT; the cap keeps fragment count bounded.

## Audio-reactive iAudio (inject only when enabled)
When the wallpaper exposes `wp.audio`, write `<audio id="lumen-audio" src="..." loop>`
and a WebAudio analyser that feeds `iAudio`:
```js
var analyser=null,audioData=null,audioLevel=0;
try{ var ael=document.getElementById('lumen-audio');
  if(ael){ var AC=window.AudioContext||window.webkitAudioContext; var ac=new AC();
    var srcNode=ac.createMediaElementSource(ael); analyser=ac.createAnalyser();
    analyser.fftSize=256; srcNode.connect(analyser); analyser.connect(ac.destination);
    audioData=new Uint8Array(analyser.frequencyBinCount); ael.play().catch(function(){}); }
}catch(e){}
// in drawFrame: if(analyser){ analyser.getByteFrequencyData(audioData);
//   var s=0; for(var i=0;i<audioData.length;i++) s+=audioData[i];
//   audioLevel=s/audioData.length/255; }
// if(uAudio) gl.uniform1f(uAudio, audioLevel);
```
No-audio wallpapers must carry ZERO analyser code (`createAnalyser` absent).

## User uniforms (Shadertoy-style custom params) — ADD-ONLY, cycle 2
A wallpaper engine needs user-tweakable uniforms (Speed, Palette, Tint, ...) so
future GUI sliders + the slideshow/randomizer can mutate live wallpapers. Add
them WITHOUT editing `shader.py`:

- `build_webgl_html(wp, ..., uniforms: dict[str, scalar|list[float]]=None)` injects
  each uniform into the shader. A scalar -> `uniform float`; a list of length N
  (2..4) -> `uniform vecN`. Helper `_normalize_uniform_value` coerces scalar/list/
  tuple to `list[float]`.
- **GLSL ordering trap (WebGL1 GLSL ES 1.00):** a `float`/`vec` declaration is
  only legal AFTER a `precision ... float;` qualifier. If you PREPEND the decl
  above the user's precision line, the shader fails to compile (blank/white).
  Insert the decl AFTER the LAST precision statement via `_inject_uniform_decl`:
  ```python
  import re
  def _inject_uniform_decl(frag, decl):
      m = list(re.finditer(r"^\s*precision\s+\w+\s+\w+\s*;", frag, re.M))
      if m:
          pos = m[-1].end()
          return frag[:pos] + "\n" + decl + frag[pos:]
      return decl + frag   # no precision line -> prepend (shader invalid anyway)
  ```
- **Per-frame feeder** `__lumenFeedUniforms(gl)` runs before `drawArrays` each
  frame; it reads a JS store `__lumenUserUniforms` and picks `uniform1f`/`2f`/`3f`/
  `4f` from the value length (`v.length`). Location resolved once after link:
  `for(k in __lumenUserUniforms){ __lumenULocs[k]=gl.getUniformLocation(pr,k); }`.
- **The DEAD-CODE pitfall this cycle actually fixed:** `WebGLSurface.set_uniform(
  name, *values)` builds JS `window.__lumenSetUniform(name, ...)` -- but if the
  generated page NEVER defines `__lumenSetUniform`, `set_uniform` is a SILENT
  NO-OP (the page just has no such function; `runJavaScript` swallows it). The
  fix is to DEFINE it in the page so it writes into the uniform store:
  ```js
  function __lumenSetUniform(name){
    __lumenUserUniforms[name] = Array.prototype.slice.call(arguments,1);
  }
  ```
  This makes `set_uniform` (called from Python) genuinely live-push values.
  REGRESSION GUARD: the desktop-gated surface test must CALL `w.set_uniform(...)`
  so the path is exercised whenever `LUMEN_RUN_WEBENGINE_TESTS=1` runs on LO's box.
- `WebGLRenderEngine.build(..., uniforms=...)` passes the map through so the
  facade supports user uniforms too (no second code path).
- No-uniforms case must inject NOTHING: `__lumenUserUniforms`/`__lumenSetUniform`/
  `__lumenULocs` must be ABSENT from the generated HTML. (The harmless per-frame
  feed guard `if(typeof __lumenFeedUniforms==='function'){...}` is always present
  by design -- don't assert it absent.)

## Offline GLSL validator (no GPU needed)
Pure-Python checks that flag blank/white shaders before they hit the GPU:
- `void\s+main\s*\(` present (entry point).
- `gl_FragColor` written (WebGL1 output).
- brace balance (track depth per line; reset negative to 0; leftover depth =
  unclosed).
- `precision (lowp|mediump|highp) float` → warning if missing (some drivers
  default lowp), NOT an error.
- no leftover `__FRAG__` placeholder (substitution guard / injection guard).
- `main` takes no params (`void main\(([^)]*)\)` non-empty → error).
Return a `ShaderIssue(level, message, line)` list; `is_valid = no errors`.

## GPU fragment-load estimator (feeds max_webgl cap)
```python
def estimate_fragment_load(w, h, fps, dpr=1.0, cap=1.5):
    wd, hd = dpr_canvas_size(w, h, dpr, cap)   # capped device px
    return int(wd * hd * clamp_fps(fps))
def surface_count_under_budget(loads, budget):
    # greedy largest-first so the most expensive surfaces don't stack
    remaining, count = budget, 0
    for load in sorted(loads, reverse=True):
        if load <= remaining: remaining -= load; count += 1
    return count
```

## ARTIFACT NON-CLOBBER RULE
Write the portable generated page as `webgl.html`, NOT `shader.html`. The cached
copy is `webgl_<id>.html`. This lets the new engine and `shader.py` coexist in the
same wallpaper folder without one overwriting the other's generated file.

## TESTING
- Pure logic (FPS throttle, DPR, GLSL validator, GPU estimate, HTML generation)
  runs headless with no Chromium — assert real numbers.
- Any test that CONSTRUCTS a `QWebEngineView` (the `WebGLSurface`/`WebGLShaderWallpaper`
  live surface) MUST be gated behind `LUMEN_RUN_WEBENGINE_TESTS=1`; headless
  Chromium can hard-abort the whole pytest process with a C-level SIGABRT Python
  can't catch. Mirror `tests/test_surfaces.py`:
  ```python
  if not os.environ.get("LUMEN_RUN_WEBENGINE_TESTS"):
      pytest.skip("set LUMEN_RUN_WEBENGINE_TESTS=1 on a real X desktop to run")
  ```
- Verify the engine handles REAL shaders by wrapping every bundled sample:
  ```python
  root = Path("lumen/samples")
  for f in sorted(root.glob("*/lumen.json")):
      meta = json.loads(f.read_text())
      if meta.get("kind") != "shader": continue
      wp = Wallpaper(root, meta)
      issues = validate_glsl((wp.folder/(wp.entry or "shader.glsl")).read_text())
      out = build_webgl_html(wp)   # asserts no __FRAG__ left, ctx-loss present
  ```
- Confirm pre-existing failures are NOT yours: run the failing test FILES in
  isolation (without collecting your new test module). If they still fail, they
  live in LUMEN core (`shader.py`/`wayland.py`/etc.) you must not touch — record
  them as out-of-scope, don't "fix" them by editing core.

## ADD-ONLY ROUTING (don't edit engine.py)
Ship a drop-in `WebGLShaderWallpaper(WebGLSurface)` that mirrors
`ShaderWallpaper`'s contract (build html, flip `wp.entry` to `webgl.html`). Then
the master's wiring is a single non-destructive line in `engine.py._make_window`:
`if kind in (KIND_SHADER, KIND_SCENE): return WebGLShaderWallpaper(screen, wp, ...)`.
Until that core edit lands, the engine is independently importable and testable.

## OANDA
A graphics render engine consumes no market/fill/volume data, so `OANDA_TOKEN`
(read-only fill/volume benchmark) does NOT apply. State that explicitly in the
STATUS file rather than silently skipping the directive.
