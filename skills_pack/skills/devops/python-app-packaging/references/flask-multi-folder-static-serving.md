# Flask Multi-Folder Static File Serving Patterns

## Problem
Flask's `static_folder` and `static_url_path` only support a single static folder by default. Projects like Demiurge Marketing have multiple static folders:
- `admin/` — admin panel HTML/JS/CSS
- `website/` — marketing website HTML/CSS/JS/images

## Solution: Custom Routes for Each Folder

```python
import os
from flask import Flask, send_from_directory

app = Flask(__name__, static_folder='../admin', static_url_path='/admin')

# Serve website static files (CSS, JS, images)
@app.route('/styles.css')
def serve_styles():
    return send_from_directory('../website', 'styles.css')

@app.route('/script.js')
def serve_script():
    return send_from_directory('../website', 'script.js')

@app.route('/images/<path:filename>')
def serve_images(filename):
    return send_from_directory('../website/images', filename)

# Or use a catch-all for the website folder (careful: order matters!)
@app.route('/<path:filename>')
def serve_website_files(filename):
    website_path = os.path.join(os.path.dirname(__file__), '..', 'website')
    if os.path.exists(os.path.join(website_path, filename)):
        return send_from_directory(website_path, filename)
    # Fall through to 404 if not found
    return "Not found", 404
```

## Key Points
- **Route order matters**: Specific routes (`/styles.css`) must come before catch-all routes
- **Use `send_from_directory`**: Secure, handles path traversal safely
- **Absolute paths**: Use `os.path.join(os.path.dirname(__file__), '..', 'folder')` for reliability
- **Blueprint alternative**: For larger apps, use Flask Blueprints with separate `static_folder` per blueprint

## Blueprint Pattern (Cleaner for Large Apps)
```python
from flask import Blueprint

admin_bp = Blueprint('admin', __name__, static_folder='../admin', static_url_path='/admin')
website_bp = Blueprint('website', __name__, static_folder='../website', static_url_path='')

app.register_blueprint(admin_bp)
app.register_blueprint(website_bp)
```

This gives each blueprint its own static folder and URL prefix automatically.

## Related Pitfall (Already Documented in SKILL.md)
**Flask 2.x incompatible with Python 3.14+** — `pkgutil.get_loader` removed. Fix: `pip install flask>=3.1.3,<4`