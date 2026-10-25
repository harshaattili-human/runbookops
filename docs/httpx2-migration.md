# HTTPX2 transport migration

RunbookOps uses an async HTTP client only for the optional local-model adapter and
for controlled loopback/ASGI test fixtures. The application previously depended on
HTTPX 0.28.1. Starlette 1.2 supports HTTPX2 for `TestClient` and deprecates its HTTPX
compatibility path, which produced one warning on every Python suite run.

The runtime and tests now import HTTPX2 2.16.0 directly. The provider adapter keeps
its existing contract: no redirects or automatic retries, identity response encoding,
a 65,536-byte raw response limit, one cooperative generation deadline, and source-text
fallback for transport or validation failures. Loopback request-admission,
client-disconnect and generation-deadline checks also use HTTPX2. The container smoke
receipt reports the installed HTTPX2 version, while the image inventory gate requires
the package to appear in the scanner output.

Pytest treats the legacy Starlette warning as an error. This guards against a future
dependency change silently putting `TestClient` back on the deprecated compatibility
path. Existing provider-boundary tests remain the behavioral gate; the migration does
not change models, retrieval, answerability thresholds, corpus data or response fields.

## Reproduce

```sh
python -m pip install -e '.[dev]'
python -m pytest -q
python -m pytest -q tests/test_ollama_boundary.py tests/test_generation_deadline.py \
  tests/test_client_disconnect.py tests/test_admission.py tests/test_triage.py
docker build --pull --tag runbookops:smoke .
python scripts/container_smoke.py
bash scripts/audit_image.sh
```

These checks cover synthetic transports, loopback servers and a provider-unavailable
container fallback. They do not run an Ollama model, assess generated-answer quality,
prove provider-side compute termination, or measure production traffic. HTTPX2 remains
a network boundary rather than an authentication or deployment control.

References: [Starlette TestClient](https://www.starlette.io/testclient/),
[Starlette 1.2 release notes](https://www.starlette.io/release-notes/#120-may-28-2026),
[HTTPX2 async and streaming API](https://pydantic.dev/docs/httpx2/async/), and
[FastAPI release notes](https://fastapi.tiangolo.com/release-notes/).

## Observed verification — October 25, 2026

Implementation commit `909144a` passed all five jobs in
[run 40197939275](https://github.com/harshaattili-human/runbookops/actions/runs/40197939275).
The verify job ran 184 Python tests and 11 subtests with no warning summary, seven
frontend component tests, the production build, the classifier evaluation and all
validation-only retrieval/answerability commands. The v3 integrity check scored zero
holdout queries. The browser job passed 27 live and 18 recorded executions across
Chromium, Firefox and WebKit; these are repeated workflows across engines and widths.
The Spring client passed nine Java tests and its live-JAR walkthrough.

The actual runtime image reported Python 3.12.15 and HTTPX2 2.16.0. Its packaged
HTTP/restart and mounted-corpus selection/rollback checks passed. Trivy inventoried
24 Python package names and retained 164 finding entries, with zero fixable high or
critical entries under the existing gate. The separate npm audit reported zero
entries. These dated scans do not establish that either dependency set is free of
vulnerabilities.

Local Python 3.12.14 produced the same 184-test/11-subtest result with no warnings;
HTTPX2 2.16.0 was installed and HTTPX was absent. Compilation, documentation links
and whitespace checks passed locally. Browser, Java and Docker execution was hosted.
