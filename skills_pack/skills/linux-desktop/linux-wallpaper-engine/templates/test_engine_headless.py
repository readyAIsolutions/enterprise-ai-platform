"""STARTER TEMPLATE — headless engine-logic regression tests for Lumen.

Copy this into ``tests/test_engine.py`` (or ``tests/test_engine_headless.py``)
and adapt. It locks the AMD multi-monitor reboot-fix invariants WITHOUT a GPU
or X server by stubbing the window factory, monitor/x11 probes, and Config,
while running the REAL ``apply`` / ``apply_config_assignments`` /
``drop_all_to_safe`` logic.

Technique + gotchas: references/headless-engine-tests.md (linux-wallpaper-engine
skill). Requires the project's offscreen-QApp helper ``tests/_qt.py::get_qapp``.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from _qt import get_qapp  # offscreen QApplication; imports WebEngine first
from lumen.wallpaper import engine as engine_mod
from lumen.wallpaper.engine import WallpaperEngine


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
class FakeWin:
    """Wallpaper surface stand-in: records lifecycle, never touches Chromium/X."""

    def __init__(self) -> None:
        self.paused = False
        self.shown = False
        self.closed = False

    def show_on_desktop(self) -> None:
        self.shown = True

    def show(self) -> None:
        self.shown = True

    def close(self) -> None:
        self.closed = True

    def deleteLater(self) -> None:
        pass

    def lower(self) -> None:
        pass

    def setScreen(self, screen) -> None:
        pass

    def setWindowFlags(self, flags) -> None:
        pass

    def showFullScreen(self) -> None:
        self.shown = True

    def apply_geometry(self) -> None:
        pass

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False

    def set_volume(self, vol) -> None:
        pass

    def reload(self) -> None:
        pass

    def winId(self) -> int:
        return 1


class FakeConfig:
    """In-memory Config stand-in — keeps tests from writing ~/.config/lumen."""

    def __init__(self, assignments=None) -> None:
        self.data = {"assignments": dict(assignments or {})}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value, persist=True) -> None:
        self.data[key] = value

    def assignment(self, screen):
        return self.data["assignments"].get(screen)

    def set_assignment(self, screen, wid) -> None:
        self.data["assignments"][screen] = wid

    def clear_assignment(self, screen) -> None:
        self.data["assignments"].pop(screen, None)


def _fake_wp(kind: str, wid: str = "wp1", name: str = "Fake") -> SimpleNamespace:
    return SimpleNamespace(
        kind=kind, id=wid, name=name, entry="index.html",
        is_renderable=lambda: True,
    )


def _fake_screen(name: str = "DP-0") -> MagicMock:
    scr = MagicMock()
    scr.name.return_value = name
    geo = MagicMock()
    geo.x.return_value = 0
    geo.y.return_value = 0
    geo.width.return_value = 1920
    geo.height.return_value = 1080
    scr.geometry.return_value = geo
    return scr


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _qapp():
    get_qapp()


def _make_engine(monkeypatch, safe_mode: bool = False, max_webgl: int = 1) -> WallpaperEngine:
    eng = WallpaperEngine(safe_mode=safe_mode)
    eng.max_webgl = max_webgl
    # Stub the window factory (avoids real QWebEngineView construction).
    monkeypatch.setattr(
        WallpaperEngine, "_make_window",
        staticmethod(lambda screen, wp: FakeWin()),
    )
    # Stub monitor + X11 probes so apply() never touches a display.
    monkeypatch.setattr(engine_mod.monitors, "screen_by_name",
                        lambda n: _fake_screen(n))
    monkeypatch.setattr(engine_mod.x11, "session_is_wayland", lambda: False)
    monkeypatch.setattr(engine_mod.x11, "set_wallpaper_window",
                        lambda *a, **k: False)
    # Replace the persistent Config with an in-memory fake.
    monkeypatch.setattr(eng, "cfg", FakeConfig())
    return eng


# ---------------------------------------------------------------------------
# Invariant tests (the AMD-reboot-fix locks)
# ---------------------------------------------------------------------------
def test_safe_mode_skips_paint(monkeypatch):
    eng = _make_engine(monkeypatch, safe_mode=True)
    eng.apply(_fake_wp("shader"), "DP-0")
    assert "DP-0" not in eng.windows
    assert "DP-0" not in eng._webgl_screens


def test_gl_context_cap_blocks_second_webgl_surface(monkeypatch):
    eng = _make_engine(monkeypatch, max_webgl=1)
    eng.apply(_fake_wp("shader", "wp1", "A"), "DP-0")
    assert "DP-0" in eng.windows and "DP-0" in eng._webgl_screens
    # 2nd live WebGL surface MUST be refused (the 4-context hammer guard).
    eng.apply(_fake_wp("shader", "wp2", "B"), "HDMI-0")
    assert "HDMI-0" not in eng.windows and "HDMI-0" not in eng._webgl_screens


def test_gl_cap_honours_raised_limit(monkeypatch):
    eng = _make_engine(monkeypatch, max_webgl=2)
    eng.apply(_fake_wp("shader", "wp1", "A"), "DP-0")
    eng.apply(_fake_wp("web", "wp2", "B"), "HDMI-0")
    assert len(eng._webgl_screens) == 2
    eng.apply(_fake_wp("web", "wp3", "C"), "DP-1")
    assert "DP-1" not in eng._webgl_screens


def test_non_webgl_does_not_consume_gl_cap(monkeypatch):
    eng = _make_engine(monkeypatch, max_webgl=1)
    eng.apply(_fake_wp("image", "img1"), "DP-0")
    assert "DP-0" in eng.windows and "DP-0" not in eng._webgl_screens
    eng.apply(_fake_wp("shader", "sh1"), "HDMI-0")
    assert "HDMI-0" in eng._webgl_screens


def test_apply_config_assignments_applies_renderable(monkeypatch):
    eng = _make_engine(monkeypatch, safe_mode=False)
    eng.cfg.data["assignments"] = {"DP-0": "wp1"}
    monkeypatch.setattr(engine_mod, "scan_library",
                        lambda: [_fake_wp("shader", "wp1")])
    eng.apply_config_assignments()
    assert "DP-0" in eng.windows


def test_apply_config_assignments_drops_missing_wallpaper(monkeypatch):
    eng = _make_engine(monkeypatch, safe_mode=False)
    eng.cfg.data["assignments"] = {"DP-0": "wp_missing"}
    monkeypatch.setattr(engine_mod, "scan_library", lambda: [])
    eng.apply_config_assignments()
    assert "DP-0" not in eng.windows
    assert eng.cfg.assignment("DP-0") is None


def test_drop_all_to_safe_tears_down_and_locks(monkeypatch):
    eng = _make_engine(monkeypatch, safe_mode=False)
    eng.apply(_fake_wp("shader", "wp1"), "DP-0")
    assert eng.windows and eng._webgl_screens
    eng.drop_all_to_safe()
    assert eng.safe_mode is True
    assert eng.windows == {}
    assert eng._webgl_screens == set()
