#!/usr/bin/env python3
"""Uji ekstraksi kode OTP — pola diambil dari email nyata (semua kode di sini palsu).

Jalankan: python3 tests/test_otp.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import otp  # noqa: E402

# (subjek, isi teks, isi html, kode yang diharapkan)
HARUS_KETEMU = [
    ('Your Code - 98986', 'Dear Dipo, Your code is: 98986. Use it to access your account.', None, '98986'),
    ('Kode Verifikasi WhatsApp: 761-810', 'Masukkan kode ini: 761-810. Jangan bagikan kode ini.', None, '761810'),
    ('Anda Link Kode verifikasi: 223 104', 'Kode verifikasi adalah: 223 104. Berlaku 10 menit.', None, '223104'),
    ('Kode OTP Login MyXL Anda', 'Kode OTP utk login ke myXL Anda: 456789. Info 123.', None, '456789'),
    ('[NO REPLY] Notifikasi Kode OTP', 'Berikut kode OTP Lupa Password.\n\nKode OTP : 7495\n', None, '7495'),
    ('Kode Verifikasi Authelia', 'The following one-time code should only be used in the prompt.\n\nDNC38MTB\n', None, 'DNC38MTB'),
    ('Your PayPal verification code', None,
     '<p>Your verification code is <b>552271</b> and will expire in 10 minutes.</p>', '552271'),
    ('Netflix: Kode masukmu', None,
     '<table><tr><td>Masukkan kode ini untuk masuk</td></tr><tr><td>'
     '&#52;&#55;&#49;&#57;</td></tr><tr><td>Berlaku 15 menit.</td></tr></table>', '4719'),
    ('Login Udemy: Berikut kode verifikasi 6 digit', 'Gunakan kode di bawah ini untuk login. 831450Kode ini akan kedaluwarsa dalam 10 menit.', None, '831450'),
    ('Verifikasi alamat email ID AWS Builder', 'Kode verifikasi: 244681\n\nKode ini akan kedaluwarsa 30 menit setelah dikirim.', None, '244681'),
]

# Email yang mirip OTP (kata kuncinya ada) tapi TIDAK boleh memunculkan kode.
TIDAK_BOLEH_KETEMU = [
    ('Tagihan listrik', 'Total Rp 1.500.000 jatuh tempo 20/2026, hubungi 081234567890.'),
    ('Kode verifikasi', 'Aktifkan kode keamanan di pengaturan akun Anda untuk keamanan ekstra.'),
    ('Transaksi Tanpa OTP Lebih Cepat', 'Sekarang transaksi tanpa OTP, hemat waktu tanpa kode.'),
    ('Diskon 50% pakai kode', 'Kode promo 1234 untuk diskon 50% sampai akhir bulan.'),
    ('Reset password', 'Klik https://contoh.com/reset?pin=881122&requestid=9 untuk mengatur ulang.'),
    ('Kode verifikasi email', 'Kode verifikasi dikirim ke perangkat lain pada 2026-09-28 pukul 10:20.'),
    ('Pinterest', 'Pin ini rasanya beda banget, coba lihat 8210 pin lainnya.'),
]


def main():
    gagal = 0
    for subj, teks, html, mau in HARUS_KETEMU:
        hasil = otp.cari(subj, teks, html)
        dapat = (hasil or {}).get('kode')
        if dapat != mau:
            gagal += 1
            print('GAGAL  %-46s -> %r (harusnya %r)' % (subj[:46], dapat, mau))
    for subj, isi in TIDAK_BOLEH_KETEMU:
        hasil = otp.cari(subj, isi, None)
        if hasil:
            gagal += 1
            print('SALAH TANGKAP  %-40s -> %r' % (subj[:40], hasil.get('kode')))
    total = len(HARUS_KETEMU) + len(TIDAK_BOLEH_KETEMU)
    print('%d kasus diuji, %d gagal' % (total, gagal))
    return 1 if gagal else 0


if __name__ == '__main__':
    sys.exit(main())
