"""A Bases-kifejezések elemzője (C12): szöveg → szintaxisfa (`Csomo`), kiértékelés nélkül.

Forrás: az Obsidian Bases dokumentációja (`Bases syntax`, `Functions`, `Formulas`). A nyelv a JavaScript
kifejezés-részhalmaza: számok, szövegek (`"…"`, `'…'`), `true/false/null`, lista `[…]`, objektum `{…}`, regex-literál
`/…/g`, névelérés (`file.name`, `note["x"]`), hívás (`f(x)`, `x.f(y)`), unáris `! -` és a binárisok.

Precedencia (alacsonytól): `||` < `&&` < `== !=` < `< > <= >=` < `+ -` < `* / %` < unáris `! -` < postfix `. [] ()`.

Minden csomóponton ott a `kezd`/`veg` (karakter-eltolás a forrásszövegben, a `veg` kizárólagos): az átnevezés
(`hivatkozas.py`) ebből tudja kicserélni a szöveg-literálokat. A `mely` a fa magassága; a `MAX_MELY` fölött az
elemzés hibával áll meg (a kiértékelő rekurziója így korlátos).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..hibakod import angol_uzenet, json_param

MAX_MELY = 200


class KifejezesHiba(ValueError):
    """Hibás kifejezés: `kod` + `param` (a `hibakodok.BAZIS_ANGOL` kulcsa), `uzenet` az angol tartalék-mondat, `hely` a hiba
    karakter-eltolása a szövegben (vagy `None`)."""

    def __init__(self, kod: str, hely: int | None = None, param: dict | None = None):
        self.kod = kod
        self.param = json_param(param)
        self.uzenet = angol_uzenet(kod, param, kod)
        self.hely = hely
        super().__init__(self.uzenet)

    def __str__(self) -> str:
        return self.uzenet if self.hely is None else angol_uzenet("bazis.kifejezes.hely", {"uzenet": self.uzenet, "hely": self.hely + 1})


# ================================================================ szintaxisfa

@dataclass(slots=True, eq=False)
class Csomo:
    kezd: int = field(default=0, kw_only=True)
    veg: int = field(default=0, kw_only=True)
    mely: int = field(default=1, kw_only=True)

    def gyerekek(self) -> tuple:
        return ()


@dataclass(slots=True, eq=False)
class Szam(Csomo):
    ertek: int | float


@dataclass(slots=True, eq=False)
class Szoveg(Csomo):
    ertek: str
    idezo: str                      # `"` vagy `'`


@dataclass(slots=True, eq=False)
class Logikai(Csomo):
    ertek: bool


@dataclass(slots=True, eq=False)
class Null(Csomo):
    pass


@dataclass(slots=True, eq=False)
class ListaL(Csomo):
    elemek: list

    def gyerekek(self):
        return tuple(self.elemek)


@dataclass(slots=True, eq=False)
class ObjektumL(Csomo):
    parok: list                     # [(kulcs: str, érték: Csomo)]

    def gyerekek(self):
        return tuple(v for _, v in self.parok)


@dataclass(slots=True, eq=False)
class RegexL(Csomo):
    minta: str
    zaszlok: str


@dataclass(slots=True, eq=False)
class Nev(Csomo):
    nev: str


@dataclass(slots=True, eq=False)
class Tag(Csomo):
    obj: Csomo
    nev: str

    def gyerekek(self):
        return (self.obj,)


@dataclass(slots=True, eq=False)
class Index(Csomo):
    obj: Csomo
    kulcs: Csomo

    def gyerekek(self):
        return (self.obj, self.kulcs)


@dataclass(slots=True, eq=False)
class Hivas(Csomo):
    fn: Csomo
    argok: list

    def gyerekek(self):
        return (self.fn, *self.argok)


@dataclass(slots=True, eq=False)
class Unaris(Csomo):
    muvelet: str                    # `!` | `-`
    operandus: Csomo

    def gyerekek(self):
        return (self.operandus,)


@dataclass(slots=True, eq=False)
class Binaris(Csomo):
    muvelet: str
    bal: Csomo
    jobb: Csomo

    def gyerekek(self):
        return (self.bal, self.jobb)


def bejar(csomo: Csomo):
    """A fa minden csomópontja, mélységi sorrendben (a gyökérrel kezdve)."""
    verem = [csomo]
    while verem:
        c = verem.pop()
        yield c
        verem.extend(reversed(c.gyerekek()))


# ================================================================ tokenizáló

_SZAMJEL = "0123456789"
_KETJELES = ("==", "!=", "<=", ">=", "&&", "||")
_EGYJELES = "+-*/%<>!()[]{},.:"
_ESC = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}
_ZASZLO = "dgimsuvy"
# A két betű közti kötőjel az azonosító része (`image-property`, az Obsidian-dokumentáció példája); kikapcsolva `a-b` kivonás.
# Nyitott paritás-pont (T155, C31): az Obsidian lexere statikusan nem volt azonosítható; a K11-próbavault `C31 JS-paritás`
# nézetének `a-b` oszlopa dönt (K212). Ha az Obsidian kivonásnak veszi, ez a kapcsoló `False`-ra áll.
KOTOJELES_AZONOSITO = True
# Ezek után `/` osztás; minden más (operátor, nyitó zárójel, vessző, kettőspont, az elejére) után regex-literál.
_OPERANDUS_VEGE = {"szam", "szoveg", "nev", "regex", ")", "]", "}"}


def _azon_kezd(c: str) -> bool:
    return c == "_" or c == "$" or c.isalpha()


def _azon_resz(c: str) -> bool:
    return c == "_" or c == "$" or c.isalnum()


def _tokenek(s: str) -> list[tuple]:
    """[(fajta, érték, kezd, veg)]; a fajta: szam | szoveg | nev | regex | vég | maga a jel."""
    out: list[tuple] = []
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c.isspace():
            i += 1
            continue
        if c in _SZAMJEL:
            j = i
            while j < n and s[j] in _SZAMJEL:
                j += 1
            tort = False
            if j + 1 < n and s[j] == "." and s[j + 1] in _SZAMJEL:
                tort = True
                j += 1
                while j < n and s[j] in _SZAMJEL:
                    j += 1
            if j < n and s[j] in "eE":
                k = j + 1
                if k < n and s[k] in "+-":
                    k += 1
                if k < n and s[k] in _SZAMJEL:
                    tort = True
                    while k < n and s[k] in _SZAMJEL:
                        k += 1
                    j = k
            if j < n and _azon_kezd(s[j]):
                raise KifejezesHiba("bazis.kifejezes.szam_utan_betu", j)
            sz = s[i:j]
            out.append(("szam", float(sz) if tort else int(sz), i, j))
            i = j
            continue
        if c in "\"'":
            j, buf = i + 1, []
            while True:
                if j >= n:
                    raise KifejezesHiba("bazis.kifejezes.lezaratlan_szoveg", i)
                d = s[j]
                if d == "\\":
                    if j + 1 >= n:
                        raise KifejezesHiba("bazis.kifejezes.lezaratlan_szoveg", i)
                    e = s[j + 1]
                    hexa = s[j + 2:j + 6]
                    if e == "u" and len(hexa) == 4 and all(h in "0123456789abcdefABCDEF" for h in hexa):
                        buf.append(chr(int(hexa, 16)))
                        j += 6
                    else:
                        buf.append(_ESC.get(e, e))
                        j += 2
                    continue
                if d == c:
                    j += 1
                    break
                buf.append(d)
                j += 1
            out.append(("szoveg", ("".join(buf), c), i, j))
            i = j
            continue
        if _azon_kezd(c):
            j = i + 1
            while j < n:
                if _azon_resz(s[j]):
                    j += 1
                elif KOTOJELES_AZONOSITO and s[j] == "-" and j + 1 < n and s[j + 1].isalpha() and s[j - 1].isalpha():
                    j += 1          # `image-property`: a kötőjel két betű között az azonosító része
                else:
                    break
            out.append(("nev", s[i:j], i, j))
            i = j
            continue
        if c == "/" and (not out or out[-1][0] not in _OPERANDUS_VEGE):
            j, osztaly = i + 1, False
            while True:
                if j >= n:
                    raise KifejezesHiba("bazis.kifejezes.lezaratlan_regex", i)
                d = s[j]
                if d == "\\":
                    j += 2
                    continue
                if d == "[":
                    osztaly = True
                elif d == "]":
                    osztaly = False
                elif d == "/" and not osztaly:
                    break
                j += 1
            minta = s[i + 1:j]
            j += 1
            k = j
            while k < n and s[k] in _ZASZLO:
                k += 1
            out.append(("regex", (minta, s[j:k]), i, k))
            i = k
            continue
        if s[i:i + 2] in _KETJELES:
            out.append((s[i:i + 2], s[i:i + 2], i, i + 2))
            i += 2
            continue
        if c in _EGYJELES:
            out.append((c, c, i, i + 1))
            i += 1
            continue
        raise KifejezesHiba("bazis.kifejezes.varatlan_karakter", i, {"c": repr(c)})
    out.append(("vég", None, n, n))
    return out


# ================================================================ elemző (Pratt)

_BINARIS = {"||": 10, "&&": 20, "==": 30, "!=": 30, "<": 40, ">": 40, "<=": 40, ">=": 40,
            "+": 50, "-": 50, "*": 60, "/": 60, "%": 60}
_UNARIS_BP = 70
_MAX_BEAGYAZAS = 100                    # zárójel-, lista- és hívás-beágyazás (szintenként 4 Python-keret); a láncot a `mely` korlátozza


class _Elemzo:
    def __init__(self, szoveg: str):
        self.s = szoveg
        self.t = _tokenek(szoveg)
        self.i = 0
        self.beagyazas = 0

    # ---- segédek
    def _nez(self):
        return self.t[self.i]

    def _lep(self):
        t = self.t[self.i]
        self.i += 1
        return t

    def _var(self, fajta: str, mit: str):
        t = self._nez()
        if t[0] != fajta:
            raise KifejezesHiba("bazis.kifejezes.hianyzik", t[2], {"mit": mit})
        return self._lep()

    def _kesz(self, csomo: Csomo, kezd: int, veg: int) -> Csomo:
        csomo.kezd, csomo.veg = kezd, veg
        csomo.mely = 1 + max((g.mely for g in csomo.gyerekek()), default=0)
        if csomo.mely > MAX_MELY:
            raise KifejezesHiba("bazis.kifejezes.tul_melyen", kezd)
        return csomo

    def _be(self, hely: int):
        self.beagyazas += 1
        if self.beagyazas > _MAX_BEAGYAZAS:
            raise KifejezesHiba("bazis.kifejezes.tul_melyen", hely)

    def _ki(self):
        self.beagyazas -= 1

    # ---- nyelvtan
    def elemez(self) -> Csomo:
        if self._nez()[0] == "vég":
            raise KifejezesHiba("bazis.kifejezes.ures", 0)
        c = self.kifejezes(0)
        t = self._nez()
        if t[0] != "vég":
            raise KifejezesHiba("bazis.kifejezes.varatlan", t[2], {"mit": self._leir(t)})
        return c

    @staticmethod
    def _leir(t) -> str:
        if t[0] == "vég":
            return "end of expression"
        return {"szam": "number", "szoveg": "text", "nev": "name", "regex": "regex"}.get(t[0], f"`{t[0]}`")

    def kifejezes(self, min_bp: int) -> Csomo:
        bal = self.unaris()
        while True:
            t = self._nez()
            bp = _BINARIS.get(t[0])
            if bp is None or bp < min_bp:
                return bal
            self._lep()
            self._be(t[2])
            jobb = self.kifejezes(bp + 1)       # balasszociatív
            self._ki()
            bal = self._kesz(Binaris(t[0], bal, jobb), bal.kezd, jobb.veg)

    def unaris(self) -> Csomo:
        t = self._nez()
        if t[0] in ("!", "-"):
            self._lep()
            self._be(t[2])
            o = self.unaris()
            self._ki()
            return self._kesz(Unaris(t[0], o), t[2], o.veg)
        return self.postfix()

    def postfix(self) -> Csomo:
        c = self.elso()
        while True:
            t = self._nez()
            if t[0] == ".":
                self._lep()
                n = self._nez()
                if n[0] != "nev":
                    raise KifejezesHiba("bazis.kifejezes.pont_utan_nev", n[2])
                self._lep()
                c = self._kesz(Tag(c, n[1]), c.kezd, n[3])
            elif t[0] == "[":
                self._lep()
                self._be(t[2])
                k = self.kifejezes(0)
                z = self._var("]", "]")
                self._ki()
                c = self._kesz(Index(c, k), c.kezd, z[3])
            elif t[0] == "(":
                self._lep()
                self._be(t[2])
                argok = self._argok(")", ")")
                z = self._lep()
                self._ki()
                c = self._kesz(Hivas(c, argok), c.kezd, z[3])
            else:
                return c

    def _argok(self, zaro: str, mit: str) -> list:
        argok = []
        if self._nez()[0] == zaro:
            return argok
        while True:
            argok.append(self.kifejezes(0))
            t = self._nez()
            if t[0] == ",":
                self._lep()
                if self._nez()[0] == zaro:      # záró vessző (JavaScript)
                    break
                continue
            break
        self._var(zaro, mit)
        self.i -= 1                             # a hívó olvassa be a záró jelet
        return argok

    def elso(self) -> Csomo:
        t = self._lep()
        f = t[0]
        if f == "szam":
            return self._kesz(Szam(t[1]), t[2], t[3])
        if f == "szoveg":
            return self._kesz(Szoveg(t[1][0], t[1][1]), t[2], t[3])
        if f == "regex":
            return self._kesz(RegexL(t[1][0], t[1][1]), t[2], t[3])
        if f == "nev":
            if t[1] == "true":
                return self._kesz(Logikai(True), t[2], t[3])
            if t[1] == "false":
                return self._kesz(Logikai(False), t[2], t[3])
            if t[1] == "null":
                return self._kesz(Null(), t[2], t[3])
            return self._kesz(Nev(t[1]), t[2], t[3])
        if f == "(":
            self._be(t[2])
            c = self.kifejezes(0)
            self._var(")", ")")
            self._ki()
            return c                                # a zárójel nem csomópont; a pozíciók a kifejezéséi maradnak
        if f == "[":
            self._be(t[2])
            elemek = self._argok("]", "]")
            z = self._lep()
            self._ki()
            return self._kesz(ListaL(elemek), t[2], z[3])
        if f == "{":
            self._be(t[2])
            parok = []
            if self._nez()[0] != "}":
                while True:
                    k = self._lep()
                    if k[0] == "szoveg":
                        kulcs = k[1][0]
                    elif k[0] == "nev":
                        kulcs = k[1]
                    elif k[0] == "szam":
                        kulcs = str(k[1])
                    else:
                        raise KifejezesHiba("bazis.kifejezes.objektum_kulcs", k[2])
                    self._var(":", ":")
                    parok.append((kulcs, self.kifejezes(0)))
                    if self._nez()[0] == ",":
                        self._lep()
                        if self._nez()[0] == "}":
                            break
                        continue
                    break
            z = self._var("}", "}")
            self._ki()
            return self._kesz(ObjektumL(parok), t[2], z[3])
        raise KifejezesHiba("bazis.kifejezes.varatlan", t[2], {"mit": self._leir(t)})


def elemez(szoveg: str) -> Csomo:
    """A kifejezés szintaxisfája; hibás szövegre `KifejezesHiba`."""
    if not isinstance(szoveg, str):
        raise KifejezesHiba("bazis.kifejezes.nem_szoveg")
    try:
        return _Elemzo(szoveg).elemez()
    except RecursionError:                  # a beágyazás-korlát mellett is: a hívó verem már mély lehet
        raise KifejezesHiba("bazis.kifejezes.tul_melyen") from None
