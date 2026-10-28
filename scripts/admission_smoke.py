"""Verify operator-selected admission using an owned, loopback-only container."""

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

QUERY = 'Kafka consumer lag keeps rising while producers send more events.'


def check_capacity(base, capacity):
    address = urlsplit(base)
    connections = []
    body = json.dumps({'query': QUERY}).encode()

    def begin(index):
        sock = socket.create_connection((address.hostname, address.port), timeout=5)
        connections.append(sock)
        framing = 'Transfer-Encoding: chunked' if index % 2 else f'Content-Length: {len(body)}'
        sock.sendall((f'POST /api/triage HTTP/1.1\r\nHost: localhost\r\n'
                      f'Content-Type: application/json\r\n{framing}\r\n'
                      'Expect: 100-continue\r\n\r\n').encode())
        head = b''
        while not head.endswith(b'\r\n\r\n'):
            part = sock.recv(1)
            require(bool(part) and len(head) < 8192, 'Incomplete or excessive response headers')
            head += part
        return sock, head

    def close_all():
        for sock in connections:
            sock.close()
        connections.clear()

    try:
        for index in range(capacity):
            _, head = begin(index)
            require(head.startswith(b'HTTP/1.1 100'), 'Configured slot was not admitted')
        _, head = begin(capacity)
        require(head.startswith(b'HTTP/1.1 503'), 'Excess upload received 100 or bypassed admission')
        require(b'cache-control: no-store' in head.lower() and b'connection: close' in head.lower(),
                'Admission rejection headers differ')
        require(get_json(base, '/healthz')['status'] == 'ok', 'Health is blocked by triage occupancy')
        close_all()
        # Client close and server cleanup are asynchronous. Retry only this
        # read-free admission probe; no completed operation is retried.
        deadline = time.monotonic() + 5
        recovery = []
        for index in range(capacity):
            while True:
                sock, head = begin(index)
                if head.startswith(b'HTTP/1.1 100'):
                    recovery.append(sock)
                    break
                require(head.startswith(b'HTTP/1.1 503') and time.monotonic() < deadline,
                        'Configured capacity did not recover after disconnect')
                sock.close()
                connections.remove(sock)
                time.sleep(.01)
        _, head = begin(capacity)
        require(head.startswith(b'HTTP/1.1 503'), 'Cleanup increased configured capacity')
        for index, sock in enumerate(recovery):
            sock.sendall(f'{len(body):x}\r\n'.encode() + body + b'\r\n0\r\n\r\n'
                         if index % 2 else body)
        for sock in recovery:
            response = HTTPResponse(sock)
            response.begin()
            require(response.status == 200 and json.loads(response.read())['mode'] == 'extractive',
                    'Recovered upload did not complete')
            response.close()
    finally:
        close_all()


def check_image(image, output):
    output.unlink(missing_ok=True)
    image_id = json.loads(docker('image', 'inspect', image))[0]['Id']
    name = 'runbookops-admission-' + uuid4().hex[:12]
    try:
        docker('run', '--pull=never', '--detach', '--name', name, '--read-only',
               '--tmpfs', '/tmp:rw,noexec,nosuid,size=64m', '--cap-drop=ALL',
               '--security-opt=no-new-privileges', '--publish', '127.0.0.1::8000',
               '--health-interval=1s', '--health-start-period=30s',
               '--env', 'RUNBOOKOPS_TRIAGE_CAPACITY=2', '--env', 'OLLAMA_MODEL=', image_id)
        for restart in (False, True):
            if restart:
                docker('stop', '--timeout', '10', name)
                require(inspect(name)['State']['ExitCode'] == 0, 'Shutdown failed')
                docker('start', name)
            wait_healthy(name)
            state = inspect(name)
            binding = state['NetworkSettings']['Ports']['8000/tcp']
            require(len(binding) == 1 and binding[0]['HostIp'] == '127.0.0.1', 'Non-loopback binding')
            require(state['Image'] == image_id and state['HostConfig']['ReadonlyRootfs'], 'Runtime changed')
            require(docker('exec', name, 'id', '-u') == '10001', 'Unexpected UID')
            check_capacity('http://127.0.0.1:' + binding[0]['HostPort'], 2)
        receipt = {'image_id': image_id, 'docker_server': docker('version', '--format', '{{.Server.Version}}'),
                   'capacity': 2, 'checks': ['fixed/chunked occupancy', 'excess rejected before body read',
                   'health during saturation', 'disconnect recovery', 'no extra slot after recovery',
                   'recovered triage completion', 'same capacity after container restart']}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps(receipt, indent=2), flush=True)
    finally:
        subprocess.run(['docker', 'logs', '--tail', '20', name], check=False, timeout=15)
        subprocess.run(['docker', 'rm', '--force', name], check=False, timeout=15)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='runbookops:smoke')
    parser.add_argument('--output', type=Path, default=Path('artifacts/admission-container.json'))
    args = parser.parse_args()
    check_image(args.image, args.output)
