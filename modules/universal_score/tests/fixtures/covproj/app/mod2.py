"""Fixture module 2 — one uncovered branch to give a non-100% measurement."""


def classify(value: int) -> str:
    """Return a label; the negative branch is left untested on purpose."""
    if value >= 0:
        return "positive"
    return "negative"  # pragma: no cover - intentionally untested branch


def triple(x: int) -> int:
    """Triple an integer."""
    return x * 3
