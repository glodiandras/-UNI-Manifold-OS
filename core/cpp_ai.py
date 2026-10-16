"""A C++ AI-réteg a core-ban (C36b; `docs/C36-TERV.md` „C36b”): végpontok, a futás-kezelő, a `cpp_ai` WS-esemény, a `cpp_tipp`
tracker-esemény.

**Csak kattintásra**: a felhasználó kérése indítja, automatikus futás nincs. A motor (`modulok/cpp`, `ai` alparancs) gyermekfolyamat,
mint a ⌘R-é (a core nem importál `modulok`-ot): ő hívja a workert (`MOS_WORKER_URL`, a router `kod` feladata: élesben csak kalibrált
modell, D9), és a modell kódját csak a program-homokozóban fordítja és futtatja (53(b)). A core és a motor **semmit nem ír** a vaultba
és a `.cpp`-be (53(d)): a javaslatot (teszt-blokk, javított program) a felület mutatja, és a felhasználó egy szerkesztő-tranzakcióval
fogadhatja el.

| Végpont | Mit ad |
|---|---|
| `GET /api/cpp/ai/allapot` | `{kalibralt, modell, indok, futas}`: van-e a `kod` feladatra kalibrált modell (a router-táblából; workert nem indít) |
| `POST /api/cpp/ai {mod, ut, jegyzet?, megerosit?}` | 202 `{ai, mod, cpp, jegyzet}`; az eredmény WS-en (`cpp_ai`) jön |
| `GET /api/cpp/ai/{id}` | a futás összesítője (késői csatlakozóknak) |
| `POST /api/cpp/ai/megszakit {ai}` | a futás leállítása |
| `POST /api/cpp/ai/tipp {ai, szint}` | a tipp-lépcső egy szintjének felfedése: `cpp_tipp` tracker-esemény (szintenként egyszer) |

A `megoldas` mód (a tipp-lépcső 4. foka, a teljes megoldás) csak `megerosit: true`-val indul, és `cpp_tipp` `szint: 4` eseményt ír.
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import threading
import time

from pathlib import Path

from .utvonalak import HttpError, Valasz
from .vaultio import Invalid, NotFound, norm_path
from .hibakod import angol_uzenet, kodol

REPO = Path(__file__).resolve().parent.parent
MODOK = ("hiba", "tipp", "megoldas", "teszt", "stressz")
FELADAT = "kod"
AI_ID = re.compile(r"^ai-[0-9a-f]{12}$")
ELOZMENY_MAX = 8
MEGSZAKIT_VARAKOZAS_S = 5.0
LOG_VEGE = 12
TIPP_SZINTEK = (1, 2, 3)
MEGOLDAS_SZINT = 4


class AIFutas:
    def __init__(self, aid: str, mod: str, cpp: str, jegyzet: str | None):
        self.id, self.mod, self.cpp, self.jegyzet = aid, mod, cpp, jegyzet
        self.allapot = "fut"                  # fut | kesz | hiba | megszakitva
        self.indult = time.time()
        self.proc: subprocess.Popen | None = None
        self.eredmeny: dict | None = None
        self.kesz: dict | None = None
        self.hiba: dict | None = None
        self.modell: str | None = None
        self.felfedett: set[int] = set()
        self.megszakit_kerve = False
        self.log: list[str] = []

    def adat(self) -> dict:
        return {"ai": self.id, "mod": self.mod, "cpp": self.cpp, "jegyzet": self.jegyzet, "allapot": self.allapot,
                "modell": self.modell, "eredmeny": self.eredmeny, "kesz": self.kesz, "hiba": self.hiba, "indult": self.indult}


class Szolgalat:
    """`feladat(ut)`: a `cpp_utvonal.Szolgalat.feladat` (a jegyzet ↔ `.cpp` párosítás egyetlen helye); `motor(*argv)` és `env()`: a
    motor parancssora és környezete (ugyanaz, mint a ⌘R-é); `worker()`: a core worker-folyamata (`biztosit() → url`)."""

    def __init__(self, cfg, vault, publish, tracker, *, feladat, motor, env, mentetlen=None, eszkoztar_hianya=None):
        self.cfg, self.vault, self.publish, self.tracker = cfg, vault, publish, tracker
        self.feladat_fn, self.motor, self.env = feladat, motor, env
        self.mentetlen = mentetlen or (lambda: set())
        self.eszkoztar_hianya = eszkoztar_hianya or (lambda: None)
        self._zar = threading.Lock()
        self._aktiv: AIFutas | None = None
        self._futasok: dict[str, AIFutas] = {}
        self._leallt = False

    # ------------------------------------------------------------------ állapot

    def kalibralt_modell(self) -> str | None:
        """A router-tábla legjobb kalibrált `kod` modellje (workert nem indít). A végső döntés a worker routeréé (az aranyhalmaz
        aktuális verziója is számít): ha az mást mond, a futás `nincs_kalibralt` hibával áll meg."""
        from .modell import kalibracio
        from .modell.halmaz import Verziok
        try:
            t = kalibracio.megnyit(self.cfg)
        except Exception:                                    # noqa: BLE001 — hiányzó/sérült tábla: nincs kalibrált modell
            return None
        try:
            sorok = t.kalibralt_sorrend(FELADAT, Verziok(self.cfg.path("modulok")))   # 63(a): csak az arany aktuális verzióján kalibrált sor
        finally:
            t.close()
        return sorok[0]["modell"] if sorok else None

    def allapot(self) -> dict:
        nev = self.kalibralt_modell()
        with self._zar:
            futas = self._aktiv.id if self._aktiv and self._aktiv.allapot == "fut" else None
        return {"kalibralt": nev is not None, "modell": nev, "futas": futas, "modok": list(MODOK),
                "indok": "" if nev else "A C++ AI-hoz még nincs kalibrált modell (a `kod` feladat kalibrálása után kapcsol be)."}

    # ------------------------------------------------------------------ indítás

    def indit(self, d: dict, worker) -> Valasz:
        mod = d.get("mod")
        if mod not in MODOK:
            raise kodol(Invalid(f"a `mod` ezek egyike: {', '.join(MODOK)}"), "cpp_ai.mod_ezek_egyike_join", {"join": ', '.join(MODOK)})
        if mod == "megoldas" and d.get("megerosit") is not True:
            raise HttpError(400, "a teljes megoldás csak külön megerősítéssel kérhető", kod="megerosites_kell")
        f = self.feladat_fn(d.get("ut"))
        jegyzet = f["jegyzet"]
        if d.get("jegyzet") is not None:
            jegyzet = self.vault.kanonikus(norm_path(str(d["jegyzet"])))
            if not jegyzet.lower().endswith(".md"):
                raise kodol(Invalid("a `jegyzet` .md fájl legyen"), "cpp_ai.jegyzet_md_fajl_legyen")
        if f["cpp"] is None:
            raise HttpError(400, f["hiba"] or "nincs .cpp megoldás", kod="nincs_cpp")
        if jegyzet is None and len(f["jegyzetek"]) > 1:
            raise HttpError(409, "több feladat-jegyzet ágyazza be ezt a .cpp-t: válassz", kod="tobbertelmu",
                            jegyzetek=f["jegyzetek"])
        ment = self.mentetlen()
        mentetlen = [u for u in (f["cpp"], jegyzet) if u and u in ment]
        if mentetlen:
            raise HttpError(409, "mentetlen változás van a fájlban: mentsd előbb", kod="mentetlen", utak=mentetlen)
        hianyzik = self.eszkoztar_hianya()
        if hianyzik:
            raise HttpError(503, hianyzik, kod="nincs_eszkoztar")
        if self.kalibralt_modell() is None:
            raise HttpError(503, self.allapot()["indok"], kod="nincs_kalibralt")
        argv = ["ai", mod, str(self.vault._abs(f["cpp"])), "--json-sorok"]
        if jegyzet:
            argv += ["--jegyzet", str(self.vault._abs(jegyzet))]
        if mod == "megoldas":
            argv.append("--megerosit")
        with self._zar:
            if self._leallt:
                raise HttpError(503, "a core leáll", kod="cpp_ai.core_leall")
            if self._aktiv is not None and self._aktiv.allapot == "fut":
                raise HttpError(409, "már fut egy AI-kérés", kod="foglalt", ai=self._aktiv.id)
            futas = AIFutas(f"ai-{os.urandom(6).hex()}", mod, f["cpp"], jegyzet)
            self._aktiv = futas
            self._futasok[futas.id] = futas
            while len(self._futasok) > ELOZMENY_MAX:
                regi = next((k for k, v in self._futasok.items() if v.allapot != "fut"), None)
                if regi is None:
                    break
                del self._futasok[regi]
        if mod == "megoldas":
            self._tracker(futas, MEGOLDAS_SZINT)
        threading.Thread(target=self._fut, args=(futas, argv, worker), daemon=True, name=f"cpp-{futas.id}").start()
        return Valasz(202, {"ai": futas.id, "mod": mod, "cpp": f["cpp"], "jegyzet": jegyzet})

    def _fut(self, futas: AIFutas, argv: list[str], worker) -> None:
        """A háttérszál: a worker biztosítása (a kérés nem vár rá), a motor indítása, a JSON-sorok olvasása."""
        try:
            env = self.env()
            if worker is not None:
                env["MOS_WORKER_URL"] = worker.biztosit()
            env["MOS_MODELL_MOD"] = "interaktiv"
            if futas.megszakit_kerve:
                self._esemeny(futas, {"szakasz": "megszakitva"})
                return
            futas.proc = subprocess.Popen(self.motor(*argv), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                          cwd=str(REPO), env=env, start_new_session=True)
        except Exception as exc:                             # noqa: BLE001 — a worker vagy a motor nem indul
            self._esemeny(futas, {"szakasz": "hiba", "kod": "nem_indul", "uzenet": f"az AI-kérés nem indul: {exc}"})
            self._vege(futas)
            return
        try:
            for sor in futas.proc.stdout:
                sor = sor.rstrip("\n")
                try:
                    d = json.loads(sor)
                    if isinstance(d, dict) and "szakasz" in d:
                        self._esemeny(futas, d)
                        continue
                except ValueError:
                    pass
                futas.log = (futas.log + [sor])[-LOG_VEGE:]
        finally:
            try:
                futas.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                futas.proc.kill()
            try:
                futas.proc.stdout.close()
            except OSError:
                pass
            if futas.allapot == "fut":
                uzenet = "az AI-motor váratlanul leállt" + (": " + " | ".join(futas.log[-3:]) if futas.log else "")
                self._esemeny(futas, {"szakasz": "hiba", "kod": "motor_hiba", "uzenet": uzenet})
            self._vege(futas)

    def _vege(self, futas: AIFutas) -> None:
        with self._zar:
            if self._aktiv is futas:
                self._aktiv = None

    def _esemeny(self, futas: AIFutas, d: dict) -> None:
        sz = d.get("szakasz")
        if sz == "modell":
            futas.modell = d.get("modell")
        elif sz == "eredmeny":
            futas.eredmeny = {k: v for k, v in d.items() if k != "szakasz"}
        elif sz == "kesz":
            futas.kesz = {k: v for k, v in d.items() if k != "szakasz"}
            futas.allapot = "kesz"
        elif sz == "hiba":
            regi = str(d.get("uzenet") or "")
            kod = d.get("kod")
            param = d.get("param") if isinstance(d.get("param"), dict) else {}
            uzenet = angol_uzenet(kod, param, "The AI request failed. Open its log for details.")
            if regi and regi != uzenet:
                futas.log = (futas.log + [regi])[-LOG_VEGE:]
            d = {**d, "uzenet": uzenet}
            futas.hiba = {"kod": d.get("kod"), "uzenet": d.get("uzenet")}
            futas.allapot = "hiba"
        elif sz == "megszakitva":
            futas.allapot = "megszakitva"
        self.publish({**d, "tipus": "cpp_ai", "ai": futas.id, "mod": futas.mod, "cpp": futas.cpp, "jegyzet": futas.jegyzet})

    # ------------------------------------------------------------------ tracker

    def _tracker(self, futas: AIFutas, szint: int) -> None:
        """`cpp_tipp`: a tipp-lépcső szintje (1–3 a felfedés, 4 a teljes megoldás kérése); csak a jegyzet útja és a szám, kód és
        szöveg nélkül; a Tracker-kapcsoló alatt (a `fogad` dönt). Hibatűrő: soha nem akaszt."""
        if not futas.jegyzet or szint in futas.felfedett:
            return
        futas.felfedett.add(szint)
        try:
            self.tracker.fogad({"esemenyek": [{"tipus": "cpp_tipp", "ut": futas.jegyzet, "adat": {"szint": int(szint)}}]})
        except Exception:                                    # noqa: BLE001
            pass

    def tipp(self, d: dict) -> dict:
        futas = self._keres(d.get("ai"))
        szint = d.get("szint")
        if futas.mod != "tipp":
            raise kodol(Invalid("ez nem tipp-kérés"), "cpp_ai.ez_tipp_keres")
        if not isinstance(szint, int) or isinstance(szint, bool) or szint not in TIPP_SZINTEK:
            raise kodol(Invalid("a `szint` 1, 2 vagy 3"), "cpp_ai.szint_1_2_3")
        if futas.eredmeny is None:
            raise HttpError(409, "a tipp még nem érkezett meg", kod="nincs_eredmeny")
        uj = szint not in futas.felfedett
        self._tracker(futas, szint)
        return {"ai": futas.id, "szint": szint, "uj": uj}

    # ------------------------------------------------------------------ lekérdezés, megszakítás, leállás

    def _keres(self, aid) -> AIFutas:
        if not isinstance(aid, str) or not aid:
            raise kodol(Invalid("hiányzik az `ai`"), "cpp_ai.hianyzik_ai")
        f = self._futasok.get(aid) if AI_ID.match(aid) else None
        if f is None:
            raise kodol(NotFound(f"nincs ilyen AI-kérés: {aid}"), "cpp_ai.nincs_ilyen_ai_keres_aid", {"aid": aid})
        return f

    def futas(self, aid: str) -> dict:
        return self._keres(aid).adat()

    def megszakit(self, d: dict) -> dict:
        f = self._keres(d.get("ai"))
        if f.allapot != "fut":
            return {"megszakitva": False, "allapot": f.allapot}
        self._leallit(f)
        return {"megszakitva": True, "allapot": f.allapot}

    def _leallit(self, f: AIFutas) -> None:
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
            aktiv = self._aktiv
        if aktiv is not None and aktiv.allapot == "fut":
            self._leallit(aktiv)
            if aktiv.proc is not None:
                try:
                    aktiv.proc.wait(timeout=MEGSZAKIT_VARAKOZAS_S + 3)
                except subprocess.TimeoutExpired:
                    pass


def utvonalak(r) -> None:
    r.get("/api/cpp/ai/allapot", lambda k: k.app.cpp.ai.allapot())
    r.post("/api/cpp/ai", lambda k: k.app.cpp.ai.indit(k.torzs(), getattr(k.app, "worker", None)))
    r.post("/api/cpp/ai/megszakit", lambda k: k.app.cpp.ai.megszakit(k.torzs()))
    r.post("/api/cpp/ai/tipp", lambda k: k.app.cpp.ai.tipp(k.torzs()))
    r.get(re.compile(r"/api/cpp/ai/(ai-[^/]+)"), lambda k: k.app.cpp.ai.futas(k.m.group(1)))


