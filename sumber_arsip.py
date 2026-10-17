#!/usr/bin/env python3
"""Pengamat arsip MailArchiver — Fase 1, mode PARALEL (tidak mengubah notifikasi apa pun).

Tugasnya mengumpulkan bukti untuk memutuskan apakah notifikasi boleh pindah membaca dari arsip:
  1. apakah arsip melihat email yang sama dengan poller IMAP (dibandingkan per akun/tag)
  2. berapa LAG arsip = jeda dari sentDate sampai email terlihat di arsip — ini batas kecepatan
     notifikasi kalau nanti pindah (kode OTP bisa kedaluwarsa, jadi angka ini penting)
  3. apakah kode OTP terbaca dari isi arsip (textBody/htmlBody) oleh otp.cari() yang SAMA
     dengan yang dipakai poller

Pakai:
  python3 sumber_arsip.py                  # normal: catat yang baru, sunyi kalau tidak ada
  python3 sumber_arsip.py --mulai-sekarang # setel watermark ke id terbaru tanpa mencatat
  python3 sumber_arsip.py --ringkas        # cetak 25 baris terakhir + ringkasan log
Catatan: kode OTP yang terdeteksi DISAMARKAN di log (5***1) — log ini bukan tempat kode.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import config as C
import otp as O

BASE = (C.get('MAILARCHIVER_URL') or 'https://arc.dipo.sh').rstrip('/')
KEY = C.get('MAILARCHIVER_API_KEY')
LOG = C.path('arsip.log')
STATE = C.path('state_arsip.json')
URN = 100          # ukuran halaman daftar (API mem-cap 100 walau diminta 200)
MAKS_HAL = 3       # batas menelusuri ke belakang setelah lama mati
OTP_AMBIL = 6      # maksimal isi email yang dibuka per jalan (uji deteksi OTP)
ROTASI = 3 * 1024 * 1024


def kini_wib():
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=C.TZ_OFFSET)


def ambil(jalur):
    r = urllib.request.Request(BASE + jalur, headers={'Authorization': 'Bearer ' + KEY})
    with urllib.request.urlopen(r, timeout=25) as f:
        return json.load(f)


def tanda(s):
    """Samarkan kode: 587161 -> 5***1."""
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


def peta_akun():
    """accountId arsip -> tag bot. Dipetakan lewat alamat email akun (pendaftaran arsip)."""
    try:
        d = ambil('/api/v1/accounts')
    except Exception:
        return {}
    item = d.get('items') if isinstance(d, dict) else d
    peta = {}
    for a in (item or []):
        if not isinstance(a, dict):
            continue
        em = (a.get('emailAddress') or a.get('email') or '').strip().lower()
        if a.get('id') and em:
            peta[a['id']] = C.EMAIL_TO_TAG.get(em) or em.split('@')[0]
    return peta


def isi_email(eid):
    """Ambil textBody/htmlBody dari endpoint detail. None kalau gagal."""
    try:
        d = ambil('/api/v1/emails/%s' % eid)
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    return d.get('textBody') or '', d.get('htmlBody') or ''


def jalan(mulai_sekarang=False):
    if not KEY:
        print('🚨 sumber_arsip: MAILARCHIVER_API_KEY belum ada di .env bot')
        return 2
    st = muat_state()
    try:
        h1 = ambil('/api/v1/emails?pageSize=%d' % URN)
    except urllib.error.HTTPError as e:
        print('🚨 sumber_arsip: API menolak (HTTP %s)' % e.code)
        return 2
    except Exception as e:
        print('🚨 sumber_arsip: tidak bisa menghubungi MailArchiver (%s)' % type(e).__name__)
        return 2

    item = h1.get('items') or []
    if not item:
        return 0
    terbaru = max(i['id'] for i in item)

    if mulai_sekarang or not st.get('last_id'):
        st['last_id'] = terbaru
        st['sejak'] = kini_wib().isoformat(timespec='seconds')
        simpan_state(st)
        print('watermark disetel ke id %d (mulai sekarang); catatan berikutnya hanya email baru' % terbaru)
        return 0

    # telusuri ke belakang kalau watermark jauh di belakang
    baru = [i for i in item if i['id'] > st['last_id']]
    hal = 1
    while len(item) >= URN and hal < MAKS_HAL and len(baru) < URN:
        hal += 1
        try:
            it = (ambil('/api/v1/emails?pageSize=%d&page=%d' % (URN, hal)).get('items') or [])
        except Exception:
            break
        item = it
        sisa = [i for i in it if i['id'] > st['last_id']]
        if not sisa:
            break
        baru += sisa

    if not baru:
        return 0

    baru.sort(key=lambda i: i['id'])
    st['last_id'] = max(st['last_id'], max(i['id'] for i in baru))

    masuk = [i for i in baru if not i.get('isOutgoing')]
    peta = peta_akun()
    per_tag, lag = {}, []
    for i in masuk:
        tag = (peta.get(i.get('accountId'))
               or C.EMAIL_TO_TAG.get((i.get('to') or '').lower())
               or C.EMAIL_TO_TAG.get((i.get('from') or '').lower()) or '?')
        per_tag[tag] = per_tag.get(tag, 0) + 1
        try:
            kirim = datetime.fromisoformat((i.get('sentDate') or '').split('.')[0])
            d = max(0.0, (kini_wib() - kirim).total_seconds() / 60.0)
            lag.append(d)
        except Exception:
            d = None
        tulis('%s WIB | id=%s | tag=%s | %s | lag=%s | %s | %s' % (
            kini_wib().strftime('%Y-%m-%d %H:%M:%S'), i['id'], tag, i.get('folderName') or '?',
            ('%.1fm' % d) if d is not None else '?',
            (i.get('from') or '')[:44], (i.get('subject') or '')[:70]))

    # uji deteksi OTP dari isi arsip (memakai otp.cari yang sama dengan poller)
    uji = [i for i in masuk if O.mirip(i.get('subject') or '')][:OTP_AMBIL]
    for i in uji:
        isi = isi_email(i['id'])
        if not isi:
            continue
        d = O.cari(i.get('subject') or '', body=isi[0], html=isi[1])
        if d:
            tulis('    └ otp dari ARSIP: %s (sumber=%s, kata=%s, %s)' % (
                tanda(d.get('kode')), d.get('sumber'), d.get('kata'), d.get('berlaku') or '-'))

    if lag:
        lag.sort()
        ringkas = 'lag min %.1fm / tengah %.1fm / maks %.1fm' % (lag[0], lag[len(lag) // 2], lag[-1])
    else:
        ringkas = 'tidak ada email masuk'
    tulis('    ... ringkas %s WIB: %d email baru (%s) | %s | %d isi dibuka untuk uji OTP' % (
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
    print('log: %d baris | %s' % (len(baris), LOG))
    masuk = [b for b in baris if ' WIB | id=' in b]
    ring = [b for b in baris if b.strip().startswith('... ringkas')]
    print('total email tercatat: %d | putaran: %d' % (len(masuk), len(ring)))
    for b in baris[-n:]:
        print(b)
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--mulai-sekarang', action='store_true')
    p.add_argument('--ringkas', action='store_true')
    a = p.parse_args()
    if a.ringkas:
        sys.exit(ringkas_log())
    sys.exit(jalan(a.mulai_sekarang))
