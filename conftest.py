"""Root conftest — makes this repo importable as the `enterprise` package
regardless of the on-disk directory name.

Locally the directory may be named `enterprise`; in CI (repo
readyAIsolutions/enterprise-ai-platform) GitHub names the checkout
`enterprise-ai-platform`. Many modules/tests `import enterprise.*`, so we must
guarantee the `enterprise` module resolves to this repo root in BOTH layouts.

Strategy:
  1. Put this repo's PARENT on sys.path (so a dir literally named `enterprise`
     resolves as the package when that's the checkout name).
  2. Otherwise, alias this repo root's `__init__.py` under the module name
     `enterprise` so `enterprise.modules.*`, `enterprise.platform_kernel`, etc.
     all resolve here without depending on the directory name.
"""
from __future__ import annotations

import importlib.util
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_ROOT)

# 1) name-based resolution (local layout: parent contains `enterprise`)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

# 2) name-agnostic alias (CI layout: checkout dir != `enterprise`)
_SELF = os.path.join(_PARENT, "enterprise")
if not os.path.isdir(_SELF) and os.path.basename(_ROOT) != "enterprise":
    init = os.path.join(_ROOT, "__init__.py")
    if os.path.isfile(init) and "enterprise" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "enterprise", init, submodule_search_locations=[_ROOT]
        )
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            sys.modules["enterprise"] = mod
            spec.loader.exec_module(mod)
