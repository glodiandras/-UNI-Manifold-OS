"""A C++ eszközlánc egyszeri telepítése (C36a; D3): az LLVM letöltése és a macOS SDK másolata.

**Hálózati lépés csak a `llvm(igen=True)`**, és az is csak a `config/cpp-pins.env`-ben rögzített URL-ről, a rögzített méret
és sha256 ellenőrzésével: eltérésnél a telepítő leáll, és nem csomagol ki. A kicsomagolás a Python beépített zstd-jével
(`tarfile`, `filter="data"`: a kifelé mutató elem és link elutasítva), külön mappába, majd atomi átnevezéssel; a meglévő
eszközláncot nem bántja (újratelepítésnél `.regi` néven félreteszi, nem törli). Az SDK nem letöltés: a gépen lévő SDK
egyszeri másolata.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Callable

ITT = Path(__file__).resolve().parent
PINEK = ITT.parent.parent / "config" / "cpp-pins.env"
KOTELEZO_PINEK = ("LLVM_VERSION", "LLVM_URL", "LLVM_ARCHIVE", "LLVM_BYTES", "LLVM_SHA256")
MIN_SZABAD_BAJT = 12 * 2 ** 30                   # a kicsomagolt LLVM becsült 3–5 GB, az archívum 0,9 GB; bő tartalék
CSOMAG_GYOKER_NEVEK = {"bin", "lib", "include", "share", "libexec", "etc"}   # az LLVM telepítési fa saját mappái
ZSTD_ABLAK_MAX = 31                              # a dekódolható ablak log2-je: az LLVM csomagja 2^30 (1 GiB) ablakot használ,
                                                 # a Python alapértéke 2^27; a dekódolás ennyi memóriát kérhet (lusta)


class TelepitesHiba(RuntimeError):
    pass


def pinek_beolvas(ut: Path = PINEK) -> dict[str, str]:
    try:
        szoveg = Path(ut).read_text(encoding="utf-8")
    except OSError as exc:
        raise TelepitesHiba(f"a pinfájl nem olvasható: {ut}: {exc}") from exc
    p: dict[str, str] = {}
    for sor in szoveg.splitlines():
        sor = sor.strip()
        if sor and not sor.startswith("#") and "=" in sor:
            k, _, v = sor.partition("=")
            p[k.strip()] = v.strip()
    hianyzik = [k for k in KOTELEZO_PINEK if not p.get(k)]
    if hianyzik:
        raise TelepitesHiba(f"a pinfájlból hiányzik: {', '.join(hianyzik)} ({ut})")
    return p


def _curl(url: str, cel: Path) -> None:
    """Folytatható letöltés `curl`-lel (a macOS része); a `cel` egy `.part` fájl, a megszakadt letöltés onnan folytatódik."""
    ki = subprocess.run(["curl", "-fL", "--retry", "3", "-C", "-", "-#", "-o", str(cel), url])
    if ki.returncode != 0:
        raise TelepitesHiba(f"a letöltés nem sikerült (curl {ki.returncode}): {url}")


def _sha256(ut: Path) -> str:
    h = hashlib.sha256()
    with open(ut, "rb") as f:
        for blokk in iter(lambda: f.read(1 << 20), b""):
            h.update(blokk)
    return h.hexdigest()


ISMERETLEN_CEL = "arm64e.x1"                    # a macOS 27 SDK .tbd célja, amelyet az LLVM 23.1.2 ld64.lld-je nem ismer
_CEL_LISTA = re.compile(r"(targets:\s*)\[([^\]]*)\]")


def _celok_igazitasa(szoveg: str) -> str:
    def csere(m: re.Match) -> str:
        elemek = [x.strip() for x in m.group(2).split(",") if x.strip()]
        marad = [x for x in elemek if not x.startswith(ISMERETLEN_CEL)]
        if marad == elemek or not marad:
            return m.group(0)
        return f"{m.group(1)}[ {', '.join(marad)} ]"
    return _CEL_LISTA.sub(csere, szoveg)


def tbd_igazit(sdk: Path) -> dict:
    """Az SDK-másolat `.tbd` fájljaiból kiveszi a linkernek ismeretlen `arm64e.x1-*` célokat (csak az arm64-et linkeljük, a
    többi cél és a szimbólumok változatlanok). Idempotens; fájlonként atomi csere. → `{tbd, modositott}`.
    Ok: az LLVM 23.1.2 `ld64.lld` „unknown target arm64e.x1-macos” hibával nem tölti be a `libSystem.tbd`-t (a valódi
    fordításon derült ki, C36a); az SDK-másolat a miénk, a forrás SDK érintetlen."""
    db = modosult = 0
    for ut in Path(sdk).rglob("*.tbd"):
        if not ut.is_file() or ut.is_symlink():
            continue
        db += 1
        try:
            szoveg = ut.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if ISMERETLEN_CEL not in szoveg:
            continue
        uj = _celok_igazitasa(szoveg)
        if uj == szoveg:
            continue
        tmp = ut.with_name(ut.name + ".tmp")
        tmp.write_text(uj, encoding="utf-8")
        os.replace(tmp, ut)
        modosult += 1
    return {"tbd": db, "modositott": modosult}


def _xcrun_sdk() -> Path | None:
    """Az aktuális SDK a gépen (`xcrun --show-sdk-path`); csak a telepítő hívja."""
    try:
        ki = subprocess.run(["xcrun", "--show-sdk-path"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    ut = ki.stdout.strip()
    return Path(os.path.realpath(ut)) if ki.returncode == 0 and ut else None


def _kozos_gyoker(nevek: list[str]) -> str | None:
    """Az archívum egyetlen közös gyökérmappája, ha van és nem az LLVM telepítési fa saját mappája (`bin`, `lib`, …)."""
    elsok = {n.split("/", 1)[0] for n in nevek if n not in ("", ".")}
    if len(elsok) != 1:
        return None
    gyoker = next(iter(elsok))
    return None if gyoker in CSOMAG_GYOKER_NEVEK else gyoker


class Telepito:
    def __init__(self, cfg, *, letolto: Callable[[str, Path], None] | None = _curl, pinek: dict[str, str] | None = None,
                 sdk_forras: Callable[[], Path | None] = _xcrun_sdk, kiir: Callable[[str], None] | None = None):
        self.cfg = cfg
        self.letolto = letolto
        self.pinek = pinek if pinek is not None else pinek_beolvas()
        self.sdk_forras = sdk_forras
        self.kiir = kiir or (lambda _s: None)
        self.runtime = cfg.path("runtime")
        self.llvm_cel = cfg.path("llvm")
        self.sdk_cel = cfg.path("sdk")

    # ------------------------------------------------------------------ lista

    def lista(self) -> str:
        """A letöltési és másolási lista (név, méret, hash, cél). Hálózatot nem használ, programot nem futtat."""
        p = self.pinek
        meret = int(p["LLVM_BYTES"])
        return "\n".join([
            "C++ eszközlánc: letöltési és másolási lista (csak kifejezett igen után; bin/mos cpp telepit --igen)",
            f" 1. LLVM {p['LLVM_VERSION']} (macOS ARM64): {p['LLVM_ARCHIVE']}",
            f"    forrás : {p['LLVM_URL']}",
            f"    méret  : {meret:,} bájt ({meret / 2 ** 20:.1f} MiB)".replace(",", " "),
            f"    sha256 : {p['LLVM_SHA256']}",
            f"    cél    : {self.runtime / 'dl' / p['LLVM_ARCHIVE']}, kicsomagolva: {self.llvm_cel} (becsült 3–5 GB)",
            " 2. macOS SDK: egyszeri másolat a gépről (nem letöltés; a forrás a `xcrun --show-sdk-path`, a másoláskor oldódik fel)",
            f"    cél    : {self.sdk_cel}",
        ])

    # ------------------------------------------------------------------ LLVM

    def llvm(self, igen: bool, ujra: bool = False) -> dict:
        p = self.pinek
        cel = self.llvm_cel
        if cel.exists() and not ujra:
            return {"allapot": "mar_megvan", "cel": str(cel), "verzio": p["LLVM_VERSION"]}
        if not igen:
            return {"allapot": "nincs_igen", "cel": str(cel), "verzio": p["LLVM_VERSION"]}
        if self.letolto is None:
            raise TelepitesHiba("nincs letöltő")
        self.runtime.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(self.runtime).free < MIN_SZABAD_BAJT:
            raise TelepitesHiba(f"kevés a szabad hely a {self.runtime} kötetén (legalább {MIN_SZABAD_BAJT >> 30} GB kell)")
        archivum = self._archivum()
        self._kicsomagol(archivum, cel, ujra)
        return {"allapot": "telepitve", "cel": str(cel), "verzio": p["LLVM_VERSION"], "archivum": str(archivum)}

    def _ellenoriz(self, ut: Path) -> str | None:
        """None, ha a fájl a rögzített méretű és hash-ű; különben a hiba szövege."""
        p = self.pinek
        if ut.stat().st_size != int(p["LLVM_BYTES"]):
            return f"a méret eltér ({ut.stat().st_size} a rögzített {p['LLVM_BYTES']} helyett)"
        if _sha256(ut) != p["LLVM_SHA256"]:
            return f"a sha256 eltér (a rögzített: {p['LLVM_SHA256']})"
        return None

    def _archivum(self) -> Path:
        p = self.pinek
        dl = self.runtime / "dl"
        dl.mkdir(parents=True, exist_ok=True)
        archivum = dl / p["LLVM_ARCHIVE"]
        if archivum.exists():
            if self._ellenoriz(archivum) is None:
                self.kiir(f"a letöltött archívum megvan és egyezik: {archivum}")
                return archivum
            self.kiir(f"a meglévő archívum hibás, újratöltés: {archivum}")
            archivum.unlink()
        resz = dl / (p["LLVM_ARCHIVE"] + ".part")
        self.kiir(f"letöltés: {p['LLVM_URL']}")
        self.letolto(p["LLVM_URL"], resz)
        if not resz.exists():
            raise TelepitesHiba("a letöltés nem hozott létre fájlt")
        os.replace(resz, archivum)
        hiba = self._ellenoriz(archivum)
        if hiba:
            archivum.unlink()
            raise TelepitesHiba(f"{p['LLVM_ARCHIVE']}: {hiba}; az archívumot nem használom, nem csomagolok ki semmit")
        return archivum

    def _kicsomagol(self, archivum: Path, cel: Path, ujra: bool) -> None:
        tmp = cel.parent / (cel.name + ".tmp")
        regi = cel.parent / (cel.name + ".regi")
        if ujra and cel.exists() and regi.exists():
            raise TelepitesHiba(f"már van félretett régi eszközlánc ({regi}): archiváld vagy töröld, majd futtasd újra")
        if tmp.exists():
            shutil.rmtree(tmp)                        # egy korábbi, megszakadt kicsomagolás maradéka (saját ideiglenes mappa)
        tmp.mkdir(parents=True)
        try:
            self._kicsomagol_tarba(archivum, tmp)
            if not (tmp / "bin" / "clang++").exists():
                raise TelepitesHiba("a kicsomagolt csomagban nincs bin/clang++: nem LLVM-telepítési fa")
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
        if cel.exists():
            os.rename(cel, regi)                      # az ujra=True ágon (a mar_megvan már visszatért)
        try:
            os.rename(tmp, cel)
        except OSError:
            if regi.exists() and not cel.exists():
                os.rename(regi, cel)
            raise

    def _kicsomagol_tarba(self, archivum: Path, tmp: Path) -> None:
        self.kiir(f"kicsomagolás: {archivum} → {tmp}")
        try:
            from compression.zstd import DecompressionParameter
            with tarfile.open(archivum, "r:zst", options={DecompressionParameter.window_log_max: ZSTD_ABLAK_MAX}) as t:
                tagok = t.getmembers()
                gyoker = _kozos_gyoker([m.name.removeprefix("./") for m in tagok])
                lista = []
                for m in tagok:
                    nev = m.name.removeprefix("./")
                    if gyoker:
                        if nev == gyoker:
                            continue
                        nev = nev.removeprefix(gyoker + "/")
                        if m.islnk():
                            m.linkname = m.linkname.removeprefix("./").removeprefix(gyoker + "/")
                    if nev in ("", "."):
                        continue
                    m.name = nev
                    lista.append(m)
                t.extractall(tmp, members=lista, filter="data")
        except (tarfile.TarError, OSError, EOFError, ValueError) as exc:
            raise TelepitesHiba(f"a kicsomagolás nem sikerült: {type(exc).__name__}: {exc}") from exc

    # ------------------------------------------------------------------ SDK

    def sdk(self, ujra: bool = False) -> dict:
        from .eszkoztar import Eszkoztar
        cel = self.sdk_cel
        if cel.exists() and not ujra:
            return {"allapot": "mar_megvan", "cel": str(cel), "verzio": Eszkoztar(self.cfg).sdk_verzio()}
        forras = self.sdk_forras()
        if forras is None:
            raise TelepitesHiba("nincs SDK a gépen (xcode-select --install)")
        forras = Path(os.path.realpath(forras))
        if forras == Path(os.path.realpath(cel)):
            raise TelepitesHiba(f"a forrás és a cél ugyanaz a hely: {forras}")
        if not (forras / "SDKSettings.json").is_file() or not (forras / "usr" / "include").is_dir():
            raise TelepitesHiba(f"nem érvényes macOS SDK (nincs SDKSettings.json vagy usr/include): {forras}")
        tmp = cel.parent / (cel.name + ".tmp")
        regi = cel.parent / (cel.name + ".regi")
        if ujra and cel.exists() and regi.exists():
            raise TelepitesHiba(f"már van félretett régi SDK ({regi}): archiváld vagy töröld, majd futtasd újra")
        cel.parent.mkdir(parents=True, exist_ok=True)
        if tmp.exists():
            shutil.rmtree(tmp)
        self.kiir(f"SDK másolása: {forras} → {cel}")
        try:
            shutil.copytree(forras, tmp, symlinks=True)
        except (OSError, shutil.Error) as exc:
            shutil.rmtree(tmp, ignore_errors=True)
            raise TelepitesHiba(f"az SDK másolása nem sikerült: {exc}") from exc
        self.kiir("a .tbd fájlok igazítása az LLVM linkeréhez (arm64e.x1 célok kivétele)")
        igazitas = tbd_igazit(tmp)
        if cel.exists():
            os.rename(cel, regi)
        os.rename(tmp, cel)
        return {"allapot": "telepitve", "cel": str(cel), "forras": str(forras), "verzio": Eszkoztar(self.cfg).sdk_verzio(),
                "tbd_igazitva": igazitas["modositott"]}


def main_igen_nelkul(cfg, kiir=print) -> int:
    t = Telepito(cfg, kiir=lambda s: print(s, file=sys.stderr))
    kiir(t.lista())
    kiir("\nA letöltéshez add meg: bin/mos cpp telepit --igen (az SDK-másolathoz: --sdk).")
    return 0
