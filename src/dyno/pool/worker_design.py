"""Desktop presentation for Dyno Worker; no network or process side effects."""
import math
import time
import tkinter as tk
from tkinter import ttk

BG = '#101318'
CARD = '#191e26'
EDGE = '#2a3240'
TEXT = '#eef2f8'
MUTED = '#98a6b9'
ACCENT = '#8ce5c4'


def label(parent, text='', size=11, color=TEXT, **kwargs):
    return tk.Label(parent, text=text, font=('Segoe UI', size), fg=color,
                    bg=parent.cget('background'), anchor='w', **kwargs)


def panel(parent):
    return tk.Frame(parent, bg=CARD, highlightbackground=EDGE, highlightthickness=1)


def build(app):
    root = app.root
    root.title('Dyno Worker · Desktop preview')
    root.geometry('1060x940')
    root.minsize(940, 780)
    root.configure(bg=BG)
    root.option_add('*TCombobox*Listbox.background', CARD)
    root.option_add('*TCombobox*Listbox.foreground', TEXT)
    root.option_add('*TCombobox*Listbox.selectBackground', EDGE)
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', font=('Segoe UI', 10), background=CARD, foreground=TEXT)
    style.configure('TButton', padding=(16, 10), background=EDGE, borderwidth=0, focusthickness=1)
    style.configure('TButton', bordercolor=EDGE, lightcolor=EDGE, darkcolor=EDGE)
    style.map('TButton', background=[('active', '#354252'), ('disabled', '#202631')], foreground=[('disabled', '#718095')])
    style.configure('Primary.TButton', background=ACCENT, foreground=BG, font=('Segoe UI', 10, 'bold'))
    style.map('Primary.TButton', background=[('active', '#b3f3dc'), ('disabled', '#293e3a')], foreground=[('disabled', '#899f97')])
    style.configure('TCombobox', fieldbackground='#222a35', background=EDGE, padding=8, arrowcolor=TEXT)
    style.configure('TCombobox', bordercolor=EDGE, lightcolor=EDGE, darkcolor=EDGE)
    style.map('TCombobox', fieldbackground=[('readonly', '#222a35')], foreground=[('readonly', TEXT)])
    style.configure('TEntry', fieldbackground='#222a35', insertcolor=TEXT, padding=9)
    style.configure('TNotebook', background=BG, borderwidth=0)
    style.configure('TNotebook.Tab', padding=(22, 12), background=BG, foreground=MUTED)
    style.configure('TNotebook.Tab', bordercolor=EDGE, lightcolor=EDGE, darkcolor=EDGE)
    style.configure('TNotebook', bordercolor=EDGE, lightcolor=EDGE, darkcolor=EDGE)
    style.map('TNotebook.Tab', background=[('selected', CARD)], foreground=[('selected', ACCENT)])
    style.configure('Horizontal.TProgressbar', background=ACCENT, troughcolor=EDGE, borderwidth=0, lightcolor=ACCENT, darkcolor=ACCENT, bordercolor=EDGE, thickness=5)
    shell = tk.Frame(root, bg=BG)
    shell.pack(fill='both', expand=True, padx=28, pady=22)
    header = tk.Frame(shell, bg=BG)
    header.pack(fill='x', pady=(0, 18))
    label(header, 'DYNO  /  WORKER', 11, ACCENT).pack(anchor='w')
    label(header, 'Your GPU. Connected.', 27).pack(side='left', pady=(8, 0))
    ttk.Button(header, text='Save diagnostics', command=app.export).pack(side='right')
    top = panel(shell)
    top.pack(fill='x', pady=(0, 14))
    inner = tk.Frame(top, bg=CARD)
    inner.pack(fill='x', padx=20, pady=16)
    app.status = tk.StringVar(value='Stopped')
    app.status_dot = tk.Canvas(inner, width=16, height=24, bg=CARD, highlightthickness=0)
    app.status_dot.pack(side='left', padx=(0, 10))
    app.dot = app.status_dot.create_oval(3, 8, 11, 16, fill=MUTED, outline='')
    label(inner, textvariable=app.status, size=17).pack(side='left')
    app.device = tk.StringVar(value='CUDA0')
    app.stop_button = ttk.Button(inner, text='Stop worker', command=app.stop)
    app.stop_button.pack(side='right')
    app.start_button = ttk.Button(inner, text='Start worker', style='Primary.TButton', command=app.start)
    app.start_button.pack(side='right', padx=8)
    app.devices = ttk.Combobox(inner, textvariable=app.device, values=['CUDA0'], width=9, state='readonly')
    app.devices.pack(side='right', padx=8)
    app.metrics = tk.StringVar(value='Checking your NVIDIA GPU…')
    label(top, textvariable=app.metrics, size=10, color=MUTED).pack(anchor='w', padx=20, pady=(0, 16))
    cards = tk.Frame(shell, bg=BG)
    cards.pack(fill='x', pady=(0, 16))
    app.metric_values = {}
    app.metric_bars = {}
    for col, (key, title) in enumerate([('memory', 'GPU MEMORY'), ('load', 'GPU UTILIZATION'), ('temperature', 'TEMPERATURE')]):
        cards.columnconfigure(col, weight=1, uniform='metrics')
        card = panel(cards)
        card.grid(row=0, column=col, sticky='ew', padx=(0 if col == 0 else 7, 0 if col == 2 else 7))
        label(card, title, 9, MUTED).pack(anchor='w', padx=18, pady=(14, 6))
        app.metric_values[key] = tk.StringVar(value='—')
        label(card, textvariable=app.metric_values[key], size=24).pack(anchor='w', padx=18)
        bar = ttk.Progressbar(card, maximum=100)
        bar.pack(fill='x', padx=18, pady=(10, 16))
        app.metric_bars[key] = bar
    label(shell, 'DESKTOP PREVIEW     •     GPU metrics include other apps     •     Encrypted SSH connection', 9, MUTED).pack(side='bottom', anchor='w', pady=(14, 0))
    tabs = ttk.Notebook(shell)
    tabs.pack(fill='both', expand=True)
    app.tabs = tabs
    connect_outer = tk.Frame(tabs, bg=CARD)
    canvas = tk.Canvas(connect_outer, bg=CARD, highlightthickness=0)
    scrollbar = ttk.Scrollbar(connect_outer, command=canvas.yview)
    scrollbar.pack(side='right', fill='y')
    canvas.pack(side='left', fill='both', expand=True)
    canvas.configure(yscrollcommand=scrollbar.set)
    connect = tk.Frame(canvas, bg=CARD, padx=22, pady=18)
    content_id = canvas.create_window(0, 0, anchor='nw', window=connect)
    canvas.bind('<Configure>', lambda e: canvas.itemconfigure(content_id, width=e.width))
    connect.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
    def wheel(event):
        widget = event.widget
        while widget:
            if widget is connect_outer:
                canvas.yview_scroll(-int(event.delta / 120), 'units')
                break
            widget = getattr(widget, 'master', None)
    root.bind('<MouseWheel>', wheel, add='+')
    activity = tk.Frame(tabs, bg=CARD, padx=18, pady=18)
    manual = tk.Frame(tabs, bg=CARD, padx=22, pady=18)
    tabs.add(connect_outer, text='Connect')
    tabs.add(activity, text='Activity')
    tabs.add(manual, text='Manual setup')
    label(connect, 'Connect a coordinator', 18).pack(anchor='w')
    label(connect, 'Choose the same local network on both devices, then compare their pairing codes.', 10, MUTED).pack(anchor='w', pady=(5, 18))
    label(connect, '01   LOCAL NETWORK', 9, MUTED).pack(anchor='w')
    network_row = tk.Frame(connect, bg=CARD)
    network_row.pack(fill='x', pady=(8, 16))
    app.networks = ttk.Combobox(network_row, textvariable=app.network_choice, state='readonly')
    app.networks.pack(side='left', fill='x', expand=True)
    app.networks.bind('<<ComboboxSelected>>', lambda event: setattr(app, 'selected_network', app.network_entries.get(app.network_choice.get(), {}).get('interface', '')))
    app.action_buttons = []
    refresh = ttk.Button(network_row, text='Refresh', command=lambda: app.background(app.refresh_networks))
    refresh.pack(side='right', padx=(10, 0))
    app.action_buttons.append(refresh)
    label(connect, '02   DISCOVERY & PAIRING', 9, MUTED).pack(anchor='w')
    row = tk.Frame(connect, bg=CARD)
    row.pack(fill='x', pady=(8, 16))
    for title, callback, primary in [
        ('Enable discovery', app.enable_discovery, True),
        ('Open pairing · 5 min', lambda: app.background(app.start_discovery), False),
        ('Stop discovery', lambda: app.background(app.stop_discovery), False),
    ]:
        button = ttk.Button(row, text=title, command=callback, style='Primary.TButton' if primary else 'TButton')
        button.pack(side='left', padx=(0, 10))
        app.action_buttons.append(button)
    telemetry_button = ttk.Button(connect, text='Enable telemetry for paired coordinator', command=app.enable_telemetry)
    telemetry_button.pack(anchor='w', pady=(0, 12))
    app.action_buttons.append(telemetry_button)
    app.telemetry_status = tk.StringVar(value='Starting local telemetry...')
    label(connect, textvariable=app.telemetry_status, size=10, color=MUTED, wraplength=820).pack(anchor='w', pady=(0, 12))
    notice = tk.Frame(connect, bg='#202b36', padx=16, pady=12)
    notice.pack(fill='x')
    app.notice_title = tk.StringVar(value='Ready to connect')
    label(notice, textvariable=app.notice_title, size=11, color=ACCENT).pack(anchor='w')
    label(notice, textvariable=app.discovery_status, size=10, color=TEXT, wraplength=820, justify='left').pack(anchor='w', pady=(5, 0))
    app.progress = ttk.Progressbar(notice, mode='indeterminate')
    app.progress.pack(fill='x', pady=(10, 0))
    app.progress_note = tk.StringVar(value='Setup progress will appear here.')
    label(notice, textvariable=app.progress_note, size=9, color=MUTED).pack(anchor='w', pady=(6, 0))
    tools = tk.Frame(activity, bg=CARD)
    tools.pack(fill='x', pady=(0, 12))
    label(tools, 'Activity log', 18).pack(side='left')
    app.log_search = tk.StringVar()
    ttk.Entry(tools, textvariable=app.log_search, width=22).pack(side='right', padx=8)
    label(tools, 'Search', 10, MUTED).pack(side='right')
    app.follow_logs = tk.BooleanVar(value=True)
    ttk.Checkbutton(tools, text='Follow latest', variable=app.follow_logs).pack(side='right', padx=12)
    app.log_text = tk.Text(activity, wrap='word', state='disabled', bg='#10151c', fg='#c8d3e2',
                           insertbackground=TEXT, font=('Cascadia Mono', 10), relief='flat', padx=14, pady=12)
    scroll = ttk.Scrollbar(activity, command=app.log_text.yview)
    scroll.pack(side='right', fill='y')
    app.log_text.configure(yscrollcommand=scroll.set)
    app.log_text.pack(fill='both', expand=True)
    app.log_text.tag_configure('error', foreground='#ffaaa8')
    app.log_text.tag_configure('info', foreground='#8ce5c4')
    label(manual, 'Connect with a public key', 18).pack(anchor='w')
    label(manual, 'Use this only when automatic pairing is unavailable.', 10, MUTED).pack(anchor='w', pady=(5, 14))
    app.mac_ip = tk.StringVar()
    label(manual, 'Coordinator local IPv4 address', 10, MUTED).pack(anchor='w')
    ttk.Entry(manual, textvariable=app.mac_ip).pack(fill='x', pady=(4, 10))
    label(manual, 'Ed25519 public key', 10, MUTED).pack(anchor='w')
    app.key = tk.Text(manual, height=2, bg=BG, fg=TEXT, insertbackground=TEXT, relief='flat', font=('Cascadia Mono', 10))
    app.key.pack(fill='x', pady=(4, 10))
    button = ttk.Button(manual, text='Set up secure connection', command=app.setup)
    button.pack(anchor='w')
    app.action_buttons.append(button)
    app.connection = tk.Text(manual, height=3, bg=CARD, fg=MUTED, relief='flat', font=('Segoe UI', 10), state='disabled', wrap='word')
    app.connection.pack(fill='both', expand=True, pady=(12, 0))
    app.motion = tk.BooleanVar(value=True)
    ttk.Checkbutton(header, text='Animations', variable=app.motion).pack(side='right', padx=16)
    app._progress_active = False
    app._busy_since = None
    app._bar_values = {'memory': 0, 'load': 0, 'temperature': 0}
    app._bar_targets = dict(app._bar_values)
    app._visual_state = 'Stopped'
    animate(app)


def animate(app):
    if app.closing:
        return
    running = app._visual_state == 'Listening'
    app.status_dot.itemconfigure(app.dot, fill=ACCENT if running else '#efaa7b' if app.busy else MUTED)
    radius = 4 + (math.sin(time.monotonic() * 2) + 1) if running and app.motion.get() else 4
    app.status_dot.coords(app.dot, 7-radius, 12-radius, 7+radius, 12+radius)
    for key, target in app._bar_targets.items():
        app._bar_values[key] += (target - app._bar_values[key]) * (.18 if app.motion.get() else 1)
        app.metric_bars[key]['value'] = app._bar_values[key]
    if app.busy:
        if app._busy_since is None:
            app._busy_since = time.monotonic()
        elapsed = int(time.monotonic() - app._busy_since)
        app.progress_note.set(f'Working · {elapsed // 60}:{elapsed % 60:02d} elapsed. You can inspect Activity while setup runs.')
    else:
        app._busy_since = None
        app.progress_note.set('Pairing window closes after five minutes. Reopen it to connect another device.')
    active = app.busy and app.motion.get()
    if active != app._progress_active:
        app.progress.start(18) if active else app.progress.stop()
        if not active:
            app.progress['value'] = 0
        app._progress_active = active
    app.root.after(40 if app.motion.get() else 250, lambda: animate(app))


def ask(app, title, message, timeout=None):
    """A keyboard-accessible confirmation inside the client, rather than an OS popup."""
    if getattr(app, '_dialog_open', False):
        return False
    app._dialog_open = True
    answer = tk.BooleanVar(value=False)
    completed = tk.BooleanVar(value=False)
    overlay = tk.Frame(app.root, bg=BG)
    overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
    card = panel(overlay)
    card.place(relx=.5, rely=.5, anchor='center', width=700)
    label(card, title, 23).pack(anchor='w', padx=28, pady=(26, 16))
    label(card, message, 12, wraplength=635, justify='left').pack(anchor='w', padx=28)
    row = tk.Frame(card, bg=CARD)
    row.pack(fill='x', padx=28, pady=26)
    def finish(value):
        answer.set(value)
        completed.set(True)
    cancel = ttk.Button(row, text='Cancel', command=lambda: finish(False))
    cancel.pack(side='left')
    button = ttk.Button(row, text='Confirm', style='Primary.TButton', command=lambda: finish(True))
    button.pack(side='right')
    escape_binding = app.root.bind('<Escape>', lambda event: (finish(False), 'break')[-1], add='+')
    def cycle_focus(event):
        (button if app.root.focus_get() is cancel else cancel).focus_set()
        return 'break'
    tab_binding = app.root.bind('<Tab>', cycle_focus, add='+')
    reverse_binding = app.root.bind('<Shift-Tab>', cycle_focus, add='+')
    overlay.grab_set()
    cancel.focus_set()
    timer = app.root.after(int(timeout * 1000), lambda: finish(False)) if timeout else None
    try:
        app.root.wait_variable(completed)
        return answer.get()
    finally:
        app.root.unbind('<Escape>', escape_binding)
        app.root.unbind('<Tab>', tab_binding)
        app.root.unbind('<Shift-Tab>', reverse_binding)
        if timer:
            app.root.after_cancel(timer)
        overlay.grab_release()
        overlay.destroy()
        app._dialog_open = False
