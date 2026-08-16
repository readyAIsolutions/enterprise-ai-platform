# Test File Naming Pitfall

## Problem

Subagents consistently create test files named `tests_*.py` (e.g., `tests_core.py`, `tests_research.py`, `tests_tools.py`). Pytest does NOT collect these — it only matches `test_*.py` or `*_test.py`.

## Symptoms

```
collected 0 items
no tests ran
```

When you KNOW the test file exists and contains valid test functions.

## Fix

```bash
# Find and rename all misnamed test files
find enterprise/ -name "tests_*.py" -type f
# → enterprise/modules/claude_code_core/tests/tests_core.py
# → enterprise/modules/research_verification/tests/tests_research.py

# Rename
for f in $(find enterprise/ -name "tests_*.py" -type f); do
    dir=$(dirname "$f")
    base=$(basename "$f")
    newname=$(echo "$base" | sed 's/^tests_/test_/')
    mv "$f" "$dir/$newname"
done
```

## Prevention

When instructing subagents to create tests, specify: "Create test file at `tests/test_MODULENAME.py` (MUST start with `test_`, NOT `tests_`)"

## Affected modules in this platform

- claude_code_core/tests/tests_core.py → test_core.py ✅
- claude_code_tools/tests/tests_tools.py → test_tools.py ✅
- claude_code_infra/tests/tests_infra.py → test_infra.py ✅
- research_verification/tests/tests_research.py → test_research.py ✅