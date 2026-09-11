"""Bounded, cached, device-wide telemetry. No LAN listener or request-time collection."""
import copy
import json
import math
import socket
import threading
import time
import uuid

from .runtime import LLAMA_REVISION
from .worker import gpu_inventory

MAX_RESPONSE = 32768
MAX_HEADERS = 8192
MAX_CLIENTS = 4


def measurement(value, low=0, high=float('inf')):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and low <= value <= high:
        return value
    return None


class Telemetry:
    def __init__(self, worker, collector=gpu_inventory, clock=time.monotonic):
        self.worker, self.collector, self.clock = worker, collector, clock
        self.instance_id = str(uuid.uuid4())
        self.lock = threading.Lock()
        self.stopped = threading.Event()
        self.sequence, self.attempt, self.status, self.gpus = 0, clock(), 'unavailable', []
        self.listener = None
        self.slots = threading.BoundedSemaphore(MAX_CLIENTS)
        self.clients = set()

    def collect(self):
        try:
            rows = self.collector()
            gpus = []
            for row in rows[:16]:
                ident = row.get('uuid')
                if not ident:
                    continue  # Never use a mutable ordinal as stable identity.
                def memory(name):
                    value = measurement(row.get(name), 0 if name == 'used_mib' else 1)
                    return int(value * 1048576) if value is not None else None
                gpus.append(dict(id=ident[:128], name=row['name'][:160], selected=None,
                    utilization_percent=measurement(row.get('utilization'), 0, 100),
                    memory_used_bytes=memory('used_mib'), memory_total_bytes=memory('total_mib'),
                    temperature_c=measurement(row.get('temperature'), -40, 200),
                    power_watts=measurement(row.get('power'), 0, 10000)))
            status = 'ok' if gpus else 'unavailable'
        except FileNotFoundError:
            status, gpus = 'unavailable', []
        except Exception:
            status, gpus = 'error', []
        with self.lock:
            self.sequence += 1
            self.attempt, self.status, self.gpus = self.clock(), status, gpus

    def snapshot(self):
        with self.lock:
            age = max(0, int((self.clock() - self.attempt) * 1000))
            result = dict(schema_version=1, instance_id=self.instance_id, sequence=self.sequence,
                          sample_age_ms=age, collector_status=self.status, gpus=copy.deepcopy(self.gpus))
        with self.worker.lock:
            process = self.worker.process
            running = process is not None and process.poll() is None
            ident = self.worker.device_id if running else None
            result['rpc'] = dict(running=running, pid=process.pid if running else None,
                device_id=ident, revision=LLAMA_REVISION, transport='tcp', port=50052)
        for gpu in result['gpus']:
            gpu['selected'] = gpu['id'] == ident if ident else None
            if age > 5000:
                for field in ('utilization_percent', 'memory_used_bytes', 'memory_total_bytes', 'temperature_c', 'power_watts'):
                    gpu[field] = None
        return result

    def payload(self):
        body = json.dumps(self.snapshot(), allow_nan=False, separators=(',', ':')).encode('utf-8')
        if len(body) > MAX_RESPONSE:
            raise ValueError('Telemetry response exceeded its size limit')
        return body

    def start(self, port=50055):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            listener.bind(('127.0.0.1', port))
            listener.listen(MAX_CLIENTS)
            listener.settimeout(.2)
        except Exception:
            listener.close()
            raise
        self.listener = listener
        self.port = listener.getsockname()[1]
        self.sampler = threading.Thread(target=self._sample_loop, daemon=True)
        self.server = threading.Thread(target=self._serve, daemon=True)
        self.sampler.start()
        self.server.start()

    def _sample_loop(self):
        while not self.stopped.is_set():
            began = self.clock()
            self.collect()
            self.stopped.wait(max(.1, 1 - (self.clock() - began)))

    def _serve(self):
        while not self.stopped.is_set():
            try:
                client, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            if not self.slots.acquire(blocking=False):
                client.close()
                continue
            with self.lock:
                self.clients.add(client)
            threading.Thread(target=self._request, args=(client,), daemon=True).start()

    def _request(self, client):
        try:
            deadline, data = time.monotonic() + 2, b''
            while b'\r\n\r\n' not in data and len(data) <= MAX_HEADERS:
                client.settimeout(max(.001, deadline - time.monotonic()))
                block = client.recv(min(1024, MAX_HEADERS + 1 - len(data)))
                if not block or time.monotonic() > deadline:
                    return
                data += block
            status, body = '400 Bad Request', b'{}'
            if len(data) > MAX_HEADERS:
                status = '431 Request Header Fields Too Large'
            else:
                lines = data.split(b'\r\n')
                request = lines[0].split(b' ')
                headers = lines[1:lines.index(b'')]
                if len(request) == 3 and request[2] in (b'HTTP/1.0', b'HTTP/1.1') and all(b':' in h for h in headers):
                    method, path, _ = request
                    if method != b'GET':
                        status = '405 Method Not Allowed'
                    elif path != b'/v1/telemetry':
                        status = '404 Not Found'
                    elif any(h.lower().startswith((b'transfer-encoding:', b'content-length:')) for h in headers):
                        status = '400 Bad Request'
                    else:
                        status, body = '200 OK', self.payload()
            client.settimeout(.5)
            client.sendall((f'HTTP/1.1 {status}\r\nContent-Type: application/json\r\nCache-Control: no-store\r\nConnection: close\r\nContent-Length: {len(body)}\r\n\r\n').encode('ascii') + body)
        except (OSError, ValueError):
            pass
        finally:
            client.close()
            with self.lock:
                self.clients.discard(client)
            self.slots.release()

    def close(self):
        self.stopped.set()
        if self.listener:
            self.listener.close()
        with self.lock:
            clients = list(self.clients)
        for client in clients:
            client.close()
        for name in ('server', 'sampler'):
            thread = getattr(self, name, None)
            if thread:
                thread.join(timeout=2.5)
