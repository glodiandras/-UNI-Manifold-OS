"""A C29 HTTP-végpontjai: a naptár és az emlékeztetők állapota, a kézi szinkron, a naptár-kategóriák, a tanulásiblokk-
javaslatok jóváhagyása és az emlékeztető-ütközések láttamozása (docs/C29-TERV.md, 5. fejezet). A szolgáltatás az
`app.naptar` (`naptar_szolgalat.NaptarSzolgalat`). Az engedélyt nem ez a réteg kéri: azt a héj GUI-folyamata."""
from __future__ import annotations

import re

from . import naptar
from .utvonalak import HttpError


def _azon(k) -> int:
    return int(k.m.group(1))


def utvonalak(r) -> None:
    def allapot(k):
        sz = k.app.naptar
        if k.q.get("frissit") == "1":
            sz.engedely()
        return sz.allapot()

    def kategoria(k):
        t = k.torzs()
        azon, kat = t.get("azon"), t.get("kategoria")
        if not isinstance(azon, str) or not isinstance(kat, str):
            raise HttpError(400, "az `azon` és a `kategoria` szöveg legyen")
        try:
            ki = naptar.kategoria_allit(k.app.cfg, azon, kat)
        except ValueError as e:
            raise HttpError(400, str(e)) from None
        except KeyError as e:
            raise HttpError(404, str(e.args[0])) from None
        k.app.bus.publish({"tipus": "naptar_valtozas", "allapot": "kategoria", "uj": 0, "valtozott": 0, "torolt": 0,
                           "valtozasok": []})
        return ki

    def jovahagy(k):
        ki = k.app.naptar.javaslatok.jovahagy(_azon(k))
        k.app.naptar.naptar_frissit()
        return ki

    def utkozes_latva(k):
        azonok = k.torzs().get("azonok")
        if azonok is not None and not (isinstance(azonok, list) and all(isinstance(a, int) for a in azonok)):
            raise HttpError(400, "az `azonok` egész számok listája legyen")
        return {"ok": True, "db": k.app.naptar.emlekezteto.utkozes_latva(azonok)}

    r.get("/api/naptar/allapot", allapot)
    r.post("/api/naptar/szinkron", lambda k: k.app.naptar.kor("kezi"))
    r.post("/api/naptar/kategoria", kategoria)
    r.get("/api/naptar/javaslatok", lambda k: {"javaslatok": k.app.naptar.javaslatok.lista(k.q.get("mind") != "1"),
                                               "hiba": k.app.naptar.javaslatok.hiba})
    r.post(re.compile(r"/api/naptar/javaslat/(\d+)/jovahagy"), jovahagy)
    r.post(re.compile(r"/api/naptar/javaslat/(\d+)/elvet"), lambda k: k.app.naptar.javaslatok.elvet(_azon(k)))
    r.get("/api/emlekezteto/allapot", lambda k: k.app.naptar.emlekezteto.allapot())
    r.post("/api/emlekezteto/utkozes/latva", utkozes_latva)
