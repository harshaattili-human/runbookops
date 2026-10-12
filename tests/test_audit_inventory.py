"""Synthetic scanner reports test missing-coverage failures, not real vulnerabilities."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('audit_inventory', Path(__file__).parents[1] / 'scripts/check_audit_inventory.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def report():
    return {'SchemaVersion': 2, 'Results': [
        {'Class': 'os-pkgs', 'Packages': [{'Name': 'libc6'}]},
        {'Type': 'python-pkg', 'Packages': [{'Name': 'scikit_learn'}, {'Name': 'fastapi'}]},
    ]}


def test_clean_report_still_requires_os_and_python_inventory():
    audit.check_inventory(report(), ['scikit-learn', 'fastapi'])


@pytest.mark.parametrize('value', [{}, {'SchemaVersion': 2, 'Results': []},
                                  {'SchemaVersion': 2, 'Results': [{'Class': 'os-pkgs', 'Packages': [{'Name': 'libc6'}]}]}])
def test_missing_scan_coverage_fails(value):
    with pytest.raises(ValueError):
        audit.check_inventory(value, ['fastapi'])
