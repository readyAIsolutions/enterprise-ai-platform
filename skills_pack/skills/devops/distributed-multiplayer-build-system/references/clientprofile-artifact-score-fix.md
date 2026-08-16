# ClientProfile artifact_quality_score Fix Reference

## Problem
`ClientProfile._score_performance()` in `creed_scoring.py` accessed `self.artifact_quality_score` but the dataclass field didn't exist with a default value.

**Error**: `AttributeError: 'ClientProfile' object has no attribute 'artifact_quality_score'`

**Stack trace**:
```
File "creed_scoring.py", line 251, in _score_performance
    artifact_quality_score=self.artifact_quality_score,
File "creed_scoring.py", line 284, in record_task_result
    self.performance = self._score_performance()
File "creed_server/server.py", line 380, in handle_task_complete
    profile.record_task_result(task_id, result.success, result.duration_seconds, result.artifacts)
```

## Root Cause
`ClientProfile` dataclass (line 91-128) had:
- `artifacts_produced: int = 0`
- `total_compute_hours: float = 0.0`

But **missing**: `artifact_quality_score: float = 0.0`

When `_score_performance()` called `self.artifact_quality_score` on line 258, the attribute didn't exist because:
1. New profiles created via `create_from_hello()` didn't initialize it
2. Loaded profiles from JSON didn't have it in saved data
3. Dataclass field without default → required in `__init__`

## Fix
Added default value in dataclass definition (line 123):
```python
artifact_quality_score: float = 0.0
```

## Files Changed
- `creed_scoring.py`: Line 123

## Verification
```python
from creed_scoring import ClientProfile
p = ClientProfile.create_from_hello('test', 'Test', {'cpu_cores': 4}, {})
print(p.artifact_quality_score)  # Should print 0.0
```

## Related
- `references/protocol.md` — TaskResult includes artifacts that update quality score
- `references/client-execution.md` — Task completion flow