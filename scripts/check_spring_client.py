"""Run the Java example against an owned local Uvicorn process and synthetic corpus."""

from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / 'examples' / 'spring-client'


def main():
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'runbookops.api:app',
                               '--host', '127.0.0.1', '--port', str(port)], cwd=ROOT)
    try:
        deadline = time.monotonic() + 30
        while True:
            if server.poll() is not None:
                raise RuntimeError('Owned API process exited before readiness')
            try:
                with urlopen(base + '/healthz', timeout=1) as response:
                    if response.status == 200:
                        break
            except (URLError, TimeoutError):
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError('API readiness timed out')
            time.sleep(.1)
        subprocess.run(['mvn', '--batch-mode', '--no-transfer-progress',
                        f'-Drunbook.live-url={base}', 'verify'], cwd=PROJECT, check=True)
        completed = subprocess.run(['java', '-jar',
                                    str(PROJECT / 'target/runbookops-client-example-0.1.0-SNAPSHOT.jar'),
                                    f'--runbook.base-url={base}'], cwd=ROOT, check=True,
                                   text=True, capture_output=True, timeout=30)
        print(completed.stdout)
        if 'mode=extractive' not in completed.stdout or 'version_verified=true' not in completed.stdout:
            raise RuntimeError('Packaged walkthrough did not inspect its source')
        print('Spring client tests and executable walkthrough passed against live FastAPI.')
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()


if __name__ == '__main__':
    main()
