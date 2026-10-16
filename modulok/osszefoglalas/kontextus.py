"""A kontextus-csomag a külső AI-nak, és a visszamásolt válasz feldolgozása (`docs/C26-TERV.md` 6. fejezet).

- `csomag`: a kijelölt jegyzetek tisztított szövege **azonosítókkal** (`J1`, `J2`, …), a külső AI szabályaival, méretkorláttal.
  **Útvonal nem kerül a csomagba** (a mappanevek tantárgyat, személyes tartalmat árulhatnak el); az azonosító → út
  leképezés helyben marad. A forrásuk (a `Source` mező) felirat szinten, útvonal nélkül szerepel.
- `valasz_feldolgoz`: a visszamásolt JSON-választ a megnevezett jegyzeten a **közös forráshűség-kapu** ellenőrzi; a forrás
  nélküli vagy kapun bukó állítás kiesik. A kimenet ugyanaz az összefoglaló formátum (`Szint: kontextus`).

Tiszta függvények: fájlt nem olvasnak, a vaultba nem írnak. Az eredmény vaultba írása a felhasználó döntése (C26-TERV 10.:
javasolt a kézi beillesztés a szerkesztő útján).
"""
from __future__ import annotations

import collections
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime

import yaml

from core.index import elemzo
from core.index.maszk import FM_RE
from modulok.kapuk import forras as KF
from modulok.kapuk import huseg as KH

from . import formatum as FM
from .formatum import Allitas, Osszefoglalo
from .lanc import Beallitas, Eredmeny, Megall, jelolt_ellenoriz, jeloltek, most, profil
from .promptok import KONTEXTUS_FEJ, PROMPT_VERZIO
from .szakaszolas import jegyzet_bemenet

_J_AZON = re.compile(r"^\s*\[?\s*J\s*(\d+)\s*\]?\s*$", re.I)
CSONKOLAS_JEL = "[… a jegyzet további részei kimaradtak]"

# --- útvonal-szűrés (A3-28): a csomagba mappa-út, abszolút út és `file:` URL nem kerülhet, kódblokkban sem
_WIKI = re.compile(r"(!?)\[\[([^\]\n]*)\]\]")
_MD_LINK = re.compile(r"(!?)\[([^\]\n]*)\]\(([^)\n]*)\)")
_FILE_URL = re.compile(r"\bfile:/{1,3}[^\s)>\]\"'`]*", re.I)
_GYOKER = r"(?:Volumes|Users|home|Library|private|System|tmp|var|opt|etc|mnt|media|Applications|root)"
# ismert gyökérnevű abszolút út: a mappanevek szóközt is tartalmazhatnak (legfeljebb 5 szó/szegmens), ezért itt a szegmenshatár a `/`
_ABS_GYOKER = re.compile(rf"(?<![\w/:.~])/{_GYOKER}/(?:[^/\s`\"<>|]+(?: [^/\s`\"<>|]+){{0,4}}/)*[^\s`\"<>|]*")
_ABS_HOME = re.compile(r"(?<![\w/:.])~/[^\s`\"<>|]*")
_ABS_ALTALANOS = re.compile(r"(?<![\w/:.~])/(?:[^\s/\\`'\"<>|]+/)+[^\s/\\`'\"<>|]*")
_ABS_WIN = re.compile(r"(?<![\w])[A-Za-z]:\\[^\s`\"<>|]*")


def _wiki_ki(m: re.Match) -> str:
    if m.group(1):                                              # beágyazás: a tartalom nem szöveg
        return ""
    cel, _, alias = m.group(2).partition("|")
    if alias.strip():
        return alias.strip()
    return cel.partition("#")[0].replace("\\", "/").rsplit("/", 1)[-1].strip()


def utak_kiszed(szoveg: str) -> str:
    """A szövegből a mappa-utas wiki-link (alias vagy a név utolsó szegmense marad), az md-link célja, a `file:` URL és az
    abszolút út (Unix, `~/`, Windows) kiesik, **kódblokkban és kódszakaszban is**. Az útvonalat a csomag nem hordozza."""
    szoveg = _WIKI.sub(_wiki_ki, szoveg)
    szoveg = _MD_LINK.sub(lambda m: "" if m.group(1) else m.group(2), szoveg)
    szoveg = _FILE_URL.sub("[fájl]", szoveg)
    for rx in (_ABS_GYOKER, _ABS_HOME, _ABS_WIN, _ABS_ALTALANOS):
        szoveg = rx.sub("[út]", szoveg)
    return szoveg


@dataclass(frozen=True)
class Jegyzet:
    ut: str          # vault-relatív, `.md`-vel
    md: str


@dataclass
class Csomag:
    szoveg: str
    azonositok: dict[str, str]                                   # J1 → vault-relatív út (helyben marad)
    benne: list[str] = field(default_factory=list)               # a csomagban szereplő azonosítók
    csonkolt: list[str] = field(default_factory=list)            # azok, amelyekből a keret miatt részek kimaradtak
    kihagyott: list[dict] = field(default_factory=list)          # {azon, ut, ok}
    karakter: int = 0


def forras_feliratok(md: str, max_db: int = 3) -> list[str]:
    """A jegyzet `Source` mezőjének felirata útvonal nélkül: `Könyv.pdf, 93. oldal` (a PDF tartalma nem kerül a csomagba)."""
    m = FM_RE.match(unicodedata.normalize("NFC", md).replace("\r\n", "\n"))
    if not m:
        return []
    try:
        adat = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return []
    forras = adat.get("Source") if isinstance(adat, dict) else None
    ki = []
    for x in (forras if isinstance(forras, list) else [forras]):
        w = re.search(r"\[\[([^\]|#]+)(?:#([^\]|]*))?", str(x or ""))
        if not w:
            continue
        nev = w.group(1).strip().rsplit("/", 1)[-1]
        oldal = re.search(r"page=(\d+)", w.group(2) or "")
        ki.append(nev + (f", {oldal.group(1)}. oldal" if oldal else ""))
    return ki[:max_db]


def _egysegek(md: str) -> list[str]:
    """A jegyzet tisztított bekezdései fejezetfejlécekkel (`## Fejezet`), a csonkolás egységei."""
    ki = []
    for sz in KF.elokeszit(md, min_karakter=1):
        if sz.cim and sz.ut:
            ki.append("## " + utak_kiszed(" › ".join(sz.ut)))
        ki += [p for p in (utak_kiszed(p).strip() for p in re.split(r"\n\s*\n", sz.szoveg)) if p]
    return ki


def _keretek(meretek: list[int], keret: int) -> list[int]:
    """Jegyzetenkénti keret: egyenlő osztás, a kisebb jegyzetek maradéka a nagyobbaké (két menetben, determinisztikusan)."""
    n = len(meretek)
    if not n:
        return []
    ki, szabad = [0] * n, keret
    maradt = sorted(range(n), key=lambda i: meretek[i])
    for k, i in enumerate(maradt):
        resz = szabad // (n - k)
        ki[i] = min(meretek[i], resz)
        szabad -= ki[i]
    return ki


def csomag(jegyzetek: list[Jegyzet], max_karakter: int = 24000, kerdes: str = "") -> Csomag:
    """A kijelölt jegyzetek csomagja. A keret a jegyzetek között arányosan oszlik (a kisebbek maradéka a nagyobbaké); ami
    nem fér, azt bekezdéshatáron vágja (félmondatot nem), és a `csonkolt` listában megnevezi."""
    if not jegyzetek:
        raise Megall("nincs kijelölt jegyzet")
    kerdes = re.sub(r"\s+", " ", kerdes or "").strip()
    fej = KONTEXTUS_FEJ.format(kerdes_resz=f" ({kerdes})" if kerdes else "")
    azon = {f"J{i}": j.ut for i, j in enumerate(jegyzetek, 1)}
    egys = {a: _egysegek(j.md) for a, j in zip(azon, jegyzetek)}
    fejlecek = {}
    for a, j in zip(azon, jegyzetek):
        forras = forras_feliratok(j.md)
        fejlecek[a] = (f"=== {a} · {FM.cim_of(j.ut)}" + (f" (forrás: {'; '.join(forras)})" if forras else "") + " ===",
                       f"=== {a} vége ===")
    # a keret a szövegre jut: levonjuk a fejet, a jegyzetenkénti fej-/láblécet, a csonkolás-jelet és a szóközöket
    rezsi = sum(len(f) + len(v) + len(CSONKOLAS_JEL) + 8 for f, v in fejlecek.values())
    keret = max(max_karakter - len(fej) - 4 - rezsi, 0)
    keretek = _keretek([sum(len(e) + 2 for e in egys[a]) for a in azon], keret)
    reszek, benne, csonkolt, kihagyott = [], [], [], []
    for (a, j), kr in zip(zip(azon, jegyzetek), keretek):
        ures = not egys[a]
        vett, hossz = [], 0
        for e in egys[a]:
            if hossz + len(e) + 2 > kr:
                break
            vett.append(e)
            hossz += len(e) + 2
        if ures or not [e for e in vett if not e.startswith("## ")]:
            kihagyott.append({"azon": a, "ut": j.ut, "ok": "ures" if ures else "nem_fer"})
            continue
        if len(vett) < len(egys[a]):
            csonkolt.append(a)
            vett.append(CSONKOLAS_JEL)
        reszek.append(fejlecek[a][0] + "\n" + "\n\n".join(vett) + "\n" + fejlecek[a][1])
        benne.append(a)
    if not benne:
        raise Megall("a megadott keretbe egyetlen jegyzet sem fér, vagy a jegyzetek üresek")
    szoveg = fej + "\n\n" + "\n\n".join(reszek) + "\n"
    return Csomag(szoveg, azon, benne, csonkolt, kihagyott, len(szoveg))


def valasz_feldolgoz(valasz: str, jegyzetek: list[Jegyzet], cim: str = "Kontextus", modell: str = "külső AI",
                     b: Beallitas | None = None, p: KH.Profil | None = None, mikor: datetime | None = None,
                     azon: str | None = None) -> Eredmeny:
    """A visszamásolt külső AI-válasz a forráshűség-kapun át. `jegyzetek`: ugyanabban a sorrendben, mint a `csomag`-nál
    (a `J<n>` azonosító a sorszám). A kapun átment állítások összefoglalóvá állnak össze (`Szint: kontextus`); az értelmezhetetlen
    válasz üres eredmény (`statisztika["nem_ertelmezheto"]`), nem kivétel. A vaultba nem ír."""
    b = b or Beallitas()
    p = p or profil()
    mikor = mikor or most()
    bemenetek = {}
    elfogadott: dict[str, list[dict]] = collections.defaultdict(list)
    sorrend: list[tuple[str, dict]] = []
    stat: collections.Counter = collections.Counter()
    elvetve: collections.Counter = collections.Counter()
    elvetett: list[dict] = []

    def bemenet(a: str):
        if a not in bemenetek:
            j = jegyzetek[int(a[1:]) - 1]
            t = elemzo.elemez(j.md)                      # az index táblái (fejezet, blokk) a core tiszta elemzőjéből
            bemenetek[a] = jegyzet_bemenet(j.md, j.ut.removesuffix(".md"), FM.cim_of(j.ut), t.fejezetek, t.blokkok,
                                           b.darab_max_karakter, b.szakasz_min_karakter, b.kihagyott_szakaszok)
        return bemenetek[a]

    lista = jeloltek(valasz)
    stat["jelolt"] = len(lista)
    if not lista:
        stat["nem_ertelmezheto"] = 1
    for j in lista:
        m = _J_AZON.match(j.forras)
        a = f"J{int(m.group(1))}" if m else None
        if not a or not 1 <= int(a[1:]) <= len(jegyzetek):
            ok = ("ismeretlen_forras", f"nincs ilyen jegyzet-azonosító: {j.forras!r}")
            rekord = None
        else:
            rekord, ok = jelolt_ellenoriz(bemenet(a), j, elfogadott[a], b, p)
        if ok:
            elvetve[ok[0]] += 1
            elvetett.append({"allitas": j.allitas, "ok": ok[0], "reszlet": ok[1]})
            continue
        elfogadott[a].append(rekord)
        sorrend.append((a, rekord))
    # a jegyzetek sorrendjében, jegyzeten belül a forráshely szerint
    sorrend.sort(key=lambda x: (int(x[0][1:]), x[1]["hely"]))
    allitasok = [Allitas(r["allitas"], r["horgony"], r["idezet"], f"a{i}") for i, (_, r) in enumerate(sorrend, 1)]
    forrasok = []
    for a, _ in sorrend:
        ut = jegyzetek[int(a[1:]) - 1].ut.removesuffix(".md")
        if ut not in forrasok:
            forrasok.append(ut)
    o = Osszefoglalo(azon or FM.uj_azon(mikor), "kontextus", forrasok, cim, modell, FM.keszult(mikor), allitasok)
    return Eredmeny(o, {**stat, "elfogadott": len(allitasok), "elvetve": dict(elvetve), "prompt_verzio": PROMPT_VERZIO},
                    elvetett, [])
