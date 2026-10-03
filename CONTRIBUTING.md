# Contributing

Make one meaningful change, test the behavior it affects, and explain the reason in
the commit. Avoid unrelated formatting churn and synthetic contribution activity.

Use current timestamps. Keep data provenance clear. Do not upload private incidents,
customer information, employer material, credentials, or screenshots of internal tools.

Before pushing:

```sh
python -m pytest -q
python -m runbookops.evaluate
cd frontend
npm ci
npm run build
```

Update the model card when a dataset, threshold, model, or evaluation protocol changes.
Keep validation and held-out evaluation sets separate as the benchmark grows.
