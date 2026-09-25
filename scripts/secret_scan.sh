#!/usr/bin/env sh
# Penjaga rahasia — jalankan SEBELUM commit/push:
#     sh scripts/secret_scan.sh
#
# Keluar dengan kode 1 kalau ada temuan. Ini jaring pengaman, BUKAN jaminan:
# tetap periksa sendiri setiap kali mengubah .env atau menambah file baru.
set -u

gagal=0
lapor() { printf '  x %s\n' "$1"; gagal=1; }

# Alamat/kata yang tidak boleh muncul di repo publik. Tambahkan punya sendiri:
#   SCAN_KATA="namaorang@example.com,namadomain" sh scripts/secret_scan.sh
extra="${SCAN_KATA:-}"

if git rev-parse --git-dir >/dev/null 2>&1; then
  daftar=$(git ls-files)
  mode="git"
else
  daftar=$(find . -type f -not -path './.git/*')
  mode="cari file"
fi

# samakan bentuk path: `find .` menghasilkan "./nama", `git ls-files` tidak
daftar=$(printf '%s\n' $daftar | sed 's|^\./||')

echo "[1/3] file yang tidak boleh ikut repo ($mode)"
for f in $daftar; do
  case "$f" in
    .env|.env.*|*/state*.json|state*.json|*/unsub.json|unsub.json|*.log|backup/*|data/*|view/*|__pycache__/*|*.pyc)
      [ "$f" = ".env.example" ] && continue
      lapor "file runtime/rahasia ikut terdaftar: $f" ;;
  esac
done

echo "[2/3] pola kredensial"
pola='BEGIN [A-Z ]*PRIVATE KEY|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|[0-9]{6,10}:[A-Za-z0-9_-]{30,}'
for f in $daftar; do
  case "$f" in
    scripts/secret_scan.sh|*.md|LICENSE) continue ;;   # contoh/placeholder, bukan rahasia
  esac
  [ -f "$f" ] || continue
  if grep -nEI "$pola" "$f" >/dev/null 2>&1; then
    lapor "pola kredensial di $f:"
    grep -nEI "$pola" "$f" | sed 's/^/      /'
  fi
done

echo "[3/3] rahasia milik sendiri (email/domain/ip internal)"
umum='@(gmail|zoho|yahoo|outlook)\.[a-z]+|(^|[^0-9])(10|192\.168|172\.(1[6-9]|2[0-9]|3[01]))\.[0-9]'
for f in $daftar; do
  case "$f" in
    scripts/secret_scan.sh|*.md|.env.example|LICENSE) continue ;;
  esac
  [ -f "$f" ] || continue
  if grep -nEI "$umum" "$f" >/dev/null 2>&1; then
    lapor "email/ip internal di $f (pastikan cuma contoh):"
    grep -nEI "$umum" "$f" | sed 's/^/      /'
  fi
done

if [ -n "$extra" ]; then
  echo "[+] kata tambahan: $extra"
  old_ifs=$IFS; IFS=,
  for k in $extra; do
    IFS=$old_ifs
    [ -n "$k" ] || continue
    for f in $daftar; do
      [ -f "$f" ] || continue
      if grep -nIF "$k" "$f" >/dev/null 2>&1; then
        lapor "kata terlarang '$k' di $f"
      fi
    done
  done
  IFS=$old_ifs
fi

echo
if [ "$gagal" -eq 0 ]; then
  echo "BERSIH: tidak ada temuan."
else
  echo "ADA TEMUAN: perbaiki dulu sebelum commit/push."
fi
exit "$gagal"
