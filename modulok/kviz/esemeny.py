"""A `kviz_eredmeny` tracker-esemény adata (CLAUDE.md 30. döntés: a felület csak eseményt küld; a használati mérés
jegyzettartalmat és útvonalat nem tárol).

Az `adat` fehérlistás: csak számok és a kvíz azonosítója; a kérdés, a válasz, a szakasz és a jegyzet útja nem. Az esemény
`ut`-ja a **forrásjegyzet** (a tantárgyhoz, 30(f)); a core a kitöltés válaszában kész `tracker` objektumot ad
(`{ut, adat}`), a felület csak továbbítja a `trackerKliens.esemeny('kviz_eredmeny', ut, adat)`-tal, így a séma egyetlen helyen
él. A `core/tracker.py` `ADAT_SEMA["kviz_eredmeny"]`-ja ugyanezeket a kulcsokat és tartományokat tartalmazza (A3-05; a
`tests/test_kviz_esemeny.py` közös tesztje őrzi: a core által küldött adat az `adat_tisztit` után nem veszít kulcsot).
"""
from __future__ import annotations

from .formatum import AZON_RE

TIPUS = "kviz_eredmeny"
KULCSOK = ("kviz", "mod", "pont", "osszes", "szazalek", "tudja", "szerencses", "tevkepzet", "hiany", "ms")
KOTELEZO = KULCSOK[:-1]                       # az `ms` (a kitöltés ideje) nem kötelező
SZAM_MAX = 100_000                            # a darabszámok felső határa (a tracker sémájával egyező)
MS_MAX = 86_400_000                           # az `ms` felső határa (egy nap; a tracker sémájával egyező)
MODOK = ("teljes", "hibasak")


def adat(ertekeles: dict, kviz_azon: str) -> dict:
    """A tracker-esemény `adat`-a egy kiértékelt kitöltésből."""
    o = ertekeles["osszegzes"]
    m = o["matrix"]
    d = {"kviz": kviz_azon, "mod": ertekeles["mod"], "pont": o["pont"], "osszes": o["osszes"], "szazalek": o["szazalek"],
         "tudja": m["tudja"], "szerencses": m["szerencses"], "tevkepzet": m["tevkepzet"], "hiany": m["hiany"]}
    if isinstance(ertekeles.get("ido_ms"), int) and not isinstance(ertekeles["ido_ms"], bool) and ertekeles["ido_ms"] >= 0:
        d["ms"] = min(ertekeles["ido_ms"], MS_MAX)
    return d


def hibak(d: dict) -> list[str]:
    """A séma-sértések (üres: rendben)."""
    ki = [f"hiányzik: {k}" for k in KOTELEZO if k not in d]
    ki += [f"ismeretlen kulcs: {k}" for k in d if k not in KULCSOK]
    if "kviz" in d and not (isinstance(d["kviz"], str) and AZON_RE.match(d["kviz"])):
        ki.append("kviz: érvénytelen azonosító")
    if "mod" in d and d["mod"] not in MODOK:
        ki.append("mod: teljes vagy hibasak")
    for k in KULCSOK[2:]:
        felso = 100 if k == "szazalek" else MS_MAX if k == "ms" else SZAM_MAX
        if k in d and (isinstance(d[k], bool) or not isinstance(d[k], int) or not 0 <= d[k] <= felso):
            ki.append(f"{k}: nem negatív egész szám kell (legfeljebb {felso})")
    if isinstance(d.get("pont"), int) and isinstance(d.get("osszes"), int) and d["pont"] > d["osszes"]:
        ki.append("pont: nem lehet több az összesnél")
    return ki
