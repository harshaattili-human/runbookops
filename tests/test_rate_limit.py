"""Token-budget and ASGI boundary checks; these are not traffic benchmarks."""

import asyncio

import pytest

from runbookops.rate_limit import RequestBudget, TriageRateLimit


SCOPE = {'type': 'http', 'method': 'POST', 'path': '/api/triage',
         'headers': [], 'http_version': '1.1'}


class Clock:
    now = 100.0

    def __call__(self):
        return self.now


@pytest.mark.parametrize('capacity,refill', [(0, 1), (10001, 1), (True, 1), (1.5, 1),
                                              (1, 0), (1, 60001), (1, True), (1, 1.5)])
def test_budget_configuration_requires_bounded_integers(capacity, refill):
    with pytest.raises(ValueError):
        RequestBudget(capacity, refill)


def test_bucket_refills_continuously_without_clock_rollback_credit():
    clock = Clock()
    budget = RequestBudget(2, 1500, clock)
    assert budget.acquire() is None
    assert budget.acquire() is None
    assert budget.acquire() == 2
    clock.now += .75
    assert budget.acquire() == 1
    clock.now -= 100
    assert budget.acquire() == 1
    clock.now = 101.5
    assert budget.acquire() is None
    clock.now = 1000
    assert budget.acquire() is None
    assert budget.acquire() is None
    assert budget.acquire() == 2


def test_rejection_precedes_body_read_and_downstream_work():
    async def check():
        clock = Clock()
        budget = RequestBudget(1, 1000, clock)
        entered = 0
        delivered = []

        async def downstream(scope, receive, send):
            nonlocal entered
            entered += 1
            await send({'type': 'http.response.start', 'status': 204, 'headers': []})
            await send({'type': 'http.response.body', 'body': b''})

        async def receive():
            pytest.fail('Rate rejection read a request body')

        async def send(message):
            delivered.append(message)

        app = TriageRateLimit(downstream, budget=budget)
        await app(SCOPE, receive, send)
        await app(SCOPE, receive, send)
        assert entered == 1
        start = delivered[2]
        assert start['status'] == 429
        headers = dict(start['headers'])
        assert headers[b'cache-control'] == b'no-store'
        assert headers[b'retry-after'] == b'1'
        assert headers[b'connection'] == b'close'
        assert b'No analysis was started' in delivered[3]['body']
        await app({**SCOPE, 'path': '/healthz', 'method': 'GET'}, receive, send)
        assert entered == 2
        clock.now += 1
        await app(SCOPE, receive, send)
        assert entered == 3
    asyncio.run(check())
