#!/usr/bin/env python3
"""Laporan uji sibuk: bandingkan email [UJI SIBUK] yang DIKIRIM dengan yang ADA di feed arsip.

Dijalankan di dalam container bot (butuh config). Tidak menyentuh database langsung: feed arsip
sudah merupakan cermin tabel, dan item uji (192 email) masih muat di jendela akumulatif feed.

  python3 uji_sibuk_laporan.py [--maks-contoh 8]
"""
import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, '/cfg')
import config as C

PENANDA = '[UJI SIBUK]'


def kini_wib():
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=C.TZ_OFFSET)


def main():
    maks_contoh = 8
    if '--maks-contoh' in sys.argv:
        maks_contoh = int(sys.argv[sys.argv.index('--maks-contoh') + 1])

    kirim = []
    try:
        for b in open(C.path('uji_sibuk.log')):
            p = [x.strip() for x in b.split('|')]
            if len(p) < 6 or p[1] != 'kirim':
                continue
            kirim.append({'waktu': p[0], 'ronde': int(p[2].split('=')[1]),
                          'dari': p[3].split('=')[1], 'ke': p[4].split('=')[1],
                          'subj': p[5]})
    except FileNotFoundError:
        print('belum ada email uji terkirim')
        return 1
    if not kirim:
        print('belum ada email uji terkirim')
        return 1

    try:
        feed = json.load(open(C.path('arsip_feed.json')))
        items = feed.get('items') or []
    except Exception as e:
        print('🚨 feed arsip tidak terbaca: %s' % type(e).__name__)
        return 2

    # Subjek di arsip memuat jam ("[UJI SIBUK] #3 21:35:02"), sedangkan catatan kirim hanya
    # "[UJI SIBUK] #3" -> cocokkan lewat (akun tujuan, nomor ronde), bukan teks penuh.
    import re
    ada = {}
    for i in items:
        s = i.get('subj') or ''
        m = re.match(r'\[UJI SIBUK\] #(\d+)', s)
        if m and not i.get('outgoing'):
            ada[((i.get('akun') or '').lower(), int(m.group(1)))] = i

    per_akun = defaultdict(lambda: [0, 0])
    lag = []
    hilang = []
    for k in kirim:
        per_akun[k['ke']][0] += 1
        email_tujuan = (C.A[k['ke']]['email'] or '').lower()
        it = ada.get((email_tujuan, k['ronde']))
        if it:
            per_akun[k['ke']][1] += 1
            # Lag diukur oleh pengamat arsip saat email PERTAMA terlihat (arsip.log),
            # bukan dari kolom tanggal: kolom tanggal tidak menunjukkan kapan arsip menerimanya.
            try:
                for baris_log in open(C.path('arsip.log')):
                    if ('id=%s ' % it['id']) in baris_log and 'lag=' in baris_log:
                        lag.append(float(baris_log.split('lag=')[1].split('m')[0]))
                        break
            except Exception:
                pass
        else:
            hilang.append(k)

    total = len(kirim)
    ketemu = total - len(hilang)
    print('🧪 Uji sibuk — kelengkapan arsip')
    print('- ronde: %d | email dikirim: %d | ditemukan di arsip: %d (%.1f%%)'
          % (max(k['ronde'] for k in kirim), total, ketemu, 100.0 * ketemu / total))
    print('- per akun: ' + ' | '.join('%s %d/%d' % (t, per_akun[t][1], per_akun[t][0])
                                      for t in sorted(per_akun)))
    if lag:
        lag.sort()
        p90 = lag[min(len(lag) - 1, int(0.9 * len(lag)))]
        print('- lag arsip: median %.1f m | p90 %.1f m | maks %.1f m (n=%d)'
              % (statistics.median(lag), p90, lag[-1], len(lag)))
    if hilang:
        print('- ❗ belum ditemukan (%d), contoh:' % len(hilang))
        for k in hilang[:maks_contoh]:
            print('   ronde %d → %s | %s' % (k['ronde'], k['ke'], k['subj']))
    else:
        print('- ✅ semua email uji ditemukan di arsip')
    print('- feed dibuat: %s' % (feed.get('dibuat_wib') or '?'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
