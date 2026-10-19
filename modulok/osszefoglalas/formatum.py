"""Az összefoglaló kísérőjegyzet formátuma (`docs/C26-TERV.md` 1. fejezet): elemző, író, fájlnév, horgony-linkek.

A formátum **egyetlen helye** (mint a `modulok/kviz/formatum.py`). Minden állítás mellett a forrás linkje és a jegyzet
szó szerinti mondata áll; a forrás nélküli sor nem állítás.

```markdown
---
Source:
  - "[[T03 - Az ókori Róma/Elmélet/08 - A polgárháborúk kora és Caesar]]"
Osszefoglalas: OSSZ-20261005-101530-3fa91c
Szint: jegyzet
Modell: "qwen35_9b"
Keszult: 2026-10-05 1015
---

# A polgárháborúk kora és Caesar — Összefoglaló

## Állítások

1. A senatus félelme a hadvezértől éppen azt a szövetséget hozta létre, amelytől félt. [[T03 - …/08 - …#^m-3f2a|forrás]]
   > „A köztársaság tehát … amelytől félt.”
```

- Az elemző **nem dob**: a hibák a jelentésben (`hibak: [{sor, fajta, szoveg}]`); a hibás állítás kimarad, a többi él.
- A kódkerítésben álló lista nem állítás (a core `mask_code`-ja).
- Tiszta függvények: szöveg be, szerkezet ki; fájlt nem olvasnak és nem írnak.
"""
from __future__ import annotations

import re
import secrets
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime

import yaml

from core import kiserok
from core.index.maszk import FM_RE, mask_code, megjegyzes_nelkul
from modulok.kartya.formatum import kiseronev as _kiseronev

SZINTEK = ("jegyzet", "mappa", "video", "kontextus")
AZON_RE = re.compile(r"^OSSZ-\d{8}-\d{6}(?:-[0-9a-z]{1,12})*$")
UTOTAG = " — összefoglaló"
ALAP_MAPPA = kiserok.alap_mappa("osszefoglalas")   # a kísérőjegyzetek mappája, ha az `[osszefoglalas] mappa` hiányzik (a forrás: core/kiserok.py)
CIM_UTOTAG = " — Összefoglaló"
ALLITASOK_CIM = "## Állítások"
FELIRAT = "forrás"

_TILTOTT = re.compile(r"\[\[|\]\]|==")
_ELEM = re.compile(r"^[ \t]*(\d+)[.)][ \t]+(.*?)[ \t]*$")
_ELEM_LINK = re.compile(r"^(.*?)[ \t]+\[\[([^\]\n]+)\]\]$")
_IDEZET = re.compile(r"^[ \t]*>[ \t]*„(.*)”[ \t]*$")
_FEJ = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*$")
_WIKI_CEL = re.compile(r"\[\[([^\]|#]+)")


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


@dataclass(frozen=True)
class Horgony:
    """Az állítás forrás-linkje: `cel` a vault-relatív út `.md` nélkül (videónál a média útja kiterjesztéssel), `alcel` a
    `#` utáni rész (`^blokk`, fejezet címe vagy `t=<mp>`), `felirat` a link felirata."""
    cel: str
    alcel: str | None = None
    felirat: str = FELIRAT

    def link(self) -> str:
        return f"[[{self.cel}{'#' + self.alcel if self.alcel else ''}|{self.felirat}]]"


@dataclass
class Allitas:
    szoveg: str
    horgony: Horgony
    idezet: str                      # a jegyzet szó szerinti mondata (nem a modell változata)
    id: str = ""                     # `a1`, `a2`, … (a sorszámból; az elemző tölti)


@dataclass
class Osszefoglalo:
    azon: str
    szint: str
    forrasok: list[str]              # vault-relatív utak `.md` nélkül
    cim: str
    modell: str
    keszult: str
    allitasok: list[Allitas] = field(default_factory=list)


@dataclass
class Elemzes:
    osszefoglalo: Osszefoglalo | None
    hibak: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------- horgonyok

def ido_felirat(mp: int) -> str:
    """Másodperc → `m:ss` (egy óra fölött `h:mm:ss`)."""
    mp = max(int(mp), 0)
    o, mp = divmod(mp, 3600)
    p, mp = divmod(mp, 60)
    return f"{o}:{p:02d}:{mp:02d}" if o else f"{p}:{mp:02d}"


def ido_horgony(cel: str, mp: int) -> Horgony:
    """A 29(d) időkód-link: `[[videó#t=<másodperc>|m:ss]]`."""
    return Horgony(cel, f"t={int(mp)}", ido_felirat(mp))


def horgony_ertek(belso: str) -> Horgony:
    """Egy `[[cél#alcél|felirat]]` belseje → `Horgony`."""
    cel, _, felirat = belso.partition("|")
    cel, _, alcel = cel.partition("#")
    return Horgony(nfc(cel.strip()), nfc(alcel.strip()) or None, felirat.strip() or FELIRAT)


# ---------------------------------------------------------------------- név, azonosító

def cim_of(ut: str) -> str:
    """A jegyzet címe: a fájlnév a `NN[A-Z] - ` sorszám-előtag nélkül (a séma H1-szabálya szerint)."""
    return re.sub(r"^\d+[A-Z]? - ", "", nfc(ut.rsplit("/", 1)[-1]).removesuffix(".md"))


def keszult(mikor: datetime) -> str:
    return mikor.strftime("%Y-%m-%d %H%M")


def uj_azon(mikor: datetime, veletlen: str | None = None) -> str:
    """`OSSZ-ÉÉÉÉHHNN-ÓÓPPMM-<6 hex>`: a C26b gépi-írás körének azonosítója."""
    return f"OSSZ-{mikor.strftime('%Y%m%d-%H%M%S')}-{veletlen or secrets.token_hex(3)}"


def kisero_nev(forras_ut: str, vault_utak, sajat: str | None = None, utotag: str = UTOTAG) -> str:
    """Az összefoglaló jegyzet neve (kiterjesztés nélkül): a kártya `kiseronev`-e (45. döntés: egy ütközési szabály) az
    összefoglaló utótagjával. Mappa-szintnél a `forras_ut` a mappa útja `.md`-vel kiegészítve."""
    return _kiseronev(forras_ut, vault_utak, sajat, utotag)


def kisero_ut(forras_ut: str, vault_utak, mappa: str = ALAP_MAPPA, sajat: str | None = None,
              utotag: str = UTOTAG) -> str:
    """A kísérőjegyzet vault-relatív útja: `<mappa>/<név>.md`."""
    return f"{mappa.strip('/')}/{kisero_nev(forras_ut, vault_utak, sajat, utotag)}.md"


# ---------------------------------------------------------------------- író

def _yaml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _egysor(s: str, mit: str) -> str:
    s = (s or "").replace("\r", "").strip()
    if not s or "\n" in s:
        raise ValueError(f"{mit}: egyetlen, nem üres sor kell")
    return s


def ir_allitas(n: int, a: Allitas) -> str:
    """Egy állítás két sora: a számozott állítás a forrás-linkkel, alatta az idézet. Forrás nélküli állítás nem írható."""
    szoveg = _egysor(a.szoveg, "az állítás")
    if _TILTOTT.search(szoveg):
        raise ValueError(f"az állítás nem tartalmazhat `[[`, `]]` vagy `==` jelölést: {szoveg[:60]!r}")
    idezet = _egysor(a.idezet, "az idézet (forrás nélküli állítás nem írható)").strip("„”")
    if not a.horgony or not a.horgony.cel:
        raise ValueError("az állításnak forrása kell legyen")
    return f"{n}. {szoveg} {a.horgony.link()}\n   > „{idezet}”"


def torzs(o: Osszefoglalo) -> str:
    """Az `## Állítások` blokk (a címsorral): a kézi beillesztés (C26-TERV 10.) és az `ir` közös törzse."""
    return ALLITASOK_CIM + "\n\n" + "\n".join(ir_allitas(i, a) for i, a in enumerate(o.allitasok, 1)) + "\n"


def ir(o: Osszefoglalo) -> str:
    """A kísérőjegyzet teljes szövege: frontmatter (`Source`, `Osszefoglalas`, `Szint`, `Modell`, `Keszult` — az
    `osszefoglalo` sémaosztály sorrendje), H1 és az állítások."""
    if o.szint not in SZINTEK:
        raise ValueError(f"ismeretlen szint: {o.szint!r} ({', '.join(SZINTEK)})")
    if not AZON_RE.match(o.azon):
        raise ValueError(f"érvénytelen azonosító: {o.azon!r}")
    if not o.allitasok:
        raise ValueError("állítás nélküli összefoglaló nem írható")
    fm = ["---"]
    fm += ["Source:"] + [f"  - {_yaml_str(f'[[{nfc(s)}]]')}" for s in o.forrasok] if o.forrasok else ["Source: []"]
    fm += [f"Osszefoglalas: {o.azon}", f"Szint: {o.szint}", f"Modell: {_yaml_str(o.modell)}" if o.modell else "Modell:",
           f"Keszult: {o.keszult}" if o.keszult else "Keszult:", "---", ""]
    cim = _egysor(o.cim, "a cím")
    return "\n".join(fm) + f"\n# {cim}{CIM_UTOTAG}\n\n" + torzs(o)


# ---------------------------------------------------------------------- elemző

def _frontmatter(txt: str, e: Elemzes) -> tuple[dict, int]:
    """(a frontmatter szótára, a törzs első sorának sorszáma 0-tól)."""
    m = FM_RE.match(txt)
    if not m:
        e.hibak.append({"sor": 1, "fajta": "frontmatter_hiba", "szoveg": "nincs frontmatter"})
        return {}, 0
    try:
        adat = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as ex:
        e.hibak.append({"sor": 1, "fajta": "frontmatter_hiba", "szoveg": str(ex).splitlines()[0]})
        return {}, txt[:m.end()].count("\n")
    if not isinstance(adat, dict):
        e.hibak.append({"sor": 1, "fajta": "frontmatter_hiba", "szoveg": "a frontmatter nem szótár"})
        adat = {}
    return adat, txt[:m.end()].count("\n")


def _forrasok(adat) -> list[str]:
    if adat is None:
        return []
    ertekek = adat if isinstance(adat, list) else [adat]
    ki = []
    for x in ertekek:
        m = _WIKI_CEL.search(str(x))
        if m:
            ki.append(nfc(m.group(1).strip()))
    return ki


def elemez(txt: str, azon_tartalek: str = "OSSZ-00000000-000000-kezi") -> Elemzes:
    """Az összefoglaló-jegyzet elemzése. Nem dob. A hibakulcsok: `frontmatter_hiba`, `forras_hiany` (a `Source` üres),
    `szint_ervenytelen`, `nincs_allitas`, `allitas_forras_nelkul` (az állítás sorában nincs link), `idezet_hiany` (az
    állítás alatt nincs idézet-sor). A hibás állítás kimarad az `allitasok`-ból."""
    txt = nfc(txt).replace("\r\n", "\n")
    e = Elemzes(None)
    adat, torzs_kezd = _frontmatter(txt, e)
    torzs = "\n".join(txt.split("\n")[torzs_kezd:])
    # Azonos hossz és sorszám: tartalmi mező csak kommentmentes nézetből,
    # kódbeli szerkezeti jelek kizárása a külön kódmaszkkal.
    sorok = megjegyzes_nelkul(torzs, frontmatter=False).split("\n")
    maszk = mask_code(torzs, frontmatter=False).split("\n")
    forrasok = _forrasok(adat.get("Source"))
    if not forrasok:
        e.hibak.append({"sor": 1, "fajta": "forras_hiany", "szoveg": "a `Source` üres: az összefoglalónak forrása kell legyen"})
    szint = str(adat.get("Szint") or "jegyzet").strip()
    if szint not in SZINTEK:
        e.hibak.append({"sor": 1, "fajta": "szint_ervenytelen", "szoveg": f"ismeretlen szint: {szint!r}"})
        szint = "jegyzet"
    cim, szakaszban, allitasok = "", False, []
    i = 0
    while i < len(maszk):
        sor, mk = sorok[i], maszk[i]
        szam = torzs_kezd + i + 1
        kod = bool(sor.strip()) and not mk.strip()
        fej = None if kod else _FEJ.match(sor)
        if fej:
            szint_n, szoveg = len(fej.group(1)), nfc(fej.group(2))
            if szint_n == 1 and not cim:
                cim = szoveg.removesuffix(CIM_UTOTAG.strip()).rstrip(" —").strip()
            szakaszban = szint_n == 2 and nfc(sor).strip().startswith(ALLITASOK_CIM)
            i += 1
            continue
        m = None if kod or not szakaszban else _ELEM.match(sor)
        if not m:
            i += 1
            continue
        n, tartalom = int(m.group(1)), m.group(2)
        ml = _ELEM_LINK.match(tartalom)
        if not ml:
            e.hibak.append({"sor": szam, "fajta": "allitas_forras_nelkul", "szoveg": tartalom[:80]})
            i += 1
            continue
        mi = _IDEZET.match(sorok[i + 1]) if i + 1 < len(maszk) and maszk[i + 1].strip() else None
        if not mi or not mi.group(1).strip():
            e.hibak.append({"sor": szam, "fajta": "idezet_hiany", "szoveg": ml.group(1)[:80]})
            i += 1
            continue
        allitasok.append(Allitas(ml.group(1).strip(), horgony_ertek(ml.group(2)), mi.group(1).strip(), f"a{n}"))
        i += 2
    if not allitasok:
        e.hibak.append({"sor": 1, "fajta": "nincs_allitas", "szoveg": "nincs érvényes állítás"})
    azon = str(adat.get("Osszefoglalas") or "").strip() or azon_tartalek
    e.osszefoglalo = Osszefoglalo(azon, szint, forrasok, cim, str(adat.get("Modell") or ""),
                                  str(adat.get("Keszult") or ""), allitasok)
    return e
