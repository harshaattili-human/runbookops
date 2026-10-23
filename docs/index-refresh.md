# Atomic in-process index refresh

`TriageService.refresh_runbooks()` rebuilds the runbook index while requests keep
using the published snapshot. Only a successfully constructed index replaces it.
A failed read or index build propagates its exception and leaves the working index
available. The classifier and incident training rows are not rebuilt.

Live refresh is a trusted Python integration operation. The stock HTTP app loads its
index at startup, optionally from a pinned release as described below. There is no
public refresh endpoint, watcher, signal handler or cross-process control channel.
A hosting integration that owns the service can run:

```python
# Stop source writers and finish the complete corpus update first.
hashes = await asyncio.to_thread(service.refresh_runbooks)
```

The returned dictionary is a copy of the published document hashes. Synchronous
operators can call the method directly. Do not run the blocking rebuild on an
async application's event loop. Cancelling an awaiting thread wrapper does not
stop its worker; the refresh can still finish and publish.

The direct-directory method remains useful for tests and controlled integrations,
but it cannot establish a multi-file filesystem generation. For coordinated
publication, create a new release directory and refresh from its manifest instead:

```sh
python -m runbookops.corpus_release \
  --source data/runbooks \
  --releases /var/lib/runbookops/releases \
  --corpus-id 2026-10-23-a
```

The command reads and validates the complete source in memory, writes a new temporary
directory, verifies its manifest, and renames it to the requested never-overwritten
release name. It refuses to replace an existing release. A trusted integration then
publishes that exact release:

```python
receipt = await asyncio.to_thread(
    service.refresh_runbooks_release,
    Path('/var/lib/runbookops/releases/2026-10-23-a'),
    expected_manifest_hash=approved_manifest_sha256,
)
```

`refresh_runbooks_release()` resolves the release directory once, reads a strict
schema-v1 manifest, rejects duplicate JSON keys, unsafe filenames, symlinked runbooks,
unexpected inventory and text-hash mismatches, and builds the candidate from the
verified in-memory texts. Its receipt includes the corpus ID, resolved release path,
manifest hash and a detached copy of every indexed document hash. A failure at any
point retains the old index. The optional `expected_manifest_hash` pins the raw
manifest bytes before any runbooks are read. Without it, this trusted method verifies
the release's internal consistency but does not select a particular manifest in
advance. Even a manifest-only formatting change needs a new pin.

## Select a release at startup

Copy `manifest_sha256` from the release command's reviewed JSON receipt into the
launch configuration. Set both values before starting the ordinary API:

```sh
export RUNBOOKOPS_CORPUS_RELEASE=/var/lib/runbookops/releases/2026-10-23-a
export RUNBOOKOPS_CORPUS_SHA256='<64 lowercase hex characters from the receipt>'
python -m uvicorn runbookops.api:app --host 127.0.0.1 --port 8000
```

Do not recompute the expected hash from the release at every launch: that would
accept a replacement manifest automatically. Verification checks the expected raw
manifest hash, strict schema, inventory and normalized document hashes, then builds
the index solely from those verified texts. A partial/empty configuration, malformed
hash, missing release, hash mismatch or index-build error prevents startup. There is
no fallback to bundled runbooks. With neither variable set, startup is unchanged.

Trusted Python callers can use `TriageService(runbook_release=path,
expected_manifest_hash=digest)`; both arguments are required together. The API reads
environment settings during its existing [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/)
startup, before accepting requests. The classifier training data and evaluation
reports still come from `RUNBOOKOPS_ROOT`; selecting a different runbook release does
not retrain the classifier or make the bundled evaluation applicable to that corpus.

An alias path is [resolved once](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path.resolve)
per load. Changing its target does not alter an already running index. Restarting
against a different manifest with the old pin fails; adopting that release requires
updating the expected hash too. Retain the old release and its pin for an explicit
restart rollback. This is a restart-based selection mechanism, not a hot-reload
trigger or an atomic rollout across workers. Trusted Python refresh calls can still
replace the index after startup; the startup pin is not a runtime authorization rule.

## Consistency contract

A refresh lock serializes complete rebuilds, preventing an earlier candidate from
replacing a later one. A separate short snapshot lock protects publication and
capture; requests do not hold it during retrieval or generation. Each triage call
captures one retriever for ranking, coverage, threshold and citation extraction.
Overview reads also capture one index. Optional generation already receives
materialized evidence, so later refreshes do not replace its source text.

An in-flight request can finish with an older document version after publication.
Opening that citation against a changed document returns 409; a removed document
returns 404. The client must analyze again. Old snapshots remain alive only while
readers reference them; rebuilds temporarily require memory for both indexes.

The original direct-directory refresh is not an atomic filesystem update. Stop
writers during that complete rebuild: reading multiple files while another process
edits them can produce a mixed corpus. Manifest-pinned releases close that refresh-time
gap because every indexed text must match one declared generation. Stop writers while
the release command captures its source too; no reader can infer an intended transaction
if a producer is actively replacing several source files without its own publication
protocol. Do not edit a published release. Later edits are detected on the next
verification but cannot retroactively change the in-memory snapshot.

Directory rename is atomic only on the release filesystem. This workflow does not
claim crash durability, authenticity or authorization: the manifest is an integrity
receipt, not a signature. An expected hash selects that receipt; it does not establish
who authored it. The stock app still has no HTTP refresh route, signal handler or
watcher. Each process must be restarted with the same path and pin or triggered by a
trusted integration with the same release. During a staggered rollout, running
processes can serve different generations; a failed restart remains unavailable.

Published retrievers are read-only by convention; trusted Python code must not
mutate their dictionaries, matrices or thresholds. Multiple server processes each
own their index and need separate coordination or restarts. Hashes identify text,
not freshness, authenticity or answer correctness.

## Verification

```sh
python -m pytest tests/test_index_refresh.py tests/test_corpus_release.py tests/test_corpus_startup.py -q
```

Four original synthetic regression cases cover live API version conflicts/removal and
receipt isolation; failed rebuild retention and recovery; event-controlled
concurrent rebuild serialization with reads still completing; and a paused answer
retaining its original search results and threshold across publication. These are
consistency tests, not load, memory or multi-process measurements. No corpus,
ranking policy, answerability threshold or exposed holdout is changed. The release
cases add creation/round-trip checks, detached receipts, changed/incomplete inventory
rejection with old-index retention, schema/path/symlink rejection and invalid-candidate
cleanup.

Startup-selection checks add strict manifest pins and integer schema versions,
an event-controlled alias replacement during refresh, and retention after a
correctly hashed but unbuildable candidate. A real Uvicorn subprocess check starts
from a release without any bundled runbooks, keeps serving its original snapshot
after alias replacement, rejects a restart with the stale pin, accepts an explicitly
updated pin, returns 409 for the prior source version, and rejects later document
tampering. Partial configuration is also rejected through the API lifespan. The
inherited-socket subprocess case targets POSIX and is skipped on non-POSIX platforms.
Existing packaged container and browser checks continue to exercise default startup;
they do not verify release selection inside a container or coordinated worker rollout.

The implementation head `b540d26` passed
[run 39966209481](https://github.com/harshaattili-human/runbookops/actions/runs/39966209481)
on October 23, 2026. The verify job ran 174 Python cases plus 11 subtests, including
the seven release cases, and retained the existing synthetic evaluations, seven
frontend component cases and production build. The other jobs passed 27 live and
18 recorded browser executions, nine Spring client cases plus its executable
walkthrough, packaged container HTTP/non-root/read-only/health/shutdown/restart checks,
and configured dependency audits. The dated scans reported 164 runtime-image finding
entries with zero fixable high/critical entries, zero entries for 26 packaged Java
libraries, and zero npm advisories. These scan results are not a vulnerability-free
claim.

Hosted versions were Python 3.12.15, Node.js 24.21.0 and Java 17.0.20.1 on Ubuntu
24.04. Local Python 3.12.14 passed compilation, whitespace checks, a ten-document CLI
release round trip and deliberate hash-tampering rejection. FastAPI, httpx and pytest
were unavailable in that local environment, so the complete application evidence is
hosted. No model, corpus, ranking setting, answerability threshold or exposed holdout
changed or was rescored.

The startup-selection increment `390d709` passed all five jobs in
[run 39970345934](https://github.com/harshaattili-human/runbookops/actions/runs/39970345934)
on October 23, 2026: 184 Python cases plus 11 subtests, including ten new cases for
pins, configuration, alias changes and process restart. The existing seven component
cases/build, validation commands, 27 live and 18 recorded browser executions, nine
Java cases/live walkthrough, container checks and audit gates also passed. The
runtime-image scan retained 164 finding entries with zero fixable high/critical
entries; 26 packaged Java libraries and npm had zero advisory entries in that dated
scan. This is not a vulnerability-free claim.

Hosted execution used Python 3.12.15, Node.js 24.21.0 and Java 17.0.20.1 on Ubuntu
24.04.5. Local Python 3.12.14 passed compilation, documentation links, whitespace and
a ten-document release round trip with deliberate manifest/schema rejection; full
API/process/browser/container/Java execution was hosted. No corpus, model, ranking
or threshold changed, and no exposed holdout was rescored.

Interview exercise: why does comparing a manifest with a separately supplied hash
protect restart selection, while recomputing that expected hash at every launch
defeats the selection check? What still happens during a staggered worker restart?
