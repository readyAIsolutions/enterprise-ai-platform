# Desktop Icons Monitor Configuration

## Problem
Desktop icons/folders were distributed across all monitors instead of appearing on the primary monitor only.

## Solution
Changed `_place_icons()` distribution logic in `desktop-icons.py`:

### Before (line 350-357)
```python
# Distribute items across monitors (first half on primary, etc)
n = len(items)
m = len(monitors)
per_monitor = []
for i, mon in enumerate(monitors):
    start = i * n // m
    end = (i + 1) * n // m
    per_monitor.append(items[start:end])
```

### After
```python
# Put ALL items on primary monitor (first in list), empty lists for others
# This ensures folders show on main screen
n = len(items)
m = len(monitors)
per_monitor = []
for i, mon in enumerate(monitors):
    if i == 0:
        per_monitor.append(items)  # All items on primary monitor
    else:
        per_monitor.append([])     # Empty on other monitors
```

## Primary Monitor Detection Fix (get_monitors)
Added primary detection and sorting:
```python
is_primary = "primary" in line
# ...
monitors.sort(key=lambda m: (not m.get("primary", False), m["x"]))
```

This ensures the primary monitor is always first in the list and gets all icons.

---

## GTK EventBox DND Fixes

### Crash Fixes (July 2026)

1. **Container attribute renamed** - `self.container = container` to `self.parent_win = parent_window`
   - Reason: `container` is a readonly Gtk property, causing `RuntimeError: field is not writable`

2. **Removed non-existent method** - Removed `self.set_relief(Gtk.ReliefStyle.NONE)`
   - Reason: `EventBox` does not have `set_relief()` method

3. **Fixed click event signal** - Changed `"clicked"` to `"button-press-event"`
   - Reason: `EventBox` doesn't emit "clicked" signal

4. **Fixed DND data retrieval** - Added `drag_get_data()` call in drop handlers
   - Reason: Must request data from drag source before `drag-data-received` fires

### Working DND Pattern
```python
# In _on_window_drop handler:
def _on_window_drop(self, widget, drag_context, x, y, time):
    widget.drag_get_data(drag_context, TARGET_TYPES[1], time)
    return True

# In icon's _on_drag_drop:
def _on_drag_drop(self, widget, drag_context, x, y, time):
    widget.drag_get_data(drag_context, TARGET_TYPES[1], time)
    return True
```

---

## Wallpaper Picker Defaults

- Default scaling: `stretch` (better compatibility than fill)
- Default target: primary monitor only
- Added validation: checks wallpaper folder and project.json exist before launching