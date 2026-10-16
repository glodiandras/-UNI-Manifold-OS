"""A matek-motor HTTP-végpontja (C24b; docs/C24-TERV.md 5.1): a levezetés-ellenőrzés a szerkesztő margójához.

`POST /api/matek/levezetes {sorok: [{sor, szoveg}], vegeredmeny?, kikotesek?}` → a C24a ellenőrzőjének ítélete (`allapot`,
`elso_hiba`, `atmenetek`, `sorok`), minden sorszám mellett a jegyzet sorszámával (`jegyzet_sor`, `jegyzet_hova`…). A felület az élő
szerkesztő sorait küldi (a mentetlen szöveg is ellenőrizhető); a kérésben útvonal nincs. A végpont **tiszta, nem író**: a vaultba nem ír,
modellt nem tölt; a végeredményt csak `vegeredmeny: true`-ra mondja meg.

A számítás a CAS-homokozóban fut (46. döntés), **alfolyamaton** át (`modulok/matek/__main__.py levezetes-json`, stdin/stdout JSON): a core
nem importál SymPy-t és `modulok`-ot, a gyermek memóriája és összeomlása nem a core-é (a `grafikon_api` mintája). Egyszerre egy alfolyamat
(zár, korlátos várakozás: `[matek] varakozas_s`, túllépve 503), időkorlát (`[matek] levezetes_idokorlat_s`), 503, ha a homokozó nem érhető el.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading

from .utvonalak import HttpError

KERES_HIBA = 64                      # a `levezetes-json` kilépési kódja hibás kérésre (a modul CLI-jével egyezik; teszt őrzi)
MAX_SOR = 60
MAX_SOR_HOSSZ = 500
MAX_KIKOTES = 8
ALAP = {"levezetes_idokorlat_s": 90.0, "varakozas_s": 20.0}
_ALLAPOT_SZAL = threading.Lock()


def ervenyes(torzs) -> dict:
    if not isinstance(torzs, dict):
        raise HttpError(400, "a törzs JSON-objektum legyen", kod="matek.torzs_objektum")
    sorok = torzs.get("sorok")
    if not isinstance(sorok, list) or not 1 <= len(sorok) <= MAX_SOR:
        raise HttpError(400, f"a `sorok` 1–{MAX_SOR} elemű lista legyen", kod="matek.sorok_lista", param={"max": MAX_SOR})
    ki = []
    for s in sorok:
        if (not isinstance(s, dict) or isinstance(s.get("sor"), bool) or not isinstance(s.get("sor"), int)
                or s["sor"] < 1 or not isinstance(s.get("szoveg"), str) or len(s["szoveg"]) > MAX_SOR_HOSSZ):
            raise HttpError(400, f"minden sor {{sor: pozitív egész, szoveg: legfeljebb {MAX_SOR_HOSSZ} jel}} legyen", kod="matek.sor_alak", param={"max": MAX_SOR_HOSSZ})
        ki.append({"sor": s["sor"], "szoveg": s["szoveg"]})
    kik = torzs.get("kikotesek", [])
    if not isinstance(kik, list) or len(kik) > MAX_KIKOTES or not all(isinstance(k, str) and len(k) <= 200 for k in kik):
        raise HttpError(400, f"a `kikotesek` legfeljebb {MAX_KIKOTES} rövid szöveg legyen", kod="matek.kikotesek", param={"max": MAX_KIKOTES})
    veg = torzs.get("vegeredmeny", False)
    if not isinstance(veg, bool):
        raise HttpError(400, "a `vegeredmeny` igaz vagy hamis legyen", kod="matek.vegeredmeny_logikai")
    return {"sorok": ki, "vegeredmeny": veg, "kikotesek": kik}


class Ellenorzo:
    """A végpont állapota: az egy-átfutás zár és az alfolyamat parancsa (a tesztek `futtato`-t adnak)."""

    def __init__(self, cfg, futtato=None):
        self.cfg = cfg
        self.beall = {**ALAP, **cfg.section("matek")}
        self.parancs = [sys.executable, "-B", str(cfg.path("modulok") / "matek" / "__main__.py"), "levezetes-json"]
        self.futtato = futtato or self._alfolyamat
        self._futas = threading.Lock()

    def levezetes(self, torzs) -> dict:
        keres = ervenyes(torzs)
        if not self._futas.acquire(timeout=max(0.0, float(self.beall["varakozas_s"]))):
            raise HttpError(503, "az ellenőrző foglalt (a homokozó másik kérést szolgál ki); próbáld újra", kod="matek.ellenorzo_foglalt")
        try:
            r = self.futtato(keres)
        finally:
            self._futas.release()
        if not isinstance(r, dict) or "allapot" not in r:
            raise HttpError(503, "az ellenőrző értelmezhetetlen választ adott", kod="matek.ellenorzo_ertelmezhetetlen")
        if r.get("allapot") == "nem_ellenorizheto" and "homokozó: homokozo_hiba" in str(r.get("ok", "")):
            raise HttpError(503, "A CAS-homokozó nem érhető el: " + str(r.get("ok")), kod="matek.cas_nem_elerheto", param={"ok": str(r.get("ok"))})
        ki = {"ok": True, **{k: v for k, v in r.items() if k != "ok"}}
        if r.get("ok"):
            ki["indok"] = r["ok"]                    # az ellenőrző `ok` szövege (miért nem ellenőrizhető) — az `ok` itt a válasz jele
        return ki

    def _alfolyamat(self, keres: dict) -> dict:
        env = dict(os.environ)
        env["MOS_ROOT"] = str(self.cfg.root)
        env["PYTHONPATH"] = str(self.cfg.root) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        try:
            p = subprocess.Popen(self.parancs, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 env=env, cwd=str(self.cfg.root), text=True, start_new_session=True)
        except OSError as exc:
            raise HttpError(503, f"az ellenőrző nem indult el: {exc}", kod="matek.ellenorzo_nem_indult", param={"hiba": str(exc)}) from None
        idokorlat = float(self.beall["levezetes_idokorlat_s"])
        try:
            ki, hiba = p.communicate(json.dumps(keres, ensure_ascii=False), timeout=idokorlat)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                p.kill()
            p.communicate()
            raise HttpError(503, f"az ellenőrzés időkorlátba ütközött ({idokorlat:g} s)", kod="matek.idokorlat", param={"mp": f"{idokorlat:g}"}) from None
        if p.returncode == KERES_HIBA:
            raise HttpError(500, "az ellenőrző elutasította a kérést: " + ki.strip()[:300], kod="matek.ellenorzo_elutasitotta", param={"hiba": ki.strip()[:300]})
        if p.returncode != 0:
            raise HttpError(503, f"az ellenőrző hibásan lépett ki ({p.returncode}): {hiba.strip()[-300:]}", kod="matek.ellenorzo_kilepes", param={"kilepes": p.returncode, "hiba": hiba.strip()[-300:]})
        try:
            return json.loads(ki)
        except ValueError:
            raise HttpError(503, "az ellenőrző értelmezhetetlen választ adott", kod="matek.ellenorzo_ertelmezhetetlen") from None


def _ellenorzo(app) -> Ellenorzo:
    """Az app egyetlen `Ellenorzo`-ja (lusta; az `App` osztályt nem kell módosítani)."""
    e = getattr(app, "_matek", None)
    if e is None:
        with _ALLAPOT_SZAL:
            e = getattr(app, "_matek", None)
            if e is None:
                e = app._matek = Ellenorzo(app.cfg)
    return e


def utvonalak(r) -> None:
    r.post("/api/matek/levezetes", lambda k: _ellenorzo(k.app).levezetes(k.torzs()))
