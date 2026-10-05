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

## Require document coverage before showing guidance

Retrieval ranking answers “which passage is most related,” not “does it contain the
requested fact or procedure.” The service therefore requires the top document to
cover at least 0.33 of the query's IDF-weighted terms before returning its passage.
The threshold was selected on validation before the v2 holdout was scored. The
[experiment](answerability-v2.md) records both fewer unsupported answers and the
supported case it suppresses. This lexical check does not establish entailment.

## Keep suggestions separate from execution

The application retrieves investigation steps. It never runs shell commands,
changes infrastructure, or grants access. A person reviews evidence before acting.

## Evaluate by scenario

Paraphrases of one incident scenario stay in the same fold. Text preprocessing is
fit inside each training fold. Synthetic validation remains a smoke benchmark,
not an estimate of real-world incident-triage quality.
