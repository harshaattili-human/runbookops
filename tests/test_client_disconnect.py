"""Real caller disconnects through Uvicorn; provider bytes are synthetic."""

import asyncio
from contextlib import asynccontextmanager
import json
import socket

import httpx2
import pytest
import uvicorn

from runbookops.api import app, triage, TriageRequest
from test_generation_deadline import provider, QUERY, local_model


@asynccontextmanager
async def running_api():
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='error', access_log=False))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if task.done():
                    task.result()
                await asyncio.sleep(.01)
        yield port
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 10)
        sock.close()


async def upload(port, chunked):
    reader, writer = await asyncio.open_connection('127.0.0.1', port)
    body = json.dumps({'query': QUERY, 'use_llm': True}).encode()
    framing = b'Transfer-Encoding: chunked' if chunked else f'Content-Length: {len(body)}'.encode()
    writer.write(b'POST /api/triage HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\n'
                 + framing + b'\r\n\r\n')
    writer.write(f'{len(body):x}\r\n'.encode() + body + b'\r\n0\r\n\r\n' if chunked else body)
    await writer.drain()
    return reader, writer


@pytest.mark.parametrize('framing', ['headers', 'chunked'])
@pytest.mark.parametrize('chunked_upload', [False, True])
def test_caller_close_cancels_provider_and_recovers_both_slots(monkeypatch, framing, chunked_upload):
    async def exercise():
        async with provider(monkeypatch, framing) as (state, _), running_api() as port:
            connections = [await upload(port, chunked_upload) for _ in range(2)]
            try:
                async with asyncio.timeout(4):
                    while state['requests'] < 2:
                        await asyncio.sleep(.01)
                async with httpx2.AsyncClient(base_url=f'http://127.0.0.1:{port}', trust_env=False) as client:
                    busy = await client.post('/api/triage', json={'query': QUERY, 'use_llm': True})
                    assert 'busy' in busy.json()['warning'] and state['requests'] == 2
                    assert (await client.get('/healthz')).status_code == 200
                    for _, writer in connections:
                        writer.close()
                        await writer.wait_closed()
                    # Production deadline remains 30s; EOF within this test bound
                    # must come from caller loss, not the total deadline.
                    async with asyncio.timeout(4):
                        while state['closed'] != 2:
                            await asyncio.sleep(.01)
                    state['healthy'] = state['hold_healthy'] = True
                    responses = await asyncio.gather(*(client.post('/api/triage', json={
                        'query': QUERY, 'use_llm': True}) for _ in range(2)))
                    assert all(response.status_code == 200 and response.json()['mode'] == 'local-llm'
                               for response in responses)
                    assert state['healthy_requests'] == 2 and state['requests'] == 4
                    assert (await client.post('/api/triage', json={'query': QUERY})).json()['mode'] == 'extractive'
            finally:
                for _, writer in connections:
                    writer.close()
                    await writer.wait_closed()
    asyncio.run(exercise())


def test_completed_work_stops_disconnect_watcher(monkeypatch):
    async def exercise():
        waiting = asyncio.Event()
        closed = asyncio.Event()
        class Request:
            async def receive(self):
                waiting.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    closed.set()
        class Service:
            async def triage_async(self, query, use_llm=False):
                await waiting.wait()
                return {'mode': 'local-llm'}
        monkeypatch.setattr(app.state, 'triage', Service(), raising=False)
        assert await triage(TriageRequest(query=QUERY, use_llm=True), Request()) == {'mode': 'local-llm'}
        assert closed.is_set()
    asyncio.run(exercise())


def test_outer_task_cancellation_joins_work_and_receive_watcher(monkeypatch):
    async def exercise():
        entered = [asyncio.Event(), asyncio.Event()]
        closed = [asyncio.Event(), asyncio.Event()]
        async def wait(index):
            entered[index].set()
            try:
                await asyncio.Event().wait()
            finally:
                closed[index].set()
        class Request:
            async def receive(self):
                return await wait(1)
        class Service:
            async def triage_async(self, query, use_llm=False):
                return await wait(0)
        monkeypatch.setattr(app.state, 'triage', Service(), raising=False)
        task = asyncio.create_task(triage(TriageRequest(query=QUERY, use_llm=True), Request()))
        await asyncio.gather(*(event.wait() for event in entered))
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert all(event.is_set() for event in closed)
    asyncio.run(exercise())
