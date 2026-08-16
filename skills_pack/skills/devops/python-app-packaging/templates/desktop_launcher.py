"""<PROGRAM> desktop app — PyQt6 WebView that launches the local web dashboard.
Copy into <prog>/desktop/launcher.py. Requires PyQt6 + PyQt6-WebEngine."""
import os, sys, subprocess
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8081

def main():
    srv = subprocess.Popen([sys.executable, os.path.join(ROOT, "web", "app.py")], cwd=ROOT)
    app = QApplication(sys.argv)
    w = QWebEngineView()
    w.setWindowTitle("<PROGRAM>")
    w.resize(1280, 860)
    w.load(QUrl(f"http://localhost:{PORT}/"))
    w.show()
    rc = app.exec()
    srv.terminate()
    sys.exit(rc)

if __name__ == "__main__":
    main()
