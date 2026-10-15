"""Levezetés-ellenőrzés modell nélkül (C24a; TERV 5.6 2.): az egymást követő sorok ekvivalenciája, az első hibás
átmenet. A homokozó gyermekében fut (`matek.levezetes` művelet); a fájlba nem ír.

Egyenlet / egyenlőtlenség (egy ismeretlen, valós számok):
  R  = az első sor megoldáshalmaza az értelmezési tartományán, metszve a hívó és a sorok kikötéseivel;
  S_i = az i. sor megoldáshalmaza (véges halmaznál behelyettesítéssel szűrve);
  i−1 → i:  S_i ⊉ R → hiba (megoldás veszett el / eltérő halmaz);  S_i = S_{i−1} → ekvivalens;
            S_i ⊋ S_{i−1} → bővülő (pl. négyzetre emelés: megengedett, de a végén ellenőrizni kell);
            S_i ⊊ S_{i−1} → szűrés (a hamis gyök elvetése);  nem összemérhető → hiba;
  a végén:  ha az utolsó sor kimondott megoldás és S ⊋ R → hamis gyök maradt (a záró, azonos halmazú
            szakasz első megoldás-során).
Kifejezés-lánc (`=`-folytatás vagy egy sorban több `=`): szomszédos kifejezések azonossága.

A végeredmény (R) csak `vegeredmeny=True`-ra szerepel a válaszban; az üzenetek alapból sem gyököt, sem halmazt
nem neveznek meg. Ami nem elemezhető vagy nem dönthető el, az így szerepel: a modul nem találgat.
"""
from __future__ import annotations

import sympy as sp
from sympy.calculus.util import continuous_domain

from homokozo.idozito import Idotullepes, korlatozva
from matek import sorelemzo as SE

M = SE.M
VALOS = sp.S.Reals
_TURES = 1e-9

UZENET = {
    "megoldas_elveszett": "Ebben az átmenetben megoldás veszett el.",
    "eltero_halmaz": "Ez a sor nem következik az előzőből: a megoldáshalmaza eltér.",
    "hamis_gyok_maradt": "A kimondott megoldás olyan értéket is tartalmaz, amely az eredeti feladatnak nem megoldása.",
    "nem_azonos": "Ez a kifejezés nem azonos az előzővel.",
}


class NemEldontheto(Exception):
    pass


# ------------------------------------------------------------------ halmazok

def _szam(e) -> complex:
    return complex(sp.N(e, 30))


def _valos_veges(e) -> float | None:
    try:
        v = _szam(e)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if v != v or abs(v) == float("inf") or abs(v.imag) > 1e-9 * max(1.0, abs(v.real)):
        return None
    return v.real


def _teljesul(rel: SE.Relacio, x: sp.Symbol, c) -> bool:
    """A reláció teljesül-e x = c-re (a két oldal valós és véges)."""
    a, b = _valos_veges(rel.bal.subs(x, c)), _valos_veges(rel.jobb.subs(x, c))
    if a is None or b is None:
        return False
    tures = 1e-8 * max(1.0, abs(a), abs(b))
    return {"=": abs(a - b) <= tures, "!=": abs(a - b) > tures, "<": a < b - tures, "<=": a <= b + tures,
            ">": a > b + tures, ">=": a >= b - tures}[rel.op]


def _tartomany(rel: SE.Relacio, x: sp.Symbol) -> sp.Set:
    d = VALOS
    for e in (rel.bal, rel.jobb):
        if x in e.free_symbols:
            d = d.intersect(continuous_domain(e, x, VALOS))
    return d


_SP_OP = {"=": sp.Eq, "!=": sp.Ne, "<": sp.Lt, "<=": sp.Le, ">": sp.Gt, ">=": sp.Ge}


def _jo_halmaz(h) -> bool:
    if h is sp.S.EmptySet or isinstance(h, (sp.FiniteSet, sp.Interval)):
        return True
    if isinstance(h, sp.Union):
        return all(_jo_halmaz(a) for a in h.args)
    return h == VALOS


def _log_osszevonva(rel: SE.Relacio, x: sp.Symbol):
    """Logaritmusok összevonása (bővítő lépés: a jelöltek utána az eredeti relációval szűrődnek)."""
    szamlalo, _ = sp.fraction(sp.together(rel.bal - rel.jobb))
    egy = sp.logcombine(sp.expand(szamlalo), force=True)
    return sp.solveset(egy, x, VALOS)


def _relacio_halmaz(rel: SE.Relacio, x: sp.Symbol) -> sp.Set:
    d = _tartomany(rel, x)
    if not (rel.bal.free_symbols | rel.jobb.free_symbols) - {x} == set():
        raise NemEldontheto("több ismeretlen")
    if x not in (rel.bal.free_symbols | rel.jobb.free_symbols):
        return d if _teljesul(rel, x, 0) else sp.S.EmptySet
    h = sp.solveset(_SP_OP[rel.op](rel.bal, rel.jobb), x, VALOS)
    if not _jo_halmaz(h) and rel.op == "=" and (rel.bal - rel.jobb).has(sp.log):
        h = _log_osszevonva(rel, x)
    if isinstance(h, sp.FiniteSet):                 # a tartomány is kell: log(−9) − log(−3) képzetes része kiesik
        return sp.FiniteSet(*[c for c in h if _teljesul(rel, x, c) and _eleme(c, d) is not False])
    if not _jo_halmaz(h):
        raise NemEldontheto(f"a CAS nem adott zárt alakot ({type(h).__name__})")
    h = h.intersect(d)
    if not _jo_halmaz(h):
        raise NemEldontheto("az értelmezési tartománnyal vett metszet nem zárt alakú")
    return h


def sor_halmaz(sor: SE.Sor, x: sp.Symbol) -> sp.Set:
    if sor.fajta == "megoldas":
        return sp.FiniteSet(*sor.ertekek)
    if sor.fajta in ("egyenlet", "egyenlotlenseg", "vagy"):
        unio = sp.S.EmptySet
        for ag in sor.agak:
            h = VALOS
            for rel in ag:
                h = h.intersect(_relacio_halmaz(rel, x))
            unio = unio.union(h)
        if not _jo_halmaz(unio):
            raise NemEldontheto("nem zárt alakú unió")
        return unio
    raise NemEldontheto(f"a(z) {sor.fajta} sornak nincs megoldáshalmaza")


def _kikotes_halmaz(rel: SE.Relacio, x: sp.Symbol) -> sp.Set:
    return _relacio_halmaz(rel, x)


def _eleme(c, h: sp.Set) -> bool | None:
    if h is sp.S.EmptySet:
        return False
    if isinstance(h, sp.FiniteSet):
        return any(M.kozel(c, e, _TURES) for e in h)
    v = _valos_veges(c)
    if v is None:
        return False
    darabok = h.args if isinstance(h, sp.Union) else (h,)
    for d in darabok:
        if isinstance(d, sp.FiniteSet):
            if any(M.kozel(c, e, _TURES) for e in d):
                return True
        elif isinstance(d, sp.Interval):
            a, b = float(d.start), float(d.end)
            if (a < v or (not d.left_open and abs(a - v) <= _TURES)) and \
               (v < b or (not d.right_open and abs(b - v) <= _TURES)):
                return True
        else:
            return None
    return False


def resze(a: sp.Set, b: sp.Set) -> bool | None:
    """a ⊆ b, a véges halmazoknál számértékkel (tűréssel)."""
    if a is sp.S.EmptySet:
        return True
    if isinstance(a, sp.FiniteSet):
        ki = [_eleme(c, b) for c in a]
        return None if None in ki else all(ki)
    if isinstance(b, sp.FiniteSet):
        return False
    try:
        r = a.is_subset(b)
    except (TypeError, ValueError, NotImplementedError):
        r = None
    if r is None:
        try:
            r = sp.Complement(a, b) is sp.S.EmptySet or sp.simplify(sp.Complement(a, b)) is sp.S.EmptySet
        except (TypeError, ValueError, NotImplementedError):
            return None
    return bool(r)


def egyenlo(a: sp.Set, b: sp.Set) -> bool | None:
    x, y = resze(a, b), resze(b, a)
    return None if None in (x, y) else (x and y)


# ------------------------------------------------------------------ az ellenőrzés

def _ismeretlen(sorok: list[SE.Sor]) -> sp.Symbol | None:
    for s in sorok:
        if s.fajta == "megoldas":
            return sp.Symbol(s.valtozo, real=True)
        if s.fajta in ("egyenlet", "egyenlotlenseg", "vagy"):
            szabad = s.szabad()
            return szabad.pop() if len(szabad) == 1 else None
    return None


def _kimondott(sor: SE.Sor, x: sp.Symbol) -> bool:
    """Kimondott megoldás-e a sor: értéklista, vagy `x op c` alakú egyenlőtlenség(ek)."""
    if sor.fajta == "megoldas":
        return True
    if sor.fajta in ("egyenlotlenseg", "vagy"):
        return all(not (r.bal.free_symbols - {x}) and (r.bal == x or r.jobb == x) and
                   not ((r.jobb if r.bal == x else r.bal).free_symbols) and r.op != "!="
                   for ag in sor.agak for r in ag)
    return False


def _mod(sorok: list[SE.Sor], mod: str) -> str:
    if mod in ("egyenlet", "kifejezes"):
        return mod
    for s in sorok:
        if s.fajta in ("kifejezes", "folytatas", "lanc"):
            return "kifejezes"
        if s.fajta in ("egyenlet", "egyenlotlenseg", "vagy", "megoldas"):
            if s.fajta == "egyenlet" and len(s.szabad()) > 1 and len(s.agak) == 1 and len(s.agak[0]) == 1:
                try:                                     # (a+b)^2 = a^2+2ab+b^2: azonosság → kifejezés-lánc
                    r = s.agak[0][0]
                    return "kifejezes" if M.kifejezes_egyezik(r.bal, r.jobb) else "egyenlet"
                except (M.MatekHiba, ValueError, TypeError):
                    return "egyenlet"
            return "egyenlet"
    return "egyenlet"


def ellenoriz(sorok: list[str], vegeredmeny: bool = False, kikotesek: list[str] | tuple = (),
              mod: str = "auto", lepes_idokorlat_s: float = 3.0) -> dict:
    """Kijelölt sorok (LaTeX, `$` nélkül vagy vele) → ítélet. Lásd a modul leírását."""
    elemzett = [SE.elemez_sor(s) for s in sorok]
    info = [{"sor": i + 1, "fajta": s.fajta, **({"ok": s.ok} if s.ok else {})} for i, s in enumerate(elemzett)]
    valasz = {"allapot": "nem_ellenorizheto", "elso_hiba": None, "atmenetek": [], "sorok": info, "mod": None}
    if sum(s.fajta not in ("nem_elemezheto", "ures") for s in elemzett) < 2:
        valasz["ok"] = "legalább két elemezhető sor kell"
        return valasz
    m = _mod(elemzett, mod)
    valasz["mod"] = m
    if m == "kifejezes":
        return _kifejezes_lanc(elemzett, valasz, vegeredmeny, lepes_idokorlat_s)
    return _egyenlet_lanc(elemzett, valasz, vegeredmeny, kikotesek, lepes_idokorlat_s)


def _egyenlet_lanc(elemzett, valasz, vegeredmeny, kikotesek, lepes) -> dict:
    x = _ismeretlen(elemzett)
    if x is None:
        valasz["ok"] = "nem egyetlen ismeretlenes egyenlet (több ismeretlen vagy paraméter)"
        return valasz
    halmazok: list[sp.Set | None] = []
    for i, s in enumerate(elemzett):
        if s.fajta in ("nem_elemezheto", "ures"):
            halmazok.append(None)
            continue
        try:
            with korlatozva(lepes):
                halmazok.append(sor_halmaz(s, x))
        except (NemEldontheto, M.MatekHiba, ValueError, TypeError, NotImplementedError, Idotullepes) as exc:
            halmazok.append(None)
            valasz["sorok"][i]["ok"] = ("időtúllépés" if isinstance(exc, Idotullepes) else str(exc)[:200])
            if s.fajta != "nem_elemezheto":
                valasz["sorok"][i]["fajta"] = s.fajta + " (nem eldönthető)"

    referencia_i = next((i for i, h in enumerate(halmazok) if h is not None), None)
    if referencia_i is None or sum(h is not None for h in halmazok) < 2:
        valasz["ok"] = "legalább két sor megoldáshalmaza kell"
        return valasz
    R = halmazok[referencia_i]
    try:
        with korlatozva(lepes):
            for k in kikotesek or ():
                ks = SE.elemez_sor(k)
                if ks.fajta not in ("egyenlotlenseg", "egyenlet") or len(ks.agak) != 1:
                    raise NemEldontheto(f"a kikötés nem elemezhető: {k}")
                for rel in ks.agak[0]:
                    R = R.intersect(_kikotes_halmaz(rel, x))
            for rel in elemzett[referencia_i].kikotesek:
                R = R.intersect(_kikotes_halmaz(rel, x))
    except (NemEldontheto, M.MatekHiba, ValueError, TypeError, NotImplementedError, Idotullepes) as exc:
        valasz["ok"] = f"a kikötés nem dönthető el: {exc}"[:200]
        return valasz

    elozo_i = referencia_i
    elso_hiba = None
    for i in range(referencia_i + 1, len(elemzett)):
        h = halmazok[i]
        atmenet = {"honnan": elozo_i + 1, "hova": i + 1}
        if h is None:
            atmenet["itelet"] = ("nem_elemezheto" if elemzett[i].fajta in ("nem_elemezheto", "ures")
                                 else "nem_eldontheto")
            valasz["atmenetek"].append(atmenet)
            continue
        bizonytalan = elozo_i != i - 1
        try:
            with korlatozva(lepes):
                for rel in elemzett[i].kikotesek:
                    R = R.intersect(_kikotes_halmaz(rel, x))
                lefed, elozo = resze(R, h), halmazok[elozo_i]
                if lefed is False:
                    itelet = "hiba"
                    fajta = "megoldas_elveszett" if resze(h, elozo) else "eltero_halmaz"
                else:
                    e1, e2 = resze(h, elozo), resze(elozo, h)
                    if lefed is None or None in (e1, e2):
                        itelet, fajta = "nem_eldontheto", None
                    elif e1 and e2:
                        itelet, fajta = "ekvivalens", None
                    elif e2:
                        itelet, fajta = "bovulo", None
                    elif e1:
                        itelet, fajta = "szures", None
                    else:
                        itelet, fajta = "hiba", "eltero_halmaz"
        except (NemEldontheto, M.MatekHiba, ValueError, TypeError, NotImplementedError, Idotullepes):
            itelet, fajta = "nem_eldontheto", None
        atmenet["itelet"] = itelet
        if bizonytalan:
            atmenet["bizonytalan"] = True
        valasz["atmenetek"].append(atmenet)
        if itelet == "hiba" and elso_hiba is None:
            elso_hiba = {"sor": i + 1, "fajta": fajta, "uzenet": UZENET[fajta], "bizonytalan": bizonytalan}
        elozo_i = i

    if elso_hiba is None:
        elso_hiba = _zaro_ellenorzes(elemzett, halmazok, R, x, lepes)
    valasz["elso_hiba"] = elso_hiba
    eldontetlen = any(a["itelet"] in ("nem_eldontheto", "nem_elemezheto") for a in valasz["atmenetek"])
    valasz["allapot"] = "hiba" if elso_hiba else ("reszben_ellenorizve" if eldontetlen else "rendben")
    if not elso_hiba and not _kimondott(elemzett[elozo_i], x):
        valasz["megjegyzes"] = "az utolsó sor nem kimondott megoldás: a hamis gyök nem vizsgált"
    if vegeredmeny:
        valasz["vegeredmeny"] = {"valtozo": x.name, "halmaz": sp.sstr(R)}
    return valasz


def _zaro_ellenorzes(elemzett, halmazok, R, x, lepes) -> dict | None:
    utolso = max(i for i, h in enumerate(halmazok) if h is not None)
    if not _kimondott(elemzett[utolso], x):
        return None
    try:
        with korlatozva(lepes):
            if egyenlo(halmazok[utolso], R) is not False:
                return None
            kezd = utolso
            for i in range(utolso - 1, -1, -1):
                if halmazok[i] is None:
                    continue
                if egyenlo(halmazok[i], halmazok[utolso]) is True:
                    if _kimondott(elemzett[i], x):
                        kezd = i
                else:
                    break
    except (NemEldontheto, M.MatekHiba, ValueError, TypeError, NotImplementedError, Idotullepes):
        return None
    return {"sor": kezd + 1, "fajta": "hamis_gyok_maradt", "uzenet": UZENET["hamis_gyok_maradt"],
            "bizonytalan": False}


def _kifejezes_lanc(elemzett, valasz, vegeredmeny, lepes) -> dict:
    lanc: list[tuple[int, sp.Expr]] = []
    for i, s in enumerate(elemzett):
        if s.fajta in ("kifejezes", "folytatas", "lanc"):
            lanc += [(i, e) for e in s.kifejezesek]
        elif s.fajta == "egyenlet" and len(s.agak) == 1 and len(s.agak[0]) == 1:
            lanc += [(i, s.agak[0][0].bal), (i, s.agak[0][0].jobb)]
        elif s.fajta not in ("nem_elemezheto", "ures"):
            valasz["sorok"][i]["ok"] = "a kifejezés-láncban nem kifejezés"
    if len(lanc) < 2:
        valasz["ok"] = "legalább két kifejezés kell"
        return valasz
    elso_hiba = None
    eldontetlen = False
    for (i0, a), (i1, b) in zip(lanc, lanc[1:]):
        atmenet = {"honnan": i0 + 1, "hova": i1 + 1}
        try:
            with korlatozva(lepes):
                azonos = M.kifejezes_egyezik(a, b)
                szabad = sorted(a.free_symbols | b.free_symbols, key=lambda s: s.name)
                if azonos and len(szabad) == 1:
                    d0 = continuous_domain(a, szabad[0], VALOS)
                    d1 = continuous_domain(b, szabad[0], VALOS)
                    if d0 != d1:
                        atmenet["megjegyzes"] = "az értelmezési tartomány megváltozott (kikötés kell)"
            atmenet["itelet"] = "ekvivalens" if azonos else "hiba"
        except (M.MatekHiba, ValueError, TypeError, NotImplementedError, Idotullepes):
            atmenet["itelet"] = "nem_eldontheto"
            eldontetlen = True
        if i1 - i0 > 1 and any(elemzett[k].fajta in ("nem_elemezheto", "ures") for k in range(i0 + 1, i1)):
            atmenet["bizonytalan"] = True
        valasz["atmenetek"].append(atmenet)
        if atmenet["itelet"] == "hiba" and elso_hiba is None:
            elso_hiba = {"sor": i1 + 1, "fajta": "nem_azonos", "uzenet": UZENET["nem_azonos"],
                         "bizonytalan": bool(atmenet.get("bizonytalan"))}
    eldontetlen = eldontetlen or any(s.fajta == "nem_elemezheto" for s in elemzett)
    valasz["elso_hiba"] = elso_hiba
    valasz["allapot"] = "hiba" if elso_hiba else ("reszben_ellenorizve" if eldontetlen else "rendben")
    if vegeredmeny:
        try:
            with korlatozva(lepes):
                valasz["vegeredmeny"] = {"kifejezes": sp.sstr(sp.simplify(lanc[0][1]))}
        except Idotullepes:
            valasz["vegeredmeny"] = {"kifejezes": None, "ok": "időtúllépés"}
    return valasz


def megoldashalmaz(sor: str, vegeredmeny: bool = True) -> dict:
    """Egy sor valós megoldáshalmaza (a C35 és a kézi ellenőrzés segédje)."""
    s = SE.elemez_sor(sor)
    if s.fajta == "nem_elemezheto":
        return {"allapot": "nem_elemezheto", "ok": s.ok}
    x = _ismeretlen([s])
    if x is None:
        return {"allapot": "nem_ellenorizheto", "ok": "nem egyetlen ismeretlenes"}
    try:
        h = sor_halmaz(s, x)
    except (NemEldontheto, M.MatekHiba, ValueError, TypeError, NotImplementedError) as exc:
        return {"allapot": "nem_eldontheto", "ok": str(exc)[:200]}
    return {"allapot": "ok", "valtozo": x.name, "halmaz": sp.sstr(h)}
