# Local corpus refresh channel

An operator can refresh a running process from a manifest-pinned release without
opening an HTTP administration route. Set `RUNBOOKOPS_CONTROL_SOCKET` to opt into
a POSIX Unix-domain socket. The default application creates no control socket.

```sh
mkdir /tmp/runbookops-control
chmod 700 /tmp/runbookops-control
export RUNBOOKOPS_CONTROL_SOCKET=/tmp/runbookops-control/operator.sock
uvicorn runbookops.api:app --host 127.0.0.1 --port 8000
# In another terminal, using a previously verified release and saved pin:
python -m runbookops.corpus_control \
  --socket /tmp/runbookops-control/operator.sock \
  --release /absolute/path/to/releases/release-b \
  --sha256 SAVED_MANIFEST_SHA256
```

The socket's existing parent directory must be owned by the application UID with
mode 0700. Parent aliases, relative paths and empty settings fail startup. The
socket has mode 0600; an existing path is never removed or replaced. Shutdown
removes the socket only if its device/inode still matches the bound socket. A
second worker cannot share the same pathname: configure separate private sockets
for independently managed processes. The operator must run as the application UID
(or have administrative access). Filesystem ownership is the authorization
boundary; this does not defend against root, compromised same-UID code or hostile
filesystem changes. Keep the directory and release storage operator-managed.

Each connection accepts one newline-terminated JSON object with exactly `release`
(an absolute path) and `manifest_sha256` (64 lowercase hex characters). Duplicate
fields, malformed UTF-8/JSON, extra fields and requests exceeding 4096 bytes including
the newline are rejected. Reading has one five-second cooperative deadline. One
operator lease covers upload, index construction and reply cleanup; another caller
gets `busy` immediately without reading its command. This is not an aggregate
socket, process-memory or denial-of-service bound. The one-second reply deadline
bounds cooperative backpressure, not scheduling or kernel work.

The existing release verifier checks the exact manifest pin, inventory and source
hashes before building an index. Building runs in a worker thread while API requests
continue using their captured snapshot. Only successful construction replaces the
snapshot. The reply contains `ok` plus the identity of that publication, or a fixed
`invalid_request`, `busy` or `refresh_failed` status without local paths/exception
text. A detached identity is included in the in-process refresh receipt so it cannot
accidentally describe a later trusted publication.

The CLI sends once and does not retry. A lost reply or its 30-second socket timeout
is **ambiguous**: an accepted refresh can still publish. Inspect `/healthz`'s corpus
identity before deciding what to do next. Disconnect does not roll back a refresh.
Shutdown cancels connection handlers but joins any index-building thread, including
a worker that eventually fails. Slow or stuck building can delay shutdown; Python
threads are not killed and there is no hard build deadline.

This channel does not change the startup selection. Restarting still uses the
configured startup release/pin (or bundled corpus); update those settings separately
when adopting a release. Rollback is an explicit refresh to a retained release and
its saved pin. The channel coordinates one process only. Sampling health behind a
load balancer cannot prove every worker refreshed, and no multi-process rollout,
publisher signature, crash durability or production deployment is claimed.

## Verification

```sh
python -m pytest tests/test_corpus_control.py -q
```

Synthetic checks cover pin rejection/retention, detached identities, private socket
permissions, schema/framing/timeouts/disconnects, busy admission before reading,
worker failure/recovery, repeated cancellation during shutdown, protected existing
and replacement paths, old HTTP snapshots during a latched rebuild, and a real
Uvicorn subprocess plus CLI refresh with old-source hash 409. The process case uses
a temporary private socket and pinned synthetic releases; no benchmark holdout is
scored. POSIX checks are skipped on other operating systems.

Local compilation and whitespace checks passed. This execution environment denied
AF_UNIX socket creation (`EPERM`) and lacks pytest/FastAPI, so local execution is not
claimed. Hosted Linux execution evidence is recorded after CI finishes. Existing
browser/container suites retain default startup; they do not exercise mounted
operator sockets.

Reference: [Python 3.12 Unix streams and ownership](https://docs.python.org/3.12/library/asyncio-stream.html#unix-sockets).

Interview exercise: why can a timed-out operator command still publish an index,
and why does a successful reply from one worker fail to establish a complete rollout?
