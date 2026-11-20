# Passage coverage on v5 validation

The pinned baseline returns the expected document for all ten supported validation
requests, but covers the annotated evidence for only six. This probe asks whether
lexical coverage of the actual extract can reject unsupported requests without
losing either supported metric. It changes no runtime behavior, corpus or ranking.

## Reproduce

```sh
PYTHONPATH=backend python -m unittest discover -s tests -p 'test_passage_probe.py'
PYTHONPATH=backend python -m runbookops.passage_probe --output /tmp/passage-probe.json
```

Use a new output filename; existing receipts are never overwritten. The runner
verifies the exact [baseline receipt](../reports/passage-validation-v5-baseline.json),
its runtime/training/evaluator hashes, frozen dataset/corpus hashes, annotation
alignment and returned passage bytes. It reads only validation responses for
scoring; integrity checks may read public holdout labels but perform no inference.
There is no holdout option, service call, model fitting or provider call.

Both variants use the existing retriever's tokenization and corpus IDF weights.
One scores the complete query against the extracted answer body; the other uses
only the existing v4 parser's final sentence/fragment. The passage heading is
excluded because it is not in the displayed extract. Baseline abstentions stay
abstained. An answered response survives when coverage is at least the threshold.
No passage is substituted, reordered or expanded.

The sweep enumerates every distinct decision boundary: zero and the next
representable float above each observed coverage. It therefore includes equality
retention and reject-all without hiding narrow feasible intervals in a coarse grid.
Selection minimizes unsupported answers subject to no loss of expected-top-and-
answered or evidence-supported-and-answered counts; ties choose the lowest threshold.
All thresholds and per-case scores remain in the [receipt](../reports/passage-coverage-probe-v5.json).
This is validation selection, not an independent evaluation of the selected threshold.

## Observed November 18, 2026

Ten AI-assisted, same-author synthetic pairs (20 queries), reused topic families,
visible labels, extractive path only. Baseline responses were captured November 16;
this is offline post-processing, not new inference. Local Python 3.12.14,
NumPy 2.3.5, scikit-learn 1.8.0, Linux x86_64/glibc 2.41. The receipt records the
exact baseline/probe hashes and environment. No holdout queries were scored.

| Policy | Supported answered | Expected document + answered | Evidence span + answered | Unsupported answered | Fully correct pairs |
| --- | --- | --- | --- | --- | --- |
| Current runtime baseline | 10/10 | 10/10 | 6/10 | 6/10 | 1/10 |
| Best preserving whole-query coverage | 10/10 | 10/10 | 6/10 | 5/10 | 2/10 |
| Best preserving final-clause coverage | 10/10 | 10/10 | 6/10 | 6/10 | 1/10 |

There are 18 whole-query and 16 clause decision boundaries, not 34 independent
experiments. Whole-query selection chooses approximately 0.171918 (exact float in
receipt). It rejects the unsupported offset-movement command request; five other
unsupported answers remain. Final-clause selection can preserve all supported
answers only at zero: the pod-startup and workflow-jobs supported requests have
zero clause overlap with their returned passage. Those are also wrong-passage
baseline answers, but removing them would still violate the separate
expected-document retention criterion. Higher thresholds cannot repair the passage.

The clause variant is rejected on validation. The small whole-query selection gain
is retained as exploratory evidence, not promoted to runtime or a holdout comparison.
Its boundary sits immediately above an observed negative score and can be sensitive
to wording or floating-point differences. A deployment threshold needs an explicitly
fixed configuration and runtime regression evidence before the protocol's one joint
holdout score. This increment deliberately leaves that score unused.

Coverage cannot establish entailment; final-sentence extraction can misidentify
multi-part requests. No real-incident accuracy, model-quality improvement or
production deployment is claimed. The original v5 annotations and all prior
receipts remain unchanged.

Optional exercise: why can a threshold reduce false answers yet remain unable to
repair a correct-document/wrong-passage answer? Which metric would hide that loss?

## Deterministic offline reduction — November 20, 2026

The original probe delegated coverage to the pinned runtime method, which sums
weights in set iteration order. Four fresh processes with `PYTHONHASHSEED` 1–4
reproduced different last-bit score values: compared with seed 1, seeds 2, 3 and 4
changed 11, 10 and 11 of the 20 case score objects respectively. Their selected
thresholds and metric counts agreed in this run. This is numerical variation,
not four independent quality experiments.

The offline probe now sorts unique query terms and uses `math.fsum` for numerator
and denominator. It preserves the pinned runtime tokenization and IDF formula,
without changing runtime retrieval, ranking, the baseline receipt or corpus. It
neither rounds scores nor merges nearby thresholds. The report identifies this
reduction explicitly. The historical November 18 receipt above remains unchanged;
regenerated receipts use the new probe hash and may differ in last bits.

Eight focused unit methods passed locally on Python 3.12.14 / NumPy 2.3.5 /
scikit-learn 1.8.0. The new subprocess regression compares all case scores and
complete threshold sweeps exactly across four hash seeds; timestamps and environment
metadata are excluded from equality. A separate check covers empty, full, absent
and partial overlap, repeated terms and reordered query terms. This guarantees
neither cross-platform/libm equality nor byte-identical timestamped receipts.
No holdout inference or candidate promotion was performed.
