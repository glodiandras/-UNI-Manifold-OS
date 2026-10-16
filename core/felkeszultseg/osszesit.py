"""A felkészültség végpontjainak válasza (C28a): a dolgozatok listája és egy dolgozat részlete — **csak olvas**.

Egy dolgozatra: a kötött felkészülési jegyzet témái → témánként a „most” és a „kilátás” (a dolgozat napjára, további
tanulás nélkül) száma és összetevői (`keplet`), a gyenge pontok, az esedékes kártyák, a napi terv (`terv`) a naptári
blokkokkal és a nyitott javaslatokkal. A hiányzó forrás nem hiba: a `adatok` és a `figyelmeztetesek` mondja meg, mi
hiányzik és miért.
"""
from __future__ import annotations

import posixpath
from datetime import date, datetime, time

from .. import szemelyes_db
from ..utvonalak import HttpError
from . import ertekeles, keplet, terv
from .adat import Adatok, Hiany

LEIRAS = ("A téma számát a négy összetevő súlyozott átlaga adja — kártya: a kötött kártyák átlagos FSRS-felidézése; "
          "kvíz: az eredmények időben csökkenő súlyú aránya; frissesség: az utolsó tanulás óta eltelt idő; idő: a tanult "
          "perc a célhoz képest — csak a mért összetevőkön újranormálva, a kevés adat kisebb bizalommal. Szám csak mért "
          "tudásból (kártya vagy kvíz) születik. A dolgozat száma a számmal rendelkező témák átlaga. A kilátás ugyanez a "
          "dolgozat napjára, ha addig nem tanulsz többet.")


def _nev(ut: str) -> str:
    n = posixpath.basename(ut)
    return n[:-3] if n.lower().endswith(".md") else n


def _tau(d: dict, most: datetime) -> datetime:
    """A dolgozat időpontja (a kilátás időpontja): a kezdet, egész naposnál 8:00; legalább a mostani idő."""
    try:
        t = datetime.fromisoformat(d["kezd"]).astimezone(most.tzinfo) if d.get("kezd") else None
    except ValueError:
        t = None
    if t is None or d.get("egesznap"):
        t = datetime.combine(date.fromisoformat(d["nap"]), time(8, 0), tzinfo=most.tzinfo)
    return max(t, most)


def _kotes(k) -> dict | None:
    return None if k is None else {"fok": k.fok, "ok": k.ok}


def _osszetevo(o: keplet.Osszetevo) -> dict:
    return {"nev": o.nev, "ertek": o.ertek, "bizalom": round(o.bizalom, 4), "suly": o.suly, "adat": o.adat}


def _tema(a: Adatok, tema_ut: str, d: dict) -> dict:
    nap = date.fromisoformat(d["nap"])
    jel, reszlet = a.tema_jel(tema_ut, nap, a.most)
    most = keplet.tema_szam(jel, a.b)
    kilatas = None
    if not d["lezart"]:
        kjel, _ = a.tema_jel(tema_ut, nap, _tau(d, a.most))
        kilatas = keplet.tema_szam(kjel, a.b)
    return {"ut": tema_ut, "nev": _nev(tema_ut), "szam": most.szam, "kilatas": None if kilatas is None else kilatas.szam,
            "bizonyitek": round(most.bizonyitek, 4), "ok": most.ok, "szint": keplet.szint(most.szam, a.b),
            "osszetevok": [_osszetevo(o) for o in most.osszetevok], **reszlet}


def _eredmeny(a: Adatok, d: dict) -> tuple[dict | None, dict | None]:
    """A lezárt dolgozat kinyert eredménye (C28b; a „Dolgozat kiértékelő” jegyzetből, `eredmeny.py`), vagy az ellentmondás jelzése.
    Nyitott dolgozatnak nincs eredménye. A forrás, az `eredet` (`mezo` | `szoveg`, C28c) és az indok a felületnek; a vaultba nem
    írunk (a szabott `Eredmény::` mezőt a felhasználó írja)."""
    k = d["kotes"]
    if k is None or not d["lezart"]:
        return None, None
    e = a.eredmenyek().get(k.jegyzet)
    if e is None:
        return None, None
    if e["eredmeny"]:
        r = e["eredmeny"]
        return {"pont": r["pont"], "max": r["max"], "szazalek": r["szazalek"], "forras": r["forras"], "szakasz": e["szakasz_cim"],
                "jegyzet": e["fajl"], "eredet": r.get("eredet", "szoveg")}, None
    return None, e["ellentmondas"] and {**e["ellentmondas"], "szakasz": e["szakasz_cim"], "jegyzet": e["fajl"],
                                        "eredet": e.get("eredet") or "szoveg"}


def ertekel(a: Adatok, d: dict) -> dict:
    """Egy dolgozat értékelése a terv nélkül: téma-sorok, szám, kilátás, lefedettség, gyenge pontok, esedékes kártyák."""
    k = d["kotes"]
    kimenet = {"azon": d["azon"], "cim": d["cim"], "nap": d["nap"], "ora": d["ora"], "napok": d["napok"],
               "tantargy": d["tantargy"], "lezart": d["lezart"], "jegyzet": None if k is None else k.jegyzet,
               "kotes": _kotes(k), "temak": [], "forrasok": [], "onmaga": False}
    if k is not None:
        t = a.temak(k.jegyzet)
        kimenet["forrasok"] = [{"ut": f.ut, "tipus": f.tipus, "oldalak": f.oldalak} for f in t.forrasok]
        kimenet["onmaga"] = t.onmaga
        for x in t.feloldatlan:
            a.figyelmeztet(f"a(z) „{x}” link nem oldható fel")
        kimenet["temak"] = [_tema(a, ut, d) for ut in t.temak]
    kimenet["eredmeny"], kimenet["eredmeny_ellentmondas"] = _eredmeny(a, d)
    szam, van, ossz = keplet.dolgozat_szam([x["szam"] for x in kimenet["temak"]])
    kilatas, _, _ = keplet.dolgozat_szam([x["kilatas"] for x in kimenet["temak"]])
    kimenet.update(szam=szam, kilatas=kilatas, szint=keplet.szint(szam, a.b), lefedettseg={"van": van, "osszes": ossz},
                   gyenge_db=sum(1 for x in kimenet["temak"] if x["szam"] is not None and x["szam"] < a.b.gyenge),
                   nincs_adat_db=sum(1 for x in kimenet["temak"] if x["szam"] is None),
                   esedekes_kartya=sum(x["kartya"]["esedekes"] for x in kimenet["temak"]),
                   uj_kartya=sum(x["kartya"]["uj"] for x in kimenet["temak"]))
    return kimenet


def _naptar_adat(a: Adatok) -> dict:
    n = a.naptar()
    return {"utolso_szinkron": n["utolso_szinkron"], "regi": n["regi"]}


def lista(a: Adatok, nap: date) -> dict:
    """`GET /api/felkeszultseg`: a közelgő dolgozatok összefoglalója."""
    ki = {"nap": nap.isoformat(), "dolgozatok": [], "naptar": None}
    a.forrasok_betolt()
    try:
        dolgozatok = a.dolgozatok()
        ki["naptar"] = _naptar_adat(a)
    except Hiany as e:
        ki.update({"hiba": "The calendar source is not available. Sync the calendar and try again.",
                   "kod": "felkeszultseg.forras_hianyzik", "param": {}})
        dolgozatok = []
    for d in dolgozatok:
        try:
            e = ertekel(a, d)
            ki["dolgozatok"].append({k: e[k] for k in ("azon", "cim", "nap", "ora", "napok", "tantargy", "lezart", "jegyzet", "kotes",
                                                       "szam", "kilatas", "szint", "lefedettseg", "gyenge_db", "nincs_adat_db",
                                                       "esedekes_kartya", "uj_kartya")} | {"temak_db": len(e["temak"])})
        except Exception as x:                    # noqa: BLE001 — egy dolgozat hibája nem viszi el a többit
            ki["dolgozatok"].append({"azon": d["azon"], "cim": d["cim"], "nap": d["nap"], "napok": d["napok"],
                                     "lezart": d["lezart"], "hiba": "This assessment could not be loaded. Try again.",
                                     "kod": "felkeszultseg.ertekeles_hiba", "param": {}})
    ki["adatok"] = a.adatok
    ki["figyelmeztetesek"] = a.figyelmeztetesek
    return ki


def _gyenge_pontok(a: Adatok, e: dict) -> dict:
    mert = sorted((x for x in e["temak"] if x["szam"] is not None and x["szam"] < a.b.gyenge), key=lambda x: (x["szam"], x["nev"]))
    kartyak = sorted(({"azon": c["azon"], "kerdes": c["kerdes"], "felidezes": c["felidezes"], "tema": x["ut"]}
                      for x in e["temak"] for c in x["kartya"]["gyenge"]), key=lambda c: (c["felidezes"], c["azon"]))
    return {"temak": [{"ut": x["ut"], "nev": x["nev"], "szam": x["szam"]} for x in mert],
            "nincs_adat": [{"ut": x["ut"], "nev": x["nev"]} for x in e["temak"] if x["szam"] is None],
            "kartyak": kartyak[:a.m.gyenge_kartya_db]}


def _javaslatok(a: Adatok, azon: str) -> dict[str, dict]:
    """A dolgozat tanulásiblokk-javaslatai napok szerint (a `naptar_javaslat` táblából, csak olvasva)."""
    try:
        with szemelyes_db.olvaso(a.cfg, 3) as c:
            if c is None:
                return {}
            return {r["nap"]: {"id": r["id"], "allapot": r["allapot"]} for r in c.execute(
                "SELECT id, nap, allapot FROM naptar_javaslat WHERE dolgozat = ? ORDER BY id", (azon,))}
    except Exception:                              # noqa: BLE001
        return {}


def terv_szamolas(a: Adatok, d: dict, e: dict) -> terv.TervEredmeny:
    """A dolgozat napi terve az értékelésből (a végpont és a javaslat-forrás közös szabálya)."""
    if d['napok'] <= 0 or not e['temak']:
        return terv.napi_terv([terv.Tema(x['ut'], x['nev'], x['szam']) for x in e['temak']], a.ma,
            date.fromisoformat(d['nap']), a.b, napi_perc=a.m.napi_perc, szelet_perc=a.m.szelet_perc, max_nap=a.m.max_terv_nap)
    if a.kozos_tervek is None:
        vizsgak = []
        for vizsga in a.dolgozatok():
            if vizsga['lezart'] or vizsga['napok'] <= 0:
                continue
            if vizsga['azon'] == d['azon']:
                adat = e
            else:
                try:
                    with a.figyelmeztetes_nelkul():     # a másik dolgozat figyelmeztetése nem ennek a dolgozatnak szól
                        adat = ertekel(a, vizsga)
                except Exception:                       # noqa: BLE001 — egy másik dolgozat hibája nem viszi el ennek a tervét
                    continue
            vizsgak.append((vizsga['azon'], date.fromisoformat(vizsga['nap']),
                           [terv.Tema(x['ut'], x['nev'], x['szam']) for x in adat['temak']]))
        foglalt = {}
        for ev in a.naptar()['esemenyek']:
            if ev.get('kategoria') != 'tanulas' or ev.get('egesznap'):
                continue
            try:
                from datetime import datetime
                kezd, veg = datetime.fromisoformat(ev['kezd']), datetime.fromisoformat(ev['veg'])
                nap = kezd.date().isoformat()
                foglalt[nap] = foglalt.get(nap, 0) + max(0, round((veg - kezd).total_seconds() / 60))
            except (ValueError, KeyError, TypeError):
                continue
        a.kozos_tervek = terv.kozos_terv(vizsgak, a.ma, a.b, napi_perc=a.m.napi_perc,
            szelet_perc=a.m.szelet_perc, max_nap=a.m.max_terv_nap, foglalt=foglalt)
    return a.kozos_tervek.get(d['azon'], terv.TervEredmeny([], 'Nincs tervezhető téma.'))


def _terv(a: Adatok, d: dict, e: dict) -> dict:
    t = terv_szamolas(a, d, e)
    napok = [x.nap for x in t.napok]
    esedekes = a.esedekes_napra([x["ut"] for x in e["temak"]], napok)
    javaslat = _javaslatok(a, d["azon"])
    blokkok: dict[str, list[dict]] = {}
    for ev in a.naptar()["esemenyek"]:
        if ev.get("kategoria") == "tanulas" and not ev.get("egesznap") and (not d["targyak"] or set(ev.get("targyak") or ()) & set(d["targyak"])):
            blokkok.setdefault((ev.get("nap") or ev.get("kezd") or "")[:10], []).append(
                {"kezd": ev.get("kezd"), "veg": ev.get("veg"), "cim": ev.get("cim")})
    # A már elfogadott naptári blokk akkor is látszik, ha aznap elfogyasztotta a teljes keretet.
    teljes = {n.nap: n for n in t.napok}
    for nap in blokkok:
        if a.ma.isoformat() <= nap < d['nap'] and nap not in teljes:
            teljes[nap] = terv.Nap(nap, 0, ())
    return {"uzenet": t.uzenet, "napok": [
        {"nap": n.nap, "perc": n.perc, "kartya_esedekes": esedekes.get(n.nap, 0), "naptar": blokkok.get(n.nap, []),
         "javaslat": javaslat.get(n.nap),
         "szeletek": [{"tema_ut": s.tema_ut, "tema": s.tema, "perc": s.perc, "ok": s.ok} for s in n.szeletek]} for n in sorted(teljes.values(), key=lambda n: n.nap)]}


def keplet_leiras(b: keplet.Beallitas) -> dict:
    return {"suly": {"kartya": b.suly_kartya, "kviz": b.suly_kviz, "frissesseg": b.suly_frissesseg, "ido": b.suly_ido},
            "min_bizonyitek": b.min_bizonyitek, "cel": b.cel, "gyenge": b.gyenge, "jo": b.jo, "kalibralt": b.kalibralt,
            "kartya_n0": b.kartya_n0, "kviz_n0": b.kviz_n0, "felezes_nap": b.felezes_nap, "cel_perc": b.cel_perc,
            "leiras": LEIRAS}


def reszlet(a: Adatok, azon: str) -> dict:
    """`GET /api/felkeszultseg/dolgozat`: egy dolgozat teljes értékelése a témákkal, a gyenge pontokkal és a tervvel."""
    try:
        dolgozatok = a.dolgozatok()
    except Hiany as e:
        raise HttpError(404, str(e), kod="felkeszultseg.forras_hianyzik") from None
    d = next((x for x in dolgozatok if x["azon"] == azon), None)
    if d is None:
        raise HttpError(404, "nincs ilyen dolgozat a naptárban (vagy már kívül esik az ablakon)", kod="felkeszultseg.osszesit.nincs_dolgozat")
    a.forrasok_betolt()
    e = ertekel(a, d)
    if d["kotes"] is None:
        a.figyelmeztet("Ehhez a dolgozathoz nincs felkészülési jegyzet: hozz létre egyet "
                       f"({a.m.dolgozat_mappa}/ÉÉÉÉ-HH-NN - Tantárgy.md, a Source és az NN mezőben a témák linkjeivel).")
    elif d["kotes"].fok != "biztos":
        a.figyelmeztet(f"A felkészülési jegyzet kötése nem biztos ({d['kotes'].fok}): {d['kotes'].ok}.")
    e["gyenge_pontok"] = _gyenge_pontok(a, e)
    e["terv"] = _terv(a, d, e)
    e["keplet"] = keplet_leiras(a.b)
    e["naptar"] = _naptar_adat(a)
    e["adatok"] = {k: a.adatok.get(k, {"van": None}) for k in ("kartya", "kviz", "tracker", "eredmeny")}
    e["figyelmeztetesek"] = a.figyelmeztetesek
    e["ertekeles_kulcs"] = ertekeles.tenyek(e, a.ma)["kulcs"]       # C28b: a szöveges értékelés elavulásának jelzése a felületen
    return e
