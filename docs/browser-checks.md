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
npx playwright install --with-deps chromium
npm run build
npm run test:browser
npx playwright show-report
```

Three workflows run in Chromium at 1440×900, 390×844 and 320×640 CSS pixels:

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
retries. Run `npm run test:browser -- --project=small` for one viewport.

This is desktop Chromium with resized viewports, not physical phone, touch,
Safari/Firefox, screen-reader or other assistive-technology verification. The
synthetic scenarios check application wiring and interactions, not model quality.
The source-conflict case is fault injection, not an index-refresh experiment.

Configuration follows Playwright's [web server](https://playwright.dev/docs/test-webserver),
[projects](https://playwright.dev/docs/test-projects) and
[CI](https://playwright.dev/docs/ci) documentation.

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
