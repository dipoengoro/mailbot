#!/usr/bin/env python3
"""Pencari kode OTP di dalam email.

Tujuan: kartu Telegram cukup menampilkan kodenya, jadi kode tidak perlu dibuka di
halaman render. Dipakai poller (untuk kartu) dan bisa dipakai handler.

Pelajaran dari 219 email OTP nyata (akun juhyuko@gmail.com + me@dipo.sh):
- Kode ada di SUBJEK pada banyak pengirim: "Your Code - 98986", "Kode verifikasi
  email: 955980", "601272 adalah kode verifikasi X Anda", "Kode Verifikasi WhatsApp:
  761-810", "Your Hetzner verification code is 389000".
- Di isi, kode selalu dekat kata kunci: "Kode OTP : 7495", "Kode verifikasi Google:
  123456", "Masukkan kode ini: 123-456", "Your verification code is 123456 and will
  expire in 10 minutes", "Your One-Time Passcode: 1234".
- Panjang kode nyata: 4, 5, 6 digit, dan 6 digit berseparator ("761-810", "123 456").
- Jebakan yang harus dibuang: nomor di dalam URL (pin=123456), nominal uang
  (Rp 50.000), tahun/tanggal, nomor telepon, nomor informasi ("Info 123" setelah kode),
  dan angka gaya CSS dari email HTML (18px, #ffffff).
"""
import html
import re

# Kata kunci KUAT: hampir pasti menandakan OTP.
KUAT = [
    'kode otp', 'kode verifikasi', 'kode keamanan', 'kode masuk', 'kode rahasia', 'kode akses',
    'kode aktivasi', 'kode autentikasi', 'kode konfirmasi', 'kode login', 'kode pengaman',
    'kode sekali pakai', 'kode rahasiamu', 'kode verifikasimu', 'kode 2fa', 'kode dua faktor',
    'otp untuk masuk', 'kode untuk masuk', 'kode pemulihan', 'kode masukmu',
    'kode di bawah ini', 'kode di bawah', 'kode berikut', 'kode ini', 'kode pin', 'pin otp',
    'verification code', 'security code', 'one-time passcode', 'one-time code', 'one time passcode',
    'one time code', 'login code', 'sign-in code', 'sign in code', 'access code', 'confirmation code',
    'authentication code', 'verification passcode',
]
# Kata kunci LEMAH: masih menandakan kode, tapi bisa muncul di email lain.
LEMAH = ['kode', 'otp', 'passcode', 'your code', 'verifikasi', 'verification', 'kode ini',
         'masukkan kode', 'kode anda', 'kode kamu', 'code', 'kodenya', 'verify']

# Pembuangan calon kode yang jelas bukan OTP.
BUKAN = [
    re.compile(r'(?:Rp|IDR|USD|EUR|\$|€)\s*$', re.I),          # dimulai mata uang
    re.compile(r'^(?:ribu|juta|rb|jt|k|m|million|billion)\b', re.I),
    re.compile(r'^(?:px|em|rem|%|mm|cm|pt)\b', re.I),          # satuan CSS
    re.compile(r'^#?[0-9a-f]{3,8}\b', re.I),                   # warna hex
]

KODE_RE = re.compile(r'(?<![\w.,\-/])(\d{3,8})(?:[ ]?[-–][ ]?(\d{3,4})| (\d{3,4}))?(?![\w\-/])')
# Kode alfanumerik (Authelia "DNC38MTB"): token 6-10 karakter, ada huruf DAN angka.
ALNUM_RE = re.compile(r'(?<![A-Za-z0-9])([A-Z0-9]{6,10})(?![A-Za-z0-9])')
KEDALUWARSA_RE = re.compile(
    r'(?:berlaku|kedaluwarsa|kadaluwarsa|expire[sd]?|valid|masa berlaku)[^\n]{0,40}?(\d{1,3})\s*'
    r'(menit|min|minute|minutes|jam|hour|hours|detik|sec|second|seconds)', re.I)

_TAG = re.compile(r'<(script|style)\b[^>]*>.*?</\1>', re.I | re.S)
_TAG2 = re.compile(r'<[^>]+>')
_TERSEMBUNYI = re.compile(
    r'<(\w+)[^>]*style="[^"]*(?:display\s*:\s*none|mso-hide|visibility\s*:\s*hidden|'
    r'max-height\s*:\s*0|font-size\s*:\s*0px)[^"]*"[^>]*>(.*?)</\1>', re.I | re.S)
_URL = re.compile(r'(?:https?://|www\.)\S+', re.I)


def _bersih_tersembunyi(m):
    """Buang elemen tersembunyi HANYA kalau isinya pendek (preheader).

    Tanpa batas ini, satu span tersembunyi yang tidak tertutup bisa menelan seluruh
    isi email (kejadian nyata: DeepSeek — kodenya ikut hilang).
    """
    return ' ' if len(m.group(2)) < 500 else m.group(0)


def bersihkan(t, spasi=False):
    """Teks siap-cari: entitas didekode, teks tersembunyi/CSS/URL dibuang, baris dirapikan.

    `spasi=False` -> tag dibuang TANPA spasi, supaya kode yang dipecah antar-tag
    ("12</span><span>34") tetap utuh. Tapi itu bisa menempelkan kode ke kata berikutnya
    ("masuk4719Berlaku"), jadi pemanggil juga menyiapkan varian `spasi=True` (tag -> spasi).

    Entitas HARUS didekode dulu: Netflix dan beberapa pengirim lain menulis kode sebagai
    referensi karakter ("&#52;&#55;..."), jadi kalau entitas dibuang mentah kodenya hilang.
    """
    if not t:
        return ''
    t = html.unescape(t)
    t = _TAG.sub(' ', t)
    t = _TERSEMBUNYI.sub(_bersih_tersembunyi, t)
    t = re.sub(r'<!--.*?-->', ' ', t, flags=re.S)
    t = re.sub(r'@media[^{]{0,120}\{', ' {', t, flags=re.I)
    t = re.sub(r'\{[^{}]{0,600}\}', ' ', t)
    t = _TAG2.sub(' ' if spasi else '', t)
    t = re.sub(r'&#\d+;|&#x[0-9a-f]+;', ' ', t, flags=re.I)
    t = _URL.sub(' ', t)
    t = re.sub(r'\b\d{1,3}(?:\.\d{3})+(?:,\d+)?\b', ' ', t)
    t = re.sub(r'[\u00a0\u200b\u200c\u200d\u2060]', ' ', t)
    # kode yang menempel ke kata berikutnya ("831450Kode ini", "masuk4719Berlaku"):
    # pengirim seperti Udemy/Netflix menyatukan sel tabel, batasnya hilang saat tag dibuang.
    t = re.sub(r'(?<=[0-9])(?=[A-Z][a-z])', ' ', t)
    t = re.sub(r'(?<=[A-Za-z])(?=[0-9]{4,8}(?![0-9]))', ' ', t)
    return re.sub(r'\s+', ' ', t)


def _buang_kandidat(t, a, b):
    """True kalau calon kode ini bukan OTP (uang, tanggal, nomor telepon, id panjang)."""
    kode = t[a:b]
    sebelum = t[max(0, a - 14):a]
    sesudah = t[b:b + 14]
    for rx in BUKAN:
        if rx.search(sebelum) or rx.search(sesudah):
            return True
    # ':' JANGAN dibuang — "Kode OTP : 7495" dan "Your code is: 12345" justru pola paling umum.
    if re.search(r'[@/=?&]', sebelum[-2:]):         # bagian email/URL/parameter query
        return True
    if re.match(r'^\d', sesudah) or re.search(r'\d$', sebelum):   # nyambung angka lain
        return True
    # Token panjang ala versi/app-password: "27205612.V1-swDgY-aEvQ" -> bukan kode.
    if re.match(r'^[.,][A-Za-z0-9]', sesudah) or re.search(r'[A-Za-z0-9][.,]$', sebelum):
        return True
    # konteks promo/diskon: angka di situ nominal kode voucher, bukan OTP
    if re.search(r'(\d+\s*%|diskon|promo|voucher|cashback|gratis|% off|off\b)', sebelum + sesudah, re.I):
        return True
    angka = kode.replace('-', '').replace(' ', '')
    if len(angka) >= 9:
        return True
    if len(angka) == 4 and re.match(r'^(19|20)\d\d$', angka):
        if re.search(r'(tgl|tanggal|date|tahun|year|/|-)\s*$', sebelum[-12:], re.I) or sesudah[:3] in ('/', '-'):
            return True
    if angka.startswith('0') and len(angka) >= 8:   # nomor telepon lokal
        return True
    return False


def _rapatkan_digit(t):
    """Rapatkan kode yang sengaja diberi spasi antar digit ("0 9 7 8 2 4").

    Hanya untuk deret digit TUNGGAL dipisah spasi (pola desain email), supaya
    "10 000" atau tabel angka tidak ikut dirapatkan.
    """
    def ganti(m):
        digit = m.group(0).split()
        return ''.join(digit) if len(digit) >= 4 else m.group(0)
    return re.sub(r'(?:\d\s+){3,}\d(?=\s|$)', lambda m: ganti(m), t)


def _kode_sekitar(t, pos, jendela=70):
    """Calon kode paling dekat dengan posisi kata kunci (cari ke kanan dulu, lalu kiri)."""
    terbaik = None
    for m in KODE_RE.finditer(t, max(0, pos - jendela), min(len(t), pos + jendela + 60)):
        raw = m.group(0)
        if _buang_kandidat(t, m.start(), m.end()):
            continue
        angka = raw.replace('-', '').replace(' ', '')
        if not (4 <= len(angka) <= 8):
            continue
        jarak = abs(m.start() - pos)
        if terbaik is None or jarak < terbaik[0]:
            terbaik = (jarak, angka, raw.strip(), m.start(), m.end())
    return terbaik


def _cari_alnum(t, pos, jendela=120):
    """Kode alfanumerik terdekat (mis. Authelia) yang mengandung huruf dan angka."""
    terbaik = None
    for m in ALNUM_RE.finditer(t, max(0, pos - jendela), min(len(t), pos + jendela + 80)):
        tok = m.group(1)
        if sum(c.isdigit() for c in tok) < 2 or sum(c.isalpha() for c in tok) < 2:
            continue
        if tok.islower():
            continue
        if re.match(r'^(HTTPS?|WWW|HTTP)$', tok):
            continue
        jarak = abs(m.start() - pos)
        if terbaik is None or jarak < terbaik[0]:
            terbaik = (jarak, tok, tok, m.start(), m.end())   # bentuknya sama dengan _kode_sekitar
    return terbaik


def cari(subject, body=None, html=None, batas=1200):
    """Kembalikan dict kode atau None.

    {'kode': '123456', 'sumber': 'subjek'|'isi', 'kata': 'kode verifikasi',
     'berlaku': '10 menit'|None, 'peringatan': True/False}
    """
    subj = bersihkan(subject or '')
    varian = []
    for bahan in (body, html):
        if not bahan:
            continue
        for spasi in (False, True):
            tx = bersihkan(bahan, spasi=spasi)
            if tx and tx not in varian:
                varian.append(tx)
    if not varian and not subj:
        return None

    kandidat = []

    # 1) Kode di SUBJEK: paling pasti ("Your Code - 98986", "601272 adalah kode verifikasi X")
    subj_l = subj.lower()
    if any(k in subj_l for k in KUAT + LEMAH):
        for m in KODE_RE.finditer(subj):
            if _buang_kandidat(subj, m.start(), m.end()):
                continue
            angka = m.group(0).replace('-', '').replace(' ', '')
            if 4 <= len(angka) <= 8:
                kuat = any(k in subj_l for k in KUAT)
                kandidat.append((100 if kuat else 70, angka, 'subjek', _kata_terdekat(subj, m.start())))

    # 2) Kode di ISI: nilai = kedekatan + kekuatan kata kunci. Dua varian teks ditelusuri
    #    (tag-dilebur & tag-jadi-spasi) supaya kode yang dipecah tag MAUPUN yang menempel
    #    ke kata berikutnya sama-sama terbaca.
    for isi in varian[:3]:
        isi_pendek = isi[:6000]
        low = isi_pendek.lower()
        for k in KUAT:
            for m in re.finditer(re.escape(k), low):
                near = _kode_sekitar(isi_pendek, m.start(), jendela=200) or _cari_alnum(isi_pendek, m.start())
                if near:
                    j, angka, raw, a, b = near
                    skor = 90 if j <= 45 else (75 if j <= 110 else (62 if j <= 200 else 45))
                    kandidat.append((skor, angka, 'isi', k))
        if not kandidat:
            for k in LEMAH:
                for m in re.finditer(re.escape(k), low):
                    # kata kunci lemah ('kode', 'code', 'pin') juga muncul di promo/newsletter:
                    # wajib ada kata berbau OTP di sekitarnya, kalau tidak -> bukan kode.
                    sekitar = low[max(0, m.start() - 150):m.start() + 260]
                    if not re.search(r'(otp|verif|verify|login|sign|masuk|security|keamanan|one[- ]time|'
                                     r'confirm|autentik|akses|2fa|mfa|kode|aktivasi|pemulihan)', sekitar, re.I):
                        continue
                    near = _kode_sekitar(isi_pendek, m.start(), jendela=60)
                    if near:
                        j, angka, raw, a, b = near
                        if j <= 30:
                            skor = 62
                        elif j <= 70 and k in ('kode', 'kodenya'):
                            skor = 55
                        else:
                            skor = 40
                        kandidat.append((skor, angka, 'isi', k))
        if not kandidat:
            # kode yang sengaja diberi spasi antar digit ("0 9 7 8 2 4"): dicari di teks rapat
            teks_rapat = _rapatkan_digit(isi_pendek)
            if teks_rapat != isi_pendek:
                low2 = teks_rapat.lower()
                for k in KUAT + LEMAH:
                    for m in re.finditer(re.escape(k), low2):
                        near = _kode_sekitar(teks_rapat, m.start(), jendela=130)
                        if near:
                            j, angka, raw, a, b = near
                            if len(angka) >= 4:
                                kandidat.append((80 if j <= 60 else 55, angka, 'isi', k + ' (berspasi)'))

    if not kandidat:
        return None
    kandidat.sort(key=lambda x: -x[0])
    skor, angka, sumber, kata = kandidat[0]
    if skor < 50:
        return None

    keluar = {'kode': angka, 'sumber': sumber, 'kata': kata, 'skor': skor,
              'berlaku': None, 'peringatan': False}
    acuan = varian[0] if varian else subj
    m = KEDALUWARSA_RE.search(acuan[:6000]) or KEDALUWARSA_RE.search(subj)
    if m:
        keluar['berlaku'] = '%s %s' % (m.group(1), m.group(2).lower()[:5])
    if re.search(r'(jangan (?:bagikan|berikan|kirim)|do not share|never share|rahasia)', acuan[:6000], re.I):
        keluar['peringatan'] = True
    return keluar


def _kata_terdekat(t, pos):
    low = t.lower()
    terbaik, jarak = None, 10 ** 6
    for k in KUAT + LEMAH:
        for m in re.finditer(re.escape(k), low):
            d = abs(m.start() - pos)
            if d < jarak:
                terbaik, jarak = k, d
    return terbaik


if __name__ == '__main__':
    import sys
    contoh = [
        ('Your Code - 98986', 'Dear Dipoengoro, Your code is: 98986. Use it to access your account.'),
        ('Kode Verifikasi WhatsApp: 761-810', 'Masukkan kode ini: 761-810. Jangan bagikan kode ini.'),
        ('Tagihan listrik', 'Total Rp 1.500.000 jatuh tempo 20/2026, info 081234567890'),
        ('Kode OTP Login MyXL Anda', 'Kode OTP utk login ke myXL Anda: 456789. Info 123.'),
    ]
    for s, b in contoh:
        print(s, '->', cari(s, b))
