#!/usr/bin/env python3
"""stl_validator.py - zero-dependency STL watertight/manifold checker.

Enforces "100% ready to print": a print-ready mesh must be (1) watertight -
every triangle edge shared by exactly 2 triangles; (2) manifold - no degenerate
(zero-area) triangles; (3) sane - finite bbox, non-trivial triangle count.

Reads BOTH ASCII and binary STL (OpenSCAD emits ASCII by default). If `trimesh`
is importable, runs is_watertight as a second opinion.

Usage:  python3 stl_validator.py file1.stl [file2.stl ...]
Returns exit code 0 if ALL files watertight, else 1.
"""
from __future__ import annotations
import struct, sys, json
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
    tris = [tuple(verts[i:i+3]) for i in range(0, len(verts)-2, 3)]
    return len(tris), tris


def _read_binary_stl(path: Path) -> Tuple[int, List[Tuple]]:
    data = Path(path).read_bytes()
    if len(data) < 84:
        raise ValueError("file too small to be STL")
    count = struct.unpack("<I", data[80:84])[0]
    tris = []
    off = 84
    for _ in range(count):
        vals = struct.unpack("<12fH", data[off:off+50])
        off += 50
        tris.append((vals[3:6], vals[6:9], vals[9:12]))
    return count, tris


def _edge_key(a, b) -> Tuple:
    r = lambda t: (round(t[0], 4), round(t[1], 4), round(t[2], 4))
    ra, rb = r(a), r(b)
    return (ra, rb) if ra <= rb else (rb, ra)


def _tri_area(v0, v1, v2) -> float:
    import math
    ax, ay, az = v1[0]-v0[0], v1[1]-v0[1], v1[2]-v0[2]
    bx, by, bz = v2[0]-v0[0], v2[1]-v0[1], v2[2]-v0[2]
    cx = ay*bz-az*by; cy = az*bx-ax*bz; cz = ax*by-ay*bx
    return 0.5*math.sqrt(cx*cx+cy*cy+cz*cz)


def validate_stl(path: str | Path, min_tris: int = 12) -> Dict:
    path = Path(path)
    res: Dict = {"ok": False, "errors": [], "warnings": [], "stats": {}}
    try:
        head = Path(path).read_bytes()
        is_ascii = head[:5].lstrip().lower() == b"solid"
        count, tris = _read_ascii_stl(path) if is_ascii else _read_binary_stl(path)
    except Exception as e:
        res["errors"].append(f"read failed: {e}")
        return res

    res["stats"]["triangles"] = count
    if count < min_tris:
        res["errors"].append(f"only {count} triangles (<{min_tris}); empty/flat")

    degenerate = 0
    mn = [float("inf")]*3; mx = [-float("inf")]*3
    for v0, v1, v2 in tris:
        if _tri_area(v0, v1, v2) < 1e-6:
            degenerate += 1
        for v in (v0, v1, v2):
            for k in range(3):
                mn[k] = min(mn[k], v[k]); mx[k] = max(mx[k], v[k])
    res["stats"]["bbox"] = [round(mx[k]-mn[k], 3) for k in range(3)]
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
        res["errors"].append(f"{non_manifold} non-manifold edges")

    try:
        import trimesh
        m = trimesh.load(str(path))
        res["stats"]["trimesh_watertight"] = bool(m.is_watertight)
        if not m.is_watertight and not boundary:
            res["warnings"].append("trimesh: non-watertight (edge-check passed; normal flip?)")
    except Exception:
        pass

    res["ok"] = len(res["errors"]) == 0
    return res


if __name__ == "__main__":
    rc = 0
    for p in sys.argv[1:]:
        r = validate_stl(p)
        print(p, "->", "OK" if r["ok"] else "FAIL", r["stats"])
        if r["errors"]:
            print("   ", r["errors"])
        rc |= 0 if r["ok"] else 1
    sys.exit(rc)
