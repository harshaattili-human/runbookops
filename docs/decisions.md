# Design decisions

## Keep the baseline inspectable

TF-IDF plus logistic regression trains locally on the small synthetic dataset and
exposes the terms contributing to each route. This gives the project a baseline
to compare with other models. The [first comparison](evaluation-v1.md) includes a
most-frequent-label predictor on the same folds; embedding and larger-model
comparisons have not been run.

## Separate routing from retrieval

The classifier suggests a service area. It does not restrict retrieval; an incorrect
label must not hide a relevant runbook. Retrieval combines BM25 lexical matching
with TF-IDF cosine similarity using a fixed weighted score. This favors vocabulary
overlap; paraphrases with different terminology may fail to retrieve useful evidence.

## Keep suggestions separate from execution

The application retrieves investigation steps. It never runs shell commands,
changes infrastructure, or grants access. A person reviews evidence before acting.

## Evaluate by scenario

Paraphrases of one incident scenario stay in the same fold. Text preprocessing is
fit inside each training fold. Synthetic validation remains a smoke benchmark,
not an estimate of real-world incident-triage quality.
