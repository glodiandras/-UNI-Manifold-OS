"""CAS-jellemzők egy függvény ablakán (C35a; TERV 5.12): zérushely, szélsőérték, aszimptota. A homokozó gyermekében fut
(`grafikon.elemzes` művelet), a vaultba nem ír; a bemenet a ```plot blokk kifejezése (a `kozos.matek.elemez` jelölése).

Szabály (a C18 `grafikon` aranyhalmazáé, `arany.json` `szabaly`): a zérushely és a szélsőérték az ablak **zárt**
intervallumán értendő; szélsőértéknek a belső pont és a töréspont számít, az ablak végpontja és az értelmezési tartomány
széle nem; az aszimptota `x=…` (függőleges) vagy `y=…` (vízszintes) alakú. A **ferde** aszimptota külön listában
(`ferde_aszimptotak`) jön, így az `aszimptotak` az aranyhalmaz alakját adja.

Pontos érték, ha a CAS zárt alakot ad (`pi/4`, `sqrt(3)`); különben közelítő (numerikus) érték, jelölve (`numerikus`,
figyelmeztetés). Páratlan nevezőjű tört kitevő (`root(x,3)`, `x^(1/3)`) **valós** (D-5: az iskolai konvenció; a SymPy
főága komplex): ilyenkor a számítás numerikus. Egy lépés időkorlátja `lepes_idokorlat_s`; túllépésnél a lépés kimarad,
az állapot `reszleges`, és a figyelmeztetés megnevezi. Nem találgat.
"""
from __future__ import annotations

import math
from typing import Callable

import sympy as sp
from sympy.calculus.util import continuous_domain

from homokozo.idozito import Idotullepes, korlatozva
from kozos import matek as M

X = sp.Symbol("x", real=True)
VALOS = sp.S.Reals
MINTA = 1500                      # numerikus mintapontok darabonként
TOL = 1e-7
POLUS_KORLAT = 1e6               # ennél nagyobb |f| a mintavételben pólus, nem szélsőérték
NAN = float("nan")


class _Kimarad(Exception):
    """Egy lépés nem fejezhető be (időkorlát vagy a CAS nem ad eredményt); a jellemző kimarad, a többi él."""


# ------------------------------------------------------------------ kis segédek

def _hatar_szam(v) -> sp.Expr:
    """Az ablak egy széle: egész, tizedes (a szöveges alakjából pontos tört) vagy konstans-kifejezés szövege."""
    if isinstance(v, bool):
        raise ValueError("az ablak határa szám vagy konstans-kifejezés")
    if isinstance(v, int):
        e = sp.Integer(v)
    elif isinstance(v, float):
        if not math.isfinite(v):
            raise ValueError("az ablak határa véges legyen")
        e = sp.Rational(repr(v))
    elif isinstance(v, str):
        try:
            e = M.elemez(v)
        except M.MatekHiba as h:
            raise ValueError(f"az ablak határa nem értelmezhető: {h}") from None
        if e.free_symbols:
            raise ValueError("az ablak határa konstans legyen")
    else:
        raise ValueError("az ablak határa szám vagy konstans-kifejezés")
    v = _valos(e)
    if v is None:
        raise ValueError("az ablak határa valós, véges szám legyen")
    return e


def _valos(e) -> float | None:
    """A szám lebegőpontos értéke, ha valós és véges; különben `None`."""
    try:
        c = complex(sp.N(e, 20))
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if c != c or not math.isfinite(c.real) or abs(c.imag) > 1e-12 * max(1.0, abs(c.real)):
        return None
    return c.real


def _szoveg(e) -> str:
    return sp.sstr(e)


def _szam_szoveg(v: float) -> str:
    """Közelítő érték olvasható szövege: az egész érték egészként, különben 10 értékes jegy."""
    if abs(v) < 1e-9:
        return "0"
    if abs(v - round(v)) < 1e-9 * max(1.0, abs(v)):
        return str(int(round(v)))
    return f"{v:.10g}"


def _darabok(halmaz) -> list | None:
    """Az értelmezési tartomány intervallumai nyitó szerint rendezve; `None`, ha nem intervallumok uniója."""
    if isinstance(halmaz, sp.Interval):
        return [halmaz]
    if isinstance(halmaz, sp.Union) and all(isinstance(a, sp.Interval) for a in halmaz.args):
        return sorted(halmaz.args, key=lambda i: (-math.inf if i.start == -sp.oo else float(sp.N(i.start))))
    return None


def _paratlan_gyok(f: sp.Expr) -> bool:
    return any(p.exp.is_Rational and p.exp.q > 1 and p.exp.q % 2 == 1 and p.base.has(X) for p in f.atoms(sp.Pow))


def _valos_gyokos(f: sp.Expr) -> sp.Expr:
    """D-5: `b^(p/q)` (q páratlan) → `sign(b)^p · |b|^(p/q)`, a negatív b-n is valós."""
    return f.replace(lambda e: e.is_Pow and e.exp.is_Rational and e.exp.q > 1 and e.exp.q % 2 == 1 and e.base.has(X),
                     lambda e: sp.sign(e.base) ** e.exp.p * sp.Abs(e.base) ** e.exp)


def _szamolo(f: sp.Expr) -> Callable[[float], float]:
    g = sp.lambdify(X, _valos_gyokos(f), modules=["math"])

    def ertek(v: float) -> float:
        try:
            r = g(v)
        except (ValueError, ZeroDivisionError, OverflowError, TypeError):
            return NAN
        if isinstance(r, complex):
            r = r.real if abs(r.imag) <= 1e-12 * max(1.0, abs(r.real)) else NAN
        try:
            r = float(r)
        except (TypeError, ValueError):
            return NAN
        return r if math.isfinite(r) else NAN
    return ertek


# ------------------------------------------------------------------ az elemző

class _Elemzo:
    def __init__(self, f: sp.Expr, a: sp.Expr, b: sp.Expr, lepes: float):
        self.f, self.a, self.b, self.lepes = f, a, b, lepes
        self.af, self.bf = float(sp.N(a, 20)), float(sp.N(b, 20))
        self.ablak = sp.Interval(a, b)
        self.num = _szamolo(f)
        self.paratlan = _paratlan_gyok(f)
        self.figyelmeztetesek: list[str] = []
        self.numerikus = False
        self.reszleges = False
        self.dom = self._tartomany()
        self.darabok = _darabok(self.dom)

    # -- futtatás időkorláttal
    def lepes_fut(self, nev: str, fv, *args, **kw):
        try:
            with korlatozva(self.lepes):
                return fv(*args, **kw)
        except Idotullepes:
            self.reszleges = True
            self.figyelmeztetesek.append(f"{nev}: időkorlát ({self.lepes:g} s), a jellemző kimaradt")
            raise _Kimarad(nev) from None
        except _Kimarad:
            raise
        except (RecursionError, ValueError, TypeError, ArithmeticError, NotImplementedError, AttributeError,
                sp.SympifyError) as h:
            self.reszleges = True
            self.figyelmeztetesek.append(f"{nev}: a CAS nem adott eredményt ({type(h).__name__}), a jellemző kimaradt")
            raise _Kimarad(nev) from None

    def _tartomany(self):
        try:
            with korlatozva(self.lepes):
                return continuous_domain(self.f, X, VALOS)
        except Idotullepes:
            self.figyelmeztetesek.append("értelmezési tartomány: időkorlát, a számítás a mintavételre támaszkodik")
        except (ValueError, TypeError, NotImplementedError, RecursionError, AttributeError):
            self.figyelmeztetesek.append("értelmezési tartomány: a CAS nem adott zárt alakot")
        return VALOS

    # -- a halmazok és a mintavétel
    def _ablak_tartomany(self, nyitott: bool = False):
        ablak = sp.Interval.open(self.a, self.b) if nyitott else self.ablak
        return ablak.intersect(self.dom) if self.darabok is not None else ablak

    def _szeletek(self, tol: float, ig: float):
        """A [tol, ig] és az értelmezési tartomány metszetének darabjai lebegőpontos határokkal."""
        if self.darabok is None:
            return [(tol, ig)]
        ki = []
        for iv in self.darabok:
            lo = -math.inf if iv.start == -sp.oo else float(sp.N(iv.start))
            hi = math.inf if iv.end == sp.oo else float(sp.N(iv.end))
            lo, hi = max(lo, tol), min(hi, ig)
            if lo < hi or (lo == hi and not (iv.left_open or iv.right_open)):
                ki.append((lo, hi))
        return ki

    def _minta(self, lo: float, hi: float, n: int = MINTA):
        return [lo + (hi - lo) * i / (n - 1) for i in range(n)]

    def _minimum_abs(self, lo: float, hi: float) -> float:
        for _ in range(100):
            m1, m2 = lo + (hi - lo) / 3, hi - (hi - lo) / 3
            f1, f2 = abs(self.num(m1)), abs(self.num(m2))
            if f1 != f1 or f2 != f2:
                break
            if f1 < f2:
                hi = m2
            else:
                lo = m1
        return 0.5 * (lo + hi)

    def _finomit_gyok(self, lo: float, hi: float) -> float:
        flo = self.num(lo)
        for _ in range(100):
            kozep = 0.5 * (lo + hi)
            fk = self.num(kozep)
            if fk != fk:
                break
            if fk == 0:
                return kozep
            if (fk > 0) == (flo > 0):
                lo, flo = kozep, fk
            else:
                hi = kozep
        return 0.5 * (lo + hi)

    # -- zérushelyek
    def zerushelyek(self) -> list[dict]:
        if not self.paratlan:
            try:
                h = self.lepes_fut("zérushelyek", sp.solveset, self.f, X, self._ablak_tartomany())
            except _Kimarad:
                h = None
            if h is sp.S.EmptySet:
                return []
            if isinstance(h, sp.FiniteSet):
                ki = []
                for e in h:
                    v = _valos(e)
                    if v is None:
                        continue
                    fv = self.num(v)
                    if fv == fv and abs(fv) <= TOL * (1 + abs(v)):
                        ki.append({"x": _szoveg(e), "ertek": v})
                return sorted(ki, key=lambda p: p["ertek"])
        return self._num_zerus()

    def _num_zerus(self) -> list[dict]:
        self.numerikus = True
        gyokok: list[float] = []
        for lo, hi in self._szeletek(self.af, self.bf):
            if not (math.isfinite(lo) and math.isfinite(hi)) or lo == hi:
                continue
            xs = self._minta(lo, hi)
            ys = [self.num(v) for v in xs]
            for i, (v, y) in enumerate(zip(xs, ys)):
                if y == y and y == 0.0:
                    gyokok.append(v)
                elif 0 < i < len(xs) - 1 and y == y and ys[i - 1] == ys[i - 1] and ys[i + 1] == ys[i + 1] \
                        and abs(y) <= abs(ys[i - 1]) and abs(y) <= abs(ys[i + 1]):
                    g = self._minimum_abs(xs[i - 1], xs[i + 1])          # érintő (kettős) zérus: nincs előjelváltás
                    if abs(self.num(g)) <= 1e-9 * (1 + abs(g)):
                        gyokok.append(g)
                if i and y == y and ys[i - 1] == ys[i - 1] and (y > 0) != (ys[i - 1] > 0) and y != 0.0 and ys[i - 1] != 0.0:
                    g = self._finomit_gyok(xs[i - 1], v)
                    if abs(self.num(g)) <= 1e-6 * (1 + abs(g)):          # pólus-átmenet nem zérushely
                        gyokok.append(g)
        ki: list[float] = []
        for g in sorted(gyokok):
            if not ki or abs(g - ki[-1]) > 1e-7:
                ki.append(g)
        if ki:
            self.figyelmeztetesek.append("zérushelyek: közelítő (numerikus) értékek")
        return [{"x": _szam_szoveg(g), "ertek": g} for g in ki]

    # -- töréspontok és stacionárius pontok
    def _toresek(self) -> list[sp.Expr]:
        """A nem differenciálható belső pontok: az `Abs` argumentumának zérusai, a törtkitevős hatvány alapjáé."""
        jelolt = []
        for ab in self.f.atoms(sp.Abs):
            jelolt.append(ab.args[0])
        for p in self.f.atoms(sp.Pow):
            if p.exp.is_Rational and not p.exp.is_Integer and 0 < p.exp < 1 and p.base.has(X):
                jelolt.append(p.base)
        ki: list[sp.Expr] = []
        for g in jelolt:
            try:
                h = self.lepes_fut("töréspontok", sp.solveset, g, X, self._ablak_tartomany(nyitott=True))
            except _Kimarad:
                continue
            if isinstance(h, sp.FiniteSet):
                ki.extend(h)
        return ki

    def _stacionarius(self, tores: list[sp.Expr]) -> list[sp.Expr]:
        """A derivált zérusai a belső szeleteken; az `Abs` deriváltjának `sign`-ját a szelet közepén vett előjel adja."""
        df = sp.diff(self.f, X)
        if df == 0:
            return []
        torvals = sorted({(_valos(t), t) for t in tores if _valos(t) is not None}, key=lambda p: p[0])
        hatarok = [self.a] + [t for _, t in torvals] + [self.b]
        ki: list[sp.Expr] = []
        for l, r in zip(hatarok, hatarok[1:]):
            lf, rf = float(sp.N(l)), float(sp.N(r))
            if rf - lf < 1e-12:
                continue
            kozep = (l + r) / 2
            d = df.replace(sp.sign, lambda g, k=kozep: sp.sign(sp.nsimplify(g.subs(X, k))))
            szelet = sp.Interval.open(l, r)
            if self.darabok is not None:
                szelet = szelet.intersect(self.dom)
            try:
                h = self.lepes_fut("szélsőértékek", sp.solveset, d, X, szelet)
            except _Kimarad:
                continue
            if isinstance(h, sp.FiniteSet):
                ki.extend(h)
            elif h is sp.S.EmptySet or h == sp.S.Reals or isinstance(h, sp.Interval):
                continue
            else:
                raise _Kimarad("a derivált zérusai nem zárt alakúak")
        return ki

    def szelsoertekek(self) -> list[dict]:
        if self.paratlan:
            return self._num_szelso()
        try:
            tores = self._toresek()
            stac = self._stacionarius(tores)
        except _Kimarad:
            return self._num_szelso()
        jelolt: list[tuple[float, sp.Expr]] = []
        for e in list(tores) + list(stac):
            v = _valos(e)
            if v is not None and self.af + 1e-9 < v < self.bf - 1e-9 and all(abs(v - u) > 1e-9 for u, _ in jelolt):
                jelolt.append((v, e))
        jelolt.sort(key=lambda p: p[0])
        pontok = [self.af] + [v for v, _ in jelolt] + [self.bf]
        ki = []
        for i, (v, e) in enumerate(jelolt):
            tipus = self._tipus(v, min(v - pontok[i], pontok[i + 2] - v))
            if tipus is None:
                continue
            try:
                y = sp.simplify(self.f.subs(X, e))
            except (TypeError, ValueError, RecursionError):
                continue
            yv = _valos(y)
            if yv is None:
                continue
            ki.append({"x": _szoveg(e), "y": _szoveg(y), "x_ertek": v, "y_ertek": yv, "tipus": tipus})
        return ki

    def _tipus(self, c: float, hely: float) -> str | None:
        """Helyi szélsőérték-e a c: az f(c) az f(c±h)-hoz képest (a töréspontnál is jó)."""
        h = max(min(0.01 * (self.bf - self.af), 0.25 * hely), 1e-9)
        fm, f0, fp = self.num(c - h), self.num(c), self.num(c + h)
        if fm != fm or f0 != f0 or fp != fp:
            return None
        eps = 4e-16 * max(1.0, abs(f0), abs(fm), abs(fp))
        if f0 > fm + eps and f0 > fp + eps:
            return "maximum"
        if f0 < fm - eps and f0 < fp - eps:
            return "minimum"
        return None

    def _num_szelso(self) -> list[dict]:
        self.numerikus = True
        ki: list[dict] = []
        for lo, hi in self._szeletek(self.af, self.bf):
            if not (math.isfinite(lo) and math.isfinite(hi)) or hi - lo < 1e-12:
                continue
            xs = self._minta(lo, hi)
            ys = [self.num(v) for v in xs]
            for i in range(1, len(xs) - 1):
                y0, ym, yp = ys[i], ys[i - 1], ys[i + 1]
                if y0 != y0 or ym != ym or yp != yp:
                    continue
                if (y0 > ym and y0 >= yp) or (y0 < ym and y0 <= yp):
                    maximum = y0 > ym
                    l, r = xs[i - 1], xs[i + 1]
                    for _ in range(100):
                        m1, m2 = l + (r - l) / 3, r - (r - l) / 3
                        f1, f2 = self.num(m1), self.num(m2)
                        if f1 != f1 or f2 != f2:
                            break
                        if (f1 < f2) == maximum:
                            l = m1
                        else:
                            r = m2
                    c = 0.5 * (l + r)
                    yc = self.num(c)
                    tipus = self._tipus(c, min(c - xs[0], xs[-1] - c, 0.5 * (xs[2] - xs[0]) * 20))
                    if yc == yc and abs(yc) < POLUS_KORLAT and tipus and all(abs(c - p["x_ertek"]) > 1e-6 for p in ki):
                        ki.append({"x": _szam_szoveg(c), "y": _szam_szoveg(yc), "x_ertek": c, "y_ertek": yc,
                                   "tipus": tipus})
        ki.sort(key=lambda p: p["x_ertek"])
        if ki:
            self.figyelmeztetesek.append("szélsőértékek: közelítő (numerikus) értékek")
        return ki

    # -- aszimptoták
    def _hatar(self, kif, pont, irany=None):
        return self.lepes_fut("aszimptoták", sp.limit, kif, X, pont, *([irany] if irany else []))

    @staticmethod
    def _vegtelen(v) -> bool:
        return v in (sp.oo, -sp.oo, sp.zoo)

    def _fuggoleges_jeloltek(self) -> list[sp.Expr]:
        ki: list[sp.Expr] = []
        if self.darabok is not None:
            for iv in self.darabok:
                for p in (iv.start, iv.end):
                    if p.is_finite:
                        ki.append(p)
        g = self.f.rewrite(sp.cos) if self.f.has(sp.tan, sp.cot) else self.f
        try:
            _, nevezo = sp.fraction(sp.together(g))
        except (ValueError, TypeError, RecursionError):
            nevezo = sp.Integer(1)
        kezelendo = []
        if nevezo.has(X):
            kezelendo.append(nevezo)
        kezelendo += [lg.args[0] for lg in self.f.atoms(sp.log) if lg.args[0].has(X)]
        for g in kezelendo:
            try:
                h = self.lepes_fut("aszimptoták", sp.solveset, g, X, self.ablak)
            except _Kimarad:
                continue
            if isinstance(h, sp.FiniteSet):
                ki.extend(h)
        egyedi: list[tuple[float, sp.Expr]] = []
        for p in ki:
            v = _valos(p)
            if v is not None and self.af - 1e-12 <= v <= self.bf + 1e-12 and all(abs(v - u) > 1e-9 for u, _ in egyedi):
                egyedi.append((v, p))
        return [p for _, p in sorted(egyedi, key=lambda t: t[0])]

    def _num_polusok(self) -> list[float]:
        """Tartalék ismeretlen szerkezetű értelmezési tartományra (pl. `tan(x^3)`): az ellentétes előjelű, nagy
        szomszéd értékek közti átmenet, bisection-nel finomítva, a növekedés ellenőrzésével."""
        ki: list[float] = []
        for lo, hi in self._szeletek(self.af, self.bf):
            if not (math.isfinite(lo) and math.isfinite(hi)) or hi - lo < 1e-12:
                continue
            xs = self._minta(lo, hi, 3 * MINTA)
            ys = [self.num(v) for v in xs]
            veges = sorted(abs(y) for y in ys if y == y)
            kozep = veges[len(veges) // 2] if veges else 0.0
            for i in range(1, len(xs)):
                y0, y1 = ys[i - 1], ys[i]
                if y0 != y0 or y1 != y1 or (y0 > 0) == (y1 > 0) or max(abs(y0), abs(y1)) < 20 * (1 + kozep):
                    continue
                l, r = xs[i - 1], xs[i]
                for _ in range(100):
                    m = 0.5 * (l + r)
                    fm = self.num(m)
                    if fm != fm:
                        break
                    if (fm > 0) == (y0 > 0):
                        l = m
                    else:
                        r = m
                p = 0.5 * (l + r)
                if (self._szamokban_nov(p, 1) or self._szamokban_nov(p, -1)) and all(abs(p - u) > 1e-6 for u in ki):
                    ki.append(p)
        return ki

    def _oldal_ertelmezett(self, v: float, irany: int) -> bool:
        return self.num(v + irany * 1e-7 * max(1.0, abs(v))) == self.num(v + irany * 1e-7 * max(1.0, abs(v)))

    def aszimptotak(self) -> tuple[list[dict], list[dict]]:
        egyenes: list[dict] = []
        ferde: list[dict] = []
        for p in self._fuggoleges_jeloltek():
            v = float(sp.N(p))
            talalat = False
            for irany, jel in ((1, "+"), (-1, "-")):
                if not self._oldal_ertelmezett(v, irany):
                    continue
                try:
                    if self._vegtelen(self._hatar(self.f, p, jel)):
                        talalat = True
                        break
                except _Kimarad:
                    if self._szamokban_nov(v, irany):
                        talalat = True
                        self.numerikus = True
                        break
            if talalat:
                egyenes.append({"egyenlet": f"x={_szoveg(p)}", "tipus": "fuggoleges", "ertek": v})
        if self.darabok is None:                                   # ismeretlen szerkezet: a mintavétel is keres
            for v in self._num_polusok():
                if all(abs(v - d["ertek"]) > 1e-6 for d in egyenes):
                    egyenes.append({"egyenlet": f"x={_szam_szoveg(v)}", "tipus": "fuggoleges", "ertek": v})
                    self.numerikus = True
                    self.figyelmeztetesek.append("aszimptoták: közelítő (numerikus) helyek")
        egyenes.sort(key=lambda d: d["ertek"])
        vizszintes: list[tuple[str, float]] = []
        for irany, vegtelen in ((1, sp.oo), (-1, -sp.oo)):
            if not (math.isfinite(self.num(irany * 1e4)) and math.isfinite(self.num(irany * 1e6))):
                continue                                           # az értelmezési tartomány nem nyúlik a végtelenbe
            try:
                L = self._hatar(self.f, vegtelen)
            except _Kimarad:
                continue
            Lv = _valos(L)
            if Lv is not None:
                e = f"y={_szoveg(L)}"
                if all(e != k for k, _ in vizszintes):
                    vizszintes.append((e, Lv))
            elif self._vegtelen(L):
                try:
                    m = self._hatar(self.f / X, vegtelen)
                    mv = _valos(m)
                    if mv is not None and mv != 0:
                        n = self._hatar(sp.simplify(self.f - m * X), vegtelen)
                        nv = _valos(n)
                        if nv is not None and not self._egybeesik(irany, mv, nv):
                            egyenlet = f"y={_szoveg(sp.simplify(m * X + n))}"
                            if all(egyenlet != d["egyenlet"] for d in ferde):
                                ferde.append({"egyenlet": egyenlet, "tipus": "ferde", "meredekseg": mv, "eltolas": nv})
                except _Kimarad:
                    continue
        egyenes += [{"egyenlet": e, "tipus": "vizszintes", "ertek": v} for e, v in vizszintes]
        return egyenes, ferde

    def _egybeesik(self, irany: int, m: float, b: float) -> bool:
        """A „ferde aszimptota” maga a függvény-e a végtelenben (egyenes, `abs(x)`): akkor nem aszimptota."""
        for x in (irany * 1e3, irany * 3e3):
            v = self.num(x)
            if v != v or abs(v - (m * x + b)) > 1e-9 * max(1.0, abs(v)):
                return False
        return True

    def _szamokban_nov(self, v: float, irany: int) -> bool:
        """Tartalék a `limit` időtúllépésére: a |f| a pólushoz közeledve monoton, nagyságrendeken át nő."""
        ertekek = [abs(self.num(v + irany * h)) for h in (1e-3, 1e-5, 1e-7)]
        return all(e == e for e in ertekek) and ertekek[0] < ertekek[1] < ertekek[2] and ertekek[2] > 1e5


def elemez(kifejezes: str, ablak, lepes_idokorlat_s: float = 3.0) -> dict:
    """A kifejezés (egy `x` változó) jellemzői az `ablak` = [alsó, felső] zárt intervallumán. Mindig szótárat ad:
    `allapot` = `ok` | `reszleges` (egy lépés kimaradt, a `figyelmeztetesek` megnevezi) | `hiba` (`uzenet`)."""
    try:
        if not isinstance(ablak, (list, tuple)) or len(ablak) != 2:
            raise ValueError("az ablak két határ: [alsó, felső]")
        a, b = _hatar_szam(ablak[0]), _hatar_szam(ablak[1])
        if not (float(sp.N(a)) < float(sp.N(b))):
            raise ValueError("az ablak alsó határa kisebb legyen a felsőnél")
        if not isinstance(kifejezes, str):
            raise ValueError("a kifejezés szöveg legyen")
        f = M.elemez(kifejezes)
        if f.free_symbols - {X}:
            raise ValueError("a kifejezésben csak az x változó állhat")
    except (ValueError, M.MatekHiba) as h:
        return {"allapot": "hiba", "uzenet": str(h)}
    el = _Elemzo(f, a, b, float(lepes_idokorlat_s))
    ki: dict = {"allapot": "ok", "kifejezes": _szoveg(f), "ertelmezes": str(el.dom)}
    for kulcs, fv, alap in (("zerushelyek", el.zerushelyek, []), ("szelsoertekek", el.szelsoertekek, [])):
        try:
            ki[kulcs] = fv()
        except _Kimarad:
            ki[kulcs] = alap
    try:
        ki["aszimptotak"], ki["ferde_aszimptotak"] = el.aszimptotak()
    except _Kimarad:
        ki["aszimptotak"], ki["ferde_aszimptotak"] = [], []
    ki["numerikus"] = el.numerikus
    ki["figyelmeztetesek"] = el.figyelmeztetesek
    if el.reszleges:
        ki["allapot"] = "reszleges"
    return ki
