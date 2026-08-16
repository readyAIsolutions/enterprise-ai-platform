#!/usr/bin/env python3
"""forge_quickstart.py - minimal Forge generator+render+validate loop.

Reproduce-with-modifications template. Shows the primitive -> .scad -> .stl ->
validate pattern that makes "100% ready to print" real. Copy `render.py` from
the forge wrapper (demiurgenas_stash/demiurge/builder/forge/render.py) into this
dir, or pip/apt install openscad and call it directly.

Run:  python3 forge_quickstart.py
"""
from __future__ import annotations
import subprocess, sys
from pathlib import Path

OUT = Path("./build_quick"); OUT.mkdir(exist_ok=True)
FN = 96  # global curve resolution


def emit_scad(name: str, body: str) -> Path:
    p = OUT / f"{name}.scad"
    p.write_text(f"$fn={FN};\nmodule part(){{\n{body}\n}}\npart();")
    return p


def render(scad: Path, stl: Path) -> bool:
    # requires openscad on PATH; or set OPENSCAD_BIN env
    bin_ = __import__("os").environ.get("OPENSCAD_BIN", "openscad")
    try:
        subprocess.run([bin_, str(scad), "-o", str(stl)], check=True,
                       capture_output=True, timeout=300)
        return stl.exists()
    except Exception as e:
        print("  render fail:", e)
        return False


# --- example primitives (condensed from forge_core.py) ----------------------
def rounded_box(w, h, d, r):
    return (f"translate([0,0,{d/2}]) minkowski(){{ cube([{w-2*r},{h-2*r},{d-2*r}],"
            f"center=true); cylinder(r={r},h=0.001,$fn=24); }}")


def press_fit_hole(shaft_d, depth, clearance=0.15):
    return f"cylinder(d={shaft_d-2*clearance},h={depth},$fn={FN});"


def living_hinge(length, width, gauge=1.0):
    land = 2.4
    return (f"union(){{ translate([-{length/2},0,0]) cube([{length},{width},{gauge}],center=true);"
            f" translate([-{length/2}-4,0,0]) cube([4,{width},{land*2}],center=true);"
            f" translate([{length/2}+4,0,0]) cube([4,{width},{land*2}],center=true); }}")


# --- a tiny 2-part demo: tray + press-fit peg -------------------------------
def build():
    # copy the real validator in if present, else inline a stub
    try:
        from stl_validator import validate_stl
    except Exception:
        sys.path.insert(0, str(Path(__file__).parent))
        from stl_validator import validate_stl

    tray = (f"difference(){{ {rounded_box(80,50,20,4)}\n"
            f"  translate([0,0,2]) {rounded_box(76,46,20,3)}\n"
            f"  translate([20,0,2]) {press_fit_hole(8,18)} }}")
    peg = f"cylinder(d=8,h=18,$fn={FN});"

    for name, body in (("tray", tray), ("peg", peg)):
        scad = emit_scad(name, body)
        stl = OUT / f"{name}.stl"
        if not render(scad, stl):
            print(f"[{name}] RENDER FAIL"); continue
        v = validate_stl(stl)
        print(f"[{name}] watertight={v['ok']} tris={v['stats'].get('triangles')} "
              f"bbox={v['stats'].get('bbox')}")
        if v["errors"]:
            print("   ERR:", v["errors"])


if __name__ == "__main__":
    build()
