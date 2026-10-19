"""Status penting/dibaca dari hub Ayn — satu permintaan per kartu.

Status tinggal di tabel `mail.message_status` milik Ayn, bukan di MailArchiver.
Kartu membaca status ini saat dikirim supaya field "status" selalu ada, bukan
baru muncul setelah tombol ditekan.
"""
import json
import urllib.request

import config as C


def baca(arsip_id, timeout=3):
    """{'penting': bool, 'dibaca': bool} atau None kalau hub tidak menjawab."""
    try:
        req = urllib.request.Request(
            C.AYN_API_URL + '/api/v1/mail/messages/%s' % arsip_id,
            headers={'Authorization': 'Bearer ' + C.AYN_API_TOKEN})
        with urllib.request.urlopen(req, timeout=timeout) as f:
            d = json.loads(f.read().decode())
        m = d.get('message') or {}
        return {'penting': bool(m.get('important')), 'dibaca': bool(m.get('read_at'))}
    except Exception:
        return None
