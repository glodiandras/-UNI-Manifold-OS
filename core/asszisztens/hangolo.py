"""Az Asszisztens önhangoló gyakorisága (J1; ESZREVETELEK-TERV 2. fejezet 3–4. pont, 80(b) döntés).

Minden javaslat-fajta (`tipus`: kiegészítés, szerkezet, ismétlődő művelet, tartalmi kiegészítés, link) és helyzet (`helyzet`:
rövid, kódolt jel, pl. `folytat`, `szunet_rovid`) saját elfogadás/elutasítás-számlálót kap a `{state}/asszisztens.json`
`hangolas` kulcsa alatt: **útvonal és szöveg nélkül**, csak a fajta, a helyzet és két lebegőpontos szám. A számláló idővel
felére kopik (`hangolas_felezes_nap`), így a régi döntés súlya csökken, és egy elnémult fajta hosszú csend után óvatosan
visszatérhet.

**A becslés** két szintű: a fajta egészének aránya optimista előzetessel (2 elfogadás : 1 elutasítás — *kezdetben bátrabb*),
a helyzeté a fajtáéra húzva (`K` döntésnyi súllyal). Ebből:

* `szorzo` — a várakozás szorzója (0,6–8): a sokat elfogadott helyzetben gyakrabban, az elutasítottban ritkábban jön javaslat;
* `szint` — `batrabb` | `alap` | `ritkabb` | `nema`; **néma**, ha a helyzetben legalább `hangolas_nema_db` (súlyozott) döntés
  van, és az elfogadás aránya `hangolas_nema_arany` alatti — vagy a fajta egészére igaz ugyanez kétszer annyi döntésből.

A kifejezett elutasítás (Esc, „Nem”) teljes súllyal, a figyelmen kívül hagyott javaslat (átírta, nem döntött) `IMPLICIT_SULY`
súllyal számít. A hangolás tanult adat: a „Mit tanult az asszisztens” listán látszik, egyenként törölhető, a vaultba nem ír.
Kikapcsolt Asszisztensnél a hívó nem rögzít (a kapcsolót a hívó nézi).
"""
from __future__ import annotations

import re
import time

from ..utvonalak import HttpError
from .allapot import Allapot
from .beallitasok import beallitasok

TIPUSOK = ("kiegeszites", "szerkezet", "muvelet", "tartalom", "link")
TIPUS_NEV = {"kiegeszites": "szövegkiegészítés", "szerkezet": "jegyzetszerkezet", "muvelet": "ismétlődő művelet",
             "tartalom": "kapcsolódó jegyzet", "link": "linkjavaslat"}
DONTESEK = ("elfogad", "elutasit", "figyelmen_kivul")
IMPLICIT_SULY = 0.3
ELOZETES_E, ELOZETES_U = 2.0, 1.0      # optimista előzetes: kezdetben bátrabb
HELYZET_SULY = 3.0                     # a helyzet becslése ennyi döntésnyi súllyal húzódik a fajtáéhoz
MAX_KULCS = 200
_HELYZET = re.compile(r"^[a-z0-9_]{1,40}$")


def kulcs(tipus: str, helyzet: str) -> str:
    return f"{tipus}|{helyzet}"


def ervenyes(tipus, helyzet) -> None:
    if tipus not in TIPUSOK:
        raise HttpError(400, f"ismeretlen javaslat-fajta: {tipus!r}")
    if not isinstance(helyzet, str) or not _HELYZET.match(helyzet):
        raise HttpError(400, "a helyzet rövid, kisbetűs azonosító (a–z, 0–9, _)")


class Hangolo:
    def __init__(self, cfg, allapot: Allapot, ido=time.time):
        self.cfg = cfg
        self.allapot = allapot
        self.ido = ido

    # -------------------------------------------------- kopás

    def _kopas(self, t: float, most: float) -> float:
        nap = max(0.1, float(beallitasok(self.cfg)["hangolas_felezes_nap"]))
        return 0.5 ** (max(0.0, most - float(t)) / (nap * 86400.0))

    def _szamlalok(self, d: dict | None = None) -> dict[str, tuple[float, float]]:
        """A kopással korrigált számlálók: `{kulcs: (elfogad, elutasit)}`; a hibás bejegyzés kimarad."""
        d = self.allapot.olvas() if d is None else d
        h = d.get("hangolas")
        most = self.ido()
        ki = {}
        if not isinstance(h, dict):
            return ki
        for k, v in h.items():
            if not isinstance(k, str) or "|" not in k or not isinstance(v, dict):
                continue
            try:
                f = self._kopas(v.get("t", most), most)
                ki[k] = (max(0.0, float(v.get("e", 0))) * f, max(0.0, float(v.get("u", 0))) * f)
            except (TypeError, ValueError):
                continue
        return ki

    # -------------------------------------------------- írás

    def rogzit(self, tipus, helyzet, dontes, *, kifejezett: bool = True) -> dict:
        """Egy döntés: `elfogad`, `elutasit` vagy `figyelmen_kivul` (az utóbbi az elutasítás kis súllyal). → az új állás."""
        ervenyes(tipus, helyzet)
        if dontes not in DONTESEK:
            raise HttpError(400, "a döntés elfogad, elutasit vagy figyelmen_kivul lehet")
        suly = 1.0 if (kifejezett and dontes != "figyelmen_kivul") else IMPLICIT_SULY
        k = kulcs(tipus, helyzet)
        most = self.ido()

        def ir(d):
            h = d.get("hangolas") if isinstance(d.get("hangolas"), dict) else {}
            sz = self._szamlalok({"hangolas": h})
            e, u = sz.get(k, (0.0, 0.0))
            if dontes == "elfogad":
                e += suly
            else:
                u += suly
            h = {kk: vv for kk, vv in h.items() if kk in sz}
            h[k] = {"e": round(e, 4), "u": round(u, 4), "t": most}
            if len(h) > MAX_KULCS:      # a legrégebben használt helyzetek esnek ki
                for regi in sorted(h, key=lambda x: h[x].get("t", 0))[:len(h) - MAX_KULCS]:
                    h.pop(regi, None)
            d["hangolas"] = h
        self.allapot.modosit(ir)
        return self.allas(tipus, helyzet)

    def torol(self, k: str) -> bool:
        van = k in (self.allapot.olvas().get("hangolas") or {})
        if van:
            self.allapot.modosit(lambda d: (d.get("hangolas") or {}).pop(k, None))
        return van

    def torol_mind(self) -> None:
        self.allapot.modosit(lambda d: d.update(hangolas={}))

    # -------------------------------------------------- becslés

    def allas(self, tipus, helyzet) -> dict:
        """A fajta és a helyzet állása: `{szint, szorzo, arany, db}` (`szorzo` `None`, ha néma)."""
        ervenyes(tipus, helyzet)
        b = beallitasok(self.cfg)
        sz = self._szamlalok()
        et = sum(e for k, (e, _) in sz.items() if k.split("|", 1)[0] == tipus)
        nt = sum(e + u for k, (e, u) in sz.items() if k.split("|", 1)[0] == tipus)
        eh, uh = sz.get(kulcs(tipus, helyzet), (0.0, 0.0))
        nh = eh + uh
        p_t = (et + ELOZETES_E) / (nt + ELOZETES_E + ELOZETES_U)
        p_h = (eh + HELYZET_SULY * p_t) / (nh + HELYZET_SULY)
        nema_db, nema_arany = float(b["hangolas_nema_db"]), float(b["hangolas_nema_arany"])
        # a kopás miatt a frissen rögzített döntés is 1-nél parányit kevesebb: a küszöb-összevetés kerekítve
        nema = (round(nh, 3) >= nema_db and eh / nh < nema_arany) or (round(nt, 3) >= 2 * nema_db and et / nt < nema_arany)
        ki = {"tipus": tipus, "helyzet": helyzet, "arany": round(p_h, 4), "db": round(nh, 2)}
        if nema:
            return {**ki, "szint": "nema", "szorzo": None}
        szorzo = min(8.0, max(0.6, 0.5 / max(p_h, 1e-6)))
        szint = "batrabb" if p_h >= 0.55 else "alap" if p_h >= 0.3 else "ritkabb"
        return {**ki, "szint": szint, "szorzo": round(szorzo, 3)}

    def lista(self) -> list[dict]:
        """A „Mit tanult” lista hangolás-sorai: helyzetenként a (kopott) számlálók és az állás."""
        ki = []
        for k, (e, u) in sorted(self._szamlalok().items()):
            tipus, helyzet = k.split("|", 1)
            if tipus not in TIPUSOK or not _HELYZET.match(helyzet):
                continue
            a = self.allas(tipus, helyzet)
            ki.append({"kulcs": k, "tipus": tipus, "tipus_nev": TIPUS_NEV[tipus], "helyzet": helyzet,
                       "elfogad": round(e, 1), "elutasit": round(u, 1), "szint": a["szint"]})
        return ki
