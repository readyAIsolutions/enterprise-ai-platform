# Module: `codegen_audit`

- Category: Build Quality · priority 3
- Version: 1.0.0
- Purpose: Audit generated code for correctness, security and quality signals.
- Skill: `eni-module-codegen_audit` (ICM stages) in skills_pack/skills/eni-modules/codegen_audit/

## What it does
codegen_audit — audit / evaluate AI-generated code.

Grounded in three JE Van Clief coding-tool-eval transcripts:

* ``_rtyhVD4v4A`` — "One of These AI Coding Tools Failed Completely": comparing
  AI coding tools on how well they understand a technical goal and produce
  working, modular code.  Feeds the static review (hallucinated imports,
  truncation/fidelity stubs) and the task-understanding evaluator (does the
  generated code satisfy the *stated requirements*, and are claimed features
  actually verified?).

* ``nWbM9Ye2sLw`` — "Open Claw Vibe Coded an App. Real Developers Read Every
  Line and Tell You What They Found": a line-by-line team security audit of a
  vibe-coded app.  Feeds the secret/credential, redundant-reinvention, and
  unverified-auth checks.

* ``5B6W2OGfxq0`` — "How One Line of Python Triggers 12,000 Lines of Code":
  the execution-abstraction stack (source -> AST -> bytecode -> interpreter ->
  runtime).  Feeds the dependency/abstraction-depth analysis and the
  error-handling checks (every layer is engineered with error handling).

Export surface (thin facades over the pure stdlib core in
:mod:`enterprise.modules.codegen_audit.codegen_audit`):

  * ``audit_code`` / ``review_code`` — static heuristic code review.
  * ``score_code`` / ``score_checks`` — review scoring report (grade + verdict).
  * ``analyze_dependencies`` / ``analyze_blast_radius`` — dependency /
    abstraction-depth analysis.
  * ``evaluate_task`` / ``verify_features`` — task-understanding evaluator.

## Key API (facade methods)
analyze_dependencies, audit, evaluate_task, health_check, initialize, review, score, set_event_bus, shutdown

## Tests
```bash
python3 -m pytest modules/codegen_audit/tests -q
```

## Import
```python
from enterprise.modules.codegen_audit import create_codegen_audit_module
m = create_codegen_audit_module()
```
