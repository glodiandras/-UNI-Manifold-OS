"""Biztonságos kifejezés-elemzés és ekvivalencia a matek-pontozókhoz.

A modell kimenete **nem fut kódként**: a szöveg előbb LaTeX-ből sima kifejezéssé alakul, utána karakter- és
névfehérlistán megy át, és csak ezután kapja meg a `parse_expr` korlátozott névtérrel. Ami a listán nincs
(attribútum, aláhúzásos név, idegen függvény), az `MatekHiba`.
"""
from __future__ import annotations

import re

import sympy as sp
from sympy.parsing.sympy_parser import (convert_xor, implicit_multiplication_application, parse_expr,
                                        rationalize, standard_transformations)


class MatekHiba(ValueError):
    pass


_VALTOZOK = set("xyztnkabcmpqruvw")
_FUGGVENYEK = {
    "sqrt": sp.sqrt, "root": sp.root, "log": sp.log, "ln": sp.log, "lg": lambda x: sp.log(x, 10),
    "exp": sp.exp, "sin": sp.sin, "cos": sp.cos, "tan": sp.tan, "tg": sp.tan, "cot": sp.cot, "ctg": sp.cot,
    "asin": sp.asin, "acos": sp.acos, "atan": sp.atan, "Abs": sp.Abs, "abs": sp.Abs,
    "factorial": sp.factorial, "binomial": sp.binomial,
}
_ALLANDOK = {"pi": sp.pi, "oo": sp.oo, "e": sp.E}
_GLOBAL = {"Integer": sp.Integer, "Float": sp.Float, "Rational": sp.Rational, "Symbol": sp.Symbol,
           "Function": sp.Function, "factorial": sp.factorial, "factorial2": sp.factorial2}
_ATALAKITAS = standard_transformations + (implicit_multiplication_application, convert_xor, rationalize)
_MEGENGEDETT = re.compile(r"^[0-9a-zA-Z+\-*/^().,! ]*$")
_UNICODE = {"−": "-", "–": "-", "—": "-", "·": "*", "×": "*", "⋅": "*", "÷": "/", "√": "sqrt", "π": "pi",
            "∞": "oo", "²": "^2", "³": "^3", "°": "", "≈": "", "≤": "<=", "≥": ">=", "∪": " U ", "∈": " in "}


def _kapcsos(s: str, i: int) -> tuple[str, int]:
    """Az `i`-n nyíló `{…}` tartalma és a zárás utáni hely; ha nem kapcsos áll ott: egy jel."""
    if i >= len(s):
        raise MatekHiba("csonka kifejezés")
    if s[i] != "{":
        m = re.match(r"\d+(?:\.\d+)?|\\?[a-zA-Z]+|.", s[i:])
        return m.group(0), i + len(m.group(0))
    melyseg = 0
    for j in range(i, len(s)):
        melyseg += (s[j] == "{") - (s[j] == "}")
        if melyseg == 0:
            return s[i + 1:j], j + 1
    raise MatekHiba("páratlan kapcsos zárójel")


def _parancs(s: str, nev: str, epit) -> str:
    """A `\\nev{a}{b}` (vagy `\\nev[n]{a}`) parancsok kifejtése belülről kifelé."""
    for _ in range(200):
        i = s.rfind("\\" + nev)
        if i < 0:
            return s
        j = i + len(nev) + 1
        opc = None
        if j < len(s) and s[j] == "[":
            z = s.find("]", j)
            if z < 0:
                raise MatekHiba("páratlan szögletes zárójel")
            opc, j = s[j + 1:z], z + 1
        while j < len(s) and s[j] == " ":
            j += 1
        a, j = _kapcsos(s, j)
        b = None
        if nev == "frac":
            while j < len(s) and s[j] == " ":
                j += 1
            b, j = _kapcsos(s, j)
        s = s[:i] + epit(a, b, opc) + s[j:]
    raise MatekHiba("túl mély egymásba ágyazás")


def latexbol(s: str) -> str:
    """LaTeX-szerű írásmódból a `parse_expr` által olvasható sima kifejezés."""
    s = (s or "").strip().strip("$").strip()
    for k, v in _UNICODE.items():
        s = s.replace(k, v)
    s = re.sub(r"\\(?:left|right|displaystyle|,|;|!|:|quad|qquad)\b|\\ ", " ", s)
    s = re.sub(r"\\(?:left|right)(?=[^a-zA-Z])", "", s)
    s = re.sub(r"\\(?:text|mathrm|operatorname)\s*\{([^{}]*)\}", r" \1 ", s)
    s = s.replace("{,}", ".").replace("\\%", "%")
    s = re.sub(r"\\(?:dfrac|tfrac|cfrac)\b", r"\\frac", s)
    s = re.sub(r"\\(?:cdot|times)\b", "*", s)
    s = re.sub(r"\\(?:leq|le)\b", "<=", s)
    s = re.sub(r"\\(?:geq|ge)\b", ">=", s)
    s = re.sub(r"\\infty\b", "oo", s)
    s = re.sub(r"\\(?:lvert|rvert|vert)\b", "|", s)
    s = _parancs(s, "frac", lambda a, b, o: f"(({a})/({b}))")
    s = _parancs(s, "sqrt", lambda a, b, o: f"root(({a}),({o}))" if o else f"sqrt({a})")
    s = re.sub(r"\\log_\{?([0-9a-z.]+)\}?\s*\(([^()]*)\)", r"log((\2),(\1))", s)
    s = re.sub(r"\\log_\{?([0-9a-z.]+)\}?\s*([0-9a-z.]+)", r"log((\2),(\1))", s)
    s = re.sub(r"\\(sin|cos|tan|tg|cot|ctg|ln|lg|log|exp|pi)\b", r" \1 ", s)
    s = re.sub(r"\^\s*\{", "^(", s)
    s = s.replace("{", "(").replace("}", ")")
    s = re.sub(r"\|([^|]+)\|", r"Abs(\1)", s)
    s = _tizedesvesszo(s)
    s = re.sub(r"(\d(?:\.\d+)?)\s*%", r"((\1)/100)", s)
    return re.sub(r"\s+", " ", s).strip()


_KETARGUMENTUMOS = re.compile(r"(?:log|root|binomial)\s*$")


def _tizedesvesszo(s: str) -> str:
    """`2,5` → `2.5`, kivéve a kétargumentumos függvény vesszőjét (`log(8,2)`: 8 kettes alapú logaritmusa)."""
    ki = []
    for i, c in enumerate(s):
        if c == "," and 0 < i < len(s) - 1 and s[i - 1].isdigit() and s[i + 1].isdigit():
            melyseg, j = 0, i - 1
            while j >= 0:
                melyseg += (s[j] == ")") - (s[j] == "(")
                if melyseg < 0:
                    break
                j -= 1
            if not (j >= 0 and _KETARGUMENTUMOS.search(s[:j])):
                c = "."
        ki.append(c)
    return "".join(ki)


def elemez(s: str) -> sp.Expr:
    """Szöveg → sympy-kifejezés, a fehérlistán át. Hibás vagy tiltott tartalom → `MatekHiba`."""
    t = latexbol(s)
    if not t or len(t) > 300:
        raise MatekHiba("üres vagy túl hosszú kifejezés")
    if "\\" in t or not _MEGENGEDETT.match(t):
        raise MatekHiba(f"nem megengedett jel: {t!r}")
    for nev in re.findall(r"[A-Za-z]+", t):
        if nev in _FUGGVENYEK or nev in _ALLANDOK:
            continue
        if not all(c in _VALTOZOK for c in nev) or len(nev) > 3:
            raise MatekHiba(f"ismeretlen név: {nev}")
    if (re.search(r"\d{13,}", t) or re.search(r"(?:\^|\*\*)\s*\(?\s*\d{4,}", t)
            or re.search(r"(?:\^|\*\*)\s*\(?\s*[\d.]+\s*\)?\s*(?:\^|\*\*)", t) or "!!" in t
            or re.search(r"\d{3,}\s*!|factorial\s*\(\s*\d{3,}", t)):
        raise MatekHiba("túl nagy szám vagy hatványtorony")
    helyi = dict(_FUGGVENYEK)
    helyi.update(_ALLANDOK)
    helyi.update({c: sp.Symbol(c, real=True) for c in _VALTOZOK})
    try:
        e = parse_expr(t, local_dict=helyi, global_dict=dict(_GLOBAL), transformations=_ATALAKITAS)
    except Exception as exc:                                   # a sympy sokféle hibát dob elemzéskor
        raise MatekHiba(f"nem elemezhető: {t!r} ({type(exc).__name__})") from None
    if not isinstance(e, sp.Expr):
        raise MatekHiba(f"nem kifejezés: {t!r}")
    return e


def _szam(e: sp.Expr) -> complex:
    if e.free_symbols:
        raise MatekHiba("a kifejezésben változó maradt")
    v = complex(sp.N(e, 15))
    if v != v:
        raise MatekHiba("nem szám")
    return v


def kozel(a: sp.Expr, b: sp.Expr, tures: float = 1e-6) -> bool:
    """Két számértékű kifejezés egyezik-e a (relatív) tűrésen belül."""
    x, y = _szam(a), _szam(b)
    return abs(x - y) <= (tures * abs(y) if y else tures)


_ELOTAG = re.compile(r"^\s*(?:[a-zA-Z]\s*(?:\([a-z]\))?(?:_\s*\{?[0-9, ]+\}?|[0-9])?\s*(?:=|≈|\\approx)\s*)")
_URES = ("nincs megoldas", "ures halmaz", "\\emptyset", "\\varnothing", "∅", "nincs valos megoldas", "nincs")


def _hajt(s: str) -> str:
    return s.translate(str.maketrans("áéíóöőúüű", "aeiooouuu")).lower()


def _mag(s: str, egysegek: tuple[str, ...] = ()) -> str:
    """Az érték a `x =`, `≈` előtag és a megadott mértékegységek nélkül."""
    s = (s or "").strip().strip("$").strip().rstrip(".").strip()
    s = re.sub(r"\\approx", "≈", s)
    for _ in range(2):
        s = _ELOTAG.sub("", s)
    s = s.lstrip("≈= ").strip()
    for e in sorted(egysegek, key=len, reverse=True):
        s = re.sub(r"\s*(?:\\text\{\s*)?" + re.escape(e) + r"\s*\}?\s*$", "", s)
    return s.strip()


def ertekek(s: str, egysegek: tuple[str, ...] = ()) -> list[sp.Expr]:
    """Megoldáshalmaz elemei a válaszból: `x_1 = 2; x_2 = -3`, `\\{2; -3\\}`, `2 és -3`, `\\pm 2`."""
    t = (s or "").strip().strip("$").strip().rstrip(".")
    if any(u in _hajt(t) for u in _URES) and not re.search(r"\d", t):
        return []
    t = re.sub(r"\\(?:left|right)", "", t)
    t = t.replace("\\{", "").replace("\\}", "")
    t = re.sub(r"^[a-zA-Z]\s*(?:\\in|∈)\s*", "", t.strip())
    if t.startswith("{") and t.endswith("}") and "\\" not in t[:2]:
        t = t[1:-1]
    darabok = re.split(r";|\s+és\s+|\s+vagy\s+|\\quad|\\lor|\\vee|\\text\{\s*(?:és|vagy)\s*\}|,\s+(?=[a-zA-Z\\\-+0-9])", t)
    ki: list[sp.Expr] = []
    for d in darabok:
        d = _mag(d, egysegek)
        if not d:
            continue
        if "\\pm" in d or "±" in d:
            bal, jobb = re.split(r"\\pm|±", d, maxsplit=1)
            bal = bal.strip() or "0"
            ki += [elemez(f"({bal})+({jobb})"), elemez(f"({bal})-({jobb})")]
        else:
            ki.append(elemez(d))
    return ki


def _halmaz_egyezik(vart: list[sp.Expr], kapott: list[sp.Expr], tures: float) -> bool:
    if len(vart) != len(kapott):
        return False
    maradek = list(kapott)
    for v in vart:
        for k in maradek:
            try:
                if kozel(k, v, tures):
                    maradek.remove(k)
                    break
            except MatekHiba:
                continue
        else:
            return False
    return True


def _vegpont(s: str) -> sp.Expr:
    s = s.strip()
    if _hajt(s) in ("+oo", "oo", "+\\infty", "\\infty", "+∞", "∞", "vegtelen"):
        return sp.oo
    if _hajt(s) in ("-oo", "-\\infty", "-∞", "−∞"):
        return -sp.oo
    return sp.nsimplify(elemez(s), rational=True)


_RELACIO = r"(<=|>=|<|>)"


def intervallum(s: str) -> sp.Set:
    """Intervallum(ok) uniója: `(2, oo)`, `]2; +∞[`, `[1; 3]`, `x > 2`, `1 <= x < 3`, `x < -1 vagy x >= 3`."""
    t = (s or "").strip().strip("$").strip().rstrip(".")
    for k, v in (("≤", "<="), ("≥", ">="), ("\\leq", "<="), ("\\geq", ">="), ("\\le", "<="), ("\\ge", ">="),
                 ("\\infty", "oo"), ("∞", "oo"), ("−", "-"), ("\\left", ""), ("\\right", ""), ("\\,", "")):
        t = t.replace(k, v)
    t = re.sub(r"^[a-zA-Z]\s*(?:\\in|∈)\s*", "", t.strip())
    reszek = [r.strip() for r in re.split(r"\\cup|∪|\s+U\s+|\s+vagy\s+|\\lor|\\text\{\s*vagy\s*\}", t) if r.strip()]
    if not reszek:
        raise MatekHiba("üres intervallum")
    halmaz: sp.Set = sp.S.EmptySet
    for r in reszek:
        m = re.match(r"^([\[\](])\s*(.+?)\s*[;,]\s*(.+?)\s*([\[\])])$", r)
        if m and not re.search(_RELACIO, r):
            a, b = _vegpont(m.group(2)), _vegpont(m.group(3))
            halmaz |= sp.Interval(a, b, m.group(1) != "[", m.group(4) != "]")
            continue
        m = re.match(rf"^(.+?)\s*{_RELACIO}\s*[a-zA-Z]\s*{_RELACIO}\s*(.+)$", r)
        if m:
            a, r1, r2, b = m.group(1), m.group(2), m.group(3), m.group(4)
            if r1[0] != r2[0]:
                raise MatekHiba("ellentétes irányú egyenlőtlenség")
            if r1[0] == ">":
                a, b, r1, r2 = b, a, r2.replace(">", "<"), r1.replace(">", "<")
            halmaz |= sp.Interval(_vegpont(a), _vegpont(b), r1 == "<", r2 == "<")
            continue
        m = re.match(rf"^[a-zA-Z]\s*{_RELACIO}\s*(.+)$", r)
        if m:
            rel, a = m.group(1), _vegpont(m.group(2))
            halmaz |= (sp.Interval(-sp.oo, a, True, rel == "<") if rel[0] == "<"
                       else sp.Interval(a, sp.oo, rel == ">", True))
            continue
        raise MatekHiba(f"nem intervallum: {r!r}")
    return halmaz


_MINTAPONTOK = (-2.3, -1.1, -0.4, 0.3, 0.9, 1.7, 2.6, 3.4, 5.2)


def kifejezes_egyezik(vart: sp.Expr, kapott: sp.Expr, tures: float = 1e-6) -> bool:
    """Két kifejezés azonossága: szimbolikusan, majd rögzített mintapontokon (legalább 4 értelmes ponton)."""
    szabad = sorted(vart.free_symbols | kapott.free_symbols, key=lambda s: s.name)
    if not szabad:
        return kozel(kapott, vart, tures)
    try:
        if sp.simplify(vart - kapott) == 0:
            return True
    except Exception:
        pass
    jo = 0
    for i, p in enumerate(_MINTAPONTOK):
        hely = {s: p + 0.37 * j for j, s in enumerate(szabad)}
        try:
            a, b = complex(sp.N(vart.subs(hely), 15)), complex(sp.N(kapott.subs(hely), 15))
        except (TypeError, ValueError):
            continue
        if a != a or b != b or abs(a) == float("inf") or abs(b) == float("inf"):
            continue
        if abs(a.imag) > 1e-9 and abs(b.imag) > 1e-9:       # mindkettő értelmezetlen a valósokon
            continue
        if abs(a - b) > tures * max(1.0, abs(a)):
            return False
        jo += 1
    return jo >= 4


def ekvivalens(vart: dict, valasz: str | None) -> tuple[bool, str]:
    """A válasz (a zárósor értéke) egyezik-e a várt eredménnyel → (igen/nem, indok)."""
    if valasz is None or not str(valasz).strip():
        return False, "nincs végeredmény-sor"
    tipus = vart.get("tipus")
    tures = float(vart.get("tures", 1e-6))
    egysegek = tuple(vart.get("egysegek", ()))
    try:
        if tipus == "szam":
            kapott = ertekek(valasz, egysegek)
            if len(kapott) != 1:
                return False, f"egy értéket vártunk, {len(kapott)} jött"
            return (kozel(kapott[0], elemez(vart["ertek"]), tures), "szám")
        if tipus == "halmaz":
            v = [elemez(x) for x in vart["ertekek"]]
            k = ertekek(valasz, egysegek)
            return _halmaz_egyezik(v, k, tures), f"halmaz: várt {len(v)}, kapott {len(k)} elem"
        if tipus == "intervallum":
            v = intervallum(vart["ertek"])
            k = intervallum(valasz)
            return bool(v == k or sp.simplify(v.symmetric_difference(k)) == sp.S.EmptySet), "intervallum"
        if tipus == "kifejezes":
            return kifejezes_egyezik(elemez(vart["ertek"]), elemez(_mag(valasz, egysegek)), tures), "kifejezés"
        if tipus == "par":
            return _par_egyezik(vart["ertekek"], valasz, tures), "pár"
    except MatekHiba as exc:
        return False, f"nem elemezhető: {exc}"
    raise ValueError(f"ismeretlen várt típus: {tipus}")


def _par_egyezik(vart: dict, valasz: str, tures: float) -> bool:
    """Nevesített értékek (`x = 4; y = 4`) vagy rendezett pár (`(4; 4)`) a várt nevek sorrendjében."""
    t = valasz.strip().strip("$").strip().rstrip(".")
    nev = r"[a-zA-Z](?:_?\{?\d+\}?)?"
    nevesitett = dict((re.sub(r"[_{}]", "", m.group(1)), m.group(2)) for m in
                      re.finditer(rf"({nev})\s*=\s*([^;=]+?)(?=\s*(?:;|,\s+{nev}\s*=|\s+és\s+|$))", t))
    if set(vart) <= set(nevesitett):
        return all(kozel(elemez(nevesitett[n]), elemez(e), tures) for n, e in vart.items())
    t = re.sub(r"^[A-Za-z]?\s*\(|\)$", "", t)
    darabok = [d for d in re.split(r";|,\s+", t) if d.strip()]
    if len(darabok) != len(vart):
        return False
    return all(kozel(elemez(d), elemez(e), tures) for d, e in zip(darabok, vart.values()))


def megoldashalmaz(egyenlet: str, valtozo: str = "x") -> sp.Set:
    """Egy `bal = jobb` egyenlet valós megoldáshalmaza (az arany-épség tesztjéhez: a levezetés szomszédos
    sorai ekvivalensek-e)."""
    if egyenlet.count("=") != 1:
        raise MatekHiba("egy egyenlőségjel kell")
    bal, jobb = egyenlet.split("=")
    x = sp.Symbol(valtozo, real=True)
    return sp.solveset(sp.Eq(elemez(bal), elemez(jobb)), x, domain=sp.S.Reals)
