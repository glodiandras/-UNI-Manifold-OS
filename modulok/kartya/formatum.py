"""A kártya-kísérőjegyzet formátuma (`docs/C23-TERV.md` 1. fejezet): elemző, író és a kísérőjegyzet neve.

```markdown
> [!card]- Mi a mértani sorozat hányadosa?
> Az egymást követő tagok hányadosa: $q = a_{n+1}/a_n$.
> — [[Mértani sorozat#^m-3f2a]]

^c-7f3a9e21
```

- kérdés = a callout címsora; válasz = a törzs (a `> ` előtag nélkül); forrás = a törzs utolsó `> — [[…]]` sora;
- az azonosító a callout utáni külön sorban (üres sorral elválasztva, az Obsidian alakja összetett blokkhoz) vagy
  az utolsó sorának végén; a szabály a core blokkazonosító-mintája (`core.index.elemzo._BLOKK`, importálva);
- a kódkerítésben álló callout nem kártya (a core maszkja, `core.index.maszk.mask_code`).

Tiszta függvények: szöveg be, szerkezet ki; fájlt nem olvas és nem ír. Az elemző nem dob: a hibák a jelentésben.
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import unicodedata
from dataclasses import dataclass, field

import yaml

from core import kiserok
from core.index.elemzo import _BLOKK
from core.index.maszk import FM_RE, mask_code

UTOTAG = " — kártyák"
ALAP_MAPPA = kiserok.alap_mappa("kartya")   # a kísérőjegyzetek mappája, ha a `[kartya] mappa` hiányzik (a forrás: core/kiserok.py)
AZON_RE = re.compile(r"c-[A-Za-z0-9]{4,16}")
_FEJ = re.compile(r">[ \t]?\[!card\]([+-]?)[ \t]*(.*?)[ \t]*$", re.I)
_FORRAS = re.compile(r"—[ \t]+\[\[([^\]\n]+)\]\][ \t]*$")
_SORELO = re.compile(r"^>[ \t]?")


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def normal(s: str) -> str:
    """Összevetési alak: NFC, a szóközök egyre húzva, a két vég levágva."""
    return re.sub(r"\s+", " ", nfc(s)).strip()


@dataclass
class Kartya:
    kerdes: str
    valasz: str
    azon: str | None = None
    forras: str | None = None       # a forrássor link-célja: 'Mértani sorozat#^m-3f2a' (alias nélkül)
    sor: int = 0                    # a callout első sora (1-től); az írónak közömbös
    nyitas: str = "-"               # a callout jelölője: '-' (összecsukott), '+' vagy ''

    def szoveg_hash(self) -> str:
        return szoveg_hash(self.kerdes, self.valasz)


@dataclass
class Elemzes:
    kartyak: list[Kartya] = field(default_factory=list)
    hibak: list[dict] = field(default_factory=list)       # {sor, fajta, szoveg}
    source: list[str] = field(default_factory=list)       # a frontmatter `Source` linkjei (a `[[…]]` nélkül)
    modell: str = ""
    keszult: str = ""


def szoveg_hash(kerdes: str, valasz: str) -> str:
    return hashlib.sha256(f"{normal(kerdes)}\x1f{normal(valasz)}".encode("utf-8")).hexdigest()


def ujjlenyomat(kerdes: str, forras: str | None) -> str:
    """A sírkő kulcsa: a kérdés és a forrás kisbetűs, normalizált alakjából (a generálás e szerint szűr, C23b)."""
    return hashlib.sha256(f"{normal(kerdes).casefold()}\x1f{normal(forras or '').casefold()}".encode("utf-8")).hexdigest()


def uj_azon(foglalt) -> str:
    """Új, a `foglalt` halmazban nem szereplő azonosító: `c-` + 8 kisbetűs hex."""
    while True:
        a = "c-" + secrets.token_hex(4)
        if a not in foglalt:
            return a


def _link_cel(belso: str) -> str:
    return belso.split("|", 1)[0].strip()


def _frontmatter(txt: str, e: Elemzes) -> int:
    m = FM_RE.match(txt)
    if not m:
        return 0
    try:
        d = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as ex:
        e.hibak.append({"sor": 1, "fajta": "frontmatter", "szoveg": str(ex).splitlines()[0]})
        return txt[:m.end()].count("\n")
    if isinstance(d, dict):
        src = d.get("Source") or []
        src = src if isinstance(src, list) else [src]
        for s in src:
            s = str(s).strip()
            mm = re.fullmatch(r"\[\[([^\]]+)\]\]", s)
            e.source.append(_link_cel(mm.group(1)) if mm else s)
        e.modell = "" if d.get("Modell") is None else str(d.get("Modell"))
        e.keszult = "" if d.get("Keszult") is None else str(d.get("Keszult"))
    return txt[:m.end()].count("\n")


def _azon_sorvegrol(sor: str) -> tuple[str, str | None]:
    """A sor végén álló `^azon` leválasztása → (a sor nélküle, azon | None)."""
    m = _BLOKK.search(sor)
    if not m or not AZON_RE.fullmatch(m.group(1)):        # csak a kártya-azonosító (`c-…`); a többi a szöveg része
        return sor, None
    return sor[:m.start()].rstrip(), m.group(1)


def elemez(txt: str) -> Elemzes:
    """Egy kísérőjegyzet (vagy bármely `.md`) kártyái. A sorvégek `\\n`-re hozva."""
    txt = txt.replace("\r\n", "\n").replace("\r", "\n")
    e = Elemzes()
    fm_sorok = _frontmatter(txt, e)
    sorok = txt.split("\n")
    maszk = mask_code(txt).split("\n")
    i = fm_sorok
    n = len(sorok)
    while i < n:
        m = _FEJ.fullmatch(sorok[i])
        if not m or not maszk[i].lstrip().startswith(">"):
            i += 1
            continue
        kezd = i
        nyitas, kerdes = m.group(1), m.group(2)
        torzs: list[str] = []
        i += 1
        while i < n and sorok[i].startswith(">"):
            torzs.append(_SORELO.sub("", sorok[i], count=1))
            i += 1
        azon = None
        # az azonosító a callout utolsó sorának végén (a címsor is lehet az)
        if torzs:
            torzs[-1], azon = _azon_sorvegrol(torzs[-1])
        else:
            kerdes, azon = _azon_sorvegrol(kerdes)
        if azon is None:
            j = i
            while j < n and not sorok[j].strip():
                j += 1
            if j < n:
                s = sorok[j].strip()
                mm = _BLOKK.search(s)
                if mm and s == "^" + mm.group(1) and AZON_RE.fullmatch(mm.group(1)) and maszk[j].strip():
                    azon = mm.group(1)
                    i = j + 1
        while torzs and not torzs[-1].strip():
            torzs.pop()
        forras = None
        if torzs:
            fm = _FORRAS.match(torzs[-1].strip())
            if fm:
                forras = _link_cel(fm.group(1))
                torzs.pop()
                while torzs and not torzs[-1].strip():
                    torzs.pop()
        k = Kartya(kerdes=kerdes.strip(), valasz="\n".join(torzs), azon=azon, forras=forras, sor=kezd + 1,
                   nyitas=nyitas)
        if azon is None:
            e.hibak.append({"sor": kezd + 1, "fajta": "azonosito_nelkul", "szoveg": k.kerdes})
        if not k.kerdes:
            e.hibak.append({"sor": kezd + 1, "fajta": "kerdes_nelkul", "szoveg": k.azon or ""})
        e.kartyak.append(k)
    latott: set[str] = set()
    for k in e.kartyak:
        if k.azon and k.azon in latott:
            e.hibak.append({"sor": k.sor, "fajta": "duplikalt", "szoveg": k.azon})
        elif k.azon:
            latott.add(k.azon)
    return e


def ervenyes(e: Elemzes) -> list[Kartya]:
    """Az ütemezhető kártyák: van azonosító és kérdés, és az azonosító első előfordulása a jegyzetben."""
    latott: set[str] = set()
    ki = []
    for k in e.kartyak:
        if k.azon and k.kerdes and k.azon not in latott:
            latott.add(k.azon)
            ki.append(k)
    return ki


def _yaml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def ir_kartya(k: Kartya) -> str:
    """Egy kártya szövege (a callout és — ha van — a külön soros azonosító), záró sorvég nélkül."""
    if "\n" in k.kerdes or not k.kerdes.strip():
        raise ValueError("a kérdés egyetlen, nem üres sor")
    sorok = [f"> [!card]{k.nyitas} {k.kerdes.strip()}"]
    for s in k.valasz.split("\n") if k.valasz else []:
        sorok.append(f"> {s}" if s else ">")
    if k.forras:
        sorok.append(f"> — [[{k.forras}]]")
    if k.azon:
        sorok += ["", f"^{k.azon}"]
    return "\n".join(sorok)


def ir(kartyak: list[Kartya], source: list[str] = (), modell: str = "", keszult: str = "") -> str:
    """A kísérőjegyzet teljes szövege: frontmatter (`Source`, `Modell`, `Keszult` — a `kartya` sémaosztály
    sorrendje) és a kártyák, üres sorral elválasztva."""
    fm = ["---"]
    fm += ["Source:"] + [f"  - {_yaml_str(f'[[{s}]]')}" for s in source] if source else ["Source: []"]
    fm += [f"Modell: {_yaml_str(modell)}" if modell else "Modell:", f"Keszult: {keszult}" if keszult else "Keszult:",
           "---", ""]
    return "\n".join(fm) + "\n\n".join(ir_kartya(k) for k in kartyak) + "\n"


def kiseronev(forras_ut: str, vault_utak, sajat: str | None = None, utotag: str = UTOTAG) -> str:
    """A forrás kísérőjegyzetének neve (kiterjesztés nélkül), a lapos kártyamappához (45. döntés, T058).

    `vault_utak`: a vault `.md` útjai; `sajat`: a forrás már meglévő kísérőjegyzetének útja (az nem ütközik).
    Ütközés (kis-nagybetűtől függetlenül, mert a link-feloldás is az, 13. döntés): ha a forrás alapneve a vaultban
    többször áll, vagy a név egy másik jegyzeté. Sorrend: `<alap><utótag>` → `<alap> (<szülőmappa>)<utótag>` →
    `<alap> (<szülőmappa>) <4 hex><utótag>` (a hex a forrás útjából, determinisztikus)."""
    forras_ut = nfc(forras_ut)
    alap = os.path.splitext(os.path.basename(forras_ut))[0]
    sajat = nfc(sajat) if sajat else None
    tortek = [os.path.splitext(os.path.basename(nfc(u)))[0].casefold() for u in vault_utak if nfc(u) != sajat]
    azonos = sum(1 for t in tortek if t == alap.casefold()) > 1
    foglalt = set(tortek)
    szulo = os.path.basename(os.path.dirname(forras_ut))
    jeloltek = [] if azonos else [f"{alap}{utotag}"]
    if szulo:
        jeloltek.append(f"{alap} ({szulo}){utotag}")
    for j in jeloltek:
        if j.casefold() not in foglalt:
            return j
    h = hashlib.sha1(forras_ut.encode("utf-8")).hexdigest()[:4]
    return f"{alap} ({szulo}) {h}{utotag}" if szulo else f"{alap} {h}{utotag}"
