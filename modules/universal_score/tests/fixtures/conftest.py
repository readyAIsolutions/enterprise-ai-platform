"""Prevent the main test suite from collecting the tiny coverage-fixture's own
tests (they only run under the real CoverageProbe subprocess smoke)."""

from __future__ import annotations

collect_ignore = ["covproj"]
