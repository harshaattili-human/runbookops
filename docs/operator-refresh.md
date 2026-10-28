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

Each connection accepts one newline-terminated JSON object with required `release`
(an absolute path) and `manifest_sha256` (64 lowercase hex characters), plus optional `expected_corpus` for a
[guarded refresh](guarded-refresh.md). Duplicate
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
`invalid_request`, `busy`, `conflict` or `refresh_failed` status without local paths/exception
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

The mounted-corpus container rehearsal now also enables the channel on a private
UID 10001 tmpfs and mounts a second release read-only. It checks socket/parent
permissions, stale-pin retention, live A-to-B refresh and B-to-A rollback without
changing the container process ID, old-source hash rejection, and a clean restart
that restores startup-configured A after a live B refresh. It invokes the shipped
CLI through `docker exec`; Docker access is trusted, not a remote operator API.
No host socket is exposed. This extends the default container checks; it does not
establish a coordinated rollout or host/container UID mapping policy.

## Hosted evidence — October 27, 2026

Initial implementation `adde7597e46e4fbf41f73f381f7aead3930eaec1`,
[run 40579723192](https://github.com/harshaattili-human/runbookops/actions/runs/40579723192),
passed all five jobs. The container extension
`bde73254ab230c6acc12b47ab3471692c6be657c`,
[run 40580141296](https://github.com/harshaattili-human/runbookops/actions/runs/40580141296),
also passed all five: verify 122457014694, container 122457014654, browser
122457014349, Spring 122457014121 and dependencies 122457014532.

The suite passed 218 Python cases plus 11 subtests, including eight new POSIX
operator cases/executions (the shutdown case runs for worker success and failure).
The existing seven component tests/build, 18 Java executions plus live JAR,
36 live and 18 recorded browser executions, validation commands and both container
rehearsals passed. Frozen-dataset integrity scored zero holdout queries. No model,
ranking, threshold or benchmark corpus changed; checked-in evaluation reports
remain their dated historical records. Local execution limitations above remain.

The operator container used Docker 28.0.4, UID 10001, read-only root, dropped
capabilities, no-new-privileges, a private tmpfs socket and read-only releases.
Its two synthetic one-document generations and 11 declared checks are preserved in
[the receipt](../reports/operator-container-2026-10-27.json), including image and
manifest/document hashes. The image is identified, not published to a registry or
claimed reproducible byte-for-byte. Hosted Python 3.12.15, Node 24.21.0, Java
17.0.20.1 and Ubuntu 24.04 were used. The image audit inventoried 24 Python package
names and 164 finding entries, with zero fixable high/critical entries; the Java
audit inventoried 26 libraries with zero entries, and npm reported zero in that
snapshot. These dated gates do not establish absence of vulnerabilities. Existing
Lucide build warnings remain.
