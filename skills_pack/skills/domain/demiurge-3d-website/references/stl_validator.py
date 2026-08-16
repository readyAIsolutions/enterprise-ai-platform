#!/usr/bin/env python3
"""
Zero-dependency STL watertight/manifold validator.
USE THIS before slicing: only watertight parts should reach the slicer/printer.

Why zero-dep: the sandbox often has no numpy/trimesh. This parses binary AND ASCII
STL with stdlib only and checks the one property that matters for print-readiness:
every triangle edge is shared by EXACTLY TWO triangles (closed manifold => watertight).

Run:  python3 stl_validator.py part1.stl part2.stl ...
Prints per-file: OK/FAIL + triangle count + boundary/non-manifold edge counts.
Exit code: 0 if all watertight, 1 if any fails.
"""
from __future__ import annotations
import struct, sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple


def _read_ascii_stl(path: Path) -> Tuple[int, List[Tuple]]:
    verts: List[Tuple] = []
    for line in Path(path).read_text(errors="replace").splitlines():
        line = line.strip()
        if line.startswith("vertex"):
            p = line.split()[1:4]
            verts.append((float(p[0]), float(p[1]), float(p[2])))
    tris = [tuple(verts[i:i + 3]) for i in range(0, len(verts) - 2, 3)]
    return len(tris), tris


def _read_binary_stl(path: Path) -> Tuple[int, List[Tuple]]:
    data = Path(path).read_bytes()
    count = struct.unpack("<I", data[80:84])[0]
    tris = []
    off = 84
    for _ in range(count):
        vals = struct.unpack("<12fH", data[off:off + 50]); off += 50
        tris.append((vals[3:6], vals[6:9], vals[9:12]))
    return count, tris


def _edge_key(a, b) -> Tuple:
    r = lambda t: (round(t[0], 4), round(t[1], 4), round(t[2], 4))
    ra, rb = r(a), r(b)
    return (ra, rb) if ra <= rb else (rb, ra)


def _tri_area(v0, v1, v2) -> float:
    import math
    ax, ay, az = v1[0] - v0[0], v1[1] - v0[1], v1[2] - v0[2]
    bx, by, bz = v2[0] - v0[0], v2[1] - v0[1], v2[2] - v0[2]
    cx = ay * bz - az * by; cy = az * bx - ax * bz; cz = ax * by - ay * bx
    return 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz)


def validate_stl(path: str | Path, min_tris: int = 12) -> Dict:
    res: Dict = {"ok": False, "errors": [], "warnings": [], "stats": {}}
    try:
        head = Path(path).read_bytes()
        is_ascii = head[:5].lower().lstrip() == b"solid"
        if is_ascii:
            count, tris = _read_ascii_stl(path)
        else:
            count, tris = _read_binary_stl(path)
    except Exception as e:
        res["errors"].append(f"read failed: {e}")
        return res

    res["stats"]["triangles"] = count
    if count < min_tris:
        res["errors"].append(f"only {count} triangles (<{min_tris}); empty/flat")

    degenerate = 0
    for v0, v1, v2 in tris:
        if _tri_area(v0, v1, v2) < 1e-6:
            degenerate += 1
    res["stats"]["degenerate_tris"] = degenerate
    if degenerate:
        res["errors"].append(f"{degenerate} degenerate (zero-area) triangles")

    edge_count: Dict[Tuple, int] = defaultdict(int)
    for v0, v1, v2 in tris:
        for a, b in ((v0, v1), (v1, v2), (v2, v0)):
            edge_count[_edge_key(a, b)] += 1
    boundary = sum(1 for c in edge_count.values() if c == 1)
    non_manifold = sum(1 for c in edge_count.values() if c != 2)
    res["stats"]["boundary_edges"] = boundary
    res["stats"]["non_manifold_edges"] = non_manifold
    if boundary:
        res["errors"].append(f"{boundary} boundary edges -> NOT watertight")
    if non_manifold:
        res["errors"].append(f"{non_manifold} non-manifold edges (shared by !=2 tris)")

    # optional trimesh second opinion if installed
    try:
        import trimesh
        m = trimesh.load(str(path))
        res["stats"]["trimesh_watertight"] = bool(m.is_watertight)
    except Exception:
        pass

    res["ok"] = len(res["errors"]) == 0
    return res


if __name__ == "__main__":
    if not sys.argv[1:]:
        print("usage: python3 stl_validator.py file.stl [...]")
        sys.exit(2)
    all_ok = True
    for p in sys.argv[1:]:
        v = validate_stl(p)
        tag = "OK " if v["ok"] else "FAIL"
        print(f"[{tag}] {p} tris={v['stats'].get('triangles')} "
              f"boundary={v['stats'].get('boundary_edges')} "
              f"nonmanifold={v['stats'].get('non_manifold_edges')}")
        if v["errors"]:
            for e in v["errors"]:
                print("     ", e)
        all_ok = all_ok and v["ok"]
    sys.exit(0 if all_ok else 1)
