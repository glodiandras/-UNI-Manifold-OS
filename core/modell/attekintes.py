"""A vezérlő Modellek szakaszának adata (C19, T051): feladatonként a router-tábla, a kalibrált jel és a router döntése.

`GET /api/vezerlo/modellek` — csak olvas: a regiszter (`config/os.toml`), a kalibrációs tábla (`{router_db}`) és az
aranyhalmazok aktuális verziója (`halmaz.Verziok`); modellt nem tölt, workert nem indít (D8). A router döntését a két
keretre (munka, távol) száraz futással adja, ugyanazzal a `Router`-rel, amelyet a worker használ.
"""
from __future__ import annotations

from . import beallitas as B
from . import kalibracio
from .halmaz import Verziok
from .router import Router, RoutingHiba

_verziok: dict = {}


def _verzio_forras(cfg) -> Verziok:
    kulcs = str(cfg.path("modulok"))
    if kulcs not in _verziok:
        _verziok[kulcs] = Verziok(cfg.path("modulok"))
    return _verziok[kulcs]


def _keret_neve(b: B.Beallitas, m: B.Modell | None) -> str:
    if m is None or m.csucs_gb is None:
        return "?"
    return "munka" if m.csucs_gb <= b.keretek["munka"] else "tavol" if m.csucs_gb <= b.keretek["tavol"] else "—"


def attekintes(cfg) -> dict:
    b = B.betolt(cfg, {})                                  # a felület a regiszter kereteit lássa, nem egy CLI-felülírást
    verziok = _verzio_forras(cfg)
    aktualis = verziok.osszes()
    t = kalibracio.megnyit(cfg)
    try:
        sorok = t.tabla()
        router = Router(b, t, verziok=verziok)
        feladatok = list(dict.fromkeys([*(b.router.get("feladatok") or []), *(s["feladat"] for s in sorok)]))
        ki = []
        for f in feladatok:
            fs = []
            for s in (x for x in sorok if x["feladat"] == f and x["ervenyes"]):     # az érvénytelen (régi) sor nem routol
                try:
                    m = b.modell(s["modell"])
                except B.RegiszterHiba:
                    m = None
                fs.append({"modell": s["modell"], "pontszam": round(float(s["pontszam"]), 4), "datum": s["datum"],
                           "aranyhalmaz_verzio": s["aranyhalmaz_verzio"], "kalibralt": bool(s["kalibralt"]),
                           "ervenyes": bool(s["ervenyes"]), "aktualis": s["aranyhalmaz_verzio"] == aktualis.get(f),
                           "csucs_gb": m.csucs_gb if m else None, "keret": _keret_neve(b, m),
                           "snapshot": (s.get("snapshot") or "")[:12], "megjegyzes": s["megjegyzes"]})
            dontes = {}
            for keret in ("munka", "tavol"):
                try:
                    d = router.valaszt(f, b.keret_gb(keret))
                    dontes[keret] = {"modell": d.modell.nev if d.modell else None, "var_tavolra": d.var_tavolra,
                                     "indok": d.indok}
                except RoutingHiba as e:
                    dontes[keret] = {"modell": None, "var_tavolra": False, "indok": str(e)}
            ki.append({"feladat": f, "aktualis_verzio": aktualis.get(f), "sorok": fs, "dontes": dontes,
                       "router_feladat": f in (b.router.get("feladatok") or [])})
    finally:
        t.close()
    return {"keretek": {"munka": b.keretek["munka"], "tavol": b.keretek["tavol"]}, "feladatok": ki}
