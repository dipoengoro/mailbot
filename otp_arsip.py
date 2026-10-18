#!/usr/bin/env python3
"""Kartu OTP dari ARSIP (jalur MailArchiver) — pengganti jalur cepat poller.

Alasan: Dipo mau OTP juga lewat arsip, bukan IMAP. Konsekuensinya lebih lambat (antrean sync
MailArchiver + feed), jadi skrip ini dibuat sering (tiap menit) dan hanya mengurus email yang
mirip OTP.

- membaca /cfg/arsip_feed.json, memakai penanda sendiri (state_otp_arsip.json)
- aturan exclude pengirim/subjek sama dengan kartu biasa; folder sampah/keluaran dilewati
- kode disamarkan setelah C.TTL_OTP detik lewat antrean yang sama dengan handler (FILE_OTP)
- kalau feed basi > MAILBOT_BASI_FEED_KARTU menit: diam (poller yang mengambil alih)
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import config as C
import otp as O
import sumber_arsip as S

STATE = C.path('state_otp_arsip.json')
LOG = C.path('otp_arsip.log')
BASI_FEED = int(getattr(C, 'BASI_FEED_KARTU', 10))
BUANG = ('spam', 'junk', 'bulk', 'sampah', 'draf', 'draft', 'sent', 'terkirim', 'template')


def kini_wib():
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=C.TZ_OFFSET)


def muat():
    try:
        return json.load(open(STATE))
    except Exception:
        return {'last_id': 0}


def simpan(d):
    tmp = STATE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(d, f)
    os.replace(tmp, STATE)


def kirim(teks):
    p = {'chat_id': C.TG_CHAT, 'text': teks, 'parse_mode': 'HTML',
         'disable_web_page_preview': 'true'}
    if C.TG_THREAD:
        p['message_thread_id'] = C.TG_THREAD
    req = urllib.request.Request('https://api.telegram.org/bot%s/sendMessage' % C.TG_TOKEN,
                                 data=urllib.parse.urlencode(p).encode())
    with urllib.request.urlopen(req, timeout=30) as f:
        return json.loads(f.read().decode())


def jadwalkan(res, kode, subj, akun, teks):
    """Samarkan kode setelah TTL — pakai antrean yang sama dengan handler."""
    if not C.TTL_OTP:
        return
    mid = (res or {}).get('result', {}).get('message_id')
    if not mid:
        return
    entri = {'id': int(mid), 'akun': akun, 'uid': 'arsip', 'kode': kode,
             'jatuh': time.time() + C.TTL_OTP,
             'teks': teks, 'markup': None}
    C.antrean_ubah(C.FILE_OTP, lambda d: (d + [entri])[-200:])


def main():
    items, dibuat = S.baca_feed()
    if items is None:
        print('🚨 otp_arsip: %s' % dibuat)
        return 2
    try:
        umur = (kini_wib() - datetime.fromisoformat(dibuat)).total_seconds() / 60.0
    except Exception:
        umur = 0.0
    if umur > BASI_FEED:
        return 0                       # feed basi -> poller yang ambil alih

    st = muat()
    baru = sorted([i for i in items if i['id'] > st['last_id']], key=lambda i: i['id'])
    for i in baru:
        st['last_id'] = max(st['last_id'], i['id'])
        if i.get('outgoing'):
            continue
        subj = i.get('subj') or ''
        dari = i.get('dari') or ''
        folder = (i.get('folder') or '').lower()
        if any(b in folder for b in BUANG):
            continue
        if any(rx.search(dari) for rx in C.SKIP_FROM_RE):
            continue
        if any(rx.search(subj) for rx in C.SKIP_SUBJECT_RE):
            continue
        if not O.mirip(subj):
            # judul tidak mirip OTP: cek isi hanya kalau ada kata kunci kode
            isi = ((i.get('teks') or '') + ' ' + (i.get('html') or '')).lower()
            if not any(k in isi for k in ('kode verifikasi', 'verification code', 'one-time',
                                          'kode otp', 'otp anda', 'your code')):
                continue
        d = O.cari(subj, body=i.get('teks') or '', html=i.get('html') or '')
        if not d:
            continue
        akun = i.get('akun') or ''
        baris = ['🔑 <b>kode OTP</b> · %s' % C.E(akun),
                 '    🔑 kode : <code>%s</code>' % C.E(d.get('kode')),
                 '    dari : %s' % C.E(dari),
                 '    subj : %s' % C.E(subj),
                 '    tgl  : %s' % C.E(i.get('sent') or '?'),
                 '    folder : %s' % C.E(i.get('folder') or '?'),
                 '    arsip : id %s' % i['id']]
        try:
            res = kirim('\n'.join(baris))
            jadwalkan(res, d.get('kode'), subj, akun, '\n'.join(baris))
            with open(LOG, 'a') as f:
                f.write('%s | otp | %s | %s | %s\n' % (
                    kini_wib().strftime('%Y-%m-%d %H:%M:%S'), akun, i['id'], subj[:70]))
            print('OTP terkirim: %s (%s)' % (subj[:40], akun))
        except Exception as e:
            print('🚨 otp_arsip: gagal kirim id %s (%s)' % (i['id'], type(e).__name__))
            return 2
        simpan(st)
        time.sleep(0.4)
    simpan(st)
    return 0


if __name__ == '__main__':
    if '--status' in sys.argv:
        print('penanda OTP arsip: %s' % muat().get('last_id'))
        try:
            b = open(LOG).read().splitlines()
            print('OTP terkirim: %d | terakhir: %s' % (len(b), b[-1][:110] if b else '-'))
        except FileNotFoundError:
            print('belum ada OTP dari arsip')
        sys.exit(0)
    sys.exit(main())
