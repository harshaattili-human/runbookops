"""Retain per-trial success, rejection and latency denominators from a saved run."""
import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path


def summarize(raw):
    report = json.loads(raw)
    if report['status'] != 'completed' or not report['valid'] or not all(report['recovery_matches']):
        raise ValueError('Expected a complete valid run with recovery')
    groups = []
    clients = report['protocol']['clients']
    if len(report['cells']) != len(clients) * report['protocol']['repetitions']:
        raise ValueError('Missing cells')
    for count in clients:
        cells = [c for c in report['cells'] if c['concurrency'] == count]
        if len(cells) != report['protocol']['repetitions']:
            raise ValueError('Missing repetitions')
        for cell in cells:
            if (len(cell['samples']) != report['protocol']['requests_per_cell']
                    or cell['attempts'] != len(cell['samples'])
                    or not all(s['valid'] for s in cell['samples'])):
                raise ValueError('Invalid sample denominator')
        groups.append({'clients': count, 'attempts': sum(c['attempts'] for c in cells),
                       'trials': [{k: v for k, v in c.items() if k != 'samples'} for c in cells]})
    return {'raw_sha256': sha256(raw).hexdigest(), 'image_id': report['image_id'],
            'protocol': report['protocol'], 'groups': groups}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    raw = args.report.read_bytes()
    if args.report.suffix == '.gz':
        raw = gzip.decompress(raw)
    print(json.dumps(summarize(raw), indent=2))
