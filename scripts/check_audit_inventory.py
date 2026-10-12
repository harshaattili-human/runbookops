"""Reject an empty/partial image scan before treating its vulnerability gate as useful."""
import json
from pathlib import Path
import re
import sys
import tomllib


def check_inventory(report, required):
    if report.get('SchemaVersion') != 2:
        raise ValueError('Expected Trivy JSON schema 2')
    results = report.get('Results', [])
    if not any(r.get('Class') == 'os-pkgs' and r.get('Packages') for r in results):
        raise ValueError('Image scan has no OS package inventory')
    packages = {
        re.sub(r'[-_.]+', '-', p['Name']).lower()
        for result in results if result.get('Type') == 'python-pkg'
        for p in result.get('Packages', [])
    }
    missing = set(required) - packages
    if missing:
        raise ValueError(f'Image scan missed runtime Python dependencies: {sorted(missing)}')
    findings = [v for r in results for v in r.get('Vulnerabilities', [])]
    blocking = [v for v in findings if v.get('Severity') in {'HIGH', 'CRITICAL'} and v.get('FixedVersion')]
    print(f'Inventoried {len(packages)} Python package names; {len(findings)} finding entries, '
          f'{len(blocking)} fixable high/critical entries (not unique CVEs).')


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / 'pyproject.toml').read_text())['project']
    required = [re.sub(r'[-_.]+', '-', dep.split('==')[0]).lower() for dep in project['dependencies']]
    check_inventory(json.loads(Path(sys.argv[1]).read_text()), required)
