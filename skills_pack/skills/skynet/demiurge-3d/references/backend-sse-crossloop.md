# D3D backend — SSE cross-event-loop broadcaster (`job_manager_api.py`)

Verified 2026-07-12 while clearing the last of the 22 pre-existing backend
failures: `test_print_job_manager.py::test_stream_emits_state_and_updates`
exercises a `StreamingResponse` (`api.stream()`) that pushes job-state events
as SSE `data: ...` frames. Two distinct traps, both live in this backend and
will recur for any future live-update stream (job progress, printer telemetry
push).

## Source trap: events produced off the serving loop are dropped

If the broadcaster enqueues onto an `asyncio.Queue` from a background thread
or a different event loop than the one running the request, a naive
`queue.put_nowait(...)` either raises or silently loses frames. Fix: capture
the serving event loop at subscribe time and bridge with
`loop.call_soon_threadsafe(queue.put_nowait, payload)` (or
`asyncio.run_coroutine_threadsafe`). The SSE generator must `await queue.get()`
on that same loop. The `_Broadcaster` in `demiurge/printing/job_manager_api.py`
was rewritten to do exactly this — keep that pattern; do not revert to a bare
`put_nowait` from the producer thread.

## Test trap: TestClient streaming + background thread hangs

`fastapi.testclient.TestClient` runs its own event loop; driving the
`StreamingResponse` body through it while a background thread mutates shared
state deadlocks (the client's loop never advances the generator). Recipe that
works — drive the response directly inside `asyncio.run` in the main thread
and mutate state from a thread:

```python
def test_stream_emits_state_and_updates():
    import threading, asyncio
    events = []
    def mutate():
        api._Broadcaster.push({"state": "printing", "progress": 0.5})
    def run():
        async def _consume():
            resp = await api.stream()
            async for chunk in resp.body_iterator:
                text = chunk if isinstance(chunk, str) else bytes(chunk).decode()
                if text.startswith("data: "):
                    events.append(text[len("data: "):])
        asyncio.run(_consume())
    t = threading.Thread(target=mutate); t.start()
    run(); t.join()
    assert any("printing" in e for e in events)
```

Key points:
- Iterate `resp.body_iterator` **directly** (NOT through `TestClient`).
- Decode each chunk (`chunk` may arrive as `bytes`); strip the `data: ` SSE
  prefix to recover the JSON payload.
- Start the mutating thread BEFORE the consume loop so frames aren't missed.
- Ensure the producer closes the stream (sentinel or generator `break` on
  disconnect) so the `async for` terminates.
- A stray variable-name slip (`line` vs `text`) in the decode step produced an
  `UnboundLocalError` on the first frame — assert the decode target name is
  consistent inside the `async for`.
