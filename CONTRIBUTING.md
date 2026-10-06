# Contributing

Make one meaningful change, test the behavior it affects, and explain the reason in
the commit. Keep unrelated formatting changes separate.

Keep data provenance clear. Do not upload private incidents,
customer information, employer material, credentials, or screenshots of internal tools.

Before pushing:

```sh
python -m pytest -q
python -m runbookops.evaluate
python -m runbookops.benchmark --split validation
python -m runbookops.answerability --split validation
cd frontend
npm ci
npm test
npm run build
```

Update the model card when a dataset, threshold, model, or evaluation protocol changes.
For Dockerfile or packaging changes, run the [container checks](docs/container-checks.md).
Keep validation and held-out evaluation sets separate as the benchmark grows.
The v1 holdout has already been inspected. Use validation for development and a new
frozen holdout for fresh quality claims. See [the protocol](docs/evaluation-v1.md).
The answerability v2 holdout is also exposed after its first score. Preserve its
failures and freeze another holdout before tuning or claiming a further improvement.

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
