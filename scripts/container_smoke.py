"""Check a built Linux image through its published loopback port.

Uses only the Python standard library and Docker CLI. No checkout mounts, local
model, cloud credentials or application packages on the host are required.
"""

import argparse
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
QUERY = 'HikariPool timeout waiting for a database connection; pending connections are rising.'
# The check targets a local container, regardless of the host's proxy settings.
HTTP = build_opener(ProxyHandler({}))


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def docker(*args):
    result = subprocess.run(['docker', *args], text=True, capture_output=True, timeout=30)
    if result.returncode:
        raise RuntimeError(f'docker {args[0]} failed: {result.stderr.strip()}')
    return result.stdout.strip()


def inspect(name):
    return json.loads(docker('inspect', name))[0]


def wait_healthy(name):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        state = inspect(name)['State']
        require(state['Running'], f'Container exited during startup: {state}')
        health = state.get('Health', {}).get('Status')
        require(health is not None, 'Image has no Docker health check')
        if health == 'healthy':
            return
        require(health != 'unhealthy', f'Docker health check failed: {state["Health"]}')
        time.sleep(1)
    raise RuntimeError('Container did not become healthy within 120 seconds')


def request(base, path, body=None, expected=200):
    data = json.dumps(body).encode() if body is not None else None
    req = Request(base + path, data=data, headers={'Content-Type': 'application/json'})
    try:
        response = HTTP.open(req, timeout=10)
    except HTTPError as error:
        response = error
    with response:
        content = response.read()
        require(response.status == expected,
                f'{path}: expected HTTP {expected}, got {response.status}: {content[:200]!r}')
        return content, response.headers.get_content_type()


def get_json(base, path, body=None):
    content, content_type = request(base, path, body)
    require(content_type == 'application/json', f'{path}: expected JSON, got {content_type}')
    return json.loads(content)


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = set()

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == 'script' or (tag == 'link' and attributes.get('rel') == 'stylesheet'):
            path = attributes.get('src' if tag == 'script' else 'href', '')
            require(path.startswith('/assets/'), f'Unexpected frontend asset URL: {path}')
            self.paths.add(path)


def check_http(base):
    expected_documents = {p.stem: p.read_text() for p in (ROOT / 'data/runbooks').glob('*.md')}
    health = get_json(base, '/healthz')
    require(health == {'status': 'ok', 'documents': len(expected_documents)}, 'Wrong health payload')
    overview = get_json(base, '/api/overview')
    require({r['id'] for r in overview['runbooks']} == set(expected_documents), 'Packaged runbooks differ')
    require(overview['incidents'] == len(json.loads((ROOT / 'data/incidents.json').read_text())),
            'Packaged incident count differs')
    require(overview['evaluation'] == json.loads((ROOT / 'reports/evaluation.json').read_text()),
            'Packaged evaluation report differs')
    for slug, content in expected_documents.items():
        require(get_json(base, '/api/runbooks/' + slug) == {
                    'id': slug, 'content': content,
                    'content_hash': sha256(content.encode('utf-8')).hexdigest()},
                f'Packaged source differs: {slug}')

    html, content_type = request(base, '/')
    require(content_type == 'text/html' and b'id="root"' in html, 'Missing frontend entry point')
    assets = Assets()
    assets.feed(html.decode())
    require(any(p.endswith('.js') for p in assets.paths), 'No compiled JavaScript linked')
    require(any(p.endswith('.css') for p in assets.paths), 'No compiled CSS linked')
    for path in sorted(assets.paths):
        content, content_type = request(base, path)
        expected_type = {'text/css'} if path.endswith('.css') else {'text/javascript', 'application/javascript'}
        require(content and content_type in expected_type, f'Missing or incorrect asset: {path}')

    result = get_json(base, '/api/triage', {'query': QUERY})
    require(result['mode'] == 'extractive' and result['routing']['category'] == 'database',
            'Supported database incident did not return an extractive route')
    require(result['sources'][0]['document'] == 'database-pool', 'Wrong top runbook')
    for source in result['sources']:
        expected_hash = sha256(expected_documents[source['document']].encode('utf-8')).hexdigest()
        require(source['document_hash'] == expected_hash, 'Evidence snapshot hash differs')
        path = '/api/runbooks/' + source['document']
        checked = get_json(base, path + '?expected_hash=' + expected_hash)
        require(checked['content'] == expected_documents[source['document']], 'Versioned source differs')
        conflict, _ = request(base, path + '?expected_hash=' + '0' * 64, expected=409)
        require('content' not in json.loads(conflict), 'Conflict leaked a different document version')
        lines = expected_documents[source['document']].splitlines()
        require('\n'.join(lines[source['start_line'] - 1:source['end_line']]).strip() == source['text'],
                f'Incorrect source lines: {source["id"]}')
    require(result['citations'] == [result['sources'][0]['id']], 'Incorrect extractive citation')
    require(result['answer'] in result['sources'][0]['text'], 'Answer is not a source extract')

    for query, status in [
        ('Redis cache keys disappear under memory pressure. How do I inspect and change its eviction policy?',
         'insufficient'),
        ('How do I bake chocolate brownies for a birthday party?', 'no-match'),
    ]:
        withheld = get_json(base, '/api/triage', {'query': query})
        require(withheld['mode'] == 'abstained' and withheld['answerability']['status'] == status
                and withheld['sources'] == [] and withheld['citations'] == []
                and withheld['routing']['needs_review'], f'Unexpected abstention for {status}')

    fallback = get_json(base, '/api/triage', {'query': QUERY, 'use_llm': True})
    require(fallback['mode'] == 'extractive' and fallback['warning']
            and fallback['answer'] == result['answer'] and fallback['citations'] == result['citations'],
            'Missing local model did not fall back to source text')
    request(base, '/api/triage', {'query': 'short'}, expected=422)
    request(base, '/api/triage', {'query': QUERY, 'provider_url': 'http://example.invalid'}, expected=422)
    for path in ['/api/runbooks/unknown', '/data/incidents.json', '/backend/runbookops/api.py', '/.env']:
        request(base, path, expected=404)
    print(f'HTTP checks passed: {len(expected_documents)} packaged runbooks, report, '
          f'{len(assets.paths)} frontend assets, source lines/hashes, version conflicts, '
          'abstention, fallback and validation', flush=True)
    return result


def check_image(image):
    docker('image', 'inspect', image)
    name = 'runbookops-smoke-' + uuid4().hex[:12]
    try:
        docker('run', '--pull=never', '--detach', '--name', name, '--read-only',
               '--tmpfs', '/tmp:rw,noexec,nosuid,size=64m', '--cap-drop=ALL',
               '--security-opt=no-new-privileges', '--publish', '127.0.0.1::8000',
               '--health-interval=1s', '--health-start-period=30s', '--env', 'OLLAMA_MODEL=', image)
        wait_healthy(name)
        container = inspect(name)
        binding = container['NetworkSettings']['Ports']['8000/tcp']
        require(len(binding) == 1 and binding[0]['HostIp'] == '127.0.0.1', 'Port is not loopback-only')
        require(docker('exec', name, 'id', '-u') == '10001', 'Image is not running as the expected non-root UID')
        require(container['HostConfig']['ReadonlyRootfs'], 'Root filesystem is writable')
        base = 'http://127.0.0.1:' + binding[0]['HostPort']
        initial = check_http(base)
        runtime = docker('exec', name, 'python', '-c',
                         'import json,platform; from importlib.metadata import version; '
                         'print(json.dumps({"python":platform.python_version(),"architecture":platform.machine(),'
                         '"packages":{n:version(n) for n in ["fastapi","uvicorn","scikit-learn","numpy","httpx"]}}))')
        print(json.dumps({'image_id': container['Image'],
                          'docker_server': docker('version', '--format', '{{.Server.Version}}'),
                          'runtime': json.loads(runtime)}, indent=2), flush=True)
        docker('stop', '--timeout', '10', name)
        state = inspect(name)['State']
        require(state['ExitCode'] == 0 and not state['OOMKilled'], f'Unclean shutdown: {state}')
        docker('start', name)
        wait_healthy(name)
        # Docker may allocate a different ephemeral host port when starting again.
        binding = inspect(name)['NetworkSettings']['Ports']['8000/tcp']
        require(len(binding) == 1 and binding[0]['HostIp'] == '127.0.0.1', 'Restart changed port exposure')
        base = 'http://127.0.0.1:' + binding[0]['HostPort']
        restarted = get_json(base, '/api/triage', {'query': QUERY})
        for field in ('routing', 'sources', 'answer', 'citations', 'mode', 'answerability'):
            require(restarted[field] == initial[field], f'Restart changed {field}')
        print('Non-root read-only container, Docker health check, clean shutdown and restart checks passed', flush=True)
    finally:
        # Keep diagnostics on failure, then remove only this run's uniquely named container.
        try:
            subprocess.run(['docker', 'logs', '--tail', '60', name], check=False, timeout=15)
        finally:
            subprocess.run(['docker', 'rm', '--force', name], check=False, timeout=15)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='runbookops:smoke', help='Already-built local image tag')
    check_image(parser.parse_args().image)
