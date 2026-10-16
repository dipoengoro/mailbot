#!/usr/bin/env python3
"""Kirim email uji dari akun ME ke JU untuk mengukur lag arsip vs poller. Isi dibuat
memuat 'kode verifikasi' supaya jalur OTP (poller maupun pengamat arsip) ikut teruji."""
import smtplib
import sys
from email.message import EmailMessage

sys.path.insert(0, '/cfg')
import config as C

a = C.A['ME']
tujuan = C.A['JU']['email']
m = EmailMessage()
m['From'] = a['email']
m['To'] = tujuan
m['Subject'] = 'Uji Fase 1: kode verifikasi untuk arsip'
m.set_content(
    'Email uji otomatis dari ade (Fase 1: satu sumber email).\n\n'
    'Kode verifikasi Anda: 904217\n\n'
    'Tidak perlu dijawab. Dipakai mengukur jeda arsip MailArchiver vs poller IMAP.\n')
s = smtplib.SMTP_SSL(a['smtp_host'], a['smtp_port'], timeout=30)
s.login(a['user'], a['pass'])
s.send_message(m)
s.quit()
print('terkirim: %s -> %s' % (a['email'], tujuan))
