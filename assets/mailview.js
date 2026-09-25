/* Tampilkan gambar remote yang diblok di halaman render mailbot.
   Gambar cuma dimuat SETELAH tombol ditekan -> tracking pixel tidak kepanggil otomatis. */
document.addEventListener('click', function (e) {
  var b = e.target.closest ? e.target.closest('#unblock') : null;
  if (!b) return;
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
});

/* Aktifkan link di body email: default mati (data-href), baru jadi <a> setelah tombol ditekan. */
document.addEventListener('click', function (e) {
  var b = e.target.closest ? e.target.closest('#aktiflink') : null;
  if (!b) return;
  var n = 0;
  document.querySelectorAll('.lnk[data-href]').forEach(function (sp) {
    var a = document.createElement('a');
    a.setAttribute('href', sp.getAttribute('data-href'));
    a.setAttribute('target', '_blank');
    a.setAttribute('rel', 'noopener noreferrer');
    a.innerHTML = sp.innerHTML;
    sp.parentNode.replaceChild(a, sp);
    n++;
  });
  b.textContent = '✔ link aktif (' + n + ')';
  b.disabled = true;
});

/* Link yang href-nya dicabut (data-href pada <a>): dipasang lagi saat tombol aktifkan ditekan. */
document.addEventListener('click', function (e) {
  var b = e.target.closest ? e.target.closest('#aktiflink') : null;
  if (!b) return;
  document.querySelectorAll('a[data-href]').forEach(function (a) {
    a.setAttribute('href', a.getAttribute('data-href'));
    a.setAttribute('target', '_blank');
    a.setAttribute('rel', 'noopener noreferrer');
    a.style.borderBottom = '0';
  });
});
