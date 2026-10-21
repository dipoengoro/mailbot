#!/usr/bin/env python3
"""Feed surel untuk mailbot, dibaca dari skema `mail` milik Ayn (bukan MailArchiver).

Kenapa pindah: MailArchiver menyinkron tiap 5 menit per akun, jadi email baru
baru terlihat 2-4 menit setelah tiba di provider. Penyalin sendiri (mail-sync)
menyimpan 15-20 detik setelah email tiba, jadi feed ini memakai sumber itu.

Bentuk keluaran sama persis dengan arsip_feed.py lama (arsip_feed.json +
arsip_detail/<id>.json), supaya bot tidak perlu diubah. Bedanya `id` sekarang
`mail.message.id`, bukan Id arsip — dan itu justru cocok dengan API Ayn.

Pakai:
  arsip_feed.py                 # normal (systemd)
  arsip_feed.py --mulai-sekarang
  arsip_feed.py --status
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

TUJUAN = '/home/opsapp/apps/mailbot/arsip_feed.json'
STATE = '/root/arsip-feed/state.json'
MAKS = 400
POTONG_TEKS = 3000
DETAIL_DIR = '/home/opsapp/apps/mailbot/arsip_detail'
SIMPAN_HARI = 8


def psql(sql):
    r = subprocess.run(['docker', 'exec', '-i', 'postgres', 'psql', '-U', 'postgres',
                        '-d', 'ayn', '-tAF', '|', '-c', sql],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:300])
    return r.stdout


def muat_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}


def simpan_state(s):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(s, f)
    os.replace(tmp, STATE)


def tulis_feed(items):
    data = {
        'dibuat': int(time.time()),
        'dibuat_wib': (datetime.now(timezone.utc) + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S'),
        'items': items,
        'sumber': 'skema-mail',
    }
    tmp = TUJUAN + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f, ensure_ascii=False)
    os.chmod(tmp, 0o600)
    os.replace(tmp, TUJUAN)


def satu(kolom, batas):
    """Satu baris per email: buang \\r dan \\n supaya parser baris tidak pecah."""
    return ("replace(replace(left(%s, %d), chr(10), ' '), chr(13), ' ')" % (kolom, batas))


def tulis_detail(items):
    if not items:
        return
    ids = ','.join(str(i['id']) for i in items)
    sql = ('select row_to_json(x) from (select id, account_id, folder, message_id, subject, '
           'from_addr, to_addr, cc_addr, sent_at, internal_at, has_attachments, '
           "left(text_body, 300000) as teks, left(html_body, 300000) as html "
           'from mail.message where id in (%s)) x;' % ids)
    out = psql(sql)
    os.makedirs(DETAIL_DIR, exist_ok=True)
    n = 0
    for b in out.splitlines():
        b = b.strip()
        if not b.startswith('{'):
            continue
        d = json.loads(b)
        # Nama kunci disamakan dengan berkas detail lama supaya handler bot
        # (arsip_detail/arsip_ke_acct_uid) tidak perlu diubah.
        isi = {
            'Id': d['id'],
            'MailAccountId': d['account_id'],
            'MessageId': d['message_id'],
            'Subject': d['subject'],
            'From': d['from_addr'],
            'To': d['to_addr'],
            'Cc': d['cc_addr'],
            'FolderName': d['folder'],
            'SentDate': d['sent_at'],
            'ReceivedDate': d['internal_at'],
            'HasAttachments': d['has_attachments'],
            'teks': d['teks'],
            'html': d['html'],
            'akun': d['account_id'],
        }
        path = os.path.join(DETAIL_DIR, '%s.json' % d['id'])
        tmp = path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(isi, f, ensure_ascii=False)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        n += 1
    batas = time.time() - SIMPAN_HARI * 86400
    for nama in os.listdir(DETAIL_DIR):
        fp = os.path.join(DETAIL_DIR, nama)
        try:
            if os.path.getmtime(fp) < batas:
                os.remove(fp)
        except OSError:
            pass
    if n:
        print('detail tersimpan: %d' % n)


def pantau():
    """Mode daemon: duduk, cek id terbaru tiap 2 detik, bangun feed saat berubah.

    Pengganti loop cron 20 detik. Biayanya satu kueri `max(id)` per 2 detik —
    jauh lebih murah daripada menyusun feed penuh, dan tidak menyentuh jalur
    penarikan email sama sekali.
    """
    print('pantau: menunggu email baru (cek tiap 2 detik)', flush=True)
    terakhir = int(muat_state().get('last_id_ayn') or 0)
    while True:
        try:
            puncak = int((psql('select coalesce(max(id),0) from mail.message;') or '0').strip() or 0)
            if puncak != terakhir:
                sys.argv = [sys.argv[0]]
                main()
                terakhir = int(muat_state().get('last_id_ayn') or puncak)
        except Exception as e:
            print('pantau galat: %s' % str(e)[:160], flush=True)
            time.sleep(5)
        time.sleep(2)


def main():
    mulai_sekarang = '--mulai-sekarang' in sys.argv
    if '--status' in sys.argv:
        try:
            d = json.load(open(TUJUAN))
        except Exception as e:
            print('feed belum ada (%s)' % e)
            return 1
        print('sumber: %s | dibuat: %s WIB | item: %d'
              % (d.get('sumber', 'arsip'), d.get('dibuat_wib'), len(d.get('items') or [])))
        for i in (d.get('items') or [])[-5:]:
            print('  id=%s %s | %s | %s' % (i.get('id'), i.get('akun'), i.get('folder'),
                                            (i.get('subj') or '')[:50]))
        return 0

    st = muat_state()
    try:
        puncak = int((psql('select coalesce(max(id),0) from mail.message;') or '0').strip() or 0)
    except Exception as e:
        print('GAGAL query max id: %s' % e)
        return 2

    terakhir = int(st.get('last_id_ayn') or 0)
    if mulai_sekarang or not terakhir:
        st['last_id_ayn'] = puncak
        simpan_state(st)
        tulis_feed([])
        print('penanda disetel ke id %d; feed kosong sampai email berikutnya' % puncak)
        return 0
    if puncak < terakhir:
        # Basis data dipulihkan/direset: jangan sampai feed diam selamanya.
        print('id mundur (%d -> %d); penanda disetel ulang' % (terakhir, puncak))
        st['last_id_ayn'] = puncak
        simpan_state(st)
        return 0

    sql = ('select id, account_id, folder, %s, %s, %s, '
           'to_char(sent_at at time zone \'Asia/Jakarta\', \'YYYY-MM-DD HH24:MI:SS\'), '
           'to_char(internal_at at time zone \'UTC\', \'YYYY-MM-DD HH24:MI:SS\'), '
           'is_outgoing, %s, %s, message_id '
           'from mail.message where id > %d and not is_outgoing order by id limit %d;'
           % (satu('from_addr', 200), satu('to_addr', 200), satu('subject', 300),
              satu('text_body', POTONG_TEKS), satu('html_body', POTONG_TEKS),
              terakhir, MAKS))
    try:
        out = psql(sql)
    except Exception as e:
        print('GAGAL ambil email baru: %s' % e)
        return 2

    items = []
    for b in out.splitlines():
        p = b.split('|', 11)
        if len(p) < 12:
            continue
        items.append({
            'id': int(p[0]), 'akun': p[1], 'folder': p[2],
            'dari': p[3], 'kepada': p[4], 'subj': p[5],
            'sent': p[6], 'terima': p[7],
            'outgoing': str(p[8]).strip().lower() in ('t', 'true', '1'),
            'teks': p[9], 'html': p[10],
            'mid': p[11].strip(),
        })

    # Satu email bisa punya beberapa salinan folder (label Gmail). Ambil satu
    # saja per MessageId, dan jangan ulangi yang sudah pernah masuk feed.
    lama = []
    try:
        _d = json.load(open(TUJUAN))
        _batas = items[0]['id'] if items else 10 ** 9
        lama = [i for i in (_d.get('items') or []) if int(i.get('id', 0)) < _batas]
    except Exception:
        lama = []
    sudah = {i.get('mid') for i in lama if i.get('mid')}
    unik = []
    for i in items:
        mid = i.get('mid')
        if mid and mid in sudah:
            continue
        if mid:
            sudah.add(mid)
        unik.append(i)
    items = unik

    try:
        tulis_detail(items)
    except Exception as e:
        print('GAGAL tulis detail: %s' % type(e).__name__)

    tulis_feed((lama + items)[-400:])
    if items:
        print('email baru: %d' % len(items))
        kirim_kartu()
    # Penanda tetap maju walau tidak ada item yang layak dikartukan (mis. semua
    # baris baru adalah salinan "Terkirim"), kalau tidak baris itu dibaca ulang
    # setiap 20 detik tanpa guna.
    if puncak > terakhir:
        st['last_id_ayn'] = puncak
        simpan_state(st)

    return 0


def kirim_kartu():
    """Beri tahu pengirim kartu SEGERA setelah feed ditulis.

    Dulu kartu menunggu cron tiap menit — ada jendela tunggu yang tidak jelas
    asalnya. Sekarang penyusun feed yang mendorong: begitu ada email baru,
    notifier dijalankan. `flock -n` mencegah dua kiriman bertumpuk kalau satu
    putaran masih berjalan. Cron tetap ada sebagai jaring pengaman kalau
    dorongan ini gagal.
    """
    try:
        r = subprocess.run(
            ['flock', '-n', '/tmp/notif_mailbot.lock',
             'docker', 'exec', 'mailbot', 'python3', '/cfg/notif_arsip.py'],
            capture_output=True, text=True, timeout=180,
        )
        keluaran = (r.stdout or '').strip()
        if keluaran:
            print(keluaran[-500:])
        if r.returncode != 0:
            print('dorong kartu gagal (kode %d): %s' % (r.returncode, (r.stderr or '')[:200]))
    except Exception as e:
        print('dorong kartu gagal: %s' % type(e).__name__)


if __name__ == '__main__':
    if '--pantau' in sys.argv:
        pantau()
        sys.exit(0)
    sys.exit(main())
