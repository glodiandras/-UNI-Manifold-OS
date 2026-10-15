#!/usr/bin/env bash
# Manifold.app fordítása (csak swiftc + codesign kell, Xcode nem). A kimenet: {os}/Manifold.app, alapból ad-hoc aláírással.
# Az app a repo része, hogy a futtatáshoz ne kelljen fordítás.
#
# Aláírás (C34): a MOS_ALAIRAS_IDENTITAS környezeti változó egy helyi kódaláíró tanúsítvány NEVE (a kulcskarikában), pl.
#   MOS_ALAIRAS_IDENTITAS="Manifold Helyi Alairas" bash shell/build.sh
# Változó nélkül ad-hoc (`-`) az aláírás: minden újrafordítás új kódazonosság, ezért a macOS a Naptár, az Emlékeztetők és az
# eltávolítható kötet engedélyét újra kéri. A stabil aláírással az engedély az újrafordítás után is megmarad.
# A tanúsítvány létrehozásának lépései: docs/KIADAS.md „Stabil aláírás”.
set -euo pipefail
MODUL="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MOS_HOME="$(cd -P "$MODUL/.." && pwd)"
EPIT="$MOS_HOME/var/tmp/shell-build"
APP="$EPIT/Manifold.app"
CEL="$MOS_HOME/Manifold.app"
export TMPDIR="$MOS_HOME/var/tmp" CLANG_MODULE_CACHE_PATH="$MOS_HOME/var/cache/clang" SWIFT_MODULECACHE_PATH="$MOS_HOME/var/cache/clang"
mkdir -p "$TMPDIR" "$CLANG_MODULE_CACHE_PATH"
IDENTITAS="${MOS_ALAIRAS_IDENTITAS:--}"
ALAIRAS_KAPCSOLOK=()
if [ "$IDENTITAS" != "-" ]; then
  security find-identity -p codesigning 2>/dev/null | grep -qF "\"$IDENTITAS\"" || {
    echo "HIBA: nincs \"$IDENTITAS\" nevű kódaláíró tanúsítvány a kulcskarikában (security find-identity -p codesigning); lépései: docs/KIADAS.md" >&2
    exit 1
  }
  ALAIRAS_KAPCSOLOK=(--timestamp=none)     # önaláírt tanúsítványnál nincs időbélyeg-kiszolgáló: hálózat nélkül is aláírjon (D3)
fi
rm -rf "$EPIT"; mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
xcrun --find swiftc >/dev/null 2>&1 || { echo "HIBA: nincs swiftc (Command Line Tools)" >&2; exit 1; }
"$MOS_HOME/bin/mos" epites --swift > "$EPIT/EpitesAzonosito.swift"
xcrun swiftc -O -swift-version 5 -parse-as-library -target "arm64-apple-macos13.0" \
  -module-cache-path "$CLANG_MODULE_CACHE_PATH" -o "$APP/Contents/MacOS/Manifold" "$MODUL"/Sources/*.swift "$EPIT/EpitesAzonosito.swift"
cp "$MODUL/Info.plist" "$APP/Contents/Info.plist"
# Az app-ikon (C37): a verziókövetett AppIcon.icns másolata — a generálás (shell/ikon/keszit.sh) külön, kézi lépés, így a
# build nem függ a raszterezéstől. Hiányzó ikon nem némán marad el.
[ -f "$MODUL/ikon/AppIcon.icns" ] || { echo "HIBA: nincs shell/ikon/AppIcon.icns (bash shell/ikon/keszit.sh)" >&2; exit 1; }
cp "$MODUL/ikon/AppIcon.icns" "$APP/Contents/Resources/AppIcon.icns"
"$MOS_HOME/bin/mos" epites > "$APP/Contents/Resources/epites.json"
codesign --force --deep --sign "$IDENTITAS" ${ALAIRAS_KAPCSOLOK[@]+"${ALAIRAS_KAPCSOLOK[@]}"} "$APP"
codesign --verify --deep --strict "$APP"
if [ "$IDENTITAS" = "-" ]; then
  echo "aláírás: ad-hoc (az engedélyeket a macOS minden újrafordítás után újra kéri; stabil aláírás: MOS_ALAIRAS_IDENTITAS, docs/KIADAS.md)"
else
  echo "aláírás: $IDENTITAS (stabil kódazonosság)"
fi
rm -rf "$CEL"; mv "$APP" "$CEL"; rm -rf "$EPIT"
echo "kész: $CEL"
