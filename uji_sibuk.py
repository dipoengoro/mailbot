#!/usr/bin/env python3
"""Uji SIBUK: kirim email bertanda [UJI SIBUK] ke SEMUA akun terpantau, tiap kali dijalankan.

Tujuan: menguji kelengkapan arsip di bawah beban, bukan menunggu email asli.
- tiap ronde mengirim 1 email ke setiap akun (8 email)
- pengirim: dua ronde pertama dari ME (Zoho), sisanya dari JU (Gmail) supaya kuota Zoho tidak kena
- subjek SELALU mengandung penanda "[UJI SIBUK]" -> aturan MAILBOT_SKIP_SUBJECT membuat poller DAN
  kanari melewatinya, jadi chat kak tidak dibanjiri kartu (tetap tercatat "lewati" di log)
- berhenti sendiri setelah RONDE_MAKS ronde
- setiap pengiriman dicatat ke /cfg/uji_sibuk.log untuk dibandingkan dengan isi arsip

Pakai: python3 uji_sibuk.py [--status]
"""
import json
import os
import smtplib
import sys
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

sys.path.insert(0, '/cfg')
import config as C

STATE = C.path('state_uji_sibuk.json')
LOG = C.path('uji_sibuk.log')
RONDE_MAKS = 24
PENANDA = '[UJI SIBUK]'


def kini_wib():
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=C.TZ_OFFSET)


def muat():
    try:
        return json.load(open(STATE))
    except Exception:
        return {'ronde': 0}


def simpan(d):
    tmp = STATE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(d, f)
    os.replace(tmp, STATE)


def kirim(pengirim_tag, tag_tujuan, ronde):
    a = C.A[pengirim_tag]
    t = C.A[tag_tujuan]
    m = EmailMessage()
    m['From'] = a['email']
    m['To'] = t['email']
    m['Subject'] = '%s #%d %s' % (PENANDA, ronde, kini_wib().strftime('%H:%M:%S'))
    m.set_content(
        'Email uji beban otomatis dari ade.\n\n'
        'Tanda: %s ronde %d, dikirim %s WIB, tujuan %s.\n'
        'Tidak perlu dijawab — dipakai mengukur kelengkapan dan jeda arsip.\n'
        % (PENANDA, ronde, kini_wib().strftime('%Y-%m-%d %H:%M:%S'), t['tag']))
    s = smtplib.SMTP_SSL(a['smtp_host'], a['smtp_port'], timeout=30)
    s.login(a['user'], a['pass'])
    s.send_message(m)
    s.quit()
    return '%s | kirim | ronde=%d | dari=%s | ke=%s | %s #%d' % (
        kini_wib().strftime('%Y-%m-%d %H:%M:%S'), ronde, a['tag'], t['tag'], PENANDA, ronde)


def main():
    st = muat()
    ronde = int(st.get('ronde', 0)) + 1
    if ronde > RONDE_MAKS:
        return 0                      # selesai, sunyi
    # Ronde 1 saja dari ME (Zoho membatasi kiriman harian; ronde 2 pernah ditolak).
    pengirim = 'ME' if ronde == 1 else 'JU'
    gagal = 0
    for tag in C.A:
        try:
            with open(LOG, 'a') as f:
                f.write(kirim(pengirim, tag, ronde) + '\n')
        except Exception as e:
            gagal += 1
            print('🚨 uji_sibuk: gagal kirim ronde %d ke %s (%s)' % (ronde, tag, type(e).__name__))
    st['ronde'] = ronde
    simpan(st)
    if gagal:
        return 2
    return 0


def status():
    st = muat()
    print('ronde terakhir: %s dari %s' % (st.get('ronde'), RONDE_MAKS))
    try:
        b = [x for x in open(LOG) if '| kirim |' in x]
        print('email terkirim: %d | baris terakhir: %s' % (len(b), b[-1].strip()[:110]))
    except FileNotFoundError:
        print('belum ada email terkirim')
    return 0


if __name__ == '__main__':
    sys.exit(status() if '--status' in sys.argv else main())
