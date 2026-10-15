"""A kvízlánc modell nélküli része: szakaszolás, jelöltek szétszedése, kapuk, kiválasztás (a legacy `kviz.py` portja).

Egy jelölt kérdés négy, egymástól független kapun megy át (a modell nem igazságforrás, I7):

1. **mechanikus** (`mechanikus.kapu`): szerkezet, jelölés, nincs „mindegyik / egyik sem”, nincs kiszivárgás;
2. **forráshűség** (a közös `modulok/kapuk`): az idézet a jegyzetben áll (a kvízbe a *jegyzet* mondata kerül, nem a modell
   változata, és a talált hely adja a szakaszt és a visszajelzés linkjét), a helyes válasz az idézetből következik
   (lefedettség, szám, név, tagadás); a kérdés a `kontextus`: a képleteken kívüli számai és nevei is a bizonyítékban állnak;
3. **rossz válaszok** (C22b; modell nélkül, a mérés pontozójával közös: `rossz_valasz_hiba`): egy rossz válasz sem
   következhet az idézetből úgy, hogy a forrásmondat ne különböztetné meg a helyestől (`tobb_helyes`), és legfeljebb egy lehet
   a jegyzettől idegen kitöltő (`hihetetlen`);
4. **vak ellenőrzés**: ugyanaz a modell a kulcs nélkül, más sorrendben válaszol; ha mást tart helyesnek, a kérdés kiesik —
   a hibás kulcs a legdrágább hiba, mert tévképzetet tanít.

A kiesett jelöltek okonként a statisztikában maradnak (I3). **A modell két hívható mögött áll** (`generalo`,
`ellenorzo`: `(prompt, max_tokens) -> szöveg`): a C22b köti rájuk a workert, a gyorsítótárat és a D9-et (`lanc.py`); a tesztek
forgatókönyvezett álmodellt adnak. A vaultba ez a modul nem ír.
"""
from __future__ import annotations

import collections
import hashlib
import random
import re
import time
from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import Callable

from modulok.kapuk import forras as KF
from modulok.kapuk import huseg as KH
from modulok.kapuk import tokenek as KT

from . import formatum as FM
from . import mechanikus as MK
from .mechanikus import BETUK, Jelolt
from .promptok import ELLENORZO_PROMPT, GENERALO_PROMPT, PROMPT_VERZIO

ModellHivas = Callable[[str, int], str]


class Megall(Exception):
    """A kvíz nem készülhet el, vagy a kérés hibás — az üzenet a gazdának szól."""


@dataclass(frozen=True)
class Beallitas:
    """A `[kviz]` szakasz (az `os.toml`); az alapértékek a legacy `calibration.json` `kviz` blokkjából."""
    kerdes_alap: int = 10
    kerdes_min: int = 3
    kerdes_max: int = 30
    tulgeneralas: float = 1.6                 # ennyiszer több jelöltet kérünk, mint ahány kérdés kell (a kapuk elvetnek)
    karakter_per_kerdes: int = 150
    darab_max_karakter: int = 2200
    szakasz_min_karakter: int = 20
    hivas_max_kerdes: int = 5
    token_per_kerdes: int = 230
    idezet_max_karakter: int = 420            # a visszajelzésben mutatott mondat legfeljebb ennyi karakter
    duplikat_jaccard: float = 0.6
    kerulendo_max: int = 12
    engedett_jelek: tuple[str, ...] = MK.ENGEDETT_JELEK


_MEZOK = {f.name for f in fields(Beallitas)}


def beallitas(cfg) -> Beallitas:
    """A `[kviz]` szakaszból; ismeretlen kulcs hiba (a `mappa` a végpontoké)."""
    adat = dict(cfg.section("kviz"))
    adat.pop("mappa", None)
    ismeretlen = sorted(set(adat) - _MEZOK)
    if ismeretlen:
        raise ValueError(f"[kviz]: ismeretlen kulcs: {', '.join(ismeretlen)}")
    if "engedett_jelek" in adat:
        adat["engedett_jelek"] = tuple(adat["engedett_jelek"])
    return Beallitas(**adat)


def most() -> datetime:
    return datetime.now()


# ---------------------------------------------------------------------- szakaszok, darabok

def darabok(szakaszok: list[KF.Szakasz], max_k: int = 2200) -> list[dict]:
    """A generálás egységei: egymás utáni szakaszok `max_k` karakterig összevonva, a túl hosszú szakasz bekezdéshatáron
    darabolva. Egy darab = egy vagy több modellhívás. → [{szoveg, szakaszok: [sorszám], karakter}]"""
    egysegek: list[tuple[int, str]] = []
    for si, s in enumerate(szakaszok):
        if len(s.szoveg) <= max_k:
            egysegek.append((si, s.szoveg))
            continue
        cur = ""
        for bek in re.split(r"\n\s*\n", s.szoveg):
            if cur and len(cur) + len(bek) + 2 > max_k:
                egysegek.append((si, cur))
                cur = ""
            cur = (cur + "\n\n" + bek).strip() if cur else bek[: max_k * 2]
        if cur:
            egysegek.append((si, cur))
    ki: list[dict] = []
    cur = None
    for si, t in egysegek:
        fej = " › ".join(szakaszok[si].ut) or "Bevezetés"
        blokk = f"[{fej}]\n{t}"
        if cur and len(cur["szoveg"]) + len(blokk) + 2 <= max_k:
            cur["szoveg"] += "\n\n" + blokk
            cur["szakaszok"].append(si)
            cur["karakter"] += len(t)
        else:
            cur = {"szoveg": blokk, "szakaszok": [si], "karakter": len(t)}
            ki.append(cur)
    return ki


def kapacitas(d: dict, b: Beallitas) -> int:
    """Hány kérdést bír el egy darab: `karakter_per_kerdes`-enként egy, felfelé kerekítve, legalább kettő."""
    return max(2, -(-d["karakter"] // b.karakter_per_kerdes))


def kiosztas(darabok_: list[dict], n: int, b: Beallitas) -> list[int]:
    """Hány jelöltet kérünk darabonként: a szöveghossz arányában, összesen ~`tulgeneralas`·n, de egy darab sem kaphat
    többet, mint amennyit a hossza elbír."""
    cel = max(n, round(n * b.tulgeneralas))
    ossz = sum(d["karakter"] for d in darabok_) or 1
    kap = [kapacitas(d, b) for d in darabok_]
    k = [min(kap[i], max(1, round(cel * d["karakter"] / ossz))) for i, d in enumerate(darabok_)]
    sorrend = sorted(range(len(darabok_)), key=lambda i: -darabok_[i]["karakter"])
    while sum(k) < cel and any(k[i] < kap[i] for i in sorrend):
        for i in sorrend:
            if sum(k) >= cel:
                break
            if k[i] < kap[i]:
                k[i] += 1
    return k


# ---------------------------------------------------------------------- a modell válaszának olvasása

_KERDES_JEL = re.compile(r"(?im)^\s*(?:\d+\s*[.)]\s*)?(?:#+\s*)?KÉRDÉS\s*\d*\s*[:.)]\s*")
_OPCIO = re.compile(r"^(?:[-*•]\s*)?\(?([ABCD])\s*[).:]\s*(.*)$")
_HELYES = re.compile(r"(?i)^HELYES(?:\s+VÁLASZ)?\s*[:.]\s*\(?([ABCD])\b")
_IDEZET = re.compile(r"(?i)^IDÉZET\s*[:.]\s*(.*)$")
_MAGY = re.compile(r"(?i)^MAGYARÁZAT\s*[:.]\s*(.*)$")


def szetszed(szoveg: str) -> list[Jelolt]:
    """A generáló válasz → jelöltek. Tűrő: a számozást, a félkövér jelölést és a „Helyes válasz: B)” alakot is
    elfogadja; ítéletet nem hoz."""
    t = szoveg.replace("\r", "").replace("**", "")
    ki: list[Jelolt] = []
    for blokk in _KERDES_JEL.split(t)[1:]:
        kerdes, valaszok, helyes, idezet, magy = [], {}, None, [], []
        mezo = "kerdes"
        for ln in blokk.split("\n"):
            s = ln.strip()
            if not s:
                continue
            m = _OPCIO.match(s)
            if m and mezo in ("kerdes", "valasz") and m.group(1) not in valaszok:
                valaszok[m.group(1)] = m.group(2).strip()
                mezo = "valasz"
                continue
            m = _HELYES.match(s)
            if m:
                helyes, mezo = m.group(1).upper(), "helyes"
                continue
            m = _IDEZET.match(s)
            if m:
                idezet, mezo = [m.group(1)], "idezet"
                continue
            m = _MAGY.match(s)
            if m:
                magy, mezo = [m.group(1)], "magy"
                continue
            if mezo == "kerdes":
                kerdes.append(s)
            elif mezo == "idezet":
                idezet.append(s)
            elif mezo == "magy":
                magy.append(s)
        ki.append(Jelolt(kerdes=" ".join(kerdes).strip(), valaszok=valaszok, helyes=helyes,
                         idezet=" ".join(idezet).strip().strip("„”\"'«»“ "), magyarazat=" ".join(magy).strip()))
    return ki


def betu(valasz: str) -> str | None:
    """Az ellenőrző válasz betűje (A–D), vagy `None`. A magyar névelő („A helyes…”) nem betűválasz."""
    t = (valasz or "").replace("*", "").strip()
    m = re.match(r"^\(?([ABCD])(?=[).:,]|\s*(?:$|\n))", t)
    if m:
        return m.group(1)
    m = re.match(r"^([BCD])\b", t)
    if m:
        return m.group(1)
    m = re.search(r"(?i:válasz|helyes)[^A-Za-z]{0,15}\(?([ABCD])(?:[).:,]|\s|$)", t)
    return m.group(1) if m else None


def _tohalmaz(s: str) -> set[str]:
    return {w.lower()[:6] for w in re.findall(r"[^\W_]+", FM.nfc(s)) if len(w) >= 3}


def jaccard(a: str, b: str) -> float:
    a, b = _tohalmaz(a), _tohalmaz(b)
    return len(a & b) / len(a | b) if a and b else 0.0


# ---------------------------------------------------------------------- kiválasztás, keverés

def _kevert(kulcs: str, n: int = 4) -> list[int]:
    """Determinisztikus keverés (a kérdés szövegéből): a modell helyzeti torzítását (a helyes válasz gyakran az A vagy a B)
    semlegesíti, és ugyanarra a kérdésre mindig ugyanazt adja."""
    r = random.Random(hashlib.sha1(kulcs.encode("utf-8")).hexdigest())
    p = list(range(n))
    r.shuffle(p)
    return p


def _kerdes_blokk(kerdes: str, valaszok: list[str]) -> str:
    return f"KÉRDÉS: {kerdes}\n" + "\n".join(f"{BETUK[i]}) {v}" for i, v in enumerate(valaszok))


def valaszt(elfogadott: list[dict], n: int) -> list[dict]:
    """Ha több ment át, mint kell: szakaszonként körbe (a kvíz a jegyzet egészét fedje), majd a jegyzet sorrendjében — a
    kvíz a jegyzet szerkezetét követi. Az elemek `si` kulcsa a szakasz sorszáma."""
    csoport: dict[int, list[tuple[int, dict]]] = collections.defaultdict(list)
    for i, q in enumerate(elfogadott):
        csoport[q["si"]].append((i, q))
    sor: list[tuple[int, dict]] = []
    kor = 0
    while len(sor) < min(n, len(elfogadott)):
        for si in sorted(csoport):
            if kor < len(csoport[si]) and len(sor) < n:
                sor.append(csoport[si][kor])
        kor += 1
    return [q for _, q in sorted(sor, key=lambda x: (x[1]["si"], x[0]))]


# ---------------------------------------------------------------------- a lánc

@dataclass
class Eredmeny:
    kviz: FM.Kviz
    statisztika: dict
    elvetett: list[dict] = field(default_factory=list)           # {kerdes, ok, reszlet}


def cim_of(ut: str) -> str:
    """A jegyzet címe: a fájlnév a `NN[A-Z] - ` sorszám-előtag nélkül (a séma H1-szabálya szerint)."""
    return re.sub(r"^\d+[A-Z]? - ", "", FM.nfc(ut.rsplit("/", 1)[-1]).removesuffix(".md"))


_KAPU_OK = {"kotott": "idezet", "hossz": "idezet", "tamogatas": "tamogatas", "kenyes": "kenyes", "tagadas": "tagadas"}


def _forras_kapu(fs: KF.ForrasSzoveg, j: Jelolt, profil: KH.Profil, b: Beallitas):
    """A közös forráshűség-kapu a jelöltre: (ok, reszlet, találat) — az ok a statisztika kulcsa (`idezet` a legacy neve)."""
    v = KH.ellenoriz(fs, j.valaszok[j.helyes], j.idezet, profil, kontextus=j.kerdes)
    if v.ok:
        return None, None, v
    elso = v.okok[0]
    return _KAPU_OK[elso], f"{', '.join(v.okok)}" + (f" ({', '.join(v.hianyzo)})" if v.hianyzo else ""), v


# ---------------------------------------------------------------------- a rossz válaszok (C22m, C22b)
#
# „Pontosan egy helyes válasz” lexikai közelítése: a rossz válasz nem következhet az idézetből (`tobb_helyes`), és a rossz
# válaszok ne legyenek a jegyzettől idegen kitöltők (`hihetetlen`). A C19 rétegzett mintája (docs/MERES-2026-10-07.md 6.)
# szerint a puszta kapu-próba (a rossz válasz is átmegy a támogatottsági vizsgálaton) alulbecsül: a tipikus rossz válasz
# **ugyanazokból a szavakból** áll, mint a helyes, de tagad, megfordít vagy egy szót cserél — a lefedettség ≥ 0,5 küszöbe ezt
# átengedi, és a fejezetcímek (a bizonyíték része) minden opciót tartalmaznak. Ezért a rossz válasz csak akkor „helyes is”, ha a
# helyestől **a forrásmondat alapján nem különböztethető meg** (`megkulonbozteti`).

HIHETO_KUSZOB = 0.3         # a rossz válasz tartalmi tövei közül ennyi arány álljon a jegyzetben, a kérdésben vagy a helyes válaszban
HIHETETLEN_MAX = 1          # ennyi jegyzeten kívüli rossz válasz még elmegy (a világtudásból vett tévedés rendes); több: kitöltő
_SZAKASZ_RE = re.compile(r"\$\$(.+?)\$\$|\$(.+?)\$|`([^`\n]+)`", re.S)
_TAGADO_SZOK = frozenset({"nem", "sem", "soha", "senki", "semmi", "sehol", "semmilyen", "semelyik", "nelkul", "ne", "se",
                          "nincs", "nincsen", "sincs", "sincsen"})
_FOSZTO = ("tlan", "tlen")  # fosztóképző (-tlan/-tlen/-talan/-telen): `tagolatlan`, `szervetlen` — a tagadás szóalakja
_FOSZTO_MIN = 7


def _tomor(s: str) -> str:
    """A képlet/kód összevetéshez: szóköz és a LaTeX-térköz (`\\ `, `\\,`) nélkül."""
    return re.sub(r"\\[ ,;:!]|\s+", "", s)


def kepletszakaszok(s: str) -> list[str]:
    """A `$…$`, `$$…$$` és `` `…` `` szakaszok tömör alakja (a válasz képlete és kódja)."""
    return [_tomor(next(g for g in m.groups() if g is not None)) for m in _SZAKASZ_RE.finditer(s or "")]


def _szovegresz(s: str) -> str:
    return _SZAKASZ_RE.sub(" ", s or "")


def tagadasok(s: str) -> int:
    """A szöveg tagadásainak száma: tagadószó (a `nincs` is) és fosztóképzős szó (`nincs tagolatlan` = 2)."""
    return sum(1 for w in KT.szavak(s)
               if (h := KT.tavolsag.hajt(w)) in _TAGADO_SZOK or (len(h) >= _FOSZTO_MIN and h.endswith(_FOSZTO)))


def _sorrend(s: str, kozos: set[str]) -> list[str]:
    ki: list[str] = []
    for w in KT.szavak(s):
        t = KT.to(w)
        if t in kozos and t not in ki:
            ki.append(t)
    return ki


_KIZARO = frozenset({"csak", "kizarolag", "egyedul", "egyetlen", "mindig", "sosem", "soha", "semmikor"})
_HATAR = ",;.:)]}"


def _keplet_a_mondatban(sz: str, mondat: str) -> bool:
    """A rossz válasz tömör képlete/kódja szó szerint a mondatban: egy mondatbeli szakasz (vagy annak `,`/`;` szerinti
    része) egyezik vele; szakasz nélküli mondatban határon álló előfordulás. A puszta részsztring nem elég: a
    `cos(α−β)=cosαcosβ` a `…=cosαcosβ+sinαsinβ` eleje, de nem ugyanaz."""
    for msz in kepletszakaszok(mondat):
        if sz == msz or sz in re.split(r"[,;]", msz):
            return True
    m = _tomor(_SZAKASZ_RE.sub(lambda x: " ", mondat)) if kepletszakaszok(mondat) else _tomor(mondat)
    i = m.find(sz)
    while i >= 0:
        if (i == 0 or m[i - 1] in _HATAR + "(") and (i + len(sz) == len(m) or m[i + len(sz)] in _HATAR):
            return True
        i = m.find(sz, i + 1)
    return False


def _szo_a_mondatban(eredeti: str, m_szavak: set[str]) -> bool:
    """A rossz válasz egy saját szava a mondatban: a betűszó (`HTTPS`) pontosan; a hosszú (≥ 9 betűs) szó 6, a rövidebb 5 betűs
    előtaggal (`mellérendelő` ≠ `mellékmondat`); a 4 betűs mondatbeli szó ragozott alakja (`hang` → `hangot`), de összetett
    szó nem (`hanghullám` ≠ `hang`)."""
    w = KT.tavolsag.hajt(eredeti)
    if eredeti.isupper() and len(eredeti) >= 2:
        return w in m_szavak
    k = min(len(w), 5 if len(w) < 9 else 6)
    return any(m.startswith(w[:k]) and len(m) >= k for m in m_szavak) or \
        any(len(m) == 4 and w.startswith(m) and len(w) <= 7 for m in m_szavak)


def _tartalmi(szo: str) -> bool:
    h = KT.tavolsag.hajt(szo)
    return len(h) >= 3 and not h.isdigit() and h not in KT.FUGGVENYSZOK and h not in _TAGADO_SZOK


def megkulonbozteti(rossz: str, helyes: str, mondat: str) -> str | None:
    """A forrásmondat megkülönbözteti-e a rossz választ a helyestől: az ok szövege, vagy `None` (a rossz válasz a mondat
    alapján a helyessel egyenértékű lehet → `tobb_helyes`). Az ok (sorrendben):

    1. **képlet** — a rossz válasz egy képlete/kódja (tömörítve) sem a helyesben, sem a mondatban nem áll
       (`$W = Q_1 + Q_2$` a `W = Q_1 - Q_2` mondatnál);
    2. **saját szó** — a rossz válasz egy tartalmi szava vagy száma, amely a helyesben nincs, a mondatban sincs (a fejezetcím
       nem számít: ott minden opció szerepel);
    3. **tagadás** — a két válasz tagadásainak száma (tagadószó, fosztóképző) eltér: a mondat a helyest támogatja, a rossz az ellentéte;
    4. **kizáró szó** — a rossz válasz szűkít (`csak`, `kizárólag`, `mindig`), a helyes és a mondat nem;
    5. **hiány / sorrend** — saját szó nélkül (a rossz a helyes szavaiból áll): a helyes egy, a mondatban álló tartalmi szavát
       elhagyja, vagy a közös szavak sorrendje más — megfordított viszony (`a nehézségi erő nulla, a súlyerő mg` ↔ `a
       nehézségi erő mg, a súlyerő nulla`)."""
    h_szak = set(kepletszakaszok(helyes))
    for sz in kepletszakaszok(rossz):
        if sz and sz not in h_szak and not _keplet_a_mondatban(sz, mondat):
            return f"képlete nincs a mondatban: {sz[:40]}"
    r_txt, h_txt = _szovegresz(rossz), _szovegresz(helyes)
    r_tovek = KT.tovek(r_txt)
    h_szavak = {KT.tavolsag.hajt(w) for w in KT.szavak(h_txt)}
    m_szavak = {KT.tavolsag.hajt(w) for w in KT.szavak(mondat)}
    sajat = [w for w in KT.szavak(r_txt) if _tartalmi(w) and not _szo_a_mondatban(w, h_szavak)]
    hianyzik = sorted({KT.to(w) for w in sajat if not _szo_a_mondatban(w, m_szavak)})
    szamok = sorted(KT.szamok(r_txt) - KT.szamok(h_txt) - KT.szamok(mondat))
    if hianyzik or szamok:
        return "saját szava nincs a mondatban: " + ", ".join((hianyzik + szamok)[:4])
    if tagadasok(r_txt) != tagadasok(h_txt):
        return "a tagadása eltér a helyesétől"
    r_kiz = {KT.tavolsag.hajt(w) for w in KT.szavak(r_txt)} & _KIZARO
    if r_kiz - {KT.tavolsag.hajt(w) for w in KT.szavak(h_txt)} - m_szavak:
        return "szűkít (" + ", ".join(sorted(r_kiz)) + "), a helyes és a mondat nem"
    if not sajat:
        r_szavak = {KT.tavolsag.hajt(w) for w in KT.szavak(r_txt)}
        elhagy = sorted({KT.to(w) for w in KT.szavak(h_txt)
                         if _tartalmi(w) and not _szo_a_mondatban(w, r_szavak) and _szo_a_mondatban(w, m_szavak)})
        if elhagy:
            return "a helyes egy, a mondatban álló elemét elhagyja: " + ", ".join(elhagy[:3])
        kozos = r_tovek & KT.tovek(h_txt)
        a, b = _sorrend(r_txt, kozos), _sorrend(h_txt, kozos)
        if len(a) >= 2 and a != b:
            return "a helyes szavai más sorrendben (megfordítás)"
    return None


def _tovek_union(fs: KF.ForrasSzoveg, j: Jelolt) -> set[str]:
    return KT.tovek(fs.szoveg, stop=False) | KT.tovek(j.kerdes, stop=False) | KT.tovek(j.valaszok[j.helyes], stop=False)


def rossz_valasz_hiba(fs: KF.ForrasSzoveg, j: Jelolt, profil: KH.Profil, v: KH.Verdikt) -> tuple[str, str] | None:
    """A három rossz válasz vizsgálata a helyes válasz kapuja (`v`: annak ítélete, a talált hellyel) után: `(kód, ok)`, vagy
    `None`. `tobb_helyes`: egy rossz válasz is átmegy ugyanazon az idézeten a közös kapun, ÉS a forrásmondat nem különbözteti
    meg a helyestől; `hihetetlen`: `HIHETETLEN_MAX`-nál több rossz válasz tartalmi tövei nem állnak a jegyzetben, a kérdésben
    vagy a helyes válaszban."""
    ismert, idegen = None, []
    mondat = fs.mondat(v.hely[0], v.hely[1], profil.mondat_max_karakter) if v.hely else ""
    for b in BETUK:
        if b == j.helyes:
            continue
        rossz = j.valaszok[b]
        m = KH.merj(fs, rossz, j.idezet, profil.mondat_max_karakter, kontextus=j.kerdes)
        if KH.dont(m, profil).ok and megkulonbozteti(rossz, j.valaszok[j.helyes], mondat) is None:
            return "tobb_helyes", f"a(z) {b}) válasz is következik az idézetből: {rossz[:50]}"
        tovek = KT.tovek(rossz)               # tartalmi szó nélküli válasz (szám, képlet): nincs szókészlet-bizonyíték
        if tovek:
            ismert = _tovek_union(fs, j) if ismert is None else ismert
            if len(KT.lefedett(tovek, ismert)) / len(tovek) < HIHETO_KUSZOB:
                idegen.append(f"{b}) {rossz[:40]}")
    if len(idegen) > HIHETETLEN_MAX:
        return "hihetetlen", ("a rossz válaszok szavai nem állnak a jegyzetben, a kérdésben vagy a helyes válaszban: "
                              + "; ".join(idegen))
    return None


def general(forras_md: str, forras_ut: str, generalo: ModellHivas, ellenorzo: ModellHivas, n: int | None = None,
            modell: str = "", azon: str | None = None, korabbi=(), b: Beallitas | None = None,
            profil: KH.Profil | None = None, mikor: datetime | None = None, log=lambda s: None,
            halad=lambda arany: None, allj=lambda: False) -> Eredmeny:
    """Egy kvíz a jegyzetből (a vaultba NEM ír). `forras_ut`: a forrásjegyzet vault-relatív útja (`.md`-vel); `korabbi`: az
    ehhez a jegyzethez már készült kvízek kérdései (az új nem ismétli őket); `profil`: a forráshűség-kapu `kviz` profilja
    (alap: a `KH.Profil()` alapértékei — az éles hívó az `os.toml`-ból tölti). `halad`: a darabok feldolgozott aránya (0–1);
    `allj`: igaz → a következő modellhívás előtt `Megall` (a leállítás; a gyorsítótárral a futás onnan folytatható)."""
    b = b or Beallitas()
    profil = profil or KH.Profil(nev="kviz", idezet_min_szo=4, idezet_max_szo=60)
    n = int(n or b.kerdes_alap)
    if not b.kerdes_min <= n <= b.kerdes_max:
        raise Megall(f"a kérdések száma {b.kerdes_min} és {b.kerdes_max} között legyen")
    if not modell:
        raise Megall("nincs megadva modell")
    t0 = time.time()
    mikor = mikor or most()
    cim = cim_of(forras_ut)
    fs = KF.ForrasSzoveg.jegyzetbol(forras_md, cim=cim)
    szak = KF.elokeszit(forras_md, min_karakter=b.szakasz_min_karakter)
    if not szak:
        raise Megall("a jegyzetnek nincs olyan szöveges része, amelyből kérdezni lehet")
    darab = darabok(szak, b.darab_max_karakter)
    ki = kiosztas(darab, n, b)
    log(f"[kvíz] {cim}: {len(szak)} szakasz, {len(darab)} darab, {sum(ki)} jelölt kérve {n} kérdéshez · {modell}")
    if (kap := sum(kapacitas(d, b) for d in darab)) < n:
        log(f"[kvíz] a jegyzet rövid: kb. {kap} kérdést bír el — a kvíz rövidebb lehet")

    korabbi = list(korabbi)
    stat: collections.Counter = collections.Counter()
    elvetve: collections.Counter = collections.Counter()
    elvetett: list[dict] = []
    elfogadott: list[dict] = []

    for di, d in enumerate(darab):
        maradt = ki[di]
        sajat: list[str] = []
        while maradt > 0:
            if allj():
                raise Megall("leállítva (a következő modellhívás előtt)")
            k = min(maradt, b.hivas_max_kerdes)
            maradt -= k
            kerul = (korabbi + [x["q"].kerdes for x in elfogadott] + sajat)[-b.kerulendo_max:]
            kerulendo = ("- Ezeket a kérdéseket már feltettük, ne ismételd és ne fogalmazd át őket:\n"
                         + "\n".join(f"  - {x}" for x in kerul) + "\n") if kerul else ""
            valasz = generalo(GENERALO_PROMPT.format(k=k, cim=cim, szoveg=d["szoveg"], kerulendo=kerulendo),
                              b.token_per_kerdes * k + 150)
            stat["hivas"] += 1
            jeloltek = szetszed(valasz)[:k + 2]
            stat["jelolt"] += len(jeloltek)
            for j in jeloltek:
                sajat.append(j.kerdes)
                ok = MK.kapu(j, b.engedett_jelek)
                talalat = None
                if not ok:
                    kod, reszlet, talalat = _forras_kapu(fs, j, profil, b)
                    ok = (kod, reszlet) if kod else None
                if not ok:
                    ok = rossz_valasz_hiba(fs, j, profil, talalat)       # pontosan egy helyes, hihető rossz válaszok
                if not ok:
                    if any(jaccard(j.kerdes, x["q"].kerdes) >= b.duplikat_jaccard for x in elfogadott):
                        ok = ("duplikatum", "egy már elfogadott kérdés ismétlése")
                    elif any(jaccard(j.kerdes, x) >= b.duplikat_jaccard for x in korabbi):
                        ok = ("korabbi_kvizben", "egy korábbi kvízben már szerepelt")
                if not ok:
                    if allj():
                        raise Megall("leállítva (a következő modellhívás előtt)")
                    ok = _vak_ellenorzes(j, d, ellenorzo, stat)
                if ok:
                    elvetve[ok[0]] += 1
                    elvetett.append({"kerdes": j.kerdes, "ok": ok[0], "reszlet": ok[1]})
                    continue
                elfogadott.append(_kerdes_rekord(j, talalat, fs, b))
        halad((di + 1) / len(darab))
    stat["elfogadott"] = len(elfogadott)
    valasztott = valaszt(elfogadott, n)
    if len(valasztott) < b.kerdes_min:
        raise Megall(f"csak {len(valasztott)} kérdés ment át a kapukon ({stat['jelolt']} jelöltből; elvetve: "
                     + ", ".join(f"{a} {c}" for a, c in elvetve.most_common()) + ") — a kvíz nem készült el")
    kerdesek = []
    for i, x in enumerate(valasztott, 1):
        q = x["q"]
        q.id = f"k{i}"
        kerdesek.append(q)
    fedett = sorted({x["si"] for x in valasztott})
    kviz = FM.Kviz(azon=azon or "KVIZ-" + mikor.strftime("%Y%m%d-%H%M%S"), forras=forras_ut.removesuffix(".md"), cim=cim,
                   modell=modell, keszult=FM.keszult(mikor), kerdesek=kerdesek)
    st = {**stat, "valasztott": len(kerdesek), "kert": n, "elvetve": dict(elvetve), "szakasz": len(fs.szakaszok),
          "lefedett_szakasz": len(fedett), "mp": round(time.time() - t0, 1), "prompt_verzio": PROMPT_VERZIO}
    log(f"[kvíz] kész: {len(kerdesek)} kérdés ({stat['jelolt']} jelöltből, elfogadva {len(elfogadott)}) · elvetve: "
        + (", ".join(f"{a} {c}" for a, c in elvetve.most_common()) or "—") + f" · {len(fedett)}/{len(fs.szakaszok)} szakasz")
    return Eredmeny(kviz, st, elvetett)


def _vak_ellenorzes(j: Jelolt, d: dict, ellenorzo: ModellHivas, stat: collections.Counter) -> tuple[str, str] | None:
    """3. kapu: a modell a kulcs NÉLKÜL, más sorrendben válaszol a részletből. `None` = átment."""
    eredeti = [j.valaszok[b] for b in BETUK]
    p = _kevert(j.kerdes + "|ellenőrzés")
    sorrend = [eredeti[i] for i in p]
    valasz = ellenorzo(ELLENORZO_PROMPT.format(szoveg=d["szoveg"], kerdes_blokk=_kerdes_blokk(j.kerdes, sorrend)), 12)
    stat["hivas"] += 1
    b = betu(valasz)
    if b is None:
        return "ellenorzes_ertelmezhetetlen", f"az ellenőrző válasz nem betű: {valasz.strip()[:40]!r}"
    if p[BETUK.index(b)] != BETUK.index(j.helyes):
        return "ellenorzes", f"vakon mást tart helyesnek: {sorrend[BETUK.index(b)][:60]}"
    return None


def _kerdes_rekord(j: Jelolt, v: KH.Verdikt, fs: KF.ForrasSzoveg, b: Beallitas) -> dict:
    """Az elfogadott kérdés: a válaszok determinisztikusan keverve, az idézet a JEGYZET mondata, a szakasz a találaté."""
    eredeti = [j.valaszok[x] for x in BETUK]
    p = _kevert(j.kerdes)
    sz = fs.szakaszok[v.szakasz]
    q = FM.Kerdes(id="", kerdes=j.kerdes, valaszok=[eredeti[i] for i in p], helyes=p.index(BETUK.index(j.helyes)),
                  magyarazat=j.magyarazat, idezet=fs.mondat(v.hely[0], v.hely[1], b.idezet_max_karakter),
                  szakasz=sz.cim, horgony=sz.horgony)
    return {"q": q, "si": v.szakasz}
