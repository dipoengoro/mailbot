"""Tombol kartu email — dipakai notifier dan handler supaya bentuknya sama.

Tombol aksi memakai id arsip (`alook`, `areply`, `astar`, `aread`). Handler yang
menerjemahkannya ke akun/uid atau ke status Ayn.
"""


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
