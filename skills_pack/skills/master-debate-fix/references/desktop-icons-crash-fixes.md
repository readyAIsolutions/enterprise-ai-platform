# Desktop Icons Crash Patterns

## SIGKILL Crashes (-9)
Cause: System kills process for excessive memory/CPU or X11 errors.
Fix: 
- Use stretch scaling to reduce GPU load
- Reduce icon density on screen
- Add proper signal handlers for SIGINT/SIGTERM

## DND (Drag-and-Drop) Fixes
EventBox requires explicit data request in drag-drop handler:
```python
def _on_window_drop(self, widget, drag_context, x, y, time):
    widget.drag_get_data(drag_context, TARGET_TYPES[1], time)
    return True
```

## Primary Monitor Enforcement
To show desktop icons only on primary monitor:
```python
# Sort monitors: primary first
monitors.sort(key=lambda m: (not m.get("primary", False), m["x"]))

# Only show icons on first monitor
for i, mon in enumerate(monitors):
    if i == 0:
        per_monitor.append(items)  # Primary
    else:
        per_monitor.append([])     # Others empty
```