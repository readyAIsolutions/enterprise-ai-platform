"""
Reusable AppImage/PyPI deploy-gate test: prove every non-Python shippable asset is
declared by a [tool.setuptools.package-data] glob in pyproject.toml — WITHOUT
building a wheel (a dev venv may lack setuptools.build_meta, and a wheel is slow).

Drop into a project's tests/ dir, set PKG_NAME, run with pytest.
Source-of-truth: pyproject.toml globs + on-disk reality. Do NOT trust
*.egg-info/SOURCES.txt (regenerated from the last build, can be stale).

This catches the #1 silent AppImage failure: a theme/sample/icon missing from the
squashfs because package-data globs forgot to declare it.
"""
import os
import glob
import tomllib
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG_NAME = "lumen"  # <-- set to the package dir name under REPO_ROOT
PKG_ROOT = os.path.join(REPO_ROOT, PKG_NAME)


def _load_pkg_data_globs():
    pyp = os.path.join(REPO_ROOT, "pyproject.toml")
    with open(pyp, "rb") as f:
        cfg = tomllib.load(f)
    data = cfg.get("tool", {}).get("setuptools", {}).get("package-data", {})
    globs = []
    for pkg, patterns in data.items():
        base = PKG_ROOT if pkg in ("*", PKG_NAME) else os.path.join(REPO_ROOT, pkg.replace(".", os.sep))
        for pat in patterns:
            globs.append((base, pat))
    return globs


def _expand(globs):
    covered = set()
    for base, pat in globs:
        if pat in ("*", "") or pat.endswith("/"):
            for root, _, files in os.walk(base):
                for fn in files:
                    covered.add(os.path.relpath(os.path.join(root, fn), base))
        else:
            for hit in glob.glob(os.path.join(base, pat), recursive=True):
                if os.path.isfile(hit):
                    covered.add(os.path.relpath(hit, base))
    return covered


@pytest.mark.parametrize("item", sorted(_expand(_load_pkg_data_globs())))
def test_every_declared_asset_exists(item):
    # every glob-matched file must actually be on disk
    assert os.path.exists(os.path.join(PKG_ROOT, item)), f"declared but missing: {item}"


def test_shippable_assets_are_covered():
    globs = _load_pkg_data_globs()
    covered = _expand(globs)
    missing = []
    for root, _, files in os.walk(PKG_ROOT):
        if "__pycache__" in root:
            continue
        for fn in files:
            if fn.endswith(".py") or fn.endswith(".pyc"):
                continue
            rel = os.path.relpath(os.path.join(root, fn), PKG_ROOT)
            if rel not in covered:
                missing.append(rel)
    assert not missing, f"shippable assets NOT covered by any glob: {missing[:10]}"
