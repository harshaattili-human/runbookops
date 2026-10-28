"""Opt-in local operator channel; filesystem ownership is the authorization boundary."""

import argparse
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import re
import socket
import stat

from .corpus_snapshot import CorpusConflict, validate_identity

MAX_REQUEST_BYTES = 4096  # Includes the terminating newline, not transport buffers.
READ_SECONDS = 5.0
WRITE_SECONDS = 1.0


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate field')
        result[key] = value
    return result


def _request(raw):
    if len(raw) > MAX_REQUEST_BYTES or not raw.endswith(b'\n'):
        raise ValueError('Invalid request framing')
    value = json.loads(raw, object_pairs_hook=_unique)
    if value == {'operation': 'inspect'}:
        return None, None, None
    if not isinstance(value, dict) or set(value) not in (
            {'release', 'manifest_sha256'}, {'release', 'manifest_sha256', 'expected_corpus'}):
        raise ValueError('Expected release and manifest_sha256')
    release, digest = value['release'], value['manifest_sha256']
    if not isinstance(release, str) or '\x00' in release or not Path(release).is_absolute():
        raise ValueError('Release must be an absolute path')
    if not isinstance(digest, str) or re.fullmatch(r'[0-9a-f]{64}', digest) is None:
        raise ValueError('Expected a lowercase SHA-256 pin')
    expected = validate_identity(value['expected_corpus']) if 'expected_corpus' in value else None
    return Path(release), digest, expected


def _socket_path(value):
    if os.name != 'posix' or not hasattr(socket, 'AF_UNIX'):
        raise ValueError('Corpus control requires POSIX Unix sockets')
    path = Path(value)
    if not value or not path.is_absolute() or path.parent.resolve() != path.parent:
        raise ValueError('Control socket requires an absolute path without parent aliases')
    parent = path.parent.lstat()
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid()
            or stat.S_IMODE(parent.st_mode) != 0o700):
        raise ValueError('Control socket parent must be owned by this UID with mode 0700')
    # bind(), rather than unlinking an existing path, decides whether it is unused.
    return path


async def _joined_worker(function, *args, **kwargs):
    worker = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        # A cancelled await cannot kill an index-building Python thread. Keep the
        # operator lease until it finishes, even after repeated cancellation.
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not worker.cancelled():
            worker.exception()
        raise


class CorpusControl:
    def __init__(self, service):
        self.service = service
        self.active = False
        self.closing = False
        self.tasks = set()

    def connected(self, reader, writer):
        task = asyncio.create_task(self.handle(reader, writer))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def respond(self, writer, value):
        writer.write(json.dumps(value, separators=(',', ':')).encode() + b'\n')
        async with asyncio.timeout(WRITE_SECONDS):
            await writer.drain()

    async def handle(self, reader, writer):
        acquired = False
        try:
            if self.active or self.closing:
                await self.respond(writer, {'status': 'busy'})
                return
            self.active = acquired = True  # No await between check and acquisition.
            try:
                async with asyncio.timeout(READ_SECONDS):
                    raw = await reader.readuntil(b'\n')
                release, digest, expected = _request(raw)
            except (ValueError, UnicodeError, RecursionError, TimeoutError,
                    asyncio.IncompleteReadError, asyncio.LimitOverrunError):
                await self.respond(writer, {'status': 'invalid_request'})
                return
            if release is None:
                await self.respond(writer, {'status': 'ok', 'corpus': self.service.snapshot.identity()})
                return
            try:
                receipt = await _joined_worker(self.service.refresh_runbooks_release, release,
                                               expected_manifest_hash=digest, expected_corpus=expected)
            except CorpusConflict:
                await self.respond(writer, {'status': 'conflict'})
                return
            except Exception:
                # Do not send filesystem paths or exception text to the socket.
                await self.respond(writer, {'status': 'refresh_failed'})
                return
            await self.respond(writer, {'status': 'ok', 'corpus': receipt['corpus']})
        except (OSError, TimeoutError):
            pass  # A lost reply does not roll back an accepted refresh.
        finally:
            writer.close()
            try:
                async with asyncio.timeout(WRITE_SECONDS):
                    await writer.wait_closed()
            except (OSError, TimeoutError):
                pass
            finally:
                if acquired:
                    self.active = False


@asynccontextmanager
async def serve_control(service, value):
    path = _socket_path(value)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    owned = None
    server = None
    control = CorpusControl(service)
    try:
        listener.bind(str(path))  # Never replaces or unlinks an existing path.
        info = path.lstat()
        owned = (info.st_dev, info.st_ino)
        path.chmod(0o600)
        listener.setblocking(False)
        server = await asyncio.start_unix_server(control.connected, sock=listener,
                                                 limit=MAX_REQUEST_BYTES, backlog=8)
        yield control
    finally:
        control.closing = True
        if server is not None:
            server.close()
            await server.wait_closed()
        else:
            listener.close()
        tasks = list(control.tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if owned is not None:
            try:
                current = path.lstat()
                if stat.S_ISSOCK(current.st_mode) and (current.st_dev, current.st_ino) == owned:
                    path.unlink()
            except FileNotFoundError:
                pass


def refresh(socket_path, release, digest, *, expected_corpus=None, timeout=30.0):
    """One request, no retry. A timeout/lost reply leaves the result ambiguous."""
    command = {'release': str(release), 'manifest_sha256': digest}
    if expected_corpus is not None:
        command['expected_corpus'] = validate_identity(expected_corpus)
    raw = json.dumps(command).encode() + b'\n'
    _request(raw)
    return _exchange(socket_path, raw, timeout)


def inspect_corpus(socket_path, *, timeout=30.0):
    """Observe this exact local process, without an HTTP/load-balancer hop."""
    return _exchange(socket_path, b'{"operation":"inspect"}\n', timeout)


def _exchange(socket_path, raw, timeout):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(str(socket_path))
        client.sendall(raw)
        with client.makefile('rb') as stream:
            reply = stream.readline(MAX_REQUEST_BYTES + 1)
    if len(reply) > MAX_REQUEST_BYTES or not reply.endswith(b'\n'):
        raise ValueError('Invalid control response')
    value = json.loads(reply, object_pairs_hook=_unique)
    if not isinstance(value, dict) or not isinstance(value.get('status'), str):
        raise ValueError('Invalid control response')
    if value['status'] == 'ok' and set(value) == {'status', 'corpus'}:
        value['corpus'] = validate_identity(value['corpus'])
    elif value['status'] not in {'busy', 'invalid_request', 'refresh_failed', 'conflict'} or set(value) != {'status'}:
        raise ValueError('Invalid control response')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--socket', required=True, type=Path)
    parser.add_argument('--release', type=Path)
    parser.add_argument('--sha256')
    parser.add_argument('--inspect', action='store_true', help='Read this process corpus identity without refreshing')
    parser.add_argument('--expected-corpus', type=Path,
                        help='JSON file containing the previously observed complete corpus identity')
    args = parser.parse_args()
    if args.inspect and any((args.release, args.sha256, args.expected_corpus)):
        parser.error('--inspect cannot be combined with refresh arguments')
    if not args.inspect and (args.release is None or args.sha256 is None):
        parser.error('refresh requires --release and --sha256')
    try:
        expected = (validate_identity(json.loads(args.expected_corpus.read_bytes(), object_pairs_hook=_unique))
                    if args.expected_corpus is not None else None)
        result = (inspect_corpus(args.socket) if args.inspect else
                  refresh(args.socket, args.release, args.sha256, expected_corpus=expected))
    except (OSError, ValueError):
        parser.exit(2, 'Control request failed; inspect served corpus identity before retrying.\n')
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result['status'] == 'ok' else 1)


if __name__ == '__main__':
    main()
