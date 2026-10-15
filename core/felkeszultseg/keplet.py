"""A felkészültség képlete (C28a, `docs/C28-TERV.md`): tiszta függvények, I/O nélkül.

Egy téma és egy időpont τ (a „most”, vagy a „kilátás”: a dolgozat napja, további tanulás nélkül) négy összetevőből áll:

| összetevő | érték sᵢ | bizalom cᵢ | súly wᵢ |
|---|---|---|---|
| kartya     | a kötött kártyák átlagos FSRS-felidézése R(τ) (az új kártya 0) | min(1, n / kartya_n0) | suly_kartya |
| kviz       | az eredmények időben csökkenő súlyú aránya (felezés `kviz_felezes_nap`) | min(1, hatékony kérdésszám / kviz_n0) | suly_kviz |
| frissesseg | 0,5^(az utolsó tanulás óta eltelt nap / `felezes_nap`) | 1, ha van tanulási jel | suly_frissesseg |
| ido        | min(1, tanult perc / `cel_perc`) | 1, ha > 0 perc | suly_ido |

`szám = Σ wᵢ·cᵢ·sᵢ / Σ wᵢ·cᵢ` — **csak ha** `wK·cK + wQ·cQ ≥ min_bizonyitek`: a szám mért tudásból (kártya, kvíz)
születik, az idő és a frissesség csak finomít, önmagukban nem adnak számot; és **együttes súlyuk legfeljebb a mért
összetevőké** (különben kevés mért adatnál a „sokat tanult” elnyomná a mért tudást: két rosszul tudott kártya mellé 60
tanult perc közepes számot adna). A súlyok **kalibrálatlan induló értékek**
(`[felkeszultseg]`), a C28b illeszti őket a valódi dolgozat-eredményekre.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, replace

OSSZETEVOK = ("kartya", "kviz", "frissesseg", "ido")


@dataclass(frozen=True)
class Beallitas:
    """A `[felkeszultseg]` szakasz képlet-kulcsai (az alapértékek az `os.toml`-éval egyeznek)."""
    suly_kartya: float = 0.40
    suly_kviz: float = 0.35
    suly_frissesseg: float = 0.10
    suly_ido: float = 0.15
    min_bizonyitek: float = 0.15
    kartya_n0: float = 5
    kviz_n0: float = 10
    kviz_felezes_nap: float = 14
    felezes_nap: float = 10
    cel_perc: float = 60
    min_tanulas_mp: int = 60
    jo: float = 0.80
    gyenge: float = 0.60
    cel: float = 0.85
    kalibralt: bool = False

    @classmethod
    def cfg_bol(cls, cfg) -> "Beallitas":
        """Az `os.toml` `[felkeszultseg]` szakaszából; a hiányzó vagy hibás típusú kulcs az alapértékre esik."""
        s = cfg.section("felkeszultseg")
        ki = {}
        for f in fields(cls):
            if f.name not in s:
                continue
            v = s[f.name]
            if isinstance(f.default, bool):
                if isinstance(v, bool):
                    ki[f.name] = v
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                ki[f.name] = type(f.default)(v)
        return cls(**ki)


@dataclass(frozen=True)
class TemaJel:
    """Egy téma bemenete a τ időpontban (a betöltő állítja össze)."""
    kartya: tuple[float, ...] = ()                       # kártyánként R(τ); az új kártya 0
    uj_kartya: int = 0                                   # ebből még nem tanult (csak kijelzésre)
    kviz: tuple[tuple[float, int, int], ...] = ()        # (kor napban τ-hoz, helyes, összes)
    utolso_tanulas_nap: float | None = None              # τ óta eltelt napok az utolsó tanulás óta; None: nincs jel
    tanult_perc: float = 0.0


@dataclass(frozen=True)
class Osszetevo:
    nev: str
    ertek: float | None            # sᵢ; None, ha nincs mit mérni
    bizalom: float                 # cᵢ ∈ [0, 1]
    suly: float                    # wᵢ
    adat: dict                     # a nyers bemenet (a lefúráshoz)


@dataclass(frozen=True)
class TemaSzam:
    szam: float | None             # None: nincs mért tudás
    bizonyitek: float              # Σ wᵢcᵢ / Σ wᵢ ∈ [0, 1]
    osszetevok: tuple[Osszetevo, ...]
    ok: str | None                 # miért nincs szám: `nincs_mert_tudas`


def _kartya(jel: TemaJel, b: Beallitas) -> Osszetevo:
    n = len(jel.kartya)
    ertek = sum(jel.kartya) / n if n else None
    return Osszetevo("kartya", ertek, min(1.0, n / b.kartya_n0) if n else 0.0, b.suly_kartya,
                     {"db": n, "uj": jel.uj_kartya})


def _kviz(jel: TemaJel, b: Beallitas) -> Osszetevo:
    sulyos_helyes = sulyos_osszes = 0.0
    db = 0
    for kor, helyes, osszes in jel.kviz:
        if osszes <= 0:
            continue
        d = 0.5 ** (max(0.0, kor) / b.kviz_felezes_nap)
        sulyos_helyes += d * helyes
        sulyos_osszes += d * osszes
        db += 1
    if sulyos_osszes <= 0:
        return Osszetevo("kviz", None, 0.0, b.suly_kviz, {"db": 0, "kerdes": 0.0})
    return Osszetevo("kviz", sulyos_helyes / sulyos_osszes, min(1.0, sulyos_osszes / b.kviz_n0), b.suly_kviz,
                     {"db": db, "kerdes": round(sulyos_osszes, 3)})


def _frissesseg(jel: TemaJel, b: Beallitas) -> Osszetevo:
    if jel.utolso_tanulas_nap is None:
        return Osszetevo("frissesseg", None, 0.0, b.suly_frissesseg, {"nap": None})
    return Osszetevo("frissesseg", 0.5 ** (max(0.0, jel.utolso_tanulas_nap) / b.felezes_nap), 1.0, b.suly_frissesseg,
                     {"nap": jel.utolso_tanulas_nap})


def _ido(jel: TemaJel, b: Beallitas) -> Osszetevo:
    perc = max(0.0, jel.tanult_perc)
    return Osszetevo("ido", min(1.0, perc / b.cel_perc), 1.0 if perc > 0 else 0.0, b.suly_ido, {"perc": jel.tanult_perc})


def tema_szam(jel: TemaJel, b: Beallitas) -> TemaSzam:
    """Egy téma felkészültsége (0–1) és az összetevői; mért tudás nélkül `szam = None`."""
    k, q, f, t = _kartya(jel, b), _kviz(jel, b), _frissesseg(jel, b), _ido(jel, b)
    mert = sum(o.suly * o.bizalom for o in (k, q) if o.ertek is not None)
    proxi = sum(o.suly * o.bizalom for o in (f, t) if o.ertek is not None)
    if proxi > mert > 0:                         # a proxik súlya legfeljebb a mért tudásé
        skala = mert / proxi
        f, t = (replace(o, bizalom=o.bizalom * skala, adat={**o.adat, "korlatozva": round(skala, 4)}) for o in (f, t))
    osszetevok = (k, q, f, t)
    sulyok = sum(o.suly for o in osszetevok)
    sulyozott = [(o.suly * o.bizalom, o.ertek) for o in osszetevok if o.ertek is not None and o.bizalom > 0]
    nevezo = sum(w for w, _ in sulyozott)
    bizonyitek = nevezo / sulyok if sulyok > 0 else 0.0
    if nevezo <= 0 or mert < b.min_bizonyitek:
        return TemaSzam(None, bizonyitek, osszetevok, "nincs_mert_tudas")
    szam = sum(w * e for w, e in sulyozott) / nevezo
    return TemaSzam(min(1.0, max(0.0, szam)), bizonyitek, osszetevok, None)


def dolgozat_szam(szamok: list[float | None]) -> tuple[float | None, int, int]:
    """A dolgozat száma: a számmal rendelkező témák egyszerű átlaga → `(szám | None, számmal rendelkező, összes)`."""
    van = [s for s in szamok if s is not None]
    return (sum(van) / len(van) if van else None), len(van), len(szamok)


def szint(szam: float | None, b: Beallitas) -> str:
    if szam is None:
        return "nincs_adat"
    if szam >= b.jo:
        return "jo"
    return "kozepes" if szam >= b.gyenge else "gyenge"
