"""Count triage request bytes before FastAPI reads or parses JSON."""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


MAX_TRIAGE_BYTES = 32_768


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
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            chunk = message.get('body', b'')
            if len(body) + len(chunk) > MAX_TRIAGE_BYTES:
                await reject(413, f'Triage request exceeds {MAX_TRIAGE_BYTES} bytes.')
                return
            body.extend(chunk)
            if not message.get('more_body', False):
                break

        # Only a complete bounded body reaches JSON parsing and the triage worker.
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {'type': 'http.request', 'body': bytes(body), 'more_body': False}

        await self.app(scope, bounded_receive, send)
