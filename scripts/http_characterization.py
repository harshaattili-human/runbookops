"""Closed-loop HTTP characterization of an owned, resource-limited local image.

No remote target option, LLM calls, holdout queries or latency pass/fail threshold.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from http.client import HTTPConnection
import json
import math
import os
from pathlib import Path
import platform
import subprocess
from threading import Barrier
from time import perf_counter
from uuid import uuid4

from container_smoke import docker, inspect, wait_healthy

ROOT = Path(__file__).resolve().parents[1]
LEVELS = (1, 2, 4, 8, 16)
REQUESTS = 1024
QUERIES = (
    'HikariPool timeout waiting for a database connection; pending connections are rising.',
    'Workflow jobs are stuck pending and the queue backlog is growing. How can I investigate?',
    'How do I bake chocolate brownies for a birthday party?',
    'Redis cache keys disappear under memory pressure. How do I inspect and change its eviction policy?',
)


def percentile(values, fraction):
    """Nearest-rank quantile; empty groups have no latency estimate."""
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


def fingerprint(payload):
    # Compare every decision/evidence field, excluding only per-request diagnostics.
    stable = {k: v for k, v in payload.items() if k not in ('request_id', 'duration_ms')}
    return sha256(json.dumps(stable, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def request(port, query):
    connection = HTTPConnection('127.0.0.1', port, timeout=15)
    started = perf_counter()
    try:
        connection.request('POST', '/api/triage', body=json.dumps({'query': query, 'use_llm': False}),
                           headers={'Content-Type': 'application/json', 'Connection': 'close'})
        response = connection.getresponse()
        raw = response.read(262145)
        elapsed = (perf_counter() - started) * 1000
        if len(raw) > 262144:
            raise ValueError('Response exceeds characterization bound')
        return {'status': response.status, 'milliseconds': elapsed,
                'payload': json.loads(raw), 'bytes': len(raw),
                'no_store': response.getheader('Cache-Control') == 'no-store'}
    except (OSError, ValueError) as failure:
        return {'status': 'transport_error', 'milliseconds': (perf_counter() - started) * 1000,
                'error_type': type(failure).__name__}
    finally:
        connection.close()


def summarize(samples, seconds):
    result = {'attempts': len(samples), 'wall_seconds': seconds,
              'attempts_per_second': len(samples) / seconds, 'outcomes': {}}
    for status in sorted({str(row['status']) for row in samples}):
        values = [row['milliseconds'] for row in samples if str(row['status']) == status]
        result['outcomes'][status] = {'count': len(values), 'p50_ms': percentile(values, .5),
                                     'p95_ms': percentile(values, .95), 'max_ms': max(values)}
    result['successful_responses_per_second'] = sum(row['status'] == 200 for row in samples) / seconds
    result['invalid_responses'] = sum(not row['valid'] for row in samples)
    result['per_query'] = {
        str(query): {status: sum(row['query'] == query and str(row['status']) == status for row in samples)
                    for status in result['outcomes']}
        for query in sorted({row['query'] for row in samples})}
    return result


def cell(port, concurrency, expected):
    # Exactly concurrency clients, each with at most one outstanding request.
    # A thread does not submit its next request until the previous response completes.
    barrier = Barrier(concurrency + 1)
    origin = [0.0]
    def client(worker):
        barrier.wait(timeout=30)
        rows = []
        for index in range(worker, REQUESTS, concurrency):
            # Each client cycles all query types, including at 4/8/16 clients.
            query = (index // concurrency + worker) % len(QUERIES)
            offset = (perf_counter() - origin[0]) * 1000
            response = request(port, QUERIES[query])
            payload = response.pop('payload', None)
            valid = (response['status'] == 200 and isinstance(payload, dict)
                     and fingerprint(payload) == expected[query]['sha256'])
            if response['status'] == 503:
                valid = response['no_store'] and payload == {
                    'detail': 'Triage capacity exhausted. No analysis was started.'}
            rows.append({'request': index, 'client': worker, 'query': query,
                         'start_offset_ms': offset, 'valid': valid, **response})
        return rows
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(client, worker) for worker in range(concurrency)]
        origin[0] = perf_counter()
        barrier.wait(timeout=30)
        samples = [row for future in futures for row in future.result()]
        seconds = perf_counter() - origin[0]
    samples.sort(key=lambda row: row['request'])
    return {'concurrency': concurrency, **summarize(samples, seconds), 'samples': samples}


def run(image, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)  # Do not mistake a prior success for this run.
    image_id = docker('image', 'inspect', '--format', '{{.Id}}', image)
    name = 'runbookops-characterization-' + uuid4().hex[:12]
    report = {'schema_version': 1, 'status': 'incomplete', 'image_id': image_id,
              'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'tracked_changes': bool(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT)),
              'workload': list(QUERIES), 'workload_sha256': sha256(json.dumps(QUERIES).encode()).hexdigest(),
              'protocol': {'clients': list(LEVELS), 'requests_per_cell': REQUESTS,
                           'repetitions': len(LEVELS), 'warmup_requests': 12,
                           'connection': 'new HTTP/1 connection per request, no application retries',
                           'arrival': 'closed loop, zero think time; one synchronized start per cell',
                           'percentile': 'nearest rank, separated by HTTP outcome',
                           'selection': 'four authored synthetic smoke descriptions; no held-out data'},
              'host': {'python': platform.python_version(), 'platform': platform.platform(),
                       'cpu_count': os.cpu_count(), 'affinity': sorted(os.sched_getaffinity(0)),
                       'cpu_models': sorted({line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines()
                                             if line.startswith('model name')}),
                       'docker': docker('version', '--format', '{{.Server.Version}}')},
              'cells': []}
    try:
        docker('run', '--pull=never', '--detach', '--name', name, '--read-only', '--cpus=2',
               '--memory=512m', '--memory-swap=512m', '--tmpfs', '/tmp:rw,noexec,nosuid,size=64m',
               '--cap-drop=ALL', '--security-opt=no-new-privileges', '--publish', '127.0.0.1::8000',
               '--health-interval=1s', '--health-start-period=30s', image_id,
               'python', '-m', 'uvicorn', 'runbookops.api:app', '--host', '0.0.0.0',
               '--port', '8000', '--workers', '1', '--no-access-log')
        wait_healthy(name)
        container = inspect(name)
        binding = container['NetworkSettings']['Ports']['8000/tcp']
        if len(binding) != 1 or binding[0]['HostIp'] != '127.0.0.1':
            raise ValueError('Characterization must remain loopback only')
        port = int(binding[0]['HostPort'])
        report['limits'] = {key: container['HostConfig'][key]
                            for key in ('NanoCpus', 'Memory', 'MemorySwap', 'ReadonlyRootfs')}
        report['runtime'] = json.loads(docker('exec', name, 'python', '-c',
            'import json,platform; from importlib.metadata import version; '
            'print(json.dumps({"python":platform.python_version(),"packages":'
            '{n:version(n) for n in ["fastapi","uvicorn","scikit-learn","numpy","httpx2"]}}))'))
        expected = []
        for repeat in range(3):
            for index, query in enumerate(QUERIES):
                response = request(port, query)
                if response['status'] != 200:
                    raise ValueError('Sequential warmup failed')
                payload = response['payload']
                if repeat == 0:
                    expected.append({'sha256': fingerprint(payload), 'mode': payload['mode'],
                                     'corpus': payload['corpus']})
                elif fingerprint(payload) != expected[index]['sha256']:
                    raise ValueError('Sequential baseline is not stable')
        report['reference_responses'] = expected
        # Cyclic Latin square: each level occupies each position once.
        for repeat in range(len(LEVELS)):
            order = LEVELS[repeat:] + LEVELS[:repeat]
            for position, concurrency in enumerate(order):
                observation = {'repeat': repeat, 'position': position, **cell(port, concurrency, expected)}
                report['cells'].append(observation)
                output.write_text(json.dumps(report, indent=2) + '\n')
                print(json.dumps({k: v for k, v in observation.items() if k != 'samples'}), flush=True)
        recovery = [request(port, query) for query in QUERIES]
        report['recovery_matches'] = [r['status'] == 200 and fingerprint(r['payload']) == e['sha256']
                                      for r, e in zip(recovery, expected)]
        report['valid'] = (all(x['invalid_responses'] == 0 for x in report['cells'])
                           and all(report['recovery_matches']))
        report['status'] = 'completed'
        if not report['valid']:
            raise ValueError('Unexpected status, transport failure or changed decision; inspect raw report')
    finally:
        output.write_text(json.dumps(report, indent=2) + '\n')
        subprocess.run(['docker', 'rm', '--force', name], check=False, timeout=20,
                       stdout=subprocess.DEVNULL)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='runbookops:smoke')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/http-characterization.json')
    args = parser.parse_args()
    run(args.image, args.output)
