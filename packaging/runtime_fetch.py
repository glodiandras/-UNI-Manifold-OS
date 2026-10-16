"""A futtatókörnyezet letöltője (F9; a `bin/mos runtime fetch` Python-portja, D3) — EXPLICIT, ember által indított lépés.

Hálózatot csak ez a szkript használ, és csak a felhasználó/építő kifejezett jóváhagyásával (`--igen`); nélküle a tervet
írja ki és kilép. Minden letöltés:
  - a `config/runtime-pins.env` rögzített URL-jéről és sha256-jával (a pin váltása más fájlnév: régi és új nem keveredik);
  - csak HTTPS, csak az engedélyezett hosztokra (`HOSZT_ENGEDELY`), az átirányítások célja is ellenőrzött;
  - előbb `.resz` néven, hash-egyezés után a végleges néven; eltérő hash → a fájl törlődik (sérült/részleges nem marad);
  - a már meglévő, egyező hash-ű fájlt nem tölti le újra.
Kibontás (`--kibont`): a `<cel>/<komponens>` alá egy ideiglenes mappán át, a verzió ellenőrzése után cserél; a régi a
`<cel>/regi/` alá kerül (nem törlődik). A `runtime` symlinkre (pl. egy másik, csak olvasható checkout runtime-jára) nem ír:
ekkor `--cel` kell.

Komponensek: uv, python, node, ffmpeg (a wheel-ből kicsomagolt, külön hash-elt bináris), wheels (`pip download`, a lock
hash-eivel), git (forrás-tarball a hordozható git építéséhez; csak ha a pin megvan: GIT_VERSION, GIT_URL, GIT_SHA256).

`python packaging/runtime_fetch.py [--cel <runtime>] [--komponens uv,python,…] [--kibont] [--igen]`
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tarfile
import time
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from csomag_kozos import REPO, CsomagHiba, Futtato, futtat  # noqa: E402

PINEK = REPO / "config" / "runtime-pins.env"
HOSZT_ENGEDELY = frozenset({
    "github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com",   # uv, python-build-standalone
    "nodejs.org",                                                                           # Node
    "files.pythonhosted.org", "pypi.org",                                                   # ffmpeg-wheel, a wheelhouse
    "mirrors.edge.kernel.org", "www.kernel.org",                                            # git forrás
})
KOMPONENSEK = ("uv", "python", "node", "ffmpeg", "wheels", "git")
ALAP_KOMPONENSEK = ("uv", "python", "node", "ffmpeg", "wheels")
BLOKK = 1 << 20


def pinek_olvas(ut: Path = PINEK) -> dict[str, str]:
    """`KULCS=ÉRTÉK` sorok (a `#` megjegyzés, az üres sor kimarad; nincs shell-kiértékelés)."""
    ki: dict[str, str] = {}
    for s in ut.read_text(encoding="utf-8").splitlines():
        s = s.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        ki[k.strip()] = v.strip().strip('"').strip("'")
    return ki


@dataclass(frozen=True)
class Tetel:
    komponens: str
    url: str
    sha256: str
    verzio: str

    @property
    def fajlnev(self) -> str:
        nev = urllib.parse.unquote(urllib.parse.urlsplit(self.url).path.rsplit("/", 1)[-1])
        if not nev or "/" in nev or nev in (".", ".."):
            raise CsomagHiba("pin_fajlnev", f"a pin URL-jének nincs érvényes fájlneve: {self.url}")
        return nev


_PIN_KULCS = {"uv": "UV", "python": "PY", "node": "NODE", "ffmpeg": "FFMPEG", "git": "GIT"}


def tervez(pinek: dict[str, str], komponensek=ALAP_KOMPONENSEK) -> list[Tetel]:
    """A letöltendő archívumok (a `wheels` a pip dolga, nem tétel). Hiányzó pin: `CsomagHiba` a pótlás módjával."""
    ki = []
    for k in komponensek:
        if k not in KOMPONENSEK:
            raise CsomagHiba("komponens", f"ismeretlen komponens: {k} ({', '.join(KOMPONENSEK)})")
        if k == "wheels":
            continue
        e = _PIN_KULCS[k]
        hianyzo = [f"{e}_{x}" for x in ("URL", "SHA256", "VERSION") if not pinek.get(f"{e}_{x}")]
        if hianyzo:
            raise CsomagHiba("pin_hianyzik", f"a(z) {k} pinje hiányos a config/runtime-pins.env-ben: {', '.join(hianyzo)}"
                                             + (" (a git forrás-tarball pinjét a kiadást végző rögzíti: verzió, URL, "
                                                "sha256 a kernel.org-ról)" if k == "git" else ""))
        t = Tetel(k, pinek[f"{e}_URL"], pinek[f"{e}_SHA256"].lower(), pinek[f"{e}_VERSION"])
        url_ellenoriz(t.url)
        if len(t.sha256) != 64 or any(c not in "0123456789abcdef" for c in t.sha256):
            raise CsomagHiba("pin_sha", f"érvénytelen sha256 a(z) {k} pinjében")
        ki.append(t)
    return ki


def url_ellenoriz(url: str) -> None:
    u = urllib.parse.urlsplit(url)
    if u.scheme != "https":
        raise CsomagHiba("url_sema", f"csak HTTPS engedélyezett: {url}")
    if (u.hostname or "").lower() not in HOSZT_ENGEDELY:
        raise CsomagHiba("url_hoszt", f"nem engedélyezett hoszt: {u.hostname} ({url})")


class _OrzottAtiranyitas(urllib.request.HTTPRedirectHandler):
    """Az átirányítás célja is az engedélylistán legyen (és HTTPS)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        url_ellenoriz(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def alap_nyito() -> Callable:
    opener = urllib.request.build_opener(_OrzottAtiranyitas())
    return lambda url, timeout: opener.open(urllib.request.Request(url, headers={"User-Agent": "manifold-runtime-fetch"}),
                                            timeout=timeout)


def sha256_fajl(p: Path) -> str:
    with open(p, "rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def letolt(t: Tetel, dl: Path, *, nyito: Callable | None = None, naplo=print, probak: int = 3) -> Path:
    """Egy tétel letöltése a `dl/` alá (lásd a modul leírását) → a hash-egyező fájl útja."""
    url_ellenoriz(t.url)
    dl.mkdir(parents=True, exist_ok=True)
    cel = dl / t.fajlnev
    if cel.exists():
        if sha256_fajl(cel) == t.sha256:
            naplo(f"{t.komponens}: megvan ({cel.name}, sha256 egyezik)")
            return cel
        naplo(f"{t.komponens}: a meglévő {cel.name} sha256-ja eltér a pintől: törlöm, újra letöltöm")
        cel.unlink()
    resz = cel.with_name(cel.name + ".resz")
    nyito = nyito or alap_nyito()
    utolso: Exception | None = None
    for i in range(probak):
        resz.unlink(missing_ok=True)
        try:
            h = hashlib.sha256()
            with nyito(t.url, 60) as valasz, open(resz, "wb") as ki:
                vegso = getattr(valasz, "geturl", lambda: t.url)()
                url_ellenoriz(vegso)
                while True:
                    blokk = valasz.read(BLOKK)
                    if not blokk:
                        break
                    h.update(blokk)
                    ki.write(blokk)
            if h.hexdigest() != t.sha256:
                resz.unlink(missing_ok=True)
                raise CsomagHiba("sha_elter", f"SHA256 eltér: {cel.name} (a letöltött fájl törölve)")
            resz.replace(cel)
            naplo(f"{t.komponens}: letöltve ({cel.name})")
            return cel
        except CsomagHiba:
            resz.unlink(missing_ok=True)
            raise
        except OSError as e:                   # hálózati hiba: újrapróba, a részleges fájl nem marad
            resz.unlink(missing_ok=True)
            utolso = e
            time.sleep(min(2 ** i, 5) if i + 1 < probak else 0)
    raise CsomagHiba("letoltes", f"a letöltés sikertelen: {t.url} ({utolso})")


# ------------------------------------------------------------------ kibontás

def _verzio_egyezik(varhato: str, kimenet: str) -> bool:
    import re
    return re.search(r"(^|[^0-9.])" + re.escape(varhato) + r"([^0-9.]|$)", kimenet) is not None


def _verzio(parancs: list[str], futtato: Futtato) -> str:
    p = futtato(parancs, check=False)
    return (p.stdout or "") + (p.stderr or "")


def _regi_felre(rt: Path, d: Path, naplo) -> None:
    if not (d.exists() or d.is_symlink()):
        return
    cel = rt / "regi" / f"{d.name}-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
    cel.parent.mkdir(parents=True, exist_ok=True)
    d.rename(cel)
    naplo(f"a régi {d.name} félretéve: {cel}")


def kibont(t: Tetel, archiv: Path, rt: Path, *, pinek: dict[str, str], futtato: Futtato = futtat, naplo=print) -> Path:
    """Egy letöltött tétel kibontása a `rt` alá, verzió-ellenőrzéssel → a kész mappa/fájl."""
    uj = rt / f".{t.komponens}.uj"
    shutil.rmtree(uj, ignore_errors=True)
    uj.mkdir(parents=True)
    try:
        if t.komponens == "ffmpeg":
            tag = pinek.get("FFMPEG_MEMBER", "")
            bin_sha = pinek.get("FFMPEG_BIN_SHA256", "").lower()
            with zipfile.ZipFile(archiv) as z:
                (uj / "ffmpeg").write_bytes(z.read(tag))
            if sha256_fajl(uj / "ffmpeg") != bin_sha:
                raise CsomagHiba("sha_elter", "SHA256 eltér: a kicsomagolt ffmpeg")
            (uj / "ffmpeg").chmod(0o755)
            ellenorzo = [uj / "ffmpeg", "-version"]
        elif t.komponens == "git":
            with tarfile.open(archiv) as tf:
                tf.extractall(uj, filter="data")
            naplo(f"git-forrás kibontva: {uj} → építés: python packaging/hordozhato_git.py epit {archiv} {rt / 'git'}")
            shutil.rmtree(uj, ignore_errors=True)
            return archiv
        else:
            with tarfile.open(archiv) as tf:
                tagok = tf.getmembers()
                for m in tagok:                 # --strip-components=1
                    reszek = m.name.split("/", 1)
                    if len(reszek) < 2 or not reszek[1]:
                        continue
                    m.name = reszek[1]
                    if m.islnk():                # a hardlink célja is a levágott névvel
                        m.linkname = m.linkname.split("/", 1)[-1]
                    tf.extract(m, uj, filter="data")
            bin_ut = {"uv": "uv", "python": "bin/python3", "node": "bin/node"}[t.komponens]
            ellenorzo = [uj / bin_ut, "--version"]
        if not _verzio_egyezik(t.verzio, _verzio([str(x) for x in ellenorzo], futtato)):
            raise CsomagHiba("verzio_elter", f"a kibontott {t.komponens} nem a pinelt {t.verzio} ({archiv.name})")
        if t.komponens == "uv":
            for n in ("uv", "uvx"):
                _regi_felre(rt, rt / n, naplo)
                if (uj / n).exists():
                    (uj / n).rename(rt / n)
            shutil.rmtree(uj)
            return rt / "uv"
        cel = rt / t.komponens
        _regi_felre(rt, cel, naplo)
        uj.rename(cel)
        naplo(f"{t.komponens} {t.verzio} kibontva: {cel}")
        return cel
    except BaseException:
        shutil.rmtree(uj, ignore_errors=True)
        raise


def wheels_parancs(rt: Path, lock: Path) -> list[str]:
    return [str(rt / "python" / "bin" / "python3"), "-B", "-m", "pip", "download", "--no-deps", "--only-binary=:all:",
            "--require-hashes", "-r", str(lock), "-d", str(rt / "wheels")]


def cel_valaszt(cel: str | None) -> Path:
    """A céltár: `--cel`, különben a repo `runtime/`-ja — de symlinkre (más checkout csak olvasható runtime-ja) soha."""
    if cel:
        return Path(cel).resolve()
    rt = REPO / "runtime"
    if rt.is_symlink():
        raise CsomagHiba("runtime_symlink", f"a {rt} symlink ({os.readlink(rt)}): oda nem írok. Adj meg saját célt: --cel <mappa>")
    return rt


def fut(argv: list[str], *, nyito: Callable | None = None, futtato: Futtato = futtat, naplo=print) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="runtime_fetch.py", description="A futtatókörnyezet letöltése (D3: jóváhagyással).")
    ap.add_argument("--cel")
    ap.add_argument("--komponens", default=",".join(ALAP_KOMPONENSEK))
    ap.add_argument("--pinek", default=str(PINEK))
    ap.add_argument("--kibont", action="store_true")
    ap.add_argument("--igen", action="store_true", help="a letöltés jóváhagyása (nélküle csak a terv)")
    a = ap.parse_args(argv)
    try:
        pinek = pinek_olvas(Path(a.pinek))
        komponensek = tuple(x.strip() for x in a.komponens.split(",") if x.strip())
        tetelek = tervez(pinek, komponensek)
        rt = cel_valaszt(a.cel)
        naplo(f"cél: {rt}")
        for t in tetelek:
            naplo(f"  {t.komponens} {t.verzio}: {t.url} (sha256 {t.sha256[:12]}…)")
        if "wheels" in komponensek:
            naplo("  wheels: " + " ".join(wheels_parancs(rt, REPO / "config" / "requirements.lock")))
        if not a.igen:
            naplo("D3: a letöltéshez kifejezett jóváhagyás kell — futtasd újra --igen kapcsolóval.")
            return 2
        dl = rt / "dl"
        for t in tetelek:
            f = letolt(t, dl, nyito=nyito, naplo=naplo)
            if a.kibont:
                kibont(t, f, rt, pinek=pinek, futtato=futtato, naplo=naplo)
        if "wheels" in komponensek:
            (rt / "wheels").mkdir(parents=True, exist_ok=True)
            futtato(wheels_parancs(rt, REPO / "config" / "requirements.lock"), timeout=3600)
        naplo("kész")
        return 0
    except CsomagHiba as e:
        naplo(f"HIBA ({e.kod}): {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(fut(sys.argv[1:]))
