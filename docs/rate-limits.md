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

## Verification — November 4, 2026

Implementation `7b0231dcfde9f304933035a2de3fc092c08cab78` passed all five jobs in
[run 41852434496](https://github.com/harshaattili-human/runbookops/actions/runs/41852434496).
Verification job `126651989771` passed 277 Python cases plus 11 subtests (29 added
executions), seven frontend component cases, validation-only model checks and the
production build. The added controlled-clock and ASGI cases exercise the enabled
budget; existing browser and container workflows retain the disabled default.

Browser job `126651988992` passed 36 live and 18 recorded executions across the
existing three engines and widths. Spring job `126651989661` passed 18 Java cases
plus the executable walkthrough. Container job `126651989571` passed the existing
packaged, non-root/read-only, restart, mounted-corpus, configured-admission and HTTP
characterization checks. It does not yet launch an enabled request budget.

The dated runtime scan inventoried 24 Python package names and 187 advisory finding
entries with zero fixable high/critical entries; the Spring scan inventoried 26
libraries with zero advisory entries, and npm reported zero vulnerabilities. These
configured gates are not a vulnerability-free claim. Hosted versions included
Python 3.12.15, Node 24.22.1, Java 17.0.21 and Ubuntu 24.04.5.

Local Python 3.12 ran the 29 focused cases successfully using a retained dependency
environment; compilation, whitespace and documentation-link checks also passed.
The current workspace lacks HTTPX2 and Docker for the complete local suite, so the
full evidence is hosted. No corpus, model, ranking, threshold or holdout score
changed.
