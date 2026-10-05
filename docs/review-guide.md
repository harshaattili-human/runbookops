# Technical review guide

RunbookOps explores one workflow: given an incident description, show a suggested
service area and the runbook evidence worth inspecting. The current implementation
is a local prototype. It has not been used to resolve production incidents.

## Implementation map

| Concern | Implementation | Evidence or boundary |
| --- | --- | --- |
| Incident routing | [Classifier](../backend/runbookops/classifier.py): TF-IDF plus logistic regression, term contributions, and heuristic abstention | [Grouped evaluation](../backend/runbookops/evaluate.py); model scores are not calibrated confidence |
| Runbook retrieval | [Retriever](../backend/runbookops/retrieval.py): Markdown sections, BM25/cosine ranking, line references | [Source-line and unrelated-query checks](../tests/test_triage.py); only a small lexical corpus is evaluated |
| HTTP boundary | [API](../backend/runbookops/api.py): length validation, rejected extra fields, known-runbook lookup | Invalid inputs and unknown runbooks are tested; authentication and tenant isolation are absent |
| Answerability and construction | [Service](../backend/runbookops/service.py): document-coverage gate, exact source extraction, optional Ollama synthesis, citation-ID validation | [Frozen holdout](answerability-v2.md) records reduced unsupported answers and supported-answer loss; live generation quality is unmeasured |
| Investigation interface | [React workbench](../frontend/src/main.tsx): sample inputs, routing signals, source inspection, evaluation view | [Component interactions](../frontend/src/main.test.tsx) cover dialog focus/Escape/restore, errors, navigation and empty state; no real-browser or assistive-technology verification |
| Repeatability | [CI workflow](../.github/workflows/ci.yml), dependency manifests, [evaluation report](../reports/evaluation.json) | CI runs tests, evaluation, and frontend build; the Dockerfile has not yet been built in CI |

## Decisions worth examining

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
answers require valid retrieved citation IDs and fall back when the provider or
validation fails. An answer can cite a valid passage and still misrepresent it;
entailment and live-model evaluation remain open work.

**Answerability after retrieval.** A top-ranked passage is not automatically shown.
The service first checks IDF-weighted query-term coverage across its document. The
fixed v2 holdout reduced unsupported answers from 11/14 to 3/14 but withheld one of
12 supported answers. Strong topical overlap still passes some requests for absent
credentials, numerical guarantees, and business decisions.

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

1. Compare passage-level answerability methods on validation, including missing
   credentials/values and verbose supported incidents; freeze a new holdout before
   another improvement claim.
2. Real-browser coverage for responsive layout and source inspection, plus manual
   assistive-technology checks. Component-level keyboard focus coverage is implemented.
3. Container-build checks and measured latency/concurrency behavior with a stated
   environment; individual request timing is not a load test.
4. Live LLM evaluation before making generation-quality claims. Authentication,
   abuse controls, and tenant boundaries before exposing a live public API.

See the [development backlog](roadmap.md) for planned work. Planned items are not
part of the current implementation.

The source dialog follows the W3C
[modal keyboard pattern](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/):
focus enters the dialog, Tab remains contained, Escape closes it, and focus returns
to the invoking source card.
