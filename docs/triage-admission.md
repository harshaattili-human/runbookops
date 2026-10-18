# Triage admission and cancellation ownership

The HTTP app admits at most eight concurrent `POST /api/triage` lifetimes per
application process, including its trailing-slash redirect path. Admission is
outside the body limiter: a slot covers upload, JSON validation, classifier/retrieval
work, optional generation and response sending. The ninth request receives JSON
503 with `Cache-Control: no-store` before its body is read or analysis begins.
HTTP/1 connections are closed on rejection rather than reused with unread bodies.
There is no queue, retry loop or `Retry-After` promise.

The default eight slots are an illustrative safety bound, not measured capacity.
Trusted embedders can pass `capacity=1..1000` to `TriageAdmission`; the stock app
uses eight with no request-controlled override. It has no per-caller map. Health,
source/overview reads, assets and direct Python service calls are outside this cap.
The independent two-slot provider admission and source-text busy fallback are
unchanged: triage saturation is a 503, not an abstention or a fabricated answer.

## Why cancellation must join the worker

Cancelling an async wait does not terminate synchronous scikit-learn code already
running in a worker thread. `triage_async` now shields the classifier/retrieval
worker and, if cancelled, joins it before propagating cancellation. Repeated task
cancellation cannot detach it. A worker failure during that join is consumed while
the original cancellation remains the caller's outcome. Optional generation is not
started after cancellation during the worker phase. Provider cancellation keeps
its existing socket/context cleanup.

Admission returns its slot in `finally` after the downstream ASGI call ends. Thus a
cancelled request does not return HTTP capacity while its synchronous triage worker
continues. The tradeoff is delayed cancellation/shutdown if that worker is slow or
stuck. Python threads are not forcibly killed. The 30-second upload and generation
deadlines remain phase-specific, not a whole-request CPU deadline or hard SLA.

This bounds admitted triage lifetimes, not total memory, connections, framework
queues, headers, rejected response work or all application CPU. Proxies can buffer
outside this boundary; workers/replicas multiply the allowance. Eight slow uploads
can occupy all slots until their upload deadline/disconnect. Response backpressure
also holds a slot. There is no tenant fairness, authentication, rate limit or
production-load claim, and direct service callers need their own admission policy.

## Verification protocol

```sh
python -m pytest -q tests/test_admission.py tests/test_client_disconnect.py tests/test_request_bounds.py
python -m pytest -q
```

New cases cover invalid configuration, simultaneous saturation, downstream errors,
external cancellation, send failure, response backpressure and exact capacity
recovery. Two event-controlled worker cases cancel twice while a synchronous worker
is held, require continued 503 rejection, then release the worker with either a
result or an exception and require cancellation propagation/capacity recovery.

A real Uvicorn HTTP/1.1 case holds eight alternating fixed/chunked uploads using
`Expect: 100-continue`. Each 100 response proves the application has requested body
bytes; the ninth receives 503 without 100. Health remains reachable. Closing those
clients allows eight more simultaneous partial uploads, with excess work still
rejected. These are synthetic lifecycle checks, not a throughput benchmark or a
model-quality evaluation. No model, corpus, threshold or held-out score changes.

Exact-head execution evidence will follow hosted CI. Local pytest was unavailable;
local syntax and whitespace checks are not a substitute for the Python suite.

References: [asyncio shielding and cancellation](https://docs.python.org/3.12/library/asyncio-task.html#shielding-from-cancellation),
[Uvicorn flow control and Expect](https://www.uvicorn.org/server-behavior/).

Interview exercise: why can releasing a semaphore in an async `finally` still return
capacity too early when the awaited operation runs in a synchronous worker thread?
