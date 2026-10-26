# Contrastive answerability dataset: v4

## Frozen, unscored status

Frozen on October 26, 2026. This increment adds data, manifest coverage, integrity
checks and a guarded loader. It runs **no retrieval, answerability decision, LLM call
or holdout score** and makes no quality-improvement claim. Production routing,
retrieval, the 0.33 coverage gate, corpus and API behavior are unchanged.

The exposed v3 experiment missed an ordinary form: a descriptive incident containing
“maximum” was treated as a request for a specific value. V4 adds fragments,
declarative requests and incident descriptions without assuming every request is a
final-sentence question. Each pair still contrasts documented guidance with an absent
live value, configuration, approval, sensitive value or unwritten procedure.

## Data and provenance

[Validation](../data/evaluation/information-validation-v4.json) and
[holdout](../data/evaluation/information-holdout-v4.json) each contain ten pairs, one
per runbook: ten supported and ten near-topic unsupported requests. Across both splits
that is **40 queries in 20 paired contexts**, not 40 independent incidents.

| Missing information | Validation | Holdout |
| --- | ---: | ---: |
| Configuration value | 2 | 3 |
| Live state | 2 | 2 |
| Approval | 2 | 2 |
| Sensitive value | 2 | 2 |
| Unwritten procedure | 2 | 1 |
| Total | 10 | 10 |

These are AI-assisted synthetic annotations by the project author, created after
v1-v3 results were visible. No employer material or real incident data is used. IDs,
scenarios and normalized full queries are disjoint from the pinned earlier data. The
checker understands earlier pair files when enforcing that rule. This does not prove
semantic independence, external review, blinding, label correctness or real-world
representativeness; V4 revisits the same ten topics and failure classes.

Every positive identifies a verbatim one-based source span. Every negative names the
missing information. Quote alignment proves source integrity, not semantic entailment.
Labels are public and author-visible. Disputes must be recorded; once results exist,
they must not be silently edited and rehashed.

## Executable freeze

[The manifest](../data/evaluation/information-manifest-v4.json) pins raw-byte SHA-256
for both v4 splits, both v3 splits, five earlier data files and all ten runbooks. Its
baseline is main commit `2a831e36a1d18858d6c489c578df2368a7ae46cc`.

```sh
PYTHONPATH=backend python -m runbookops.information_dataset
PYTHONPATH=backend python -m unittest \
  tests.test_information_dataset tests.test_information_dataset_v4 -v
```

The command checks v3 and v4 and reports `scored_queries: 0`. It imports no service,
retriever, scikit-learn or HTTP transport and writes no result file. V4 validation is
available through `load_cases(..., version="v4")`. Holdout loading also requires
`split="holdout", allow_holdout=True`; this is an accidental-use guard, not access
control over public JSON.

## Preregistered next comparison

1. Develop using v4 validation only. V1-v3 holdouts and v3 runtime failures are exposed
   regression evidence, not tuning data. A learned model needs separate training data.
2. Keep ranking and corpus fixed. Publish candidate code, configuration, evaluator,
   validation per-case results and environment before v4 holdout inference.
3. Run the current coverage baseline and one frozen candidate on holdout together once.
   Preserve per-case query, label, top document, score, decision and failure.
4. Report supported answered /10, expected-top-and-answered /10, unsupported answered
   /10, type denominators above and fully correct pairs /10. Adoption requires fewer
   unsupported answers with no loss of expected-top-and-answered supported cases and
   a passing application suite.
5. Then mark v4 exposed. Do not repair a candidate from holdout failures; another
   improvement claim needs a new freeze.

Even a passing comparison would be a small paired synthetic result, not production
accuracy, calibration, live-LLM quality, safety or proof of entailment.

Optional interview exercise: why can a declarative fragment request unavailable
information, and why should new data cover forms the previous candidate assumed away
without copying its observed failures into holdout?
