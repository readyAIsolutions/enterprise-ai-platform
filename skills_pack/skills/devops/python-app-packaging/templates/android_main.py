"""<PROGRAM> Android app — bundles the Flask dashboard and shows it in a WebView.
Build: cd android && buildozer android debug  (needs buildozer + Android SDK)."""
import os, sys, threading
from kivy.app import App
from kivy.uix.webview import WebView

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8081

def _start_server():
    sys.path.insert(0, APP_DIR)
    import web.app as wa
    wa.app.run(host="127.0.0.1", port=PORT, debug=False)

class ProgramApp(App):
    def build(self):
        threading.Thread(target=_start_server, daemon=True).start()
        return WebView(url=f"http://127.0.0.1:{PORT}/")

if __name__ == "__main__":
    ProgramApp().run()
