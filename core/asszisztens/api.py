"""Az Asszisztens végpontjai (C30a; CHATKALAUZ C30): a gyorsítótárazott higiénia-összegzés, a linkeletlen említések, a heti
szokásminta, a döntések és a statisztika. A teljes riport soron belül **soha** nem számolódik (háttérszolgáltatás); egy
jegyzet tételei a meglévő `GET /api/higienia?ut=` végponton jönnek (egy indexelt lekérdezés)."""
from __future__ import annotations

from ..utvonalak import HttpError


def _torzs(k) -> dict:
    d = k.torzs()
    if not isinstance(d, dict):
        raise HttpError(400, "JSON-objektum kell", kod="asszisztens.api.objektum_kell")
    return d


def utvonalak(r) -> None:
    def a(k):
        return k.app.asszisztens

    r.get("/api/asszisztens/higienia", lambda k: a(k).szolgalat.osszegzes())
    r.post('/api/asszisztens/kiegeszites', lambda k: a(k).kiegeszites.ker(_torzs(k)))
    r.post('/api/asszisztens/kiegeszites/elvet',
           lambda k: (lambda d: a(k).kiegeszites.elvet(d.get('azon'), d.get('kifejezett') is True))(_torzs(k)))
    r.post('/api/asszisztens/kiegeszites/elfogad', lambda k: a(k).kiegeszites.elfogad(_torzs(k).get('azon')))
    r.get('/api/asszisztens/mintak', lambda k: a(k).kiegeszites.mintak())
    r.post('/api/asszisztens/mintak/tanit', lambda k: a(k).kiegeszites.tanit(_torzs(k)))
    r.post('/api/asszisztens/mintak/torles', lambda k: a(k).kiegeszites.torol())
    r.post("/api/asszisztens/higienia/latva", lambda k: a(k).szolgalat.latva())
    # J1/J3: a tanult minták, a javaslat-kártya és a „Mit tanult” lista ({state}/asszisztens.json; a vaultba nem ír)
    r.get("/api/asszisztens/tanult", lambda k: a(k).tanult())
    r.post("/api/asszisztens/tanult/torles", lambda k: (lambda d: a(k).tanult_torol(d.get("fajta"), d.get("kulcs")))(_torzs(k)))
    r.post("/api/asszisztens/tanul", lambda k: a(k).mintatar.tanul(_torzs(k)))
    r.post("/api/asszisztens/kartya", lambda k: a(k).mintatar.kartya(_torzs(k)))
    r.post("/api/asszisztens/kartya/dontes", lambda k: a(k).mintatar.dontes(_torzs(k)))

    def emlitesek(k):
        d = _torzs(k)
        if not isinstance(d.get("szoveg"), str):
            raise HttpError(400, "a szöveg kötelező", kod="asszisztens.api.szoveg_kotelezo")
        if not a(k).kapcsolo():
            return {"ut": d.get("ut"), "emlitesek": [], "kapcsolo": False}
        limit = d.get("limit")
        if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500):
            raise HttpError(400, "a limit 1 és 500 közötti egész szám", kod="asszisztens.api.limit_tartomany")
        return {**a(k).emlitesek.keres(d.get("ut"), d["szoveg"], limit), "kapcsolo": True}
    r.post("/api/asszisztens/emlitesek", emlitesek)

    r.get("/api/asszisztens/szokas", lambda k: {"javaslat": a(k).szokasok.aktualis()})
    r.post("/api/asszisztens/szokas/dontes", lambda k: a(k).szokasok.dontes(_torzs(k).get("azon"), _torzs(k).get("dontes")))
    def dontes(k):
        d = _torzs(k)
        ki = a(k).statisztika.rogzit(d.get("fajta"), d.get("dontes"))
        if d.get("fajta") == "emlites" and a(k).kapcsolo():         # J1: a linkjavaslat ugyanazzal a hangolással tanul
            a(k).hangolo.rogzit("link", "szoveg", d.get("dontes"))
        return ki
    r.post("/api/asszisztens/dontes", dontes)

    def statisztika(k):
        s = a(k).statisztika.osszesit()
        e = s["fajtak"]["emlites"]
        if s["kapcsolo"]["asszisztens"]:
            e["kuszob"] = a(k).link_kuszob(e["kuszob"])
            e["hasonlosag_kuszob"] = a(k).statisztika.hasonlosag_kuszob(e["kuszob"])
        return s
    r.get("/api/asszisztens/statisztika", statisztika)
    r.post("/api/asszisztens/statisztika/torles", lambda k: a(k).statisztika.torol())
