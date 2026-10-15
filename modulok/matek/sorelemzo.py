"""Egy levezetés-sor elemzése (C24a): LaTeX → relációk, megoldáslista, kikötés, vagy „nem elemezhető”.

A kifejezések a `kozos.matek.elemez` fehérlistás elemzőjén mennek át (kódot nem futtat); ez a modul csak az
elé tesz előfeldolgozást (egymásba ágyazott abszolút érték, `\\log_b` kiegyensúlyozott argumentummal, `\\big`),
és a sor szerkezetét bontja (relációjelek, vesszős lista, szöveges kötőszavak).

Szöveg a sorban (`\\text{…}` vagy ismert magyar kötőszó):
- `vagy`: unió;
- `miatt`, `ezért`, `így`, `tehát`, `vagyis`, `azaz`: az utolsó ilyen szó UTÁNI rész a sor állítása, az előtte
  álló egyenlőtlenség **kikötés**, minden más előtte csak indoklás;
- `nem megoldás`, `nem lehet`, `hamis gyök`, …: az előtte álló matematikai rész kimarad (elvetett jelölt);
- a szöveget tartalmazó zárójeles megjegyzés kimarad.
Ami ezen kívül esik, az `nem_elemezheto`: a modul nem találgat.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

_EVAL = Path(__file__).resolve().parent.parent / "eval"
if str(_EVAL) not in sys.path:
    sys.path.insert(0, str(_EVAL))
import sympy as sp  # noqa: E402

from kozos import matek as M  # noqa: E402

MatekHiba = M.MatekHiba

KOVETKEZTETES = ("miatt", "ezért", "ezert", "így", "igy", "tehát", "tehat", "vagyis", "azaz")
TAGADAS = ("nem megoldás", "nem megoldas", "nem lehet", "hamis gyök", "hamis gyok", "nem felel meg",
           "nem jó", "nem jo", "nem valós", "nem valos", "elvetjük", "elvetjuk", "nem megfelel")
_SZAVAK = ("vagy", "és", "miatt", "ezért", "így", "tehát", "vagyis", "azaz", "nem", "mert", "hamis", "gyök",
           "megoldás", "lehet", "kikötés", "ellenőrzés", "illetve")
_RELACIO = re.compile(r"<=|>=|!=|=|<|>")
_VALTOZO_BAL = re.compile(r"^\s*([a-zA-Z])\s*(?:_\s*(?:\{[^{}]*\}|[0-9a-zA-Z]))?\s*$")
_SZOVEG_JEL = "\x00"


@dataclass
class Relacio:
    bal: sp.Expr
    op: str                                 # "=", "<", "<=", ">", ">=", "!="
    jobb: sp.Expr


@dataclass
class Sor:
    fajta: str                              # egyenlet | egyenlotlenseg | megoldas | vagy | kifejezes | folytatas |
                                            # lanc | nem_elemezheto | ures
    agak: list = field(default_factory=list)      # egyenlet/egyenlőtlenség/vagy: [[Relacio, …], …] (ágon belül ÉS)
    ertekek: list = field(default_factory=list)   # megoldas: [sp.Expr, …]
    kifejezesek: list = field(default_factory=list)   # kifejezes/folytatas/lanc
    kikotesek: list = field(default_factory=list)     # [Relacio] — a sorban kimondott kikötés
    valtozo: str | None = None              # megoldáslista: a bal oldal betűje (x_1 → x)
    ok: str = ""                            # nem_elemezheto: miért

    def szabad(self) -> set:
        s: set = set()
        for ag in self.agak:
            for r in ag:
                s |= r.bal.free_symbols | r.jobb.free_symbols
        for e in self.kifejezesek:
            s |= e.free_symbols
        return s


# ------------------------------------------------------------------ előfeldolgozás (a kozos.latexbol elé)

def _zaro(s: str, i: int, nyit: str, zar: str) -> int:
    """Az `i`-n álló nyitójel párjának helye; -1, ha nincs."""
    m = 0
    for j in range(i, len(s)):
        m += (s[j] == nyit) - (s[j] == zar)
        if m == 0:
            return j
    return -1


def _abs(s: str) -> str:
    """`|…|` → `Abs(…)`, egymásba ágyazva is: a `|` nyitó, ha előtte művelet/nyitó áll vagy nincs nyitott."""
    ki: list[str] = []
    verem = 0
    for c in s:
        if c != "|":
            ki.append(c)
            continue
        elozo = "".join(ki).rstrip()[-1:]
        if verem == 0 or elozo == "" or elozo in "+-*/=(,^{[<>":
            ki.append("Abs(")
            verem += 1
        else:
            ki.append(")")
            verem -= 1
    if verem:
        raise MatekHiba("páratlan abszolútérték-jel")
    return "".join(ki)


def _log_alap(s: str) -> str:
    """`\\log_b ARG` → `log((ARG),(b))`; az ARG kiegyensúlyozott zárójel, `\\frac{…}{…}`, `{…}` vagy egy jel."""
    for _ in range(50):
        i = s.find("\\log_")
        if i < 0:
            return s
        j = i + 5
        if j < len(s) and s[j] == "{":
            z = _zaro(s, j, "{", "}")
            if z < 0:
                raise MatekHiba("páratlan kapcsos zárójel")
            alap, j = s[j + 1:z], z + 1
        else:
            m = re.match(r"\d+(?:\.\d+)?|[a-zA-Z]", s[j:])
            if not m:
                raise MatekHiba("hiányzó logaritmus-alap")
            alap, j = m.group(0), j + len(m.group(0))
        while j < len(s) and s[j] == " ":
            j += 1
        if s.startswith("\\frac", j) or s.startswith("\\dfrac", j) or s.startswith("\\tfrac", j):
            k = s.index("frac", j) + 4
            vegek = []
            for _ in range(2):
                while k < len(s) and s[k] == " ":
                    k += 1
                if k < len(s) and s[k] == "{":
                    z = _zaro(s, k, "{", "}")
                    if z < 0:
                        raise MatekHiba("páratlan kapcsos zárójel")
                    k = z + 1
                else:
                    k += 1
                vegek.append(k)
            arg, j = s[j:vegek[-1]], vegek[-1]
        elif j < len(s) and s[j] in "({":
            z = _zaro(s, j, s[j], ")" if s[j] == "(" else "}")
            if z < 0:
                raise MatekHiba("páratlan zárójel")
            arg, j = s[j + 1:z], z + 1
        else:
            m = re.match(r"\d+(?:\.\d+)?|[a-zA-Z]", s[j:])
            if not m:
                raise MatekHiba("hiányzó logaritmus-argumentum")
            arg, j = m.group(0), j + len(m.group(0))
        s = s[:i] + f"log(({arg}),({alap}))" + s[j:]
    raise MatekHiba("túl sok logaritmus")


def elokeszit(s: str) -> str:
    """A LaTeX-darab előkészítése a `kozos.matek.elemez`-hez."""
    s = s.replace("{,}", ".")
    s = re.sub(r"\\(?:,|;|!|:|\s)", " ", s)
    s = re.sub(r"\\[dtc]frac(?![a-zA-Z])", r"\\frac", s)
    s = re.sub(r"\\frac\s*([0-9a-zA-Z])\s*([0-9a-zA-Z])", r"\\frac{\1}{\2}", s)       # \frac12 → 1/2
    s = re.sub(r"\\(?:big|Big|bigg|Bigg)[lr]?\b", "", s)
    s = re.sub(r"\\(?:left|right)\s*(?=[|()\[\]])", "", s)
    s = re.sub(r"\\(?:lvert|rvert|vert)\b", "|", s)
    s = re.sub(r"\\(?:mid)\b", "|", s)
    s = _log_alap(s)
    return _abs(s)


def kifejezes(s: str) -> sp.Expr:
    """Egy LaTeX-kifejezés (reláció nélkül) → sympy, a fehérlistán át."""
    return M.elemez(elokeszit(s))


# ------------------------------------------------------------------ szöveg és szerkezet

def _szovegek(s: str) -> tuple[str, list[str]]:
    """A `\\text{…}`-szerű részek és az ismert csupasz szavak helyén jelölő; → (jelölt sor, szövegek)."""
    szovegek: list[str] = []

    def jel(t: str) -> str:
        szovegek.append(t)
        return f" {_SZOVEG_JEL}{len(szovegek) - 1}{_SZOVEG_JEL} "

    for _ in range(100):
        m = re.search(r"\\(?:text|textrm|textit|mbox|mathrm)\s*\{", s)
        if not m:
            break
        z = _zaro(s, m.end() - 1, "{", "}")
        if z < 0:
            raise MatekHiba("páratlan kapcsos zárójel a szövegben")
        belso = s[m.end():z]
        if re.fullmatch(r"\s*[a-zA-Z]{1,3}\s*", belso) and not any(belso.strip() == w for w in ("és", "ha")):
            s = s[:m.start()] + belso + s[z + 1:]                 # \mathrm{d} és társai: matematika
        else:
            s = s[:m.start()] + jel(belso) + s[z + 1:]
    minta = re.compile(r"(?<![\\a-zA-Z])(" + "|".join(sorted(_SZAVAK, key=len, reverse=True)) + r")(?![a-zA-Z])"
                       r"|(?<![\\a-zA-Z])[a-zA-ZáéíóöőúüűÁÉÍÓÖŐÚÜŰ]*[áéíóöőúüűÁÉÍÓÖŐÚÜŰ][a-zA-ZáéíóöőúüűÁÉÍÓÖŐÚÜŰ]*")
    s = minta.sub(lambda m: jel(m.group(0)), s)
    return s, szovegek


def _zarojeles_megjegyzes_ki(s: str) -> str:
    """A szöveget tartalmazó zárójeles csoport (megjegyzés) kimarad."""
    for _ in range(50):
        talalt = False
        for i, c in enumerate(s):
            if c == "(":
                z = _zaro(s, i, "(", ")")
                if z > 0 and _SZOVEG_JEL in s[i:z]:
                    s = s[:i] + " " + s[z + 1:]
                    talalt = True
                    break
        if not talalt:
            return s
    return s


def _darabol(s: str) -> list[tuple[str, str]]:
    """A jelölt sor → [("m", matek) | ("t", szöveg-index), …]."""
    ki = []
    for i, d in enumerate(s.split(_SZOVEG_JEL)):
        if i % 2:
            ki.append(("t", d))
        elif d.strip(" ,;.:\\"):
            ki.append(("m", d))
    return ki


def _relaciok_normal(s: str) -> str:
    for minta, csere in ((r"\\(?:leq|leqslant|le)\b|≤", "<="), (r"\\(?:geq|geqslant|ge)\b|≥", ">="),
                         (r"\\(?:neq|ne)\b|≠", "!="), (r"\\lt\b", "<"), (r"\\gt\b", ">"), (r"\\approx\b|≈", "~~")):
        s = re.sub(minta, csere, s)
    return s


def _felso_szint_split(s: str, minta: re.Pattern) -> list[str]:
    """Darabolás a `minta` találatainál, de csak zárójelen kívül; a relációjelek is megmaradnak a listában."""
    ki, mely, kezd, i = [], 0, 0, 0
    while i < len(s):
        c = s[i]
        if c in "([{":
            mely += 1
        elif c in ")]}":
            mely -= 1
        elif mely == 0:
            m = minta.match(s, i)
            if m:
                ki += [s[kezd:i], m.group(0)]
                i = kezd = m.end()
                continue
        i += 1
    return ki + [s[kezd:]]


_LISTA_ELEM = re.compile(r",\s*(?:\\ |\\,|\\;|\\quad|\s)*(?=[a-zA-Z]\s*(?:_\s*(?:\{[^{}]*\}|[0-9a-zA-Z]))?\s*=)")


def _lista_darabok(s: str) -> list[str]:
    """`x_1=0,\\ x_2=3` → két elem; a tizedesvessző és a zárójelen belüli vessző nem bont."""
    darabok, mely, kezd = [], 0, 0
    for i, c in enumerate(s):
        if c in "([{":
            mely += 1
        elif c in ")]}":
            mely -= 1
        elif c in ",;" and mely == 0 and (c == ";" or _LISTA_ELEM.match(s, i)):
            darabok.append(s[kezd:i])
            kezd = i + 1
    return [d.strip().lstrip("\\ ,;").strip() for d in darabok + [s[kezd:]] if d.strip(" \\,;")]


def _pm(s: str) -> list[str]:
    if "\\pm" in s or "±" in s:
        return [re.sub(r"\\pm|±", "+", s, count=1), re.sub(r"\\pm|±", "-", s, count=1)]
    if "\\mp" in s or "∓" in s:
        return [re.sub(r"\\mp|∓", "-", s, count=1), re.sub(r"\\mp|∓", "+", s, count=1)]
    return [s]


def _resz(d: str) -> dict:
    """Egy matematikai darab (szöveg nélkül) → {relaciok | ertekek | kifejezesek | folytatas}."""
    d = _relaciok_normal(d).strip().strip(" ,;.:").strip()
    while d.startswith("(") and _zaro(d, 0, "(", ")") == len(d) - 1:
        d = d[1:-1].strip()                                       # (x>0) → x>0
    if "~~" in d:
        raise MatekHiba("közelítő egyenlőség (≈): nem ellenőrizhető")
    elemek = _lista_darabok(d)
    if len(elemek) > 1 or (len(elemek) == 1 and _VALTOZO_BAL.match(_felso_szint_split(elemek[0], _RELACIO)[0])):
        ertekek, valtozo = [], None
        for e in elemek:
            t = _felso_szint_split(e, _RELACIO)
            if len(t) != 3 or t[1] != "=":
                break
            m = _VALTOZO_BAL.match(t[0])
            if not m:
                break
            ertek = [kifejezes(v) for v in _pm(t[2])]
            if any(v.free_symbols for v in ertek):
                break
            if valtozo not in (None, m.group(1)):
                raise MatekHiba("több ismeretlen a megoldáslistában")
            valtozo = m.group(1)
            ertekek += ertek
        else:
            return {"ertekek": ertekek, "valtozo": valtozo}
        if len(elemek) > 1:
            raise MatekHiba("a vesszős lista nem megoldáslista")
    t = _felso_szint_split(d, _RELACIO)
    if len(t) == 1:
        return {"kifejezesek": [kifejezes(t[0])]}
    if not t[0].strip():
        if t[1] != "=":
            raise MatekHiba("a sor relációjellel kezdődik")
        return {"folytatas": [kifejezes(x) for x in t[2::2]]}
    oldalak, jelek = [kifejezes(x) for x in t[0::2]], t[1::2]
    if all(j == "=" for j in jelek) and len(jelek) > 1:
        return {"lanc": oldalak}
    if "=" in jelek and len(jelek) > 1:
        raise MatekHiba("egyenlőség és egyenlőtlenség egy láncban")
    if "!=" in jelek and len(jelek) > 1:
        raise MatekHiba("≠ láncban")
    return {"relaciok": [Relacio(oldalak[k], jelek[k], oldalak[k + 1]) for k in range(len(jelek))]}


def _kovetkeztetes_szo(t: str) -> bool:
    h = t.lower()
    return any(re.search(rf"(?<![a-záéíóöőúüű]){re.escape(k)}(?![a-záéíóöőúüű])", h) for k in KOVETKEZTETES)


def _tagado(t: str) -> bool:
    h = t.lower()
    return any(k in h for k in TAGADAS)


def elemez_sor(latex: str) -> Sor:
    """Egy levezetés-sor → `Sor`. Hibánál `Sor("nem_elemezheto", ok=…)`, kivétel nem jön ki."""
    try:
        return _elemez_sor(latex)
    except (MatekHiba, ValueError, TypeError, RecursionError) as exc:
        return Sor("nem_elemezheto", ok=str(exc)[:200])


def _elemez_sor(latex: str) -> Sor:
    s = (latex or "").strip().strip("$").strip()
    if not s:
        return Sor("ures")
    s = re.sub(r"\\(?:quad|qquad)\b", " ", s)
    s, szovegek = _szovegek(s)
    s = _zarojeles_megjegyzes_ki(s)
    darabok = _darabol(s)
    tagolt = [(f, d if f == "m" else szovegek[int(d)]) for f, d in darabok]

    # a tagadott jelölt (az előtte álló matek-darab) kimarad
    tisztitott: list[tuple[str, str]] = []
    for f, d in tagolt:
        if f == "t" and _tagado(d):
            while tisztitott and tisztitott[-1][0] == "t" and not _kovetkeztetes_szo(tisztitott[-1][1]):
                tisztitott.pop()
            if tisztitott and tisztitott[-1][0] == "m":
                tisztitott.pop()
        tisztitott.append((f, d))

    kovetkeztetes = [i for i, (f, d) in enumerate(tisztitott) if f == "t" and _kovetkeztetes_szo(d)]
    kikotesek: list[Relacio] = []
    if kovetkeztetes:
        utolso = kovetkeztetes[-1]
        for f, d in tisztitott[:utolso]:
            if f != "m":
                continue
            try:
                r = _resz(d)
            except MatekHiba:
                continue                                         # az indoklás számolása (pl. √49=7≠…) nem állítás
            for rel in r.get("relaciok", []):
                if rel.op in ("<", "<=", ">", ">=") and len(rel.bal.free_symbols | rel.jobb.free_symbols) == 1:
                    kikotesek.append(rel)
        allitas = tisztitott[utolso + 1:]
    else:
        allitas = tisztitott

    agak_szoveg: list[list[str]] = [[]]
    for f, d in allitas:
        if f == "m":
            agak_szoveg[-1].append(d)
        elif re.fullmatch(r"\s*vagy\s*,?\s*", d.lower()):
            agak_szoveg.append([])
        elif re.fullmatch(r"\s*és\s*", d.lower()):
            continue                                             # egyenlőtlenségek metszete (ugyanabban az ágban)
        elif _tagado(d) or not d.strip(" ,.;:"):
            continue
        else:
            raise MatekHiba(f"értelmezhetetlen szöveg: {d.strip()[:60]!r}")
    agak_szoveg = [a for a in agak_szoveg if a]
    if not agak_szoveg:
        raise MatekHiba("a sorban nincs matematikai állítás")

    reszek = [[_resz(d) for d in ag] for ag in agak_szoveg]
    lapos = [r for ag in reszek for r in ag]
    if len(lapos) == 1 and "kifejezesek" in lapos[0]:
        return Sor("kifejezes", kifejezesek=lapos[0]["kifejezesek"], kikotesek=kikotesek)
    if len(lapos) == 1 and "folytatas" in lapos[0]:
        return Sor("folytatas", kifejezesek=lapos[0]["folytatas"], kikotesek=kikotesek)
    if len(lapos) == 1 and "lanc" in lapos[0]:
        return Sor("lanc", kifejezesek=lapos[0]["lanc"], kikotesek=kikotesek)
    if all("ertekek" in r for r in lapos):
        valtozok = {r["valtozo"] for r in lapos}
        if len(valtozok) > 1:
            raise MatekHiba("több ismeretlen a megoldáslistában")
        return Sor("megoldas", ertekek=[v for r in lapos for v in r["ertekek"]], kikotesek=kikotesek,
                   valtozo=valtozok.pop())
    agak = []
    for ag in reszek:
        relek: list[Relacio] = []
        for r in ag:
            if "relaciok" in r:
                relek += r["relaciok"]
            elif "ertekek" in r:
                v = sp.Symbol(r["valtozo"], real=True)
                if len(r["ertekek"]) != 1:
                    raise MatekHiba("megoldáslista egy vagy-ágon belül")
                relek.append(Relacio(v, "=", r["ertekek"][0]))
            else:
                raise MatekHiba("kifejezés reláció nélkül egy vagy-ágban")
        agak.append(relek)
    if len(agak) == 1:
        fajta = "egyenlet" if all(r.op == "=" for r in agak[0]) else (
            "egyenlotlenseg" if all(r.op != "=" for r in agak[0]) else "")
        if not fajta:
            raise MatekHiba("egyenlőség és egyenlőtlenség egy ágon")
        return Sor(fajta, agak=agak, kikotesek=kikotesek)
    return Sor("vagy", agak=agak, kikotesek=kikotesek)
