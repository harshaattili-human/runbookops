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
The default service accepts 10/10 supported routes correctly in each split; on the
unsupported cases it accepts 5/10 routes and returns guidance for 6/10. The route's
`needs-review` flag does not by itself prevent an extractive answer.

The [protocol and failure analysis](evaluation-v1.md) link every case and hash. The
holdout is authored synthetic data and now exposed, not a fresh test set for future
tuning. Naturally occurring incidents and passage-level answerability remain gaps.

## Retrieval and answer generation

Markdown sections are indexed with title context and original line references.
Ranking is 0.65 times TF-IDF cosine similarity plus 0.35 times query-normalized
BM25 (k1=1.5, b=0.75). A passage needs two non-stopword overlaps and cosine >=0.09.
The four highest eligible chunks are returned, possibly from the same document.
This is sparse lexical retrieval; it is not neural semantic search.

Default answers extract the highest-ranked passage verbatim. Optional Ollama
synthesis uses retrieved passages and a JSON response contract. Citation IDs are
validated against retrieved IDs; this does not verify the truth or entailment of
the generated answer. Prompt injection is not solved by the prompt instruction.
Only authored local documents are indexed, and the model has no tool execution.

## Known gaps

- Synthetic English descriptions favor vocabulary represented in training.
- No public or real operational validation, calibration study, or drift monitoring.
- No live LLM quality evaluation; adapter behavior is covered with mocked responses.
- No production authentication, rate limiting, or tenant isolation.
- This demo should run locally. Public deployment needs a separate security review.
- UI keyboard focus containment and end-to-end browser tests remain on the backlog.
