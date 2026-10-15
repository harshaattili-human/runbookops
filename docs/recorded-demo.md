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
npx playwright install --with-deps chromium firefox webkit
npm run test:replay
npx playwright show-report playwright-replay-report
```

The separate configuration starts no web server and opens a `file:` URL. Chromium
and Firefox use Playwright's offline context setting. WebKit uses request blocking
instead, because its offline setting rejects local-file navigation before the app
loads. All engines abort HTTP(S) requests, block service workers and assert that no
HTTP(S) request was attempted. This tests the replay's network independence, not
an operating-system network disconnection. Two workflows run at 1440×900, 390×844 and
320×640 in Chromium, Firefox and WebKit: 18 executions, not 18 distinct workflows.
The first exercises all five
scenarios, replay labels/controls, viewport fit, source focus/return, library and
evaluation while rejecting page errors or attempted HTTP(S) requests. The second
checks all ten document hashes, conflicts, missing sources and unsupported requests.
The HTML hash is also compared with the receipt. Screenshots are observations,
not stored pixel baselines. No automatic retries are configured.

These checks exercise a recorded workflow in three resized desktop browser engines.
They do not establish physical-device, screen-reader, branded Safari or live-model quality.
The existing [live browser suite](browser-checks.md) remains separate and continues
to exercise FastAPI inference. [Playwright offline mode](https://playwright.dev/docs/api/class-browsercontext#browser-context-set-offline)
is a browser test setting, not a security boundary or public deployment control.

Optional interview exercise: which checks would fail if this supposedly standalone
file still depended on a font CDN, JavaScript asset or live API, and which inference
claims cannot be supported by a replay?

## Observed verification

On October 15, 2026, implementation `b65fa4b` passed
[run 38692924184](https://github.com/harshaattili-human/runbookops/actions/runs/38692924184):
six offline executions (two workflows at three widths), alongside the nine live
browser executions and the verify, container and dependency jobs. The browser job
used Python 3.12.15, Node.js 24.21.0 and Chromium 151.0.7922.34. All three source-dialog
screenshots were inspected; the narrow layouts wrap the source text inside a
scrollable, keyboard-focusable region.

The [checked demo artifact](https://github.com/harshaattili-human/runbookops/actions/runs/38692924184/artifacts/11953185857)
contains 428,169 HTML bytes, five scenarios and ten documents. Its receipt identifies
GitHub test-merge commit `01db9afd0682d91ec768336eafd6f231d6e5f2aa`, with no tracked
changes, and HTML SHA-256
`202696a49fe4b5ee098296f4efc6c10de81d1fd7eb513497116679be60ef3062`.
This identifies that export, not a promise that later exports have identical bytes.

Local Python tests (77), component tests (7), validation commands, production build,
export and receipt hash checks passed. Local Chromium downloads returned invalid
archives, so browser execution evidence comes from hosted CI. Existing Starlette/httpx
and Lucide warnings remain. No exposed holdout was rescored.

The later [three-engine run 38744301512](https://github.com/harshaattili-human/runbookops/actions/runs/38744301512)
at `f99ec1a` passed all 18 replay executions and all 27 live executions. Its
[checked export](https://github.com/harshaattili-human/runbookops/actions/runs/38744301512/artifacts/11978161582)
is retained for 30 days. See [browser evidence](browser-checks.md#three-engine-verification--october-15-2026)
for engine versions, the initial WebKit failure and the request-blocking adjustment.
To reproduce the minimal navigation comparison independently, run
`node file-navigation-probe.mjs` from `frontend` after installing WebKit. The probe
prints observations for both offline settings; it does not assert that a browser
limitation must persist in future versions. The replay suite remains the acceptance
check for the actual exported application.
