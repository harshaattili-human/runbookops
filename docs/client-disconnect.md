# Cancel optional generation when the caller leaves

The generation deadline bounds how long an unfinished provider reply can occupy a
slot. It did not notice a caller that had already closed its HTTP connection. The
API now races optional triage against a blocking ASGI disconnect receive after
FastAPI has consumed and validated the complete bounded request body.

On `http.disconnect`, it cancels and joins the triage task. The existing adapter's
async response/client contexts close and its `finally` releases the generation
slot. On normal completion, it cancels and joins the receive watcher. Cancellation
of the outer handler joins both children. There is no polling interval or detached
generation task. The default extractive path does not create a watcher.

The body-limit middleware remains the only receiver during upload and replays the
bounded body once to FastAPI. The watcher starts afterward, so it cannot steal
request-body bytes from the parser. The handler uses an empty internal 499 response
for disconnect logging; 499 is nonstandard and no response delivery is promised to
a caller that has closed its connection. A simultaneous disconnect and completed
answer is treated as a disconnect. HTTPX operation timeouts, the 30-second generation
deadline, two process-local slots, byte limit and fallback contract remain unchanged.

Cancellation depends on the server observing connection loss. A proxy may keep its
upstream connection open after its downstream caller leaves, and a silent network
failure may not become an immediate disconnect. The total deadline still applies.
Cooperative cancellation does not interrupt synchronous retrieval/JSON parsing,
kill a worker or DNS thread, or prove that the provider stopped model computation.
No live model, production latency, distributed admission or proxy topology was tested.

## Reproduce

```sh
python -m pytest -q tests/test_client_disconnect.py tests/test_generation_deadline.py
python -m pytest -q
```

Four new real HTTP cases start Uvicorn on an ephemeral loopback port and use two
raw client sockets. They cross fixed/chunked request uploads with provider stalls
before headers/during a chunked reply. Both provider calls must arrive before the
clients close; a third request checks busy fallback and health remains available.
The provider then observes EOF on both connections within a test-only wait bound,
while the production deadline remains 30 seconds. Two recovery responses are held
until both calls arrive, establishing that both admission slots were released.
Normal generated responses and subsequent extractive requests are checked too.

Two additional coroutine lifecycle cases verify that normal completion stops the
watcher and outer task cancellation joins both child tasks. These controlled
fixtures test resource lifetime, not actual model behavior or a throughput claim.

References: the [ASGI disconnect event](https://asgi.readthedocs.io/en/stable/specs/www.html#disconnect-receive-event)
and [Uvicorn response completion behavior](https://uvicorn.dev/server-behavior/).

Interview exercise: why must the disconnect watcher wait until body parsing is
complete, and why does closing the provider socket establish less than stopping
its model computation?
