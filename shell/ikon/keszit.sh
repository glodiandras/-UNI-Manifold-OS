#!/usr/bin/env bash
# A Manifold app-ikon (AppIcon.icns) előállítása a design system SVG-jeiből (C37, CLAUDE.md 25. döntés).
# Hálózat és telepítés nélkül: a macOS saját eszközei (a Command Line Tools swiftc-je, iconutil). A kimenet,
# shell/ikon/AppIcon.icns, VERZIÓKÖVETETT: a héj build-je (shell/build.sh) csak másolja, így a build nem függ ettől a
# lépéstől. Ezt a szkriptet akkor kell futtatni, ha az SVG-k változnak:
#   bash shell/ikon/keszit.sh
# Determinisztikus: ugyanabból az SVG-ből bájtra azonos .icns jön (a szkript a végén ki is írja az sha256-ot, és a
# `bash shell/ikon/keszit.sh --ellenoriz` összeveti a verziókövetett fájllal).
# Raszterezés: a rasztero.swift (AppKit/CoreSVG, átlátszó háttérrel). A qlmanage nem használható: az SVG-t fehér
# háttérre rendereli, így a lekerekített sarkok fehérek lennének.
# Méretek: 16–32 px a manifold-ikon-kicsi.svg-ből (vastagabb gömbvonal), 64 px-től a manifold-ikon.svg-ből.
# A manifold-ikon-teli.svg (széltől szélig) és a manifold-sablon.svg (egyszínű sablonjel a menüsorhoz) a forrás része;
# a héj ma egyiket sem használja.
set -euo pipefail
MODUL="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MOS_HOME="$(cd -P "$MODUL/../.." && pwd)"
MUNKA="$MOS_HOME/var/tmp/ikon-build"
export TMPDIR="$MOS_HOME/var/tmp" CLANG_MODULE_CACHE_PATH="$MOS_HOME/var/cache/clang" SWIFT_MODULECACHE_PATH="$MOS_HOME/var/cache/clang"
mkdir -p "$TMPDIR" "$CLANG_MODULE_CACHE_PATH"
rm -rf "$MUNKA"; mkdir -p "$MUNKA/AppIcon.iconset"

xcrun --find swiftc >/dev/null 2>&1 || { echo "HIBA: nincs swiftc (Command Line Tools)" >&2; exit 1; }
xcrun --find iconutil >/dev/null 2>&1 || { echo "HIBA: nincs iconutil" >&2; exit 1; }
xcrun swiftc -O -module-cache-path "$CLANG_MODULE_CACHE_PATH" -o "$MUNKA/rasztero" "$MODUL/rasztero.swift"

# fájlnév  pixel  forrás
while read -r nev px forras; do
  "$MUNKA/rasztero" "$MODUL/$forras" "$MUNKA/AppIcon.iconset/$nev.png" "$px"
done <<'LISTA'
icon_16x16 16 manifold-ikon-kicsi.svg
icon_16x16@2x 32 manifold-ikon-kicsi.svg
icon_32x32 32 manifold-ikon-kicsi.svg
icon_32x32@2x 64 manifold-ikon.svg
icon_128x128 128 manifold-ikon.svg
icon_128x128@2x 256 manifold-ikon.svg
icon_256x256 256 manifold-ikon.svg
icon_256x256@2x 512 manifold-ikon.svg
icon_512x512 512 manifold-ikon.svg
icon_512x512@2x 1024 manifold-ikon.svg
LISTA

iconutil -c icns -o "$MUNKA/AppIcon.icns" "$MUNKA/AppIcon.iconset"
UJ="$(shasum -a 256 "$MUNKA/AppIcon.icns" | cut -d' ' -f1)"

if [ "${1:-}" = "--ellenoriz" ]; then
  REGI="$(shasum -a 256 "$MODUL/AppIcon.icns" | cut -d' ' -f1)"
  if [ "$UJ" = "$REGI" ]; then echo "RENDBEN: az AppIcon.icns a forrásból reprodukálható ($UJ)"; exit 0; fi
  echo "ELTÉRÉS: az AppIcon.icns nem egyezik a forrásból készülttel ($REGI ≠ $UJ)" >&2; exit 1
fi

cp "$MUNKA/AppIcon.icns" "$MODUL/AppIcon.icns"
rm -rf "$MUNKA"
echo "kész: $MODUL/AppIcon.icns (sha256 $UJ)"
