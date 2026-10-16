"""Stateless HTTP boundary. Run from the repository, not as a standalone wheel."""

import asyncio
from contextlib import asynccontextmanager
import json

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .service import ROOT, TriageService
from .request_bounds import TriageBodyLimit


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
app.add_middleware(TriageBodyLimit)


@app.get('/healthz')
def health():
    return {'status': 'ok', 'documents': len(app.state.triage.retriever.documents)}


@app.post('/api/triage')
async def triage(body: TriageRequest, request: Request):
    if not body.use_llm:
        return await app.state.triage.triage_async(body.query)

    # FastAPI has consumed the complete body. Only this watcher reads afterward.
    async def disconnected():
        while (await request.receive())['type'] != 'http.disconnect':
            pass

    work = asyncio.create_task(app.state.triage.triage_async(body.query, True))
    watcher = asyncio.create_task(disconnected())
    try:
        done, _ = await asyncio.wait((work, watcher), return_when=asyncio.FIRST_COMPLETED)
        if watcher in done:
            watcher.result()  # Do not hide a receive-channel failure.
            # No answer is sent to a caller that has already left. Uvicorn ignores
            # this empty response on the closed transport; 499 labels access logs.
            return Response(status_code=499)
        return work.result()
    finally:
        for task in (work, watcher):
            if not task.done():
                task.cancel()
        await asyncio.gather(work, watcher, return_exceptions=True)


@app.get('/api/overview')
def overview():
    service = app.state.triage
    retriever = service.retriever
    report = ROOT / 'reports' / 'evaluation.json'
    return {'documents': len(retriever.documents),
            'chunks': len(retriever.chunks), 'incidents': len(service.rows),
            'categories': sorted({r['category'] for r in service.rows}),
            'evaluation': json.loads(report.read_text()) if report.exists() else None,
            'runbooks': [{'id': slug, 'title': text.splitlines()[0].removeprefix('# ')}
                        for slug, text in retriever.documents.items()]}


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
