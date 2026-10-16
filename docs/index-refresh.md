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

Atomic publication is not an atomic filesystem update. Stop writers during the
complete rebuild: reading multiple files while another process edits them can
produce a mixed corpus. This method does not detect or repair that situation.
Published retrievers are read-only by convention; trusted Python code must not
mutate their dictionaries, matrices or thresholds. Multiple server processes each
own their index and need separate coordination or restarts. Hashes identify text,
not freshness, authenticity or answer correctness.

## Verification

```sh
python -m pytest tests/test_index_refresh.py -q
```

Four synthetic regression cases cover live API version conflicts/removal and
receipt isolation; failed rebuild retention and recovery; event-controlled
concurrent rebuild serialization with reads still completing; and a paused answer
retaining its original search results and threshold across publication. These are
consistency tests, not load, memory or multi-process measurements. No corpus,
ranking policy, answerability threshold or exposed holdout is changed.

Interview exercise: why must a request capture the retriever once even though
replacing a single reference is short, and why is publication atomicity insufficient
when source files are edited concurrently?
