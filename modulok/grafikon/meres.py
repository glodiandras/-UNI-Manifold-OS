"""A determinisztikus felismerés mérése (C35a): a C18 `grafikon` aranyhalmaza (15 képlet) és egy szintetikus
kiegészítő halmaz. Csak olvas; `bin/mos grafikon arany` kiírja a riportot.

Mérőszámok (a modell-ág, C35b, ehhez viszonyít):
- **biztos_helyes**: a javaslat `biztos`, a kifejezése egyezik a várttal (`kozos.matek.kifejezes_egyezik`), és a
  blokk visszaelemezve azonos az ábrával;
- **biztos_rossz**: `biztos`, de téves (a kapu: 0 kell legyen: a bizonytalan jobb a tévesnél);
- **bizonytalan**: a döntés a modell-ágra marad; **nincs**: nem grafikon-alapanyag;
- **lefedes** (csak az aranyhalmazon): a javasolt x-ablak tartalmazza a várt zérushelyeket és szélsőérték-helyeket.
A zérushely, szélsőérték és aszimptota **kiszámítása** a C35b CAS-os dolga, itt nem mérjük.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import sympy as sp

from . import felismeres as R
from . import formatum as F

_matek = R._matek

# (képlet, várt fajta, várt bizonyosság, várt kifejezés (függvénynél) | None)
KIEGESZITO = [
    (r"y = x^2 - 4x + 3", "fuggveny", "biztos", "x^2-4*x+3"),
    (r"f(x) = \frac{1}{2}x + 1", "fuggveny", "biztos", "x/2+1"),
    (r"g(x) = e^{-x^2}", "fuggveny", "biztos", "exp(-x^2)"),
    (r"y = \cos x", "fuggveny", "biztos", "cos(x)"),
    (r"h(x) = \sqrt[3]{x}", "fuggveny", "biztos", "root(x,3)"),
    (r"y = x^2, \quad x \in [-2, 3]", "fuggveny", "biztos", "x^2"),
    (r"f(x) = \ln x, x > 0", "fuggveny", "biztos", "log(x)"),
    (r"y = 2^x", "fuggveny", "biztos", "2^x"),
    (r"y = \sqrt{x-1}", "fuggveny", "biztos", "sqrt(x-1)"),
    (r"y = |x - 2| + 1", "fuggveny", "biztos", "Abs(x-2)+1"),
    (r"f(t) = t^3 - t", "fuggveny", "biztos", "x^3-x"),
    (r"y = \sin x + \cos x", "fuggveny", "biztos", "sin(x)+cos(x)"),
    (r"x = 3\cos t, \; y = 2\sin t, \; t \in [0, 2\pi]", "parameteres", "biztos", None),
    (r"x(t) = t^2, y(t) = t^3, -1 \le t \le 1", "parameteres", "biztos", None),
    (r"y \ge x^2 - 1", "egyenlotlenseg", "biztos", None),
    (r"y < -x + 3", "egyenlotlenseg", "biztos", None),
    (r"x^2 \le y", "egyenlotlenseg", "biztos", None),
    (r"\begin{tikzpicture}\begin{axis}\addplot[domain=-2:2]{x^3};\end{axis}\end{tikzpicture}", "tikz", "biztos", None),
    (r"\begin{tikzpicture}\draw[domain=0:2] plot (\x,{\x*\x});\end{tikzpicture}", "tikz", "biztos", None),
    (r"\begin{tikzpicture}\begin{axis}\addplot[domain=0:2*pi]{sin(deg(x))};\end{axis}\end{tikzpicture}", "tikz", "biztos", None),
    (r"y = \frac{1}{x}", "fuggveny", "bizonytalan", None),
    (r"y = \tan x", "fuggveny", "bizonytalan", None),
    (r"y = \frac{x+1}{x-1}", "fuggveny", "bizonytalan", None),
    (r"y = ax + b", "nem_abra", "bizonytalan", None),
    (r"y = 3", "fuggveny", "bizonytalan", None),
    (r"x = \cos t, y = \sin t", "parameteres", "bizonytalan", None),
    (r"x^2 + y^2 = 1", "implicit", "bizonytalan", None),
    (r"f(x) = \begin{cases} x & x > 0 \\ -x & x \le 0 \end{cases}", "szakaszonkent", "bizonytalan", None),
    (r"\begin{tikzpicture}\begin{axis}\addplot[domain=0:360]{sin(x)};\end{axis}\end{tikzpicture}", "tikz", "bizonytalan", None),
    (r"2x + 1 = 0", "nem_abra", "nincs", None),
    (r"f(2) = 5", "nem_abra", "nincs", None),
    (r"f'(x) = 2x", "nem_abra", "nincs", None),
    (r"\sin^2 x + \cos^2 x = 1", "nem_abra", "nincs", None),
    (r"x = 3", "nem_abra", "nincs", None),
    (r"a^2 + b^2 = c^2", "nem_abra", "nincs", None),
    (r"\frac{a}{b}", "nem_abra", "nincs", None),
]


def _korut_ok(j: R.Javaslat) -> bool:
    """A blokk szövege visszaelemezve ugyanazt az ábrát adja, és hibátlan."""
    if j.abra is None:
        return False
    torzs = j.blokk.split("\n", 1)[1].rsplit("```", 1)[0]
    vissza = F.elemez(torzs)
    return vissza == j.abra and not vissza.hibak and F.szerializal(vissza) == F.szerializal(j.abra)


def _kif_egyezik(j: R.Javaslat, vart: str) -> bool:
    if j.abra is None or len(j.abra.elemek) != 1 or not isinstance(j.abra.elemek[0], F.Fuggveny):
        return False
    try:
        return _matek.kifejezes_egyezik(_matek.elemez(vart), _matek.elemez(j.abra.elemek[0].kifejezes), 1e-6)
    except _matek.MatekHiba:
        return False


def _lefedes(j: R.Javaslat, vart: dict) -> bool:
    """A javasolt x-ablak tartalmazza a várt zérushelyeket és szélsőérték-helyeket."""
    if j.abra is None or j.abra.x_tartomany is None:
        return False
    lo = float(sp.N(_matek.elemez(j.abra.x_tartomany[0])))
    hi = float(sp.N(_matek.elemez(j.abra.x_tartomany[1])))
    helyek = list(vart.get("zerushelyek", [])) + [p["x"] for p in vart.get("szelsoertekek", [])]
    return all(lo <= float(sp.N(_matek.elemez(h))) <= hi for h in helyek)


def meres_arany(arany: dict) -> dict:
    tetelek, szamlalo = [], {"biztos_helyes": 0, "biztos_rossz": 0, "bizonytalan": 0, "nincs": 0, "lefedes": 0}
    for k in arany["kepletek"]:
        j = R.felismer(k["keplet"])
        helyes = j.bizonyossag == R.BIZTOS and _kif_egyezik(j, k["vart"]["kifejezes"]) and _korut_ok(j)
        lefed = helyes and _lefedes(j, k["vart"])
        if j.bizonyossag == R.BIZTOS:
            szamlalo["biztos_helyes" if helyes else "biztos_rossz"] += 1
        else:
            szamlalo["bizonytalan" if j.bizonyossag == R.BIZONYTALAN else "nincs"] += 1
        szamlalo["lefedes"] += bool(lefed)
        tetelek.append({"id": k["id"], "bizonyossag": j.bizonyossag, "helyes": bool(helyes), "lefedes": bool(lefed),
                        "ok": j.ok, "blokk": j.blokk})
    return {"osszes": len(tetelek), **szamlalo, "tetelek": tetelek}


def meres_kiegeszito() -> dict:
    tetelek, szamlalo = [], {"biztos_helyes": 0, "biztos_rossz": 0, "bizonytalan_jo": 0, "bizonytalan_biztos_helyett": 0,
                             "nincs_jo": 0, "tevedes": 0}
    for keplet, fajta, bizonyossag, vart in KIEGESZITO:
        j = R.felismer(keplet)
        jo_fajta = j.fajta == fajta
        jo_kif = vart is None or _kif_egyezik(j, vart)
        if j.bizonyossag == R.BIZTOS:
            if jo_fajta and jo_kif and _korut_ok(j) and bizonyossag == "biztos":
                szamlalo["biztos_helyes"] += 1
            else:
                szamlalo["biztos_rossz"] += 1
        elif j.bizonyossag == R.BIZONYTALAN:
            szamlalo["bizonytalan_jo" if bizonyossag == "bizonytalan" else "bizonytalan_biztos_helyett"] += 1
        else:
            szamlalo["nincs_jo" if bizonyossag == "nincs" else "tevedes"] += 1
        tetelek.append({"keplet": keplet, "kapott": (j.fajta, j.bizonyossag), "vart": (fajta, bizonyossag), "ok": j.ok})
    return {"osszes": len(tetelek), **szamlalo, "tetelek": tetelek}


def valasz_alak(eredmeny: dict, kifejezes: str) -> dict:
    """Az `elemzes.elemez` kimenete a modell válaszának alakjában (`modulok/eval/grafikon/feladat.py` PROMPT): így az
    aranyhalmaz pontozója a CAS-jellemzőket ugyanúgy értékeli, mint a modellét."""
    return {"valtozo": "x", "kifejezes": kifejezes,
            "zerushelyek": [p["x"] for p in eredmeny.get("zerushelyek", [])],
            "szelsoertekek": [{"x": p["x"], "y": p["y"]} for p in eredmeny.get("szelsoertekek", [])],
            "aszimptotak": [a["egyenlet"] for a in eredmeny.get("aszimptotak", [])]}


def _feladat_modul():
    """A C18 aranyhalmaz-pontozó (`modulok/eval/grafikon/feladat.py`), a core betöltőjének módján."""
    import importlib.util
    ut = Path(R.__file__).resolve().parents[1] / "eval" / "grafikon" / "feladat.py"
    spec = importlib.util.spec_from_file_location("mos_eval_grafikon_meres", ut)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _ablak(szoveg: str) -> list[str]:
    a, b = szoveg.strip("[]").split(",")
    return [a.strip(), b.strip()]


def _elso_fuggveny(j: dict) -> str | None:
    e = ((j.get("abra") or {}).get("elemek") or [None])[0]
    return e["kifejezes"] if e and e["fajta"] == "fuggveny" else None


def arany_riport(hk=None) -> dict:
    """A C35a mérése a homokozón át (csak olvas): (1) a felismerés a `keplet`-ből, (2) a CAS-jellemzők a modell
    pontozójával (`feladat.pontoz_egyet`), (3) a felismerés a `szoveg` `$…$` képleteiből, (4) a cloud szintetikus
    halmaza, (5) hogy a homokozó és a folyamaton belüli út azonos eredményt ad."""
    import grafikon as G
    feladat = _feladat_modul()
    arany = feladat.ARANY["kepletek"]
    hk = G._homokozo(hk)
    # (1) felismerés a homokozóban
    kepletek = [k["keplet"] for k in arany]
    javaslatok = G.felismerek(kepletek, homokozo=hk)
    # (2) CAS-jellemzők, tételenként a saját ablakukon (egy gyermek)
    lepes = float(hk.beall["lepes_idokorlat_s"])
    kifejezesek = [_elso_fuggveny(j) for j in javaslatok]
    jelenti = hk.futtat([G._elemzes_feladat(kif or "x", _ablak(k["vart"]["ablak"]), lepes) for kif, k in zip(kifejezesek, arany)],
                        idokorlat_s=lepes * 6 + 2)
    felism = {"biztos_helyes": 0, "biztos_rossz": 0, "bizonytalan": 0, "nincs": 0, "lefedes": 0}
    jell = {"pontszam": 0.0, "zerushelyek": 0, "szelsoertekek": 0, "aszimptotak": 0, "tipus": 0, "reszleges": 0, "numerikus": 0}
    tetelek = []
    for k, j, kif, e in zip(arany, javaslatok, kifejezesek, jelenti):
        vart = k["vart"]
        helyes = bool(j["bizonyossag"] == "biztos" and kif and _kif_szoveg_egyezik(kif, vart["kifejezes"]))
        if j["bizonyossag"] == "biztos":
            felism["biztos_helyes" if helyes else "biztos_rossz"] += 1
        else:
            felism["bizonytalan" if j["bizonyossag"] == "bizonytalan" else "nincs"] += 1
        lo, hi = (float(sp.N(_matek.elemez(x))) for x in (j["abra"]["x_tartomany"] if j.get("abra") and j["abra"]["x_tartomany"] else ("0", "0")))
        helyek = list(vart.get("zerushelyek", [])) + [p["x"] for p in vart.get("szelsoertekek", [])]
        lefed = bool(helyes and all(lo <= float(sp.N(_matek.elemez(h))) <= hi for h in helyek))
        felism["lefedes"] += lefed
        t = {"id": k["id"], "bizonyossag": j["bizonyossag"], "helyes": helyes, "lefedes": lefed, "blokk": j["blokk"]}
        if e["allapot"] == "ok" and kif:
            r = e["ertek"]
            pont = feladat.pontoz_egyet(vart, json.dumps(valasz_alak(r, kif)))
            tipus_jo = sorted((round(float(sp.N(_matek.elemez(p["x"]))), 6), p["tipus"]) for p in r["szelsoertekek"]) == \
                sorted((round(float(sp.N(_matek.elemez(p["x"]))), 6), p["tipus"]) for p in vart["szelsoertekek"])
            jell["pontszam"] += pont["pont"]
            for kulcs in ("zerushelyek", "szelsoertekek", "aszimptotak"):
                jell[kulcs] += bool(pont[kulcs])
            jell["tipus"] += tipus_jo
            jell["reszleges"] += r["allapot"] != "ok"
            jell["numerikus"] += bool(r["numerikus"])
            t.update(pont=pont["pont"], tipus_jo=tipus_jo, jellemzok_allapot=r["allapot"])
        else:
            t.update(pont=0.0, tipus_jo=False, jellemzok_allapot=e["allapot"])
        tetelek.append(t)
    jell["pontszam"] = round(jell["pontszam"] / len(arany), 4)
    # (3) kontextus: a `szoveg` `$…$` képleteiből is megvan-e a cél, és mi a többlet
    kontextus = {"tetelek": 0, "megtalalt": 0, "hianyzik": [], "tobblet": []}
    for k in arany:
        if "$" not in k["szoveg"]:
            continue
        kontextus["tetelek"] += 1
        talalatok = [j for j in G.felismer_jegyzet(k["szoveg"], homokozo=hk) if j["bizonyossag"] == "biztos"]
        cel = [j for j in talalatok if _elso_fuggveny(j) and _kif_szoveg_egyezik(_elso_fuggveny(j), k["vart"]["kifejezes"])]
        kontextus["megtalalt"] += bool(cel)
        if not cel:
            kontextus["hianyzik"].append(k["id"])
        kontextus["tobblet"] += [{"id": k["id"], "keplet": j["forras_keplet"]} for j in talalatok if j not in cel]
    # (4) a cloud szintetikus halmaza (folyamaton belül mérve) és (5) a homokozó azonossága
    kieg = meres_kiegeszito()
    minden = kepletek + [k[0] for k in KIEGESZITO]
    sandbox = javaslatok + G.felismerek([k[0] for k in KIEGESZITO], homokozo=hk)
    elteres = []
    for keplet, s in zip(minden, sandbox):
        folyamat = R.felismer(keplet)
        if (s["bizonyossag"], s["fajta"], s["blokk"], s["kulcs"]) != (folyamat.bizonyossag, folyamat.fajta, folyamat.blokk, folyamat.kulcs):
            elteres.append(keplet)
    return {"verzio": feladat.VERZIO, "osszes": len(arany), "felismeres": felism, "jellemzok": jell, "kontextus": kontextus,
            "kiegeszito": {k: v for k, v in kieg.items() if k != "tetelek"},
            "azonossag": {"osszes": len(minden), "azonos": len(minden) - len(elteres), "elteres": elteres},
            "tetelek": tetelek}


def _kif_szoveg_egyezik(kapott: str, vart: str) -> bool:
    try:
        return _matek.kifejezes_egyezik(_matek.elemez(vart), _matek.elemez(kapott), 1e-6)
    except _matek.MatekHiba:
        return False


def riport_szoveg(r: dict) -> str:
    f, j, k, c, a = r["felismeres"], r["jellemzok"], r["kontextus"], r["kiegeszito"], r["azonossag"]
    n = r["osszes"]
    sorok = [
        f"Grafikon-mérés — a `grafikon` aranyhalmaza ({r['verzio']}, {n} képlet), a CAS-homokozón át",
        f"felismerés (a `keplet`-ből): biztos és helyes {f['biztos_helyes']}/{n}, biztosan rossz {f['biztos_rossz']}, "
        f"bizonytalan {f['bizonytalan']}, nincs {f['nincs']}; a javasolt ablak lefedi a várt pontokat {f['lefedes']}/{n}",
        f"CAS-jellemzők (a modell pontozója): zérushely {j['zerushelyek']}/{n}, szélsőérték {j['szelsoertekek']}/{n}, "
        f"aszimptota {j['aszimptotak']}/{n}, szélsőérték-típus {j['tipus']}/{n}; pontszám átlag {j['pontszam']:.3f}; "
        f"részleges {j['reszleges']}, numerikus {j['numerikus']}",
        f"kontextus (a `szoveg` `$…$` képleteiből): a cél megvan {k['megtalalt']}/{k['tetelek']}"
        f"{' (hiányzik: ' + ', '.join(k['hianyzik']) + '; egyenlőség-lánc/implicit: a modell-ágra marad)' if k['hianyzik'] else ''}; "
        f"többlet-javaslat (nem hiba) {len(k['tobblet'])}",
        f"szintetikus kiegészítő halmaz ({c['osszes']} tétel; nem jóváhagyott): biztos és helyes {c['biztos_helyes']}, "
        f"biztosan rossz {c['biztos_rossz']}, helyesen bizonytalan {c['bizonytalan_jo']}, helyesen „nincs” {c['nincs_jo']}, "
        f"téves {c['tevedes'] + c['bizonytalan_biztos_helyett']}",
        f"a homokozó és a folyamaton belüli út azonos: {a['azonos']}/{a['osszes']}",
    ]
    rendben = (f["biztos_helyes"] == n and f["biztos_rossz"] == 0 and f["lefedes"] == n and j["pontszam"] == 1.0
               and j["tipus"] == n and c["biztos_rossz"] == 0 and c["tevedes"] == 0 and a["elteres"] == [])
    sorok.append("RENDBEN" if rendben else "ELTÉRÉS — nézd a tételenkénti riportot (--json)")
    return "\n".join(sorok)


def main(argv=None, hk=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if sys.platform != "darwin" and type(hk).__name__ == "Homokozo":
        print("[indokolt] a valódi mérés a macOS sandbox-exec homokozóján át fut; ezen a rendszeren nem mérhető "
              "(a valódi homokozó zárva hibázik). A folyamaton belüli út a tesztben (tests.test_grafikon_meres) mérve.")
        return 3
    r = arany_riport(hk)
    if "--json" in argv:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        print(riport_szoveg(r))
    return 0 if riport_szoveg(r).endswith("RENDBEN") else 1


if __name__ == "__main__":
    sys.exit(main())
