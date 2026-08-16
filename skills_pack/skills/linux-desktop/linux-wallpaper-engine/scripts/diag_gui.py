#!/usr/bin/env python3
"""Grab the Lumen main window under a virtual display to triage a white/blank
GUI bug.

WHY: when LO reports "Lumen is just a white screen" but the app boots without a
traceback, the white is almost always an *overlaying wallpaper surface*, not the
GUI. This script isolates the GUI by using a STUB engine (no wallpaper windows
are created) and grabs the window to /tmp/gui.png so you can confirm the GUI
renders dark/structured.

RUN (from the lumen repo root, where `import lumen` works):
    xvfb-run -a python /path/to/diag_gui.py
Then measure brightness with PIL — see references/debug-white-screen.md.

If the grab is dark + structured -> the GUI is fine; fix window stacking.
If the grab is white -> the GUI/QSS is the problem.
"""
import os
import sys
from PyQt6.QtWidgets import QApplication

# Run this from the lumen repo root so `import lumen` resolves.
sys.path.insert(0, os.getcwd())


class StubEngine:
    """No-op engine: apply() etc. do nothing, so no wallpaper windows open."""
    def apply(self, *a, **k): pass
    def set_volume(self, *a, **k): pass
    def set_slideshow(self, *a, **k): pass
    def randomize_now(self, *a, **k): pass
    def apply_config_assignments(self, *a, **k): pass
    def shutdown(self, *a, **k): pass
    windows = []


def main() -> int:
    from lumen.ui.main_window import MainWindow
    from lumen.ui.styles import load_stylesheet
    app = QApplication(sys.argv)
    app.setStyleSheet(load_stylesheet())
    w = MainWindow(StubEngine())
    w.show()
    app.processEvents()
    out = "/tmp/gui.png"
    w.grab().save(out)
    print(f"grabbed {w.width()}x{w.height()} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
