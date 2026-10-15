"""A `.base` fájlok és a ```` ```base ```` blokkok hivatkozásai az átnevezéshez (C12, a terv 11. lépése).

Az átnevezés (`core/atnevezes.py`) innen kapja, mit kell átírni a Bases-szövegekben, és mit nem tud átírni (a
kifejezések szövegében álló hivatkozások a jegyzetlinkekkel azonos szabályt követnek: `core/index/feloldas.py`,
L42; itt saját feloldás nincs).

**Mi hivatkozás** (a kifejezés-nyelv `kifejezes.py`-beli szintaxisfáján, a szűrők, a `formulas` és a `summaries`
szövegeiben):

- *link-típusú hely*: a `link(…)`, `file(…)` első argumentuma, a `.hasLink(…)` és `.linksTo(…)` argumentuma, ha
  szöveg-literál; plusz minden szöveg-literálban álló `[[cél…]]`. Átírás csak ha a cél előtte feloldódott, és
  utána nem a várt fájlra oldódna (az *elrablást* is fogja); az új szöveget a hívó adja (`uj_cel`, a jegyzetlinkek
  stílusőrző szabályával);
- *út-literál* (szűk fehérlista): `file.path == "P"` / `!=` (ha a `P` fájl mozog), `file.inFolder("P")`,
  `file.folder == "P"` (mappa mozgatásakor: pontos egyezés vagy `régi/` előtag);
- **soha nem íródik át**, csak figyelmeztetésként látszik: a `file.name`, `file.basename` (és a lánc: `.lower()`
  stb.) egyenlősége, a `startsWith/contains/endsWith` szöveg-literállal, és a regex-literál a fájl nevén, útján,
  mappáján — az átnevezés után másként szűrhet.

**Technika**: a YAML skalár-csomópontjának helye (`yaml.compose`) adja, hol áll a kifejezés; a literál a
kifejezésben cserélődik, és a skalár újra kiíródik (a stílus megtartásával: sima, `'…'`, `"…"`; ha a stílus az
új értéket nem tartaná, idézőjeles alak jön). **Minden más bájt érintetlen** (megjegyzések, kulcssorrend,
behúzás). Blokk-skalárban (`|`, `>`) álló érintett hivatkozás **blokkoló**. Az átírás után a szöveg újra
kivonódik, és a hivatkozások listájának a vártnak kell lennie, különben blokkoló.

A ```` ```base ```` blokk törzse a jegyzet szövegének egy darabja (idézetben a `> ` előtagok nélkül, a pozíciók
visszaképezve); a CRLF megmarad (a pozíciók a nyers szövegre mutatnak).
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

import yaml

from ..index import linkek
from ..index.elemzo import _Betolto
from ..index.feloldas import kis, nfc
from ..index.maszk import FM_RE, keritesek
from .ertekek import FutasHiba, Regex
from .kifejezes import (Binaris, Hivas, Index, KifejezesHiba, Nev, RegexL, Szoveg, Tag, bejar, elemez)

_STR = "tag:yaml.org,2002:str"
_TULAJDONSAGOK = ("name", "basename", "path", "folder")
_TUL_NEV = {"name": "neve (a kiterjesztéssel)", "basename": "alapneve", "path": "útja", "folder": "mappája"}
_NEV_MUVELETEK = ("startsWith", "contains", "endsWith")

_BAZIS_NYITO = re.compile(r"(?:`{3,}|~{3,})[ \t]*base", re.I)       # gyors előszűrő: van-e egyáltalán ilyen blokk
_BAZIS_NYITO_B = re.compile(rb"(?:`{3,}|~{3,})[ \t]*base", re.I)
_KERITES_JEL = re.compile(r"[ \t]*(?:>[ \t]*)*(?:(?:[-*+]|\d{1,9}[.)])[ \t]+)?(`{3,}|~{3,})")
_ELOTAG = re.compile(r"[ \t]*(?:>[ \t]*)*")
_IDEZET_JEL = re.compile(r"[ \t]*>[ \t]?")
_WIKI = re.compile(r"!?\[\[([^\]|#]*)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
_KULSO = re.compile(r"^(?:[a-z][a-z0-9+.-]*://|mailto:)", re.I)


# ================================================================ adatalakok

@dataclass(eq=False)
class Skalar:
    """Egy kifejezést tartalmazó YAML-skalár."""
    kezd: int                   # a skalár forrásszövege a teljes szövegben (nyers eltolás)
    veg: int
    ertek: str                  # a kifejezés (a skalár értéke)
    stilus: str | None          # None (sima) | `'` | `"` | `|` | `>`
    folyam: bool                # folyam-gyűjteményben áll (`[…]`, `{…}`)
    atirhato: bool              # a forrásszöveg-szakasz egyértelműen az értéket adja (nincs címke, horgony)
    hely: str                   # `filters`, `views[0].filters.and[1]`, `formulas.x`, `summaries.y`


@dataclass(eq=False)
class Hiv:
    """Egy hivatkozás vagy figyelmeztetést érdemlő hely egy kifejezésben."""
    fajta: str                  # link | ut | mappa | figy
    skalar: Skalar
    lit_kezd: int               # a szöveg-literál a kifejezésben (az idézőjelekkel)
    lit_veg: int
    lit_ertek: str              # a literál dekódolt értéke
    idezo: str
    kezd: int                   # a cserélendő szakasz a `lit_ertek`-ben (link: a cél; út, mappa: az egész érték)
    veg: int
    cel: str = ""               # a szakasz szövege (figy: a literál értéke vagy a regex-minta)
    muvelet: str = ""           # figy: `==`, `!=`, startsWith, contains, endsWith, regex
    tul: str = ""               # figy: name | basename | path | folder
    zaszlok: str = ""           # figy: a regex zászlói


@dataclass
class Eredmeny:
    cserek: list = field(default_factory=list)          # [(kezd, veg, új szöveg)] a nyers szövegben
    db: int = 0                                         # a módosuló hivatkozások (literál-helyek) száma
    blokkolok: list = field(default_factory=list)
    figyelmeztetesek: list = field(default_factory=list)


# ================================================================ YAML: hol állnak a kifejezések

def _szuro(n, hely: str, folyam: bool, ki: list) -> None:
    """A `filters` részfa skalárjai: egy kifejezés, lista (implicit `and`), vagy `and`/`or`/`not` szerkezet."""
    if isinstance(n, yaml.ScalarNode):
        ki.append((hely, n, folyam))
    elif isinstance(n, yaml.SequenceNode):
        f = folyam or bool(n.flow_style)
        for i, e in enumerate(n.value):
            _szuro(e, f"{hely}[{i}]", f, ki)
    elif isinstance(n, yaml.MappingNode):
        f = folyam or bool(n.flow_style)
        for k, v in n.value:
            if isinstance(k, yaml.ScalarNode) and k.value in ("and", "or", "not"):
                _szuro(v, f"{hely}.{k.value}", f, ki)


def _kifejezes_csomopontok(gyoker: yaml.MappingNode) -> list[tuple[str, yaml.ScalarNode, bool]]:
    """[(hely, skalár-csomópont, folyam)] a `.base` összes kifejezés-szövegére (dokumentum-sorrendben)."""
    ki: list = []
    ff = bool(gyoker.flow_style)
    for k, v in gyoker.value:
        kn = k.value if isinstance(k, yaml.ScalarNode) else None
        if kn == "filters":
            _szuro(v, "filters", ff, ki)
        elif kn in ("formulas", "summaries") and isinstance(v, yaml.MappingNode):
            for ak, av in v.value:
                if isinstance(ak, yaml.ScalarNode) and isinstance(av, yaml.ScalarNode):
                    ki.append((f"{kn}.{ak.value}", av, ff or bool(v.flow_style)))
        elif kn == "views" and isinstance(v, yaml.SequenceNode):
            for i, nezet in enumerate(v.value):
                if isinstance(nezet, yaml.MappingNode):
                    for nk, nv in nezet.value:
                        if isinstance(nk, yaml.ScalarNode) and nk.value == "filters":
                            _szuro(nv, f"views[{i}].filters", ff or bool(v.flow_style) or bool(nezet.flow_style), ki)
    return ki


def _skalar_atirhato(szoveg: str, n: yaml.ScalarNode) -> bool:
    """A skalár forrásszövege egyértelműen az értéket adja: idézőjeles alaknál az idézőjelek határolják, sima alaknál
    a szakasz önállóan olvasva ugyanazt adja (címke vagy horgony esetén nem)."""
    if n.style in ("|", ">"):
        return False
    forras = szoveg[n.start_mark.index:n.end_mark.index]
    if n.style in ("'", '"'):
        return len(forras) >= 2 and forras[0] == n.style and forras[-1] == n.style
    if not forras or forras[0] in "&!*":
        return False
    try:
        m = yaml.compose(forras, Loader=_Betolto)
    except yaml.YAMLError:
        return False
    return isinstance(m, yaml.ScalarNode) and m.value == n.value


# ================================================================ AST: a hivatkozások

def _file_tul(c) -> str | None:
    """`file.<tul>` közvetlenül."""
    if isinstance(c, Tag) and isinstance(c.obj, Nev) and c.obj.nev == "file":
        return c.nev
    return None


def _file_tul_lanc(c) -> str | None:
    """A lánc gyökere `file.<tul>` (`file.name.lower()`, `file.path.split("/")[0]` is), és a tulajdonság a fehérlistán."""
    while True:
        t = _file_tul(c)
        if t is not None:
            return t if t in _TULAJDONSAGOK else None
        if isinstance(c, (Tag, Index)):
            c = c.obj
        elif isinstance(c, Hivas):
            c = c.fn
        else:
            return None


def _link_szakaszok(ertek: str, link_hely: bool) -> list[tuple[int, int]]:
    """A cél-szakaszok egy szöveg-literál dekódolt értékében: a `[[cél…]]`-k céljai; ha nincs ilyen és a literál
    link-típusú helyen áll (`link(…)`, `hasLink(…)`), maga a (`#`/`|` előtti) szöveg."""
    ki = []
    for m in _WIKI.finditer(ertek):
        a, b = m.start(1), m.end(1)
        if b > a and ertek[b - 1] == "\\":
            b -= 1                                      # a táblázatbeli `\|` visszapere az elválasztóé
        if ertek[a:b].strip():
            ki.append((a, b))
    if ki or not link_hely:
        return ki
    if not ertek.strip() or _KULSO.match(ertek.strip()):
        return []
    vegek = [i for i in (ertek.find("#"), ertek.find("|")) if i >= 0]
    return [(0, min(vegek) if vegek else len(ertek))]


def _hivek(skalar: Skalar, csomo) -> list[Hiv]:
    osztaly: dict[int, tuple] = {}              # id(Szoveg) → ("link",) | ("ut",) | ("mappa",) | ("figy", művelet, tul)
    szovegek: list[Szoveg] = []
    figyek: list[Hiv] = []

    def figy_szoveg(sz: Szoveg, muvelet: str, tul: str) -> None:
        osztaly[id(sz)] = ("figy", muvelet, tul)

    for c in bejar(csomo):
        if isinstance(c, Szoveg):
            szovegek.append(c)
        elif isinstance(c, Hivas):
            f, elso = c.fn, (c.argok[0] if c.argok else None)
            if isinstance(f, Nev) and f.nev in ("link", "file") and isinstance(elso, Szoveg):
                osztaly[id(elso)] = ("link",)
            elif isinstance(f, Tag):
                if f.nev in ("hasLink", "linksTo") and isinstance(elso, Szoveg):
                    osztaly[id(elso)] = ("link",)
                elif f.nev == "inFolder" and isinstance(f.obj, Nev) and f.obj.nev == "file" and isinstance(elso, Szoveg):
                    osztaly[id(elso)] = ("mappa",)
                elif f.nev in _NEV_MUVELETEK and isinstance(elso, Szoveg) and _file_tul_lanc(f.obj):
                    figy_szoveg(elso, f.nev, _file_tul_lanc(f.obj))
                else:
                    tul = _file_tul_lanc(f.obj)
                    if tul:                                         # `file.name.matches(/…/)`, `.replace(/…/, …)`
                        for a in c.argok:
                            if isinstance(a, RegexL):
                                figyek.append(Hiv("figy", skalar, 0, 0, "", "", 0, 0, a.minta, "regex", tul, a.zaszlok))
                    elif isinstance(f.obj, RegexL):                 # `/…/.matches(file.name)`
                        for a in c.argok:
                            t2 = _file_tul_lanc(a)
                            if t2:
                                figyek.append(Hiv("figy", skalar, 0, 0, "", "", 0, 0, f.obj.minta, "regex", t2,
                                                  f.obj.zaszlok))
        elif isinstance(c, Binaris) and c.muvelet in ("==", "!="):
            for oldal, masik in ((c.bal, c.jobb), (c.jobb, c.bal)):
                if not isinstance(masik, Szoveg):
                    continue
                kozvetlen = _file_tul(oldal)
                if kozvetlen == "path":
                    osztaly[id(masik)] = ("ut",)
                elif kozvetlen == "folder":
                    osztaly[id(masik)] = ("mappa",)
                elif _file_tul_lanc(oldal):
                    figy_szoveg(masik, c.muvelet, _file_tul_lanc(oldal))
    ki: list[Hiv] = list(figyek)
    for sz in szovegek:
        o = osztaly.get(id(sz))
        kozos = (skalar, sz.kezd, sz.veg, sz.ertek, sz.idezo)
        if o is None or o[0] == "link":
            for a, b in _link_szakaszok(sz.ertek, o is not None):
                ki.append(Hiv("link", *kozos, a, b, sz.ertek[a:b]))
        elif o[0] in ("ut", "mappa"):
            ki.append(Hiv(o[0], *kozos, 0, len(sz.ertek), sz.ertek))
        else:
            ki.append(Hiv("figy", *kozos, 0, len(sz.ertek), sz.ertek, o[1], o[2]))
    ki.sort(key=lambda h: (h.skalar.kezd, h.lit_kezd, h.kezd))
    return ki


# ================================================================ kivonás

def _yaml_hivek(t: str, poz_kezd, poz_veg) -> list[Hiv]:
    """Egy YAML-szöveg hivatkozásai. `poz_kezd(i)` / `poz_veg(i)`: a `t` `i`. karakterének / kizárólagos végének
    helye a teljes (nyers) szövegben."""
    try:
        gyoker = yaml.compose(t, Loader=_Betolto)
    except (yaml.YAMLError, RecursionError):
        return []
    if not isinstance(gyoker, yaml.MappingNode):
        return []
    ki: list[Hiv] = []
    latott: set[int] = set()
    for hely, n, folyam in _kifejezes_csomopontok(gyoker):
        if id(n) in latott or n.tag != _STR or not n.value.strip():
            continue
        latott.add(id(n))
        try:
            csomo = elemez(n.value)
        except KifejezesHiba:
            continue
        a, b = n.start_mark.index, n.end_mark.index
        if b <= a:
            continue
        sk = Skalar(poz_kezd(a), poz_veg(b), n.value, n.style, folyam, _skalar_atirhato(t, n), hely)
        ki += _hivek(sk, csomo)
    return ki


def _blokk_torzsek(norm: str) -> list[tuple[str, list[int]]]:
    """A ```` ```base ```` blokkok YAML-törzse: [(szöveg, tm)] — a `tm[i]` a törzs `i`. karakterének helye a
    normalizált jegyzetben. Idézetben (callout) álló blokknál a sorok `> ` előtagja kimarad."""
    if not _BAZIS_NYITO.search(norm):
        return []
    fm = FM_RE.match(norm)
    fm_veg = fm.end() if fm else 0
    ki = []
    for a, b, info in keritesek(norm[fm_veg:]):
        if not info or info.split()[0].lower() != "base":
            continue
        kezd = fm_veg + a
        sorok = norm[kezd:fm_veg + b].split("\n")
        nyito = sorok[0]
        mj = _KERITES_JEL.match(nyito)
        jel, hossz = (mj.group(1)[0], len(mj.group(1))) if mj else ("`", 3)
        zart = False
        if len(sorok) >= 2:
            mag = sorok[-1][_ELOTAG.match(sorok[-1]).end():].rstrip(" \t")
            zart = len(mag) >= hossz and mag == jel * len(mag)
        torzs = sorok[1:-1] if zart else sorok[1:]
        idezet = _ELOTAG.match(nyito).group(0).count(">")
        poz = kezd + len(nyito) + 1
        reszek, tm = [], []
        for sor in torzs:
            k = 0
            for _ in range(idezet):
                mm = _IDEZET_JEL.match(sor, k)
                if not mm:
                    break
                k = mm.end()
            reszek.append(sor[k:] + "\n")
            tm.extend(range(poz + k, poz + len(sor)))
            tm.append(poz + len(sor))
            poz += len(sor) + 1
        t = "".join(reszek)
        if t.strip():
            tm.append(poz)
            ki.append((t, tm))
    return ki


def kivon(szoveg: str, fajta: str) -> list[Hiv]:
    """A szöveg hivatkozásai dokumentum-sorrendben. `fajta`: `base` (egy `.base` fájl szövege) | `md` (egy jegyzet:
    a ```` ```base ```` blokkjai). A szöveg a **nyers** (CRLF-es, `surrogateescape`-dekódolt) szöveg; a pozíciók
    arra mutatnak."""
    if fajta == "base":
        return _yaml_hivek(szoveg, lambda i: i, lambda i: i)
    if fajta != "md" or not _BAZIS_NYITO.search(szoveg):
        return []
    norm, terkep = linkek.normalizalt(szoveg)
    ki: list[Hiv] = []
    for t, tm in _blokk_torzsek(norm):
        ki += _yaml_hivek(t, lambda i, tm=tm: terkep[tm[i]], lambda i, tm=tm: terkep[tm[i - 1]] + 1)
    return ki


def _fajta(rp: str) -> str | None:
    low = rp.lower()
    return "base" if low.endswith(".base") else "md" if low.endswith(".md") else None


def celok(rp: str, bajtok: bytes) -> list[str]:
    """A referencia-próba (`feloldas.hivatkozasok(…, tovabbi=)`) kiegészítése: a `.base` fájl vagy a jegyzet
    ```` ```base ```` blokkjainak link-céljai a szövegsorrendben (a feloldó ugyanúgy oldja fel őket, mint a
    jegyzetlinkeket)."""
    fajta = _fajta(rp)
    if fajta is None or (fajta == "md" and not _BAZIS_NYITO_B.search(bajtok)):
        return []
    return [h.cel.strip() for h in kivon(linkek.dekodol(bajtok), fajta) if h.fajta == "link"]


# ================================================================ átírás

def _csere(s: str, cserek: list[tuple[int, int, str]]) -> str:
    ki, poz = [], 0
    for kezd, veg, uj in sorted(cserek):
        ki.append(s[poz:kezd])
        ki.append(uj)
        poz = veg
    ki.append(s[poz:])
    return "".join(ki)


def _literal(ertek: str, idezo: str) -> str:
    """Szöveg-literál a kifejezés-nyelvben (`kifejezes.py` tokenizálója olvassa vissza)."""
    ki = [idezo]
    for c in ertek:
        if c == "\\":
            ki.append("\\\\")
        elif c == idezo:
            ki.append("\\" + c)
        elif c == "\n":
            ki.append("\\n")
        elif c == "\r":
            ki.append("\\r")
        elif c == "\t":
            ki.append("\\t")
        else:
            ki.append(c)
    ki.append(idezo)
    return "".join(ki)


def _dupla(ertek: str) -> str:
    """Idézőjeles YAML-skalár (a JSON-escape YAML-kompatibilis; a YAML-sortörésnek számító karakterek escape-elve)."""
    s = json.dumps(ertek, ensure_ascii=False)
    return s.replace("\x85", "\\x85").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def _skalar_rendben(jelolt: str, ertek: str, folyam: bool) -> bool:
    """A jelölt skalár-szöveg minden környezetben (blokk-leképezés és blokk-lista, vagy folyam) pontosan az `ertek`
    szöveget adja."""
    kornyezetek = ("[" + jelolt + "]", "{x: " + jelolt + "}") if folyam else ("x: " + jelolt, "- " + jelolt)
    for k in kornyezetek:
        try:
            n = yaml.compose(k, Loader=_Betolto)
        except yaml.YAMLError:
            return False
        if isinstance(n, yaml.MappingNode) and len(n.value) == 1:
            sz = n.value[0][1]
        elif isinstance(n, yaml.SequenceNode) and len(n.value) == 1:
            sz = n.value[0]
        else:
            return False
        if not (isinstance(sz, yaml.ScalarNode) and sz.value == ertek and sz.tag == _STR):
            return False
    return True


def _skalar_ki(ertek: str, stilus: str | None, folyam: bool) -> str | None:
    """Az új skalár forrásszövege: az eredeti stílus megtartásával; ha az az új értéket nem tartaná, a következő
    (sima → `'…'` → `"…"`). Mindig egysoros. `None`, ha egyik sem olvasható vissza pontosan."""
    jeloltek = []
    if stilus is None and not folyam and "\n" not in ertek:
        jeloltek.append(ertek)
    if stilus in (None, "'") and "\n" not in ertek:
        jeloltek.append("'" + ertek.replace("'", "''") + "'")
    jeloltek.append(_dupla(ertek))
    for j in jeloltek:
        if _skalar_rendben(j, ertek, folyam):
            return j
    return None


def _ertek(tul: str, ut: str) -> str:
    nev = ut.rsplit("/", 1)[-1]
    if tul == "name":
        return nev
    if tul == "basename":
        return os.path.splitext(nev)[0]
    if tul == "path":
        return ut
    return ut.rsplit("/", 1)[0] if "/" in ut else ""


def _egyezik(h: Hiv, ut: str, lassu: set | None = None) -> bool | None:
    """A figyelmeztetést érdemlő kifejezés-rész illik-e erre az útra (a fájl névére, alapnevére, útjára, mappájára).
    A regex a Bases saját, időkorlátos motorjával fut (`ertekek.Regex`: `regex` csomag, `concurrent=True`; T040 — a stdlib `re`
    a GIL-t fogva percekig futhatott). `None`: nem eldönthető (a minta nem fordítható, vagy időtúllépett) — a hívó ezt
    óvatosan „érintett”-nek veszi. `lassu`: a tervenként már időtúllépett minták: egy 1000 fájlos mappa-mozgatás mintánként
    egyszer fizeti meg az időkorlátot, nem fájlonként."""
    v = _ertek(h.tul, nfc(ut))
    if h.muvelet == "regex":
        kulcs = (h.cel, h.zaszlok)
        if lassu is not None and kulcs in lassu:
            return None
        try:
            return Regex(h.cel, h.zaszlok).keres(v) is not None
        except FutasHiba:
            if lassu is not None:
                lassu.add(kulcs)
            return None
    v, l = v.casefold(), nfc(h.cel).casefold()
    if h.muvelet in ("==", "!="):
        return v == l
    if h.muvelet == "startsWith":
        return v.startswith(l)
    if h.muvelet == "endsWith":
        return v.endswith(l)
    return l in v


def _figyelmeztetesek(hivek: list[Hiv], forras: str, lek: dict[str, str]) -> list[dict]:
    ki, latott, lassu = [], set(), set()
    for h in hivek:
        if h.fajta != "figy":
            continue
        kulcs = (h.skalar.hely, h.tul, h.muvelet, h.cel)
        if kulcs in latott:
            continue
        erintett = []
        for r, u in lek.items():
            if r == u:
                continue
            a, b = _egyezik(h, r, lassu), _egyezik(h, u, lassu)
            if a is None or b is None or (a and not b):          # nem eldönthető: óvatosan érintett
                erintett.append(r)
        if not erintett:
            continue
        latott.add(kulcs)
        mit = f"a /{h.cel}/ mintára" if h.muvelet == "regex" else f"„{h.cel}” szövegre ({h.muvelet})"
        pl = ", ".join(erintett[:3]) + (f" (+{len(erintett) - 3})" if len(erintett) > 3 else "")
        ki.append({"ut": forras, "hely": h.skalar.hely, "kifejezes": h.skalar.ertek[:200],
                   "uzenet": f"{forras}: a(z) {h.skalar.hely} kifejezése a fájl {_TUL_NEV[h.tul]} szerint szűr, {mit}; "
                             f"az átnevezés után másként viselkedhet, ezt nem írom át. Érintett: {pl}."})
    return ki


def _link_tobbertelmu(er: "Eredmeny", h: Hiv, t: str, vegso: str, forras: str, s2: str, lek: dict[str, str], fo_u,
                      tobb_e: bool, latott: set) -> None:
    """T126 (C29.8; a K11 döntéséig figyelmeztetés, nem blokkoló): a Bases a `link("X")`-et a SOR fájljának mappájából
    oldja fel (`fuggvenyek._link_keszit`), az átnevezés-terv viszont a `.base` (vagy a blokkot hordozó jegyzet) útjából.
    Ha a név többértelmű (az átnevezés előtt, vagy a végső szöveggel utána), és ugyanilyen nevű fájl átnevezkedik vagy
    mozog, a más mappában álló sorok másik jegyzetre oldódhatnak: a nézet sorai csendben megváltozhatnak."""
    if not (tobb_e or fo_u.resolve(vegso, s2)[2]):
        return
    alap = kis(os.path.basename(t))
    erintett = [r for r, u in lek.items() if alap in (kis(os.path.basename(r)), kis(os.path.basename(u)))]
    kulcs = (h.skalar.hely, h.cel)
    if not erintett or kulcs in latott:
        return
    latott.add(kulcs)
    pl = ", ".join(erintett[:3]) + (f" (+{len(erintett) - 3})" if len(erintett) > 3 else "")
    er.figyelmeztetesek.append({
        "ut": forras, "hely": h.skalar.hely, "kifejezes": h.skalar.ertek[:200],
        "uzenet": f"{forras}: a(z) {h.skalar.hely} kifejezésében a link(\"{h.cel.strip()}\") többértelmű: a Bases soronként a sor "
                  f"fájljának mappájából old fel, az átnevezés-terv a {forras} útjából — az átnevezés után egyes sorok másik "
                  f"jegyzetre oldódhatnak, és a nézet sorai változhatnak (a Bases link() szemantikájáról a K11 dönt). "
                  f"Érintett: {pl}."})


def cserek_keszit(szoveg: str, fajta: str, forras: str, s2: str, lek: dict[str, str], fo_e, fo_u, uj_cel,
                  mappa: tuple[str, str] | None = None) -> Eredmeny:
    """Az átnevezés által kért cserék egy `.base` fájlban (`fajta` `base`) vagy egy jegyzet ```` ```base ````
    blokkjaiban (`md`).

    `forras`: a fájl útja az átnevezés előtt, `s2` utána; `lek`: régi → új út minden mozgó fájlra; `fo_e` / `fo_u`: a
    feloldó az átnevezés előtti / utáni fájlhalmazon; `uj_cel(cel, vart) → str | None`: a link új cél-szövege (a
    jegyzetlinkek stílusőrző szabálya, a feloldóval ellenőrizve); `mappa`: (régi, új) mappaút, ha mappát mozgatunk.
    → `Eredmeny`: a cserék a nyers szövegben, a blokkolók és a figyelmeztetések."""
    er = Eredmeny()
    hivek = kivon(szoveg, fajta)
    if not hivek:
        return er
    er.figyelmeztetesek = _figyelmeztetesek(hivek, forras, lek)
    uj: dict[int, str] = {}                                    # id(Hiv) → az új szakasz-szöveg
    link_figy: set = set()                                     # (hely, cél): a többértelmű link figyelmeztetése egyszer
    for h in hivek:
        if h.fajta == "link":
            cel = h.cel
            t, _, tobb_e = fo_e.resolve(cel, forras)
            if t is None:
                continue
            vart = lek.get(t, t)
            vegso = cel                                         # a hivatkozás szövege az átnevezés után
            if fo_u.resolve(cel, s2)[0] != vart:
                j = uj_cel(cel, vart)
                if j is None:
                    er.blokkolok.append(f"{forras}: a(z) „{cel.strip()}” hivatkozás ({h.skalar.hely}) nem írható át egyértelműen")
                    continue
                pre, _, post = linkek.cel_resz(cel)
                uj[id(h)] = vegso = pre + j + post
            _link_tobbertelmu(er, h, t, vegso, forras, s2, lek, fo_u, tobb_e, link_figy)
        elif h.fajta == "ut":
            k = nfc(h.cel)
            if lek.get(k, k) != k:
                uj[id(h)] = lek[k]
        elif h.fajta == "mappa" and mappa is not None:
            m = re.match(r"^([\s/]*)(.*?)([\s/]*)$", nfc(h.cel), re.S)
            p = m.group(2)
            if p == mappa[0] or p.startswith(mappa[0] + "/"):
                uj[id(h)] = m.group(1) + mappa[1] + p[len(mappa[0]):] + m.group(3)
    csoportok: dict[int, tuple[Skalar, list[Hiv]]] = {}
    for h in hivek:
        if id(h) in uj:
            csoportok.setdefault(id(h.skalar), (h.skalar, []))[1].append(h)
    for sk, lista in csoportok.values():
        kif = sk.ertek if len(sk.ertek) <= 80 else sk.ertek[:77] + "…"
        if sk.stilus in ("|", ">"):
            er.blokkolok.append(f"{forras}: a(z) „{kif}” kifejezés ({sk.hely}) blokk-skalárban ({sk.stilus}) áll, a benne "
                                "lévő hivatkozás nem írható át egyértelműen — írd át kézzel.")
            continue
        if not sk.atirhato:
            er.blokkolok.append(f"{forras}: a(z) „{kif}” kifejezés ({sk.hely}) YAML-címkével vagy horgonnyal áll, a benne "
                                "lévő hivatkozás nem írható át egyértelműen — írd át kézzel.")
            continue
        literalok: dict[tuple[int, int], list[Hiv]] = {}
        for h in lista:
            literalok.setdefault((h.lit_kezd, h.lit_veg), []).append(h)
        lit_cserek = []
        for (lk, lv), hs in literalok.items():
            ertek = _csere(hs[0].lit_ertek, [(h.kezd, h.veg, uj[id(h)]) for h in hs])
            lit_cserek.append((lk, lv, _literal(ertek, hs[0].idezo)))
        uj_kif = _csere(sk.ertek, lit_cserek)
        szoveg_uj = _skalar_ki(uj_kif, sk.stilus, sk.folyam)
        if szoveg_uj is None:
            er.blokkolok.append(f"{forras}: a(z) „{kif}” kifejezés ({sk.hely}) nem írható át egyértelműen.")
            continue
        er.cserek.append((sk.kezd, sk.veg, szoveg_uj))
        er.db += len(lista)
    if er.cserek and not er.blokkolok:                         # ellenőrzés: az átírt szöveg hivatkozásai a vártak
        vart = [(h.fajta, uj.get(id(h), h.cel)) for h in hivek]
        van = [(h.fajta, h.cel) for h in kivon(_csere(szoveg, er.cserek), fajta)]
        if vart != van:
            er.blokkolok.append(f"{forras}: a Bases-kifejezések átírásának ellenőrzése sikertelen — nem írható át egyértelműen.")
            er.cserek, er.db = [], 0
    return er
