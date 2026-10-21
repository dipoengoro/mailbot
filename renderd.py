#!/usr/bin/env python3
"""renderd — halaman email dibuat saat link DIBUKA, bukan saat tombol ditekan.

Dulu tombol 👁 Lihat menunggu render selesai: tarik email penuh lewat IMAP, susun
HTML, tulis berkas — dua sampai lima detik. Sekarang tombolnya cuma memesan
token (satu berkas kecil), lalu langsung menjawab link. Render baru terjadi saat
link itu dibuka, dan hasilnya disimpan supaya buka kedua kali seketika.

Rute (dipanggil Caddy lewat reverse_proxy):
  GET /l/<token>     halaman email
  GET /healthz       tanda hidup

Token 16 heksadesimal dari bot, disimpan sebagai /view/jobs/<token>.json berisi
{acct, uid, dibuat}. Isi halaman ditulis ke /view/cache/<token>.html.
"""
import fcntl
import json
import os
import re
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import config as C  # noqa: E402

JOBS = os.path.join(C.VIEW_DIR, 'jobs')
CACHE = os.path.join(C.VIEW_DIR, 'cache')
PORT = int(os.environ.get('MAILBOT_VIEWD_PORT') or 8098)
UMUR_JOB = 7 * 24 * 3600
POLA_TOKEN = re.compile(r'^[0-9a-f]{16,64}$')


def siapkan():
    os.makedirs(JOBS, exist_ok=True)
    os.makedirs(CACHE, exist_ok=True)
    # Bersihkan sisa lama supaya volume tidak menumpuk tanpa batas.
    batas = time.time() - UMUR_JOB
    for folder in (JOBS, CACHE):
        for nama in os.listdir(folder):
            path = os.path.join(folder, nama)
            try:
                if os.path.getmtime(path) < batas:
                    os.remove(path)
            except OSError:
                pass


def render(acct, uid, keluar):
    """Jalankan renderer yang sudah ada; dia yang tahu cara membaca IMAP."""
    r = subprocess.run(
        [sys.executable, os.path.join(HERE, 'render.py'), '--acct', acct,
         '--uid', str(uid), '--out', keluar],
        capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0 or not os.path.exists(keluar):
        return (r.stderr or r.stdout or 'render gagal').strip()[:300]
    return None


class Handler(BaseHTTPRequestHandler):
    server_version = 'renderd/1'

    def log_message(self, fmt, *args):
        sys.stderr.write('%s %s\n' % (self.command, self.path.split('?')[0]))

    def kirim(self, kode, isi, tipe='text/html; charset=utf-8'):
        if isinstance(isi, str):
            isi = isi.encode('utf-8', 'replace')
        self.send_response(kode)
        self.send_header('Content-Type', tipe)
        self.send_header('Content-Length', str(len(isi)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Robots-Tag', 'noindex, nofollow')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.end_headers()
        try:
            self.wfile.write(isi)
        except BrokenPipeError:
            pass

    def halaman_galat(self, kode, pesan):
        aman = (pesan or '').replace('&', '&amp;').replace('<', '&lt;')
        self.kirim(kode, (
            '<!doctype html><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<body style="font:16px/1.5 system-ui;padding:24px">'
            f'<h1 style="font-size:18px">Halaman tidak bisa dibuka</h1><p>{aman}</p></body>'
        ))

    def do_GET(self):
        jalan = self.path.split('?')[0].rstrip('/')
        if jalan == '/healthz':
            return self.kirim(200, 'ok', 'text/plain')

        bagian = [b for b in jalan.split('/') if b]
        if len(bagian) != 2 or bagian[0] != 'l':
            return self.halaman_galat(404, 'Alamat tidak dikenal.')

        token = bagian[1]
        if not POLA_TOKEN.match(token):
            return self.halaman_galat(404, 'Token tidak sah.')

        berkas_job = os.path.join(JOBS, token + '.json')
        if not os.path.exists(berkas_job):
            return self.halaman_galat(410, 'Link ini sudah kedaluwarsa atau tidak pernah ada.')

        try:
            job = json.load(open(berkas_job))
        except (OSError, ValueError):
            return self.halaman_galat(500, 'Data link rusak.')

        keluaran = os.path.join(CACHE, token + '.html')
        if not os.path.exists(keluaran):
            # Satu pembaca merender; yang lain menunggu berkas yang sama jadi.
            kunci = open(os.path.join(CACHE, token + '.lock'), 'w')
            try:
                fcntl.flock(kunci, fcntl.LOCK_EX)
                if not os.path.exists(keluaran):
                    galat = render(job['acct'], job['uid'], keluaran)
                    if galat:
                        return self.halaman_galat(502, galat)
            finally:
                fcntl.flock(kunci, fcntl.LOCK_UN)
                kunci.close()

        try:
            with open(keluaran, 'rb') as f:
                return self.kirim(200, f.read())
        except OSError:
            return self.halaman_galat(500, 'Halaman gagal dibaca.')


def main():
    siapkan()
    srv = ThreadingHTTPServer(('0.0.0.0', PORT), Handler)
    sys.stderr.write('renderd mendengarkan di :%d (job %s)\n' % (PORT, JOBS))
    srv.serve_forever()


if __name__ == '__main__':
    main()
