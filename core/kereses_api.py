"""A hibrid keresés és a „Kérdezz a vaulttól” végpontjai (C25b; `docs/C25B-TERV.md`). Csak olvasnak.

| Végpont | Válasz |
|---|---|
| `GET /api/kereses/hibrid?q=&limit=&mod=hibrid\\|lexikai` | a `HibridKereso.keres` válasza (`mod`, `ok`, `osszes`, `legalabb`, `talalatok`) |
| `GET /api/kereses/vektor-allapot` | a vektortár állapota (`van`, `motor`, `jegyzetek`, `darabok`, `modell`), és mi van kötve |
| `POST /api/kereses/kerdezz {kerdes, folyam?}` | a `kerdezz.valaszol` válasza; `folyam: true` → NDJSON-események (`kerdezz.folyam`) |
| `GET /api/kereses/hasonlo?ut=&n=` | C25c: a hasonló jegyzetek a vektortárból, modell nélkül (`hibrid.hasonlo.hasonlok`) |
| `POST /api/kereses/hasonlosag {ut, celok}` | C25c: a jegyzet hasonlósága a megadott jegyzetekhez (a C30b linkjavaslatának szűrője) |

A végpontok az API-titok mögött állnak (a regiszter minden `/api/*` útja, 54(a)); a lépés-token a „Kérdezz”-t nem hívhatja
(default-deny, `lepes_kapu`), a folyamos változatot sem (ugyanaz az út).

**Kötés (C25b modellfele).** A valódi core-ban (`app.worker`) a modellek a workeren át kötődnek, lustán, az első kéréskor
(`core/kereses_modell.py`): a vault-válasz modellje a router `szoveg` feladata (élesben csak kalibrált modell fut, D9: ha a
routernek nincs kalibrált modellje, a worker 409-cel elutasít, a válasz 503). A beágyazó és a reranker a `[kereses.hibrid]`
`vektor` és `rerank` kulcsa szerint kötődik (M12: csak ha a C18 keresési halmazán mérhetően javít; a mérés: NAPLO C25b).
**A hibrid keresés nem vár modellre** (`Szolgalat.hibrid`): ha a beágyazó vagy a reranker épp nincs betöltve (a munka-keretben
egymás és a nyelvi modell mellé sem fér), a válasz azonnal a lexikai (`ok: "modell_betoltes_alatt"`), és ugyanez a kérés a
háttérben, a modellek betöltésével lefut; a felület megismétli, és a kész hibrid választ kapja (58(b)). A tesztek
és a mag a `kotes` horgot használják (álhívókkal). A vektortárat (`{index}/vektor.sqlite`) ez a modul nem írja.
"""
from __future__ import annotations

import json
import threading
import weakref
from pathlib import Path

from .utvonalak import KESZ, HttpError, biztonsagi_fejlecek
from .vaultio import Invalid

_szolgalatok: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()
_zar = threading.Lock()


def tar_ut(cfg) -> Path:
    return Path(cfg.path("index")) / "vektor.sqlite"


def _hibrid_kapcsolok(cfg) -> tuple[bool, bool]:
    s = dict(cfg.section("kereses", "hibrid"))
    return bool(s.get("vektor", False)), bool(s.get("rerank", False))


class Szolgalat:
    """Az app-onkénti állapot: a vektortár (lusta, csak olvasva) és a kötött hívhatók."""

    def __init__(self, app):
        self.app = app
        self.beagyazo = None
        self.reranker = None
        self.modell = None              # ModellHivas: (prompt, max_tokens) → szöveg | tokenek
        self.kalibralt = False
        self.megszakit = None
        self.kezi_kotes = False         # a `kotes` horog (tesztek, mag): a worker-kötés nem írja felül
        self._tar = None
        self._hatter: threading.Thread | None = None
        self._hatter_zar = threading.Lock()
        self._hatter_kesz: dict = {}           # (q, limit) → a háttérben elkészült hibrid válasz (legfeljebb 8)

    def tar(self):
        from .index.hibrid.vektortar import NincsTar, Vektortar
        if self._tar is None:
            try:
                self._tar = Vektortar(tar_ut(self.app.cfg), csak_olvas=True)
            except NincsTar:
                return None
        return self._tar

    # ------------------------------------------------------------------ worker-kötés

    def _worker(self):
        return getattr(self.app, "worker", None)

    def worker_kot(self) -> None:
        """A valódi core-ban: a modellek a workeren át (lustán; a worker indul, modellt még nem tölt be)."""
        w = self._worker()
        if self.kezi_kotes or w is None:
            return
        from .kereses_modell import WorkerBeagyazo, WorkerModell, WorkerReranker
        if self.modell is None and self._kalibralt_modell("szoveg"):
            self.modell, self.kalibralt = WorkerModell(w.biztosit), True        # D9: a worker csak kalibráltat futtat
        vektor, rerank = _hibrid_kapcsolok(self.app.cfg)
        if vektor and self.beagyazo is None:
            nev = self._kalibralt_modell("beagyazas")
            if nev:
                self.beagyazo = WorkerBeagyazo(w.biztosit, nev, dim=self._tar_dim(nev))
        if rerank and self.reranker is None:
            nev = self._kalibralt_modell("rerank")
            if nev:
                self.reranker = WorkerReranker(w.biztosit)
                self.reranker.nev = nev

    def _kalibralt_modell(self, feladat: str) -> str | None:
        """A router-tábla legjobb kalibrált modellje a feladatra (workert nem indít; nélküle nincs kötés: a „Kérdezz” 503, a
        keresés lexikai). A worker a válaszban a ténylegesen futott modellt adja: a beágyazónál ez ellenőrzött."""
        from .modell import kalibracio
        from .modell.halmaz import Verziok
        t = kalibracio.megnyit(self.app.cfg)
        try:
            sorok = t.kalibralt_sorrend(feladat, Verziok(self.app.cfg.path("modulok")))      # a router szűrője
        finally:
            t.close()
        return sorok[0]["modell"] if sorok else None

    def _tar_dim(self, nev: str) -> int:
        t = self.tar()
        k = t.modell_kulcs() if t is not None else None
        return int(k.get("dim") or 0) if k and k.get("nev") == nev else 0

    def betoltve(self) -> set[str]:
        """A workerben épp bent lévő modellek (a futó worker `/health`-éből; nem indít workert)."""
        from .modell import kliens
        w = self._worker()
        u = (w.url if w is not None else None) or kliens.fut_url(self.app.cfg)
        if not u:
            return set()
        try:
            h = kliens.health(u, timeout=2)
        except kliens.KliensHiba:
            return set()
        return {x for x in [h.get("modell"), *(h.get("mellette") or [])] if x}

    def kereso(self, beagyazo=True, reranker=True):
        from .index.hibrid import kereso
        self.worker_kot()
        return kereso.HibridKereso(self.app.index.olvaso, self.tar(), self.beagyazo if beagyazo else None,
                                   self.reranker if reranker else None, kereso.beallitas(self.app.cfg),
                                   getattr(self.app.index, "regex_idokorlat", 2.0))

    def hianyzo_modell(self) -> bool:
        """Kell-e még betölteni a hibrid kereséshez a beágyazót vagy a rerankert (a futó worker szerint)."""
        if self.kezi_kotes or (self.beagyazo is None and self.reranker is None):
            return False
        if self.kereso().miert_lexikai() is not None:      # nincs (egyező) vektortár: a hibrid úgyis lexikai, modell nem kell
            return False
        bent = self.betoltve()
        return any(m is not None and getattr(m, "nev", None) not in bent for m in (self.beagyazo, self.reranker))

    def hibrid(self, q, limit: int, mod: str) -> dict:
        """A ⌘⇧F hibrid kérése (58(b), C25b): ha a kereső-modellek bent vannak, a hibrid válasz azonnal; ha nincsenek, a
        válasz **azonnal a lexikai** (`ok: "modell_betoltes_alatt"`), és ugyanez a kérés a háttérben a modellek
        betöltésével lefut (egyszerre egy); a felület ugyanazt a kérést megismétli, és a kész hibrid választ kapja. Egy
        háttérfutás az egész láncot viszi (beágyazás, majd rerank): a munka-keretben a két modell nem fér együtt (63.,
        C25b), így a külön „melegítés” egymást ürítené ki."""
        self.worker_kot()
        if mod != "hibrid" or not isinstance(q, str) or not self.hianyzo_modell():
            return self.kereso().keres(q, limit, mod)
        kulcs = (q, limit)
        with self._hatter_zar:
            kesz = self._hatter_kesz.pop(kulcs, None)
            if kesz is not None:
                return kesz
            fut = self._hatter is not None and self._hatter.is_alive()
            if not fut:
                self._hatter = threading.Thread(target=self._hatter_fut, args=(kulcs,), name="kereses-hibrid", daemon=True)
                self._hatter.start()
        v = self.kereso(beagyazo=False, reranker=False).keres(q, limit, "hibrid")
        v["ok"] = "modell_betoltes_alatt"
        return v

    def _hatter_fut(self, kulcs) -> None:
        q, limit = kulcs
        try:
            v = self.kereso().keres(q, limit, "hibrid")
        except Exception as e:  # noqa: BLE001 — a háttérfutás hibája a következő kérésben lexikai válasz okaként látszik
            v = {**self.kereso(beagyazo=False, reranker=False).keres(q, limit, "lexikai"), "ok": f"modell_hiba: {e}"}
        with self._hatter_zar:
            self._hatter_kesz[kulcs] = v
            while len(self._hatter_kesz) > 8:
                self._hatter_kesz.pop(next(iter(self._hatter_kesz)))


def szolgalat(app) -> Szolgalat:
    with _zar:
        sz = _szolgalatok.get(app)
        if sz is None:
            sz = _szolgalatok[app] = Szolgalat(app)
        return sz


def kotes(app, *, beagyazo=None, reranker=None, modell=None, kalibralt: bool = False, megszakit=None) -> Szolgalat:
    """A kötés horga (tesztek, mag): a beágyazó, a reranker és a vault-válasz modellje (D9: `kalibralt`)."""
    sz = szolgalat(app)
    sz.beagyazo, sz.reranker, sz.modell, sz.kalibralt, sz.megszakit = beagyazo, reranker, modell, bool(kalibralt), megszakit
    sz.kezi_kotes = True
    return sz


def vektor_allapot(sz: Szolgalat) -> dict:
    t = sz.tar()
    alap = t.allapot() if t is not None else {"van": False}
    vektor, rerank = _hibrid_kapcsolok(sz.app.cfg)
    return {**alap, "kapcsolok": {"vektor": vektor, "rerank": rerank},
            "kotve": {"beagyazo": getattr(sz.beagyazo, "nev", None), "reranker": sz.reranker is not None,
                      "modell": sz.modell is not None, "kalibralt": sz.kalibralt}}


def _kerdes(k) -> tuple[str, bool]:
    t = k.torzs()
    kerdes = t.get("kerdes")
    if not isinstance(kerdes, str) or not kerdes.strip():
        raise Invalid("hiányzó kérdés")
    if len(kerdes) > 2000:
        raise Invalid("a kérdés legfeljebb 2000 karakter")
    return kerdes, bool(t.get("folyam"))


def _folyam_kuld(h, esemenyek) -> None:
    """NDJSON-válasz: soronként egy esemény. A kliens bontásakor (az írás hibája) a generátor bezárul: a modell
    tokenfolyama is, így a worker a következő tokennél megáll (`kerdezz.folyam`)."""
    h.send_response(200)
    h.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
    h.send_header("Cache-Control", "no-store")
    biztonsagi_fejlecek(h)
    h.send_header("Connection", "close")
    h.end_headers()
    try:
        for e in esemenyek:
            h.wfile.write(json.dumps(e, ensure_ascii=False).encode("utf-8") + b"\n")
            h.wfile.flush()
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass
    finally:
        esemenyek.close()


def _hiba_esemenyekkel(esemenyek):
    """A modell hibája (nincs kalibrált modell, a worker nem érhető el) a folyamban `hiba` esemény, nem félbeszakadt válasz."""
    from .modell.kliens import KliensHiba
    try:
        yield from esemenyek
    except KliensHiba as e:
        yield {"tipus": "hiba", "kod": 503 if e.kod in (409, 503) else e.kod, "hiba": str(e)}
    finally:
        esemenyek.close()


def utvonalak(r) -> None:
    def hibrid(k):
        mod = k.q.get("mod") or "hibrid"
        limit = k.egesz("limit", 20, 1, 1000)
        v = szolgalat(k.app).hibrid(k.q.get("q"), limit, mod)
        return k.app.index.media_kiegeszit(v)           # C25c: a felirat-találat médiája (a másodpercre nyitáshoz)

    def kerdezz(k):
        from .index.hibrid import kerdezz as K
        from .modell.kliens import KliensHiba
        kerdes, folyam = _kerdes(k)
        sz = szolgalat(k.app)
        cfg = k.app.cfg
        kw = dict(b=K.beallitas(cfg), prof=K.profil(cfg), kalibralt=sz.kalibralt, megszakit=sz.megszakit)
        kr = sz.kereso()
        if folyam:
            _folyam_kuld(k.h, _hiba_esemenyekkel(K.folyam(kerdes, kr, sz.modell, **kw)))
            return KESZ
        try:
            v = K.valaszol(kerdes, kr, sz.modell, **kw)
        except KliensHiba as e:
            raise HttpError(503, f"A „Kérdezz a vaulttól” modellje nem érhető el: {e}") from None
        if v["allapot"] == "nincs_modell":
            raise HttpError(503, "A „Kérdezz a vaulttól” modellje nincs kötve (a router-táblában nincs kalibrált `szoveg` modell).", forrasok=v["forrasok"])
        return v

    def hasonlo(k):
        from .index.hibrid import hasonlo as H
        sz = szolgalat(k.app)
        from .automatika import kisero_elotag
        return H.hasonlok(k.app.index.olvaso, sz.tar(), k.q.get("ut"), k.egesz("n", 10, 1, 50), kisero_elotag(k.app.cfg))

    def hasonlosag(k):
        from .index.hibrid import hasonlo as H
        t = k.torzs()
        sz = szolgalat(k.app)
        return H.hasonlosag(k.app.index.olvaso, sz.tar(), t.get("ut"), t.get("celok"))

    r.get("/api/kereses/hibrid", hibrid)
    r.get("/api/kereses/hasonlo", hasonlo)
    r.post("/api/kereses/hasonlosag", hasonlosag)
    r.get("/api/kereses/vektor-allapot", lambda k: vektor_allapot(szolgalat(k.app)))
    r.post("/api/kereses/kerdezz", kerdezz)
