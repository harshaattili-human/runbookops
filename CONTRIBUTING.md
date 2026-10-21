# Contributing

Make one meaningful change, test the behavior it affects, and explain the reason in
the commit. Keep unrelated formatting changes separate.

Keep data provenance clear. Do not upload private incidents,
customer information, employer material, credentials, or screenshots of internal tools.

Before pushing:

```sh
python -m pytest -q
python -m runbookops.information_dataset
python -m runbookops.information_answerability --split validation
python -m runbookops.evaluate
python -m runbookops.benchmark --split validation
python -m runbookops.answerability --split validation
python -m runbookops.passage_answerability --split validation
cd frontend
npm ci
npm test
npm run build
```

Update the model card when a dataset, threshold, model, or evaluation protocol changes.
For Java example changes, run `python scripts/check_spring_client.py` with Java 17
and Maven available; it owns its API process and checks the packaged walkthrough.
Also run the [packaged Java audit](docs/java-audit.md) after Java dependency or packaging changes.
For Dockerfile or packaging changes, run the [container checks](docs/container-checks.md)
and [image/dependency audits](docs/dependency-audits.md). Preserve unfiltered findings
and the scanner database date when reporting an update.
For UI interaction or layout changes, run the [browser checks](docs/browser-checks.md)
and inspect the generated screenshots as well as the assertions.
For recorded-demo changes, generate the HTML after the frontend build, then run
`npm run test:replay` from `frontend`; see [offline checks](docs/recorded-demo.md).
Keep validation and held-out evaluation sets separate as the benchmark grows.
The v1 holdout has already been inspected. Use validation for development and a new
frozen holdout for fresh quality claims. See [the protocol](docs/evaluation-v1.md).
The answerability v2 holdout is also exposed after its first score. Preserve its
failures and freeze another holdout before tuning or claiming a further improvement.
The [passage experiment](docs/passage-experiment.md) uses v2 only as an explicitly
exposed regression check; its negative result is not permission to tune on those cases.

The [v3 contrastive holdout](docs/information-type-v3.md) is exposed after its first
score. It may be reproduced or used as a regression suite, but it must not select new
rules, thresholds or features. Freeze another holdout before a fresh improvement claim.

## Evidence for a change

- State the concrete problem and the behavior that changes.
- Describe the alternative considered and why the chosen approach fits the constraints.
- Add a focused regression check for a behavior fix; documentation-only changes need
  content and link review, not new tests that merely repeat the implementation.
- For reported metrics, identify the dataset, split, configuration, and command.
  Compare against a baseline when claiming an improvement; preserve unfavorable results.
- Update the review guide if a capability moves from planned to implemented or verified.
- Explain residual limitations. A passing build does not establish model quality,
  security, performance at scale, or a successful deployment.

Use issue or pull-request discussion when it helps explain a substantial change.
Keep exploratory work on a branch until it is ready to reproduce from the default branch.
