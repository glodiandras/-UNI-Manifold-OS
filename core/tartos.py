"""Tartós fájlírás (C29.6; 2. audit T026, T025, T092; az 1. audit M5 része): közös segédek a vault-írókhoz.

- **`fsync_teljes`**: macOS-en az `os.fsync` nem üríti a lemez gyorsítótárát, csak az `F_FULLFSYNC` — ezt kérjük a
  fájlra és (`fsync_mappa`) a szülőmappára is, hogy a csere bejegyzése is tartós legyen. Ha a kötet nem támogatja
  (`ENOTSUP`), az `os.fsync` a tartalék.
- **`atomi_ir`**: egyedi tmp + `F_FULLFSYNC` + az `ellenoriz()` a csere előtt + `os.replace` + mappa-fsync. A csere
  új inode-ot ad, ezért a **születési idő** (`st_birthtime`: a Bases `file.ctime`-ja, az Obsidian „Created time”)
  elveszne; a csere előtt kiolvassuk, utána `os.utime`-mal visszahúzzuk (a macOS a crtime-ot a nála korábbi mtime-ra
  állítja), majd az mtime az új tartalomé marad.
- **`kizaro_ir`** / **`rename_excl`**: létrehozás vagy átnevezés, amely meglévő célt **soha nem ír felül**
  (`renamex_np` + `RENAME_EXCL`, APFS-en atomi; fájlra és mappára is). Hard link (`os.link`) szándékosan nincs: a
  hard linkkel létrehozott fájl törlésének eseményét az FSEvents nem jelenti (T100).
"""
from __future__ import annotations

import ctypes
import errno
import fcntl
import os
import secrets
from pathlib import Path

from . import osszeomlas

TMP_UTOTAG = ".manifold-tmp"            # az ideiglenes fájl utótagja (a pillanatkép kizárja)
RENAME_EXCL = 0x00000004                # <sys/stdio.h>: ne írja felül a célt

_libc = ctypes.CDLL(None, use_errno=True)
_renamex = getattr(_libc, "renamex_np", None)
if _renamex is not None:
    _renamex.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
    _renamex.restype = ctypes.c_int
CLONE_NOFOLLOW = 0x0001                 # <sys/clonefile.h>: a forrás symlinkjét nem követi
_clonefile = getattr(_libc, "clonefile", None)
if _clonefile is not None:
    _clonefile.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint32]
    _clonefile.restype = ctypes.c_int


def tmp_ut(p: Path) -> Path:
    """Az ideiglenes fájl: rejtett, egyedi, és a neve 255 bájt alatt marad (L9) — a `*.manifold-tmp` kizárás illik rá."""
    nev = p.name.encode("utf-8")[:200].decode("utf-8", "ignore")
    return p.with_name(f".{nev}.{secrets.token_hex(4)}{TMP_UTOTAG}")


def fsync_teljes(fd: int) -> None:
    """`F_FULLFSYNC` (a lemez gyorsítótárát is üríti); ha a kötet nem támogatja, `os.fsync`."""
    try:
        fcntl.fcntl(fd, fcntl.F_FULLFSYNC)
    except (OSError, AttributeError):
        os.fsync(fd)


def fsync_mappa(d) -> None:
    """A mappa bejegyzéseinek tartóssága (egy csere vagy létrehozás után)."""
    fd = os.open(d, os.O_RDONLY)
    try:
        fsync_teljes(fd)
    finally:
        os.close(fd)


def fsync_ir(p, b: bytes) -> None:
    """Egy fájl írása közvetlenül, `F_FULLFSYNC`-kel (a szándéknapló darabjai: nem atomi csere, a `terv.json`-t
    az `os.replace` teszi érvényessé)."""
    with open(p, "wb") as fh:
        fh.write(b)
        fh.flush()
        fsync_teljes(fh.fileno())


def _tmp_torol(tmp) -> None:
    try:
        os.remove(tmp)                  # a saját ideiglenes fájlunk
    except FileNotFoundError:
        pass


def _szuletesi_ido_ns(p: Path) -> int | None:
    """A meglévő fájl születési ideje ns-ban (a Python nem ad `st_birthtime_ns`-t), vagy None (nincs fájl / nincs ilyen
    mező ezen a rendszeren)."""
    try:
        szuletes = getattr(os.stat(p), "st_birthtime", None)
    except OSError:
        return None
    return None if szuletes is None else int(szuletes * 1_000_000_000)


def _szuletesi_ido_vissza(p: Path, szuletes_ns: int) -> None:
    """A születési idő visszahúzása a cserélt fájlon, az mtime megtartásával (lásd a modul leírását)."""
    try:
        st = os.stat(p)
        if getattr(st, "st_birthtime", None) is None or int(st.st_birthtime * 1_000_000_000) <= szuletes_ns:
            return
        os.utime(p, ns=(st.st_atime_ns, szuletes_ns))          # a crtime a korábbi mtime-ra áll
        os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))       # az mtime visszaáll az új tartalomé
    except OSError:
        pass                            # a születési idő megőrzése jó szándékú: az írás sikere nem múlik rajta


def atomi_ir(p, b: bytes, ellenoriz=None) -> None:
    """Atomi, tartós csere (L45): egyedi tmp + `F_FULLFSYNC`, az `ellenoriz()` a csere előtt (kivételére a tmp
    törlődik, a fájl érintetlen), `os.replace`, a szülőmappa fsync-je, és a születési idő megőrzése."""
    p = Path(p)
    tmp = tmp_ut(p)
    try:
        with open(tmp, "wb") as fh:
            fh.write(b)
            fh.flush()
            fsync_teljes(fh.fileno())
        if ellenoriz is not None:
            ellenoriz()
        szuletes = _szuletesi_ido_ns(p)
        osszeomlas.pont("atomi.csere_elott")
        os.replace(tmp, p)
    except BaseException:
        _tmp_torol(tmp)
        raise
    osszeomlas.pont("atomi.csere_utan")
    if szuletes is not None:
        _szuletesi_ido_vissza(p, szuletes)
    fsync_mappa(p.parent)


def rename_excl(src, dst) -> None:
    """Átnevezés, amely a meglévő célt nem írja felül (`FileExistsError`); fájlra és mappára is. Ha a `renamex_np`
    nem elérhető (nem macOS), létezés-ellenőrzés + `os.rename` a tartalék — ott a kizárás nem atomi."""
    if _renamex is None:
        if os.path.lexists(dst):
            raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), os.fspath(dst))
        os.rename(src, dst)
        return
    if _renamex(os.fsencode(src), os.fsencode(dst), RENAME_EXCL) != 0:
        e = ctypes.get_errno()
        raise OSError(e, os.strerror(e), os.fspath(src), None, os.fspath(dst))     # EEXIST → FileExistsError, …


def klon_excl(src, dst) -> None:
    """APFS-klón (`clonefile`, C20b): azonnali, helyfoglalás nélküli másolat ugyanazon a köteten, amely a meglévő célt **nem írja
    felül** (`FileExistsError`). Más kötet vagy nem APFS: `OSError` (`EXDEV`/`ENOTSUP`) — tartalék másolás nincs, a hívó dönt."""
    if _clonefile is None:
        raise OSError(errno.ENOTSUP, "a clonefile nem elérhető (nem macOS)", os.fspath(src))
    if _clonefile(os.fsencode(src), os.fsencode(dst), CLONE_NOFOLLOW) != 0:
        e = ctypes.get_errno()
        raise OSError(e, os.strerror(e), os.fspath(src), None, os.fspath(dst))


def kizaro_ir(p, b: bytes) -> None:
    """Új fájl létrehozása teljes tartalommal, tartósan, és **meglévőt nem írva felül** (`FileExistsError`): egyedi
    tmp + `F_FULLFSYNC`, majd `rename_excl`. A kivétel vagy a megszakadás nem hagy csonka célfájlt."""
    p = Path(p)
    tmp = tmp_ut(p)
    try:
        with open(tmp, "xb") as fh:
            fh.write(b)
            fh.flush()
            fsync_teljes(fh.fileno())
        rename_excl(tmp, p)
    except BaseException:
        _tmp_torol(tmp)
        raise
    fsync_mappa(p.parent)
