"""A C35a HTTP-végpontja: a ```plot blokk függvényeinek CAS-jellemzői (zérushely, szélsőérték, aszimptota).

`POST /api/grafikon/elemzes {fuggvenyek: ["x^2-4", …], ablak: [alsó, felső]}`. A számítás a CAS-homokozóban fut
(CLAUDE.md 46. döntés), **alfolyamatként**: a core nem importál `modulok`-ot (docs/C35-TERV.md, D-1), így a SymPy-gyermek
memóriája és összeomlása sem a core-é. Az alfolyamat a `modulok/grafikon/__main__.py elemez-json` (stdin/stdout JSON).

Védelmek: szigorú érvényesítés (a ```plot formátum karakter-fehérlistája, legfeljebb 8 függvény, véges ablak),
kifejezésenkénti gyorsítótár (LRU; az ablak 9 értékes jegyre kerekítve a kulcsban és a kérésben), **egyszerre egy
homokozó** (zár: a memória nem szorozódik; az azonos kérések egyszer futnak; a zárra várakozás korlátos:
`[grafikon] varakozas_s`, túllépve 503 „foglalt” — a kérés-szálak nem sorakoznak korlátlanul), az alfolyamat időkorlátja
(`[grafikon] elemzes_idokorlat_s`, túllépve a folyamatcsoport leáll), 503, ha a homokozó nem érhető el.
A vaultba nem ír, modellt nem tölt.

**Tiltólista** (C35b-mag; 5. döntés, `docs/PLOT-FORMATUM.md`): `GET /api/grafikon/tiltolista` a tiltott képletek listája (kulcs,
a megjelenítő út, idő, ok); `POST /api/grafikon/tiltolista/levesz {kulcs}` a vezérlőből való levétel. Az állapotfájl a
`core/plot_allapot.py`-é (`{state}/plot-tiltolista.json`); a végpont a vaultba nem ír.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import signal
import subprocess
import sys
import threading
import time
from collections import OrderedDict

from . import plot_allapot
from .utvonalak import HttpError

KERES_HIBA = 64                           # az `elemez-json` kilépési kódja hibás kérésre (a Python saját 2-es kódjával nem ütközik)
MAX_FUGGVENY = 8                          # a `modulok/grafikon` CLI-je is ennyit enged (a tesztek egyezését ellenőrzik)
MAX_KIF = 300                             # a `kozos.matek.elemez` plafonja
MAX_SZELESSEG = 1e7
MAX_ERTEK = 1e9
_KARAKTER = re.compile(r"^[0-9A-Za-z+\-*/^().,!_ ]+$")      # a ```plot formátum kifejezés-jelei (formatum.py)
ALAP = {"elemzes_idokorlat_s": 30.0, "gyorsitotar_db": 256, "varakozas_s": 20.0}
_ALLAPOT_SZAL = threading.Lock()


def _kerek(v: float) -> float:
    return float(f"{v:.9g}")


def _szam(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


class Elemzo:
    """A végpont állapota: gyorsítótár, egy-átfutás zár, az alfolyamat parancsa."""

    def __init__(self, cfg, futtato=None, **beallitas):
        self.cfg = cfg
        self.beall = dict(ALAP)
        self.beall.update(cfg.section("grafikon"))
        self.beall.update({k: v for k, v in beallitas.items() if v is not None})
        self.parancs = [sys.executable, "-B", str(cfg.path("modulok") / "grafikon" / "__main__.py"), "elemez-json"]
        self.futtato = futtato or self._alfolyamat
        self._lru: OrderedDict[str, dict] = OrderedDict()
        self._lru_zar = threading.Lock()
        self._futas = threading.Lock()

    # ------------------------------------------------------------------ érvényesítés

    @staticmethod
    def ervenyes(torzs) -> tuple[list[str], list[float]]:
        if not isinstance(torzs, dict):
            raise HttpError(400, "a törzs JSON-objektum legyen")
        f, ablak = torzs.get("fuggvenyek"), torzs.get("ablak")
        if not isinstance(f, list) or not 1 <= len(f) <= MAX_FUGGVENY:
            raise HttpError(400, f"a `fuggvenyek` 1–{MAX_FUGGVENY} szövegből álló lista legyen")
        ki = []
        for kif in f:
            if not isinstance(kif, str) or not kif.strip() or len(kif) > MAX_KIF or not _KARAKTER.match(kif):
                raise HttpError(400, "a kifejezés legfeljebb %d jel, és csak számot, betűt, `+-*/^().,!_` jelet és "
                                     "szóközt tartalmazhat" % MAX_KIF)
            ki.append(kif.strip())
        if not isinstance(ablak, list) or len(ablak) != 2 or not all(_szam(v) for v in ablak):
            raise HttpError(400, "az `ablak` két véges szám legyen: [alsó, felső]")
        lo, hi = float(ablak[0]), float(ablak[1])
        if not lo < hi:
            raise HttpError(400, "az ablak alsó határa kisebb legyen a felsőnél")
        if max(abs(lo), abs(hi)) > MAX_ERTEK or hi - lo > MAX_SZELESSEG:
            raise HttpError(400, "az ablak túl nagy")
        return ki, [_kerek(lo), _kerek(hi)]

    # ------------------------------------------------------------------ gyorsítótár

    @staticmethod
    def _kulcs(kif: str, ablak: list[float]) -> str:
        return hashlib.sha1(json.dumps([kif, ablak]).encode("utf-8")).hexdigest()

    def _olvas(self, kulcs: str) -> dict | None:
        with self._lru_zar:
            if kulcs in self._lru:
                self._lru.move_to_end(kulcs)
                return self._lru[kulcs]
        return None

    def _ir(self, kulcs: str, ertek: dict) -> None:
        with self._lru_zar:
            self._lru[kulcs] = ertek
            self._lru.move_to_end(kulcs)
            while len(self._lru) > int(self.beall["gyorsitotar_db"]):
                self._lru.popitem(last=False)

    # ------------------------------------------------------------------ a kérés

    def elemez(self, torzs) -> dict:
        ido = time.monotonic()
        fuggvenyek, ablak = self.ervenyes(torzs)
        kulcsok = [self._kulcs(k, ablak) for k in fuggvenyek]
        talalt = [self._olvas(k) for k in kulcsok]
        minden_gyorsitotarbol = all(t is not None for t in talalt)
        if not minden_gyorsitotarbol:
            if not self._futas.acquire(timeout=max(0.0, float(self.beall["varakozas_s"]))):
                raise HttpError(503, "az elemző foglalt (a homokozó másik kérést szolgál ki); próbáld újra")
            try:                                                 # egyszerre egy homokozó; az azonos kérések egyszer futnak
                talalt = [self._olvas(k) for k in kulcsok]
                hianyzo = list(dict.fromkeys(f for f, t in zip(fuggvenyek, talalt) if t is None))
                minden_gyorsitotarbol = not hianyzo              # a várakozás alatt más kitöltötte: ez a kérés nem futott
                if hianyzo:
                    ered = self.futtato(hianyzo, ablak)
                    if len(ered) != len(hianyzo):
                        raise HttpError(503, "az elemző hibás választ adott (a tételek száma eltér)")
                    if all(e.get("allapot") == "homokozo_hiba" for e in ered):
                        raise HttpError(503, "A CAS-homokozó nem érhető el: " + str(ered[0].get("uzenet", "")))
                    for f, e in zip(hianyzo, ered):
                        if e.get("allapot") != "homokozo_hiba":      # az átmeneti hiba nem gyorsítótárazott
                            self._ir(self._kulcs(f, ablak), e)
                    felold = dict(zip(hianyzo, ered))
                    talalt = [t if t is not None else felold[f] for f, t in zip(fuggvenyek, talalt)]
            finally:
                self._futas.release()
        return {"ok": True, "fuggvenyek": [{"kif": f, **t} for f, t in zip(fuggvenyek, talalt)],
                "ido_ms": int((time.monotonic() - ido) * 1000), "gyorsitotar": minden_gyorsitotarbol}

    # ------------------------------------------------------------------ az alfolyamat

    def _alfolyamat(self, fuggvenyek: list[str], ablak: list[float]) -> list[dict]:
        env = dict(os.environ)
        env["MOS_ROOT"] = str(self.cfg.root)
        env["PYTHONPATH"] = str(self.cfg.root) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        try:
            p = subprocess.Popen(self.parancs, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 env=env, cwd=str(self.cfg.root), text=True, start_new_session=True)
        except OSError as exc:
            raise HttpError(503, f"az elemző nem indult el: {exc}") from None
        idokorlat = float(self.beall["elemzes_idokorlat_s"])
        try:
            ki, hiba = p.communicate(json.dumps({"fuggvenyek": fuggvenyek, "ablak": ablak}), timeout=idokorlat)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                p.kill()
            p.communicate()
            raise HttpError(503, f"az elemzés időkorlátba ütközött ({idokorlat:g} s)") from None
        if p.returncode == KERES_HIBA:
            raise HttpError(500, "az elemző elutasította a kérést: " + ki.strip()[:300])
        if p.returncode != 0:
            raise HttpError(503, f"az elemző hibásan lépett ki ({p.returncode}): {hiba.strip()[-300:]}")
        try:
            v = json.loads(ki)["fuggvenyek"]
            if not isinstance(v, list) or not all(isinstance(e, dict) for e in v):
                raise ValueError("nem tételek listája")
        except (ValueError, KeyError, TypeError):
            raise HttpError(503, "az elemző értelmezhetetlen választ adott") from None
        return v


def _elemzo(app) -> Elemzo:
    """Az app egyetlen `Elemzo`-ja (lusta; az `App` osztályt nem kell módosítani)."""
    e = getattr(app, "_grafikon", None)
    if e is None:
        with _ALLAPOT_SZAL:
            e = getattr(app, "_grafikon", None)
            if e is None:
                e = app._grafikon = Elemzo(app.cfg)
    return e


def tiltolista(app) -> dict:
    try:
        return {"ok": True, "tiltott": plot_allapot.Tiltolista(app.cfg).lista()}
    except plot_allapot.AllapotHiba as e:
        raise HttpError(500, f"a tiltólista nem olvasható: {e}") from None


def tiltolista_levesz(app, torzs) -> dict:
    kulcs = torzs.get("kulcs") if isinstance(torzs, dict) else None
    if not isinstance(kulcs, str) or not plot_allapot.KULCS_MINTA.fullmatch(kulcs):
        raise HttpError(400, "a `kulcs` 16 hexa jegyű szöveg legyen")
    try:
        volt = plot_allapot.Tiltolista(app.cfg).levesz(kulcs)
    except plot_allapot.AllapotHiba as e:
        raise HttpError(500, f"a tiltólista nem olvasható: {e}") from None
    if not volt:
        raise HttpError(404, "nincs ilyen kulcs a tiltólistán")
    return {"ok": True, "kulcs": kulcs}


def utvonalak(r) -> None:
    r.post("/api/grafikon/elemzes", lambda k: _elemzo(k.app).elemez(k.torzs()))
    r.get("/api/grafikon/tiltolista", lambda k: tiltolista(k.app))
    r.post("/api/grafikon/tiltolista/levesz", lambda k: tiltolista_levesz(k.app, k.torzs()))
