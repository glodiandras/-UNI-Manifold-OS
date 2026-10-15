"""A Bases-lekérdezés (C12): `futtat(bazis, tabla, nezet, …) → dict` (a `POST …/bazis/lekerdez` válaszának magja).

Sorrend: szűrés (a globális ÉS a nézet-szűrő) → rendezés (`sort`; alap: `file.name`) → `limit` → csoportosítás
(`groupBy`) → cellák és összesítők. A **rendezés után** vág a `limit`. A képlet lustán, soronként egyszer számolódik
(`KepletTar` + közös memó); egy hibás képlet hiba-cella, nem dönti el a nézetet. A szűrő futási hibája a sort
kihagyja, és a `hibak[].db` számolja.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime

from . import fuggvenyek as fn
from .adat import Sor, Tabla
from .ertekek import (
    Datum, Fajl, FutasHiba, Hiba, Idotartam, Kep, Keret, Link, datum_ms, kimenet, kulcs, rendezo_kulcs, szovegge, _szam_e,
)
from .kiertekelo import Kor, KepletTar, futtat as _futtat, fordit_szoveg
from .kifejezes import KifejezesHiba
from .modell import OSSZESITOK, Bazis, Nezet, SzuroHiba, hiba, szuro_fa, szuro_fordit, szuro_szoveg, tulajdonsag_id

MAX_SOR = 10_000
ERTEK_KERET = 16 * 1024 * 1024        # T041: az egy lekérdezésben előállított értékek együttes mérete (karakter/elem-egység)
FAJL_TIPUS = {"name": "text", "basename": "text", "path": "text", "folder": "text", "ext": "text", "size": "number",
              "ctime": "datetime", "mtime": "datetime", "tags": "tags", "links": "multitext", "embeds": "multitext",
              "backlinks": "multitext"}
FAJL_NEV = {"name": "Fájlnév", "basename": "Név", "path": "Útvonal", "folder": "Mappa", "ext": "Kiterjesztés",
            "size": "Méret", "ctime": "Létrehozva", "mtime": "Módosítva", "tags": "Címkék", "links": "Linkek",
            "embeds": "Beágyazások", "backlinks": "Visszahivatkozások"}
_SZIN = re.compile(r"^#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_KULSO = re.compile(r"^https?://", re.I)


def _ures_e(x) -> bool:
    return x is None or x == "" or x == [] or x == {}


def _json_biztos(x):
    """A nyers YAML-érték JSON-biztos másolata (a nézet `beallitas`-a). Ami nem szerializálható (körkörös hivatkozás, túl
    mély fa, T041), annak a szöveges alakja megy ki — a lekérdezés nem 500-zal esik el."""
    try:
        return json.loads(json.dumps(x, ensure_ascii=False, default=str))
    except (RecursionError, ValueError, OverflowError):
        return str(x)[:2000]


def _meret(v) -> int:
    """Egy érték becsült mérete a keret számára: szövegnél a hossz, listánál az elemszám és a szöveges elemek hossza."""
    if isinstance(v, str):
        return len(v)
    if isinstance(v, (list, tuple)):
        return len(v) + sum(len(e) for e in v[:10_000] if isinstance(e, str))
    return 1


# ================================================================ összesítők

def _datumok(ertekek):
    return [x for x in ertekek if isinstance(x, Datum)]


def osszesit(nev: str, ertekek: list, kor: Kor, egyedi: dict):
    """Egy összesítő értéke az oszlop értékein. A beépített 15 mellett a `summaries` képletei (`values` lista)."""
    if nev in egyedi:
        try:
            f = fordit_szoveg(egyedi[nev])
        except KifejezesHiba as e:
            return Hiba(str(e))
        try:
            return _futtat(f, kor.alkor(values=list(ertekek)))
        except FutasHiba as e:
            return Hiba(e.uzenet)
    szamok = [x for x in ertekek if _szam_e(x)]
    hiv = lambda m: fn.hivas_metodus(kor, szamok, m, [])               # noqa: E731
    if nev == "Average":
        return hiv("mean")
    if nev in ("Min", "Max", "Sum", "Median", "Stddev"):
        return hiv(nev.lower())
    if nev == "Earliest":
        d = _datumok(ertekek)
        return min(d, key=rendezo_kulcs) if d else None
    if nev == "Latest":
        d = _datumok(ertekek)
        return max(d, key=rendezo_kulcs) if d else None
    if nev == "Range":
        d = _datumok(ertekek)
        if d:
            return Idotartam(0, datum_ms(max(d, key=rendezo_kulcs)) - datum_ms(min(d, key=rendezo_kulcs)))
        return fn.hivas_metodus(kor, [max(szamok) - min(szamok)], "sum", []) if szamok else None
    if nev == "Checked":
        return sum(1 for x in ertekek if x is True)
    if nev == "Unchecked":
        return sum(1 for x in ertekek if x is False)
    if nev == "Empty":
        return sum(1 for x in ertekek if _ures_e(x))
    if nev == "Filled":
        return sum(1 for x in ertekek if not _ures_e(x))
    if nev == "Unique":
        return len({kulcs(x) for x in ertekek if x is not None})
    return Hiba(f"ismeretlen összesítő: {nev}")


# ================================================================ kép

def _kep(v, sor: Sor, tabla: Tabla):
    """A kártya borítója: `{t: ut|szin|kulso, …}` vagy `None`. A `ut` csak képfájl lehet (a feloldás a core-é)."""
    if isinstance(v, list):
        v = v[0] if v else None
    if isinstance(v, Kep):
        if v.szin:
            return {"t": "szin", "v": v.szin}
        if v.url:
            return {"t": "kulso", "url": v.url}
        ut = v.ut
    elif isinstance(v, Link):
        if v.kulso:
            return {"t": "kulso", "url": v.cel}
        ut = v.ut
    elif isinstance(v, Fajl):
        ut = v.sor.ut
    elif isinstance(v, str):
        s = v.strip()
        if _SZIN.match(s):
            return {"t": "szin", "v": s}
        if _KULSO.match(s):
            return {"t": "kulso", "url": s}
        ut = tabla.felold(s, sor.ut) or (s if s in tabla.ut_szerint else None)
    else:
        return None
    cel = tabla.ut_szerint.get(ut) if ut else None
    return {"t": "ut", "ut": ut} if cel is not None and cel.tipus == "kep" else None


# ================================================================ futtatás

def futtat(bazis: Bazis, tabla: Tabla, nezet: Nezet, ez_ut: str | None = None, most: Datum | None = None,
           max_sor: int = MAX_SOR, hatarido_mp: float | None = None, megszakitva=None,
           ertek_keret: int = ERTEK_KERET) -> dict:
    """A nézet futtatása. `hatarido_mp`: a teljes időkeret másodpercben (túllépés: `IdokeretHiba`, T040); `megszakitva`:
    hívható, amely igaz, ha a kérés elavult (az újabb kérés megelőzte; `IdokeretHiba`, `megszakitva=True`); `ertek_keret`: az
    előállított értékek együttes mérete (túllépés: `ErtekKeretHiba`, T041)."""
    t0 = time.perf_counter()
    most = most or Datum(datetime.now().replace(microsecond=0), True)
    kepletek = KepletTar(bazis.kepletek)
    ez = None
    if ez_ut:
        ez = tabla.fajl(ez_ut) or Fajl(Sor(ez_ut), tabla)          # a még nem indexelt fájl (új jegyzet) is lehet `this`
    alap = Kor(None, tabla, ez, kepletek, None, most,
               hatarido=None if hatarido_mp is None else time.monotonic() + hatarido_mp, megszakitva=megszakitva,
               keret=Keret(ertek_keret))
    glob_f, _ = szuro_fordit(szuro_fa(bazis.nyers.get("filters"), "filters")[0])
    nezet_f, _ = szuro_fordit(szuro_fa(nezet.nyers.get("filters"), f"views[{nezet.index}].filters")[0])

    # ---- szűrés
    szurt: list[tuple[Sor, Kor]] = []
    szuro_hibak: dict[str, list] = {}
    for sor in tabla.sorok:
        kor = alap.sorra(sor)
        kor.ellenoriz()                                       # T040: időkeret és megszakítás soronként
        try:
            if glob_f(kor) and nezet_f(kor):
                szurt.append((sor, kor))
        except SzuroHiba as e:
            h = szuro_hibak.setdefault(e.hely, [e.uzenet, 0])
            h[1] += 1

    # ---- értékek (soronként és oszloponként egyszer)
    hozz: dict = {}
    memo: dict = {}

    def hozzaferes(azon: str):
        f = hozz.get(azon)
        if f is None:
            ter, nev = tulajdonsag_id(azon)
            if ter == "file":
                f = lambda kor, nev=nev: fn.fajl_mezo(kor, kor.fajl(), nev)               # noqa: E731
            elif ter == "note":
                f = lambda kor, nev=nev: kor.sor.tulajdonsag(kor.tabla, nev)             # noqa: E731
            else:
                f = lambda kor, nev=nev: kor.kepletek.ertek(kor, nev)                     # noqa: E731
            hozz[azon] = f
        return f

    def ertek(azon: str, sor: Sor, kor: Kor):
        k = (azon, sor.ut)
        if k not in memo:
            try:
                v = _futtat(hozzaferes(azon), kor)
                if azon == "file.name":
                    v = Fajl(sor, tabla)                     # a fájlnév-oszlop a fájlra mutató link
            except FutasHiba as e:
                v = Hiba(e.uzenet)
            kor.keret.fogyaszt(_meret(v))                     # T041: lekérdezésenkénti értékkeret
            memo[k] = v
        return memo[k]

    def rendezheto(azon, sor, kor):
        v = ertek(azon, sor, kor)
        return None if isinstance(v, Hiba) else (v.sor.nev if isinstance(v, Fajl) else v)

    # ---- rendezés (a hátulsó kulcstól, stabilan), limit
    for azon, irany in reversed(nezet.rendezes() or [("file.name", "ASC")]):
        kulcsok = {id(sor): rendezo_kulcs(rendezheto(azon, sor, kor)) for sor, kor in szurt}
        szurt.sort(key=lambda sk: kulcsok[id(sk[0])], reverse=irany == "DESC")
    lim = nezet.nyers.get("limit")
    if isinstance(lim, int) and not isinstance(lim, bool) and lim > 0:
        szurt = szurt[:lim]
    osszes = len(szurt)
    levagva = osszes > max_sor
    if levagva:
        szurt = szurt[:max_sor]

    # ---- csoportosítás
    csoport = nezet.csoport()
    csoportok = None
    if csoport:
        azon, irany = csoport
        csopertek: dict = {}
        for sor, kor in szurt:
            v = ertek(azon, sor, kor)
            v = None if isinstance(v, Hiba) else (v.sor.nev if isinstance(v, Fajl) else v)
            k = kulcs(v)
            if k not in csopertek:
                csopertek[k] = [v, []]
            csopertek[k][1].append((sor, kor))
        rendezett = sorted(csopertek.values(), key=lambda e: rendezo_kulcs(e[0]), reverse=irany == "DESC")
        szurt = [sk for _, tagok in rendezett for sk in tagok]
        csoportok_nyers = rendezett

    # ---- oszlopok
    oszlop_idk = nezet.oszlopok()
    oszlopok = []
    for azon in oszlop_idk:
        ter, nev = tulajdonsag_id(azon)
        tip = FAJL_TIPUS.get(nev, "text") if ter == "file" else "formula" if ter == "formula" \
            else tabla.tulajdonsag_tipus(nev)
        szel = nezet.nyers.get("columnSize")
        szel = szel.get(azon) if isinstance(szel, dict) else None
        oszlopok.append({"id": azon, "nev": bazis.megjelenes(azon) or (FAJL_NEV.get(nev, nev) if ter == "file" else nev),
                         "ter": ter, "tipus": tip, "szerkesztheto": ter == "note",
                         "szelesseg": szel if _szam_e(szel) else None})

    # ---- cellák
    kep_azon = nezet.nyers.get("image")
    kep_azon = kep_azon if isinstance(kep_azon, str) and kep_azon.strip() else None
    sorok = []
    for sor, kor in szurt:
        r = {"ut": sor.ut, "nev": sor.nev.rsplit(".", 1)[0] if sor.tipus in ("md", "canvas", "base") else sor.nev,
             "md": sor.tipus == "md", "cellak": [kimenet(ertek(a, sor, kor)) for a in oszlop_idk]}
        if kep_azon:
            k = _kep(ertek(kep_azon, sor, kor), sor, tabla)
            if k:
                r["kep"] = k
        sorok.append(r)

    # ---- összesítők
    egyedi = bazis.osszesitok
    ossz_beallitas = nezet.nyers.get("summaries")
    ossz_beallitas = ossz_beallitas if isinstance(ossz_beallitas, dict) else {}
    figyelm = list(bazis.figyelmeztetesek)

    def osszesitok(sk_lista) -> dict:
        ki = {}
        for azon, nev in ossz_beallitas.items():
            if not isinstance(nev, str):
                continue
            ertekek = [ertek(azon, sor, kor) for sor, kor in sk_lista]
            ertekek = [None if isinstance(x, Hiba) else (x.sor.nev if isinstance(x, Fajl) else x) for x in ertekek]
            ki[azon] = {"nev": nev, "ertek": kimenet(osszesit(nev, ertekek, alap, egyedi))}
        return ki

    for nev in {n for n in ossz_beallitas.values() if isinstance(n, str)}:
        if nev not in OSSZESITOK and nev not in egyedi:
            figyelm.append(hiba(f"views[{nezet.index}].summaries", f"ismeretlen összesítő: {nev}"))
    osszesitok_ki = osszesitok(szurt) if ossz_beallitas else {}
    if csoport:
        csoportok, tol = [], 0
        for v, tagok in csoportok_nyers:
            csoportok.append({"kulcs": kimenet(v), "cimke": szovegge(v), "tol": tol, "db": len(tagok),
                              "osszesitok": osszesitok(tagok) if ossz_beallitas else {},
                              "huzhato": tulajdonsag_id(csoport[0])[0] == "note"})
            tol += len(tagok)

    elerheto = [{"id": f"file.{k}", "nev": FAJL_NEV[k], "ter": "file", "tipus": FAJL_TIPUS[k]} for k in FAJL_NEV]
    elerheto += [{"id": k, "nev": k, "ter": "note", "tipus": t} for k, t in tabla.tulajdonsag_lista()]
    elerheto += [{"id": f"formula.{k}", "nev": k, "ter": "formula", "tipus": "formula"} for k in bazis.kepletek]
    return {
        "nezetek": [{"nev": n.nev, "tipus": n.tipus, "ismert": n.ismert} for n in bazis.nezetek],
        "nezet": {"index": nezet.index, "nev": nezet.nev, "tipus": nezet.tipus, "eredeti_tipus": nezet.eredeti_tipus,
                  "beallitas": _json_biztos(nezet.nyers)},
        "oszlopok": oszlopok, "sorok": sorok, "csoportok": csoportok, "osszesitok": osszesitok_ki,
        "fajl": {"szuro": szuro_szoveg(bazis.nyers.get("filters")),
                 "szuro_nezet": szuro_szoveg(nezet.nyers.get("filters")),
                 "kepletek": {str(k): str(v) for k, v in bazis.kepletek.items()},
                 "osszesitok": [str(k) for k in bazis.osszesitok], "elerheto": elerheto},
        "osszes": osszes, "levagva": levagva,
        "hibak": [hiba(h, m, db=db) for h, (m, db) in szuro_hibak.items()],
        "figyelmeztetesek": figyelm,
        "ido_ms": round((time.perf_counter() - t0) * 1000, 1), "generacio": tabla.generacio,
    }
