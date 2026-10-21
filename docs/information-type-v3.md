# Contrastive answerability dataset: v3

## Status and purpose

Frozen on October 20, 2026. The **holdout was first scored on October 21 and is now exposed**. The freeze increment added data, an integrity
checker and a guarded case loader without running inference. A later validation-only
increment added the experimental request-shape candidate described below; production
retrieval, the 0.33 coverage gate, classifier and corpus remain unchanged. Neither
freeze made no improvement claim. The rejected
[passage gate](passage-experiment.md) remains outside the service.

The unresolved problem is a request that shares incident vocabulary with a runbook
but asks for information the runbook does not supply. Each v3 pair holds the incident
context fixed and changes the request: documented investigation guidance versus an
absent value, live observation, approval, sensitive value or unwritten procedure.
This makes “retrieve the right topic” insufficient to pass the pair. Supported
questions also discuss values, credentials and approval processes; rejecting those
words wholesale is not the intended policy.

## Data and labels

The [validation file](../data/evaluation/information-validation-v3.json) and
[holdout file](../data/evaluation/information-holdout-v3.json) each contain ten pairs:
one per existing runbook, ten supported and ten near-topic unsupported requests.
That is **40 queries in 20 pairs across both splits**, not 40 independent scenarios.
There are no unrelated questions in v3; the earlier exposed suites retain those checks.
Two holdout contexts include irrelevant incident-adjacent detail, not a systematic
robustness or prompt-injection benchmark.

| Missing information | Validation unsupported | Holdout unsupported |
| --- | ---: | ---: |
| Configuration value | 3 | 3 |
| Live state | 3 | 2 |
| Approval | 2 | 3 |
| Sensitive value | 1 | 1 |
| Unwritten procedure | 1 | 1 |
| Total | 10 | 10 |

The existing project [provenance statement](../data/README.md) applies. These are
AI-assisted synthetic annotations by the same author who can see both splits,
written after earlier failure analysis. Exact IDs, scenario names and normalized
queries are disjoint from training, smoke, v1 and v2 inputs. This does **not** establish
semantic independence, blinding, external review or real-incident generalization.

The query is exactly `context + " " + request`; IDs, labels, evidence and absence
rationales are evaluator metadata, never candidate inputs. A supported label means
the cited runbook lines provide the requested guidance. Every positive includes a
verbatim quote and one-based line span. A negative identifies the requested information
that is absent from the corpus. An otherwise accurate extract on that topic still
counts as an unsupported answer; this label alone does not establish hallucination,
secret disclosure, an unsafe action or false source text.

Annotations were checked against the source text. Automated quote matching proves
alignment, not semantic entailment or correctness of the label. Disputed labels must
be reported, not silently edited after results are visible.

## Freeze and executable contract

[The manifest](../data/evaluation/information-manifest-v3.json) pins raw-byte SHA-256
for both new splits, all ten runbooks and five historical data files. It identifies
baseline commit `deaf323c0419670b5e8f923a47f0cc84e0e1bf26`. Historical manifests and
reports are untouched. The freeze commit is the first published commit containing
this manifest: `00caeec3756875a6aa0867fb99d2bf6b7d81f024`.

```sh
PYTHONPATH=backend python -m runbookops.information_dataset
PYTHONPATH=backend python -m unittest discover -s tests -p test_information_dataset.py -v
```

The stdlib-only [checker](../backend/runbookops/information_dataset.py) rejects changed
input hashes/inventory, duplicate JSON keys, malformed records, overlapping identifiers
or normalized queries, invalid or mismatched evidence spans, absent rationales and
missing topic pairs. It imports no model, retriever or HTTP client, writes no results
and reports `scored_queries: 0`. Routine CI may read both splits for **integrity only**.

`load_cases()` defaults to validation. Loading holdout cases requires both
`split="holdout"` and `allow_holdout=True`, checked before reading the data. This is
an accidental-use guard, not access control: the JSON remains public and author-visible.
The tests load cases to verify shape and isolation, but never pass a v3 query to the
retriever or service. There is no automatic manifest-rewrite command. A changed corpus
or semantic label requires a separately versioned experiment, not rehashing this freeze.

## Preregistered next comparison

1. Develop a candidate using validation only (v1 and v3 may be used). Do not tune on
   the exposed v1/v2 holdouts or v3 holdout. If fitting a learned answerability model,
   author a separate training split first; these validation examples are not its
   training set. Keep preprocessing fit away from held-out data; see scikit-learn's
   [data-leakage guidance](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage).
2. Compare against the current production hybrid retrieval and 0.33 document-coverage
   baseline, with the frozen corpus and extractive responses, no live LLM. Keep ranking
   fixed to isolate the answerability decision. Publish candidate code/configuration,
   validation per-case results and the evaluator before scoring the holdout. Record
   code/input hashes, environment and reproducible commands. Do not select thresholds,
   words, type rules or features using holdout failures.
3. Run baseline and the single frozen candidate on the holdout together once. Preserve
   every query, label, top document, score/decision and failure. Report supported
   answered /10, expected-top-document **and** answered /10, unsupported answered /10,
   unsupported answers by the type denominators above, and fully correct pairs /10.
   A fully correct pair answers the positive with its expected top document and
   abstains on the negative. Keep ranking errors separate from withholding errors.
4. The candidate is eligible for adoption only if unsupported answers decrease with
   **no loss** in expected-top-document-and-answered supported cases versus baseline.
   Otherwise retain the negative result and do not retune on this holdout. Passing
   this small authored comparison would still not establish production accuracy or
   answer entailment. Treat pairs as grouped observations, not independent queries.
5. After the first score, label v3 holdout exposed and use it only for reproduction
   or regression. Further model selection or fresh improvement claims need another
   frozen holdout. Keep the original data/manifest; record the exposure in the report
   and this document rather than overwriting historical provenance.

## Validation candidate

The first candidate is a narrow **request-shape guard** layered after the current
0.33 document-coverage gate. It examines only the final sentence of the submitted
query. Guidance forms such as “what should …” take precedence. Otherwise it withholds
answers for four inspectable forms: approval/decision commands; direct requests for
sensitive values; direct requests for scripts, commands or procedures; and requests
marked as live or specific results (for example, exact/current/configured values).
It uses no case ID, runbook name, expected label or retrieved passage. The rules and
ordered precedence are serialized in the validation report.

On v3 validation, the current coverage baseline answered 9/10 supported requests
with the expected top document and 8/10 unsupported requests. The candidate retained
the same 9/10 supported expected-top-and-answered count, answered 0/10 unsupported
requests and completed 9/10 pairs correctly versus 1/10 for baseline. The one
supported failure was a Kafka partition-rate investigation withheld by the existing
coverage gate at 0.3012; the candidate cannot recover an answer that never reaches it.
See [all cases and denominators](../reports/information-validation-v3.json).

This clean separation was development evidence on 20 authored validation queries,
not by itself an improvement claim. The rules can reflect the author's request grammar and
may fail on multi-question, fragmentary or differently phrased incidents. They do
not prove source entailment. Its code, configuration, evaluator and validation report
were published before holdout scoring; no pattern changed in response to that score.

## First holdout score and adoption

Candidate commit `2ee4780f5aaf17f16d74e6f2b447e95a3a4104fb` published the rules,
evaluator and complete validation report before any holdout inference. After its five
hosted jobs passed (with the separately corrected Vite advisory in descendant commit
`1e2bdf4af89b2b6cc0c29fb57d5762d279bb5232`), the baseline and unchanged candidate
were run together once:

```sh
PYTHONPATH=backend python -m runbookops.information_answerability \
  --split holdout --allow-holdout
```

| Holdout metric | Coverage baseline | Request-shape candidate |
| --- | ---: | ---: |
| Supported answered | 8/10 | 8/10 |
| Expected top document and answered | 8/10 | 8/10 |
| Unsupported answered | 6/10 | 1/10 |
| Fully correct pairs | 2/10 | 7/10 |

The candidate met the preregistered rule: unsupported answers decreased with no loss
in expected-top-and-answered supported cases. It was therefore adopted unchanged
after the score. The service now applies it after document coverage, exposes the
matched request shape in `answerability.request_signal`, withholds sources and optional
generation when signaled, and asks for verified evidence or an authorized decision.
The workbench displays that reason.

All failures remain in the [holdout report](../reports/information-holdout-v3.json).
API-timeout and database-lock supported requests were already withheld by coverage
at 0.3006 and 0.2698. The request-shape guard cannot recover them. The unsupported
database-pool request still passed: “What maximum pool size should each of the four
replicas use?” received guidance precedence and 0.5351 coverage. This is a concrete
counterexample to interpreting request shape as entailment. No pattern, threshold,
label or corpus was changed after observing it.

The 20 holdout queries are ten paired, same-author synthetic contexts—not 20
independent incidents. The result is no live-LLM, production, safety, calibration or
real-incident evidence. Future candidate selection requires a new frozen holdout;
v3 may now be used only for reproduction and regression.

## Verification

Freeze commit `00caeec` passed [run 39431909665](https://github.com/harshaattili-human/runbookops/actions/runs/39431909665)
on October 20, 2026. All five jobs succeeded:

- Verify: 154 Python cases (14 new dataset-contract cases), integrity-only v3 check,
  existing classifier/validation evaluations, seven component cases and production build.
- Browser: 27 live and 18 recorded-replay executions across Chromium, Firefox and
  WebKit at three widths; these remain three live and two replay workflows, not
  45 distinct workflows. No UI code changed or new visual-inspection claim is made.
- Spring client: nine Java cases, executable walkthrough against live FastAPI,
  four audit-checker fixtures and the packaged-library audit.
- Container: packaged HTTP, non-root/read-only runtime, health, shutdown and restart;
  the image audit retained 166 advisory entries, zero fixable high/critical entries.
- Dependencies: frontend lockfile audit. The Java scan inventoried 26 libraries
  and returned zero advisory entries in that snapshot; neither audit proves security.

Hosted versions were Python 3.12.15, Node 24.21.0 and Java 17.0.20.1 on Ubuntu 24.04.
Local Python 3.12.14 passed all 14 stdlib contract cases, integrity, documentation-link
and whitespace checks; pytest/application dependencies were unavailable locally.
The existing Starlette/httpx deprecation and Lucide build warnings remain.
The checker reported zero scored v3 queries; exposed holdouts were not rescored and
checked-in historical reports were not refreshed. This verifies infrastructure and
unchanged application behavior, not v3 answerability quality.

Optional interview exercise: explain why correct document retrieval can pass both
members of a contrast pair while only one is answerable, and why a quote/hash checker
cannot certify the semantic label.
