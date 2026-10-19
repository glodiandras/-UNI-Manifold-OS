"""Jegyzet- és canvas-elemző: frontmatter típusokkal, fejezetek, blokkok, linkek, címkék, feladatok,
képletek, kódblokkok. Tiszta függvények: szöveg be, `Jegyzet` ki; fájlt nem olvas.

Minden a közös maszk (`maszk.py`, C10.6) után: a kódban álló link, címke, feladat, fejezet nem számít, a
képletben álló link sem (L42; egy maszk mindenhol). A maszk a hosszt megtartja, így az eltolások az
eredeti szövegre mutatnak. A sorok 1-től, az oszlopok 0-tól számolnak, Python-karakterben (kódpont).

A linklista a gráf forrása is: a wikilink-rekordok célja pontosan a `feloldas.jegyzet_celok` listája
(ugyanabban a sorrendben), így a gráf és a backlink nem térhet el.
"""
from __future__ import annotations

import bisect
import json
import re
from dataclasses import asdict, dataclass, field

import yaml

from .feloldas import MD_RE, WIKI_RE, md_reszek
from .maszk import FM_RE, KEPLET_BLOKK as _KEPLET_BLOKK, KEPLET_SOR as _KEPLET_SOR, keritesek, link_maszk, maszkok, megjegyzes_nelkul
_FM_KULCS = re.compile(r"^([^\s#:\-][^:]*):")
_FEJEZET = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*$", re.M)
# setext fejezet (CommonMark): a címsor közvetlenül a `=`/`-` aláhúzás felett; nem címsor, ha a felső sor üres, ATX-címsor,
# listaelem, idézet vagy táblázatsor (akkor az aláhúzás vízszintes vonal) — a kódot és a frontmattert a `torzs` már takarja
# C33: a `([^\n]*\S[^\n]*)` soronként négyzetes visszalépést okozott (egy 500 karakteres bekezdés-sor ~250 000 lépés): az
# elemzés idejének ~90%-a ez volt (10 000 jegyzeten a hideg építés fele); a nem üres sort egy előretekintés biztosítja, a
# sor egyetlen `[^\n]+`-szal — ugyanazok az illeszkedések, lineáris időben
_SETEXT = re.compile(r"^(?![ \t]{0,3}(?:#{1,6}(?:[ \t]|$)|[-*+>|]|\d+[.)][ \t]))(?=[^\n]*\S)([^\n]+)\n[ \t]{0,3}(=+|-+)[ \t]*$", re.M)
_BLOKK = re.compile(r"\^(?<![^ \t\n]\^)([A-Za-z0-9-]+)[ \t]*$", re.M)   # a `^` előtt sorkezdet vagy szóköz
_LISTA = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]")
_FELADAT = re.compile(r"^([ \t]*)(?:[-*+]|\d+[.)])[ \t]+\[(.)\][ \t]+(.*)$", re.M)
_CIMKE = re.compile(r"#(?<!\S#)([\w/-]+)")
_DATUM = r"(\d{4}-\d{2}-\d{2})"
_EMOJI = {"📅": "hatarido", "⏳": "utemezve", "🛫": "kezdes", "✅": "kesz", "➕": "letrehozva", "❌": "torolve"}
_EMOJI_RE = re.compile("(" + "|".join(_EMOJI) + r")️?\s*" + _DATUM)
_DATAVIEW = {"due": "hatarido", "scheduled": "utemezve", "start": "kezdes", "completion": "kesz",
             "created": "letrehozva", "cancelled": "torolve"}
_DATAVIEW_RE = re.compile(r"\[(" + "|".join(_DATAVIEW) + r")::\s*" + _DATUM + r"[^\]]*\]")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$")
_TAGS_KULCS = re.compile(r"^tags?$", re.I)
_ALIAS_KULCS = re.compile(r"^alias(es)?$", re.I)
TIPUSOK = ("text", "multitext", "number", "checkbox", "date", "datetime", "tags", "aliases")


# ---------------------------------------------------------------- YAML (1.2-szerű)

class _Betolto(yaml.SafeLoader):
    """SafeLoader YAML 1.2-szerű skalárokkal: a dátum szöveg marad (a típust a mező adja), a `yes/no/on/off`
    nem bool, a `10:30` nem hatvanas szám, a `0x1F` nem egész — ahogy az Obsidian olvassa.

    **A core egyetlen YAML-betöltője** (frontmatter, `.base`, képletek, visszaolvasás-próba; C29.8, T041): a YAML-alias (`*x`)
    tiltott — egy kívülről érkező jegyzet „billion laughs” fája a memóriaőrt megkerülve kimeríthetné a gépet —, és a
    beágyazás mélysége korlátos (a `RecursionError` helyett értelmes hiba). A horgony (`&x`) önmagában inert, marad."""
    MAX_MELYSEG = 64
    _melyseg = 0

    def compose_node(self, parent, index):
        if self.check_event(yaml.events.AliasEvent):
            ev = self.peek_event()
            raise yaml.composer.ComposerError(None, None, f"a YAML-alias (*{ev.anchor}) nem megengedett", ev.start_mark)
        self._melyseg += 1
        try:
            if self._melyseg > self.MAX_MELYSEG:
                raise yaml.composer.ComposerError(None, None, f"a YAML legfeljebb {self.MAX_MELYSEG} szint mélyen "
                                                              "ágyazható egymásba", self.peek_event().start_mark)
            return super().compose_node(parent, index)
        finally:
            self._melyseg -= 1


_Betolto.yaml_implicit_resolvers = {
    k: [(tag, rx) for tag, rx in v if tag.rsplit(":", 1)[-1] not in ("timestamp", "bool", "int", "float")]
    for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()}
_Betolto.add_implicit_resolver("tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
                               list("tTfF"))
_Betolto.add_implicit_resolver("tag:yaml.org,2002:int", re.compile(r"^[-+]?[0-9]+$"), list("-+0123456789"))
_Betolto.add_implicit_resolver(
    "tag:yaml.org,2002:float",
    re.compile(r"^(?:[-+]?(?:\.[0-9]+|[0-9]+\.[0-9]*|[0-9]+)(?:[eE][-+]?[0-9]+)?|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$"),
    list("-+0123456789."))


class _EgyediBetolto(_Betolto):
    """A `_Betolto`, amely a **duplikált kulcsot** is hibának veszi (a PyYAML alapból az utolsót tartja): a tulajdonság-szerkesztő
    visszaolvasás-próbája ezt használja, hogy a sorbontó által nem ismert kulcsalak (`? kulcs`, escape-es idézett
    `"Sta\\x74us"`) ne hozhasson létre második kulcsot (T129)."""

    def construct_mapping(self, node, deep=False):
        self.flatten_mapping(node)
        latott = set()
        for kulcs_node, _ in node.value:
            k = self.construct_object(kulcs_node, deep=True)
            try:
                if k in latott:
                    raise yaml.constructor.ConstructorError("a tábla felépítése közben", node.start_mark,
                                                            f"duplikált kulcs: {k!r}", kulcs_node.start_mark)
                latott.add(k)
            except TypeError:
                pass                                   # nem hash-elhető kulcs: a szülő `construct_mapping` jelzi
        return super().construct_mapping(node, deep)


def _json_kompatibilis(x):
    if isinstance(x, dict):
        return {str(k): _json_kompatibilis(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_json_kompatibilis(v) for v in x]
    if isinstance(x, float) and (x != x or x in (float("inf"), float("-inf"))):
        return str(x)
    if x is None or isinstance(x, (str, int, float, bool)):
        return x
    return str(x)


# ---------------------------------------------------------------- adatalak

@dataclass
class Link:
    cel: str                        # a nyers gráf-cél (a `jegyzet_celok` / `canvas_celok` eleme)
    fajta: str                      # wiki | md | canvas_fajl | canvas_szoveg
    sor: int | None = None
    oszlop: int | None = None
    hossz: int | None = None
    alcel: str | None = None        # "Fejezet" vagy "^blokk" (a `#` utáni rész)
    alias: str | None = None
    beagyazas: bool = False
    tulajdonsag: str | None = None  # a frontmatter kulcsa, ha ott áll
    csomopont: str | None = None    # canvas-node azonosítója


@dataclass
class Tulajdonsag:
    kulcs: str
    ertek: object
    tipus: str
    ervenyes: bool = True           # az érték illik-e a (types.json-ban rögzített) típushoz


@dataclass
class Jegyzet:
    fm_nyers: str | None = None
    fm_hiba: str | None = None
    tulajdonsagok: list[Tulajdonsag] = field(default_factory=list)
    aliasok: list[str] = field(default_factory=list)
    fejezetek: list[dict] = field(default_factory=list)       # {szint, szoveg, sor}
    blokkok: list[dict] = field(default_factory=list)         # {azon, sor, kezdo_sor}
    linkek: list[Link] = field(default_factory=list)
    cimkek: list[dict] = field(default_factory=list)          # {cimke, forras: fm|szoveg, sor}
    feladatok: list[dict] = field(default_factory=list)       # {sor, allapot, szoveg, behuzas, datumok}
    kepletek: list[dict] = field(default_factory=list)        # {sor, kezd, veg, blokk, forras}
    kodblokkok: list[dict] = field(default_factory=list)      # {nyelv, sor_kezd, sor_veg}
    tartalom: str = ""                                        # a keresés szövege
    canvas_hiba: str | None = None

    def publikus(self) -> dict:
        return asdict(self)


class _Sorok:
    """Eltolás → (sor 1-től, oszlop 0-tól)."""

    def __init__(self, txt: str):
        self.kezdet = [0] + [m.end() for m in re.finditer("\n", txt)]

    def __call__(self, off: int) -> tuple[int, int]:
        i = bisect.bisect_right(self.kezdet, off) - 1
        return i + 1, off - self.kezdet[i]


# ---------------------------------------------------------------- frontmatter

def tipus_ertekbol(kulcs: str, ertek) -> str:
    if _TAGS_KULCS.match(kulcs):
        return "tags"
    if _ALIAS_KULCS.match(kulcs):
        return "aliases"
    if isinstance(ertek, bool):
        return "checkbox"
    if isinstance(ertek, (int, float)):
        return "number"
    if isinstance(ertek, list):
        return "multitext"
    if isinstance(ertek, str) and _DATE.match(ertek):
        return "date"
    if isinstance(ertek, str) and _DATETIME.match(ertek):
        return "datetime"
    if isinstance(ertek, dict):
        return "unknown"
    return "text"


def _illik(tipus: str, ertek) -> bool:
    if ertek is None:
        return True
    return {
        "checkbox": lambda v: isinstance(v, bool),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "date": lambda v: isinstance(v, str) and bool(_DATE.match(v)),
        "datetime": lambda v: isinstance(v, str) and bool(_DATETIME.match(v) or _DATE.match(v)),
        "multitext": lambda v: isinstance(v, (list, str)),
        "tags": lambda v: isinstance(v, (list, str)),
        "aliases": lambda v: isinstance(v, (list, str)),
        "text": lambda v: not isinstance(v, (list, dict)),
    }.get(tipus, lambda v: True)(ertek)


def _lista(ertek) -> list[str]:
    """Lista-értékű mező elemei; a szöveges érték vesszőnél, ha nincs vessző, szóköznél bomlik."""
    if ertek is None:
        return []
    if isinstance(ertek, list):
        return [str(x) for x in ertek if x is not None and str(x).strip()]
    s = str(ertek)
    return [x for x in re.split(r"," if "," in s else r"\s+", s) if x.strip()]


def _alias_szoveg(a) -> str:
    """Egy alias szövege: a szám, a logikai érték és a tört is szöveg (`aliases: [1984, true]` — T037; a `true` YAML-alakban)."""
    if isinstance(a, bool):
        return "true" if a else "false"
    return str(a).strip()


def frontmatter(fm_nyers: str | None, tipusok: dict | None = None,
                egyedi: bool = False) -> tuple[list[Tulajdonsag], str | None]:
    """A frontmatter tulajdonságai a sorrendjükben, típussal; a formai hiba szövegként (nem nyelődik el). `egyedi`: a
    duplikált kulcs is formai hiba (`_EgyediBetolto`; a tulajdonság-szerkesztő visszaolvasás-próbája, T129)."""
    if fm_nyers is None:
        return [], None
    try:
        d = yaml.load(fm_nyers, Loader=_EgyediBetolto if egyedi else _Betolto)
    except yaml.YAMLError as e:
        return [], " ".join(str(e).split())[:300]
    except RecursionError:                       # a mélységkorlát a betöltőben él; ez a végső háló (T037)
        return [], "a frontmatter túl mélyen egymásba ágyazott"
    if d is None:
        return [], None
    if not isinstance(d, dict):
        return [], "a frontmatter nem kulcs–érték párokból áll"
    out, tipusok = [], tipusok or {}
    for k, v in d.items():
        k, v = str(k), _json_kompatibilis(v)
        rogzitett = tipusok.get(k)
        t = rogzitett if rogzitett in TIPUSOK else tipus_ertekbol(k, v)
        out.append(Tulajdonsag(k, v, t, _illik(t, v)))
    return out, None


# ---------------------------------------------------------------- linkek

def _wiki_rekordok(maszk: str, eredeti: str, poz, fajta: str = "wiki") -> list[Link]:
    out = []
    for m in WIKI_RE.finditer(maszk):
        sor, osz = poz(m.start()) if poz else (None, None)
        zar = maszk.find("]]", m.end())
        uj_sor = maszk.find("\n", m.end())
        alcel = alias = None
        hossz = None
        if zar >= 0 and (uj_sor < 0 or zar < uj_sor):
            maradek = eredeti[m.end():zar]
            hossz = zar + 2 - m.start()
            if maradek.startswith("#"):
                alcel, _, a = maradek[1:].partition("|")
                alcel = alcel[:-1].rstrip() if alcel.endswith("\\") else alcel
                alias = a if _ else None
            elif maradek.startswith("|"):
                alias = maradek[1:]
        out.append(Link(cel=m.group(1), fajta=fajta, sor=sor, oszlop=osz, hossz=hossz,
                        alcel=alcel.strip() if alcel else None, alias=alias,
                        beagyazas=m.group(0).startswith("!")))
    return out


def _md_rekordok(maszk: str, poz) -> list[Link]:
    out = []
    for m in MD_RE.finditer(maszk):
        r = md_reszek(m.group(1))             # C31 (36. döntés): burok nélkül, URL-dekódolva; None: nem belső link
        if r is None:
            continue
        cel, alcel = r
        sor, osz = poz(m.start())
        szoveg = maszk[m.start() + 1:m.start(1) - 2]
        out.append(Link(cel=cel, fajta="md", sor=sor, oszlop=osz, hossz=m.end() - m.start(),
                        alcel=alcel or None, alias=szoveg or None,
                        beagyazas=m.start() > 0 and maszk[m.start() - 1] == "!"))
    return out


# ---------------------------------------------------------------- jegyzet

def _nyito(sor: str) -> bool:
    """Blokkot nyitó sor: listaelem, idézet, táblázatsor."""
    return bool(_LISTA.match(sor)) or sor.lstrip().startswith((">", "|"))


def _hatar(sor: str) -> bool:
    """Blokkot lezáró sor: üres, fejezet, kódkerítés."""
    s = sor.strip()
    return not s or s.startswith(("#", "```"))


_IDEZET_ELOTAG = re.compile(r"^(?:>[ \t]?)+")


def _blokk_eleje(sorok: list[str], sor: int) -> int:
    """A `sor`-t tartalmazó blokk első sora: az idézet vagy a táblázat első sora (a vele azonos jelű sorok összefüggő
    sora — T039: a PDF-kiemelés `> …` blokkjának beágyazása a kiemelt szöveggel együtt kell), a listaelem (az idézetben
    álló is egy elem), vagy a bekezdés eleje (fejezet és kerítés után)."""
    s = sorok[sor - 1].lstrip()
    jel = None
    if s.startswith(">") and not _LISTA.match(_IDEZET_ELOTAG.sub("", s)):
        jel = ">"
    elif s.startswith("|"):
        jel = "|"
    if jel:
        while sor > 1 and sorok[sor - 2].lstrip().startswith(jel):
            sor -= 1
        return sor
    while sor > 1 and not _nyito(sorok[sor - 1]) and not _hatar(sorok[sor - 2]):
        sor -= 1
    return sor


def elemez(txt: str, tipusok: dict | None = None) -> Jegyzet:
    """Egy `.md` elemzése. `txt`: a `feloldas.szoveg` szerinti szöveg (`\\n` sorvégek). `tipusok`: a vault
    `.obsidian/types.json` `types` táblája."""
    lathato = megjegyzes_nelkul(txt)
    j = Jegyzet(tartalom=lathato)
    poz = _Sorok(txt)
    maszk, linkmaszk = maszkok(txt)            # kód; kód + képlet (a linkekhez)
    fm = FM_RE.match(txt)
    fm_veg = 0
    if fm:
        j.fm_nyers, fm_veg = fm.group(1), fm.end()
        j.tulajdonsagok, j.fm_hiba = frontmatter(j.fm_nyers, tipusok)
    torzs = re.sub(r"[^\n]", " ", maszk[:fm_veg]) + maszk[fm_veg:]   # a törzs-elemzők a frontmattert nem látják

    # linkek: a wikilinkek (a gráf sorrendje), azután az md-linkek; a frontmatterben állók a kulcsukkal
    j.linkek = _wiki_rekordok(linkmaszk, txt, poz) + _md_rekordok(linkmaszk, poz)
    if fm:
        kulcsok = []
        for m in re.finditer(r"^.*$", txt[:fm.end(1)], re.M):
            km = _FM_KULCS.match(m.group(0))
            if km:
                kulcsok.append((m.start(), km.group(1).strip()))
        for L in j.linkek:
            off = poz.kezdet[L.sor - 1] + L.oszlop
            if off < fm.end(1):
                elotte = [k for s, k in kulcsok if s <= off]
                L.tulajdonsag = elotte[-1] if elotte else None

    for t in j.tulajdonsagok:
        if t.tipus == "tags" or _TAGS_KULCS.match(t.kulcs):
            for c in _lista(t.ertek):
                c = c.strip().lstrip("#")
                if c:
                    j.cimkek.append({"cimke": c, "forras": "fm", "sor": None})
        if t.tipus == "aliases" or _ALIAS_KULCS.match(t.kulcs):
            j.aliasok += [_alias_szoveg(a) for a in (t.ertek if isinstance(t.ertek, list) else [t.ertek])
                          if isinstance(a, (str, int, float)) and _alias_szoveg(a)]

    for m in _CIMKE.finditer(torzs):
        c = m.group(1).rstrip("/")
        if c and re.search(r"[^\d/]", c):
            j.cimkek.append({"cimke": c, "forras": "szoveg", "sor": poz(m.start())[0]})

    for m in _FEJEZET.finditer(torzs):
        szoveg = re.sub(r"[ \t]+#+$", "", m.group(2)).strip()
        if szoveg:
            j.fejezetek.append({"szint": len(m.group(1)), "szoveg": szoveg, "sor": poz(m.start())[0]})
    for m in _SETEXT.finditer(torzs):          # T039: `Cím\n===` (1. szint), `Cím\n---` (2. szint)
        szoveg = m.group(1).strip()
        j.fejezetek.append({"szint": 1 if m.group(2)[0] == "=" else 2, "szoveg": szoveg, "sor": poz(m.start(1))[0]})
    j.fejezetek.sort(key=lambda f: f["sor"])      # a `fejezet_tartomany` sor szerint rendezett bemenetet kér

    sorok = lathato.split("\n")
    for m in _BLOKK.finditer(torzs):
        sor = poz(m.start(1))[0]
        kezdo = sor
        if sorok[sor - 1].strip() == "^" + m.group(1):   # külön sorban: az előző blokkra vonatkozik
            kezdo = sor - 1
            while kezdo > 1 and not sorok[kezdo - 1].strip():
                kezdo -= 1
        j.blokkok.append({"azon": m.group(1), "sor": sor, "kezdo_sor": _blokk_eleje(sorok, max(kezdo, 1))})

    for m in _FELADAT.finditer(torzs):
        sor = poz(m.start())[0]
        szoveg = sorok[sor - 1][m.start(3) - m.start():].rstrip()
        datumok = {_EMOJI[e]: d for e, d in _EMOJI_RE.findall(szoveg)}
        datumok.update({_DATAVIEW[k]: d for k, d in _DATAVIEW_RE.findall(szoveg)})
        j.feladatok.append({"sor": sor, "allapot": m.group(2), "szoveg": szoveg,
                            "behuzas": len(m.group(1).expandtabs(4)), "datumok": datumok})

    # T146 (C21): a blokk-képletek kitakarása EGY menetben (a `maszk._kitakar` mintája) — a korábbi, képletenkénti szelet-összefűzés
    # négyzetes volt (10 000 blokk-képletes jegyzeten másodpercek); a kitakarás szóközzel, a hossz és a pozíciók változatlanok
    darabok, poz_ = [], 0
    for m in _KEPLET_BLOKK.finditer(torzs):
        s = poz(m.start())[0]
        j.kepletek.append({"sor": s, "sor_veg": poz(m.end())[0], "kezd": m.start(), "veg": m.end(), "blokk": True,
                           "forras": m.group(1).strip()})
        darabok += [torzs[poz_:m.start()], " " * (m.end() - m.start())]
        poz_ = m.end()
    kepletes = "".join(darabok) + torzs[poz_:] if darabok else torzs
    for m in _KEPLET_SOR.finditer(kepletes):
        s = poz(m.start())[0]
        j.kepletek.append({"sor": s, "sor_veg": s, "kezd": m.start(), "veg": m.end(), "blokk": False,
                           "forras": m.group(1) or m.group(2)})
    j.kepletek.sort(key=lambda k: k["kezd"])

    for a, b, info in keritesek(txt[fm_veg:]):
        j.kodblokkok.append({"nyelv": info.split()[0] if info else "", "sor_kezd": poz(a + fm_veg)[0],
                             "sor_veg": poz(max(a, b - 1) + fm_veg)[0]})
    return j


# ---------------------------------------------------------------- canvas

def elemez_canvas(adat: dict | None, hiba: str | None) -> Jegyzet:
    """Egy canvas (a `feloldas` szerint beolvasott JSON) linkjei és keresési szövege."""
    j = Jegyzet(canvas_hiba=hiba)
    if adat is None:
        return j
    reszek = []
    for node in adat.get("nodes", []):
        nid = node.get("id")
        if node.get("file"):
            sub = node.get("subpath") or ""
            j.linkek.append(Link(cel=node["file"], fajta="canvas_fajl", alcel=sub.lstrip("#") or None,
                                 csomopont=nid))
            reszek.append(str(node["file"]))
        text = node.get("text") or ""
        if text:
            reszek.append(megjegyzes_nelkul(str(text), frontmatter=False))
            for L in _wiki_rekordok(link_maszk(text, frontmatter=False), text, None, "canvas_szoveg"):
                L.csomopont = nid
                j.linkek.append(L)
        if node.get("label"):
            reszek.append(str(node["label"]))
    j.tartalom = "\n\n".join(reszek)
    return j


def tipusok_olvas(vault) -> dict:
    """A vault `.obsidian/types.json` `types` táblája (ha nincs vagy hibás: üres)."""
    import os
    try:
        with open(os.path.join(os.fspath(vault), ".obsidian", "types.json"), encoding="utf-8") as fh:
            t = json.load(fh).get("types", {})
        return {str(k): str(v) for k, v in t.items()} if isinstance(t, dict) else {}
    except (OSError, ValueError, AttributeError):
        return {}
