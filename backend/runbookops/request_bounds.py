"""Count triage request bytes before FastAPI reads or parses JSON."""

import asyncio

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


MAX_TRIAGE_BYTES = 32_768
TRIAGE_UPLOAD_SECONDS = 30.0


class TriageBodyLimit:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if (scope['type'] != 'http' or scope['method'] != 'POST'
                or scope['path'] not in ('/api/triage', '/api/triage/')):
            await self.app(scope, receive, send)
            return

        async def reject(status: int, detail: str):
            await JSONResponse({'detail': detail}, status_code=status)(scope, receive, send)

        headers = [(name.lower(), value) for name, value in scope['headers']]
        encodings = [value.strip().lower() for name, value in headers if name == b'content-encoding']
        if any(value != b'identity' for value in encodings):
            await reject(415, 'Content-Encoding must be identity.')
            return
        lengths = [value.strip() for name, value in headers if name == b'content-length']
        if lengths:
            if len(lengths) != 1 or not lengths[0].isdigit():
                await reject(400, 'Invalid Content-Length.')
                return
            # Compare digits before int conversion, including arbitrarily long headers.
            length = lengths[0].lstrip(b'0') or b'0'
            if len(length) > 5 or int(length) > MAX_TRIAGE_BYTES:
                await reject(413, f'Triage request exceeds {MAX_TRIAGE_BYTES} bytes.')
                return

        body = bytearray()
        oversized = False
        try:
            # One deadline for the whole upload; incremental progress cannot reset it.
            async with asyncio.timeout(TRIAGE_UPLOAD_SECONDS):
                while True:
                    message = await receive()
                    if message['type'] == 'http.disconnect':
                        return
                    chunk = message.get('body', b'')
                    if len(body) + len(chunk) > MAX_TRIAGE_BYTES:
                        oversized = True
                        break
                    body.extend(chunk)
                    if not message.get('more_body', False):
                        break
        except TimeoutError:
            # Do not reuse HTTP/1 connections carrying an unfinished request body.
            headers = {'Connection': 'close'} if scope.get('http_version') in ('1.0', '1.1') else {}
            await JSONResponse({'detail': 'Triage request upload timed out.'},
                               status_code=408, headers=headers)(scope, receive, send)
            return

        if oversized:
            await reject(413, f'Triage request exceeds {MAX_TRIAGE_BYTES} bytes.')
            return

        # Only a complete bounded body reaches JSON parsing and the triage worker.
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {'type': 'http.request', 'body': bytes(body), 'more_body': False}

        await self.app(scope, bounded_receive, send)
