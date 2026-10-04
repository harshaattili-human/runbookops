# Baselines and unsupported queries

The October 4, 2026 experiment found a gap hidden by the original smoke checks:
RunbookOps returned a passage for six of ten unsupported requests in each new query
split. The service still uses the existing thresholds and hybrid weights. This
increment measures the failure; it does not claim to fix answerability.

## Protocol

The [query files and manifest](../data/evaluation/manifest-v1.json) were frozen in
[commit 58b624b](https://github.com/harshaattili-human/runbookops/commit/58b624bf4c04e9f715bd35c6796a2db6b8bd2d16)
before scoring. Each split has ten supported requests, eight near-topic unsupported
requests and two unrelated questions. Labels include a rationale. An unsupported
label means the requested procedure, fact or value is absent from these runbooks;
topical word overlap alone does not satisfy it.

Both splits were authored with AI assistance for the same ten-runbook corpus. IDs,
authored scenario IDs and normalized query texts are disjoint, including checks
against training text and the original smoke questions. These checks do not prove
semantic independence. This is a synthetic holdout withheld from parameter selection,
not a blinded or external benchmark. After this first inspection it is exposed
regression data; later tuning needs a new evaluation set for fresh claims.

The classifier comparison uses the existing 90 descriptions, 30 scenario groups,
and three grouped folds. A `DummyClassifier(strategy='most_frequent')` is fitted on
each fold's training labels and evaluated on exactly the same test rows as logistic
regression. The query suites are not used for fitting either classifier.

Retrieval comparisons change only the ranking score: the existing hybrid, BM25, or
TF-IDF cosine. All use the same sections, a four-chunk limit, at least two overlapping
terms and cosine >= 0.09. The BM25 variant therefore still uses a cosine eligibility
gate. This is a ranking ablation, not a comparison of separately tuned retrievers.
Equal negative acceptance across rankers follows from that shared gate.

## Observed results

| Classifier on the same grouped folds | Macro F1 | Evaluated descriptions |
| --- | --- | --- |
| TF-IDF + logistic regression | 0.9450 | 90 |
| Most-frequent training label | 0.0667 | 90 |

These are forced-label classifier scores. They do not evaluate routing abstention,
answer quality, or performance on real incidents. Fold membership, dummy predictions,
confusion matrices and classifier errors are in [evaluation.json](../reports/evaluation.json).

| Fixed ranking | Validation top document correct | Holdout top document correct | Validation unsupported false matches | Holdout unsupported false matches |
| --- | --- | --- | --- | --- |
| Hybrid | 10 / 10 | 10 / 10 | 6 / 10 | 6 / 10 |
| BM25 with shared gate | 10 / 10 | 10 / 10 | 6 / 10 | 6 / 10 |
| TF-IDF with shared gate | 10 / 10 | 10 / 10 | 6 / 10 | 6 / 10 |

The expected document also appeared within the four returned chunks on every
supported case. Mean reciprocal document rank was 1.0 for each variant and split.
These easy positive cases do not establish a benefit from hybrid ranking. More
ambiguous supported cases are needed before choosing a ranker on quality grounds.

All six false matches in each split came from the eight near-topic requests; the
two unrelated questions in each split returned no passage. False match here means
guidance was returned for a request whose target answer was absent. It does not
mean the source quote was fabricated, nor does a document hit prove that the selected
passage answers the full question.

The default extractive service accepted all ten supported routes in each split and
all ten matched their category and top document labels. On unsupported requests it
returned guidance in six of ten cases but accepted only five of ten routes. The
remaining false match displayed `needs-review` while still returning a source quote.
Routing abstention alone therefore does not suppress unsupported guidance.

## Examples to investigate

| Case | Requested information | Returned top document | Why the label is unsupported |
| --- | --- | --- | --- |
| `validation-13` | Redis eviction policy | Container memory pressure | JVM/container investigation does not describe Redis eviction |
| `validation-15` | Kafka invoice cost per partition | Kafka consumer lag | No billing data or pricing rules exist in the corpus |
| `holdout-13` | Exact backup identifier and restore command | Database connection pool | No backup inventory or restore procedure is available |
| `holdout-18` | Private tenant's exact JWT issuer URL | API token validation | The runbook describes an issuer check, not that tenant's value |

Every query, label rationale, returned document/source ID and service routing outcome
is retained in the [validation report](../reports/retrieval-validation-v1.json) and
[holdout report](../reports/retrieval-holdout-v1.json). Each report records input and
code hashes plus Python, NumPy and scikit-learn versions. The local run used Python
3.12.14, NumPy 2.3.5 and scikit-learn 1.8.0. No LLM was called.

Implementation commit `fd8b657` passed [hosted CI run 37237761878](https://github.com/harshaattili-human/runbookops/actions/runs/37237761878):
21 Python tests, the grouped classifier evaluation, the validation benchmark and
the frontend production build. The Python tests retain one Starlette/httpx
deprecation warning. The holdout report was generated locally after the implementation
was fixed; that CI run did not score holdout queries. No browser or container checks
were added in this increment.

## Reproduce

From the installed checkout:

```sh
python -m pytest -q
python -m runbookops.evaluate
python -m runbookops.benchmark --split validation
```

Routine CI runs validation only. To reproduce the already-published holdout result:

```sh
python -m runbookops.benchmark --split holdout
```

The commands rewrite their corresponding checked-in JSON report. Input hash changes
or duplicate cases stop evaluation. Reproducing a published holdout does not make
it unseen again. Unit tests validate metric denominators, train-only dummy fitting,
split integrity, source lines and that the default benchmark never scores holdout
queries. Model-quality failures are recorded rather than converted into unit-test
thresholds that encourage tuning for a green build.

## Next experiment

Use validation to study when a passage is useful partial guidance versus when the
question needs an unavailable fact, procedure or value. Compare an explicit
insufficient-evidence response with the current extractive path, including its effect
on supported-query coverage. Do not add a list of special-case query strings to make
these cases pass. Freeze a new, more diverse holdout before measuring an improvement.

References: [scikit-learn dummy baseline](https://scikit-learn.org/1.8/modules/generated/sklearn.dummy.DummyClassifier.html)
and [avoiding test-set leakage](https://scikit-learn.org/1.8/common_pitfalls.html).
