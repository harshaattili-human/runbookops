"""Exercise an enabled request budget in the built image, including restart."""

import argparse
from http.client import HTTPResponse
import json
from pathlib import Path
import socket
import subprocess
import time
from urllib.parse import urlsplit
from uuid import uuid4

from container_smoke import docker, get_json, inspect, require, wait_healthy

BODY = json.dumps({'query': 'Kafka consumer lag keeps rising while producers send more events.'}).encode()


def begin(base, chunked=False, path='/api/triage'):
    address = urlsplit(base)
    sock = socket.create_connection((address.hostname, address.port), timeout=10)
    try:
        framing = 'Transfer-Encoding: chunked' if chunked else f'Content-Length: {len(BODY)}'
        sock.sendall((f'POST {path} HTTP/1.1\r\nHost: localhost\r\n'
                      f'Content-Type: application/json\r\n{framing}\r\n'
                      'Expect: 100-continue\r\n\r\n').encode())
        head = b''
        while not head.endswith(b'\r\n\r\n'):
            part = sock.recv(1)
            require(bool(part) and len(head) < 8192, 'Incomplete or excessive response headers')
            head += part
        lines = head.decode('ascii').split('\r\n')
        status = int(lines[0].split()[1])
        headers = dict(line.lower().split(': ', 1) for line in lines[1:] if line)
        return sock, status, headers
    except BaseException:
        sock.close()
        raise


def finish(sock, chunked=False):
    sock.sendall(f'{len(BODY):x}\r\n'.encode() + BODY + b'\r\n0\r\n\r\n' if chunked else BODY)
    response = HTTPResponse(sock)
    try:
        response.begin()
        require(response.status == 200, 'Admitted request did not complete successfully')
        require(json.loads(response.read())['mode'] == 'extractive', 'Unexpected triage mode')
    finally:
        response.close()


def reject(base, expected, chunked=False, path='/api/triage'):
    sock, status, headers = begin(base, chunked, path)
    try:
        require(status == expected, f'Expected {expected} before upload, received {status}')
        require(headers.get('cache-control') == 'no-store' and headers.get('connection') == 'close',
                'Rejection cache/connection policy differs')
        if expected == 429:
            retry = headers.get('retry-after', '')
            require(retry.isascii() and retry.isdecimal() and 1 <= int(retry) <= 60,
                    'Retry-After must be an integer from 1 to 60 seconds')
            return int(retry)
    finally:
        sock.close()


def base_url(name, image_id):
    wait_healthy(name)
    state = inspect(name)
    binding = state['NetworkSettings']['Ports']['8000/tcp']
    require(len(binding) == 1 and binding[0]['HostIp'] == '127.0.0.1', 'Non-loopback binding')
    require(state['Image'] == image_id and state['HostConfig']['ReadonlyRootfs'], 'Runtime changed')
    require(docker('exec', name, 'id', '-u') == '10001', 'Unexpected runtime UID')
    return 'http://127.0.0.1:' + binding[0]['HostPort']


def check_image(image, output):
    output.unlink(missing_ok=True)
    image_id = json.loads(docker('image', 'inspect', image))[0]['Id']
    name = 'runbookops-rate-' + uuid4().hex[:12]
    try:
        docker('run', '--pull=never', '--detach', '--name', name, '--read-only',
               '--tmpfs', '/tmp:rw,noexec,nosuid,size=64m', '--cap-drop=ALL',
               '--security-opt=no-new-privileges', '--publish', '127.0.0.1::8000',
               '--health-interval=1s', '--health-start-period=30s',
               '--env', 'RUNBOOKOPS_TRIAGE_CAPACITY=1',
               '--env', 'RUNBOOKOPS_RATE_LIMIT_CAPACITY=2',
               '--env', 'RUNBOOKOPS_RATE_LIMIT_REFILL_MS=60000',
               '--env', 'OLLAMA_MODEL=', image_id)
        base = base_url(name, image_id)
        first, status, _ = begin(base)
        try:
            require(status == 100, 'First upload did not acquire the sole admission slot')
            # A rate token is spent even when the next layer returns 503.
            reject(base, 503, chunked=True)
            reject(base, 429)
            reject(base, 429, chunked=True, path='/api/triage/')
            require(get_json(base, '/healthz')['status'] == 'ok', 'Health blocked during saturation')
            finish(first)
        finally:
            first.close()
        retry = reject(base, 429, chunked=True)
        require(bool(get_json(base, '/api/overview')), 'Read API blocked by exhausted budget')
        # Real monotonic refill, without replacing the app clock or retrying a
        # completed request. Retry-After rounds up; margin avoids boundary jitter.
        time.sleep(retry + .1)
        recovered, status, _ = begin(base, chunked=True)
        try:
            require(status == 100, 'Refill did not restore admission after completion')
            finish(recovered, chunked=True)
        finally:
            recovered.close()
        reject(base, 429)
        docker('stop', '--timeout', '10', name)
        require(inspect(name)['State']['ExitCode'] == 0, 'Shutdown failed')
        docker('start', name)
        base = base_url(name, image_id)
        for chunked in (False, True):
            sock, status, _ = begin(base, chunked)
            try:
                require(status == 100, 'Restart did not restore the configured two-token burst')
                finish(sock, chunked)
            finally:
                sock.close()
        reject(base, 429)
        receipt = {'image_id': image_id,
                   'docker_server': docker('version', '--format', '{{.Server.Version}}'),
                   'rate_capacity': 2, 'refill_ms': 60000, 'triage_capacity': 1,
                   'checks': ['fixed and chunked rejection before 100 Continue',
                              'rate token spent on downstream 503',
                              'health and overview bypass exhausted budget',
                              'completion does not refund rate token',
                              'real clock refill restores successful chunked triage',
                              'restart restores exactly two successful requests']}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps(receipt, indent=2), flush=True)
    finally:
        subprocess.run(['docker', 'logs', '--tail', '20', name], check=False, timeout=15)
        subprocess.run(['docker', 'rm', '--force', name], check=False, timeout=15)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='runbookops:smoke')
    parser.add_argument('--output', type=Path, default=Path('artifacts/rate-limit-container.json'))
    args = parser.parse_args()
    check_image(args.image, args.output)
