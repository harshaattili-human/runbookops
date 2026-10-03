# RunbookOps

Route an incident description to a service area, retrieve relevant runbook passages,
and inspect the source lines behind each suggested investigation step.

RunbookOps is a local prototype built with Python, scikit-learn, FastAPI, and
React/TypeScript. Its default path uses a trained classifier and sparse retrieval;
local LLM synthesis is optional. The application never executes remediation.

**Status:** working baseline with passing Python tests and frontend build.
Evaluation uses 90 synthetic descriptions across 30 scenarios and 10 synthetic
runbooks. Operational usefulness has not been measured on real incidents.

## Review in three minutes

| Question | Evidence |
| --- | --- |
| What is implemented, and where? | [Technical review guide](docs/review-guide.md) |
| Why this architecture? | [Design decisions](docs/decisions.md) |
| How was it evaluated? | [Model card](docs/model-card.md) and [results with individual errors](reports/evaluation.json) |
| Does it build and pass checks? | [GitHub Actions](https://github.com/harshaattili-human/runbookops/actions) |
| How can I try it? | [Local setup](#run-locally) and [two-minute walkthrough](docs/demo-script.md) |

## Scope

- Python API for classification, retrieval, and evidence-linked triage.
- A compact React/TypeScript workbench for investigating incidents.
- Reproducible evaluation with scenario-grouped classifier splits.
- Optional local-model synthesis; the default works without an LLM or API key.

## Run locally

Requires Python 3.12 and Node.js 24 (the versions targeted by CI).

```sh
git clone https://github.com/harshaattili-human/runbookops.git
cd runbookops
python -m venv .venv
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e '.[dev]'
python -m runbookops.evaluate
cd frontend
npm ci
npm run build
cd ..
python -m uvicorn runbookops.api:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 for the workbench and http://127.0.0.1:8000/docs for
the API. For frontend development, run `npm run dev` in `frontend` with the API
running separately; Vite proxies `/api` to port 8000.

The editable install intentionally uses the checked-out `data/` and `reports/`
directories. For a non-editable package installation, set `RUNBOOKOPS_ROOT` to the
absolute checkout path. The Dockerfile sets this to `/app`.

## Try it

Choose **Connection pool**, inspect the routing signals, and open the referenced
source. Then choose **Outside the corpus** to inspect abstention. The **Evaluation**
tab displays measured results and misclassifications from the checked-in report.

```sh
curl http://127.0.0.1:8000/api/triage \
  -H 'Content-Type: application/json' \
  -d '{"query":"Kafka consumer lag keeps rising and the group rebalances repeatedly."}'
```

## How it fits together

```mermaid
flowchart TD
  A[Incident description] --> B[FastAPI validation]
  B --> C[TF-IDF classifier]
  B --> D[Hybrid runbook retrieval]
  E[Local Markdown runbooks] --> D
  D --> F{Matching evidence?}
  F -->|No| G[Ask for more context]
  F -->|Yes| H[Extract source or summarize locally]
  C --> I[React workbench]
  G --> I
  H --> I
```

The classifier uses TF-IDF and logistic regression. Retrieval combines BM25 and
TF-IDF cosine similarity. Sparse retrieval was chosen to make the first baseline
fast, reproducible, and easy to inspect. Neither LangChain nor a vector database
is required by this implementation.

## Evaluation and checks

```sh
python -m pytest -q
python -m runbookops.evaluate
```

The initial local run passed 15 tests and produced approximately **0.945 macro F1**
under three-fold, scenario-grouped cross-validation. The runbook retriever found
the expected document for 10 of 10 positive smoke cases and abstained on 4 of 4
unrelated smoke cases. This is a tiny synthetic benchmark, **not production accuracy**.

Read [the model card](docs/model-card.md) and inspect
[the complete evaluation](reports/evaluation.json), including failures and split
membership. [The first GitHub Actions run](https://github.com/harshaattili-human/runbookops/actions/runs/37152016110)
passed on October 3, 2026, including the Python tests, evaluation, and frontend
production build on Python 3.12 and Node.js 24.

## Optional local LLM

Start an Ollama instance and choose a model already available on that instance.
Set `OLLAMA_MODEL` to that exact model name before starting the API. Optionally set
`OLLAMA_BASE_URL`; its default is `http://127.0.0.1:11434`. Check **Use configured
local LLM** in the UI. No model is downloaded automatically and no cloud service is
called by default.

Generation requires citation IDs from the retrieved evidence. Invalid IDs or a
provider failure return the original source extract. This validates references,
not factual entailment. The adapter has mocked contract tests; a live local-model
quality evaluation is still pending.

## Container

```sh
docker build -t runbookops .
docker run --rm -p 127.0.0.1:8000:8000 runbookops
```

The image builds the frontend and runs the API as a non-root user. Docker build
execution has not been verified in the current workspace. Keep this demo local:
authentication, rate limiting, and multi-tenant isolation are not implemented.

## Project notes

- [Design decisions](docs/decisions.md)
- [Data provenance](data/README.md)
- [Two-minute demo and interview discussion](docs/demo-script.md)
- [Next improvements](docs/roadmap.md)
- [Contribution workflow](CONTRIBUTING.md)

## Provenance

Independent portfolio project by Harsha Attili, developed with AI coding assistance.
The code, incidents, and runbooks were created for this project; no employer code,
internal documents, or production logs are included. See [data provenance](data/README.md).

Implementation references: [scikit-learn pipelines](https://scikit-learn.org/stable/modules/compose.html),
[grouped splits](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.StratifiedGroupKFold.html),
[FastAPI static files](https://fastapi.tiangolo.com/tutorial/static-files/),
and [Ollama chat API](https://docs.ollama.com/api/chat).
