"""Tests for the tiny CoverageProbe fixture project."""


def test_add() -> None:
    from app.mod1 import add

    assert add(1, 2) == 3


def test_double() -> None:
    from app.mod1 import double

    assert double(4) == 8


def test_classify_positive() -> None:
    from app.mod2 import classify

    assert classify(5) == "positive"


def test_triple() -> None:
    from app.mod2 import triple

    assert triple(3) == 9
