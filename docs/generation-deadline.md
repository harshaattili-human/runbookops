# Generation deadline and cancellation

An inactivity timeout resets when a provider sends more data. A reply that trickles
bytes indefinitely could therefore occupy one of the two generation slots even
with a response byte limit. Optional generation now has one **30-second cooperative
I/O deadline**, starting after admission and before provider setup.

The FastAPI handler awaits HTTPX's asynchronous transport on the running event
loop. Classification/retrieval still use FastAPI's worker pool. One monotonic
deadline covers provider setup, connection, request transmission, response headers,
body consumption and validation. It is not reset by network progress. HTTPX's
existing 30-second per-operation timeouts remain as additional bounds.

On expiry, cancellation unwinds the response/client contexts before releasing the
generation slot. The API returns HTTP 200 with the original source extract,
citations, routing, sources and answerability fields, plus a time-limit warning.
No partial generated text is published. A completed result that returns after the
deadline during synchronous validation is also rejected. There is no retry or
background generation task left running by the adapter.

Explicit cancellation of `triage_async` propagates as `CancelledError`, rather than
being converted into a successful fallback response. Its provider contexts close
and the slot is released. Busy fallback and the existing byte/completion/citation
checks are unchanged. No new dependencies, model/data/threshold changes or live
model evaluation are involved.

## Python callers

The synchronous `service.triage(query, use_llm=True)` entry point remains available
for scripts, using `asyncio.run` for optional generation. Code already in an event
loop must instead use `await service.triage_async(query, use_llm=True)`. Extractive
calls remain synchronous. The HTTP handler uses the async entry point, so it does
not create a new event loop or wait for a generation worker thread per request.

## Boundaries

This is cooperative cancellation, not a hard 30-second response-time SLA. Upload,
validation before admission, retrieval, worker-pool waiting, event-loop scheduling,
blocking code and cleanup can add time. Bounded JSON parsing is synchronous and
cannot be interrupted mid-parse; the final clock check prevents accepting a late
answer. A blocking DNS resolver thread may outlive cancellation. The synchronous
wrapper can additionally wait for its event loop's executor shutdown; it does not
promise an end-to-end wall-clock bound for hostname resolution.

Closing a socket does not prove that Ollama stopped model loading or generation.
An HTTP client disconnect after upload does not itself trigger task cancellation
here; generation can continue until completion or the deadline. Incoming admission,
rate limits, aggregate memory, provider-side cancellation and a production load
study remain open. Each process still has its own two-slot admission limit.

## Checks

```sh
python -m pytest -q tests/test_generation_deadline.py tests/test_generation_concurrency.py tests/test_ollama_boundary.py
python -m pytest -q
```

Nine new cases cover:

- Four API cases with real loopback provider HTTP: stalled headers and unfinished
  fixed-length, chunked and connection-terminated bodies. The provider sends one
  byte every 20 ms; the tests shorten only the total deadline to 400 ms while the
  inactivity timeout remains 30 seconds. They check health availability, unchanged
  fallback fields, socket EOF and a subsequent successful generation.
- Two explicit task-cancellation cases, before response headers and during a
  chunked body. Both generation slots are occupied, a third call falls back, both
  tasks are cancelled, and two subsequent generations succeed. Provider-side EOF
  verifies socket closure. These do not simulate an HTTP client disconnect.
- One synchronous caller against the same slow loopback provider.
- One controlled synchronous overrun showing that a late result is not accepted,
  and one guard against using synchronous generation inside an event loop.

The four API cases use an ASGI client with the real provider network transport;
they are not external HTTP clients of Uvicorn. Existing HTTP/container and browser
suites exercise the changed handler through the running application. Provider
fixtures are synthetic protocol responses, not evidence of live-model quality or
measured production latency. Timing waits prevent hangs; they are not benchmarks.

References: Python's [timeout and cancellation semantics](https://docs.python.org/3.12/library/asyncio-task.html#timeouts),
[runner shutdown](https://docs.python.org/3.12/library/asyncio-runner.html#running-an-asyncio-program),
and HTTPX's [async streaming contexts](https://www.python-httpx.org/async/).

Interview exercise: why does `future.result(timeout=30)` on a synchronous worker
not cancel the worker's socket read, and why does closing that socket still fail
to establish that the model stopped computing?
