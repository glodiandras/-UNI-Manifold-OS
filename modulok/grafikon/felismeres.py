"""Determinisztikus felismerés: LaTeX / TikZ-pgfplots képlet → ```` ```plot ```` blokk-javaslat (C35a).

Csak szabály és SymPy; modellt nem tölt, hálózatot nem hív, a vaultba nem ír. Ha a felismerés nem biztos,
kimondja (`bizonyossag="bizonytalan"`, `ok`), és a döntés a modell-ágra marad (C35b). A kifejezéseket a
`modulok/eval/kozos/matek.elemez` elemzi (LaTeX → SymPy, fehérlistával); új függőség nincs.

Szabály: a *bizonytalan* jobb, mint a téves. Biztos javaslat csak olyan képletből lesz, amelyben a rajzolandó
kifejezés egyértelmű, az elemzés hibátlan, és az ablakon belül nincs szakadás.
"""
from __future__ import annotations

import hashlib
import math
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import sympy as sp

from . import formatum as F
from . import jegyzet as J


def _kozos():
    """A `modulok/eval/kozos` csomag (a közös LaTeX → SymPy elemző): a hely a `MOS_MODULOK`-ból vagy a csomag helyéből."""
    modulok = os.environ.get("MOS_MODULOK") or str(Path(__file__).resolve().parents[1])
    ut = str(Path(modulok) / "eval")
    if ut not in sys.path:
        sys.path.insert(0, ut)
    from kozos import latex, matek
    return latex, matek


_latex, _matek = _kozos()
MatekHiba = _matek.MatekHiba
_X = sp.Symbol("x", real=True)

BIZTOS, BIZONYTALAN, NINCS = "biztos", "bizonytalan", "nincs"
ALAP_ABLAK = (-5.0, 5.0)           # alapértelmezett x-ablak; trigonometrikusnál [-2π, 2π]
MINTA = 401                        # mintavételi pontok az ablak-heurisztikához
_TRIG = (sp.sin, sp.cos, sp.tan, sp.cot, sp.asin, sp.acos, sp.atan)


@dataclass(frozen=True)
class Javaslat:
    fajta: str                     # fuggveny | parameteres | egyenlotlenseg | tikz | implicit | szakaszonkent | nem_abra
    bizonyossag: str               # biztos | bizonytalan | nincs
    ok: str                        # magyar indoklás (mindig kitöltött)
    forras_keplet: str
    kulcs: str                     # sha1(normalizált képlet)[:16]; a tiltólista jegyzet-úttól független kulcsa
    abra: F.Abra | None = None
    blokk: str = ""                # a jegyzetbe írható szöveg; üres, ha nincs rajzolható javaslat
    sor: int | None = None         # a képlet első sora a jegyzetben (1-től), `felismer_jegyzet` tölti
    veg_sor: int | None = None
    blokk_kovetkezik: bool = False  # a képlet alatt (3 soron belül) már van plot blokk


def kulcs(keplet: str) -> str:
    return hashlib.sha1(_latex.normalizal(keplet).encode("utf-8")).hexdigest()[:16]


# ---- szövegtisztítás és felbontás ---------------------------------------------------------------------------

# C35b: a függvény jegyzetbeli címkéje (`f: y = …`, `g_1: f(x) = …`): a címke elhagyható, a definíció marad (a gráf-blokk címkéje nem a
# jegyzet-jelölésből jön). Csak akkor, ha a kettőspont után közvetlenül `y =` vagy `f(x) =` áll (a `f: \mathbb{R} \to \mathbb{R}` nem).
_CIMKE_ELOTAG = re.compile(r"^[a-zA-Z](?:_\{?[0-9a-z]+\}?)?\s*:\s*(?=y\s*=|[a-zA-Z](?:_\{?[0-9a-z]+\}?)?\s*\(\s*[a-z]\s*\)\s*=)")


def _tisztit(s: str) -> str:
    t = (s or "").strip().strip("$").strip()
    t = re.sub(r"\\(?:displaystyle|left|right|big|Big|bigg|Bigg)(?![a-zA-Z])", "", t)
    t = re.sub(r"\\(?:dfrac|tfrac|cfrac)\b", r"\\frac", t)
    t = re.sub(r"\\(?:leqslant|leq|le)(?![a-zA-Z])", "<=", t)
    t = re.sub(r"\\(?:geqslant|geq|ge)(?![a-zA-Z])", ">=", t)
    t = t.replace("≤", "<=").replace("≥", ">=").replace("−", "-").replace("∈", " in ")
    t = re.sub(r"\\in(?![a-zA-Z])", " in ", t)
    t = re.sub(r"\\(?:quad|qquad|land|wedge)(?![a-zA-Z])", ",", t)
    t = re.sub(r"\\text\{\s*(?:ha|ahol|if|for|where|és)\s*\}", ",", t, flags=re.I)
    t = re.sub(r"\\[,;:! ]", " ", t)
    t = _CIMKE_ELOTAG.sub("", t.strip(), count=1)
    return t.strip(" .;,")


def _felbont(t: str) -> list[str]:
    """Felső szintű `,` / `;` mentén; a számok közti vessző (2,5) tizedesvessző."""
    reszek, melyseg, ki = [], 0, 0
    for i, c in enumerate(t):
        if c in "([{":
            melyseg += 1
        elif c in ")]}":
            melyseg -= 1
        elif c in ",;" and melyseg == 0:
            if c == "," and 0 < i < len(t) - 1 and t[i - 1].isdigit() and t[i + 1].isdigit():
                continue
            reszek.append(t[ki:i])
            ki = i + 1
    reszek.append(t[ki:])
    return [r.strip() for r in reszek if r.strip()]


_EGYENLOSEG = re.compile(r"(?<![<>!=])=(?!=)")
_RELACIO = re.compile(r"<=|>=|<|>")
_NEV_FGV = re.compile(r"^(?P<nev>[a-zA-Z](?:_\{?[0-9a-z]+\}?)?)\s*\(\s*(?P<v>[a-z])\s*\)$")
_SZAM_RE = r"[^<>=,;]+?"


class _Hiba(Exception):
    """Felismerési hiba: a javaslat bizonytalan vagy nem rajzolható; az üzenet az `ok`."""


# ---- kifejezések --------------------------------------------------------------------------------------------

_FV_NEVEK = r"sin|cos|tan|tg|cot|ctg|ln|lg|exp|asin|acos|atan"


def _kif(nyers: str) -> tuple[str, sp.Expr]:
    """LaTeX-kifejezés → (olvasható sima szöveg, SymPy). A szöveg `elemez`-hető és szerkezetileg azonos."""
    try:
        e = _matek.elemez(nyers)
    except MatekHiba as h:
        raise _Hiba(f"nem elemezhető kifejezés: {nyers.strip()!r} ({h})") from None
    szoveg = _matek.latexbol(nyers)
    szep = re.sub(r"\(\((\w+)\)/\((\w+)\)\)", r"\1/\2", szoveg)
    szep = re.sub(r"log\(\(([^()]+)\),\(([^()]+)\)\)", r"log(\1, \2)", szep)
    szep = re.sub(r"\s+", " ", szep).strip()
    szep = _kulso_zarojel(szep)
    szep = re.sub(r"/\((\w+)\)", r"/\1", szep)
    szep = re.sub(r"(?<![\w)])\((\w+)\)/", r"\1/", szep)
    szep = re.sub(rf"\b({_FV_NEVEK}|sqrt|Abs|abs|log) \(", r"\1(", szep).replace("Abs(", "abs(")
    szep = re.sub(rf"(\d)(?=(?:{_FV_NEVEK}|sqrt|abs|log)\()", r"\1*", szep)
    if re.search(rf"\b(?:{_FV_NEVEK})\b(?!\s*\()", szep):
        szep = _sstr(e)                # függvény zárójel nélkül (`sin 2x`): a SymPy kanonikus alakja egyértelmű
    else:
        try:
            if _matek.elemez(szep) != e:
                szep = _sstr(e)
        except MatekHiba:
            szep = _sstr(e)
    return szep, e


def _kulso_zarojel(s: str) -> str:
    """`((a)/(b))` → `(a)/(b)`: a teljes kifejezést körülvevő, fölösleges zárójel levétele."""
    while s.startswith("(") and s.endswith(")"):
        melyseg = 0
        for i, c in enumerate(s):
            melyseg += (c == "(") - (c == ")")
            if melyseg == 0 and i < len(s) - 1:
                return s
        s = s[1:-1].strip()
    return s


def _sstr(e: sp.Expr) -> str:
    return sp.sstr(e).replace("**", "^")


def _szam_szoveg(v: float) -> str:
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return f"{v:.6g}"


def _hatar_szoveg(nyers: str) -> tuple[str, float]:
    """Tartomány-határ: (kanonikus szöveg, szám); az egész és a tizedes szám számként, a többi (`2*pi`, `1/2`) szimbolikusan."""
    try:
        e = _matek.elemez(nyers)
        if e.free_symbols:
            raise _Hiba(f"a tartomány határa nem szám: {nyers.strip()!r}")
        ertek = float(sp.N(e, 15))
    except MatekHiba as h:
        raise _Hiba(f"nem elemezhető tartomány-határ: {nyers.strip()!r} ({h})") from None
    except TypeError:
        raise _Hiba(f"a tartomány határa nem valós szám: {nyers.strip()!r}") from None
    if not math.isfinite(ertek):
        raise _Hiba(f"végtelen tartomány-határ: {nyers.strip()!r}")
    return (_szam_szoveg(ertek) if (e.is_Integer or e.is_Float) else _sstr(e)), ertek


# ---- ablak-heurisztika --------------------------------------------------------------------------------------

def _mintak(f, lo: float, hi: float, n: int = MINTA) -> list[tuple[float, float | None]]:
    ki = []
    for i in range(n):
        x = lo + (hi - lo) * i / (n - 1)
        try:
            v = f(x)
            if isinstance(v, complex):
                v = v.real if abs(v.imag) < 1e-9 else None
            v = float(v) if v is not None else None
            if v is not None and (not math.isfinite(v) or abs(v) > 1e8):
                v = None
        except (ArithmeticError, ValueError, TypeError, OverflowError):
            v = None
        ki.append((x, v))
    return ki


def _szep_hatarok(lo: float, hi: float) -> tuple[float, float]:
    szelesseg = hi - lo
    if szelesseg <= 1e-12:
        lo, hi, szelesseg = lo - 1, hi + 1, 2.0
    lo -= 0.08 * szelesseg
    hi += 0.08 * szelesseg
    nyers = (hi - lo) / 10
    p = 10 ** math.floor(math.log10(nyers))
    lepes = next(m * p for m in (1, 2, 5, 10) if m * p >= nyers)
    return math.floor(lo / lepes) * lepes, math.ceil(hi / lepes) * lepes


def _y_hatar(ys: list[float]) -> tuple[float, float]:
    """Az y-ablak nyers határa: a teljes terjedelem; ha egy-két szélsőséges érték (az értelmezési tartomány széle
    közelében) tízszeresére nyújtaná, az 1.–99. percentilis."""
    rendezett = sorted(ys)
    teljes = (rendezett[0], rendezett[-1])
    n = len(rendezett)
    if n < 50:
        return teljes
    vagott = (rendezett[int(0.01 * (n - 1))], rendezett[int(0.99 * (n - 1))])
    if (teljes[1] - teljes[0]) > 10 * max(vagott[1] - vagott[0], 1e-9):
        return vagott
    return teljes


def _pol(ertekek: list[float]) -> bool:
    """Pólus-gyanú: szomszédos, ellentétes előjelű, a mediánhoz képest nagyon nagy értékek."""
    if len(ertekek) < 5:
        return False
    abszolut = sorted(abs(v) for v in ertekek)
    kuszob = 20 * max(1.0, abszolut[len(abszolut) // 2])
    return any(a * b < 0 and abs(a) > kuszob and abs(b) > kuszob for a, b in zip(ertekek, ertekek[1:]))


def _ablak(e: sp.Expr, korlat: tuple[str | None, str | None] | None) -> tuple[tuple[str, str], tuple[str, str], list[str]]:
    """(x-ablak, y-ablak, figyelmeztetések); a figyelmeztetés `bizonytalan` okot jelent."""
    figy: list[str] = []
    trig = e.has(*_TRIG)
    alap = (-2 * math.pi, 2 * math.pi) if trig else ALAP_ABLAK
    szimb = ("-2*pi", "2*pi") if trig else None
    f = sp.lambdify(_X, e, modules=["math"])
    a_sz, b_sz = (korlat or (None, None))
    if a_sz is not None or b_sz is not None:
        a = _hatar_szoveg(a_sz) if a_sz is not None else None
        b = _hatar_szoveg(b_sz) if b_sz is not None else None
        if a and b:
            lo, hi = a[1], b[1]
        elif a:
            lo, hi = a[1], a[1] + 10
        else:
            lo, hi = b[1] - 10, b[1]
        if lo >= hi:
            raise _Hiba("üres vagy fordított x-tartomány")
        xt = ((a[0] if a else _szam_szoveg(lo)), (b[0] if b else _szam_szoveg(hi)))
    else:
        lo, hi = alap
        xt = szimb or (_szam_szoveg(lo), _szam_szoveg(hi))
        m = _mintak(f, lo, hi)
        ervenyes = [i for i, (_, v) in enumerate(m) if v is not None]
        if len(ervenyes) < 0.2 * len(m):
            raise _Hiba("a kifejezés az alap ablakon alig értelmezett (a tartomány kézi megadása kell)")
        elso, utolso = ervenyes[0], ervenyes[-1]
        if utolso - elso + 1 != len(ervenyes):
            figy.append("a függvény az ablakon belül nem értelmezett (szakadás, aszimptota)")
        else:
            if elso > 0:
                lo = _hatarpont(f, m[elso - 1][0], m[elso][0])
            if utolso < len(m) - 1:
                hi = _hatarpont(f, m[utolso + 1][0], m[utolso][0])
            if elso > 0 or utolso < len(m) - 1:
                xt = (_szam_szoveg(round(lo, 6)), _szam_szoveg(round(hi, 6)))
    m = _mintak(f, lo, hi)
    ys = [v for _, v in m if v is not None]
    if not ys:
        raise _Hiba("az x-tartományon a kifejezés sehol nem értelmezett")
    if (korlat and (korlat[0] or korlat[1])) and any(v is None for _, v in m[1:-1]):
        figy.append("a megadott tartományon a függvény nem mindenhol értelmezett (szakadás, aszimptota)")
    if e.has(sp.tan, sp.cot) or _pol(ys):
        figy.append("aszimptota/pólus gyanú (a CAS-os ellenőrzés a C35b dolga)")
    ylo, yhi = _szep_hatarok(*_y_hatar(ys))
    return xt, (_szam_szoveg(ylo), _szam_szoveg(yhi)), figy


def _hatarpont(f, rossz: float, jo: float) -> float:
    """Az értelmezési tartomány széle felezéssel (a `rossz` és a `jo` között)."""
    for _ in range(60):
        k = (rossz + jo) / 2
        try:
            v = f(k)
            ok = not (isinstance(v, complex) and abs(v.imag) > 1e-9) and math.isfinite(float(v.real if isinstance(v, complex) else v))
        except (ArithmeticError, ValueError, TypeError, OverflowError):
            ok = False
        if ok:
            jo = k
        else:
            rossz = k
    return jo


# ---- korlátok ---------------------------------------------------------------------------------------------

_K_INTERVALLUM = re.compile(rf"^(?P<v>[a-z])\s+in\s*[\[(]\s*(?P<a>{_SZAM_RE})\s*[;,]\s*(?P<b>{_SZAM_RE})\s*[\])]$")
_K_VALOS = re.compile(r"^[a-z]\s+in\s*(?:\\mathbb\{R\}|\\R|R)$")
_K_KETOLDALI = re.compile(rf"^(?P<a>{_SZAM_RE})\s*(?P<r1><=|<)\s*(?P<v>[a-z])\s*(?P<r2><=|<)\s*(?P<b>{_SZAM_RE})$")
_K_EGYOLDALI = re.compile(rf"^(?P<v>[a-z])\s*(?P<r><=|>=|<|>)\s*(?P<a>{_SZAM_RE})$")


def _korlat(resz: str):
    """Egy tartomány-megszorító rész → (változó, alsó|None, felső|None); `()`, ha nincs hatása; `None`, ha nem korlát."""
    if _K_VALOS.match(resz):
        return ()
    m = _K_INTERVALLUM.match(resz)
    if m:
        return m["v"], m["a"], m["b"]
    m = _K_KETOLDALI.match(resz)
    if m:
        return m["v"], m["a"], m["b"]
    m = _K_EGYOLDALI.match(resz)
    if m and m["v"] != "y":
        if m["r"] in (">=", ">"):
            return m["v"], m["a"], None
        return m["v"], None, m["a"]
    return None


# ---- az egyes alakok ----------------------------------------------------------------------------------------

def _fuggveny_def(bal: str):
    """`y` vagy `f(x)` → (név|None, változó); különben `None`."""
    bal = bal.strip()
    if bal == "y":
        return None, "x"
    m = _NEV_FGV.match(bal)
    if m and m["nev"] != "y":
        return m["nev"], m["v"]
    if m:
        return None, m["v"]
    raise _Hiba(f"a bal oldal nem függvény-definíció: {bal!r}")


def _atnevez(szoveg: str, honnan: str, hova: str) -> str:
    return re.sub(rf"\b{honnan}\b", hova, szoveg)


def _egy_fuggveny(p: str) -> tuple[F.Fuggveny, sp.Expr, list[str], str]:
    """Egyenlőség-rész → (elem, kifejezés x-ben, bizonytalansági okok, az eredeti változó neve)."""
    reszek = _EGYENLOSEG.split(p)
    if re.search(r"\by\b", "".join(reszek[1:])):
        raise _Hiba("implicit alak (y a jobb oldalon is szerepel)")
    nev, v = _fuggveny_def(reszek[0])
    okok: list[str] = []
    if len(reszek) > 2:
        okok.append("egyenlőség-lánc (több jobb oldal): az elsőt rajzoljuk")
    szoveg, e = _kif(reszek[1])
    szimbolumok = {s.name for s in e.free_symbols}
    if not szimbolumok:
        okok.append("konstans jobb oldal: az egyenlet megoldása is lehet, nem csak vízszintes egyenes")
    elif v not in szimbolumok:                      # `y = 5 - t`: más nevű, egyetlen változó
        if nev is not None or len(szimbolumok) != 1:
            raise _Hiba("a kifejezés a deklarált változótól eltérő változót vagy paramétert tartalmaz: "
                        + ", ".join(sorted(szimbolumok)))
        v = next(iter(szimbolumok))
        okok.append(f"a változó {v}, nem x")
    elif szimbolumok - {v}:
        raise _Hiba("a kifejezés paramétert is tartalmaz (" + ", ".join(sorted(szimbolumok - {v}))
                    + "): csúszka nincs, a modell-ágra marad")
    if v != "x":
        szoveg = _atnevez(szoveg, v, "x")
        e = e.subs(sp.Symbol(v, real=True), _X)
    return F.Fuggveny(szoveg, nev), e, okok, v


def _kor_ablak(korlatok: dict, v: str):
    k = korlatok.get(v)
    return (k[0], k[1]) if k else None


def _fuggvenyek(fo: list[str], korlatok: dict) -> tuple[F.Abra, list[str]]:
    elemek, okok, ablakok = [], [], []
    for p in fo:
        elem, e, o, v = _egy_fuggveny(p)
        okok += o
        xt, yt, figy = _ablak(e, _kor_ablak(korlatok, v))
        okok += figy
        elemek.append(elem)
        ablakok.append((xt, yt))
    xt, yt = _egyesit(ablakok)
    return F.Abra(xt, yt, tuple(elemek)), okok


def _egyesit(ablakok: list) -> tuple[tuple[str, str], tuple[str, str]]:
    """Több elem ablaka: az x-ablak az elsőé (a megadott vagy közös), az y-ablak a burkoló."""
    if len(ablakok) == 1:
        return ablakok[0]
    xs = ablakok[0][0]
    ylo = min(float(a[1][0]) for a in ablakok)
    yhi = max(float(a[1][1]) for a in ablakok)
    return xs, (_szam_szoveg(ylo), _szam_szoveg(yhi))


def _egyenlotlenseg(p: str, korlatok: dict) -> tuple[F.Abra, list[str]]:
    m = _RELACIO.search(p)
    if not m or len(_RELACIO.findall(p)) != 1:
        raise _Hiba("összetett egyenlőtlenség (több reláció)")
    bal, jobb, rel = p[:m.start()].strip(), p[m.end():].strip(), m.group(0)
    if bal == "y":
        kif = jobb
    elif jobb == "y":
        kif = bal
        rel = {"<": ">", "<=": ">=", ">": "<", ">=": "<="}[rel]
    else:
        raise _Hiba("az egyenlőtlenség nincs y-ra rendezve")
    szoveg, e = _kif(kif)
    sz = {s.name for s in e.free_symbols}
    if "y" in sz or sz - {"x"}:
        raise _Hiba("az egyenlőtlenség jobb oldala nem csak x-től függ")
    okok: list[str] = []
    xt, yt, figy = _ablak(e, _kor_ablak(korlatok, "x"))
    okok += figy
    return F.Abra(xt, yt, (F.Egyenlotlenseg(szoveg, rel),)), okok


_PARAM_BAL = re.compile(r"^(?P<k>[xy])\s*(?:\(\s*(?P<v>[a-z])\s*\))?$")


def _parameteres(fo: list[str], korlatok: dict) -> tuple[F.Abra, list[str]]:
    jobb = {}
    valtozo = None
    for p in fo:
        r = _EGYENLOSEG.split(p)
        if len(r) != 2:
            raise _Hiba("paraméteres alak: egyenlőség-lánc")
        m = _PARAM_BAL.match(r[0].strip())
        if not m:
            raise _Hiba("paraméteres alak: a bal oldal nem x vagy y")
        jobb[m["k"]] = r[1]
        valtozo = valtozo or m["v"]
    if set(jobb) != {"x", "y"}:
        raise _Hiba("paraméteres alak: x és y egyaránt kell")
    okok: list[str] = []
    if not valtozo:
        parameterek = [v for v in korlatok if v not in "xy"]
        valtozo = parameterek[0] if parameterek else None
    if valtozo and valtozo != "t" and not any(re.search(r"(?<![\\\w])t(?!\w)", j) for j in jobb.values()):
        # a `matek.elemez` csak a fehérlistás változóneveket ismeri: a paramétert előre `t`-re nevezzük
        jobb = {k: re.sub(rf"(?<![\\\w]){valtozo}(?!\w)", "t", j) for k, j in jobb.items()}
        korlatok = {("t" if k == valtozo else k): v for k, v in korlatok.items()}
        valtozo = "t"
    szovegek, kifejezesek = {}, {}
    for k in "xy":
        szovegek[k], kifejezesek[k] = _kif(jobb[k])
    sz = set().union(*(set(s.name for s in e.free_symbols) for e in kifejezesek.values()))
    if not valtozo:
        parameterek = [v for v in korlatok if v not in "xy"]
        valtozo = parameterek[0] if parameterek else (sorted(sz)[0] if len(sz) == 1 else None)
    if not valtozo:
        raise _Hiba("paraméteres alak: nem állapítható meg a paraméter")
    if sz - {valtozo}:
        raise _Hiba("paraméteres alak: a kifejezés a paraméteren kívül mást is tartalmaz: " + ", ".join(sorted(sz - {valtozo})))
    if valtozo in korlatok:
        a, b = korlatok[valtozo][0], korlatok[valtozo][1]
        if a is None or b is None:
            okok.append("a paraméter tartománya félig megadott: alap [0, 2*pi]")
            a, b = "0", "2*pi"
        ta, ja = _hatar_szoveg(a)
        tb, jb = _hatar_szoveg(b)
        if ja >= jb:
            raise _Hiba("üres vagy fordított paraméter-tartomány")
        t_tart = (ta, tb)
        t_lo, t_hi = ja, jb
    else:
        okok.append("a paraméter tartománya hiányzik: alap [0, 2*pi]")
        t_tart, t_lo, t_hi = ("0", "2*pi"), 0.0, 2 * math.pi
    if valtozo != "t":
        for k in "xy":
            szovegek[k] = _atnevez(szovegek[k], valtozo, "t")
    s = sp.Symbol(valtozo, real=True)
    fx, fy = (sp.lambdify(s, kifejezesek[k], modules=["math"]) for k in "xy")
    pontok = []
    for i in range(MINTA):
        t = t_lo + (t_hi - t_lo) * i / (MINTA - 1)
        try:
            px, py = float(fx(t)), float(fy(t))
        except (ArithmeticError, ValueError, TypeError, OverflowError):
            continue
        if math.isfinite(px) and math.isfinite(py) and abs(px) < 1e8 and abs(py) < 1e8:
            pontok.append((px, py))
    if len(pontok) < 0.2 * MINTA:
        raise _Hiba("a paraméteres görbe a tartományon alig értelmezett")
    if len(pontok) < MINTA:
        okok.append("a paraméteres görbe nem mindenhol értelmezett")
    xl, xh = _szep_hatarok(*_y_hatar([p[0] for p in pontok]))
    yl, yh = _szep_hatarok(*_y_hatar([p[1] for p in pontok]))
    elem = F.Parameteres(szovegek["x"], szovegek["y"], "t", t_tart)
    return F.Abra((_szam_szoveg(xl), _szam_szoveg(xh)), (_szam_szoveg(yl), _szam_szoveg(yh)), (elem,)), okok


# ---- TikZ / pgfplots ----------------------------------------------------------------------------------------

_PGF_KULCS = J.PGF_KULCS
_ADDPLOT = re.compile(r"\\addplot3?\*?\+?\s*(?:\[(?P<opt>[^\]]*)\])?\s*(?=[{(]|table\b|coordinates\b)")
_DRAWPLOT = re.compile(r"\\draw\s*(?:\[(?P<opt>[^\]]*)\])?\s*plot\s*(?:\[[^\]]*\]\s*)?(?=\()")
_AXIS = re.compile(r"\\begin\{axis\}\s*\[(?P<opt>.*?)\]", re.S)
_LEGEND = re.compile(r"\\addlegendentry\s*\{(.*?)\}", re.S)


def _opciok(s: str | None) -> dict[str, str]:
    ki = {}
    for resz in _felbont(s or ""):
        if "=" in resz:
            k, v = resz.split("=", 1)
            ki[k.strip()] = v.strip().strip("{}").strip()
    return ki


def _csoport(szoveg: str, i: int) -> str | None:
    """Az `i`-n nyíló `(`/`{` csoport tartalma a párjáig (zárójel nélkül); `None`, ha nem csoport vagy lezáratlan."""
    if i >= len(szoveg) or szoveg[i] not in "({":
        return None
    melyseg = 0
    for j in range(i, len(szoveg)):
        melyseg += (szoveg[j] in "({") - (szoveg[j] in ")}")
        if melyseg == 0:
            return szoveg[i + 1:j]
    return None


def _pgf_kif(s: str, valtozo: str) -> tuple[str, sp.Expr, list[str]]:
    """pgf-matematika → sima szöveg (a változó `x`-re átnevezve), SymPy; a fokban számolt trigonometria bizonytalan."""
    okok: list[str] = []
    t = s.strip().replace("**", "^").replace("\\" + valtozo, valtozo)
    t = re.sub(r"\\x\b", "x", t)
    van_deg = re.search(r"\bdeg\s*\(", t)
    trig = re.search(r"\b(?:sin|cos|tan)\s*\(", t)
    if trig and not van_deg:
        okok.append("a pgfplots a sin/cos/tan argumentumát fokban értelmezi (`deg()` nélkül): a rajz szándéka bizonytalan")
    t = re.sub(r"\bdeg\s*\(((?:[^()]|\([^()]*\))*)\)", r"(\1)", t)
    t = re.sub(r"\brad\s*\(", "(", t)
    while True:
        uj = re.sub(r"\(\(([^()]*)\)\)", r"(\1)", t)
        if uj == t:
            break
        t = uj
    szoveg, e = _kif(t)
    if valtozo != "x":
        szoveg = _atnevez(szoveg, valtozo, "x")
        e = e.subs(sp.Symbol(valtozo, real=True), _X)
    return szoveg, e, okok


def _pgf_hatarok(opciok: dict) -> tuple[tuple[str, float], tuple[str, float]] | None:
    d = opciok.get("domain")
    if not d or ":" not in d:
        return None
    a, b = d.split(":", 1)
    return _hatar_szoveg(a.strip().strip("{}")), _hatar_szoveg(b.strip().strip("{}"))


def _pgf(szoveg: str) -> tuple[F.Abra, list[str]]:
    ax = _AXIS.search(szoveg)
    tengely = _opciok(ax["opt"]) if ax else {}
    plotok = []
    for minta, mod in ((_ADDPLOT, "addplot"), (_DRAWPLOT, "draw")):
        for m in minta.finditer(szoveg):
            i = m.end()
            if szoveg.startswith(("table", "coordinates"), i):
                raise _Hiba("adatpontokból álló görbe (table/coordinates): nem képlet")
            belso = _csoport(szoveg, i)
            if belso is None:
                raise _Hiba("nem értelmezhető \\addplot / plot argumentum")
            plotok.append((m.start(), m["opt"], belso, szoveg[i] if szoveg[i] == "(" else "{"))
    plotok.sort(key=lambda t: t[0])
    if not plotok:
        raise _Hiba("nincs értelmezhető \\addplot / plot parancs")
    cimkek = _LEGEND.findall(szoveg)
    elemek, okok, xek, yek = [], [], [], []
    for n, (_, opt, belso, nyito) in enumerate(plotok):
        o = _opciok(opt)
        valtozo = o.get("variable", tengely.get("variable", "x")).lstrip("\\")
        hatarok = _pgf_hatarok(o) or _pgf_hatarok(tengely)
        if hatarok is None:
            okok.append("nincs domain: a pgfplots alapja [-5, 5]")
            hatarok = (("-5", -5.0), ("5", 5.0))
        cimke = cimkek[n] if len(cimkek) == len(plotok) else None
        if cimke is not None:
            cimke = cimke.replace('"', "'").replace("\n", " ").strip()
        lo, hi = hatarok[0][1], hatarok[1][1]
        koord = [r.strip().strip("{}").strip() for r in _felbont(belso)] if nyito == "(" else None
        if koord is not None and len(koord) != 2:
            raise _Hiba("paraméteres \\addplot: nem két koordináta")
        if koord is not None and koord[0].lstrip("\\") != valtozo:       # valódi paraméteres görbe
            sx, ex, o1 = _pgf_kif(koord[0], valtozo)
            sy, ey, o2 = _pgf_kif(koord[1], valtozo)
            okok += o1 + o2
            sx, sy = _atnevez(sx, "x", "t"), _atnevez(sy, "x", "t")
            t = sp.Symbol("t", real=True)
            fx, fy = (sp.lambdify(t, k.subs(_X, t), modules=["math"]) for k in (ex, ey))
            elem = F.Parameteres(sx, sy, "t", (hatarok[0][0], hatarok[1][0]), cimke)
            xs, ys = [], []
            for i in range(MINTA):
                tt = lo + (hi - lo) * i / (MINTA - 1)
                try:
                    px, py = float(fx(tt)), float(fy(tt))
                except (ArithmeticError, ValueError, TypeError, OverflowError):
                    continue
                if math.isfinite(px) and math.isfinite(py):
                    xs.append(px)
                    ys.append(py)
            if not xs:
                raise _Hiba("a paraméteres görbe a tartományon nem értelmezett")
            xek += [min(xs), max(xs)]
            yek += [min(ys), max(ys)]
        else:                                                              # y = f(x): `{f}` vagy `(\x, {f})`
            forras = koord[1] if koord is not None else belso
            szoveg_f, e, o1 = _pgf_kif(forras, valtozo)
            okok += o1
            elem = F.Fuggveny(szoveg_f, cimke)
            m = _mintak(sp.lambdify(_X, e, modules=["math"]), lo, hi)
            ys = [v for _, v in m if v is not None]
            if not ys:
                raise _Hiba("a függvény a megadott tartományon nem értelmezett")
            if any(v is None for _, v in m[1:-1]):
                okok.append("a függvény a tartományon nem mindenhol értelmezett (szakadás)")
            xek += [lo, hi]
            yek += [min(ys), max(ys)]
        elemek.append(elem)
    x_t = (_szam_szoveg(min(xek)), _szam_szoveg(max(xek)))
    if all(isinstance(e, F.Fuggveny) for e in elemek):
        h = _pgf_hatarok(_opciok(plotok[0][1])) or _pgf_hatarok(tengely)
        x_t = (h[0][0], h[1][0]) if h else ("-5", "5")
    if tengely.get("xmin") is not None and tengely.get("xmax") is not None:
        x_t = (_hatar_szoveg(tengely["xmin"])[0], _hatar_szoveg(tengely["xmax"])[0])
    if tengely.get("ymin") is not None and tengely.get("ymax") is not None:
        y_t = (_hatar_szoveg(tengely["ymin"])[0], _hatar_szoveg(tengely["ymax"])[0])
    else:
        y_t = tuple(_szam_szoveg(v) for v in _szep_hatarok(*_y_hatar(yek)))
    return F.Abra(x_t, y_t, tuple(elemek)), okok


# ---- belépési pont ------------------------------------------------------------------------------------------

def _eredmeny(fajta: str, abra: F.Abra | None, okok: list[str], keplet: str, alap_ok: str) -> Javaslat:
    if abra is None:
        return Javaslat(fajta, BIZONYTALAN, alap_ok, keplet, kulcs(keplet))
    bizonyossag = BIZONYTALAN if okok else BIZTOS
    ok = "; ".join(okok) if okok else alap_ok
    return Javaslat(fajta, bizonyossag, ok, keplet, kulcs(keplet), abra, F.blokk(abra))


def felismer(keplet: str) -> Javaslat:
    """Egy képlet (vagy TikZ/pgfplots szövegrész) → javaslat. Mindig ad választ: `bizonyossag == "nincs"`, ha a
    képlet nem grafikon-alapanyag; `bizonytalan`, ha a döntés a modell-ágra (C35b) marad."""
    nyers = keplet or ""
    try:
        if _PGF_KULCS.search(nyers):
            abra, okok = _pgf(nyers)
            return _eredmeny("tikz", abra, okok, keplet, "TikZ/pgfplots függvény-ábra átalakítva")
        t = _tisztit(nyers)
        if re.search(r"\\begin\{(?:cases|array|aligned|align\*?)\}", t):
            return Javaslat("szakaszonkent", BIZONYTALAN,
                            "szakaszonként vagy többsoros definíció: a modell-ágra marad", keplet, kulcs(keplet))
        korlatok: dict[str, tuple[str | None, str | None]] = {}
        fo: list[str] = []
        ismeretlen: list[str] = []
        for resz in _felbont(t):
            k = _korlat(resz)
            if k is None:
                (fo if (_EGYENLOSEG.search(resz) or _RELACIO.search(resz)) else ismeretlen).append(resz)
            elif k:
                korlatok[k[0]] = (k[1], k[2])
        if not fo:
            return Javaslat("nem_abra", NINCS, "nincs egyenlet vagy egyenlőtlenség: nem függvény-definíció", keplet,
                            kulcs(keplet))
        if re.search(r"\by\b", " ".join(fo)) is None and not any(_PARAM_BAL.match(_EGYENLOSEG.split(p)[0].strip())
                                                                   for p in fo if _EGYENLOSEG.search(p)):
            egyenlet = [p for p in fo if _EGYENLOSEG.search(p)]
            if not any(_NEV_FGV.match(_EGYENLOSEG.split(p)[0].strip()) for p in egyenlet):
                return Javaslat("nem_abra", NINCS, "szám-egyenlet vagy azonosság (nincs y= vagy f(x)= alak)", keplet,
                                kulcs(keplet))
        egyenletek = [p for p in fo if _EGYENLOSEG.search(p)]
        okok_extra: list[str] = []
        if ismeretlen:
            okok_extra.append("nem értelmezett kiegészítés: " + "; ".join(ismeretlen))
        if len(fo) == 2 and len(egyenletek) == 2 and all(_PARAM_BAL.match(_EGYENLOSEG.split(p)[0].strip()) for p in fo):
            abra, okok = _parameteres(fo, korlatok)
            return _eredmeny("parameteres", abra, okok + okok_extra, keplet, "paraméteres görbe")
        if len(egyenletek) == len(fo):
            for p in fo:
                bal = _EGYENLOSEG.split(p)[0].strip()
                if bal != "y" and not _NEV_FGV.match(bal):
                    if re.search(r"\by\b", p):
                        return Javaslat("implicit", BIZONYTALAN, "implicit görbe (y nem a bal oldalon áll): a modell-ágra marad",
                                        keplet, kulcs(keplet))
                    return Javaslat("nem_abra", NINCS, f"nem függvény-definíció (bal oldal: {bal!r})", keplet,
                                    kulcs(keplet))
            abra, okok = _fuggvenyek(fo, korlatok)
            return _eredmeny("fuggveny", abra, okok + okok_extra, keplet, "függvény-definíció")
        if len(fo) == 1:
            abra, okok = _egyenlotlenseg(fo[0], korlatok)
            return _eredmeny("egyenlotlenseg", abra, okok + okok_extra, keplet, "egyenlőtlenség-tartomány")
        return Javaslat("nem_abra", BIZONYTALAN, "több, nem összetartozó reláció egy képletben", keplet, kulcs(keplet))
    except _Hiba as h:
        if "implicit" in str(h):
            return Javaslat("implicit", BIZONYTALAN, str(h) + ": a modell-ágra marad", keplet, kulcs(keplet))
        if str(h).startswith("a bal oldal nem függvény-definíció"):
            return Javaslat("nem_abra", NINCS, str(h), keplet, kulcs(keplet))
        return Javaslat("nem_abra", BIZONYTALAN, str(h), keplet, kulcs(keplet))
    except (RecursionError, ValueError, TypeError, ArithmeticError, sp.SympifyError, AttributeError) as h:
        return Javaslat("nem_abra", BIZONYTALAN, f"váratlan elemzési hiba ({type(h).__name__}): a modell-ágra marad",
                        keplet, kulcs(keplet))


def felismer_jegyzet(szoveg: str, mindet: bool = False) -> list[Javaslat]:
    """A jegyzet minden képletére (és TikZ/pgfplots blokkjára) a javaslat, a jegyzetbeli sorokkal és a
    „már van blokk alatta” jelzéssel. Alapból a `nincs` (nem grafikon-alapanyag) tételek kimaradnak.
    A kivágás és a hely a `jegyzet` modulban él (sympy nélkül), hogy a szülő-oldal is ugyanazt használja."""
    szoveg = szoveg or ""
    blokkok = F.blokkok(szoveg)
    ki: list[Javaslat] = []
    for i, k in J.jeloltek(szoveg):
        j = felismer(k)
        if j.bizonyossag == NINCS and not mindet:
            continue
        h = J.hely(szoveg, i, k, blokkok)
        ki.append(Javaslat(j.fajta, j.bizonyossag, j.ok, j.forras_keplet, j.kulcs, j.abra, j.blokk,
                           h["sor"], h["veg_sor"], h["blokk_kovetkezik"]))
    return ki
