#!/usr/bin/env python3
"""Healthcheck container (dipakai HEALTHCHECK di Dockerfile).

Sehat kalau poller masih menulis heartbeat setiap siklus. Kalau heartbeat basi,
artinya poller mati atau macet (mis. koneksi IMAP menggantung) — dan itu kondisi
yang perlu kelihatan dari luar (docker healthcheck, Uptime Kuma, Prometheus).

Keluar 0 = sehat, 1 = tidak sehat. Stdout ikut muncul di `docker inspect`.
"""
import os
import sys
import time

sys.path.insert(0, os.environ.get('MAILBOT_CODE_DIR')
                or os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config as C

batas = int(os.environ.get('MAILBOT_HEALTH_MAX_AGE') or (C.POLL_INTERVAL * 3 + 120))
hb = C.path('.heartbeat')

if not os.path.exists(hb):
    # Belum ada siklus pertama yang selesai: jangan vonis sakit dulu.
    print('heartbeat belum ada (poller baru mulai?)')
    sys.exit(0)

umur = time.time() - os.path.getmtime(hb)
print('heartbeat %.0f detik lalu (batas %d detik)' % (umur, batas))
sys.exit(1 if umur > batas else 0)
