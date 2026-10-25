"""Admission lifecycle fixtures; no throughput or model-quality measurements."""

import asyncio
import json
from threading import Event

import httpx2
import pytest

from runbookops.admission import TriageAdmission
from runbookops.service import TriageService
from test_client_disconnect import running_api


SCOPE = {'type': 'http', 'method': 'POST', 'path': '/api/triage',
         'headers': [], 'http_version': '1.1'}
QUERY = 'Kafka consumer lag keeps rising while producers send more events.'


@pytest.mark.parametrize('capacity', [0, -1, 1001, True, 1.5])
def test_capacity_requires_bounded_integer(capacity):
    with pytest.raises(ValueError):
        TriageAdmission(None, capacity)


@pytest.mark.parametrize('exit_kind', ['success', 'error', 'cancel', 'send-error'])
def test_admission_retains_slots_until_completion_and_recovers(exit_kind):
    async def check():
        entered = asyncio.Queue()
        release = asyncio.Event()
        delivered = []

        async def receive():
            pytest.fail('Admission rejection read a body')

        async def send(message):
            delivered.append(message)

        async def downstream(scope, receive, send):
            if scope['path'] != '/api/triage':
                return
            await entered.put(True)
            await release.wait()
            if exit_kind == 'error':
                raise ValueError('synthetic downstream failure')
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            if exit_kind == 'send-error':
                raise OSError('synthetic closed response transport')
            await send({'type': 'http.response.body', 'body': b'ok'})

        app = TriageAdmission(downstream, capacity=2)
        tasks = [asyncio.create_task(app(SCOPE, receive, send)) for _ in range(2)]
        try:
            for _ in tasks:
                await asyncio.wait_for(entered.get(), 2)
            await app(SCOPE, receive, send)
            assert delivered[0]['status'] == 503
            assert dict(delivered[0]['headers'])[b'cache-control'] == b'no-store'
            assert dict(delivered[0]['headers'])[b'connection'] == b'close'
            assert b'retry-after' not in dict(delivered[0]['headers'])
            await app({**SCOPE, 'path': '/healthz', 'method': 'GET'}, receive, send)
            if exit_kind == 'cancel':
                for task in tasks:
                    task.cancel()
            release.set()
            outcomes = await asyncio.gather(*tasks, return_exceptions=True)
            expected = {'error': ValueError, 'send-error': OSError, 'cancel': asyncio.CancelledError}
            if exit_kind in expected:
                assert all(isinstance(value, expected[exit_kind]) for value in outcomes)
            else:
                assert outcomes == [None, None]
            # Occupy both again to catch leaks and accidental double releases.
            release.clear()
            tasks = [asyncio.create_task(app(SCOPE, receive, send)) for _ in range(2)]
            for _ in tasks:
                await asyncio.wait_for(entered.get(), 2)
            delivered.clear()
            await app(SCOPE, receive, send)
            assert delivered[0]['status'] == 503
        finally:
            release.set()
            await asyncio.gather(*tasks, return_exceptions=True)
    asyncio.run(check())


def test_response_backpressure_holds_admission():
    async def check():
        sending = asyncio.Event()
        release = asyncio.Event()
        rejected = []

        async def downstream(scope, receive, send):
            await send({'type': 'http.response.body', 'body': b'ok'})

        async def slow_send(message):
            sending.set()
            await release.wait()

        async def send(message):
            rejected.append(message)

        app = TriageAdmission(downstream, 1)
        task = asyncio.create_task(app(SCOPE, None, slow_send))
        try:
            await sending.wait()
            await app(SCOPE, None, send)
            assert rejected[0]['status'] == 503
        finally:
            release.set()
            await task
        rejected.clear()
        await app(SCOPE, None, send)
        assert rejected == [{'type': 'http.response.body', 'body': b'ok'}]
    asyncio.run(check())


@pytest.mark.parametrize('worker_fails', [False, True])
def test_repeated_cancellation_joins_classifier_before_returning_capacity(monkeypatch, worker_fails):
    async def check():
        started = Event()
        finish = Event()
        service = TriageService()

        def classify(query):
            started.set()
            assert finish.wait(5), 'Test did not release worker'
            if worker_fails:
                raise ValueError('synthetic classifier failure')
            return {'sources': []}

        monkeypatch.setattr(service, 'triage', classify)
        responses = []

        async def downstream(scope, receive, send):
            await service.triage_async(QUERY, True)

        async def send(message):
            responses.append(message)

        app = TriageAdmission(downstream, 1)
        task = asyncio.create_task(app(SCOPE, None, send))
        try:
            async with asyncio.timeout(3):
                while not started.is_set():
                    await asyncio.sleep(.001)
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
            await app(SCOPE, None, send)
            assert responses[0]['status'] == 503
        finally:
            finish.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 3)
        assert app.slots.acquire(blocking=False)
        assert not app.slots.acquire(blocking=False)
        app.slots.release()
    asyncio.run(check())


def test_stock_http_cap_precedes_body_reads_and_recovers_after_disconnect():
    async def check():
        connections = []
        async with running_api() as port:
            async def begin(index):
                reader, writer = await asyncio.open_connection('127.0.0.1', port)
                connections.append(writer)
                framing = 'Transfer-Encoding: chunked' if index % 2 else 'Content-Length: 100'
                writer.write((f'POST /api/triage HTTP/1.1\r\nHost: localhost\r\n'
                              f'Content-Type: application/json\r\n{framing}\r\n'
                              'Expect: 100-continue\r\n\r\n').encode())
                await writer.drain()
                return reader, writer, await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 3)

            try:
                for index in range(8):
                    _, _, head = await begin(index)
                    # Uvicorn sends 100 only when the application requests body bytes.
                    assert head.startswith(b'HTTP/1.1 100')
                reader, writer, head = await begin(8)
                assert head.startswith(b'HTTP/1.1 503')
                assert b'connection: close' in head.lower()
                assert json.loads(await asyncio.wait_for(reader.read(), 3))['detail'].startswith('Triage capacity exhausted')
                async with httpx2.AsyncClient(base_url=f'http://127.0.0.1:{port}', trust_env=False) as client:
                    assert (await client.get('/healthz')).status_code == 200
                    for connection in connections:
                        connection.close()
                        await connection.wait_closed()
                    connections.clear()
                    # Wait for server-side EOF handling, without assuming client close is synchronous.
                    async with asyncio.timeout(5):
                        for index in range(8):
                            while True:
                                _, recovery, head = await begin(index)
                                if head.startswith(b'HTTP/1.1 100'):
                                    break
                                assert head.startswith(b'HTTP/1.1 503')
                                recovery.close()
                                await recovery.wait_closed()
                                connections.remove(recovery)
                                await asyncio.sleep(.01)
                    assert (await client.post('/api/triage', json={'query': QUERY})).status_code == 503
            finally:
                for connection in connections:
                    connection.close()
                    await connection.wait_closed()
    asyncio.run(check())
