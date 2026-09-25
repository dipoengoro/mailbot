<div align="center">

# 📮 mailbot

**Email ke Telegram** — notifikasi, baca, balas, arsip, dan berhenti-langganan langsung dari chat.

Python 3.13 · tanpa dependensi luar (hanya pustaka standar) · Docker siap pakai · MIT

</div>

---

## Kenapa

Email penting tenggelam di antara newsletter, notifikasi mesin, dan spam. mailbot mengirim
kartu ringkas ke Telegram begitu ada email baru, dan semua aksi yang biasanya butuh buka
webmail bisa dilakukan dari chat: lihat isi aslinya sebagai halaman web, balas, tandai
sudah dibaca, arsipkan, atau berhenti langganan.

Semuanya jalan di infrastruktur sendiri: yang keluar hanya koneksi ke server IMAP/SMTP
emailmu dan `api.telegram.org`.

## Fitur

**Notifikasi**

- Kartu email baru: pengirim, subjek, tanggal, nomor pesan, dan **ringkasan belum dibaca**
  (total + rincian per folder) supaya kelihatan masih ada berapa yang menunggu.
- **Status di kartu** (`🔵 belum dibaca` → `✅ sudah dibaca` → `📁 diarsipkan`) ikut berubah
  sendiri setelah tombol ditekan, sekaligus angka "sisa" dihitung ulang.
- Dedup berlapis: UID + UIDVALIDITY per folder, plus Message-ID lintas folder — satu email
  yang muncul di INBOX dan di beberapa label Gmail hanya diberitakan sekali.
- Hasil tap tombol dikirim sebagai **balasan ke kartu emailnya**, jadi kalau menekan
  beberapa tombol berdekatan tetap jelas hasil itu milik email yang mana.
- Hanya folder yang relevan yang dipantau; folder buatan bot sendiri (Arsip/Terkirim) tidak.

**Aksi dari chat**

| Tombol | Yang terjadi |
| --- | --- |
| 👁 Lihat | Email dirender jadi halaman HTML aman + ditandai sudah dibaca (di folder yang benar) |
| ✍️ Balas | Bot menyiapkan draft balasan; kirim setelah menekan 🚀 Kirim |
| 📁 Arsip | Email dikeluarkan dari INBOX (dipindah ke folder arsip) |
| ✅ Baca | Tandai sudah dibaca tanpa membuka |
| 🔇 Bisukan | Berhenti dikabari untuk pengirim itu |

**Menulis**

- Balas email dengan utas yang benar: `In-Reply-To` dan `References` diisi, subjek `Re:`
  otomatis, penerima diambil dari `Reply-To` → `From`.
- `/tulis` untuk email baru: `ke | subjek | isi`, isi boleh banyak baris, pengirim bisa dipilih.
- Semua kiriman lewat **draft dulu** — tidak ada pengiriman otomatis.
- 🤖 Sempurnakan (opsional): draft dirapikan LLM sebelum dikirim.

**Lain-lain**

- `/unsub`: memindai header `List-Unsubscribe` dan mendukung RFC 8058 *one-click* — beberapa
  pengirim bisa berhenti langganan hanya dengan satu ketukan.
- Halaman "Lihat" aman: `default-src 'none'`, script email dihapus, gambar remote diblok
  (anti tracking pixel), tujuan setiap link ditulis di sebelahnya, lampiran bisa diunduh.
- Multi-akun: akun apa pun yang punya IMAP/SMTP, ditambah hanya lewat variabel `.env`.
- Satu container berisi dua proses (poller + handler) yang dijaga supervisor (auto-restart),
  plus healthcheck berbasis heartbeat.
- Zona waktu bisa diatur (`MAILBOT_TZ_OFFSET`), tanpa perlu tzdata.

## Arsitektur

```
                    ┌──────────────────── container: mailbot ────────────────────┐
   IMAP ─────────►  │  poller.py       : cek email baru, kirim kartu ke Telegram  │
   (tiap 180s)      │      │  state_poller.json (watermark UID, cache kepala, sisa) │
                    │      ▼                                                      │
   Telegram  ◄────► │  handler.py      : tombol, /tulis, /balas, /unsub, /help    │
   (long poll)      │      │  state.json (offset getUpdates, draft, pending)       │
                    │      ▼                                                      │
   SMTP ──────────► │  render.py       : email → satu file HTML aman              │
                    │  unsub.py        : pindai List-Unsubscribe                  │
                    │  supervisor.py   : jalankan & hidupkan ulang keduanya       │
                    └───────────────┬───────────────────────┬────────────────────┘
                                    │ /data (volume)        │ /view (volume, read-only web)
                                    ▼                       ▼
                             state, log, heartbeat     halaman hasil render
```

Detail per berkas dan alur datanya: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Instalasi

### 0. Yang perlu disiapkan

- Docker + Docker Compose (atau Python 3.11+ kalau mau jalan tanpa container).
- Akun email dengan IMAP/SMTP aktif dan **kata sandi aplikasi** (bukan kata sandi utama).
- Bot Telegram (dibuat lewat [@BotFather](https://t.me/BotFather)) — gratis.
- Opsional: web server / reverse proxy untuk membuka halaman "Lihat".

### 1. Bot Telegram

1. Chat [@BotFather](https://t.me/BotFather) → `/newbot` → simpan **token**.
2. Kalau notifikasi dikirim ke **grup**: `/setprivacy` → pilih bot → **Disable**,
   supaya bot bisa membaca perintah di grup. Cek hasilnya: `/mybots` → *API Token*.
3. Siapkan tujuan notifikasi dan id yang dibutuhkan:

   | Yang dibutuhkan | Cara mendapatkannya |
   | --- | --- |
   | `TELEGRAM_HOME_CHANNEL` | kirim pesan di grup/DM lalu buka `https://api.telegram.org/bot<TOKEN>/getUpdates` → `chat.id` (grup bernilai negatif) |
   | `TELEGRAM_HOME_THREAD` | sama seperti di atas, ambil `message_thread_id` kalau grubnya forum (topik) |
   | `TELEGRAM_ALLOWED_USERS` | `from.id` kamu di hasil `getUpdates` (hanya id ini yang bisa memerintah bot) |

### 2. Kredensial email

Pakai **kata sandi aplikasi**; kalau tidak, penyedia menolak login IMAP/SMTP.

- **Gmail**: aktifkan 2FA → <https://myaccount.google.com/apppasswords> → buat sandi aplikasi.
  IMAP: `imap.gmail.com:993`, SMTP: `smtp.gmail.com:465` (sudah otomatis diturunkan).
- **Zoho**: *Settings → Security → App Passwords* → buat sandi aplikasi.
  IMAP: `imappro.zoho.com:993`, SMTP: `smtp.zoho.com:465` (sudah ada di peta host).
- **Penyedia lain**: isi `IMAP_<TAG>_HOST`, dan `SMTP_<TAG>_HOST` kalau host SMTP tidak
  bisa ditebak dari host IMAP.

### 3. Konfigurasi

```bash
git clone https://github.com/<kamu>/mailbot.git
cd mailbot
cp .env.example .env
chmod 600 .env
$EDITOR .env          # isi token, akun, dan MAILBOT_VIEW_BASE
```

Semua variabelnya dijelaskan di [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) dan
dengan komentar di [`.env.example`](.env.example). Yang wajib diisi minimal:

```ini
TELEGRAM_BOT_TOKEN=...
TELEGRAM_HOME_CHANNEL=...
TELEGRAM_ALLOWED_USERS=...
MAILBOT_ACCOUNTS=MAIN:you@example.com
IMAP_MAIN_HOST=imap.example.com
IMAP_MAIN_USER=you@example.com
IMAP_MAIN_PASS=...
MAILBOT_VIEW_BASE=https://mail.example.com
MAILBOT_BOT_USERNAME=nama_bot_kamu
```

Cek konfigurasi tanpa membocorkan rahasia:

```bash
docker compose run --rm mailbot python3 config.py
# menampilkan: akun terdaftar (host/port, panjang sandi), chat/thread, status fitur AI
```

### 4. Jalankan

```bash
docker compose up -d --build          # build image sendiri dari Dockerfile
docker compose logs -f mailbot
```

Atau pakai image yang sudah dibuild orang lain / CI (tanpa build lokal):

```bash
docker compose pull && docker compose up -d          # kalau compose pakai `image:`
# atau langsung:
docker run -d --name mailbot --restart unless-stopped \
  --env-file .env -v "$PWD/data:/data" -v "$PWD/view:/view" \
  ghcr.io/dipoengoro/mailbot:latest
```

### 5. Publikasikan image (opsional)

Repo ini sengaja tidak mengunci ke satu registry: image dibuat tanpa rahasia apa pun,
jadi aman dibagikan. Cara paling gampang adalah GitHub Actions (build otomatis di
GitHub, tanpa menyimpan kredensial di komputermu):

```bash
cp deploy/ghcr-publish.yml.example .github/workflows/publish.yml
git add .github/workflows/publish.yml && git commit -m "ci: publikasi image" && git push
# lalu: git tag 1.0.0 && git push origin 1.0.0
```

> Push yang menambah `.github/workflows/` butuh token git dengan scope **workflow**.

Mau push dari komputer sendiri?

```bash
# GitHub Container Registry (ghcr.io)
echo "$GH_TOKEN" | docker login ghcr.io -u <username> --password-stdin   # token butuh write:packages
docker build -t ghcr.io/<username>/mailbot:1.0.0 .
docker push ghcr.io/<username>/mailbot:1.0.0

# Docker Hub
docker login -u <username>                                         # butuh access token, bukan sandi akun
docker tag mailbot:1.0.0 <username>/mailbot:1.0.0
docker push <username>/mailbot:1.0.0
```

Setelah dipublikasikan, ubah `docker-compose.yml`: ganti `build: .` menjadi
`image: ghcr.io/<username>/mailbot:1.0.0` — supaya orang lain (atau server lain)
tinggal `docker compose up -d`.

#### Tanpa registry: pakai berkas image dari Releases

Kalau registry belum dipakai, image-nya tersedia sebagai berkas di halaman
[Releases](https://github.com/dipoengoro/mailbot/releases) — tinggal dimuat:

```bash
curl -LO https://github.com/dipoengoro/mailbot/releases/download/v1.0.0/mailbot-1.0.0-image.tar.gz
curl -LO https://github.com/dipoengoro/mailbot/releases/download/v1.0.0/mailbot-1.0.0-image.tar.gz.sha256
sha256sum -c mailbot-1.0.0-image.tar.gz.sha256      # pastikan berkasnya utuh
docker load -i mailbot-1.0.0-image.tar.gz           # menghasilkan image mailbot:1.0.0
docker run -d --name mailbot --restart unless-stopped \
  --env-file .env -v "$PWD/data:/data" -v "$PWD/view:/view" mailbot:1.0.0
```

Yang akan terlihat di log: `supervisor aktif`, `poller mulai (interval 180 detik)`,
`fase D aktif`, lalu baris ringkasan per akun:

```
  folder me@example.com : 9 | sisa : 12 belum dibaca (INBOX 8 · Newsletter 4)
```

Uji jalur lengkap (mengirim email uji dari akun terakhir ke dirinya sendiri):

```bash
docker compose exec mailbot python3 poller.py --test
```

Kartu akan muncul di Telegram dalam ≤ `MAILBOT_POLL_INTERVAL` detik.

### 6. Halaman "Lihat" (opsional tapi disarankan)

Tombol 👁 Lihat menulis file HTML ke `MAILBOT_VIEW_DIR` dan mengirim link
`MAILBOT_VIEW_BASE/<nama-file>`. Nama file memuat token acak 16 karakter, jadi link
bisa dibuka tanpa login — **jangan** disajikan tanpa HTTPS dan jangan diindeks.

Pilihan menyajikannya:

- **Sudah punya reverse proxy** → ikuti [`deploy/Caddyfile.example`](deploy/Caddyfile.example)
  (nginx sama saja: root ke folder view + `Cache-Control: no-store`).
- **Belum ada** → pakai service `viewer` di compose:

  ```bash
  docker compose --profile viewer up -d
  # lalu arahkan MAILBOT_VIEW_BASE ke http://<host>:8080 (atau pasang proxy di depannya)
  ```

### 7. Tanpa Docker

```bash
python3 -m venv .venv && . .venv/bin/activate     # tidak ada dependensi, venv sekedar rapi
export MAILBOT_CODE_DIR=$PWD MAILBOT_STATE_DIR=$PWD/data MAILBOT_VIEW_DIR=$PWD/view
mkdir -p data view
python3 supervisor.py          # jalankan poller + handler
# atau manual: python3 poller.py  &  python3 handler.py --minutes 100000
```

## Perintah di chat

| Perintah | Fungsi |
| --- | --- |
| `/help` | daftar fitur & tombol |
| `/tulis ke@x.com \| Subjek \| isi` | email baru (isi boleh banyak baris; tambahkan `\| akun-pengirim` di akhir untuk memilih pengirim) |
| `/unsub` | memindai kandidat berhenti-langganan, lalu satu ketukan per pengirim |

Kartu notifikasi juga membawa tombol 👁 Lihat · ✍️ Balas · 📁 Arsip · ✅ Baca · 🔇 Bisukan.

## Keamanan

- **Tidak ada rahasia di kode.** Semua kredensial dari `.env`/env container; `.env`,
  `state*.json` (berisi subjek & Message-ID email), dan log sudah masuk `.gitignore`.
- **Whitelist perintah**: hanya `TELEGRAM_ALLOWED_USERS` yang bisa memerintah bot.
- **IMAP selalu `readonly`/`BODY.PEEK`** saat membaca, jadi status "belum dibaca" tidak
  berubah hanya karena bot membaca email.
- **Halaman render**: CSP `default-src 'none'`, script email dihapus, `on*` dibersihkan,
  gambar remote diganti placeholder (baru dimuat kalau tombolnya ditekan), form dimatikan.
- Ada pemeriksa cepat sebelum commit: `sh scripts/secret_scan.sh`.

Selengkapnya (termasuk cara rotasi kredensial dan apa yang terjadi kalau `.env` bocor):
[`docs/SECURITY.md`](docs/SECURITY.md).

## Integrasi

mailbot sengaja dibuat "miskin dependensi": yang dipakai dari luar hanya Telegram, server
IMAP/SMTP, dan opsional web server + LLM. Sebaliknya, hal-hal di luar mailbot hanya
menempel lewat tiga titik: **heartbeat**, **log**, dan **folder `/data`**.

Ringkasnya:

| Arah | Yang terlibat | Cara menanganinya |
| --- | --- | --- |
| mailbot → luar | Telegram Bot API | token dari BotFather; fitur mati sendiri kalau token kosong |
| mailbot → luar | IMAP/SMTP penyedia email | didaftarkan lewat `MAILBOT_ACCOUNTS`; akun yang env-nya tidak lengkap dilewati |
| mailbot → luar | LLM (fitur 🤖) | opsional; tanpa `AI_KEY` tombolnya menjawab bahwa fitur mati |
| mailbot → luar | web server untuk `/view` | opsional; tanpa itu email tetap bisa dibaca di webmail |
| luar → mailbot | monitoring / watchdog | `HEALTHCHECK` container + file `.heartbeat` di `/data` |
| luar → mailbot | log | `poller.log` & `handler.log` di `/data`, plus stdout container |
| luar → mailbot | backup | backup folder `data/` (state apa adanya) |

Detail + contoh perintah: [`docs/INTEGRATIONS.md`](docs/INTEGRATIONS.md).

## Operasional

- **Backup**: cukup folder `data/`. State bisa hilang tanpa bencana (bot mengirim ulang
  kartu untuk email yang lebih baru dari watermark terakhir), tapi isi `data/` membuat
  bot tidak mengulang notifikasi.
- **Update**: `git pull && docker compose up -d --build`. State ada di volume, jadi tidak hilang.
- **Rotasi kredensial** (token bot / kata sandi aplikasi): ubah `.env` lalu
  `docker compose up -d` (bukan `restart` — compose baru membaca `.env` saat recreate).
- **Ganti akun** = ubah `MAILBOT_ACCOUNTS` + variabel `IMAP_<TAG>_*`, lalu recreate.
- **Healthcheck**: `docker inspect --format '{{.State.Health.Status}}' mailbot`
  (`healthy`/`unhealthy`, dan alasannya terlihat di `.State.Health.Log`).

## Struktur repo

```
config.py        konfigurasi bersama: .env, daftar akun, helper (escape, tanggal, io)
poller.py        pemantau email baru -> kartu Telegram
handler.py       semua interaksi Telegram (tombol, /tulis, /unsub, /help)
render.py        email -> halaman HTML aman
unsub.py         pemindai List-Unsubscribe
supervisor.py    jalankan poller + handler, auto-restart
assets/          mailview.js (pembuka gambar/link di halaman render)
scripts/         healthcheck.py (dipakai Docker), secret_scan.sh
deploy/          contoh konfigurasi reverse proxy
docs/            arsitektur, konfigurasi, integrasi, keamanan, troubleshooting
```

## Troubleshooting

Kasus yang paling sering: lihat [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md).
Contoh cepat:

- **Bot diam saja** → cek `docker compose logs mailbot`; kalau ada
  `getUpdates err ... 409 Conflict`, berarti ada dua proses handler jalan (matikan salah satu).
- **Kartu tidak muncul padahal ada email** → pastikan folder email itu ada di
  `MAILBOT_FOLDERS` dan bukan folder yang dikecualikan (Arsip/Terkirim/Spam-nya Gmail).
- **Link 👁 Lihat 404** → `MAILBOT_VIEW_BASE` harus sama dengan domain web server, dan
  `MAILBOT_VIEW_DIR` harus folder yang disajikan.
- **Login IMAP gagal** → hampir selalu karena memakai kata sandi utama, bukan kata sandi aplikasi.
- **Tombol Sempurnakan bilang fitur mati** → `AI_KEY` belum diisi (fitur ini opsional).

## Lisensi

MIT — lihat [LICENSE](LICENSE).
