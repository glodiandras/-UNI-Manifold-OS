"""A kitöltés kiértékelése és az elemzés — determinisztikus, modell nélkül (a legacy `kviz.py` portja).

A pontszámot a core számolja, a felület „helyes” jelzése nem számít (I7: a mérés ne függjön a mért rendszertől; a
kulcs a válasz előtt nem hagyja el a core-t). Az elemzés négy kategóriája a válasz helyességéből × a kitöltő előzetes
biztosságából (a válasz *előtt* jelzi, hogy tippel — utólag a visszajelzés torzítaná):

- **tudod** (helyes, biztos), **szerencsés tipp** (helyes, de tippelt: ingatag),
- **tévképzet** (rossz, de biztos volt — ezt kell először javítani), **hiány** (rossz tipp, vagy „nem tudom”).

A javaslatok szakaszonként, prioritás szerint (tévképzet vagy tartós hiba → hiány → szerencsés tipp), azon belül súly szerint
(tévképzet 3, hiány 2, tartós hiba +2, szerencsés tipp 1); mind a jegyzet szakaszára mutat, és hozza a mondatot, amelyet
újra kell olvasni. A tartós hiba: az előző kitöltésben is rossz volt.
"""
from __future__ import annotations

import collections

from .formatum import Kerdes, Kviz

KATEGORIA = {"tudja": "tudod", "szerencses": "szerencsés tipp", "tevkepzet": "tévképzet", "hiany": "hiány"}


class Hiba(ValueError):
    """Hibás kérés (ismeretlen kérdés); az üzenet a kitöltőnek szól."""


def kitoltesre(k: Kviz, jelolesek=frozenset()) -> dict:
    """A kvíz a kitöltéshez: a kulcs, az idézet és a magyarázat NÉLKÜL (azt a válasz után kapja meg)."""
    return {"azon": k.azon, "cim": k.cim, "forras": k.forras, "modell": k.modell, "keszult": k.keszult,
            "kerdesek": [{"id": q.id, "kerdes": q.kerdes, "valaszok": list(q.valaszok), "szakasz": q.szakasz,
                          "jelolt": q.id in jelolesek} for q in k.kerdesek]}


def _kerdes(k: Kviz, kid: str) -> Kerdes:
    for q in k.kerdesek:
        if q.id == kid:
            return q
    raise Hiba(f"nincs ilyen kérdés: {kid}")


def megoldas(k: Kviz, kid: str, valasz: int | None = None) -> dict:
    """Egy kérdés megoldása (a válasz után): helyes-e, a helyes válasz, a magyarázat és az idézet a szakasszal — ide mutat a
    visszajelzés. Nem ír semmit."""
    q = _kerdes(k, kid)
    return {"kerdes": kid, "helyes": isinstance(valasz, int) and not isinstance(valasz, bool) and valasz == q.helyes,
            "helyes_index": q.helyes, "helyes_valasz": q.valaszok[q.helyes], "magyarazat": q.magyarazat, "idezet": q.idezet,
            "szakasz": q.szakasz, "horgony": q.horgony, "jegyzet": k.forras}


def _kategoria(helyes: bool, tipp: bool) -> str:
    if helyes:
        return "szerencses" if tipp else "tudja"
    return "hiany" if tipp else "tevkepzet"


def _elozo_eredmenyek(elozmenyek) -> dict[str, list[bool]]:
    """Kérdésenként az előző kitöltések eredménye, időrendben."""
    ki: dict[str, list[bool]] = collections.defaultdict(list)
    for t in elozmenyek:
        for e in t.get("eredmenyek", []):
            ki[e["kerdes"]].append(bool(e["helyes"]))
    return ki


def kitoltes_ertekel(k: Kviz, valaszok, mod: str = "teljes", elozmenyek=(), jelolesek=frozenset(), ido_ms: int | None = None,
                     szakaszok_cimei: list[str] | None = None, teljes_halmaz: bool = False) -> dict:
    """Egy kitöltés kiértékelése és elemzése.

    `valaszok`: [{kerdes, valasz (a válasz indexe a kvízjegyzetben álló sorrendben, vagy None), tipp (bool), ms}]; az
    ismeretlen és a megismételt kérdés kiesik. `elozmenyek`: a korábbi kitöltések időrendben (`mod`, `osszegzes`,
    `eredmenyek`). `jelolesek`: a „hibás kérdés” jelölések (nem számítanak a pontba). `szakaszok_cimei`: a forrásjegyzet
    szakaszai (a kvíz által nem érintettek jelzéséhez). `teljes_halmaz` (A3-04): a `teljes` kitöltés nevezője a kvíz összes
    érvényes kérdése — a meg nem válaszolt kérdés „hiány” (nem tudom), nem esik ki a pontból; a `hibasak` kör nevezője a
    megválaszolt kérdések száma marad (a kör kérdéshalmazát a kitöltő választja)."""
    jel = set(jelolesek)
    if teljes_halmaz and mod == "teljes":
        megvolt = {v.get("kerdes") for v in valaszok or [] if isinstance(v, dict)}
        valaszok = [*(valaszok or []), *({"kerdes": q.id, "valasz": None, "tipp": True} for q in k.kerdesek if q.id not in megvolt)]
    elozo = _elozo_eredmenyek(elozmenyek)
    ervenyes = {q.id: q for q in k.kerdesek}
    eredmenyek: list[dict] = []
    for sorszam, v in enumerate(valaszok or []):
        kid = v.get("kerdes")
        if kid not in ervenyes or any(e["kerdes"] == kid for e in eredmenyek):
            continue
        q = ervenyes[kid]
        vi = v.get("valasz")
        vi = vi if isinstance(vi, int) and not isinstance(vi, bool) and 0 <= vi < len(q.valaszok) else None
        helyes = vi == q.helyes
        tipp = bool(v.get("tipp")) or vi is None
        e = {"kerdes": kid, "sorszam": q.szam, "valasz": vi, "helyes": helyes, "tipp": tipp, "kategoria": _kategoria(helyes, tipp),
             "jelolt": kid in jel, "ms": int(v["ms"]) if isinstance(v.get("ms"), (int, float)) and not isinstance(v.get("ms"), bool) else None,
             "szakasz": q.szakasz, "horgony": q.horgony, "elozo": elozo[kid][-1] if elozo.get(kid) else None}
        e["tartos"] = not helyes and e["elozo"] is False
        eredmenyek.append(e)
    szamit = [e for e in eredmenyek if not e["jelolt"]]
    pont, osszes = sum(e["helyes"] for e in szamit), len(szamit)
    matrix = collections.Counter(e["kategoria"] for e in szamit)
    biztos = [e for e in szamit if not e["tipp"]]
    tippelt = [e for e in szamit if e["tipp"] and e["valasz"] is not None]

    szak: dict[str, dict] = {}
    for e in szamit:
        s = szak.setdefault(e["szakasz"] or k.cim, {"szakasz": e["szakasz"] or k.cim, "horgony": e["horgony"], "osszes": 0, "helyes": 0,
                                                    "kategoriak": collections.Counter(), "kerdesek": [], "tartos": 0})
        s["osszes"] += 1
        s["helyes"] += e["helyes"]
        s["kategoriak"][e["kategoria"]] += 1
        s["tartos"] += e["tartos"]
        if e["kategoria"] != "tudja":
            s["kerdesek"].append(e["sorszam"])
    szakaszok = []
    for s in szak.values():
        kt = s["kategoriak"]
        s["allapot"] = "rendben" if kt["tudja"] == s["osszes"] else "ingatag" if s["helyes"] == s["osszes"] else "hianyos"
        s["kategoriak"] = dict(kt)
        s["suly"] = 3 * kt["tevkepzet"] + 2 * kt["hiany"] + 2 * s["tartos"] + kt["szerencses"]
        s["prioritas"] = 1 if kt["tevkepzet"] or s["tartos"] else 2 if kt["hiany"] else 3 if kt["szerencses"] else 9
        szakaszok.append(s)
    # egy sorrend mindenhol (javaslatok, a kvízjegyzet „Nézd át” sora, a fő üzenet): előbb a prioritás — a tévképzet és a
    # tartós hiba megelőzi a több, de „csak” hiányzó tudást —, azon belül a súly
    szakaszok.sort(key=lambda s: (s["prioritas"], -s["suly"]))

    trend = None
    if elozmenyek:
        # a százalék csak teljes kitöltések között vethető össze (a „csak a hibásak” kör más kérdéshalmaz)
        teljes = [t for t in elozmenyek if t.get("mod") != "hibasak"]
        e0 = (teljes[-1].get("osszegzes") or {}) if teljes and mod != "hibasak" else {}
        trend = {"elozo_szazalek": e0.get("szazalek"), "javult": sum(1 for e in szamit if e["helyes"] and e["elozo"] is False),
                 "romlott": sum(1 for e in szamit if not e["helyes"] and e["elozo"] is True),
                 "tartos": sum(e["tartos"] for e in szamit)}
    szazalek = round(100 * pont / osszes) if osszes else 0
    osszegzes = {"pont": pont, "osszes": osszes, "szazalek": szazalek, "matrix": {x: matrix.get(x, 0) for x in KATEGORIA},
                 "atnezni": [{"szakasz": s["szakasz"], "horgony": s["horgony"], "kerdesek": s["kerdesek"]} for s in szakaszok if s["suly"]],
                 "jelolt": sorted(e["sorszam"] for e in eredmenyek if e["jelolt"])}
    onismeret = {"biztos": len(biztos), "biztos_helyes": sum(e["helyes"] for e in biztos),
                 "tipp": len(tippelt), "tipp_helyes": sum(e["helyes"] for e in tippelt)}
    fedett = {q.szakasz or k.cim for q in k.kerdesek}
    return {"mod": mod, "eredmenyek": eredmenyek, "osszegzes": osszegzes, "szakaszok": szakaszok,
            "javaslatok": javaslatok(k, szamit, szakaszok), "fo_uzenet": fo_uzenet(osszegzes, szakaszok, onismeret, trend),
            "onismeret": onismeret, "trend": trend,
            "fedetlen_szakaszok": [c for c in (szakaszok_cimei or []) if c and c not in fedett],
            "ujra": [e["kerdes"] for e in szamit if e["kategoria"] != "tudja"], "ido_ms": ido_ms}


def javaslatok(k: Kviz, szamit: list[dict], szakaszok: list[dict]) -> list[dict]:
    """Mit és hol: szakaszonként, prioritás szerint; minden javaslat a jegyzet szakaszára mutat, és hozza a mondatot, amelyet
    újra kell olvasni."""
    qk = {q.id: q for q in k.kerdesek}
    ki = []
    for s in szakaszok:
        if not s["suly"]:
            continue
        sajat = [e for e in szamit if (e["szakasz"] or k.cim) == s["szakasz"] and e["kategoria"] != "tudja"]
        kt = s["kategoriak"]
        teendo, tevk = [], []
        for e in sajat:
            q = qk[e["kerdes"]]
            if e["kategoria"] == "tevkepzet":
                tevk.append({"sorszam": e["sorszam"], "kerdes": q.kerdes, "hitted": q.valaszok[e["valasz"]],
                             "helyes": q.valaszok[q.helyes], "idezet": q.idezet})
        if kt.get("tevkepzet"):
            teendo.append(f"{kt['tevkepzet']} tévképzet: biztosra mentél, de rosszul. Olvasd újra a lenti mondatot, és "
                          "fogalmazd meg a saját szavaiddal, miben más, mint amit gondoltál.")
        if s["tartos"]:
            teendo.append(f"{s['tartos']} kérdés az előző kitöltésben is hibás volt: itt nem elég átfutni — írj a szakaszhoz egy "
                          "saját példát vagy vázlatot, és abból ellenőrizd magad.")
        if kt.get("hiany"):
            teendo.append(f"{kt['hiany']} kérdésre nem tudtad a választ: olvasd el a szakaszt, csukd be, és próbáld fejből "
                          "felidézni a lényegét.")
        if kt.get("szerencses"):
            teendo.append(f"{kt['szerencses']} kérdést eltaláltál, de tippelve: ismételd át röviden, hogy biztos legyen.")
        ki.append({"szakasz": s["szakasz"], "horgony": s["horgony"], "jegyzet": k.forras, "prioritas": s["prioritas"],
                   "cimke": {1: "először ezt", 2: "átnézendő", 3: "rögzítendő"}[s["prioritas"]], "teendok": teendo,
                   "kerdesek": sorted(e["sorszam"] for e in sajat), "tevkepzetek": tevk,
                   "idezetek": list(dict.fromkeys(qk[e["kerdes"]].idezet for e in sajat))[:4]})
    return ki


def fo_uzenet(o: dict, szakaszok: list[dict], onismeret: dict, trend: dict | None) -> str:
    if not o["osszes"]:
        return "Nincs értékelhető válasz."
    m = o["matrix"]
    if m["tudja"] == o["osszes"]:
        uz = "Hibátlan és magabiztos: ez a jegyzet megy. Pár nap múlva ismételd meg, vagy kérj új kvízt (más kérdésekkel)."
    else:
        elso = szakaszok[0]
        mi = ("tévképzet" if elso["kategoriak"].get("tevkepzet") else "tartós hiba" if elso["tartos"]
              else "hiány" if elso["kategoriak"].get("hiany") else "bizonytalan tudás")
        uz = f"{o['szazalek']} %. Először ezt nézd át: {elso['szakasz']} ({mi})."
    b, bh = onismeret["biztos"], onismeret["biztos_helyes"]
    if b >= 3 and bh / b < 0.8:
        uz += f" Önismeret: a biztosnak jelölt válaszaid közül csak {bh}/{b} volt helyes — ahol bizonytalan vagy, jelöld tippnek."
    if trend and trend.get("elozo_szazalek") is not None:
        d = o["szazalek"] - trend["elozo_szazalek"]
        uz += f" Az előző teljes kitöltéshez képest {d:+d} százalékpont (javult {trend['javult']}, romlott {trend['romlott']})."
    elif trend and (trend["javult"] or trend["tartos"]):
        uz += f" Az előző kitöltés hibáiból most {trend['javult']} jó, {trend['tartos']} megint hibás."
    return uz
