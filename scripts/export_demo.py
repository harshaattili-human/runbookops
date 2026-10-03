"""Export a self-contained, explicitly labeled replay of real API responses.

Run after `npm run build`. Requires development dependencies and a checkout.
The replay supports the four sample incidents, source viewing, and evaluation;
it does not claim to execute Python inference in the browser.
"""

import base64
import json
import mimetypes
from pathlib import Path
import re
import sys

from fastapi.testclient import TestClient
from runbookops.api import app
from runbookops.service import ROOT

queries = [
    'Requests time out acquiring a HikariPool database connection. Active connections are at the maximum and pending requests keep rising.',
    'Kafka consumer lag is increasing and the group keeps rebalancing. What should we inspect before considering a replay?',
    'A Camunda workflow service task exhausted its retries and the process instance is stuck after a downstream error.',
    'How do I bake chocolate brownies for a birthday party?',
]

with TestClient(app) as client:
    overview = client.get('/api/overview').json()
    results = {q: client.post('/api/triage', json={'query': q}).json() for q in queries}
    documents = {r['id']: client.get('/api/runbooks/' + r['id']).json()
                 for r in overview['runbooks']}

payload = json.dumps({'overview': overview, 'results': results, 'documents': documents}).replace('<', '\\u003c')
shim = """
window.RUNBOOKOPS_DEMO = true;
const fixtures = PAYLOAD;
window.fetch = async (path, options) => {
  let body;
  if (path === '/api/overview') body = fixtures.overview;
  else if (path === '/api/triage') body = fixtures.results[JSON.parse(options.body).query];
  else if (path.startsWith('/api/runbooks/')) body = fixtures.documents[decodeURIComponent(path.split('/').pop())];
  return new Response(JSON.stringify(body || {detail:'Choose a recorded scenario.'}), {status: body ? 200 : 404, headers:{'Content-Type':'application/json'}});
};
""".replace('PAYLOAD', payload)
dist = ROOT / 'frontend/dist'
html = (dist / 'index.html').read_text()
css = '\n'.join(p.read_text() for p in sorted((dist / 'assets').glob('*.css')))


def inline_asset(match):
    relative = match.group(1).strip('\"\'')
    asset = dist / relative.lstrip('/')
    if not asset.is_file():
        raise ValueError(f'Missing demo asset: {relative}')
    mime = mimetypes.guess_type(asset)[0] or 'application/octet-stream'
    return f'url(data:{mime};base64,{base64.b64encode(asset.read_bytes()).decode()})'


css = re.sub(r'url\(([^)]+)\)', inline_asset, css)
javascript = '\n'.join(p.read_text() for p in sorted((dist / 'assets').glob('*.js')))
javascript = javascript.replace('</script', '<\\/script')
html = re.sub(r'<script[^>]*src="[^"]+"[^>]*></script>', '', html)
html = re.sub(r'<link[^>]*rel="stylesheet"[^>]*>', '', html)
html = html.replace('</head>', '<style>' + css + '</style></head>')
html = html.replace('</body>', '<script>' + shim + '</script><script type="module">' + javascript + '</script></body>')
destination = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'RunbookOps-Demo.html'
destination.write_text(html)
print(f'Created {destination.name}: {destination.stat().st_size} bytes; {len(results)} recorded scenarios')
