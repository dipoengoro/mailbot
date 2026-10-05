#!/usr/bin/env python3
"""Uji penyamaran kode OTP di kartu (timer MAILBOT_TTL_OTP).

Jalankan: python3 tests/test_otp_ttl.py
Tidak menyentuh jaringan — `handler.api` diganti fungsi palsu.
"""
import importlib
import json
import os
import sys
import tempfile
import time

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, AKAR)
os.environ['MAILBOT_STATE_DIR'] = tempfile.mkdtemp(prefix='mailbot-uji-')

import config as C  # noqa: E402
import handler as H  # noqa: E402
import poller as P  # noqa: E402

importlib.reload(C)

KARTU = ('📥 <b>email baru</b> · me@dipo.sh\n'
         '    status : 🔵 belum dibaca\n'
         '    dari : Netflix &lt;info@netflix.com&gt;\n'
         '    subj : Kode masukmu 4719 sekarang\n'
         '    🔑 kode : <code>4719</code> · berlaku ±15 menit · jangan dibagikan\n'
         '    tgl  : 5 Okt 2026 10:00 WIB\n'
         '    uid  : 999 · 24 pesan di INBOX')


def main():
    gagal = 0

    # 1) penyamaran: baris 🔑 jadi kadaluarsa + kode di baris subjek jadi ••••
    baru = H._sembunyikan_kode(KARTU, '4719')
    if '4719' in baru:
        gagal += 1
        print('GAGAL  kode masih tampil setelah disamarkan')
    if 'kadaluarsa' not in baru:
        gagal += 1
        print('GAGAL  baris kode tidak ditandai kadaluarsa')
    if 'subj : Kode masukmu •••• sekarang' not in baru:
        gagal += 1
        print('GAGAL  kode di baris subjek tidak disamarkan')
    for utuh in ('status : 🔵 belum dibaca', 'tgl  : 5 Okt 2026 10:00 WIB', 'uid  : 999'):
        if utuh not in baru:
            gagal += 1
            print('GAGAL  baris lain ikut berubah:', utuh)

    # 2) bentuk kode di subjek boleh beda (761-810 vs 761810)
    kartu2 = KARTU.replace('Kode masukmu 4719', 'Kode masukmu 761-810')
    if '761' in H._sembunyikan_kode(kartu2, '761810'):
        gagal += 1
        print('GAGAL  kode berspasi di subjek tidak tersamarkan')

    # 3) siklus antrean: poller menjadwalkan -> handler menyapu
    P._TERAKHIR.update({'text': KARTU, 'reply_markup': '{"inline_keyboard": []}'})
    P.jadwalkan_otp({'result': {'message_id': 777}}, '4719', 'ME', b'999')
    antre = json.load(open(C.path(C.FILE_OTP)))
    if not antre or antre[0]['id'] != 777 or antre[0]['kode'] != '4719':
        gagal += 1
        print('GAGAL  antrean tidak tercatat:', antre)

    terkirim = []
    H.api = lambda m, **p: (terkirim.append((m, p)) or {'ok': True})
    H.CHAT = '123'
    C.antrean_ubah(C.FILE_OTP, lambda d: [{**e, 'jatuh': time.time() - 1} for e in d])
    if H.sapu_otp() != 1:
        gagal += 1
        print('GAGAL  penyapu tidak menyamarkan entri')
    if json.load(open(C.path(C.FILE_OTP))):
        gagal += 1
        print('GAGAL  entri tidak dibuang setelah disamarkan')
    if not terkirim or terkirim[0][0] != 'editMessageText' or '4719' in terkirim[0][1]['text']:
        gagal += 1
        print('GAGAL  panggilan editMessageText tidak benar:', terkirim[:1])

    # 4) antrean kosong tidak melakukan apa-apa
    if H.sapu_otp() != 0:
        gagal += 1
        print('GAGAL  penyapu jalan padahal antrean kosong')

    print('%d pemeriksaan, %d gagal' % (9, gagal))
    return 1 if gagal else 0


if __name__ == '__main__':
    sys.exit(main())
