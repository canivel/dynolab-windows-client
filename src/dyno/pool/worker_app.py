"""Windows desktop companion with loopback-only RPC and telemetry."""
import json
import queue
import socket
from pathlib import Path
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .worker import Worker, bundled_binary, gpu_inventory


class WorkerApp:
    def __init__(self, root):
        self.root = root
        self.worker = Worker()
        self.busy = False
        self.closing = False
        self.gpus = []
        self.events = queue.Queue()
        self.pair_server = self.advertisement = None
        self.discovery_status = tk.StringVar(value='Enable discovery once, then find this worker from your coordinator.')
        self.selected_network = ''
        self.network_choice = tk.StringVar()
        self.network_entries = {}
        from .worker_design import build
        build(self)
        from .telemetry import Telemetry
        self.telemetry = Telemetry(self.worker)
        try:
            self.telemetry.start()
            self.telemetry_status.set('Telemetry ready on this computer. Enable access for an existing paired coordinator below.')
            self.worker.log('Telemetry listening on 127.0.0.1:50055 (device-wide metrics).')
        except OSError as exc:
            self.telemetry_status.set('Telemetry unavailable: ' + str(exc) + '. Inference can still run.')
            self.notice('Telemetry unavailable', 'Could not start local telemetry: ' + str(exc))
        self.last_log = None
        root.protocol('WM_DELETE_WINDOW', self.close)
        threading.Thread(target=self.poll_metrics, daemon=True).start()
        self.refresh()
        if (Path.home() / '.dyno' / 'worker-discovery-enabled').exists():
            self.background(self.start_discovery)
        else:
            self.background(self.refresh_networks)

    def ask(self, title, message, timeout=None):
        from .worker_design import ask
        return ask(self, title, message, timeout)

    def notice(self, title, message):
        self.notice_title.set(title)
        self.discovery_status.set(message)
        self.worker.log(message)
        self.tabs.select(0)

    def setup_progress(self, message):
        self.events.put(('status', message))

    def background(self, fn):
        if self.busy:
            return
        self.busy = True
        def work():
            try:
                fn()
            except Exception as exc:
                self.worker.log(str(exc))
                self.events.put(('status', str(exc)))
            finally:
                self.busy = False
        threading.Thread(target=work, daemon=True).start()

    def start(self):
        device = self.device.get()
        def work():
            gpu = next((g for g in gpu_inventory() if g['device'] == device), None)
            if not gpu or not gpu.get('uuid'):
                raise ValueError('Could not verify the selected GPU identity. Refresh metrics and retry.')
            self.worker.start(bundled_binary(), device, gpu_uuid=gpu['uuid'])
        self.background(work)

    def enable_telemetry(self):
        if not self.ask('Enable telemetry for paired coordinator?',
                'Allow existing Dyno coordinator keys for this Windows account to forward device-wide GPU metrics. Existing keys and pairing stay unchanged. Windows administrator approval is required.'):
            return
        def work():
            from .worker_setup import launch_elevated
            result = launch_elevated({}, 'setup-telemetry.ps1', notify=self.setup_progress)
            self.events.put(('status', result))
        self.background(work)

    def stop(self):
        if self.worker.snapshot()['state'] in ('Starting', 'Listening'):
            if not self.ask('Stop worker?', 'This interrupts any pool request using this GPU. Stop now?'):
                return
        self.background(self.worker.stop)

    def poll_metrics(self):
        import time
        while not self.closing:
            try:
                self.gpus = gpu_inventory()
                self.gpu_error = '' if self.gpus else 'No NVIDIA GPU was found.'
            except Exception as exc:
                self.gpus = []
                self.gpu_error = 'NVIDIA metrics unavailable: ' + str(exc)
            time.sleep(3)

    def refresh(self):
        while not self.events.empty():
            kind, value = self.events.get_nowait()
            if kind == 'status':
                self.discovery_status.set(value)
                self.notice_title.set('Needs attention' if any(word in value.lower() for word in ('failed', 'error', 'unavailable', 'no private')) else 'Connection status')
                self.worker.log(value)
            elif kind == 'interfaces':
                self.network_entries = {f"{i['interface']} — {i.get('category', 'Private')} — {i['address']}": i for i in value}
                self.networks.configure(values=list(self.network_entries))
                label = next((label for label, i in self.network_entries.items() if i['interface'] == self.selected_network), '')
                self.network_choice.set(label or 'Select a network…')
            elif kind == 'selected_network':
                self.selected_network = value
                label = next((label for label, i in self.network_entries.items() if i['interface'] == value), '')
                self.network_choice.set(label or 'Select a network…')
            elif kind == 'confirm':
                code, name, event, answer = value
                answer.append(self.ask('Verify coordinator',
                    f'Pair with {name}?\n\n{code}\n\nConfirm only if every group matches on the coordinator.', timeout=100))
                event.set()
        if self.pair_server and self.pair_server.stopped.is_set():
            self.stop_discovery(announce=False)
        snapshot = self.worker.snapshot()
        self._visual_state = snapshot['state']
        self.status.set(f"{snapshot['state']}  ·  {snapshot['uptime_seconds'] // 60}:{snapshot['uptime_seconds'] % 60:02d}")
        if snapshot['error']:
            self.discovery_status.set(snapshot['error'])
            self.notice_title.set('Worker needs attention')
        values = [gpu['device'] for gpu in self.gpus]
        if values:
            self.devices.configure(values=values)
        gpu = next((g for g in self.gpus if g['device'] == self.device.get()), None)
        def display(value):
            return 'unavailable' if value is None else str(value)
        self.metrics.set(f"{gpu['name']}  ·  {gpu['device']}  ·  Driver {gpu['driver']}" if gpu else getattr(self, 'gpu_error', 'Checking NVIDIA driver…'))
        if gpu:
            used, total = gpu['used_mib'], gpu['total_mib']
            self.metric_values['memory'].set(f'{used / 1024:.1f} / {total / 1024:.0f} GB' if used is not None and total else 'Unavailable')
            self.metric_values['load'].set(f"{gpu['utilization']}%" if gpu['utilization'] is not None else 'Unavailable')
            self.metric_values['temperature'].set(f"{gpu['temperature']}°C" if gpu['temperature'] is not None else 'Unavailable')
            self._bar_targets.update(memory=100 * used / total if used is not None and total else 0,
                                     load=gpu['utilization'] or 0, temperature=min(100, gpu['temperature'] or 0))
        else:
            for key in self.metric_values:
                self.metric_values[key].set('—')
                self._bar_targets[key] = 0
        for button in self.action_buttons:
            button.configure(state='disabled' if self.busy else 'normal')
        running = snapshot['state'] in ('Starting', 'Listening', 'Stopping')
        self.start_button.configure(state='disabled' if self.busy or running or not values else 'normal')
        self.stop_button.configure(state='normal' if running and not self.busy else 'disabled')
        self.devices.configure(state='disabled' if running else 'readonly')
        query = self.log_search.get().lower()
        text = '\n'.join(line for line in snapshot['logs'] if query in line.lower())
        if text != self.last_log:
            previous_view = self.log_text.yview()
            self.log_text.configure(state='normal')
            self.log_text.delete('1.0', 'end')
            for line in text.splitlines():
                tag = 'error' if any(word in line.lower() for word in ('error', 'failed', 'denied')) else 'info' if any(word in line.lower() for word in ('listening', 'paired', 'complete')) else ''
                self.log_text.insert('end', line + '\n', tag)
            if self.follow_logs.get():
                self.log_text.see('end')
            else:
                self.log_text.yview_moveto(previous_view[0])
            self.log_text.configure(state='disabled')
            self.last_log = text
        if not self.closing:
            self.root.after(500, self.refresh)

    def setup(self):
        if self.busy:
            return
        self.setup_result = 'Setup failed. See Runtime log for details.'
        from .worker_setup import setup_request, launch_setup
        try:
            request = setup_request(self.mac_ip.get(), self.key.get('1.0', 'end'))
        except ValueError as exc:
            self.notice('Connection details', str(exc))
            return
        if not self.ask('Set up Windows SSH?', 'This installs/enables OpenSSH, adds a firewall rule for this coordinator, '
                                  'and adds a restricted public key for your Windows account. Continue?'):
            return
        def work():
            result = launch_setup(request, notify=self.setup_progress)
            self.worker.log(result)
            self.setup_result = result
        self.background(work)
        self.show_setup_result()

    def show_setup_result(self):
        if self.busy:
            self.root.after(500, self.show_setup_result)
            return
        self.connection.configure(state='normal')
        self.connection.delete('1.0', 'end')
        self.connection.insert('end', getattr(self, 'setup_result', 'Setup failed. See Runtime log for details.'))
        self.connection.configure(state='disabled')

    def export(self):
        path = filedialog.asksaveasfilename(defaultextension='.json', initialfile='dyno-worker-diagnostics.json')
        if path:
            Path(path).write_text(json.dumps(dict(worker=self.worker.snapshot(), gpus=self.gpus), indent=2), encoding='utf-8')

    def refresh_networks(self):
        from .discovery import local_interfaces
        interfaces = local_interfaces(include_public=True)
        self.events.put(('interfaces', interfaces))
        if not interfaces:
            self.events.put(('status', 'No connected local IPv4 networks found. Connect to your LAN, then click Refresh networks.'))
        elif not self.pair_server:
            self.events.put(('status', 'Select the trusted network shared with your coordinator. Public networks require your confirmation to become Private.'))
        return interfaces

    def enable_discovery(self):
        selected = self.network_entries.get(self.network_choice.get())
        if not selected:
            self.notice('Select a network', 'Select the local network shared with your coordinator first.')
            return
        make_private = selected.get('category') == 'Public'
        if make_private and not self.ask('Trust this network?',
                f"Make {selected['interface']} ({selected['address']}) Private and enable discovery?\n\nPrivate networks can allow other Windows sharing rules. Continue only for a trusted home or office LAN."):
            return
        def work():
            from .worker_setup import launch_elevated
            result = launch_elevated({'program': sys.executable, 'interface': selected['interface'],
                'address': selected['address'], 'make_private': make_private}, 'setup-discovery.ps1', notify=self.setup_progress)
            marker = Path.home() / '.dyno' / 'worker-discovery-enabled'
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text('enabled', encoding='ascii')
            self.worker.log(result)
            self.start_discovery()
        self.background(work)

    def start_discovery(self):
        from .discovery import Advertisement, PAIR_PORT, local_interfaces, peer_on_lan, safe_label
        from .pairing import PairingServer
        self.stop_discovery(announce=False)
        interfaces = local_interfaces()
        self.events.put(('interfaces', local_interfaces(include_public=True)))
        if not interfaces:
            self.events.put(('status', 'No Private LAN found. Set your trusted LAN to Private, then enable discovery.'))
            return
        # Restrict the listener and advertisements to one concrete interface.
        interface = next((i for i in interfaces if i['interface'] == self.selected_network), None)
        if interface is None:
            if len(interfaces) > 1:
                self.events.put(('status', 'Choose the Private local network shared with your coordinator, then open pairing.'))
                return
            interface = interfaces[0]
        self.events.put(('selected_network', interface['interface']))
        def allowed(peer):
            return any(i['address'] == interface['address'] and peer_on_lan(peer, i) for i in local_interfaces())
        def confirm(code, name, stopped):
            event, answer = threading.Event(), []
            self.events.put(('confirm', (code, safe_label(name), event, answer)))
            for _ in range(110):
                if event.wait(1):
                    return bool(answer and answer[0])
                if stopped.is_set() or self.closing:
                    return False
            return False
        def install(request):
            from .worker_setup import launch_setup
            self.busy = True
            try:
                self.events.put(('status', 'Codes confirmed. Approve Windows connection setup to finish pairing.'))
                return json.loads(launch_setup(request | {'automatic': True}, notify=self.setup_progress))
            finally:
                self.busy = False
        try:
            self.pair_server = PairingServer(interface['address'], PAIR_PORT, allowed, confirm, install,
                lambda value: self.events.put(('status', value)))
            gpu = self.gpus[0]['name'] if self.gpus else 'NVIDIA GPU'
            self.advertisement = Advertisement(interface, socket.gethostname(), gpu)
            self.events.put(('status', f'Discoverable on {interface["interface"]} for 5 minutes. Open Nearby workers on your coordinator.'))
            server = self.pair_server
            def watch_interface():
                while not server.stopped.wait(5):
                    try:
                        valid = any(i['address'] == interface['address'] for i in local_interfaces())
                    except Exception:
                        valid = False
                    if not valid:
                        self.events.put(('status', 'Discovery stopped because the Private LAN changed.'))
                        server.close()
                        break
            threading.Thread(target=watch_interface, daemon=True).start()
        except Exception as exc:
            self.stop_discovery()
            self.events.put(('status', 'Discovery unavailable: ' + str(exc)))

    def stop_discovery(self, announce=True):
        if self.pair_server:
            self.pair_server.close()
            self.pair_server = None
        if self.advertisement:
            self.advertisement.close()
            self.advertisement = None
        if announce:
            self.events.put(('status', 'Discovery stopped. Open pairing when you want to connect another coordinator.'))

    def close(self):
        if self.busy:
            self.notice('Operation in progress', 'Wait for the current operation to finish before quitting.')
            return
        if self.worker.snapshot()['state'] == 'Listening' and not self.ask('Quit worker?', 'Quit and interrupt active pool requests?'):
            return
        self.closing = True
        self.stop_discovery()
        def stop_owned():
            self.telemetry.close()
            self.worker.stop()
        self.background(stop_owned)
        self.finish_close()

    def finish_close(self):
        if self.busy:
            self.root.after(100, self.finish_close)
        else:
            self.root.destroy()


def main():
    root = tk.Tk()
    if sys.platform != 'win32':
        root.withdraw()
        messagebox.showerror('Windows worker', 'This desktop companion currently targets native Windows with NVIDIA CUDA.')
        root.destroy()
        return 1
    WorkerApp(root)
    root.mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
