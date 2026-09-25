#!/usr/bin/env python3
"""Scan kandidat unsubscribe -> unsub.json (di MAILBOT_STATE_DIR)

Dipakai perintah /unsub di handler. Dijalankan sebagai subprocess (bukan di dalam
proses handler) supaya chat tidak diam lama, dan hasilnya dicache ke file.

Yang dicari: header List-Unsubscribe (+ List-Unsubscribe-Post). Kalau Post nya
'List-Unsubscribe=One-Click' artinya pengirim dukung RFC 8058 -> cukup satu POST.
"""
import email
import json
import sys
from collections import defaultdict

import config as C

FOLDERS = C.FOLDERS                    # daftar folder yang dipindai
TAGS = [a['tag'] for a in C.ACCOUNTS]  # akun dari MAILBOT_ACCOUNTS
BATAS = int(sys.argv[1]) if len(sys.argv) > 1 else 80
OUT = C.path('unsub.json')

hasil = {}
for tag in TAGS:
    agg = defaultdict(lambda: {'n': 0, 'mode': '', 'lu': ''})
    try:
        M = C.imap(tag)
    except Exception as e:
        print('gagal konek', tag, type(e).__name__)
        continue
    for f in FOLDERS:
        try:
            if M.select(f, readonly=True)[0] != 'OK':
                continue
            t, d = M.uid('SEARCH', None, 'ALL')
            uids = (d[0].split() if (d and d[0]) else [])[-BATAS:]
            for i in range(0, len(uids), 40):
                t, d2 = M.uid('FETCH', b','.join(uids[i:i + 40]),
                              '(BODY.PEEK[HEADER.FIELDS (FROM LIST-UNSUBSCRIBE LIST-UNSUBSCRIBE-POST)])')
                for part in d2 or []:
                    if not isinstance(part, tuple):
                        continue
                    m = email.message_from_bytes(part[1])
                    lu = (m.get('List-Unsubscribe') or '').strip()
                    if not lu:
                        continue
                    lup = (m.get('List-Unsubscribe-Post') or '').strip()
                    nm, adr = email.utils.parseaddr(m.get('From') or '')
                    adr = (adr or nm or '?').lower()
                    a = agg[adr]
                    a['n'] += 1
                    a['lu'] = lu[:400]
                    a['mode'] = ('ONE-CLICK' if 'one-click' in lup.lower()
                                 else ('mailto' if 'mailto:' in lu.lower() else 'link'))
        except Exception as e:
            print('lewati folder', f, type(e).__name__)
    try:
        M.logout()
    except Exception:
        pass
    hasil[tag] = sorted([{'adr': k, **v} for k, v in agg.items()], key=lambda x: -x['n'])

json.dump(hasil, open(OUT, 'w'))
print('kandidat tersimpan:', {k: len(v) for k, v in hasil.items()}, '->', OUT)
