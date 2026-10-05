# Lexical answerability gate

The October 5, 2026 follow-up separates finding a related runbook from deciding
whether its text covers enough of the request to show guidance. The new policy
withholds a retrieved passage when the top document covers less than 0.33 of the
query's IDF-weighted terms.

This is a small lexical safeguard, not an entailment model or calibrated confidence
score. It runs locally and adds no dependency or network call.

## Protocol

The policy and threshold were selected using the exposed 20-case v1 validation set.
The threshold retained all ten supported validation answers while reducing answers
to unsupported requests from six to one. The service marks a below-threshold match
as `insufficient`, returns no source text, and does not call the optional local LLM.

The 26-case [answerability holdout](../data/evaluation/answerability-holdout-v2.json)
was then frozen in [commit 1661081](https://github.com/harshaattili-human/runbookops/commit/1661081b607ef8f7322552a7ad5c830d8bf4c5c7),
before the policy was implemented or scored against those cases. It contains 12
supported investigations, 12 near-topic requests for absent information, and two
unrelated questions. The [manifest](../data/evaluation/answerability-manifest-v2.json)
records hashes and the one-score protocol. The same author created both suites, so
this is neither a blinded nor an external evaluation.

The implementation and validation report were fixed in
[commit 947c6d5](https://github.com/harshaattili-human/runbookops/commit/947c6d5a961c1f2192e868e37a5b1a921301b5c7)
before the v2 holdout command was run. No threshold, corpus, runbook, or query was
changed after inspecting the holdout result in this increment.

For a query with distinct non-stopword terms \(Q\), top document terms \(D\), and
frequency across indexed chunks \(df(t)\), coverage is:

\[
\frac{\sum_{t \in Q \cap D} \log(1 + \frac{N-df(t)+0.5}{df(t)+0.5})}
     {\sum_{t \in Q} \log(1 + \frac{N-df(t)+0.5}{df(t)+0.5})}
\]

Terms absent from the corpus remain in the denominator. This is why a query asking
for a missing secret or commercial value tends to score lower than a supported
investigation using runbook vocabulary. It also means unrelated padding can suppress
an otherwise useful answer.

## Results

| Fixed suite and decision | Supported answers | Correct top document and answered | Unsupported answers |
| --- | ---: | ---: | ---: |
| Validation, retrieval gate only | 10 / 10 | 10 / 10 | 6 / 10 |
| Validation, coverage policy | 10 / 10 | 10 / 10 | 1 / 10 |
| Frozen v2 holdout, retrieval gate only | 12 / 12 | 11 / 12 | 11 / 14 |
| Frozen v2 holdout, coverage policy | 11 / 12 | 10 / 12 | 3 / 14 |

The holdout's two unrelated questions abstained under both decisions. Among the 12
near-topic unsupported requests, the baseline returned 11 passages and the coverage
policy returned three. These denominators are small and synthetic. The result does
not establish production safety, real-incident accuracy, or a general 73-point
improvement rate.

## Failure analysis

| Case | Coverage | Observed failure |
| --- | ---: | --- |
| `answerability-holdout-04` | 0.3565 | A supported retry/idempotency question passed the gate, but `workflow-jobs` ranked above the expected `message-retries` document. Answerability cannot repair ranking. |
| `answerability-holdout-07` | 0.3118 | A supported exhausted-retry question was withheld. Paraphrases such as “no retries left” and “downstream action” were not represented strongly enough. |
| `answerability-holdout-18` | 0.4749 | A request for guaranteed numeric heap and container limits passed because most topical memory terms appear in the runbook. |
| `answerability-holdout-19` | 0.3637 | A business refund decision passed because the workflow gateway and approval vocabulary outweighed the absent policy/customer facts. |
| `answerability-holdout-21` | 0.3522 | A request for production OAuth secrets passed because token, signing-key and validation terms are present even though the requested credentials are not. The extractive passage does not reveal a secret, but it still fails the request's answerability label. |

An earlier regression query that prepends unrelated instruction-like text to a valid
Kafka incident falls below the threshold. The text remains data and no instruction
is executed, but useful evidence is withheld. The test preserves this known behavior.

## Reproduce

The default command scores validation only:

```sh
python -m pytest -q
python -m runbookops.answerability --split validation
```

The published one-time holdout result can be reproduced explicitly:

```sh
python -m runbookops.answerability --split holdout
```

Both reports contain every case, decision, top source, coverage value, input hashes
and code hashes:

- [validation report](../reports/answerability-validation-v2.json)
- [holdout report](../reports/answerability-holdout-v2.json)

Re-running the holdout reproduces an exposed result; it does not make the data unseen.
Routine CI scores validation only.

## Next experiment

Keep the v2 failures fixed as regression examples. On validation, compare the document
coverage rule with a passage-level method that identifies the requested information
type and can distinguish investigation guidance from credentials, numerical guarantees
and business decisions. Add paraphrases with irrelevant context so useful evidence is
not lost merely because a description is verbose. Freeze another holdout before any
new improvement claim.
