# pytest prepend-import-mode breaks `isinstance(x, _qp.QueuePlan)` gates

Verified D3D16 Cycle 5 (2026-07-11) on `backend/forge/farm_planner.py`.

## Symptom
A test imports `forge.queue_planner as qp`, builds `qp.QueuePlan(...)`, and passes it
to `farm_planner.plan_farm(...)`. Under `pytest`'s default **prepend** import mode the
call raises:

```
TypeError: 'QueuePlan' object is not iterable
```

...even though `farm_planner.py` gates with `isinstance(x, _qp.QueuePlan)` and the SAME
call works when you run the module in isolation (`python3 -c "..."`).

## Root cause
pytest prepends the rootdir to `sys.path` (prepend mode), so `forge` can be imported as
TWO distinct module objects during a test session: the one your test imports as `qp`, and
the one `farm_planner` imported internally as `_qp`. `qp.QueuePlan is not fp._qp.QueuePlan`
— they are two class objects. `isinstance(obj, _qp.QueuePlan)` is therefore False, and the
code falls through to a branch that tries to iterate `obj` as if it were a list → the error.

This is a **test-harness artifact, not a module defect.** Prove the module is fine by
running it outside pytest (isolated import) — it passes.

## Fix A — bind the class through the owning module (test-side)
In the test, get `QueuePlan` from the module that performs the gate, not from your own
import alias:

```python
import importlib
fp = importlib.import_module("forge.farm_planner")   # the module that gates
qp = importlib.import_module("forge.queue_planner")
QueuePlan = fp._qp.QueuePlan        # <-- identity matches farm_planner's gate
PlannedJob = fp._qp.PlannedJob

plan = fp.plan_farm(QueuePlan([PlannedJob("a", 30), PlannedJob("b", 10)]))
assert plan.makespan_min == 40
```

This makes the object you hand in the *exact* class the gate checks.

## Fix B — duck-typed gate (module-side, preferred for MASTER)
If you own the module, make the gate immune to import-mode identity so ANY correctly
shaped object passes regardless of which copy of the class it is:

```python
def _is_queue_plan(x):
    return type(x).__name__ == "QueuePlan" and hasattr(x, "dispatch")
```

Replace `isinstance(x, _qp.QueuePlan)` with `if not _is_queue_plan(x): ...`.

## How to detect this vs a real bug
1. Run the module in isolation (no pytest): `python3 -c "import forge.farm_planner as fp, forge.queue_planner as qp; print(fp.plan_farm(qp.QueuePlan([qp.PlannedJob('a',30)])))"`.
   If that works, the module is correct and the pytest failure is the import-mode artifact.
2. Run ONLY your test file: `python3 -m pytest tests/test_farm_planner_d3d16.py -q`. If it
   passes alone but fails when the full suite runs, a sibling's import aliasing is the
   trigger (the class object identity differs between test modules). Bind via `fp._qp.*`.
3. Confirm the fix: the same env that failed now passes, and the full suite still collects
   the sibling's file without crashing your module.

## Related
- SWARM collision on `tests/test_*.py` paths → name your test file uniquely
  (`test_farm_planner_d3d16.py`) so a sibling writing the bare name can't clobber it and
  both files survive `pytest tests/`.
