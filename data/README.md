# Data provenance

Every runbook and incident in this directory was authored for this independent
portfolio project with AI assistance. Service names are fictional. No employer
documents, customer records, tokens, or production logs were used.

`incidents.json` contains scenario groups with three paraphrases each. Keep a
scenario's paraphrases together during evaluation. The dataset is deliberately
small and educational; it is not suitable for operational deployment.

`evaluation/retrieval.json` is a hand-authored smoke set. Positive questions have
an expected document. Negative questions expect abstention. It is not an unseen
external benchmark; do not describe its metrics as production accuracy.

`evaluation/validation-v1.json` and `evaluation/holdout-v1.json` each contain 20
additional synthetic queries: 10 supported, eight near-topic unsupported requests,
and two unrelated questions. Every label has a rationale. Supported labels identify
an applicable runbook and service area; unsupported labels mean the requested
procedure, fact or value is absent, even if a passage shares its vocabulary.
A false match under this rubric does not mean the quoted passage itself is false.

These files and the original training data/corpus are frozen by SHA-256 in
`evaluation/manifest-v1.json` before scoring. The authored scenarios and query texts
are disjoint across the new splits; both query the same ten runbooks. The same author
can see both sets, so this is an untuned synthetic holdout, not a blinded external
assessment. The existing classifier settings, retrieval gate, and hybrid weights
are fixed for this experiment. Once results are inspected, the holdout is exposed:
use it for reproducibility, not repeated model selection or fresh generalization claims.

The planned comparisons are a most-frequent-class predictor on the classifier's
existing folds, and hybrid/BM25/TF-IDF ranking under the same retrieval eligibility
gate. Holding the gate fixed isolates ordering; it does not compare independently
tuned abstention policies. Report per-case failures and denominators, along with
the current service's supported-query routing coverage and unsupported-query answer
rate. No live LLM is used.

`evaluation/answerability-holdout-v2.json` adds 26 cases for a later answerability
check: 12 supported investigations, 12 near-topic requests whose target information
is absent, and two unrelated questions. It was authored after the v1 failure analysis
but frozen before scoring an answerability policy. It remains synthetic, visible to
the same author, and is not an external benchmark. Its first score should be reported
once and preserved; subsequent changes require another holdout for fresh claims.

Runbook text is illustrative investigation guidance, not vendor documentation.
Verify real systems against current vendor documentation and local procedures.
