# Integrasi: apa yang dipakai mailbot, dan siapa yang memakai mailbot

mailbot sengaja berdiri sendiri: **tidak ada database, tidak ada message broker, tidak ada
dependensi Python di luar pustaka standar**. Yang perlu diperhatikan justru koneksi ke luar,
dan cara "menutup" tiap ketergantungan itu supaya bot tetap jalan kalau salah satunya tidak ada.

## A. Dipakai oleh mailbot (keluar)

| Layanan | Dipakai untuk | Kalau tidak ada | Cara menutupnya |
| --- | --- | --- | --- |
| Telegram Bot API | semua notifikasi & interaksi | bot tidak berguna | wajib; token dari @BotFather. `config.py` menandai `telegram` kosong saat `config.py` dijalankan |
| Server IMAP | memantau email baru, membaca isi, menandai/arsip | tidak ada notifikasi | wajib per akun; akun dengan env tidak lengkap dilewati, akun lain tetap jalan |
| Server SMTP | mengirim balasan & email baru, kirim mailto unsubscribe | tombol 🚀 Kirim gagal | opsional fungsional; host SMTP diturunkan dari host IMAP atau diisi manual |
| LLM kompatibel OpenAI | tombol 🤖 Sempurnakan | tombol menjawab "fitur mati" | opsional; cukup kosongkan `AI_KEY` |
| Web server untuk `/view` | menyajikan halaman hasil render | tombol 👁 mengirim link yang tidak bisa dibuka | opsional; bisa dipakai webmail saja, atau pakai service `viewer` di compose |

Praktiknya: **kegagalan satu layanan tidak boleh mematikan yang lain.** Contoh yang sudah
dipegang di kode:

- akun yang env-nya tidak lengkap → dilewati dengan catatan, bukan `sys.exit`;
- folder yang tidak ada di server → dilewati;
- halaman render gagal → status "sudah dibaca" **tidak** diubah, dan pesan errornya muncul di chat;
- LLM mati → hanya tombol 🤖 yang terdampak.

## B. Memakai mailbot (masuk)

Ini bagian yang paling mudah terlupakan: bot hidup di dalam ekosistem, dan hal-hal di luar
menempel lewat **tiga titik saja** — heartbeat, log, dan folder state.

### 1. Heartbeat & healthcheck

Poller menulis `/data/.heartbeat` setiap selesai siklus. Jadi:

- **Docker** sudah memakainya: `HEALTHCHECK` di Dockerfile menjalankan
  `scripts/healthcheck.py`, yang membandingkan umur heartbeat dengan
  `MAILBOT_POLL_INTERVAL * 3 + 120` detik.

  ```bash
  docker inspect --format '{{.State.Health.Status}}' mailbot        # healthy / unhealthy
  docker inspect --format '{{range .State.Health.Log}}{{.Output}}{{end}}' mailbot
  ```

- **Uptime Kuma / Healthchecks / Prometheus** bisa memakai cara yang sama tanpa menyentuh
  bot: cek umur file, bukan isinya.

  ```bash
  # contoh: watchdog sederhana yang lapor kalau poller basi > 15 menit
  umur=$(( $(date +%s) - $(stat -c %Y /path/ke/data/.heartbeat) ))
  [ "$umur" -gt 900 ] && echo "mailbot: poller basi ${umur}s"
  ```

- Kalau `MAILBOT_ACCOUNTS` benar-benar kosong, bot hidup tapi tidak melakukan apa pun.
  Ini bukan "sakit", jadi healthcheck tetap `healthy` — periksa lewat `python3 config.py`.

### 2. Log

| Sumber | Isi | Keterangan |
| --- | --- | --- |
| stdout container | gabungan poller + handler | `docker logs -f mailbot`, atau otomatis masuk Loki/promtail/CloudWatch kalau container logging driver-nya sudah diatur |
| `poller.log` | baris ringkasan per siklus (`folder x : 9 \| sisa : 12 belum dibaca (…)`), kartu yang dikirim, error per akun | ditulis dengan `tee`, jadi dua-duanya jalan |
| `handler.log` | `TAP <aksi> -> reply ke <message_id> \| <hasil>`, `KARTU …`, error kirim pesan | satu baris per interaksi |

Pola yang enak dipakai untuk alert sederhana: `grep -c "getUpdates err" handler.log`
(di atas 0 dalam 15 menit terakhir biasanya cuma gangguan jaringan sesaat).

### 3. Folder state (`/data`) → backup

Yang perlu di-backup hanya folder `data/` (state kecil, hitungan KB):

```bash
docker run --rm -v "$PWD/data:/data:ro" -v "$PWD/backup:/out" alpine \
  tar czf /out/mailbot-state-$(date +%F).tar.gz -C /data .
```

Kalau backup-nya hilang: bot menganggap semua email lama sebagai baseline dan mulai
mengabari dari yang baru (aman, tidak ada email yang hilang dari server), tetapi draft yang
belum dikirim di `state.json` ikut hilang.

### 4. Reverse proxy (untuk halaman "Lihat")

Caddy:

```
mail.example.com {
    root * /srv/mailview
    file_server
    header {
        Cache-Control "no-store"
        X-Robots-Tag "noindex, nofollow"
        Referrer-Policy "no-referrer"
    }
}
```

nginx:

```nginx
server {
    listen 443 ssl;
    server_name mail.example.com;
    root /srv/mailview;
    add_header Cache-Control "no-store" always;
    add_header X-Robots-Tag "noindex, nofollow" always;
    add_header Referrer-Policy "no-referrer" always;
}
```

Halaman lama menumpuk di folder itu. Bersihkan berkala, mis. simpan 7 hari:

```bash
find /srv/mailview -maxdepth 1 -name 'mail-*.html' -mtime +7 -delete
find /srv/mailview -maxdepth 1 -name 'mail-*-att*' -mtime +7 -delete
```

### 5. Yang dipakai bersama container lain

Tidak ada. mailbot tidak butuh jaringan Docker bersama reverse proxy (dia hanya konek
keluar), tidak membuka port, dan tidak menyentuh database. Jadi dia aman dipindah, di-restart,
atau dihapus tanpa mengganggu layanan lain — asalkan folder `data/` dan `view/` tetap ada.
