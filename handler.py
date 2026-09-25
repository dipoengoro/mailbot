#!/usr/bin/env python3
"""Handler: semua interaksi Telegram — tombol di kartu email, tulis/balas email,
/unsub, /help, dan pembaruan status di kartu.

Cara jalan:
  python3 handler.py --once             proses sekali lalu keluar
  python3 handler.py --minutes 100000   loop (dipakai supervisor.py)

Hanya SATU proses boleh menarik getUpdates (dikunci lewat .handler.lock2); kalau ada dua,
Telegram menjawab HTTP 409 Conflict dan update bisa hilang.
"""
import email
import imaplib
import json
import os
import smtplib
import ssl
import sys
import time
import urllib.parse
import urllib.request
from email.header import decode_header
from email.mime.text import MIMEText
from email.utils import formatdate

import config as C

ST = C.path('state.json')
ACC = C.EMAIL_TO_TAG              # alamat email -> tag akun
SMTP = C.SMTP                     # tag -> (host smtp, port)
ALLOWED = C.TG_ALLOWED            # whitelist user Telegram yang boleh memerintah bot
CHAT, THREAD = C.TG_CHAT, C.TG_THREAD
BOT_USERNAME = C.BOT_USERNAME     # balasan harus reply ke pesan bot ini
NAMA_AKUN = [a['email'] for a in C.ACCOUNTS]

# message_id kartu email yang sedang ditap. Diisi tiap callback diproses, dipakai
# say() supaya hasil aksi nempel (reply) ke kartu asalnya. Teks biasa -> None.
CARD_ID = None


def api(m, **p):
    """Panggil satu method Telegram. Kalau Telegram menolak, isi jawabannya ikut
    dibawa di pesan error ('description' di situ sebabnya), supaya bisa didiagnosa."""
    import urllib.error as _ue
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{C.TG_TOKEN}/{m}",
        data=urllib.parse.urlencode(p).encode())
    try:
        with urllib.request.urlopen(req, timeout=30) as f:
            return json.loads(f.read().decode())
    except _ue.HTTPError as e:
        raise RuntimeError('%s %s: %s' % (m, e.code, e.read().decode(errors='replace')[:300]))


def load():
    try:
        return json.load(open(ST))
    except Exception:
        return {}


def save(s):
    with open(ST, 'w') as f:
        json.dump(s, f)
    os.chmod(ST, 0o600)


E, dec = C.E, C.dec        # helper yang sama dipakai poller/render (config.py)


def say(t, kb=None, reply_to='auto'):
    """Kirim hasil aksi sebagai pesan biasa.
    reply_to='auto' -> ikut menempel (reply) ke kartu email yang sedang ditap,
    supaya jelas hasil ini milik email yang mana. None = pesan lepas."""
    if C.FOOTER:               # penanda bot (MAILBOT_FOOTER), biar kebedain dari bot lain
        t = t + '\n\n' + C.FOOTER
    p = {'chat_id': CHAT, 'text': t, 'parse_mode': 'HTML', 'disable_web_page_preview': 'true'}
    if THREAD:
        p['message_thread_id'] = THREAD
    rt = CARD_ID if reply_to == 'auto' else reply_to
    if rt:
        p['reply_to_message_id'] = rt
        # kartu-nya sudah keburu hilang/dihapus? tetap kirim, jangan gagal 400
        p['allow_sending_without_reply'] = 'true'
    if kb:
        p['reply_markup'] = json.dumps(kb)
    return api('sendMessage', **p)


def detail(acct, uid):
    """Baris detail email (dari / subj / tgl) buat hasil aksi tombol.
    Sumber pertama: cache kepala email yang ditulis poller (state_poller.json),
    biar tidak perlu fetch IMAP lagi. Kalau kosong: fetch header langsung."""
    d = None
    try:
        d = (json.load(open(C.path('state_poller.json'))).get('head') or {}).get(f'{acct}:{uid}')
    except Exception:
        d = None
    if d:
        return [f'    dari : {d.get("from") or "?"}',
                f'    subj : {d.get("subj") or "(tanpa subjek)"}',
                f'    tgl  : {d.get("tgl") or "-"}']
    try:
        m = head(acct, uid)
        return [f'    dari : {dec(m.get("From"), 60)}',
                f'    subj : {dec(m.get("Subject"), 80) or "(tanpa subjek)"}',
                f'    tgl  : {dec(m.get("Date"), 40)}']
    except Exception:
        return []


# Status kartu setelah tombol berhasil ditekan (poller menulis status awalnya).
STATUS_AKSI = {'look': '✅ sudah dibaca', 'seen': '✅ sudah dibaca', 'arch': '📁 diarsipkan'}


def sisa_baru(acct):
    """Baris 'sisa' dihitung ULANG setelah aksi, biar angka di kartu tidak basi.
    Logika unread dipakai ulang dari poller.py — jangan ditulis dua kali."""
    try:
        import importlib.util
        s = importlib.util.spec_from_file_location('mb_poller', os.path.join(C.CODE_DIR, 'poller.py'))
        p = importlib.util.module_from_spec(s)
        s.loader.exec_module(p)
        tag = ACC[acct]
        M = C.imap(tag)
        baris = p.unread_line(*p.unread_of(M, p.folders_of(M)))
        M.logout()
        return baris
    except Exception:
        return None


def edit_card(cq, status=None, acct=None):
    """Tulis ulang kartu yang ditap: baris status (+ baris sisa) diedit di tempat.
    Tombol dipasang balik dari reply_markup kartu, kalau tidak ikut hilang."""
    import re as _rx
    m = (cq or {}).get('message') or {}
    mid, txt = m.get('message_id'), m.get('text') or ''
    if not mid or not txt:
        return False
    baru = txt
    if status:
        _s = '    status : ' + status
        baru = (_rx.sub(r'^    status :.*$', lambda _m: _s, baru, flags=_rx.M)
                if _rx.search(r'^    status :.*$', baru, _rx.M)
                else baru.rstrip('\n') + '\n' + _s)   # kartu lama (belum ada baris status)
    if acct:
        _l = sisa_baru(acct)
        if _l:
            for _pola in (r'^    sisa :.*$', r'^    belum dibaca :.*$'):
                if _rx.search(_pola, baru, _rx.M):
                    baru = _rx.sub(_pola, lambda _m: _l, baru, flags=_rx.M)
                    break
    if baru == txt:
        return False
    p = {'chat_id': CHAT, 'message_id': mid, 'text': baru, 'parse_mode': 'HTML',
         'disable_web_page_preview': 'true'}
    if m.get('reply_markup'):
        p['reply_markup'] = json.dumps(m['reply_markup'])
    try:
        return bool(api('editMessageText', **p).get('ok'))
    except Exception as e:
        print('edit kartu gagal', type(e).__name__, str(e)[:200])
        # Kartu lama bisa memuat '<' atau '&' mentah sehingga parse_mode HTML ditolak
        # Telegram. Coba sekali lagi tanpa parse_mode: tampilan apa adanya lebih baik
        # daripada status di kartu yang tidak ikut berubah.
        try:
            p.pop('parse_mode', None)
            return bool(api('editMessageText', **p).get('ok'))
        except Exception as e2:
            print('edit kartu gagal juga tanpa parse_mode', type(e2).__name__, str(e2)[:200])
            return False


FOLDER_KANDIDAT = C.FOLDERS       # folder yang dicari saat tombol aksi dipakai


def head(acct, uid):
    tag = ACC[acct]
    M = C.imap(tag)
    for _f in FOLDER_KANDIDAT:
        try:
            if M.select(_f, readonly=True)[0] != 'OK':
                continue
            _t, _d = M.uid('SEARCH', None, f'UID {uid}')
            if _d and _d[0]:
                break
        except Exception:
            continue
    t, d = M.uid('FETCH', uid, '(BODY.PEEK[HEADER])')
    raw = b''.join(x[1] for x in d if isinstance(x, tuple))
    M.logout()
    return email.message_from_bytes(raw)


def send_mail(acct, uid, body, to=None, subject=None):
    tag = ACC[acct]
    if to:                                   # compose: tidak ada email asal, jadi tanpa In-Reply-To
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['From'] = C.A[tag]['user']
        msg['To'] = to
        msg['Subject'] = (subject or '(tanpa subjek)').strip()
        msg['Date'] = formatdate(localtime=True)
        s = C.smtp(tag)
        s.send_message(msg)
        s.quit()
        return to
    m = head(acct, uid)
    to = (m.get('Reply-To') or m.get('From') or '').strip()
    subj = dec(m.get('Subject'), 200)
    mid = (m.get('Message-ID') or '').strip()
    refs = (m.get('References') or '').strip()
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['From'] = C.A[tag]['user']
    msg['To'] = to
    msg['Subject'] = subj if subj.lower().startswith('re:') else f'Re: {subj}'
    msg['Date'] = formatdate(localtime=True)
    if mid:
        msg['In-Reply-To'] = mid
        msg['References'] = (refs + ' ' + mid).strip() if refs else mid
    s = C.smtp(tag)
    s.send_message(msg)
    s.quit()
    return to


def perlu_jaga(adr):
    """True = email transaksional/penting -> JANGAN di-unsubscribe."""
    import re as _r3
    a = (adr or '').lower()
    pola = (r'(accounts?@|noreply-accounts|cloudplatform|security|billing|invoice|receipt|'
            r'payment|transaksi|tagihan|verifikasi|otp|reset|support|help@|order|shipping|'
            r'pengiriman|alert|monitoring)')
    if _r3.search(pola, a):
        return True
    # domain yang isinya transaksi/infra penting (jangan dibuangkan)
    jaga = ('jenius.com', 'wise.com', 'grab.com', 'google.com', 'zohocorp.com',
            'netdata.cloud', 'dicoding.com', 'github.com', 'openai.com', 'anthropic.com',
            'cloudflare.com', 'hetzner', 'contabo', 'aws.amazon.com', 'microsoft.com')
    return any(d in a for d in jaga)


# nama perintah & akun ikut konfigurasi (username bot dari MAILBOT_BOT_USERNAME)
_cmd = ('@' + BOT_USERNAME) if BOT_USERNAME else ''
_tulis = '/tulis' + _cmd
_unsub = '/unsub' + _cmd
_akun1 = NAMA_AKUN[0] if NAMA_AKUN else 'you@example.com'
_akun2 = NAMA_AKUN[1] if len(NAMA_AKUN) > 1 else _akun1

HELP_TEXT = f"""🤖 <b>mailbot — cara pakai</b>

<b>Kartu email baru</b> (muncul otomatis)
👁 <b>Lihat</b> — buka emailnya sebagai halaman web (langsung ditandai sudah dibaca)
✍️ <b>Balas</b> — bikin draft balasan. balas pesan bot, ketik teksmu, lalu 🚀 Kirim
📁 <b>Arsip</b> — keluarkan dari INBOX
✅ <b>Baca</b> — tandai sudah dibaca tanpa membuka
🔇 <b>Bisukan</b> — berhenti dikabari untuk email itu

Setiap kartu juga menampilkan <b>jumlah email yang belum dibaca</b> (total + per folder),
dan hasil tap tombol muncul sebagai <b>balasan ke kartu emailnya</b> — jadi jelas
hasil ini milik email yang mana.

<b>Status di kartu</b> ikut berubah sendiri: <code>status : 🔵 belum dibaca</code>
jadi <code>✅ sudah dibaca</code> setelah 👁 Lihat / ✅ Baca, atau
<code>📁 diarsipkan</code> setelah 📁 Arsip — sekaligus angka sisa dihitung ulang.

<b>Tulis email baru</b>
<code>{_tulis} ke@x.com | Subjek | isi email</code>
   • bagian isi boleh banyak baris
   • pengirim default <code>{_akun1}</code>. ganti dengan menambah di akhir:
     <code>... | isi email | {_akun2}</code>
   • setelah draft muncul: 🚀 Kirim · ❌ Batal · 🔄 Ganti pengirim

<b>Berhenti langganan (unsubscribe)</b>
<code>{_unsub}</code>
   • bot scan dulu (±30-60 detik), lalu kasih daftar pengirim yang nyediain unsubscribe
   • dipisah 2: ✅ rekomendasi dibuangkan · ⚠️ jangan (transaksional/penting)
   • tap tombol 🚫 = berhenti langganan: ⚡ one-click sekali tap,
     ✉️ bot kirim mailto-nya, 🔗 bot kasih linknya

<b>Catatan</b>
   • semua kiriman lewat DRAFT dulu — tidak ada kirim otomatis
   • jam &amp; tanggal pakai {C.TZ_LABEL}
   • akun: {' · '.join(NAMA_AKUN) or '(belum diisi)'}
"""


def draft_kb(baru=False):
    """Tombol kartu draft: Kirim / Batal / Sempurnakan AI / kembali ke versi awal (+ pilih pengirim)."""
    rows = [[
        {'text': '🚀 Kirim', 'callback_data': 'snd:x:x'},
        {'text': '❌ Batal', 'callback_data': 'cxl:x:x'}],
        [{'text': '🤖 Sempurnakan', 'callback_data': 'ai:x:x'},
         {'text': '↩️ Versi awal', 'callback_data': 'bck:x:x'}]]
    if baru:
        rows.append([{'text': '🔄 Ganti pengirim', 'callback_data': 'sw:x:x'}])
    return {'inline_keyboard': rows}


def on_text(m):
    st = load()
    cid = str(m.get('from', {}).get('id', ''))
    txt = (m.get('text') or '').strip()
    pend = st.get('pending')
    rp = (m.get('reply_to_message') or {}).get('from', {}) or {}
    # --- /unsub: cari kandidat berhenti langganan (RFC 8058 one-click) ---
    if cid in ALLOWED and txt.lower().split('@')[0].strip() in ('/unsub', '/unsubscribe'):
        say('⏳ nyari kandidat unsubscribe di semua akun… (±30-60 detik, santai aja)')
        import subprocess as _sp
        try:
            _sp.run([sys.executable, os.path.join(C.CODE_DIR, 'unsub.py'), '60'],
                    capture_output=True, text=True, timeout=420)
            data = json.load(open(C.path('unsub.json')))
        except Exception as e:
            say(f'⚠️ gagal scan: {type(e).__name__}: {str(e)[:120]}')
            return
        st['unsub'] = data
        save(st)
        ikon = {'ONE-CLICK': '⚡', 'mailto': '✉️', 'link': '🔗'}
        baris, kb = [], []
        for tag, nama in C.ACCTS:
            rows = data.get(tag) or []
            buang = [r for r in rows if not perlu_jaga(r['adr'])]
            jaga = [r for r in rows if perlu_jaga(r['adr'])]
            baris.append(f'<b>{E(nama)}</b>')
            baris.append(f'   <b>✅ rekomendasi dibuangkan</b> ({len(buang)})')
            for r in buang[:9]:
                baris.append(f'      {ikon.get(r["mode"], "•")} {r["n"]}x {E(r["adr"])}')
            if jaga:
                baris.append(f'   <b>⚠️ jangan (transaksional/penting)</b> ({len(jaga)})')
                for r in jaga[:5]:
                    baris.append(f'      {ikon.get(r["mode"], "•")} {r["n"]}x {E(r["adr"])}')
            baris.append('')
            for i, r in enumerate(rows):
                if r['adr'] in [x['adr'] for x in buang[:8]]:
                    kb.append({'text': f'🚫 {r["adr"].split("@")[-1][:16]} ({r["n"]})', 'callback_data': f'uns:{tag}:{i}'})
        baris.append('<i>tombol 🚫 cuma buat yang direkomendasikan · ⚡ one-click · ✉️/🔗 manual</i>')
        say('\n'.join(baris), kb={'inline_keyboard': [kb[i:i + 2] for i in range(0, len(kb), 2)]})
        return 'daftar unsub dikirim'
    # --- /help, /bantuan, /start ---
    if cid in ALLOWED and txt.lower().split('@')[0].strip() in ('/help', '/bantuan', '/start'):
        say(HELP_TEXT)
        return
    # --- compose: /tulis[@bot]  ke | subjek | isi [| akun-pengirim] ---
    if txt.lower().startswith('/tulis') and cid in ALLOWED:
        import re as _re
        arg = _re.sub(r'^/tulis(@\w+)?', '', txt, flags=_re.I).strip()
        if not arg or arg.lower() in ('help', '?', 'bantuan'):
            say(HELP_TEXT if arg else '✍️ <b>tulis email baru</b>\n'
                'format: <code>' + _tulis + ' ke@x.com | Subjek | isi email</code>\n'
                'opsional di akhir: <code>| ' + _akun2 + '</code> — akun pengirim (default ' + _akun1 + ')')
            return
        f = [x.strip() for x in arg.split('|')]
        acct = NAMA_AKUN[0] if NAMA_AKUN else ''
        if len(f) > 3 and f[-1] in ACC:
            acct = f.pop()
        to = f[0] if f else ''
        subj = f[1] if len(f) > 1 else ''
        body = '|'.join(f[2:]).strip() if len(f) > 2 else ''
        if '@' not in to or not body:
            say('⚠️ format belum lengkap. contoh:\n<code>' + _tulis + ' budi@x.com | Laporan | isi emailnya</code>')
            return
        st['draft'] = {'kind': 'new', 'acct': acct, 'to': to, 'subject': subj, 'body': body}
        save(st)
        say('\n'.join([
            f'📝 <b>DRAFT email baru</b> · dari {E(acct)}',
            f'    ke   : {E(to)}',
            f'    subj : {E(subj) or "(tanpa subjek)"}',
            '',
            E(body[:900]),
            '',
            '<i>belum terkirim. tekan 🚀 Kirim kalau sudah pas.</i>']),
            kb=draft_kb(True))
        return
    if cid not in ALLOWED or not pend or not txt or txt.startswith('/'):
        return
    # opsi B: balasan wajib berupa REPLY ke pesan bot ini, biar nggak nyasar ke Hermes
    if rp.get('username') != BOT_USERNAME:
        return
    acct, uid = pend['acct'], pend['uid']
    try:
        om = head(acct, uid)
    except Exception as e:
        say(f'⚠️ gagal baca email aslinya: {type(e).__name__}: {str(e)[:90]}')
        st.pop('pending', None)
        save(st)
        return
    st['draft'] = {'acct': acct, 'uid': uid, 'body': txt}
    st.pop('pending', None)
    save(st)
    say('\n'.join([
        f'📝 <b>DRAFT balasan</b> · {E(acct)}',
        f'    ke   : {E(dec(om.get("Reply-To") or om.get("From"), 60))}',
        f'    subj : {E("Re: " + dec(om.get("Subject"), 70))}',
        '',
        E(txt[:900]),
        '',
        '<i>belum terkirim. tekan 🚀 Kirim kalau sudah pas.</i>']),
        kb=draft_kb(False))


def do(action, acct, uid):
    st = load()
    if action == 'reply':
        m = head(acct, uid)
        st['pending'] = {'acct': acct, 'uid': uid}
        save(st)
        say('\n'.join([
            f'✍️ <b>balas</b> · {E(acct)} · uid {E(uid)}',
            f'    ke   : {E(dec(m.get("Reply-To") or m.get("From"), 60))}',
            f'    subj : {E(dec(m.get("Subject"), 70))}',
            '',
            '<i>ketik teks balasanmu sebagai pesan biasa di chat ini. bot bikin DRAFT dulu — belum terkirim.</i>']))
        return 'mode balas aktif — ketik balasanmu'
    if action == 'uns':
        import re as _re2
        import urllib.parse as _up
        import urllib.request as _ur
        data = st.get('unsub') or {}
        rows = data.get(acct) or []
        try:
            r = rows[int(uid)]
        except Exception:
            return 'daftar sudah kedaluwarsa — jalankan /unsub lagi'
        lu = r.get('lu') or ''
        urls = _re2.findall(r'<([^>]+)>', lu) or [x.strip() for x in lu.split(',')]
        http_url = next((u for u in urls if u.lower().startswith('http')), '')
        mailto = next((u for u in urls if u.lower().startswith('mailto:')), '')
        if r.get('mode') == 'ONE-CLICK' and http_url:
            try:
                _req = _ur.Request(http_url, data=b'List-Unsubscribe=One-Click',
                                   headers={'Content-Type': 'application/x-www-form-urlencoded'})
                _res = _ur.urlopen(_req, timeout=30)
                return f'✅ {r["adr"]}: permintaan berhenti-langganan terkirim (HTTP {_res.status})'
            except Exception as e:
                return (f'⚠️ {r["adr"]}: one-click gagal ({type(e).__name__}). '
                        f'buka manual: {http_url[:90]}')
        if mailto:
            try:
                tujuan = mailto.split(':', 1)[1].split('?')[0]
                tag = ACC[acct]
                msgx = MIMEText('unsubscribe', 'plain', 'utf-8')
                msgx['From'] = C.A[tag]['user']
                msgx['To'] = tujuan
                msgx['Subject'] = 'unsubscribe'
                msgx['Date'] = formatdate(localtime=True)
                sx = C.smtp(tag)
                sx.send_message(msgx)
                sx.quit()
                return f'✉️ {r["adr"]}: email berhenti-langganan dikirim ke {tujuan[:60]}'
            except Exception as e:
                return f'⚠️ {r["adr"]}: gagal kirim mailto ({type(e).__name__})'
        if http_url:
            return f'🔗 {r["adr"]}: harus dibuka manual → {http_url[:90]}'
        return f'⚠️ {r["adr"]}: nggak ada cara unsubscribe yang dikenali'
    if action == 'sw':
        d = st.get('draft')
        if not d or d.get('kind') != 'new':
            return 'draft ini bukan email baru — pengirimnya ikut email asalnya'
        urut = list(NAMA_AKUN)
        d['acct'] = urut[(urut.index(d['acct']) + 1) % len(urut)] if d['acct'] in urut else urut[0]
        save(st)
        say('\n'.join([
            f'📝 <b>DRAFT email baru</b> · dari {E(d["acct"])}',
            f'    ke   : {E(d["to"])}',
            f'    subj : {E(d.get("subject")) or "(tanpa subjek)"}',
            '',
            E(d['body'][:900]),
            '',
            '<i>belum terkirim. tekan 🚀 Kirim kalau sudah pas.</i>']),
            kb=draft_kb(True))
        return f'🔄 pengirim diganti ke {d["acct"]}'
    if action == 'ai':
        d = st.get('draft')
        if not d:
            return 'nggak ada draft yang bisa disempurnakan'
        import urllib.request as _ur
        import urllib.error as _ue
        d.setdefault('body_orig', d.get('body', ''))
        konteks = [f'Subjek: {d.get("subject") or "(tanpa subjek)"}', f'Ke: {d.get("to") or "-"}']
        if d.get('kind') != 'new':
            try:
                om = head(d['acct'], d['uid'])
                konteks.append(f'Membalas email dari: {om.get("From") or "-"}')
                konteks.append(f'Subjek email asal: {om.get("Subject") or "-"}')
            except Exception:
                pass
        sys_p = ('Kamu asisten penulis email berbahasa Indonesia. Perbaiki dan lengkapi draft '
                 'email berikut supaya jelas, sopan, dan tidak menggantung. Pertahankan bahasa '
                 'draft (Indonesia/Inggris) dan maksudnya. JANGAN menambah janji, angka, atau '
                 'komitmen yang tidak ada di draft. JANGAN menuliskan ulang baris Subjek/Ke/"Membalas email dari" '
                 'atau konteks lain. Mulai langsung dari sapaan atau isi emailnya. '
                 'Balas HANYA isi emailnya, tanpa penjelasan.')
        usr_p = '\n'.join(konteks) + '\n\nDraft dari saya:\n' + d.get('body', '')
        import json as _json
        if not C.AI_AKTIF:
            return '⚠️ fitur Sempurnakan mati: isi AI_KEY di .env dulu'
        body = _json.dumps({'model': C.AI_MODEL,
                            'messages': [{'role': 'system', 'content': sys_p},
                                         {'role': 'user', 'content': usr_p}],
                            'temperature': 0.4}).encode()
        try:
            req = _ur.Request(C.AI_URL, data=body,
                              headers={'Content-Type': 'application/json',
                                       'Authorization': 'Bearer ' + C.AI_KEY})
            res = _json.load(_ur.urlopen(req, timeout=60))
            hasil = (res['choices'][0]['message']['content'] or '').strip()
            import re as _re4
            _b = hasil.split('\n')
            while _b and _re4.match(r'^(subjek|ke|membalas email dari|subjek email asal)\\s*:', _b[0].strip(), _re4.I):
                _b.pop(0)
            hasil = '\n'.join(_b).strip()
        except Exception as e:
            return f'⚠️ AI gagal: {type(e).__name__}: {str(e)[:110]}'
        if not hasil:
            return '⚠️ AI balas kosong, draft tidak diubah'
        d['body'] = hasil
        save(st)
        baris = [f'📝 <b>DRAFT</b> (versi AI) · dari {E(d["acct"])}' if d.get('kind') == 'new'
                 else f'📝 <b>DRAFT balasan</b> (versi AI) · {E(d["acct"])}']
        if d.get('kind') == 'new':
            baris += [f'    ke   : {E(d.get("to") or "")}', f'    subj : {E(d.get("subject")) or "(tanpa subjek)"}']
        baris += ['', E(hasil[:900]), '', '<i>belum terkirim. cek dulu, baru 🚀 Kirim.</i>']
        say('\n'.join(baris), kb=draft_kb(d.get('kind') == 'new'))
        return 'draft disempurnakan AI'
    if action == 'bck':
        d = st.get('draft')
        if not d or not d.get('body_orig'):
            return 'nggak ada versi awal yang tersimpan'
        d['body'] = d['body_orig']
        save(st)
        baris = ['📝 <b>DRAFT (versi awal)</b>', '', E(d['body'][:900])]
        say('\n'.join(baris), kb=draft_kb(d.get('kind') == 'new'))
        return 'draft dikembalikan ke versi awal'
    if action == 'snd':
        d = st.get('draft')
        if not d:
            return 'nggak ada draft yang nunggu'
        if d.get('kind') == 'new':
            to = send_mail(d['acct'], None, d['body'], to=d['to'], subject=d.get('subject'))
        else:
            to = send_mail(d['acct'], d['uid'], d['body'])
        st.pop('draft', None)
        save(st)
        return f'🚀 terkirim ke {to[:50]}'
    import re as _re
    if action == 'look':
        import secrets
        import subprocess
        tok = secrets.token_hex(C.VIEW_TOKEN_BYTES)
        base = _re.sub(r'[^a-z0-9]', '', acct.split('@')[0].lower())
        name = f'mail-{base}-{uid}-{tok}.html'
        out = os.path.join(C.VIEW_DIR, name)
        os.makedirs(C.VIEW_DIR, exist_ok=True)
        r = subprocess.run([sys.executable, os.path.join(C.CODE_DIR, 'render.py'), '--acct', acct,
                            '--uid', str(uid), '--out', out], capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(out):
            return f'gagal render: {(r.stderr or r.stdout or "")[:120]}'
        # Lihat = sudah dibaca (seperti email client). Flag HANYA diubah kalau render sukses.
        tandai = ''
        try:
            import imaplib as _imap
            _t = ACC[acct]
            _M = C.imap(_t)
            # UID itu unik PER FOLDER: jangan asal STORE ke INBOX, nanti yang
            # ketandai email lain yang kebetulan punya uid sama.
            for _f in FOLDER_KANDIDAT:
                try:
                    if _M.select(_f)[0] != 'OK':
                        continue
                    _x, _y = _M.uid('SEARCH', None, f'UID {uid}')
                    if _y and _y[0]:
                        break
                except Exception:
                    continue
            _M.uid('STORE', uid, '+FLAGS', '(\\Seen)')
            _M.logout()
            tandai = ' · ✓ ditandai sudah dibaca'
        except Exception as e:
            tandai = f' · (gagal menandai dibaca: {type(e).__name__})'
        # detail email ikut ditulis di pesan yang sama (biar jelas ini email yang mana)
        return '\n'.join([f'👁 lihat email · {acct} · uid {uid}'] + detail(acct, uid) +
                         [f'    link : {C.VIEW_BASE}/{name}{tandai}'])
    if action in ('seen', 'mute', 'arch'):
        tag = ACC[acct]
        M = C.imap(tag)
        try:
            for _f in FOLDER_KANDIDAT:      # folder-awareness: email bisa dari Newsletter/Spam dll
                try:
                    if M.select(_f)[0] != 'OK':
                        continue
                    _t, _d = M.uid('SEARCH', None, f'UID {uid}')
                    if _d and _d[0]:
                        break
                except Exception:
                    continue
            if action == 'seen':
                M.uid('STORE', uid, '+FLAGS', '(\\Seen)')
                return f'✅ ditandai sudah dibaca — {acct} uid {uid}'
            if action == 'mute':
                s2 = load()
                mm = s2.setdefault('mute', [])
                if acct not in mm:
                    mm.append(acct)
                save(s2)
                return f'🔇 {acct} dibisukan (aturan tersimpan)'
            t, dl = M.list()
            names = []
            for x in (dl or []):
                q = _re.findall('"([^"]*)"', x.decode(errors='replace'))
                if q:
                    names.append(q[-1])
            dest = None
            for cand in ('all mail', 'archive', 'arsip', 'semua email'):
                for n in names:
                    if n.lower() == cand or n.lower().endswith('/' + cand):
                        dest = n
                        break
                if dest:
                    break
            if not dest:
                return '📁 folder arsip tidak ketemu — dibatalkan, email aman'
            M.uid('COPY', uid, dest)
            M.uid('STORE', uid, '+FLAGS', '(\\Deleted)')
            M.expunge()
            return f'📁 diarsipkan ke "{dest}" — {acct} uid {uid}'
        finally:
            try:
                M.logout()
            except Exception:
                pass
    if action == 'cxl':
        st.pop('draft', None)
        save(st)
        return '❌ draft dibatalkan'
    return None


def handle_once():
    global CARD_ID
    st = load()
    off = st.get('offset', 0)
    n = 0
    try:
        r = api('getUpdates', offset=off, timeout=0,
                allowed_updates=json.dumps(['callback_query', 'message']))
    except Exception as e:
        print('getUpdates err', type(e).__name__, str(e)[:80])
        return 0
    for u in r.get('result', []):
        off = max(off, u['update_id'] + 1)
        if u.get('callback_query'):
            cq = u['callback_query']
            p = (cq.get('data') or '').split(':')
            # kartu yang ditap -> dipakai say() biar hasilnya jadi reply ke kartu itu
            CARD_ID = ((cq.get('message') or {}).get('message_id')) or None
            try:
                msg = (do(p[0], p[1], p[2]) if len(p) == 3 else None) or 'aksi fase C'
            except Exception as e:
                msg = f'gagal: {type(e).__name__}: {str(e)[:130]}'
            # kartunya sendiri diperbarui (status + angka sisa) SEBELUM pesan hasil dikirim,
            # biar kutipan kartu di pesan hasil sudah ikut yang baru
            if p[0] in STATUS_AKSI and 'gagal' not in msg:
                try:
                    if edit_card(cq, STATUS_AKSI[p[0]], p[1]):
                        print('KARTU', p[1], p[2], '->', STATUS_AKSI[p[0]])
                except Exception as e:
                    print('edit kartu err', type(e).__name__, str(e)[:70])
            # jawaban pendek ke toast (biar tombolnya nggak muter)
            try:
                api('answerCallbackQuery', callback_query_id=cq['id'],
                    text=('ok' if not msg.startswith('gagal') else 'gagal — lihat pesannya'))
            except Exception:
                pass
            # hasil aksi dikirim sebagai PESAN BIASA, supaya link bisa diklik
            try:
                say(E(msg if len(msg) < 900 else msg[:900]), reply_to=CARD_ID)   # escape: teks error ada '<' '>' -> Telegram nolak kalau mentah
            except Exception as e:
                print('say err', type(e).__name__, str(e)[:80])
            print('TAP', (cq.get('data') or '')[:24], '-> reply ke', CARD_ID, '|', msg[:100])
            n += 1
        elif u.get('message'):
            CARD_ID = None          # teks biasa: jangan nempel ke kartu lama
            try:
                on_text(u['message'])
            except Exception as e:
                print('msg err', type(e).__name__, str(e)[:90])
            n += 1
    fresh = load()
    fresh['offset'] = max(int(off), int(fresh.get('offset') or 0))
    save(fresh)
    return n


if __name__ == '__main__':
    if '--minutes' in sys.argv:
        import fcntl
        lk = open(C.path('.handler.lock2'), 'w')
        try:
            fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print('handler lain sedang jalan — batal (biar nggak 409 Conflict)')
            sys.exit(0)
        mins = float(sys.argv[sys.argv.index('--minutes') + 1])
        end = time.time() + mins * 60
        print(f'fase D aktif {mins} menit (lock dipegang)')
        while time.time() < end:
            try:
                handle_once()
            except Exception as e:
                print('loop err', type(e).__name__, str(e)[:90])
            time.sleep(3)
        print('selesai (waktu habis)')
    else:
        print('diproses:', handle_once())
