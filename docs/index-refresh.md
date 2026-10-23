# Atomic in-process index refresh

`TriageService.refresh_runbooks()` rebuilds the runbook index while requests keep
using the published snapshot. Only a successfully constructed index replaces it.
A failed read or index build propagates its exception and leaves the working index
available. The classifier and incident training rows are not rebuilt.

This is a trusted Python integration operation. The stock HTTP app still loads its
index at startup: there is no public refresh endpoint, watcher, signal handler or
cross-process control channel. A hosting integration that owns the service can run:

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
)
```

`refresh_runbooks_release()` resolves the release directory once, reads a strict
schema-v1 manifest, rejects duplicate JSON keys, unsafe filenames, symlinked runbooks,
unexpected inventory and text-hash mismatches, and builds the candidate from the
verified in-memory texts. Its receipt includes the corpus ID, resolved release path,
manifest hash and a detached copy of every indexed document hash. A failure at any
point retains the old index.

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
receipt, not a signature. The stock app still has no HTTP refresh route, signal handler
or watcher. Each process must be triggered by a trusted integration with the same
release, and a failed process can remain on the previous generation.

Published retrievers are read-only by convention; trusted Python code must not
mutate their dictionaries, matrices or thresholds. Multiple server processes each
own their index and need separate coordination or restarts. Hashes identify text,
not freshness, authenticity or answer correctness.

## Verification

```sh
python -m pytest tests/test_index_refresh.py tests/test_corpus_release.py -q
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

Interview exercise: why must a request capture the retriever once even though
replacing a single reference is short, why does a manifest stop refresh-time mixing,
and why can it neither authenticate the publisher nor coordinate several workers?
