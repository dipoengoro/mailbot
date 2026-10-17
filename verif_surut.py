#!/usr/bin/env python3
"""Verifikasi surut: kartu poller vs email di database arsip (26 jam terakhir).
Dijalankan DI DALAM container mailbot (butuh config untuk peta email->tag)."""
import re
import sys

sys.path.insert(0, '/cfg')
import config as C

def kunci(tag, subj):
    s = (subj or '').strip().lower()
    s = re.sub(r'^(re|fwd|fw)\s*:\s*', '', s)
    return (tag, re.sub(r'\s+', ' ', s)[:60])

akun = {}
try:
    for b in open('/tmp/akun.txt'):
        if '|' in b:
            i, e = b.strip().split('|', 1)
            akun[i] = C.EMAIL_TO_TAG.get(e.strip().lower(), e.split('@')[0])
except FileNotFoundError:
    print('file /tmp/akun.txt tidak ada')
    sys.exit(1)

arsip = {}
n = 0
for b in open('/tmp/arsip24.txt'):
    p = b.rstrip('\n').split('|')
    if len(p) < 4:
        continue
    n += 1
    arsip.setdefault(kunci(akun.get(p[0], '?'), p[2]), []).append((p[1], p[3]))

kartu = []
for b in open('/cfg/kartu.log'):
    m = re.match(r'^(\S+ \S+) \| kartu \| tag=(\S+) \| (\d+) \| (.*)$', b.strip())
    if m:
        kartu.append((m.group(1), m.group(2), m.group(4)))

hilang = [k for k in kartu if kunci(k[1], k[2]) not in arsip]
ada = len(kartu) - len(hilang)
print('== verifikasi surut (database, bukan API) ==')
print('email masuk di arsip (26 jam): %d | kartu poller: %d' % (n, len(kartu)))
print('kelengkapan: %d/%d = %.1f%%' % (ada, len(kartu), 100.0 * ada / len(kartu) if kartu else 0))
for w, t, s in hilang:
    print('  TANPA ARSIP: %s | %s | %s' % (w, t, s[:66]))
print()
print('catatan: kartu yang subjeknya sama persis dihitung sekali (key tag+subjek).')
