# Konfigurasi

Semua pengaturan lewat variabel lingkungan. Sumbernya dibaca dari dua tempat, dan
**env container menang atas file `.env`**:

1. file `$MAILBOT_STATE_DIR/.env` (atau `$MAILBOT_ENV` kalau diisi),
2. environment proses (inilah yang dipakai `docker compose` dengan `env_file:`).

Cek hasil pembacaan tanpa membocorkan rahasia (yang dicetak hanya panjang sandi):

```bash
docker compose run --rm mailbot python3 config.py
```

## Akun email

| Variabel | Wajib | Default | Keterangan |
| --- | --- | --- | --- |
| `MAILBOT_ACCOUNTS` | ✅ | – | daftar akun, format `TAG:alamat@email`, dipisah koma. Contoh: `MAIN:aku@contoh.com,KEDUA:aku@gmail.com` |
| `IMAP_<TAG>_HOST` | ✅ | – | host IMAP (mis. `imap.gmail.com`) |
| `IMAP_<TAG>_USER` | – | = alamat email | biasanya sama dengan alamat |
| `IMAP_<TAG>_PASS` | ✅ | – | **kata sandi aplikasi**, bukan kata sandi utama |
| `IMAP_<TAG>_PORT` | – | `993` | IMAP SSL |
| `SMTP_<TAG>_HOST` | – | diturunkan | kalau kosong: peta penyedia (`imap.gmail.com → smtp.gmail.com`, `imappro.zoho.com → smtp.zoho.com`, …) atau aturan `imap.x.y → smtp.x.y` |
| `SMTP_<TAG>_PORT` | – | `465` | SMTP SSL |

`TAG` = nama pendek huruf besar (dipakai juga di `callback_data`, jadi jangan diubah
sembarangan setelah kartu beredar). **Akun yang env-nya belum lengkap dilewati** dengan
catatan di log — sengaja begitu supaya satu akun salah tidak mematikan semuanya.

## Telegram

| Variabel | Wajib | Default | Keterangan |
| --- | --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | ✅ | – | token dari @BotFather |
| `TELEGRAM_HOME_CHANNEL` | ✅ | – | id chat tujuan (grup negatif, mis. `-1001234567890`) |
| `TELEGRAM_HOME_THREAD` | – | kosong | `message_thread_id` kalau tujuan grup forum/topik |
| `TELEGRAM_ALLOWED_USERS` | ✅ | kosong | id user yang boleh memerintah bot, dipisah koma. Kosong = tidak ada yang boleh |
| `MAILBOT_BOT_USERNAME` | – | kosong | username bot tanpa `@`; dipakai memastikan balasan benar-benar reply ke pesan bot |
| `MAILBOT_FOOTER` | – | kosong | penanda di akhir setiap pesan (mis. `📮 via @bot_aku`); kosong = tanpa footer |

> Kalau bot dipakai di **grup**, matikan privacy di @BotFather (`/setprivacy` → Disable).
> Kalau tidak, bot tidak bisa membaca perintah di grup dan hanya menerima pesan yang
> di-reply langsung ke pesannya.

## Email yang dipantau

| Variabel | Wajib | Default | Keterangan |
| --- | --- | --- | --- |
| `MAILBOT_FOLDERS` | – | `INBOX,Newsletter,Notification,Spam,Archive,[Gmail]/Spam,[Gmail]/Penting` | folder yang dicari saat tombol aksi dipakai (UID unik per folder, jadi daftarnya dipakai untuk menemukan lokasi email) |
| `MAILBOT_POLL_INTERVAL` | – | `180` | jeda antar siklus poller (detik) |
| `MAILBOT_MAX_HEAD_CACHE` | – | `400` | batas entri cache kepala email (untuk baris `dari/subj/tgl` di hasil tombol) |
| `MAILBOT_MAX_MSGID_MEMORY` | – | `1200` | batas ingatan Message-ID untuk dedup lintas folder |

Folder yang **tidak pernah** dipantau poller (bukan pengaturan, sudah pasti): nama yang
mengandung arsip/archive, sent/terkirim, draft, trash/sampah, all mail/semua email, template.
Alasannya: isinya dibuat oleh aksi bot sendiri atau hanya duplikat — kalau dipantau, email
lama akan muncul sebagai "email baru" setiap kali bot mengarsipkan sesuatu.

Folder yang **tidak dihitung** di baris `sisa` (juga bawaan): spam, junk, bulk, draf/draft,
penting/important, berbintang/starred, snoozed. Gmail menyimpan satu email di INBOX **dan**
label penting secara bersamaan, jadi menghitung dua-duanya membuat totalnya bohong.

## Halaman "Lihat"

| Variabel | Wajib | Default | Keterangan |
| --- | --- | --- | --- |
| `MAILBOT_VIEW_BASE` | ✅ (kalau pakai 👁) | `http://127.0.0.1:8080` | URL publik tempat file render disajikan; harus sama persis dengan domain web server |
| `MAILBOT_VIEW_DIR` | – | `/view` | folder tujuan file HTML (di-mount ke web server) |
| `MAILBOT_VIEW_TOKEN_BYTES` | – | `8` | panjang token acak di nama file (8 byte = 16 karakter hex) |

## Umum & opsional

| Variabel | Wajib | Default | Keterangan |
| --- | --- | --- | --- |
| `MAILBOT_TZ_OFFSET` | – | `7` | offset jam dari UTC untuk tanggal di kartu & jam di log (tanpa tzdata) |
| `MAILBOT_TZ_LABEL` | – | `WIB` | label yang ikut ditulis (mis. `WIB`, `UTC`, `JST`) |
| `MAILBOT_CODE_DIR` | – | folder kode | lokasi `poller.py`, `render.py`, `unsub.py`, `assets/` |
| `MAILBOT_STATE_DIR` | – | = `MAILBOT_CODE_DIR` | lokasi state, log, heartbeat |
| `MAILBOT_ENV` | – | `<STATE_DIR>/.env` | lokasi file `.env` kalau bukan default |
| `AI_KEY` | – | kosong | kunci API LLM untuk tombol 🤖 Sempurnakan; kosong = fitur mati (tombol menjawab bahwa fitur mati) |
| `AI_URL` | – | `https://api.deepseek.com/v1/chat/completions` | endpoint yang kompatibel dengan format OpenAI chat completions |
| `AI_MODEL` | – | `deepseek-chat` | nama model yang diminta |
| `MAILBOT_HEALTH_MAX_AGE` | – | `POLL_INTERVAL*3+120` | batas umur heartbeat sebelum healthcheck bilang `unhealthy` |

## Menambah akun kedua

```ini
MAILBOT_ACCOUNTS=MAIN:aku@contoh.com,KERJA:aku@perusahaan.com
IMAP_MAIN_HOST=imap.contoh.com
IMAP_MAIN_USER=aku@contoh.com
IMAP_MAIN_PASS=...
IMAP_KERJA_HOST=outlook.office365.com
IMAP_KERJA_USER=aku@perusahaan.com
IMAP_KERJA_PASS=...
SMTP_KERJA_HOST=smtp.office365.com      # opsional kalau host SMTP beda nama
```

Lalu `docker compose up -d` (recreate). Akun baru otomatis ikut dipantau, ikut dihitung di
ringkasan "sisa", dan muncul di pemilih pengirim `/tulis`.

## Pitfall konfigurasi

- **`docker compose restart` tidak membaca ulang `.env`.** Perubahan env baru berlaku
  setelah recreate: `docker compose up -d`.
- **Jangan pakai kata sandi utama email.** Gmail/Zoho menolak IMAP tanpa kata sandi
  aplikasi; gejalanya `AUTHENTICATIONFAILED`.
- **Nilai di `.env` jangan diberi kutip ganda** (bot menormalkan kutip, tapi `.env` dengan
  tanda kutip bisa bikin `docker compose` menganggapnya bagian nilai).
- **`MAILBOT_VIEW_BASE` harus publik dan HTTPS** kalau link dipakai dari HP; kalau di
  belakang Cloudflare, matikan *Scrape Shield → Email Address Obfuscation* (kalau tidak,
  alamat email di halaman rusak karena script pembukanya diblok CSP halaman).
- **`TELEGRAM_HOME_CHANNEL` harus format numerik**, bukan `@username` — bot tidak selalu
  bisa resolve username kalau belum pernah melihat chat itu.
