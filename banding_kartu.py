#!/usr/bin/env python3
"""Bandingkan kartu poller (/cfg/kartu.log) dengan kartu uji dari arsip (/cfg/kartu_arsip.log).

Dipakai selama uji kanari: bukti bahwa jalur arsip melihat email yang SAMA dengan poller.
Hanya membandingkan sejak kartu uji pertama ada (sebelumnya jalur arsip belum jalan).

  python3 banding_kartu.py
"""
import re
import sys

import config as C

BARIS = re.compile(r'^(\S+ \S+) \| (kartu|lewati) \| tag=(\S+) \| (.*)$')


def baca(p):
    out = []
    try:
        for b in open(p):
            m = BARIS.match(b.strip())
            if not m or m.group(2) != 'kartu':
                continue
            waktu, _, tag, sisa = m.groups()
            # sisa = "<uid/id> | <subjek>" untuk kartu, "<id> | <subjek>" untuk arsip
            bagian = sisa.split(' | ', 1)
            subj = (bagian[1] if len(bagian) > 1 else '').strip()
            out.append({'waktu': waktu, 'tag': tag, 'subj': subj,
                        'kunci': (tag, re.sub(r'\s+', ' ', subj).strip().lower()[:70])})
    except FileNotFoundError:
        return []
    return out


def main():
    poller = baca(C.path('kartu.log'))
    arsip = baca(C.path('kartu_arsip.log'))
    if not arsip:
        print('belum ada kartu uji dari arsip; jalankan notif_arsip.py dulu')
        return 1
    mulai = arsip[0]['waktu']
    poller = [k for k in poller if k['waktu'] >= mulai]
    kp = {k['kunci'] for k in poller}
    ka = {k['kunci'] for k in arsip}
    hilang = [k for k in poller if k['kunci'] not in ka]
    lebih = [k for k in arsip if k['kunci'] not in kp]
    import os
    import time
    _flip = C.path('flip_arsip.txt')
    if os.path.exists(_flip):
        _t = open(_flip).read().strip()
        poller = [k for k in poller if k['waktu'] < _t]
        print('catatan: kartu poller dihitung hanya SEBELUM flip (%s) — sesudah flip kartu '
              'dikirim jalur arsip, poller cuma OTP + cadangan' % _t)
    print('periode %s s/d sekarang' % mulai)
    print('kartu poller: %d | kartu uji arsip: %d' % (len(poller), len(arsip)))
    if hilang:
        print('❗ kartu poller TANPA padanan di arsip (%d):' % len(hilang))
        for k in hilang[:10]:
            print('   %s [%s] %s' % (k['waktu'], k['tag'], k['subj'][:60]))
    else:
        print('✅ semua kartu poller punya padanan di arsip')
    if lebih:
        print('ℹ️  kartu arsip tanpa padanan poller (%d) — arsip melihat lebih banyak/folder lain:' % len(lebih))
        for k in lebih[:10]:
            print('   %s [%s] %s' % (k['waktu'], k['tag'], k['subj'][:60]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
