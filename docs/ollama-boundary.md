# Optional generation response boundary

The optional adapter previously buffered the complete HTTP response before checking
the generated answer. Its 6,000-character answer check and `num_predict=450` request
option did not bound the provider's JSON envelope. It also accepted an answer with
valid citation IDs without checking whether the provider had finished generation.

## Behavior

The adapter still requests one non-streaming Ollama chat result. HTTP response
streaming is used internally to enforce a **65,536-byte envelope limit** before
either JSON layer is parsed. This limit includes metadata, escaped content and
trailing whitespace, but excludes HTTP headers and transfer framing.

- A declared Content-Length above the limit is rejected before reading the body.
- Chunked and connection-terminated responses are counted as they arrive. The
  accumulator never retains more than the limit; raw chunks are read in 8,192-byte
  pieces and the first piece crossing the limit is rejected before appending.
- The request sends `Accept-Encoding: identity`. Any other response content encoding
  is rejected without decompression, so a compressed reply cannot expand around
  the envelope limit. HTTPX remains responsible for HTTP framing and socket buffers.
- The envelope must contain boolean `done=true` and `done_reason="stop"`. Missing
  completion metadata, `done=false`, a token-limit stop (`length`) or another reason
  falls back, even if the answer happens to be valid JSON with valid citations.
- The existing nonempty answer and retrieved-citation checks still apply. Invalid
  JSON, excessive nesting, transport errors, redirects and provider error statuses
  also return the original source extract and citations, with a warning.

The response and client contexts close on success and failure. Redirects remain
disabled and no retry is added. Request callers still cannot choose the provider
URL or model; those are operator environment settings.

## Tradeoffs and limits

The fixed cap leaves room for the brief answer and ordinary response metadata while
limiting what this adapter retains and parses. It is a local policy, not an Ollama
protocol maximum. A compatible proxy must return identity encoding and the required
completion fields. Older servers, unusually verbose metadata, large thinking
outputs or heavily escaped content may fall back despite containing useful text.
The adapter does not silently truncate a reply to make it fit.

The existing HTTPX timeout remains 30 seconds for network operations. In particular,
the read timeout concerns inactivity between received data, **not a 30-second total
request deadline**. Slow progress can keep a call alive longer. This increment does
not bound concurrent requests, all process memory, HTTP headers, provider compute
or model loading. Cancellation, total deadlines and generation concurrency limits
remain separate work.

Completion flags and valid citation IDs do not prove entailment or factual accuracy.
No model was downloaded or run for these tests. Ranking, answerability thresholds,
the corpus and default extractive behavior are unchanged.

## Reproduce and evidence

```sh
python -m pytest -q tests/test_ollama_boundary.py tests/test_triage.py
python -m pytest -q
```

The new boundary module contains 32 cases. Twenty-seven use a controlled loopback
HTTP/1.1 server with the real HTTPX transport; one exercises the FastAPI handler via
TestClient while that provider remains a real local HTTP server. Four instrumented
streams check early rejection, bounded consumption, timeout fallback and closure.
The provider generates synthetic protocol responses, not model outputs.

Coverage includes exact-limit and one-byte-over bodies for fixed, chunked and
connection-terminated framing; UTF-8 and whitespace accounting; deduplicated valid
citations; required completion metadata; invalid outer/inner JSON and excessive
nesting; gzip rejection; redirects, HTTP 500 and premature disconnect; and unchanged
extractive fields after rejection. The instrumented unknown-length response stops
after nine 8,192-byte pieces rather than consuming its 100-piece source. This is an
application-buffer check, not a measured upper bound on total transport memory.

Before the implementation changed, the initial 11-case subset had three passing
exact-limit cases and eight failures: all three oversized replies and five
unfinished/truncated replies were accepted. After the fix, local Python 3.12.14
passed all 77 Python cases. Seven frontend component tests, the production build,
classifier evaluation and validation-only retrieval/answerability/passage commands
also passed. Validation reports changed only in the service source hash; exposed
holdouts were not rescored. Existing Starlette/httpx and Lucide warnings remain.

Hosted [run 38690943933](https://github.com/harshaattili-human/runbookops/actions/runs/38690943933)
at implementation commit `05a5796` passed all four jobs on October 15, 2026:
77 Python tests, seven component tests, nine existing Chromium executions,
evaluations/build, container HTTP/runtime/restart checks and the configured image
and npm audit gates. The verify job used Python 3.12.15 and Node 24.21.0 on Ubuntu.
Container/browser execution was hosted; the new controlled-provider cases ran in
the Python job, not against an Ollama process inside the container. Passing audit
gates does not imply zero unresolved advisories; see [audit scope](dependency-audits.md).

References: Ollama's [chat response fields](https://docs.ollama.com/api/chat),
HTTPX [streaming responses](https://www.python-httpx.org/quickstart/#streaming-responses)
and [timeout semantics](https://www.python-httpx.org/advanced/timeouts/).

Optional interview exercise: why do a token-generation option, a final answer-length
check and an inactivity timeout fail to establish a byte bound or total deadline?
