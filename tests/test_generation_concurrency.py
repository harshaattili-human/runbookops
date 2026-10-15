"""Latch real provider requests to check admission without sleep-based ordering."""
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Event, Lock, Thread

from fastapi.testclient import TestClient
import pytest

from runbookops.api import app
from runbookops.service import TriageService

QUERY = 'Kafka consumer lag increases while producers send more events.'
OTHER = 'Requests time out acquiring a HikariPool database connection. Active connections are at the maximum and pending requests keep rising.'


@pytest.mark.parametrize('first_reply', ['valid', 'http-error', 'invalid-json'])
def test_busy_generation_preserves_each_request_and_releases_capacity(monkeypatch, first_reply):
    for name in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('OLLAMA_MODEL', 'synthetic-admission-fixture')
    entered, release = Event(), Event()
    lock = Lock()
    requests = 0

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def do_POST(self):
            nonlocal requests
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            with lock:
                requests += 1
                ordinal = requests
                if requests == 2:
                    entered.set()
            ready = release.wait(timeout=10)
            evidence = json.loads(payload['messages'][1]['content'])['evidence']
            body = json.dumps({'done': True, 'done_reason': 'stop', 'message': {'content': json.dumps({
                'answer': 'Synthetic completed response.', 'citations': [evidence[0]['id']]})}}).encode()
            status = 200
            if (ordinal <= 2 and first_reply == 'http-error') or not ready:
                status = 503
            elif ordinal <= 2 and first_reply == 'invalid-json':
                body = b'{invalid'
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=lambda: server.serve_forever(poll_interval=.01), daemon=True)
    thread.start()
    monkeypatch.setenv('OLLAMA_BASE_URL', f'http://127.0.0.1:{server.server_port}')
    independent_service = TriageService()
    try:
        with TestClient(app) as client, ThreadPoolExecutor(max_workers=2) as executor:
            api_call = executor.submit(client.post, '/api/triage', json={'query': QUERY, 'use_llm': True})
            service_call = executor.submit(independent_service.triage, QUERY, True)
            try:
                assert entered.wait(timeout=5), 'Two provider requests did not arrive'
                baseline = client.post('/api/triage', json={'query': OTHER}).json()
                rejected = client.post('/api/triage', json={'query': OTHER, 'use_llm': True})
                assert rejected.status_code == 200
                busy = rejected.json()
                assert busy['warning'] == 'Local generation is busy. Showing source text instead.'
                for field in ('answer', 'citations', 'sources', 'routing', 'answerability', 'mode'):
                    assert busy[field] == baseline[field], field
                abstained = client.post('/api/triage', json={
                    'query': 'How should I bake a chocolate cake?', 'use_llm': True}).json()
                assert abstained['mode'] == 'abstained' and abstained['warning'] is None
                assert client.get('/healthz').status_code == 200
                with lock:
                    assert requests == 2, 'Busy or unsupported requests reached the provider'
                assert not api_call.done() and not service_call.done(), 'Provider latch released early'
            finally:
                release.set()
            response = api_call.result(timeout=5)
            assert response.status_code == 200
            admitted = [response.json(), service_call.result(timeout=5)]
            for result in admitted:
                assert result['mode'] == ('local-llm' if first_reply == 'valid' else 'extractive')
            # Both slots must be reusable after completion or caught provider failures.
            retried = [executor.submit(independent_service.triage, QUERY, True) for _ in range(2)]
            assert all(f.result(timeout=5)['mode'] == 'local-llm' for f in retried)
            with lock:
                assert requests == 4
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()
