"""A CAS-homokozó (C24a; a C24b és a C35 is ezt hívja): SymPy-számítás külön, elzárt folyamatban.

    hk = Homokozo(cfg)                     # cfg nélkül: a `core.config.load()`, ha elérhető, különben alapértékek
    hk.elerheto()        → (bool, ok)      # sandbox-exec megvan, a gyermek elindul (önpróba, gyorsítótárazva)
    hk.futtat([{"muvelet": "kod", "kod": "...", "valtozo": "EREDMENY"},
               {"muvelet": "hivas", "nev": "matek.levezetes", "args": {...}}],
              idokorlat_s=None, memoria_mb=None) → [eredmény, …]

Minden eredmény `{"allapot", "ertek", "uzenet", "mp", "csucs_mb"}`; az állapot az `ALLAPOTOK` egyike.

A határ (a T059 és a C24-prompt 6. pontja szerint):
- **fájl és hálózat**: `sandbox-exec` profil (`profil.sb`): olvasni csak a Pythont, a venvet, a rendszer-könyvtárakat
  és a homokozó saját kódját lehet; írni csak a `/dev/null`-ba; hálózat, exec, fork, jel nincs;
- **idő**: a gyermekben feladatonként puha korlát (`setitimer`), a szülőben kemény (SIGKILL a folyamatcsoportra);
- **memória**: a szülő mintavételezi a gyermek `phys_footprint`-jét, és a korlát fölött SIGKILL a folyamatcsoportra
  (`setrlimit` nincs: macOS-en ValueError);
- **kimenet**: feladatonként legfeljebb `kimenet_max_kb`; fölötte ölés.
Ölés után a hátralévő feladatok új gyermekben futnak.

Elszigetelés (Javító 1, Audit 3 A3-02): a `sandbox-exec` a folyamaton belüli állapotot nem védi, és a nem megbízható kód
(a `sympify` `eval`-ján át) a gyermek bármely függvényét átírhatja vagy a protokoll-leíróra írhat. Ezért:
- egy **`kod` feladat után a gyermek mindig leáll**; a következő feladat új gyermekben fut, így a `hivas` (megbízható
  művelet) soha nem fut olyan gyermekben, amelyben `kod` futott (a `hivas`-ok egymás között egy gyermeken osztoznak);
- minden feladat **egyszeri azonosítót** (`azonosito`, 128 bit) kap, a gyermek visszaadja; a szülő csak az épp várt
  azonosítójú sort fogadja el, és a sort **szigorúan** értelmezi (`_ertelmez`: szótár, csak ismert kulcsok és típusok,
  a gyermek által jelenthető állapotok); minden eltérés `homokozo_hiba`, nem kivétel a hívóban (A3-15);
- a memóriaőr **zárva hibázik**: ha az élő gyermek memóriája nem olvasható, a gyermek leáll, a feladat `homokozo_hiba`
  (A3-16).
A `kod` feladat a saját eredményét így is meghamisíthatja (a saját azonosítóját olvashatja) — ez a kódja eredménye,
ugyanúgy, mintha az `EREDMENY`-t állítaná; más feladatét nem. Ha a `sandbox-exec` hiányzik vagy a profil nem indul, a
homokozó **zárva hibázik** (`homokozo_hiba`): csupasz, elzáratlan futtatás nincs.
"""
from __future__ import annotations

import json
import os
import secrets
import select
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ITT = Path(__file__).resolve().parent
MODULOK = ITT.parent
PROFIL = ITT / "profil.sb"
GYEREK = ITT / "gyerek.py"

ALLAPOTOK = ("ok", "hiba", "tiltott", "idotullepes", "memoria", "kimenet_tullepes", "homokozo_hiba")
ALAP = {"idokorlat_s": 10.0, "lepes_idokorlat_s": 3.0, "memoria_mb": 768, "mintavetel_ms": 20,
        "kimenet_max_kb": 256, "indulas_s": 20.0, "max_ujrainditas": 50}
_TARTALEK_S = 1.5                     # a kemény korlát ennyivel a puha után: a gyermek előbb maga jelezzen
_STDERR_MAX = 4096
# a gyermek ezeket jelentheti; a `kimenet_tullepes` és a `homokozo_hiba` csak a szülő ítélete
GYEREK_ALLAPOTOK = ("ok", "hiba", "tiltott", "idotullepes", "memoria")
# a gyermek eredmény-sorának kulcsai és típusai (az `ertek` bármely JSON-érték; a `kimenet` csak a `kod`-é)
_KOTELEZO = ("azonosito", "allapot")
_TIPUSOK = {"azonosito": str, "allapot": str, "ertek": object, "uzenet": str, "mp": (int, float), "kimenet": str}


def _ertelmez(adat, azonosito: str) -> tuple[str, dict]:
    """A gyermek egy eredmény-sora → ("ok", {allapot, ertek, uzenet, mp[, kimenet]}) vagy ("homokozo_hiba", {uzenet}).

    Szigorú: a sor szótár, csak ismert kulcsokkal és típusokkal, az épp várt `azonosito`-val, és az állapot a gyermek
    által jelenthetők egyike. Kivételt nem dob."""
    if not isinstance(adat, dict):
        return "homokozo_hiba", {"uzenet": f"a homokozó válasza nem szótár ({type(adat).__name__})"}
    ismeretlen = sorted(set(adat) - set(_TIPUSOK))
    if ismeretlen:
        return "homokozo_hiba", {"uzenet": f"a homokozó válaszában ismeretlen kulcs: {', '.join(ismeretlen)[:200]}"}
    hiany = [k for k in _KOTELEZO if k not in adat]
    if hiany:
        return "homokozo_hiba", {"uzenet": f"a homokozó válaszából hiányzik: {', '.join(hiany)}"}
    for k, v in adat.items():
        if not isinstance(v, _TIPUSOK[k]) or (k == "mp" and (isinstance(v, bool) or not 0 <= v < 1e6)):
            return "homokozo_hiba", {"uzenet": f"a homokozó válaszában hibás típusú érték: {k}"}
    if not secrets.compare_digest(adat["azonosito"], azonosito):
        return "homokozo_hiba", {"uzenet": "a homokozó válasza nem ehhez a feladathoz tartozik (azonosító-eltérés)"}
    if adat["allapot"] not in GYEREK_ALLAPOTOK:
        return "homokozo_hiba", {"uzenet": f"ismeretlen állapot: {adat['allapot'][:50]}"}
    e = {"allapot": adat["allapot"], "ertek": adat.get("ertek"), "uzenet": adat.get("uzenet", ""),
         "mp": float(adat.get("mp", 0.0))}
    if "kimenet" in adat:
        e["kimenet"] = adat["kimenet"]
    return "ok", e


def _cfg_betolt():
    try:
        from core import config
        return config.load()
    except Exception:                                           # a homokozó core nélkül is futhat (pl. eval-pontozó)
        return None


class _Gyerek:
    """Egy elindított gyermekfolyamat: sorok olvasása határidővel, memória- és kimenet-őrrel."""

    def __init__(self, proc: subprocess.Popen, beall: dict, memoria_mb: float):
        self.proc = proc
        self.beall = beall
        self.memoria_mb = memoria_mb
        self.puffer = b""
        self.hiba_kimenet = b""
        self.el = True
        self.szennyezett = False            # futott-e benne `kod` (nem megbízható kód): utána csak leállítható
        self.hiba_ok = ""                   # a szülő `homokozo_hiba`-ítéletének oka (pl. olvashatatlan memória)

    def leallit(self) -> None:
        if self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        for f in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            try:
                f and f.close()
            except OSError:
                pass
        self.el = False

    def sor(self, hatarido: float, kimenet_max: int) -> tuple[str, object, float]:
        """Egy protokoll-sor → (állapot, a sor JSON-értéke, csúcs MB). Állapot: ok | idotullepes | memoria |
        kimenet_tullepes | homokozo_hiba (a gyermek kilépett, értelmezhetetlen sort írt, vagy élő gyermekre a memória
        nem olvasható). A sor alakját a hívó ellenőrzi (`_ertelmez`)."""
        from homokozo import memoria
        csucs = 0.0
        ki, hib = self.proc.stdout.fileno(), self.proc.stderr.fileno()
        nyitott = {ki, hib}
        mintavetel = max(float(self.beall["mintavetel_ms"]), 5.0) / 1000
        olvasott = 0
        while True:
            if b"\n" in self.puffer:
                sor, self.puffer = self.puffer.split(b"\n", 1)
                try:
                    return "ok", json.loads(sor.decode("utf-8")), csucs
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self.leallit()
                    return "homokozo_hiba", None, csucs
            mb = memoria.mb(self.proc.pid)
            if mb is None and self.proc.poll() is None:
                mb = memoria.mb(self.proc.pid)                 # egy újrapróba (a kilépés pillanata)
                if mb is None and self.proc.poll() is None:  # élő gyermek, őr nélkül nem futhat tovább (A3-16)
                    self.leallit()
                    self.hiba_ok = "a homokozó memóriája nem olvasható (a memóriaőr zárva hibázik)"
                    return "homokozo_hiba", None, csucs
            if mb is not None:
                csucs = max(csucs, mb)
                if mb > self.memoria_mb:
                    self.leallit()
                    return "memoria", None, csucs
            if time.monotonic() > hatarido:
                self.leallit()
                return "idotullepes", None, csucs
            if not nyitott:
                self.leallit()
                return "homokozo_hiba", None, csucs
            keszek, _, _ = select.select(list(nyitott), [], [], mintavetel)
            for fd in keszek:
                darab = os.read(fd, 65536)
                if not darab:
                    nyitott.discard(fd)
                elif fd == hib:
                    self.hiba_kimenet = (self.hiba_kimenet + darab)[-_STDERR_MAX:]
                else:
                    self.puffer += darab
                    olvasott += len(darab)
                    if olvasott > kimenet_max:
                        self.leallit()
                        return "kimenet_tullepes", None, csucs


class Homokozo:
    def __init__(self, cfg=None, *, sandbox_exec: str | None = None, **beallitas):
        cfg = cfg if cfg is not None else _cfg_betolt()
        self.beall = dict(ALAP)
        if cfg is not None:
            self.beall.update(cfg.section("homokozo"))
        self.beall.update({k: v for k, v in beallitas.items() if v is not None})
        if sandbox_exec is None and cfg is not None and "sandbox_exec" in getattr(cfg, "utak", {}):
            sandbox_exec = str(cfg.path("sandbox_exec"))
        self.sandbox_exec = sandbox_exec if sandbox_exec is not None else shutil.which("sandbox-exec")
        self._elerheto: tuple[bool, str] | None = None

    # ------------------------------------------------------------------ indítás

    def parancs(self) -> list[str]:
        exe = os.path.abspath(sys.executable)
        d = {"PY_EXE": exe, "PY_EXE_VALOS": os.path.realpath(exe),
             "PY_PREFIX": os.path.realpath(sys.prefix), "PY_BASE": os.path.realpath(sys.base_prefix),
             "KOD_MODULOK": str(MODULOK), "KOD_EVAL": str(MODULOK / "eval"), "KOD_HOMOKOZO": str(ITT),
             "KOD_MATEK": str(MODULOK / "matek"), "KOD_KOZOS": str(MODULOK / "eval" / "kozos"),
             "KOD_GRAFIKON": str(MODULOK / "grafikon")}
        p = [str(self.sandbox_exec), "-f", str(PROFIL)]
        for k, v in d.items():
            p += ["-D", f"{k}={os.path.realpath(v) if k != 'PY_EXE' else v}"]
        return p + [exe, "-I", "-B", "-X", "utf8", str(GYEREK)]

    def _indit(self, memoria_mb: float) -> tuple[_Gyerek | None, str]:
        if not self.sandbox_exec or not os.access(self.sandbox_exec, os.X_OK):
            return None, f"nincs sandbox-exec ({self.sandbox_exec or 'nem található'}): elzáratlan futtatás nincs"
        try:
            proc = subprocess.Popen(self.parancs(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, cwd="/", env={}, start_new_session=True)
        except OSError as exc:
            return None, f"a homokozó nem indul: {exc}"
        gy = _Gyerek(proc, self.beall, memoria_mb)
        allapot, adat, _ = gy.sor(time.monotonic() + float(self.beall["indulas_s"]), 4096)
        if allapot != "ok" or not isinstance(adat, dict) or adat.get("kesz") is not True or gy.puffer:
            hiba = ([gy.hiba_ok] if gy.hiba_ok else []) or \
                gy.hiba_kimenet.decode("utf-8", "replace").strip().splitlines()[-1:] or [allapot]
            gy.leallit()
            return None, f"a homokozó nem indult ({allapot}): {hiba[0][:300]}"
        return gy, ""

    # ------------------------------------------------------------------ futtatás

    def futtat(self, feladatok: list[dict], idokorlat_s: float | None = None,
               memoria_mb: float | None = None) -> list[dict]:
        """A feladatok sorban; a `kod` után a gyermek leáll (a következő új gyermekben fut), a `hivas`-ok egy gyermeken
        osztozhatnak. A `max_ujrainditas` a rendellenes leállításokat számolja (korlát, hiba), a `kod` utánit nem."""
        ido = float(idokorlat_s if idokorlat_s is not None else self.beall["idokorlat_s"])
        mem = float(memoria_mb if memoria_mb is not None else self.beall["memoria_mb"])
        kimenet_max = int(self.beall["kimenet_max_kb"]) * 1024
        eredmenyek: list[dict] = []
        gy: _Gyerek | None = None
        rendellenes = 0
        try:
            for i, f in enumerate(feladatok):
                if gy is not None and gy.szennyezett:                # nem fordulhat elő (a `kod` után leállítjuk)
                    gy.leallit()
                    gy = None
                if gy is None:
                    if rendellenes > int(self.beall["max_ujrainditas"]):
                        eredmenyek += [_hiba("túl sok újraindítás") for _ in feladatok[i:]]
                        break
                    gy, ok = self._indit(mem)
                    if gy is None:
                        eredmenyek += [_hiba(ok) for _ in feladatok[i:]]
                        break
                azonosito = secrets.token_hex(16)
                kuldott = dict(f, azonosito=azonosito, idokorlat_s=min(float(f.get("idokorlat_s") or ido), ido))
                indul = time.monotonic()
                gy.szennyezett = gy.szennyezett or f.get("muvelet") != "hivas"     # minden nem-`hivas` nem megbízható
                try:
                    gy.proc.stdin.write((json.dumps(kuldott, ensure_ascii=False) + "\n").encode("utf-8"))
                    gy.proc.stdin.flush()
                except (BrokenPipeError, OSError, TypeError, ValueError) as exc:
                    gy.leallit()
                    eredmenyek.append(_hiba("a homokozó kilépett" if isinstance(exc, OSError)
                                            else f"a feladat nem küldhető: {exc}"[:300]))
                    gy = None
                    rendellenes += 1
                    continue
                allapot, adat, csucs = gy.sor(indul + kuldott["idokorlat_s"] + _TARTALEK_S, kimenet_max)
                if allapot == "ok":
                    allapot, e = _ertelmez(adat, azonosito)
                    if allapot == "ok" and gy.puffer:                # a válasz után további sor: protokollsértés
                        allapot, e = "homokozo_hiba", {"uzenet": "a homokozó a válasza után további adatot írt"}
                    if allapot != "ok":
                        gy.leallit()
                        e = {"allapot": "homokozo_hiba", "ertek": None, "uzenet": e["uzenet"],
                             "mp": round(time.monotonic() - indul, 4)}
                else:
                    e = {"allapot": allapot, "ertek": None, "uzenet": gy.hiba_ok or _UZENET[allapot],
                         "mp": round(time.monotonic() - indul, 4)}
                e["csucs_mb"] = round(csucs, 1)
                eredmenyek.append(e)
                if not gy.el:
                    rendellenes += 1
                    gy = None
                elif gy.szennyezett:                                  # A3-02: `kod` után nincs több feladat ebben
                    gy.leallit()
                    gy = None
        finally:
            if gy is not None:
                gy.leallit()
        return eredmenyek

    def egy(self, feladat: dict, **kw) -> dict:
        return self.futtat([feladat], **kw)[0]

    def elerheto(self) -> tuple[bool, str]:
        """Önpróba: a profil alatt elindul-e a gyermek, és válaszol-e (gyorsítótárazva)."""
        if self._elerheto is None:
            e = self.egy({"muvelet": "hivas", "nev": "homokozo.alvas", "args": {"mp": 0}})
            self._elerheto = (e["allapot"] == "ok", e["uzenet"] or "rendben")
        return self._elerheto


_UZENET = {"idotullepes": "a feladat túllépte a kemény időkorlátot (a folyamatcsoport leállítva)",
           "memoria": "a feladat túllépte a memóriakorlátot (a folyamatcsoport leállítva)",
           "kimenet_tullepes": "a feladat túl sok kimenetet írt (a folyamatcsoport leállítva)",
           "homokozo_hiba": "a homokozó váratlanul kilépett vagy értelmezhetetlen választ adott"}


def _hiba(uzenet: str) -> dict:
    return {"allapot": "homokozo_hiba", "ertek": None, "uzenet": uzenet, "mp": 0.0, "csucs_mb": 0.0}
