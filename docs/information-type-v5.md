# Passage evidence evaluation freeze: v5

This increment freezes data and a comparison protocol, not a new answerability
method. No v5 query has been scored at publication. The service still uses the
unchanged document-coverage and v4 request-target gates. V1–v4 holdouts are exposed
and must not select a new candidate.

## What is being tested

Related-document ranking does not establish that the returned passage answers a
request. V5 pairs a request for a particular documented investigation/review detail
with a related request requiring information absent from the corpus. Each supported
request has one exact source sentence, annotated by one-based line range. A future
comparison must measure whether the **returned answer evidence** covers that span,
not merely whether the expected document ranks first.

[Validation](../data/evaluation/information-validation-v5.json) and
[holdout](../data/evaluation/information-holdout-v5.json) each contain ten pairs,
one per existing runbook: ten supported and ten unsupported requests. Each split
has two unsupported requests in each of five types: configuration value, live state,
approval, sensitive value and unwritten procedure. Total: 40 queries in 20 paired
contexts, not 40 independent incidents.

These are AI-assisted, same-author synthetic annotations with visible labels, not
blinded or independently reviewed data. They reuse the same ten topic families and
runbooks. Exact query/ID separation is checked; semantic independence is not claimed.
The phrasing often states the requested information directly, which can favor lexical
rules. This small diagnostic suite is not a representative operational benchmark.
No employer material or real incident data is included.

## Freeze and integrity

[The manifest](../data/evaluation/information-manifest-v5.json) pins both v5 splits,
v3/v4 splits, five earlier data files and all ten runbooks. Baseline commit
`0286b6bf61f9d8ad7e4f6db9d407c41b0a5646a2` identifies the current runtime, including
the fixed request-target guard. Earlier coverage-only baselines are historical;
they must not be substituted for the current runtime to inflate a new gain.

```sh
PYTHONPATH=backend python -m runbookops.information_dataset --version v5
PYTHONPATH=backend python -m unittest tests.test_information_dataset_v5 tests.test_evidence_metrics -v
```

The default integrity command now includes v5. It reads public labels to check
hashes, inventory, field structure, query separation and exact quote alignment,
but imports no retriever/service and scores zero queries. `load_cases(version="v5")`
loads validation by default; holdout requires explicit `allow_holdout=True`.
This guard prevents accidental loading, not access to the public JSON files.

A matching quote proves alignment, not that an annotation is semantically correct.
Record disputed labels before scoring; if discovered after the holdout score,
preserve the original result and report the dispute rather than silently editing it.

## Metric implementation

`runbookops.evidence_metrics.evidence_supported_and_answered` implements the
mechanical span criterion for a retained extractive service response. It resolves
citation IDs against returned sources, considers only the annotated document and
merges sorted inclusive line intervals without bridging gaps. Uncited retrieval
hits do not count. Duplicate citations cannot add coverage; duplicate source IDs,
unknown citations and invalid line intervals fail explicitly. Abstention and blank
answers fail the criterion. Local-model responses are outside this protocol.

Twelve hand-constructed unit cases cover exact/full, partial, wrong-passage,
wrong-document, uncited, disjoint/adjacent/overlapping and invalid evidence paths.
These fixtures do not load or score either v5 split. The helper trusts coordinates
from the retained response; the future evaluator must verify corpus/code hashes
and retain text. It does not prove that generated prose is faithful to those spans.
The validation-only baseline runner is implemented; candidate comparison and
holdout inference remain planned.

## Preregistered comparison

1. Develop a passage-aware candidate on v5 validation only. Keep corpus, classifier
   and ranking fixed. A learned method requires separate training data. Do not tune
   on exposed holdouts or the new holdout. If validation gives no useful improvement,
   retain that negative result without scoring holdout merely to seek a better result.
2. Publish candidate/configuration/evaluator hashes, all validation decisions and
   environment before any v5 holdout inference. The evaluator must test its metric
   calculations on hand-constructed cases, including correct document/wrong passage,
   partial span coverage, abstention and multiple disjoint citations.
3. Run the current runtime baseline and that fixed candidate jointly on holdout once.
   Use the extractive path only. Save exact returned text, cited spans, selected
   documents, decisions, signals, scores and failures for every query. Verify baseline
   code and corpus hashes before scoring; never overwrite the first score receipt.
4. Report supported answered /10, expected-top-and-answered /10, unsupported answered
   /10, unsupported type counts /2, and **evidence-supported-and-answered /10**.
   The last metric requires an answer plus returned evidence from the expected document
   whose line intervals cover the entire annotated span. A correct document alone,
   a partially covered span or an uncited retrieved passage does not pass. Report
   fully correct pairs /10 using that evidence criterion and refusal of the negative.
   Span coverage remains a mechanical proxy, not semantic entailment.
5. Adoption requires strictly fewer unsupported answers, no loss of either
   expected-top-and-answered or evidence-supported-and-answered supported cases,
   and a passing application regression suite. Preserve descriptive/no-question input
   behavior, concurrency/fallback contracts and existing provenance. Numerical
   eligibility alone does not authorize shipping a runtime regression.
6. Mark v5 holdout exposed after its first score. Do not repair the candidate based
   on those failures; a new improvement claim needs another frozen holdout.

No model-quality improvement, production accuracy, live LLM evaluation, independent
annotation, deployment or new runtime behavior is claimed by this freeze.

Optional exercise: construct an answer that cites the correct document but the wrong
section. Why would document-level scoring accept it while evidence-span scoring fails,
and why can even complete span coverage still fail to prove entailment?

## Validation baseline receipt

Run `python -m runbookops.passage_validation --output passage-validation-v5.json`
from an installed checkout. The command refuses to overwrite a receipt and has no
holdout option. It verifies pinned baseline code and training data from the protocol
checkpoint, checks the frozen datasets/corpus, then invokes the actual service with
`use_llm=False`. Returned source hashes, line bounds, passage text, citation IDs and
extractive answer text are checked before scoring. Integrity checks may read public
holdout labels; inference receives only validation queries.

The JSON retains all 20 validation responses, annotations, per-case decisions,
explicit metric denominators, code/input hashes and package/platform versions.
Fully correct pairs require supported cited-span coverage and negative abstention.
Missing or duplicate pair members fail rather than reducing a denominator. Response
IDs, durations and timestamps vary. CI retains the receipt for 30 days; regenerate
with a new output filename afterward. This is baseline measurement, not a candidate
improvement or a held-out result. No v5 baseline numbers were asserted before running
this command. The original freeze statement above describes its publication checkpoint.

### Recorded baseline, November 16, 2026

[Run 43887300263](https://github.com/harshaattili-human/runbookops/actions/runs/43887300263)
at implementation `17c46c8dcda242cc8aec388f0a3b9157a580244d` produced the
[complete receipt](../reports/passage-validation-v5-baseline.json). Python 3.12.16,
scikit-learn 1.8.0, NumPy 2.3.5, FastAPI 0.142.2 and HTTPX2 2.16.0 ran on Linux
x86_64/glibc 2.39. The receipt retains exact input/code hashes and package versions.
This is the unchanged current-runtime baseline on ten same-author validation pairs;
there is no candidate comparison and zero holdout queries were scored.

| Metric | Count |
| --- | --- |
| Supported answered | 10/10 |
| Expected top document and answered | 10/10 |
| Annotated evidence covered and answered | 6/10 |
| Unsupported answered | 6/10 |
| Fully correct pairs | 1/10 |

Unsupported answers by type: approval 1/2, configuration value 2/2, live state 1/2,
sensitive value 0/2 and unwritten procedure 2/2. The four supported passage misses
all returned the expected document: database-pool cited lines 19–20 instead of
annotated line 15; message-retries cited 5–7 instead of 9; pod-startup cited 5–7
instead of 11; workflow-jobs cited 8–13 instead of 15. Inspect their exact answer
text and query in the receipt. This demonstrates a limitation of document-only
scoring on this authored suite, not real-world error prevalence.

The checked-in receipt preserves this observation beyond CI artifact expiry. New
runs write new files; do not replace it silently or treat repeated validation runs
as independent evidence. Develop the next candidate on validation only, with the
existing ranking fixed as required by the preregistered protocol.
