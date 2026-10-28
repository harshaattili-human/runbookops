# Triage admission and cancellation ownership

By default the HTTP app admits at most eight concurrent `POST /api/triage` lifetimes per
application process, including its trailing-slash redirect path. Admission is
outside the body limiter: a slot covers upload, JSON validation, classifier/retrieval
work, optional generation and response sending. The ninth request receives JSON
503 with `Cache-Control: no-store` before its body is read or analysis begins.
HTTP/1 connections are closed on rejection rather than reused with unread bodies.
There is no queue, retry loop or `Retry-After` promise.

The default eight slots are an illustrative safety bound, not measured capacity.
Operators can set `RUNBOOKOPS_TRIAGE_CAPACITY` at process startup to an integer
from 1 through 1000. Unset selects eight; empty, whitespace, signed, fractional,
non-ASCII, leading-zero and out-of-range values prevent startup. The value is
read once when middleware is constructed; changing an environment or config file
does not resize a running process. Restart with the new setting. Trusted embedders
can pass `capacity=1..1000` to `TriageAdmission`, which takes precedence over the
environment. There is no request-controlled override. It has no per-caller map. Health,
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
outside this boundary; workers/replicas multiply the allowance. Enough slow uploads
can occupy all configured slots until their upload deadline/disconnect. Response backpressure
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

## Observed execution — October 18, 2026

Implementation `e7fc6373861cdb3e0abc549f543b8c33736516b6` passed all five jobs in
[run 39134584208](https://github.com/harshaattili-human/runbookops/actions/runs/39134584208).
Verification job `117696397813` passed 140 Python cases (13 new executions), seven
component cases, the existing validation commands and frontend production build.
Browser job `117696397898` passed 27 live and 18 recorded executions across the
existing three-engine/three-width matrix; no new UI behavior was introduced.
Spring job `117696397883` passed nine Java cases and the live executable walkthrough.
Container job `117696397892` passed packaged HTTP, non-root read-only operation,
health, shutdown and restart; its existing checks do not saturate admission.

The image audit still reported 166 finding entries with zero fixable high/critical
entries. The Java audit inventoried 26 libraries with zero advisory entries in that
snapshot; dependency job `117696397848` also passed. These are configured advisory
gates, not vulnerability-free claims. Hosted Python 3.12.15/Node 24.21.0/Java
17.0.20.1 ran on Ubuntu 24.04. The existing Starlette/httpx and Lucide warnings remain.

Local compileall, relative documentation links and whitespace checks passed;
pytest was unavailable locally. Existing checked-in evaluation reports remain
historical artifacts; CI ran validation, not exposed holdouts, on this candidate.
Final-head CI is retained in [PR 20](https://github.com/harshaattili-human/runbookops/pull/20).

References: [asyncio shielding and cancellation](https://docs.python.org/3.12/library/asyncio-task.html#shielding-from-cancellation),
[Uvicorn flow control and Expect](https://www.uvicorn.org/server-behavior/).

Interview exercise: why can releasing a semaphore in an async `finally` still return
capacity too early when the awaited operation runs in a synchronous worker thread?

## Operator configuration — October 28, 2026

```sh
RUNBOOKOPS_TRIAGE_CAPACITY=2 uvicorn runbookops.api:app --host 127.0.0.1 --port 8000
python -m pytest -q tests/test_admission_configuration.py tests/test_admission.py
python scripts/admission_smoke.py --image runbookops:smoke
```

Two is an illustrative override, not a recommended production value. The
[HTTP characterization](http-characterization.md) showed increasing response
latency without proportional success-throughput scaling on one constrained image.
It does not justify choosing a universal replacement for eight. Select a value
using the intended hardware, worker count, request mix and observed rejection and
latency behavior. This change does not add fairness, queuing, autoscaling or a
memory/CPU guarantee. Multiple processes still multiply the configured allowance.

Configuration cases cover rejected spellings, both range endpoints, the default,
read-once selection and explicit-constructor precedence. A POSIX subprocess starts
the actual stock Uvicorn app with two slots, holds fixed/chunked uploads, checks
503 before body reads, health availability, disconnect cleanup and simultaneous
recovery, then verifies invalid configuration prevents a new process from starting.
The container rehearsal repeats the same HTTP contract with the actual non-root,
read-only image before and after a container restart. It records the immutable
image ID and Docker version. These are lifecycle fixtures, not throughput tests.
Existing default-eight coverage remains. Full hosted execution is pending; local
Python compilation and whitespace checks passed, but application dependencies and
Docker are unavailable in this execution environment.

Optional interview exercise: why can lowering admission improve successful-request
latency while increasing rejections, and why do four workers not share one budget?
