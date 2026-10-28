# Reject stale corpus refresh commands

Two trusted operators can observe A and independently prepare B and C. Serializing
builds alone would still let the second command overwrite B using its stale view
of A. A refresh can now carry the complete previously observed corpus identity.
The service compares it under the refresh lock before reading the candidate release.
A mismatch returns `conflict` and leaves the published snapshot unchanged.

Save the `corpus` object from this specific worker's `/healthz` response as JSON,
review the target release and saved manifest pin, then run:

```sh
python -m runbookops.corpus_control --socket /private/operator.sock \
  --release /absolute/releases/release-b --sha256 SAVED_MANIFEST_SHA256 \
  --expected-corpus observed-corpus.json
```

The optional wire field is `expected_corpus`; partial, null, extra-field and
inconsistent identities are invalid. Comparison includes schema, source, corpus ID,
manifest hash and document inventory hash. Matching documents with different release
metadata therefore conflict. The CLI exits 1 for a conflict; it never rereads the
current identity and retries automatically. Inspect the worker and decide explicitly.
The in-process method accepts the same optional `expected_corpus` argument and
raises `CorpusConflict`. Direct directory refreshes use the same serialization lock,
so a guarded command queued behind one compares against its resulting publication.

Omitting the precondition preserves the original trusted unconditional operation.
This is a content-identity comparison, not a monotonically increasing revision:
A-to-B-to-A is indistinguishable from unchanged A and is deliberately accepted.
It is not multi-process atomicity, durable transaction logging, authorization,
startup-configuration persistence or publisher authentication. A lost reply still
has an ambiguous result; guard failure on retry does not prove which operator won.
Use distinct worker endpoints and sockets; sampling a load-balanced health URL
cannot establish the precondition of a particular worker.

## Verification

```sh
python -m pytest -q tests/test_corpus_control.py tests/test_index_refresh.py
```

Added synthetic checks cover malformed identities, same-document/different-release
conflict, rejection before candidate filesystem access, a command queued behind a
latched trusted directory refresh, and real Uvicorn/CLI success, stale retry and
explicit recovery. Existing unguarded, pin, permissions, cancellation and container
workflows remain regression checks. No dataset or answerability rule changes.
Local compilation/whitespace checks pass; local AF_UNIX creation is denied and the
application test dependencies are absent. Hosted results are recorded separately.

Interview exercise: why must the precondition be checked after acquiring the build
lock, and why does content equality fail to detect an A-to-B-to-A publication history?

## Hosted evidence — October 28, 2026

Implementation `3def2490c4e096184705cb359a7b7767776355c0` passed all five jobs in
[run 40694019996](https://github.com/harshaattili-human/runbookops/actions/runs/40694019996):
verify 122835881490, browser 122835881365, container 122835881588, Spring client
122835881511 and dependencies 122835881191. There were 222 Python cases plus
11 subtests (four new cases), seven component tests/build, 18 Java executions and
the live JAR walkthrough, 36 live plus 18 recorded browser executions, validation
commands, default/mounted-release containers and audit gates. No holdout was scored.
The new CLI race/recovery evidence is in Python's POSIX tests; existing container
checks still exercise unguarded operator commands.

The runtime audit inventoried 24 Python names and 164 finding entries, with zero
fixable high/critical entries. The Java audit inventoried 26 libraries with zero
entries. These dated scan results do not mean vulnerability-free. Java was
17.0.21; the hosted job used the configured Python 3.12 / Node 24 / Ubuntu 24.04
matrix. Local identity/parser probes, compilation and whitespace checks passed;
full application execution remained hosted because of the local restrictions above.
