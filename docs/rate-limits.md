# Optional triage request budget

RunbookOps can reject bursts before body buffering, concurrency admission, JSON
parsing, retrieval or optional generation. The feature is disabled when both
settings are absent. Enable it at process startup with both values:

```sh
RUNBOOKOPS_RATE_LIMIT_CAPACITY=20 \
RUNBOOKOPS_RATE_LIMIT_REFILL_MS=100 \
python -m uvicorn runbookops.api:app --host 127.0.0.1 --port 8000
```

`CAPACITY` accepts 1–10,000 and `REFILL_MS` accepts 1–60,000. Empty, partial,
signed, fractional, padded, leading-zero, non-ASCII and out-of-range settings
prevent the stock app from importing. Values are captured once at startup.

The implementation is a synchronized, continuously refilling token bucket using
the monotonic clock. Every admitted `POST /api/triage` spends one token. Rejection
returns 429, an integer `Retry-After` rounded up to the next token, and
`Cache-Control: no-store`. HTTP/1 connections close because the body remains unread.
Health, overview, source reads, assets and direct Python service calls are outside
the budget. A rejected request consumes no triage concurrency slot and starts no
analysis.

This is one shared process-local budget. It does not identify callers, reserve
capacity, queue work, coordinate workers or replicas, or protect an upstream proxy.
Restarting refills it. It is a burst control, not a fair scheduler, distributed
quota, abuse defense or measured capacity recommendation. The default app remains
loopback-only and unauthenticated; do not treat this option as authorization.

Focused checks use a controlled monotonic clock to cover exact exhaustion, rounded
retry delay, fractional refill, clock rollback, burst capping and recovery. ASGI
checks prove rejection occurs without reading a body and does not reach downstream
work. Environment cases cover disabled, partial, invalid and read-once settings.

```sh
python -m pytest -q tests/test_rate_limit.py tests/test_rate_limit_configuration.py
```

Interview exercise: why should rate rejection happen before concurrency admission,
and why can a shared token bucket still let one fast caller consume every token?
