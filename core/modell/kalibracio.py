"""A kalibrációs tábla: `{router_db}` (`var/router.sqlite`), feladat × modell → pontszám.

Üresen indul (a chat döntése, 2026-09-30): „kalibrált” jelet csak a C18 aranyhalmazán, a C19-ben mért
modell kap (D9, kiterjesztve). Minden rögzítés a hozzáfűzős `kalibracio_naplo`-ba is bekerül; a
`kalibracio` a feladat × modell legutóbbi **érvényes** állása. A `hoalap` a hőfigyelés modellenkénti
token/s-alapszintje. Séma csak új migrációval (`PRAGMA user_version`), WAL (L57).

2-es migráció (C18.1): `ervenyes` oszlop mindkét táblában. Az érvénytelen mérés (a futtató érvényességi
kapuja szerint) csak a naplóba kerül, a `kalibracio` sorát nem írja felül; kalibrált jelet nem kaphat. A
migráció előtti sorok kapu nélkül születtek: `ervenyes = 0`, a megjegyzés elé „elavult (C18.1): ” kerül.
"""
from __future__ import annotations

import datetime as _dt
import sqlite3
import threading
from pathlib import Path
from typing import Callable

_SEMA = """
CREATE TABLE kalibracio (
  feladat TEXT NOT NULL,
  modell TEXT NOT NULL,
  pontszam REAL NOT NULL,
  datum TEXT NOT NULL,
  aranyhalmaz_verzio TEXT NOT NULL,
  kalibralt INTEGER NOT NULL DEFAULT 0,
  megjegyzes TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (feladat, modell)
);
CREATE TABLE kalibracio_naplo (
  sor INTEGER PRIMARY KEY AUTOINCREMENT,
  feladat TEXT NOT NULL, modell TEXT NOT NULL, pontszam REAL NOT NULL, datum TEXT NOT NULL,
  aranyhalmaz_verzio TEXT NOT NULL, kalibralt INTEGER NOT NULL, megjegyzes TEXT NOT NULL DEFAULT ''
);
CREATE TABLE hoalap (
  modell TEXT PRIMARY KEY,
  tps_alap REAL NOT NULL,
  mintak INTEGER NOT NULL,
  frissitve TEXT NOT NULL
);
"""


_MIGRACIO_2 = """
ALTER TABLE kalibracio ADD COLUMN ervenyes INTEGER NOT NULL DEFAULT 1;
ALTER TABLE kalibracio_naplo ADD COLUMN ervenyes INTEGER NOT NULL DEFAULT 1;
UPDATE kalibracio SET ervenyes = 0, megjegyzes = 'elavult (C18.1): ' || megjegyzes;
UPDATE kalibracio_naplo SET ervenyes = 0, megjegyzes = 'elavult (C18.1): ' || megjegyzes;
"""
# 3-as migráció (C19, T141): a mért modell pillanatképe (a HF-repó commit-sha-ja); a régi sorok üres értéket kapnak
_MIGRACIO_3 = (
    "ALTER TABLE kalibracio ADD COLUMN snapshot TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE kalibracio_naplo ADD COLUMN snapshot TEXT NOT NULL DEFAULT ''",
)
VERZIO = 3
MEZOK = ("feladat", "modell", "pontszam", "datum", "aranyhalmaz_verzio", "kalibralt", "megjegyzes", "ervenyes", "snapshot")


def vazlat(aranyhalmaz_verzio: str) -> bool:
    """Jóvá nem hagyott (`-vazlat` utótagú) aranyhalmaz-verzió (`modulok/eval/kozos/arany.py`)."""
    return str(aranyhalmaz_verzio).endswith("-vazlat")


def _most() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def megnyit(cfg) -> "Tabla":
    """A `{router_db}` a 33. döntés szerinti migráció előtti másolattal (`mentes.migracio_elott`)."""
    ut = cfg.path("router_db")

    def elotte(regi_verzio: int) -> None:
        from .. import mentes
        mentes.migracio_elott(cfg, ut, regi_verzio)
    return Tabla(ut, elotte=elotte)


class Tabla:
    def __init__(self, ut: Path, elotte: Callable[[int], None] | None = None):
        """`elotte(régi_verzió)`: a meglévő (≥ 1-es) adatbázis migrációja előtt fut (állapotmásolat); ha hibát dob, a
        migráció elmarad (33. döntés)."""
        Path(ut).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(ut, check_same_thread=False, isolation_level=None, timeout=30)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            v = self._db.execute("PRAGMA user_version").fetchone()[0]
            if 1 <= v < VERZIO and elotte is not None:
                elotte(v)
            if v < 1:
                self._db.executescript("BEGIN;" + _SEMA + "PRAGMA user_version=1; COMMIT;")
            if self._db.execute("PRAGMA user_version").fetchone()[0] < 2:
                self._db.executescript("BEGIN;" + _MIGRACIO_2 + "PRAGMA user_version=2; COMMIT;")
            self._db.execute("BEGIN IMMEDIATE")               # két folyamat (worker, eval) egyszerre nyithatja
            try:
                if self._db.execute("PRAGMA user_version").fetchone()[0] < 3:
                    for s in _MIGRACIO_3:
                        self._db.execute(s)
                    self._db.execute("PRAGMA user_version=3")
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def rogzit(self, feladat: str, modell: str, pontszam: float, aranyhalmaz_verzio: str,
               kalibralt: bool | None = None, megjegyzes: str = "", ervenyes: bool = True, snapshot: str = "") -> dict:
        """Érvényes mérés: napló + `kalibracio`. Érvénytelen: csak a napló (a C19 nem használhatja).

        A `kalibralt` háromállapotú: `True` felveszi a kalibrált jelet; `False` **kifejezetten leveszi** (CLI: `--kalibralt-le`);
        `None` (alap) **nem változtat**: ha a (feladat, modell) meglévő, érvényes sora ugyanerre az aranyhalmaz-verzióra már
        kalibrált, a jel megmarad (az újrapontozás ne vegye le a jóváhagyott jelet), különben a sor jel nélkül íródik. A
        naplósor a tényleges állapotot rögzíti."""
        if not feladat or not modell or not aranyhalmaz_verzio:
            raise ValueError("a feladat, a modell és az aranyhalmaz-verzió kötelező")
        if kalibralt and not ervenyes:
            raise ValueError("érvénytelen mérés nem kaphat kalibrált jelet")
        if kalibralt and vazlat(aranyhalmaz_verzio):
            raise ValueError(f"vázlat-aranyhalmazon ({aranyhalmaz_verzio}) mért sor nem kaphat kalibrált jelet: "
                             "előbb az aranyhalmaz jóváhagyása, utána újrapontozás")
        oszlopok = ", ".join(MEZOK)
        jelek = ",".join("?" * len(MEZOK))
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")          # a meglévő jel olvasása és az írás egy tranzakció
            try:
                jel = kalibralt
                if jel is None:
                    meglevo = self._db.execute(
                        "SELECT kalibralt, aranyhalmaz_verzio FROM kalibracio WHERE feladat=? AND modell=? AND ervenyes=1",
                        (feladat, modell)).fetchone()
                    jel = bool(ervenyes and meglevo and meglevo["kalibralt"] and meglevo["aranyhalmaz_verzio"] == aranyhalmaz_verzio
                               and not vazlat(aranyhalmaz_verzio))
                    if jel:
                        megjegyzes = (megjegyzes + "; " if megjegyzes else "") + "a kalibrált jel megmaradt (nem kért változtatást)"
                sor = (feladat, modell, float(pontszam), _most(), aranyhalmaz_verzio, int(bool(jel)), megjegyzes,
                       int(bool(ervenyes)), str(snapshot or ""))
                self._db.execute(f"INSERT INTO kalibracio_naplo ({oszlopok}) VALUES ({jelek})", sor)
                if ervenyes:
                    self._db.execute(f"INSERT OR REPLACE INTO kalibracio ({oszlopok}) VALUES ({jelek})", sor)
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
        return dict(zip(MEZOK, sor))

    def tabla(self, feladat: str | None = None) -> list[dict]:
        q, a = "SELECT * FROM kalibracio", ()
        if feladat:
            q, a = q + " WHERE feladat=?", (feladat,)
        with self._lock:
            return [dict(r) for r in self._db.execute(q + " ORDER BY feladat, pontszam DESC, modell", a)]

    def kalibralt_sorrend(self, feladat: str, verziok: Callable[[str], str | None] | None = None) -> list[dict]:
        """A feladat kalibrált és érvényes, jóváhagyott (nem `-vazlat`) aranyhalmazon mért modelljei, a legjobb elöl.

        `verziok` (`halmaz.Verziok`): router-feladat → az aranyhalmaz **aktuális** verziója; ha meg van adva, csak az ezen
        mért sor marad (a router szűrője, `Router.kalibralt_sorok`; a D9 írás-kapu és a „Kérdezz” kötése is ezt használja —
        az elavult verzión kalibrált sor ne menjen át). Ismeretlen aktuális verzió: nincs sor (zárva hibázik)."""
        with self._lock:
            sorok = [dict(r) for r in self._db.execute(
                "SELECT * FROM kalibracio WHERE feladat=? AND kalibralt=1 AND ervenyes=1 ORDER BY pontszam DESC, modell",
                (feladat,))]
        sorok = [s for s in sorok if not vazlat(s["aranyhalmaz_verzio"])]
        if verziok is None:
            return sorok
        aktualis = verziok(feladat)
        return [s for s in sorok if aktualis is not None and s["aranyhalmaz_verzio"] == aktualis]

    def hoalap(self, modell: str) -> float | None:
        with self._lock:
            r = self._db.execute("SELECT tps_alap FROM hoalap WHERE modell=?", (modell,)).fetchone()
        return r[0] if r else None

    def hoalap_ir(self, modell: str, tps: float, mintak: int) -> None:
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO hoalap VALUES (?,?,?,?)", (modell, float(tps), mintak, _most()))
