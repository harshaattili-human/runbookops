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

The service imports the same candidate function used by the frozen evaluator; there
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
python -m pytest -q tests/test_request_target_service.py
cd frontend
npm run test:browser -- --grep 'external value'
```

Initial integration `dca6bf230b7ac0c6e33fb811574c89096e9ea8f1` passed the Python,
component/build, Spring and container jobs in run `40527981916`; browser execution
was still pending system-package installation when the additional workflow was
prepared. Final integration/browser evidence is recorded below after execution.

Exercise: why can high document coverage coexist with abstention, and why does a
passing synthetic paired holdout still leave both false answers and false refusals?
