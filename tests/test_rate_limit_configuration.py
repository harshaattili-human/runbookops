"""Fail-closed environment configuration for the optional request budget."""

import pytest

from runbookops.rate_limit import TriageRateLimit


@pytest.mark.parametrize('capacity,refill', [
    ('', '1'), ('0', '1'), ('10001', '1'), ('01', '1'), (' 2', '1'), ('2 ', '1'),
    ('1.5', '1'), ('true', '1'), ('１', '1'), ('1', ''), ('1', '0'), ('1', '60001'),
    ('1', '01'), ('1', '1.5'), ('1', ' 1'), ('1', '１')])
def test_invalid_environment_fails_closed(monkeypatch, capacity, refill):
    monkeypatch.setenv('RUNBOOKOPS_RATE_LIMIT_CAPACITY', capacity)
    monkeypatch.setenv('RUNBOOKOPS_RATE_LIMIT_REFILL_MS', refill)
    with pytest.raises(ValueError):
        TriageRateLimit(None)


@pytest.mark.parametrize('missing', ['capacity', 'refill'])
def test_partial_environment_fails_closed(monkeypatch, missing):
    monkeypatch.delenv('RUNBOOKOPS_RATE_LIMIT_CAPACITY', raising=False)
    monkeypatch.delenv('RUNBOOKOPS_RATE_LIMIT_REFILL_MS', raising=False)
    monkeypatch.setenv('RUNBOOKOPS_RATE_LIMIT_REFILL_MS' if missing == 'capacity'
                       else 'RUNBOOKOPS_RATE_LIMIT_CAPACITY', '10')
    with pytest.raises(ValueError, match='Set both'):
        TriageRateLimit(None)


def test_unset_is_disabled_and_configuration_is_read_once(monkeypatch):
    monkeypatch.delenv('RUNBOOKOPS_RATE_LIMIT_CAPACITY', raising=False)
    monkeypatch.delenv('RUNBOOKOPS_RATE_LIMIT_REFILL_MS', raising=False)
    assert TriageRateLimit(None).budget is None
    monkeypatch.setenv('RUNBOOKOPS_RATE_LIMIT_CAPACITY', '3')
    monkeypatch.setenv('RUNBOOKOPS_RATE_LIMIT_REFILL_MS', '250')
    limiter = TriageRateLimit(None)
    monkeypatch.setenv('RUNBOOKOPS_RATE_LIMIT_CAPACITY', 'invalid')
    assert limiter.budget.capacity == 3
    assert limiter.budget.refill_seconds == .25
