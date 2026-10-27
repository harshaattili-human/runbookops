# Request-target abstention

The service applies the fixed v4 request-target guard after document coverage and
before extraction or optional generation. A related document can have high lexical
coverage while lacking the requested live value, configuration, approval, sensitive
value or unwritten procedure. When a signal matches, the API returns an abstained
answer, empty sources/citations and routing that needs review. It explains the missing
external information and skips optional generation in both synchronous and async calls.

`answerability.external_information_signal` is an additive response field containing
the matched signal or null. Coverage, its 0.33 threshold and the candidate source ID
remain available, so callers can distinguish a request-target rejection from low
coverage. The existing dashboard shows the explanation even with high evidence
coverage. A later ordinary incident can still return guidance.

The runtime module re-exports the same candidate function used by the frozen evaluator; there
is no second runtime copy of its patterns. Importing it performs no dataset load or
evaluation. Candidate and ranking file hashes remain those published in
`edcada1089c663aa7466109aa01f4114b43d7a83`. No rule was changed after holdout scoring.
See [the protocol and full failures](information-type-v4.md).

## Evidence and limitations

Validation contained ten supported and ten unsupported queries in ten paired
contexts: expected-top-and-answered supported stayed 9/10; unsupported answers
changed 8/10 to 0/10. The single later holdout comparison preserved 10/10 supported
answers and changed unsupported answers 9/10 to 5/10 (correct pairs 1/10 to 5/10).
These are visible, same-author, AI-assisted synthetic data. Five holdout misses
remain; the rule is not passage entailment and can reject legitimate requests with
similar grammar. A custom corpus may document values these rules withhold; its
operator must evaluate suitability separately. V4 is now exposed, not tuning data.

Three service/API cases compare the 20 validation decisions, verify sync/async
provider bypass and preserve the ordinary descriptive pool incident. No holdout
query is inferred by these tests. A fourth live browser workflow checks high-coverage
abstention, its explanation and no source cards, then keyboard submission of an
ordinary incident. It uses the live API at all nine engine/viewport combinations,
with optional generation selected on the withheld request; no live LLM is invoked.

```sh
python -m runbookops.request_target
python -m pytest -q tests/test_request_target_service.py
cd frontend
npm run test:browser -- --grep 'external value'
```

Initial integration `dca6bf230b7ac0c6e33fb811574c89096e9ea8f1` passed the Python,
component/build, Spring and container jobs in run `40527981916`; browser execution
was still pending system-package installation when the additional workflow was
prepared. The expanded workflow evidence follows.

Exercise: why can high document coverage coexist with abstention, and why does a
passing synthetic paired holdout still leave both false answers and false refusals?

The current validation command is `python -m runbookops.request_target`. It refreshes
lifecycle metadata to describe runtime adoption and the now-exposed holdout without
editing the pinned candidate module. Its metrics still use validation only. The
original frozen evaluator retains publication-time wording for auditability.

## Observed verification — October 27, 2026

[Run 40529246766](https://github.com/harshaattili-human/runbookops/actions/runs/40529246766)
at `5845dc76c8f6e7eabc92ed8a5a63f1dd80834bd2` passed all five jobs. Verify
`122277188950` passed 207 Python cases plus 11 subtests, seven component cases,
validation-only evaluations, frozen-dataset integrity and the frontend build.
Browser `122277188538` passed four live workflows across nine projects (36 executions)
and the existing two replay workflows (18 executions), one worker and no retries.
All nine new abstention/recovery executions passed with the actual API.

The request-target screenshots were inspected for Chromium desktop, Firefox small
and WebKit small. The explanation fits, source cards are absent and coverage remains
visible. The [browser report](https://github.com/harshaattili-human/runbookops/actions/runs/40529246766/artifacts/12745831274)
is retained for 14 days; the command above reproduces the workflow after expiry.
These are resized desktop browsers, not physical-device or assistive-technology proof.

Spring job `122277188606` passed nine Java cases and the live executable walkthrough;
its 26-library audit returned zero advisory entries. Container `122277188408` passed
default and mounted-release workflows, non-root/read-only/health/shutdown/restart
checks and its audit: 24 Python package names, 164 finding entries, zero fixable
HIGH/CRITICAL entries. npm dependencies `122277187853` passed its configured gate.
These dated inventories are not vulnerability-free or deployment claims.

Hosted verification used Python 3.12.15, Node 24.21.0, Java 17.0.21, Ubuntu 24.04,
Chromium 151.0.7922.34, Firefox 153.0 and WebKit 26.5. Locally, TypeScript/build,
seven component cases, discovery of all 36 live executions, validation-only
reproduction, compilation, links and whitespace passed. Full Python/application,
Java, browser and Docker execution used hosted CI because local pytest/HTTPX2 and
Maven dependencies were unavailable. The existing Lucide bundling warning remains.

The subsequent runtime-alias/reporting change preserves the same frozen candidate
function, and refreshes validation metadata rather than the holdout result. No
corpus, ranking, classifier, threshold or holdout label changed. Runtime/API behavior
is now the added target gate, not a claim that the five remaining unsupported
holdout requests have become answerable or fixed.
