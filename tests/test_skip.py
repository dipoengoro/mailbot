#!/usr/bin/env python3
"""Uji aturan exclude notifikasi (MAILBOT_SKIP_FROM / MAILBOT_SKIP_SUBJECT).

Jalankan: python3 tests/test_skip.py
"""
import os
import sys
import tempfile

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, AKAR)
os.environ['MAILBOT_STATE_DIR'] = tempfile.mkdtemp(prefix='mailbot-uji-skip-')
os.environ['MAILBOT_SKIP_FROM'] = r'zabbix-bcp@telkomsel\.co\.id'
os.environ['MAILBOT_SKIP_SUBJECT'] = r'^BCP Production'

import config as C  # noqa: E402
import poller as P  # noqa: E402

# (pengirim, subjek, harus dilewati?)
KASUS = [
    ('Zabbix BCP <zabbix-bcp@telkomsel.co.id>',
     'BCP Production: bcpafs40gplgpapp1: NA-255: Interface Operational Status', True),
    ('Zabbix BCP <zabbix-bcp@telkomsel.co.id>', 'Recovery: host X kembali normal', True),
    ('<zabbix-bcp@telkomsel.co.id>', 'Problem: CPU tinggi', True),
    ('Indra <indra.ilham@solusi247.com>', 'Re: BCP Production: jadwal', False),
    ('HRD <hrd@solusi247.com>', 'Jadwal Standby - Oktober 2026', False),
    ('Netflix <info@netflix.com>', 'Kode masukmu', False),
    ('Zabbix <zabbix@telkomsel.co.id>', 'BCP Production: tes dari pengirim lain', True),
    ('Budi <budi@example.com>', 'Rapat BCP Production bulan depan', False),
]


def main():
    gagal = 0
    print('pola pengirim :', [r.pattern for r in C.SKIP_FROM_RE])
    print('pola subjek   :', [r.pattern for r in C.SKIP_SUBJECT_RE])
    for pengirim, subjek, mau in KASUS:
        hasil = bool(P.lewati_email(pengirim, subjek))
        if hasil != mau:
            gagal += 1
            print('GAGAL  %-40s | %-46s -> %s (harusnya %s)' % (pengirim[:40], subjek[:46], hasil, mau))
    print('%d kasus, %d gagal' % (len(KASUS), gagal))
    return 1 if gagal else 0


if __name__ == '__main__':
    sys.exit(main())
