#!/usr/bin/env python3
"""Kirim email uji berisi kode OTP dari ME ke JU (untuk mengukur jalur OTP dari arsip)."""
import smtplib
import sys
import time
from email.message import EmailMessage

sys.path.insert(0, '/cfg')
import config as C

kode = '481902'
a = C.A['ME']
t = C.A['JU']
m = EmailMessage()
m['From'] = a['email']
m['To'] = t['email']
m['Subject'] = 'Kode verifikasi Anda: %s' % kode
m.set_content('Kode verifikasi Anda adalah %s.\n\nBerlaku 10 menit. Jangan bagikan kode ini.\n' % kode)
s = smtplib.SMTP_SSL(a['smtp_host'], a['smtp_port'], timeout=30)
s.login(a['user'], a['pass'])
s.send_message(m)
s.quit()
open('/cfg/otp_uji_kirim.txt', 'w').write('%d\n%s\n' % (int(time.time()), kode))
print('terkirim %s -> %s pada %s' % (a['email'], t['email'], time.strftime('%H:%M:%S')))
