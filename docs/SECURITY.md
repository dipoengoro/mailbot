# Keamanan & penanganan rahasia

## Di mana rahasia disimpan

| Rahasia | Tempat | Catatan |
| --- | --- | --- |
| Token bot Telegram | `.env` (`TELEGRAM_BOT_TOKEN`) | kalau bocor: `/revoke` di @BotFather → token baru → recreate container |
| Kata sandi aplikasi email | `.env` (`IMAP_<TAG>_PASS`) | bisa dipakai untuk membaca seluruh isi kotak surat → satu kebocoran paling berdampak |
| Kunci API LLM | `.env` (`AI_KEY`) | opsional; kalau tidak dipakai, tidak perlu diisi |
| URL halaman hasil render | dikirim sebagai pesan Telegram | bukan rahasia jangka panjang, tapi isinya isi email |

Aturannya: **tidak ada satu pun nilai rahasia di dalam kode atau file yang di-commit.**
Semua lewat `.env` (mode `600`) atau environment container, dan `.env`, `state*.json`,
`unsub.json`, `*.log` sudah masuk `.gitignore` + `.dockerignore`.

## Sebelum commit / push

```bash
sh scripts/secret_scan.sh
```

Yang diperiksa: file runtime yang ikut ter-track, pola kredensial (private key, token bot
Telegram, `ghp_`, `sk-`, `AKIA`, …), dan email/IP internal yang tidak seharusnya muncul di
kode. Bisa diperkuat dengan daftar kata sendiri:

```bash
SCAN_KATA="namaasli@contoh.com,namadomainku.com" sh scripts/secret_scan.sh
```

Hook pre-commit (opsional):

```bash
mkdir -p .git/hooks
printf '#!/bin/sh\nsh scripts/secret_scan.sh || exit 1\n' > .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

Jaring pengaman ini **bukan jaminan** — dia memeriksa pola, bukan maksud. Setiap kali
menambah berkas baru, tanya: apakah isinya boleh dibaca orang lain?

## Data yang tersimpan di bot (bukan rahasia, tapi pribadi)

`state_poller.json` memuat subjek email, alamat pengirim, dan Message-ID;
`state.json` memuat isi draft yang belum dikirim; `poller.log`/`handler.log` memuat subjek
email. Perlakukan folder `/data` seperti kotak surat: hak akses ketat
(`chmod 700`, file `600`), tidak di-upload ke layanan pihak ketiga tanpa alasan, dan
ikut dihapus saat dekomisioning.

## Halaman "Lihat" (halaman render email)

Desainnya: **link acak, tanpa login** — dipilih supaya link tetap bisa diklik dari HP tanpa
menambah sistem autentikasi lagi. Konsekuensinya jujur saja: siapa pun yang punya URL-nya
bisa membaca email itu.

Batas risikonya yang sudah dipasang:

- nama file memuat token acak (`secrets.token_hex`, default 16 karakter heksadesimal);
- CSP `default-src 'none'` + `script-src 'self'` di halaman: konten email tidak bisa
  menjalankan apa pun, dan tidak bisa "memanggil pulang" saat halaman dibuka;
- gambar remote diblok oleh default dan script email dihapus → tracking pixel tidak aktif;
- link di badan email tidak bisa diklik sampai tombol di halaman ditekan, dan tujuannya
  ditulis terbuka di sebelah link (termasuk peringatan untuk shortener/typosquatting);
- header yang disarankan di reverse proxy: `Cache-Control: no-store`,
  `X-Robots-Tag: noindex, nofollow`, `Referrer-Policy: no-referrer`;
- halaman ditulis di bawah `MAILBOT_VIEW_DIR` (volume terpisah dari state).

Yang perlu kamu lakukan sendiri:

1. **HTTPS** wajib kalau diakses dari luar (kalau tidak, link dan isi email lewat jalur terbuka).
2. **Bersihkan berkala** — halaman tidak punya masa berlaku:
   `find /srv/mailview -maxdepth 1 -name 'mail-*' -mtime +7 -delete`.
3. **Jangan taruh folder view di repositori git atau sinkronisasi cloud publik.**
4. Kalau ingin lebih ketat: batasi akses di proxy (mis. basic auth, allow-list IP/VPN) dan
   matikan tombol 👁 dari alur dengan tidak mengisi `MAILBOT_VIEW_BASE`.

## Siapa yang bisa memerintah bot

- `TELEGRAM_ALLOWED_USERS` = daftar id user Telegram. Di luar daftar itu, perintah dan teks
  diabaikan.
- Balasan email hanya dibaca kalau memang **reply ke pesan bot** dan pengirimnya di whitelist.
  Ini yang mencegah percakapan grup biasa diproses sebagai isi balasan.
- Notifikasi dikirim ke satu chat/topik (`TELEGRAM_HOME_CHANNEL`/`THREAD`); kalau bot dipakai
  di grup, pastikan hanya orang yang kamu percaya ada di sana — isi kartu memuat subjek email.

## Izin akses email

- Semua pembacaan memakai `readonly=True` + `BODY.PEEK[...]`: bot tidak pernah "membaca
  tanpa sengaja" (tidak mengubah status belum dibaca hanya karena memeriksa).
- Perubahan status hanya terjadi lewat aksi eksplisit: `STORE \Seen` (👁 Lihat / ✅ Baca),
  `COPY` + `\Deleted` + `EXPUNGE` (📁 Arsip).
- Pengiriman email **selalu lewat draft**; tidak ada auto-send, dan tidak ada balas-otomatis.

## Kalau `.env` bocor

1. **Putar semua kredensial yang ada di dalamnya**: token bot (`/revoke` di BotFather),
   kata sandi aplikasi tiap akun email (hapus & buat baru di penyedia), kunci API LLM.
2. Update `.env` → `docker compose up -d` (recreate, bukan `restart`).
3. Periksa `handler.log`/`poller.log` untuk aktivitas yang tidak kamu kenali, dan folder
   `/view` untuk halaman yang tidak kamu minta.
4. Kalau bocornya lewat git: hapus dari riwayat (`git filter-repo`), lalu putar kredensial —
   **urutan ini penting**, karena menghapus commit tidak membatalkan nilai yang sudah tersalin.
5. Kalau bocornya di layanan publik (mis. Docker Hub image): query pencarian registry
   sudah tidak relevan karena image tidak memuat `.env` sama sekali — tapi tetap putar
   kredensial kalau ada kemungkinan nilai itu pernah masuk ke layer.

## Rahasia & image Docker

Image dibuat **tanpa** `.env` (lihat `.dockerignore`). Konfigurasi masuk saat runtime lewat
`env_file:` atau `-e`. Jadi image aman dibagikan/dipublikasikan; yang tidak boleh dibagikan
adalah folder `data/` dan file `.env`.
