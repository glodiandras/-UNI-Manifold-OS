"""Keresés az indexben: az Obsidian lekérdezés-nyelvének részhalmaza.

    szó             a szó a szókezdetre illeszt (a „ház” a „házak”-at is), kis-nagybetű- és ékezetfüggetlenül;
                    a tartalomban, a fájlnévben vagy az útban
    "kifejezés"     egymást követő szavak, pontosan
    a b             ÉS · a OR b · -a (tagadás) · (zárójel)
    path:x          az út része (ékezetfüggetlen); file:x a fájlnév része; mindkettő lehet /regex/ is
    tag:#a          a címke, vagy alatta álló (#a/b); kis-nagybetűtől független
    line:(a b)      egy soron belül teljesül; csak a sor szövegét nézi (a fájlnevet és az utat nem)
    section:(a b)   egy szakaszon belül teljesül (címsortól a következő azonos vagy magasabb szintű címsorig; a címsor előtti
                    szöveg külön szakasz; a frontmatter nem tartozik szakaszhoz)
    task:(a b)      egy feladatsor szövegén belül teljesül; `task-todo:` a nyitott (`[ ]`), `task-done:` a kész (`[x]`) feladatok
    [kulcs]         a jegyzetnek van ilyen tulajdonsága (kulcs: kis-nagybetűtől független); `[kulcs:érték]` az érték (lista:
                    elemenként) ékezetfüggetlen részszövege; `[k:"a b"]`, `[k:/re/]`, `[k:a OR b]`, `[k:null]` (üres érték)
    match-case:(…)  a belsejében a szavak és kifejezések kis-nagybetű- és ékezetérzékenyek (az Obsidian „Match case”);
                    `ignore-case:(…)` visszakapcsol; a `/regex/` alapból érzékeny, az `ignore-case:`-ben nem
    *szó            részszó: a szó a szó belsejében is illeszt (additív; `substring:(…)` a belsejében minden csupasz szóra)
    /regex/         Python-regex a tartalomra (kis-nagybetűre érzékeny)

Végrehajtás: az FTS5 (`unicode61 remove_diacritics 2`) szűri a jelölteket, ahol a lekérdezés kifejezhető
vele; a `line:`, a regex, a tagadás és az operátorok ellenőrzése Pythonban fut. Rangsor: `bm25`
(út 2, név 10, tartalom 1). Találatonként a sorok (sor 1-től, oszlop 0-tól, kódpontban) a kiemeléshez.

C25c: a PDF lapjainak és a VTT-felirat mondatainak szövege a külön `fts_szakasz` táblában áll (a jegyzetek `fts`-ének
bm25-statisztikája így változatlan); a kérdés lapon / ~60 s-os feliratablakon belül teljesül (`_media`). Az ilyen fájl
találata `tipus`-t (`pdf` | `felirat`) kap, a sorai a helyet: `oldal` (1-től), ill. `mp` (a mondat kezdete); a pontja a legjobb
szakaszáé `MEDIA_SULY`-lyal súlyozva (kalibrálatlan induló érték, NAPLO C25c). A csak regexes vagy csak operátoros kérdés
(FTS-kifejezés nélkül) a média szövegét nem nézi.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
import unicodedata

import regex

from ..vaultio import Invalid
from .elemzo import FM_RE, _Sorok
from .feloldas import MD_RE
from .maszk import link_maszk
from ..hibakod import kodol

ALOP_OPERATOROK = ("line", "section", "task", "task-todo", "task-done", "match-case", "ignore-case", "substring")
OPERATOROK = ("path", "file", "tag", *ALOP_OPERATOROK)         # az „alop” operátorok zárójeles al-kifejezést vagy egy értéket kapnak
ERZEKENY, ERZEKENYTELEN, RESZSZO = 1, 2, 4                     # a kiértékelés módjai (bitek): match-case · ignore-case · substring
MEDIA_TIPUSOK = ("pdf", "felirat")
MEDIA_SULY = 0.5
MAX_JELOLT = 5000
MAX_SOR = 20

_HAJT: dict[int, str] = {cp: chr(cp + 32) for cp in range(65, 91)}
for _cp in [*range(0x80, 0x250), *range(0x370, 0x530), *range(0x1E00, 0x1F00)]:
    _d = unicodedata.normalize("NFD", chr(_cp))[0].lower()
    if len(_d) == 1 and _d != chr(_cp):
        _HAJT[_cp] = _d


def hajt(s: str) -> str:
    """Kisbetűs, ékezet nélküli alak, hossztartó (az eltolások az eredetire mutatnak)."""
    return s.translate(_HAJT)


# ================================================================ lexer + parser

def _lex(q: str) -> list[tuple[str, str]]:
    out, i, n = [], 0, len(q)
    while i < n:
        ch = q[i]
        if ch.isspace():
            i += 1
        elif ch in "()":
            out.append((ch, ch))
            i += 1
        elif ch == '"':
            j = q.find('"', i + 1)
            j = n if j < 0 else j
            out.append(("kif", q[i + 1:j]))
            i = j + 1
        elif ch == "/" and _regex_veg(q, i) > 0:
            j = _regex_veg(q, i)
            out.append(("regex", q[i + 1:j]))
            i = j + 1
        elif ch == "-" and i + 1 < n and not q[i + 1].isspace():
            out.append(("nem", "-"))
            i += 1
        elif ch == "[" and (j := _tul_veg(q, i)) > 0:
            out.append(("tul", q[i + 1:j]))
            i = j + 1
        else:
            j = i
            while j < n and not q[j].isspace() and q[j] not in "()":
                if q[j] == ":" and q[i:j].lower() in OPERATOROK:
                    break
                j += 1
            if j < n and q[j] == ":":
                out.append(("op", q[i:j].lower()))
                i = j + 1
                continue
            szo = q[i:j]
            out.append(("vagy", szo) if szo == "OR" else ("szo", szo))
            i = j
    return out


def _tul_veg(q: str, i: int) -> int:
    """A `[kulcs:érték]` tulajdonság-feltétel záró `]`-je (az idézőjelek és a `/regex/` belsejében álló `]` nem zár), vagy -1, ha
    ez nem feltétel (nincs záró, üres a kulcs, `[[wikilink]]`, vagy a `]` után nem szóköz/zárójel/vég áll) — ekkor a `[` sima
    szó-karakter, mint eddig."""
    n = len(q)
    if q.startswith("[[", i):
        return -1
    j, kettospont = i + 1, False
    while j < n:
        ch = q[j]
        if ch == "]":
            break
        if ch == '"':
            k = q.find('"', j + 1)
            if k < 0:
                return -1
            j = k + 1
            continue
        if ch == "/" and kettospont and q[j - 1] == ":" and _regex_veg(q, j) > 0:
            j = _regex_veg(q, j) + 1
            continue
        if ch == ":":
            kettospont = True
        j += 1
    if j >= n or not q[i + 1:j].partition(":")[0].strip().strip('"').strip() \
            or (j + 1 < n and not (q[j + 1].isspace() or q[j + 1] == ")")):
        return -1
    return j


def _tul_szet(belso: str):
    """A `[…]` belseje → `(kulcs, alternativák | None)`; alternatíva: `("szo", szöveg)` | `("regex", _Rx)` | `("nulla",)`."""
    kulcs, kp, ertek = belso.partition(":")
    kulcs = kulcs.strip().strip('"').strip()
    if not kp:
        return kulcs, None
    return kulcs, _alternativak(ertek)


def _alternativak(ertek: str) -> list[tuple]:
    darabok, kezd, i, n = [], 0, 0, len(ertek)
    while i < n:
        if ertek[i] == '"' and ertek.find('"', i + 1) > 0:
            i = ertek.find('"', i + 1) + 1
        elif ertek[i] == "/" and _regex_veg(ertek, i) > 0:
            i = _regex_veg(ertek, i) + 1
        elif ertek.startswith(" OR ", i):
            darabok.append(ertek[kezd:i])
            i += 4
            kezd = i
        else:
            i += 1
    darabok.append(ertek[kezd:])
    ki = []
    for d in darabok:
        d = d.strip()
        if len(d) >= 2 and d[0] == d[-1] == '"':
            ki.append(("szo", d[1:-1]))
        elif len(d) >= 3 and d[0] == "/" and _regex_veg(d, 0) == len(d) - 1:
            ki.append(("regex", _regex(d[1:-1])))
        elif d.lower() == "null":
            ki.append(("nulla",))
        elif d:
            ki.append(("szo", d))
    return ki or [("szo", "")]


def _regex_veg(q: str, i: int) -> int:
    j = i + 1
    while j < len(q):
        if q[j] == "\\":
            j += 2
            continue
        if q[j] == "/":
            return j if j > i + 1 else -1
        j += 1
    return -1


class _Parser:
    def __init__(self, tokenek):
        self.t, self.i = tokenek, 0

    def kov(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def vesz(self):
        tok = self.kov()
        self.i += 1
        return tok

    def kifejezes(self):
        agak = [self.es()]
        while self.kov()[0] == "vagy":
            self.vesz()
            agak.append(self.es())
        return agak[0] if len(agak) == 1 else ("vagy", agak)

    def es(self):
        tagok = []
        while self.kov()[0] not in (None, ")", "vagy"):
            tagok.append(self.egy())
        if not tagok:
            raise kodol(Invalid("üres keresési kifejezés"), "index.kereses.ures_keresesi_kifejezes")
        return tagok[0] if len(tagok) == 1 else ("es", tagok)

    def egy(self):
        f, v = self.vesz()
        if f == "nem":
            return ("nem", self.egy())
        if f == "(":
            e = self.kifejezes()
            if self.vesz()[0] != ")":
                raise kodol(Invalid("hiányzó záró zárójel"), "index.kereses.hianyzo_zaro_zarojel")
            return e
        if f == "op":
            if v in ALOP_OPERATOROK and self.kov()[0] == "(":
                return ("op", v, self.egy())
            return ("op", v, self._ertek())
        if f == "tul":
            kulcs, alt = _tul_szet(v)
            return ("tul", kulcs, alt)
        if f == "regex":
            return ("regex", _regex(v))
        if f == "szo" and len(v) > 1 and v[0] == "*":
            return ("reszszo", v[1:])
        if f in ("szo", "kif"):
            return (f, v)
        raise kodol(Invalid(f"váratlan elem a keresésben: {v}"), "index.kereses.varatlan_elem_keresesben_v", {"v": v})

    def _ertek(self):
        f, v = self.vesz()
        if f == "regex":
            return ("regex", _regex(v))
        if f in ("szo", "kif"):
            return (f, v)
        raise kodol(Invalid("az operátor után érték kell"), "index.kereses.operator_utan_ertek_kell")


REGEX_IDOKORLAT_MP = 2.0
_hatar = threading.local()          # a folyó keresés határideje (monotonic), szálanként


class _Rx:
    """A felhasználói regex (H5, audit): a `regex` csomag V0 (a `re`-vel kompatibilis) módjában, keresésenkénti
    határidővel és a GIL elengedésével (`concurrent`) — a katasztrofális visszalépés nem állítja meg a core-t."""

    def __init__(self, minta: str):
        try:
            self.rx = regex.compile(minta, regex.M)
        except regex.error as e:
            raise kodol(Invalid(f"hibás regex: {e}"), "index.kereses.hibas_regex_e", {"e": e}) from e
        self.minta, self._ic = minta, None

    @property
    def ic(self) -> "_Rx":
        """Ugyanez kis-nagybetűtől függetlenül (az `ignore-case:` belsejében)."""
        if self._ic is None:
            self._ic = _Rx.__new__(_Rx)
            self._ic.rx, self._ic.minta, self._ic._ic = regex.compile(self.minta, regex.M | regex.I), self.minta, self._ic
        return self._ic

    @staticmethod
    def _hatra() -> float:
        h = getattr(_hatar, "ertek", None)
        if h is None:
            return REGEX_IDOKORLAT_MP
        hatra = h - time.monotonic()
        if hatra <= 0:
            raise TimeoutError
        return hatra

    def search(self, s: str):
        return self.rx.search(s, concurrent=True, timeout=self._hatra())

    def finditer(self, s: str):
        return self.rx.finditer(s, concurrent=True, timeout=self._hatra())


def _regex(minta: str) -> _Rx:
    return _Rx(minta)


def elemez(q: str):
    if not isinstance(q, str) or not q.strip():
        raise kodol(Invalid("üres keresés"), "index.kereses.ures_kereses")
    p = _Parser(_lex(q))
    e = p.kifejezes()
    if p.kov()[0] is not None:
        raise kodol(Invalid("fölösleges záró zárójel"), "index.kereses.folosleges_zaro_zarojel")
    return e


# ================================================================ FTS-szűrő

def _tokenek(s: str) -> list[str]:
    return re.findall(r"\w+", hajt(s))


def fts_kifejezes(s: str, prefix: bool = False) -> str | None:
    """Egy szó vagy kifejezés FTS5-alakja (idézett tokenek; `prefix`: az utolsó token előtag)."""
    t = _tokenek(s)
    if not t:
        return None
    return '"' + " ".join(t) + '"' + ("*" if prefix else "")


def _fts(e, reszszo: bool = False) -> str | None:
    """Az FTS-előszűrő: az `e` minden találatát tartalmazó jelölthalmaz (szuperhalmaz) kifejezése, vagy `None` (nincs szűrés).
    `reszszo`: a `substring:` belsejében a csupasz szó nem előtag-alapú, így nem szűrhető."""
    f = e[0]
    if f == "szo":
        return None if reszszo else fts_kifejezes(e[1], prefix=True)
    if f == "kif":
        return fts_kifejezes(e[1])
    if f == "es":
        r = [x for x in (_fts(y, reszszo) for y in e[1]) if x]
        return " AND ".join(f"({x})" for x in r) if r else None
    if f == "vagy":
        r = [_fts(x, reszszo) for x in e[1]]
        return None if any(x is None for x in r) else " OR ".join(f"({x})" for x in r)
    if f == "op" and e[1] in ALOP_OPERATOROK and isinstance(e[2], tuple):
        # a belső kifejezés szavai a fájlban (a sor/szakasz/feladat/kisnagy módosító mind a fájl szövegének részhalmazára szűr)
        return _fts(e[2], reszszo or e[1] == "substring")
    return None


# ================================================================ kiértékelés

class _Gyoker:
    """Egy jegyzet lusta, fájlonként egyszer betöltött adatai (tulajdonságok, feladatok, címsorok) — a `line:`/`section:`/`task:`
    al-dokumentumai ezt osztják."""

    def __init__(self, c, fid: int, media: bool):
        self.c, self.fid, self.media = c, fid, media
        self._tul = self._fel = self._fej = None

    @property
    def tul(self) -> dict[str, list[str]]:
        """kisbetűs kulcs → az érték szövegei (lista: elemenként; `null`/üres: üres lista)."""
        if self._tul is None:
            self._tul = {}
            for kulcs, ertek in self.c.execute("SELECT kulcs, ertek FROM tulajdonsag WHERE fajl_id = ? ORDER BY sorrend",
                                               (self.fid,)):
                if isinstance(kulcs, str):
                    self._tul.setdefault(kulcs.strip().lower(), []).extend(_tul_szovegek(ertek))
        return self._tul

    @property
    def feladatok(self) -> list[tuple[int, str, str]]:
        if self._fel is None:
            self._fel = [] if self.media else self.c.execute(
                "SELECT sor, allapot, szoveg FROM feladat WHERE fajl_id = ? ORDER BY sor", (self.fid,)).fetchall()
        return self._fel

    @property
    def fejezetek(self) -> list[tuple[int, int]]:
        if self._fej is None:
            self._fej = [] if self.media else self.c.execute(
                "SELECT sor, szint FROM fejezet WHERE fajl_id = ? ORDER BY sor", (self.fid,)).fetchall()
        return self._fej


def _tul_szovegek(nyers) -> list[str]:
    """Egy `tulajdonsag.ertek` (JSON) kereshető szövegei: skalár → 1, lista → elemenként (üres/null → nincs); a logikai
    érték `true`/`false`."""
    try:
        v = json.loads(nyers)
    except (TypeError, ValueError):
        return [str(nyers)] if nyers else []
    ki: list[str] = []
    for e in (v if isinstance(v, list) else [v]):
        if e is None or isinstance(e, (dict, list)):
            continue
        s = ("true" if e else "false") if isinstance(e, bool) else str(e).strip()
        if s:
            ki.append(s)
    return ki


class _Dok:
    def __init__(self, c, fid, ut, nev, cimkek, tartalom=None, gyoker: _Gyoker | None = None, media: bool = False):
        self.c, self.fid, self.ut, self.nev, self._cimkek = c, fid, ut, nev, cimkek
        self._t, self._h, self._sorkezd = tartalom, None, None
        self.gyoker = gyoker or _Gyoker(c, fid, media)
        self.fo = gyoker is None                    # a jegyzet maga (nem `line:`/`section:`/`task:` al-dokumentuma)

    @property
    def tartalom(self) -> str:
        if self._t is None:
            r = self.c.execute("SELECT tartalom FROM fts WHERE rowid = ?", (self.fid,)).fetchone()
            self._t = r[0] if r else ""
        return self._t

    @property
    def hajtott(self) -> str:
        if self._h is None:
            self._h = hajt(self.tartalom)
        return self._h

    @property
    def cimkek(self) -> set[str]:
        return self._cimkek.get(self.fid, set())

    def sor(self, szoveg: str) -> "_Dok":
        # a `line:` csak a sor szövegét értékeli: üres név és út mellett a név/út-visszaesés nem találhat (T061)
        return _Dok(self.c, self.fid, "", "", self._cimkek, szoveg, self.gyoker)

    def sorkezdetek(self) -> list[int]:
        if self._sorkezd is None:
            self._sorkezd = [0] + [m.end() for m in re.finditer("\n", self.tartalom)]
        return self._sorkezd

    def szakaszok(self) -> list[tuple[int, int]]:
        """A `section:` szakaszai (karakter-eltolás-tartományok): a címsor-tábla szerint; az első címsor előtti szöveg külön
        szakasz; a frontmatter egyikhez sem tartozik. Címsor-tábla nélküli (média, al-dokumentum) szövegnél az egész."""
        t = self.tartalom
        if not self.fo or self.gyoker.media or not self.gyoker.fejezetek:
            return [(0, len(t))]
        kezd = self.sorkezdetek()
        fm = FM_RE.match(t)
        elejo = fm.end() if fm else 0
        fejek = [(kezd[sor - 1], szint) for sor, szint in self.gyoker.fejezetek if 0 < sor <= len(kezd) and kezd[sor - 1] >= elejo]
        ki = [(elejo, fejek[0][0])] if fejek and fejek[0][0] > elejo else ([] if fejek else [(elejo, len(t))])
        for i, (off, szint) in enumerate(fejek):
            veg = next((o for o, sz in fejek[i + 1:] if sz <= szint), len(t))
            ki.append((off, veg))
        return ki


def _szo_minta(e, mod: int = 0):
    """A csupasz szó / kifejezés mintája a hajtott (ékezet- és kisbetű-nélküli) szövegre; `ERZEKENY`: a nyers szövegre, a
    kis-nagybetűt és az ékezetet megtartva. Csupasz szó: szókezdetre (`RESZSZO`/`*szó`: a szó belsejében is)."""
    nyers = e[1] if mod & ERZEKENY else hajt(e[1])
    if e[0] in ("szo", "reszszo"):
        return re.compile(("" if e[0] == "reszszo" or mod & RESZSZO else r"(?<!\w)") + re.escape(nyers))
    return re.compile(r"(?<!\w)" + r"\s+".join(map(re.escape, nyers.split())) + r"(?!\w)")


def _ertek_illik(e, szoveg: str, mod: int = 0) -> bool:
    if e[0] == "regex":
        return bool((e[1].ic if mod & ERZEKENYTELEN else e[1]).search(szoveg))
    return e[1] in szoveg if mod & ERZEKENY else hajt(e[1]) in hajt(szoveg)


def _tul_illik(alt: list[tuple], ertekek: list[str], mod: int) -> bool:
    for a in alt:
        if a[0] == "nulla":
            if not ertekek:
                return True
        elif a[0] == "regex":
            rx = a[1].ic if mod & ERZEKENYTELEN else a[1]
            if any(rx.search(x) for x in ertekek):
                return True
        else:
            cel = a[1].strip()
            cel = cel[1:] if cel.startswith("#") else cel
            if mod & ERZEKENY:
                if any(cel in x for x in ertekek):
                    return True
            elif any(hajt(cel) in hajt(x) for x in ertekek):
                return True
    return False


def _kiertekel(e, d: _Dok, minták: dict, mod: int = 0) -> tuple[bool, list]:
    f = e[0]
    if f in ("szo", "kif", "reszszo"):
        if not e[1].strip():
            return True, []
        m = minták.setdefault(id(e), _szo_minta(e, mod))
        szoveg = d.tartalom if mod & ERZEKENY else d.hajtott
        spanok = [x.span() for x in m.finditer(szoveg)]
        if spanok:
            return True, spanok
        nev, ut = d.nev.rsplit(".", 1)[0], d.ut
        if not mod & ERZEKENY:
            nev, ut = hajt(nev), hajt(ut)
        return bool(m.search(nev) or m.search(ut)), []
    if f == "regex":
        rx = e[1].ic if mod & ERZEKENYTELEN else e[1]
        spanok = [x.span() for x in rx.finditer(d.tartalom) if x.end() > x.start()]
        return bool(spanok) or bool(rx.search(d.tartalom)), spanok
    if f == "tul":
        ertekek = d.gyoker.tul.get(e[1].strip().lower())
        if ertekek is None:
            return False, []
        return (True if e[2] is None else _tul_illik(e[2], ertekek, mod)), []
    if f == "nem":
        return not _kiertekel(e[1], d, minták, mod)[0], []
    if f == "es":
        spanok = []
        for x in e[1]:
            ok, s = _kiertekel(x, d, minták, mod)
            if not ok:
                return False, []
            spanok += s
        return True, spanok
    if f == "vagy":
        ok_any, spanok = False, []
        for x in e[1]:
            ok, s = _kiertekel(x, d, minták, mod)
            ok_any |= ok
            spanok += s
        return ok_any, spanok
    if f == "op":
        nev, v = e[1], e[2]
        if nev == "match-case":
            return _kiertekel(v, d, minták, (mod | ERZEKENY) & ~ERZEKENYTELEN)
        if nev == "ignore-case":
            return _kiertekel(v, d, minták, (mod | ERZEKENYTELEN) & ~ERZEKENY)
        if nev == "substring":
            return _kiertekel(v, d, minták, mod | RESZSZO)
        if nev == "path":
            return _ertek_illik(v, d.ut, mod), []
        if nev == "file":
            return _ertek_illik(v, d.nev, mod), []
        if nev == "tag":
            if v[0] == "regex":
                rx = v[1].ic if mod & ERZEKENYTELEN else v[1]
                return any(rx.search(t) for t in d.cimkek), []
            cel = v[1].strip().lstrip("#").lower()
            return any(t == cel or t.startswith(cel + "/") for t in d.cimkek), []
        if nev == "line":
            spanok, off = [], 0
            for s in d.tartalom.split("\n"):
                ok, sp = _kiertekel(v, d.sor(s), minták, mod)
                if ok and s.strip():
                    spanok += [(a + off, b + off) for a, b in sp] or [(off, off + len(s))]
                off += len(s) + 1
            return bool(spanok), spanok
        if nev == "section":
            spanok = []
            for kezd, veg in d.szakaszok():
                szoveg = d.tartalom[kezd:veg]
                ok, sp = _kiertekel(v, d.sor(szoveg), minták, mod)
                if ok and szoveg.strip():
                    elso = len(szoveg) - len(szoveg.lstrip())
                    sor_veg = szoveg.find("\n", elso)
                    spanok += [(a + kezd, b + kezd) for a, b in sp] or [(kezd + elso, kezd + (len(szoveg) if sor_veg < 0 else sor_veg))]
            return bool(spanok), spanok
        if nev in ("task", "task-todo", "task-done"):
            spanok, kezd = [], d.sorkezdetek()
            sorok = d.tartalom.split("\n")
            for sor, allapot, szoveg in d.gyoker.feladatok:
                if not d.fo or not szoveg or not 0 < sor <= len(sorok):
                    continue
                if (nev == "task-todo" and allapot != " ") or (nev == "task-done" and allapot not in ("x", "X")):
                    continue
                p = max(0, sorok[sor - 1].find(szoveg))
                ok, sp = _kiertekel(v, d.sor(szoveg), minták, mod)
                if ok:
                    eltol = kezd[sor - 1] + p
                    spanok += [(a + eltol, b + eltol) for a, b in sp] or [(eltol, eltol + len(szoveg))]
            return bool(spanok), spanok
    raise kodol(Invalid(f"ismeretlen keresési elem: {f}"), "index.kereses.ismeretlen_keresesi_elem_f", {"f": f})


def _van(e, fajta: str) -> bool:
    """Szerepel-e a `fajta` operátor (`tag`) a kifejezésben, az al-kifejezések (`line:(…)`, `section:(…)`, …) belsejében is."""
    if e[0] == fajta or (e[0] == "op" and e[1] == fajta):
        return True
    if e[0] in ("es", "vagy"):
        return any(_van(x, fajta) for x in e[1])
    if e[0] == "nem":
        return _van(e[1], fajta)
    if e[0] == "op":
        return _van(e[2], fajta) if isinstance(e[2], tuple) else False
    return False


def _sorok(tartalom: str, spanok: list, max_db: int = MAX_SOR, kornyezet: int = 0) -> list[dict]:
    """A találati sorok; `kornyezet` > 0: soronként a szomszédos sorok is (`elotte`, `utana`, legfeljebb ennyi-ennyi,
    a fájl szélén kevesebb; a sorvég-`\\r` nélkül)."""
    poz, sorok, out, lattam = _Sorok(tartalom), None, [], set()
    for a, b in sorted(set(spanok)):
        sor, osz = poz(a)
        if (sor, osz) in lattam:
            continue
        lattam.add((sor, osz))
        if sorok is None:
            sorok = tartalom.split("\n")
        szoveg = sorok[sor - 1]
        t = {"sor": sor, "oszlop": osz, "hossz": min(b - a, len(szoveg) - osz), "szoveg": szoveg[:400]}
        if kornyezet:
            t["elotte"] = [x.rstrip("\r")[:400] for x in sorok[max(0, sor - 1 - kornyezet):sor - 1]]
            veg = len(sorok) - 1 if sorok[-1] == "" else len(sorok)               # a záró újsor utáni üres „sor” nem sor
            t["utana"] = [x.rstrip("\r")[:400] for x in sorok[sor:min(sor + kornyezet, veg)]]
        out.append(t)
        if len(out) >= max_db:
            break
    return out


def keres(c, q: str, limit: int = 200, idokorlat: float = REGEX_IDOKORLAT_MP, kornyezet: int = 0) -> dict:
    """A keresés; a regexek együtt legfeljebb `idokorlat` másodpercig futnak (túllépés: `Invalid` → 400)."""
    e = elemez(q)
    _hatar.ertek = time.monotonic() + idokorlat
    try:
        return _keres(c, q, e, limit, kornyezet)
    except TimeoutError:
        raise kodol(Invalid(f"A regex túl sokáig futott ({idokorlat:g} s alatt nem végzett) — egyszerűsítsd a mintát "
                      "(pl. az egymásba ágyazott ismétlést, mint az „(a|aa)+”)."), "index.kereses.regex_tul_sokaig_futott_idokorlat", {"idokorlat": idokorlat}) from None
    finally:
        _hatar.ertek = None


def _keres(c, q: str, e, limit: int, kornyezet: int = 0) -> dict:
    fts = _fts(e)
    if fts:
        jeloltek = c.execute("SELECT f.id, f.ut, f.nev, bm25(fts, 2.0, 10.0, 1.0), f.tipus FROM fts JOIN fajl f "
                             "ON f.id = fts.rowid WHERE fts MATCH ? AND f.torolve IS NULL ORDER BY bm25(fts, 2.0, 10.0, 1.0) "
                             "LIMIT ?", (fts, MAX_JELOLT)).fetchall()
    else:
        jeloltek = c.execute("SELECT id, ut, nev, 0, tipus FROM fajl WHERE torolve IS NULL ORDER BY ut").fetchall()
    cimkek: dict[int, set] = {}
    if _van(e, "tag"):
        for fid, kis in c.execute("SELECT fajl_id, kis FROM cimke"):
            cimkek.setdefault(fid, set()).add(kis)
    minták: dict = {}
    talalatok, osszes, legalabb = [], 0, len(jeloltek) >= MAX_JELOLT
    hatar = getattr(_hatar, "ertek", None)
    for fid, ut, nev, pont, tipus in jeloltek:
        if len(talalatok) >= limit or (hatar is not None and time.monotonic() >= hatar):
            legalabb = True                 # korai leállás a `limit`-nél, vagy lejárt az időkeret (T152): az `osszes` alsó korlát
            break
        d = _Dok(c, fid, ut, nev, cimkek)
        ok, spanok = _kiertekel(e, d, minták)
        if not ok:
            continue
        osszes += 1
        t = {"ut": ut, "pont": round(-pont, 4) if pont else 0,
             "talalatok": _sorok(d.tartalom, spanok, kornyezet=kornyezet) if spanok else []}
        if tipus in MEDIA_TIPUSOK:
            t["tipus"] = tipus
        talalatok.append(t)
    if fts:
        uj, tobb = _media(c, e, fts, minták, cimkek, talalatok, kornyezet, hatar)
        osszes += uj
        legalabb |= tobb
        if uj:
            talalatok.sort(key=lambda t: -t["pont"])            # stabil: a jegyzetek bm25-sorrendje megmarad
            if len(talalatok) > limit:
                del talalatok[limit:]
                legalabb = True
    return {"q": q, "osszes": osszes, "legalabb": legalabb, "talalatok": talalatok}


def _media(c, e, fts: str, minták: dict, cimkek: dict, talalatok: list, kornyezet: int, hatar) -> tuple[int, bool]:
    """C25c: a PDF-lapok és a feliratablakok (`fts_szakasz`) találatai, fájlonként összevonva a `talalatok`-ba (a név szerinti
    találatba is). A kérdés a szakaszon (lapon, ablakon) belül teljesül; a `path:`/`file:` a fájlra szűr. A fájl pontja a legjobb
    szakaszáé, `MEDIA_SULY`-lyal; a sor `sor`-a a fájl egész szövegében, mellette az `oldal` vagy a mondat `mp`-je.
    → (új fájlok száma, korai leállás)."""
    try:
        sorok = c.execute("SELECT s.fajl_id, s.ertek, s.sor_kezd, s.idok, f.ut, f.nev, f.tipus, fts_szakasz.tartalom, "
                          "bm25(fts_szakasz) FROM fts_szakasz JOIN szakasz s ON s.id = fts_szakasz.rowid "
                          "JOIN fajl f ON f.id = s.fajl_id WHERE fts_szakasz MATCH ? AND f.torolve IS NULL "
                          "ORDER BY bm25(fts_szakasz) LIMIT ?", (fts, MAX_JELOLT)).fetchall()
    except sqlite3.OperationalError:            # régi (4-es migráció előtti) olvasó-séma: nincs média-szöveg
        return 0, False
    tobb = len(sorok) >= MAX_JELOLT
    fajlok = {t["ut"]: t for t in talalatok}
    uj = 0
    for fid, ertek, sor_kezd, idok, ut, nev, tipus, szoveg, pont in sorok:
        if hatar is not None and time.monotonic() >= hatar:
            return uj, True
        d = _Dok(c, fid, ut, nev, cimkek, szoveg, media=True)
        ok, spanok = _kiertekel(e, d, minták)
        if not ok:
            continue
        t = fajlok.get(ut)
        if t is None:
            t = fajlok[ut] = {"ut": ut, "pont": round(-pont * MEDIA_SULY, 4), "talalatok": [], "tipus": tipus}
            talalatok.append(t)
            uj += 1
        else:
            t["tipus"] = tipus
            t["pont"] = max(t["pont"], round(-pont * MEDIA_SULY, 4))
        hely = MAX_SOR - len(t["talalatok"])
        if hely <= 0 or not spanok:
            continue
        idolista = json.loads(idok) if idok else None
        for h in _sorok(szoveg, spanok, hely, kornyezet):
            helyi = h["sor"]
            h["sor"] = sor_kezd + helyi - 1
            if tipus == "pdf":
                h["oldal"] = int(ertek)
            elif idolista and helyi <= len(idolista):
                h["mp"] = idolista[helyi - 1]
            t["talalatok"].append(h)
    return uj, tobb


# ================================================================ említések

_WIKI_TELJES = re.compile(r"!?\[\[[^\]]*\]\]")


def emlites_talalatok(tartalom: str, mintak: list, max_db: int = 50) -> list[dict]:
    """A nevek előfordulásai a szövegben: kód, képlet, frontmatter és link (wiki, md) nélkül — a linkek
    maszkjával (`maszk.link_maszk`)."""
    m = link_maszk(tartalom)
    fm = FM_RE.match(m)
    if fm:
        m = re.sub(r"[^\n]", " ", m[:fm.end()]) + m[fm.end():]
    for rx in (_WIKI_TELJES, MD_RE):
        m = rx.sub(lambda x: re.sub(r"[^\n]", " ", x.group(0)), m)
    spanok = sorted({x.span() for rx in mintak for x in rx.finditer(m)})
    return _sorok(tartalom, spanok, max_db)
