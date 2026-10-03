# Design decisions

## Keep the baseline inspectable

Use TF-IDF plus logistic regression for incident routing. A small synthetic dataset
does not justify fine-tuning a large model. Inspectable feature contributions and
honest error analysis are more useful here than an expensive black box.

## Separate routing from retrieval

The classifier suggests a service area. It does not restrict retrieval; an incorrect
label must not hide a relevant runbook. Retrieval combines BM25 lexical matching
with TF-IDF cosine similarity using a fixed weighted score. These are sparse text
retrieval methods, not neural embeddings or a vector database.

## Keep suggestions separate from execution

The application retrieves investigation steps. It never runs shell commands,
changes infrastructure, or grants access. A person reviews evidence before acting.

## Evaluate by scenario

Paraphrases of one incident scenario stay in the same fold. Text preprocessing is
fit inside each training fold. Synthetic validation remains a smoke benchmark,
not an estimate of real-world incident-triage quality.
