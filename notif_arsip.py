#!/usr/bin/env python3
"""Notifier KANARI — kirim kartu email dari FEED arsip ke topik monitoring (BUKAN chat utama).

Tujuan: membuktikan jalur notifikasi berbasis arsip setara dengan poller IMAP sebelum dipindah.
  - kartu diberi penanda 🧪 supaya jelas ini uji, bukan notifikasi utama
  - setiap kartu dicatat ke /cfg/kartu_arsip.log (format SAMA dengan kartu.log poller) sehingga
    kedua jalur bisa dibandingkan otomatis oleh pembanding.py --kartu
  - aturan exclude pengirim/subjek + folder yang dipakai poller ikut diterapkan di sini
  - kalau feed lebih tua dari 10 menit: TIDAK mengirim apa pun (poller tetap jalur utama)

Pakai:
  python3 notif_arsip.py                 # normal (cron tiap 2 menit)
  python3 notif_arsip.py --mulai-sekarang
  python3 notif_arsip.py --status
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import config as C
import otp as O
import sumber_arsip as S

STATE = C.path('state_notif_arsip.json')
LOG_KARTU = C.path('kartu_arsip.log')
CHAT = os.environ.get('KANARI_CHAT') or '-1003949807125'
THREAD = os.environ.get('KANARI_THREAD') or '57'
BASI_FEED = 10
# CATATAN PENTING (temuan 17 Okt): Gmail kadang hanya menyimpan salinan di LABEL
# ("[Gmail]/Penting"), tanpa salinan INBOX. Kalau folder label ikut dibuang, email seperti itu
# hilang dari notifikasi. Jadi label DIPERBOLEHKAN; yang dibuang hanya folder sampah/keluaran.
BUANG_RE = re.compile(r'(spam|junk|bulk|sampah|trash|draf|draft|sent|terkirim|template)', re.I)
KUNCI_MAKS = 400


def kini_wib():
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=C.TZ_OFFSET)


def muat_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {'last_id': 0}


def simpan_state(s):
    tmp = STATE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(s, f)
    os.replace(tmp, STATE)


def tulis_log(baris):
    with open(LOG_KARTU, 'a') as f:
        f.write(baris + '\n')


def kirim(teks):
    p = {'chat_id': CHAT, 'text': teks, 'parse_mode': 'HTML',
         'disable_web_page_preview': 'true', 'message_thread_id': THREAD}
    req = urllib.request.Request(
        'https://api.telegram.org/bot%s/sendMessage' % C.TG_TOKEN,
        data=urllib.parse.urlencode(p).encode())
    with urllib.request.urlopen(req, timeout=30) as f:
        return json.loads(f.read().decode())


def jalan(mulai_sekarang=False):
    items, info = S.baca_feed()
    if items is None:
        print('🚨 notif_arsip: %s' % info)
        return 2
    try:
        umur = (kini_wib() - datetime.fromisoformat(info)).total_seconds() / 60.0
    except Exception:
        umur = 0.0
    if umur > BASI_FEED:
        # sengaja diam: poller masih jalur utama; jangan kirim dari data basi
        return 0

    st = muat_state()
    if mulai_sekarang:
        st['last_id'] = max([i['id'] for i in items], default=0)
        simpan_state(st)
        print('penanda notifier disetel ke id %d' % st['last_id'])
        return 0

    baru = sorted([i for i in items if i['id'] > st['last_id']], key=lambda i: i['id'])
    if not baru:
        return 0

    terkirim = 0
    for i in baru:
        if i.get('outgoing'):
            st['last_id'] = max(st['last_id'], i['id'])
            continue
        subj = i.get('subj') or '(tanpa subjek)'
        dari = i.get('dari') or ''
        folder = i.get('folder') or ''
        if (any(rx.search(dari) for rx in C.SKIP_FROM_RE)
                or any(rx.search(subj) for rx in C.SKIP_SUBJECT_RE)):
            tulis_log('%s | lewati | tag=%s | %s | %s' % (
                kini_wib().strftime('%Y-%m-%d %H:%M:%S'),
                C.EMAIL_TO_TAG.get((i.get('akun') or '').lower(), '?'), i['id'], subj[:60]))
            st['last_id'] = max(st['last_id'], i['id'])
            continue
        if folder and BUANG_RE.search(folder):
            st['last_id'] = max(st['last_id'], i['id'])
            continue
        # satu email bisa tersimpan di beberapa folder (INBOX + label) -> kartu hanya sekali
        kunci = '%s|%s|%s' % (i.get('akun'), (subj or '')[:80], i.get('sent'))
        if kunci in st.get('kunci', []):
            st['last_id'] = max(st['last_id'], i['id'])
            continue

        tag = C.EMAIL_TO_TAG.get((i.get('akun') or '').lower()) or (i.get('akun') or '?').split('@')[0]
        try:
            kirim_dt = datetime.fromisoformat((i.get('sent') or '').split('.')[0])
            lag = max(0.0, (kini_wib() - kirim_dt).total_seconds() / 60.0)
            lag_s = '%.1fm' % lag
        except Exception:
            lag_s = '?'

        baris = ['🧪 <b>UJI ARSIP</b> · %s' % C.E(i.get('akun') or tag),
                 '    dari : %s' % C.E(dari),
                 '    subj : %s' % C.E(subj),
                 '    tgl  : %s' % C.E(i.get('sent') or '?')]
        if O.mirip(subj):
            d = O.cari(subj, body=i.get('teks') or '', html=i.get('html') or '')
            if d:
                baris.insert(3, '    🔑 kode : %s' % C.E(d.get('kode')))
        baris += ['    folder : %s' % C.E(folder or '?'),
                  '    lag  : %s (arsip → terlihat)' % lag_s,
                  '    status : arsip tidak menyimpan status baca',
                  '    arsip : id %s' % i['id']]
        try:
            kirim('\n'.join(baris))
            terkirim += 1
            st.setdefault('kunci', []).append(kunci)
            st['kunci'] = st['kunci'][-KUNCI_MAKS:]
            tulis_log('%s | kartu | tag=%s | %s | %s' % (
                kini_wib().strftime('%Y-%m-%d %H:%M:%S'), tag, i['id'], subj[:80]))
        except Exception as e:
            print('🚨 notif_arsip: gagal kirim id %s (%s)' % (i['id'], type(e).__name__))
            return 2
        st['last_id'] = max(st['last_id'], i['id'])
        simpan_state(st)
        time.sleep(0.4)

    simpan_state(st)
    return 0


def status():
    st = muat_state()
    print('penanda notifier: %s' % st.get('last_id'))
    try:
        b = open(LOG_KARTU).read().splitlines()
        print('kartu uji terkirim: %d | baris terakhir: %s' % (
            len([x for x in b if '| kartu |' in x]), b[-1][:120] if b else '(belum ada)'))
    except FileNotFoundError:
        print('belum ada kartu uji terkirim')
    return 0


if __name__ == '__main__':
    a = argparse.ArgumentParser()
    a.add_argument('--mulai-sekarang', action='store_true')
    a.add_argument('--status', action='store_true')
    arg = a.parse_args()
    sys.exit(status() if arg.status else jalan(arg.mulai_sekarang))
