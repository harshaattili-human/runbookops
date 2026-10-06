"""Stateless HTTP boundary. Run from the repository, not as a standalone wheel."""

from contextlib import asynccontextmanager
import json

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .service import ROOT, TriageService


class TriageRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    query: str = Field(min_length=8, max_length=2000)
    use_llm: bool = False

    @field_validator('query')
    @classmethod
    def useful_text(cls, value: str) -> str:
        if len(value.strip()) < 8:
            raise ValueError('Provide at least eight non-padding characters')
        return value.strip()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.triage = TriageService()
    yield


app = FastAPI(title='RunbookOps', version='0.1.0', lifespan=lifespan)


@app.get('/healthz')
def health():
    return {'status': 'ok', 'documents': len(app.state.triage.retriever.documents)}


@app.post('/api/triage')
def triage(body: TriageRequest):
    return app.state.triage.triage(body.query, body.use_llm)


@app.get('/api/overview')
def overview():
    service = app.state.triage
    report = ROOT / 'reports' / 'evaluation.json'
    return {'documents': len(service.retriever.documents),
            'chunks': len(service.retriever.chunks), 'incidents': len(service.rows),
            'categories': sorted({r['category'] for r in service.rows}),
            'evaluation': json.loads(report.read_text()) if report.exists() else None,
            'runbooks': [{'id': slug, 'title': text.splitlines()[0].removeprefix('# ')}
                        for slug, text in service.retriever.documents.items()]}


@app.get('/api/runbooks/{slug}')
def runbook(slug: str, expected_hash: str | None = None):
    retriever = app.state.triage.retriever
    text = retriever.documents.get(slug)
    if text is None:
        raise HTTPException(404, 'Runbook not found')
    content_hash = retriever.document_hashes[slug]
    if expected_hash is not None and expected_hash != content_hash:
        raise HTTPException(409, 'Runbook version changed; run triage again.')
    return {'id': slug, 'content': text, 'content_hash': content_hash}


# Only the compiled frontend is served. No source tree or data directory mount.
dist = ROOT / 'frontend' / 'dist'
if dist.exists():
    app.mount('/assets', StaticFiles(directory=dist / 'assets'), name='assets')

    @app.get('/', include_in_schema=False)
    def index():
        return FileResponse(dist / 'index.html')
