#!/usr/bin/env python3
"""Konfigurasi bersama mailbot.

Satu tempat untuk SEMUA yang berhubungan dengan luar: file .env, daftar akun
IMAP/SMTP, kredensial Telegram, folder yang dipantau, alamat halaman render,
zona waktu, dan API LLM opsional.

Aturan penting:
- Tidak ada satu pun nilai rahasia yang ditanam di kode. Semuanya dari env/.env.
- Menambah akun = tambah 1 var `MAILBOT_ACCOUNTS` + 3 var IMAP_<TAG>_* (lihat .env.example).
- Akun yang env-nya belum lengkap DILEWATI (dengan catatan), bukan bikin bot mati.

Dipakai oleh: poller.py, handler.py, render.py, unsub.py, supervisor.py.
"""
import os

# --- lokasi (hanya dari environment: belum ada .env yang bisa dibaca) --------

# Kode dan data dipisah: kode bisa dari image (read-only), data di volume.
CODE_DIR = os.environ.get('MAILBOT_CODE_DIR') or os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.environ.get('MAILBOT_STATE_DIR') or CODE_DIR
ENV_PATH = os.environ.get('MAILBOT_ENV') or os.path.join(STATE_DIR, '.env')


# --- baca .env + env container ----------------------------------------------

def _baca_env(p):
    d = {}
    try:
        with open(p) as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    d[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return d


ENV = _baca_env(ENV_PATH)
# env container MENANG atas file .env (pola docker compose / env_file)
for _k, _v in os.environ.items():
    if _k.startswith(('TELEGRAM_', 'IMAP_', 'SMTP_', 'MAILBOT_', 'AI_')):
        ENV[_k] = _v


def get(k, d=''):
    """Ambil satu nilai (dari .env atau env container)."""
    return ENV.get(k, d)


def _num(k, default):
    """Nilai angka dari .env/env; kalau kosong atau bukan angka, pakai default."""
    try:
        v = str(get(k)).strip()
        return type(default)(v) if v else default
    except Exception:
        return default


# --- pengaturan umum (boleh diisi di .env MAUPUN env container) --------------

VIEW_DIR = get('MAILBOT_VIEW_DIR') or '/view'
VIEW_BASE = (get('MAILBOT_VIEW_BASE') or 'http://127.0.0.1:8080').rstrip('/')

TZ_OFFSET = _num('MAILBOT_TZ_OFFSET', 7)      # jam dari UTC (+7 = WIB)
TZ_LABEL = get('MAILBOT_TZ_LABEL') or 'WIB'

# Folder yang dicari saat tombol aksi/lihat dipakai (uid itu unik PER folder).
FOLDERS = [x.strip() for x in (get('MAILBOT_FOLDERS') or
           'INBOX,Newsletter,Notification,Spam,Archive,[Gmail]/Spam,[Gmail]/Penting').split(',')
           if x.strip()]

# Nama folder yang TIDAK dipantau poller (isi buatan kita sendiri / duplikat).
SKIP_FOLDER = r'(arsip|archive|sent|terkirim|draft|trash|sampah|all mail|semua email|template)'

# Folder yang tidak dihitung di ringkasan "belum dibaca" (sampah / label duplikat).
SKIP_UNREAD = (r'(spam|junk|bulk|draf|draft|penting|important|berbintang|starred|'
               r'snoozed|all mail|semua email|template)')

# Batas ukuran state (biar file tidak tumbuh tanpa henti).
MAX_HEAD_CACHE = _num('MAILBOT_MAX_HEAD_CACHE', 400)
MAX_MSGID_MEMORY = _num('MAILBOT_MAX_MSGID_MEMORY', 1200)
POLL_INTERVAL = _num('MAILBOT_POLL_INTERVAL', 180)

VIEW_TOKEN_BYTES = _num('MAILBOT_VIEW_TOKEN_BYTES', 8)   # 8 byte = 16 hex


def path(nama):
    """Path file state/log di dalam STATE_DIR."""
    return os.path.join(STATE_DIR, nama)


# --- akun email -------------------------------------------------------------

_SMTP_PETA = {
    'imap.gmail.com': 'smtp.gmail.com',
    'imappro.zoho.com': 'smtp.zoho.com',
    'imap.zoho.com': 'smtp.zoho.com',
    'imap.zoho.eu': 'smtp.zoho.eu',
    'imap.zoho.in': 'smtp.zoho.in',
    'outlook.office365.com': 'smtp.office365.com',
    'imap.mail.yahoo.com': 'smtp.mail.yahoo.com',
    'imap.fastmail.com': 'smtp.fastmail.com',
    'imap.mail.me.com': 'smtp.mail.me.com',
    'imap.migadu.com': 'smtp.migadu.com',
}


def _smtp_host(host, tag):
    """SMTP satu penyedia dengan IMAP-nya. Selalu utamakan SMTP_<TAG>_HOST kalau diisi."""
    eksplisit = ENV.get('SMTP_%s_HOST' % tag)
    if eksplisit:
        return eksplisit
    h = (host or '').lower()
    if h in _SMTP_PETA:
        return _SMTP_PETA[h]
    if h.startswith('imap'):            # imap.example.com / imap2.example.com -> smtp.example.com
        sisa = h[4:].lstrip('0123456789.')
        return ('smtp.' + sisa) if sisa else ''
    return ''


def _akun():
    raw = ENV.get('MAILBOT_ACCOUNTS', '')
    hasil = []
    for bagian in raw.replace(';', ',').split(','):
        bagian = bagian.strip()
        if not bagian:
            continue
        if ':' in bagian:
            tag, email = bagian.split(':', 1)
        else:
            tag, email = bagian, bagian
        tag = tag.strip().upper().replace(' ', '_')
        email = email.strip()
        host = ENV.get('IMAP_%s_HOST' % tag, '')
        sandi = ENV.get('IMAP_%s_PASS' % tag, '')
        if not (tag and email and host and sandi):
            print('  akun %s dilewati: env IMAP_%s_{HOST,PASS} belum lengkap' % (email or tag, tag))
            continue
        hasil.append({
            'tag': tag, 'email': email, 'host': host,
            'imap_port': int(ENV.get('IMAP_%s_PORT' % tag) or 993),
            'user': ENV.get('IMAP_%s_USER' % tag) or email,
            'pass': sandi,
            'smtp_host': _smtp_host(host, tag),
            'smtp_port': int(ENV.get('SMTP_%s_PORT' % tag) or 465),
        })
    return hasil


ACCOUNTS = _akun()
A = {a['tag']: a for a in ACCOUNTS}                      # tag -> data akun
EMAIL_TO_TAG = {a['email'].lower(): a['tag'] for a in ACCOUNTS}
SMTP = {a['tag']: (a['smtp_host'], a['smtp_port']) for a in ACCOUNTS}
ACCTS = [(a['tag'], a['email']) for a in ACCOUNTS]       # urutan pemrosesan poller


def imap(tag, folder=None, readonly=True):
    """Koneksi IMAP siap pakai. folder=None -> belum ada kotak yang dipilih."""
    import imaplib
    a = A[tag]
    M = imaplib.IMAP4_SSL(a['host'], a['imap_port'])
    M.login(a['user'], a['pass'])
    if folder:
        M.select(folder, readonly=readonly)
    return M


def smtp(tag):
    """SMTP_SSL siap pakai (sudah login)."""
    import smtplib
    import ssl
    a = A[tag]
    s = smtplib.SMTP_SSL(a['smtp_host'], a['smtp_port'],
                         context=ssl.create_default_context(), timeout=40)
    s.login(a['user'], a['pass'])
    return s


# --- telegram ---------------------------------------------------------------

TG_TOKEN = ENV.get('TELEGRAM_BOT_TOKEN', '')
TG_CHAT = ENV.get('TELEGRAM_HOME_CHANNEL', '')
TG_THREAD = ENV.get('TELEGRAM_HOME_THREAD', '')
TG_ALLOWED = set(x for x in ENV.get('TELEGRAM_ALLOWED_USERS', '').split(',') if x)
# Username bot (tanpa @), dipakai handler untuk memastikan balasan memang reply ke pesan bot.
# Ambil dari nama bot di BotFather, atau isi MAILBOT_BOT_USERNAME di .env.
BOT_USERNAME = ENV.get('MAILBOT_BOT_USERNAME', '').lstrip('@')

# Penanda bot di tiap pesan (biar kebedain dari bot lain di grup yang sama). Kosong = tanpa footer.
FOOTER = ENV.get('MAILBOT_FOOTER', '')


def tg_admin_chat():
    """true kalau chat/thread notifikasi memang sudah diisi."""
    return bool(TG_TOKEN and TG_CHAT)


# --- LLM opsional (tombol 🤖 Sempurnakan) -----------------------------------

AI_KEY = ENV.get('AI_KEY', '')
AI_URL = ENV.get('AI_URL') or 'https://api.deepseek.com/v1/chat/completions'
AI_MODEL = ENV.get('AI_MODEL') or 'deepseek-chat'
AI_AKTIF = bool(AI_KEY)          # tanpa AI_KEY fitur Sempurnakan dimatikan, bot tetap jalan


# --- helper kecil yang dipakai banyak script --------------------------------

def E(s):
    """Escape buat parse_mode HTML Telegram."""
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def hdr(s):
    """Decode RFC2047 (subjek/nama ber-encode) dengan benar ('=' dan '_')."""
    from email.header import decode_header, make_header
    try:
        return str(make_header(decode_header(str(s or ''))))
    except Exception:
        return str(s or '')


def dec(s, n=95):
    """Header -> teks bersih, dipotong n karakter."""
    s = hdr(s)
    if not s:
        return ''
    out = ''
    from email.header import decode_header
    for part, enc in decode_header(s):
        out += part.decode(enc or 'utf-8', 'replace') if isinstance(part, bytes) else part
    return ' '.join(out.split())[:n]


def sname(raw):
    """'Nama <alamat>' yang rapi (nama didecode lebih dulu)."""
    import email.utils
    n, a = email.utils.parseaddr(raw or '')
    return (dec(n, 38) or a or '?') + ((' <%s>' % a[:36]) if a else '')


def jam():
    """Jam lokal untuk log — offset tetap, tidak butuh tzdata."""
    from datetime import datetime, timezone, timedelta
    return datetime.now(timezone(timedelta(hours=TZ_OFFSET))).strftime('%H:%M:%S')


def wib(raw):
    """Tanggal header email -> jam lokal (label TZ_LABEL)."""
    from datetime import timezone, timedelta
    from email.utils import parsedate_to_datetime
    try:
        d = parsedate_to_datetime(str(raw or '').strip())
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone(timedelta(hours=TZ_OFFSET))).strftime('%d %b %Y %H:%M') + ' ' + TZ_LABEL
    except Exception:
        return dec(raw, 40)


def baca_json(p, default=None):
    import json
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        return {} if default is None else default


def tulis_json(p, data, mode=0o600):
    """Tulis atomik (temp + rename) supaya pembaca lain tidak dapat file separuh."""
    import json
    import os as _os
    try:
        tmp = p + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(data, f)
            f.flush()
            _os.fsync(f.fileno())
        _os.replace(tmp, p)
        _os.chmod(p, mode)
    except Exception:
        pass


if __name__ == '__main__':
    # `python3 config.py` = cara cepat cek konfigurasi tanpa membocorkan rahasia.
    print('state dir   :', STATE_DIR)
    print('env file    :', ENV_PATH, '(ada)' if os.path.exists(ENV_PATH) else '(tidak ada)')
    print('view        :', VIEW_BASE, '->', VIEW_DIR)
    print('zona waktu  :', 'UTC%+g' % TZ_OFFSET, TZ_LABEL)
    print('akun terdaftar:', len(ACCOUNTS))
    for a in ACCOUNTS:
        print('  - %-4s %s  imap=%s:%s smtp=%s:%s  pass=%d karakter'
              % (a['tag'], a['email'], a['host'], a['imap_port'],
                 a['smtp_host'], a['smtp_port'], len(a['pass'])))
    print('telegram    : chat=%s thread=%s whitelist=%d  token=%d karakter'
          % (TG_CHAT or '(kosong)', TG_THREAD or '(kosong)', len(TG_ALLOWED), len(TG_TOKEN)))
    print('LLM /ai     :', 'aktif (%s)' % AI_MODEL if AI_AKTIF else 'mati (AI_KEY kosong)')
    print('footer      :', FOOTER or '(tanpa footer)')
