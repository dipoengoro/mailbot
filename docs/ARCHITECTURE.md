# Arsitektur

## Topologi

Satu container menjalankan satu proses induk dan dua proses anak:

```
supervisor.py  ──┬── poller.py            loop: pantau IMAP, kirim kartu (interval MAILBOT_POLL_INTERVAL)
                 └── handler.py --minutes  loop: tarik update Telegram (getUpdates)
```

`supervisor.py` memantau tiap 15 detik; kalau ada anak yang mati, dia dihidupkan lagi
dengan jeda naik (5s, 10s, 15s, … maks 60s). Output kedua anak ditulis ke `STATE_DIR`
(`poller.log`, `handler.log`) **sekaligus** ke stdout container, supaya bisa dibaca
`docker logs` maupun dikirim ke sistem log terpusat.

Kode dan data dipisah:

| Variabel | Isi | Contoh di image |
| --- | --- | --- |
| `MAILBOT_CODE_DIR` | kode program | `/app` |
| `MAILBOT_STATE_DIR` | state, log, heartbeat, `.env` (opsional) | `/data` |
| `MAILBOT_VIEW_DIR` | halaman hasil render | `/view` |

Kalau `MAILBOT_*_DIR` tidak diisi (jalan tanpa Docker), semuanya memakai folder tempat
kode berada — jadi `python3 supervisor.py` di root repo juga jalan.

## Alur poller (email baru → Telegram)

1. **Daftar folder** per akun: `LIST`, buang folder `\Noselect` dan nama yang cocok
   `SKIP_FOLDER` (arsip/archive, sent/terkirim, draft, trash/sampah, all mail, template).
   Folder itu dibuang karena isinya dibuat oleh aksi bot sendiri atau hanya duplikat.
2. **Hitung belum dibaca**: `STATUS <folder> (UNSEEN)` per folder; kalau server menolak,
   jatuh ke `SELECT readonly` + `SEARCH UNSEEN`. Folder `SKIP_UNREAD` (spam/junk/draf/
   penting/berbintang/snoozed) tidak dihitung — Gmail menyimpan satu email di beberapa
   label, jadi menghitung semuanya membuat angkanya dobel.
3. **Cari UID baru**: `UID SEARCH ALL`, bandingkan dengan watermark terakhir per
   `<TAG>:<folder>:<UIDVALIDITY>`. Pembacaan selalu `readonly` + `BODY.PEEK`, jadi status
   "belum dibaca" tidak berubah hanya karena bot memeriksa.
4. **Ambil kepala + flag** untuk UID baru: `UID FETCH <uid> (FLAGS BODY.PEEK[HEADER.FIELDS
   (SUBJECT FROM DATE MESSAGE-ID)])`. `\Seen` diambil dari prefix respons (bukan bagian
   non-literal) untuk menulis status awal di kartu.
5. **Dedup**: kalau `Message-ID` sudah pernah dikirim, UID ini dilewati (menangani email
   yang sama muncul di INBOX dan di label lain).
6. **Kirim kartu** (`sendMessage`), dengan tombol yang membawa
   `callback_data = "<aksi>:<akun>:<uid>"`. Isi kartu:

   ```
   📥 email baru · nama@contoh.com
       status : 🔵 belum dibaca
       dari : Nama Pengirim <pengirim@contoh.com>
       subj : Subjek email
       tgl  : 25 Sep 2026 20:00 WIB
       sisa : 30 belum dibaca (INBOX 30)
       uid  : 110208 · 99 pesan di INBOX
   ```

   Tiap nilai dinamis di-escape `& < >` sebelum dikirim (parse_mode HTML).
7. **Simpan kepala email** ke `state['head']['<akun>:<uid>']` (`dari`, `subj`, `tgl`,
   `folder`) — dipakai handler untuk menampilkan detail saat tombol ditekan, tanpa
   mengambil ulang dari IMAP. Cache ini dipangkas otomatis (`MAILBOT_MAX_HEAD_CACHE`).
8. **Simpan state** secara atomik (tulis file `.tmp` → `os.replace`) supaya pembaca lain
   tidak pernah melihat file separuh. Tiap siklus juga memperbarui `.heartbeat`.

## Alur handler (aksi dari chat)

1. `handler.py` memanggil `getUpdates` dengan `offset` tersimpan dan
   `allowed_updates=['callback_query','message']`. **Hanya satu proses** yang boleh
   melakukan ini — dikunci dengan `flock` pada `.handler.lock2`; dua pemanggil bersamaan
   membuat Telegram menjawab `409 Conflict` dan update bisa hilang.
2. **Callback (tombol)**: dari `callback_query.message.message_id` handler tahu kartu mana
   yang ditekan, dan menyimpan id itu di `CARD_ID`. Semua pesan hasil (`say()`) otomatis
   dikirim sebagai **reply ke kartu itu** (`allow_sending_without_reply=true` supaya tidak
   gagal 400 kalau kartunya sudah dihapus).
3. **Aksi** dijalankan sesuai tombol:

   | Aksi | Yang dilakukan |
   | --- | --- |
   | `look` | `render.py` (subprocess) menulis halaman HTML, lalu `STORE \Seen` **di folder tempat UID itu ditemukan** (UID unik per folder — salah folder berarti menandai email lain), lalu mengirim link |
   | `reply` | Menyimpan `pending` dan menunggu teks balasan dari whitelist |
   | `seen` | `STORE \Seen` tanpa membuka |
   | `arch` | `UID COPY` ke folder arsip → `STORE \Deleted` → `EXPUNGE` |
   | `mute` | Menambahkan akun ke daftar `mute` di state |
   | `uns` | Menjalankan one-click / mailto / membuka link dari hasil `/unsub` |
   | `snd` / `cxl` | Mengirim draft lewat SMTP (dengan `In-Reply-To`/`References`) atau membuangnya |
   | `ai` / `bck`| Merapikan draft dengan LLM (kalau `AI_KEY` diisi) atau kembali ke versi awal |

4. **Kartu diperbarui**: untuk `look`/`seen`/`arch` yang berhasil, teks kartu diedit
   (`editMessageText`) — baris `status` diganti (`✅ sudah dibaca` / `📁 diarsipkan`) dan
   baris `sisa` **dihitung ulang** dengan logika yang sama seperti poller
   (`importlib` memuat `poller.py`, jadi tidak ada dua implementasi unread).
   `reply_markup` (tombol) dipasang ulang saat mengedit — tanpa itu Telegram menghapus
   seluruh tombol kartu. Kalau aksinya gagal, kartu tidak disentuh.
5. **Hasil aksi** dikirim sebagai pesan biasa (bukan toast `answerCallbackQuery`) supaya
   link di dalamnya bisa diklik.
6. **Pesan teks** diproses `on_text`: `/help`, `/tulis`, `/unsub`, dan teks balasan untuk
   draft. Balasan hanya diterima kalau memang **reply ke pesan bot** dan pengirimnya ada di
   whitelist — ini yang mencegah pesan grup biasa ikut diproses.

## Halaman hasil render (`render.py`)

1. Cari UID di folder kandidat (`MAILBOT_FOLDERS`); gagal → keluar dengan kode 2.
2. Ambil `RFC822` utuh, pilih bagian `text/html` (fallback `text/plain` jadi `<pre>`).
3. Bersihkan: buang `<!DOCTYPE>`, `<script>`, atribut `on*`, ganti `<form>` jadi `<div>`,
   dan ganti `src`/`background` remote dengan placeholder 1px (`data-blocked` menyimpan URL
   aslinya) — jadi tracking pixel tidak dipanggil saat halaman dibuka.
4. Setiap link: tujuan ditulis di sebelahnya, plus peringatan kalau domainnya beda dari
   pengirim, menyerupai domain pengirim (typosquatting), atau memakai shortener.
   Link diblokir sampai tombol "aktifkan link" ditekan.
5. Lampiran ditulis di samping halaman dengan nama `<halaman>-attN-<namafile>`.
6. Halaman dibungkus CSP `default-src 'none'; style-src 'unsafe-inline'` + CSS bertema
   gelap, dan `mailview.js` disalin dari `assets/` kalau belum ada/beda.

## File state (di `MAILBOT_STATE_DIR`)

| File | Isi | Kalau hilang |
| --- | --- | --- |
| `state_poller.json` | watermark `<TAG>:<folder>:<UIDVALIDITY>` (`seen`, `last`), `_seen_msgid` (dedup lintas folder), `head` (cache kepala email) | bot menganggap semua email di folder sebagai baseline baru → tidak mengirim notifikasi untuk yang lama, aman |
| `state.json` | `offset` getUpdates, `pending` (menunggu balasan), `draft` (menunggu dikirim), `mute`, `unsub` | draft yang belum dikirim hilang; offset direset → Telegram mengirim ulang update yang belum di-ack |
| `unsub.json` | hasil pemindaian `/unsub` (per tag) | tinggal jalankan `/unsub` lagi |
| `.heartbeat` | timestamp siklus poller terakhir | healthcheck melaporkan `unhealthy` sampai siklus berikutnya |
| `poller.log`, `handler.log` | log kedua proses | tidak apa-apa (log juga ada di stdout container) |

File state berisi data pribadi (subjek, Message-ID, alamat pengirim) — perlakukan seperti
`/var/mail`, bukan seperti cache biasa. Mode default `0600`.
