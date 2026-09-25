# Troubleshooting

Urutan periksa yang paling cepat: `docker compose logs --tail 100 mailbot` (atau
`docker logs --tail 100 mailbot`), lalu `poller.log` / `handler.log` di folder `data/`,
lalu `python3 config.py` untuk memastikan konfigurasi yang benar-benar terbaca.

---

## Bot sama sekali tidak bereaksi

**Gejala**: tidak ada kartu, tombol tidak merespons.

1. `docker inspect --format '{{.State.Health.Status}}' mailbot` — kalau `unhealthy`,
   lihat `.State.Health.Log`: berarti poller macet (biasanya koneksi IMAP menggantung).
2. `python3 config.py` → pastikan `akun terdaftar` tidak nol dan `telegram` terisi.
   Akun dengan env tidak lengkap hanya dicatat di log lalu dilewati — jadi bot "hidup"
   tapi tidak memantau apa pun.
3. `getUpdates err ... 409 Conflict` di `handler.log` → ada **dua** proses handler
   (mis. container lama belum mati, atau `handler.py` dijalankan manual sambil container
   jalan). Matikan salah satu; lock `.handler.lock2` mencegah ini kalau semuanya lewat
   `supervisor.py`.

## Kartu muncul, tapi tombolnya tidak ada

Tombol dibentuk poller dengan mengekstrak akun dan uid dari teks kartu
(pola `...email baru... <alamat>` dan `uid  : <angka>`). Kalau salah satu baris itu hilang
atau formatnya berubah, kartu tetap terkirim tetapi tanpa tombol. Perbaiki format kartu di
`tg()` pada `poller.py` — jangan mengubah baris `uid  :` atau baris pertama kartu.

## Tombol ditekan, tapi hasilnya salah email

UID itu **unik per folder**. Kalau aksi mencari UID di folder yang salah, yang terpengaruh
bisa email lain yang kebetulan punya UID sama. Semua aksi sekarang mencari dulu di folder
kandidat (`MAILBOT_FOLDERS`) dengan `UID SEARCH`, baru bertindak. Kalau kamu menambah folder
baru di email, tambahkan juga namanya ke `MAILBOT_FOLDERS`.

## Link 👁 Lihat 404 / halaman kosong

1. `MAILBOT_VIEW_BASE` harus sama persis dengan domain proxy (termasuk skema `https://`).
2. `MAILBOT_VIEW_DIR` harus folder yang benar-benar disajikan web server (periksa lewat
   `docker compose exec mailbot ls /view`).
3. Halaman hanya ada selama file-nya belum dibersihkan — kalau kamu punya cron pembersih,
   pastikan tidak menghapus file baru.
4. Kalau di belakang Cloudflare dan alamat email di halaman tampil rusak
   (`[email protected]` atau `[email protected]`): matikan *Scrape Shield → Email Address
   Obfuscation*. Script pembukanya diblok CSP halaman, jadi alamat email tinggal separuh.

## ⚠️ "gagal render" di chat

Pesan ini muncul kalau `render.py` gagal. Isi pesan memuat penyebab singkatnya. Yang umum:
UID tidak ditemukan di folder kandidat (email sudah dipindah/dihapus), atau folder tidak ada
di server. Jalankan manual untuk melihat detailnya:

```bash
docker compose exec mailbot python3 render.py --acct you@example.com --uid 12345 --out /tmp/x.html
```

## Status kartu tidak berubah jadi "sudah dibaca"

- Kartu hanya diedit kalau aksinya **berhasil**. Kalau hasilnya memuat kata `gagal`, kartu
  sengaja tidak disentuh supaya statusnya tidak berbohong.
- Kartu yang dibuat sebelum fitur status ada akan **ditambahkan** barisnya di bagian bawah
  (bukan menggantikan baris lain), jadi kartu lama tetap bisa dipakai.
- Kalau kartunya sudah dihapus, hasil aksi tetap dikirim (tanpa edit).

## Tombol di kartu hilang setelah ditekan

`editMessageText` **menghapus** `reply_markup` kalau tidak dikirim ulang. Di kode, tombol
dipasang kembali dari `callback_query.message.reply_markup`. Kalau kamu mengubah fungsi
`edit_card()`, jangan lupa bagian itu.

## Login IMAP gagal (`AUTHENTICATIONFAILED`)

- Paling sering: memakai kata sandi utama, bukan **kata sandi aplikasi**.
- Gmail: 2FA wajib aktif dulu, baru bisa membuat *App Password*.
- Zoho: *App Passwords* per aplikasi, dan host-nya `imappro.zoho.com` (bukan `imap.zoho.com`).
- Email kantor (Office 365/Exchange): IMAP sering dimatikan admin; cek dengan
  `openssl s_client -connect outlook.office365.com:993` lalu coba login manual.

## Email baru tidak diberitakan, tapi ada di kotak surat

- Folder tidak ada di hasil `LIST` yang dipantau, atau namanya mengandung kata yang
  dikecualikan (arsip/archive, sent/terkirim, trash/sampah, all mail, template, draft).
- Email itu sudah pernah diberitakan: dedup `Message-ID` berlaku lintas folder (satu email
  yang muncul di INBOX dan label lain hanya dikabari sekali).
- Setelah bot dijalankan pertama kali, semua email lama dianggap baseline — hanya email
  yang lebih baru dari watermark terakhir yang dikirim. Untuk menguji, pakai
  `python3 poller.py --test` (mengirim email uji ke akun terakhir).

## Angka "sisa belum dibaca" terasa aneh

- Folder spam/draf/penting/berbintang/snoozed sengaja tidak dihitung (label Gmail bisa
  memuat email yang sama dengan INBOX → dobel).
- Kalau server menolak `STATUS (UNSEEN)`, bot otomatis memakai `SELECT readonly` +
  `SEARCH UNSEEN` (hasilnya sama, sedikit lebih lambat).
- Angka dihitung **per akun**: kartu akun A menampilkan sisa akun A saja.

## Balasan email saya di chat tidak diproses

- Harus berupa **reply ke pesan bot** (`BOT_USERNAME`/`MAILBOT_BOT_USERNAME`) dan pengirim
  harus ada di `TELEGRAM_ALLOWED_USERS`.
- Kalau bot dipakai di grup, privacy harus **Disable** (@BotFather → `/setprivacy`),
  kalau tidak bot tidak menerima pesan biasa di grup.
- Kalau ada dua bot di grup yang sama, pastikan reply-nya ke pesan bot yang benar —
  bot lain bisa ikut "menelan" pesan.

## Draft hilang / tombol Kirim bilang tidak ada draft

`state.json` (isi draft) ikut hilang kalau volume `data/` tidak ter-mount atau folder-nya
dibersihkan. Pastikan `./data:/data` ada di compose dan backup rutin jalan.

## Tombol 🤖 Sempurnakan bilang fitur mati

`AI_KEY` belum diisi. Isi `AI_KEY` (+ opsional `AI_URL`, `AI_MODEL`) lalu recreate container.
Bot sengaja tetap jalan penuh tanpa fitur ini.

## Perubahan `.env` tidak berefek

`docker compose restart` **tidak** membaca ulang `.env`. Pakai:

```bash
docker compose up -d
```

Kalau masih sama, cek env yang benar-benar diterima proses:

```bash
docker inspect mailbot --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E 'MAILBOT|TELEGRAM|IMAP'
```

## Waktu di kartu meleset

Bot memakai offset tetap (`MAILBOT_TZ_OFFSET`) supaya tidak butuh tzdata di container kecil.
Isi `7` untuk WIB, `9` untuk JST, `0` untuk UTC. Jam di **log** memakai offset yang sama.

## Ingin lihat apa yang sebenarnya dikirim tanpa mengirim

Uji render dan aksi tanpa menyentuh Telegram:

```bash
# isi kartu yang akan dikirim (tidak dikirim)
docker compose exec mailbot python3 - <<'PY'
import importlib.util, json, shutil
s = importlib.util.spec_from_file_location('p', '/app/poller.py')
p = importlib.util.module_from_spec(s); s.loader.exec_module(p)
shutil.copy(p.STATE, '/tmp/st.json')          # state salinan, produksi tidak disentuh
st = json.load(open('/tmp/st.json')); st.pop('_seen_msgid', None)
k = [x for x in st if x.startswith(p.ACCTS[0][0] + ':')][0]
st[k]['last'] = str(int(st[k]['last']) - 3)   # 3 email terakhir saja
p.STATE = '/tmp/st.json'; json.dump(st, open('/tmp/st.json', 'w'))
sent = []; p.tg = lambda t: sent.append(t)    # kirim ke variabel, bukan Telegram
p.check(*p.ACCTS[0], folder='INBOX', unread='    sisa : 0 belum dibaca')
print(sent[-1] if sent else '(tidak ada kartu baru)')
PY
```
