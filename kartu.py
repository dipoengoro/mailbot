"""Tombol dan teks kartu email — satu sumber bentuk.

Semua pengirim kartu (notifier arsip, OTP arsip, poller cadangan) memakai
`teks()` di sini supaya urutan baris dan labelnya tidak pernah berbeda. Dulu tiap
berkas menyusun barisnya sendiri, dan hasilnya kartu OTP tanpa tombol serta kartu
poller dengan label berbeda.

Tombol aksi memakai id arsip (`alook`, `areply`, `astar`, `aread`). Handler yang
menerjemahkannya ke akun/uid atau ke status Ayn.
"""

import config as C


def kb(arsip_id, penting=False, dibaca=False):
    """Papan tombol satu kartu email.

    `penting` dan `dibaca` hanya mengubah label, supaya setelah ditekan kartunya
    langsung terlihat berubah tanpa perlu dikirim ulang.
    """
    return {'inline_keyboard': [
        [{'text': '👁 Lihat', 'callback_data': 'alook:%s' % arsip_id},
         {'text': '✍️ Balas', 'callback_data': 'areply:%s' % arsip_id}],
        [{'text': '★ Penting' if penting else '☆ Penting',
          'callback_data': 'astar:%s' % arsip_id},
         {'text': '✅ Dibaca' if dibaca else '☑️ Dibaca',
          'callback_data': 'aread:%s' % arsip_id}],
    ]}


def label_status(penting=False, dibaca=False):
    """Satu baris status yang selalu ada di kartu."""
    return '%s · %s' % ('★ penting' if penting else '☆ biasa',
                        '✅ sudah dibaca' if dibaca else '🔵 belum dibaca')


def teks(judul, akun, dari, subj, tgl, folder=None, lag_s=None,
         kode=None, status=None, ekor=None, catatan=None):
    """Susun isi kartu dengan urutan baris yang tetap.

    Urutannya: judul, kode (kalau ada), dari, subjek, tanggal, folder, lag,
    lalu satu baris penutup — `arsip : id ...` untuk jalur arsip, `uid : ...`
    untuk jalur cadangan poller.
    """
    baris = ['%s · %s' % (judul, C.E(akun or '?'))]
    if kode:
        baris.append('    🔑 kode : <code>%s</code>' % C.E(kode))
    baris += ['    dari : %s' % C.E(dari or '?'),
              '    subj : %s' % C.E(subj or '(tanpa subjek)'),
              '    tgl  : %s' % C.E(tgl or '?')]
    if folder:
        baris.append('    folder : %s' % C.E(folder))
    if lag_s:
        baris.append('    lag  : %s (masuk arsip → terlihat)' % lag_s)
    if status:
        baris.append('    status : %s' % status)
    if catatan:
        baris.append('    %s' % catatan)
    if ekor:
        baris.append('    %s' % ekor)
    return '\n'.join(baris)
