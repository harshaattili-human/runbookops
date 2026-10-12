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
  content hash, modal focus containment, keyboard source scrolling and focus return.
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
