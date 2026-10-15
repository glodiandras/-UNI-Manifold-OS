"""A ```` ```plot ```` blokk formátuma: elemzés és kanonikus szerializálás (C35a; `docs/PLOT-FORMATUM.md`).

A blokk soronkénti, ember által is írható szöveg; Obsidianban sima kódblokk, a visszaút (1. döntés) megmarad.
A formátum csak **adat**: kifejezést nem értékel (az a renderelő dolga, C35b), a kifejezés szövege az
`modulok/eval/kozos/matek.elemez` jelölése (`*`, `^`, `sqrt()`, `abs()`, `log(x, 2)`).

Körút: `szerializal(elemez(s))` kanonikus, ismételve fixpont; `elemez(szerializal(a)) == a`. Az ismeretlen sor
és a megjegyzés megmarad (kézi szerkesztés), hibát nem okoz; a `hibak` csak jelzi.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

MAX_ELEM = 64            # ennél több rajzelemet a renderelő nem kap (a többi `Ismeretlen`)
MAX_SOR = 2000           # ennél hosszabb sor `Ismeretlen`
MAX_BLOKK = 100_000      # ennél nagyobb blokkot nem elemzünk

_KIF = r"[0-9A-Za-z+\-*/^().,!_ ]+?"             # a kifejezés megengedett jelei (a matek.elemez fehérlistájának része)
_BIZ = re.compile(r"^[0-9A-Za-z+\-*/^().,!_ ]+$")
_SZAM = r"[^\[\]()\"]+?"
_TART = re.compile(rf"^([xy])\s+in\s*\[\s*({_KIF})\s*,\s*({_KIF})\s*\]$")
_PTART = re.compile(rf"^([a-wz])\s+in\s*\[\s*({_KIF})\s*,\s*({_KIF})\s*\]$")
_EGYENL = re.compile(rf"^y\s*(<=|>=|<|>)\s*({_KIF})$")
_FGV = re.compile(rf"^y\s*=\s*({_KIF})$")
_PONT = re.compile(rf"^pont\s*\(\s*({_KIF})\s*,\s*({_KIF})\s*\)$")
_CIMKE = re.compile(r'\s+"((?:[^"\\]|\\.)*)"\s*$')
_PARAM = re.compile(rf"^x\s*=\s*({_KIF})$")
_PARAM_Y = re.compile(rf"^y\s*=\s*({_KIF})$")
_UNICODE = {"−": "-", "–": "-", "≤": "<=", "≥": ">="}


@dataclass(frozen=True)
class Fuggveny:
    kifejezes: str                    # y = kifejezes (x-ben)
    cimke: str | None = None


@dataclass(frozen=True)
class Parameteres:
    x: str                            # x = x(t)
    y: str                            # y = y(t)
    t: str = "t"
    tartomany: tuple[str, str] = ("0", "2*pi")
    cimke: str | None = None


@dataclass(frozen=True)
class Egyenlotlenseg:
    kifejezes: str                    # y RELÁCIÓ kifejezes
    relacio: str                      # < <= > >=
    cimke: str | None = None


@dataclass(frozen=True)
class Pont:
    x: str
    y: str
    cimke: str | None = None


@dataclass(frozen=True)
class Megjegyzes:
    szoveg: str                       # a `#` utáni rész


@dataclass(frozen=True)
class Ismeretlen:
    sor: str                          # értelmezhetetlen sor, szó szerint megőrizve


@dataclass(frozen=True)
class Abra:
    x_tartomany: tuple[str, str] | None = None
    y_tartomany: tuple[str, str] | None = None
    elemek: tuple = ()
    hibak: tuple = field(default=(), compare=False)   # (sorszám, üzenet); nem része az egyenlőségnek


@dataclass(frozen=True)
class BlokkHely:
    """Egy ```` ```plot ```` blokk a jegyzet szövegében (a kódmaszk után)."""
    kezdo: int            # a nyitó sor első karaktere (a szövegben)
    veg: int              # a záró sor vége (sortöréssel együtt), lezáratlan blokknál a szöveg vége
    kezdo_sor: int        # a nyitó sor sorszáma (1-től)
    veg_sor: int          # a záró sor sorszáma (lezáratlannál az utolsó sor)
    forras: str           # a két kerítés közti szöveg
    lezart: bool
    abra: Abra


def _tisztit(s: str) -> str:
    for k, v in _UNICODE.items():
        s = s.replace(k, v)
    return re.sub(r"\s+", " ", s).strip()


def _lev(s: str) -> str:
    """Címke-escape: `\\` és `"`."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _kibont(s: str) -> str:
    return re.sub(r"\\(.)", r"\1", s)


def _cimkevel(szoveg: str) -> tuple[str, str | None]:
    m = _CIMKE.search(szoveg)
    if not m:
        return szoveg, None
    return szoveg[:m.start()], _kibont(m.group(1))


def _megjegyzes_nelkul(sor: str) -> str:
    """A sor végi ` # …` megjegyzés levágása (idézőjelen kívül)."""
    benn = False
    i = 0
    while i < len(sor):
        c = sor[i]
        if c == "\\" and benn:
            i += 2
            continue
        if c == '"':
            benn = not benn
        elif c == "#" and not benn and (i == 0 or sor[i - 1] == " "):
            return sor[:i]
        i += 1
    return sor


def _felbont_vesszo(s: str) -> list[str]:
    """Felső szintű vesszők mentén (zárójelen belül nem)."""
    reszek, melyseg, ki = [], 0, 0
    for i, c in enumerate(s):
        if c in "([":
            melyseg += 1
        elif c in ")]":
            melyseg -= 1
        elif c == "," and melyseg == 0:
            reszek.append(s[ki:i])
            ki = i + 1
    reszek.append(s[ki:])
    return [r.strip() for r in reszek]


def _jo(*kifejezesek: str) -> bool:
    """A kifejezés-szövegek nem üresek, a megengedett jelekből állnak, a zárójelek párosak."""
    for k in kifejezesek:
        if not k.strip() or not _BIZ.match(k):
            return False
        m = 0
        for c in k:
            m += (c == "(") - (c == ")")
            if m < 0:
                return False
        if m:
            return False
    return True


def _elem(sor: str):
    """Egy (megjegyzés nélküli, tisztított) sor → ('xt'|'yt', (a, b)) vagy rajzelem; `None`, ha ismeretlen."""
    torzs, cimke = _cimkevel(sor)
    torzs = torzs.strip()
    m = _TART.match(torzs)
    if m and cimke is None:
        if _jo(m.group(2), m.group(3)):
            return (m.group(1) + "t", (m.group(2).strip(), m.group(3).strip()))
        return None
    m = _PONT.match(torzs)
    if m and _jo(m.group(1), m.group(2)):
        return Pont(m.group(1).strip(), m.group(2).strip(), cimke)
    m = _EGYENL.match(torzs)
    if m and _jo(m.group(2)):
        return Egyenlotlenseg(m.group(2).strip(), m.group(1), cimke)
    m = _FGV.match(torzs)
    if m and _jo(m.group(1)):
        return Fuggveny(m.group(1).strip(), cimke)
    reszek = _felbont_vesszo(torzs)
    if len(reszek) == 3:
        mx, my, mt = _PARAM.match(reszek[0]), _PARAM_Y.match(reszek[1]), _PTART.match(reszek[2])
        if mx and my and mt and _jo(mx.group(1), my.group(1), mt.group(2), mt.group(3)):
            return Parameteres(mx.group(1).strip(), my.group(1).strip(), mt.group(1),
                               (mt.group(2).strip(), mt.group(3).strip()), cimke)
    return None


def elemez(szoveg: str) -> Abra:
    """A blokk tartalma (kerítés nélkül) → `Abra`; soronkénti hiba a `hibak`-ban, az ismeretlen sor megmarad."""
    if len(szoveg or "") > MAX_BLOKK:
        return Abra(hibak=((0, "túl nagy blokk"),))
    x_t = y_t = None
    elemek: list = []
    hibak: list = []
    for n, nyers in enumerate((szoveg or "").splitlines(), 1):
        sor = _tisztit(nyers)
        if not sor:
            continue
        if sor.startswith("#"):
            elemek.append(Megjegyzes(sor[1:].strip()))
            continue
        if len(sor) > MAX_SOR:
            elemek.append(Ismeretlen(sor))
            hibak.append((n, f"a sor hosszabb {MAX_SOR} jelnél"))
            continue
        e = _elem(_tisztit(_megjegyzes_nelkul(sor)))
        if e is None:
            elemek.append(Ismeretlen(sor))
            hibak.append((n, "ismeretlen vagy hibás sor"))
        elif isinstance(e, tuple):
            if e[0] == "xt" and x_t is None:
                x_t = e[1]
            elif e[0] == "yt" and y_t is None:
                y_t = e[1]
            else:
                elemek.append(Ismeretlen(sor))
                hibak.append((n, "a tartomány már meg van adva"))
        elif sum(not isinstance(k, (Megjegyzes, Ismeretlen)) for k in elemek) >= MAX_ELEM:
            elemek.append(Ismeretlen(sor))
            hibak.append((n, f"legfeljebb {MAX_ELEM} rajzelem"))
        else:
            elemek.append(e)
    return Abra(x_t, y_t, tuple(elemek), tuple(hibak))


def _cimke_szoveg(cimke: str | None) -> str:
    return f' "{_lev(cimke)}"' if cimke is not None else ""


def _sor(e) -> str:
    if isinstance(e, Fuggveny):
        return f"y = {e.kifejezes}{_cimke_szoveg(e.cimke)}"
    if isinstance(e, Parameteres):
        return (f"x = {e.x}, y = {e.y}, {e.t} in [{e.tartomany[0]}, {e.tartomany[1]}]"
                f"{_cimke_szoveg(e.cimke)}")
    if isinstance(e, Egyenlotlenseg):
        return f"y {e.relacio} {e.kifejezes}{_cimke_szoveg(e.cimke)}"
    if isinstance(e, Pont):
        return f"pont ({e.x}, {e.y}){_cimke_szoveg(e.cimke)}"
    if isinstance(e, Megjegyzes):
        return f"# {e.szoveg}".rstrip()
    return e.sor


def szerializal(abra: Abra) -> str:
    """Kanonikus szöveg (kerítés nélkül, záró újsor nélkül): előbb az `x`, `y` tartomány, aztán az elemek."""
    sorok = []
    if abra.x_tartomany:
        sorok.append(f"x in [{abra.x_tartomany[0]}, {abra.x_tartomany[1]}]")
    if abra.y_tartomany:
        sorok.append(f"y in [{abra.y_tartomany[0]}, {abra.y_tartomany[1]}]")
    sorok += [_sor(e) for e in abra.elemek]
    return "\n".join(sorok)


def _elem_szotar(e) -> dict:
    if isinstance(e, Fuggveny):
        return {"fajta": "fuggveny", "kifejezes": e.kifejezes, "cimke": e.cimke}
    if isinstance(e, Parameteres):
        return {"fajta": "parameteres", "x": e.x, "y": e.y, "t": e.t, "tartomany": list(e.tartomany), "cimke": e.cimke}
    if isinstance(e, Egyenlotlenseg):
        return {"fajta": "egyenlotlenseg", "kifejezes": e.kifejezes, "relacio": e.relacio, "cimke": e.cimke}
    if isinstance(e, Pont):
        return {"fajta": "pont", "x": e.x, "y": e.y, "cimke": e.cimke}
    if isinstance(e, Megjegyzes):
        return {"fajta": "megjegyzes", "szoveg": e.szoveg}
    return {"fajta": "ismeretlen", "sor": e.sor}


def abra_szotar(abra: Abra) -> dict:
    """Az ábra JSON-ható alakja (a homokozó eredményében és a core API-ban); a felület `forras.ts`-e ugyanezt a
    szerkezetet adja a blokk szövegéből (közös vektorok: `vektorok/forras.json`)."""
    return {"x_tartomany": list(abra.x_tartomany) if abra.x_tartomany else None,
            "y_tartomany": list(abra.y_tartomany) if abra.y_tartomany else None,
            "elemek": [_elem_szotar(e) for e in abra.elemek],
            "hibak": [[n, uzenet] for n, uzenet in abra.hibak]}


def blokk(abra: Abra) -> str:
    """A jegyzetbe írható blokk a kerítéssel, záró újsorral."""
    torzs = szerializal(abra)
    return "```plot\n" + (torzs + "\n" if torzs else "") + "```\n"


_KERITES = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")


def blokkok(jegyzet: str) -> list[BlokkHely]:
    """A jegyzet ```` ```plot ```` blokkjai. Más kódblokkban álló példa (akár hosszabb kerítéssel) és a
    frontmatter nem számít (13. döntés: a kódban álló szöveg nem tartalom)."""
    szoveg = jegyzet or ""
    sorok = szoveg.splitlines(keepends=True)
    helyek, kezdetek, p = [], [], 0
    for s in sorok:
        kezdetek.append(p)
        p += len(s)
    i = 0
    if sorok and sorok[0].rstrip("\r\n") == "---":
        for j in range(1, len(sorok)):
            if sorok[j].rstrip("\r\n") in ("---", "..."):
                i = j + 1
                break
    ki = []
    while i < len(sorok):
        m = _KERITES.match(sorok[i].rstrip("\r\n"))
        if not m or (m.group(1)[0] == "`" and "`" in m.group(2)):
            i += 1
            continue
        jel, info = m.group(1), m.group(2).strip()
        j = i + 1
        while j < len(sorok):
            z = _KERITES.match(sorok[j].rstrip("\r\n"))
            if z and z.group(1)[0] == jel[0] and len(z.group(1)) >= len(jel) and not z.group(2).strip():
                break
            j += 1
        lezart = j < len(sorok)
        if info.split(" ", 1)[0].lower() == "plot" and jel[0] == "`":
            forras = "".join(sorok[i + 1:j])
            veg_hely = kezdetek[j] + len(sorok[j]) if lezart else len(szoveg)
            ki.append(BlokkHely(kezdetek[i], veg_hely, i + 1, (j + 1) if lezart else len(sorok), forras, lezart,
                                elemez(forras)))
        i = j + 1
    return ki
