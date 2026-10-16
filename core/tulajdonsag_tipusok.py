"""Explicit felhasználói típusválasztás az Obsidian-kompatibilis types.json-ba (F11).

Ez az egyetlen szűk kivétel a rejtett vault-utak írási tilalma alól. Jegyzetet nem
ír, értéket nem konvertál. A gépi lépés-token nem hívhatja ezt az íróvégpontot.
Szigorú JSON + nyersbájt-CAS, kör-zár, kötelező előzetes pillanatkép, ugyanahhoz a
rögzített mappaleíróhoz kötött olvasás/tmp/csere. Az ismeretlen JSON-adat megmarad.
"""
from __future__ import annotations

import contextlib
import errno
import hashlib
import json
import os
import re
import secrets
import stat
import unicodedata
from decimal import Decimal, DecimalException

from . import frame, snapshot
from .index import elemzo
from .tartos import fsync_teljes
from .utvonalak import HttpError

UT = ".obsidian/types.json"
NEV = "types.json"
MAX_BAJT = 1024 * 1024
HIANY_REV = "hianyzik"
FORRAS = "pult-tulajdonsag-tipus"


def _rev(nyers: bytes | None) -> str:
    return HIANY_REV if nyers is None else hashlib.sha256(nyers).hexdigest()


def _utkozes():
    return HttpError(409, "Property types changed. Reload the list before trying again.",
                     kod="tulajdonsag_tipus.utkozes")


def _egyedi(parok):
    adat = {}
    for k, v in parok:
        if k in adat:
            raise ValueError("duplicate key")
        adat[k] = v
    return adat


def _nem_veges(_):
    raise ValueError("non-finite JSON number")


class _TulNagy(ValueError):
    pass


def _json(adat):
    """Veszteségmentes számok, írás közbeni méretkorlát; nincs behúzás miatti négyzetes bővülés."""
    reszek, hossz = [], 0
    def ir(resz):
        nonlocal hossz
        hossz += len(resz)                   # a kimenet ASCII: a karakter- és bájtszám azonos
        if hossz >= MAX_BAJT:                # egy záró LF-nek is helyet hagyunk
            raise _TulNagy()
        reszek.append(resz)
    def ertek(v):
        if isinstance(v, dict):
            ir("{")
            for i, (k, e) in enumerate(v.items()):
                if i:
                    ir(",")
                ir(json.dumps(k, ensure_ascii=True))
                ir(":")
                ertek(e)
            ir("}")
        elif isinstance(v, list):
            ir("[")
            for i, e in enumerate(v):
                if i:
                    ir(",")
                ertek(e)
            ir("]")
        else:
            ir(str(v) if isinstance(v, Decimal) else json.dumps(v, ensure_ascii=True, allow_nan=False))
    ertek(adat)
    return "".join(reszek)


def _olvas(dfd: int):
    try:
        fd = os.open(NEV, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd)
    except FileNotFoundError:
        return None, {}, None
    except OSError as e:
        if e.errno == errno.ELOOP:
            raise HttpError(409, "Property types must be stored in a regular file, not a symbolic link.",
                            kod="tulajdonsag_tipus.nem_biztonsagos") from None
        raise
    with os.fdopen(fd, "rb") as fh:
        st = os.fstat(fh.fileno())
        if not stat.S_ISREG(st.st_mode):
            raise HttpError(409, "Property types must be stored in a regular file, not a symbolic link.",
                            kod="tulajdonsag_tipus.nem_biztonsagos")
        if st.st_size > MAX_BAJT:
            raise HttpError(413, "The property types file is too large to edit safely.",
                            kod="tulajdonsag_tipus.tul_nagy")
        nyers = fh.read(MAX_BAJT + 1)
        utan = os.fstat(fh.fileno())
    if (st.st_size, st.st_mtime_ns, st.st_ctime_ns) != (utan.st_size, utan.st_mtime_ns, utan.st_ctime_ns):
        raise _utkozes()
    if len(nyers) > MAX_BAJT:
        raise HttpError(413, "The property types file is too large to edit safely.",
                        kod="tulajdonsag_tipus.tul_nagy")
    try:
        adat = json.loads(nyers.decode("utf-8-sig"), object_pairs_hook=_egyedi, parse_constant=_nem_veges,
                          parse_float=Decimal)
        if not isinstance(adat, dict) or not isinstance(adat.get("types", {}), dict):
            raise ValueError("expected object and types object")
    except (ValueError, RecursionError, DecimalException):
        raise HttpError(409, "The property types file is not valid JSON. Repair it before changing a type; it was not overwritten.",
                        kod="tulajdonsag_tipus.hibas_json") from None
    return nyers, adat, st


@contextlib.contextmanager
def _mappa(vault):
    def munkater_ellenoriz():
        if not vault._munkater_azonos():
            raise HttpError(409, "The workspace changed on disk. Reopen it before changing property types.",
                            kod="tulajdonsag_tipus.munkater_csere")
    munkater_ellenoriz()                    # az elérhetőség cache-e nem munkatér-azonossági bizonyíték
    root = vault.root                       # a munkatér azonosságának és elérhetőségének kapuja
    rfd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        try:
            dfd = os.open(".obsidian", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=rfd)
        except OSError as e:
            raise HttpError(409, "The vault configuration folder is unavailable or is a symbolic link.",
                            kod="tulajdonsag_tipus.mappa") from e
        try:
            def ellenoriz():
                munkater_ellenoriz()
                most = os.stat(vault.root, follow_symlinks=False)
                mappa = os.stat(".obsidian", dir_fd=rfd, follow_symlinks=False)
                regi, regi_mappa = os.fstat(rfd), os.fstat(dfd)
                if not stat.S_ISDIR(most.st_mode) or not stat.S_ISDIR(mappa.st_mode) or \
                        (most.st_dev, most.st_ino) != (regi.st_dev, regi.st_ino) or \
                        (mappa.st_dev, mappa.st_ino) != (regi_mappa.st_dev, regi_mappa.st_ino):
                    raise _utkozes()
            ellenoriz()
            yield dfd, ellenoriz
        finally:
            os.close(dfd)
    finally:
        os.close(rfd)


def _valasz(nyers, adat):
    return {"rev": _rev(nyers), "types": {k: v for k, v in adat.get("types", {}).items()
                                         if isinstance(v, str) and v in elemzo.TIPUSOK}}


def olvas(vault):
    with _mappa(vault) as (dfd, ellenoriz):
        nyers, adat, _ = _olvas(dfd)
        ellenoriz()
        return _valasz(nyers, adat)


def _keres(adat):
    from .tulajdonsagok import _KULCS_NEV
    if not isinstance(adat, dict) or set(adat) != {"kulcs", "tipus", "rev"}:
        raise HttpError(400, "Choose a property key, a type and the loaded revision.", kod="tulajdonsag_tipus.keres")
    kulcs, tipus, rev = adat["kulcs"], adat["tipus"], adat["rev"]
    if not isinstance(kulcs, str):
        raise HttpError(400, "Enter a valid property name.", kod="tulajdonsag_tipus.kulcs")
    kulcs = unicodedata.normalize("NFC", kulcs.strip())
    if len(kulcs.encode("utf-8", errors="surrogatepass")) > 256 or not _KULCS_NEV.fullmatch(kulcs):
        raise HttpError(400, "Enter a valid property name.", kod="tulajdonsag_tipus.kulcs")
    if not isinstance(tipus, str) or tipus not in elemzo.TIPUSOK:
        raise HttpError(400, "Choose a supported property type.", kod="tulajdonsag_tipus.tipus")
    rogzitett = "tags" if elemzo._TAGS_KULCS.fullmatch(kulcs) else \
        "aliases" if elemzo._ALIAS_KULCS.fullmatch(kulcs) else None
    if rogzitett and tipus != rogzitett or not rogzitett and tipus in ("tags", "aliases"):
        raise HttpError(400, "Tags and aliases have fixed property types.", kod="tulajdonsag_tipus.rogzitett")
    if not isinstance(rev, str) or not (rev == HIANY_REV or re.fullmatch(r"[a-f0-9]{64}", rev)):
        raise HttpError(400, "Reload property types before saving a change.", kod="tulajdonsag_tipus.rev")
    return kulcs, tipus, rev


def _csere(dfd, nyers, uj, st, ellenoriz):
    tmp = f".types.json.{secrets.token_hex(4)}.manifold-tmp"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dfd)
        with os.fdopen(fd, "wb") as fh:
            fh.write(uj)
            if st is not None:
                os.fchmod(fh.fileno(), stat.S_IMODE(st.st_mode) & 0o777)
            fh.flush()
            fsync_teljes(fh.fileno())
        ellenoriz()
        if _olvas(dfd)[0] != nyers:
            raise _utkozes()
        os.replace(tmp, NEV, src_dir_fd=dfd, dst_dir_fd=dfd)
        try:
            fsync_teljes(dfd)
        except OSError:
            return False                   # a fájl már cserélődött: nincs hamis „nem mentődött” válasz
        return True
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp, dir_fd=dfd)


def beallit(vault, adat, index=None):
    kulcs, tipus, rev = _keres(adat)
    try:
        with frame.run_lock(vault.cfg, wait=False, turelem_mp=frame.felhasznaloi_turelem(vault.cfg)):
            with _mappa(vault) as (dfd, ellenoriz):
                nyers, regi, st = _olvas(dfd)
                if _rev(nyers) != rev:
                    raise _utkozes()
                if regi.get("types", {}).get(kulcs) == tipus:
                    return {**_valasz(nyers, regi), "valtozas": False}
                uj_adat = {**regi, "types": {**regi.get("types", {}), kulcs: tipus}}
                try:
                    uj = (_json(uj_adat) + "\n").encode("utf-8")
                except _TulNagy:
                    raise HttpError(413, "The property types file is too large to edit safely.",
                                    kod="tulajdonsag_tipus.tul_nagy") from None
                except (ValueError, RecursionError):
                    raise HttpError(409, "The property types file is too complex to edit safely. It was not overwritten.",
                                    kod="tulajdonsag_tipus.bonyolult_json") from None
                if len(uj) > MAX_BAJT:
                    raise HttpError(413, "The property types file is too large to edit safely.",
                                    kod="tulajdonsag_tipus.tul_nagy")
                repo = vault.repo()
                if repo is None:
                    raise HttpError(503, "Property types were not changed because snapshots are unavailable. Repair the snapshot store and try again.",
                                    kod="tulajdonsag_tipus.pillanat_nincs")
                try:
                    ellenoriz()
                    repo.commit("Manual changes before changing property types", {"Mos-Forras": "kezi"})
                    if not repo.has_head():
                        repo.git("commit", "-q", "--allow-empty", "--no-verify", "-m", "Baseline before changing property types")
                    # check-ignore nem támogatja a Repo által alapból kért literal pathspec-mágiát.
                    # Az út itt kódállandó, a globális tiltás erre az egy lekérdezésre oldható.
                    if nyers is None and repo.git("--no-literal-pathspecs", "check-ignore", "--no-index", "-q", "--", UT, check=False).returncode != 1:
                        raise snapshot.SnapshotError("New property types are excluded from snapshots.")
                    # A testreszabott kizárás vagy az előzetes snapshot közbeni külső írás nem veszhet el.
                    elozo = repo.git_bytes("show", f"HEAD:{UT}", check=False)
                    if (nyers is None and elozo.returncode == 0) or \
                            (nyers is not None and (elozo.returncode != 0 or elozo.stdout != nyers)):
                        raise snapshot.SnapshotError("The previous property types revision is not in the snapshot.")
                except snapshot.SnapshotError:
                    raise HttpError(503, "Property types were not changed because the safety snapshot failed. Repair the snapshot store and try again.",
                                    kod="tulajdonsag_tipus.pillanat_hiba") from None
                tartos = _csere(dfd, nyers, uj, st, ellenoriz)
                kor, pillanat, git = frame.new_id("TIPUS"), None, True
                figyelmeztetes = [] if tartos else ["The type changed on disk, but the folder could not be synced. Its durability is uncertain. Reload property types to check the current version."]
                try:
                    pillanat = repo.commit_machine("Property type changed", {snapshot.TRAILER_RUN: kor,
                                                   snapshot.TRAILER_ITEM: UT, "Mos-Forras": FORRAS}, [UT])
                    mentett = repo.git_bytes("show", f"HEAD:{UT}", check=False)
                    if mentett.returncode != 0 or mentett.stdout != uj:
                        raise snapshot.SnapshotError("The saved property types revision is not in the snapshot.")
                except snapshot.SnapshotError:
                    # A csere már tartós: a válasz a fájlírásé. Az előző bájtok biztosan snapshotban állnak.
                    git = False
                    figyelmeztetes.append("The new snapshot failed. The previous version is preserved in snapshots. Repair the snapshot store before another type change.")
                valasz = {**_valasz(uj, uj_adat), "valtozas": True, "git": git, "tartos": tartos,
                          "pillanat": pillanat, "kor": kor, "figyelmeztetes": " ".join(figyelmeztetes) or None}
    except frame.Busy:
        raise HttpError(423, "The vault is busy. Wait for the current operation to finish, then try again.",
                        kod="tulajdonsag_tipus.foglalt") from None
    if index is not None:
        valasz["index_kesz"] = index.frissit([UT])
        if not valasz["index_kesz"]:
            figyelmeztetes = "The type was saved, but the note index has not finished updating. Wait for it to recover before relying on property filters."
            valasz["figyelmeztetes"] = " ".join(filter(None, [valasz["figyelmeztetes"], figyelmeztetes]))
    return valasz
