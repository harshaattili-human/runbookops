"""Cancellation checks use synthetic loopback HTTP, never a model process."""

import asyncio
from contextlib import asynccontextmanager
import json
from time import perf_counter

import httpx
import pytest

from runbookops.api import app
from runbookops import service as service_module
from runbookops.service import TriageService

QUERY = 'Kafka consumer lag increases while producers send more events.'
FIELDS = ('answer', 'citations', 'sources', 'routing', 'answerability', 'mode')


@pytest.fixture(scope='module')
def service():
    return TriageService()


@pytest.fixture(autouse=True)
def local_model(monkeypatch):
    monkeypatch.setenv('OLLAMA_MODEL', 'synthetic-deadline-fixture')
    for name in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY',
                 'http_proxy', 'https_proxy', 'all_proxy'):
        monkeypatch.delenv(name, raising=False)


@asynccontextmanager
async def provider(monkeypatch, framing):
    state = {'requests': 0, 'closed': 0, 'pieces': 0, 'healthy': False,
             'hold_healthy': False, 'healthy_requests': 0}
    entered = asyncio.Event()
    both_healthy = asyncio.Event()
    handlers = []

    async def handle(reader, writer):
        task = asyncio.current_task()
        handlers.append(task)
        try:
            headers = await reader.readuntil(b'\r\n\r\n')
            length = next(int(line.split(b':', 1)[1]) for line in headers.split(b'\r\n')
                          if line.lower().startswith(b'content-length:'))
            payload = json.loads(await reader.readexactly(length))
            evidence = json.loads(payload['messages'][1]['content'])['evidence']
            body = json.dumps({'done': True, 'done_reason': 'stop', 'message': {
                'content': json.dumps({'answer': 'Synthetic completed response.',
                                      'citations': [evidence[0]['id']]})}}).encode()
            state['requests'] += 1
            healthy = state['healthy']
            entered.set()
            if framing == 'headers' and not healthy:
                assert await reader.read(1) == b''
                state['closed'] += 1
                return
            response_headers = b'HTTP/1.1 200 OK\r\nConnection: close\r\n'
            if healthy or framing == 'fixed':
                response_headers += f'Content-Length: {len(body)}\r\n'.encode()
            elif framing == 'chunked':
                response_headers += b'Transfer-Encoding: chunked\r\n'
            writer.write(response_headers + b'\r\n')
            await writer.drain()
            if healthy:
                if state['hold_healthy']:
                    state['healthy_requests'] += 1
                    if state['healthy_requests'] == 2:
                        both_healthy.set()
                    await asyncio.wait_for(both_healthy.wait(), 3)
                writer.write(body)
                await writer.drain()
                return
            # A byte every 20 ms keeps the 30-second inactivity timer satisfied.
            # Watch EOF concurrently so closure is observed even without a write error.
            for byte in body:
                piece = bytes([byte])
                writer.write(b'1\r\n' + piece + b'\r\n' if framing == 'chunked' else piece)
                await writer.drain()
                state['pieces'] += 1
                try:
                    assert await asyncio.wait_for(reader.read(1), .02) == b''
                    state['closed'] += 1
                    return
                except TimeoutError:
                    pass
            raise AssertionError('Fixture completed before cancellation')
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(handle, '127.0.0.1', 0)
    monkeypatch.setenv('OLLAMA_BASE_URL', f'http://127.0.0.1:{server.sockets[0].getsockname()[1]}')
    try:
        yield state, entered
    finally:
        server.close()
        await server.wait_closed()
        if handlers:
            await asyncio.wait_for(asyncio.gather(*handlers), 3)


@pytest.mark.parametrize('framing', ['headers', 'fixed', 'chunked', 'close'])
def test_api_total_deadline_closes_slow_provider_and_preserves_extract(monkeypatch, framing):
    # Shorten only the test budget. Production always uses 30 seconds.
    monkeypatch.setattr(service_module, 'GENERATION_DEADLINE_SECONDS', .4)

    async def exercise():
        async with app.router.lifespan_context(app), provider(monkeypatch, framing) as (state, entered):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                         base_url='http://api.test') as client:
                baseline = (await client.post('/api/triage', json={'query': QUERY})).json()
                pending = asyncio.create_task(client.post('/api/triage', json={
                    'query': QUERY, 'use_llm': True}))
                await asyncio.wait_for(entered.wait(), 2)
                assert (await client.get('/healthz')).status_code == 200
                assert not pending.done()
                response = await asyncio.wait_for(pending, 3)
                assert response.status_code == 200
                actual = response.json()
                assert actual['warning'] == 'Local generation exceeded its time limit. Showing source text instead.'
                assert all(actual[field] == baseline[field] for field in FIELDS)
                if framing != 'headers':
                    assert state['pieces'] >= 2, 'Fixture must make progress before timing out'
                state['healthy'] = True
                recovered = await client.post('/api/triage', json={'query': QUERY, 'use_llm': True})
                assert recovered.json()['mode'] == 'local-llm'
                assert state['requests'] == 2
        assert state['closed'] == 1, 'Timed-out provider connection was not closed'

    asyncio.run(exercise())


@pytest.mark.parametrize('framing', ['headers', 'chunked'])
def test_external_cancellation_propagates_and_both_slots_are_reusable(service, monkeypatch, framing):
    async def exercise():
        async with provider(monkeypatch, framing) as (state, entered):
            calls = [asyncio.create_task(service.triage_async(QUERY, True)) for _ in range(2)]
            try:
                async with asyncio.timeout(3):
                    while state['requests'] < 2:
                        await asyncio.sleep(.01)
                busy = await service.triage_async(QUERY, True)
                assert 'busy' in busy['warning'] and state['requests'] == 2
                for task in calls:
                    task.cancel()
                results = await asyncio.gather(*calls, return_exceptions=True)
                assert all(isinstance(result, asyncio.CancelledError) for result in results)
                state['healthy'] = True
                state['hold_healthy'] = True
                recovered = await asyncio.gather(*(service.triage_async(QUERY, True) for _ in range(2)))
                assert all(result['mode'] == 'local-llm' for result in recovered)
                assert state['requests'] == 4
            finally:
                for task in calls:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*calls, return_exceptions=True)
        assert state['closed'] == 2

    asyncio.run(exercise())


def test_synchronous_service_keeps_deadline_fallback(service, monkeypatch):
    monkeypatch.setattr(service_module, 'GENERATION_DEADLINE_SECONDS', .4)

    async def exercise():
        async with provider(monkeypatch, 'chunked') as (state, _):
            result = await asyncio.wait_for(asyncio.to_thread(service.triage, QUERY, True), 3)
            assert result['mode'] == 'extractive' and 'time limit' in result['warning']
        assert state['closed'] == 1

    asyncio.run(exercise())


def test_late_synchronous_validation_is_not_published(service, monkeypatch):
    monkeypatch.setattr(service_module, 'GENERATION_DEADLINE_SECONDS', .01)

    async def late_answer(query, sources):
        # Deliberately block the loop: its timer cannot run until this returns.
        end = perf_counter() + .02
        while perf_counter() < end:
            pass
        return 'Late answer', [sources[0]['id']]

    monkeypatch.setattr(service, '_generate', late_answer)
    result = service.triage(QUERY, True)
    assert result['mode'] == 'extractive' and 'time limit' in result['warning']
    assert result['answer'] != 'Late answer'


def test_async_caller_must_use_async_entry_point(service):
    async def exercise():
        with pytest.raises(RuntimeError, match='triage_async'):
            service.triage(QUERY, True)
    asyncio.run(exercise())
