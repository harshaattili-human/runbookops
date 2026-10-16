"""Controlled provider responses test transport contracts, not model quality."""

import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread

import httpx
import pytest
from fastapi.testclient import TestClient

from runbookops.api import app
from runbookops.service import TriageService


QUERY = 'Kafka consumer lag increases while producers send more events.'
LIMIT = 65_536


@pytest.fixture(scope='module')
def service():
    return TriageService()


@pytest.fixture(autouse=True)
def local_model(monkeypatch):
    monkeypatch.setenv('OLLAMA_MODEL', 'test-only-model')
    for name in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY',
                 'http_proxy', 'https_proxy', 'all_proxy'):
        monkeypatch.delenv(name, raising=False)


def envelope(service, **changes):
    source = service.triage(QUERY)['sources'][0]['id']
    body = {'done': True, 'done_reason': 'stop', 'message': {
        'role': 'assistant', 'content': json.dumps({
            'answer': 'Inspect the consumer group — café.', 'citations': [source, source]},
            ensure_ascii=False)}}
    body.update(changes)
    return json.dumps(body, ensure_ascii=False).encode('utf-8')


@pytest.fixture
def provider(monkeypatch):
    responses = []
    requests = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def do_POST(self):
            requests.append({'path': self.path, 'headers': dict(self.headers),
                             'body': json.loads(self.rfile.read(int(self.headers['Content-Length'])))})
            body, framing, status, headers = responses.pop(0)
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Connection', 'close')
            if framing == 'fixed':
                self.send_header('Content-Length', str(len(body)))
            elif framing == 'chunked':
                self.send_header('Transfer-Encoding', 'chunked')
            elif framing == 'truncated':
                self.send_header('Content-Length', str(len(body) + 10))
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            try:
                for offset in range(0, len(body), 1024):
                    chunk = body[offset:offset + 1024]
                    if framing == 'chunked':
                        self.wfile.write(f'{len(chunk):x}\r\n'.encode() + chunk + b'\r\n')
                    else:
                        self.wfile.write(chunk)
                if framing == 'chunked':
                    self.wfile.write(b'0\r\n\r\n')
            except (BrokenPipeError, ConnectionResetError):
                pass  # Early client rejection may close an oversized response.
            self.close_connection = True

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = Thread(target=lambda: server.serve_forever(poll_interval=.01), daemon=True)
    worker.start()
    monkeypatch.setenv('OLLAMA_BASE_URL', f'http://127.0.0.1:{server.server_port}')
    try:
        yield responses, requests
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
        assert not worker.is_alive()


def assert_fallback(service):
    expected = service.triage(QUERY)
    actual = service.triage(QUERY, use_llm=True)
    assert actual['warning']
    for field in ('answer', 'citations', 'sources', 'routing', 'answerability', 'mode'):
        assert actual[field] == expected[field], field


@pytest.mark.parametrize('framing', ['fixed', 'chunked', 'close'])
@pytest.mark.parametrize('excess', [0, 1])
def test_byte_limit_includes_trailing_whitespace(service, provider, framing, excess):
    responses, requests = provider
    body = envelope(service)
    body += b' ' * (LIMIT + excess - len(body))
    responses.append((body, framing, 200, {}))
    if excess:
        assert_fallback(service)
    else:
        result = service.triage(QUERY, use_llm=True)
        assert result['mode'] == 'local-llm'
        assert result['warning'] is None
        assert result['answer'] == 'Inspect the consumer group — café.'
        assert result['citations'] == [result['sources'][0]['id']]
    assert len(requests) == 1
    assert requests[0]['path'] == '/api/chat'
    assert requests[0]['body']['stream'] is False
    assert requests[0]['headers']['Accept-Encoding'] == 'identity'


@pytest.mark.parametrize('changes', [
    {'done': False}, {'done': 1}, {'done': None},
    {'done_reason': 'length'}, {'done_reason': None},
])
def test_unfinished_or_truncated_generation_uses_source(service, provider, changes):
    responses, _ = provider
    responses.append((envelope(service, **changes), 'fixed', 200, {}))
    assert_fallback(service)


@pytest.mark.parametrize('field', ['done', 'done_reason'])
def test_completion_metadata_is_required(service, provider, field):
    body = json.loads(envelope(service))
    del body[field]
    provider[0].append((json.dumps(body).encode(), 'fixed', 200, {}))
    assert_fallback(service)


@pytest.mark.parametrize('payload', [
    b'{broken', b'null', b'[]', b'\xff',
    b'[' * 2000 + b'0' + b']' * 2000,
])
def test_invalid_outer_json_falls_back(service, provider, payload):
    provider[0].append((payload, 'chunked', 200, {}))
    assert_fallback(service)


@pytest.mark.parametrize('content', [
    'not-json', 'null', '{"answer": 42, "citations": []}',
    json.dumps({'answer': 'x' * 6001, 'citations': ['kafka-lag:1']}),
    '[' * 2000 + '0' + ']' * 2000,
])
def test_invalid_generated_json_falls_back(service, provider, content):
    body = envelope(service, message={'content': content})
    provider[0].append((body, 'fixed', 200, {}))
    assert_fallback(service)


@pytest.mark.parametrize('case', ['gzip', 'redirect', 'server-error', 'disconnect'])
def test_transport_rejection_preserves_source(service, provider, case):
    body = envelope(service)
    status, framing, headers = 200, 'fixed', {}
    if case == 'gzip':
        body, headers = gzip.compress(body), {'Content-Encoding': 'gzip'}
    elif case == 'redirect':
        status, headers = 307, {'Location': '/redirected'}
    elif case == 'server-error':
        status = 500
    else:
        framing = 'truncated'
    provider[0].append((body, framing, status, headers))
    assert_fallback(service)
    assert len(provider[1]) == 1  # No redirect follow or automatic retry.


@pytest.mark.parametrize('case', ['declared-excess', 'encoding', 'unknown-length', 'timeout'])
def test_stream_is_bounded_and_closed(service, monkeypatch, case):
    class ProbeStream(httpx.AsyncByteStream):
        chunks = 0
        closed = False

        async def __aiter__(self):
            if case == 'timeout':
                raise httpx.ReadTimeout('Controlled provider timeout')
            for _ in range(100):
                self.chunks += 1
                yield b' ' * 8192

        async def aclose(self):
            self.closed = True

    stream = ProbeStream()
    headers = {}
    if case == 'declared-excess':
        headers['Content-Length'] = str(LIMIT + 1)
    elif case == 'encoding':
        headers['Content-Encoding'] = 'gzip'

    async def reply(self, request):
        return httpx.Response(200, headers=headers, stream=stream)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', reply)
    assert_fallback(service)
    assert stream.closed
    assert stream.chunks == (9 if case == 'unknown-length' else 0)


def test_api_returns_fallback_after_provider_rejection(service, provider):
    provider[0].append((envelope(service, done_reason='length'), 'chunked', 200, {}))
    with TestClient(app) as client:
        original = client.post('/api/triage', json={'query': QUERY}).json()
        response = client.post('/api/triage', json={'query': QUERY, 'use_llm': True})
    assert response.status_code == 200
    result = response.json()
    assert result['warning'] and result['mode'] == 'extractive'
    for field in ('answer', 'citations', 'sources', 'answerability', 'routing'):
        assert result[field] == original[field]
