# Multi-Monitor Desktop Icon Placement

## Problem
Desktop icons distributed across all monitors instead of primary only.

## Solution
In the main() function, change item distribution to put all items on primary monitor:

```python
# BEFORE: Items distributed across monitors
per_monitor = []
for i, mon in enumerate(monitors):
    start = i * n // m
    end = (i + 1) * n // m
    per_monitor.append(items[start:end])

# AFTER: All items on primary monitor
per_monitor = []
for i, mon in enumerate(monitors):
    if i == 0:
        per_monitor.append(items)  # All items on primary
    else:
        per_monitor.append([])     # Empty on others
```

## Primary Monitor Detection
Add "primary" detection in `get_monitors()`:

```python
is_primary = "primary" in line
# ...
monitors.sort(key=lambda m: (not m.get("primary", False), m["x"]))
```

## Set Primary Monitor via xrandr
```bash
xrandr --output MONITOR_NAME --primary
```

## GTK EventBox DND Pitfalls
- **No set_relief**: EventBox doesn't have `set_relief()` - remove this call
- **No clicked signal**: Use `button-press-event` instead of `"clicked"` for mouse clicks on EventBox
- **Attribute name conflicts**: Avoid `self.container` - it conflicts with Gtk's readonly property. Use `self.parent_win` instead
- **drag_get_data required**: The `drag-drop` handler must call `widget.drag_get_data()` to trigger `drag-data-received` callback

## External Drop Handler Fix
```python
def _on_window_drop(self, widget, drag_context, x, y, time):
    # MUST call drag_get_data to trigger data reception
    widget.drag_get_data(drag_context, TARGET_TYPES[1], time)
    return True

def _on_window_data(self, widget, drag_context, x, y, data, info, time):
    if data and data.get_uris():
        for uri in data.get_uris():
            path = uri.replace("file://", "").replace("%20", " ")
            # Handle dropped file
    drag_context.finish(True, False, time)
```

## Scaling Modes for Wallpapers
- **fill**: Scale to fill screen, crop if needed (default but may crop aspect ratio)
- **stretch**: Stretch to fit screen (best compatibility, may distort)
- **fit**: Scale to fit within screen bounds (letterbox style)
- **center**: Center original size
- **auto**: Let wallpaper engine decide based on content type

Recommendation: Use "stretch" as default for better compatibility across resolutions.