# Roll out a corpus across local processes

A local operator can now apply a manifest-pinned release to an explicit list of
process sockets, using each process's observed corpus as a precondition. The tool
records a journal and stops at the first failure. Earlier workers may already have
changed; later workers are untouched. It does not describe that partial result as
a successful or atomic deployment.

First inspect each worker directly:

```sh
python -m runbookops.corpus_control --socket /private/w1.sock --inspect
```

Build a JSON plan with `release` (absolute target path), `manifest_sha256` (the saved
pin), and `workers` in the desired application order. Each worker has an `id`, an
absolute private `socket`, and `expected_corpus` containing the complete `corpus`
object from its inspect reply. Use distinct IDs and socket paths. For example,
replace the placeholders below with actual saved values:

```json
{
  "release": "/absolute/releases/b",
  "manifest_sha256": "SAVED_64_CHARACTER_MANIFEST_SHA256",
  "workers": [
    {
      "id": "worker-1",
      "socket": "/private/w1.sock",
      "expected_corpus": {
        "schema_version": 1,
        "source": "release",
        "corpus_id": "a",
        "manifest_sha256": "OBSERVED_64_CHARACTER_MANIFEST_SHA256",
        "documents_sha256": "OBSERVED_64_CHARACTER_DOCUMENTS_SHA256"
      }
    }
  ]
}
```

```sh
python -m runbookops.corpus_rollout --plan rollout.json --journal attempt-1.jsonl
```

The plan is at most 64 KiB and contains 1..32 workers. Duplicate JSON fields, worker
IDs, sockets, path aliases and incomplete identities are rejected. Before contacting
any worker, the coordinator verifies the target pin/inventory and builds its index
locally. Workers must share access to that absolute release path; this is a local
process tool, not an SSH, container-orchestration or multi-host transport.

The journal is created exclusively with mode 0600. Existing files are never
overwritten. Records identify the plan hash, target identity, worker IDs and outcomes;
they omit socket/release paths and exception messages. Each record is flushed and
fsynced before proceeding. A storage failure stops the run, including failure after
a refresh may already have published. Keep the plan and journal together under
trusted operator control. An interrupted write may leave a partial final JSON line;
there is no atomic journal replacement, directory-fsync, crash-recovery or
power-loss-durability guarantee.

## Partial outcomes and recovery

The coordinator sends one guarded refresh per worker, sequentially. `conflict`,
`busy`, invalid requests and refresh failures stop it. A transport failure or invalid
reply during application is `ambiguous`: that worker may have published already.
`workers_acknowledged` counts successful replies, not all changes that might have
occurred. There is no automatic retry, resume, rollback or write to startup settings.

After every apply reply succeeds, it re-inspects each exact socket. A different
identity or unavailable/busy worker stops verification. A final `complete` record
means all listed workers acknowledged the target and were then observed serving it.
These are sequential observations, not a simultaneous consistency barrier. Another
operator can change a worker between or after observations. No traffic draining,
load-balancer control, worker discovery, quorum or distributed lock is provided.

After a stopped/interrupted run, inspect every listed worker. Decide whether to
continue or roll back; prepare a new plan with those actual observed identities and
a new journal name. Retain the original evidence. Rollback is the same guarded
workflow targeting a retained release. Remember that a process restart still uses
its separately configured startup release and pin.

Filesystem ownership and same-UID/root trust remain the operator authorization
boundary. The [guard](guarded-refresh.md) compares content identities, so it does
not detect A-to-B-to-A history. The tool does not authenticate a publisher, prove
release quality, or coordinate unrelated trusted in-process callers.

## Verification

```sh
python -m pytest -q tests/test_corpus_rollout.py tests/test_corpus_control.py
```

Controlled cases check preflight rejection before any command, existing-journal
preservation, second-worker conflict and ambiguous reply with no third-worker call,
post-apply drift, and journal failure after one acknowledged change. A POSIX process
case launches three actual Uvicorn workers against synthetic single-document releases:
A/A/A is observed, another operator changes the middle worker to C, the stale plan
stops at B/C/A, and an explicitly revised plan reaches B/B/B. It checks exact-socket
inspection, CLI exit codes, the journal and old-source hash conflicts over HTTP.

This fixture is a correctness/recovery rehearsal, not a load, crash or deployment
test. No model, candidate, threshold, benchmark dataset or holdout score changes.
Local compilation/diff checks run; socket/application execution needs hosted CI
because the local environment denies AF_UNIX and lacks application test dependencies.

Interview exercise: why is a lost reply different from a rejected precondition,
and why would an automatic rollback risk overwriting another operator's work?

## Hosted evidence — October 28, 2026

Implementation `9af7c15657eddbf65411aa740bb28f294052dd72` passed all five jobs in
[run 40696433740](https://github.com/harshaattili-human/runbookops/actions/runs/40696433740):
verify 122844330067, container 122844329605, browser 122844330049, Spring client
122844330245 and dependencies 122844330200. The Python suite passed 228 cases plus
11 subtests, including six new rollout executions (conflict/lost reply are two
parameterized executions). The three-worker Uvicorn/CLI recovery case passed on
hosted Linux. It uses three authored one-document release generations and scores
no holdout queries.

The existing seven component tests/build, 18 Java executions plus live walkthrough,
36 live plus 18 recorded browser executions, validation and both container rehearsals
passed. The new multi-process rehearsal runs in Python tests; the existing container
rehearsal does not run the coordinator. Hosted Python 3.12.15, Node 24.22.1, Java
17.0.21 and Ubuntu 24.04 were used. The runtime audit reported 164 finding entries
and zero fixable high/critical entries across 24 inventoried Python package names;
Java inventoried 26 libraries with zero entries. Dated audit success is not absence
of vulnerabilities. Local compilation/whitespace passed; process execution remained
hosted under the documented local socket/dependency limitations.
