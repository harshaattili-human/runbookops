"""Non-queuing admission around the complete triage HTTP lifecycle."""

from threading import BoundedSemaphore

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class TriageAdmission:
    def __init__(self, app: ASGIApp, capacity: int = 8):
        if type(capacity) is not int or not 1 <= capacity <= 1000:
            raise ValueError('Triage capacity must be an integer in 1..1000')
        self.app = app
        self.slots = BoundedSemaphore(capacity)

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if (scope['type'] != 'http' or scope['method'] != 'POST'
                or scope['path'] not in ('/api/triage', '/api/triage/')):
            await self.app(scope, receive, send)
            return
        if not self.slots.acquire(blocking=False):
            headers = {'Cache-Control': 'no-store'}
            if scope.get('http_version') in ('1.0', '1.1'):
                headers['Connection'] = 'close'
            await JSONResponse({'detail': 'Triage capacity exhausted. No analysis was started.'},
                               status_code=503, headers=headers)(scope, receive, send)
            return
        try:
            await self.app(scope, receive, send)
        finally:
            self.slots.release()
