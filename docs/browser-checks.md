# Workbench browser checks

The browser suite opens the built React app served by FastAPI and uses live
synthetic triage and runbook responses. Playwright starts its own loopback Uvicorn
process on port 8765 and refuses to reuse an existing server. No Ollama or cloud
service is needed.

From the repository root, with Python 3.12 and Node.js 24:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cd frontend
npm ci
npx playwright install --with-deps chromium firefox webkit
npm run build
npm run test:browser
npx playwright show-report
```

Three workflows run in Chromium, Firefox and WebKit, each at 1440×900, 390×844
and 320×640 CSS pixels: 27 executions across nine projects, not 27 distinct workflows.

- Live analysis, the citation's expected hash in the source request, matching
  content hash, modal focus containment, keyboard scrolling to the end of overflowing source text
  and focus return.
- Unsupported-query abstention, keyboard page navigation, library filtering and
  evaluation layout without horizontal page overflow.
- An explicitly injected source HTTP 409, focus retention and successful live
  reanalysis/source recovery after removing the injected response.

The HTML report includes analysis, source and filtered-library screenshots for
review. CI retains it for 14 days; failing tests also retain a trace and screenshot.
These are observations, not pixel-baseline assertions. There are no automatic
retries. Run `npm run test:browser -- --project=firefox-small` for one engine/viewport.
Project names combine `chromium`, `firefox` or `webkit` with `desktop`, `narrow` or
`small`. The same project matrix is used for the separate offline replay suite.

These are Playwright's desktop browser builds with resized viewports, not physical
phones, touch input, branded Safari, screen-reader or other assistive-technology verification. The
synthetic scenarios check application wiring and interactions, not model quality.
The source-conflict case is fault injection, not an index-refresh experiment.

Configuration follows Playwright's [web server](https://playwright.dev/docs/test-webserver),
[projects](https://playwright.dev/docs/test-projects) and
[CI](https://playwright.dev/docs/ci) documentation.
The [browser guide](https://playwright.dev/docs/browsers) explains why Playwright's
patched Firefox and WebKit builds do not stand in for every installed browser or OS.

## Failure found during implementation

The initial [run 38259046506](https://github.com/harshaattili-human/runbookops/actions/runs/38259046506)
at `98fd0f4` passed six browser executions but failed the source-reading workflow
at all three widths. The source text had no keyboard focus target, so the custom
modal trap kept Tab on the close button. On narrow screens the document extended
below the visible region.

The source is now a labeled, focusable region inside the existing trap. Tab moves
from Close to the text; End scrolls overflowing text to the bottom; Tab and
Shift+Tab stay inside the dialog; Escape restores the invoking card. Its focus
outline is inset so the modal's clipping does not hide it. This adds one tab stop,
including when the whole document fits on desktop. No separate scrolling widget or
custom arrow-key handler is needed.

The browser assertion requires overflow in both narrow fixtures and checks the
bottom scroll position after End. It does not require scrolling when the full
document already fits. The existing component test also checks the two focus stops.

Optional interview exercise: explain why trapping Tab on a close button can pass
a modal-focus test while still making the document unusable to a keyboard reader.

## Observed verification — October 12, 2026

Fix commit `29c555421eb038a01e74a55b90df74470c85753b` passed
[run 38259513249](https://github.com/harshaattili-human/runbookops/actions/runs/38259513249).
The browser job used Playwright 1.62.1 / Chromium 151.0.7922.34 on Ubuntu 24.04,
Python 3.12.15 and Node.js 24. All nine executions passed with no retries: the same
three workflows at the three viewport sizes above, not nine distinct workflows.
The same run passed 41 Python tests, seven jsdom component tests, the classifier
and validation evaluation commands, production build, and container HTTP/runtime/
restart checks. No exposed holdout was rescored.

The [browser report](https://github.com/harshaattili-human/runbookops/actions/runs/38259513249/artifacts/11751323346)
contains the screenshots; download and extract it, then run
`npx playwright show-report /path/to/extracted-report` from `frontend`.
The artifact expires after 14 days; the command above reproduces the checks and
screenshots. The images have no stored pixel-comparison baseline.

Local Python/component tests, validation commands and frontend build passed.
Local browser installation returned invalid downloaded archives, so Chromium
execution evidence comes from hosted CI. Existing Starlette/httpx and Lucide build
warnings remain. Passing these checks does not establish screen-reader behavior,
full accessibility conformance, other browser support or production readiness.

## Three-engine verification — October 15, 2026

Commit `f99ec1ae234fcf6d71254c1fae42f9fddee286a4` passed
[run 38744301512](https://github.com/harshaattili-human/runbookops/actions/runs/38744301512):
27 live executions (three workflows × three engines × three widths) and 18 separate
recorded-replay executions (two workflows × the same matrix), with no retries.
The browser job used Playwright 1.62.1, Chromium 151.0.7922.34, Firefox 153.0 and
WebKit 26.5 on Ubuntu 24.04, Python 3.12.15 and Node.js 24.21.0. The same run passed
80 Python tests, seven component tests, validation/build, container HTTP/runtime/
restart checks and the configured dependency audit gates. No exposed holdout was
rescored and no application/model behavior changed in this increment.

The initial [run 38742987142](https://github.com/harshaattili-human/runbookops/actions/runs/38742987142)
already passed all 27 live checks. Its six WebKit replay executions failed during
local-file navigation; the twelve Chromium/Firefox replay executions passed. A
minimal HTML file with no scripts or assets reproduced WebKit's internal navigation
error with `offline: true`, while `offline: false` loaded it. The replay configuration
therefore uses HTTP(S) request blocking for WebKit and retains offline mode for the
other engines. All engines reject attempted HTTP(S) requests. See the
[replay contract and limitation](recorded-demo.md#browser-verification).

The [live report](https://github.com/harshaattili-human/runbookops/actions/runs/38744301512/artifacts/11977362630)
and [replay report](https://github.com/harshaattili-human/runbookops/actions/runs/38744301512/artifacts/11977247660)
expire after 14 days. Narrow Firefox/WebKit live source-dialog screenshots from the
initial run were inspected. Local TypeScript/build, test discovery, documentation
links and whitespace checks passed; browser execution was hosted. Narrow Firefox/
WebKit replay source-dialog screenshots from the passing run were also inspected.
These results
extend engine coverage, not physical-device or assistive-technology coverage.
