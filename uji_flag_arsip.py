#!/usr/bin/env python3
"""Uji: apakah MailArchiver mengubah flag \\Seen di mailbox saat sync?

Cara: kirim email uji ke JU, catat FLAGS-nya sekarang, tunggu MailArchiver menyimpannya,
lalu baca FLAGS lagi. Kalau tetap tidak ada \\Seen, artinya sync arsip read-only (pakai PEEK).
"""
import imaplib
import smtplib
import sys
import time
from email.message import EmailMessage

sys.path.insert(0, '/cfg')
import config as C

subj = 'Uji flag: apakah arsip menandai dibaca %d' % int(time.time())
a, t = C.A['ME'], C.A['JU']
m = EmailMessage()
m['From'] = a['email']
m['To'] = t['email']
m['Subject'] = subj
m.set_content('Uji flag baca. Tidak perlu dijawab.\n')
s = smtplib.SMTP_SSL(a['smtp_host'], a['smtp_port'], timeout=30)
s.login(a['user'], a['pass'])
s.send_message(m)
s.quit()
print('terkirim:', subj)


def flags():
    M = C.imap('JU', 'INBOX', readonly=True)
    try:
        typ, d = M.uid('SEARCH', None, 'HEADER', 'Subject', '"%s"' % subj)
        uid = (d[0].split() or [b''])[0]
        if not uid:
            return None, 'belum ada di mailbox'
        typ, f = M.uid('FETCH', uid, '(FLAGS)')
        return uid.decode(), f[0].decode() if f and f[0] else '?'
    finally:
        C.tutup(M)


for i in range(10):
    uid, fl = flags()
    print('t+%2d menit: uid=%s flags=%s' % (i, uid, fl))
    if i == 0:
        pertama = fl
    time.sleep(60)
    if i == 3:
        break
print('--- kesimpulan: kalau tidak ada \\Seen setelah beberapa menit, arsip TIDAK menandai dibaca ---')
