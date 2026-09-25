#!/usr/bin/env python3
"""Supervisor: satu container, dua proses (poller + handler), auto-restart.

Kenapa begini: kalau poller atau handler jalan sebagai container terpisah dan salah
satunya mati diam-diam, notifikasi berhenti tanpa ada yang tahu. Supervisor ini yang
menjaga: anaknya mati -> langsung dihidupkan lagi (dengan jeda naik 5s, 10s, ... maks 60s),
dan log-nya ditulis ke STATE_DIR/*.log supaya bisa dipantau watchdog/monitoring.

Container dijalankan dengan --restart unless-stopped, jadi kalau supervisor-nya sendiri
mati (atau VPS reboot), Docker yang naikin lagi.
"""
import os
import subprocess
import sys
import time

# Kode dan data dipisah: kode di image (read-only), state/log di volume.
CODE_DIR = os.environ.get('MAILBOT_CODE_DIR') or os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.environ.get('MAILBOT_STATE_DIR') or CODE_DIR

JOBS = [
    ('poller', [sys.executable, f'{CODE_DIR}/poller.py']),
    ('handler', [sys.executable, f'{CODE_DIR}/handler.py', '--minutes', '100000']),
]

procs = {}


def jam():
    """Jam WIB (UTC+7) untuk log — offset tetap, biar tidak butuh tzdata."""
    from datetime import datetime, timezone, timedelta
    return datetime.now(timezone(timedelta(hours=7))).strftime('%H:%M:%S')


def start(name, cmd):
    # Output anak ditulis ke file (buat watchdog) SEKALIGUS ke stdout container,
    # supaya ikut ketangkep promtail/Loki. Pakai tee, bukan redirect murni.
    baris = ' '.join(cmd)
    p = subprocess.Popen(f'{baris} 2>&1 | tee -a {STATE_DIR}/{name}.log', shell=True,
                         stdout=sys.stdout, stderr=sys.stderr, cwd=CODE_DIR,
                         bufsize=1, text=True)
    procs[name] = {'p': p, 'cmd': cmd, 'since': time.time(), 'restarts': procs.get(name, {}).get('restarts', 0)}
    print(jam(), 'start', name, 'pid', p.pid, flush=True)


for _n, _c in JOBS:
    start(_n, _c)

print(jam(), 'supervisor aktif — pantau tiap 15 detik', flush=True)

while True:
    time.sleep(15)
    for _n, _c in JOBS:
        _st = procs[_n]
        _rc = _st['p'].poll()
        if _rc is None:
            continue
        _up = int(time.time() - _st['since'])
        _st['restarts'] += 1
        _delay = min(60, 5 * _st['restarts'])
        print(jam(), f'MATI {_n} (exit {_rc}) setelah {_up}s '
              f'-> restart ke-{_st["restarts"]} dalam {_delay}s', flush=True)
        time.sleep(_delay)
        start(_n, _c)
