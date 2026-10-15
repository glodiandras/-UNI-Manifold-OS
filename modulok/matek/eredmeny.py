"""A CAS-eredmények megjelenítése és összevetése (C24b) — a homokozó megbízható `matek.eredmeny` művelete.

A bemenet a homokozó `kod` műveletének JSON-eredménye (`homokozo.kod.szerializal`: `halmaz`, `intervallum`, `par`, `kifejezes`,
`logikai`, `egyeb`). A szöveges elemeket a nem megbízható kód állította elő, ezért a SymPy-olvasásuk **csak a homokozó gyermekében**
fut (46. döntés); a szülő a kész LaTeX-szöveget és az egyezés logikai értékét kapja.

    osszevet(a, b=None) → {"latex_a", "latex_b", "egyezik": True | False | None}

Az `egyezik` None, ha valamelyik eredmény nem értelmezhető (`egyeb`), vagy a két alak nem vethető össze.
"""
from __future__ import annotations

MAX_ELEM = 50


def _sp():
    import sympy as sp
    return sp


def _olvas(s: str):
    sp = _sp()
    return sp.sympify(str(s)[:2000], rational=False)


def ertek(e: dict):
    """JSON-eredmény → („alak”, SymPy-érték); értelmezhetetlennél (None, None)."""
    sp = _sp()
    if not isinstance(e, dict):
        return None, None
    t = e.get("tipus")
    try:
        if t == "halmaz":
            return "halmaz", sp.FiniteSet(*[_olvas(x) for x in list(e.get("elemek") or [])[:MAX_ELEM]])
        if t == "intervallum":
            darabok = [sp.Interval(_olvas(d["a"]), _olvas(d["b"]), bool(d.get("bal_nyitott")), bool(d.get("jobb_nyitott")))
                       for d in list(e.get("darabok") or [])[:MAX_ELEM]]
            return "intervallum", sp.Union(*darabok) if darabok else sp.S.EmptySet
        if t == "kifejezes":
            return "kifejezes", _olvas(e.get("ertek", ""))
        if t == "par":
            return "par", {str(k): _olvas(v) for k, v in list((e.get("ertekek") or {}).items())[:MAX_ELEM]}
        if t == "logikai":
            return "logikai", bool(e.get("ertek"))
    except (sp.SympifyError, TypeError, ValueError, KeyError, SyntaxError, AttributeError):
        return None, None
    return None, None


def _szam_latex(v) -> str:
    return _sp().latex(v)


def latex(alak: str | None, v) -> str | None:
    """A végeredmény LaTeX-alakja (a magyar jelöléssel: `;` az elemek között, `[a;\\ b)` intervallum)."""
    sp = _sp()
    if alak is None:
        return None
    if alak == "halmaz":
        elemek = sorted(v, key=sp.default_sort_key)
        return r"\emptyset" if not elemek else r"\{" + r";\ ".join(_szam_latex(x) for x in elemek) + r"\}"
    if alak == "intervallum":
        if v is sp.S.EmptySet:
            return r"\emptyset"
        darabok = v.args if isinstance(v, sp.Union) else (v,)
        ki = []
        for d in darabok:
            if isinstance(d, sp.FiniteSet):
                ki.append(r"\{" + r";\ ".join(_szam_latex(x) for x in sorted(d, key=sp.default_sort_key)) + r"\}")
            elif isinstance(d, sp.Interval):
                ki.append(("(" if d.left_open else "[") + _szam_latex(d.start) + r";\ " + _szam_latex(d.end)
                          + (")" if d.right_open else "]"))
            else:
                ki.append(_szam_latex(d))
        return r" \cup ".join(ki)
    if alak == "kifejezes":
        return _szam_latex(v)
    if alak == "par":
        return r",\ ".join(f"{_szam_latex(sp.Symbol(k))} = {_szam_latex(x)}" for k, x in v.items())
    if alak == "logikai":
        return r"\text{igaz}" if v else r"\text{hamis}"
    return None


def _azonos(x, y) -> bool | None:
    sp = _sp()
    try:
        if x == y:
            return True
        d = sp.simplify(x - y)
        if d == 0:
            return True
        if d.is_number:
            return abs(complex(sp.N(d, 30))) < 1e-12
        return False
    except (TypeError, ValueError, AttributeError):
        return None


def _halmaz_egyezik(a, b) -> bool | None:
    a, b = list(a), list(b)
    if len(a) != len(b):
        return False
    maradek = list(b)
    for x in a:
        talalt = None
        for i, y in enumerate(maradek):
            if _azonos(x, y):
                talalt = i
                break
        if talalt is None:
            return False
        maradek.pop(talalt)
    return True


def _egyezik(aa: str | None, va, ab: str | None, vb) -> bool | None:
    sp = _sp()
    if aa is None or ab is None:
        return None
    if aa == "kifejezes" and ab == "halmaz" and len(vb) == 1:          # egyelemű halmaz ≡ egyetlen érték
        ab, vb = "kifejezes", list(vb)[0]
    if ab == "kifejezes" and aa == "halmaz" and len(va) == 1:
        aa, va = "kifejezes", list(va)[0]
    if {aa, ab} == {"halmaz", "intervallum"}:                         # a pontokból álló intervallum-unió halmaz is lehet
        h, i = (va, vb) if aa == "halmaz" else (vb, va)
        try:
            return bool(sp.FiniteSet(*h) == i) or (bool(i.is_FiniteSet) and _halmaz_egyezik(h, i))
        except (TypeError, ValueError, AttributeError):
            return None
    if aa != ab:
        return False
    if aa == "kifejezes":
        return _azonos(va, vb)
    if aa == "halmaz":
        return _halmaz_egyezik(va, vb)
    if aa == "intervallum":
        try:
            return bool(sp.simplify(va.symmetric_difference(vb)) == sp.S.EmptySet)
        except (TypeError, ValueError, AttributeError, NotImplementedError):
            return None
    if aa == "par":
        if set(va) != set(vb):
            return False
        r = [_azonos(va[k], vb[k]) for k in va]
        return None if None in r else all(r)
    if aa == "logikai":
        return va == vb
    return None


def osszevet(a: dict, b: dict | None = None) -> dict:
    """Az első (és ha van, a második) eredmény LaTeX-alakja, és a kettő egyezése."""
    aa, va = ertek(a)
    ki = {"latex_a": latex(aa, va), "alak_a": aa, "latex_b": None, "alak_b": None, "egyezik": None}
    if b is not None:
        ab, vb = ertek(b)
        ki.update(latex_b=latex(ab, vb), alak_b=ab, egyezik=_egyezik(aa, va, ab, vb))
    return ki
