"""Az automatikus mód döntései (`docs/C26-TERV.md` 5. fejezet) — **csak tiszta függvények**.

Nincs ütemező, háttérszál és modellhívás: a közös ütemező (`core/automatika.py`, T149) a C23b-ben épül, és erre a fogyasztóra
(`Fogyaszto`: feladattípus, szűrő, küszöb, csend, min. hossz) egy regisztrációval köt. Az automatikus munka
`TaskType(automatikus=True)` feladatként indul, a meglévő `Kapu.admit` (`core/modell/kapu.py`: D8 indulási szünet, aktív
használat, szabad memória) alatt — a memóriaőrt itt nem másoljuk. A 9 GB-os modellek tétlenségben-szabálya a router-választásé.

A döntés sorrendje (az első bukó az `ok`): kapcsoló → tartalmi jegyzet → nincs tiltva → elég hosszú → **10 perce nem
változott** → **új vagy erősen módosult** → a jelenlegi változatra nincs még összefoglaló.

**„Erősen módosult”** (a C23-TERV 6. fejezetének mértéke): a normalizált mondathalmazok hosszal súlyozott Jaccard-távolsága
az utoljára feldolgozott változathoz ≥ `kuszob`, **vagy** legalább `uj_karakter` karakternyi új mondat.
"""
# KÖZÖS (C23b): a `mondatok`, a `valtozas`, a `forras_ujjlenyomat` és a `tartalmi_ut` a `core/automatika.py`-ban él (egy mérték,
# egy hely); ez a modul a közös példányt hívja. A regisztráció a közös ütemezőn a C26b-ben megtörtént (`core/automatika.alap_fogyasztok`:
# `Fogyaszto("osszefoglalo", …)`, a feladattípus a `core/osszefoglalas_feladat.py`).
from __future__ import annotations

from dataclasses import dataclass, fields

from core import automatika as _K

KISERO_ELOTAG = _K.KISERO_ELOTAG


@dataclass(frozen=True)
class Beallitas:
    """Az `[osszefoglalas.automatika]` szakasz."""
    be: bool = False              # 80(a): az automatikus fogyasztó regisztrálása (core/automatika.py); alapból hamis — az összefoglaló csak gombra
    csend_perc: int = 10          # ennyi perce nem változhatott a jegyzet
    kuszob: float = 0.3           # hosszal súlyozott Jaccard-távolság az utoljára feldolgozott változathoz
    min_hossz: int = 400          # az új jegyzet legalább ennyi karakter (tisztított)
    uj_karakter: int = 600        # ennyi karakternyi új mondat már önmagában „erős” módosulás
    koteg: int = 2                # C26b: egy automatikus feladatban legfeljebb ennyi jegyzet (egy összefoglaló hosszú modellmunka)
    ujraproba_ora: float = 1.0    # C26b: a beküldött, de nem befejezett (pl. nyitott dokumentum miatt kimaradt) jegyzet újrapróbája


_MEZOK = {f.name for f in fields(Beallitas)}


def beallitas(cfg) -> Beallitas:
    adat = dict(cfg.section("osszefoglalas", "automatika"))
    ismeretlen = sorted(set(adat) - _MEZOK)
    if ismeretlen:
        raise ValueError(f"[osszefoglalas.automatika]: ismeretlen kulcs: {', '.join(ismeretlen)}")
    return Beallitas(**adat)


# A közös mérték egyetlen helye a `core/automatika.py` (C23b): itt csak újra-exportálva (a C26 és a C35 innen is elérheti).
mondatok = _K.mondatok
Valtozas = _K.Valtozas
valtozas = _K.valtozas
forras_ujjlenyomat = _K.forras_ujjlenyomat
tartalmi_ut = _K.tartalmi_ut


@dataclass(frozen=True)
class Allapot:
    """Egy jegyzet helyzete az automatikus döntés pillanatában (az ütemező adja, az index és az `alap` tábla alapján)."""
    ut: str
    md: str
    csend_mp: float                                   # ennyi másodperce nem változott (most − utolsó módosítás)
    kapcsolo_be: bool = True                          # az Asszisztens-kapcsoló (27(c))
    tiltva: bool = False                              # a felhasználó törölte az összefoglalót ehhez az úthoz
    alap: frozenset[str] | None = None                # az utoljára feldolgozott változat mondatai (`None`: új)
    kesz_ujjlenyomat: str | None = None               # annak a változatnak az ujjlenyomata, amelyre van összefoglaló


@dataclass(frozen=True)
class Dontes:
    fusson: bool
    ok: str                                           # `fusson`: "uj" | "erosen_modosult"; különben a bukott feltétel
    valtozas: Valtozas | None = None


def dont(a: Allapot, b: Beallitas | None = None) -> Dontes:
    """Kell-e az automatikus összefoglaló erre a jegyzetre most. Tiszta függvény: modellt nem hív, nem ír, órát nem olvas."""
    b = b or Beallitas()
    if not a.kapcsolo_be:
        return Dontes(False, "kapcsolo_ki")
    if not tartalmi_ut(a.ut):
        return Dontes(False, "nem_tartalmi")
    if a.tiltva:
        return Dontes(False, "tiltva")
    hossz = sum(len(m) for m in mondatok(a.md))
    if hossz < b.min_hossz:
        return Dontes(False, "rovid")
    if a.csend_mp < b.csend_perc * 60:
        return Dontes(False, "meg_valtozik")
    v = valtozas(a.alap, a.md)
    if a.alap is None:
        ok = "uj"
    elif v.tavolsag >= b.kuszob or v.uj_karakter >= b.uj_karakter:
        ok = "erosen_modosult"
    else:
        return Dontes(False, "nem_valtozott_eleg", v)
    if a.kesz_ujjlenyomat and a.kesz_ujjlenyomat == forras_ujjlenyomat(a.md):
        return Dontes(False, "mar_kesz", v)
    return Dontes(True, ok, v)
