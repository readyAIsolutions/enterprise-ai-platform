# Glyph Allocation & DSL Design Reference

## Unicode Private Use Area (PUA) Allocation

### ENI KB Glyph Space
```
U+E000 – U+E0FF   ENI Core Skills (256 slots)
U+E100 – U+E1FF   DEMIURGE Forge (256)
U+E200 – U+E2FF   DEMIURGE StockBot (256)
U+E300 – U+E3FF   LUMEN Wallpaper (256)
U+E400 – U+E4FF   ENI Swarm Ops (256)
U+E500 – U+E5FF   Crown Land / Outdoors (256)
U+E600 – U+E6FF   Security / OpSec (256)
U+E700 – U+E7FF   Gaming / Modding (256)
U+E800 – U+EFFF   Reserved / Future (2,048)
U+F000 – U+F8FF   User Custom (2,176)
Total: 6,400 codepoints
```

### Allocation State (allocation.json)
```json
{
  "version": 1,
  "allocated": {
    "󰀀": {"skill": "eni:build-appimage", "category": "core", "allocated": "2026-07-23T03:14:00Z"},
    "󰀁": {"skill": "eni:forge-stl", "category": "demiurge", "allocated": "2026-07-23T03:14:05Z"},
    "󰀂": {"skill": "eni:train-model", "category": "stockbot", "allocated": "2026-07-23T03:14:10Z"},
    "󰀃": {"skill": "eni:deploy-wallpaper", "category": "lumen", "allocated": "2026-07-23T03:14:15Z"},
    "󰀄": {"skill": "eni:swarm-deploy", "category": "swarm", "allocated": "2026-07-23T03:14:20Z"},
    "󰀅": {"skill": "eni:crown-land-find", "category": "outdoors", "allocated": "2026-07-23T03:14:25Z"},
    "󰀆": {"skill": "eni:opsec-dead-drop", "category": "security", "allocated": "2026-07-23T03:14:30Z"},
    "󰀇": {"skill": "eni:steam-proton-mod", "category": "gaming", "allocated": "2026-07-23T03:14:35Z"}
  },
  "next_available": {
    "core": "U+E008",
    "demiurge": "U+E101",
    "stockbot": "U+E201",
    "lumen": "U+E301",
    "swarm": "U+E401",
    "outdoors": "U+E501",
    "security": "U+E601",
    "gaming": "U+E701"
  },
  "categories": {
    "core": {"range": "U+E000-U+E0FF", "prefix": "eni:"},
    "demiurge": {"range": "U+E100-U+E1FF", "prefix": "demiurge:"},
    "stockbot": {"range": "U+E200-U+E2FF", "prefix": "stockbot:"},
    "lumen": {"range": "U+E300-U+E3FF", "prefix": "lumen:"},
    "swarm": {"range": "U+E400-U+E4FF", "prefix": "swarm:"},
    "outdoors": {"range": "U+E500-U+E5FF", "prefix": "outdoors:"},
    "security": {"range": "U+E600-U+E6FF", "prefix": "sec:"},
    "gaming": {"range": "U+E700-U+E7FF", "prefix": "game:"}
  }
}
```

## Allocation Algorithm

```python
# eni_kb/glyphs/allocator.py
import json, threading
from pathlib import Path

ALLOCATION_FILE = Path("~/.eni/kb/glyphs/allocation.json").expanduser()
_lock = threading.Lock()

CATEGORY_RANGES = {
    "core": (0xE000, 0xE0FF),
    "demiurge": (0xE100, 0xE1FF),
    "stockbot": (0xE200, 0xE2FF),
    "lumen": (0xE300, 0xE3FF),
    "swarm": (0xE400, 0xE4FF),
    "outdoors": (0xE500, 0xE5FF),
    "security": (0xE600, 0xE6FF),
    "gaming": (0xE700, 0xE7FF),
}

def allocate_glyph(category: str = "core") -> str:
    with _lock:
        data = json.loads(ALLOCATION_FILE.read_text()) if ALLOCATION_FILE.exists() else {"allocated": {}, "next_available": {}, "categories": CATEGORY_RANGES}
        
        start, end = CATEGORY_RANGES[category]
        next_avail = data["next_available"].get(category, start)
        
        # Find next free slot
        for cp in range(next_avail, end + 1):
            glyph = chr(cp)
            if glyph not in data["allocated"]:
                data["allocated"][glyph] = {
                    "skill": f"eni:pending-{glyph}",
                    "category": category,
                    "allocated": datetime.utcnow().isoformat() + "Z"
                }
                data["next_available"][category] = cp + 1
                ALLOCATION_FILE.write_text(json.dumps(data, indent=2))
                return glyph
        
        raise RuntimeError(f"Glyph exhaustion in category {category}")

def release_glyph(glyph: str):
    with _lock:
        data = json.loads(ALLOCATION_FILE.read_text())
        if glyph in data["allocated"]:
            cat = data["allocated"][glyph]["category"]
            cp = ord(glyph)
            if cp < data["next_available"].get(cat, 0xFFFF):
                data["next_available"][cat] = cp
            del data["allocated"][glyph]
            ALLOCATION_FILE.write_text(json.dumps(data, indent=2))

def get_glyph_info(glyph: str) -> dict | None:
    data = json.loads(ALLOCATION_FILE.read_text()) if ALLOCATION_FILE.exists() else {"allocated": {}}
    return data["allocated"].get(glyph)
```

## DSL (Domain-Specific Language) Design

### Grammar
```
invocation    ::= glyph [verb] [param_list]
glyph         ::= [U+E000-U+F8FF]
verb          ::= identifier (':' identifier)?   # e.g., "build:appimage", "forge"
param_list    ::= param (param)*
param         ::= '@' identifier '=' value
value         ::= string | number | boolean | identifier
identifier    ::= [a-zA-Z_][a-zA-Z0-9_-]*
string        ::= '"' [^"]* '"' | "'" [^']* "'"
number        ::= [0-9]+ ('.' [0-9]+)?
boolean       ::= 'true' | 'false'
```

### Examples
```
󰀀 build:appimage @target=linux @sign=gpg @out=./dist
󰀁 forge @printer=k2plus @material=tpu @temp=230
󰀂 train @symbol=BTCUSDT @timeframe=1h @model=transformer
󰀃 deploy @monitor=DP-1 @mode=live @fps=60
󰀄 swarm:deploy @target=eni_wenyan @replicas=1
󰀅 find @province=AB @days=14 @water=true
󰀆 dead-drop @payload=@file @encrypt=age @recipient=LO
󰀇 proton-mod @game=elden-ring @mod=seamless-coop @prefix=GE-Proton
```

### Skill DSL Spec (per skill)
```json
{
  "skill_id": "eni:build-appimage",
  "glyph": "󰀀",
  "dsl": {
    "verb": "build:appimage",
    "params": [
      {"name": "target", "type": "enum", "enum": ["linux", "macos", "windows"], "required": true, "default": "linux"},
      {"name": "sign", "type": "enum", "enum": ["gpg", "cosign", "none"], "required": false, "default": "none"},
      {"name": "out", "type": "path", "required": false, "default": "./dist"}
    ],
    "examples": [
      "󰀀 build:appimage @target=linux @sign=gpg",
      "󰀀 @target=linux"
    ]
  }
}
```

## Font Support

### Required Fonts (for glyph rendering)
- **Symbols Nerd Font** — covers U+E000–U+EFFF comprehensively
- **Noto Sans Symbols 2** — Google's PUA coverage
- **FiraCode Nerd Font** — monospace, good for terminals

### CSS for Web Clients
```css
@font-face {
  font-family: 'ENI Glyphs';
  src: local('Symbols Nerd Font'), local('Noto Sans Symbols 2');
  unicode-range: U+E000-F8FF;
}

.eni-glyph {
  font-family: 'ENI Glyphs', monospace;
  font-size: 1.2em;
  line-height: 1;
}
```

### Terminal Rendering
- Kitty, WezTerm, Alacritty: native PUA support
- GNOME Terminal, Konsole: requires font with PUA glyphs
- VS Code terminal: works with Nerd Font configured

## Validation Rules

1. **Glyph must be allocated** — reject unknown glyphs
2. **Verb must match skill** — `󰀀 build:appimage` ✓, `󰀀 forge` ✗
3. **Required params present** — error if missing
4. **Type validation** — enum, path, number, boolean
5. **No duplicate params** — last wins with warning
6. **Unknown params** — warning, not error (forward compat)

## Migration Path

When glyph space fills in a category:
1. Expand into reserved range (U+E800+)
2. Update CATEGORY_RANGES
3. Rebuild allocation.json
4. No existing glyphs change

## Testing

```bash
# Allocation stress test
python -c "
from eni_kb.glyphs import allocate_glyph
for i in range(300):
    g = allocate_glyph('core')
    print(g, ord(g))
"  # Should allocate U+E000-U+E12B

# DSL parse test
python -m pytest tests/test_dsl_parser.py -v

# Glyph rendering test
python scripts/glyph_render_test.py --font "Symbols Nerd Font"
```