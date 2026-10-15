# Offline interview demo

The exported HTML lets a reviewer explore five recorded scenarios, inspect source
lines and browse the evaluation without installing Python or starting an API.
The visible **Recorded demo** label and replay notice remain present. This file
does not analyze arbitrary text or run a language model.

## Build and open

From the checkout with Python 3.12, Node.js 24 and the project dependencies installed:

```sh
cd frontend
npm ci
npm run build
cd ..
python scripts/export_demo.py artifacts/RunbookOps-Demo.html
```

Open `artifacts/RunbookOps-Demo.html` in a browser. Keep the adjacent
`RunbookOps-Demo.json` as its provenance receipt; opening the HTML does not require
the receipt, a server or a network connection. The exporter uses FastAPI TestClient
to capture current extractive results, the ten runbooks and the existing evaluation
report. API errors fail export instead of becoming silently recorded error bodies.
All inputs are the project's synthetic examples.

The receipt includes the HTML SHA-256, generation time, Git HEAD, whether tracked
files differ from HEAD, Python version, scenario outcomes, document hashes and
hashes of source/data/report/built assets. Git HEAD alone does not identify modified
local inputs; use the input hashes too. In pull-request CI, HEAD may be GitHub's
test merge commit. A hash identifies bytes, not authorship, authenticity or quality.
Timestamps, request IDs and recorded durations vary between exports, so the procedure
is reproducible but output bytes are not promised to be identical.

## Download a checked export

Open a successful **Project checks** run under the repository's **Actions** tab.
Download the `recorded-demo` artifact and extract its HTML and JSON files. GitHub
may require sign-in to download artifacts. CI uploads that artifact only after the
offline browser checks pass and retains it for 30 days. To share it afterward,
regenerate it from the repository. Generated bundles are not committed as source.

The separate `recorded-demo-browser-report` artifact contains screenshots and failure
traces, retained for 14 days. These retention windows are not permanent hosting.

## Walkthrough

1. Choose **Connection pool**. Explain the service-area suggestion and open the
   cited source. Tab to the source text and use Escape to return to the card.
2. Try **Consumer backlog** and **Stalled approval** to show other supported scenarios.
3. Choose **Missing information**, then **Outside the corpus**. Explain why a related
   document and no candidate are different cases even though both withhold guidance.
4. Filter the **Runbook library**, then open **Evaluation** and discuss a limitation.
5. For a new incident, run the live app locally using the README. The replay keeps
   its text field read-only and disables local-model generation.

The shim returns 404 for an unrecorded query and 422 for a local-model request.
It retains versioned source reads: a mismatched expected hash returns 409 without
document content, while a missing source returns 404. It is a limited replay layer,
not a general offline API implementation or an index-refresh demonstration.

## Browser verification

After generating the artifact:

```sh
cd frontend
npx playwright install --with-deps chromium
npm run test:replay
npx playwright show-report playwright-replay-report
```

The separate configuration starts no web server and opens a `file:` URL with
Playwright's browser context offline. Two workflows run at 1440×900, 390×844 and
320×640: six executions, not six distinct workflows. The first exercises all five
scenarios, replay labels/controls, viewport fit, source focus/return, library and
evaluation while rejecting page errors or attempted HTTP(S) requests. The second
checks all ten document hashes, conflicts, missing sources and unsupported requests.
The HTML hash is also compared with the receipt. Screenshots are observations,
not stored pixel baselines. No automatic retries are configured.

These checks establish a recorded workflow in resized desktop Chromium. They do
not establish physical-device, screen-reader, other-browser or live-model quality.
The existing [live browser suite](browser-checks.md) remains separate and continues
to exercise FastAPI inference. [Playwright offline mode](https://playwright.dev/docs/api/class-browsercontext#browser-context-set-offline)
is a browser test setting, not a security boundary or public deployment control.

Optional interview exercise: which checks would fail if this supposedly standalone
file still depended on a font CDN, JavaScript asset or live API, and which inference
claims cannot be supported by a replay?
