# Troubleshooting

## Provider Validation in Learned Routing

When `learned_routing.json` contains invalid provider names (like `"all-free"` which isn't in `_PROVIDER_DEFS`), the engine hangs. Fix:

1. In `learn.py`, validate providers before writing:
```python
valid_providers = [s["provider"] for s in scored if s["provider"] in _PROVIDER_DEFS]
```

2. In `engine.py` `_rank()` function, skip invalid providers:
```python
def _rank(p: str):
    if p not in _PROVIDER_DEFS:
        return (9999, True, True)  # Sort to end, mark unusable
```

## Desktop Icon Drag-and-Drop

Symptoms: DND works internally but not from file managers.

Fix: Add `Gtk.TargetFlags.OTHER_APP` to target entries:
```python
TARGET_TYPES = [
    Gtk.TargetEntry.new("text/uri-list", Gtk.TargetFlags.SAME_APP, 100),
    Gtk.TargetEntry.new("text/uri-list", Gtk.TargetFlags.OTHER_APP, 101),
]
```

## Scaling Options for Wallpapers

linux-wallpaperengine supports: `fill`, `fit`, `stretch`, `center`, `auto`

Add to CLI: `--scaling <mode>`