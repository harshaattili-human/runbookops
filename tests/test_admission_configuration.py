"""Trusted startup configuration and real-process admission contract."""

import os
from pathlib import Path
import sys

import pytest

from runbookops.admission import TriageAdmission
from test_corpus_startup import _server


@pytest.mark.parametrize('value', ['', '0', '-1', '1001', '1.5', 'true', ' 2', '2 ', '+2', '02', '２', '1_000'])
def test_invalid_environment_fails_closed(monkeypatch, value):
    monkeypatch.setenv('RUNBOOKOPS_TRIAGE_CAPACITY', value)
    with pytest.raises(ValueError):
        TriageAdmission(None)


@pytest.mark.parametrize('value,expected', [(None, 8), ('1', 1), ('2', 2), ('1000', 1000)])
def test_environment_is_selected_once(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv('RUNBOOKOPS_TRIAGE_CAPACITY', raising=False)
    else:
        monkeypatch.setenv('RUNBOOKOPS_TRIAGE_CAPACITY', value)
    admission = TriageAdmission(None)
    monkeypatch.setenv('RUNBOOKOPS_TRIAGE_CAPACITY', 'invalid')
    for _ in range(expected):
        assert admission.slots.acquire(blocking=False)
    assert not admission.slots.acquire(blocking=False)
    for _ in range(expected):
        admission.slots.release()
    # A trusted embedder can override inherited configuration explicitly.
    explicit = TriageAdmission(None, 2)
    assert explicit.slots.acquire(False) and explicit.slots.acquire(False)
    assert not explicit.slots.acquire(False)


@pytest.mark.skipif(os.name != 'posix', reason='Inherited-socket process check targets POSIX')
def test_configured_stock_process_saturates_recovers_and_rejects_invalid_startup():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'scripts'))
    try:
        from admission_smoke import check_capacity
    finally:
        sys.path.pop(0)
    env = {**os.environ, 'RUNBOOKOPS_TRIAGE_CAPACITY': '2', 'PYTHONPATH': str(root / 'backend')}
    with _server(env) as base:
        check_capacity(base, 2)
    with _server({**env, 'RUNBOOKOPS_TRIAGE_CAPACITY': 'invalid'},
                 expected_failure='RUNBOOKOPS_TRIAGE_CAPACITY must be an integer in 1..1000'):
        pass
