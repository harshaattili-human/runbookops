"""Real HTTP framing plus ASGI receive probes; no model-quality claims."""

import asyncio
import gzip
from http.client import HTTPConnection
import json
import socket
from threading import Event, Thread
import time

import pytest
import uvicorn

from runbookops.api import app
from runbookops import request_bounds
from runbookops.request_bounds import MAX_TRIAGE_BYTES, TriageBodyLimit


QUERY = 'Kafka consumer lag increases while producers send more events.'


@pytest.mark.parametrize('chunked', [False, True])
@pytest.mark.parametrize('trickle', [False, True])
def test_upload_deadline_rejects_stalls_and_progress(api_server, calls, monkeypatch, chunked, trickle):
    monkeypatch.setattr(request_bounds, 'TRIAGE_UPLOAD_SECONDS', .3)
    stopped = Event()
    sent_chunks = []
    with socket.create_connection(('127.0.0.1', api_server), timeout=3) as client:
        framing = 'Transfer-Encoding: chunked' if chunked else 'Content-Length: 1000'
        client.sendall((f'POST /api/triage HTTP/1.1\r\nHost: localhost\r\n'
                        f'Content-Type: application/json\r\n{framing}\r\n\r\n').encode())

        def upload():
            while not stopped.is_set():
                try:
                    client.sendall(b'1\r\n \r\n' if chunked else b' ')
                    sent_chunks.append(1)
                except OSError:
                    return
                if not trickle:
                    return
                stopped.wait(.03)

        worker = Thread(target=upload)
        worker.start()
        try:
            reply = bytearray()
            while block := client.recv(4096):
                reply.extend(block)
            head, body = bytes(reply).split(b'\r\n\r\n', 1)
            assert head.startswith(b'HTTP/1.1 408')
            assert b'connection: close' in head.lower()
            assert json.loads(body) == {'detail': 'Triage request upload timed out.'}
            if trickle:
                assert len(sent_chunks) >= 2
            assert calls == []
        finally:
            stopped.set()
            worker.join(timeout=2)
            assert not worker.is_alive()
    assert request(api_server, json.dumps({'query': QUERY}).encode())[0] == 200


def test_upload_cancellation_propagates_without_response():
    async def check():
        entered = asyncio.Event()
        sent = []

        async def receive():
            entered.set()
            await asyncio.Event().wait()

        async def downstream(*args):
            pytest.fail('Partial upload reached downstream')

        async def send(message):
            sent.append(message)

        task = asyncio.create_task(TriageBodyLimit(downstream)(
            {'type': 'http', 'method': 'POST', 'path': '/api/triage', 'headers': []}, receive, send))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert sent == []
    asyncio.run(check())


@pytest.mark.parametrize('oversized', [False, True])
def test_upload_timer_does_not_cover_analysis_or_rejection_send(monkeypatch, oversized):
    monkeypatch.setattr(request_bounds, 'TRIAGE_UPLOAD_SECONDS', .01)

    async def check():
        sent = []
        delivered = []

        async def receive():
            return {'type': 'http.request', 'body': b'x' * (MAX_TRIAGE_BYTES + 1 if oversized else 1),
                    'more_body': False}

        async def send(message):
            # Backpressure after accepting/rejecting a body is not upload time.
            await asyncio.sleep(.03)
            sent.append(message)

        async def downstream(scope, receive, send):
            delivered.append(await receive())
            await asyncio.sleep(.03)
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            await send({'type': 'http.response.body', 'body': b'ok'})

        await TriageBodyLimit(downstream)(
            {'type': 'http', 'method': 'POST', 'path': '/api/triage', 'headers': []}, receive, send)
        assert [m['status'] for m in sent if m['type'] == 'http.response.start'] == [413 if oversized else 200]
        assert len(delivered) == (0 if oversized else 1)
    asyncio.run(check())


@pytest.fixture(scope='module')
def api_server():
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='error', access_log=False))
    worker = Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    worker.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and worker.is_alive() and time.monotonic() < deadline:
            time.sleep(.01)
        assert server.started
        yield port
    finally:
        server.should_exit = True
        worker.join(timeout=10)
        sock.close()
        assert not worker.is_alive()


@pytest.fixture
def calls(api_server, monkeypatch):
    queries = []
    original = app.state.triage.triage

    def record(query, use_llm=False):
        queries.append((query, use_llm))
        return original(query, use_llm)

    monkeypatch.setattr(app.state.triage, 'triage', record)
    return queries


def request(port, payload, chunked=False, **headers):
    connection = HTTPConnection('127.0.0.1', port, timeout=5)
    try:
        body = (payload[i:i + 257] for i in range(0, len(payload), 257)) if chunked else payload
        connection.request('POST', '/api/triage', body=body,
                           headers={'Content-Type': 'application/json', **headers},
                           encode_chunked=chunked)
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


@pytest.mark.parametrize('chunked', [False, True])
@pytest.mark.parametrize('extra', [0, 1])
def test_complete_body_counts_whitespace_before_service(api_server, calls, chunked, extra):
    body = json.dumps({'query': QUERY}).encode()
    body += b' ' * (MAX_TRIAGE_BYTES + extra - len(body))
    status, result = request(api_server, body, chunked)
    assert status == (413 if extra else 200)
    assert calls == ([] if extra else [(QUERY, False)])
    if not extra:
        assert result['mode'] == 'extractive'
    # A rejection does not consume provider slots or break subsequent analysis.
    assert request(api_server, json.dumps({'query': QUERY}).encode())[0] == 200


@pytest.mark.parametrize('escaped', [False, True])
def test_max_query_unicode_bytes_and_escapes_are_accepted(api_server, calls, escaped):
    query = '😀' * 2000
    body = json.dumps({'query': query}, ensure_ascii=escaped).encode()
    # Even 2,000 supplementary characters encoded as surrogate-pair escapes fit.
    status, _ = request(api_server, body)
    assert status == 200
    assert len(calls) == 1


@pytest.mark.parametrize('payload', [b'', b'{broken', b'{"query":"short"}',
                                    b'{"query":"Valid query text", "extra":1}'])
def test_bounded_invalid_json_and_fields_keep_validation(api_server, calls, payload):
    assert request(api_server, payload)[0] == 422
    assert calls == []


def test_encoded_body_is_rejected_without_analysis(api_server, calls):
    body = gzip.compress(json.dumps({'query': QUERY}).encode())
    assert request(api_server, body, **{'Content-Encoding': 'gzip'})[0] == 415
    assert calls == []


def probe(headers, messages, path='/api/triage'):
    consumed = []
    delivered = []
    sent = []

    async def downstream(scope, receive, send):
        delivered.append(await receive())

    async def receive():
        message = messages[len(consumed)]
        consumed.append(message)
        return message

    async def send(message):
        sent.append(message)

    asyncio.run(TriageBodyLimit(downstream)(
        {'type': 'http', 'method': 'POST', 'path': path, 'headers': headers}, receive, send))
    return consumed, delivered, sent


@pytest.mark.parametrize('headers,status', [
    ([(b'content-length', b'32769')], 413),
    ([(b'content-length', b'9' * 5000)], 413),
    ([(b'content-length', b'-1')], 400),
    ([(b'content-length', b'1'), (b'content-length', b'2')], 400),
    ([(b'content-encoding', b'gzip')], 415),
])
def test_rejects_headers_before_receiving_body(headers, status):
    consumed, delivered, sent = probe(headers, [])
    assert consumed == delivered == []
    assert sent[0]['status'] == status


@pytest.mark.parametrize('headers', [[], [(b'content-length', b'1')]])
def test_unknown_or_understated_length_stops_on_crossing_chunk(headers):
    messages = [{'type': 'http.request', 'body': b'x' * 4096, 'more_body': True}] * 100
    consumed, delivered, sent = probe(headers, messages)
    assert len(consumed) == 9
    assert delivered == []
    assert sent[0]['status'] == 413


def test_disconnect_does_not_dispatch_partial_body():
    consumed, delivered, sent = probe([], [
        {'type': 'http.request', 'body': b'{', 'more_body': True},
        {'type': 'http.disconnect'},
    ])
    assert len(consumed) == 2
    assert delivered == sent == []


def test_empty_asgi_chunks_and_identity_replay_exact_bytes():
    body = b'{"query":"Kafka lag"}'
    consumed, delivered, sent = probe([(b'content-encoding', b' Identity ')], [
        {'type': 'http.request', 'more_body': True},
        {'type': 'http.request', 'body': body[:5], 'more_body': True},
        {'type': 'http.request', 'body': body[5:]},
    ])
    assert len(consumed) == 3
    assert delivered == [{'type': 'http.request', 'body': body, 'more_body': False}]
    assert sent == []


def test_slash_redirect_is_bounded_but_unrelated_route_is_not_intercepted():
    headers = [(b'content-length', b'32769')]
    assert probe(headers, [], path='/api/triage/')[2][0]['status'] == 413
    message = {'type': 'http.request', 'body': b'x'}
    assert probe(headers, [message], path='/other')[1] == [message]
