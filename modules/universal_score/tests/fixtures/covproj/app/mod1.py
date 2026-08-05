"""Fixture module 1 — deterministic, fully-covered happy path."""


def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


def double(x: int) -> int:
    """Double an integer."""
    return x * 2
