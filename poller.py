#!/usr/bin/env python3
"""Poller: memantau email baru di semua akun (IMAP) lalu mengirim kartu ke Telegram.

Cara jalan:
  python3 poller.py                 loop terus-menerus (interval MAILBOT_POLL_INTERVAL)
  python3 poller.py --once          sekali periksa, lalu keluar
  python3 poller.py --test          kirim satu email uji dari akun terakhir (uji jalur)

Dedup pakai UID + UIDVALIDITY (per folder) dan Message-ID (antar folder / label),
jadi email yang sama di INBOX dan label lain tidak dikabari dua kali.
"""
import email
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

import config as C

STATE = C.path('state_poller.json')
ACCTS = C.ACCTS             # [(tag, alamat email), ...] dari MAILBOT_ACCOUNTS

# Folder yang dipantau per akun. INBOX selalu ikut. Folder filter (Newsletter/Notification)
# TIDAK lewat INBOX, jadi harus dipantau sendiri, kalau tidak notifikasinya kelewat.
# Jangan tambah Arsip/Trash/Sent: email yang kita sendiri pindahkan ke sana akan
# dianggap email baru kalau foldernya dipantau.
# Folder yang TIDAK dipantau: isinya dibuat oleh aksi kita sendiri / duplikat.
# Arsip = hasil tombol Arsip, Sent = hasil kiriman kita, Trash = hasil hapus,
# All Mail/Semua Email = duplikat dari folder lain.
# '\\' sebagai bytes, dibikin dari chr(92) biar tidak tersangkut escaping string
BACKSLASH = chr(92).encode()
SKIP_FOLDER = re.compile(C.SKIP_FOLDER, re.I)

# Folder yang TIDAK dihitung di ringkasan "belum dibaca": isinya bukan email yang
# nunggu dibaca, atau cuma LABEL duplikat (Gmail: email yang sama muncul di INBOX
# dan [Gmail]/Penting -> kalau dihitung dua-duanya, angkanya bohong).
SKIP_UNREAD = re.compile(C.SKIP_UNREAD, re.I)


def folders_of(M):
    """Semua folder yang bisa dibaca, minus yang di-skip."""
    out = []
    try:
        t, dl = M.list()
    except Exception:
        return ['INBOX']
    for line in dl or []:
        s2 = line.decode('utf-8', 'replace')
        if '\\Noselect' in s2:
            continue
        q = re.findall(r'"([^"]*)"', s2)
        if not q:
            continue
        n = q[-1]
        if SKIP_FOLDER.search(n):
            continue
        out.append(n)
    if 'INBOX' not in out:
        out.insert(0, 'INBOX')
    return out


def q(f):
    """Nama mailbox untuk IMAP — selalu quoted-string (nama folder bisa ada spasi)."""
    return '"' + f.replace('\\', '\\\\').replace('"', '\\"') + '"'


def unread_of(M, folders):
    """({folder: jumlah UNSEEN}, total). Pakai STATUS (satu perintah per folder,
    tanpa SELECT) — poller versi lama sudah membuktikan STATUS jalan di Zoho
    maupun Gmail walau mailbox lain sedang terpilih. Kalau STATUS ditolak,
    jatuh ke SELECT readonly + SEARCH UNSEEN (tidak mengubah flag)."""
    per, tot = {}, 0
    for f in folders:
        if SKIP_UNREAD.search(f):
            continue
        num = None
        try:
            t, d = M.status(q(f), '(UNSEEN)')
            if t == 'OK' and d and d[0]:
                m2 = re.search(rb'UNSEEN\s+(\d+)', d[0])
                if m2:
                    num = int(m2.group(1))
        except Exception:
            num = None
        if num is None:
            try:
                if M.select(q(f), readonly=True)[0] != 'OK':
                    continue
                _t, _d = M.uid('SEARCH', None, 'UNSEEN')
                num = len(_d[0].split()) if _d and _d[0] else 0
            except Exception:
                continue
        per[f] = num
        tot += num
    return per, tot


def unread_line(per, tot):
    """Ringkasan buat kartu notifikasi: total + rincian per folder yang ada isinya."""
    if not per:
        return ''
    ada = [f'{f} {n}' for f, n in per.items() if n]
    if not ada:
        return '    sisa : 0 belum dibaca ✨'
    return f'    sisa : {tot} belum dibaca (' + ' · '.join(ada) + ')'


E, dec, sname, jam, wib = C.E, C.dec, C.sname, C.jam, C.wib


def tg(text):
    import re as _re
    p = {'chat_id': C.TG_CHAT, 'text': text,
         'parse_mode': 'HTML', 'disable_web_page_preview': 'true'}
    # Tombol aksi — bridge: poller & handler masih proses terpisah (nanti digabung di deployment).
    _a = _re.search(r'email baru</b>[^\n]*?([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+)', text) \
        or _re.search(r'([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})', text)
    _u = _re.search(r'uid\s*:\s*(\d+)', text)
    if _a and _u:
        _acct, _uid = _a.group(1), _u.group(1)
        p['reply_markup'] = json.dumps({'inline_keyboard': [
            [{'text': '👁 Lihat', 'callback_data': f'look:{_acct}:{_uid}'},
             {'text': '✍️ Balas', 'callback_data': f'reply:{_acct}:{_uid}'}],
            [{'text': '📁 Arsip', 'callback_data': f'arch:{_acct}:{_uid}'},
             {'text': '✅ Baca', 'callback_data': f'seen:{_acct}:{_uid}'},
             {'text': '🔇 Bisukan', 'callback_data': f'mute:{_acct}:{_uid}'}]]})
    if C.TG_THREAD:
        p['message_thread_id'] = C.TG_THREAD
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{C.TG_TOKEN}/sendMessage",
        data=urllib.parse.urlencode(p).encode())
    with urllib.request.urlopen(req, timeout=30) as f:
        return json.loads(f.read().decode())


def load():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}


def save(st):
    """Tulis atomik (temp + os.replace) supaya pembaca lain tidak pernah dapat file separuh."""
    import os as _os
    try:
        _tmp = STATE + '.tmp'
        with open(_tmp, 'w') as f:
            json.dump(st, f)
            f.flush()
            _os.fsync(f.fileno())
        _os.replace(_tmp, STATE)
    except Exception:
        pass


def check(tag, label, send=True, folder='INBOX', unread=''):
    M = C.imap(tag, folder, readonly=True)
    addr = label.split(' · ')[0]          # alamat akun (label bisa dapat sufiks folder)
    uidv = M.status(folder, 'UIDVALIDITY')[1][0].decode().split()[-1].strip(')')
    if folder.upper() != 'INBOX':
        label = f'{label} · {folder}'
    typ, data = M.uid('SEARCH', None, 'ALL')
    ids = data[0].split() if data and data[0] else []
    st = load()
    key = f'{tag}:{folder}:{uidv}'
    if not ids:
        M.logout()
        return 0, 0
    if st.get(key, {}).get('last') is None:      # baseline pertama: tandai, jangan spam
        st[key] = {'seen': [i.decode() for i in ids[-400:]], 'last': ids[-1].decode()}
        save(st)
        M.logout()
        return 0, len(ids)
    _last = int(st.get(key, {}).get('last') or 0)   # watermark: kirim hanya uid yang lebih besar
    n = 0
    st[key] = {'seen': [x.decode() for x in ids[-400:]], 'last': ids[-1].decode()}
    save(st)
    for i in [x for x in ids if int(x) > _last]:
        typ, d = M.uid('FETCH', i, '(FLAGS BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE MESSAGE-ID)])')
        raw = b''.join(p[1] for p in d if isinstance(p, tuple))
        # FLAGS ada di PREFIX tuple respons (bukan di bagian non-literal) -> status awal kartu
        meta = b''.join((x[0] if isinstance(x, tuple) else x) for x in d)
        sudah = (BACKSLASH + b'Seen') in meta
        m = email.message_from_bytes(raw)
        # Gmail menaruh email yang sama di beberapa folder (INBOX, [Gmail]/Penting, Berbintang)
        # dengan UID berbeda per folder -> tanpa penjaga ini notifikasi bisa dobel.
        _mid = (m.get('Message-ID') or '').strip()
        _sudah = st.setdefault('_seen_msgid', [])
        if _mid and _mid in _sudah:
            print(f'  lewati (sudah pernah dikirim): {_mid[:44]}')
            continue
        if _mid:
            _sudah.append(_mid)
            st['_seen_msgid'] = _sudah[-C.MAX_MSGID_MEMORY:]
        if send:
            _baris = [
                f'📥 <b>email baru</b> · {E(label)}',
                f'    status : {"✅ sudah dibaca" if sudah else "🔵 belum dibaca"}',
                f'    dari : {E(sname(m.get("From")))}',
                f'    subj : {E(dec(m.get("Subject")) or "(tanpa subjek)")}',
                f'    tgl  : {E(wib(m.get("Date")))}']
            if unread:
                _baris.append(E(unread))
            _baris.append(f'    uid  : {E(i.decode())} · {len(ids)} pesan di {E(folder)}')
            tg('\n'.join(_baris))
            # Simpan kepala email di state supaya handler (tombol Lihat/Balas) bisa
            # menampilkan detail email tanpa fetch IMAP lagi.
            try:
                _hd = st.setdefault('head', {})
                _hd[f'{addr}:{i.decode()}'] = {
                    'from': sname(m.get('From')),
                    'subj': dec(m.get('Subject')) or '(tanpa subjek)',
                    'tgl': wib(m.get('Date')), 'folder': folder,
                    'ts': int(time.time())}
                if len(_hd) > C.MAX_HEAD_CACHE:
                    for _k in sorted(_hd, key=lambda k: _hd[k].get('ts', 0))[:len(_hd) - C.MAX_HEAD_CACHE]:
                        _hd.pop(_k, None)
            except Exception:
                pass
            time.sleep(0.6)
        n += 1
    st[key] = {'seen': [i.decode() for i in ids[-400:]], 'last': ids[-1].decode()}
    save(st)
    M.logout()
    return n, len(ids)


def testmail():
    tag, label = ACCTS[1] if len(ACCTS) > 1 else ACCTS[0]
    user = C.A[tag]['user']
    msg = MIMEText('Email uji otomatis dari Fase B mailbot. Kalau preview-nya muncul di chat, '
                   'berarti jalur email -> IMAP -> Telegram nyambung.', 'plain')
    msg['Subject'] = f'[UJI FASE B] {jam()} WIB'
    msg['From'] = user
    msg['To'] = user
    msg['Date'] = formatdate(localtime=True)
    msg['Message-ID'] = make_msgid()
    s = C.smtp(tag)
    s.send_message(msg)
    s.quit()
    print('email uji terkirim ke', user)


if __name__ == '__main__':
    if '--test' in sys.argv:
        testmail()
    elif '--once' in sys.argv:
        for t, l in ACCTS:
            try:
                _Mx = C.imap(t)
                _F = folders_of(_Mx)
                _U = unread_line(*unread_of(_Mx, _F))
                _Mx.logout()
                for _f in _F:
                    n, tot = check(t, l, folder=_f, unread=_U)
                print(f'{l}: baru {n} | total {tot} | {_U.strip()}')
            except Exception as e:
                print(f'{l}: GAGAL {type(e).__name__}: {str(e)[:90]}')
    else:
        print('poller mulai (interval %d detik)' % C.POLL_INTERVAL)
        while True:
            _FOLDERS, _UNREAD = {}, {}
            for _t, _l in ACCTS:
                try:
                    _Mx = C.imap(_t)
                    _FOLDERS[_t] = folders_of(_Mx)
                    _UNREAD[_t] = unread_line(*unread_of(_Mx, _FOLDERS[_t]))
                    _Mx.logout()
                    print('  folder', _l, ':', len(_FOLDERS[_t]), '|', _UNREAD[_t].strip() or 'belum dibaca: ?')
                except Exception as e:
                    print('  folder err', _t, type(e).__name__)
                    _FOLDERS[_t] = ['INBOX']
                    _UNREAD[_t] = ''
            for t, l in ACCTS:
                try:
                    _n = 0
                    for _f in _FOLDERS[t]:
                        n, tot = check(t, l, folder=_f, unread=_UNREAD[t])
                        _n += n          # n cuma dari folder TERAKHIR -> jumlahkan semua
                    if _n:
                        print(jam(), l, 'baru', _n)
                except Exception as e:
                    print('err', l, type(e).__name__, str(e)[:80])
            # heartbeat: dipakai healthcheck container & watchdog luar
            try:
                with open(C.path('.heartbeat'), 'w') as _fh:
                    _fh.write(str(int(time.time())))
            except Exception:
                pass
            time.sleep(C.POLL_INTERVAL)