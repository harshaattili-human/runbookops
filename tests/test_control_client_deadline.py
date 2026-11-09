"""Synthetic Unix peer checks for the operator client's elapsed I/O budget."""
import math
import os
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

from runbookops.corpus_control import _exchange, MAX_REQUEST_BYTES


@unittest.skipUnless(os.name == 'posix', 'Unix control sockets require POSIX')
class ControlClientDeadlineTest(unittest.TestCase):
    def test_invalid_budgets_fail_before_connect(self):
        for value in (0, -1, True, None, '1', math.inf, math.nan):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _exchange('/missing', b'{}\n', value)

    def test_trickling_reply_times_out_closes_and_next_request_recovers(self):
        with tempfile.TemporaryDirectory(prefix='rbd-') as directory:
            path = str(Path(directory) / 'control.sock')
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
                listener.bind(path)
                listener.listen(2)
                listener.settimeout(3)
                closed = threading.Event()
                errors = []

                def peer():
                    try:
                        with listener.accept()[0] as first:
                            first.settimeout(3)
                            self.assertEqual(first.recv(4096), b'{"operation":"inspect"}\n')
                            # Each gap is below the client's .2s budget. An inactivity
                            # timeout would accept this complete reply after ~.6s.
                            for byte in b'{"status":"busy"}\n':
                                try:
                                    first.sendall(bytes([byte]))
                                except (BrokenPipeError, ConnectionResetError):
                                    closed.set()
                                    break
                                time.sleep(.04)
                            if not closed.is_set():
                                self.assertEqual(first.recv(1), b'')
                                closed.set()
                        with listener.accept()[0] as second:
                            second.settimeout(3)
                            second.recv(4096)
                            second.sendall(b'{"status":"busy"}\n')
                    except BaseException as failure:
                        errors.append(failure)

                thread = threading.Thread(target=peer, daemon=True)
                thread.start()
                start = time.monotonic()
                with self.assertRaises(TimeoutError):
                    _exchange(path, b'{"operation":"inspect"}\n', .2)
                self.assertLess(time.monotonic() - start, 1.5)
                self.assertTrue(closed.wait(2))
                self.assertEqual(_exchange(path, b'{"operation":"inspect"}\n', 2), {'status': 'busy'})
                thread.join(3)
                self.assertFalse(thread.is_alive())
                if errors:
                    raise errors[0]

    def test_fragmented_boundary_and_invalid_frames(self):
        with tempfile.TemporaryDirectory(prefix='rbd-') as directory:
            path = str(Path(directory) / 'control.sock')
            good = b'{"status":"busy"}'
            exact = good + b' ' * (MAX_REQUEST_BYTES - len(good) - 1) + b'\n'
            for payload, accepted in ((exact, True), (exact[:-1] + b' \n', False),
                                      (good, False), (b'{"status":"unknown"}\n', False)):
                with self.subTest(length=len(payload)), socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
                    listener.bind(path)
                    listener.listen(1)
                    listener.settimeout(3)
                    errors = []
                    def peer():
                        try:
                            with listener.accept()[0] as client:
                                client.settimeout(3)
                                client.recv(4096)
                                for offset in range(0, len(payload), 97):
                                    client.sendall(payload[offset:offset + 97])
                        except BaseException as failure:
                            errors.append(failure)
                    thread = threading.Thread(target=peer, daemon=True)
                    thread.start()
                    if accepted:
                        self.assertEqual(_exchange(path, b'{}\n', 2), {'status': 'busy'})
                    else:
                        with self.assertRaises(ValueError):
                            _exchange(path, b'{}\n', 2)
                    thread.join(3)
                    self.assertFalse(thread.is_alive())
                    if errors:
                        raise errors[0]
                if os.path.exists(path):
                    os.unlink(path)


if __name__ == '__main__':
    unittest.main()
