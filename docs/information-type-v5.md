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
PYTHONPATH=backend python -m unittest tests.test_information_dataset_v5 -v
```

The default integrity command now includes v5. It reads public labels to check
hashes, inventory, field structure, query separation and exact quote alignment,
but imports no retriever/service and scores zero queries. `load_cases(version="v5")`
loads validation by default; holdout requires explicit `allow_holdout=True`.
This guard prevents accidental loading, not access to the public JSON files.

A matching quote proves alignment, not that an annotation is semantically correct.
Record disputed labels before scoring; if discovered after the holdout score,
preserve the original result and report the dispute rather than silently editing it.

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
