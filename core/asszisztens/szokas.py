"""Szokásminta-javaslat a trackerből (C30a; TERV 5.10, CHATKALAUZ C30 3. pont): **a hét napja × tantárgy** a `tr_aktiv`-ból,
**legfeljebb heti egy** javaslat, modell nélkül. A **napszak** (C30b, K205 (a)) kiegészítés: a `tr_aktiv_ora` (nap × óra × tantárgy,
útvonal nélkül, az 5-ös migráció) alapján a javaslat megmondja, melyik napszakban szokott tanulni („szerda este matek”) — a
napszak a hét napja × tantárgy mintát csak finomítja (nélküle a javaslat változatlan), és külön javaslatot nem ad.

*Minta*: az utolsó `szokas_ablak_het` hét azonos napjai közül legalább `szokas_min_het` napon (a küszöb-szorzóval nőhet)
legalább `szokas_min_perc` percet töltött a tantárgyban, és ma még nem. A legtöbb alkalmú, azon belül a hosszabb átlagú
tantárgy nyer; az `Egyéb` kimarad. *Heti egy*: a kiadott javaslat az ISO-héttel az állapotfájlban él (újraindítás után
is); a döntés (elfogad/elutasít) a statisztikába kerül; figyelmen kívül hagyva a nap végén lejár, és a hét nem ad újat.
"""
from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta

from .. import szemelyes_db
from ..utvonalak import HttpError
from .allapot import Allapot
from .beallitasok import beallitasok
from .statisztika import DONTESEK, Statisztika

EGYEB = "Egyéb"
NAPOK = ("hétfő", "kedd", "szerda", "csütörtök", "péntek", "szombat", "vasárnap")
ONKENT = ("Hétfőnként", "Keddenként", "Szerdánként", "Csütörtökönként", "Péntekenként", "Szombatonként", "Vasárnaponként")
NAPON = ("hétfőn", "kedden", "szerdán", "csütörtökön", "pénteken", "szombaton", "vasárnap")
# C30b: a napszakok a helyi nap óráira (kezdet inkluzív, vég exkluzív); az éjszaka átível az éjfélen (a nap 22–24 és 0–5 órája)
NAPSZAKOK = (("reggel", 5, 9), ("délelőtt", 9, 12), ("délután", 12, 17), ("este", 17, 22), ("éjszaka", 22, 5))
ORA_VERZIO = 5                                  # a `tr_aktiv_ora` az 5-ös migrációban jött


def napszak_neve(ora: int) -> str:
    """A nap órájának (0–23) napszaka."""
    for nev, kezd, veg in NAPSZAKOK:
        if (kezd <= ora < veg) if kezd < veg else (ora >= kezd or ora < veg):
            return nev
    return NAPSZAKOK[-1][0]                     # elérhetetlen (a tartomány teljes), a típus-szigorúság kedvéért


def napszak_minta(ora_sorok, tantargy: str, datumok: list[str], min_mp: int, min_het: int) -> tuple[str, int] | None:
    """A tantárgy szokásos napszaka az ablak azonos hétköznapjain: `(napszak, hány napon)`. Egy nap akkor számít a napszakra, ha a
    tantárgyból ott legalább `min_mp` aktív másodpercet töltött; a napszak akkor „szokásos”, ha legalább `min_het` napon (a
    legtöbbön; döntetlennél a több aktív másodperc, majd a napszak sorrendje). `ora_sorok`: `(nap ISO, óra, tantárgy, mp)`."""
    if not ora_sorok:
        return None
    ablak = set(datumok)
    mp: dict[tuple[str, str], int] = defaultdict(int)
    for nap, ora, t, m in ora_sorok:
        if t == tantargy and nap in ablak:
            mp[(nap, napszak_neve(int(ora)))] += int(m)
    napok: dict[str, list[int]] = defaultdict(list)
    for (nap, nsz), m in mp.items():
        if m >= min_mp:
            napok[nsz].append(m)
    sorrend = [n for n, _, _ in NAPSZAKOK]
    jeloltek = sorted((-len(v), -sum(v), sorrend.index(nsz), nsz) for nsz, v in napok.items() if len(v) >= min_het)
    return (jeloltek[0][3], -jeloltek[0][0]) if jeloltek else None


def javaslat(sorok, ma: date, b: dict, szorzo: float = 1.0, ora_sorok=None) -> dict | None:
    """A mai napra illő minta. `sorok`: `(nap ISO, út, tantárgy, aktív mp)` a `tr_aktiv`-ból. Nincs minta: `None`.

    `ora_sorok` (C30b): `(nap ISO, óra, tantárgy, aktív mp)` a `tr_aktiv_ora`-ból — ha elég adat van, a javaslat a szokásos napszakot
    is megnevezi (`napszak`, `napszak_hit`), különben ezek `None` és a szöveg a napszak nélküli (C30a) marad."""
    het, min_mp = int(b["szokas_ablak_het"]), int(b["szokas_min_perc"]) * 60
    min_het = max(1, math.ceil(b["szokas_min_het"] * (szorzo or 1.0)))
    datumok = [(ma - timedelta(days=7 * k)).isoformat() for k in range(1, het + 1)]
    ma_s = ma.isoformat()
    nap_mp: dict[tuple[str, str], int] = defaultdict(int)
    jegyzetek: dict[str, list] = defaultdict(list)
    for nap, ut, tantargy, mp in sorok:
        if not tantargy or tantargy == EGYEB:
            continue
        nap_mp[(nap, tantargy)] += int(mp)
        if nap < ma_s:
            jegyzetek[tantargy].append((nap, int(mp), ut))
    jeloltek = []
    for tantargy in {t for _, t in nap_mp}:
        napok = [d for d in datumok if nap_mp.get((d, tantargy), 0) >= min_mp]
        if len(napok) < min_het or nap_mp.get((ma_s, tantargy), 0) >= min_mp:
            continue
        atlag = round(sum(nap_mp[(d, tantargy)] for d in napok) / len(napok) / 60)
        jeloltek.append((-len(napok), -atlag, tantargy))
    if not jeloltek:
        return None
    jeloltek.sort()
    db, atlag, tantargy = -jeloltek[0][0], -jeloltek[0][1], jeloltek[0][2]
    legutobbi = max(jegyzetek[tantargy], default=None)         # (nap, mp, út): a legfrissebb nap, azon belül a több perc
    nap_nev = NAPOK[ma.weekday()]
    nev = b["tantargy_nevek"].get(tantargy, tantargy)
    nsz = napszak_minta(ora_sorok, tantargy, datumok, min_mp, min_het) if b.get("szokas_napszak", True) else None
    napszak, napszak_hit = nsz if nsz else (None, None)
    mikor = f"{napszak} " if napszak else ""
    reszlet = f", ebből {napszak_hit} {napszak}" if napszak else ""
    return {
        "tantargy": tantargy, "tantargy_nev": nev, "het_nap": ma.weekday(), "nap_neve": nap_nev, "hit": db, "het": het,
        "atlag_perc": atlag, "legutobbi_ut": legutobbi[2] if legutobbi else None,
        "napszak": napszak, "napszak_hit": napszak_hit,
        "szoveg": f"{ONKENT[ma.weekday()]} általában {mikor}tanulsz (tantárgy: {nev}) — az utolsó {het} hétből {db} "
                  f"{NAPON[ma.weekday()]}, átlag ~{atlag} perc{reszlet}. Ma még nem.",
    }


class Szokasok:
    """A heti javaslat szolgáltatása: lusta kiértékelés (a „Ma” oldal kérésére), az állapotfájlban rögzítve."""

    def __init__(self, cfg, tracker, statisztika: Statisztika, allapot: Allapot, mikor=datetime.now):
        self.cfg = cfg
        self.tr = tracker
        self.st = statisztika
        self.allapot = allapot
        self.mikor = mikor

    @staticmethod
    def _het(ma: date) -> str:
        iso = ma.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"

    @staticmethod
    def _publikus(r: dict) -> dict:
        return {**r["javaslat"], "azon": r["azon"], "allapot": r["allapot"], "het": r["het"], "nap": r["nap"]}

    def _sorok(self, ma: date, b: dict) -> list[tuple]:
        kezd = (ma - timedelta(days=7 * int(b["szokas_ablak_het"]))).isoformat()
        try:
            with self.tr._olvaso() as c:
                if c is None:
                    return []
                return [tuple(r) for r in c.execute("SELECT nap, ut, tantargy, mp FROM tr_aktiv WHERE nap BETWEEN ? AND ?",
                                                    (kezd, ma.isoformat()))]
        except sqlite3.Error as e:
            self.tr._naploz("szokas.olvasas", e)
            return []

    def _ora_sorok(self, ma: date, b: dict) -> list[tuple]:
        """A `tr_aktiv_ora` sorai az ablakra (C30b); nincs fájl / még nincs 5-ös séma / hiba: üres (a napszak nélküli minta)."""
        kezd = (ma - timedelta(days=7 * int(b["szokas_ablak_het"]))).isoformat()
        try:
            with szemelyes_db.olvaso(self.cfg, ORA_VERZIO) as c:
                if c is None:
                    return []
                return [tuple(r) for r in c.execute("SELECT nap, ora, tantargy, mp FROM tr_aktiv_ora WHERE nap BETWEEN ? AND ?",
                                                    (kezd, ma.isoformat()))]
        except sqlite3.Error as e:
            self.tr._naploz("szokas.napszak", e)
            return []

    def aktualis(self) -> dict | None:
        """A mai javaslat, vagy `None` (nincs minta, már döntöttek / lejárt, a küszöb néma, kikapcsolt kapcsoló)."""
        k = self.st.kapcsolok()
        if not (k["asszisztens"] and k["tracker"]):
            return None
        ma = self.mikor().date()
        het = self._het(ma)
        r = self.allapot.olvas().get("szokas")
        if isinstance(r, dict) and r.get("het") == het:
            return self._publikus(r) if r.get("allapot") == "uj" and r.get("nap") == ma.isoformat() else None
        kuszob = self.st.kuszob("szokas")
        if kuszob["szint"] == "nema":
            return None
        b = beallitasok(self.cfg)
        ora_sorok = self._ora_sorok(ma, b) if b["szokas_napszak"] else None
        j = javaslat(self._sorok(ma, b), ma, b, kuszob["szorzo"] or 1.0, ora_sorok)
        if j is None:
            return None
        rekord = {"het": het, "nap": ma.isoformat(), "azon": f"szokas:{het}:{j['tantargy']}", "allapot": "uj", "javaslat": j}
        self.allapot.modosit(lambda d: d.update(szokas=rekord))
        return self._publikus(rekord)

    def dontes(self, azon, dontes) -> dict:
        """A javaslat elfogadása vagy elutasítása: a statisztikába kerül, és a hét többi részében nincs új javaslat."""
        if dontes not in DONTESEK:
            raise HttpError(400, "a döntés elfogad vagy elutasit lehet")
        r = self.allapot.olvas().get("szokas")
        if not isinstance(r, dict) or r.get("azon") != azon:
            raise HttpError(404, "nincs ilyen javaslat")
        if r.get("allapot") != "uj":
            raise HttpError(409, "a javaslatról már döntöttek")
        statisztika = self.st.rogzit("szokas", dontes)
        self.allapot.modosit(lambda d: d["szokas"].update(allapot="elfogadva" if dontes == "elfogad" else "elutasitva"))
        return {"ok": True, "statisztika": statisztika}
