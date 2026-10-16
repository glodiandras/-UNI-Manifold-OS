"""A kalibrált jel használati küszöbei a kódban (F6; az 5. audit §1.2/6. pontja, R2).

A v2-ben a küszöb csak dokumentum volt (`docs/MERES-2026-10-07.md` 3. fejezet, K298, K431), a jelet ember adta. A termékben a
„Test this model” folyamat automatikusan ad jelet, ezért a küszöb **a kódban él és kikényszerített**: az `eval.rogzit` (a jel egyetlen
éles írója: a CLI és a „Test this model”) ellenőrzi; a `kalibracio.Tabla` tárolási primitív marad. A konfiguráció (`config/models.toml [kalibracio.<feladat>]`) a küszöböt csak
**szigoríthatja** (magasabb `kuszob`, nagyobb `min_tetel`), lazítani nem tud: a hatályos érték `max(kód, konfig)`.

Feladat küszöb nélkül (`kuszob = None`: `atirat`, `tema`, `kotes`, `osztalyozas`): kalibrált jel **nem adható** (zárva hibázik),
amíg a felhasználó/koordinátor egy mért küszöböt ide fel nem vesz.

`min_tetel`: a teljes halmaz legkisebb tételszáma; a saját (felhasználói) halmaznak is ennyi kell, különben egy mini-halmaz bármit
átengedne (az audit §2.2). `reszpont`: további feltételek az értékelés egy mezőjére (pl. a `kod` `hiba` módjának részpontja).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Kuszob:
    kuszob: float | None                         # a pontszám alsó határa; None: jel nem adható
    min_tetel: int = 20
    reszpont: dict = field(default_factory=dict)  # "modok.hiba" → alsó határ (pontozott úton az értékelésben)
    forras: str = ""                             # honnan jön a szám (a döntés azonosítója)


ALAP: dict[str, Kuszob] = {
    "ocr_keplet": Kuszob(0.90, 20, forras="MERES-2026-10-07 §3"),
    "ocr_kezi": Kuszob(0.60, 20, forras="MERES-2026-10-07 §3"),
    "fuzet_fejezet": Kuszob(0.897, 20, forras="MERES-2026-10-07 §3 (a legacy 87/97)"),
    "fuzet_valaszto": Kuszob(0.897, 20, forras="MERES-2026-10-07 §3 (a legacy 87/97)"),
    "szoveg": Kuszob(0.40, 20, forras="MERES-2026-10-07 §3"),
    "kviz": Kuszob(0.40, 20, forras="MERES-2026-10-07 §3"),
    "matek": Kuszob(0.75, 20, forras="MERES-2026-10-07 §3"),
    "matek_cas": Kuszob(0.75, 20, forras="MERES-2026-10-07 §3 (a matek küszöbe)"),
    "grafikon": Kuszob(0.75, 15, forras="MERES-2026-10-07 §3"),
    "matek_ellenorzo": Kuszob(0.80, 20, forras="MERES-2026-10-07 §3"),
    "beagyazas": Kuszob(0.80, 20, forras="MERES-2026-10-07 §3 (recall@5)"),
    "rerank": Kuszob(0.80, 20, forras="MERES-2026-10-07 §3 (MRR)"),
    "kod": Kuszob(0.60, 20, {"modok.hiba": 0.5}, forras="K298"),
    "kiegeszites": Kuszob(0.70, 12, forras="K431 (javaslat)"),
    "kifejtes": Kuszob(0.70, 12, forras="K431 (javaslat)"),
    "osszefoglal_kijeloles": Kuszob(0.70, 12, forras="K431 (javaslat)"),
    "atirat": Kuszob(None, 10, forras="nincs mért küszöb"),
    "tema": Kuszob(None, 20, forras="nincs mért küszöb"),
    "kotes": Kuszob(None, 20, forras="nincs mért küszöb"),
    "osztalyozas": Kuszob(None, 20, forras="nincs aranyhalmaz"),
}


def hatalyos(feladat: str, konfig: dict | None = None) -> Kuszob | None:
    """A feladat hatályos küszöbe: a kód értéke, a konfig (`[kalibracio.<feladat>]`) csak szigoríthat. Ismeretlen feladat: None."""
    alap = ALAP.get(feladat)
    if alap is None:
        return None
    k = dict((konfig or {}).get(feladat) or {})
    kuszob = alap.kuszob
    if kuszob is not None and isinstance(k.get("kuszob"), (int, float)) and not isinstance(k.get("kuszob"), bool):
        kuszob = max(kuszob, float(k["kuszob"]))
    min_tetel = alap.min_tetel
    if isinstance(k.get("min_tetel"), int) and not isinstance(k.get("min_tetel"), bool):
        min_tetel = max(min_tetel, int(k["min_tetel"]))
    return Kuszob(kuszob, min_tetel, dict(alap.reszpont), alap.forras)


def _mezo(ert: dict, ut: str):
    x = ert
    for r in ut.split("."):
        if not isinstance(x, dict) or r not in x:
            return None
        x = x[r]
    return x


def dont(feladat: str, ert: dict, konfig: dict | None = None) -> dict:
    """Az értékelés (`eval.ertekel` kimenete) a küszöbhöz mérve → `{kalibralhato, kuszob, min_tetel, okok: [{kod, param}]}`.

    Csak a küszöb-kaput nézi (pontszám, tételszám, részpontok); a teljesség, az érvényesség és a jóváhagyott arany a hívó
    (`eval.rogzit`) dolga. Ismeretlen vagy küszöb nélküli feladat: nem kalibrálható (zárva hibázik)."""
    k = hatalyos(feladat, konfig)
    okok: list[dict] = []
    if k is None or k.kuszob is None:
        okok.append({"kod": "modell.kuszob_nincs", "param": {"feladat": feladat}})
        return {"kalibralhato": False, "kuszob": None, "min_tetel": k.min_tetel if k else None, "okok": okok}
    pont = float(ert.get("pontszam") or 0.0)
    n = min(int(ert.get("n") or 0), int(ert.get("tetelszam") or ert.get("n") or 0))
    if n < k.min_tetel:
        okok.append({"kod": "modell.keves_tetel", "param": {"feladat": feladat, "n": n, "min_tetel": k.min_tetel}})
    if pont < k.kuszob:
        okok.append({"kod": "modell.kuszob_alatt", "param": {"feladat": feladat, "pontszam": round(pont, 4), "kuszob": k.kuszob}})
    for ut, also in k.reszpont.items():
        ertek = _mezo(ert, ut)
        if not isinstance(ertek, (int, float)) or float(ertek) < also:
            okok.append({"kod": "modell.reszpont_alatt",
                         "param": {"feladat": feladat, "mezo": ut, "ertek": ertek if isinstance(ertek, (int, float)) else None,
                                   "kuszob": also}})
    return {"kalibralhato": not okok, "kuszob": k.kuszob, "min_tetel": k.min_tetel, "okok": okok}

