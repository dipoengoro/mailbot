#!/usr/bin/env python3
"""Renderer: ambil satu email via IMAP -> tulis satu file HTML yang aman dibuka di browser.

Isi email dibungkus CSP `default-src 'none'`: gambar remote & script tidak jalan otomatis
(anti tracking pixel), tujuan link ditulis di sebelahnya, form dimatikan. Gambar dan link
baru aktif setelah tombol di halaman ditekan (assets/mailview.js).
Pakai: python3 render.py --acct you@example.com --uid 34 --out /srv/mailview/x.html
"""
import email
import os
import re
import sys

import config as C

def _esc(t):
    import html as _h
    return _h.escape(str(t or ''))



def _link_teks(m):
    """URL di email teks polos: sama perlakuannya seperti link HTML (label tujuan + tanda bahaya)."""
    url = m.group(0)
    href = url.replace('&amp;', '&')
    host = re.sub(r'^[a-zA-Z]+://', '', href).split('/')[0].split('?')[0][:60]
    hl = host.lower().lstrip('www.')
    cls, cat = 'tujuan', []
    try:
        _d = re.search(r'@([A-Za-z0-9.-]+)', _hdr(msg.get('From') or ''))
        dom = _d.group(1).lower().strip('.') if _d else ''
    except Exception:
        dom = ''
    if dom and dom not in hl:
        if dom.split('.')[0] and dom.split('.')[0] in hl:
            cls = 'bahaya'
            cat.append('MENYERUPAI pengirim tapi domain BEDA')
        else:
            cat.append('beda domain dari pengirim')
    if any(hl == x or hl.endswith('.' + x) for x in (
            'bit.ly', 't.co', 'tinyurl.com', 'goo.gl', 'ow.ly', 'is.gd', 'buff.ly',
            'rebrand.ly', 's.id', 'shorturl.at', 'lnkd.in')):
        cat.append('link PENDEK - tujuan tersembunyi')
        cls = 'bahaya' if cls == 'bahaya' else 'waspada'
    pesan = ' &middot; '.join(cat) if cat else 'tujuan'
    return (f'<span class="lnk" data-href="{href}">{url}</span>'
            f'<span class="{cls}"> &#10216;{host} &#8212; {pesan}&#10217;</span>')


a = sys.argv[1:]
g = lambda k, d='': (a[a.index(k) + 1] if k in a else d)
acct, uid, out = g('--acct'), g('--uid'), g('--out', os.path.join(C.VIEW_DIR, 'mailview.html'))

tag = C.EMAIL_TO_TAG.get(acct)
if not tag:
    print('akun tidak dikenal:', acct, '-> daftarnya di MAILBOT_ACCOUNTS')
    raise SystemExit(3)

M = C.imap(tag)
KANDIDAT = C.FOLDERS
folder = g('--folder', '')
cari = [folder] if folder else KANDIDAT
ketemu = ''
for _f in cari:
    try:
        if M.select(_f, readonly=True)[0] != 'OK':
            continue
        _t, _d = M.uid('SEARCH', None, f'UID {uid}')
        if _d and _d[0]:
            ketemu = _f
            break
    except Exception:
        continue
if not ketemu:
    print(f'uid {uid} tidak ketemu di folder yang dipantau: {cari}')
    raise SystemExit(2)
t, d = M.uid('FETCH', uid, '(RFC822)')
M.logout()
msg = email.message_from_bytes(d[0][1])

html = text = ''
for part in msg.walk():
    ct = part.get_content_type()
    if part.get_content_disposition() == 'attachment':
        continue
    if ct == 'text/html' and not html:
        html = part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8', 'replace')
    elif ct == 'text/plain' and not text:
        text = part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8', 'replace')

if not html:
    _teks = _esc(text or '(kosong)')
    _teks = re.sub(r'https?://[^\s<>"]+', _link_teks, _teks)
    html = '<pre style="white-space:pre-wrap;font:14px/1.5 monospace">' + _teks + '</pre>'

def _netral(m):
    """Anchor yang isinya gambar/tabel: href dicabut (jadi data-href) supaya TETAP mati,
    markup-nya dibiarkan utuh, dan tujuan ditulis di dalamnya."""
    href = (m.group(3) or m.group(4) or '').strip()
    host = re.sub(r'^[a-zA-Z]+://', '', href).split('/')[0].split('?')[0][:60]
    return (m.group(1) + ' data-href="' + href + '"' + m.group(5) +
            '<span class="tujuan"> &#10216;' + _esc(host) + ' &#8212; tujuan&#10217;</span>')


html = re.sub(r'(<a[^>]*?)\shref\s*=\s*("([^"]*)"|\'([^\']*)\')([^>]*>)', _netral, html, flags=re.I)

# Buang pembungkus dokumen email (doctype/html/head/body). Kalau tidak dibuang, tag <head>
# nyasar di tengah halaman dan isi <style> bisa tampil sebagai teks di browser.
html = re.sub(r'<!DOCTYPE[^>]*>', '', html, flags=re.I)
_mb = re.search(r'<body[^>]*>(.*?)</body>', html, flags=re.I | re.S)
if _mb:
    _mh = re.search(r'<head[^>]*>(.*?)</head>', html, flags=re.I | re.S)
    _css = ''.join(re.findall(r'<style[^>]*>.*?</style>', _mh.group(1), flags=re.I | re.S)) if _mh else ''
    html = _css + _mb.group(1)
else:
    html = re.sub(r'</?(html|head|body)[^>]*>', '', html, flags=re.I)

before = len(re.findall(r'src\s*=', html, re.I))
html = re.sub(r'<script.*?</script>', '', html, flags=re.I | re.S)
html = re.sub(r'<script[^>]*/?>', '', html, flags=re.I)
html = re.sub(r'\son\w+\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+)', '', html, flags=re.I)
def _blokir(m):
    """Ganti src/background remote dengan placeholder 1px, TAPI sekalian makan tanda kutipnya
    (kalau tidak, sisa tanda kutip bikin markup setelahnya tampil sebagai teks)."""
    asli = m.group(3) or m.group(4) or m.group(5) or ''
    if asli.startswith('data:'):
        return m.group(0)
    return (m.group(1) + '="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"'
            ' data-blocked="' + asli.replace('"', '&quot;') + '"')


html = re.sub(r'(src|background)\s*=\s*("([^"]*)"|\'([^\']*)\'|([^"\'>\s]+))', _blokir, html, flags=re.I)
html = re.sub(r'<form[^>]*>', '<div>', html, flags=re.I).replace('</form>', '</div>')
# Link di body: tetap bisa diklik (kamu yang mutusin), tapi tujuannya ditulis di sebelahnya.
def _link(m):
    href = (m.group(1) or m.group(2) or '').strip()
    isi = m.group(3) or href
    if not href or href.lower().startswith(('javascript:', 'data:', 'blob:')):
        return _esc(isi)
    host = re.sub(r'^[a-zA-Z]+://', '', href).split('/')[0].split('?')[0][:60]
    hl = host.lower().lstrip('www.')
    cls, cat = 'tujuan', []
    try:
        _d = re.search(r'@([A-Za-z0-9.-]+)', _hdr(msg.get('From') or ''))
        dom = _d.group(1).lower().strip('.') if _d else ''
    except Exception:
        dom = ''
    if dom and dom not in hl:
        inti = dom.split('.')[0]
        if inti and inti in hl:
            cls = 'bahaya'
            cat.append('MENYERUPAI pengirim tapi domain BEDA')
        else:
            cat.append('beda domain dari pengirim')
    if any(hl == x or hl.endswith('.' + x) for x in (
            'bit.ly', 't.co', 'tinyurl.com', 'goo.gl', 'ow.ly', 'is.gd', 'buff.ly',
            'rebrand.ly', 's.id', 'shorturl.at', 'lnkd.in')):
        cat.append('link PENDEK - tujuan tersembunyi')
        cls = 'bahaya' if cls == 'bahaya' else 'waspada'
    pesan = ' &middot; '.join(cat) if cat else 'tujuan'
    return (f'<span class="lnk" data-href="{href}">{_esc(isi)}</span>'
            f'<span class="{cls}"> &#10216;{host} &#8212; {pesan}&#10217;</span>')


html = re.sub(r'<a[^>]*?href\s*=\s*(?:"([^"]*)"|\'([^\']*)\')([^>]*)>([^<]*)</a>',
              lambda m: _link(type('_M', (), {'group': staticmethod(lambda i: {
                  1: m.group(1), 2: m.group(2), 3: m.group(4)}.get(i))})()),
              html, flags=re.I | re.S)
# --- lampiran: disimpan di sebelah halaman render, biar bisa diunduh ---
import os as _os
import re as _re
_hdr = C.hdr                # decoder header RFC2047 (config.py)
attrows = ''
_natt = 0
try:
    attdir = _os.path.dirname(_os.path.abspath(out))
    base = _os.path.basename(out).rsplit('.', 1)[0]
    for _p in msg.walk():
        _fn = _p.get_filename()
        if not _fn:
            continue
        _data = _p.get_payload(decode=True) or b''
        if not _data:
            continue
        _natt += 1
        _safe = _re.sub(r'[^A-Za-z0-9._-]', '_', str(_fn))[:60]
        _dst = _os.path.join(attdir, f'{base}-att{_natt}-{_safe}')
        with open(_dst, 'wb') as _f:
            _f.write(_data)
        _alink = _os.path.basename(_dst).replace('&', '&amp;').replace('@', '&#64;')
        _sz = (f'{len(_data)} byte' if len(_data) < 1024
               else (f'{len(_data)/1024:.0f} KB' if len(_data) < 1048576 else f'{len(_data)/1048576:.1f} MB'))
        _ico = '🖼' if _re.search(r'\.(png|jpe?g|gif|webp|bmp)$', _safe, _re.I) else ('📄' if _re.search(r'\.(pdf)$', _safe, _re.I) else ('📊' if _re.search(r'\.(xlsx?|csv)$', _safe, _re.I) else '📎'))
        attrows += f'  {_ico} <a href="{_alink}" download>{_alink}</a> &middot; {_sz}<br>\n'
except Exception as _e:
    print('att err', type(_e).__name__, str(_e)[:80])


def H(k):
    """Ambil header (di-decode), escape HTML, dan samarkan @ (biar Cloudflare nggak nyamarin)."""
    import html as _h
    v = _hdr(msg.get(k))
    return _h.escape(v).replace('@', '&#64;')


def W(k):
    """Tanggal header -> WIB (UTC+7)."""
    import html as _h
    from datetime import timezone, timedelta
    from email.utils import parsedate_to_datetime
    raw = str(msg.get(k) or '').strip()
    if not raw:
        return '?'
    try:
        d = parsedate_to_datetime(raw)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        w = d.astimezone(timezone(timedelta(hours=C.TZ_OFFSET)))
        return f"{w.strftime('%d %b %Y %H:%M')} {C.TZ_LABEL}"
    except Exception:
        return _h.escape(raw)


cc = msg.get('Cc') or ''
ccrow = f'  cc: {H("Cc")}<br>\n' if cc else ''
reply = msg.get('Reply-To') or ''
rrow = f'  balas-ke: {H("Reply-To")}<br>\n' if reply and reply != (msg.get('From') or '') else ''


# Estetika: label tujuan untuk link NORMAL dipindah ke satu baris daftar (biar layout email bersih).
# Link yang MENCURIGAKAN (waspada/bahaya) tetap dilabeli langsung di tempatnya.
_HOSTS_TUJUAN = []


def _rapi_label(m):
    _HOSTS_TUJUAN.append(m.group(1))
    return ''


html = re.sub(r'<span class="tujuan"> &#10216;([^&]*) &#8212; tujuan&#10217;</span>', _rapi_label, html)

# mailview.js (pembuka gambar/link) ditaruh di sebelah halaman. Disalin dari
# assets/ kalau belum ada / isinya beda -> halaman tidak butuh file lain.
try:
    _js_src = _os.path.join(C.CODE_DIR, 'assets', 'mailview.js')
    _js_dst = _os.path.join(_os.path.dirname(_os.path.abspath(out)), 'mailview.js')
    if _os.path.exists(_js_src):
        _isi = open(_js_src, 'rb').read()
        if (not _os.path.exists(_js_dst)) or open(_js_dst, 'rb').read() != _isi:
            with open(_js_dst, 'wb') as _f:
                _f.write(_isi)
except Exception as _e:
    print('mailview.js gagal disalin', type(_e).__name__)

page = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'self'; img-src data: https: http:; font-src data:;">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{H('Subject') or '(tanpa subjek)'}</title>
<style>
 *{{box-sizing:border-box}}
 body{{margin:0 !important;padding:14px !important;background:#0d1117 !important;color:#e6edf3;font:14px/1.6 -apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif}}
 html{{background:#0d1117 !important}}
 .wrap{{max-width:900px;margin:0 auto !important;background:transparent !important}}
 .card{{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:16px 18px;margin-bottom:16px !important}}
 .cap{{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#7d8fa3;margin-bottom:10px}}
 .rows{{font-size:13px;line-height:1.95;color:#c9d1d9;word-break:break-word}}
 .rows b{{color:#8b98a5;font-weight:600;display:inline-block;min-width:82px}}
 .subject{{font-size:16px;font-weight:700;color:#e6edf3;margin-bottom:12px;word-break:break-word}}
 .warn{{margin-top:12px;padding:8px 11px;background:#3a2222;border:1px solid #5c2b2b;border-radius:8px;font-size:12px;color:#f0b4b4}}
 button{{margin-top:12px;padding:9px 14px;border:0;border-radius:8px;background:#238636;color:#fff;font-size:13px;font-weight:600;cursor:pointer}}
 button:disabled{{background:#30363d;color:#8b98a5}}
 .bodycard{{background:#fff;border-radius:12px;padding:18px;color:#1f2328;overflow-x:auto}}
 .bodycard img{{opacity:.35;outline:1px dashed #c00}}
 .lnk, a[data-href]{{border-bottom:1px solid #1f6feb;text-decoration:none}}
 .bodycard a[data-href]{{border-bottom:1px solid #1f6feb}}
 .bodycard > *{{margin-left:auto !important;margin-right:auto !important;float:none !important}}
 .bodycard > table, .bodycard > div > table, .bodycard > center > table{{margin-left:auto !important;margin-right:auto !important;float:none !important}}
 .bodycard table{{max-width:100% !important;width:auto !important}}
 .bodycard img{{max-width:100% !important;height:auto !important}}
 .bodycard td, .bodycard th{{max-width:100% !important}}
 .tujuan{{font-size:11px;color:#7fa8d8}}
 .waspada{{font-size:11px;color:#e3b341}} .bahaya{{font-size:11px;color:#f85149;font-weight:600}}
</style></head><body>
<div class="wrap">

 <div class="card">
  <div class="subject">{H('Subject') or '(tanpa subjek)'}</div>
  <div class="rows">
   <b>dari</b> {H('From') or '?'}<br>
   <b>ke</b> {H('To') or '?'}<br>
{ccrow}{rrow}   <b>tanggal</b> {W('Date')}<br>
   <b>akun</b> {acct}<br>
   <b>uid</b> {uid}
{attrows}  </div>
  <div class="warn">Gambar remote diblok ({before} referensi) &middot; script email dihapus &middot; render offline</div>
  {'' if not _HOSTS_TUJUAN else '<div class="rows" style="font-size:11px;color:#7d8fa3;margin-top:6px">🔗 tujuan link: ' + ' &middot; '.join(list(dict.fromkeys(_HOSTS_TUJUAN))[:8]) + '</div>'}
  <button id="unblock" type="button">🖼 tampilkan gambar ({before})</button>
  <button id="aktiflink" type="button" style="background:#1f6feb">🔗 aktifkan link</button>
 </div>

 <div class="bodycard">{html}</div>
<style>
 html body{{padding:14px !important;margin:0 !important;background:#0d1117 !important;width:auto !important;max-width:none !important}}
 html body .wrap{{max-width:900px !important;margin:0 auto !important}}
 html body .card{{margin-bottom:16px !important}}
</style>

</div>
<script src="mailview.js"></script>
</body></html>"""

open(out, 'w').write(page)
print(f'render OK: {out} ({len(page)} byte) | {before} gambar/asset remote diblok | subjek: {str(msg.get("Subject"))[:50]}')
