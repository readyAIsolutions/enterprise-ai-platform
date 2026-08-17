#!/usr/bin/env python3
"""ENI two-pane desktop chat — Hermes (left) + Local (right), side by side.

Native GTK3 + WebKit2 app. Each pane is a WebKitWebView pointed at the local
bridge UI (http://127.0.0.1:<port>/chat/left and /chat/right). The bridge is
started automatically on launch (in-thread) if it isn't already up.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
PORT = int(os.environ.get("ENI_DESKTOP_PORT", "8765"))

import gi  # noqa: E402
gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gtk, WebKit2  # noqa: E402


def _bridge_alive() -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def _start_bridge() -> None:
    if _bridge_alive():
        return
    env = dict(os.environ)
    sys.path.insert(0, str(_HERE))
    from bridge import main as bridge_main
    thread = threading.Thread(target=bridge_main, daemon=True)
    thread.start()
    for _ in range(40):
        if _bridge_alive():
            return
        time.sleep(0.1)


def _pane(name: str) -> WebKit2.WebView:
    web = WebKit2.WebView()
    settings = web.get_settings()
    settings.set_property("enable-developer-extras", True)
    settings.set_property("enable-javascript", True)
    web.load_uri(f"http://127.0.0.1:{PORT}/chat/{name}")
    return web


class App:
    def __init__(self) -> None:
        _start_bridge()
        self.win = Gtk.Window(title="ENI Desktop — Hermes | Local")
        self.win.set_default_size(1280, 820)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.props.title = "ENI Desktop"
        header.props.subtitle = "Hermes (left)   |   Local (right)"
        self.win.set_titlebar(header)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.position = 640
        self.left = _pane("left")
        self.right = _pane("right")
        for child, label in ((self.left, "Hermes"), (self.right, "Local")):
            frame = Gtk.Frame(label=label)
            frame.add(child)
            frame.set_shadow_type(Gtk.ShadowType.IN)
            if label == "Hermes":
                paned.pack1(frame, True, False)
            else:
                paned.pack2(frame, True, False)

        box.pack_start(paned, True, True, 0)
        self.win.add(box)
        self.win.connect("destroy", Gtk.main_quit)
        self.win.show_all()

    def run(self) -> None:
        Gtk.main()


def main() -> None:
    App().run()


if __name__ == "__main__":
    main()