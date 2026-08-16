"""<PROGRAM> — web dashboard + API. Lazy-imports the core so it boots instantly.
Copy into <prog>/web/app.py and set ROOT/PORT/CORE_MODULES."""
import os, sys, json
from flask import Flask, jsonify, render_template_string

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8081
CORE_MODULES = ["module_a", "module_b"]   # lazy-import smoke targets
app = Flask(__name__)

DASH = """<!doctype html><html><head><meta charset=utf-8><title><PROGRAM></title>
<style>body{font:14px/1.5 monospace;background:#0c0c0c;color:#d8d8d8;padding:2rem}
h1{color:#7fd1ff}b{color:#fff}pre{background:#161616;padding:1rem;border-radius:8px}</style></head>
<body><h1><PROGRAM></h1><p>status: <b>{{status}}</b></p>
{% if gate %}<pre>{{gate}}</pre>{% endif %}
<p><a href="/selftest" style="color:#7fd1ff">run self-test</a></p></body></html>"""

@app.route("/")
def index():
    rep = os.path.join(ROOT, "gate_report.json")
    gate = json.dumps(json.load(open(rep)), indent=2) if os.path.exists(rep) else None
    return render_template_string(DASH, status="up", gate=gate)

@app.route("/selftest")
def selftest():
    sys.path.insert(0, ROOT)
    res = {}
    for mod in CORE_MODULES:
        try:
            __import__(mod); res[mod] = "ok"
        except Exception as e:
            res[mod] = f"ERR {e}"
    return jsonify(res)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
