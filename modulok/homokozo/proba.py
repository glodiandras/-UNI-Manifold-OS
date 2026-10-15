"""A homokozó biztonsági próbái (C24a): a tesztek és a `bin/mos matek homokozo-proba` közös készlete.

Minden próba egy kitörési kísérlet, és akkor RENDBEN, ha a homokozó nem engedi (az állapot nem `ok`, illetve az
elvárt). A kitörések a SymPy `sympify`-án át mennek, mert az a Python-szintű fehérlistát megkerüli: így a
`sandbox-exec` profilt mérik, nem a fehérlistát. A próbák csak olvasást kísérelnek meg a vaultban és a home-ban;
írni csak a `{tmp}` alá próbálnak, és utána a szülő ellenőrzi, hogy a fájl nem jött létre.

Az elszigetelési próbák (Javító 1, Audit 3 A3-02) kötegeket futtatnak: egy támadó `kod` feladat után becsületes
feladatok jönnek, és a próba akkor RENDBEN, ha azok eredménye a támadás mellett is helyes.
"""
from __future__ import annotations

import json
from pathlib import Path

HAMIS = {"allapot": "ok", "ertek": {"tipus": "halmaz", "elemek": ["42"]}, "uzenet": "", "mp": 0.0}
BECSULETES = {"muvelet": "kod", "kod": "import sympy as sp\nx = sp.Symbol('x')\nEREDMENY = sp.solveset(x**2 - 4, x)"}
BECSULETES_ERTEK = {"tipus": "halmaz", "elemek": ["-2", "2"]}
HIVAS = {"muvelet": "hivas", "nev": "homokozo.alvas", "args": {"mp": 0}}


def _kitores(py: str) -> str:
    """Python-kifejezés a SymPy `eval`-ján át (a fehérlista megkerülése)."""
    return f"import sympy as sp\nEREDMENY = sp.sympify({py!r})"


def vegrehajt_csere() -> dict:
    """Támadás: a gyermek `vegrehajt` függvényét hamisra cseréli (a köteg későbbi tételeinek hamisítása, A3-02)."""
    belso = ("import sys\nm = sys.modules['__main__']\n"
             f"m.vegrehajt = lambda f, *a, **k: dict({HAMIS!r}, azonosito=f.get('azonosito'))")
    return {"muvelet": "kod", "kod": _kitores(f"__import__('builtins').exec({belso!r})")}


def leirora_ir(sor: bytes) -> dict:
    """Támadás: `sor`-t ír minden nyitott leíróra (a protokoll-leíróra is) a saját feladata közben."""
    belso = (f"import os\nfor i in range(2, 64):\n    try:\n        os.write(i, {sor!r})\n"
             "    except OSError:\n        pass")
    return {"muvelet": "kod", "kod": _kitores(f"__import__('builtins').exec({belso!r})")}


def sajat_azonositoval(sor: dict) -> dict:
    """Támadás: a saját feladata azonosítóját a hívási keretekből kiolvassa, és azzal ír `sor`-t a protokoll-leíróra
    (a szülőnek a sor alakja miatt kell elutasítania: a nonce itt nem véd)."""
    belso = ("import sys, json, os\nf = sys._getframe()\naz = None\nwhile f is not None:\n"
             "    v = f.f_locals.get('feladat')\n    if isinstance(v, dict) and 'azonosito' in v:\n"
             "        az = v['azonosito']\n    f = f.f_back\n"
             f"b = (json.dumps(dict({sor!r}, azonosito=az)) + '\\n').encode()\n"
             "for i in range(2, 64):\n    try:\n        os.write(i, b)\n    except OSError:\n        pass")
    return {"muvelet": "kod", "kod": _kitores(f"__import__('builtins').exec({belso!r})")}


def elore_gyartott_sorok() -> dict:
    """Támadás: előre gyártott eredmény-sorok (azonosító nélkül) a protokoll-leíróra."""
    return leirora_ir((json.dumps(HAMIS) + "\n").encode() * 20)


def elszigetelesi_probak() -> list[dict]:
    """→ [{nev, kotet: [feladat, …], ellenoriz(eredmények) → hibaüzenet | None}]."""
    def utana_helyes(es: list[dict]) -> str | None:
        rossz = [i for i, e in enumerate(es[1:], 1)
                 if e["allapot"] != "ok" or e["ertek"] != (BECSULETES_ERTEK if i != 2 else "ok")]
        return f"a támadás utáni tétel hamis vagy hibás: {[es[i] for i in rossz]}"[:300] if rossz else None

    def gyartott(es: list[dict]) -> str | None:
        if es[0]["allapot"] == "ok" and es[0]["ertek"] == HAMIS["ertek"]:
            return "az előre gyártott sort a szülő elfogadta"
        return utana_helyes(es)

    return [
        {"nev": "a kod után a következő feladat érintetlen (a gyermek függvényének cseréje)",
         "kotet": [vegrehajt_csere(), BECSULETES, HIVAS, BECSULETES], "ellenoriz": utana_helyes},
        {"nev": "előre gyártott eredmény-sor a protokoll-leírón nem fogadható el",
         "kotet": [elore_gyartott_sorok(), BECSULETES, HIVAS], "ellenoriz": gyartott},
    ]


def elszigetelesi_probak_futtat(hk) -> list[dict]:
    """Az elszigetelési próbák (kötegenként egy `futtat` hívás) → [{nev, rendben, allapot, uzenet, csucs_mb}]."""
    ki = []
    for p in elszigetelesi_probak():
        es = hk.futtat(p["kotet"])
        hiba = p["ellenoriz"](es) if len(es) == len(p["kotet"]) else "hiányzó eredmény"
        ki.append({"nev": p["nev"], "rendben": hiba is None, "allapot": "/".join(e["allapot"] for e in es),
                   "uzenet": hiba or "", "csucs_mb": max((e.get("csucs_mb", 0.0) for e in es), default=0.0)})
    return ki


def probak(vault: Path, home: Path, tmp: Path, olvasando: Path) -> list[dict]:
    """→ [{nev, feladat, elvart (állapotok halmaza), [memoria_mb], [idokorlat_s], [kell: a létező út, különben a
    próba kimarad], [ellenoriz(eredmény) → hibaüzenet | None]}]."""
    irando = tmp / "homokozo-proba-iras.txt"
    nem_ok = {"tiltott", "hiba", "idotullepes", "memoria", "kimenet_tullepes", "homokozo_hiba"}
    return [
        {"nev": "rendes SymPy-számítás", "elvart": {"ok"},
         "feladat": {"muvelet": "kod", "kod": "import sympy as sp\nx = sp.Symbol('x')\n"
                                             "EREDMENY = sp.solveset(x**2 - 4, x)"}},
        {"nev": "fájl olvasása (a kódtár konfigja)", "elvart": {"tiltott"}, "kell": olvasando,
         "feladat": {"muvelet": "kod", "kod": _kitores(f"__import__('builtins').open({str(olvasando)!r}).read()")}},
        {"nev": "a vault listázása", "elvart": {"tiltott"}, "kell": vault,
         "feladat": {"muvelet": "kod", "kod": _kitores(f"__import__('os').listdir({str(vault)!r})")}},
        {"nev": "a home listázása", "elvart": {"tiltott"}, "kell": home,
         "feladat": {"muvelet": "kod", "kod": _kitores(f"__import__('os').listdir({str(home)!r})")}},
        {"nev": "fájl írása a {tmp} alá", "elvart": {"tiltott"},
         "feladat": {"muvelet": "kod", "kod": _kitores(f"__import__('builtins').open({str(irando)!r}, 'w')"
                                                       ".write('x')")},
         "ellenoriz": lambda e: f"a fájl létrejött: {irando}" if irando.exists() else None},
        {"nev": "hálózat (TCP)", "elvart": {"tiltott"},
         "feladat": {"muvelet": "kod", "kod": _kitores("__import__('socket').create_connection(('1.1.1.1', 80), 2)")}},
        {"nev": "hálózat (DNS)", "elvart": nem_ok,
         "feladat": {"muvelet": "kod", "kod": _kitores("__import__('socket').getaddrinfo('example.com', 80)")}},
        {"nev": "program indítása (exec)", "elvart": nem_ok,
         "feladat": {"muvelet": "kod", "kod": _kitores("__import__('os').execv('/bin/ls', ['ls'])")}},
        {"nev": "fork", "elvart": {"tiltott"},
         "feladat": {"muvelet": "kod", "kod": _kitores("__import__('os').fork()")}},
        {"nev": "jel más folyamatnak", "elvart": {"tiltott"},
         "feladat": {"muvelet": "kod", "kod": _kitores("__import__('os').kill(1, 0)")}},
        {"nev": "tiltott import (os)", "elvart": {"tiltott"},
         "feladat": {"muvelet": "kod", "kod": "import os\nEREDMENY = os.getcwd()"}},
        {"nev": "tiltott név (__import__)", "elvart": {"tiltott"},
         "feladat": {"muvelet": "kod", "kod": "EREDMENY = __import__('os')"}},
        {"nev": "tiltott attribútum (__class__)", "elvart": {"tiltott"},
         "feladat": {"muvelet": "kod", "kod": "EREDMENY = ().__class__.__bases__"}},
        {"nev": "végtelen ciklus (puha korlát)", "elvart": {"idotullepes"}, "idokorlat_s": 1.0,
         "feladat": {"muvelet": "kod", "kod": "while True:\n    pass"}},
        {"nev": "C-szintű végtelen számítás (kemény korlát, SIGKILL)", "elvart": {"idotullepes"}, "idokorlat_s": 1.0,
         "feladat": {"muvelet": "kod", "kod": "EREDMENY = sum(range(10**12))"}},
        {"nev": "kimenet-áradat a protokoll-csatornán", "elvart": {"kimenet_tullepes", "homokozo_hiba"},
         "feladat": {"muvelet": "kod", "kod": _kitores(
             "__import__('builtins').exec('import os\\nfor i in range(3, 40):\\n    try:\\n'"
             "'        os.write(i, b\"x\" * 400000)\\n    except OSError:\\n        pass')")}},
        {"nev": "a leállítás után a következő feladat új gyermekben fut", "elvart": {"ok"},
         "feladat": {"muvelet": "kod", "kod": "import sympy as sp\nEREDMENY = sp.Rational(1, 3) + 1"}},
        {"nev": "memória (800 MB, 300 MB-os korláttal)", "elvart": {"memoria"}, "memoria_mb": 300,
         "feladat": {"muvelet": "kod", "kod": "x = [0] * (10**8)\nEREDMENY = len(x)"}},
    ]


def futtat(hk, vault: Path, home: Path, tmp: Path, olvasando: Path) -> list[dict]:
    """A próbák lefuttatása → [{nev, rendben, allapot, uzenet, csucs_mb}]. A memória-próba külön hívás (más korlát)."""
    lista = probak(vault, home, tmp, olvasando)
    ki: list[dict] = [{"nev": p["nev"], "rendben": True, "kihagyva": True, "allapot": "kihagyva",
                       "uzenet": f"nincs ilyen út: {p['kell']}", "csucs_mb": 0.0}
                      for p in lista if "kell" in p and not Path(p["kell"]).exists()]
    lista = [p for p in lista if "kell" not in p or Path(p["kell"]).exists()]
    sorrend = {p["nev"]: i for i, p in enumerate(probak(vault, home, tmp, olvasando))}
    egyutt = [p for p in lista if "memoria_mb" not in p and "idokorlat_s" not in p]
    for p, e in zip(egyutt, hk.futtat([p["feladat"] for p in egyutt])):
        ki.append(_ertekel(p, e))
    for p in (p for p in lista if "memoria_mb" in p or "idokorlat_s" in p):
        e = hk.egy(p["feladat"], idokorlat_s=p.get("idokorlat_s"), memoria_mb=p.get("memoria_mb"))
        ki.append(_ertekel(p, e))
    return sorted(ki, key=lambda r: sorrend[r["nev"]]) + elszigetelesi_probak_futtat(hk)


def _ertekel(p: dict, e: dict) -> dict:
    hiba = None if e["allapot"] in p["elvart"] else f"várt: {'/'.join(sorted(p['elvart']))}"
    if hiba is None and p.get("ellenoriz"):
        hiba = p["ellenoriz"](e)
    return {"nev": p["nev"], "rendben": hiba is None, "allapot": e["allapot"], "uzenet": hiba or e["uzenet"],
            "csucs_mb": e.get("csucs_mb", 0.0)}
