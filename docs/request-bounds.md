# Triage request byte limit

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
aggregate memory limit, upload deadline, rate limit, authentication boundary or
request-smuggling defense. Slow clients can still occupy connections. Deployment
would require separate server/proxy controls.

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
