"""A dolgozat eredménye a „Dolgozat kiértékelő” jegyzetekből (C28b; `docs/C28-TERV.md` 7., NAPLO: C28b) — a legacy
`szemelyes/dolgozat.py` `eredmeny()`-ének portja, a három ismert hiba javításával, tiszta függvényekkel (I/O nélkül).

A jegyzet szabad szöveg („Megkaptam az eredményt: 16/23 lett”), ezért a kinyerő **óvatos**: ami nem egyértelmű, az hiány,
nem találgatás. A legacy három hibája és a javítás:

1. *téves kizárás*: a „7,5 pontot értem el végül a 10-ből, ami szerintem fair” a „szerintem” miatt kiesett → a bizonytalanságjelző
   (szerintem, úgy érzem) csak akkor zár ki, ha a mondatban nincs múlt idejű eredményjelző (lett, kaptam, értem el, eredmény…);
2. *téves találat*: a pluszpont („26/26 pontot szereztem” a plusz munkákon), az önbecslés („az anyag 80–85%-át el tudtam volna mondani”),
   a jövő idejű becslés és az összesített havi jegy („kettes (18/30)”) nem a dolgozat eredménye → kizárja őket a **mondat-** és
   **tagmondat-szintű** környezet (a vizsgálat a szám előtti mondatrészre és a szám tagmondatának végére terjed, így a „10/10 pontos
   lett, sőt plusz feladatot is csináltam, amelyre 4/4 pontot kaptam pluszban” 10/10-et ad, a 4/4 kiesik);
3. *ellentmondás*: a „68% lett (18/31)” két, egymásnak ellentmondó értéket ad (18/31 = 58,1%) — a legacy az első reguláris kifejezés
   találatát adta, csendben; itt **nincs eredmény**, hanem `ellentmondas` jelzés a két jelölttel (a felhasználó javítja a jegyzetben).
   Az egymással összhangban álló pont/max és százalék (±1,5 százalékpont) egy eredmény.

**Szabott eredmény-mező (C28c, K348; a D12 nyitott kérdése, a felhasználó igent mondott 2026-10-14).** A szakasz törzsében egy
saját sorban álló, Dataview-stílusú inline mező (`Eredmény:: 16/23`, `Eredmény:: 68%`, `Eredmény:: 16/23 (70%)`; a kulcs
kis-nagybetűtől és ékezettől független, listajel, idézetjel és `**` állhat előtte) **elsőbbséget kap**: ha a szakaszban van nem üres
mező, a szabad szöveget a kinyerő nem nézi. A pont/max és a zárójeles százalék egyezése ±1,5 százalékpont; az ellentmondó vagy nem
olvasható mező, illetve a több, egymásnak ellentmondó mező **jelzett hiány** (`ellentmondas`), nem tartalék a szövegre. Az üres
mező (`Eredmény::`, pl. sablonból) nem mező: a szöveg dönt. Frontmatter-kulcs nem lehet: a kiértékelő jegyzet egy szakasza egy
dolgozat (egy jegyzetben több), és az AI01 séma ismeretlen frontmatter-kulcsot nem enged (`config/vault-sema.json`).
Az eredmény `eredet` mezője: `"mezo"` | `"szoveg"`.

A kinyerő a **vaultot nem módosítja**; a mezőt a felhasználó írja, gép soha.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

TURES_SZAZALEKPONT = 1.5          # a pont/max és a kimondott százalék ennyin belül „egyező”

_SZAM = r"\d+(?:[.,]\d+)?"
_BOL = r"b[őo]l"
# 1. „6,5 pont lett végül a 10-ből”, „46 pontot kaptam az 50-ből”
_P1 = re.compile(rf"({_SZAM})\s*pont\w*\b[^\n.!?]{{0,40}}?\b(?:az?\s+)?({_SZAM})\s*-?\s*{_BOL}", re.I)
# 1/b. „a 10-ből 6,5 pontot kaptam”
_P1R = re.compile(rf"\b(?:az?\s+)?({_SZAM})\s*-?\s*{_BOL}\s+({_SZAM})\s*pont\w*", re.I)
# 2. „16/23”, „13.5/16”, „4,5/10”
_P2 = re.compile(rf"(?<![\d/.,])({_SZAM})\s*/\s*({_SZAM})(?![\d/])")
# 3. „68%”
_P3 = re.compile(rf"(?<![\d.,])(\d{{1,3}}(?:[.,]\d+)?)\s*%")

_MONDATHATAR = re.compile(r"(?<=[.!?])\s+|\n+")
_TAGKEZD = re.compile(r"(?<!\d),|,(?!\d)|;|\s[-–—]\s")          # a tagmondat eleje (a zárójel nem határ: „68% lett (18/31)”)
_TAGVEG = re.compile(r"(?<!\d),|,(?!\d)|;|\s[-–—]\s|\(")        # a tagmondat vége (a nyitó zárójel is lezárja)

_PLUSZ = re.compile(r"plusz")
_FELTETELES = re.compile(r"\bvolna\b|\blenne\b|\blennék\b|\blennének\b")
_JOVO = re.compile(r"\blesz\b|\bleszek\b|\bleszünk\b|\bleszel\b|\blesznek\b|\bvárhatóan\b|\bremélem\b|\bszámítok\b|\btippelek\b"
                   r"|\bbecsl\w*|\bbecsül\w*")
# K390 (2026-10-14, F8): a jelen idejű, de jövőre vagy szándékra utaló alak sem tényleges eredmény (77(a): a bizonytalan hiány,
# nem találgatás) — „8 pontot elérek a 10-ből”, „szeretnék 80%-ot”, „talán 15/20”; a múlt idejű alak („elértem”, „kaptam”) nem ilyen
_SZANDEK = re.compile(r"\b(?:el|meg)?érek\b|\b(?:el|meg)?érem\b|\b(?:meg)?kapok\b|\b(?:meg)?kapom\b|\bszerzek\b|\bszerzem\b"
                      r"|\bszeretnék\b|\bszeretném\b|\bszeretnénk\b|\bkellene\b|\bkéne\b|\bakarok\b|\bakarom\b"
                      r"|\bfogok\b|\bfogom\b|\bfogunk\b|\btalán\b|\bhátha\b|\bremélhetőleg\b|\bcélom\b|\bcél\b")
_KOZELITO = re.compile(r"\b(?:kb|kábé|körülbelül|nagyjából|talán|valahol)\b\.?")
_BIZONYTALAN = re.compile(r"\bszerintem\b|\bgondolom\b|\búgy érzem\b|\búgy gondolom\b")
_OSSZESITETT = re.compile(r"össze\w*gében|összességében|\bhavi\b|\behavi\b|\bátlag\w*|\bösszesít\w*|\bfélév\w*|\btanév\w*")
_ERO = re.compile(r"\blett\b|\bkaptam\b|\bkaptunk\b|\bkaptuk\b|\bértem el\b|\bértünk el\b|\belértem\b|\bszereztem\b|\beredmény\w*"
                  r"|\bzártam\b|\bmegkaptam\b|\bvisszakaptuk\b|\bírtam\b")
_PONT_SZO = re.compile(r"\bpont\w*")
_TARTOMANY_ELOTT = re.compile(r"\d\s*[-–]\s*$")
_SZAZALEK_RAG = re.compile(r"^\s*-?\s*(?:át|ét|kal|kel|ra|re|ig|ban|ben|nál|nél)\b")


@dataclass(frozen=True)
class Talalat:
    fajta: str                    # "pont" | "szazalek"
    pont: float | None
    max: float | None
    szazalek: float               # 0–100
    forras: str                   # a találat szövege
    mondat: str
    elfogadva: bool
    ok: str                       # a kizárás oka (magyarul), elfogadottnál ""
    pontszam: int = 0


@dataclass(frozen=True)
class Kinyeres:
    eredmeny: dict | None         # {pont, max, szazalek, forras, fajta, mondat, eredet}
    ellentmondas: dict | None     # {jeloltek: [{forras, szazalek}], ok} — több, egymásnak ellentmondó érték
    talalatok: tuple[Talalat, ...] = ()
    eredet: str | None = None     # "mezo" (a szabott `Eredmény::` mező döntött, akkor is, ha hibás) | "szoveg" | None


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def _szam(s: str) -> float:
    return float(s.replace(",", "."))


def _tisztit(szoveg: str) -> str:
    """NFC, sorvég-egységesítés, Markdown-kiemelés (`**`, `__`, `*`) nélkül; a hossz változhat, a pozíciók erre vonatkoznak."""
    s = _nfc(szoveg).replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\*{1,3}|__", "", s)


def _mondat_hatar(s: str, poz: int) -> tuple[int, int]:
    kezd = 0
    for m in _MONDATHATAR.finditer(s):
        if m.end() <= poz:
            kezd = m.end()
        else:
            return kezd, m.start()
    return kezd, len(s)


def _tagmondat_hatar(s: str, mk: int, mv: int, poz: int, poz_veg: int) -> tuple[int, int]:
    """A mondat (`[mk, mv)`) azon tagmondatának határai, amely a `[poz, poz_veg)` találatot tartalmazza."""
    kezd, veg = mk, mv
    for m in _TAGKEZD.finditer(s, mk, mv):
        if m.end() <= poz:
            kezd = m.end()
        else:
            break
    for m in _TAGVEG.finditer(s, poz_veg, mv):
        veg = m.start()
        break
    return kezd, veg


def _kozelito_kozel(elotte: str) -> bool:
    """Közelítő szó (kb, körülbelül…) közvetlenül a szám előtt (legfeljebb két szó távolságban)."""
    szavak = elotte.split()
    ablak = " ".join(szavak[-3:])
    return bool(_KOZELITO.search(ablak))


def _talalatok(s: str) -> list[tuple[str, float | None, float | None, float, int, int]]:
    """A nyers jelöltek: (fajta, pont, max, százalék, kezd, vég) — a szám-ellenőrzéssel (0 ≤ pont ≤ max ≤ 1000, 0 ≤ % ≤ 100)."""
    ki = []
    for m in _P1.finditer(s):
        pont, mx = _szam(m.group(1)), _szam(m.group(2))
        if 0 < mx <= 1000 and 0 <= pont <= mx:
            ki.append(("pont", pont, mx, 100 * pont / mx, m.start(), m.end()))
    for m in _P1R.finditer(s):
        mx, pont = _szam(m.group(1)), _szam(m.group(2))
        if 0 < mx <= 1000 and 0 <= pont <= mx:
            ki.append(("pont", pont, mx, 100 * pont / mx, m.start(), m.end()))
    for m in _P2.finditer(s):
        pont, mx = _szam(m.group(1)), _szam(m.group(2))
        if 0 < mx <= 1000 and 0 <= pont <= mx:
            ki.append(("pont", pont, mx, 100 * pont / mx, m.start(), m.end()))
    for m in _P3.finditer(s):
        sz = _szam(m.group(1))
        if 0 <= sz <= 100:
            ki.append(("szazalek", None, None, sz, m.start(), m.end()))
    # azonos szöveghelyen több minta is találhat (pl. a „6,5 pont … 10-ből” és a „P1R”): az első (legszélesebb) marad
    ki.sort(key=lambda x: (x[4], -(x[5] - x[4])))
    szuk, utolso_veg = [], -1
    for x in ki:
        if x[4] < utolso_veg:
            continue
        szuk.append(x)
        utolso_veg = x[5]
    return szuk


def _dont(s: str, fajta: str, kezd: int, veg: int) -> tuple[bool, str, int, str]:
    """Egy jelölt sorsa a környezete szerint → (elfogadva, kizárás oka, pontszám, mondat)."""
    mk, mv = _mondat_hatar(s, kezd)
    mondat = s[mk:mv].strip()
    tk, tv = _tagmondat_hatar(s, mk, mv, kezd, veg)
    kis_elotte = s[mk:kezd].lower()
    kis_mondat = s[mk:mv].lower()
    hatokor = s[mk:tv].lower()                                # a mondat eleje, a találat és a tagmondat vége
    kis_tag = s[tk:tv].lower()

    if _PLUSZ.search(hatokor):
        return False, "pluszpont (nem a dolgozat eredménye)", 0, mondat
    if _FELTETELES.search(hatokor):
        return False, "feltételes mondat („…volna”): nem tényleges eredmény", 0, mondat
    if _OSSZESITETT.search(kis_mondat):
        return False, "összesített (havi, átlag) érték, nem egy dolgozat eredménye", 0, mondat
    if _JOVO.search(hatokor):
        return False, "jövő idejű vagy becsült érték", 0, mondat
    if _SZANDEK.search(hatokor):
        return False, "jövőre vagy szándékra utaló mondat („elérek”, „szeretnék”, „talán”): nem tényleges eredmény", 0, mondat
    if _kozelito_kozel(kis_elotte):
        return False, "közelítő érték („kb.”, „körülbelül”)", 0, mondat
    erosseg = 0
    if _ERO.search(kis_tag):
        erosseg = 2
    elif _ERO.search(kis_mondat):
        erosseg = 1
    if erosseg == 0 and _BIZONYTALAN.search(kis_mondat):
        return False, "bizonytalan, véleményt kifejező mondat (nincs eredményjelző: „lett”, „kaptam”…)", 0, mondat
    if fajta == "szazalek":
        if _TARTOMANY_ELOTT.search(s[max(0, kezd - 4):kezd]):
            return False, "százalék-tartomány („80–85%”), nem eredmény", 0, mondat
        if _SZAZALEK_RAG.match(s[veg:veg + 8].lower()):
            return False, "arány egy tartalomra („…%-át”), nem eredmény", 0, mondat
        if erosseg == 0:
            return False, "a százalék mellett nincs eredményjelző („lett”, „kaptam”, „eredmény”)", 0, mondat
    else:
        if erosseg == 0 and not _PONT_SZO.search(kis_mondat):
            return False, "a törtnek nincs eredmény- vagy pontjelzője a mondatban", 0, mondat
    pont = erosseg + (1 if _PONT_SZO.search(kis_mondat) else 0)
    return True, "", pont, mondat


def _kerekit(x: float) -> float:
    return round(x, 1)


def _eredmeny_dict(t: Talalat, szazalek: float | None = None, eredet: str = "szoveg") -> dict:
    return {"pont": t.pont, "max": t.max, "szazalek": _kerekit(t.szazalek if szazalek is None else szazalek),
            "forras": t.forras, "fajta": t.fajta, "mondat": t.mondat, "eredet": eredet}


# ------------------------------------------------------------------ a szabott mező (C28c)

MEZO_KULCS = "Eredmény"
MEZO_MINTA = "Eredmény:: 16/23"     # a felület tippje és a dokumentáció példája
# egy saját sor: opcionális listajel / idézetjel, a kulcs (ékezettel vagy nélküle), `::`, az érték
_MEZO_SOR = re.compile(r"^[ \t]*(?:>[ \t]*)*(?:[-*+][ \t]+)?eredm[eé]ny[ \t]*::(.*)$", re.I)
_MEZO_PONT = re.compile(rf"^({_SZAM})\s*/\s*({_SZAM})(?:\s*pont\w*)?(?:\s*\(\s*({_SZAM})\s*%\s*\))?$", re.I)
_MEZO_SZAZALEK = re.compile(rf"^({_SZAM})\s*%$")


def _mezo_sorok(s: str) -> list[tuple[str, str]]:
    """A kódblokkon kívüli, nem üres `Eredmény::` mezők: `[(a sor szövege, az érték)]` (a `s` már tisztított: `**` nélkül)."""
    ki, kod = [], False
    for sor in s.split("\n"):
        if sor.lstrip().startswith(("```", "~~~")):
            kod = not kod
            continue
        if kod:
            continue
        m = _MEZO_SOR.match(sor)
        if m and m.group(1).strip():
            ki.append((sor.strip(), m.group(1).strip()))
    return ki


def mezo_ertek(ertek: str) -> tuple[dict | None, str]:
    """Egy mező-érték elemzése → (`{pont, max, szazalek, fajta}`, "") vagy (None, a hiba oka magyarul). A zárójeles százalék a
    pont/max-szal ±1,5 százalékponton belül egyezzen; a pont ≤ max ≤ 1000, a százalék 0–100."""
    v = ertek.strip()
    m = _MEZO_PONT.match(v)
    if m:
        pont, mx = _szam(m.group(1)), _szam(m.group(2))
        if not (0 < mx <= 1000 and 0 <= pont <= mx):
            return None, f"a mező értéke nem lehetséges pontszám („{v}”: 0 ≤ pont ≤ max ≤ 1000)"
        sz = 100 * pont / mx
        if m.group(3) is not None:
            kimondott = _szam(m.group(3))
            if abs(kimondott - sz) > TURES_SZAZALEKPONT:
                return None, (f"a mezőben a pont és a százalék ellentmond („{v}”: {_szam_szoveg(pont)}/{_szam_szoveg(mx)} = "
                              f"{_szam_szoveg(_kerekit(sz))}%, nem {_szam_szoveg(kimondott)}%)")
        return {"pont": pont, "max": mx, "szazalek": sz, "fajta": "pont"}, ""
    m = _MEZO_SZAZALEK.match(v)
    if m:
        sz = _szam(m.group(1))
        if not 0 <= sz <= 100:
            return None, f"a mező százaléka 0 és 100 között legyen („{v}”)"
        return {"pont": None, "max": None, "szazalek": sz, "fajta": "szazalek"}, ""
    return None, f"a mező értéke nem olvasható („{v}”; jó alak: 16/23, 68% vagy 16/23 (70%))"


def _szam_szoveg(x: float) -> str:
    return (f"{x:g}").replace(".", ",")


def _mezo_kinyeres(s: str) -> Kinyeres | None:
    """A szabott mező eredménye, ha a szakaszban van nem üres mező; különben `None` (a szöveg dönt)."""
    sorok = _mezo_sorok(s)
    if not sorok:
        return None
    jo: list[Talalat] = []
    hibak: list[tuple[str, str]] = []
    for sor, ertek in sorok:
        e, ok = mezo_ertek(ertek)
        if e is None:
            hibak.append((sor, ok))
        else:
            jo.append(Talalat(e["fajta"], e["pont"], e["max"], e["szazalek"], sor, sor, True, "", 9))
    talalatok = tuple(jo) + tuple(Talalat("mezo", None, None, 0.0, sor, sor, False, ok) for sor, ok in hibak)
    if hibak:
        return Kinyeres(None, {"ok": hibak[0][1] + " — javítsd a mezőt a jegyzetben",
                               "jeloltek": [{"forras": sor, "szazalek": None} for sor, _ in hibak]
                               + [{"forras": t.forras, "szazalek": _kerekit(t.szazalek)} for t in jo]}, talalatok, "mezo")
    if any(abs(t.szazalek - x.szazalek) > TURES_SZAZALEKPONT for t in jo for x in jo):
        return Kinyeres(None, {"ok": "több, egymásnak ellentmondó „Eredmény::” mező a szakaszban — hagyj meg egyet",
                               "jeloltek": [{"forras": t.forras, "szazalek": _kerekit(t.szazalek)} for t in jo]}, talalatok, "mezo")
    elso = next((t for t in jo if t.fajta == "pont"), jo[0])
    return Kinyeres(_eredmeny_dict(elso, eredet="mezo"), None, talalatok, "mezo")


def kinyer(szoveg: str) -> Kinyeres:
    """A kiértékelő szövegéből a dolgozat eredménye (pont/max vagy százalék), ha egyértelmű; ellentmondásnál `ellentmondas`.
    A szabott `Eredmény::` mező elsőbbséget kap (C28c); nélküle a szabad szöveg dönt."""
    s = _tisztit(szoveg)
    mezo = _mezo_kinyeres(s)
    if mezo is not None:
        return mezo
    talalatok = []
    for fajta, pont, mx, sz, kezd, veg in _talalatok(s):
        elfogad, ok, pontszam, mondat = _dont(s, fajta, kezd, veg)
        talalatok.append(Talalat(fajta, pont, mx, sz, s[kezd:veg].strip(), mondat, elfogad, ok, pontszam))
    jeloltek = [t for t in talalatok if t.elfogadva]
    if not jeloltek:
        return Kinyeres(None, None, tuple(talalatok), None)
    # csoportok: a kölcsönösen egyező (±1,5 százalékpont) jelöltek egy eredmény
    csoportok: list[list[Talalat]] = []
    for t in jeloltek:
        for cs in csoportok:
            if all(abs(t.szazalek - x.szazalek) <= TURES_SZAZALEKPONT for x in cs):
                cs.append(t)
                break
        else:
            csoportok.append([t])
    csoportok.sort(key=lambda cs: -max(x.pontszam for x in cs))
    legjobb = max(x.pontszam for x in csoportok[0])
    if len(csoportok) > 1 and max(x.pontszam for x in csoportok[1]) >= legjobb:
        return Kinyeres(None, {
            "ok": "ellentmondó értékek a szakaszban — javítsd a jegyzetben, hogy egyértelmű legyen",
            "jeloltek": [{"forras": x.forras, "szazalek": _kerekit(x.szazalek)} for cs in csoportok for x in cs]}, tuple(talalatok),
            "szoveg")
    cs = csoportok[0]
    par = next((x for x in cs if x.fajta == "pont"), None)
    elso = par or cs[0]
    return Kinyeres(_eredmeny_dict(elso), None, tuple(talalatok), "szoveg")


def eredmeny(szoveg: str) -> dict | None:
    """A legacy-kompatibilis alak: az eredmény (`pont`, `max`, `szazalek`, `forras`), vagy `None` (nincs egyértelmű eredmény)."""
    return kinyer(szoveg).eredmeny


# ------------------------------------------------------------------ szakaszok (a „Dolgozat kiértékelő” jegyzet szerkezete)

_FRONTMATTER = re.compile(r"\A---\r?\n.*?\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)
_CIMSOR = re.compile(r"^#[ \t]+(.+?)[ \t]*$")
_WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")


@dataclass(frozen=True)
class Szakasz:
    cim: str
    torzs: str
    link: str | None          # az első wikilink célja (a felkészülési jegyzet neve), cső és horgony nélkül
    sor: int                  # a címsor sora a jegyzetben (1-től)


def szakaszok(szoveg: str) -> list[Szakasz]:
    """A jegyzet első szintű (`# `) címsoraival határolt szakaszai; a frontmatter és a kódblokkok nem címsorok. A szakasz
    `link`-je a törzs első wikilinkje (a legacy: az alatta álló első wikilink a felkészülési jegyzetre mutat)."""
    s = _nfc(szoveg).replace("\r\n", "\n")
    m = _FRONTMATTER.match(s)
    eltolas = s[:m.end()].count("\n") if m else 0
    if m:
        s = s[m.end():]
    ki: list[Szakasz] = []
    cim, sor0, torzs = None, 0, []
    kod = False

    def zar():
        if cim is not None:
            szoveg_ = "\n".join(torzs).strip()
            link = _WIKILINK.search(szoveg_)
            ki.append(Szakasz(cim, szoveg_, _nfc(link.group(1).strip()) if link else None, sor0))

    for i, sor in enumerate(s.split("\n"), start=1):
        if sor.lstrip().startswith(("```", "~~~")):
            kod = not kod
        c = None if kod else _CIMSOR.match(sor)
        if c:
            zar()
            cim, sor0, torzs = c.group(1), i + eltolas, []
        elif cim is not None:
            torzs.append(sor)
    zar()
    return ki


@dataclass(frozen=True)
class SzakaszEredmeny:
    szakasz: Szakasz
    kinyeres: Kinyeres
    fajl: str = ""            # a kiértékelő jegyzet vault-relatív útja (a felületnek: honnan olvastuk)


def szakasz_eredmenyek(szoveg: str, fajl: str = "") -> list[SzakaszEredmeny]:
    return [SzakaszEredmeny(sz, kinyer(sz.torzs), fajl) for sz in szakaszok(szoveg)]


def jegyzetenkent(eredmenyek: list[tuple[str, SzakaszEredmeny]]) -> dict[str, dict]:
    """A felkészülési jegyzethez (a feloldott útja) tartozó szakasz-eredmények összegzése: `[(jegyzet_ut, szakasz_eredmeny)]` →
    `{jegyzet_ut: {eredmeny | None, ellentmondas | None, szakasz_cim, forras_jegyzet}}`. Egy jegyzethez több szakasz is tartozhat
    (a másik hónap jegyzete, ismétlés): egy különböző eredmény → `ellentmondas`; azonos értékű → egy eredmény. Ha valamelyik szakasz
    szabott mezőt hordoz (C28c), csak a mezős szakaszok számítanak (a mező a szöveg előtt áll, a jegyzeten belül is)."""
    csoport: dict[str, list[tuple[str, SzakaszEredmeny]]] = {}
    for jegyzet, se in eredmenyek:
        csoport.setdefault(jegyzet, []).append((jegyzet, se))
    ki: dict[str, dict] = {}
    for jegyzet, lista in csoport.items():
        mezos = [x for x in lista if x[1].kinyeres.eredet == "mezo"]
        if mezos:
            lista = mezos
        eredmenyek_ = [se for _, se in lista if se.kinyeres.eredmeny]
        ellent = next((se.kinyeres.ellentmondas for _, se in lista if se.kinyeres.ellentmondas), None)
        egy, kul = None, False
        for se in eredmenyek_:
            if egy is None:
                egy = se
            elif abs(se.kinyeres.eredmeny["szazalek"] - egy.kinyeres.eredmeny["szazalek"]) > TURES_SZAZALEKPONT:
                kul = True
        if kul:
            ellent = {"ok": "több szakasz különböző eredménnyel ugyanahhoz a dolgozathoz", "jeloltek": [
                {"forras": se.kinyeres.eredmeny["forras"], "szazalek": se.kinyeres.eredmeny["szazalek"]} for se in eredmenyek_]}
            egy = None
        elif ellent and egy is not None:
            ellent = None              # van egy egyértelmű szakasz: a másik (ellentmondó) szakasz nem írja felül
        ref = egy if egy is not None else lista[0][1]
        ki[jegyzet] = {"eredmeny": None if egy is None else egy.kinyeres.eredmeny, "ellentmondas": ellent,
                       "szakasz_cim": ref.szakasz.cim, "fajl": ref.fajl, "sor": ref.szakasz.sor, "eredet": ref.kinyeres.eredet}
    return ki
