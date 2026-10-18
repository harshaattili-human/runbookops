# Triage request byte and upload limits

`POST /api/triage` now accepts at most 32,768 body bytes before JSON parsing or
classification. The character limit alone was insufficient: unknown fields and
trailing whitespace could make a body arbitrarily large before validation.
The byte allowance fits a 2,000-character query even when every supplementary
Unicode character uses two JSON escapes. Extra padding can still exceed it.

A pure ASGI middleware checks declared Content-Length before reading. It also
counts every received body chunk, including whitespace and UTF-8 bytes, so absent
or understated lengths do not bypass the bound. A crossing chunk is rejected
before appending it. Oversized requests receive JSON `detail` with HTTP 413;
nonidentity Content-Encoding receives 415 without decompression. Malformed or
duplicate length headers reaching ASGI receive 400. The HTTP server may reject
invalid framing first. The trailing-slash redirect path has the same bound.

Only a complete accepted body reaches FastAPI. Existing field/JSON validation
still returns 422. A client disconnect during upload discards the partial body
without invoking triage. Other routes and direct Python service calls are outside
this policy. No training data, retrieval policy or evaluation threshold changes.

The middleware accumulator is bounded; the server-supplied ASGI chunk, socket and
header buffers, JSON objects and concurrent requests have separate memory costs.
Replaying the accepted body also makes a bounded bytes copy. This is not an
aggregate memory limit, rate limit, authentication boundary or
request-smuggling defense. Deployment
would require separate server/proxy controls.

## Upload deadline

After header checks, one 30-second cooperative asyncio deadline covers reading the
complete body. Receiving another chunk does not reset it. An incomplete upload
returns JSON HTTP 408 without invoking JSON parsing, classification or generation.
HTTP/1 responses request connection closure so an unfinished body is not reused.
External task cancellation still propagates; disconnects still discard the body.
Completed requests leave the timeout context before downstream work begins.

This starts when the ASGI middleware receives the request, not when a TCP connection
opens. Header reception, proxy buffering, event-loop scheduling and response sending
are outside the guarantee. It is not a hard wall-clock SLA, concurrent-connection
limit or protection against many clients. A slow valid upload can be rejected;
clients should send the bounded JSON in one ordinary request. No automatic retry is
added. The separate generation deadline starts later and remains unchanged.

Four new real Uvicorn HTTP/1.1 cases cross fixed/chunked framing with stalled/trickle
uploads using a test-only 0.3-second limit. They require 408, connection closure,
no triage invocation and a successful subsequent request; trickle cases confirm
multiple chunks were sent. One ASGI lifecycle case checks cancellation propagation
without a response. Production retains 30 seconds. These are synthetic protocol
checks, not a load benchmark. See [asyncio timeout semantics](https://docs.python.org/3.12/library/asyncio-task.html#asyncio.timeout).

## Reproduce

```sh
python -m pytest -q tests/test_request_bounds.py
python -m pytest -q
docker build -t runbookops:smoke .
python scripts/container_smoke.py
```

Twenty-one cases include eleven real HTTP/1.1 checks against Uvicorn and ten ASGI
probes. They cover exact/one-byte-over fixed and chunked bodies, safe subsequent
requests, raw/escaped maximum Unicode queries, invalid JSON/fields, gzip rejection,
early header rejection, counting unknown/understated lengths, empty chunks and
disconnects. A triage spy confirms rejected requests never reach analysis. The
unknown-length probe stops at its ninth 4,096-byte chunk instead of reading all
100 supplied chunks. Understated-length probes test the ASGI boundary; they do not
claim HTTP servers accept contradictory wire framing.

The packaged container smoke repeats exact/over-bound fixed and chunked requests
and a subsequent valid analysis. These are synthetic protocol fixtures, not a
load test or model-quality evaluation.

The [ASGI HTTP specification](https://asgi.readthedocs.io/en/latest/specs/www.html)
defines body chunks, completion and disconnect events. Interview exercise: why
does a 2,000-character query limit fail to bound the HTTP request body, and why
does a per-request byte limit fail to cap total process memory?

## Observed verification — October 15, 2026

Implementation `abdc3032cce031ab1911fbf116c9d84b91ac645b` passed
[run 38805246280](https://github.com/harshaattili-human/runbookops/actions/runs/38805246280):
101 Python cases (21 new boundary cases), seven component cases, validation
evaluations, production build, 27 live and 18 recorded browser executions across
the existing three-engine/three-width matrix, and the configured dependency gates.
The container job passed fixed/chunked body checks plus non-root read-only,
health, shutdown and restart checks on Python 3.12.15. Its audit still reported
166 advisory entries and zero fixable high/critical entries under the gate;
this is not a vulnerability-free image claim.

Local Python 3.12.14 tests, validation commands, frontend tests/build and whitespace
checks passed. Docker and browser execution were hosted. The existing
Starlette/httpx deprecation and Lucide build warnings remain. Validation reports
changed only in code hashes; exposed holdouts were not rescored. These checks
establish the stated HTTP behavior, not a measured memory ceiling or load capacity.
