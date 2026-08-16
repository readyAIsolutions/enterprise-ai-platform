# Project Rename Across Mixed File Types (2026-07-23)

When renaming a project referenced across HTML, CSS, JS, and Python files:

## One-Pass Python Replacement
```python
import os
from pathlib import Path

project_dir = Path("/path/to/project")
replacements = [
    ("Old Name", "New Name"),
    ("old-name", "new_name"), 
    ("OLD_CONSTANT", "NEW_CONSTANT"),
]

for target, replacement in replacements:
    for pattern in ["*.py", "*.html", "*.js", "*.css"]:
        for file_path in project_dir.rglob(pattern):
            try:
                content = file_path.read_text()
                if target in content:
                    file_path.write_text(content.replace(target, replacement))
            except: pass
```

## Verify
- `git diff --stat` to confirm changes
- Grep old names: `grep -r "Old Name" .` (should return nothing)

## Gotcha
- Script tags in HTML may have inline JS - verify syntax after edit
- CSS class names that look like the old name but are semantic (keep semantic names)