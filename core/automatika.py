"""A közös automatika-ütemező (C23b, T149; `docs/C23-TERV.md` 6. fejezet; CLAUDE.md 2., 3. döntés, D4, D8, 27(c)).

Egy ütemező, amelyre minden automatikus fogyasztó köt (kártya, vektorindex, grafikon; később a C21 füzetmappa és a C26
összefoglaló): **senki nem épít saját változásfigyelőt**. Az ütemező maga modellt nem tölt, a vaultba nem ír, és a futó app
alatt él (háttérdémon nincs, D4): csak eldönti, *melyik jegyzet* érett a feldolgozásra, és fogyasztónként legfeljebb egy
`TaskType(automatikus=True)` feladatot küld be a feladatsorba — az indítás kapuja a meglévő `admit` (memóriaőr, tétlenség, a
9 GB-os modell csak tétlenségben, Asszisztens-kapcsoló).

**Események és egyeztetés.** A `Bus` `vault_valtozas` eseményei (`utak`, `torolt`) megjelölik a változott utakat; induláskor,
ha a busz eseményt dobott el (`kimaradt`), tömeges változásnál (`tomeges`) és `teljes_perc`-enként **teljes egyeztetés** az
index `fajl_allapot`-jából (út → hash, mtime). A döntés minden esetben az index hash-én és mtime-ján múlik, nem az esemény
idején: az eseményvesztés legfeljebb késleltet.

**„Erősen módosult”** (a mérték egyetlen helye; a C26 és a C35 innen importál): a normalizált mondathalmazok (NFC, kisbetű,
szóköz-normalizálás; a kód, a frontmatter, a megjegyzés, a beágyazás és a gép írta szakaszok nélkül — a forráshűség-kapu
előkészítésével) hosszal súlyozott Jaccard-távolsága az utoljára feldolgozott változathoz ≥ `kuszob`, **vagy** legalább
`uj_karakter` karakternyi új mondat. Az új jegyzet legalább `min_hossz` karakter. A `kuszob = 0` fogyasztó minden
tartalmi változásra fut (a fájl hash-e dönt, olvasás nélkül).

**Indítás**: a jegyzet `csend_perc` perce nem változott (az index mtime-ja szerint); 60 s-os ütem; az indulás utáni első
`[feladatsor] indulasi_szunet_mp`-ben semmi (D8); kikapcsolt Asszisztensnél nincs beküldés; a fogyasztó jelölt útjai
kötegelve (`koteg`). **Visszacsatolás**: a lépés a jegyzet feldolgozása után `Tar.kesz`-t hív (az `alap` a feldolgozott
változat mondathalmaza). Ha a gép kimenetét (pl. a kártya-kísérőjegyzetet) a felhasználó törli vagy visszavonja, a forrás
`tiltva` lesz: az automatika nem hozza vissza (a kézi parancs igen).

**Tároló**: `[utak] automatika_db` (`{var}/automatika.sqlite`), a belső mentés `VACUUM INTO`-listájában (33. döntés), a
használt adatbázis migrációja előtt állapotmásolattal (`mentes.migracio_elott`, a `tanulas_db` mintája, 45(c)).
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import sys
import threading
import time
import unicodedata
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import kiserok

KISERO_ELOTAG = kiserok.ALAP_ELOTAG   # a kísérőjegyzet-mappák névelőtagja, ha a `[vault] kisero_elotag` hiányzik (a forrás: core/kiserok.py)
_MONDAT_HATAR = re.compile(r"(?<=[.!?])\s+|\n+")
UTEM_MP = 60.0


# ------------------------------------------------------------------ a mérték (egyetlen hely)

def mondatok(md: str) -> frozenset[str]:
    """A jegyzet normalizált mondatai (NFC, kisbetű, szóköz-normalizálás; a kód, a frontmatter, a megjegyzés, a beágyazás és a
    gép írta szakaszok nélkül — a forráshűség-kapu előkészítésével). A `modulok` importja lusta (a core indulását nem viheti el)."""
    from modulok.kapuk import forras as KF
    ki = set()
    for sz in KF.elokeszit(md):
        for m in _MONDAT_HATAR.split(sz.szoveg):
            m = re.sub(r"\s+", " ", unicodedata.normalize("NFC", m)).strip().casefold()
            if len(m) >= 3:
                ki.add(m)
    return frozenset(ki)


@dataclass(frozen=True)
class Valtozas:
    tavolsag: float               # 0: azonos mondathalmaz, 1: semmi közös
    uj_karakter: int              # az `alap`-ban nem álló mondatok karaktere


JAVITAS_HASONLOSAG = 0.75          # a javított (elgépelés, jelölés) mondat a régi párja, nem új mondat (C23b mérése)
_JAVITAS_MAX = 200                 # ennél több eltérő mondatnál a párosítás elmarad (átírásnál úgyis „erős”)


def _harmasok(s: str) -> set[str]:
    return {s[i:i + 3] for i in range(max(0, len(s) - 2))}


def _javitasok(uj: frozenset[str], eltunt: frozenset[str]) -> set[str]:
    """Az új mondatok közül azok, amelyek egy eltűnt mondat javított változatai (karakter-3gram Jaccard ≥ `JAVITAS_HASONLOSAG`):
    a kis javítás (elgépelés, írásjel, jelölés) így nem számít tartalmi változásnak."""
    if not uj or not eltunt or len(uj) > _JAVITAS_MAX or len(eltunt) > _JAVITAS_MAX:
        return set()
    regiek = [(_harmasok(x), len(x)) for x in eltunt]
    ki = set()
    for x in uj:
        h = _harmasok(x)
        for rh, rl in regiek:
            if h and rh and min(len(x), rl) >= 0.6 * max(len(x), rl) and len(h & rh) / len(h | rh) >= JAVITAS_HASONLOSAG:
                ki.add(x)
                break
    return ki


def valtozas(alap: frozenset[str] | None, md: str | frozenset[str]) -> Valtozas:
    """A jegyzet (vagy kész mondathalmaz) az `alap`-hoz képest (`None`: nincs alap → minden új). A javított mondat (egy eltűnt
    mondat közeli változata) közösnek számít, nem újnak."""
    most = md if isinstance(md, frozenset) else mondatok(md)
    alap = alap or frozenset()
    javitott = _javitasok(most - alap, alap - most)
    egyesites = sum(len(x) for x in most | alap) - sum(len(x) for x in javitott)
    kozos = sum(len(x) for x in most & alap) + sum(len(x) for x in javitott)
    tavolsag = max(0.0, 1 - kozos / egyesites) if egyesites else 0.0
    return Valtozas(round(tavolsag, 6), sum(len(x) for x in most - alap - javitott))


def forras_ujjlenyomat(md: str | frozenset[str]) -> str:
    """A jegyzet tartalmi ujjlenyomata (a rendezett mondathalmaz sha1-je): a kisebb szerkesztés (sortörés, jelölés, blokkazonosító,
    `## Gyakorlás`) nem változtat rajta, a tartalmi igen."""
    m = md if isinstance(md, frozenset) else mondatok(md)
    return hashlib.sha1("\n".join(sorted(m)).encode("utf-8")).hexdigest()


def kisero_elotag(cfg) -> str:
    """A kísérőjegyzet-mappák névelőtagja: `[vault] kisero_elotag` (hiányában `KISERO_ELOTAG`); egyetlen forrás: `core/kiserok.py`."""
    return kiserok.kisero_elotag(cfg)


def tartalmi_ut(ut: str, elotag: str = KISERO_ELOTAG) -> bool:
    """Tartalmi `.md`: nem kísérőjegyzet (egyetlen útvonal-elem sem kezdődik az `elotag`-gal), nem rejtett mappa."""
    return kiserok.tartalmi_elotaggal(ut, elotag)


def hossz(m: frozenset[str]) -> int:
    return sum(len(x) for x in m)


def erosen_modosult(alap: frozenset[str] | None, most: frozenset[str], kuszob: float, uj_karakter: int,
                    min_hossz: int) -> tuple[str | None, Valtozas]:
    """A közös döntés: `("uj" | "erosen_modosult", v)` ha a jegyzet feldolgozandó, különben `(None, v)`."""
    v = valtozas(alap, most)
    if alap is None:
        return ("uj" if hossz(most) >= min_hossz else None), v
    if v.tavolsag >= kuszob or v.uj_karakter >= uj_karakter:
        return "erosen_modosult", v
    return None, v


# ------------------------------------------------------------------ fogyasztók

@dataclass(frozen=True)
class Fogyaszto:
    """Egy automatikus fogyasztó. `feladattipus`: a beküldendő `TaskType` (automatikus); `szuro(ut)`: kell-e neki az út;
    `kuszob`: 0 = minden tartalmi változásra (olvasás nélkül), különben az „erősen módosult” mérték; `koteg`: legfeljebb ennyi
    út egy feladatban (a paraméter `{"utak": […]}`); `onallo`: a lépés maga választja ki a jegyzeteket (a paraméter üres, a
    beküldéskor minden jelölt feldolgozottnak számít); `engedelyezett(cfg)`: a fogyasztó be van-e kapcsolva (pl. a vektorindex
    csak `[kereses.hibrid] vektor = true` mellett); `kimenet_tilt`: a fogyasztó gépi kimenetének (a `Tar.kesz` `kimenet`-je)
    törlése tiltja a forrást; `tartalom_szuro(md)`: a jegyzet tartalma kell-e a fogyasztónak (pl. van-e benne képlet; a hamis
    „nem_kell”, elbírált); `kiegeszito(md, sor)`: a közös mérték után a fogyasztó saját oka (pl. „uj_keplet”; csak ha a jegyzetnek
    van feldolgozott alapja), `None`: nincs."""
    nev: str
    feladattipus: str
    szuro: Callable[[str], bool] = tartalmi_ut
    kuszob: float = 0.3
    uj_karakter: int = 600
    csend_perc: float = 10
    min_hossz: int = 400
    koteg: int = 5
    onallo: bool = False
    engedelyezett: Callable[[object], bool] = lambda cfg: True
    parameterek: dict = field(default_factory=dict)
    ujraproba_ora: float = 6.0
    tartalom_szuro: Callable[[str], bool] | None = None
    kiegeszito: Callable[[str, dict], str | None] | None = None


REGISZTER: dict[str, Fogyaszto] = {}


def regisztral(f: Fogyaszto) -> Fogyaszto:
    """Fogyasztó felvétele (idempotens: ugyanaz a név felülírja)."""
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", f.nev):
        raise ValueError(f"érvénytelen fogyasztó-név: {f.nev!r}")
    REGISZTER[f.nev] = f
    return f


# ------------------------------------------------------------------ tároló

_MIGRACIO_1 = """
CREATE TABLE allapot (
    fogyaszto TEXT NOT NULL, ut TEXT NOT NULL,
    hash TEXT,                  -- az utoljára elbírált változat (az index hash-e): addig nem olvassuk újra
    alap TEXT,                  -- az utoljára FELDOLGOZOTT változat mondatai (JSON-lista); NULL: soha nem dolgoztuk fel
    ujjlenyomat TEXT,           -- annak tartalmi ujjlenyomata
    feldolgozva TEXT, bekuldve TEXT, feladat TEXT,
    kimenet TEXT,               -- a gépi kimenet vault-útja (pl. a kártya-kísérőjegyzet): a törlése tiltja a forrást
    tiltva TEXT, tiltas_ok TEXT,
    PRIMARY KEY (fogyaszto, ut));
CREATE INDEX allapot_kimenet ON allapot (kimenet);
"""
_MIGRACIO_2 = """
ALTER TABLE allapot ADD COLUMN adat TEXT;   -- fogyasztó-specifikus JSON az utoljára feldolgozott változatról (C35b: a képletkulcsok)
"""
MIGRACIOK = [_MIGRACIO_1, _MIGRACIO_2]
_ZAR = threading.Lock()


def _most() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def ut(cfg) -> Path:
    return cfg.path("automatika_db")


def _verzio(c) -> int:
    return c.execute("PRAGMA user_version").fetchone()[0]


def migral(c: sqlite3.Connection, elotte=None) -> None:
    """A séma léptetése (a `tanulas_db.migral` mintája): újabb sémánál nem nyúl hozzá, ha az ismert tábla megvan; a használt
    adatbázis sémaváltása előtt `elotte(régi_verzió)` (a mentés), és ha dob, a migráció elmarad."""
    v = _verzio(c)
    if v > len(MIGRACIOK):
        if not c.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'allapot'").fetchone():
            raise sqlite3.DatabaseError(f"az automatika.sqlite sémája újabb ({v}), és hiányzik az `allapot` tábla")
        return
    if v == len(MIGRACIOK):
        return
    if v >= 1 and elotte is not None:
        try:
            elotte(v)
        except Exception as e:      # noqa: BLE001 — bármilyen mentési hiba megállítja a migrációt
            raise sqlite3.DatabaseError(f"az automatika.sqlite migrációja elmaradt: a mentés előtte nem sikerült ({e})") from e
    for i, sql in enumerate(MIGRACIOK[v:], start=v + 1):
        c.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version={i};\nCOMMIT;")


@contextlib.contextmanager
def _kapcsolat(cfg):
    """Író kapcsolat (létrehoz, migrál a fájlzár alatt, WAL); egy tranzakció."""
    with _ZAR:
        p = ut(cfg)
        p.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(p, timeout=15, isolation_level=None)
        try:
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            if _verzio(c) < len(MIGRACIOK):
                fd = os.open(p.with_name(p.name + ".migracio.lock"), os.O_CREAT | os.O_RDWR, 0o600)
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX)

                    def ment(regi: int) -> None:
                        from core import mentes
                        mentes.migracio_elott(cfg, p, regi)
                    migral(c, ment)
                finally:
                    os.close(fd)
            c.execute("BEGIN IMMEDIATE")
            try:
                yield c
            except BaseException:
                c.execute("ROLLBACK")
                raise
            c.execute("COMMIT")
        finally:
            c.close()


@contextlib.contextmanager
def olvaso(cfg):
    """Csak olvasó kapcsolat, vagy `None`, ha nincs még fájl (nem hoz létre, nem migrál)."""
    p = ut(cfg)
    if not p.exists():
        yield None
        return
    c = sqlite3.connect(f"file:{urllib.parse.quote(str(p))}?mode=ro", uri=True, timeout=5)
    try:
        c.row_factory = sqlite3.Row
        yield c if _verzio(c) >= 1 else None
    finally:
        c.close()


class Tar:
    """Az ütemező és a fogyasztó-lépések közös állapota (a lépés alfolyamat is írja: SQLite, WAL, rövid tranzakciók)."""

    def __init__(self, cfg):
        self.cfg = cfg

    def sorok(self, fogyaszto: str) -> dict[str, dict]:
        with olvaso(self.cfg) as c:
            if c is None:
                return {}
            return {r["ut"]: dict(r) for r in c.execute("SELECT * FROM allapot WHERE fogyaszto = ?", (fogyaszto,))}

    def sor(self, fogyaszto: str, ut_: str) -> dict | None:
        with olvaso(self.cfg) as c:
            if c is None:
                return None
            r = c.execute("SELECT * FROM allapot WHERE fogyaszto = ? AND ut = ?", (fogyaszto, ut_)).fetchone()
            return dict(r) if r else None

    @staticmethod
    def _upsert(c, fogyaszto: str, ut_: str, **mezok) -> None:
        c.execute("INSERT INTO allapot (fogyaszto, ut) VALUES (?, ?) ON CONFLICT DO NOTHING", (fogyaszto, ut_))
        if mezok:
            c.execute(f"UPDATE allapot SET {', '.join(f'{k} = ?' for k in mezok)} WHERE fogyaszto = ? AND ut = ?",
                      (*mezok.values(), fogyaszto, ut_))

    def elbiralt(self, fogyaszto: str, hashek: dict[str, str]) -> None:
        """Az utak mostani változata elbírálva (nem kell feldolgozni): a következő ütem csak változás után olvassa újra."""
        if not hashek:
            return
        with _kapcsolat(self.cfg) as c:
            for u, h in hashek.items():
                self._upsert(c, fogyaszto, u, hash=h)

    def bekuldve(self, fogyaszto: str, hashek: dict[str, str], feladat: str, kesz: bool = False) -> None:
        with _kapcsolat(self.cfg) as c:
            for u, h in hashek.items():
                self._upsert(c, fogyaszto, u, hash=h, bekuldve=_most(), feladat=feladat,
                             **({"feldolgozva": _most()} if kesz else {}))

    def kesz(self, fogyaszto: str, ut_: str, md: str, hash_: str | None = None, kimenet: str | None = None,
             adat: dict | None = None) -> None:
        """A fogyasztó feldolgozta a jegyzet `md` változatát (a lépés hívja). `hash_`: a feldolgozás utáni fájl hash-e (a
        gépi írás válaszából), hogy a saját írás ne számítson új változásnak; `kimenet`: a gépi kimenet vault-útja; `adat`: a
        fogyasztó saját, JSON-ba férő állapota erről a változatról (a `kiegeszito` olvassa)."""
        m = mondatok(md)
        mezok = {"alap": json.dumps(sorted(m), ensure_ascii=False), "ujjlenyomat": forras_ujjlenyomat(m),
                 "feldolgozva": _most()}
        if hash_:
            mezok["hash"] = hash_
        if adat is not None:
            mezok["adat"] = json.dumps(adat, ensure_ascii=False, sort_keys=True)
        if kimenet:
            mezok["kimenet"] = unicodedata.normalize("NFC", kimenet)
        with _kapcsolat(self.cfg) as c:
            self._upsert(c, fogyaszto, ut_, **mezok)

    def atvesz(self, fogyaszto: str, ut_: str, mondatok_: list[str], ujjlenyomat: str, adat: dict | None = None) -> None:
        """Külső (régi) állapot átvétele: az alap, az ujjlenyomat és az `adat` — hash nélkül (az első ütemben a mérték dönt), meglévő
        feldolgozott sort nem ír felül."""
        with _kapcsolat(self.cfg) as c:
            if (c.execute("SELECT alap FROM allapot WHERE fogyaszto = ? AND ut = ?", (fogyaszto, ut_)).fetchone() or [None])[0]:
                return
            self._upsert(c, fogyaszto, ut_, alap=json.dumps(sorted(mondatok_), ensure_ascii=False), ujjlenyomat=ujjlenyomat or None,
                         feldolgozva=_most(),
                         **({"adat": json.dumps(adat, ensure_ascii=False, sort_keys=True)} if adat is not None else {}))

    def tilt(self, fogyaszto: str, ut_: str, ok: str) -> None:
        with _kapcsolat(self.cfg) as c:
            self._upsert(c, fogyaszto, ut_, tiltva=_most(), tiltas_ok=ok)

    def felold(self, fogyaszto: str, ut_: str) -> bool:
        with _kapcsolat(self.cfg) as c:
            return c.execute("UPDATE allapot SET tiltva = NULL, tiltas_ok = NULL WHERE fogyaszto = ? AND ut = ? "
                             "AND tiltva IS NOT NULL", (fogyaszto, ut_)).rowcount > 0

    def kimenet_torolve(self, utak) -> list[tuple[str, str]]:
        """A törölt utak közül a gépi kimenetek: a forrásuk tiltva lesz. → [(fogyasztó, forrás)]."""
        utak = [unicodedata.normalize("NFC", u) for u in utak]
        if not utak or not ut(self.cfg).exists():
            return []
        ki = []
        with _kapcsolat(self.cfg) as c:
            for u in utak:
                for r in c.execute("SELECT fogyaszto, ut FROM allapot WHERE kimenet = ? AND tiltva IS NULL", (u,)).fetchall():
                    c.execute("UPDATE allapot SET tiltva = ?, tiltas_ok = ? WHERE fogyaszto = ? AND ut = ?",
                              (_most(), f"a gépi kimenet ({u}) törölve vagy visszavonva", r["fogyaszto"], r["ut"]))
                    ki.append((r["fogyaszto"], r["ut"]))
        return ki

    def tiltottak(self) -> list[dict]:
        with olvaso(self.cfg) as c:
            if c is None:
                return []
            return [dict(r) for r in c.execute("SELECT fogyaszto, ut, kimenet, tiltva, tiltas_ok FROM allapot "
                                                "WHERE tiltva IS NOT NULL ORDER BY tiltva")]


# ------------------------------------------------------------------ a döntés (tiszta függvény)

@dataclass(frozen=True)
class Jelolt:
    ut: str
    hash: str
    ok: str                     # uj | erosen_modosult | valtozott (kuszob 0)


def dont(f: Fogyaszto, ut_: str, hash_: str, mtime: float, most: float, sor: dict | None,
         olvas: Callable[[str], str], elotag: str = KISERO_ELOTAG) -> tuple[str, Jelolt | None]:
    """Egy út egy fogyasztónak: (állapot, jelölt). Állapot: `szuro`, `elbiralt` (ez a változat már eldőlt), `tiltva`,
    `csend` (még változik), `nem_eleg` / `rovid` / `mar_kesz` (elbírálva, nem kell), `jelolt`. Az `olvas(ut)` csak akkor
    hívódik, ha a mérték kell (a `kuszob > 0` fogyasztónál, a változott és csendes jegyzetre). Az `elotag` a beépített
    `tartalmi_ut` szűrő kísérőmappa-előtagja (`kisero_elotag(cfg)`)."""
    if not (tartalmi_ut(ut_, elotag) if f.szuro is tartalmi_ut else f.szuro(ut_)):
        return "szuro", None
    sor = sor or {}
    if sor.get("tiltva"):
        return "tiltva", None
    if sor.get("hash") == hash_:
        bek, kesz = sor.get("bekuldve"), sor.get("feldolgozva")
        lejart = bek and (not kesz or kesz < bek) and \
            most - time.mktime(time.strptime(bek, "%Y-%m-%dT%H:%M:%S")) > f.ujraproba_ora * 3600
        if not lejart:
            return "elbiralt", None
    if most - mtime < f.csend_perc * 60:
        return "csend", None
    if f.kuszob <= 0:
        return "jelolt", Jelolt(ut_, hash_, "valtozott")
    try:
        szoveg = olvas(ut_)
        m = mondatok(szoveg)
    except (OSError, UnicodeDecodeError, ValueError):
        return "olvashatatlan", None
    if f.tartalom_szuro is not None and not f.tartalom_szuro(szoveg):
        return "nem_kell", None
    alap = frozenset(json.loads(sor["alap"])) if sor.get("alap") else None
    if sor.get("ujjlenyomat") and sor["ujjlenyomat"] == forras_ujjlenyomat(m):
        return "mar_kesz", None
    ok, _ = erosen_modosult(alap, m, f.kuszob, f.uj_karakter, f.min_hossz)
    if ok is None and alap is not None and f.kiegeszito is not None:
        ok = f.kiegeszito(szoveg, sor)
    if ok is None:
        return ("rovid" if alap is None else "nem_eleg"), None
    return "jelolt", Jelolt(ut_, hash_, ok)


# ------------------------------------------------------------------ az ütemező (a core háttérszála)

class Utemezo:
    """A core háttérszála: a busz `vault_valtozas` eseményei + időszakos teljes egyeztetés → beküldés a feladatsorba.

    `index`: `fajl_allapot()` (út → (hash, mtime_ns, méret, lemez_ut)); `queue`: `submit`, `fuggo`; `kapcsolo()`: az
    Asszisztens-kapcsoló (27(c)); `indulasi_kesleltetes_mp`: D8."""

    def __init__(self, cfg, index, queue, bus=None, kapcsolo: Callable[[], bool] = lambda: True,
                 indulasi_kesleltetes_mp: float | None = None, ora: Callable[[], float] = time.time,
                 teljes_perc: float = 15.0, publish=lambda e, **k: None):
        self.cfg, self.index, self.queue, self.bus = cfg, index, queue, bus
        self.kapcsolo, self.ora, self.publish = kapcsolo, ora, publish
        szunet = cfg.section("feladatsor").get("indulasi_szunet_mp", 180)
        self.indulas = ora() + float(szunet if indulasi_kesleltetes_mp is None else indulasi_kesleltetes_mp)
        self.teljes_perc = teljes_perc
        self.tar = Tar(cfg)
        self._piszkos: set[str] = set()
        self._varakozo: set[str] = set()
        self._teljes = True
        self._utolso_teljes = 0.0
        self._zar = threading.Lock()
        self._stop = threading.Event()
        self._szalak: list[threading.Thread] = []
        self.utolso: dict = {}
        self._naplozott_hibak: set[tuple[str, str]] = set()

    # -- életciklus
    def indit(self) -> None:
        if self._szalak:
            return
        if self.bus is not None:
            sub = self.bus.subscribe()
            self._szalak.append(threading.Thread(target=self._figyel, args=(sub,), name="automatika-esemeny", daemon=True))
        self._szalak.append(threading.Thread(target=self._fut, name="automatika-utem", daemon=True))
        for t in self._szalak:
            t.start()

    def leallit(self) -> None:
        self._stop.set()

    def _figyel(self, sub) -> None:
        try:
            while not self._stop.is_set():
                e = sub.get(timeout=1.0)
                if e:
                    self.esemeny(e)
        finally:
            sub.close()

    def esemeny(self, e: dict) -> None:
        t = e.get("tipus")
        if t == "kimaradt":
            with self._zar:
                self._teljes = True
        elif t == "vault_valtozas":
            with self._zar:
                if e.get("tomeges"):
                    self._teljes = True
                self._piszkos.update(e.get("utak") or ())
            if e.get("torolt"):
                try:
                    for fogy, forras in self.tar.kimenet_torolve(e["torolt"]):
                        print(f"[automatika] {fogy}: {forras} tiltva (a gépi kimenete törölve)", file=sys.stderr, flush=True)
                except (sqlite3.Error, OSError) as exc:
                    print(f"[automatika] a tiltás nem íródott: {exc}", file=sys.stderr, flush=True)

    def _fut(self) -> None:
        while not self._stop.wait(UTEM_MP):
            try:
                self.utem()
            except Exception as exc:  # noqa: BLE001 — az ütemező hibája nem viheti el a core-t
                print(f"[automatika] ütem-hiba: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)

    # -- egy ütem
    def _olvas(self, lemez: dict[str, str]):
        vault = Path(self.cfg.path("vault"))

        def olvas(u: str) -> str:
            return (vault / (lemez.get(u) or u)).read_bytes().decode("utf-8")
        return olvas

    def utem(self) -> dict:
        """Egy ütem: → összesítés (fogyasztónként a beküldött utak és az állapotok száma). A D8-szünet alatt és kikapcsolt
        Asszisztensnél semmi."""
        most = self.ora()
        if most < self.indulas:
            return {"szunet": True}
        if not self.kapcsolo():
            return {"kapcsolo_ki": True}
        allapot = self.index.fajl_allapot()
        with self._zar:
            teljes = self._teljes or most - self._utolso_teljes >= self.teljes_perc * 60
            self._teljes = False
            nezendo = set(allapot) if teljes else (self._piszkos | self._varakozo) & set(allapot)
            self._piszkos.clear()
            if teljes:
                self._utolso_teljes = most
        if teljes:                          # a lemaradt törlés-esemény pótlása: az eltűnt gépi kimenet is tilt
            with olvaso(self.cfg) as c:
                kimenetek = [r[0] for r in c.execute("SELECT DISTINCT kimenet FROM allapot WHERE kimenet IS NOT NULL "
                                                     "AND tiltva IS NULL")] if c is not None else []
            self.tar.kimenet_torolve([k for k in kimenetek if k not in allapot])
        lemez = {u: a[3] for u, a in allapot.items()}
        olvas = self._olvas(lemez)
        ossz: dict = {}
        varakozo: set[str] = set()
        for f in list(REGISZTER.values()):
            try:
                if not f.engedelyezett(self.cfg):
                    continue
            except Exception as exc:  # noqa: BLE001 — hibás beállítás: a fogyasztó kimarad, de nem csendben (F6)
                hiba = f"a beállítása hibás ({type(exc).__name__}: {str(exc)[:200]}); a fogyasztó kimarad"
                ossz[f.nev] = {"hiba": hiba}
                if (f.nev, hiba) not in self._naplozott_hibak:
                    self._naplozott_hibak.add((f.nev, hiba))
                    print(f"[automatika] {f.nev}: {hiba}", file=sys.stderr, flush=True)
                continue
            sorok = self.tar.sorok(f.nev)
            szam: dict[str, int] = {}
            jeloltek: list[Jelolt] = []
            elbiralt: dict[str, str] = {}
            for u in sorted(nezendo):
                h, mtime_ns = allapot[u][0], allapot[u][1]
                st, j = dont(f, u, h, mtime_ns / 1e9, most, sorok.get(u), olvas, kisero_elotag(self.cfg))
                szam[st] = szam.get(st, 0) + 1
                if st == "csend":
                    varakozo.add(u)
                elif st in ("nem_eleg", "rovid", "mar_kesz", "nem_kell"):
                    elbiralt[u] = h
                elif j is not None:
                    jeloltek.append(j)
            self.tar.elbiralt(f.nev, elbiralt)
            bekuldott = []
            if jeloltek:
                if self.queue.fuggo(f.feladattipus):
                    varakozo.update(j.ut for j in jeloltek)         # a futó feladat után a következő ütem viszi
                else:
                    jeloltek.sort(key=lambda j: allapot[j.ut][1])   # a régebben módosult előbb
                    resz = jeloltek if f.onallo else jeloltek[:max(1, f.koteg)]
                    params = dict(f.parameterek)
                    if not f.onallo:
                        params["utak"] = [j.ut for j in resz]
                    try:
                        d = self.queue.submit(f.feladattipus, params)
                    except Exception as exc:  # noqa: BLE001 — a beküldés hibája: a következő ütem újra próbálja
                        print(f"[automatika] {f.nev}: a beküldés nem sikerült: {exc}", file=sys.stderr, flush=True)
                        varakozo.update(j.ut for j in jeloltek)
                    else:
                        self.tar.bekuldve(f.nev, {j.ut: j.hash for j in resz}, d.get("id", ""), kesz=f.onallo)
                        bekuldott = [j.ut for j in resz]
                        varakozo.update(j.ut for j in jeloltek[len(resz):])
            ossz[f.nev] = {"allapotok": szam, "bekuldve": bekuldott}
        with self._zar:
            self._varakozo = varakozo
        self.utolso = {"ido": _most(), "teljes": teljes, "fogyasztok": ossz}
        return self.utolso


# ------------------------------------------------------------------ a meglévő fogyasztók (C23b: egy-egy sor)

def _vektor_be(cfg) -> bool:
    return bool(cfg.section("kereses", "hibrid").get("vektor", False))


def alap_fogyasztok(cfg) -> None:
    """A meglévő automatikus fogyasztók regisztrációja (a core indulásakor; idempotens).

    80(a), AI csak gombra: **magától csak a `vektorindex` fut** (a vaultba nem ír; `[kereses.hibrid] vektor`). A kártya, az összefoglaló és
    a grafikon-beírás fogyasztója **feltétel nélkül** nincs regisztrálva: a `[kartya|osszefoglalas|grafikon.automatika] be` kulcsot a core
    nem olvassa, a régi `be = true` sem kapcsolja vissza (CX-011). A kézi útjuk (feladattípus, „… ebből” parancs) ettől függetlenül
    működik; a feladatsor ráadásul minden `automatikus` feladattípust elutasít a `vektorindex`-en kívül (`server.automatikus_tiltott`)."""
    for nev in ("kartya", "osszefoglalo", "grafikon"):
        REGISZTER.pop(nev, None)
    regisztral(Fogyaszto("vektorindex", "vektorindex", kuszob=0, csend_perc=2, onallo=True, engedelyezett=_vektor_be))
    try:
        from . import plot_allapot
        plot_allapot.Automatika(cfg).atvesz(Tar(cfg))
    except Exception as exc:  # noqa: BLE001 — a régi állapot átvétele nem akadályozhatja a core indulását (sérült fájl: marad, jelzés)
        print(f"[automatika] a plot-automatika.json átvétele nem sikerült: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
