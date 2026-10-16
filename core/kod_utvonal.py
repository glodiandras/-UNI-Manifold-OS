"""F10: the multi-language code workbench in the core — endpoints, the run handler, the WS events. The language profiles are
`core/kod_nyelvek.py`; the engine (`modulok/kod`) is a **child process** (`python -m modulok.kod … --json-sorok`), like the
C36a C++ engine: the core imports no `modulok`. The engine never writes the vault or the source; an AI suggestion is shown by
the UI and only the user can accept it (an editor transaction). The C36a `/api/cpp/*` endpoints stay as they are; this
service is reached through the C++ service (`app.cpp.kod`) so the server wiring is untouched.

| Endpoint | Returns |
|---|---|
| `GET /api/kod/nyelvek[?frissit=1]` | `{nyelvek: [profile + toolchain state]}` (discovery is cached for `NYELVEK_TTL_S`) |
| `GET /api/kod/feladat?ut=` | `{nyelv, jegyzet, forras, jegyzetek, tesztek, hiba}`: the note ↔ source pairing of any language |
| `POST /api/kod/ellenoriz {ut, jegyzet?, nyelv?, mod?}` | 202 `{futas, nyelv, forras, jegyzet, mod, tesztek_db}`; events on WS (`kod_futas`) |
| `GET /api/kod/futas/{id}` | the summary of a run (for late joiners) |
| `POST /api/kod/megszakit {futas}` | stop the run |
| `POST /api/kod/ai {mod, ut, jegyzet?, nyelv?, megerosit?}` | 202 `{ai, mod, nyelv, forras, jegyzet}`; events on WS (`kod_ai`) |
| `GET /api/kod/ai/{id}` | the summary of an AI request |
| `POST /api/kod/ai/megszakit {ai}` | stop the AI request |

Errors carry `kod` + `param` + an English message (`HttpError`). One check run and one AI request at a time.
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import cpp_teszt, kod_nyelvek as KN
from .utvonalak import HttpError, Valasz
from .vaultio import Invalid, NotFound, norm_path

REPO = Path(__file__).resolve().parent.parent
FUTAS_ID = re.compile(r"^kod-[0-9a-f]{12}$")
AI_ID = re.compile(r"^kodai-[0-9a-f]{12}$")
ELOZMENY_MAX = 8
LOG_VEGE = 12
MEGSZAKIT_VARAKOZAS_S = 5.0
NYELVEK_TTL_S = 300.0
NYELVEK_IDOKORLAT_S = 120


class Folyamat:
    """One engine child process (a check run or an AI request) and its collected events."""

    def __init__(self, fid: str, fajta: str, nyelv: str, forras: str, jegyzet: str | None, mod: str, tesztek_db: int = 0):
        self.id, self.fajta, self.nyelv, self.forras, self.jegyzet, self.mod = fid, fajta, nyelv, forras, jegyzet, mod
        self.tesztek_db = tesztek_db
        self.proc: subprocess.Popen | None = None
        self.allapot = "fut"                     # fut | kesz | hiba | megszakitva
        self.indult = time.time()
        self.fordit: dict | None = None
        self.tesztek: list[dict] = []
        self.kesz: dict | None = None
        self.hiba: dict | None = None
        self.eredmeny: dict | None = None
        self.modell: dict | None = None
        self.megszakit_kerve = False
        self.log: list[str] = []
        self.worker = None

    def adat(self) -> dict:
        d = {"id": self.id, "nyelv": self.nyelv, "forras": self.forras, "jegyzet": self.jegyzet, "mod": self.mod,
             "allapot": self.allapot, "kesz": self.kesz, "hiba": self.hiba, "indult": self.indult}
        if self.fajta == "futas":
            d.update(futas=self.id, tesztek_db=self.tesztek_db, fordit=self.fordit, tesztek=self.tesztek)
        else:
            d.update(ai=self.id, modell=self.modell, eredmeny=self.eredmeny)
        return d


class Szolgalat:
    def __init__(self, cfg, vault, index, publish, *, env, mentetlen=None):
        self.cfg, self.vault, self.index, self.publish = cfg, vault, index, publish
        self.env = env
        self.mentetlen = mentetlen or (lambda: set())
        self._zar = threading.Lock()
        self._aktiv: dict[str, Folyamat | None] = {"futas": None, "ai": None}
        self._folyamatok: dict[str, Folyamat] = {}
        self._leallt = False
        self._nyelvek: tuple[float, dict] | None = None

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def motor(*argv: str) -> list[str]:
        return [sys.executable, "-B", "-m", "modulok.kod", *argv]

    def _szoveg(self, rp: str) -> str:
        return self.vault.read(rp)["tartalom"]

    def _rp(self, ut, *kiterjesztesek: str) -> str:
        if not isinstance(ut, str) or not ut.strip():
            raise HttpError(400, "The path (`ut`) is missing.", kod="kod.hianyzik_ut")
        rp = self.vault.kanonikus(norm_path(ut))
        if kiterjesztesek and not rp.lower().endswith(kiterjesztesek):
            raise HttpError(400, f"Not a task note or a source file of a known language: {rp}", kod="kod.ismeretlen_kiterjesztes",
                            param={"ut": rp})
        return rp

    def _tesztek(self, rp: str) -> list[dict]:
        b = KN.beallitasok(self.cfg)
        return [t.szotar() for t in cpp_teszt.tesztek(self._szoveg(rp), float(b["teszt_idokorlat_max_s"]),
                                                      float(b["teszt_memoria_max_mb"]))]

    # ------------------------------------------------------------------ languages

    def nyelvek(self, frissit: bool = False) -> dict:
        with self._zar:
            gyors = self._nyelvek
        if gyors and not frissit and time.monotonic() - gyors[0] < NYELVEK_TTL_S:
            return gyors[1]
        try:
            ki = subprocess.run(self.motor("nyelvek", "--json"), capture_output=True, text=True, timeout=NYELVEK_IDOKORLAT_S,
                                cwd=str(REPO), env=self.env())
            d = json.loads(ki.stdout)
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            raise HttpError(503, f"The code engine does not answer: {exc}", kod="kod.motor_nem_valaszol",
                            param={"hiba": str(exc)}) from exc
        with self._zar:
            self._nyelvek = (time.monotonic(), d)
        return d

    # ------------------------------------------------------------------ note ↔ source

    def _beagyazott(self, jegyzet: str, szoveg: str) -> tuple[str | None, str | None]:
        celok = KN.beagyazott_forrasok(szoveg)
        if not celok:
            return None, "There is no embedded source file in the note (![[name.ext]])."
        try:
            feloldott = [l["cel"] for l in self.index.jegyzet(jegyzet)["linkek"]
                         if l["beagyazas"] and l["cel"] and KN.nyelv_ut(l["cel"]) is not None]
        except Exception:                                   # noqa: BLE001 — the index is building or does not see it yet
            feloldott = []
        if feloldott:
            return feloldott[0], None
        mappa = jegyzet.rpartition("/")[0]
        for jelolt in ((f"{mappa}/{celok[0]}" if mappa else celok[0]), celok[0]):
            try:
                rp = self.vault.kanonikus(norm_path(jelolt))
                if self.vault._abs(rp).is_file():
                    return rp, None
            except (Invalid, NotFound):
                continue
        return None, f"The embedded file is not found: {celok[0]}"

    def _jegyzetek(self, forras: str) -> list[str]:
        try:
            forrasok = self.index.visszahivatkozasok(forras)["forrasok"]
        except Exception:                                   # noqa: BLE001
            return []
        ki = []
        for f in forrasok:
            if f["ut"].lower().endswith(".md") and any(l["beagyazas"] for l in f["linkek"]):
                try:
                    if cpp_teszt.tesztek(self._szoveg(f["ut"])):
                        ki.append(f["ut"])
                except (Invalid, NotFound):
                    continue
        return sorted(ki)

    def feladat(self, ut) -> dict:
        rp = self._rp(ut, ".md", *KN.kiterjesztesek())
        jegyzet = forras = hiba = None
        jegyzetek: list[str] = []
        if rp.lower().endswith(".md"):
            jegyzet, jegyzetek = rp, [rp]
            forras, hiba = self._beagyazott(rp, self._szoveg(rp))
        else:
            # only existence: the engine reads the source itself (vaultio's editor allow-list is `.cpp`-only, C36a)
            if not self.vault._abs(rp).is_file():
                raise HttpError(404, f"No such file: {rp}", kod="kod.nincs_forras", param={"ut": rp})
            forras = rp
            jegyzetek = self._jegyzetek(rp)
            jegyzet = jegyzetek[0] if len(jegyzetek) == 1 else None
        p = KN.nyelv_ut(forras) if forras else None
        return {"nyelv": p.azonosito if p else None, "jegyzet": jegyzet, "forras": forras, "jegyzetek": jegyzetek, "hiba": hiba,
                "tesztek": self._tesztek(jegyzet) if jegyzet else []}

    def _cel(self, d: dict) -> tuple[KN.Profil, str, str | None]:
        """The language, the source and the note of a request (shared by the check and the AI)."""
        f = self.feladat(d.get("ut"))
        jegyzet = f["jegyzet"]
        if d.get("jegyzet") is not None:
            jegyzet = self._rp(d["jegyzet"], ".md")
        if f["forras"] is None:
            raise HttpError(400, f["hiba"] or "There is no source file.", kod="kod.nincs_beagyazott_forras")
        if jegyzet is None and len(f["jegyzetek"]) > 1:
            raise HttpError(409, "More than one task note embeds this source: choose one.", kod="kod.tobbertelmu",
                            jegyzetek=f["jegyzetek"])
        nyelv = d.get("nyelv") or f["nyelv"]
        p = KN.profil(nyelv) if isinstance(nyelv, str) else None
        if p is None:
            raise HttpError(400, f"Unknown language: {nyelv}", kod="kod.ismeretlen_nyelv", param={"nyelv": str(nyelv)})
        ment = self.mentetlen()
        mentetlen = [u for u in (f["forras"], jegyzet) if u and u in ment]
        if mentetlen:
            raise HttpError(409, "The file has unsaved changes: save it first.", kod="kod.mentetlen", utak=mentetlen)
        return p, f["forras"], jegyzet

    # ------------------------------------------------------------------ check run

    def ellenoriz(self, d: dict) -> Valasz:
        mod = d.get("mod") or "gyors"
        if mod not in KN.MODOK:
            raise HttpError(400, "The mode is `gyors` or `hibakereso`.", kod="kod.ismeretlen_mod", param={"mod": str(mod)})
        p, forras, jegyzet = self._cel(d)
        if mod != "gyors" and p.motor != "cpp":
            raise HttpError(400, f"The {mod} mode is only available for C and C++.", kod="kod.mod_nem_tamogatott",
                            param={"mod": mod, "nyelv": p.nev})
        tesztek = self._tesztek(jegyzet) if jegyzet else []
        argv = ["ellenoriz", str(self.vault._abs(forras)), "--nyelv", p.azonosito, "--mod", mod, "--json-sorok"]
        if jegyzet:
            argv += ["--jegyzet", str(self.vault._abs(jegyzet))]
        f = self._indit("futas", Folyamat(f"kod-{os.urandom(6).hex()}", "futas", p.azonosito, forras, jegyzet, mod,
                                          len(tesztek)), argv)
        return Valasz(202, {"futas": f.id, "nyelv": p.azonosito, "forras": forras, "jegyzet": jegyzet, "mod": mod,
                            "tesztek_db": len(tesztek)})

    # ------------------------------------------------------------------ AI

    def ai(self, d: dict, worker=None) -> Valasz:
        """`worker`: the app's model worker (its `biztosit()` gives `MOS_WORKER_URL`); None in tests (the engine's own URL)."""
        mod = d.get("mod")
        if mod not in KN.AI_MODOK:
            raise HttpError(400, f"The mode is one of: {', '.join(KN.AI_MODOK)}.", kod="kod.ismeretlen_ai_mod",
                            param={"modok": ", ".join(KN.AI_MODOK)})
        if mod == "megoldas" and d.get("megerosit") is not True:
            raise HttpError(400, "The full solution can only be requested with a separate confirmation.",
                            kod="kod.megerosites_kell")
        p, forras, jegyzet = self._cel(d)
        argv = ["ai", mod, str(self.vault._abs(forras)), "--nyelv", p.azonosito, "--json-sorok"]
        if jegyzet:
            argv += ["--jegyzet", str(self.vault._abs(jegyzet))]
        if mod == "megoldas":
            argv.append("--megerosit")
        f = Folyamat(f"kodai-{os.urandom(6).hex()}", "ai", p.azonosito, forras, jegyzet, mod)
        f.worker = worker
        self._indit("ai", f, argv)
        return Valasz(202, {"ai": f.id, "mod": mod, "nyelv": p.azonosito, "forras": forras, "jegyzet": jegyzet})

    # ------------------------------------------------------------------ the child process

    def _indit(self, fajta: str, f: Folyamat, argv: list[str]) -> Folyamat:
        with self._zar:
            if self._leallt:
                raise HttpError(503, "Manifold is shutting down.", kod="kod.core_leall")
            aktiv = self._aktiv[fajta]
            if aktiv is not None and aktiv.allapot == "fut":
                raise HttpError(409, "A run is already in progress.", kod="kod.foglalt", **{fajta: aktiv.id})
            self._aktiv[fajta] = f
            self._folyamatok[f.id] = f
            while len(self._folyamatok) > 2 * ELOZMENY_MAX:
                regi = next((k for k, v in self._folyamatok.items() if v.allapot != "fut"), None)
                if regi is None:
                    break
                del self._folyamatok[regi]
        threading.Thread(target=self._fut, args=(f, argv), daemon=True, name=f"kod-{f.id}").start()
        return f

    def _fut(self, f: Folyamat, argv: list[str]) -> None:
        try:
            env = self.env()
            if f.fajta == "ai":
                if f.worker is not None:
                    env["MOS_WORKER_URL"] = f.worker.biztosit()
                env["MOS_MODELL_MOD"] = "interaktiv"
            if f.megszakit_kerve:
                self._esemeny(f, {"szakasz": "megszakitva"})
                return
            f.proc = subprocess.Popen(self.motor(*argv), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                      cwd=str(REPO), env=env, start_new_session=True)
        except Exception as exc:                             # noqa: BLE001 — the worker or the engine does not start
            self._esemeny(f, {"szakasz": "hiba", "kod": "kod.nem_indul", "param": {"hiba": str(exc)},
                              "uzenet": f"The code engine does not start: {exc}"})
            self._vege(f)
            return
        try:
            for sor in f.proc.stdout:
                sor = sor.rstrip("\n")
                try:
                    d = json.loads(sor)
                    if isinstance(d, dict) and "szakasz" in d:
                        self._esemeny(f, d)
                        continue
                except ValueError:
                    pass
                f.log = (f.log + [sor])[-LOG_VEGE:]
        finally:
            try:
                f.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                f.proc.kill()
            try:
                f.proc.stdout.close()
            except OSError:
                pass
            if f.allapot == "fut":
                self._esemeny(f, {"szakasz": "hiba", "kod": "kod.motor_hiba", "param": {"log": " | ".join(f.log[-3:])},
                                  "uzenet": "The code engine stopped unexpectedly" + (": " + " | ".join(f.log[-3:]) if f.log else "")})
            self._vege(f)

    def _vege(self, f: Folyamat) -> None:
        with self._zar:
            if self._aktiv.get(f.fajta) is f:
                self._aktiv[f.fajta] = None

    def _esemeny(self, f: Folyamat, d: dict) -> None:
        sz = d.get("szakasz")
        if sz == "fordit_kesz":
            f.fordit = d.get("fordit")
        elif sz == "teszt":
            f.tesztek.append(d.get("teszt"))
        elif sz == "modell":
            f.modell = {k: d.get(k) for k in ("modell", "proba", "kalibracios_kulcs", "indok")}
        elif sz == "eredmeny":
            f.eredmeny = {k: v for k, v in d.items() if k not in ("szakasz", "nyelv")}
        elif sz == "kesz":
            f.kesz = {k: v for k, v in d.items() if k not in ("szakasz", "nyelv", "forras")}
            f.allapot = "kesz"
        elif sz == "hiba":
            f.hiba = {"kod": d.get("kod"), "param": d.get("param") or {}, "uzenet": d.get("uzenet")}
            f.allapot = "hiba"
        elif sz == "megszakitva":
            f.allapot = "megszakitva"
        tipus = "kod_futas" if f.fajta == "futas" else "kod_ai"
        self.publish({**d, "tipus": tipus, f.fajta: f.id, "nyelv": f.nyelv, "forras": f.forras, "jegyzet": f.jegyzet,
                      "mod": f.mod})

    # ------------------------------------------------------------------ summary, stop

    def _keres(self, fid, minta: re.Pattern) -> Folyamat:
        f = self._folyamatok.get(fid) if isinstance(fid, str) and minta.match(fid) else None
        if f is None:
            raise HttpError(404, f"No such run: {fid}", kod="kod.nincs_ilyen_futas", param={"id": str(fid)})
        return f

    def futas(self, fid: str) -> dict:
        return self._keres(fid, FUTAS_ID).adat()

    def ai_futas(self, aid: str) -> dict:
        return self._keres(aid, AI_ID).adat()

    def megszakit(self, d: dict, kulcs: str = "futas") -> dict:
        if not isinstance(d.get(kulcs), str) or not d.get(kulcs):
            raise HttpError(400, f"The `{kulcs}` field is missing.", kod="kod.hianyzik_azonosito", param={"mezo": kulcs})
        f = self._keres(d.get(kulcs), FUTAS_ID if kulcs == "futas" else AI_ID)
        if f.allapot != "fut":
            return {"megszakitva": False, "allapot": f.allapot}
        self._leallit(f)
        return {"megszakitva": True, "allapot": f.allapot}

    def _leallit(self, f: Folyamat) -> None:
        """SIGTERM to the engine (it stops its own sandboxed children); SIGKILL to the group after `MEGSZAKIT_VARAKOZAS_S`."""
        f.megszakit_kerve = True
        if f.proc is None:
            return
        try:
            f.proc.send_signal(signal.SIGTERM)
        except (ProcessLookupError, OSError):
            return

        def kenyszer():
            try:
                f.proc.wait(timeout=MEGSZAKIT_VARAKOZAS_S)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(f.proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
        threading.Thread(target=kenyszer, daemon=True).start()

    def leallit(self) -> None:
        with self._zar:
            self._leallt = True
            aktivak = [f for f in self._aktiv.values() if f is not None and f.allapot == "fut"]
        for f in aktivak:
            self._leallit(f)
        for f in aktivak:
            if f.proc is not None:
                try:
                    f.proc.wait(timeout=MEGSZAKIT_VARAKOZAS_S + 3)
                except subprocess.TimeoutExpired:
                    pass


def utvonalak(r) -> None:
    r.get("/api/kod/nyelvek", lambda k: k.app.cpp.kod.nyelvek(k.q.get("frissit") in ("1", "true")))
    r.get("/api/kod/feladat", lambda k: k.app.cpp.kod.feladat(k.q.get("ut")))
    r.post("/api/kod/ellenoriz", lambda k: k.app.cpp.kod.ellenoriz(k.torzs()))
    r.get(re.compile(r"/api/kod/futas/([^/]+)"), lambda k: k.app.cpp.kod.futas(k.m.group(1)))
    r.post("/api/kod/megszakit", lambda k: k.app.cpp.kod.megszakit(k.torzs(), "futas"))
    r.post("/api/kod/ai/megszakit", lambda k: k.app.cpp.kod.megszakit(k.torzs(), "ai"))
    r.post("/api/kod/ai", lambda k: k.app.cpp.kod.ai(k.torzs(), getattr(k.app, "worker", None)))
    r.get(re.compile(r"/api/kod/ai/(kodai-[^/]+)"), lambda k: k.app.cpp.kod.ai_futas(k.m.group(1)))
