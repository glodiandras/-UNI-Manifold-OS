"""Ál-EventKit a C29 tesztjeihez: a Manifold.app `--naptar` CLI-módjának protokollját (docs/C29-TERV.md, 2.) adja
egy JSON-állapotfájlból (`MOS_ALARM_ALLAPOT`). Valódi naptárhoz vagy emlékeztetőkhöz nem nyúl.

Használat: `naptar_seged_alarm.py --naptar <parancs>` — a kérés a stdinen, a válasz a stdouton.
"""
import json
import os
import sys
from datetime import datetime


def _betolt(ut):
    with open(ut, encoding="utf-8") as f:
        return json.load(f)


def _ment(ut, d):
    tmp = ut + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, ut)


def _most():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _kiir(valasz):
    sys.stdout.write(json.dumps(valasz, ensure_ascii=False))
    sys.stdout.flush()


def _lista(d, nev):
    return d.get("listak", {}).get(nev)


def _emlekezteto_kimenet(r):
    return {k: r.get(k) for k in ("azon", "kulso", "cim", "hatarido", "ora", "kesz", "kesz_ido", "modositva", "jegyzet")}


def main():
    if len(sys.argv) < 3 or sys.argv[1] != "--naptar":
        return _kiir({"ok": False, "hiba": "ismeretlen hívás"})
    parancs = sys.argv[2]
    ut = os.environ["MOS_ALARM_ALLAPOT"]
    d = _betolt(ut)
    d.setdefault("hivasok", []).append(parancs)
    try:
        kerelem = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return _kiir({"ok": False, "hiba": "hibás JSON a kérésben"})
    if d.get("hiba_parancs") == parancs:                       # a teszt hibát kényszeríthet
        _ment(ut, d)
        return _kiir({"ok": False, "hiba": d.get("hiba_uzenet", "ál-hiba")})
    es, em = d.get("esemeny", "engedelyezve"), d.get("emlekezteto", "engedelyezve")

    if parancs == "allapot":
        _ment(ut, d)
        return _kiir({"ok": True, "esemeny": es, "emlekezteto": em})
    if parancs == "kerd":
        if kerelem.get("esemeny") and es == "nincs_dontes":
            d["esemeny"] = es = d.get("kerd_eredmeny", "engedelyezve")
        if kerelem.get("emlekezteto") and em == "nincs_dontes":
            d["emlekezteto"] = em = d.get("kerd_eredmeny", "engedelyezve")
        _ment(ut, d)
        return _kiir({"ok": True, "esemeny": es, "emlekezteto": em})
    if parancs == "olvas":
        _ment(ut, d)
        ki = {"ok": True, "verzio": 2, "allapot": es, "most": _most(), "tol": kerelem.get("tol"), "ig": kerelem.get("ig"),
              "idozona": "Europe/Budapest", "naptarak": [], "esemenyek": []}
        if es == "engedelyezve":
            ki["naptarak"], ki["esemenyek"] = d.get("naptarak", []), d.get("esemenyek", [])
        return _kiir(ki)
    if parancs == "emlekeztetok":
        _ment(ut, d)
        nev = kerelem.get("lista") or "Manifold"
        l = _lista(d, nev)
        ki = {"ok": True, "allapot": em, "lista": None, "emlekeztetok": []}
        if em == "engedelyezve" and l:
            ki["lista"] = {"azon": l["azon"], "nev": nev, "forras": l.get("forras", "")}
            ki["emlekeztetok"] = [_emlekezteto_kimenet(r) for r in d.get("emlekeztetok", {}).values() if r.get("lista") == nev]
        return _kiir(ki)
    if parancs == "emlekezteto-ir":
        if em != "engedelyezve":
            _ment(ut, d)
            return _kiir({"ok": False, "hiba": f"nincs emlékeztető-engedély ({em})"})
        nev = kerelem.get("lista") or "Manifold"
        l = _lista(d, nev)
        uj_lista = False
        if not l:
            d.setdefault("listak", {})[nev] = l = {"azon": f"LISTA-{len(d.get('listak', {})) + 1}",
                                                    "forras": kerelem.get("forras") or "iCloud"}
            uj_lista = True
        eredmeny = []
        rems = d.setdefault("emlekeztetok", {})
        for m in kerelem.get("muveletek", []):
            op, kulcs, azon = m.get("op"), m.get("kulcs"), m.get("azon")
            if op == "uj":
                d["sorszam"] = d.get("sorszam", 0) + 1
                azon = f"REM-{d['sorszam']}"
                rems[azon] = {"azon": azon, "kulso": f"EXT-{d['sorszam']}", "lista": nev, "cim": m.get("cim"),
                              "hatarido": m.get("hatarido"), "ora": kerelem.get("ora"), "kesz": False, "kesz_ido": None,
                              "modositva": _most(), "jegyzet": m.get("jegyzet", ""), "riasztas": bool(kerelem.get("riasztas"))}
                eredmeny.append({"kulcs": kulcs, "ok": True, "azon": azon, "kulso": rems[azon]["kulso"]})
                continue
            r = rems.get(azon)
            if not r or r.get("lista") != nev:
                eredmeny.append({"kulcs": kulcs, "ok": False, "nincs": True, "hiba": "nincs ilyen emlékeztető"})
                continue
            if op == "modosit":
                for k in ("cim", "hatarido", "jegyzet"):
                    if k in m:
                        r[k] = m[k]
                r["ora"] = kerelem.get("ora")
            elif op == "kesz":
                r["kesz"], r["kesz_ido"] = True, _most()
            elif op == "nyit":
                r["kesz"], r["kesz_ido"] = False, None
            elif op == "torol":
                del rems[azon]
                eredmeny.append({"kulcs": kulcs, "ok": True, "azon": azon})
                continue
            else:
                eredmeny.append({"kulcs": kulcs, "ok": False, "hiba": f"ismeretlen művelet: {op}"})
                continue
            r["modositva"] = _most()
            eredmeny.append({"kulcs": kulcs, "ok": True, "azon": azon, "kulso": r.get("kulso")})
        _ment(ut, d)
        return _kiir({"ok": True, "lista": {"azon": l["azon"], "nev": nev, "forras": l.get("forras", ""), "uj": uj_lista},
                      "eredmeny": eredmeny})
    if parancs == "esemeny-ir":
        j = (kerelem.get("jovahagyva") or {}).get("javaslat")
        if j is None:
            _ment(ut, d)
            return _kiir({"ok": False, "hiba": "jóváhagyás nélkül naptáresemény nem írható"})
        n = next((x for x in d.get("naptarak", []) if x["azon"] == kerelem.get("naptar")), None)
        if es != "engedelyezve" or not n or not n.get("irhato"):
            _ment(ut, d)
            return _kiir({"ok": False, "hiba": "a naptár nem írható"})
        d["sorszam"] = d.get("sorszam", 0) + 1
        azon = f"EVT-{d['sorszam']}"
        e = {"azon": f"{azon}|{kerelem['kezd']}", "naptar": n["azon"], "cim": kerelem["cim"], "kezd": kerelem["kezd"],
             "veg": kerelem["veg"], "nap": kerelem["kezd"][:10], "egesznap": False, "ismetlodo": False,
             "leszakitott": False, "allapot": 1, "jegyzet": kerelem.get("jegyzet", "")}
        d.setdefault("esemenyek", []).append(e)
        d.setdefault("esemeny_irasok", []).append({"javaslat": j, "azon": e["azon"], "naptar": n["azon"]})
        _ment(ut, d)
        return _kiir({"ok": True, "azon": e["azon"], "naptar": n["azon"]})
    _ment(ut, d)
    return _kiir({"ok": False, "hiba": f"ismeretlen parancs: {parancs}"})


if __name__ == "__main__":
    main()
