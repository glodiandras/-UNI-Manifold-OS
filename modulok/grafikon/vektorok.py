"""Közös vektorok a Python és a TypeScript oldal paritásához (C35a).

A felület (`app/src/szerkeszto/renderelok/plot/kifejezes.ts`, `forras.ts`) a ```plot blokkot és a kifejezéseit saját
elemzővel olvassa, hogy a rajz azonnal, hálózat nélkül elkészüljön; a vektorok rögzítik, hogy ugyanazt az értéket és
ugyanazt az ábrát adja, mint a Python-oldal. Két fájl a `vektorok/` alatt:

- `kifejezes.json`: kifejezés, x → érték (`null`, ha a pont a valós értelmezési tartományon kívül esik); az érték a
  `kozos.matek.elemez` szemantikájából jön (D-5: a páratlan nevezőjű tört kitevő valós), SymPy-vel kiértékelve;
  `hibas_mindketto`: az `elemez` is, a felület is elutasítja; `hibas_csak_ts`: a Python elfogadja, a felület
  **szándékosan szigorúbb** (D-4: függvényhívás csak zárójellel, nincs `|x|`, nincs `sin^2(x)`, nincs faktoriális).
- `forras.json`: blokk-szöveg → ábra (`formatum.abra_szotar`) és kanonikus alak (`formatum.szerializal`).

Előállítás: `bin/mos grafikon vektorok --ir`; ellenőrzés (elsodródás-őr): `bin/mos grafikon vektorok`.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import sympy as sp

from . import felismeres as R
from . import formatum as F
from . import jellemzok as J

MAPPA = Path(__file__).resolve().parent / "vektorok"
_M = R._matek                                             # kozos.matek

XS = [-8.0, -3.0, -2.5, -1.0, -0.5, 0.0, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 4.5, 9.0]

# Az elfogadott nyelv egy-egy szerkezete: precedencia, implicit szorzás, hatvány, gyök, abszolútérték, trigonometria…
KIFEJEZESEK = [
    "x", "-x", "x + 1", "2x", "1.5*x - 0.25", "x^2", "-x^2", "x^3 - 3x", "x^2 - 4x + 5", "x^4", "x^5 - x",
    "x^2/4", "x^2/(x+1)", "(x^3 - x)/(x^2 + 1)", "x - 1/x", "2^x - 2^-x", "x^x",
    "2^x", "2^-x", "2^(2-x) + 5", "e^x", "e^(-x^2)", "exp(x)", "exp(-x)", "x*e^(-x)",
    "1/x", "1/x^2", "x/(x^2-1)", "(x^2-1)/(x-1)", "(x+1)/(x-2)", "1/(1+x^2)",
    "sqrt(x)", "sqrt(x+3) - 2", "sqrt(4 - x^2)", "sqrt(3x^2+1)", "x^(1/2)", "x^0.5",
    "x^(1/3)", "x^(2/3)", "x^(-1/3)", "root(x,3)", "root(x,2)", "root(x,5)", "root(x,3)^2", "root(x,4)",
    "abs(x)", "Abs(x-2)+1", "2abs(x)", "abs(x) - 3", "abs(abs(x)-2)",
    "sin(x)", "cos(x)", "tan(x)", "tg(x)", "cot(x)", "ctg(x)", "sin(2x)", "sin(x)^2", "sin(x)^2*cos(x)",
    "sin(x) + cos(x)", "2sin(x)", "3sin(x)cos(x)", "sin(x)cos(x)", "x sin(x)",
    "asin(x)", "acos(x)", "atan(x)",
    "ln(x)", "lg(x)", "log(x)", "log(x, 2)", "log(x,10)", "log(x^2+1)", "ln(x)/x", "x*ln(x)",
    "pi*x", "x/pi", "pi", "e", "2pi",
    "(x+1)(x-1)", "x(x+1)", "2(x+1)", "(x+1)(x+2)(x+3)",
    "-(x+1)", "-x^2 + 8", "2 - x^3", "(-x)^2", "-2^2", "x**2", "2**x",
]

# A felület is, az `elemez` is elutasítja.
HIBAS_MINDKETTO = [
    "x^2^3", "2^(3^2)", "x^10000", "1234567890123456", "sin(", "x +", "()", "foo(x)", "x_1", "x@2", "sqrt", "x^",
    "^x", "x..2", "((x)", "sin^2(x)",
    # A3-29: nem ismert állandó — a sima objektum prototípus-kulcsai (`constructor`, `toString`…) sem állandók
    "constructor", "toString", "valueOf", "hasOwnProperty", "isPrototypeOf", "__proto__", "x + constructor",
    "x*toString", "2valueOf",
]

# A Python elfogadja, a felület szándékosan szigorúbb (D-4): ezeket a `forras.ts` / `kifejezes.ts` elutasítja.
# (Egy `x` változós kifejezést vár: más betű — `y`, `a` — ismeretlen változó.)
HIBAS_CSAK_TS = [
    "sin x", "sin x cos x", "cos x + 1", "x!", "factorial(x)", "binomial(x,2)", "xx", "2 3", "ln x", "sqrt x",
    "x y z w", "y + 1", "a*x",
]

# A ```plot blokkok (kerítés nélkül): minden elemfajta, a határ- és hibaesetek.
BLOKKOK = [
    "",
    "   \n\n  ",
    "# csak megjegyzés",
    "y = x",
    "y = x^2 + 2",
    '  y   =   x  ^ 2  ',
    "y\t=\tx",
    "y = sin(2*x)  # sorvégi megjegyzés",
    'y = x "a # b"',
    'y = x^2 "f \\"x\\""',
    'y = x "\\\\"',
    "y = x +",
    "Y = x",
    "x = 3",
    'y = x "nincs lezárva',
    # A3-14: a címke karakterosztálya (`CIMKE`) bármit elfogad, a HTML-jelet is — a megjelenítés szövegként történik
    'pont (1, 1) "<img src=x onerror=alert(1)>"',
    'pont (1, 1) "<a href=javascript:alert(1) style=position:fixed>x</a> & é"',
    'y = x "<b>fél"',
    "x in [-4, 4]",
    "y in [-2, 10]",
    "y in [-2, 10]\nx in [-4, 4]\ny = x",
    "x in [-2*pi, 2*pi]\ny = sin(x)",
    "x in [-4, 4]\nx in [-1, 1]\ny = x",
    "x in [a, b]",
    "x = 3*cos(t), y = 2*sin(t), t in [0, 2*pi]",
    'x = cos(s), y = sin(s), s in [0, 2*pi] "kör"',
    "x = t^2, y = t^3, t in [-1, 1]",
    "x = t, y = t^2",
    "y < x",
    "y <= x^2 - 1",
    "y > 2x + 1",
    'y >= -x "föléje"',
    "y ≤ x^2",
    "y ≥ 1",
    "y −x",
    "y = x − 1",
    "pont (2, 1)",
    'pont (pi/2, 1) "csúcs"',
    "pont (1; 2)",
    "valami ismeretlen\ny = x",
    "y = x\r\ny = 2x\r\n",
    "y = x y = 2x",
    "# példa\ny in [-2, 10]\nx in [-4, 4]\ny = x^2 + 2  \"f \\\"x\\\"\"   # sorvégi megjegyzés\n"
    "x = 3*cos(t), y = 2*sin(t), t in [0, 2*pi]\ny >= x^2\npont (2, 1) \"min\"\nvalami ismeretlen",
    "\n".join(f"y = x + {k}" for k in range(70)),
    "y = x" + "+x" * 1100,
]


def ertek(f: sp.Expr, v: float) -> float | None:
    """A kifejezés értéke x = v-ben (SymPy, 20 értékes jegy); `None`, ha nem valós vagy nem véges."""
    g = J._valos_gyokos(f)
    try:
        c = complex(sp.N(g.subs(J.X, sp.Float(v, 30)), 20))
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if c != c or not math.isfinite(c.real) or not math.isfinite(c.imag):
        return None
    if abs(c.imag) > 1e-12 * max(1.0, abs(c.real)):
        return None
    return c.real


def _tetel(kif: str, xs: list[float], forras: str | None = None) -> list[dict]:
    f = _M.elemez(kif)
    ki = []
    for v in xs:
        t = {"kifejezes": kif, "x": float(v), "ertek": ertek(f, v)}
        if forras:
            t["forras"] = forras
        ki.append(t)
    return ki


def _arany():
    import importlib.util
    ut = Path(R.__file__).resolve().parents[1] / "eval" / "grafikon" / "feladat.py"
    spec = importlib.util.spec_from_file_location("mos_eval_grafikon_vektor", ut)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.ARANY


def _ablak_pontok(ablak: str, n: int = 21) -> list[float]:
    a, b = (J._valos(_M.elemez(s.strip())) for s in ablak.strip("[]").split(","))
    return [a + (b - a) * i / (n - 1) for i in range(n)]


def general() -> dict:
    """A két vektorfájl tartalma."""
    tetelek: list[dict] = []
    for kif in KIFEJEZESEK:
        tetelek += _tetel(kif, XS)
    blokkok: list[dict] = []
    for szoveg in BLOKKOK:
        a = F.elemez(szoveg)
        blokkok.append({"szoveg": szoveg, "abra": F.abra_szotar(a), "kanonikus": F.szerializal(a)})
    for k in _arany()["kepletek"]:
        j = R.felismer(k["keplet"])
        azon = f"arany:{k['id']}"
        kif = j.abra.elemek[0].kifejezes
        tetelek += _tetel(kif, _ablak_pontok(k["vart"]["ablak"]), azon)
        blokkok.append({"szoveg": F.szerializal(j.abra), "abra": F.abra_szotar(j.abra),
                        "kanonikus": F.szerializal(j.abra), "forras": azon})
    return {"kifejezes": {"verzio": 1, "tetelek": tetelek, "hibas_mindketto": HIBAS_MINDKETTO,
                          "hibas_csak_ts": HIBAS_CSAK_TS},
            "forras": {"verzio": 1, "tetelek": blokkok}}


def ir() -> list[Path]:
    MAPPA.mkdir(exist_ok=True)
    ki = []
    for nev, tartalom in general().items():
        fajl = MAPPA / f"{nev}.json"
        fajl.write_text(json.dumps(tartalom, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        ki.append(fajl)
    return ki


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--ir" in argv:
        for f in ir():
            print("írva:", f)
        return 0
    uj = general()
    rossz = []
    for nev, tartalom in uj.items():
        fajl = MAPPA / f"{nev}.json"
        if not fajl.exists() or json.loads(fajl.read_text(encoding="utf-8")) != json.loads(json.dumps(tartalom)):
            rossz.append(nev)
    print("RENDBEN: a vektorfájlok naprakészek" if not rossz else f"ELSODRÓDOTT: {', '.join(rossz)} (--ir)")
    return 1 if rossz else 0
