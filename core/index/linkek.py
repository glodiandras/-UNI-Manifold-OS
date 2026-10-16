"""Link-segédek a feloldás fölött (C10): rövid cél-szöveg, fejezet- és blokk-horgony, link-átírás.

A feloldás maga a `feloldas.Feloldo` (L42, egyetlen hely); itt csak ráépülő, tiszta függvények vannak:
a felület és az átnevezés ezeken át kap cél-szöveget és horgonyt, saját szabályt nem alkalmaz.

Az átírás a közös link-maszkon (`maszk.link_maszk`) és a `WIKI_RE`/`MD_RE`-n dolgozik (ugyanaz a link-halmaz, mint a gráfé), de
**a nyers szövegen**: a `feloldas.szoveg` normalizálásának (`\\r\\n`, `\\r` → `\\n`) offset-térképével, így a
CRLF és az érvénytelen UTF-8 (surrogateescape) bájtra megmarad.
"""
from __future__ import annotations

import json
import posixpath
import re
from dataclasses import dataclass

from .feloldas import MD_RE, WIKI_RE, Feloldo, md_cel, nfc
from .maszk import link_maszk

_ALCEL_KARAKTER = re.compile(r"[#|^:\[\]\\]|%%")
_MD_JEL = re.compile(r"[*_~=`]")
_LISTA = re.compile(r"^([ \t]*)(?:[-*+]|\d+[.)])[ \t]")


# ---------------------------------------------------------------- rövid cél

def cel_szoveg(ut: str) -> str:
    """A fájl teljes útja link-célként: jegyzetnél kiterjesztés nélkül."""
    return ut[:-3] if ut.lower().endswith(".md") else ut


def rovid_cel(feloldo: Feloldo, ut: str, forras: str) -> str:
    """A legrövidebb cél-szöveg, amely a `forras`-ból egyértelműen az `ut` fájlra oldódik: a fájlnév, ha az
    egyedi (vagy a forrás mappájához a legközelebbi), különben egyre hosszabb útvonal-végződés. Mindig
    ellenőrzi a feloldóval; ha semmi sem működik, a teljes út kiterjesztéssel."""
    reszek = ut.split("/")
    for k in range(1, len(reszek) + 1):
        szoveg = cel_szoveg("/".join(reszek[-k:]))
        if feloldo.resolve(szoveg, forras)[0] == ut:
            return szoveg
    return ut


def relativ_cel(feloldo: Feloldo, ut: str, forras: str) -> str:
    cel = cel_szoveg(posixpath.relpath(ut, posixpath.dirname(forras) or "."))
    if not cel.startswith("../"):
        cel = "./" + cel
    return cel if feloldo.resolve(cel, forras)[0] == ut else rovid_cel(feloldo, ut, forras)


def abszolut_cel(feloldo: Feloldo, ut: str, forras: str) -> str:
    """A vault gyökeréhez viszonyított teljes út (jegyzetnél kiterjesztés nélkül); ha ez nem oldódik az `ut`-ra, a
    kiterjesztéses teljes út, végül a rövid cél (mindig a feloldóval ellenőrizve)."""
    for cel in dict.fromkeys([cel_szoveg(ut), ut]):
        if feloldo.resolve(cel, forras)[0] == ut:
            return cel
    return rovid_cel(feloldo, ut, forras)


FORMAK = {"rovid": rovid_cel, "relativ": relativ_cel, "abszolut": abszolut_cel}


def cel_forma(feloldo: Feloldo, ut: str, forras: str, forma: str | None = "rovid") -> str:
    """A link-cél a beállított „New link format” szerint (`rovid` | `relativ` | `abszolut`; ismeretlen: rövid)."""
    return FORMAK.get(forma or "rovid", rovid_cel)(feloldo, ut, forras)


_MD_UJ_KODOLANDO = re.compile(r"[\\\x00-\x1f\x7f %()<>\[\]]")


def md_ujra_kodol(szoveg: str) -> str:
    """Az újonnan írt md-link célja/horgonya: a szóköz, a vezérlőjelek és a `\\ % ( ) < > [ ]` `%XX`. Csak olyan jelet kódol,
    amelyet a `feloldas.decode_uri` (a JS `decodeURI`) vissza is fejt — a fenntartott jelek (`; / ? : @ & = + $ , #`)
    kódolatlanok, különben a cél nem oldódna fel. Az ékezet és minden más marad."""
    return _MD_UJ_KODOLANDO.sub(lambda m: "".join(f"%{b:02X}" for b in m.group(0).encode("utf-8")), szoveg)


def md_cel_irasra(cel: str, ut: str, alcel: str | None = None) -> str:
    """Az md-link célja (zárójel között): a `cel` (rövid/relatív/abszolút szöveg) a jegyzet `.md` kiterjesztésével, kódolva,
    a horgonnyal (`#fejezet`, `#^blokk`). A `feloldas.md_cel` visszafejtve a `cel + kiterjesztés` szöveget adja."""
    kit = ".md" if ut.lower().endswith(".md") and not cel.lower().endswith(".md") else ""
    ki = md_ujra_kodol(cel + kit)
    if alcel and alcel.strip():
        ki += "#" + md_ujra_kodol(alcel.strip())
    return ki


# ---------------------------------------------------------------- horgonyok

def alcel_norm(s: str) -> str:
    """A fejezet-egyeztetés alakja: NFC, a link- és blokkjelek szóközzé, a Markdown-kiemelés elhagyva, a
    szóközök összevonva, kisbetű. Az Obsidian pontos szabályának közelítése (a valódi vaulton mérve)."""
    s = _MD_JEL.sub("", _ALCEL_KARAKTER.sub(" ", nfc(s)))
    return " ".join(s.split()).casefold()


def fejezet_tartomany(fejezetek: list[tuple[int, str, int]], sorok_szama: int, alcel: str) -> tuple[int, int] | None:
    """`[[Jegyzet#Fejezet]]` → (első sor, utolsó sor), 1-től, zártan. `fejezetek`: (szint, szöveg, sor) sor
    szerint rendezve. A `A#B` egymásba ágyazott út az A szakaszán belül keresi B-t. A szakasz a következő,
    legfeljebb ugyanilyen szintű fejezet előtt ér véget."""
    utak = [alcel_norm(x) for x in alcel.split("#") if alcel_norm(x)]
    if not utak:
        return None
    lo, hi, talalt = 0, len(fejezetek), None
    for cel in utak:
        talalt = None
        for i in range(lo, hi):
            if alcel_norm(fejezetek[i][1]) == cel:
                talalt = i
                break
        if talalt is None:
            return None
        szint, _, sor = fejezetek[talalt]
        veg_i = next((j for j in range(talalt + 1, hi) if fejezetek[j][0] <= szint), hi)
        lo, hi = talalt + 1, veg_i
        veg = (fejezetek[veg_i][2] - 1) if veg_i < len(fejezetek) else sorok_szama
        eredmeny = (sor, max(sor, veg))
    return eredmeny


def blokk_tartomany(sorok: list[str], kezdo: int, sor: int) -> tuple[int, int]:
    """A `^id`-s blokk sorai: a kezdő sortól az azonosító soráig; ha listaelem, a mélyebben behúzott
    gyerekekkel (az Obsidian a listaelemet a gyerekeivel együtt ágyazza be)."""
    m = _LISTA.match(sorok[kezdo - 1]) if 0 < kezdo <= len(sorok) else None
    if not m:
        return kezdo, sor
    szint = len(m.group(1).expandtabs(4))
    veg, i = sor, sor
    while i < len(sorok):
        s = sorok[i]
        if not s.strip():
            j = i
            while j < len(sorok) and not sorok[j].strip():
                j += 1
            if j < len(sorok) and len(sorok[j]) - len(sorok[j].lstrip(" \t")) > szint:
                i = j
                continue
            break
        if len(s.expandtabs(4)) - len(s.expandtabs(4).lstrip(" ")) > szint:
            veg = i + 1
            i += 1
            continue
        break
    return kezdo, veg


# ---------------------------------------------------------------- nyers szöveg ↔ normalizált

def normalizalt(nyers: str) -> tuple[str, list[int]]:
    """A `feloldas.szoveg` szerinti szöveg és az offset-térkép: `terkep[i]` a normalizált `i`. karakter helye a
    nyers szövegben (`terkep[len(norm)]` = a nyers hossza)."""
    ki, terkep, i, n = [], [], 0, len(nyers)
    while i < n:
        c = nyers[i]
        terkep.append(i)
        if c == "\r":
            ki.append("\n")
            i += 2 if nyers[i + 1:i + 2] == "\n" else 1
        else:
            ki.append(c)
            i += 1
    terkep.append(n)
    return "".join(ki), terkep


def dekodol(b: bytes) -> str:
    return b.decode("utf-8", errors="surrogateescape")


def kodol(s: str) -> bytes:
    return s.encode("utf-8", errors="surrogateescape")


# ---------------------------------------------------------------- link-találatok

@dataclass
class Talalat:
    fajta: str          # wiki | md | canvas_fajl | canvas_szoveg
    cel: str            # a nyers cél-szöveg, ahogy a gráf kapja (a `\\|` escape-je nélkül is feloldható)
    kezd: int           # a cél-szakasz helye a NYERS szövegben (a csere ezt írja át)
    veg: int
    sorrend: int        # a `jegyzet_celok` sorrendje (wiki-k, azután az md-linkek)
    burok: bool = False  # md-link `<…>` burokban (C31): az átírás burokban, kódolás nélkül ír; különben `md_kodol`


def jegyzet_talalatok(nyers: str) -> list[Talalat]:
    """Egy `.md` linkjei a gráf szabálya szerint, a cél-szakasz nyers helyével. A sorrend és a halmaz
    megegyezik a `feloldas.jegyzet_celok`-éval (a teszt méri)."""
    norm, terkep = normalizalt(nyers)
    maszk = link_maszk(norm)
    ki: list[Talalat] = []
    for m in WIKI_RE.finditer(maszk):
        a, b = m.start(1), m.end(1)
        if b > a and norm[b - 1] == "\\":
            b -= 1          # a táblázatbeli `\|` visszapere az elválasztóé
        ki.append(Talalat("wiki", m.group(1), terkep[a], terkep[b], len(ki)))
    for m in MD_RE.finditer(maszk):
        t = m.group(1)
        cel = md_cel(t)                       # C31 (36. döntés): a feloldás a dekódolt célt kapja
        if cel is None:
            continue
        a = m.start(1)
        burok = t.strip().startswith("<") and t.strip().endswith(">")
        if burok:                             # a csere a burok BELSEJÉT írja (a `<`, `>` marad)
            belso = t.index("<") + 1
            a, t = a + belso, t[belso:t.rindex(">")]
        b = a + (t.index("#") if "#" in t else len(t))
        ki.append(Talalat("md", cel, terkep[a], terkep[b], len(ki), burok))
    return ki


def cel_resz(szoveg: str) -> tuple[str, str, str]:
    """A cél-szakasz (kezd..veg) szövege → (vezető szóköz, a tényleges cél, záró szóköz)."""
    kerek = szoveg.strip()
    if not kerek:
        return szoveg, "", ""
    i = szoveg.index(kerek[0])
    return szoveg[:i], kerek, szoveg[i + len(kerek):]


def uj_cel_szoveg(regi_cel: str, uj_ut: str, forras: str | None = None, regi_ut: str | None = None) -> list[str]:
    """Jelölt cél-szövegek egy link új alakjához, sorrendben (a hívó a feloldóval ellenőrzi az elsőt, amely a
    célra oldódik): **stílusőrző** — a bare marad bare, a `./`/`../` relatív marad relatív (az **új** forrás mappájától,
    ha a `forras` adott), a teljes (vault-gyökerű) út teljes út marad (ha a `regi_ut` adott), különben az útvonal-végződés
    ugyanannyi szegmenssel; a `.md` megmarad, ha volt. A beállított formátum tartaléka a hívóé (`cel_forma`)."""
    s = nfc(regi_cel.strip())
    if s.endswith("\\"):
        s = s[:-1].rstrip()
    s = s.replace("\\", "/")
    perjel = "/" if s.startswith("/") else ""
    s = s.lstrip("/")
    volt_md = s.lower().endswith(".md")

    def alak(sz: str) -> str:
        return sz if (volt_md or not uj_ut.lower().endswith(".md")) else cel_szoveg(sz)

    jeloltek: list[str] = []
    if forras is not None and not perjel and s.startswith(("./", "../")):
        if regi_ut is not None and posixpath.dirname(regi_ut) == posixpath.dirname(uj_ut) and "/" in s:
            jeloltek.append(s[:s.rindex("/") + 1] + alak(posixpath.basename(uj_ut)))      # csak a név változott: a szerző útja marad
        rel = posixpath.relpath(uj_ut, posixpath.dirname(forras) or ".")
        jeloltek.append(alak(rel if rel.startswith("../") else "./" + rel))
    elif regi_ut is not None and "/" in regi_ut and cel_szoveg(s).casefold() == cel_szoveg(nfc(regi_ut)).casefold():
        jeloltek.append(perjel + alak(uj_ut))
    szegmens = max(1, len([x for x in s.split("/") if x]))
    reszek = uj_ut.split("/")
    for k in dict.fromkeys([min(szegmens, len(reszek)), len(reszek)]):
        jeloltek.append(perjel + alak("/".join(reszek[-k:])))
    return list(dict.fromkeys(jeloltek))


# ---------------------------------------------------------------- canvas

def canvas_stringek(nyers: str) -> list[tuple[int, int, str, str, int]]:
    """A canvas JSON string-literáljai a nyers szövegben: (kezd, veg, a dekódolt érték, a szülő kulcs, mélység).
    Csak az objektum-értékek (a kulcsok kimaradnak). A `kezd..veg` az idézőjelekkel együtt."""
    ki: list[tuple[int, int, str, str, int]] = []
    verem: list[list] = []      # [fajta, aktuális kulcs, kulcsra vár]
    i, n = 0, len(nyers)
    while i < n:
        c = nyers[i]
        if c == '"':
            j = i + 1
            while j < n and nyers[j] != '"':
                j += 2 if nyers[j] == "\\" else 1
            lit = nyers[i:j + 1]
            try:
                ertek = json.loads(lit)
            except ValueError:
                ertek = ""
            if verem and verem[-1][0] == "{" and verem[-1][2]:
                verem[-1][1], verem[-1][2] = ertek, False       # kulcs
            else:
                kulcs = verem[-1][1] if verem and verem[-1][0] == "{" else ""
                ki.append((i, j + 1, ertek, kulcs, len(verem)))
            i = j + 1
            continue
        if c in "{[":
            verem.append([c, "", c == "{"])
        elif c in "}]":
            if verem:
                verem.pop()
        elif c == "," and verem and verem[-1][0] == "{":
            verem[-1][2] = True
        i += 1
    return ki


def canvas_talalatok(nyers: str) -> list[tuple[int, int, str, str]]:
    """Egy canvas linkjei a `canvas_celok` szabálya szerint: (kezd, veg, a cél-szöveg, fajta). A `file` node
    útja (a teljes literál) és a szövegnode-ok `[[…]]`-jei (a dekódolt szövegen: a hívó írja át)."""
    ki = []
    for kezd, veg, ertek, kulcs, _ in canvas_stringek(nyers):
        if kulcs == "file" and ertek:
            ki.append((kezd, veg, ertek, "canvas_fajl"))
        elif kulcs == "text" and isinstance(ertek, str) and "[[" in ertek:
            ki.append((kezd, veg, ertek, "canvas_szoveg"))
    return ki


def json_literal(s: str) -> str:
    """Egy string JSON-literálja a JS `JSON.stringify` szerinti alakban (nem ASCII-escape-elt)."""
    return json.dumps(s, ensure_ascii=False)

