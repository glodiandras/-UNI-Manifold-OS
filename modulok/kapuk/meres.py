"""A forráshűség-kapu mérése a C18 `szoveg` aranyhalmazán (`docs/C22-KAPU-MERES.md`).

Modell nélkül, determinisztikusan (seedelt), az `arany.json`-t és a fagyasztott `forrasok/jNN.md` másolatokat csak olvassa.

**Pozitív minták** (a kapunak el kell fogadnia):
- `poz_teny`: a 299 kártyázható *tény* — az állítás a `teny`, az idézet a szó szerinti `forras`;
- `poz_kulcsresz`: a 158 *kulcsrész* — az állítás a `megnevezes`, az idézet a szó szerinti `idezet`;
- `poz_zaj_*`: a tények idézete a modell tipikus apró hibáival (kisbetű és írásjel nélkül, egy elütés, egy kihagyott szó,
  levágott szél).

**Negatív minták** (szintetikusan rontott; a kapunak el kell utasítania):
- `neg_szam`: az állítás egy számát megváltoztatjuk;
- `neg_tagadas`: az állításba „nem” kerül;
- `neg_nev_kivul`: egy tulajdonnevet a jegyzet egy másik, a mondatban nem szereplő nevére cserélünk;
- `neg_masik_forras`: ugyanazon jegyzet másik mondatának idézete;
- `neg_idegen_jegyzet`: másik jegyzet idézete;
- `neg_kitalalt`: az idézet szavainak ~35%-a véletlen szóra cserélve (nem szó szerinti).

**Leíró osztályok** (nem számítanak a döntésbe; megmutatják, mit *nem lát* a lexikai kapu): `leiro_parafrazis` (idézet
helyett az átfogalmazott állítás), `leiro_nev_belul` (névcsere a mondaton belül), `leiro_szo_belul` (tartalmi szó cseréje
egy, a mondatban álló másikra).

A küszöbrácsot a nyers mérések (`huseg.merj`) fölött járjuk be: az idézet keresése és a bizonyíték-képzés esetenként egyszer
fut. A kiválasztási szabály: a pozitív osztályokon legalább `PADLO` arány, ezen belül a negatív osztályok makró-átlagos
elutasítása a legnagyobb (döntetlennél a pozitívok átlaga); ha ez a padló egyetlen cellában sem tartható, a padló
`PADLO_LEPCSO`-nként csökken, és a riport ezt kimondja.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from collections import defaultdict
from dataclasses import dataclass
from itertools import product
from pathlib import Path

from . import forras as F
from . import huseg as H
from . import tokenek as T

REPO = Path(__file__).resolve().parents[2]
ARANY_MAPPA = REPO / "modulok" / "eval" / "szoveg"

POZITIV = ("poz_teny", "poz_kulcsresz", "poz_zaj_kisbetu", "poz_zaj_elutes", "poz_zaj_kihagy", "poz_zaj_vagott")
NEGATIV = ("neg_szam", "neg_tagadas", "neg_nev_kivul", "neg_masik_forras", "neg_idegen_jegyzet", "neg_kitalalt")
LEIRO = ("leiro_parafrazis", "leiro_nev_belul", "leiro_szo_belul")
CIMKE = {
    "poz_teny": "tény + szó szerinti forrásrész", "poz_kulcsresz": "kulcsrész megnevezése + idézete",
    "poz_zaj_kisbetu": "idézet kisbetűvel, írásjel nélkül", "poz_zaj_elutes": "idézet egy elütéssel",
    "poz_zaj_kihagy": "idézet egy kihagyott szóval", "poz_zaj_vagott": "idézet levágott szélső szóval",
    "neg_szam": "megváltoztatott szám", "neg_tagadas": "beszúrt tagadás", "neg_nev_kivul": "név cseréje a jegyzet másik nevére",
    "neg_masik_forras": "ugyanazon jegyzet másik mondata", "neg_idegen_jegyzet": "másik jegyzet idézete",
    "neg_kitalalt": "kitalált (35% cserélt szavú) idézet",
    "leiro_parafrazis": "átfogalmazott állítás mint idézet", "leiro_nev_belul": "névcsere a mondaton belül",
    "leiro_szo_belul": "szócsere a mondaton belül"}

IDEZET_KUSZOBOK = (0.70, 0.75, 0.80, 0.85, 0.90)
TAMOGATAS_KUSZOBOK = (0.3, 0.4, 0.5, 0.6, 0.7, 0.8)
PADLO = 0.90
PADLO_LEPCSO = 0.05
ELHAGYASOK = (           # (név, a kiválasztott profil módosítása): mit ér az egyes szabály
    ("teljes", {}),
    ("kényes tokenek nélkül", {"kenyes": False}),
    ("tagadás-vizsgálat nélkül", {"tagadas": "ki"}),
    ("támogatás nélkül (küszöb 0)", {"tamogatas_kuszob": 0.0}),
    ("se kényes, se tagadás", {"kenyes": False, "tagadas": "ki"}),
    ("bizonyíték: csak a talált rész", {"bizonyitek": "idezet"}),
    ("bizonyíték: a kibővített mondat", {"bizonyitek": "mondat"}),
    ("tagadás: paritás", {"tagadas": "paritas"}),
)


@dataclass
class Eset:
    osztaly: str
    jegyzet: str
    sorszam: int
    allitas: str
    idezet: str
    forras_idezet: str = ""           # az eredeti (rontatlan) szó szerinti forrásrész, ha van


@dataclass
class Halmaz:
    arany: dict
    arany_sha256: str
    forrasok: dict[str, F.ForrasSzoveg]
    esetek: list[Eset]


def _rng(mag: int, *kulcs) -> random.Random:
    return random.Random("|".join(str(k) for k in (mag, *kulcs)))


# ---------------------------------------------------------------------- rontások

_CIKK = {"a", "az", "egy"}


def _szam_csere(teny: str, biz_szamok: set[str], rng: random.Random) -> str | None:
    ms = list(re.finditer(r"\d+", teny))
    if not ms:
        return None
    m = ms[rng.randrange(len(ms))]
    n = int(m.group(0))
    for d in rng.sample((1, 2, 3, 10, 100), 5):
        uj = str(n + d)
        if uj not in biz_szamok and uj != m.group(0):
            return teny[:m.start()] + uj + teny[m.end():]
    return None


def _tagadas_beszur(teny: str) -> str | None:
    if T.tagado(teny):
        return None
    szavak = list(re.finditer(r"\S+", teny))
    if len(szavak) < 3:
        return None
    i = 1 if T.tavolsag.hajt(szavak[0].group(0).strip(".,;:")) in _CIKK else 0
    hely = szavak[i].end()
    return teny[:hely] + " nem" + teny[hely:]


def _nevek_felszin(fs: F.ForrasSzoveg) -> list[str]:
    """A jegyzet tulajdonnevei felszíni alakban (a `nevtovek` szerint, tövenként egyszer, a jegyzet sorrendjében)."""
    ki: list[str] = []
    latott: set[str] = set()
    for w, kezdo in T.nagybetus(fs.szoveg):
        t = T.to(w)
        if not kezdo and len(w) >= 3 and t in fs.nevtovek() and t not in latott:
            latott.add(t)
            ki.append(w)
    return ki


def _csere_szo(szoveg: str, regi: str, uj: str) -> str:
    return re.sub(rf"(?<![0-9A-Za-zÀ-ɏ]){re.escape(regi)}", uj, szoveg, count=1)


def _nev_csere(teny: str, fs: F.ForrasSzoveg, biz: str, belul: bool, rng: random.Random) -> str | None:
    """Az állítás egy nevét a jegyzet egy másik nevére cseréli; `belul`: az a név a bizonyítékban is áll (a kapu számára
    láthatatlan csere), különben nem."""
    nevek = [w for w, _ in T.nagybetus(teny) if len(w) >= 3 and T.to(w) in fs.nevtovek()]
    if not nevek:
        return None
    biz_tovek, teny_tovek = T.tovek(biz, stop=False), T.tovek(teny, stop=False)
    jeloltek = sorted({w for w in _nevek_felszin(fs) if T.to(w) not in teny_tovek and (T.to(w) in biz_tovek) == belul})
    return _csere_szo(teny, rng.choice(nevek), rng.choice(jeloltek)) if jeloltek else None


def _szo_csere_belul(teny: str, biz: str, rng: random.Random) -> str | None:
    teny_tovek = T.tovek(teny, stop=False)
    celok = [w for w in T.szavak(teny) if len(w) >= 5 and w.islower() and not w.isdigit()]
    forrasok = sorted({w for w in T.szavak(biz) if len(w) >= 5 and w.islower() and T.to(w) not in teny_tovek})
    if not celok or not forrasok:
        return None
    return _csere_szo(teny, rng.choice(celok), rng.choice(forrasok))


def _kisbetu(idezet: str) -> str:
    return re.sub(r"[^\w\s]", "", idezet.lower())


def _elutes(idezet: str, rng: random.Random) -> str | None:
    szavak = list(re.finditer(r"[^\W\d_]{6,}", idezet))
    if not szavak:
        return None
    m = rng.choice(szavak)
    i = rng.randrange(1, len(m.group(0)) - 1)
    c = m.group(0)[i]
    uj = rng.choice([x for x in "aeiouknrst" if x != c.lower()])
    return idezet[:m.start() + i] + uj + idezet[m.start() + i + 1:]


def _kihagy(idezet: str, rng: random.Random) -> str | None:
    szavak = idezet.split()
    if len(szavak) < 5:
        return None
    del szavak[rng.randrange(1, len(szavak) - 1)]
    return " ".join(szavak)


def _vagott(idezet: str, rng: random.Random) -> str | None:
    szavak = idezet.split()
    if len(szavak) < 6:
        return None
    return " ".join(szavak[1:] if rng.random() < 0.5 else szavak[:-1])


def _kitalalt(idezet: str, fs: F.ForrasSzoveg, rng: random.Random) -> str | None:
    szavak = idezet.split()
    helyek = [i for i, w in enumerate(szavak) if len(w) >= 4]
    if len(helyek) < 3:
        return None
    szotar = sorted({w for w in T.szavak(fs.szoveg) if len(w) >= 4})
    for i in rng.sample(helyek, min(max(2, round(0.35 * len(szavak))), len(helyek))):
        szavak[i] = rng.choice(szotar)
    return " ".join(szavak)


# ---------------------------------------------------------------------- a halmaz

def betolt(arany_mappa: Path | None = None) -> tuple[dict, str, dict[str, F.ForrasSzoveg]]:
    mappa = Path(arany_mappa or ARANY_MAPPA)
    nyers = (mappa / "arany.json").read_bytes()
    arany = json.loads(nyers)
    forrasok = {j["id"]: F.ForrasSzoveg.jegyzetbol((mappa / "forrasok" / f"{j['id']}.md").read_text(encoding="utf-8"),
                                                   cim=j["cim"]) for j in arany["jegyzetek"]}
    return arany, hashlib.sha256(nyers).hexdigest(), forrasok


def esetek_keszit(arany: dict, forrasok: dict[str, F.ForrasSzoveg], mag: int = 1, jegyzetek: int | None = None) -> list[Eset]:
    """Az összes minta (a `jegyzetek` az első N jegyzetre szűkíti: gyors tesztekhez)."""
    lista = arany["jegyzetek"][:jegyzetek] if jegyzetek else arany["jegyzetek"]
    ki: list[Eset] = []

    def uj(osztaly, j, i, allitas, idezet, eredeti=""):
        ki.append(Eset(osztaly, j["id"], i, allitas, idezet, eredeti))

    for j in lista:
        fs = forrasok[j["id"]]
        for i, k in enumerate(j["kulcsreszek"]):
            uj("poz_kulcsresz", j, i, k["megnevezes"], k["idezet"], k["idezet"])
        for i, t in enumerate(j["tenyek"]):
            teny, forras = t["teny"], t["forras"]
            uj("poz_teny", j, i, teny, forras, forras)
            for osztaly, f in (("poz_zaj_kisbetu", lambda r: _kisbetu(forras)), ("poz_zaj_elutes", lambda r: _elutes(forras, r)),
                               ("poz_zaj_kihagy", lambda r: _kihagy(forras, r)), ("poz_zaj_vagott", lambda r: _vagott(forras, r))):
                z = f(_rng(mag, osztaly, j["id"], i))
                if z and z != forras:
                    uj(osztaly, j, i, teny, z, forras)
            talalat = fs.keres(forras, 0.85)
            if talalat is None:
                continue
            mondat = fs.mondat(*talalat.hely, max_k=600)
            biz = H.bizonyitek_szoveg(fs, talalat, "mondat+cim")
            r = _rng(mag, "neg", j["id"], i)
            if (a := _szam_csere(teny, T.szamok(biz), r)):
                uj("neg_szam", j, i, a, forras, forras)
            if (a := _tagadas_beszur(teny)):
                uj("neg_tagadas", j, i, a, forras, forras)
            if (a := _nev_csere(teny, fs, biz, False, r)):
                uj("neg_nev_kivul", j, i, a, forras, forras)
            if (a := _nev_csere(teny, fs, biz, True, r)):
                uj("leiro_nev_belul", j, i, a, forras, forras)
            if (a := _szo_csere_belul(teny, biz, r)):
                uj("leiro_szo_belul", j, i, a, forras, forras)
            if (z := _kitalalt(forras, fs, r)):
                uj("neg_kitalalt", j, i, teny, z, forras)
            uj("leiro_parafrazis", j, i, teny, teny, forras)
            masok = []                              # más mondat, amely az állítást sem támogatja (nem rejtett pozitív)
            teny_tovek = T.tovek(teny)
            for i2, t2 in enumerate(j["tenyek"]):
                t2h = fs.keres(t2["forras"], 0.85) if i2 != i else None
                if t2h and fs.mondat(*t2h.hely, max_k=600) != mondat \
                        and len(T.lefedett(teny_tovek, T.tovek(t2["forras"], stop=False))) < 0.5 * len(teny_tovek):
                    masok.append(t2["forras"])
            if masok:
                uj("neg_masik_forras", j, i, teny, r.choice(masok), forras)
            masik = [x for x in arany["jegyzetek"] if x["id"] != j["id"]]
            for _ in range(5):
                if not masik:
                    break
                idegen = r.choice(r.choice(masik)["tenyek"])["forras"]
                if fs.keres(idegen, 0.70) is None:
                    uj("neg_idegen_jegyzet", j, i, teny, idegen, forras)
                    break
    return ki


def halmaz(arany_mappa: Path | None = None, mag: int = 1, jegyzetek: int | None = None) -> Halmaz:
    arany, sha, forrasok = betolt(arany_mappa)
    return Halmaz(arany, sha, forrasok, esetek_keszit(arany, forrasok, mag, jegyzetek))


def merj_esetek(h: Halmaz, mondat_max: int = 600) -> list[tuple[Eset, H.Meres]]:
    return [(e, H.merj(h.forrasok[e.jegyzet], e.allitas, e.idezet, mondat_max)) for e in h.esetek]


# ---------------------------------------------------------------------- kiértékelés

def kiertekel(merdek: list[tuple[Eset, H.Meres]], p: H.Profil) -> dict[str, dict]:
    """Osztályonként {n, elfogad, arany}: az `arany` az elfogadott esetek aránya."""
    db: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for e, m in merdek:
        db[e.osztaly][0] += 1
        db[e.osztaly][1] += H.dont(m, p).ok
    return {o: {"n": n, "elfogad": ok, "arany": ok / n if n else None} for o, (n, ok) in db.items()}


def pontszam(ered: dict[str, dict]) -> dict:
    """A kiválasztás mutatói: a pozitív osztályok minimuma és átlaga, a negatív osztályok makró-elutasítása."""
    poz = [ered[o]["arany"] for o in POZITIV if o in ered and ered[o]["n"]]
    neg = [1 - ered[o]["arany"] for o in NEGATIV if o in ered and ered[o]["n"]]
    return {"poz_min": min(poz) if poz else 0.0, "poz_atlag": sum(poz) / len(poz) if poz else 0.0,
            "neg_makro": sum(neg) / len(neg) if neg else 0.0}


def racs() -> list[H.Profil]:
    return [H.Profil(idezet_min_szo=1, idezet_max_szo=None, idezet_kuszob=ik, tamogatas_kuszob=tk, bizonyitek=b, kenyes=k, tagadas=t)
            for ik, tk, b, k, t in product(IDEZET_KUSZOBOK, TAMOGATAS_KUSZOBOK, H.BIZONYITEKOK, (True, False), H.TAGADAS_MODOK)]


def valaszt(merdek: list[tuple[Eset, H.Meres]]) -> tuple[H.Profil, dict, float, list[tuple[H.Profil, dict]]]:
    """A kiválasztott profil, a mutatói, a teljesített padló és a teljes rács (profil, mutatók)."""
    cellak = [(p, pontszam(kiertekel(merdek, p))) for p in racs()]
    padlo = PADLO
    while padlo > 0:
        jok = [(p, s) for p, s in cellak if s["poz_min"] >= padlo]
        if jok:
            # döntetlennél: a pozitívok átlaga, majd a szigorúbb beállítások (kényes be, tagadás be, magasabb küszöb)
            jo = max(jok, key=lambda x: (round(x[1]["neg_makro"], 6), round(x[1]["poz_atlag"], 6), x[0].kenyes,
                                         x[0].tagadas != "ki", x[0].idezet_kuszob, x[0].tamogatas_kuszob))
            return jo[0], jo[1], padlo, cellak
        padlo = round(padlo - PADLO_LEPCSO, 4)
    jo = max(cellak, key=lambda x: x[1]["poz_min"] + x[1]["neg_makro"])
    return jo[0], jo[1], 0.0, cellak


def profil_szoveg(p: H.Profil) -> str:
    return (f'idezet_kuszob = {p.idezet_kuszob}\ntamogatas_kuszob = {p.tamogatas_kuszob}\nbizonyitek = "{p.bizonyitek}"\n'
            f'kenyes = {str(p.kenyes).lower()}\ntagadas = "{p.tagadas}"')


def fragmens_hosszak(arany: dict) -> dict:
    """Az arany szó szerinti forrásrészeinek szószám-eloszlása (a fogyasztói hossz-határokhoz)."""
    hosszak = sorted(len(T.szavak(t["forras"])) for j in arany["jegyzetek"] for t in j["tenyek"])
    n = len(hosszak)
    return {"n": n, "min": hosszak[0], "median": hosszak[n // 2], "max": hosszak[-1],
            "alatt_3": sum(1 for h in hosszak if h < 3), "alatt_4": sum(1 for h in hosszak if h < 4),
            "felett_45": sum(1 for h in hosszak if h > 45), "felett_60": sum(1 for h in hosszak if h > 60)}


def minta(merdek: list[tuple[Eset, H.Meres]], p: H.Profil, darab: int = 10) -> dict[str, list]:
    """A döntés két oldaláról `darab`-nyi eset a K101 átnézéshez: a küszöbhöz legközelebb elfogadottak és elutasítottak."""
    def tavolsag(m: H.Meres, v: H.Verdikt) -> float:
        t = m.talalat
        if t is None:
            return 9.0
        b = m.bizonyitek[p.bizonyitek]
        return min(abs(t.hasonlosag - p.idezet_kuszob), abs(b.lefedettseg - p.tamogatas_kuszob))
    elfogadott, elutasitott = [], []
    for e, m in merdek:
        if e.osztaly.startswith("leiro"):
            continue
        v = H.dont(m, p)
        (elfogadott if v.ok else elutasitott).append((tavolsag(m, v), e, m, v))
    def legkozelebbi(lista):
        """Tényenként a küszöbhöz legközelebbi eset (egy tény öt zajos változata ne töltse meg a lapot), távolság szerint."""
        legjobb: dict[tuple[str, int], tuple] = {}
        for x in sorted(lista, key=lambda x: (x[0], x[1].osztaly, x[1].jegyzet, x[1].sorszam)):
            legjobb.setdefault((x[1].jegyzet, x[1].sorszam), x)
        return sorted(legjobb.values(), key=lambda x: (x[0], x[1].jegyzet, x[1].sorszam))[:darab]
    return {"elfogadott": legkozelebbi(elfogadott), "elutasitott": legkozelebbi(elutasitott)}


# ---------------------------------------------------------------------- riport

def ablacio(merdek: list[tuple[Eset, H.Meres]], p: H.Profil) -> list[dict]:
    """A kiválasztott profil változatai egy-egy szabály nélkül: mutatók és a negatív osztályok elutasítása."""
    ki = []
    for nev, mod in ELHAGYASOK:
        v = H.Profil(**{**p.__dict__, **mod})
        ered = kiertekel(merdek, v)
        ki.append({"nev": nev, **pontszam(ered), "elutasitas": {o: 1 - ered[o]["arany"] for o in NEGATIV if o in ered}})
    return ki


def _szazalek(x: float | None) -> str:
    return "—" if x is None else f"{100 * x:.1f}%"


def riport(h: Halmaz, merdek: list[tuple[Eset, H.Meres]], p: H.Profil, mutatok: dict, padlo: float, parancs: str,
           datum: str) -> str:
    ered = kiertekel(merdek, p)
    hossz = fragmens_hosszak(h.arany)
    sor = [
        "# A közös forráshűség-kapu mérése (C22a)", "",
        f"Generálva: `{parancs}` · {datum} · determinisztikus (mag 1), modell nélkül.", "",
        f"**Adat**: a C18 `szoveg` aranyhalmaz (`{h.arany.get('verzio')}`, állapot: `{h.arany.get('allapot')}`, "
        f"sha256 `{h.arany_sha256[:16]}…`), {len(h.arany['jegyzetek'])} fagyasztott jegyzet, {len(h.esetek)} minta. "
        "A halmaz jóváhagyása (K27) után a mérést újra kell futtatni; a küszöbök a `config/os.toml` `[kapuk]` szakaszában élnek.", "",
        "## Eredmény", "",
        "A kiválasztott beállítás (`config/os.toml`):", "", "```toml", "[kapuk]", profil_szoveg(p), "```", "",
        f"- **pozitív minták** (a kapunak el kell fogadnia): a legkisebb osztály {_szazalek(mutatok['poz_min'])}, az átlag "
        f"{_szazalek(mutatok['poz_atlag'])};",
        f"- **negatív minták** (el kell utasítania): a hat osztály makró-átlaga {_szazalek(mutatok['neg_makro'])};",
        f"- a kiválasztási padló: a pozitív osztályokon legalább {_szazalek(padlo)}"
        + (" (az elsőként teljesülő fok a 90%-ról lépcsőzve)." if padlo >= PADLO else " — **a 90%-os padló nem volt tartható**, lásd lent."), "",
        "### Osztályonként", "",
        "| osztály | mi ez | minta | elfogadva | elutasítva |", "|---|---|---:|---:|---:|"]
    for o in POZITIV + NEGATIV + LEIRO:
        if o in ered:
            e = ered[o]
            jel = {"poz": "elvárás: elfogad", "neg": "elvárás: elutasít", "lei": "leíró, nem számít a döntésbe"}[o[:3]]
            sor.append(f"| `{o}` | {CIMKE[o]} ({jel}) | {e['n']} | {_szazalek(e['arany'])} | {_szazalek(1 - e['arany'])} |")
    sor += ["", "## Mit ér az egyes szabály", "",
            "A kiválasztott beállítás változatai (a többi küszöb változatlan). A negatív oszlopok az **elutasítás** arányát mutatják.", "",
            "| változat | pozitív min | pozitív átlag | negatív makró | szám | tagadás | név | másik mondat | idegen jegyzet | kitalált idézet |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for a in ablacio(merdek, p):
        e = a["elutasitas"]
        sor.append(f"| {a['nev']} | {_szazalek(a['poz_min'])} | {_szazalek(a['poz_atlag'])} | {_szazalek(a['neg_makro'])} | "
                   + " | ".join(_szazalek(e.get(o)) for o in NEGATIV) + " |")
    sor += ["", "A tanulság: a puszta szó-lefedettség a számcserét, a tagadást és a névcserét alig fogja meg; ezeket a **kényes tokenek** és a "
            "**tagadás-vizsgálat** adja. A bizonyíték kibővítése (mondat, jegyzetcím, fejezetcímek) a pozitívokon nyer, mert a tények "
            "alanya gyakran a címben áll, nem a szó szerinti forrásrészben.", "",
            "## Mit nem lát a kapu", "",
            "Lexikai vizsgálat, ezért **a szókészletet nem változtató hamis állítást nem fogja meg**:", "",
            f"- névcsere a mondaton belül (`leiro_nev_belul`): {_szazalek(ered.get('leiro_nev_belul', {}).get('arany'))} átmegy;",
            f"- tartalmi szó cseréje a mondat egy másik szavára (`leiro_szo_belul`): {_szazalek(ered.get('leiro_szo_belul', {}).get('arany'))} átmegy;",
            "- szinonima- és ellentétcsere, a viszony megfordítása („A előzte meg B-t” ↔ „B előzte meg A-t”): a szavak ugyanazok;",
            "- a tagadás beszúrása olyan mondatba, amely már tartalmaz tagadást (`neg_tagadas` maradék);",
            "- az idézet-nélküli átfogalmazás elfogadása: az átfogalmazott állítás mint „idézet” "
            f"{_szazalek(ered.get('leiro_parafrazis', {}).get('arany'))}-ban átmegy (ott, ahol a `teny` közel szó szerinti).", "",
            "Ezt a hézagot a láncok modell-alapú „vak ellenőrzése” (a modell a kérdésre a forrásmondatból, a válasz nélkül felel) és "
            "a rétegzett emberi minta (C19) fedi; a kapu a **gyors, olcsó, modell nélküli** első szűrő.", "",
            "## Az idézetek hossza", "",
            f"Az arany {hossz['n']} szó szerinti forrásrésze: legrövidebb {hossz['min']}, medián {hossz['median']}, leghosszabb "
            f"{hossz['max']} szó; 3 szónál rövidebb {hossz['alatt_3']}, 4-nél rövidebb {hossz['alatt_4']}, 45-nél hosszabb "
            f"{hossz['felett_45']}, 60-nál hosszabb {hossz['felett_60']}. A fogyasztói hossz-határok (`[kapuk.<fogyasztó>]`) ezért nem "
            "szűkítik a mért pozitívokat. A mért halmaz a tény egy klauzáját idézi; a modell hosszabb mondatokat is idézhet.", "",
            "## Korlátok", "",
            "- A pozitív minták **optimisták**: az arany tények a forrásmondathoz közeli, az emberi vázlatban készült állítások, a modell "
            "átfogalmazottabb. A kártya (C23b), a kvíz és az összefoglaló (C22b/C26) elfogadási aránya a saját aranyhalmazán újramérendő.",
            "- A negatív minták szintetikusak (szám, tagadás, név, mondat, idézet rontása); a valódi modellhiba eloszlása más lehet.",
            "- Az `arany.json` állapota `vazlat` (K27). A kulcsrész-megnevezések (`poz_kulcsresz`) összefoglaló címkék, ezért ez az osztály "
            "a legalacsonyabb.",
            "- A küszöbök egy 20 jegyzetes halmazra állnak; a jóváhagyás után a mérés megismétlendő, a K101 emberi mintával együtt.", "",
            "## Reprodukálás", "", "```bash", parancs, "```", ""]
    return "\n".join(sor)


def minta_lap(merdek: list[tuple[Eset, H.Meres]], p: H.Profil, h: Halmaz, darab: int = 10) -> str:
    """A K101 átnézési lapja: a döntés két oldaláról `darab`-nyi eset, üres „jó-e a döntés” mezővel."""
    m = minta(merdek, p, darab)
    sor = ["# A forráshűség-kapu mintapárjai (K101)", "",
           "Minden pár a küszöbhöz legközelebb eső esetek közül való. Írd a „Jó a döntés?” mezőbe: **igen** (a kapu jól döntött) vagy "
           "**nem**; a „nem” esetekből látszik, melyik szabályt kell lazítani vagy szigorítani.", ""]
    for cim, kulcs in (("Elfogadott párok", "elfogadott"), ("Elutasított párok", "elutasitott")):
        sor += [f"## {cim}", ""]
        for i, (_, e, mm, v) in enumerate(m[kulcs], 1):
            fs = h.forrasok[e.jegyzet]
            mondat = fs.mondat(*mm.talalat.hely, max_k=600) if mm.talalat else "—"
            sor += [f"### {i}. `{e.osztaly}` · {e.jegyzet} #{e.sorszam}", "",
                    f"- **Állítás**: {e.allitas}", f"- **Idézet**: {e.idezet}", f"- **A forrásmondat**: {mondat}",
                    f"- **Döntés**: {'elfogad' if v.ok else 'elutasít'}; bukott szabály: {', '.join(v.okok) or '—'}; "
                    f"hasonlóság {v.hasonlosag:.2f}, lefedettség "
                    f"{'—' if v.lefedettseg is None else f'{v.lefedettseg:.2f}'}"
                    + (f"; hiányzó: {', '.join(v.hianyzo)}" if v.hianyzo else ""),
                    "- **Jó a döntés?** ", ""]
    return "\n".join(sor)


def futtat(mag: int = 1, jegyzetek: int | None = None, arany_mappa: Path | None = None):
    """A teljes mérés: halmaz, nyers mérések, kiválasztás → (halmaz, merdek, profil, mutatók, padló)."""
    h = halmaz(arany_mappa, mag, jegyzetek)
    merdek = merj_esetek(h)
    p, mutatok, padlo, _ = valaszt(merdek)
    return h, merdek, p, mutatok, padlo
