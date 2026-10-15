"""Az Asszisztens javaslatainak elfogadási statisztikája (C30a; CHATKALAUZ C30 4–5. pont, T064) és a belőle számolt küszöb.

**Tárolás**: a `pos.sqlite` `has_asszisztens(nap, fajta, dontes, db)` táblája (4-es migráció) — napi számláló, **útvonal és
szöveg nélkül**. Az írás a **tracker egyetlen írójával** megy (`Tracker._iro()`: migrál, WAL, egy tranzakció; saját
adatbázis-kapcsolat itt nincs), és **két kapcsoló alatt** áll: a Tracker-kapcsoló (a használati mérés) és az Asszisztens-
kapcsoló (10. és 27(c) döntés) is bekapcsolva kell; kikapcsolva nem ír, fájlt sem hoz létre. Az olvasás `mode=ro`
(`szemelyes_db.olvaso`), semmit nem hoz létre és nem migrál.

**Küszöb** (`kuszob`): a `kuszob_ablak_nap` napos ablak döntéseiből: kevés döntésből nincs következtetés (`alap`); alacsony
elfogadási arány → `szigoru` (a javaslat szigorúbb küszöbbel); nagyon alacsony, elég döntés után → `nema` (a fajta nem
javasol, amíg az ablak ki nem fut vagy a statisztikát nem törlik). A fogyasztó a szorzót a saját küszöbére alkalmazza.
"""
from __future__ import annotations

import sqlite3
from datetime import timedelta

from .. import szemelyes_db, vezerlo
from ..utvonalak import HttpError
from .beallitasok import beallitasok

FAJTAK = ("emlites", "szokas", "higienia")
DONTESEK = ("elfogad", "elutasit")
MIN_VERZIO = 4                      # a `has_asszisztens` a 4-es migrációban jött
ALAP_KUSZOB = {"szint": "alap", "szorzo": 1.0}
MAX_HASONLOSAG = 0.95               # a szigorúbb szorzó sem emeli a hasonlósági küszöböt a koszinusz-skála tetejére


class Statisztika:
    def __init__(self, cfg, tracker):
        self.cfg = cfg
        self.tr = tracker

    # -------------------------------------------------- kapcsolók

    def kapcsolok(self) -> dict[str, bool]:
        k = vezerlo.kapcsolok(self.cfg)
        return {"asszisztens": bool(k["asszisztens"]), "tracker": bool(k["tracker"])}

    # -------------------------------------------------- írás

    def rogzit(self, fajta, dontes) -> dict:
        """Egy döntés (a javaslat elfogadva vagy elutasítva). Érvénytelen fajta/döntés: 400. Kikapcsolt kapcsolónál
        `{fogadva: false, ok}`, és semmi nem íródik."""
        if fajta not in FAJTAK or dontes not in DONTESEK:
            raise HttpError(400, "a fajta emlites, szokas vagy higienia, a döntés elfogad vagy elutasit lehet")
        k = self.kapcsolok()
        if not k["asszisztens"]:
            return {"fogadva": False, "ok": "asszisztens_ki"}
        if not k["tracker"]:
            return {"fogadva": False, "ok": "tracker_ki"}
        try:
            with self.tr._iro() as c:
                c.execute("INSERT INTO has_asszisztens (nap, fajta, dontes, db) VALUES (?,?,?,1) "
                          "ON CONFLICT(nap, fajta, dontes) DO UPDATE SET db = db + 1", (self.tr.ma_nap(), fajta, dontes))
        except (sqlite3.Error, OSError) as e:
            self.tr._naploz("asszisztens", e)
            return {"fogadva": False, "ok": "hiba"}
        return {"fogadva": True}

    # -------------------------------------------------- olvasás

    def _ablak(self) -> tuple[str, str, int]:
        n = int(beallitasok(self.cfg)["kuszob_ablak_nap"])
        ma = self.tr.mikor().date()
        return (ma - timedelta(days=max(1, n) - 1)).isoformat(), ma.isoformat(), n

    def _szamok(self) -> dict[str, dict[str, int]]:
        """Az ablak döntései fajtánként: `{fajta: {elfogad, elutasit}}`; nincs fájl vagy tábla: nullák."""
        ki = {f: {d: 0 for d in DONTESEK} for f in FAJTAK}
        kezd, veg, _ = self._ablak()
        try:
            with szemelyes_db.olvaso(self.cfg, MIN_VERZIO) as c:
                if c is None:
                    return ki
                for r in c.execute("SELECT fajta, dontes, SUM(db) FROM has_asszisztens WHERE nap BETWEEN ? AND ? "
                                   "GROUP BY fajta, dontes", (kezd, veg)):
                    if r[0] in ki and r[1] in DONTESEK:
                        ki[r[0]][r[1]] = int(r[2])
        except sqlite3.Error as e:
            self.tr._naploz("asszisztens.olvasas", e)
        return ki

    def _kuszob(self, szamok: dict[str, int], b: dict) -> dict:
        db = szamok["elfogad"] + szamok["elutasit"]
        if db < b["kuszob_min_db"]:
            return dict(ALAP_KUSZOB)
        arany = szamok["elfogad"] / db
        if db >= b["kuszob_nema_db"] and arany < b["kuszob_nema"]:
            return {"szint": "nema", "szorzo": None}
        if arany < b["kuszob_alacsony"]:
            return {"szint": "szigoru", "szorzo": float(b["kuszob_szigoru_szorzo"])}
        return dict(ALAP_KUSZOB)

    def kuszob(self, fajta: str) -> dict:
        """A fajta küszöbe a döntésekből: `{szint: alap|szigoru|nema, szorzo}`. Kikapcsolt Tracker- vagy Asszisztens-kapcsolónál
        az alap (a tracker adatát kikapcsolva nem használjuk)."""
        k = self.kapcsolok()
        if fajta not in FAJTAK or not (k["asszisztens"] and k["tracker"]):
            return dict(ALAP_KUSZOB)
        return self._kuszob(self._szamok()[fajta], beallitasok(self.cfg))

    def hasonlosag_kuszob(self, kuszob: dict) -> float | None:
        """A linkjavaslat hasonlósági küszöbe (C30b; K205 (b)): a `[asszisztens] emlites_hasonlosag_kuszob` alap a küszöb szorzójával
        nő (szigorúbb küszöb → csak a közelebbi jegyzetek), legfeljebb `MAX_HASONLOSAG`; `nema` → `None` (nincs javaslat)."""
        if kuszob["szint"] == "nema":
            return None
        alap = max(0.0, float(beallitasok(self.cfg)["emlites_hasonlosag_kuszob"]))
        return round(min(MAX_HASONLOSAG, alap * float(kuszob.get("szorzo") or 1.0)), 4)

    def osszesit(self) -> dict:
        """A vezérlő nézete: fajtánként elfogadva/elutasítva/arány/küszöb az ablakban. Az `emlites` sor a linkjavaslat
        hasonlósági küszöbét (`hasonlosag_kuszob`) is hordozza: a szerkesztő ezt a hasonlóság-szűrőhöz használja."""
        b = beallitasok(self.cfg)
        k = self.kapcsolok()
        szamok = self._szamok()
        fajtak = {}
        for f in FAJTAK:
            e, u = szamok[f]["elfogad"], szamok[f]["elutasit"]
            fajtak[f] = {"elfogad": e, "elutasit": u, "db": e + u, "arany": round(e / (e + u), 4) if e + u else None,
                         "kuszob": self._kuszob(szamok[f], b) if k["asszisztens"] and k["tracker"] else dict(ALAP_KUSZOB)}
            if f == "emlites":
                fajtak[f]["hasonlosag_kuszob"] = self.hasonlosag_kuszob(fajtak[f]["kuszob"])
        return {"kapcsolo": k, "ablak_nap": int(b["kuszob_ablak_nap"]), "fajtak": fajtak,
                "osszes": {d: sum(szamok[f][d] for f in FAJTAK) for d in DONTESEK}}

    # -------------------------------------------------- törlés

    def torol(self) -> dict:
        """Az Asszisztens statisztikájának törlése (egy gomb): csak a `has_asszisztens`; `secure_delete`, utána a WAL kiürítése
        és `VACUUM` (a törölt sorok nem maradnak a szabad lapokon). Fájl nélkül nem hoz létre semmit."""
        try:
            with szemelyes_db.olvaso(self.cfg, MIN_VERZIO) as c:
                van = c is not None
            if not van:
                return {"torolt": 0, "tisztitva": True}
            with self.tr._iro(biztonsagos=True) as c:
                db = c.execute("DELETE FROM has_asszisztens").rowcount
        except (sqlite3.Error, OSError) as e:
            self.tr._naploz("asszisztens.torles", e)
            raise HttpError(503, "a statisztika adatbázisa nem írható") from e
        try:
            tisztitva = szemelyes_db.tisztit(self.cfg)
        except (sqlite3.Error, OSError) as e:
            self.tr._naploz("asszisztens.torles.tisztit", e)
            tisztitva = False
        return {"torolt": db, "tisztitva": tisztitva}
