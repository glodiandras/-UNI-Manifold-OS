"""A tanulási adatbázis (`[utak] tanulas_db`, alapból `{var}/tanulas.sqlite`) közös rétege: a séma-migrációk és az
író/olvasó kapcsolat (C23a; a C22a kvíze a 2-es migrációval bővítette).

A `szemelyes_db` mintája (L56–L57 elve): a séma csak új migrációval bővül (`PRAGMA user_version`), WAL, a migrációk
atomi szkriptek, és egy újabb app sémáját a régebbi kód nem bántja, ha az ismert táblák megvannak (T007 tanulsága).

- 1-es: `kartya` (azonosító → FSRS-állapot és a szöveg gyorsítótára), `valasz` (a válasznapló), `sirko` (a törölt
  kártyák ujjlenyomata: a generálás nem hozza vissza őket), `apkg_kulcs` (az idegen `.apkg`-pakli újraimportja
  nem duplikál) — `docs/C23-TERV.md` 2. fejezet.
- 2-es (C22a): `kviz_kitoltes` (egy kitöltés összegzése és elemzése; a `kulcs` egyedi: az újraküldött kitöltés nem
  duplikál), `kviz_valasz` (kérdésenként a válasz, a tipp és a kategória), `kviz_jeloles` („hibás a kérdés”) — a kvíz
  maga a vaultban él, itt csak az eredményei; `docs/C22-TERV.md` 4. fejezet.

**Migráció előtt mentés** (33. döntés, A3-06): egy létező, már használt adatbázis (`user_version` ≥ 1) sémaváltása előtt
a `tanulas.sqlite` önálló, konzisztens másolata készül (`mentes.migracio_elott`: `VACUUM INTO`, fájlonkénti rotáció) —
nem a közös `mentes.allapot_masolat`, amely a készülő másik másolatot törölné, a közös rotációban kifutna, és más fájl
hibája miatt megállítaná ezt a migrációt; ha a másolat nem sikerül, a migráció elmarad — a tanulási történet mentés
nélkül nem kerül sémaváltás alá. A migrációt **fájlzár** védi (`{db}.migracio.lock`, `flock`): a core és a `bin/mos
kartya` két folyamatként ne fusson egyszerre ugyanabba a sémaváltásba. Az olvasó semmit nem hoz létre és nem migrál.
"""
from __future__ import annotations

import contextlib
import fcntl
import os
import re
import sqlite3
import threading
import urllib.parse
from pathlib import Path

_MIGRACIO_1 = """
CREATE TABLE kartya (
    azon TEXT PRIMARY KEY, jegyzet TEXT, sor INTEGER, forras TEXT,
    kerdes TEXT NOT NULL DEFAULT '', valasz TEXT NOT NULL DEFAULT '', szoveg_hash TEXT,
    eredet TEXT NOT NULL DEFAULT 'kezi',
    letrehozva TEXT NOT NULL, utoljara_latva TEXT, szoveg_valtozott TEXT, torolve TEXT,
    felfuggesztve INTEGER NOT NULL DEFAULT 0,
    allapot INTEGER NOT NULL DEFAULT 0, lepes INTEGER, stabilitas REAL, nehezseg REAL,
    esedekes TEXT, utolso TEXT);
CREATE INDEX kartya_esedekes ON kartya (torolve, felfuggesztve, allapot, esedekes);
CREATE INDEX kartya_jegyzet ON kartya (jegyzet);
CREATE TABLE valasz (
    id INTEGER PRIMARY KEY, kartya TEXT NOT NULL, mikor TEXT NOT NULL,
    jegy INTEGER NOT NULL CHECK (jegy BETWEEN 1 AND 4), ms INTEGER,
    forras TEXT NOT NULL DEFAULT 'ismetles', elotte TEXT, utana TEXT, visszavonva TEXT);
CREATE INDEX valasz_kartya ON valasz (kartya, mikor);
CREATE TABLE sirko (ujjlenyomat TEXT PRIMARY KEY, kartya TEXT, mikor TEXT NOT NULL);
CREATE TABLE apkg_kulcs (guid TEXT NOT NULL, ord INTEGER NOT NULL, kartya TEXT NOT NULL, PRIMARY KEY (guid, ord));
"""

_MIGRACIO_2 = """
CREATE TABLE kviz_kitoltes (
    id INTEGER PRIMARY KEY,
    kulcs TEXT NOT NULL UNIQUE,
    kviz TEXT NOT NULL, kviz_ut TEXT, forras TEXT, modell TEXT, szoveg_hash TEXT,
    mikor TEXT NOT NULL,
    mod TEXT NOT NULL DEFAULT 'teljes' CHECK (mod IN ('teljes', 'hibasak')),
    pont INTEGER NOT NULL, osszes INTEGER NOT NULL, szazalek INTEGER NOT NULL, ido_ms INTEGER,
    elemzes TEXT NOT NULL);
CREATE INDEX kviz_kitoltes_kviz ON kviz_kitoltes (kviz, mikor);
CREATE TABLE kviz_valasz (
    kitoltes INTEGER NOT NULL REFERENCES kviz_kitoltes (id), kerdes TEXT NOT NULL,
    valasz INTEGER,
    helyes INTEGER NOT NULL, tipp INTEGER NOT NULL,
    kategoria TEXT NOT NULL CHECK (kategoria IN ('tudja', 'szerencses', 'tevkepzet', 'hiany')),
    ms INTEGER, jelolt INTEGER NOT NULL DEFAULT 0, szakasz TEXT, horgony TEXT,
    PRIMARY KEY (kitoltes, kerdes));
CREATE TABLE kviz_jeloles (
    kviz TEXT NOT NULL, kerdes TEXT NOT NULL, mikor TEXT NOT NULL, megjegyzes TEXT,
    PRIMARY KEY (kviz, kerdes));
"""

MIGRACIOK = [_MIGRACIO_1, _MIGRACIO_2]
_ZAR = threading.Lock()


def ismert_tablak(migraciok: list[str] | None = None) -> tuple[str, ...]:
    """Az ismert migrációk összes táblája (a szövegükből, hogy ne csússzon el)."""
    return tuple(sorted({n for sql in (migraciok or MIGRACIOK) for n in re.findall(r"CREATE TABLE (\w+)", sql)}))


def ut(cfg) -> Path:
    return cfg.path("tanulas_db")


def _verzio(c: sqlite3.Connection) -> int:
    return c.execute("PRAGMA user_version").fetchone()[0]


def migral(c: sqlite3.Connection, elotte=None) -> None:
    """A séma léptetése az ismert migrációkig. `elotte(régi_verzió)`: a használt (≥ 1) adatbázis sémaváltása előtt hívódik
    (a mentés); ha dob, a migráció elmarad. Újabb `user_version`-nél nem dob és nem nyúl a sémához, ha az ismert
    táblák megvannak (a séma csak bővül)."""
    migraciok = MIGRACIOK
    v = _verzio(c)
    if v > len(migraciok):
        van = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        hianyzik = [n for n in ismert_tablak(migraciok) if n not in van]
        if hianyzik:
            raise sqlite3.DatabaseError(f"a tanulas.sqlite sémája újabb ({v}), mint amit ez a verzió ismer, és "
                                        f"hiányzó táblák: {', '.join(hianyzik)}")
        return
    if v == len(migraciok):
        return
    if v >= 1 and elotte is not None:
        try:
            elotte(v)
        except Exception as e:      # noqa: BLE001 — bármilyen mentési hiba megállítja a migrációt
            raise sqlite3.DatabaseError(f"a tanulas.sqlite migrációja elmaradt: a mentés előtte nem sikerült ({e})") from e
    for i, sql in enumerate(migraciok[v:], start=v + 1):        # migrációnként egy atomi szkript
        c.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version={i};\nCOMMIT;")


def _mentes_elotte(cfg):
    def ment(regi_verzio: int) -> None:
        from core import mentes
        mentes.migracio_elott(cfg, ut(cfg), regi_verzio)
    return ment


def migracio_zar_ut(cfg) -> Path:
    p = ut(cfg)
    return p.with_name(p.name + ".migracio.lock")


@contextlib.contextmanager
def _migracios_zar(cfg):
    """Folyamatok közti kizárás a sémaváltásra (a szálak közt a `_ZAR` véd). A fájl a lezáráskor szabadul."""
    fd = os.open(migracio_zar_ut(cfg), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


@contextlib.contextmanager
def iro(cfg):
    """Író kapcsolat (létrehozza a fájlt, migrál, WAL); egy tranzakció, kivételnél visszagörget."""
    with _ZAR:
        p = ut(cfg)
        p.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(p, timeout=15, isolation_level=None)
        try:
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA foreign_keys=ON")
            if _verzio(c) < len(MIGRACIOK):
                with _migracios_zar(cfg):                  # a verziót a zár alatt a `migral` újraolvassa
                    migral(c, _mentes_elotte(cfg))
            else:
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
    c = sqlite3.connect(f"file:{urllib.parse.quote(str(p))}?mode=ro", uri=True, timeout=5)   # T108: kódolt út
    try:
        c.row_factory = sqlite3.Row
        yield c if _verzio(c) >= min_verzio else None
    finally:
        c.close()
