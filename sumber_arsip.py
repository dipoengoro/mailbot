#!/usr/bin/env python3
"""Pengamat arsip MailArchiver — Fase 1/2, mode PARALEL (belum mengubah notifikasi).

Sumber data: FEED dari DATABASE (`/cfg/arsip_feed.json`), bukan API. Alasannya: daftar
/api/v1/emails tidak lengkap (email di folder "DMARC Logs/Google" ada di tabel tapi tidak pernah
muncul di API), pageSize di-cap 100, dan tidak ada pencarian. Feed ditulis skrip host
`/root/arsip-feed/arsip_feed.py` tiap menit (bot tidak perlu kredensial DB).

Yang dicatat per email ke /cfg/arsip.log:
  - id arsip, tag akun, folder, LAG dari waktu kirim, pengirim, subjek
  - kalau subjeknya mirip email berkode: hasil otp.cari() dari ISI arsip (kode DISAMARKAN)
  - baris "... ringkas" per putaran: jumlah + lag min/tengah/maks

Pakai:
  python3 sumber_arsip.py                  # normal: catat yang baru, sunyi kalau tidak ada
  python3 sumber_arsip.py --mulai-sekarang # setel penanda ke id terbaru tanpa mencatat
  python3 sumber_arsip.py --ringkas        # 25 baris terakhir + ringkasan log
"""
import argparse
import json
import os
import statistics
import sys
from datetime import datetime, timedelta, timezone

import config as C
import otp as O

FEED = C.path('arsip_feed.json')
LOG = C.path('arsip.log')
STATE = C.path('state_arsip.json')
OTP_AMBIL = 6      # maksimal isi email yang diperiksa untuk uji deteksi OTP
ROTASI = 3 * 1024 * 1024
FEED_BASI = 15     # menit; feed lebih tua dari ini berarti skrip host bermasalah


def kini_wib():
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=C.TZ_OFFSET)


def tanda(s):
    """Samarkan kode: 587161 -> 5***1. Log bukan tempat kode."""
    s = str(s or '')
    return (s[0] + '*' * (len(s) - 2) + s[-1]) if len(s) > 2 else '***'


def muat_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except Exception:
        return {'last_id': 0, 'sejak': None}


def simpan_state(s):
    tmp = STATE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(s, f)
    os.replace(tmp, STATE)


def tulis(baris):
    if os.path.exists(LOG) and os.path.getsize(LOG) > ROTASI:
        os.replace(LOG, LOG + '.1')
    with open(LOG, 'a') as f:
        f.write(baris + '\n')


def baca_feed():
    """Kembalikan (items, dibuat_wib) atau (None, alasan gagal)."""
    try:
        with open(FEED) as f:
            d = json.load(f)
    except FileNotFoundError:
        return None, 'feed belum ada (%s)' % FEED
    except Exception as e:
        return None, 'feed rusak: %s' % type(e).__name__
    return (d.get('items') or []), (d.get('dibuat_wib') or '')


def jalan(mulai_sekarang=False):
    items, info = baca_feed()
    if items is None:
        print('🚨 sumber_arsip: %s' % info)
        return 2

    # feed basi = skrip host mati. Beri tahu, jangan diam.
    try:
        umur = (kini_wib() - datetime.fromisoformat(info)).total_seconds() / 60.0
        if umur > FEED_BASI:
            print('🚨 sumber_arsip: feed arsip basi %.0f menit — cek /root/arsip-feed (crontab host)' % umur)
            return 2
    except Exception:
        pass

    st = muat_state()
    # Catatan: id 0 adalah penanda yang SAH (mulai dari awal feed). Jangan pakai `not last_id`,
    # itu membuat penanda disetel ulang terus dan email baru tidak pernah dicatat.
    if mulai_sekarang:
        st['last_id'] = max([i['id'] for i in items], default=0)
        st['sejak'] = kini_wib().isoformat(timespec='seconds')
        simpan_state(st)
        print('penanda disetel ke id %d; catatan berikutnya hanya email baru' % st['last_id'])
        return 0

    baru = sorted([i for i in items if i['id'] > st['last_id']], key=lambda i: i['id'])
    if not baru:
        return 0

    st['last_id'] = max(st['last_id'], max(i['id'] for i in baru))
    masuk = [i for i in baru if not i.get('outgoing')]
    per_tag, lag = {}, []
    for i in masuk:
        tag = C.EMAIL_TO_TAG.get((i.get('akun') or '').lower())
        if not tag:
            tag = (i.get('akun') or '?').split('@')[0]
        per_tag[tag] = per_tag.get(tag, 0) + 1
        try:
            kirim = datetime.fromisoformat((i.get('sent') or '').split('.')[0])
            d = max(0.0, (kini_wib() - kirim).total_seconds() / 60.0)
            lag.append(d)
        except Exception:
            d = None
        tulis('%s WIB | id=%s | tag=%s | %s | lag=%s | %s | %s' % (
            kini_wib().strftime('%Y-%m-%d %H:%M:%S'), i['id'], tag, i.get('folder') or '?',
            ('%.1fm' % d) if d is not None else '?',
            (i.get('dari') or '')[:44], (i.get('subj') or '')[:70]))

    # uji deteksi OTP dari isi arsip, memakai otp.cari() yang SAMA dengan poller
    uji = [i for i in masuk if O.mirip(i.get('subj') or '')][:OTP_AMBIL]
    for i in uji:
        d = O.cari(i.get('subj') or '', body=i.get('teks') or '', html=i.get('html') or '')
        if d:
            tulis('    └ otp dari ARSIP: %s (sumber=%s, kata=%s, %s)' % (
                tanda(d.get('kode')), d.get('sumber'), d.get('kata'), d.get('berlaku') or '-'))

    if lag:
        lag.sort()
        ringkas = 'lag min %.1fm / tengah %.1fm / maks %.1fm' % (
            lag[0], statistics.median(lag), lag[-1])
    else:
        ringkas = 'tidak ada email masuk'
    tulis('    ... ringkas %s WIB: %d email baru (%s) | %s | %d isi diperiksa untuk OTP' % (
        kini_wib().strftime('%H:%M:%S'), len(masuk),
        ', '.join('%s %d' % kv for kv in sorted(per_tag.items())), ringkas, len(uji)))
    simpan_state(st)
    return 0


def ringkas_log(n=25):
    try:
        with open(LOG) as f:
            baris = f.read().splitlines()
    except FileNotFoundError:
        print('belum ada log arsip (%s)' % LOG)
        return 0
    masuk = [b for b in baris if ' WIB | id=' in b]
    ring = [b for b in baris if b.strip().startswith('... ringkas')]
    print('log: %d baris | email tercatat: %d | putaran: %d' % (len(baris), len(masuk), len(ring)))
    for b in baris[-n:]:
        print(b)
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--mulai-sekarang', action='store_true')
    p.add_argument('--ringkas', action='store_true')
    a = p.parse_args()
    sys.exit(ringkas_log() if a.ringkas else jalan(a.mulai_sekarang))
