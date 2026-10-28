# Technical review guide

RunbookOps explores one workflow: given an incident description, show a suggested
service area and the runbook evidence worth inspecting. The current implementation
is a local prototype. It has not been used to resolve production incidents.

## Implementation map

| Concern | Implementation | Evidence or boundary |
| --- | --- | --- |
| Incident routing | [Classifier](../backend/runbookops/classifier.py): TF-IDF plus logistic regression, term contributions, and heuristic abstention | [Grouped evaluation](../backend/runbookops/evaluate.py); model scores are not calibrated confidence |
| Runbook retrieval | [Retriever](../backend/runbookops/retrieval.py): Markdown sections, BM25/cosine ranking, line references | [Source-line and unrelated-query checks](../tests/test_triage.py); only a small lexical corpus is evaluated |
| Source identity | SHA-256 of indexed document text; optional expected-hash check; [served corpus identity](corpus-identity.md) | [Snapshot and version-mismatch tests](../tests/test_source_versions.py); workbench refuses changed or removed versions; automatic refresh remains pending |
| HTTP boundary | [API](../backend/runbookops/api.py): length validation, rejected extra fields, known-runbook lookup | Invalid inputs and unknown runbooks are tested; authentication and tenant isolation are absent |
| Answerability and construction | [Service](../backend/runbookops/service.py): document-coverage and fixed request-target gates, exact source extraction, optional Ollama synthesis over HTTPX2, citation-ID validation | [v3 contrastive comparison](information-type-v3.md) records a positive paired result and the runtime regression that prevented adoption; the [transport migration](httpx2-migration.md) preserves the provider boundary |
| Investigation interface | [React workbench](../frontend/src/main.tsx): sample inputs, routing signals, source inspection, evaluation view | [Component interactions](../frontend/src/main.test.tsx) plus [live browser checks](browser-checks.md) cover source focus/scrolling, version checks, navigation and narrow layouts; assistive-technology and physical-device verification remain pending |
| Repeatability | [CI workflow](../.github/workflows/ci.yml), dependency manifests, [evaluation report](../reports/evaluation.json) | Separate [container checks](container-checks.md) exercise the packaged UI/API, non-root read-only operation, health and restart; the separate mounted-release rehearsal checks selection, version conflicts and explicit rollback; no deployment or load claim |
| Java integration | [Spring Boot client](spring-client.md): typed extractive/abstained results, response request IDs and versioned source inspection | Loopback failure fixtures and live FastAPI contract checks; synchronous calls with connect/read inactivity timeouts, no whole-request deadline |

## Source versions

Each triage source includes `document_hash`, the lowercase SHA-256 hex digest of
its complete indexed document, not just the returned passage. The runbook endpoint
returns the same value as `content_hash`. Hash input is the UTF-8 encoding of the
served `content`: text-mode reading normalizes CRLF/CR to LF; trailing newlines and
all other text are retained. File location and timestamps do not enter the hash.

A version-aware client sends `GET /api/runbooks/{slug}?expected_hash=<document_hash>`.
A matching version returns HTTP 200 with `{id, content, content_hash}`; a mismatch
returns HTTP 409 with `{"detail":"Runbook version changed; run triage again."}` and
no document content. A removed or unknown document returns HTTP 404. Omitting
`expected_hash` retains the unversioned fetch behavior for existing callers.
Compare the complete hash rather than relying on the section ID, which can survive
an edit while its line numbers or contents change.

This identifies an in-memory snapshot; it does not make that snapshot current.
Sources are still read only when the retriever is constructed. Disk edits do not
change a running service until it restarts or explicitly rebuilds its index. The
workbench sends the citation hash and checks the returned hash before opening the
dialog. HTTP 409 or a mismatched response hash asks for a new analysis; HTTP 404
explains that the source was removed. The current page and card focus are retained,
and starting another analysis clears that alert. Library browsing intentionally
fetches the current snapshot without pinning a prior version. Automatic refresh
remains a separate backlog item. Hashes detect version differences, not
source authenticity, factual correctness, or LLM citation entailment.

The [12 focused regression cases](../tests/test_source_versions.py) cover all three
ranking modes, Unicode text, normalized line endings, stable and changed hashes,
restart/version conflicts, removed sources, and unversioned callers. Run
`python -m pytest -q tests/test_source_versions.py`. These are synthetic contract
checks, not a new retrieval-quality evaluation. Four additional workbench cases
cover versioned success, changed/removed sources, an unexpected HTTP 200 with a
different hash, and recovery through reanalysis. They use jsdom, not a real browser.
The recorded-demo fetch shim accepts versioned URLs, and the container HTTP check
compares full-document hashes and rejects version mismatches.

The hash is computed with Python [SHA-256](https://docs.python.org/3.12/library/hashlib.html)
from the same in-memory text used to build the index. Hashing a fresh disk read
instead would risk labeling old indexed passages with a newer file version.

Verified October 10 in [run 38063334397](https://github.com/harshaattili-human/runbookops/actions/runs/38063334397)
at implementation head `07ca789`: 41 Python tests, seven frontend component tests,
classifier/validation evaluations, production build and packaged container
HTTP/restart checks passed. Local Python 3.12.14 checks also passed, including a
Uvicorn HTTP smoke and exported replay-shim checks for all ten runbooks. Docker ran
in hosted CI; no new real-browser, accessibility or retrieval-quality claim follows.
Validation reports changed only in code hashes; exposed holdouts were not rescored.
The existing Starlette/httpx deprecation and Lucide bundling warnings remain.

## Decisions worth examining

The [v3 contrastive comparison](information-type-v3.md) published its candidate,
configuration, evaluator and validation report before a single holdout score. It
preserved the baseline expected-top-and-answered supported count (9/10 validation,
8/10 holdout), while unsupported answers changed from 8/10 to 0/10 on validation and
6/10 to 1/10 on holdout. It was still rejected after existing generation-admission
checks showed that “Active connections are at the maximum” triggered the value rule
even though it described the incident rather than asking a question. Inspect that
runtime regression alongside the pool-size failure, two coverage-withheld positives,
ordered expressions and final-sentence assumption. The service remains unchanged.

The follow-up [v4 experiment](information-type-v4.md) separates its integrity-only
freeze from a later validation-only candidate. The request-target guard retained 9/10
expected-top-and-answered supported cases and changed unsupported validation answers
from 8/10 to 0/10. Inspect its fixed ordered signals and per-case report, especially
the supported API-timeout case already withheld by document coverage. The service was
unchanged at the evaluation checkpoint. Its subsequent [integration](request-target-guard.md)
uses the exact frozen candidate and explains request-target refusals. The once-scored holdout preserved 10/10
supported answers and changed unsupported answers from 9/10 to 5/10. Read the five
missed targets and distinguish numeric eligibility from tested runtime integration.

**A small, inspectable classifier.** TF-IDF and logistic regression establish a
baseline that can train locally and expose influential terms. Its grouped macro F1
is approximately 0.945 versus 0.067 for a most-frequent-label predictor on the same
folds. The fixed-gate hybrid, BM25 and TF-IDF rankings tied on the new small query
suites. Embedding comparisons have not been run. See [the experiment](evaluation-v1.md).

**Retrieval independent of routing.** The classifier label does not filter runbooks.
This avoids hiding relevant evidence solely because the router chose the wrong
service area. The service can return useful evidence while requesting review of
the classification.

**Grouping by incident scenario.** Each of the 30 scenarios has three paraphrases.
The evaluation keeps a scenario's paraphrases in one fold and fits preprocessing
only on training data. This addresses that leakage route; it does not establish
generalization beyond the authored synthetic dataset.

**An explicit fallback.** Source extraction is the default. Optional generated
answers require valid retrieved citation IDs and a normally completed response.
The [provider boundary](ollama-boundary.md) rejects oversized envelopes before
parsing and closes rejected streams. The [generation deadline](generation-deadline.md)
cancels slow provider I/O and releases its admission slot.
[Client-disconnect handling](client-disconnect.md) also cancels optional work when
the ASGI server reports that the caller has left. An answer can cite a valid passage and still
misrepresent it; entailment and live-model evaluation remain open work.

**Answerability after retrieval.** A top-ranked passage is not automatically shown.
The service first checks IDF-weighted query-term coverage across its document. The
fixed v2 holdout reduced unsupported answers from 11/14 to 3/14 but withheld one of
12 supported answers. Strong topical overlap still passes some requests for absent
credentials, numerical guarantees, and business decisions. A later request-shape
guard improved a small paired holdout but also misread an existing descriptive incident,
so it remains experimental rather than part of the service.

## What the measurements establish

The checked-in report records approximately 0.945 macro F1 under three-fold grouped
cross-validation on 90 synthetic descriptions. This is a **forced-label classifier
metric**; it does not evaluate the service's abstention policy end to end.

Retrieval smoke checks find the expected document within four returned chunks for
10 positive queries and return no passage for four unrelated queries. The questions
are visible to the developer. They are not an independent holdout, and the perfect
smoke result should not be read as evidence of robust open-world retrieval.

The v1 validation and holdout suites each include eight near-topic unsupported
requests and two unrelated questions. Six unsupported requests in each split receive
guidance despite the absent target answer. The reports separate that behavior from
routing acceptance. These authored suites do not establish real-incident quality;
the published holdout is now exposed and must not become a tuning target. A later
26-case holdout measures the coverage gate separately; see
[the answerability report](answerability-v2.md) for its denominators and five failures.

Reproduction, split membership, individual errors, environment versions, and the
dataset hash are available in the [evaluation report](../reports/evaluation.json).
The [model card](model-card.md) describes thresholds and limitations.

## What needs evidence next

1. Test an information-type or entailment-oriented answerability method that can
   distinguish investigation guidance from absent credentials, values and business
   decisions. Do not tune on v2; freeze a new holdout before an improvement claim.
2. Touch/physical-device and manual assistive-technology checks.
   [Browser workflows](browser-checks.md) run on Chromium, Firefox and WebKit at
   three viewport sizes and include screenshots for review.
3. Open-arrival load and deployment-capacity evidence beyond the
   [closed-loop HTTP characterization](http-characterization.md). Its raw samples
   separate successful responses from rejection latency under explicit image limits;
   the container smoke check and individual request timing are not load tests.
4. Live LLM evaluation before making generation-quality claims. Authentication,
   abuse controls, and tenant boundaries before exposing a live public API.

See the [development backlog](roadmap.md) for planned work. Planned items are not
part of the current implementation.

The [recorded demo](recorded-demo.md) packages five actual synthetic API responses,
the runbooks and evaluation into one HTML file with an adjacent provenance receipt.
Its offline browser checks are separate from live inference checks. Use the replay
for a walkthrough; it supplies no additional model-quality evidence.

The source dialog follows the W3C
[modal keyboard pattern](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/):
focus enters the dialog, Tab remains contained, Escape closes it, and focus returns
to the invoking source card.

## Dependency evidence

[Triage admission](triage-admission.md) bounds concurrent HTTP lifetimes and joins
cancelled synchronous workers before returning their capacity. It is separate from
provider admission, phase deadlines and any future measured throughput claim.

[Image/dependency audits](dependency-audits.md) preserve installed inventories,
unfiltered advisories, scanner/database versions and the local image ID. The
fixed high/critical image gate permits unresolved OS findings; read the report
before interpreting a green check. npm's separate gate includes build/test tools.

Trusted integrations can now [refresh an index atomically](index-refresh.md).
Manifest-pinned, never-overwritten release directories keep a refresh on one declared
corpus generation and retain the old index on any inventory/hash/build failure. The
stock HTTP app can select an explicit release plus expected manifest hash at startup
and rejects invalid selections without falling back. Responses now identify their
[served corpus snapshot](corpus-identity.md), including optional manifest identity
and a content-inventory digest without filesystem paths. Its optional [local operator channel](operator-refresh.md) refreshes one process;
producer-side multi-file capture still requires stopped writers, and multiple
processes are not coordinated.

Trusted operator refreshes can now [compare an observed corpus identity](guarded-refresh.md)
before publication, including commands queued behind other trusted refresh paths.

The [local rollout rehearsal](local-rollout.md) exercises three real processes,
partial conflict, journals and explicit recovery without claiming atomic deployment.
