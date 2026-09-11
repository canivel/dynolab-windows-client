import json
import socket
import subprocess
import threading
import time
import unittest
from unittest.mock import Mock, patch

from dyno.pool.telemetry import Telemetry, MAX_HEADERS, MAX_RESPONSE, MAX_CLIENTS
from dyno.pool.worker import Worker, gpu_inventory, parse_gpus

UUID = 'GPU-11111111-2222-3333-4444-555555555555'


def inventory():
    return parse_gpus(f'7, NVIDIA test, 32768, 2048, 76, 44, 595.95, {UUID}, [N/A]\n')


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.worker = Worker()
        self.service = Telemetry(self.worker, inventory)
        self.addCleanup(self.service.close)

    def request(self, method='GET', path='/v1/telemetry', extra=b''):
        with socket.create_connection(('127.0.0.1', self.service.port), timeout=2) as client:
            client.sendall(f'{method} {path} HTTP/1.1\r\nHost: localhost\r\n'.encode() + extra + b'\r\n')
            data = b''
            while True:
                try:
                    block = client.recv(65536)
                except ConnectionResetError:
                    return data  # Windows may reset after rejecting unread oversized input.
                if not block:
                    return data
                data += block

    def test_schema_and_null_metrics(self):
        self.service.collect()
        result = json.loads(self.service.payload())
        self.assertEqual(set(result), {'schema_version', 'instance_id', 'sequence', 'sample_age_ms', 'collector_status', 'rpc', 'gpus'})
        self.assertEqual(result['collector_status'], 'ok')
        gpu = result['gpus'][0]
        self.assertEqual(gpu['memory_used_bytes'], 2048 * 1048576)
        self.assertIsNone(gpu['power_watts'])
        self.assertIsNone(gpu['selected'])
        self.assertLess(len(self.service.payload()), MAX_RESPONSE)

    def test_rpc_owned_process_and_uuid_not_ordinal(self):
        self.service.collect()
        self.assertFalse(self.service.snapshot()['rpc']['running'])
        self.worker.process = Mock(pid=999)
        self.worker.process.poll.return_value = None
        self.worker.device_id = UUID
        self.worker.state = 'Stopped'  # UI state must not control telemetry.
        result = self.service.snapshot()
        self.assertTrue(result['rpc']['running'])
        self.assertTrue(result['gpus'][0]['selected'])
        self.assertEqual(result['rpc']['device_id'], UUID)
        self.worker.device_id = None
        self.assertIsNone(self.service.snapshot()['gpus'][0]['selected'])
        self.worker.process.poll.return_value = 1
        self.assertFalse(self.service.snapshot()['rpc']['running'])
        self.assertIsNone(self.service.snapshot()['rpc']['pid'])

    def test_errors_advance_sequence_without_cached_metrics(self):
        self.service.collect()
        for error, status in [(FileNotFoundError(), 'unavailable'), (subprocess.TimeoutExpired('nvidia-smi', 2), 'error'), (ValueError(), 'error')]:
            previous = self.service.sequence
            self.service.collector = Mock(side_effect=error)
            self.service.collect()
            result = self.service.snapshot()
            self.assertEqual(result['sequence'], previous + 1)
            self.assertEqual(result['collector_status'], status)
            self.assertEqual(result['gpus'], [])

    def test_stale_and_restart(self):
        clock = Mock(return_value=10.)
        self.service.clock = clock
        self.service.collect()
        clock.return_value = 16.
        result = self.service.snapshot()
        self.assertEqual(result['sample_age_ms'], 6000)
        self.assertIsNone(result['gpus'][0]['utilization_percent'])
        self.assertNotEqual(Telemetry(self.worker).instance_id, self.service.instance_id)

    def test_http_routes_methods_headers_and_loopback(self):
        self.service.start(port=0)
        self.assertEqual(self.service.listener.getsockname()[0], '127.0.0.1')
        good = self.request()
        self.assertIn(b'200 OK', good)
        self.assertIn(b'Cache-Control: no-store', good)
        self.assertIn(b'Content-Type: application/json', good)
        for method in ('POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'CONNECT'):
            self.assertIn(b'405', self.request(method))
        for path in ('/', '/v1/telemetry?x=1', '/other', 'http://example.com/v1/telemetry'):
            self.assertIn(b'404', self.request(path=path))
        self.assertIn(b'400', self.request(extra=b'Content-Length: 0\r\n'))
        rejected = self.request(extra=b'X: ' + b'a' * MAX_HEADERS + b'\r\n')
        self.assertTrue(not rejected or b'431' in rejected)

    def test_occupied_port_preserved(self):
        with socket.socket() as other:
            other.bind(('127.0.0.1', 0))
            other.listen()
            with self.assertRaises(OSError):
                self.service.start(port=other.getsockname()[1])
            self.assertIsNone(self.service.listener)
            with socket.create_connection(other.getsockname(), timeout=1):
                pass

    def test_sampling_never_blocks_requests_or_start(self):
        gate = threading.Event()
        self.addCleanup(gate.set)
        calls = []
        def slow():
            calls.append(threading.get_ident())
            gate.wait(2)
            return inventory()
        self.service.collector = slow
        began = time.monotonic()
        self.service.start(port=0)
        for _ in range(5):
            self.assertIn(b'200 OK', self.request())
        self.assertLess(time.monotonic() - began, 1)
        self.assertEqual(len(calls), 1)
        self.assertNotEqual(calls[0], threading.get_ident())
        gate.set()

    def test_concurrency_and_close_do_not_stop_rpc(self):
        self.service.start(port=0)
        clients = [socket.create_connection(('127.0.0.1', self.service.port)) for _ in range(MAX_CLIENTS)]
        try:
            deadline = time.monotonic() + 1
            while len(self.service.clients) < MAX_CLIENTS and time.monotonic() < deadline:
                time.sleep(.01)
            with socket.create_connection(('127.0.0.1', self.service.port), timeout=1) as extra:
                self.assertEqual(extra.recv(1), b'')
            self.worker.process = Mock(pid=999)
            self.service.close()
            self.worker.process.terminate.assert_not_called()
            self.assertLessEqual(len(self.service.clients), MAX_CLIENTS)
        finally:
            for client in clients:
                client.close()

    def test_collector_timeout_and_bad_values(self):
        with patch('dyno.pool.worker.run_hidden', return_value=subprocess.CompletedProcess([], 1, '', 'failure')) as run:
            with self.assertRaises(ValueError):
                gpu_inventory()
            self.assertEqual(run.call_args.kwargs['timeout'], 2)
        rows = inventory()
        rows[0].update(utilization=float('nan'), power=float('inf'), temperature=999)
        self.service.collector = lambda: rows * 30
        self.service.collect()
        result = self.service.snapshot()
        self.assertEqual(len(result['gpus']), 16)
        self.assertIsNone(result['gpus'][0]['utilization_percent'])
        self.assertIsNone(result['gpus'][0]['power_watts'])
        self.assertIsNone(result['gpus'][0]['temperature_c'])


if __name__ == '__main__':
    unittest.main()
