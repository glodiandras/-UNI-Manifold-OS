"""A kártya-lánc modell nélküli része (C23b; `docs/C23-TERV.md` 5. fejezet): mennyiség, darabok, jelöltek, kapuk.

Egy jelölt kártya (kérdés, válasz, a jegyzet szó szerinti forrásmondata) öt, egymástól független kapun megy át (a modell nem
igazságforrás, I7):

1. **kötött + igaz** — a közös forráshűség-kapu (`modulok/kapuk`, `[kapuk.kartya]` profil; „egy kapu, nem négy”): a
   forrásmondat a jegyzetben áll, a **válasz** (az állítás) abból következik (lefedettség, szám, név, tagadás); a **kérdés** a
   `kontextus`: a képleteken kívüli számai és nevei is a bizonyítékban állnak;
2. **atomi** — legfeljebb `valasz_max_szo` szó, egy kérdőjel, nincs felsorolás (a C18 kártya-definíciója, `docs/C18-ARANYHALMAZOK.md`);
3. **egyértelmű** — a kérdés önmagában érthető (nem utal a jegyzetre, nem névmással kezd), nem árulja el a választ;
4. **vak önellenőrzés** — második hívás csak a kérdéssel és a forrásmondattal, a válasz nélkül; a modell válaszának tövei a
   kártya válaszának legalább `vak_kuszob` részét fedik (a számok is egyeznek), különben a kérdés nem egyértelmű vagy a kulcs
   hibás — a hibás kártya tévképzetet tanít;
5. **duplikáció** — karakter-3gram Jaccard ≥ `duplikat_jaccard` egy már elfogadott, egy meglévő vagy egy **törölt** kártya
   kérdésével (a törölt kártya nem generálódik újra), illetve a sírkő-ujjlenyomat egyezése.

A kiesett jelöltek okonként a statisztikában maradnak (I3). **A modell két hívható mögött áll** (`generalo`, `ellenorzo`:
`(prompt, max_tokens) -> szöveg`): az éles lánc (`lanc.py`) a workert köti rájuk, a tesztek forgatókönyvezett álmodellt. A
válasz elemzése a mérés pontozójának tűrésével megy (`kimenet.kulcs_turo`, C19). A vaultba ez a modul nem ír.
"""
from __future__ import annotations

import collections
import re
import time
import unicodedata
from dataclasses import dataclass, field, fields
from typing import Callable

from modulok.eval.kozos import kimenet
from modulok.kapuk import forras as KF
from modulok.kapuk import huseg as KH
from modulok.kapuk import tokenek

from . import formatum

ModellHivas = Callable[[str, int], str]
PROMPT_VERZIO = "kartya-1"

GENERALO_PROMPT = (
    "Készíts {k} tanulókártyát az alábbi jegyzetrészletből, magyarul. Egy kártya egyetlen tényt kérdez. A kérdés "
    "önmagában érthető legyen (ne utaljon a jegyzetre vagy a szövegkörnyezetre), és ne árulja el a választ; a válasz rövid "
    "(legfeljebb 12 szó). Mindegyik kártyához add meg a jegyzet SZÓ SZERINTI mondatát, amelyből a válasz következik.\n"
    "{kerulendo}"
    'Csak JSON-t adj vissza, ebben az alakban: [{{"kerdes": "…", "valasz": "…", "forras": "…"}}]\n\n'
    "JEGYZET ({cim}):\n{szoveg}")
ELLENORZO_PROMPT = (
    "Válaszolj a kérdésre röviden (legfeljebb 12 szóval), KIZÁRÓLAG az alábbi mondat alapján. Ha a mondatból nem "
    "válaszolható meg, írd azt, hogy: NEM TUDOM.\n\nMONDAT: {forras}\nKÉRDÉS: {kerdes}\nVÁLASZ:")

_UTALAS = re.compile(r"\b(a jegyzet|a szöveg|a fenti|az alábbi|az előző|a következő|fentebb|lentebb|az említett)\b", re.I)
_NEVMAS_ELEJEN = re.compile(r"^(ez|ezt|ezek|az|azt|azok|ő|ők|itt|ott|ekkor|akkor)\b", re.I)
_DEFINICIO = re.compile(r"\b(nevez\w*|jelenti|jelöli|jelöljük|definí\w*|azt mondjuk|amely\w*|ahol)\b", re.I)
_MONDAT = re.compile(r"(?<=[.!?])\s+|\n+")
_NEM_TUDOM = re.compile(r"nem\s+tudom|nem\s+válaszolható|nem\s+derül\s+ki", re.I)


class Megall(Exception):
    """A kártyák nem készülhetnek el, vagy a kérés hibás — az üzenet a felhasználónak szól."""


@dataclass(frozen=True)
class Beallitas:
    """A `[kartya.generalas]` szakasz (az `os.toml`)."""
    max_kartya: int = 30                 # jegyzetenként legfeljebb (kézi „Kártyák ebből”)
    auto_max_kartya: int = 10            # az automatikus mód jegyzetenként és körönként legfeljebb ennyit ad (a koordinátor döntése)
    suruseg: float = 0.5                 # tényes mondatonként ennyi kártya
    tulgeneralas: float = 1.6            # ennyiszer több jelöltet kérünk (a kapuk elvetnek)
    darab_max_karakter: int = 2200
    szakasz_min_karakter: int = 20
    hivas_max_kartya: int = 8
    token_per_kartya: int = 110
    valasz_max_szo: int = 12
    vak_kuszob: float = 0.5              # a vak válasz tövei a kártya válaszának legalább ennyi részét fedik
    vak_max_token: int = 60
    duplikat_jaccard: float = 0.8        # karakter-3gram Jaccard a kérdésekre
    kerulendo_max: int = 12
    kihagyott_szakaszok: tuple[str, ...] | None = field(default=None, compare=False)   # nem a `[kartya.generalas]` kulcsa: a `[kapuk] kihagyott_szakaszok` (None: az alap)


_MEZOK = {f.name for f in fields(Beallitas)} - {"kihagyott_szakaszok"}


def beallitas(cfg) -> Beallitas:
    adat = dict(cfg.section("kartya", "generalas"))
    ismeretlen = sorted(set(adat) - _MEZOK)
    if ismeretlen:
        raise ValueError(f"[kartya.generalas]: ismeretlen kulcs: {', '.join(ismeretlen)}")
    return Beallitas(**adat, kihagyott_szakaszok=KF.kihagyott_szakaszok(cfg))


def profil(cfg=None) -> KH.Profil:
    """A forráshűség-kapu `kartya` profilja (config nélkül: a profil alapértékei és a 3–60 szavas idézet)."""
    return KH.profil(cfg, "kartya") if cfg is not None else KH.Profil(nev="kartya", idezet_min_szo=3, idezet_max_szo=60)


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s or "")


# ---------------------------------------------------------------------- mennyiség a sűrűségből

def tenyes(mondat: str) -> bool:
    """Tényes mondat: szám, képlet, definíció-minta vagy tulajdonnév (mondat közbeni nagybetűs szó) áll benne."""
    if re.search(r"\d|\$|=", mondat) or _DEFINICIO.search(mondat):
        return True
    return any(not kezdo and len(w) >= 3 for w, kezdo in tokenek.nagybetus(mondat))


def mondatai(md: str, kihagy: tuple[str, ...] | None = None) -> list[str]:
    """A jegyzet tisztított mondatai (a forráshűség-kapu előkészítésével: kód, frontmatter, gép írta szakaszok nélkül)."""
    ki = []
    for sz in KF.elokeszit(md, kihagy=kihagy):
        ki += [m.strip() for m in _MONDAT.split(sz.szoveg) if len(m.strip()) >= 3]
    return ki


def mennyiseg(md: str, b: Beallitas, automatikus: bool = False, csak: set[str] | None = None) -> int:
    """Hány kártya kell: a tényes mondatok × `suruseg`, legfeljebb `max_kartya` (automatikus módban `auto_max_kartya`).
    `csak`: a módosult jegyzet új mondatai (normalizált, kisbetűs alak, a `core.automatika.mondatok` szerint) — csak ezek számítanak."""
    db = 0
    for m in mondatai(md, b.kihagyott_szakaszok):
        if csak is not None and re.sub(r"\s+", " ", nfc(m)).strip().casefold() not in csak:
            continue
        db += tenyes(m)
    felso = b.auto_max_kartya if automatikus else b.max_kartya
    return max(0, min(felso, round(db * b.suruseg)))


def darabok(szakaszok: list[KF.Szakasz], max_k: int) -> list[dict]:
    """A generálás egységei (a kvíz darabolásával azonos): → [{szoveg, karakter}]."""
    from modulok.kviz import generalas as KG
    return KG.darabok(szakaszok, max_k)


def kiosztas(darab: list[dict], cel: int) -> list[int]:
    """Jelöltek darabonként a szöveghossz arányában (legalább egy, összesen ~`cel`)."""
    if not darab or cel <= 0:
        return [0] * len(darab)
    ossz = sum(d["karakter"] for d in darab) or 1
    k = [max(1, round(cel * d["karakter"] / ossz)) for d in darab]
    while sum(k) > cel and max(k) > 1:
        k[k.index(max(k))] -= 1
    return k


# ---------------------------------------------------------------------- a modell válasza

@dataclass
class Jelolt:
    kerdes: str
    valasz: str
    forras: str


def szetszed(valasz: str) -> list[Jelolt]:
    """A generáló válasza → jelöltek (tűrő: kerítés, burok, elcsúszott kulcs — `kulcs_turo`, a mérés pontozójával azonos)."""
    ki = []
    for x in kimenet.kulcs_turo(kimenet.lista_kinyer(valasz, ("kerdes",)), ("kerdes", "valasz", "forras")):
        if not isinstance(x, dict):
            continue
        s = lambda k: re.sub(r"\s+", " ", nfc(x.get(k) if isinstance(x.get(k), str) else str(x.get(k) or ""))).strip()  # noqa: E731
        ki.append(Jelolt(s("kerdes"), s("valasz"), s("forras").strip("„”\"'«»“ ")))
    return ki


# ---------------------------------------------------------------------- kapuk

def atomi(j: Jelolt, b: Beallitas) -> str | None:
    szo = tokenek.szavak(j.valasz)
    if not szo:
        return "ures_valasz"
    if len(szo) > b.valasz_max_szo:
        return "hosszu_valasz"
    if j.kerdes.count("?") != 1:
        return "nem_egy_kerdes"
    if ";" in j.valasz or "\n" in j.valasz or j.valasz.count(",") > 2:
        return "felsorolas"
    return None


def egyertelmu(j: Jelolt) -> str | None:
    if len(tokenek.szavak(j.kerdes)) < 3:
        return "rovid_kerdes"
    if _UTALAS.search(j.kerdes) or _NEVMAS_ELEJEN.search(j.kerdes):
        return "kontextusfuggo"
    vt, kt = tokenek.tovek(j.valasz), tokenek.tovek(j.kerdes)
    if vt and vt <= kt:
        return "elarulja"
    return None


def harmasok(s: str) -> set[str]:
    t = re.sub(r"\s+", " ", re.sub(r"[^\w ]", " ", nfc(s).casefold())).strip()
    return {t[i:i + 3] for i in range(max(0, len(t) - 2))}


def jaccard3(a: str, b: str) -> float:
    x, y = harmasok(a), harmasok(b)
    return len(x & y) / len(x | y) if x and y else 0.0


def vak_egyezes(vak: str, valasz: str) -> float:
    """A vak válasz mennyire fedi a kártya válaszát: a válasz tövei (vagy jelei) közül a vak válaszban állók aránya; a válasz
    számainak mind szerepelnie kell (különben 0)."""
    if not vak or _NEM_TUDOM.search(vak):
        return 0.0
    if not tokenek.szamok(valasz) <= tokenek.szamok(vak):
        return 0.0
    vt = tokenek.tovek(valasz) or tokenek.jelek(valasz)
    if not vt:
        return 0.0
    bt = tokenek.tovek(vak, stop=False) | tokenek.jelek(vak)
    return len(tokenek.lefedett(vt, bt) if tokenek.tovek(valasz) else vt & bt) / len(vt)


# ---------------------------------------------------------------------- a lánc

@dataclass
class Kartyajelolt:
    kerdes: str
    valasz: str
    forras_mondat: str               # a JEGYZET mondata (nem a modell változata)
    idezet: str                      # a talált forrásrész szövege (a horgony helyének kereséséhez)
    szakasz: int | None = None
    horgony: str | None = None       # a szakasz fejezet-horgonya (tartalék link, ha a bekezdés nem kap blokkazonosítót)


@dataclass
class Eredmeny:
    kartyak: list[Kartyajelolt]
    statisztika: dict
    elvetett: list[dict] = field(default_factory=list)


def _kerulendo(lista: list[str], b: Beallitas) -> str:
    lista = lista[-b.kerulendo_max:]
    return ("Ezeket a kérdéseket már feltettük, ne ismételd és ne fogalmazd át őket:\n"
            + "\n".join(f"- {x}" for x in lista) + "\n") if lista else ""


def general(md: str, cim: str, generalo: ModellHivas, ellenorzo: ModellHivas, n: int, *, meglevo: tuple[str, ...] = (),
            sirkovek: frozenset[str] = frozenset(), forras_link: str = "", b: Beallitas | None = None,
            p: KH.Profil | None = None, log=lambda s: None, allj=lambda: False) -> Eredmeny:
    """Legfeljebb `n` kártya a jegyzetből (a vaultba NEM ír). `meglevo`: a meglévő és a törölt kártyák kérdései (a jegyzet
    kísérőjegyzetéből és a tanulási adatbázisból); `sirkovek`: a törölt kártyák ujjlenyomatai (`formatum.ujjlenyomat`);
    `forras_link`: a forrásjegyzet link-célja horgony nélkül (a sírkő-ujjlenyomat a horgony nélküli célra is egyezik)."""
    b = b or Beallitas()
    p = p or profil()
    t0 = time.time()
    stat: collections.Counter = collections.Counter()
    elvetve: collections.Counter = collections.Counter()
    elvetett: list[dict] = []
    elfogadott: list[Kartyajelolt] = []
    if n <= 0:
        return Eredmeny([], {"kert": 0, "hivas": 0, "jelolt": 0, "elfogadott": 0, "elvetve": {}, "mp": 0.0,
                             "prompt_verzio": PROMPT_VERZIO})
    fs = KF.ForrasSzoveg.jegyzetbol(md, cim=cim, kihagy=b.kihagyott_szakaszok)
    szak = KF.elokeszit(md, min_karakter=b.szakasz_min_karakter, kihagy=b.kihagyott_szakaszok)
    if not szak:
        raise Megall("a jegyzetnek nincs olyan szöveges része, amelyből kártya készülhet")
    darab = darabok(szak, b.darab_max_karakter)
    ki = kiosztas(darab, max(n, round(n * b.tulgeneralas)))
    log(f"[kártya] {cim}: {len(darab)} darab, {sum(ki)} jelölt kérve {n} kártyához")
    meglevo = tuple(meglevo)

    def elvet(j: Jelolt, ok: str, reszlet: str = "") -> None:
        elvetve[ok] += 1
        elvetett.append({"kerdes": j.kerdes, "valasz": j.valasz, "forras": j.forras, "ok": ok, "reszlet": reszlet})

    for di, d in enumerate(darab):
        maradt = ki[di]
        while maradt > 0 and len(elfogadott) < n * 2:
            if allj():
                raise Megall("Leállítva.")
            k = min(maradt, b.hivas_max_kartya)
            maradt -= k
            prompt = GENERALO_PROMPT.format(k=k, cim=cim, szoveg=d["szoveg"],
                                            kerulendo=_kerulendo(list(meglevo) + [x.kerdes for x in elfogadott], b))
            valasz = generalo(prompt, b.token_per_kartya * k + 120)
            stat["hivas"] += 1
            jeloltek = szetszed(valasz)[:k + 2]
            stat["jelolt"] += len(jeloltek)
            for j in jeloltek:
                if not j.kerdes or not j.valasz:
                    elvet(j, "hianyos")
                    continue
                if not j.forras:
                    elvet(j, "forras_nelkul")
                    continue
                v = KH.ellenoriz(fs, j.valasz, j.forras, p, kontextus=j.kerdes)
                if not v.ok:
                    elvet(j, "huseg_" + v.okok[0], ", ".join(v.okok) + (f" ({', '.join(v.hianyzo)})" if v.hianyzo else ""))
                    continue
                ok = atomi(j, b) or egyertelmu(j)
                if ok:
                    elvet(j, ok)
                    continue
                if formatum.ujjlenyomat(j.kerdes, forras_link) in sirkovek or any(
                        jaccard3(j.kerdes, x) >= b.duplikat_jaccard for x in meglevo):
                    elvet(j, "duplikat_meglevo")
                    continue
                if any(jaccard3(j.kerdes, x.kerdes) >= b.duplikat_jaccard for x in elfogadott):
                    elvet(j, "duplikat")
                    continue
                mondat = fs.mondat(v.hely[0], v.hely[1], max_k=420)
                vak = ellenorzo(ELLENORZO_PROMPT.format(forras=mondat, kerdes=j.kerdes), b.vak_max_token)
                stat["hivas"] += 1
                e = vak_egyezes(vak, j.valasz)
                if e < b.vak_kuszob:
                    elvet(j, "vak", f"{e:.2f}: {vak.strip()[:60]!r}")
                    continue
                sz = fs.szakaszok[v.szakasz] if v.szakasz is not None and v.szakasz >= 0 else None
                elfogadott.append(Kartyajelolt(j.kerdes, j.valasz, mondat, fs.szoveg[v.hely[0]:v.hely[1]], v.szakasz,
                                               sz.horgony if sz else None))
    valasztott = elfogadott[:n]
    st = {**stat, "kert": n, "elfogadott": len(elfogadott), "valasztott": len(valasztott), "elvetve": dict(elvetve),
          "mp": round(time.time() - t0, 1), "prompt_verzio": PROMPT_VERZIO}
    log(f"[kártya] kész: {len(valasztott)} kártya ({stat['jelolt']} jelöltből) · elvetve: "
        + (", ".join(f"{a} {c}" for a, c in elvetve.most_common()) or "—"))
    return Eredmeny(valasztott, st, elvetett)
