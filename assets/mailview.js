/* mailview.js — pembuka gambar, link, dan "muat ke layar" di halaman hasil render mailbot.

   Kenapa begini: isi email TIDAK boleh memanggil apa pun saat halaman dibuka
   (tracking pixel, dan link yang cuma "bertanda" pengirim). Jadi semua gambar remote
   dan semua link DIAM dulu; baru aktif setelah tombolnya ditekan.

   - gambar remote: atribut data-blocked -> dipasang jadi src
   - link teks: <span class="lnk" data-href> -> diganti jadi <a href>
   - link yang href-nya dicabut: <a data-href> -> href dipasang kembali
   - #fit: email yang lebih lebar dari layar (desain 600px dkk) diperkecil pakai zoom
     supaya seluruh isi terlihat, tanpa ada yang kepotong di kanan.
   Satu pendengar untuk semua tombol supaya hitungannya akurat. */

function _muatKeLayar() {
  var kartu = document.querySelector('.bodycard');
  var tombol = document.getElementById('fit');
  if (!kartu || !tombol) return;
  var kurang = kartu.scrollWidth - kartu.clientWidth;
  if (kurang <= 4) {
    tombol.style.display = 'none';
    if (kartu.dataset.fit === '1') {
      kartu.style.zoom = '';
      kartu.dataset.fit = '0';
    }
    return;
  }
  var skala = Math.floor((kartu.clientWidth / kartu.scrollWidth) * 100) / 100;
  tombol.style.display = '';
  if (kartu.dataset.fit !== '1') {
    tombol.textContent = '🔍 muat ke layar (' + skala.toFixed(2) + '×)';
  }
}

document.addEventListener('click', function (e) {
  var t = e.target;
  var b = t && t.closest ? t.closest('#unblock') : null;
  if (b) {
    var n = 0;
    var imgs = document.querySelectorAll('.bodycard img[data-blocked], .body img[data-blocked]');
    for (var i = 0; i < imgs.length; i++) {
      var img = imgs[i];
      var src = img.getAttribute('data-blocked');
      if (src) {
        img.src = src;
        img.removeAttribute('data-blocked');
        img.style.opacity = '1';
        img.style.outline = 'none';
        n++;
      }
    }
    b.textContent = '✔ gambar ditampilkan (' + n + ')';
    b.disabled = true;
    setTimeout(_muatKeLayar, 1200);   /* lebar layout berubah setelah gambar masuk */
    return;
  }

  b = t && t.closest ? t.closest('#fit') : null;
  if (b) {
    var kartu = document.querySelector('.bodycard');
    if (!kartu) return;
    if (kartu.dataset.fit === '1') {
      kartu.style.zoom = '';
      kartu.dataset.fit = '0';
      b.textContent = '🔍 muat ke layar';
      return;
    }
    kartu.style.zoom = String(Math.floor((kartu.clientWidth / kartu.scrollWidth) * 1000) / 1000);
    kartu.dataset.fit = '1';
    b.textContent = '🔍 tampilan asli';
    return;
  }

  b = t && t.closest ? t.closest('#aktiflink') : null;
  if (!b) return;

  var jml = 0;

  // link teks yang diganti jadi <span class="lnk" data-href="...">
  document.querySelectorAll('.lnk[data-href]').forEach(function (sp) {
    var a = document.createElement('a');
    a.setAttribute('href', sp.getAttribute('data-href'));
    a.setAttribute('target', '_blank');
    a.setAttribute('rel', 'noopener noreferrer');
    a.innerHTML = sp.innerHTML;
    sp.parentNode.replaceChild(a, sp);
    jml++;
  });

  // link yang href-nya dicabut jadi data-href (markup email dibiarkan utuh)
  document.querySelectorAll('a[data-href]').forEach(function (a) {
    a.setAttribute('href', a.getAttribute('data-href'));
    a.setAttribute('target', '_blank');
    a.setAttribute('rel', 'noopener noreferrer');
    a.style.borderBottom = '0';
    jml++;
  });

  b.textContent = '✔ link aktif (' + jml + ')';
  b.disabled = true;
});

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _muatKeLayar);
} else {
  _muatKeLayar();
}
window.addEventListener('load', _muatKeLayar);
