"""A személyes adatbázis (`{szemelyes}/pos.sqlite`) közös rétege: a séma-migrációk és az író/olvasó kapcsolat.

A séma a legacy `db.py` elvét követi (L56–L57): csak új migrációval bővül (`PRAGMA user_version`), WAL, a
migrációk atomi szkriptek. Az 1-es migráció (a naptár tábláit a legacy hozta) változatlan; a 2.0 az 1-es táblák
**tartalmát** a naptár-szinkron (C29) írja, a sémájukhoz nem nyúl.

- 1-es: `forras_rekord`, `import_futas`, `naptar`, `naptar_valtozas` (legacy, L56);
- 2-es: `tr_*` és `has_*` — a tracker (C27, 30. döntés);
- 3-as: `emlekezteto*` és `naptar_javaslat` — az emlékeztetők és a tanulásiblokk-javaslatok (C29, 32. döntés);
- 4-es: `has_asszisztens` — az Asszisztens javaslatainak elfogadási statisztikája (C30a), útvonal és szöveg nélkül;
- 5-ös: `tr_aktiv_ora` — az aktív idő napszak-bontása (C30b, K205 (a)): nap × óra × tantárgy, útvonal és szöveg nélkül.

Az írók (a tracker és a naptár/emlékeztető) ugyanazon a zárral szerializálódnak egy folyamaton belül; a másik
folyamat ellen az SQLite saját írászára véd (`timeout`). Az olvasó semmit nem hoz létre.
"""
from __future__ import annotations

import contextlib
import re
import sqlite3
import sys
import threading
import urllib.parse
from pathlib import Path

POS_FAJL = "pos.sqlite"

_MIGRACIO_1 = """
CREATE TABLE forras_rekord (
    forras TEXT NOT NULL, forras_id TEXT NOT NULL, kezd TEXT, veg TEXT, tipus TEXT,
    payload TEXT NOT NULL, hash TEXT NOT NULL, importalva TEXT NOT NULL, import_futas INTEGER, torolve TEXT,
    PRIMARY KEY (forras, forras_id));
CREATE INDEX forras_rekord_kezd ON forras_rekord (forras, kezd);
CREATE TABLE import_futas (
    id INTEGER PRIMARY KEY, forras TEXT NOT NULL, kezdes TEXT NOT NULL, vege TEXT, allapot TEXT,
    uj INTEGER DEFAULT 0, valtozott INTEGER DEFAULT 0, torolt INTEGER DEFAULT 0, osszes INTEGER DEFAULT 0, uzenet TEXT);
CREATE TABLE naptar (
    azon TEXT PRIMARY KEY, nev TEXT NOT NULL, forras TEXT, forras_tipus TEXT, tipus TEXT, szin TEXT,
    kategoria TEXT NOT NULL, kategoria_forras TEXT NOT NULL,
    elso_latva TEXT, utoljara_latva TEXT, eltunt TEXT, utod TEXT);
CREATE TABLE naptar_valtozas (mikor TEXT NOT NULL, azon TEXT NOT NULL, fajta TEXT NOT NULL, regi TEXT, uj TEXT);
"""

_MIGRACIO_2 = """
CREATE TABLE tr_aktiv (nap TEXT NOT NULL, ut TEXT NOT NULL, tantargy TEXT NOT NULL, mp INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (nap, ut));
CREATE TABLE tr_karakter (nap TEXT NOT NULL, ut TEXT NOT NULL, tantargy TEXT NOT NULL,
    beszurt INTEGER NOT NULL DEFAULT 0, torolt INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (nap, ut));
CREATE TABLE tr_esemeny (id INTEGER PRIMARY KEY, mikor TEXT NOT NULL, nap TEXT NOT NULL, tipus TEXT NOT NULL,
    tantargy TEXT, ut TEXT, adat TEXT);
CREATE INDEX tr_esemeny_nap ON tr_esemeny (nap, tipus);
CREATE TABLE tr_naptar_blokk (azon TEXT PRIMARY KEY, nap TEXT NOT NULL, kezd TEXT, veg TEXT, kategoria TEXT,
    tantargy TEXT, forras TEXT);
CREATE TABLE has_parancs (nap TEXT NOT NULL, parancs TEXT NOT NULL, forras TEXT NOT NULL, db INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (nap, parancs, forras));
CREATE TABLE has_gepi (nap TEXT NOT NULL, funkcio TEXT NOT NULL, iras INTEGER NOT NULL DEFAULT 0,
    visszavonas INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (nap, funkcio));
CREATE TABLE has_kesleltetes (nap TEXT NOT NULL, fajta TEXT NOT NULL, vedro INTEGER NOT NULL,
    db INTEGER NOT NULL DEFAULT 0, max_ms REAL NOT NULL DEFAULT 0, PRIMARY KEY (nap, fajta, vedro));
CREATE TABLE has_szunet (nap TEXT NOT NULL, tipus TEXT NOT NULL, db INTEGER NOT NULL DEFAULT 0,
    mp INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (nap, tipus));
"""

# C29: az `emlekezteto` a jegyzet-feladat ↔ Apple Emlékeztető leképezés az utoljára szinkronizált állapottal
# (a háromutas összevetés alapja); az `emlekezteto_utkozes` az ütközések naplója (a jegyzet nyert); a
# `naptar_javaslat` a jóváhagyásra váró és eldöntött tanulásiblokk-javaslatok (`azon`: a javaslat természetes
# kulcsa, hogy ugyanaz ne készüljön újra az elvetés után sem).
_MIGRACIO_3 = """
CREATE TABLE emlekezteto (
    kulcs TEXT PRIMARY KEY, ut TEXT NOT NULL, elofordulas INTEGER NOT NULL DEFAULT 0, sor INTEGER,
    szoveg TEXT NOT NULL, hatarido TEXT NOT NULL,
    rem_azon TEXT, rem_kulso TEXT, rem_cim TEXT, rem_hatarido TEXT,
    jegyzet_kesz INTEGER NOT NULL DEFAULT 0, rem_kesz INTEGER NOT NULL DEFAULT 0,
    allapot TEXT NOT NULL DEFAULT 'aktiv', letrehozva TEXT NOT NULL, utolso TEXT);
CREATE INDEX emlekezteto_ut ON emlekezteto (ut);
CREATE TABLE emlekezteto_utkozes (
    id INTEGER PRIMARY KEY, mikor TEXT NOT NULL, kulcs TEXT NOT NULL, ut TEXT, szoveg TEXT,
    fajta TEXT NOT NULL, reszlet TEXT, latva TEXT);
CREATE TABLE naptar_javaslat (
    id INTEGER PRIMARY KEY, forras TEXT NOT NULL, azon TEXT NOT NULL UNIQUE, nap TEXT NOT NULL,
    kezd TEXT NOT NULL, veg TEXT NOT NULL, perc INTEGER NOT NULL, cim TEXT NOT NULL, tantargy TEXT, tema TEXT,
    indok TEXT, dolgozat TEXT, allapot TEXT NOT NULL DEFAULT 'uj', esemeny_azon TEXT, hiba TEXT,
    letrehozva TEXT NOT NULL, dontve TEXT);
"""

# C30a: az Asszisztens döntéseinek napi számlálója (a `has_*` család: használati mérés, a Tracker-kapcsoló alatt);
# `fajta`: emlites | szokas | higienia, `dontes`: elfogad | elutasit — jegyzetút és szöveg nincs benne.
_MIGRACIO_4 = """
CREATE TABLE has_asszisztens (nap TEXT NOT NULL, fajta TEXT NOT NULL, dontes TEXT NOT NULL,
    db INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (nap, fajta, dontes));
"""

# C30b (K205 (a)): az aktív másodpercek napszak-bontása a „szerda este matek” mintához. A `tr_*` család (a tracker az egyetlen író, a
# Tracker-kapcsoló alatt); a `tr_aktiv`-nál kisebb: **útvonal és szöveg nélkül**, csak a tantárgy; `ora` a helyi nap órája (0–23).
_MIGRACIO_5 = """
CREATE TABLE tr_aktiv_ora (nap TEXT NOT NULL, ora INTEGER NOT NULL, tantargy TEXT NOT NULL, mp INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (nap, ora, tantargy));
"""

MIGRACIOK = [_MIGRACIO_1, _MIGRACIO_2, _MIGRACIO_3, _MIGRACIO_4, _MIGRACIO_5]
VERZIO = len(MIGRACIOK)
# az ismert migrációk összes táblája (a migrációk szövegéből, hogy ne csússzon el): az újabb séma előre-kompatibilitásának
# próbája — a séma csak bővül (L56), tehát ezek egy újabb `user_version` mellett is megvannak
ISMERT_TABLAK = tuple(sorted({n for sql in MIGRACIOK for n in re.findall(r"CREATE TABLE (\w+)", sql)}))

_ZAR = threading.Lock()
_MASOLT: set[str] = set()      # azok a fájlok, amelyekre ebben a folyamatban a migráció előtti másolat már megvizsgálva/kész


def ut(cfg) -> Path:
    return cfg.path("szemelyes") / POS_FAJL


def _migracio_elott(cfg, p: Path) -> None:
    """33. döntés (C29.7b): egy MEGLÉVŐ, régebbi sémájú `pos.sqlite` léptetése előtt másolat a `{backup}` alá. Új fájl, friss
    vagy újabb séma nem kér másolatot; folyamatonként egyszer vizsgál (a tracker 30 s-onként ír). A másolat hibája
    nem akasztja a migrációt (a séma csak bővül, L56): stderr-jelzés, a migráció megy. A felhasználói adat a naptár-szinkron
    (1-es táblák) és a tracker tartalma — az 1-esről a 3-asra egy `iro` lépteti át."""
    kulcs = str(p)
    if kulcs in _MASOLT or not p.is_file():
        return
    _MASOLT.add(kulcs)
    try:
        con = sqlite3.connect(f"file:{urllib.parse.quote(kulcs)}?mode=ro", uri=True, timeout=5)
        try:
            v = con.execute("PRAGMA user_version").fetchone()[0]
        finally:
            con.close()
    except sqlite3.Error:
        return                                   # sérült/nem olvasható: a `connect` + `migral` majd a saját hibáját adja
    if not 0 < v < VERZIO:
        return
    try:
        from . import mentes                     # lusta: a `mentes` nem importálja a `szemelyes_db`-t, de így biztos
        mentes.migracio_elott(cfg, p, v)
    except (OSError, sqlite3.Error) as e:
        print(f"[migráció] a migráció előtti másolat nem készült el ({p.name}, v{v}): {e}", file=sys.stderr, flush=True)


def migral(c: sqlite3.Connection) -> None:
    """A séma léptetése az ismert migrációkig. Újabb `user_version`-nél (egy újabb app írta) nem dob és nem nyúl a
    sémához, ha az ismert táblák mind megvannak: a séma csak bővül (L56), így a régebbi kód a saját tábláiba
    ugyanúgy írhat — különben a tracker egy verzióugrástól kezdve minden eseményt csendben eldobna (T007)."""
    v = c.execute("PRAGMA user_version").fetchone()[0]
    if v > len(MIGRACIOK):
        van = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        hianyzik = [n for n in ISMERT_TABLAK if n not in van]
        if hianyzik:
            raise sqlite3.DatabaseError(f"a pos.sqlite sémája újabb ({v}), mint amit ez a verzió ismer, és hiányzó "
                                        f"táblák: {', '.join(hianyzik)}")
        return
    for i, sql in enumerate(MIGRACIOK[v:], start=v + 1):        # migrációnként egy atomi szkript
        c.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version={i};\nCOMMIT;")


@contextlib.contextmanager
def iro(cfg, *, biztonsagos: bool = False):
    """Író kapcsolat (létrehozza a fájlt, migrál, WAL); egy tranzakció, kivételnél visszagörget. `biztonsagos=True`:
    `secure_delete` — a törölt sorok tartalma a lapokon nullázódik (a felhasználó kérésére törlő hívások, T110)."""
    with _ZAR:
        p = ut(cfg)
        p.parent.mkdir(parents=True, exist_ok=True)
        _migracio_elott(cfg, p)
        c = sqlite3.connect(p, timeout=15, isolation_level=None)
        try:
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            if biztonsagos:
                c.execute("PRAGMA secure_delete=ON")
            c.execute("PRAGMA foreign_keys=ON")
            migral(c)
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
def olvaso(cfg, min_verzio: int = 1):
    """Csak olvasó kapcsolat, vagy `None`, ha nincs fájl vagy a séma még régebbi a `min_verzio`-nál (az olvasás
    semmit nem hoz létre és nem migrál)."""
    p = ut(cfg)
    if not p.exists():
        yield None
        return
    # T108: az út kódolt (`#`, `?`, `%`), különben a `?mode=ro` a fragmentbe esne, és az SQLite az út elejét nyitná írhatóan
    c = sqlite3.connect(f"file:{urllib.parse.quote(str(p))}?mode=ro", uri=True, timeout=5)
    try:
        c.row_factory = sqlite3.Row
        yield c if c.execute("PRAGMA user_version").fetchone()[0] >= min_verzio else None
    finally:
        c.close()


def _kiurit(c: sqlite3.Connection) -> bool:
    """A WAL kiürítése és lerövidítése; `False`, ha egy másik kapcsolat miatt nem sikerült (busy)."""
    return c.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] == 0


def tisztit(cfg) -> bool:
    """A törölt sorok maradványainak eltávolítása a fájlból (T110): a WAL kiürítése, `VACUUM` (a szabad lapok
    újraírása, a fájl összehúzása), újra a WAL kiürítése. Az írókkal ugyanazon a záron szerializálódik. `True`, ha a
    maradék biztosan eltűnt. A séma és a sorok tartalma nem változik (az explicit INTEGER PRIMARY KEY nélküli
    táblák rowid-jai igen változhatnak). Nem migrál, fájlt nem hoz létre."""
    with _ZAR:
        p = ut(cfg)
        if not p.exists():
            return True
        c = sqlite3.connect(p, timeout=15, isolation_level=None)
        try:
            c.execute("PRAGMA secure_delete=ON")
            elso = _kiurit(c)
            c.execute("VACUUM")
            return _kiurit(c) and elso
        finally:
            c.close()
