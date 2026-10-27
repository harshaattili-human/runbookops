# Identify the corpus serving a response

A startup manifest pin selects a release, but it did not tell an operator which
release a running process was actually serving. Successful health, overview,
triage and source responses now include a `corpus` object captured with the same
published index used by that response. It contains no filesystem path.

| Field | Meaning |
| --- | --- |
| `schema_version` | Identity format, currently integer 1 |
| `source` | `release` for a verified release; `directory` for direct/bundled loading |
| `corpus_id` | Verified manifest's release ID, or null for a directory |
| `manifest_sha256` | SHA-256 of verified raw manifest bytes, or null for a directory |
| `documents_sha256` | SHA-256 of the indexed document-hash inventory described below |

The content inventory is a JSON object mapping document slug to lowercase SHA-256
of its indexed UTF-8 text. Serialize it with sorted keys, compact separators
(`,` and `:`), ASCII escaping and no trailing newline, encode as UTF-8, then hash
those bytes. The schema version makes that serialization contract explicit.
Retrieval already normalizes file line endings when reading text. The digest
identifies that served text, not the source filesystem's raw bytes.

Two releases with identical documents can share `documents_sha256` while having
different release IDs and manifest hashes. Renaming, adding, removing or changing
any indexed document changes the inventory. The identity does not include the
classifier, routing thresholds, request-target guard, application binary or model
quality. Bundled evaluation results do not become applicable to a custom corpus.

## Publication and observation

The service publishes an immutable snapshot wrapper containing the retriever and
its identity under the existing short lock. Each response captures that wrapper
once. Index construction and digest calculation happen before publication. Failed
refresh retains both the old index and identity; a direct-directory refresh clears
previous release metadata. Returned identity dictionaries are detached. Trusted
Python integrations must still avoid mutating the retriever itself.

An in-flight triage can finish with the old corpus identity after a refresh. That
is intentional: its identity follows its own evidence. Later source inspection
can return a different corpus identity while an unchanged document hash still
matches. Existing `expected_hash` remains a per-document check, not a whole-corpus
pin. Removed or changed documents retain the existing 404/409 behavior.

For an individually addressed process:

```sh
curl --fail http://127.0.0.1:8000/healthz
```

Compare its manifest/content identity with the reviewed release. Query every
individually addressable replica to inspect a rollout; repeated requests through
a load balancer cannot prove that every worker was sampled. The identity is an
observation, not a readiness gate, coordinator, authenticated publisher statement
or proof of fleet convergence. Health still reports a functioning local service.
Release IDs are now public response metadata, so choose nonsensitive names.

## Verification

```sh
python -m pytest -q tests/test_corpus_identity.py tests/test_index_refresh.py tests/test_corpus_startup.py
python scripts/container_smoke.py --image runbookops:smoke
python scripts/corpus_container_smoke.py --image runbookops:smoke
```

Three new Python cases cover cross-route identity, filesystem edits versus
publication, pinned-release startup, failed-refresh retention, clearing metadata
on directory refresh and equal-content/different-manifest releases. The existing
event-held triage case now proves its old identity survives a concurrent refresh.
The existing real Uvicorn restart case checks selected manifest identities.

Both container scripts now verify identity from the actual built image. The
mounted fixture checks it on health/overview/source/triage across A restart,
coexisting A/B processes and explicit rollback. Existing stale-pin/tamper startup
failures and cross-generation document conflicts remain. This is a local Linux
Docker rehearsal, not deployment or coordinated rollout evidence.

Implementation `4be32026957ea1d3a3fb71be4193a447c82f8a32`,
[run 40575920440](https://github.com/harshaattili-human/runbookops/actions/runs/40575920440),
passed verify `122442201628` with 210 Python cases plus 11 subtests, seven component
cases and the frontend build; Spring `122442201360` passed 18 Java executions and
the live executable walkthrough. Container `122442201001` passed default and
mounted-corpus rehearsals. Its runtime image inventory had 24 Python package names,
164 advisory entries and zero fixable high/critical entries; the Java inventory
had 26 libraries and zero entries in those dated snapshots. These are not
vulnerability-free claims. The browser job was still installing system packages when this documentation
commit was prepared; no browser-pass claim is made for that implementation run.
The final-head results are recorded in [PR 33](https://github.com/harshaattili-human/runbookops/pull/33).

Local compilation, whitespace and documentation links passed. The focused local
pytest command could not run because pytest is absent. Application,
Java, browser and Docker execution used hosted CI. The frozen retrieval and v4
guard source hashes are unchanged. No dataset, ranking, threshold or model changed;
CI uses validation only and no exposed holdout was rescored.

Optional exercise: why can a source document retain its hash while the corpus
identity changes, and why is observing both A and B not proof of an atomic rollout?
