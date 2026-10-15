"""Real HTTP framing plus ASGI receive probes; no model-quality claims."""

import asyncio
import gzip
from http.client import HTTPConnection
import json
import socket
from threading import Thread
import time

import pytest
import uvicorn

from runbookops.api import app
from runbookops.request_bounds import MAX_TRIAGE_BYTES, TriageBodyLimit


QUERY = 'Kafka consumer lag increases while producers send more events.'


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
