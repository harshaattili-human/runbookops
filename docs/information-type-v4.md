# Contrastive answerability dataset: v4

## Freeze history and current status

Frozen on October 26, 2026 with integrity checks only. The candidate was published
and validated on October 27 before the single joint holdout score later that day.
**V4 holdout is now exposed.** Runtime behavior was unchanged at the score checkpoint. The subsequent
[service integration](request-target-guard.md) applies the same candidate; candidate
and ranking files retain their published hashes.

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

## Fixed validation candidate

The first v4 candidate is a **request-target guard** layered after the existing 0.33
document-coverage gate. It inspects only the final sentence or fragment and applies
five ordered lexical signals: approval or action, an unwritten command or procedure,
a directly requested sensitive value, current/live state, and literal configuration.
It does not read labels, IDs, runbook names or retrieved text. In particular,
`Active connections are at the maximum and pending requests keep rising.` has no
signal; a numeric statement such as `Pool maximum: 80 connections on each replica.`
does. This preserves the ordinary incident form that invalidated the v3 runtime
candidate while addressing the statement and fragment forms introduced in v4.

```sh
PYTHONPATH=backend python -m runbookops.information_answerability_v4
```

The evaluator has no split argument or holdout scoring path. The shared integrity
validator still reads both public splits to verify their hashes, labels and separation;
only v4 validation is sent to retrieval and the candidate. It writes
[the validation report](../reports/information-validation-v4.json). On the ten
supported and ten unsupported validation queries:

| Decision | Existing coverage gate | Request-target candidate |
| --- | ---: | ---: |
| Supported answered | 9/10 | 9/10 |
| Expected-top and answered supported | 9/10 | 9/10 |
| Unsupported answered | 8/10 | 0/10 |
| Fully correct pairs | 1/10 | 9/10 |

The one incomplete pair is the supported API-timeout request. The fixed ranking finds
`api-timeouts` first, but document coverage is 0.2756, below the unchanged 0.33 gate;
the candidate cannot recover an answer already withheld by the baseline. All ten
unsupported validation requests are withheld: two each for configuration values,
live state, approval, sensitive values and unwritten procedures.

These validation results are development evidence on visible, same-author synthetic
data. The rules can encode its grammar, reject answerable literal requests or miss
unseen phrasing. Request shape does not establish passage entailment. At candidate publication the service was unchanged and holdout was unscored. The
subsequent comparison below used those exact candidate and ranking bytes.

## Freeze verification

Implementation [run 40331717832](https://github.com/harshaattili-human/runbookops/actions/runs/40331717832)
passed all five jobs on October 26, 2026. Verify ran 187 Python cases plus 11
subtests, including the three new v4 contract cases, and reported zero scored queries.
It also passed seven component cases and the production frontend build. The existing
v3 validation candidate was reproduced; no v3 holdout or v4 query was scored.

The unchanged browser suite passed 27 live and 18 recorded-replay executions across
Chromium, Firefox and WebKit. The container checks passed packaged and mounted-corpus
workflows; its dated audit inventoried 24 Python package names and 164 finding entries,
with zero fixable high/critical entries. The Spring client passed nine Java cases and
its live walkthrough; 26 packaged libraries had zero advisory entries in that scan.
The npm audit job passed. These snapshots do not establish vulnerability freedom,
and the unchanged browser/container checks add no v4 quality evidence.

Local Python 3.12 ran all 17 stdlib v3/v4 dataset cases, both-split integrity,
bytecode compilation, JSON parsing, documentation links and whitespace checks.
Full application dependencies were unavailable locally, so application, browser,
Java and container execution evidence is hosted.

## Candidate verification — October 27, 2026

Candidate commit `edcada1089c663aa7466109aa01f4114b43d7a83` was published before
any v4 holdout inference. [Run 40515935642](https://github.com/harshaattili-human/runbookops/actions/runs/40515935642)
then passed all five jobs. Verify ran 202 Python cases plus 11 subtests, including the
15 new request-target executions, and reproduced the validation metrics above. The
integrity command again reported zero scored queries. Seven frontend component cases
and the production build passed.

The unchanged browser suite passed 27 live and 18 recorded-replay executions across
Chromium 151.0.7922.34, Firefox 153.0 and WebKit 26.5. The Spring client passed nine
Java cases and its live executable walkthrough; its audit inventoried 26 packaged
libraries with zero advisory entries in that scan. Packaged and mounted-corpus
container checks passed. The runtime-image audit inventoried 24 Python package names
and 164 finding entries with zero fixable high/critical entries. The npm audit job
also passed. These dated known-advisory scans do not establish vulnerability freedom,
and the unchanged browser, Java and container checks add no answerability-quality
evidence.

Local Python 3.12 ran the 17 stdlib dataset cases, generated and checked the 20-case
validation report, compiled the changed Python files, and passed JSON, documentation
link and whitespace checks. Full pytest/application execution used hosted Python
3.12.15 because pytest and HTTPX2 were unavailable locally.

Optional interview exercise: why can a declarative fragment request unavailable
information, and why should new data cover forms the previous candidate assumed away
without copying its observed failures into holdout?

## Single holdout comparison — October 27, 2026

[The complete report](../reports/information-holdout-v4.json) records one joint
comparison using candidate commit `edcada1089c663aa7466109aa01f4114b43d7a83`.
The separate evaluator checks SHA-256 pins for the unchanged candidate and retriever
before loading holdout. CI continues to score validation only; its two new evaluator
contract tests reject missing opt-in and modified code without loading holdout.

| Decision | Coverage baseline | Fixed request-target candidate |
| --- | ---: | ---: |
| Supported answered | 10/10 | 10/10 |
| Expected-top and answered supported | 10/10 | 10/10 |
| Unsupported answered | 9/10 | 5/10 |
| Fully correct pairs | 1/10 | 5/10 |

Unsupported answers by type changed as follows: approval 1/2 to 0/2,
configuration 3/3 to 2/3, live state 2/2 to 1/2, sensitive value 2/2 to 1/2,
and unwritten procedure 1/1 to 1/1. These are ten paired contexts with twenty
queries, not twenty independent incidents. The numeric adoption criterion is met;
application integration is covered separately in the [runtime record](request-target-guard.md).

All five remaining unsupported cases are preserved: yesterday's recovery metrics
(coverage 0.5476), a 6 GiB heap/8 GiB container statement (0.4829), a 30-second/twelve
attempt retry instruction (0.5395), a private process-variable payload (0.5031), and
an executable migration script (0.4690). The unchanged lexical signals miss these
forms. No rule, threshold, corpus, label or ranking was changed after observing them.
This smaller holdout gain than validation is evidence of grammar sensitivity, not a
reason to tune on the exposed cases.

First score environment: Python 3.12.14, scikit-learn 1.8.0, NumPy 2.3.5,
Linux x86_64/glibc 2.39. The report records platform, UTC time, full cases, source/data
hashes, evaluator hash and published candidate commit. To reproduce as an **exposed
regression**, choose a new output so the first receipt is never overwritten:

```sh
PYTHONPATH=backend python -m runbookops.information_holdout_v4 --allow-holdout \
  --output /tmp/information-holdout-v4-reproduction.json
```

The earlier validation report's unscored wording describes its publication time.
The integrity command still prints zero scored queries because that command performs
no inference; it does not mean no other command has ever evaluated this dataset.
The result does not establish production accuracy, entailment, independent annotation
or live-LLM quality. Future model selection requires another frozen holdout.
