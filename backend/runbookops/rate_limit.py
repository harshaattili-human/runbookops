"""Optional process-local request budget for the triage HTTP boundary."""

from dataclasses import dataclass
import math
import os
import re
from threading import Lock
import time
from typing import Callable

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


@dataclass(frozen=True)
class RateLimitConfiguration:
    capacity: int
    refill_ms: int


_UNSET = object()


def configuration_from_environment() -> RateLimitConfiguration | None:
    capacity = os.environ.get('RUNBOOKOPS_RATE_LIMIT_CAPACITY')
    refill_ms = os.environ.get('RUNBOOKOPS_RATE_LIMIT_REFILL_MS')
    if capacity is None and refill_ms is None:
        return None
    if capacity is None or refill_ms is None:
        raise ValueError('Set both RUNBOOKOPS_RATE_LIMIT_CAPACITY and RUNBOOKOPS_RATE_LIMIT_REFILL_MS')
    if (not re.fullmatch(r'[1-9][0-9]{0,4}', capacity)
            or not re.fullmatch(r'[1-9][0-9]{0,4}', refill_ms)
            or int(capacity) > 10000 or int(refill_ms) > 60000):
        raise ValueError('RunbookOps rate limit requires capacity 1..10000 and refill milliseconds 1..60000')
    return RateLimitConfiguration(int(capacity), int(refill_ms))


class RequestBudget:
    """A synchronized token bucket with a continuous monotonic refill."""

    def __init__(self, capacity: int, refill_ms: int,
                 clock: Callable[[], float] = time.monotonic):
        if type(capacity) is not int or not 1 <= capacity <= 10000:
            raise ValueError('Rate limit capacity must be an integer in 1..10000')
        if type(refill_ms) is not int or not 1 <= refill_ms <= 60000:
            raise ValueError('Rate limit refill milliseconds must be an integer in 1..60000')
        self.capacity = capacity
        self.refill_seconds = refill_ms / 1000
        self.clock = clock
        self.tokens = float(capacity)
        self.updated = clock()
        self.lock = Lock()

    def acquire(self) -> int | None:
        """Spend one token, or return a positive Retry-After value in seconds."""
        with self.lock:
            now = self.clock()
            elapsed = max(0.0, now - self.updated)
            self.tokens = min(float(self.capacity), self.tokens + elapsed / self.refill_seconds)
            self.updated = max(self.updated, now)
            if self.tokens >= 1:
                self.tokens -= 1
                return None
            return max(1, math.ceil((1 - self.tokens) * self.refill_seconds))


class TriageRateLimit:
    def __init__(self, app: ASGIApp,
                 configuration: RateLimitConfiguration | None | object = _UNSET,
                 budget: RequestBudget | None = None):
        self.app = app
        if configuration is _UNSET and budget is None:
            configuration = configuration_from_environment()
        if configuration is not _UNSET and configuration is not None and budget is not None:
            raise ValueError('Provide rate-limit configuration or a request budget, not both')
        self.budget = budget if budget is not None else (
            RequestBudget(configuration.capacity, configuration.refill_ms)
            if isinstance(configuration, RateLimitConfiguration) else None)

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if (self.budget is None or scope['type'] != 'http' or scope['method'] != 'POST'
                or scope['path'] not in ('/api/triage', '/api/triage/')):
            await self.app(scope, receive, send)
            return
        retry_after = self.budget.acquire()
        if retry_after is None:
            await self.app(scope, receive, send)
            return
        headers = {'Cache-Control': 'no-store', 'Retry-After': str(retry_after)}
        if scope.get('http_version') in ('1.0', '1.1'):
            headers['Connection'] = 'close'
        await JSONResponse(
            {'detail': 'Triage request budget exhausted. No analysis was started.'},
            status_code=429, headers=headers)(scope, receive, send)
