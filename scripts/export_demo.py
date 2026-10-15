"""Export a self-contained, explicitly labeled replay of real API responses.

Run after `npm run build`. Requires development dependencies and a checkout.
The replay supports the five sample incidents, source viewing, and evaluation;
it does not claim to execute Python inference in the browser.
"""

import base64
from datetime import datetime, timezone
from hashlib import sha256
import json
import mimetypes
from pathlib import Path
import re
import subprocess
import sys

from fastapi.testclient import TestClient
from runbookops.api import app
from runbookops.service import ROOT

queries = [
    'Requests time out acquiring a HikariPool database connection. Active connections are at the maximum and pending requests keep rising.',
    'Kafka consumer lag is increasing and the group keeps rebalancing. What should we inspect before considering a replay?',
    'A Camunda workflow service task exhausted its retries and the process instance is stuck after a downstream error.',
    'Redis cache keys disappear under memory pressure. How do I inspect and change its eviction policy?',
    'How do I bake chocolate brownies for a birthday party?',
]

with TestClient(app) as client:
    overview = client.get('/api/overview').raise_for_status().json()
    results = {q: client.post('/api/triage', json={'query': q, 'use_llm': False})
               .raise_for_status().json() for q in queries}
    documents = {r['id']: client.get('/api/runbooks/' + r['id']).raise_for_status().json()
                 for r in overview['runbooks']}

payload = json.dumps({'overview': overview, 'results': results, 'documents': documents}).replace('<', '\\u003c')
shim = """
window.RUNBOOKOPS_DEMO = true;
const fixtures = PAYLOAD;
window.fetch = async (path, options) => {
  let body;
  let status;
  const url = new URL(path, 'http://recorded.local');
  if (url.pathname === '/api/overview') body = fixtures.overview;
  else if (url.pathname === '/api/triage') {
    const request = JSON.parse(options.body);
    if (request.use_llm) {
      body = {detail:'Recorded replay does not run a local model.'};
      status = 422;
    } else body = fixtures.results[request.query];
  }
  else if (url.pathname.startsWith('/api/runbooks/')) {
    body = fixtures.documents[decodeURIComponent(url.pathname.split('/').pop())];
    if (body && url.searchParams.has('expected_hash') &&
        url.searchParams.get('expected_hash') !== body.content_hash) {
      body = {detail:'Runbook version changed; run triage again.'};
      status = 409;
    }
  }
  return new Response(JSON.stringify(body || {detail:'Choose a recorded scenario.'}), {status: status ?? (body ? 200 : 404), headers:{'Content-Type':'application/json'}});
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
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(html, encoding='utf-8')
inputs = [Path(__file__).resolve(), ROOT / 'reports/evaluation.json',
          *sorted((ROOT / 'backend/runbookops').glob('*.py')),
          *sorted((ROOT / 'data').rglob('*.json')),
          *sorted((ROOT / 'data/runbooks').glob('*.md')),
          *sorted(p for p in dist.rglob('*') if p.is_file())]
receipt = {
    'mode': 'recorded replay; no browser inference or live model',
    'generated_at': datetime.now(timezone.utc).isoformat(),
    'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
    'tracked_changes': bool(subprocess.check_output(['git', 'diff', 'HEAD', '--name-only'], cwd=ROOT)),
    'html_sha256': sha256(destination.read_bytes()).hexdigest(),
    'python': sys.version.split()[0],
    'scenario_count': len(results), 'document_count': len(documents),
    'scenarios': [{'query': q, 'mode': result['mode'],
                   'answerability': result['answerability']['status']} for q, result in results.items()],
    'document_hashes': {slug: document['content_hash'] for slug, document in documents.items()},
    'input_sha256': {str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest() for p in inputs},
}
destination.with_suffix('.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
print(f'Created {destination.name}: {destination.stat().st_size} bytes; {len(results)} recorded scenarios')
