"""Sequential local-process corpus rollout with guarded writes and a progress journal."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from time import time

from .corpus_control import _unique, inspect_corpus, refresh
from .corpus_release import verify_release
from .corpus_snapshot import CorpusSnapshot, validate_identity
from .retrieval import Retriever

MAX_PLAN_BYTES = 65536
MAX_WORKERS = 32


def prepare(raw):
    """Validate the whole plan and build the target before contacting any worker."""
    if len(raw) > MAX_PLAN_BYTES:
        raise ValueError('Plan exceeds 64 KiB')
    plan = json.loads(raw, object_pairs_hook=_unique)
    if not isinstance(plan, dict) or set(plan) != {'release', 'manifest_sha256', 'workers'}:
        raise ValueError('Expected release, manifest_sha256 and workers')
    if not isinstance(plan['release'], str) or not Path(plan['release']).is_absolute():
        raise ValueError('Release must be an absolute path')
    workers = plan['workers']
    if not isinstance(workers, list) or not 1 <= len(workers) <= MAX_WORKERS:
        raise ValueError('Expected 1..32 workers')
    names, sockets = set(), set()
    for worker in workers:
        if not isinstance(worker, dict) or set(worker) != {'id', 'socket', 'expected_corpus'}:
            raise ValueError('Invalid worker fields')
        name, address = worker['id'], worker['socket']
        if not isinstance(name, str) or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', name) is None:
            raise ValueError('Invalid worker ID')
        if not isinstance(address, str) or '\x00' in address or not Path(address).is_absolute():
            raise ValueError('Worker socket must be an absolute path')
        # Reject lexical/path aliases, but do not require workers to be reachable.
        if str(Path(address).resolve()) != address:
            raise ValueError('Worker socket aliases are not accepted')
        if name in names or address in sockets:
            raise ValueError('Duplicate worker ID or socket')
        names.add(name)
        sockets.add(address)
        worker['expected_corpus'] = validate_identity(worker['expected_corpus'])
    digest = plan['manifest_sha256']
    if not isinstance(digest, str) or re.fullmatch(r'[0-9a-f]{64}', digest) is None:
        raise ValueError('Expected a saved lowercase SHA-256 pin')
    release = verify_release(Path(plan['release']), expected_manifest_hash=digest)
    target = CorpusSnapshot.capture(Retriever(documents=release.documents),
        corpus_id=release.corpus_id, manifest_sha256=release.manifest_hash).identity()
    # Resolve the source once, like the service release verifier.
    plan['release'] = str(release.release_path)
    return plan, target


def run(raw, journal):
    plan, target = prepare(raw)
    # Exclusive creation prevents accidentally overwriting another run's evidence.
    descriptor = os.open(journal, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as output:
        def record(event):
            output.write(json.dumps({'time_unix': time(), **event}, sort_keys=True) + '\n')
            output.flush()
            os.fsync(output.fileno())
        record({'phase': 'planned', 'plan_sha256': sha256(raw).hexdigest(),
                'target': target, 'workers': [w['id'] for w in plan['workers']]})
        applied = 0
        for phase in ('apply', 'verify'):
            for worker in plan['workers']:
                try:
                    result = (refresh(worker['socket'], plan['release'], plan['manifest_sha256'],
                                      expected_corpus=worker['expected_corpus']) if phase == 'apply'
                              else inspect_corpus(worker['socket']))
                    if result['status'] == 'ok' and result['corpus'] != target:
                        result = {'status': 'identity_mismatch', 'corpus': result['corpus']}
                except (OSError, ValueError, RecursionError):
                    # The refresh may have committed before the reply was lost.
                    result = {'status': 'ambiguous' if phase == 'apply' else 'unavailable'}
                record({'phase': phase, 'worker': worker['id'], 'result': result})
                if result['status'] != 'ok':
                    record({'phase': 'stopped', 'workers_acknowledged': applied})
                    return False
                if phase == 'apply':
                    applied += 1
        record({'phase': 'complete', 'workers_acknowledged': applied})
        return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--journal', type=Path, required=True)
    args = parser.parse_args()
    try:
        with args.plan.open('rb') as plan_file:
            raw = plan_file.read(MAX_PLAN_BYTES + 1)
        complete = run(raw, args.journal)
    except (OSError, ValueError, RecursionError):
        parser.exit(2, 'Rollout could not finish; inspect the journal and each worker before further action.\n')
    print(json.dumps({'status': 'complete' if complete else 'stopped'}))
    raise SystemExit(0 if complete else 1)


if __name__ == '__main__':
    main()
