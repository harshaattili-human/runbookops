"""Rehearse pinned corpus selection in a built image using disposable bind mounts."""

import argparse
import errno
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from uuid import uuid4

from container_smoke import docker, get_json, inspect, request, require, wait_healthy


QUERY = 'Database connection timeout with pending requests and active connections.'
DOCUMENT = ('# Database pool\n\n## Inspect\n'
            'Database connection timeout: inspect active connections and pending requests.\n'
            'Synthetic release {version}: compare the connection metrics before changing configuration.\n')


def create_fixture(image, root, version):
    source, releases = root / ('source-' + version), root / 'releases'
    source.mkdir()
    releases.mkdir(exist_ok=True)
    text = DOCUMENT.format(version=version)
    (source / 'database-pool.md').write_text(text, encoding='utf-8')
    # Only this producer uses the host UID, so temporary artifacts remain cleanable.
    # API containers retain the image's default UID 10001.
    receipt = json.loads(docker(
        'run', '--rm', '--pull=never', '--network=none', '--read-only',
        '--user', f'{os.getuid()}:{os.getgid()}', '--cap-drop=ALL',
        '--security-opt=no-new-privileges', '--tmpfs', '/tmp:rw,noexec,nosuid,size=64m',
        '--mount', f'type=bind,src={source},dst=/source,readonly',
        '--mount', f'type=bind,src={releases},dst=/releases',
        image, 'python', '-m', 'runbookops.corpus_release', '--source', '/source',
        '--releases', '/releases', '--corpus-id', version))
    release = releases / version
    # The publisher intentionally creates a private directory (0700). This public
    # synthetic fixture grants traversal to the different API UID explicitly.
    release.chmod(0o755)
    for entry in release.iterdir():
        entry.chmod(0o644)
    digest = sha256((release / 'manifest.json').read_bytes()).hexdigest()
    require(receipt['manifest_sha256'] == digest and receipt['documents'] == 1
            and receipt['corpus_id'] == version,
            'Packaged publisher receipt differs from its files')
    return release, digest, text


@contextmanager
def selected_container(image, release, pin, *, failure=None):
    name = 'runbookops-corpus-' + uuid4().hex[:12]
    try:
        docker('run', '--pull=never', '--detach', '--name', name, '--read-only',
               '--tmpfs', '/tmp:rw,noexec,nosuid,size=64m', '--cap-drop=ALL',
               '--security-opt=no-new-privileges', '--publish', '127.0.0.1::8000',
               '--health-interval=1s', '--health-start-period=30s',
               '--mount', f'type=bind,src={release},dst=/corpus,readonly',
               '--env', 'RUNBOOKOPS_CORPUS_RELEASE=/corpus',
               '--env', 'RUNBOOKOPS_CORPUS_SHA256=' + pin, '--env', 'OLLAMA_MODEL=', image)
        if failure:
            deadline = time.monotonic() + 30
            while inspect(name)['State']['Running'] and time.monotonic() < deadline:
                time.sleep(.1)
            state = inspect(name)['State']
            require(not state['Running'] and state['ExitCode'] != 0 and not state['OOMKilled'],
                    f'Invalid release did not fail startup: {state}')
            captured = subprocess.run(['docker', 'logs', name], text=True,
                                      capture_output=True, timeout=15, check=True)
            logs = captured.stdout + captured.stderr
            require(failure in logs and 'Application startup complete' not in logs,
                    'Startup did not fail for the expected release-validation reason')
        else:
            wait_healthy(name)
            details = inspect(name)
            require(docker('exec', name, 'id', '-u') == '10001', 'API UID changed')
            require(details['HostConfig']['ReadonlyRootfs'], 'API root is writable')
            mounts = [m for m in details['Mounts'] if m['Destination'] == '/corpus']
            require(len(mounts) == 1 and not mounts[0]['RW']
                    and mounts[0]['Source'] == str(release.resolve()), 'Wrong release mount')
            # API permissions may reject the open before the read-only check.
            # The owning UID has file write permission and isolates the mount check.
            for uid, allowed in (('10001', (errno.EACCES, errno.EROFS)),
                                 (f'{os.getuid()}:{os.getgid()}', (errno.EROFS,))):
                docker('exec', '--user', uid, name, 'python', '-c',
                       'from pathlib import Path\n'
                       'for name in ("manifest.json", "database-pool.md"):\n'
                       ' try:\n  with (Path("/corpus") / name).open("a"): pass\n'
                       f' except OSError as error: assert error.errno in {allowed!r}\n'
                       ' else: raise AssertionError("Release mount accepted a write")')
        yield name
    finally:
        # Only this run's uniquely named containers are removed.
        subprocess.run(['docker', 'logs', '--tail', '35', name], check=False, timeout=15)
        subprocess.run(['docker', 'rm', '--force', name], check=False, timeout=15)


def base_url(name):
    binding = inspect(name)['NetworkSettings']['Ports']['8000/tcp']
    require(len(binding) == 1 and binding[0]['HostIp'] == '127.0.0.1', 'Port is not loopback-only')
    return 'http://127.0.0.1:' + binding[0]['HostPort']


def check_loaded(name, text):
    base, digest = base_url(name), sha256(text.encode('utf-8')).hexdigest()
    require(get_json(base, '/healthz') == {'status': 'ok', 'documents': 1}, 'Bundled corpus loaded')
    require([r['id'] for r in get_json(base, '/api/overview')['runbooks']] == ['database-pool'],
            'Selected inventory differs')
    source = get_json(base, '/api/runbooks/database-pool?expected_hash=' + digest)
    require(source['content'] == text and source['content_hash'] == digest, 'Selected source differs')
    result = get_json(base, '/api/triage', {'query': QUERY})
    require(result['mode'] == 'extractive' and result['sources'], 'Selected corpus did not answer')
    for evidence in result['sources']:
        require(evidence['document_hash'] == digest, 'Triage used a different snapshot')
        lines = text.splitlines()[evidence['start_line'] - 1:evidence['end_line']]
        require('\n'.join(lines).strip() == evidence['text'], 'Selected source lines differ')
    return digest


def check_releases(image, receipt_path):
    receipt_path.unlink(missing_ok=True)
    image_id = json.loads(docker('image', 'inspect', image))[0]['Id']
    image = image_id
    with tempfile.TemporaryDirectory(prefix='runbookops-corpus-check-') as directory:
        root = Path(directory)
        a, pin_a, text_a = create_fixture(image, root, 'release-a')
        b, pin_b, text_b = create_fixture(image, root, 'release-b')
        with selected_container(image, a, pin_a) as first:
            hash_a = check_loaded(first, text_a)
            docker('stop', '--timeout', '10', first)
            require(inspect(first)['State']['ExitCode'] == 0, 'Pinned container did not stop cleanly')
            docker('start', first)
            wait_healthy(first)
            require(check_loaded(first, text_a) == hash_a, 'Restart changed selected release')
            with selected_container(image, b, pin_b) as second:
                hash_b = check_loaded(second, text_b)
                require(hash_a != hash_b, 'Fixture releases must differ')
                # Coexistence exposes a staggered rollout's two snapshots explicitly.
                check_loaded(first, text_a)
                for name, other in ((first, hash_b), (second, hash_a)):
                    body, _ = request(base_url(name), '/api/runbooks/database-pool?expected_hash=' + other,
                                      expected=409)
                    require('content' not in json.loads(body), 'Conflict returned another version')
        with selected_container(image, a, pin_a) as rollback:
            require(check_loaded(rollback, text_a) == hash_a, 'Explicit rollback did not restore A')
        with selected_container(image, b, pin_a, failure='Release manifest does not match expected SHA-256'):
            pass
        # Deliberately mutate only the disposable fixture after all successful loads.
        (b / 'database-pool.md').write_text('tampered synthetic fixture', encoding='utf-8')
        with selected_container(image, b, pin_b, failure='Runbook hash does not match manifest'):
            pass
    receipt = {
        'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'image_id': image_id,
        'docker_server': docker('version', '--format', '{{.Server.Version}}'),
        'synthetic_generations': 2, 'documents_per_generation': 1,
        'manifest_sha256': {'release-a': pin_a, 'release-b': pin_b},
        'document_sha256': {'release-a': hash_a, 'release-b': hash_b},
        'checks': ['packaged release producer', 'UID 10001 and read-only mount write rejection',
                   'selected inventory/source/triage lines', 'same-pin clean restart',
                   'two coexisting generations and bidirectional 409', 'explicit rollback to A',
                   'stale manifest pin startup rejection', 'changed document startup rejection'],
        'limits': 'Synthetic local Linux Docker rehearsal; no coordinator, load, crash recovery or deployment.',
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(receipt, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='runbookops:smoke')
    parser.add_argument('--receipt', type=Path, default=Path('artifacts/corpus-container.json'))
    args = parser.parse_args()
    check_releases(args.image, args.receipt)
