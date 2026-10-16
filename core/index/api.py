"""A vault-index végpontjai az útvonal-regiszterben (C06, C10; C11a-tól regiszteres).

Minden `/api/vault/*` index-végpont a `limit` paramétert (1–10 000) a név előtt ellenőrzi, mint az if-láncos
szerveren: a hibás `limit` az ismeretlen végpontra is 400.
"""
from __future__ import annotations

import re

from ..utvonalak import Etagos, HttpError
from . import graf_meta


def utvonalak(r) -> None:
    def vegpont(nev, fn):
        def kezelo(k):
            limit = k.egesz("limit", None, 1, 10_000)
            return fn(k, limit)
        r.get(f"/api/vault/{nev}", kezelo)

    vegpont("index", lambda k, limit: k.app.index.allapot())
    vegpont("fa", lambda k, limit: k.app.index.fa())
    vegpont("jegyzet", lambda k, limit: k.app.index.jegyzet(k.q.get("ut")))
    vegpont("visszahivatkozasok", lambda k, limit: k.app.index.visszahivatkozasok(k.q.get("ut")))
    vegpont("emlitesek", lambda k, limit: k.app.index.emlitesek(k.q.get("ut"), limit))
    vegpont("kereses", lambda k, limit: k.app.index.kereses(k.q.get("q"), limit, k.egesz("kornyezet", 0, 0, 5)))
    # C33 (T070): a gráf és a graf-meta a szerkezeti generáció szerint gyorsítótárazva, ETag/304-gyel
    vegpont("graf", lambda k, limit: Etagos(*k.app.index.graf_valasz()))
    vegpont("graf-meta", lambda k, limit: Etagos(*graf_meta.graf_meta_valasz(k.app.index)))
    vegpont("graf-beallitasok", lambda k, limit: graf_meta.graf_beallitasok(k.app.index.root))
    vegpont("linkcel", lambda k, limit: k.app.index.link_cel(k.q.get("ut"), k.q.get("forras")))
    vegpont("beagyazas", lambda k, limit: k.app.index.beagyazas(k.q.get("forras"), k.q.get("cel"), k.q.get("alcel")))
    vegpont("aliasok", lambda k, limit: k.app.index.aliasok())

    def ismeretlen(k):
        k.egesz("limit", None, 1, 10_000)
        raise HttpError(404, "nincs ilyen végpont", kod="index.api.nincs_vegpont")
    r.get(re.compile(r"/api/vault/.*", re.S), ismeretlen)

    r.post("/api/vault/feloldas", lambda k: {"eredmenyek": k.app.index.feloldas(k.torzs().get("forras"),
                                                                                  k.torzs().get("celok"))})
