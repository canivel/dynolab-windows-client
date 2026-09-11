import base64
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from dyno.pool import worker as w
from dyno.pool.worker_setup import setup_request, launch_setup


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.binary = Path(self.folder.name) / 'rpc'
        self.binary.write_bytes(b'test runtime')
        self.manifest()
        self.worker = w.Worker()
        self.addCleanup(self.worker.stop)

    def manifest(self):
        (self.binary.parent / 'manifest.json').write_text(json.dumps({
            'revision': w.LLAMA_REVISION,
            'files': {self.binary.name: hashlib.sha256(self.binary.read_bytes()).hexdigest()},
        }))

    def test_corrupt_runtime_is_not_started(self):
        self.binary.write_bytes(b'changed')
        with patch.object(w.subprocess, 'Popen') as popen:
            with self.assertRaisesRegex(ValueError, 'integrity'):
                self.worker.start(self.binary)
            popen.assert_not_called()
        self.assertEqual(self.worker.snapshot()['state'], 'Failed')

    def test_wrong_revision_rejected(self):
        path = self.binary.parent / 'manifest.json'
        manifest = json.loads(path.read_text())
        manifest['revision'] = 'different'
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'match'):
            w.verify_runtime(self.binary)

    def test_gpu_unavailable_is_not_zero(self):
        gpu = w.parse_gpus('0, NVIDIA test, 32768, 2048, [N/A], 44, 555.1\n')[0]
        self.assertIsNone(gpu['utilization'])
        self.assertEqual(gpu['used_mib'], 2048)
        self.assertEqual(gpu['device'], 'CUDA0')

    def test_occupied_port_does_not_spawn_or_kill(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            port = listener.getsockname()[1]
            with patch.object(w.subprocess, 'Popen') as popen:
                with self.assertRaises(OSError):
                    self.worker.start(self.binary, port=port)
                popen.assert_not_called()
            with socket.create_connection(('127.0.0.1', port), timeout=1):
                pass

    def test_real_owned_process_start_stop_restart(self):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        script = ('import socket,time\n'
                  's=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)\n'
                  f's.bind(("127.0.0.1",{port}));s.listen()\n'
                  'print("worker listening",flush=True)\n'
                  'while True:\n c,a=s.accept();c.close()\n')
        with patch.object(w, 'command', return_value=[sys.executable, '-u', '-c', script]):
            for _ in range(2):
                self.worker.start(self.binary, port=port)
                self.assertEqual(self.worker.snapshot()['state'], 'Listening')
                process = self.worker.process
                with self.assertRaisesRegex(ValueError, 'already'):
                    self.worker.start(self.binary, port=port)
                self.worker.stop()
                self.assertIsNotNone(process.poll())
                self.assertEqual(self.worker.snapshot()['state'], 'Stopped')

    def test_early_exit_is_failure(self):
        with patch.object(w, 'command', return_value=[sys.executable, '-c', 'raise SystemExit(2)']):
            with self.assertRaisesRegex(ValueError, 'exited'):
                self.worker.start(self.binary, port=0)
        self.assertEqual(self.worker.snapshot()['state'], 'Failed')

    def test_logs_bounded(self):
        for index in range(2100):
            self.worker.log(str(index))
        self.assertEqual(len(self.worker.snapshot()['logs']), 2000)

    def test_uuid_remaps_child_to_cuda_zero_and_disables_rdma(self):
        ident = 'GPU-11111111-2222-3333-4444-555555555555'
        script = 'import os; print(os.environ.get("CUDA_VISIBLE_DEVICES"), os.environ.get("GGML_RPC_NO_RDMA"), flush=True)'
        with patch.object(w, 'command', return_value=[sys.executable, '-u', '-c', script]) as command:
            with self.assertRaisesRegex(ValueError, 'exited'):
                self.worker.start(self.binary, device='CUDA7', port=0, gpu_uuid=ident)
        self.assertEqual(command.call_args.args[1], 'CUDA0')
        self.assertEqual(self.worker.device_id, ident)
        self.assertTrue(any(ident + ' 1' in line for line in self.worker.snapshot()['logs']))

    @unittest.skipUnless(sys.platform == 'win32', 'Windows Job Object failure path')
    def test_assignment_failure_closes_pipe_and_owned_process(self):
        with patch.object(w, 'command', return_value=[sys.executable, '-u', '-c',
                'import time; time.sleep(60)']), \
                patch('dyno.pool.windows_job.Job.assign', side_effect=OSError('assignment denied')):
            with self.assertRaisesRegex(OSError, 'assignment denied'):
                self.worker.start(self.binary, port=0)
        self.assertIsNotNone(self.worker.process.poll())
        self.assertTrue(self.worker.process.stdout.closed)
        self.assertIsNone(self.worker.job)
        self.assertEqual(self.worker.snapshot()['state'], 'Failed')

    def test_pairing_accepts_only_public_ed25519_and_private_ip(self):
        key = 'ssh-ed25519 ' + base64.b64encode(b'\0\0\0\x0bssh-ed25519\0\0\0\x20' + bytes(32)).decode()
        self.assertEqual(setup_request('192.168.40.10', key + ' my Mac')['public_key'], key)
        for address, badkey in [('8.8.8.8', key), ('127.0.0.1', key),
                                ('192.168.40.10', key + '\n' + key),
                                ('192.168.40.10', '-----BEGIN OPENSSH PRIVATE KEY-----'),
                                ('192.168.40.10', 'ssh-ed25519 aaaa')]:
            with self.assertRaises(ValueError):
                setup_request(address, badkey)

    def test_setup_cancellation_and_missing_result_are_failures(self):
        identity = subprocess.CompletedProcess([], 0, '"test","S-1-5-21-1-2-3-1001"', '')
        for code, error in [(1, 'Windows setup was cancelled'), (0, '')]:
            with self.subTest(code=code), patch('dyno.pool.worker_setup.run_hidden', side_effect=[
                    identity, subprocess.CompletedProcess([], code, '', error)]) as run:
                with self.assertRaises(ValueError):
                    launch_setup({})
                self.assertIn("$ErrorActionPreference = 'Stop'", run.call_args.args[0][-1])

    def test_setup_result_exists_before_elevation(self):
        identity = subprocess.CompletedProcess([], 0, '"test","S-1-5-21-1-2-3-1001"', '')
        with tempfile.TemporaryDirectory() as folder:
            class Directory:
                def __enter__(self): return folder
                def __exit__(self, *args): pass
            def elevated(*args, **kwargs):
                result = Path(folder) / 'result.txt'
                self.assertTrue(result.exists())
                self.assertEqual(result.read_text(), '')
                result.write_text('Discovery enabled', encoding='utf-8')
                (Path(folder) / 'status.txt').write_text('Installing OpenSSH', encoding='utf-8')
                import time
                time.sleep(.6)
                return subprocess.CompletedProcess([], 0, '', '')
            with patch('dyno.pool.worker_setup.tempfile.TemporaryDirectory', return_value=Directory()), patch(
                    'dyno.pool.worker_setup.run_hidden', side_effect=[identity, None]) as run:
                run.side_effect = lambda *args, **kwargs: identity if args[0][0] == 'whoami' else elevated(*args, **kwargs)
                stages = []
                self.assertEqual(launch_setup({}, notify=stages.append), 'Discovery enabled')
                self.assertIn('Installing OpenSSH', stages)
                self.assertIn('-WindowStyle Hidden', run.call_args.args[0][-1])


if __name__ == '__main__':
    unittest.main()
