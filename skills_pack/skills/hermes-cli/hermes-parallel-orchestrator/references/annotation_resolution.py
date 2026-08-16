# Annotation Resolution Helper
# =============================
# When a Python module uses `from __future__ import annotations` (PEP 563),
# all type annotations become strings at runtime.  This breaks any code that
# inspects types via `hasattr(anno, "__dataclass_fields__")` because the
# annotation is the *string* "VoiceConfig", not the actual class.
#
# This helper resolves string annotations back to the real types by looking
# them up in the module where they were defined.

from __future__ import annotations

import sys
from typing import Any


def resolve_annotation(annotation: Any, module_globals: dict) -> Any:
    """If *annotation* is a string (PEP 563), resolve it to the real type
    by searching *module_globals* (the defining module's ``__dict__``).

    Returns the resolved type or the original annotation unchanged.
    """
    if not isinstance(annotation, str):
        return annotation

    # Try the defining module's namespace first
    resolved = module_globals.get(annotation)
    if resolved is not None:
        return resolved

    # Fall back to builtins (str → str, int → int, etc.)
    builtins = (
        __builtins__
        if isinstance(__builtins__, dict)
        else getattr(__builtins__, "__dict__", {})
    )
    resolved = builtins.get(annotation)
    if resolved is not None:
        return resolved

    return annotation


# ── Usage in a config loader ──────────────────────────────────────────────
#
# def _dict_to_config(data: dict) -> MasterchiefConfig:
#     import sys as _sys
#
#     def _populate(target_cls, source_dict):
#         fields = {f.name for f in target_cls.__dataclass_fields__.values()}
#         kwargs = {}
#         for key, value in source_dict.items():
#             if key not in fields:
#                 continue
#             raw_type = target_cls.__dataclass_fields__[key].type
#             # Resolve string annotations caused by:
#             #     from __future__ import annotations
#             field_type = resolve_annotation(
#                 raw_type,
#                 _sys.modules[target_cls.__module__].__dict__,
#             )
#             if isinstance(value, dict) and hasattr(field_type, "__dataclass_fields__"):
#                 kwargs[key] = _populate(field_type, value)
#             else:
#                 kwargs[key] = value
#         return target_cls(**kwargs)
#
#     cfg = _populate(MasterchiefConfig, data)
#     return cfg


# ── Alternative: just remove the future import ────────────────────────────
#
# If your config module does runtime type inspection, the simplest fix is to
# REMOVE this line from the top of the file:
#
#     from __future__ import annotations
#
# That restores the pre-PEP-563 behavior where annotations are actual type
# objects at runtime.  This is fine for config modules that don't need forward
# references or deferred evaluation.
