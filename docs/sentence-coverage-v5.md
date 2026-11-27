# Sentence-local coverage: negative validation result

The existing whole-answer coverage probe can combine query terms appearing in
unrelated sentences. This experiment asks whether requiring those terms to occur
within one punctuation/newline unit provides a useful additional refusal signal.
It does not: neither tested variant reduces unsupported answers while retaining
the baseline supported metrics. No candidate is promoted and v5 holdout remains
unscored.

## Protocol and reproduction

```sh
PYTHONPATH=backend python -m unittest tests.test_sentence_probe tests.test_passage_probe tests.test_evidence_metrics -v
PYTHONPATH=backend python -m runbookops.sentence_probe --output sentence-validation-v5.json
```

The command refuses existing output files and has no holdout option. It first runs
the existing probe's checks of the pinned baseline receipt, code, training data,
frozen annotations, source hashes, passage text and citations. It then processes
only the saved validation responses; it does not invoke the service or a model.
The [baseline receipt](../reports/passage-validation-v5-baseline.json) remains
unchanged. Its SHA-256 is
`db9098dda34c56370eeab3ac21cfa2c322e4d9d4cf835654102a9cc1225495f4`.

Split each answered extract at newlines or whitespace following `.`, `!` or `?`,
discarding empty units. For each unit, compute the existing deterministic
IDF-weighted token coverage of (a) the whole query or (b) the frozen v4 request
clause. The score is the maximum unit coverage. No terms are combined across units;
no heading, annotation span, case ID or expected document selects the unit.
Baseline abstentions stay abstentions. Ranking, answer text, corpus and classifier
remain fixed. This simple splitter is deliberately inspectable, not a linguistic
sentence parser: abbreviations and wrapped prose can create misleading boundaries.

The sweep uses zero and the next representable float above every score. It chooses
the smallest threshold minimizing unsupported answers while preserving both
expected-document-and-answered and cited-evidence-and-answered counts. Every boundary,
per-unit text/score, per-case decision and pair-omission fold is retained in the
[November 27 receipt](../reports/sentence-validation-v5-2026-11-27.json), together
with code hashes and environment. The existing whole-answer comparison is retained
in that same receipt. This is repeated selection on visible validation, not fresh
held-out evidence or an estimate of production error rates.

## Observed result

Ten same-author AI-assisted pairs contain ten supported and ten unsupported
queries over the existing ten synthetic runbooks. These are twenty queries, not
twenty independent incidents. The local run used Python 3.12.14, NumPy 2.3.5,
scikit-learn 1.8.0, Linux x86_64 and glibc 2.41. Exact versions/platform and input
hashes are in the receipt.

| Policy selected on all ten validation pairs | Expected document and answered /10 | Cited annotation covered and answered /10 | Unsupported answered /10 | Fully correct pairs /10 |
| --- | --- | --- | --- | --- |
| Current runtime baseline | 10 | 6 | 6 | 1 |
| Whole-query sentence-local, threshold 0 | 10 | 6 | 6 | 1 |
| Request-clause sentence-local, threshold 0 | 10 | 6 | 6 | 1 |

For whole-query scoring, the supported workflow-job request scores approximately
0.13737, below every answered unsupported query (lowest approximately 0.14159).
Any threshold rejecting even the lowest-scoring unsupported answer therefore also
rejects that supported request. Its baseline passage is already wrong, but the
preregistered protocol requires preserving correct-document answers as well as
correct-evidence answers. We do not relax that rule to manufacture eligibility.

For request-clause scoring, the supported pod-startup and workflow-job requests
have zero overlap with their returned answer units. Every positive threshold loses
both. Matching words in a sentence also cannot distinguish “identify the transaction
age” from supplying that incident's actual transaction age; the latter unsupported
request still receives the investigation instructions.

The pair-omission diagnostic selects on nine pairs and applies the selected
threshold to both omitted members. Whole-query aggregate counts become 9/10
expected-document answers, 6/10 evidence answers, 5/10 unsupported answers and
1/10 correct pairs. Request-clause counts remain the baseline's 10/6/6/1. The
whole-query reduction sacrifices a supported case and does not meet the retention
rule. These folds reuse validation and are not independent cross-validation.

## Verification and next work

Four new unittest methods cover deterministic segmentation, the distinction between
union and unit coverage, empty evidence, rejection of a holdout argument before
file reads, and validation integration without promoting baseline abstentions.
Locally, all 26 methods across the new suite, existing probe and span metric passed.
Hosted application/build/container/browser checks are recorded in the associated
pull request; the local experiment alone does not establish those checks.

Further lexical threshold variants should not consume the holdout merely to seek
a gain. A next candidate needs a better request/evidence relation on validation,
or a separately preregistered retrieval experiment if changing passage selection.
The existing v5 protocol keeps ranking fixed. A gate cannot repair the four baseline
wrong-passage answers. Live LLM entailment, independent annotations and real-incident
quality remain unverified.

Optional exercise: why can sentence-level overlap still accept a request for a live
value when the sentence only tells an operator how to investigate that value?
