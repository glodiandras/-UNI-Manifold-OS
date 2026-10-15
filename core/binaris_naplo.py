"""A bináris mozgásnapló (LEGACY-SZERZODESEK L19) portja (C20a): a vaultba került bináris fájlok (videó, kép, PDF) naplója és visszavonása.

A pillanatkép-tároló csak a szövegréteget követi (14. döntés); a médiafájlt nem. Egy gépi tétel (a C20b `mozgat` művelete, a C21 füzetfotói)
viszont bináris fájlt is tesz a vaultba. Ha a tételt visszavonjuk, a leíró jegyzet eltűnik, a videó viszont bekötetlenül ott maradna (I40).
Ezért a tétel naplózza a bináris fájlokat, a visszavonás pedig **nem törli** őket (a törlés gazdai művelet), hanem visszaköltözteti a lánc
munkamappájába — onnan egy újabb tétel újra elhelyezheti. Ugyanez az eszköz teszi visszavonhatóvá a média **átnevezését** is (`tipus: "atnevezes"`).

A fájl és a rekord az L19-é: `{state}/binaris-naplo.jsonl`, soronként `{"commit", "kor", "kulcs", "fajlok": [vault-relatív út…]}`; a régi sorokat
(a legacy 102 sorát) érti. **Csak hozzáadás** (L09): új opcionális kulcsok — `tipus` (`media` | `fuzet` | `atnevezes`), `forras` (a lánc
munkamappájának gyökér-kulcsos hivatkozása), `sha256`, `regi`/`uj` (átnevezés). A visszaállítás után a legacy jelzősora kerül a naplóba
(`{"visszaallitva": […], "commitok": […]}`).

A legacy `binaris.py`-hoz képest (a viselkedés azonos, a hibái javítva): a fájlnév-összevetés **NFC/NFD-tűrő** (a rekord NFC-ben íródik, a lemezen
NFD név is megtalálható); a mozgatás **soha nem ír felül** (`tartos.rename_excl`; azonos köteten atomi), ütközésnél a fájl a helyén marad és ez
jelentve van; a `commit: null` rekord a körre (`kor`) is illeszthető; az utak a vaulton belül maradnak (`utkapu`).

**Javító 3 (Audit 3: A3-10, A3-11, A3-20)** — a visszaállítás a naplót megbízhatatlan bemenetnek tekinti (a napló a legacy 102 sorát is
tartalmazza, régi abszolút forrásmappákkal):

- a rekord `commit`-ja legalább 7 hex jegy, és előtag-egyezéssel illik a visszavont commithoz (egy `"a"` mező nem illik mindenre);
- a cél csak a megadott `gyokerek` (a `video_jobs`) szigorú ALATT állhat, a feloldott (`realpath`) úton: a `..`, a symlinkelt mappa és az
  azon kívüli abszolút mappa `marad`; **nem létező abszolút mappát nem hozunk létre** (a régi út nem támad fel), relatív kulcs mappája a
  `video_jobs` alatt létrejön; a forrás (és az átnevezés célja) minden útelemének feloldott útja a vaulton belül marad;
- azonosság: a rekord `sha256`-ja és/vagy `meret`-e (szöveg/szám egyetlen fájlnál, vagy `{vault-relatív út: érték}` szótár) ellenőrzött;
  eltérésnél a más tartalmú fájl a helyén `marad`. A rekordok, amelyek azonosságot nem rögzítenek (a legacy sorok), az útvédelem alatt
  mozognak; az új sorok írója (C20b) az `azonossag_mezok`-kal rögzíti őket;
- fájlonkénti hibakezelés: egy fájl hibája (`OSError`, váratlan kivétel) a fájlt a `marad` listába teszi az okkal, a többi mozog, a
  mozgatott lista és a jelzősor mindig a ténylegesen mozgatottakról szól, és a jelzősor írásának hibája a választ nem viszi el.

**C20b, a videó-klón (`klon: true`)**: a gépi írás `mozgat` videó-profilja a staging videóját APFS-klónként teszi a vaultba, a staging
példánya (`forras_ut`) marad. A visszavonás **nem töröl**: ha a staging eredetije megvan és bájtra azonos (sha256), a vaultbeli klón az
`archiv` (`[utak] video_visszavont`) alá költözik, `<kör>/` mappába, az `INDOK.md`-vel; ha az eredeti hiányzik, a klón a helyére tér
vissza (csak a `staging_gyokerek` alatt, létező mappába); ha az eredeti más tartalmú, a klón a helyén marad (`marad`).

**83. döntés javaslata, az `.apkg` médiája (`tipus: "apkg"`)**: a gépi írás `behoz` művelete az importáló saját `{tmp}` kicsomagoló
mappájából hozza a fájlokat (az a mappa az import után megszűnik), ezért a visszavonásnak nincs „honnan jött” helye: a bájtra azonos
(`sha256` + `meret`) fájl az `apkg_archiv` (`[utak] apkg_visszavont`) `<kör>/` mappájába költözik, az `INDOK.md`-vel — **nem törlődik**;
a közben átírt fájl a helyén marad (`marad`). A felhasználó által már korábban a vaultban tartott, újrahasznosított fájl nem kerül a
rekordba, így a visszavonás nem nyúl hozzá.
"""
from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import shutil
import time
import unicodedata
from pathlib import Path

from . import mediatipus, tartos, utkapu

KIHAGY = {".obsidian", ".trash", ".git"}
TIPUSOK = (None, "media", "fuzet", "atnevezes", "apkg")
MIN_SHA = 7
_HEX = re.compile(r"[0-9a-f]+")


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def naplo_ut(cfg) -> Path:
    return cfg.path("binaris_naplo")


# ------------------------------------------------------------------ leltár

def leltar(vault: str | Path) -> dict[str, tuple[int, int]]:
    """A vault bináris fájljai: `{vault-relatív út (NFC): (méret, mtime)}` — a `mediatipus` bináris kiterjesztéseivel."""
    vault = Path(vault)
    ki: dict[str, tuple[int, int]] = {}
    for d, almappak, fajlok in os.walk(vault):
        almappak[:] = [a for a in almappak if a not in KIHAGY]
        for f in fajlok:
            if mediatipus.binaris_e(f):
                p = Path(d) / f
                try:
                    st = p.stat()
                except OSError:
                    continue
                ki[nfc(str(p.relative_to(vault)))] = (st.st_size, int(st.st_mtime))
    return ki


def uj_fajlok(elotte: dict, utana: dict) -> list[str]:
    """A leltárban az `elotte` után megjelent fájlok (rendezve)."""
    return sorted(k for k in utana if k not in elotte)


# ------------------------------------------------------------------ napló

def rekord(commit: str | None, kor: str, kulcs: str, fajlok: list[str], *, tipus: str | None = None, forras: str | None = None,
           **extra) -> dict:
    """Egy napló-rekord (L19 alakja; az opcionális kulcsok csak hozzáadás). A `fajlok` NFC-ben íródik."""
    if tipus not in TIPUSOK:
        raise ValueError(f"ismeretlen tipus: {tipus}")
    r: dict = {"commit": commit, "kor": kor, "kulcs": kulcs, "fajlok": [nfc(f) for f in fajlok]}
    if tipus:
        r["tipus"] = tipus
    if forras:
        r["forras"] = forras
    r.update(extra)
    return r


def ir(naplo: str | Path, rec: dict) -> None:
    """Egy sor hozzáfűzése (tartósan: `F_FULLFSYNC`; a naplót a visszavonás olvassa, elveszett sor = bekötetlen videó)."""
    naplo = Path(naplo)
    naplo.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(naplo, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, (json.dumps(rec, ensure_ascii=False) + "\n").encode("utf-8"))
        tartos.fsync_teljes(fd)
    finally:
        os.close(fd)


def olvas(naplo: str | Path) -> list[dict]:
    """A napló sorai; a sérült sor (megszakadt írás) kimarad (nem akasztja a visszavonást)."""
    naplo = Path(naplo)
    if not naplo.is_file():
        return []
    ki = []
    for sor in naplo.read_text(encoding="utf-8", errors="replace").splitlines():
        if not sor.strip():
            continue
        try:
            r = json.loads(sor)
        except ValueError:
            continue
        if isinstance(r, dict):
            ki.append(r)
    return ki


# ------------------------------------------------------------------ azonosság

def kivonat(p: str | Path) -> str:
    """A fájl sha256-ja (blokkonként olvasva: a videó több GB lehet)."""
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blokk in iter(lambda: f.read(1 << 20), b""):
            h.update(blokk)
    return h.hexdigest()


def azonossag_mezok(vault: str | Path, fajlok: list[str]) -> dict:
    """A `rekord(..., **mezok)` azonosság-kulcsai a vaultban álló fájlokhoz: `{"sha256": {út: hex}, "meret": {út: bájt}}` (NFC utakkal).
    A rekord írója (C20b `mozgat`) a fájl vaultba kerülése után hívja; a visszaállítás ezzel veti össze a mostani fájlt (A3-11)."""
    vault = Path(vault)
    sha, meret = {}, {}
    for rel in fajlok:
        p = vault / rel
        sha[nfc(rel)], meret[nfc(rel)] = kivonat(p), p.stat().st_size
    return {"sha256": sha, "meret": meret}


def _azonossag_hiba(rec: dict, rel: str, p: Path, egyedi: bool) -> str | None:
    """`None`, ha a fájl azonos a rekordban rögzítettel (vagy a rekord a fájlhoz azonosságot nem rögzít); különben az ok."""
    for kulcs, mod in (("meret", lambda q: q.stat().st_size), ("sha256", kivonat)):
        ertek = rec.get(kulcs)
        if ertek is None:
            continue
        if isinstance(ertek, dict):
            elvart = ertek.get(nfc(rel), ertek.get(rel))
            if elvart is None:
                continue
        elif egyedi:
            elvart = ertek
        else:
            return f"a rekord {kulcs}-ja több fájl mellett nem rendelhető a fájlhoz"
        try:
            van = mod(p)
        except OSError as e:
            return f"a fájl azonossága nem ellenőrizhető: {e.strerror or e}"
        if (van != elvart) if kulcs == "meret" else (str(van).lower() != str(elvart).lower()):
            return f"a vaultban álló fájl nem azonos a naplózottal ({kulcs} eltér)"
    return None


# ------------------------------------------------------------------ visszaállítás

def _commit_ervenyes(c) -> bool:
    return isinstance(c, str) and len(c) >= MIN_SHA and bool(_HEX.fullmatch(c.lower()))


def _illik(rec: dict, shak: list[str], korok: list[str]) -> bool:
    """A rekord a visszavont commitokhoz (előtag-egyezés mindkét irányban; mindkét oldal legalább 7 hex jegy) vagy körökhöz tartozik.
    A rekord hibás (rövid, nem hex) `commit`-ja semmire nem illik; a `commit: null` sor a körre."""
    c = rec.get("commit")
    if c:
        if not _commit_ervenyes(c):
            return False
        c = c.lower()
        return any(len(s) >= MIN_SHA and (c.startswith(s.lower()) or s.lower().startswith(c)) for s in shak)
    return bool(rec.get("kor")) and rec["kor"] in korok


def _biztonsagos(rel: str) -> bool:
    return bool(rel) and not os.path.isabs(rel) and ".." not in Path(rel).parts and "\x00" not in rel


def _utkozik(vault: Path, rel: str) -> tuple[Path | None, str | None]:
    """A vault-relatív út létező fájlja (NFC, majd NFD névvel — a lemezen álló alak): `(út, None)`. Nincs ilyen: `(None, None)`.
    Van, de a feloldott útja (minden útelemé, a symlinkelt mappáké is) a vaulton kívülre esik: `(None, ok)`."""
    for r in (rel, unicodedata.normalize("NFD", rel)):
        p = vault / r
        if os.path.lexists(p):
            if utkapu.alatta(vault, p):
                return p, None
            return None, "a vaulton kívülre mutat (symlink)"
    return None, None


def _celmappa(kulcs: str, cel, gyokerek, sajat=()) -> tuple[Path | None, bool, str | None]:
    """A rekord kulcsának célmappája: `(mappa, létrehozható, hiba)`. A mappa feloldott útja a `gyokerek` valamelyikének szigorú alatt
    áll, vagy (C21) maga egy `sajat` gyökér (a füzetlánc figyelt mappája: onnan vitte el a 2.0 a fotót); nem létező abszolút kulcsú
    mappa nem jön létre (a legacy sorok régi forrásmappái); a relatív kulcsé a gyökér alatt igen."""
    try:
        mappa = Path(cel(kulcs))
        abszolut = os.path.isabs(kulcs)
        maga = any(os.path.realpath(g) == os.path.realpath(mappa) for g in sajat)
        if not maga and not any(utkapu.alatta(g, mappa) for g in [*gyokerek, *sajat]):
            return None, False, "a célmappa a megengedett gyökéren kívül esik"
        if os.path.lexists(mappa) and not mappa.is_dir():
            return None, False, "a cél nem mappa"
        if abszolut and not mappa.is_dir():
            return None, False, "a naplózott abszolút célmappa nem létezik (nem hozom létre)"
    except (ValueError, OSError) as e:
        return None, False, f"a célmappa nem értelmezhető: {e}"
    return mappa, not abszolut, None


def _mozgat(src: Path, dst: Path, letrehoz: bool = True) -> None:
    """Átköltöztetés, amely a meglévő célt nem írja felül. Azonos köteten `rename_excl` (atomi); más kötetre másolás + ellenőrzés + a
    forrás eltávolítása (soha nem csonka cél: `.manifold-tmp` → `rename_excl`). `letrehoz=False`: a célmappa nem jön létre."""
    if letrehoz:
        dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        tartos.rename_excl(src, dst)
    except OSError as e:
        if e.errno != errno.EXDEV:
            raise
        tmp = tartos.tmp_ut(dst)
        shutil.copy2(src, tmp)
        if tmp.stat().st_size != src.stat().st_size:
            tmp.unlink(missing_ok=True)
            raise OSError(errno.EIO, "a másolat mérete eltér a forrásétól", str(src))
        try:
            tartos.rename_excl(tmp, dst)
        except OSError:
            tmp.unlink(missing_ok=True)
            raise
        src.unlink()
    tartos.fsync_mappa(dst.parent)


ARCHIV_INDOK = ("# A visszavont gépi tételek videó-klónjai\n\nA videólánc (C20b) a staging videóját APFS-klónként teszi a vaultba "
                "(`ATTCHMNTS - Videos/`), a staging példánya marad. A tétel visszavonásakor a vaultbeli klón ide költözik: a "
                "visszavonás nem töröl (68(b), CLAUDE.md §4). Az eredeti a stagingben áll; ez a példány a felhasználó igenjével "
                "törölhető.\n")


APKG_INDOK = ("# A visszavont `.apkg`-importok médiája\n\nAz Anki-csomag importja (83. döntés javaslata) a csomag képeit és hangjait a "
              "vault csatolmány-mappájába tette (gépi írás, `behoz`). Az import visszavonásakor a fájlok ide költöztek: a visszavonás "
              "nem töröl (CLAUDE.md §4). Ezek a példányok a felhasználó igenjével törölhetők.\n")


def _klon_archival(src: Path, archiv: Path, kor: str) -> Path:
    """A vaultbeli videó-klón az `archiv/<kör>/` alá (felülírás nélkül; ütközésnél számozott név), az `INDOK.md`-vel."""
    return archival(src, archiv, kor, ARCHIV_INDOK)


def archival(src: Path, archiv: Path, kor: str, indok_szoveg: str) -> Path:
    """Egy vaultbeli fájl az `archiv/<kör>/` alá (felülírás nélkül; ütközésnél számozott név), az `INDOK.md`-vel (a videó-klón és
    az `.apkg` médiája közös útja). → az új hely."""
    archiv.mkdir(parents=True, exist_ok=True)
    indok = archiv / "INDOK.md"
    if not indok.exists():
        try:
            tartos.kizaro_ir(indok, indok_szoveg.encode("utf-8"))
        except FileExistsError:
            pass
    mappa = archiv / re.sub(r"[^0-9A-Za-z._-]", "_", kor or "kor")[:80]
    mappa.mkdir(exist_ok=True)
    torzs, kit = os.path.splitext(src.name)
    for i in range(1000):
        dst = mappa / (src.name if i == 0 else f"{torzs} ({i}){kit}")
        try:
            _mozgat(src, dst, letrehoz=False)
            return dst
        except FileExistsError:
            continue
    raise OSError(errno.EEXIST, "nincs szabad név az archívumban", str(mappa))


def visszaallit(naplo: str | Path, vault: str | Path, shak: list[str], cel, *, gyokerek, korok: list[str] | None = None, log=print,
                sajat_gyokerek=(), archiv: str | Path | None = None, staging_gyokerek=(), apkg_archiv: str | Path | None = None) -> dict:
    """A visszavont commitok (és körök) bináris fájljainak visszaköltöztetése. `cel(kulcs)` a lánc munkamappája (a `media`/`fuzet` rekordoknál);
    a `gyokerek` a megengedett célgyökerek (a `video_jobs`): a célmappa feloldott útja csak ezek szigorú alatt állhat (A3-10).

    → `{"mozgatva": [(vault-relatív út, új hely)], "marad": [(út, ok)], "hianyzik": [út]}`. A fájlt **nem töröljük** és **nem írunk felül**:
    ha a célban már van ilyen nevű fájl, vagy a fájl nem azonos a naplózottal, vagy az út/cél tiltott, a fájl a helyén marad (`marad`). A már
    visszaállított (nincs a vaultban) fájl `hianyzik`, nem hiba (a visszavonás idempotens). Az `atnevezes` rekordnál a `uj` utat `regi` névre
    nevezzük vissza. **Nem dob**: egy fájl hibája a `marad`-ba kerül, a többi mozog; a jelzősor (legacy alak) a ténylegesen mozgatottakról íródik."""
    vault = Path(vault)
    gyokerek = [Path(g) for g in gyokerek]
    korok = korok or []
    mozgatva: list[tuple[str, str]] = []
    marad: list[tuple[str, str]] = []
    hianyzik: list[str] = []

    def nem_mozog(rel: str, ok: str) -> None:
        marad.append((rel, ok))
        log(f"  a fájl a helyén marad ({ok}): {rel}")

    def egy_atnevezes(rec: dict) -> None:
        regi, uj = rec.get("regi"), rec.get("uj")
        if not (isinstance(regi, str) and isinstance(uj, str) and _biztonsagos(regi) and _biztonsagos(uj)):
            return
        src, ok = _utkozik(vault, uj)
        if src is None:
            if ok:
                nem_mozog(uj, ok)
            else:
                hianyzik.append(uj)
            return
        dst = vault / regi
        if os.path.lexists(dst):
            nem_mozog(uj, f"a régi néven már van fájl: {regi}")
            return
        if not utkapu.alatta(vault, dst):
            nem_mozog(uj, f"a régi név a vaulton kívülre mutat: {regi}")
            return
        elteres = _azonossag_hiba(rec, uj, src, True)
        if elteres:
            nem_mozog(uj, elteres)
            return
        _mozgat(src, dst)
        mozgatva.append((uj, regi))
        log(f"  visszanevezve: {uj} → {regi}")

    def egy_klon(rec: dict) -> None:
        """C20b: a vaultbeli videó-klón (nem töröl): archívumba, ha a staging eredetije azonos; vissza a helyére, ha hiányzik."""
        fajlok = [f for f in rec.get("fajlok", []) if isinstance(f, str)] if isinstance(rec.get("fajlok", []), list) else []
        eredeti = rec.get("forras_ut")
        for rel in fajlok:
            if not _biztonsagos(rel):
                continue
            try:
                src, ok = _utkozik(vault, rel)
                if src is None:
                    if ok:
                        nem_mozog(rel, ok)
                    else:
                        hianyzik.append(rel)
                    continue
                elteres = _azonossag_hiba(rec, rel, src, len(fajlok) == 1)
                if elteres:
                    nem_mozog(rel, elteres)
                    continue
                if not isinstance(eredeti, str) or not os.path.isabs(eredeti) or \
                        not any(utkapu.alatta(g, Path(eredeti)) for g in staging_gyokerek):
                    nem_mozog(rel, "a klón staging-beli eredetije nem a megengedett gyökér alatt áll")
                    continue
                e = Path(eredeti)
                if os.path.lexists(e):
                    if os.path.islink(e) or not e.is_file() or kivonat(e) != str(rec.get("sha256") or "").lower():
                        nem_mozog(rel, "a staging-beli eredeti más tartalmú: a klón nem költözik el")
                        continue
                    if archiv is None:
                        nem_mozog(rel, "nincs archívum-gyökér a klónnak")
                        continue
                    dst = _klon_archival(src, Path(archiv), str(rec.get("kor") or ""))
                    mozgatva.append((rel, str(dst)))
                    log(f"  a klón az archívumba került (az eredeti a stagingben): {rel} → {dst}")
                    continue
                if not e.parent.is_dir():
                    nem_mozog(rel, "a staging-beli eredeti mappája nem létezik (nem hozom létre)")
                    continue
                _mozgat(src, e, letrehoz=False)
                mozgatva.append((rel, str(e)))
                log(f"  visszaköltöztetve a stagingbe (az eredeti hiányzott): {rel} → {e}")
            except Exception as exc:  # noqa: BLE001
                nem_mozog(rel, f"hiba: {getattr(exc, 'strerror', None) or exc}")

    def egy_apkg(rec: dict) -> None:
        """83: az `.apkg` médiája (nem töröl): a bájtra azonos fájl az `apkg_archiv/<kör>/` alá, a más tartalmú a helyén marad."""
        fajlok = [f for f in rec.get("fajlok", []) if isinstance(f, str)] if isinstance(rec.get("fajlok", []), list) else []
        for rel in fajlok:
            if not _biztonsagos(rel):
                continue
            try:
                src, ok = _utkozik(vault, rel)
                if src is None:
                    if ok:
                        nem_mozog(rel, ok)
                    else:
                        hianyzik.append(rel)
                    continue
                if os.path.islink(src) or not src.is_file():
                    nem_mozog(rel, "nem közönséges fájl")
                    continue
                if not isinstance(rec.get("sha256"), dict):
                    nem_mozog(rel, "a rekord nem rögzít azonosságot (az `.apkg` médiája csak azonossággal mozog)")
                    continue
                elteres = _azonossag_hiba(rec, rel, src, False)
                if elteres:
                    nem_mozog(rel, elteres)
                    continue
                if apkg_archiv is None:
                    nem_mozog(rel, "nincs archívum-gyökér az `.apkg` médiájának")
                    continue
                dst = archival(src, Path(apkg_archiv), str(rec.get("kor") or ""), APKG_INDOK)
                mozgatva.append((rel, str(dst)))
                log(f"  az `.apkg` médiája az archívumba került: {rel} → {dst}")
            except Exception as exc:  # noqa: BLE001
                nem_mozog(rel, f"hiba: {getattr(exc, 'strerror', None) or exc}")

    def egy_media(rec: dict) -> None:
        if rec.get("tipus") == "apkg":
            egy_apkg(rec)
            return
        if rec.get("klon") is True:
            egy_klon(rec)
            return
        kulcs = rec.get("kulcs") or "ismeretlen"
        fajlok = [f for f in rec.get("fajlok", []) if isinstance(f, str)] if isinstance(rec.get("fajlok", []), list) else []
        celmappa, letrehoz, hiba = _celmappa(kulcs, cel, gyokerek, sajat_gyokerek if rec.get("tipus") == "fuzet" else ())
        nevek = rec.get("forras_nevek") if isinstance(rec.get("forras_nevek"), dict) else {}
        for rel in fajlok:
            if not _biztonsagos(rel):
                continue
            try:
                src, ok = _utkozik(vault, rel)
                if src is None:
                    if ok:
                        nem_mozog(rel, ok)
                    else:
                        hianyzik.append(rel)
                    continue
                if celmappa is None:
                    nem_mozog(rel, hiba or "érvénytelen célmappa")
                    continue
                nev = nevek.get(nfc(rel)) or nevek.get(rel)          # C21: a fotó a forrásbeli nevén tér vissza
                dst = celmappa / (nev if isinstance(nev, str) and nev and "/" not in nev and nev not in (".", "..") else src.name)
                if os.path.lexists(dst):
                    nem_mozog(rel, "a célban már van ilyen nevű fájl")
                    continue
                elteres = _azonossag_hiba(rec, rel, src, len(fajlok) == 1)
                if elteres:
                    nem_mozog(rel, elteres)
                    continue
                _mozgat(src, dst, letrehoz)
                mozgatva.append((rel, str(dst)))
                log(f"  visszaköltöztetve: {rel} → {dst}")
            except Exception as e:  # noqa: BLE001 — egy fájl hibája (I/O, jogosultság, váratlan) a többit nem akasztja
                nem_mozog(rel, f"hiba: {getattr(e, 'strerror', None) or e}")

    try:
        for rec in olvas(naplo):
            if not _illik(rec, shak, korok):          # a legacy jelzősora (`visszaallitva`) nem commit-rekord: kimarad
                continue
            try:
                if rec.get("tipus") == "atnevezes":
                    egy_atnevezes(rec)
                else:
                    egy_media(rec)
            except Exception as e:  # noqa: BLE001 — az átnevezés-sor hibája (a média-sor fájlonként kezelt)
                nem_mozog(str(rec.get("uj") or rec.get("kulcs") or "?"), f"hiba: {getattr(e, 'strerror', None) or e}")
    finally:
        if mozgatva:
            try:
                ir(naplo, {"visszaallitva": [m[0] for m in mozgatva], "commitok": list(shak), "ido": time.strftime("%Y-%m-%dT%H:%M:%S")})
            except Exception as e:  # noqa: BLE001 — a jelzősor hiánya csak annyit jelent, hogy egy újabb visszavonás `hianyzik`-ot lát
                log(f"  FIGYELEM: a jelzősor nem íródott ({e}); a fájlok visszaköltöztek")
    return {"mozgatva": mozgatva, "marad": marad, "hianyzik": hianyzik}


def visszavonas_utan(cfg, repo, sha: str | None, kor: str | None, log=print, gyokerek=None) -> dict:
    """Az `App.undo` hívja a vault-visszavonás UTÁN (a kör-zár alatt): a visszavont commit(ok) bináris fájljai a lánc munkamappájába.
    A `media` rekord kulcsa a médiajob kulcsa (`{video_jobs}/<kulcs>`); az abszolút kulcs (legacy füzet-sor) csak a `gyokerek`
    (alapból a `video_jobs`) alatt álló, LÉTEZŐ mappa lehet. **Nem dob** (A3-20): a hiba a `marad` listában jön vissza."""
    naplo = naplo_ut(cfg)
    if not naplo.is_file():
        return {"mozgatva": [], "marad": [], "hianyzik": []}
    jobs = cfg.path("video_jobs")
    try:
        shak = [sha] if sha else [c.sha for c in repo.log(run=kor)]
    except Exception as e:  # noqa: BLE001
        return {"mozgatva": [], "marad": [("(napló)", f"a visszavont commitok nem olvashatók: {e}")], "hianyzik": []}
    from . import fuzet           # C21: a füzetlánc fotója a figyelt mappájába tér vissza (csak a `fuzet` rekord, azonossággal)
    return visszaallit(naplo, repo.work_tree, shak, lambda kulcs: Path(kulcs) if os.path.isabs(kulcs) else jobs / kulcs,
                       gyokerek=[jobs, *(gyokerek or [])], korok=[kor] if kor else [], log=log,
                       sajat_gyokerek=fuzet.figyelt_mappak(cfg), archiv=cfg.path("video_visszavont"),
                       staging_gyokerek=[cfg.path("staging")], apkg_archiv=cfg.path("apkg_visszavont"))
