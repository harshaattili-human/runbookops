# Passage-coverage experiment

The October 8, 2026 experiment asks whether lexical coverage in the highest-ranked
passage is a useful second answerability gate. The current service measures coverage
across the entire top runbook, which can let broad topical overlap outweigh a missing
credential, numeric value, or business decision.

The candidate requires both the existing 0.33 document score and a 0.27 score in the
top retrieved chunk plus its document title. The passage threshold was selected on
`validation-v1`: it sits below the lowest supported score (0.2702) and above the
highest unsupported score (0.2528). That narrow separation is a reason for caution,
not evidence of calibration.

## Result

| Fixed suite and policy | Supported answers | Correct top document and answered | Unsupported answers |
| --- | ---: | ---: | ---: |
| Validation, current document gate | 10 / 10 | 10 / 10 | 1 / 10 |
| Validation, document + passage gate | 10 / 10 | 10 / 10 | 0 / 10 |
| Exposed v2 regression, current document gate | 11 / 12 | 10 / 12 | 3 / 14 |
| Exposed v2 regression, document + passage gate | 9 / 12 | 8 / 12 | 3 / 14 |

The validation result does not carry over. On the already-published v2 suite, the
candidate rejects two additional supported answers and does not reject any of the
three remaining unsupported answers. An API-timeout investigation scores 0.2049 in
its top passage because the relevant terms are distributed across the runbook. A
database-lock investigation scores 0.2660, just below the selected threshold. The
requests for guaranteed memory sizing, a refund decision, and OAuth secrets still
pass at 0.3136, 0.2945, and 0.2796 respectively.

The candidate is therefore **not used by the service**. Production behavior remains
the documented IDF-weighted whole-document gate. This is a negative result on small,
authored synthetic suites; it does not show that all passage-level methods fail.

## Reproduce

The routine command writes the validation report:

```sh
python -m runbookops.passage_answerability --split validation
```

The explicit regression command uses the already-exposed v2 cases. It is not a fresh
holdout result and is not run in CI:

```sh
python -m runbookops.passage_answerability --split exposed-v2
```

- [Validation report](../reports/passage-validation-v1.json)
- [Exposed v2 regression report](../reports/passage-exposed-v2.json)

Both reports retain each case, both scores, both decisions, source IDs, input hashes,
and code hashes. A future policy should model the requested information type rather
than rely only on term locality, be selected without tuning on v2, and use a newly
frozen holdout before any improvement claim.
