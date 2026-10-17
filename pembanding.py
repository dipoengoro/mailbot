#!/usr/bin/env python3
"""Pembanding: kartu yang dikirim poller (kartu.log) vs email yang dilihat arsip (arsip.log).

Fase 1 "satu sumber" — membuktikan MailArchiver melihat hal yang sama dengan jalur IMAP.
Jalankan di dalam container mailbot:
    python3 /cfg/pembanding.py
"""
import re
import sys


def baca(p):
    try:
        return open(p).read().splitlines()
    except FileNotFoundError:
        return []


def kunci(tag, subj):
    s = (subj or '').strip().lower()
    s = re.sub(r'^(re|fwd|fw)\s*:\s*', '', s)
    return (tag, re.sub(r'\s+', ' ', s)[:60])


mulai = None
for b in baca('/cfg/kartu.log'):
    m0 = re.match(r'^(\S+ \S+) \| kartu \|', b)
    if m0:
        mulai = m0.group(1)
        break

kartu, arsip = [], []
for b in baca('/cfg/kartu.log'):
    m = re.match(r'^(\S+ \S+) \| kartu \| tag=(\S+) \| (\d+) \| (.*)$', b)
    if m:
        kartu.append({'waktu': m.group(1), 'tag': m.group(2), 'uid': m.group(3), 'subj': m.group(4)})
for b in baca('/cfg/arsip.log'):
    m = re.match(r'^(\S+ \S+) WIB \| id=(\d+) \| tag=(\S+) \| (\S+) \| lag=(\S+)m \| (\S+) \| (.*)$', b)
    if m and (mulai is None or m.group(1) >= mulai):
        arsip.append({'waktu': m.group(1), 'id': m.group(2), 'tag': m.group(3), 'subj': m.group(7)})

ka, aa = {}, {}
for k in kartu:
    ka.setdefault(kunci(k['tag'], k['subj']), []).append(k)
for a in arsip:
    aa.setdefault(kunci(a['tag'], a['subj']), []).append(a)

cocok = set(ka) & set(aa)
hanya_kartu = sorted(set(ka) - set(aa))
hanya_arsip = sorted(set(aa) - set(ka))

print('== pembanding kartu poller vs arsip MailArchiver ==')
print('kartu terkirim: %d | email di arsip: %d | yang cocok: %d' % (len(kartu), len(arsip), len(cocok)))
if kartu:
    print('kelengkapan arsip: %d/%d kartu ada di arsip (%.0f%%)' % (
        len(cocok), len(kartu), 100.0 * len(cocok) / len(kartu)))
if hanya_kartu:
    print()
    print('!! KARTU TANPA ARSIP (%d) — ini yang berbahaya kalau nanti pindah:' % len(hanya_kartu))
    for t, s in hanya_kartu:
        print('   %s | %s' % (t, s))
if hanya_arsip:
    print()
    print('arsip tanpa kartu (%d) — biasanya wajar (aturan exclude / folder tak dipantau):' % len(hanya_arsip))
    for t, s in hanya_arsip[:15]:
        print('   %s | %s' % (t, s))
if not kartu and not arsip:
    print('belum ada data di kedua log')
