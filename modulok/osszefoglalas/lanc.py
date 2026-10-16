"""Az összefoglaló lánc modell nélküli része (`docs/C26-TERV.md` 4. fejezet): darabok → jelöltek → kapuk → kiválasztás.

Egy jelölt állítás négy, egymástól független kapun megy át (a modell nem igazságforrás, I7):

1. **mechanikus**: van állítás és idézet (**forrás nélküli mondat itt esik ki**), egy mondat, nincs link- vagy kiemelés-jel;
2. **forráshűség** (a közös `modulok/kapuk`, `[kapuk.osszefoglalo]` profil): az idézet a jegyzetben áll, az állítás abból
   következik (lefedettség, szám, név, tagadás). Az összefoglalóba a *jegyzet* mondata kerül idézetként;
3. **ismétlés**: a tőhalmaz Jaccard-hasonlósága egy már elfogadott állítással;
4. **fedés**: két állítás ne ugyanarra a forráshelyre épüljön.

A kiesett jelöltek okonként a statisztikában maradnak (I3). **A modell egy hívható mögött áll** (`hivo`:
`(prompt, max_tokens) -> szöveg`, mint a kvíz generálója): a C26b köti rá a workert, a gyorsítótárat és a D9-et; a tesztek
forgatókönyvezett álmodellt adnak. A vaultba ez a modul nem ír.
"""
from __future__ import annotations

import collections
import dataclasses
import re
import time
from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import Callable

from core import kiserok
from modulok.eval.kozos import kimenet
from modulok.kapuk import forras as KF
from modulok.kapuk import huseg as KH
from modulok.kapuk import tokenek

from . import formatum as FM
from .formatum import Allitas, Osszefoglalo
from .promptok import MAPPA_PROMPT, PROMPT_VERZIO, darab_prompt
from .szakaszolas import Bemenet, horgony_keres, norm

ModellHivas = Callable[[str, int], str]
IDEZET_SZEL = "„”\"“«»*_ "      # a jegyzet mondatát kísérő idézőjel és kiemelés (`*„…”*`) az idézet szélén nem része a mondatnak


class Megall(Exception):
    """Az összefoglaló nem készülhet el, vagy a kérés hibás — az üzenet a gazdának szól."""


@dataclass(frozen=True)
class Beallitas:
    """Az `[osszefoglalas]` szakasz (az `os.toml`)."""
    mappa: str = FM.ALAP_MAPPA
    utotag: str = FM.UTOTAG
    darab_max_karakter: int = 2200
    szakasz_min_karakter: int = 20
    karakter_per_allitas: int = 350
    allitas_per_darab_max: int = 6
    allitas_min: int = 3
    allitas_max: int = 12
    allitas_max_szo: int = 45
    token_per_allitas: int = 140
    idezet_max_karakter: int = 420
    duplikat_jaccard: float = 0.6
    mappa_max_per_jegyzet: int = 3
    mappa_allitas_max: int = 10
    mappa_max_jegyzet: int = 40       # mappa-szint: legfeljebb ennyi jegyzet-összefoglaló kerül a modell elé
    mappa_max_uj: int = 4             # mappa-szint: egy kérésben a hiányzó jegyzet-összefoglalókból ennyit készít el (C26b; + a mappa-szint = ≤ 5 tétel)
    kontextus_max_karakter: int = 24000
    ablak_mp: int = 60
    gyorsitotar_ora: float = 12.0     # a modell-válasz gyorsítótárának élettartama (C26b; a `{tmp}` alatt)
    kihagyott_szakaszok: tuple[str, ...] | None = field(default=None, compare=False)   # nem az `[osszefoglalas]` kulcsa: a `[kapuk] kihagyott_szakaszok` (None: az alap)


_MEZOK = {f.name for f in fields(Beallitas)} - {"kihagyott_szakaszok"}


def beallitas(cfg) -> Beallitas:
    """Az `[osszefoglalas]` szakaszból; ismeretlen kulcs hiba (az `automatika` alszakasz az `automatika.py`-é)."""
    adat = {k: v for k, v in dict(cfg.section("osszefoglalas")).items() if not isinstance(v, dict)}
    ismeretlen = sorted(set(adat) - _MEZOK)
    if ismeretlen:
        raise ValueError(f"[osszefoglalas]: ismeretlen kulcs: {', '.join(ismeretlen)}")
    adat["mappa"] = kiserok.kisero_mappa(cfg, "osszefoglalas")
    return Beallitas(**adat, kihagyott_szakaszok=KF.kihagyott_szakaszok(cfg))


def profil(cfg=None) -> KH.Profil:
    """A forráshűség-kapu `osszefoglalo` profilja (config nélkül: a profil alapértékei és a 4–45 szavas idézet)."""
    return KH.profil(cfg, "osszefoglalo") if cfg is not None else KH.Profil(nev="osszefoglalo", idezet_min_szo=4, idezet_max_szo=45)


# ---------------------------------------------------------------------- a modell válasza, mechanikus kapu

@dataclass
class Jelolt:
    allitas: str
    idezet: str
    forras: str = ""


def jeloltek(valasz: str, kulcs: tuple[str, ...] = ("allitas",)) -> list[Jelolt]:
    """A modell válasza → jelöltek (tűrő: kerítés, burok); ítéletet nem hoz. Nem szöveg mező üres szöveg lesz."""
    ki = []
    for x in kimenet.lista_kinyer(valasz, kulcs):
        s = lambda k: x.get(k) if isinstance(x.get(k), str) else ""      # noqa: E731
        ki.append(Jelolt(norm(s("allitas")), norm(s("idezet")).strip("„”\"'«»“ "), norm(s("forras"))))
    return ki


def mechanikus(j: Jelolt, b: Beallitas) -> tuple[str, str] | None:
    """(ok, részlet) a bukó szabályról, vagy `None`. A forrás (idézet) nélküli mondat itt esik ki."""
    if not j.allitas:
        return "ures_allitas", "nincs állítás"
    if not j.idezet:
        return "forras_nelkul", f"az állításhoz nincs idézet: {j.allitas[:60]!r}"
    szavak = len(j.allitas.split())
    if szavak < 3 or szavak > b.allitas_max_szo:
        return "allitas_hossz", f"{szavak} szó"
    if re.search(r"\[\[|\]\]|==", j.allitas):
        return "tiltott_jeloles", "link- vagy kiemelés-jel az állításban"
    return None


# ---------------------------------------------------------------------- kapuk

_KAPU_OK = {"kotott": "idezet", "hossz": "idezet", "tamogatas": "tamogatas", "kenyes": "kenyes", "tagadas": "tagadas"}


def hasonlosag(a: str, b: str) -> float:
    """Két állítás tőhalmazának Jaccard-hasonlósága (a kapuk `tokenek` töveivel)."""
    x, y = set(tokenek.tovek(a)), set(tokenek.tovek(b))
    return len(x & y) / len(x | y) if x and y else 0.0


def _atfed(h1: tuple[int, int], h2: tuple[int, int]) -> bool:
    kozos = min(h1[1], h2[1]) - max(h1[0], h2[0])
    return kozos > 0 and kozos >= 0.5 * min(h1[1] - h1[0], h2[1] - h2[0])


def _forras_kapu(bemenet: Bemenet, j: Jelolt, p: KH.Profil):
    """A közös kapu a jelöltre: (ok, részlet, verdikt) — az ok a statisztika kulcsa."""
    v = KH.ellenoriz(bemenet.fs, j.allitas, j.idezet, p)
    if v.ok:
        return None, None, v
    return _KAPU_OK[v.okok[0]], ", ".join(v.okok) + (f" ({', '.join(v.hianyzo)})" if v.hianyzo else ""), v


# ---------------------------------------------------------------------- a lánc

@dataclass
class Eredmeny:
    osszefoglalo: Osszefoglalo
    statisztika: dict
    elvetett: list[dict] = field(default_factory=list)          # {allitas, ok, reszlet}
    uj_horgonyok: list[dict] = field(default_factory=list)      # {szakasz, bekezdes}: blokkazonosítót érdemes kapnia (C26b)


def most() -> datetime:
    return datetime.now()


def allitas_darabra(karakter: int, b: Beallitas) -> int:
    """Hány állítást kérünk egy darabtól: `karakter_per_allitas`-enként egyet (felfelé), legalább kettőt, plafonnal."""
    return min(b.allitas_per_darab_max, max(2, -(-karakter // b.karakter_per_allitas)))


def valaszt(elfogadott: list[dict], n: int) -> list[dict]:
    """Ha több ment át, mint `n`: szakaszonként körbe (az összefoglaló a jegyzet egészét fedje), majd a jegyzet
    sorrendjében. Az elemek `hely` (a forrásszöveg-pozíció) és `si` (szakasz) kulcsúak."""
    csoport: dict[int, list[dict]] = collections.defaultdict(list)
    for q in sorted(elfogadott, key=lambda q: q["hely"]):
        csoport[q["si"]].append(q)
    sor: list[dict] = []
    kor = 0
    while len(sor) < min(n, len(elfogadott)):
        for si in sorted(csoport):
            if kor < len(csoport[si]) and len(sor) < n:
                sor.append(csoport[si][kor])
        kor += 1
    return sorted(sor, key=lambda q: q["hely"])


def _rekord(j: Jelolt, v: KH.Verdikt, bemenet: Bemenet, b: Beallitas) -> dict:
    """Az elfogadott állítás: az idézet a JEGYZET mondata, a horgony a találat bekezdéséé."""
    talalt = bemenet.fs.szoveg[v.hely[0]:v.hely[1]]
    horgony, bek = horgony_keres(bemenet, v.szakasz, talalt)
    mondat = bemenet.fs.mondat(v.hely[0], v.hely[1], b.idezet_max_karakter)
    return {"allitas": j.allitas, "idezet": norm(mondat).strip(IDEZET_SZEL), "horgony": horgony, "hely": v.hely, "si": v.szakasz,
            "bekezdes": bek}


def jelolt_ellenoriz(bemenet: Bemenet, j: Jelolt, elfogadott: list[dict], b: Beallitas, p: KH.Profil):
    """Egy jelölt a négy kapun: `(rekord, None)` ha átment, `(None, (ok, részlet))` ha kiesett. `elfogadott`: az ugyanebből a
    forrásból már elfogadott rekordok (az ismétlés és a fedés ellen). A mechanikus kapu → a közös forráshűség-kapu → ismétlés
    → fedés sorrendje rögzített, hogy a statisztika okai összevethetők legyenek."""
    ok = mechanikus(j, b)
    v = None
    if not ok:
        kod, reszlet, v = _forras_kapu(bemenet, j, p)
        ok = (kod, reszlet) if kod else None
    if not ok and any(hasonlosag(j.allitas, x["allitas"]) >= b.duplikat_jaccard for x in elfogadott):
        ok = ("duplikatum", "egy már elfogadott állítás ismétlése")
    if not ok and any(_atfed(v.hely, x["hely"]) for x in elfogadott):
        ok = ("ugyanaz_a_hely", "ugyanarra a forráshelyre épül, mint egy elfogadott állítás")
    return (None, ok) if ok else (_rekord(j, v, bemenet, b), None)


def osszefoglal(bemenet: Bemenet, hivo: ModellHivas, modell: str, cim: str, forrasok: list[str] | None = None,
                szint: str = "jegyzet", azon: str | None = None, b: Beallitas | None = None,
                p: KH.Profil | None = None, mikor: datetime | None = None, log=lambda s: None,
                max_allitas: int | None = None, allj: Callable[[], bool] = lambda: False) -> Eredmeny:
    """Egy összefoglaló a `Bemenet`ből (a vaultba NEM ír). `forrasok`: a `Source` (alap: a bemenet célja); `p`: a kapu
    `osszefoglalo` profilja (az éles hívó az `os.toml`-ból tölti); `allj`: a kecses leállítás jelzője (darabonként nézi)."""
    b = b or Beallitas()
    p = p or profil()
    if not modell:
        raise Megall("nincs megadva modell")
    if szint not in FM.SZINTEK:
        raise Megall(f"ismeretlen szint: {szint!r}")
    if not bemenet.darabok:
        raise Megall("a forrásnak nincs olyan szöveges része, amelyből összefoglalni lehet")
    n = int(max_allitas or b.allitas_max)
    t0, mikor = time.time(), mikor or most()
    stat: collections.Counter = collections.Counter()
    elvetve: collections.Counter = collections.Counter()
    elvetett: list[dict] = []
    elfogadott: list[dict] = []
    log(f"[összefoglaló] {cim}: {len(bemenet.fs.szakaszok)} szakasz, {len(bemenet.darabok)} darab · {modell}")

    for d in bemenet.darabok:
        if allj():
            raise Megall("leállítva (a következő darab előtt)")
        k = allitas_darabra(d.karakter, b)
        valasz = hivo(darab_prompt(k, cim, d.szoveg), b.token_per_allitas * k + 150)
        stat["hivas"] += 1
        lista = jeloltek(valasz)[:k + 2]
        if not lista:
            stat["ertelmezhetetlen_valasz"] += 1
        stat["jelolt"] += len(lista)
        for j in lista:
            rekord, ok = jelolt_ellenoriz(bemenet, j, elfogadott, b, p)
            if ok:
                elvetve[ok[0]] += 1
                elvetett.append({"allitas": j.allitas, "ok": ok[0], "reszlet": ok[1]})
                continue
            elfogadott.append(rekord)
    stat["elfogadott"] = len(elfogadott)
    valasztott = valaszt(elfogadott, n)
    if len(valasztott) < b.allitas_min:
        raise Megall(f"csak {len(valasztott)} állítás ment át a kapukon ({stat['jelolt']} jelöltből; elvetve: "
                     + (", ".join(f"{a} {c}" for a, c in elvetve.most_common()) or "—") + ") — az összefoglaló nem készült el")
    allitasok = [Allitas(x["allitas"], x["horgony"], x["idezet"], f"a{i}") for i, x in enumerate(valasztott, 1)]
    fedett = sorted({x["si"] for x in valasztott})
    uj = []
    for x in valasztott:
        if x["horgony"].alcel is None or not x["horgony"].alcel.startswith("^"):
            bek = x["bekezdes"]
            e = {"szakasz": bemenet.fs.szakaszok[x["si"]].cim, "bekezdes": (bek.szoveg[:120] if bek else "")}
            if e not in uj and bek is not None and not bek.blokkok:
                uj.append(e)
    o = Osszefoglalo(azon or FM.uj_azon(mikor), szint, list(forrasok) if forrasok else [bemenet.cel], cim, modell,
                     FM.keszult(mikor), allitasok)
    st = {**stat, "valasztott": len(allitasok), "kert": n, "elvetve": dict(elvetve), "szakasz": len(bemenet.fs.szakaszok),
          "lefedett_szakasz": len(fedett), "mp": round(time.time() - t0, 1), "prompt_verzio": PROMPT_VERZIO}
    log(f"[összefoglaló] kész: {len(allitasok)} állítás ({stat['jelolt']} jelöltből) · elvetve: "
        + (", ".join(f"{a} {c}" for a, c in elvetve.most_common()) or "—") + f" · {len(fedett)}/{len(bemenet.fs.szakaszok)} szakasz")
    return Eredmeny(o, st, elvetett, uj)


# ---------------------------------------------------------------------- mappa-szint

_J_AZON = re.compile(r"J?\s*(\d+)\s*\.\s*(\d+)", re.I)


def mappa_osszefoglal(cim: str, jegyzetek: list[tuple[Osszefoglalo, Bemenet]], hivo: ModellHivas, modell: str,
                      azon: str | None = None, b: Beallitas | None = None, p: KH.Profil | None = None,
                      mikor: datetime | None = None, log=lambda s: None) -> Eredmeny:
    """Mappa-szintű összefoglaló a jegyzet-szintűekből (`docs/C26-TERV.md` 3.2). **Új állítás csak már ellenőrzött
    állításból:** a modell a számozott jegyzet-állításokra hivatkozva ír, és az új állítást a közös kapu a hivatkozott
    jegyzet-állítás *idézetére* (a jegyzet mondatára) méri; a link a jegyzet eredeti horgonyára mutat."""
    b = b or Beallitas()
    p = dataclasses.replace(p or profil(), idezet_max_szo=None)          # az idézet itt már a jegyzet mondata
    if not modell:
        raise Megall("nincs megadva modell")
    if not jegyzetek:
        raise Megall("a mappában nincs összefoglalt jegyzet")
    t0, mikor = time.time(), mikor or most()
    sorok = [f"J{i}.{j}: {a.szoveg}" for i, (o, _) in enumerate(jegyzetek, 1) for j, a in enumerate(o.allitasok, 1)]
    k = min(b.mappa_allitas_max, max(b.allitas_min, len(sorok) // 3))
    valasz = hivo(MAPPA_PROMPT.format(k=k, allitasok="\n".join(sorok)), b.token_per_allitas * k + 150)
    stat: collections.Counter = collections.Counter(hivas=1)
    elvetve: collections.Counter = collections.Counter()
    elvetett: list[dict] = []
    elfogadott: list[tuple[int, Allitas]] = []
    per_jegyzet: collections.Counter = collections.Counter()
    lista = jeloltek(valasz)[:k + 2]
    stat["jelolt"] = len(lista)
    for j in lista:
        m = _J_AZON.search(j.forras)
        ok = None
        i = a = None
        if not j.allitas or len(j.allitas.split()) < 3 or re.search(r"\[\[|\]\]|==", j.allitas):
            ok = ("allitas_hossz", "üres, túl rövid vagy jelölést tartalmazó állítás")
        elif not m or not (1 <= int(m.group(1)) <= len(jegyzetek)) or not (1 <= int(m.group(2)) <= len(jegyzetek[int(m.group(1)) - 1][0].allitasok)):
            ok = ("forras_nelkul", f"nincs érvényes hivatkozás a jegyzet-állításra: {j.forras!r}")
        else:
            i, a = int(m.group(1)) - 1, int(m.group(2)) - 1
            forras_allitas = jegyzetek[i][0].allitasok[a]
            v = KH.ellenoriz(jegyzetek[i][1].fs, j.allitas, forras_allitas.idezet, p)
            if not v.ok:
                ok = (_KAPU_OK[v.okok[0]], ", ".join(v.okok))
            elif per_jegyzet[i] >= b.mappa_max_per_jegyzet:
                ok = ("jegyzet_plafon", "ebből a jegyzetből már elég állítás van")
            elif any(hasonlosag(j.allitas, x.szoveg) >= b.duplikat_jaccard for _, x in elfogadott):
                ok = ("duplikatum", "egy már elfogadott állítás ismétlése")
        if ok:
            elvetve[ok[0]] += 1
            elvetett.append({"allitas": j.allitas, "ok": ok[0], "reszlet": ok[1]})
            continue
        fa = jegyzetek[i][0].allitasok[a]
        per_jegyzet[i] += 1
        elfogadott.append((i, Allitas(j.allitas, fa.horgony, fa.idezet)))
    if len(elfogadott) < b.allitas_min:
        raise Megall(f"csak {len(elfogadott)} állítás ment át a kapukon ({len(lista)} jelöltből) — a mappa-összefoglaló nem készült el")
    elfogadott.sort(key=lambda x: x[0])
    allitasok = [dataclasses.replace(x, id=f"a{n}") for n, (_, x) in enumerate(elfogadott, 1)]
    forrasok = []
    for i, _ in elfogadott:
        for f in jegyzetek[i][0].forrasok:
            if f not in forrasok:
                forrasok.append(f)
    o = Osszefoglalo(azon or FM.uj_azon(mikor), "mappa", forrasok, cim, modell, FM.keszult(mikor), allitasok)
    st = {**stat, "valasztott": len(allitasok), "kert": k, "elvetve": dict(elvetve), "jegyzet": len(jegyzetek),
          "mp": round(time.time() - t0, 1), "prompt_verzio": PROMPT_VERZIO}
    log(f"[összefoglaló/mappa] kész: {len(allitasok)} állítás {len(set(i for i, _ in elfogadott))}/{len(jegyzetek)} jegyzetből")
    return Eredmeny(o, st, elvetett, [])
