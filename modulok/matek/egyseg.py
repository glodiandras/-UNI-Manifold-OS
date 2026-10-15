"""Fizika: mértékegység- és dimenzió-ellenőrzés (C24a; TERV 5.6 4.). A homokozó gyermekében fut (`matek.egyseg`).

Egy sor `=`-lánc (`v = 72\\,\\text{km/h} = 20\\,\\text{m/s}`, `F = ma = 2\\,\\text{kg}\\cdot 3\\,\\text{m/s^2}`):
- minden tag dimenziója egyezik; egy tagon belül az összeadandóké is, és a `sin`/`exp`/`log` argumentuma
  dimenziótlan;
- a csak számot és egységet tartalmazó tagok SI-értéke tűréssel egyezik.

**Egység csak** a `\\text{}`/`\\mathrm{}` (és `\\si{}`, `\\unit{}`) belsejében, vagy egy számliterál után **szóközzel
vagy `\\,`-vel elválasztva** állhat (`2\\,\\text{s}`, `2 s`); a `2t` = 2·t. Így a változó (`m`, `s`, `t`) nem
téveszthető össze az egységgel. A szótár zárt (SI-alap és származtatott egységek, prefixekkel, néhány
gyakorlati egység); a `°C` (affin) nem ellenőrizhető. A jelek dimenziója a hívó `jelolesek` szótárából jön
(`{"v": "m/s"}`); alapból csak egy szűk, egyértelmű tábla él, és a válasz megnevezi, mit feltételezett.
Ismeretlen jel: `nem_ellenorizheto` — a modul nem találgat. Az egységtábla saját (skála + dimenzió), a
`sympy.physics.units` nem kell hozzá.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_EVAL = Path(__file__).resolve().parent.parent / "eval"
if str(_EVAL) not in sys.path:
    sys.path.insert(0, str(_EVAL))
import sympy as sp  # noqa: E402
from sympy.parsing.sympy_parser import (convert_xor, implicit_multiplication_application, parse_expr,  # noqa: E402
                                        rationalize, standard_transformations)

from kozos import matek as M  # noqa: E402
from matek.sorelemzo import elokeszit  # noqa: E402

R = sp.Rational
ALAPDIM = ("M", "L", "T", "I", "H", "N")              # tömeg, hossz, idő, áram, hőmérséklet, anyagmennyiség
_SI_NEV = {"L": "m", "M": "kg", "T": "s", "I": "A", "H": "K", "N": "mol"}


def _d(**k) -> dict:
    return {a: b for a, b in k.items() if b}


ERO = _d(M=1, L=1, T=-2)
ENERGIA = _d(M=1, L=2, T=-2)
_ALAP = {                                              # név → (SI-skála, dimenzió); prefixelhető
    "m": (R(1), _d(L=1)), "g": (R(1, 1000), _d(M=1)), "s": (R(1), _d(T=1)), "A": (R(1), _d(I=1)),
    "K": (R(1), _d(H=1)), "mol": (R(1), _d(N=1)), "N": (R(1), ERO), "J": (R(1), ENERGIA),
    "W": (R(1), _d(M=1, L=2, T=-3)), "Pa": (R(1), _d(M=1, L=-1, T=-2)), "V": (R(1), _d(M=1, L=2, T=-3, I=-1)),
    "C": (R(1), _d(I=1, T=1)), "Ω": (R(1), _d(M=1, L=2, T=-3, I=-2)), "ohm": (R(1), _d(M=1, L=2, T=-3, I=-2)),
    "Hz": (R(1), _d(T=-1)), "l": (R(1, 1000), _d(L=3)), "L": (R(1, 1000), _d(L=3)),
    "eV": (R(1602176634, 10 ** 28), ENERGIA), "Wh": (R(3600), ENERGIA), "F": (R(1), _d(M=-1, L=-2, T=4, I=2)),
    "T": (R(1), _d(M=1, T=-2, I=-1)), "Wb": (R(1), _d(M=1, L=2, T=-2, I=-1)), "H": (R(1), _d(M=1, L=2, T=-2, I=-2)),
}
_KULON = {                                             # nem prefixelhető vagy kétértelmű nevek (elsőbbséget kapnak)
    "h": (R(3600), _d(T=1)), "min": (R(60), _d(T=1)), "óra": (R(3600), _d(T=1)), "perc": (R(60), _d(T=1)),
    "mp": (R(1), _d(T=1)), "t": (R(1000), _d(M=1)), "bar": (R(100000), _d(M=1, L=-1, T=-2)),
    "rad": (R(1), {}), "°": (sp.pi / 180, {}), "%": (R(1, 100), {}), "km/h": (R(5, 18), _d(L=1, T=-1)),
}
_PREFIX = {"k": R(1000), "M": R(10 ** 6), "G": R(10 ** 9), "m": R(1, 1000), "µ": R(1, 10 ** 6), "μ": R(1, 10 ** 6),
           "u": R(1, 10 ** 6), "n": R(1, 10 ** 9), "c": R(1, 100), "d": R(1, 10), "h": R(100)}
AFFIN = ("°C", "℃", "°F")

# alapból feltételezett jelölések (szűk, egyértelmű tábla); a hívó `jelolesek`-e felülírja/bővíti
ALAP_JELOLESEK = {"t": "s", "m": "kg", "v": "m/s", "a": "m/s^2", "F": "N", "s": "m", "g": "m/s^2"}

_FUGGVENYEK = {"sqrt": sp.sqrt, "sin": sp.sin, "cos": sp.cos, "tan": sp.tan, "tg": sp.tan, "exp": sp.exp,
               "log": sp.log, "ln": sp.log, "lg": lambda x: sp.log(x, 10), "Abs": sp.Abs, "pi": sp.pi}
_GOROG = ("alpha", "beta", "gamma", "delta", "epsilon", "varepsilon", "eta", "theta", "vartheta", "kappa",
          "lambda", "rho", "sigma", "tau", "phi", "varphi", "omega", "Omega", "Delta", "Phi", "psi", "nu", "xi")
_ATALAKITAS = standard_transformations + (implicit_multiplication_application, convert_xor, rationalize)


class EgysegHiba(ValueError):
    pass


class Ismeretlen(ValueError):
    pass


# ------------------------------------------------------------------ egység-kifejezés

def egyseg_nev(nev: str) -> tuple:
    """Egy egységnév → (SI-skála, dimenzió). Ismeretlen: `EgysegHiba`."""
    nev = nev.replace("\\Omega", "Ω").replace("\\mu", "µ").replace("^\\circ", "°").replace("\\%", "%")
    if nev in AFFIN:
        raise EgysegHiba(f"affin egység ({nev}): nem ellenőrizhető")
    if nev in _KULON:
        return _KULON[nev]
    if nev in _ALAP:
        return _ALAP[nev]
    for p, szorzo in _PREFIX.items():
        if nev.startswith(p) and nev[len(p):] in _ALAP:
            skala, dim = _ALAP[nev[len(p):]]
            return szorzo * skala, dim
    raise EgysegHiba(f"ismeretlen egység: {nev}")


def _dim_szor(a: dict, b: dict, k=1) -> dict:
    ki = dict(a)
    for d, e in b.items():
        ki[d] = ki.get(d, 0) + k * e
    return {d: e for d, e in ki.items() if e}


def egyseg(szoveg: str) -> tuple:
    """Egység-kifejezés (`km/h`, `kg\\cdot m/s^2`, `\\frac{m}{s^2}`, `N m`) → (SI-skála, dimenzió)."""
    t = szoveg.strip()
    if t in _KULON:
        return _KULON[t]
    t = re.sub(r"\\[dt]?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", r"(\1)/(\2)", t)
    t = re.sub(r"\\(?:cdot|times)|·|⋅|\*", " * ", t)
    t = t.replace("\\,", " ").replace("\\ ", " ").replace("{", "(").replace("}", ")").replace("−", "-")
    for k, v in (("\\Omega", "Ω"), ("\\mu", "µ"), ("^\\circ", "°"), ("\\%", "%")):
        t = t.replace(k, v)
    tokenek = re.findall(r"km/h|[A-Za-zΩµμ°%]+|-?\d+|[*/^()]", t)
    if "".join(tokenek).replace(" ", "") != re.sub(r"\s+", "", t):
        raise EgysegHiba(f"nem egység-kifejezés: {szoveg!r}")
    poz = 0

    def tenyezo():
        nonlocal poz
        if poz >= len(tokenek):
            raise EgysegHiba("csonka egység")
        tk = tokenek[poz]
        if tk == "(":
            poz += 1
            ertek = szorzat()
            if poz >= len(tokenek) or tokenek[poz] != ")":
                raise EgysegHiba("páratlan zárójel az egységben")
            poz += 1
        elif re.fullmatch(r"km/h|[A-Za-zΩµμ°%]+", tk):
            poz += 1
            ertek = egyseg_nev(tk)
        elif tk == "1":                                          # 1/s
            poz += 1
            ertek = (R(1), {})
        else:
            raise EgysegHiba(f"váratlan jel az egységben: {tk}")
        if poz < len(tokenek) and tokenek[poz] == "^":
            if poz + 1 >= len(tokenek) or not re.fullmatch(r"-?\d+", tokenek[poz + 1]):
                raise EgysegHiba("a kitevő egész szám kell legyen")
            k = int(tokenek[poz + 1])
            poz += 2
            ertek = (ertek[0] ** k, {d: e * k for d, e in ertek[1].items()})
        return ertek

    def szorzat():
        nonlocal poz
        skala, dim = tenyezo()
        while poz < len(tokenek) and tokenek[poz] != ")":
            if tokenek[poz] == "*":
                poz += 1
                s2, d2 = tenyezo()
                skala, dim = skala * s2, _dim_szor(dim, d2)
            elif tokenek[poz] == "/":
                poz += 1
                s2, d2 = tenyezo()
                skala, dim = skala / s2, _dim_szor(dim, d2, -1)
            else:                                                # szóköz = szorzás (`N m`)
                s2, d2 = tenyezo()
                skala, dim = skala * s2, _dim_szor(dim, d2)
        return skala, dim

    ki = szorzat()
    if poz != len(tokenek):
        raise EgysegHiba(f"nem egység-kifejezés: {szoveg!r}")
    return ki


def dim_szoveg(dim: dict) -> str:
    if not dim:
        return "1 (dimenziótlan)"
    poz = [f"{_SI_NEV[d]}" + (f"^{e}" if e != 1 else "") for d in ALAPDIM for e in [dim.get(d, 0)] if e > 0]
    neg = [f"{_SI_NEV[d]}" + (f"^{-e}" if e != -1 else "") for d in ALAPDIM for e in [dim.get(d, 0)] if e < 0]
    return ("·".join(poz) or "1") + ("/" + "·".join(neg) if neg else "")


# ------------------------------------------------------------------ a sor tagjai

_EGYSEG_BURKOK = re.compile(r"\\(?:text|mathrm|textrm|si|unit|mbox)\s*\{")
_SZAM = r"\d+(?:[.,]\d+)?(?:\{,\}\d+)?"


def _tag_elokeszit(tag: str, helyorzok: dict) -> str:
    """Az egységek helyére `egysegXX` helyőrző (a `helyorzok` kapja az (SI-skála, dimenzió)-t)."""
    def uj(egy) -> str:
        nev = "egyseg" + "".join(chr(97 + int(c)) for c in f"{len(helyorzok):02d}")
        helyorzok[nev] = egy
        return f" {nev} "

    for _ in range(50):
        m = _EGYSEG_BURKOK.search(tag)
        if not m:
            break
        mely, j = 1, m.end()
        while j < len(tag) and mely:
            mely += (tag[j] == "{") - (tag[j] == "}")
            j += 1
        if mely:
            raise EgysegHiba("páratlan kapcsos zárójel")
        belso = tag[m.end():j - 1]
        kitevo = re.match(r"\s*\^\s*(\{-?\d+\}|-?\d)", tag[j:])
        if kitevo:
            belso = f"({belso})^{kitevo.group(1).strip('{}')}"
            j += kitevo.end()
        tag = tag[:m.start()] + uj(egyseg(belso)) + tag[j:]
    # csupasz egység számliterál után, szóközzel vagy \,-vel elválasztva
    minta = re.compile(r"(" + _SZAM + r")(?:\s|\\,|\\ |~)+((?:km/h)|[A-Za-zΩµμ°%][A-Za-zΩµμ°%]*(?:\s*[/*]\s*[A-Za-zΩµμ]+"
                       r"|\s*\^\s*-?\d)*)")

    def csupasz(m):
        try:
            return m.group(1) + uj(egyseg(m.group(2)))
        except EgysegHiba:
            return m.group(0)

    return minta.sub(csupasz, tag)


def _nevek(t: str, helyorzok: dict) -> tuple[str, dict]:
    """A változónevek kezelése: `v_0`, `\\Delta t`, görög betűk egyben; a többi több betűs név betűnként (`ma`)."""
    t = re.sub(r"\\Delta\s*([a-zA-Z])", r" Delta_\1 ", t)
    t = re.sub(r"\\(" + "|".join(_GOROG) + r")\b", r" \1 ", t)
    t = re.sub(r"([A-Za-z])_\s*\{\s*([A-Za-z0-9]+)\s*\}|([A-Za-z])_\s*([A-Za-z0-9])", lambda m: (m.group(1) or m.group(3))
               + "_" + (m.group(2) or m.group(4)), t)
    t = M.latexbol(elokeszit(t))
    jelek: dict = {}

    def nev(m):
        n = m.group(0)
        if n in helyorzok or n in _FUGGVENYEK or n in _GOROG or "_" in n:
            if n not in helyorzok and n not in _FUGGVENYEK:
                jelek[n] = sp.Symbol(n, positive=True)
            return n
        if len(n) == 1:
            jelek[n] = sp.Symbol(n, positive=True)
            return n
        for c in n:
            jelek[c] = sp.Symbol(c, positive=True)
        return "*".join(n)

    t = re.sub(r"[A-Za-z][A-Za-z0-9_]*", nev, t)
    return t, jelek


def _tag_kifejezes(tag: str, helyorzok: dict) -> sp.Expr:
    t = _tag_elokeszit(tag, helyorzok)
    t, jelek = _nevek(t, helyorzok)
    if not re.fullmatch(r"[0-9a-zA-Z_+\-*/^().,! ]*", t) or len(t) > 400:
        raise EgysegHiba(f"nem megengedett jel a tagban: {t!r}")
    if re.search(r"\d{13,}|(?:\^|\*\*)\s*\(?\s*\d{4,}", t):
        raise EgysegHiba("túl nagy szám")
    helyi = dict(_FUGGVENYEK)
    helyi.update({n: sp.Symbol(n, positive=True) for n in helyorzok})
    helyi.update(jelek)
    try:
        return parse_expr(t, local_dict=helyi, global_dict={"Integer": sp.Integer, "Float": sp.Float,
                                                             "Rational": sp.Rational, "Symbol": sp.Symbol},
                          transformations=_ATALAKITAS)
    except Exception as exc:                                    # a sympy sokféle hibát dob elemzéskor
        raise EgysegHiba(f"nem elemezhető tag ({type(exc).__name__})") from None


class _DimHiba(Exception):
    def __init__(self, fajta: str, uzenet: str):
        super().__init__(uzenet)
        self.fajta = fajta


def dimenzio(e: sp.Expr, tabla: dict, feltetelezett: dict, hasznalt: set | None = None) -> dict:
    """A kifejezés dimenziója. `tabla`: jelnév → (skála, dimenzió) (helyőrzők és a hívó jelölései);
    `feltetelezett`: az alapjelölések; a ténylegesen felhasznált alapjelölés neve a `hasznalt`-ba kerül."""
    hasznalt = set() if hasznalt is None else hasznalt

    def rek(a):
        return dimenzio(a, tabla, feltetelezett, hasznalt)

    if e.is_Number or e in (sp.pi, sp.E):
        return {}
    if isinstance(e, sp.Symbol):
        if e.name in tabla:
            return tabla[e.name][1]
        for n in (e.name, re.sub(r"_.*$", "", e.name), e.name.removeprefix("Delta_")):   # v_0 → v, Δt → t
            if n in feltetelezett:
                hasznalt.add(n)
                return feltetelezett[n][1]
        raise Ismeretlen(e.name)
    if isinstance(e, sp.Mul):
        d: dict = {}
        for a in e.args:
            d = _dim_szor(d, rek(a))
        return d
    if isinstance(e, sp.Pow):
        alap, kitevo = e.args
        if rek(kitevo):
            raise _DimHiba("kitevo_dimenzio", "a kitevő nem dimenziótlan")
        db = rek(alap)
        if not db:
            return {}
        if not kitevo.is_Rational:
            raise _DimHiba("kitevo_dimenzio", "dimenziós mennyiség nem szám kitevőn")
        return {k: v * kitevo for k, v in db.items()}
    if isinstance(e, sp.Add):
        dimek = [rek(a) for a in e.args]
        if any(d != dimek[0] for d in dimek[1:]):
            raise _DimHiba("osszeg_dimenzio", "az összeadandók dimenziója eltér: " +
                           ", ".join(sorted({dim_szoveg(d) for d in dimek})))
        return dimek[0]
    if isinstance(e, sp.Abs):
        return rek(e.args[0])
    if isinstance(e, sp.Function):
        for a in e.args:
            if rek(a):
                raise _DimHiba("argumentum_dimenzio", f"a {type(e).__name__} argumentuma nem dimenziótlan")
        return {}
    raise EgysegHiba(f"nem kezelt kifejezés: {type(e).__name__}")


def ellenoriz(sor: str, jelolesek: dict | None = None, tures: float = 0.005, alap_jelolesek: bool = True) -> dict:
    """Egy fizikai sor (`=`-lánc) mértékegység-ellenőrzése. Lásd a modul leírását."""
    valasz: dict = {"allapot": "nem_ellenorizheto", "tagok": [], "elso_hiba": None, "feltetelezett": {}}
    s = (sor or "").strip().strip("$").strip()
    s = re.sub(r"\\approx|≈", "=", s)
    tagok = [t for t in re.split(r"(?<![<>!])=(?!=)", s)]
    if len(tagok) < 2 or any(not t.strip() for t in tagok):
        valasz["ok"] = "legalább két, `=`-vel elválasztott tag kell"
        return valasz
    jelek_tabla: dict = {}
    for nev, egys in (jelolesek or {}).items():
        try:
            jelek_tabla[nev] = egyseg(egys)
        except EgysegHiba as exc:
            valasz["ok"] = f"a(z) {nev} jelölés egysége hibás: {exc}"
            return valasz
    alap = {n: egyseg(u) for n, u in ALAP_JELOLESEK.items() if n not in jelek_tabla} if alap_jelolesek else {}
    tabla: dict = {}
    kifejezesek = []
    try:
        for t in tagok:
            kifejezesek.append(_tag_kifejezes(t, tabla))
    except EgysegHiba as exc:
        valasz["ok"] = str(exc)
        return valasz
    tabla.update(jelek_tabla)
    hasznalt: set = set()
    dimek: list[dict | None] = []
    for i, e in enumerate(kifejezesek, 1):
        tag = {"tag": i}
        try:
            d = dimenzio(e, tabla, alap, hasznalt)
            tag["dimenzio"] = dim_szoveg(d)
            dimek.append(d)
        except Ismeretlen as exc:
            tag["ok"] = f"ismeretlen jel dimenziója: {exc}"
            dimek.append(None)
        except _DimHiba as exc:
            dimek.append(None)
            tag["ok"] = str(exc)
            valasz["tagok"].append(tag)
            valasz["elso_hiba"] = valasz["elso_hiba"] or {"tag": i, "fajta": exc.fajta, "uzenet": str(exc)}
            continue
        except EgysegHiba as exc:
            tag["ok"] = str(exc)
            dimek.append(None)
        if not (e.free_symbols - {sp.Symbol(n, positive=True) for n in tabla if n.startswith("egyseg")}):
            ertek = e.subs({sp.Symbol(n, positive=True): tabla[n][0] for n in tabla if n.startswith("egyseg")})
            try:
                tag["si_ertek"] = float(sp.N(ertek, 15))
            except (TypeError, ValueError):
                pass
        valasz["tagok"].append(tag)
    valasz["feltetelezett"] = {n: ALAP_JELOLESEK[n] for n in sorted(hasznalt)}
    if valasz["elso_hiba"] is None:
        ismert = [(i, d) for i, d in enumerate(dimek, 1) if d is not None]
        for (i0, d0), (i1, d1) in zip(ismert, ismert[1:]):
            if d0 != d1:
                valasz["elso_hiba"] = {"tag": i1, "fajta": "dimenzio_elteres",
                                       "uzenet": f"a(z) {i1}. tag dimenziója ({dim_szoveg(d1)}) eltér a(z) {i0}. "
                                                 f"tagétól ({dim_szoveg(d0)})"}
                break
    if valasz["elso_hiba"] is None:
        szamok = [(t["tag"], t["si_ertek"]) for t in valasz["tagok"] if "si_ertek" in t]
        for (i0, a), (i1, b) in zip(szamok, szamok[1:]):
            if abs(a - b) > tures * max(abs(a), abs(b), 1e-300):
                valasz["elso_hiba"] = {"tag": i1, "fajta": "ertek_elteres",
                                       "uzenet": f"a(z) {i1}. tag SI-értéke ({b:.6g}) eltér a(z) {i0}. tagétól "
                                                 f"({a:.6g})"}
                break
    hianyos = any(d is None for d in dimek)
    valasz["allapot"] = "hiba" if valasz["elso_hiba"] else ("reszben_ellenorizve" if hianyos else "rendben")
    if hianyos and valasz["allapot"] != "hiba" and all(d is None for d in dimek):
        valasz["allapot"] = "nem_ellenorizheto"
    return valasz
