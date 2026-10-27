# Model card

## Intended use

Demonstrate an inspectable incident routing and retrieval workflow to engineering
reviewers. This is an educational portfolio baseline, not a production incident
response system. It never executes remediation.

## Classifier

Word unigram/bigram TF-IDF, sublinear term frequency, English stopword removal,
and multiclass logistic regression (C=4, max_iter=1000, random_state=42).
Training at application startup uses all 90 synthetic examples across 30 scenario
groups and five service areas. Training takes place locally and requires no
downloaded model weights. Learned weights are reconstructed rather than loaded
from an untrusted pickle.

`api-security` combines authentication and API reliability for this small initial
taxonomy. Separating those categories is a planned improvement.

Routing abstains if no features match, the top score is below 0.40, the top-two
score gap is below 0.08, or retrieval finds no evidence. These are heuristic
thresholds, not calibrated risk controls. The default full-data router is distinct
from the out-of-fold models used to compute metrics.

## Evaluation

Three-fold StratifiedGroupKFold with shuffling and random_state=42. All three
paraphrases from a scenario remain together. The vectorizer and classifier are fit
only on each fold's training examples. The report records fold membership, dataset
SHA-256, per-class metrics, confusion matrix, and every misclassification.

The initial run produced macro F1 approximately 0.945. The 10 positive retrieval
smoke cases found their expected document among four retrieved chunks; four
negative smoke cases abstained. See `reports/evaluation.json` for exact results.
These numbers come from a small authored dataset and must not be marketed as real
incident accuracy. Benchmark questions are available to the developer.

The October 4 comparison adds a most-frequent-label baseline on the same grouped
folds (macro F1 approximately 0.0667) and separate 20-query validation/holdout suites.
Each new suite has ten supported requests, eight near-topic unsupported requests and
two unrelated questions. Fixed hybrid/BM25/TF-IDF rankings share the same eligibility
gate and all find the expected top document on 10/10 supported cases, but each returns
guidance on 6/10 unsupported cases. No settings were tuned on either new suite.
Before the later answerability gate, the default service accepted 10/10 supported
routes correctly in each split; on unsupported cases it accepted 5/10 routes and
returned guidance for 6/10. The route's `needs-review` flag did not by itself prevent
an extractive answer. The follow-up policy and new holdout are described below.

The [protocol and failure analysis](evaluation-v1.md) link every case and hash. The
holdout is authored synthetic data and now exposed, not a fresh test set for future
tuning. Naturally occurring incidents remain a gap.

## Retrieval and answer generation

Markdown sections are indexed with title context and original line references.
Ranking is 0.65 times TF-IDF cosine similarity plus 0.35 times query-normalized
BM25 (k1=1.5, b=0.75). A passage needs two non-stopword overlaps and cosine >=0.09.
The four highest eligible chunks are returned, possibly from the same document.
Before showing guidance, the service also requires the top document to contain at
least 0.33 of the query's IDF-weighted terms. Below that threshold it returns no
source passage and does not call the optional LLM. The threshold was selected on
the v1 validation set; it is a lexical heuristic, not calibrated confidence or
entailment. A later request-shape guard was evaluated but rejected before adoption.

On the separately frozen v2 synthetic holdout, the original retrieval gate answered
11/14 unsupported requests and all 12 supported requests. The coverage policy answered
3/14 unsupported requests and 11/12 supported requests. It answered ten supported
requests with the expected top document; one answered case selected the wrong document.
See the [protocol and failures](answerability-v2.md). This is sparse lexical retrieval,
not neural semantic search or passage entailment.

A later [passage-coverage experiment](passage-experiment.md) added a 0.27 top-chunk
threshold to the document gate. It changed validation from 1/10 to 0/10 unsupported
answers while retaining 10/10 supported answers, but on the exposed v2 regression set
it retained the same 3/14 unsupported answers and reduced supported answers from 11/12
to 9/12. The candidate was rejected and is not part of the service decision.

Default answers extract the highest-ranked passage verbatim. Optional Ollama
synthesis uses retrieved passages and a JSON response contract. Citation IDs are
validated against retrieved IDs; this does not verify the truth or entailment of
the generated answer. Prompt injection is not solved by the prompt instruction.
Only authored local documents are indexed, and the model has no tool execution.
The [provider boundary](ollama-boundary.md) requires normal completion and bounds
the JSON envelope before parsing; it does not evaluate generated-answer quality.

## Known gaps

The [v4 contrastive dataset](information-type-v4.md) freezes another 20 validation
and 20 holdout queries and covers fragmentary and statement-form requests after the
v3 runtime regression. A request-target candidate was developed on validation only.
It retained 9/10 expected-top-and-answered supported cases and changed unsupported
answers from 8/10 to 0/10; the remaining supported case was already below the 0.33
coverage gate. The single holdout comparison then preserved 10/10 expected-top-and-answered
supported cases and reduced unsupported answers from 9/10 to 5/10. Correct pairs
changed from 1/10 to 5/10; five lexical misses remain. V4 is now exposed and cannot
select further rules. The [runtime guard](request-target-guard.md) applies the unchanged candidate before
extraction/generation. Its lexical false-answer and false-refusal risks remain.
Same-author construction, visible labels and semantic overlap remain limitations.

The [v3 contrastive dataset](information-type-v3.md) adds 20 validation queries and
20 once-scored holdout queries, ten supported/unsupported pairs per split. Each pair
shares one incident context; all use the same ten synthetic runbooks. Source quotes
and hashes are checked, but annotations are author-visible and not independently
validated. The initial freeze ran no v3 inference. Candidate development used
validation only, and its code/configuration/report were published before the single
holdout score; v3 is now exposed.

A later validation-only request-shape experiment now uses the final query sentence
to detect demands for external values, approvals, sensitive values or unwritten
artifacts. On 10 supported/10 unsupported v3 validation queries, it retained 9/10
expected-top supported answers and reduced unsupported answers from 8/10 to 0/10.
On the once-scored holdout it retained the baseline's 8/10 expected-top supported
answers and reduced unsupported answers from 6/10 to 1/10. Existing application tests
then showed that the word “maximum” in a descriptive incident falsely triggered the
guard, bypassing optional generation. The candidate was rejected without changing its
rules; the remaining pool-size miss and two coverage-withheld positives are also
preserved. These authored grammar patterns are not semantic entailment or a trained
information-type model; see [the protocol and per-case reports](information-type-v3.md).

- Synthetic English descriptions favor vocabulary represented in training.
- No public or real operational validation, calibration study, or drift monitoring.
- No live LLM quality evaluation; adapter behavior is covered with controlled HTTP
  responses and instrumented streams.
- No production authentication, rate limiting, or tenant isolation.
- This demo should run locally. Public deployment needs a separate security review.
- Component interaction tests cover source-dialog focus containment, Escape, focus
  restoration, fetch errors, keyboard navigation and the empty state.
  [Browser checks](browser-checks.md) also cover three viewport sizes and live source
  inspection. Physical-device and assistive-technology verification remain pending.
- The coverage gate can suppress useful evidence when a query contains irrelevant
  terms, and can pass absent values or secrets when topical overlap is strong.
